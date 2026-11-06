"""자율 실행: YOLO로 물체 판별 → 물체별 ACT 정책이 집어서 살짝 들어올림 → (쥠 감지) poses.json 자세로 수거함까지 → 놓고 home. 물체가 없을 때까지 반복.
사용 (dev 폴더에서): python scripts/run_auto.py [--seconds 20] [--device cpu] [--fps 15] [--n_action_steps 40]
- --n_action_steps: 작게(예: 40) 하면 물체 가까이서 다시 보고 위치를 보정 (빗나갈 때 시험)
- 좌우 회전 보정: 기본으로 물체 위치(YOLO 박스 x)에 따라 PAN_FIT 적용 (양 끝에서 바깥쪽으로 더 도는 버릇 상쇄). --no_pan_fit으로 끄기,
  --pan_offset 값을 주면 그 값으로 고정
- --smooth: 예측 동작 평활 (기본 0.3, 1이면 끔). 뚝뚝 끊기면 낮추고, 너무 굼뜨면 올림
- --fps: 정책 루프 속도. 학습 데이터는 30Hz라 15면 같은 동작을 절반 속도로 (처음 시험할 때 추천)
- 정책 실행 중 스페이스 = 지금 놓기(남은 시간 건너뜀), q = 이번 시도만 중단(그리퍼 열고 home → 다음 시도)
- 전체 종료 = 성공 질문에 q, 급하면 Ctrl+C
- 시도마다 성공 여부(y/n)와 실패 이유(번호 또는 직접 입력)를 입력받아 outputs/run_log.csv에 기록, 클래스별 성공률 출력 (로봇 없이 보기: --stats)
- 카메라 번호는 record_pick.yaml 그대로 씀 (실행마다 head/wrist가 바뀔 수 있으니 시작 화면 확인)
- --knn: 비교 기준. 정책 없이 물체 위치와 가장 가까운 시연(_v2, _demo)의 동작을 그대로 재생. 기록은 outputs/run_log_knn.csv
  시연 위치 표가 먼저 있어야 함: python scripts/demo_map.py pick_tape_v2 pick_tape_demo ...
- --collect: 데이터 모으기 (리더 암 연결 필요). 기록은 outputs/run_log_collect.csv (기준 성공률과 섞이지 않음)
  · 빗나가려 하면 i → 팔 멈춤 → 리더를 팔로워 자세에 맞춤 (차이 표시) → i → 직접 집어 들어 올림 → i → 저장 여부. 넘겨받은 구간만 pick_<물체>_dagger에 저장. 수집 중엔 수거함까지 안 가고 그 자리에서 놓고 home
  · 정책이 혼자 깔끔하게 성공하면 쥐고 들어 올릴 때까지를 pick_<물체>_success에 저장
"""
import argparse
import csv
import ctypes
import glob
import json
import logging
import msvcrt
import os
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import draccus
import numpy as np
import pandas as pd
import torch
import yaml
from lerobot.cameras import opencv  # noqa: F401  (opencv 카메라 타입 등록)
from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.utils import build_dataset_frame, hw_to_dataset_features
from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.utils import make_robot_action
from lerobot.robots import RobotConfig, make_robot_from_config
from lerobot.robots import so_follower  # noqa: F401  (so101_follower 타입 등록)
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.control_utils import predict_action
from ultralytics import YOLO

ctypes.windll.winmm.timeBeginPeriod(1)  # 윈도우 sleep 해상도 15.6ms → 1ms (60Hz 전송 간격 유지용)
os.chdir(Path(__file__).resolve().parent.parent)  # 아래 상대경로는 dev 기준: 어느 폴더에서 실행해도 되게
CFG =Path("configs/robot/record_pick.yaml")
POSES = json.loads(Path("configs/robot/poses.json").read_text(encoding="utf-8"))
LOG = Path("outputs/run_log.csv")
COLLECT_LOG = Path("outputs/run_log_collect.csv")
V2_TO_NOW = (-23, 2)  # 10/30 시연 화면 → 11/6 화면 어긋남(px, check_head). ponytail: 카메라를 다시 옮기면 여기도 다시 잴 것
HEAD_SHIFT = None  # --head_shift: 정책·교정 녹화에 들어가는 head 화면 이동 (dx, dy)
LOG_COLS = ["time", "class", "conf", "seconds", "success", "reason", "step", "fix", "pan", "reach", "x", "y",
            "policy", "fps", "n_action_steps", "smooth", "max_seconds", "yolo", "commit"]
COMMIT = subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True, text=True).stdout.strip()  # -dirty = 커밋 안 한 수정 있음
DATA_ROOT = Path("outputs/datasets")
INTERVENE = ("i", "I", "ㅑ")  # 교정 키 (한글 입력 상태면 ㅑ로 들어옴)
ALIGN_MAX = 8.0  # 리더-팔로워 차이가 이 안이어야 넘겨받음. 쥔 물체를 떨어뜨리지 않을 정도로. 실물 보고 조정
TAKEOVER_FPS, TAKEOVER_MAX_S = 30, 40  # 시연과 같은 30Hz. 상한은 메모리 보호용 (초당 약 55MB)
REASONS = {"1": "탐지 실패", "2": "빗나감-왼쪽", "3": "빗나감-오른쪽", "4": "빗나감-앞뒤", "9": "너무 뻗음(앞)", "0": "덜 뻗음(뒤)",
           "5": "쥐었다 놓침", "6": "쥠 감지 안 됨", "7": "수거함 잘못", "8": "멈춤/시간 초과"}
