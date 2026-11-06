"""시연 물체 위치 지도. 에피소드 첫 head 프레임에서 YOLO로 물체를 찾아 점으로 표시 → 어디가 부족한지 보고 보강
사용 (dev 폴더에서): python scripts/demo_map.py pick_eraser_v2 pick_paper_v2   → outputs/demo_map/<이름>.jpg
녹화 중 실시간: python scripts/record.py ... --dataset.repo_id=local/pick_eraser_v2 --resume=true --coverage
위치는 outputs/demo_map/<이름>.json에 저장해 다음부터 새 에피소드만 탐지
ponytail: 에피소드 재녹화·삭제로 번호가 바뀌면 json을 지우고 다시 만들 것"""
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from run_auto import V2_TO_NOW, detect_all  # 정책 실행과 같은 탐지 설정. run_auto가 작업 폴더를 dev로 맞춤

WS = (170, 230, 540, 430)  # 작업 구역 (head 화면 x1, y1, x2, y2). progress.md의 시작 위치 범위. 구역을 바꾸면 여기만
COLS, ROWS, LOW = 6, 4, 4  # 격자, 이 개수 미만인 칸은 붉게
OUT = Path("outputs/demo_map")
PORT = 8010  # 녹화 중 실시간 지도 주소 http://localhost:8010 (venv의 opencv에 창 기능이 없어 브라우저로 표시)


PAGE = b"""<!doctype html><title>demo map</title><body style='margin:0;background:#111'><img id=v style='width:100%;max-width:1280px'>
<script>
const v = document.getElementById("v");
function tick() {
  const i = new Image();
  i.onload = () => { v.src = i.src; setTimeout(tick, 100); };
  i.onerror = () => setTimeout(tick, 500);
  i.src = "/f.jpg?" + Date.now();
}
tick();
</script>"""


