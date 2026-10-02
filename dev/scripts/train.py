"""고정 조건으로 학습하고 결과를 results.csv에 한 줄 추가. 바꾸는 건 증강 값만.
사용: python scripts/train.py 이름 [증강옵션 key=value ...]
  python scripts/train.py base
  python scripts/train.py hsv_v_high hsv_v=0.7
  python scripts/train.py geo1 degrees=15 flipud=0.5 scale=0.7
"""
import csv
import os
import sys
from pathlib import Path

import ultralytics
from ultralytics import YOLO

PROJECT = str(Path(__file__).resolve().parent.parent / "runs" / "desk")  # 절대경로: 전역 설정(settings.json)과 무관하게 dev/runs/desk에 저장
DATA = os.environ.get("DATA", "datasets/desk/data.yaml")  # 공유받은 데이터셋의 data.yaml 경로
FIXED = dict(model="yolo11n.pt", imgsz=960, epochs=int(os.environ.get("EPOCHS", 100)), seed=0, deterministic=True)  # 팀 공통, EPOCHS는 시험용으로만 바꿀 것

name, extra = sys.argv[1], dict(a.split("=") for a in sys.argv[2:])
extra = {k: float(v) for k, v in extra.items()}

m = YOLO(FIXED["model"])
m.train(data=DATA, project=PROJECT, name=name, imgsz=FIXED["imgsz"], epochs=FIXED["epochs"],
        seed=FIXED["seed"], deterministic=FIXED["deterministic"], **extra)
r = m.val(data=DATA, imgsz=FIXED["imgsz"], project=PROJECT, name=f"{name}_val")  # best.pt 기준 val 결과

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
