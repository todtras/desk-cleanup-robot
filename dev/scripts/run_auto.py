"""자율 실행: YOLO로 물체 판별 → 물체별 ACT 정책이 집어서 살짝 들어올림 → (쥠 감지) poses.json 자세로 수거함까지 → 놓고 home. 물체가 없을 때까지 반복.
사용 (dev 폴더에서): python scripts/run_auto.py [--seconds 20] [--device cpu] [--fps 15] [--n_action_steps 40]
- --n_action_steps: 작게(예: 40) 하면 물체 가까이서 다시 보고 위치를 보정 (빗나갈 때 시험)
- --pan_offset: 늘 같은 쪽으로 빗나가면 좌우 회전 보정. 생략하면 클래스별 PAN_OFFSET (tape 2.0)
- --smooth: 예측 동작 평활 (기본 0.3, 1이면 끔). 뚝뚝 끊기면 낮추고, 너무 굼뜨면 올림
- --fps: 정책 루프 속도. 학습 데이터는 30Hz라 15면 같은 동작을 절반 속도로 (처음 시험할 때 추천)
- 정책 실행 중 스페이스 = 지금 놓기(남은 시간 건너뜀), q = 이번 시도만 중단(그리퍼 열고 home → 다음 시도)
- 전체 종료 = 성공 질문에 q, 급하면 Ctrl+C
- 시도마다 성공 여부(y/n)를 입력받아 outputs/run_log.csv에 기록, 클래스별 성공률 출력 (로봇 없이 보기: --stats)
- 카메라 번호는 record_pick.yaml 그대로 씀 (실행마다 head/wrist가 바뀔 수 있으니 시작 화면 확인)
"""
import argparse
import csv
import ctypes
import json
import msvcrt
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import draccus
import torch
import yaml
from lerobot.cameras import opencv  # noqa: F401  (opencv 카메라 타입 등록)
from lerobot.configs.policies import PreTrainedConfig
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
CKPT = "outputs/train/act_pick_{}/checkpoints/last/pretrained_model"  # lerobot-train --output_dir 기준
PLAN = {"tape": "office", "bottle": "trash", "pen": "pen"}  # YOLO 클래스 → 수거함 (정책은 act_pick_<클래스>)
EMPTY_GRIP = 2.5  # 그리퍼가 이보다 닫혀 있으면 빈손 (펜을 쥐어도 3.9). 그리퍼 다시 캘리브레이션하면 다시 볼 것
LIFT_ACTIONS = 30  # 쥔 뒤 정책을 더 돌리는 스텝 수 (= 시연 1초 분량. 시연에서 쥔 직후 들어올리는 동작)
SEND_HZ = 60  # 모터에 보내는 빈도 (텔레옵과 같게). 정책 스텝 사이는 시간 기준 직선 보간
FPS, CONF, IMGSZ = 30, 0.3, 640  # head 첫 프레임 기준 물병 탐지: 960/0.5 → 18/31, 640/0.3 → 30/31 (새 카메라 구도 0/19 → 11/19)
PAN_OFFSET = {"tape": 2.0}  # 클래스별 shoulder_pan 보정 (실물로 맞춤). tape: 30k 체크포인트 기준 2026-10-23. 체크포인트 바꾸면 다시 맞출 것
BIN_X = 100  # head 640x480에서 수거함 구역 테이프 선의 x(약 88~115, 살짝 기울어짐). 박스 중심이 이보다 왼쪽이면 이미 정리된 물건 → 무시. 카메라 옮기면 다시 잴 것


def load_policy(path, device, n_action_steps):
    cfg = PreTrainedConfig.from_pretrained(path)
    cfg.device = device  # 학습은 cuda, 노트북 실행은 cpu일 수 있음
    cfg.n_action_steps = n_action_steps  # 예측한 100개 중 몇 개만 실행하고 다시 볼지 (작을수록 자주 다시 봄, 대신 CPU 추론 0.2초 멈춤이 잦아짐)
    policy = ACTPolicy.from_pretrained(path, config=cfg)
    pre, post = make_pre_post_processors(cfg, pretrained_path=path,
                                         preprocessor_overrides={"device_processor": {"device": device}})
    return policy, pre, post