def grid(pts):
    """위치 → 칸별 개수. 구역 밖 점은 가장 가까운 칸에"""
    g = np.zeros((ROWS, COLS), int)
    for x, y in pts:
        c = int(np.clip((x - WS[0]) * COLS // (WS[2] - WS[0]), 0, COLS - 1))
        r = int(np.clip((y - WS[1]) * ROWS // (WS[3] - WS[1]), 0, ROWS - 1))
        g[r, c] += 1
    return g


def find(model, rgb, cls):
    """물체 중심 (x, y), 못 찾으면 None"""
    hits = detect_all(model, rgb, {cls})
    if not hits:
        return None
    x1, y1, x2, y2 = max(hits, key=lambda h: h[1])[2]
    return [(x1 + x2) // 2, (y1 + y2) // 2]


def draw(bgr, name, pts, fails):
    """BGR 화면 위에 격자, 칸별 개수, 점을 그림"""
    img, g = bgr.copy(), grid(pts)
    w, h = (WS[2] - WS[0]) / COLS, (WS[3] - WS[1]) / ROWS
    tint = img.copy()
    for r in range(ROWS):
        for c in range(COLS):
            a, b = (int(WS[0] + c * w), int(WS[1] + r * h)), (int(WS[0] + (c + 1) * w), int(WS[1] + (r + 1) * h))
            if g[r, c] < LOW:
                cv2.rectangle(tint, a, b, (0, 0, 255), -1)
    img = cv2.addWeighted(tint, 0.25, img, 0.75, 0)
    for r in range(ROWS):
        for c in range(COLS):
            a, b = (int(WS[0] + c * w), int(WS[1] + r * h)), (int(WS[0] + (c + 1) * w), int(WS[1] + (r + 1) * h))
            cv2.rectangle(img, a, b, (255, 255, 255), 1)
            cv2.putText(img, str(g[r, c]), (a[0] + 4, a[1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    for i, (x, y) in enumerate(pts):
        cv2.circle(img, (x, y), 4, (0, 255, 255) if i == len(pts) - 1 else (0, 255, 0), -1)
        cv2.circle(img, (x, y), 4, (0, 0, 0), 1)
    cv2.putText(img, f"{name}: {len(pts)} found, {fails} missed  (image right = robot left)", (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def load(name, model):
    """데이터셋 전체 위치 {에피소드: [x, y] 또는 None}, 마지막 에피소드 첫 화면(RGB). 데이터셋이 아직 없으면 ({}, None)"""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    root, cache = Path("outputs/datasets") / name, OUT / f"{name}.json"
    if not (root / "meta/episodes").exists():  # 없거나 첫 에피소드 저장 전에 끊김 (읽으려 하면 lerobot이 허깅페이스에서 찾다가 실패)
        return {}, None
    OUT.mkdir(parents=True, exist_ok=True)
    pos = dict(json.loads(cache.read_text())) if cache.exists() else {}
    ds = LeRobotDataset("local/" + name, root=root, video_backend="pyav")
    cls, rgb = name.split("_")[1], None
    for e in range(ds.meta.total_episodes):
        if e in pos and e < ds.meta.total_episodes - 1:  # 마지막 에피소드는 지도 배경으로 화면이 필요
            continue
        x = ds[int(ds.meta.episodes[e]["dataset_from_index"])]["observation.images.head"]
        rgb = (x.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        pos.setdefault(e, find(model, rgb, cls))
    cache.write_text(json.dumps(sorted(pos.items())))
    return pos, rgb


class Live:
    """녹화 중 브라우저 화면: 실시간 head 화면 + 지금까지 위치. 물체 놓을 때 비어 있는 칸을 보고 놓으면 됨"""

    def __init__(self, name):
        self.name, self.cls = name, name.split("_")[1]
        self.model = YOLO("models/best.pt")
        pos, _ = load(name, self.model)
        self.pts = [p for p in pos.values() if p]
        if name.endswith("_demo"):  # 보강 녹화: 기존 시연 위치도 함께 표시 → 정말 빈 곳을 채움
            base, _ = load(f"pick_{self.cls}_v2", self.model)
            self.pts = [[x + V2_TO_NOW[0], y + V2_TO_NOW[1]] for x, y in filter(None, base.values())] + self.pts
        self.fails = sum(p is None for p in pos.values())
        self.mark_next, self.last_found, self.jpg = False, None, None

    def undo(self):
        """방금 에피소드를 다시 녹화: 그 위치를 뺌"""
        if self.last_found:
            self.pts.pop()
        elif self.last_found is False:
            self.fails -= 1
        self.last_found = None

    def run(self, robot):
        while not robot.is_connected:
            time.sleep(0.2)
        while True:
            try:
                rgb = robot.cameras["head"].read_latest()
            except Exception:  # 끝날 때 카메라 닫힘, 잠깐 프레임 늦음
                if not robot.is_connected:
                    return
                time.sleep(0.1)
                continue
            try:  # 탐지·그리기 오류로 스레드가 죽으면 화면이 멈춤. 지도는 보조라 녹화에 영향 없게 기록만 하고 계속
                if self.mark_next:  # 에피소드 시작 순간 위치를 찍음 (제어 스레드와 분리)
                    self.mark_next = False
                    p = find(self.model, rgb, self.cls)
                    self.last_found = bool(p)
                    if p:
                        self.pts.append(p)
                    else:
                        self.fails += 1
                self.jpg = cv2.imencode(".jpg", draw(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), self.name, self.pts, self.fails))[1].tobytes()
            except Exception as e:
                print(f"[demo_map] {type(e).__name__}: {e}", flush=True)
            time.sleep(0.1)  # 10fps면 충분. 녹화 CPU를 뺏지 않게

    def serve(self):
        live = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                # 연속 스트림(MJPEG)은 끊기면 화면이 검게 변해서, 사진을 한 장씩 받아 다 받은 뒤에만 바꿈 → 실패해도 마지막 화면 유지
                body, kind = PAGE, "text/html"
                if self.path.startswith("/f.jpg"):
                    body, kind = live.jpg or b"", "image/jpeg"
                try:
                    self.send_response(200 if body else 503)
                    self.send_header("Content-Type", kind)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:  # 브라우저 닫음
                    pass

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    def start(self, robot):
        self.serve()
        threading.Thread(target=self.run, args=(robot,), daemon=True).start()
        webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    assert grid([(170, 230), (539, 429), (1000, 0)]).sum() == 3 and grid([(170, 230)])[0, 0] == 1 and grid([(539, 429)])[-1, -1] == 1
    model = YOLO("models/best.pt")
    for name in sys.argv[1:]:
        pos, rgb = load(name, model)
        pts = [p for p in pos.values() if p]
        missed = [e for e, p in pos.items() if p is None]
        path = OUT / f"{name}.jpg"
        cv2.imwrite(str(path), draw(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), name, pts, len(missed)))
        print(f"{name}: {len(pos)} 에피소드, 찾음 {len(pts)}, 못 찾음 {missed} → {path}\n{grid(pts)}")