# 빗나감 방향 = 그리퍼가 물체보다 어느 쪽으로 갔나, 로봇 기준 (로봇 왼쪽 = head 화면 오른쪽). 앞뒤 = 로봇에서 멀게/가깝게
REASONS_HELP = " ".join(f"{k}={v}" for k, v in REASONS.items())
CKPT = "outputs/train/act_pick_{}_v2/checkpoints/{}/pretrained_model"  # v2 = 2026-10-30 새 환경 데이터. 서버에서 scp로 받은 스텝 폴더
V3 = {"eraser", "paper"}  # v3(약한 위치 보강 녹화)가 있는 물체. --v3로 선택


def ckpt_path(name, step, v3=False):
    return CKPT.format(name, step).replace("_v2/", "_v3/") if v3 and name in V3 else CKPT.format(name, step)


def step_label(name, step, v3=False):
    """기록·보정표의 스텝 이름. v3는 'v3-050000'으로 구분 (v2 스텝용 보정값이 적용되거나 기록이 섞이지 않게)"""
    return f"v3-{step}" if v3 and name in V3 else step


PLAN = {"tape": "office", "bottle": "trash", "pen": "pen", "eraser": "pen", "paper": "trash"}  # YOLO 클래스 → 수거함 (정책은 act_pick_<클래스>)
EMPTY_GRIP = 2.5  # 그리퍼가 이보다 닫혀 있으면 빈손 (펜을 쥐어도 3.9). 그리퍼 다시 캘리브레이션하면 다시 볼 것
LIFT_ACTIONS = 30  # 쥔 뒤 정책을 더 돌리는 스텝 수 (= 시연 1초 분량. 시연에서 쥔 직후 들어올리는 동작)
SEND_HZ = 60  # 모터에 보내는 빈도 (텔레옵과 같게). 정책 스텝 사이는 시간 기준 직선 보간
FPS, CONF, IMGSZ = 30, 0.3, 640  # head 첫 프레임 기준 물병 탐지: 960/0.5 → 18/31, 640/0.3 → 30/31 (새 카메라 구도 0/19 → 11/19)
PAN_OFFSET = {}  # 클래스별 shoulder_pan 보정 (실물로 맞춤). 예전 tape 2.0은 v1 30k 기준이라 v2에서 뺌. 체크포인트 바꾸면 다시 맞출 것
# ---------- 위치별 보정 (영점 조절) ----------
# 정책은 물체가 양 끝·가까운 곳에 있을 때 일정하게 빗나감 → 물체 위치(YOLO 박스 중심 x)마다 보정값을 더함.
#  pan: shoulder_pan에 더할 도. pan은 화면 x가 클수록(로봇 왼쪽) 작아짐 → +는 로봇 오른쪽으로
#  reach: "물체가 r px(화면 y) 더 가까이 있는 것처럼" 어깨·팔꿈치를 바꿈. +는 덜 뻗음
# 보정표 configs/robot/calib.json {"물체|스텝": {"pan": [[x, 도], ...], "reach": [[x, px], ...]}}: 표 사이는 직선, 표 밖은 끝값.
# --calib로 돌리면 시도마다 "좌1 앞2"처럼 빗나간 쪽을 입력 → 그 위치 값이 고쳐져 저장됨. 정책이 보정을 약 3배로 키우니 작게.
# 표가 없으면 pan은 PAN_FIT(녹화 화면으로 잰 오차 직선 ≈ a·x + c, 10/30 물병·지우개, 물병 2만은 실물로 다시 맞춤), reach는 0
CALIB_FILE = Path("configs/robot/calib.json")
CALIB = json.loads(CALIB_FILE.read_text(encoding="utf-8")) if CALIB_FILE.exists() else {}
PAN_FIT = {("bottle", "010000"): (-0.0244, 7.14), ("bottle", "020000"): (-0.0237, 7.04),
           ("eraser", "020000"): (-0.0135, 4.02)}  # 지우개: 물병 조정을 빌린 값(+6도@520)은 실물에서 지나치게 오른쪽 → 절반에서 시작, --calib로 맞춤
PAN_FIT_X = (170, 580)  # 시연이 있는 범위 (밖은 끝값)
CALIB_STEP = {"pan": 0.5, "reach": 2.0}  # 입력 1칸 = pan 0.5도 / reach 2px
CALIB_MERGE_PX = 40  # 이 거리 안의 기존 칸은 새 값으로 바꿈
# 시연에서 물체가 y로 1px 멀어질 때 쥘 때 (어깨 들기, 팔꿈치) 변화(도/px), v2 49~50개 직선 맞춤 (10/30)
REACH_SLOPE = {"eraser": (0.389, -0.521), "bottle": (0.316, -0.206), "paper": (0.242, -0.357),
               "pen": (0.395, -0.597), "tape": (0.387, -0.535)}
# 시연에서 물체를 쥔 순간의 pan ≈ a·x + b·y + c (x = 박스 중심, y = 박스 아래쪽). 실제 시도의 pan 오차를 재는 기준 (시연끼리도 ±3도 흩어짐)
DEMO_PAN = {"bottle": (-0.2181, -0.0265, 86.36), "eraser": (-0.2668, -0.0811, 117.0)}
PAN_LOG = Path("outputs/pan_debug.csv")
JOINT_LOG = Path("outputs/joint_debug.csv")
GRASP_POSE = {}  # run_policy가 쥠을 감지한 순간의 관절값 (기록용)


def _cx(box):
    return (box[0] + box[2]) / 2


def _table(name, step, kind):
    return CALIB.get(f"{name}|{step}", {}).get(kind)


def pan_fix(name, step, box):
    t = _table(name, step, "pan")
    if t:
        return float(np.interp(_cx(box), *zip(*t)))
    a, c = PAN_FIT.get((name, step), (0.0, 0.0))
    return -(a * min(max(_cx(box), PAN_FIT_X[0]), PAN_FIT_X[1]) + c)


def reach_px(name, step, box):
    t = _table(name, step, "reach")
    return float(np.interp(_cx(box), *zip(*t))) if t else 0.0


