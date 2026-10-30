"""웹 서버: 브라우저 화면(static/)과 정리 로봇(Cleaner)을 이어준다.
실행 (dev 폴더에서): python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
→ 노트북: http://localhost:8000   같은 와이파이의 폰: http://<노트북 IP>:8000
진짜 로봇 (팀장 노트북, lerobot venv): PowerShell에서 $env:ROBOT="real" 후 같은 명령"""
import os
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

if os.environ.get("ROBOT") == "real":
    from app.real_cleaner import RealCleaner as Cleaner  # lerobot·torch 필요 (팀원 PC에는 없음)
else:
    from app.cleaner import FakeCleaner as Cleaner

app = FastAPI()
cleaner = Cleaner()


@app.get("/api/status")
def status():
    return cleaner.status()


@app.post("/api/{action}")
def command(action: str):
    actions = {"start": cleaner.start, "pause": cleaner.pause, "resume": cleaner.resume,
               "stop": cleaner.stop, "estop": cleaner.estop}
    if action not in actions:
        return {"ok": False, "error": f"모르는 명령: {action}"}
    result = actions[action]()
    return {"ok": result is not False}


@app.get("/api/settings")
def get_settings():
    return cleaner.get_settings()


@app.put("/api/settings")
def put_settings(new: dict):
    return {"ok": cleaner.set_settings(new)}


@app.get("/video/{cam}")
def video(cam: str):
    """MJPEG: 브라우저에서 <img src="/video/head"> 하나로 실시간 화면이 나온다"""
    def gen():
        while True:
            jpg = cleaner.frame(cam)
            if jpg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            time.sleep(1 / 15)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
