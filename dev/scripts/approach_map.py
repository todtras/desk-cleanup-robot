"""YOLO 좌표 → 접근 자세 변환식 (coarse-to-fine의 coarse 단계, 11/13)
시연마다 물체의 head 화면 위치(demo_map 표)와 "쥐기 직전" 팔 자세(그리퍼를 닫기 시작하기 LEAD프레임 전의 관측 관절값)를 모아
화면 (x, y) → 팔 5관절을 2차식으로 맞춤. 물체별 식과 물체 공용 식을 같이 만들고, 하나씩 빼고 맞춘 오차(LOO)로 확인.
결과: configs/robot/approach_fit_lead<N>.json (run_auto --approach_lead N으로 고름). 사용 (dev 폴더): python scripts/approach_map.py [--lead 30]
"""
import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

OBJECTS = ("bottle", "tape", "pen", "eraser", "paper")
V2_TO_NOW = (-23, 2)  # run_auto.V2_TO_NOW와 같음 (10/30 시연 화면 → 지금 구도)
JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
OUT = "configs/robot/approach_fit_lead{}.json"  # 리드(프레임)별로 따로 저장


def feats(xy):
    x, y = (np.asarray(xy, float) - [320, 300]).T / 100  # 화면 가운데 근처 기준, 100px 단위
    return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], 1)


def grasp_start(g):
    """그리퍼 동작에서 닫기 시작하는 프레임: 가장 크게 연 뒤 연 폭의 절반만큼 닫힌 첫 프레임"""
    p = int(np.argmax(g))
    lo = g[p:].min()
    if g[p] - lo < 3:  # 거의 안 닫음 = 쥐지 않은 에피소드
        return None
    return p + int(np.argmax(g[p:] < g[p] - 0.5 * (g[p] - lo)))


def samples(obj, lead):
    xs, poses, grips = [], [], []
    for repo, (dx, dy) in ((f"pick_{obj}_v2", V2_TO_NOW), (f"pick_{obj}_demo", (0, 0))):
        pos_file = Path(f"outputs/demo_map/{repo}.json")
        files = sorted(glob.glob(f"outputs/datasets/{repo}/data/chunk-*/file-*.parquet"))
        if not pos_file.exists() or not files:
            continue
        pos = dict(json.loads(pos_file.read_text()))
        df = pd.concat(pd.read_parquet(f) for f in files)
        for ep, g in df.groupby("episode_index"):
            p = pos.get(int(ep))
            if not p:
                continue
            g = g.sort_values("frame_index")
            act, st = np.stack(g["action"].to_numpy()), np.stack(g["observation.state"].to_numpy())
            c = grasp_start(act[:, 5])
            if c is None:
                continue
            k = max(0, c - lead)
            xs.append((p[0] + dx, p[1] + dy))
            poses.append(st[k, :5])
            grips.append(act[k, 5])
    return np.array(xs, float), np.array(poses), np.array(grips)


def fit(X, Y):
    coef, *_ = np.linalg.lstsq(feats(X), Y, rcond=None)
    return coef


def loo(X, Y):
    """하나씩 빼고 맞춘 뒤 뺀 것을 예측한 오차 (관절별 평균 절대 오차, 도)"""
    err = []
    for i in range(len(X)):
        m = np.arange(len(X)) != i
        err.append(np.abs(feats(X[i:i + 1]) @ fit(X[m], Y[m]) - Y[i]))
    return np.concatenate(err).mean(0)


def predict(entry, xy):
    """저장한 식으로 화면 위치 → 팔 5관절 (run_auto에서 씀)"""
    return dict(zip(JOINTS, (feats([xy]) @ np.array(entry["coef"]))[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", type=int, default=15, help="그리퍼를 닫기 시작하기 몇 프레임 전 자세를 접근 자세로 볼지 (30Hz)")
    args = ap.parse_args()
    out, allX, allY = {"lead": args.lead, "joints": JOINTS}, [], []
    print(f"접근 자세 = 닫기 시작 {args.lead}프레임 전. 오차는 하나씩 빼고 맞춘 값(도), 순서 {JOINTS}")
    for obj in OBJECTS:
        X, Y, G = samples(obj, args.lead)
        if len(X) < 12:
            print(f"{obj}: 시연 {len(X)}개라 건너뜀")
            continue
        e, spread = loo(X, Y), Y.std(0)
        out[obj] = {"coef": fit(X, Y).tolist(), "grip": float(np.median(G)), "n": len(X), "loo_mae": e.round(2).tolist()}
        print(f"{obj:7s} n={len(X):3d} 오차 {np.round(e, 1)} | 위치마다 다른 정도(표준편차) {np.round(spread, 1)}")
        allX.append(X), allY.append(Y)
    X, Y = np.concatenate(allX), np.concatenate(allY)
    out["all"] = {"coef": fit(X, Y).tolist(), "n": len(X), "loo_mae": loo(X, Y).round(2).tolist()}
    print(f"{'공용':7s} n={len(X):3d} 오차 {np.round(out['all']['loo_mae'], 1)}")
    Path(OUT.format(args.lead)).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"저장: {OUT.format(args.lead)}")


if __name__ == "__main__":
    main()