def reach_fix(name, px):
    a, b = REACH_SLOPE.get(name, (0.0, 0.0))
    return {"shoulder_lift.pos": -a * px, "elbow_flex.pos": -b * px}


def calib_add(name, step, box, kind, delta):
    """이 위치(x)의 보정값을 지금 값 + delta로 바꿔 저장. pan 표를 처음 만들 땐 PAN_FIT 직선을 4칸으로 깔고 시작"""
    x, cur = round(_cx(box)), (pan_fix if kind == "pan" else reach_px)(name, step, box)
    entry = CALIB.setdefault(f"{name}|{step}", {})
    t = entry.get(kind) or ([[px, round(pan_fix(name, step, (px, 0, px, 0)), 2)] for px in (170, 310, 450, 580)]
                            if kind == "pan" else [])
    t = [p for p in t if abs(p[0] - x) > CALIB_MERGE_PX] + [[x, round(cur + delta, 2)]]
    entry[kind] = sorted(t)
    CALIB_FILE.write_text(json.dumps(CALIB, ensure_ascii=False, indent=1), encoding="utf-8")
    return cur + delta


def calib_input(name, step, box):
    """빗나간 방향 입력 → 보정표 수정. 좌/우 = 그리퍼가 물체보다 로봇 기준 어느 쪽, 앞 = 너무 뻗음(로봇에서 멀리), 뒤 = 덜 뻗음"""
    import re
    s = input("보정 입력 (그리퍼가 간 쪽, 로봇 기준. 예: 좌1  우2  앞1  뒤2  좌1 앞1 / 엔터=그대로): ").strip()
    for d, n in re.findall(r"(좌|우|앞|뒤)\s*(\d*\.?\d*)", s):
        n = float(n or 1)
        kind = "pan" if d in "좌우" else "reach"
        sign = {"좌": +1, "우": -1, "앞": +1, "뒤": -1}[d]  # 너무 왼쪽 → pan +(오른쪽으로), 너무 뻗음 → reach +(덜 뻗기)
        v = calib_add(name, step, box, kind, sign * n * CALIB_STEP[kind])
        print(f"  {name} x={_cx(box):.0f}: {kind} → {v:+.1f}{'도' if kind == 'pan' else 'px'} (저장: {CALIB_FILE})")


ESTOP = threading.Event()  # 웹 UI(app/real_cleaner.py)의 비상정지: 정책 루프와 move_to가 즉시 멈춤. 터미널 실행에서는 안 씀
BIN_X = 100  # head 640x480에서 수거함 구역 테이프 선의 x(약 88~115, 살짝 기울어짐). 박스 중심이 이보다 왼쪽이면 이미 정리된 물건 → 무시. 카메라 옮기면 다시 잴 것


def load_policy(path, device, n_action_steps):
    cfg = PreTrainedConfig.from_pretrained(path)
    cfg.device = device  # 학습은 cuda, 노트북 실행은 cpu일 수 있음
    cfg.n_action_steps = n_action_steps  # 예측한 100개 중 몇 개만 실행하고 다시 볼지 (작을수록 자주 다시 봄, 대신 CPU 추론 0.2초 멈춤이 잦아짐)
    policy = ACTPolicy.from_pretrained(path, config=cfg)
    pre, post = make_pre_post_processors(cfg, pretrained_path=path,
                                         preprocessor_overrides={"device_processor": {"device": device}})
    return policy, pre, post


def detect_all(model, head_rgb, names):
    """head 한 장 → 정책이 있는 클래스의 [(이름, 신뢰도, (x1, y1, x2, y2))]. 수거함 구역(박스 중심 x < BIN_X)은 제외"""
    img = cv2.cvtColor(head_rgb, cv2.COLOR_RGB2BGR)  # lerobot은 RGB, YOLO는 BGR
    boxes = model.predict(img, imgsz=IMGSZ, conf=CONF, verbose=False)[0].boxes  # imgsz 생략하면 학습값 960이 쓰임
    return [(model.names[int(c)], float(p), tuple(int(v) for v in xyxy))
            for c, p, xyxy in zip(boxes.cls, boxes.conf, boxes.xyxy)
            if model.names[int(c)] in names and (xyxy[0] + xyxy[2]) / 2 >= BIN_X]


def key():
    return msvcrt.getwch() if msvcrt.kbhit() else None


def grasped(g, fps):
    """그리퍼 관측값 기록 g로 '물체를 쥐었다' 판단: 가장 닫힌 값보다 5 이상 열었다가 → 그 뒤 최대에서 5 이상 닫힌 채 0.5초 멈춤.
    (home 그리퍼가 13.9로 반쯤 열려 있어 시작하자마자 닫히는 건 '여는 동작'이 없으니 무시)
    녹화 데이터 기준: 최대 열림 17~32 → 쥔 값 테이프 6, 물병 15.5, 펜 3.9, 빈손으로 끝까지 닫으면 약 1"""
    n = max(3, round(fps * 0.5))
    if len(g) <= n:
        return False
    lo = g[0]
    for j, x in enumerate(g[:-n]):
        lo = min(lo, x)
        if x - lo > 5:  # 여는 동작 시작
            return (max(g[j:-n]) - g[-1] > 5 and max(g[-n:]) - min(g[-n:]) < 0.5
                    and g[-1] > EMPTY_GRIP)  # 끝까지 닫혔으면 빈손
    return False


def observe(robot, lock):
    """robot.get_observation()과 같은 내용. 시리얼 버스 읽기만 잠가서 전송 스레드가 오래 기다리지 않게"""
    with lock:
        obs = {f"{m}.pos": v for m, v in robot.bus.sync_read("Present_Position").items()}
    obs.update({k: cam.read_latest() for k, cam in robot.cameras.items()})  # 카메라는 자체 스레드가 받은 최신 프레임
    if HEAD_SHIFT:
        obs["head"] = shift_image(obs["head"], *HEAD_SHIFT)
    return obs


