"""시연 앞의 대기 구간 자르기: pick_<물체>_v5 → pick_<물체>_v5t (영상 다시 인코딩, 원본은 그대로)
11/6 시연은 시작 전에 1초 넘게 가만히 있던 것이 많아 v5가 '처음엔 기다리기'를 배움 → 실물에서 출발을 안 함 (실험기록 2절).
대기 = 첫 동작과 팔 5관절 차이 합이 IDLE_DEG 이내인 앞쪽 프레임. 움직이기 직전 KEEP 프레임은 남김.
사용 (서버): ~/lerobot-env/bin/python ~/trim_idle.py pick_bottle_v5 pick_eraser_v5 [--root ~/datasets] [--episodes 2 --out_suffix t_test]
"""
import argparse
from pathlib import Path

import numpy as np
import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset

IDLE_DEG = 5.0  # run_auto.IDLE_DEG와 같은 기준
KEEP = 5  # 움직이기 직전 남길 프레임 (30Hz에서 0.17초). v2 시연의 대기 중앙값 0.5초에서도 출발은 정상


def idle_len(actions):
    moved = np.abs(actions - actions[0])[:, :5].sum(1) > IDLE_DEG
    return int(moved.argmax()) if moved.any() else 0


def trim(root, name, suffix, limit=None):
    src = LeRobotDataset(f"local/{name}", root=root / name, video_backend="pyav")
    out = root / f"{name}{suffix}"
    if out.exists():
        print(f"{out} 이미 있음 → 건너뜀")
        return
    dst = LeRobotDataset.create(f"local/{name}{suffix}", src.fps, src.meta.features, root=out,
                                robot_type=src.meta.robot_type, image_writer_threads=8, vcodec="h264")  # 원본과 같은 h264
    cams = [k for k, v in src.meta.features.items() if v["dtype"] == "video"]
    acts = np.stack(src.hf_dataset.with_format("numpy")["action"])
    removed = []
    for ep in range(src.meta.total_episodes if limit is None else limit):
        a, b = int(src.meta.episodes[ep]["dataset_from_index"]), int(src.meta.episodes[ep]["dataset_to_index"])
        cut = max(0, idle_len(acts[a:b]) - KEEP)
        removed.append(cut)
        loader = torch.utils.data.DataLoader(torch.utils.data.Subset(src, range(a + cut, b)), batch_size=None, num_workers=8)
        for f in loader:  # 순서 유지 (shuffle 없음)
            frame = {"action": f["action"].numpy(), "observation.state": f["observation.state"].numpy(), "task": f["task"]}
            for k in cams:
                frame[k] = (f[k].permute(1, 2, 0) * 255).round().to(torch.uint8).numpy()
            dst.add_frame(frame)
        dst.save_episode()
        print(f"{name} ep {ep}: {b - a}프레임 중 앞 {cut} 자름", flush=True)
    dst.finalize()
    r = np.array(removed)
    print(f"===== {name}{suffix}: 에피소드 {len(r)}개, 자른 프레임 합 {r.sum()} (중앙값 {np.median(r) / src.fps:.1f}s, 1초 넘게 자른 것 {np.sum(r > src.fps)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--root", default=str(Path.home() / "datasets"))
    ap.add_argument("--out_suffix", default="t")
    ap.add_argument("--episodes", type=int, help="앞 N개 에피소드만 (시험용)")
    args = ap.parse_args()
    for name in args.names:
        trim(Path(args.root), name, args.out_suffix, args.episodes)


if __name__ == "__main__":
    main()
