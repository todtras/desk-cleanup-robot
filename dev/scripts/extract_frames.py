"""영상 -> 학습용 프레임. 사용:
  python scripts/extract_frames.py clip1.mp4 clip2.mp4 --split train
  python scripts/extract_frames.py clip3.mp4 --split val
val은 반드시 train과 다른 영상(다른 배치/배경)으로 — 같은 영상 프레임을 섞으면 검증 점수가 부풀려진다.
"""
import argparse
from pathlib import Path
import cv2

ap = argparse.ArgumentParser()
ap.add_argument("videos", nargs="+")
ap.add_argument("--split", choices=["train", "val"], required=True)
ap.add_argument("--long", type=int, default=960, help="긴 변 크기 = 학습 imgsz와 동일하게 (0이면 원본)")
ap.add_argument("--every", type=int, default=10, help="N프레임마다 후보 (30fps면 약 0.33초)")
ap.add_argument("--diff", type=float, default=4.0, help="직전 저장 프레임과 평균 차이가 이보다 작으면 스킵(중복 제거)")
ap.add_argument("--out", default="datasets/desk/images")
a = ap.parse_args()

out = Path(a.out) / a.split
out.mkdir(parents=True, exist_ok=True)
for v in a.videos:
    cap = cv2.VideoCapture(v)
    prev, n, saved = None, 0, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        n += 1
        if n % a.every:
            continue
        if a.long:
            s = a.long / max(f.shape[:2])
            f = cv2.resize(f, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(cv2.resize(f, (64, 36)), cv2.COLOR_BGR2GRAY)
        if prev is not None and cv2.absdiff(g, prev).mean() < a.diff:
            continue
        prev = g
        cv2.imwrite(str(out / f"{Path(v).stem}_{n:05d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 95])
        saved += 1
    print(f"{v}: {saved}장 저장 -> {out}")