def shift_image(img, dx, dy):
    """화면을 (dx, dy)px 옮김. 바깥은 가장자리 색으로. ponytail: 이동만 보정, 회전(약 0.5도)은 못 고침 → 근본 해결은 카메라를 다시 맞추기"""
    return cv2.warpAffine(img, np.float32([[1, 0, dx], [0, 1, dy]]), img.shape[1::-1], borderMode=cv2.BORDER_REPLICATE)


def run_policy(robot, policy, pre, post, features, seconds, fps, smooth, pan_offset, poll_key=key, extra=None, rec=None):
    """정책으로 seconds초 구동. 스페이스로 조기 종료. 물체를 쥐면 LIFT_ACTIONS만큼 더 돌려 들어올린 뒤 끝냄.
    반환: (눌린 키 ' '/'q'/None, 쥐었으면 그때 명령하던 그리퍼 값 아니면 None)
    poll_key: 키 입력 대신 쓸 함수 (웹 UI가 ' '/'q'를 넘김). ESTOP이 켜지면 바로 멈춤
    정책은 fps로 다음 목표만 계산하고, 별도 스레드가 SEND_HZ로 시간에 맞춰 보간해서 계속 보냄
    → 관측·추론 시간이 들쭉날쭉해도 모터 명령 간격은 일정 (텔레옵처럼)
    rec: 리스트를 주면 스텝마다 (관측, 보낸 명령)을 쌓고, 교정 키로도 멈춤"""
    stops = (" ", "q") + (INTERVENE if rec is not None else ())
    policy.reset(); pre.reset(); post.reset()
    lock, stop = threading.Lock(), threading.Event()  # 같은 시리얼 버스를 두 스레드가 씀 → 한 번에 하나만
    obs = observe(robot, lock)
    now = {m: obs[m] for m in features[ACTION]["names"]}
    seg = [(now, now, time.perf_counter())]  # (출발, 목표, 시작 시각). 튜플 통째로 바꿔서 스레드 간 일관성 유지

    def interp(t):
        fr, to, ts = seg[0]
        a = min(1.0, (t - ts) * fps)  # 정책 한 스텝(1/fps초)에 걸쳐 출발 → 목표
        return {m: fr[m] + (to[m] - fr[m]) * a for m in to}

    def sender():
        nxt = time.perf_counter()
        while not stop.is_set():
            with lock:
                robot.send_action(interp(time.perf_counter()))
            nxt += 1 / SEND_HZ  # 마감 시각 기준: 보내는 데 걸린 시간만큼 밀리지 않게
            time.sleep(max(0.0, nxt - time.perf_counter()))

    th = threading.Thread(target=sender, daemon=True)
    th.start()
    t0, steps, k, calc = time.perf_counter(), 0, None, []
    g, hold, lift = [], None, 0  # 그리퍼 관측 기록, 쥔 순간의 그리퍼 명령값, 쥔 뒤 남은 들어올리기 스텝
    try:
        while (time.perf_counter() - t0 < seconds and k not in stops and not (hold is not None and lift <= 0)
               and not ESTOP.is_set()):
            t = time.perf_counter()
            obs = observe(robot, lock)
            g.append(obs["gripper.pos"])
            frame = build_dataset_frame(features, obs, prefix=OBS_STR)
            act = make_robot_action(predict_action(frame, policy, torch.device(policy.config.device), pre, post,
                                                   policy.config.use_amp), features)
            act["shoulder_pan.pos"] += pan_offset  # 모델이 좌우로 한쪽에 치우칠 때 보정
            for m, v in (extra or {}).items():  # 그 밖의 관절 보정 (reach_fix: 덜/더 뻗기)
                act[m] += v
            last = seg[0][1]  # 직전 목표
            act = {m: last[m] + smooth * (act[m] - last[m]) for m in act}  # 지수 평활: 덜 학습된 ACT의 들쭉날쭉한 예측을 고르게
            tn = time.perf_counter()
            seg[0] = (interp(tn), act, tn)  # 지금 보내던 위치에서 새 목표로 (같은 시각 기준이라 뒤로 튀지 않음)
            if rec is not None:
                rec.append((obs, act))
            calc.append(time.perf_counter() - t)
            if hold is None and grasped(g, fps):
                hold, lift, grip0 = act["gripper.pos"], LIFT_ACTIONS, g[-1]
                GRASP_POSE.clear()
                GRASP_POSE.update({m: obs[m] for m in features[ACTION]["names"]})
                print(f"쥠 감지 (그리퍼 {g[-1]:.1f}) → {LIFT_ACTIONS}스텝 더 들어올린 뒤 수거함 자세로")
            elif hold is not None and g[-1] > grip0 + 3:  # 들어올리다 다시 벌림 = 정책이 다시 잡으려는 중 → 취소
                hold = None
                print("그리퍼를 다시 벌림 → 쥠 취소, 정책 계속")
            elif hold is not None:
                hold, lift = act["gripper.pos"], lift - 1  # 들어올리는 동안도 정책이 그리퍼를 더 조일 수 있음 → 마지막 명령값을 유지
            steps, k = steps + 1, poll_key()
            time.sleep(max(0.0, 1 / fps - (time.perf_counter() - t)))
    finally:
        stop.set()
        th.join()
    # ponytail: 동작 묶음을 새로 예측하는 스텝은 CPU에서 0.2~0.3초 → 그동안은 목표에 멈춰 있음. 없애려면 GPU 서버 추론(async_inference)
    print(f"정책 루프 {steps / (time.perf_counter() - t0):.0f}Hz (목표 {fps}), 스텝 계산 평균 {1000 * sum(calc) / max(1, len(calc)):.0f}ms"
          f" / 최대 {1000 * max(calc, default=0):.0f}ms / 100ms 넘은 스텝 {sum(c > 0.1 for c in calc)}개")
    return k, hold


