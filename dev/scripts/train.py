"""고정 조건으로 학습하고 결과를 results.csv에 한 줄 추가. 바꾸는 건 증강 값만.
사용: python scripts/train.py 이름 [증강옵션 key=value ...]
  python scripts/train.py base
  python scripts/train.py hsv_v_high hsv_v=0.7
  python scripts/train.py geo1 degrees=15 flipud=0.5 scale=0.7
"""
import csv
import sys
from pathlib import Path

import ultralytics
from ultralytics import YOLO

DATA = "datasets/desk/data.yaml"  # 팀장이 공유한 데이터셋 경로로 맞출 것
FIXED = dict(model="yolo11n.pt", imgsz=960, epochs=100, seed=0, deterministic=True)  # 팀 공통, 바꾸지 말 것

name, extra = sys.argv[1], dict(a.split("=") for a in sys.argv[2:])
extra = {k: float(v) for k, v in extra.items()}

m = YOLO(FIXED["model"])
m.train(data=DATA, name=name, imgsz=FIXED["imgsz"], epochs=FIXED["epochs"],
        seed=FIXED["seed"], deterministic=FIXED["deterministic"], **extra)
r = m.val(data=DATA, imgsz=FIXED["imgsz"])  # best.pt 기준 val 결과

per_class = {f"AP50-95_{n}": round(float(v), 3) for n, v in zip(r.names.values(), r.box.maps)}
row = {"name": name, "ultralytics": ultralytics.__version__, "aug": extra,
       "mAP50": round(float(r.box.map50), 3), "mAP50-95": round(float(r.box.map), 3), **per_class}
f = Path("results.csv")
new = not f.exists()
with f.open("a", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(row))
    if new:
        w.writeheader()
    w.writerow(row)
print(row)