def detect(model, robot, names):
    """head 카메라 한 장으로 탐지 → 정책이 있는 클래스 중 신뢰도 최고 (이름, 신뢰도) 또는 None"""
    img = cv2.cvtColor(robot.get_observation()["head"], cv2.COLOR_RGB2BGR)  # lerobot은 RGB, YOLO는 BGR
    boxes = model.predict(img, imgsz=IMGSZ, conf=CONF, verbose=False)[0].boxes  # imgsz 생략하면 학습값 960이 쓰임
    found = [(model.names[int(c)], float(p)) for c, p, (x, _, _, _) in zip(boxes.cls, boxes.conf, boxes.xywh)
             if model.names[int(c)] in names and x >= BIN_X]  # x = 박스 중심
    return max(found, key=lambda x: x[1]) if found else None


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
    return obs


def run_policy(robot, policy, pre, post, features, seconds, fps, smooth, pan_offset):
    """정책으로 seconds초 구동. 스페이스로 조기 종료. 물체를 쥐면 LIFT_ACTIONS만큼 더 돌려 들어올린 뒤 끝냄.
    반환: (눌린 키 ' '/'q'/None, 쥐었으면 그때 명령하던 그리퍼 값 아니면 None)
    정책은 fps로 다음 목표만 계산하고, 별도 스레드가 SEND_HZ로 시간에 맞춰 보간해서 계속 보냄
    → 관측·추론 시간이 들쭉날쭉해도 모터 명령 간격은 일정 (텔레옵처럼)"""
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
        while time.perf_counter() - t0 < seconds and k not in (" ", "q") and not (hold is not None and lift <= 0):
            t = time.perf_counter()
            obs = observe(robot, lock)
            g.append(obs["gripper.pos"])
            frame = build_dataset_frame(features, obs, prefix=OBS_STR)
            act = make_robot_action(predict_action(frame, policy, torch.device(policy.config.device), pre, post,
                                                   policy.config.use_amp), features)
            act["shoulder_pan.pos"] += pan_offset  # 모델이 좌우로 한쪽에 치우칠 때 보정
            last = seg[0][1]  # 직전 목표
            act = {m: last[m] + smooth * (act[m] - last[m]) for m in act}  # 지수 평활: 덜 학습된 ACT의 들쭉날쭉한 예측을 고르게
            tn = time.perf_counter()
            seg[0] = (interp(tn), act, tn)  # 지금 보내던 위치에서 새 목표로 (같은 시각 기준이라 뒤로 튀지 않음)
            calc.append(time.perf_counter() - t)
            if hold is None and grasped(g, fps):
                hold, lift, grip0 = act["gripper.pos"], LIFT_ACTIONS, g[-1]
                print(f"쥠 감지 (그리퍼 {g[-1]:.1f}) → {LIFT_ACTIONS}스텝 더 들어올린 뒤 수거함 자세로")
            elif hold is not None and g[-1] > grip0 + 3:  # 들어올리다 다시 벌림 = 정책이 다시 잡으려는 중 → 취소
                hold = None
                print("그리퍼를 다시 벌림 → 쥠 취소, 정책 계속")
            elif hold is not None:
                hold, lift = act["gripper.pos"], lift - 1  # 들어올리는 동안도 정책이 그리퍼를 더 조일 수 있음 → 마지막 명령값을 유지
            steps, k = steps + 1, key()
            time.sleep(max(0.0, 1 / fps - (time.perf_counter() - t)))
    finally:
        stop.set()
        th.join()
    # ponytail: 동작 묶음을 새로 예측하는 스텝은 CPU에서 0.2~0.3초 → 그동안은 목표에 멈춰 있음. 없애려면 GPU 서버 추론(async_inference)
    print(f"정책 루프 {steps / (time.perf_counter() - t0):.0f}Hz (목표 {fps}), 스텝 계산 평균 {1000 * sum(calc) / max(1, len(calc)):.0f}ms"
          f" / 최대 {1000 * max(calc, default=0):.0f}ms / 100ms 넘은 스텝 {sum(c > 0.1 for c in calc)}개")
    return k, hold


def move_to(robot, target, seconds):
    """현재 관절값에서 target까지 직선 보간으로 이동"""
    start = {k: v for k, v in robot.get_observation().items() if k.endswith(".pos")}
    n = max(1, int(seconds * FPS))
    for i in range(1, n + 1):
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