def load_knn(name):
    """시연 표 [(x, y, 이름, 에피소드, 동작 배열)]. 위치는 demo_map 표(json)에서 읽음 (영상을 여기서 읽으면 av 때문에 카메라가 안 열림)"""
    table = []
    for repo, dx, dy in ((f"pick_{name}_v2", *V2_TO_NOW), (f"pick_{name}_demo", 0, 0)):
        pos_file = Path(f"outputs/demo_map/{repo}.json")
        files = glob.glob(str(DATA_ROOT / repo / "data/chunk-*/file-*.parquet"))
        if not files:
            continue
        if not pos_file.exists():
            raise SystemExit(f"위치 표 없음: python scripts/demo_map.py {repo}")
        pos = dict(json.loads(pos_file.read_text()))
        df = pd.concat(pd.read_parquet(f, columns=["episode_index", "frame_index", "action"]) for f in files)
        if set(df["episode_index"].unique()) - set(pos):
            raise SystemExit(f"위치 표가 오래됨: python scripts/demo_map.py {repo}")
        for ep, g in df.groupby("episode_index"):
            if pos[ep]:
                table.append((pos[ep][0] + dx, pos[ep][1] + dy, repo, int(ep), np.stack(g.sort_values("frame_index")["action"].to_numpy())))
    return table


def nearest_demo(table, box):
    """박스 중심과 시작 위치가 가장 가까운 시연, 거리(px)"""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    d = min(table, key=lambda t: (t[0] - cx) ** 2 + (t[1] - cy) ** 2)
    return d, float(np.hypot(d[0] - cx, d[1] - cy))


def run_replay(robot, actions, names, fps, poll_key=key):
    """시연 동작 재생 (첫 자세까지 1초, 이후 fps로). run_policy와 같은 반환: (눌린 키, 쥐었으면 마지막 그리퍼 명령 아니면 None). 끝까지 재생해야 들어 올림까지 끝남"""
    move_to(robot, dict(zip(names, actions[0].tolist())), 1.0)
    g, grip, k, next_read, t0, seen = [], names.index("gripper.pos"), None, 0.0, time.perf_counter(), False
    while not ESTOP.is_set() and k not in (" ", "q"):
        t = (time.perf_counter() - t0) * fps
        if t >= len(actions) - 1:
            break
        i, a = int(t), t - int(t)
        robot.send_action(dict(zip(names, (actions[i] + (actions[i + 1] - actions[i]) * a).tolist())))
        if t >= next_read:  # 정책 실행과 같은 간격으로 쥠 판단
            g.append(robot.bus.sync_read("Present_Position")["gripper"])
            seen, next_read, k = seen or grasped(g, fps), t + 1, poll_key()
        time.sleep(1 / SEND_HZ)
    return k, float(actions[-1][grip]) if seen else None


def takeover(robot, teleop, features, poll_key=key):
    """팔은 멈춘 채 리더를 맞추게 한 뒤 넘겨받아 30Hz로 녹화. 반환: ([(관측, 리더 명령)], 마지막 그리퍼 명령), q면 (None, None)"""
    names, lock = features[ACTION]["names"], threading.Lock()
    print("팔 멈춤. 리더를 팔로워 자세에 맞추고 i (q=이번 시도 버리기)")
    while True:
        now, lead = observe(robot, lock), teleop.get_action()
        diff = {m: lead[m] - now[m] for m in names}
        worst = max(abs(v) for v in diff.values())
        print("\r  리더-팔로워: " + " ".join(f"{m.split('.')[0][:5]} {v:+5.1f}" for m, v in diff.items()) + f"  최대 {worst:4.1f} ", end="", flush=True)
        k = poll_key()
        if k == "q" or ESTOP.is_set():
            print()
            return None, None
        if k in INTERVENE:
            if worst <= ALIGN_MAX:
                break
            print(f"\n  차이가 {ALIGN_MAX:.0f}보다 큼 → 더 맞추고 다시 i")
        time.sleep(0.05)
    start = {m: now[m] for m in names}
    for i in range(1, 16):  # 남은 차이를 0.5초에 걸쳐 없앰 (팔이 튀지 않게). 이 구간은 저장 안 함
        lead = teleop.get_action()
        robot.send_action({m: start[m] + (lead[m] - start[m]) * i / 15 for m in names})
        time.sleep(1 / TAKEOVER_FPS)
    print(f"\n녹화 중: 집어서 들어 올린 뒤 i (q=버리기, 최대 {TAKEOVER_MAX_S}초)")
    frames, t0, act = [], time.perf_counter(), lead
    while time.perf_counter() - t0 < TAKEOVER_MAX_S and not ESTOP.is_set():
        t = time.perf_counter()
        obs, act = observe(robot, lock), teleop.get_action()
        robot.send_action(act)
        frames.append((obs, act))
        k = poll_key()
        if k == "q":
            return None, None
        if k in INTERVENE:
            break
        time.sleep(max(0.0, 1 / TAKEOVER_FPS - (time.perf_counter() - t)))
    hz = len(frames) / (time.perf_counter() - t0)
    print(f"{len(frames)}프레임, {hz:.0f}Hz" + (" ← 30Hz보다 많이 느림. 동작 속도가 시연과 달라짐" if hz < 25 else ""))
    return frames, act["gripper.pos"]


