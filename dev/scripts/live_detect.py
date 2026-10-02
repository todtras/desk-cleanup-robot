"""웹캠 실시간 탐지 확인. 사용: python scripts/live_detect.py models/best.pt  (q로 종료)"""
import sys
import time

import cv2
from ultralytics import YOLO

W, H, CAM, IMGSZ, CONF = 1280, 720, 1, 960, 0.5  # 학습 해상도/카메라와 동일하게

model = YOLO(sys.argv[1])
for _ in range(8):  # 첫 연결이 자주 실패해서 간격 두고 재시도
    cap = cv2.VideoCapture(CAM, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    if cap.read()[0]:
        break
    cap.release()
    time.sleep(1)
while True:
    ok, f = cap.read()
    if not ok:
        break
    r = model.predict(f, imgsz=IMGSZ, conf=CONF, verbose=False)[0]
    cv2.imshow("detect (q=quit)", r.plot())
    if cv2.waitKey(1) == ord("q"):
        break
cap.release()