def file_rates():
    if not LOG.exists():
        return {}
    with LOG.open(encoding="utf-8-sig") as f:
        return rates((r["class"], r["success"]) for r in csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yolo", default="models/best.pt")
    ap.add_argument("--stats", action="store_true", help="로봇 없이 run_log.csv 성공률만 출력")
    ap.add_argument("--seconds", type=float, default=20, help="정책 최대 실행 시간 (녹화 episode_time_s와 비슷하게)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--n_action_steps", type=int, default=100, help="ACT 동작 묶음 중 실행할 개수(1~100). 30~50이면 가까이 가서 다시 보고 보정")
    ap.add_argument("--pan_offset", type=float, default=None, help="정책 shoulder_pan 출력에 더할 값. 생략하면 클래스별 PAN_OFFSET (늘 한쪽으로 빗나갈 때)")
    ap.add_argument("--smooth", type=float, default=0.3, help="동작 평활 (1=끔, 작을수록 부드럽지만 늦게 따라감). 10k 체크포인트 기준 0.3이면 시연 데이터 수준")
    ap.add_argument("--fps", type=float, default=FPS, help="정책 루프 속도. 낮추면 느리게 (시간도 그만큼 늘릴 것: --seconds)")
    args = ap.parse_args()
    if args.stats:
        print(f"{LOG}: {fmt(file_rates())}")
        return

    policies = {}
    for name in PLAN:
        path = CKPT.format(name)
        if Path(path).exists():
            policies[name] = load_policy(path, args.device, args.n_action_steps)
        else:
            print(f"[건너뜀] {name}: 체크포인트 없음 ({path})")
    if not policies:
        raise SystemExit("실행할 정책이 없음. lerobot-train 결과를 outputs/train/ 아래에 두기")

    robot = make_robot_from_config(draccus.decode(RobotConfig, yaml.safe_load(CFG.read_text(encoding="utf-8"))["robot"]))
    features = {**hw_to_dataset_features(robot.observation_features, OBS_STR),
                **hw_to_dataset_features(robot.action_features, ACTION)}
    model = YOLO(args.yolo)
    LOG.parent.mkdir(exist_ok=True)
    new_log = not LOG.exists()

    robot.connect()
    try:
        move_to(robot, POSES["home"], 3.0)
        with LOG.open("a", newline="", encoding="utf-8-sig") as f:
            log = csv.writer(f)
            if new_log:
                log.writerow(["time", "class", "conf", "seconds", "success"])
            session = []  # 이번 실행 기록 (class, y/n)
            while True:
                det = detect(model, robot, policies)
                if det is None:
                    cv2.imwrite("outputs/last_head.jpg", cv2.cvtColor(robot.get_observation()["head"], cv2.COLOR_RGB2BGR))
                    print("탐지된 물체 없음 → 종료. head 화면: outputs/last_head.jpg (책상이 안 보이면 카메라 번호 확인)")
                    break
                name, conf = det
                print(f"\n{name} ({conf:.2f}) → act_pick_{name} 실행. 스페이스=지금 놓기, q=이번 시도 중단")
                t0 = time.perf_counter()
                _, hold = run_policy(robot, *policies[name], features, args.seconds, args.fps, args.smooth,
                                     PAN_OFFSET.get(name, 0.0) if args.pan_offset is None else args.pan_offset)
                if hold is not None:
                    carry_and_drop(robot, PLAN[name], hold)
                else:  # 못 쥠 / 스페이스 / q / 시간 초과 → 그 자리에서 그리퍼 열고 home
                    release_and_home(robot, PLAN[name])
                ok = input("성공? (y/n, q=종료): ").strip().lower()
                if ok in ("y", "n"):
                    log.writerow([datetime.now().isoformat(timespec="seconds"), name, f"{conf:.2f}",
                                  f"{time.perf_counter() - t0:.1f}", ok])
                    f.flush()
                    session.append((name, ok))
                    print(f"성공률  이번 실행: {fmt(rates(session))}  |  파일 전체: {fmt(file_rates())}")
                if ok == "q":  # 정책 중 q는 이번 시도만 끊음 (위에서 이미 home)
                    break
    finally:
        robot.disconnect()
    print(f"\n최종 성공률  파일 전체({LOG}): {fmt(file_rates())}")


if __name__ == "__main__":
    main()