class Collector:
    """모은 시도를 물체·종류별 데이터셋에 에피소드로 저장. 기존 데이터셋은 건드리지 않음 → 재학습 때 합침"""

    def __init__(self, features, robot_type, task):
        self.features, self.robot_type, self.task, self.open = features, robot_type, task, {}

    def _get(self, repo):
        if repo not in self.open:
            root = DATA_ROOT / repo
            opts = dict(root=root, vcodec="h264", streaming_encoding=True)  # record_pick.yaml과 같은 인코딩
            self.open[repo] = (LeRobotDataset(f"local/{repo}", **opts) if (root / "meta/info.json").exists() else
                               LeRobotDataset.create(f"local/{repo}", FPS, self.features, robot_type=self.robot_type, **opts))
        return self.open[repo]

    def save(self, kind, name, frames):
        repo = f"pick_{name}_{kind}"
        ds = self._get(repo)
        for obs, act in frames:
            ds.add_frame({**build_dataset_frame(self.features, obs, OBS_STR),
                          **build_dataset_frame(self.features, act, ACTION), "task": self.task})
        ds.save_episode()
        print(f"저장: {repo} {ds.num_episodes}개 ({len(frames)}프레임)")

    def close(self):
        for ds in self.open.values():
            ds.finalize()  # 안 하면 parquet이 깨짐


def move_to(robot, target, seconds):
    """현재 관절값에서 target까지 직선 보간으로 이동"""
    start = {k: v for k, v in robot.get_observation().items() if k.endswith(".pos")}
    n = max(1, int(seconds * FPS))
    for i in range(1, n + 1):
        if ESTOP.is_set():
            return
        robot.send_action({k: start[k] + (target[k] - start[k]) * i / n for k in target})
        time.sleep(1 / FPS)


def release_and_home(robot, bin_name):
    now = {k: v for k, v in robot.get_observation().items() if k.endswith(".pos")}
    move_to(robot, {**now, "gripper.pos": POSES[f"bin_{bin_name}_drop"]["gripper.pos"]}, 0.5)  # 자세 그대로 그리퍼만 열기
    time.sleep(0.5)
    move_to(robot, POSES["home"], 3.0)


def carry_and_drop(robot, bin_name, hold):
    """쥔 채로 (정책이 들어올린 자세에서 바로) 수거함 위 → 놓는 자세로 내려서 그리퍼 열기 → home"""
    keep = lambda pose: {**POSES[pose], "gripper.pos": hold}  # 이동 중엔 쥔 그리퍼 값 유지
    move_to(robot, keep(f"bin_{bin_name}_above"), 3.0)
    move_to(robot, keep(f"bin_{bin_name}_drop"), 1.0)
    move_to(robot, POSES[f"bin_{bin_name}_drop"], 0.5)  # 그리퍼 열기
    time.sleep(0.5)
    move_to(robot, POSES["home"], 3.0)


def rates(rows):
    """[(class, 'y'/'n'), ...] → {class: (성공, 시도)}"""
    out = {}
    for c, ok in rows:
        y, n = out.get(c, (0, 0))
        out[c] = (y + (ok == "y"), n + 1)
    return out


def fmt(r):
    return ", ".join(f"{c} {y}/{n} ({100 * y / n:.0f}%)" for c, (y, n) in sorted(r.items())) or "기록 없음"


def tag(r):
    """기록 한 줄 → 'bottle 보정O' 처럼 물체 + 보정 여부 (예전 기록엔 fix 칸이 없어 물체만)"""
    step = f" {r['step']}" if r.get("step") else ""  # 체크포인트끼리 비교할 때 성공률이 섞이지 않게
    opts = f" a{r['n_action_steps']} f{r['fps']}" if r.get("n_action_steps") else ""  # 옵션이 다른 시도도 섞이지 않게
    return r["class"] + step + opts + {"on": " 보정O", "off": " 보정X"}.get(r.get("fix") or "", "")


def zone(r):
    """head 화면 x → 위치 구간 (로봇 기준. 로봇 왼쪽 = 화면 오른쪽). 경계는 약했던 양 끝 기준"""
    x = int(r.get("x") or -1)
    return "?" if x < 0 else "로봇오른쪽" if x < 250 else "로봇왼쪽" if x > 420 else "가운데"


def file_rates():
    if not LOG.exists():
        return {}
    with LOG.open(encoding="utf-8-sig") as f:
        return rates((tag(r), r["success"]) for r in csv.DictReader(f))


def rotate_old_log(log=None):
    """칸이 다른 예전 기록은 run_log_MMDD.csv로 옮겨 보관 (같은 파일에 칸이 어긋나게 섞이지 않게)"""
    log = log or LOG
    if not log.exists():
        return
    with log.open(encoding="utf-8-sig") as f:
        if next(csv.reader(f), None) == LOG_COLS:
            return
    log.rename(log.with_name(f"{log.stem}_{datetime.fromtimestamp(log.stat().st_mtime):%m%d}{log.suffix}"))


def run_meta(args, name):
    """시도마다 남기는 버전·옵션. 보고서에서 어떤 조건의 결과인지 이 칸들로 구분"""
    return [ckpt_path(name, args.step, args.v3), args.fps, args.n_action_steps, args.smooth, args.seconds, args.yolo, COMMIT]


