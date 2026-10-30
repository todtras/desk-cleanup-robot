"""정리 로봇 '두뇌' 쪽. 화면(server.py)은 이 파일의 Cleaner만 쓴다.
지금은 녹화 영상으로 흉내 내는 FakeCleaner. 나중에 팀장이 같은 메서드를 가진 RealCleaner(진짜 로봇)를 만든다."""
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

PACK = Path(__file__).resolve().parent.parent / "outputs" / "ui_pack"  # 팀장이 준 가짜 로봇 데이터
SETTINGS_FILE = Path(__file__).resolve().parent.parent / "configs" / "app_settings.json"

OBJECTS = {"tape": "테이프", "bottle": "물병", "pen": "펜", "eraser": "지우개", "paper": "종이"}
BINS = {"tape": "사무용품", "bottle": "쓰레기", "pen": "필기구", "eraser": "필기구", "paper": "쓰레기"}
DEFAULT_SETTINGS = {"objects": {k: True for k in OBJECTS}, "speed": "normal", "max_retries": 1}


def load_settings():
    if SETTINGS_FILE.exists():
        return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
    return dict(DEFAULT_SETTINGS)


class FakeCleaner:
    def __init__(self):
        self.clips = json.loads((PACK / "clips.json").read_text(encoding="utf-8"))
        self.settings = load_settings()
        self.lock = threading.Lock()
        self.cmd = None  # 화면이 누른 버튼: "pause" / "stop" / "estop"
        self.frames = {"head": None, "wrist": None}  # 지금 화면 (JPEG bytes)
        self.st = {"state": "idle", "step": None, "current": None, "message": "대기 중이에요",
                   "detected": [], "progress": {"done": 0, "failed": 0, "remaining": 0}, "notifications": []}
        self._show_still()

    # ---------- 화면이 부르는 메서드 (모두 바로 반환) ----------
    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.st))  # 복사본

    def frame(self, cam):
        return self.frames[cam]

    def start(self):
        if self.st["state"] in ("cleaning", "paused"):
            return False
        self.cmd = None
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def pause(self):
        """지금 물건은 마저 정리하고 멈춤 (물건을 든 채 공중에서 멈추면 위험)"""
        if self.st["state"] == "cleaning":
            self.cmd = "pause"
            self._set(message="지금 물건까지 정리하고 멈출게요")

    def resume(self):
        if self.st["state"] == "paused":
            self.cmd = None

    def stop(self):
        self.cmd = "stop"

    def estop(self):
        self.cmd = "estop"

    def get_settings(self):
        return self.settings

    def set_settings(self, new):
        if self.st["state"] in ("cleaning", "paused"):
            return False  # 정리 중에는 못 바꿈
        self.settings = {**self.settings, **new}
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=1), encoding="utf-8")
        return True

    # ---------- 내부 ----------
    def _set(self, **kw):
        with self.lock:
            self.st.update(kw)

    def _notify(self, text, level="info"):
        with self.lock:
            self.st["notifications"].append({"time": datetime.now().strftime("%H:%M:%S"), "level": level, "text": text})
            self.st["notifications"] = self.st["notifications"][-50:]

    def _show_still(self, clip=None, boxes=()):
        clip = clip or self.clips[0]
        for cam in ("head", "wrist"):
            ok, img = cv2.VideoCapture(str(PACK / clip[cam])).read()
            if cam == "head":
                for b in boxes:
                    cv2.rectangle(img, tuple(b["box"][:2]), tuple(b["box"][2:]), (0, 200, 0), 2)
                    cv2.putText(img, f'{b["object"]} {b["conf"]:.2f}', (b["box"][0], b["box"][1] - 6),  # OpenCV 글씨는 영어만
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)
            self.frames[cam] = cv2.imencode(".jpg", img)[1].tobytes()

    def _wait_if_paused(self):
        while self.cmd == "pause":
            self._set(state="paused", message="일시정지 — 계속하려면 '계속'을 누르세요")
            time.sleep(0.2)
        if self.cmd is None:
            self._set(state="cleaning")

    def _play(self, clip, until=None):
        """영상 재생 (= 로봇이 움직이는 중). 중지 버튼이면 False"""
        caps = {c: cv2.VideoCapture(str(PACK / clip[c])) for c in ("head", "wrist")}
        speed = 1.0 if self.settings["speed"] == "normal" else 0.6
        n = 0
        while until is None or n < until * 15:
            if self.cmd in ("stop", "estop"):
                return False
            imgs = {c: cap.read() for c, cap in caps.items()}
            if not all(ok for ok, _ in imgs.values()):
                break
            for c, (_, img) in imgs.items():
                self.frames[c] = cv2.imencode(".jpg", img)[1].tobytes()
            n += 1
            time.sleep(1 / 15 / speed)
        return True

    def _run(self):
        todo = [o for o, on in self.settings["objects"].items() if on]
        random.shuffle(todo)
        self._set(state="cleaning", step="detecting", current=None, message="책상을 살펴보는 중이에요",
                  progress={"done": 0, "failed": 0, "remaining": len(todo)})
        self._notify("정리를 시작했어요")
        done = failed = 0
        for obj in todo:
            self._wait_if_paused()
            clip = random.choice([c for c in self.clips if c["object"] == obj])
            det = [{"object": obj, "conf": round(random.uniform(0.6, 0.95), 2), "box": clip["box"]}]
            self._set(step="detecting", detected=det, message=f"{OBJECTS[obj]}을(를) 찾았어요")
            self._show_still(clip, det)
            time.sleep(1.0)
            ok = False
            for attempt in range(1 + self.settings["max_retries"]):
                self._set(step="picking", current={"object": obj, "bin": BINS[obj], "attempt": attempt + 1},
                          message=f"{OBJECTS[obj]} 집는 중 ({attempt + 1}번째)")
                if not self._play(clip):
                    return self._finish_stop()
                ok = random.random() < 0.7  # 가짜: 70% 확률로 성공
                if ok:
                    break
                self._notify(f"{OBJECTS[obj]}을(를) 놓쳤어요. 다시 시도해요", "warn")
            if ok:
                self._set(step="carrying", message=f"{OBJECTS[obj]}을(를) {BINS[obj]} 수거함으로 옮기는 중")
                time.sleep(2.0)
                done += 1
            else:
                failed += 1
                self._notify(f"{OBJECTS[obj]}을(를) 집지 못해 건너뛰었어요. 직접 정리해 주세요", "warn")
            self._set(step="returning", message="처음 자세로 돌아가는 중" if self.cmd != "pause" else "처음 자세로 돌아가서 멈출게요")
            time.sleep(1.0)
            self._set(progress={"done": done, "failed": failed, "remaining": len(todo) - done - failed})
        self._set(state="done", step=None, current=None, detected=[], message=f"정리 끝! {done}개 정리, {failed}개 실패")
        self._notify(f"정리를 마쳤어요 ({done}개 정리, {failed}개 실패)")

    def _finish_stop(self):
        if self.cmd == "estop":
            self._set(state="estop", step=None, message="비상정지! 로봇이 그 자세로 멈췄어요. 주변을 확인한 뒤 다시 시작하세요")
            self._notify("비상정지 버튼이 눌렸어요", "error")
        else:
            self._set(state="idle", step=None, current=None, message="중지했어요. 처음 자세로 돌아왔어요")
            self._notify("정리를 중지했어요")
        self.cmd = None
