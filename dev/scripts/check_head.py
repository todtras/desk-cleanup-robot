"""head 카메라가 학습 때 구도와 같은지 실시간 확인. 기준(configs/robot/head_ref_1106.png)에 지금 화면을 겹쳐 브라우저로 보여주고 어긋남(px)을 표시.
사용 (dev 폴더에서, 측정·녹화 전 매번): python scripts/check_head.py [카메라 번호] → http://localhost:8001   Ctrl+C = 종료 (켜 두면 카메라를 잡고 있음)
기준 다시 만들기: --make_ref (녹화 영상 프레임들의 중앙값이라 팔·물체가 지워짐)
venv의 opencv가 headless라 cv2.imshow 창을 못 띄움 → dashboard.py처럼 브라우저로 스트리밍
"""
import argparse
import glob
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import yaml

os.chdir(Path(__file__).resolve().parent.parent)
REF = Path("configs/robot/head_ref_1106.png")  # 11/6 구도 (v4·v5 시연·기준 측정). 10/30 원래 학습 구도는 head_ref.png
PATCHES = {"bins": (0, 130), "base": (220, 20), "right": (440, 280)}  # 왼쪽 위 좌표, 크기 200x200
SIZE = 200
OK_PX = 2.0  # 약 7px 어긋남 + 초점 변화에서 정책이 전반적으로 실패했음 (10/30)
WINDOW = cv2.createHanningWindow((SIZE, SIZE), cv2.CV_32F)
PORT = 8001
# 테이프 붙일 측정 위치 (head 화면 px, 물체 YOLO 박스 중심). 11/6 물병·지우개 10만 측정 위치의 평균을 격자로 반듯하게 맞춤 (차이 수 px).
# 줄 N/M/F = 로봇에서 가까운(화면 위)/가운데/먼(화면 아래), L/C/R = 로봇 왼쪽/가운데/오른쪽 (로봇 왼쪽 = 화면 오른쪽, 실험기록 표와 같은 기준)
MARKS = {(x, y): f"{r}-{c}" for r, y in (("N", 240), ("M", 345), ("F", 395)) for c, x in (("L", 460), ("C", 305), ("R", 172))}


def shifts(ref, now):
    """영역별 (dx, dy, 신뢰도). dx > 0 = 지금 화면의 물체들이 기준보다 오른쪽"""
    a, b = (cv2.cvtColor(i, cv2.COLOR_BGR2GRAY).astype(np.float32) for i in (ref, now))
    out = {}
    for name, (x, y) in PATCHES.items():
        (dx, dy), r = cv2.phaseCorrelate(a[y:y + SIZE, x:x + SIZE], b[y:y + SIZE, x:x + SIZE], WINDOW)
        out[name] = (dx, dy, r)
    return out


def status(ref, now):
    """(표시 글자, BGR 색). 신뢰도가 낮은 영역은 빼고 중앙값"""
    good = [v for v in shifts(ref, now).values() if v[2] > 0.15]
    if not good:
        return "no match (clear the desk)", (0, 165, 255)
    dx, dy = (float(np.median([v[i] for v in good])) for i in (0, 1))
    aligned = abs(dx) <= OK_PX and abs(dy) <= OK_PX
    return f"dx {dx:+.1f} dy {dy:+.1f} {'OK' if aligned else 'MOVE CAMERA'}", (0, 200, 0) if aligned else (0, 0, 255)


def make_ref():
    import av  # 카메라(DSHOW)와 같은 프로세스에서 쓰면 프레임을 못 읽어서 여기서만 불러옴

    frames = []
    for d in ("bottle", "paper", "pen", "tape", "eraser"):
        for path in sorted(glob.glob(f"outputs/datasets/pick_{d}_v2/videos/observation.images.head/chunk-*/file-*.mp4")):
            with av.open(path) as c:
                frames += [f.to_ndarray(format="bgr24") for i, f in enumerate(c.decode(video=0)) if i % 400 == 0]
    ref = Path("configs/robot/head_ref.png")  # v2(10/30) 영상의 중앙값이라 10/30 기준 파일에 씀 (11/6 기준을 덮지 않게)
    cv2.imwrite(str(ref), np.median(frames, axis=0).astype(np.uint8))
    print(f"{ref}: 프레임 {len(frames)}장의 중앙값")


class Handler(BaseHTTPRequestHandler):
    ref, index, last, jpg = None, 1, "starting", None

    def do_GET(self):
        if self.path == "/status":  # 지금 어긋남 글자만
            body, kind = Handler.last.encode(), "text/plain"
        elif self.path == "/":
            body = b'<!doctype html><title>head check</title><body style="margin:0;background:#111"><img src="/stream" style="width:100%;max-width:1280px">'
            kind = "text/html"
        elif self.path == "/stream":
            return self.stream()
        else:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
        self.end_headers()
        try:
            while True:
                if Handler.jpg:
                    self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + Handler.jpg + b"\r\n")
                time.sleep(1 / 15)
        except (ConnectionError, OSError):
            pass

    def log_message(self, *a):
        pass


def capture_loop():
    """카메라는 이 스레드만 염 (카메라 하나를 보는 사람마다 열면 두 번째부터 'no camera'). 읽기가 실패하면 다시 엶"""
    cap = None
    while True:
        ok, now = cap.read() if cap else (False, None)
        if ok:
            Handler.last, color = status(Handler.ref, now)
            view = cv2.addWeighted(Handler.ref, 0.5, now, 0.5, 0)
        else:
            Handler.last, color = f"no camera {Handler.index}", (0, 0, 255)
            view = np.full_like(Handler.ref, 40)
            if cap:
                cap.release()
            time.sleep(0.5)
            cap = cv2.VideoCapture(Handler.index, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        for (x, y), label in MARKS.items():
            c = (0, 255, 255) if label.startswith("M") else (200, 200, 200)  # 노랑 = 스텝 비교 3곳 (가운데 줄)
            cv2.circle(view, (x, y), 12, c, 2)
            cv2.putText(view, label, (x + 15, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1)
        cv2.putText(view, Handler.last, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        Handler.jpg = cv2.imencode(".jpg", view)[1].tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("index", nargs="?", type=int, help="카메라 번호 (생략하면 record_pick.yaml의 head)")
    ap.add_argument("--make_ref", action="store_true")
    ap.add_argument("--ref", default=str(REF), help="비교할 기준 이미지")
    ap.add_argument("--save_ref", help="지금 화면을 이 파일로 저장하고 끝 (책상을 비우고 실행)")
    args = ap.parse_args()
    if args.make_ref:
        return make_ref()
    cfg = yaml.safe_load(Path("configs/robot/record_pick.yaml").read_text(encoding="utf-8"))["robot"]["cameras"]["head"]
    Handler.ref = cv2.imread(args.ref)
    Handler.index = cfg["index_or_path"] if args.index is None else args.index
    if args.save_ref:
        cap = cv2.VideoCapture(Handler.index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        frames = [f for ok, f in (cap.read() for _ in range(30)) if ok]
        cap.release()
        if not frames:
            raise SystemExit(f"카메라 {Handler.index}에서 화면을 못 읽음 (다른 프로그램이 잡고 있는지 확인)")
        cv2.imwrite(args.save_ref, frames[-1])
        return print(f"{args.save_ref} 저장, 현재 기준 대비 {status(Handler.ref, frames[-1])[0]}")
    threading.Thread(target=capture_loop, daemon=True).start()
    print(f"http://localhost:{PORT}  (Ctrl+C 종료)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
