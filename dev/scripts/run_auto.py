"""자율 실행: YOLO로 물체 판별 → 물체별 ACT 정책이 집어서 수거함 위까지 → 그리퍼 열기 → home. 물체가 없을 때까지 반복.
사용 (dev 폴더에서): python scripts/run_auto.py [--seconds 20] [--device cpu]
- 정책 실행 중 스페이스 = 지금 놓기(남은 시간 건너뜀), q = 전체 중단
- 시도마다 성공 여부(y/n)를 입력받아 outputs/run_log.csv에 기록 → 성공률 측정용
- 카메라 번호는 record_pick.yaml 그대로 씀 (실행마다 head/wrist가 바뀔 수 있으니 시작 화면 확인)
"""
import argparse
import csv
import json
import msvcrt
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

CFG = Path("configs/robot/record_pick.yaml")
POSES = json.loads(Path("configs/robot/poses.json").read_text(encoding="utf-8"))
LOG = Path("outputs/run_log.csv")
CKPT = "outputs/train/act_pick_{}/checkpoints/last/pretrained_model"  # lerobot-train --output_dir 기준
PLAN = {"tape": "office", "bottle": "trash", "pen": "pen"}  # YOLO 클래스 → 수거함 (정책은 act_pick_<클래스>)
FPS, CONF = 30, 0.5


def load_policy(path, device):
    cfg = PreTrainedConfig.from_pretrained(path)
    cfg.device = device  # 학습은 cuda, 노트북 실행은 cpu일 수 있음
    policy = ACTPolicy.from_pretrained(path, config=cfg)
    pre, post = make_pre_post_processors(cfg, pretrained_path=path,
                                         preprocessor_overrides={"device_processor": {"device": device}})
    return policy, pre, post


def detect(model, robot, names):
    """head 카메라 한 장으로 탐지 → 정책이 있는 클래스 중 신뢰도 최고 (이름, 신뢰도) 또는 None"""
    img = cv2.cvtColor(robot.get_observation()["head"], cv2.COLOR_RGB2BGR)  # lerobot은 RGB, YOLO는 BGR
    boxes = model.predict(img, conf=CONF, verbose=False)[0].boxes
    found = [(model.names[int(c)], float(p)) for c, p in zip(boxes.cls, boxes.conf) if model.names[int(c)] in names]
    return max(found, key=lambda x: x[1]) if found else None


def key():
    return msvcrt.getwch() if msvcrt.kbhit() else None


def run_policy(robot, policy, pre, post, features, seconds):
    """정책으로 seconds초 구동. 스페이스로 조기 종료. 반환: 눌린 키(' ', 'q') 또는 None"""
    policy.reset(); pre.reset(); post.reset()
    t0, steps, k = time.perf_counter(), 0, None
    while time.perf_counter() - t0 < seconds and k not in (" ", "q"):
        t = time.perf_counter()
        frame = build_dataset_frame(features, robot.get_observation(), prefix=OBS_STR)
        act = predict_action(frame, policy, torch.device(policy.config.device), pre, post, policy.config.use_amp)
        robot.send_action(make_robot_action(act, features))
        steps, k = steps + 1, key()
        time.sleep(max(0.0, 1 / FPS - (time.perf_counter() - t)))
    # ponytail: 노트북 CPU에선 약 20Hz (학습 데이터 30Hz) → 동작이 느려질 뿐 순서는 같음. 문제되면 GPU 노트북에서 실행
    print(f"정책 루프 {steps / (time.perf_counter() - t0):.0f}Hz (목표 {FPS})")
    return k


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yolo", default="models/best.pt")
    ap.add_argument("--seconds", type=float, default=20, help="정책 최대 실행 시간 (녹화 episode_time_s와 비슷하게)")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    policies = {}
    for name in PLAN:
        path = CKPT.format(name)
        if Path(path).exists():
            policies[name] = load_policy(path, args.device)
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
            while True:
                det = detect(model, robot, policies)
                if det is None:
                    print("탐지된 물체 없음 → 종료")
                    break
                name, conf = det
                print(f"\n{name} ({conf:.2f}) → act_pick_{name} 실행. 스페이스=지금 놓기, q=중단")
                t0 = time.perf_counter()
                k = run_policy(robot, *policies[name], features, args.seconds)
                release_and_home(robot, PLAN[name])
                ok = input("성공? (y/n, q=종료): ").strip().lower()
                if ok in ("y", "n"):
                    log.writerow([datetime.now().isoformat(timespec="seconds"), name, f"{conf:.2f}",
                                  f"{time.perf_counter() - t0:.1f}", ok])
                    f.flush()
                if k == "q" or ok == "q":
                    break
    finally:
        robot.disconnect()


if __name__ == "__main__":
    main()
