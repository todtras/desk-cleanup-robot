"""웹캠을 고정 해상도로 녹화. 사용: python scripts/record_video.py out.mp4  (q로 종료)"""
import sys
import time
import cv2

W, H, FPS = 1280, 720, 30  # 실제 운용 카메라 해상도와 동일하게 유지

for _ in range(8):  # 첫 연결이 자주 실패해서 간격 두고 재시도
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    if cap.read()[0]:
        break
    cap.release()
    time.sleep(1)
w, h = int(cap.get(3)), int(cap.get(4))
assert (w, h) == (W, H), f"카메라가 {W}x{H}를 지원하지 않음: {w}x{h}"
out = cv2.VideoWriter(sys.argv[1], cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
t0 = time.time()
while True:
    ok, f = cap.read()
    if not ok:
        break
    out.write(f)
    s = int(time.time() - t0)
    view = f.copy()  # 시간 표시는 화면에만, 녹화본에는 넣지 않음
    cv2.putText(view, f"REC {s // 60:02d}:{s % 60:02d}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    cv2.imshow("rec (q=stop)", view)
    if cv2.waitKey(1) == ord("q"):
        break
out.release()