def main():
    global LOG, HEAD_SHIFT
    ap = argparse.ArgumentParser()
    ap.add_argument("--yolo", default="models/best.pt")
    ap.add_argument("--step", default="010000", help="체크포인트 스텝 폴더 (010000 ~ 100000)")
    ap.add_argument("--v3", action="store_true", help="지우개·종이는 v3 체크포인트 사용 (나머지 물체는 v2)")
    ap.add_argument("--stats", action="store_true", help="로봇 없이 run_log.csv 성공률만 출력")
    ap.add_argument("--seconds", type=float, default=20, help="정책 최대 실행 시간 (녹화 episode_time_s와 비슷하게)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--n_action_steps", type=int, default=100, help="ACT 동작 묶음 중 실행할 개수(1~100). 30~50이면 가까이 가서 다시 보고 보정")
    ap.add_argument("--pan_offset", type=float, default=None, help="정책 shoulder_pan 출력에 더할 값. 생략하면 클래스별 PAN_OFFSET (늘 한쪽으로 빗나갈 때)")
    ap.add_argument("--smooth", type=float, default=0.3, help="동작 평활 (1=끔, 작을수록 부드럽지만 늦게 따라감). 10k 체크포인트 기준 0.3이면 시연 데이터 수준")
    ap.add_argument("--no_pan_fit", action="store_true", help="위치별 좌우 회전 보정(PAN_FIT) 끄기 (비교 시험용)")
    ap.add_argument("--calib", action="store_true", help="보정 모드: 시도마다 빗나간 쪽(좌/우/앞/뒤)을 입력하면 configs/robot/calib.json 보정표가 고쳐짐")
    ap.add_argument("--reach_px", type=float, default=None, help="뻗는 거리 보정: 물체가 이만큼(px) 가까이 있는 것처럼 (+ = 덜 뻗음). 생략하면 보정표(calib.json)")
    ap.add_argument("--pan_scale", type=float, default=1.0, help="PAN_FIT 보정 배율. 실제 로봇 오차가 녹화로 잰 것보다 크면 키움 (outputs/pan_debug.csv 차이가 0에 가깝게)")
    ap.add_argument("--fps", type=float, default=FPS, help="정책 루프 속도. 낮추면 느리게 (시간도 그만큼 늘릴 것: --seconds)")
    ap.add_argument("--collect", action="store_true", help="교정(i)·성공 시도 저장 모드. 맨 위 설명 참고")
    ap.add_argument("--knn", action="store_true", help="정책 대신 가장 가까운 시연 재생 (비교 기준). 맨 위 설명 참고")
    ap.add_argument("--head_shift", type=float, nargs=2, metavar=("DX", "DY"), help="head 화면을 옮겨 학습 때 구도에 맞춤 (check_head의 dx, dy 부호 반대로). 기록은 run_log_shift_<dx>_<dy>.csv")
    args = ap.parse_args()
    if args.head_shift:
        HEAD_SHIFT = args.head_shift
        LOG = LOG.with_name(f"run_log_shift_{args.head_shift[0]:g}_{args.head_shift[1]:g}.csv")  # 기준 측정과 섞이지 않게
    if args.collect:
        LOG = COLLECT_LOG
    if args.knn:
        if args.collect:
            raise SystemExit("--knn과 --collect는 함께 못 씀")
        LOG = LOG.with_name("run_log_knn.csv")
    if args.stats:
        print(f"{LOG}: {fmt(file_rates())}")
        if LOG.exists():
            with LOG.open(encoding="utf-8-sig") as f:
                fails = Counter((tag(r), r.get("reason") or "?") for r in csv.DictReader(f) if r["success"] == "n")
            for (c, why), n in sorted(fails.items()):
                print(f"  실패 {c} - {why}: {n}")
            with LOG.open(encoding="utf-8-sig") as f:
                by_zone = rates((f"{tag(r)} {zone(r)}", r["success"]) for r in csv.DictReader(f))
            print("위치별:\n  " + fmt(by_zone).replace(", ", "\n  "))
        return

    policies = {}
    logging.disable(logging.WARNING)  # 체크포인트마다 "cuda 없음 → cpu" 경고 2줄씩 (무해)
    print(f"정책 불러오는 중: {', '.join(PLAN)}")
    for name in PLAN:
        path = ckpt_path(name, args.step, args.v3)
        if args.knn:
            policies[name] = load_knn(name)
        elif Path(path).exists():
            policies[name] = load_policy(path, args.device, args.n_action_steps)
        else:
            print(f"[건너뜀] {name}: 체크포인트 없음 ({path})")
    logging.disable(logging.NOTSET)
    if not policies:
        raise SystemExit("실행할 정책이 없음. lerobot-train 결과를 outputs/train/ 아래에 두기")

    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    robot = make_robot_from_config(draccus.decode(RobotConfig, cfg["robot"]))
    features = {**hw_to_dataset_features(robot.observation_features, OBS_STR),
                **hw_to_dataset_features(robot.action_features, ACTION)}
    model = YOLO(args.yolo)
    LOG.parent.mkdir(exist_ok=True)
    rotate_old_log()
    new_log = not LOG.exists()
    teleop, collector = None, None
    if args.collect:
        from lerobot.teleoperators import TeleoperatorConfig, make_teleoperator_from_config, so_leader  # noqa: F401
        teleop = make_teleoperator_from_config(draccus.decode(TeleoperatorConfig, cfg["teleop"]))
        collector = Collector(features, robot.name, cfg["dataset"]["single_task"])

    robot.connect()
    if teleop:
        teleop.connect()
    try:
        move_to(robot, POSES["home"], 3.0)
        with LOG.open("a", newline="", encoding="utf-8-sig") as f:
            log = csv.writer(f)
            if new_log:
                log.writerow(LOG_COLS)
            session = []  # 이번 실행 기록 (class, y/n)
            while True:
                found = detect_all(model, robot.get_observation()["head"], policies)
                det = max(found, key=lambda d: d[1]) if found else None
                if det is None:
                    cv2.imwrite("outputs/last_head.jpg", cv2.cvtColor(robot.get_observation()["head"], cv2.COLOR_RGB2BGR))
                    print("탐지된 물체 없음 → 종료. head 화면: outputs/last_head.jpg (책상이 안 보이면 카메라 번호 확인)")
                    break
                name, conf, box = det
                step = step_label(name, args.step, args.v3)
                pan = PAN_OFFSET.get(name, 0.0) + (0.0 if args.no_pan_fit else args.pan_scale * pan_fix(name, step, box))
                if args.pan_offset is not None:
                    pan = args.pan_offset
                reach = reach_px(name, step, box) if args.reach_px is None else args.reach_px
                print(f"\n{name} ({conf:.2f}, x={(box[0] + box[2]) // 2}, y={(box[1] + box[3]) // 2}) → act_pick_{name} {step} 실행, "
                      f"pan 보정 {pan:+.1f}도, 거리 보정 {reach:+.0f}px. 스페이스=지금 놓기, q=이번 시도 중단")
                t0 = time.perf_counter()
                GRASP_POSE.clear()
                rec = [] if args.collect else None
                meta = run_meta(args, name)
                if args.knn:
                    (dx, dy, repo, ep, actions), dist = nearest_demo(policies[name], box)
                    step, meta[0] = "knn", f"{repo}#{ep} d={dist:.0f}px"
                    print(f"가장 가까운 시연: {meta[0]}")
                    k, hold = run_replay(robot, actions, features[ACTION]["names"], args.fps)
                else:
                    k, hold = run_policy(robot, *policies[name], features, args.seconds, args.fps, args.smooth, pan,
                                         extra=reach_fix(name, reach), rec=rec)
                if args.collect and k in INTERVENE:
                    frames, grip = takeover(robot, teleop, features)
                    keep = bool(frames) and input("쥐고 들어 올렸나요? 저장하고 수거함으로 y / 버리기 n: ").strip().lower() == "y"
                    if keep:
                        collector.save("dagger", name, frames)
                    release_and_home(robot, PLAN[name])  # 수집 중엔 수거함까지 안 감: 그 자리에서 놓고 home
                    log.writerow([datetime.now().isoformat(timespec="seconds"), name, f"{conf:.2f}", f"{time.perf_counter() - t0:.1f}", "n",
                                  "교정 저장" if keep else "교정 버림", step, "off", f"{pan:.2f}", f"{reach:.1f}",
                                  (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, *run_meta(args, name)])
                    f.flush()
                    if input("다음 물체를 놓고 Enter (q=종료): ").strip().lower() == "q":
                        break
                    continue
                new = not JOINT_LOG.exists()
                with JOINT_LOG.open("a", encoding="utf-8") as jf:  # 쥔 순간 관절 (쥠 감지 못 하면 빈칸) — 거리 보정 맞출 때 참고
                    jf.write(("time,class,step,x,y,pan_fix,reach_px,pan,lift,elbow,wflex,held\n" if new else "") +
                             f"{datetime.now():%H:%M:%S},{name},{step},{(box[0] + box[2]) // 2},{(box[1] + box[3]) // 2},"
                             f"{pan:.2f},{reach:.0f}," + ",".join(f"{GRASP_POSE[m]:.1f}" if m in GRASP_POSE else ""
                             for m in ("shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos")) +
                             f",{hold is not None}\n")
                if name in DEMO_PAN:  # 실제 pan 오차 재기: 정책이 끝난 자세(쥐고 들어 올린 직후) vs 시연에서 이 위치 물체를 쥔 pan
                    a, b, c = DEMO_PAN[name]
                    cx, by, end = (box[0] + box[2]) / 2, box[3], robot.get_observation()["shoulder_pan.pos"]
                    want = a * cx + b * by + c
                    print(f"[pan] 끝 {end:.1f}도, 시연 기준 {want:.1f}도 → 차이 {end - want:+.1f}도 (보정 {pan:+.1f} 포함)")
                    new = not PAN_LOG.exists()
                    with PAN_LOG.open("a", encoding="utf-8") as pf:
                        pf.write(("time,class,step,x,y,pan_fix,end_pan,demo_pan,held\n" if new else "") +
                                 f"{datetime.now():%H:%M:%S},{name},{step},{cx:.0f},{by},{pan:.2f},{end:.2f},{want:.2f},{hold is not None}\n")
                if hold is not None and not args.collect:
                    carry_and_drop(robot, PLAN[name], hold)
                else:  # 못 쥠 / 스페이스 / q / 시간 초과 / 수집 중 → 그 자리에서 그리퍼 열고 home
                    release_and_home(robot, PLAN[name])
                ok = input("성공? (y/n, q=종료): ").strip().lower()
                if ok in ("y", "n"):
                    reason = ""
                    if ok == "n":
                        r = input(f"실패 이유 번호 또는 직접 입력 ({REASONS_HELP}) [빗나감 = 그리퍼가 물체보다 로봇 기준 어느 쪽]: ").strip()
                        reason = "+".join(REASONS.get(p.strip(), p.strip()) for p in r.split(","))  # "2, 9"처럼 여러 개 가능
                    fix = "off" if abs(pan) < 1e-6 and abs(reach) < 1e-6 else "on"  # 실제로 더한 보정 기준
                    row = [datetime.now().isoformat(timespec="seconds"), name, f"{conf:.2f}", f"{time.perf_counter() - t0:.1f}",
                           ok, reason, step, fix, f"{pan:.2f}", f"{reach:.1f}", (box[0] + box[2]) // 2, (box[1] + box[3]) // 2,
                           *meta]
                    log.writerow(row)
                    f.flush()
                    session.append((tag({"class": name, "step": step, "fix": fix, "fps": args.fps, "n_action_steps": args.n_action_steps}), ok))
                    if args.collect and ok == "y":
                        if hold is None:
                            print("쥠 감지가 안 되어 저장 안 함 (시도가 언제 끝났는지 알 수 없음)")
                        elif input("깔끔한 성공인가요? 저장 Enter / 안 함 n: ").strip().lower() != "n":
                            collector.save("success", name, rec)
                    print(f"성공률  이번 실행: {fmt(rates(session))}  |  파일 전체: {fmt(file_rates())}")
                    if args.calib:
                        calib_input(name, step, box)
                if ok == "q":  # 정책 중 q는 이번 시도만 끊음 (위에서 이미 home)
                    break
    finally:
        if collector:
            collector.close()
        if teleop:
            teleop.disconnect()
        robot.disconnect()
    print(f"\n최종 성공률  파일 전체({LOG}): {fmt(file_rates())}")


if __name__ == "__main__":
    main()
