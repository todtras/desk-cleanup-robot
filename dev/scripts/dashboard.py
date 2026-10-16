"""녹화 전후 점검 대시보드. 사용 (dev 폴더에서): python scripts/dashboard.py → http://localhost:8000
- 포트: 지금 꽂힌 COM 포트 vs record_pick.yaml 설정
- 카메라: 번호별 실시간 화면 (head/wrist 번호 찾기용)
- 데이터셋: 에피소드 수, 에피소드별 길이 (너무 짧거나 긴 것 = 실패 후보)
lerobot-record 실행 전에 이 창의 카메라 화면은 꺼야 함 (카메라를 동시에 못 씀).
"""
import glob
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import serial.tools.list_ports
import yaml

CFG = Path("configs/robot/record_pick.yaml")
POSES = Path("configs/robot/poses.json")
DATASET_DIRS = ["outputs/datasets/*", str(Path.home() / ".cache/huggingface/lerobot/local/*")]
CAM_INDICES = range(5)


def section(title, body):
    return f"<h2>{title}</h2>{body}"


def ports_html(cfg):
    want = {cfg["robot"]["port"]: "팔로워", cfg["teleop"]["port"]: "리더"}
    found = {p.device: p.description for p in serial.tools.list_ports.comports()}
    rows = [f"<tr><td>{d}</td><td>{desc}</td><td>{want.get(d, '')}</td></tr>" for d, desc in found.items()]
    missing = [f"{d}({w})" for d, w in want.items() if d not in found]
    warn = f"<p class=bad>설정에 있는데 안 보이는 포트: {', '.join(missing)} → lerobot-find-port로 확인 후 yaml 수정</p>" if missing else "<p class=ok>설정한 포트 모두 연결됨</p>"
    return warn + "<table><tr><th>포트</th><th>설명</th><th>설정상 역할</th></tr>" + "".join(rows) + "</table>"


def cams_html(cfg):
    roles = {c["index_or_path"]: name for name, c in cfg["robot"]["cameras"].items()}
    tiles = "".join(
        f"<div class=cam><b>{i}번 {('= ' + roles[i]) if i in roles else ''}</b>"
        f"<img id=c{i}><button onclick=\"t({i})\">켜기/끄기</button></div>" for i in CAM_INDICES)
    return "<p>한 번에 1~2개만 켜기 (USB 대역폭). 녹화 전엔 모두 끄기.</p><div class=grid>" + tiles + "</div>"


def datasets_html():
    out = []
    for d in sorted(p for pat in DATASET_DIRS for p in glob.glob(pat)):
        info_f = Path(d) / "meta/info.json"
        if not info_f.exists():
            continue
        info = json.loads(info_f.read_text(encoding="utf-8"))
        cams = [k.split(".")[-1] for k in info["features"] if k.startswith("observation.images")]
        files = glob.glob(f"{d}/meta/episodes/*/*.parquet")
        eps = pd.concat(pd.read_parquet(f, columns=["episode_index", "length"]) for f in files) if files else pd.DataFrame()
        bars = ""
        if len(eps):
            med = eps["length"].median()
            for _, r in eps.iterrows():
                odd = abs(r["length"] - med) > 0.4 * med  # ponytail: 중앙값 ±40% 기준, 실패 판정은 영상으로 직접 확인
                bars += (f"<div class='bar{' odd' if odd else ''}' title='ep {r['episode_index']}: {r['length']}프레임'"
                         f" style='height:{r['length'] / eps['length'].max() * 60:.0f}px'></div>")
        sec = info["total_frames"] / info["fps"]
        out.append(f"<h3>{Path(d).name}</h3><p>에피소드 {info['total_episodes']}개 · 총 {sec / 60:.1f}분 · "
                   f"카메라 {', '.join(cams)} · <code>{d}</code></p><div class=bars>{bars}</div>")
    return "".join(out) or "<p>아직 없음</p>"


def poses_html():
    poses = json.loads(POSES.read_text(encoding="utf-8")) if POSES.exists() else {}
    return "<p>" + " · ".join(poses) + "</p>"


PAGE = """<!doctype html><meta charset=utf-8><title>녹화 점검</title><style>
body{font:14px sans-serif;margin:16px;max-width:1100px} table{border-collapse:collapse} td,th{border:1px solid #ccc;padding:4px 8px}
.ok{color:#080}.bad{color:#c00;font-weight:bold} .grid{display:flex;flex-wrap:wrap;gap:8px}
.cam{width:320px;border:1px solid #ccc;padding:4px} .cam img{width:100%;min-height:180px;background:#eee;display:block}
.bars{display:flex;align-items:flex-end;gap:2px;height:64px;border-bottom:1px solid #999}.bar{width:8px;background:#48c}.odd{background:#e60}
code{background:#f3f3f3;padding:2px 4px}</style>
<h1>녹화 점검 <small><a href=/>새로고침</a></small></h1>BODY
<script>function t(i){const e=document.getElementById('c'+i);e.src=e.src.includes('/cam/')?'':'/cam/'+i+'?'+Date.now()}</script>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/cam/"):
            return self.stream(int(self.path[5:].split("?")[0]))
        cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
        body = (section("포트", ports_html(cfg)) + section("카메라", cams_html(cfg))
                + section("데이터셋 (주황 막대 = 길이가 튀는 에피소드)", datasets_html())
                + section("저장된 포즈", poses_html())
                + section("명령어", "<p><code>python scripts/record.py --config_path=configs/robot/record_pick.yaml --dataset.repo_id=local/pick_tape --dataset.single_task=\"pick up the tape and lift it\"</code><br>"
                          "조작: → 에피소드 끝내기 · ← 다시 찍기 · Esc 녹화 종료<br>"
                          "실패 에피소드 삭제: <code>lerobot-edit-dataset --repo_id local/pick_tape "
                          "--operation.type delete_episodes --operation.episode_indices \"[3, 7]\"</code></p>"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE.replace("BODY", body).encode())

    def stream(self, i):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # 보는 동안만 열고, 창을 끄면 바로 놓음
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
        self.end_headers()
        try:
            while True:
                ok, f = cap.read()
                if not ok:
                    f = cv2.putText(np.full((270, 480, 3), 230, np.uint8), f"no camera {i}", (120, 140), 0, 1, (0, 0, 200), 2)
                jpg = cv2.imencode(".jpg", cv2.resize(f, (480, 270)))[1].tobytes()
                self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                if not ok:
                    time.sleep(1)
        except (ConnectionError, OSError):
            pass
        finally:
            cap.release()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("http://localhost:8000  (Ctrl+C 종료)")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
