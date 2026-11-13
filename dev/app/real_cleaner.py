"""진짜 로봇용 Cleaner. 메서드와 status() 형식은 FakeCleaner(cleaner.py)와 같다 → server.py에서 바꿔 끼우기만 하면 됨.
동작은 scripts/run_auto.py 함수를 그대로 쓴다 (탐지 → 정책 → 쥠 감지 → 수거함 → home).
run_auto와 다른 점: 성공 여부를 사람이 입력하지 않고, home에서 다시 봤을 때 그 물건이 그 자리에 없으면 성공.
실행: dev 폴더, lerobot venv에서  $env:ROBOT="real"; python -m uvicorn app.server:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 1"""
import csv
import json
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import draccus
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_auto as ra  # noqa: E402  (dev로 chdir, 카메라·로봇 타입 등록)
from lerobot.datasets.utils import hw_to_dataset_features  # noqa: E402
from lerobot.robots import RobotConfig, make_robot_from_config  # noqa: E402
from lerobot.utils.constants import ACTION, OBS_STR  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from app.cleaner import BINS, OBJECTS, load_settings, SETTINGS_FILE  # noqa: E402

LOG = Path("outputs/app_log.csv")  # 웹으로 돌린 시도 기록 (run_log.csv와 섞지 않음)
FPS = {"normal": 15, "slow": 10}  # 속도 설정 → 정책 fps (15보다 빠르면 팔이 못 따라감)
SECONDS = 30  # 정책 최대 시간 (보통 속도 기준, 느리게면 비례해서 늘림)
STEPS = (60, 30, 20)  # 예측마다 실행할 동작 수 (run_auto 기본과 같음): 첫 예측을 길게 해 출발 움찔거림 없앰, 쥐기 가까이 갈수록 자주 다시 봄
PICK_ORDER = ["bottle", "tape", "eraser", "pen", "paper"]  # 집는 순서 기본값: 키 큰 것부터 (5종을 같이 두면 다른 물체를 집으러 가다 물병에 걸림, 11/13). 설정 "order"로 바꿈
# 다른 물체 가리기: 설정 "mask_others" (기본 켬). 시연은 물체 하나씩이라 여러 개 보이면 정책이 흔들림 (11/13)
SOFT_START = 1.0  # 처음 1초는 천천히 출발 (시연 첫 동작이 빨라 사람 옆에서 위협적, 11/13)
SAME_SPOT_PX = 50  # 놓은 뒤 같은 물건이 원래 자리 이만큼 안에 보이면 실패. ponytail: 같은 종류 물건이 근처에 또 있으면 오판


def center(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def near(a, b, px=SAME_SPOT_PX):
    (ax, ay), (bx, by) = center(a), center(b)
    return abs(ax - bx) < px and abs(ay - by) < px


class RealCleaner:
    def __init__(self, robot=None, step=None):
        self.settings = load_settings()
        self.step = step = step or self.settings.get("step", "010000")
        self.ver = ver = self.settings.get("ver", "v3")  # app_settings.json의 "ver" (run_auto --ver와 같은 값). v3 = 지우개·종이 v3, 나머지 v2
        logging.disable(logging.WARNING)  # 체크포인트마다 cuda 경고
        self.policies = {o: ra.load_policy(ra.ckpt_path(o, step, ver), "cpu", STEPS[0])
                         for o in ra.PLAN if o in BINS and Path(ra.ckpt_path(o, step, ver)).exists()}  # 화면에 이름·수거함이 정해진 물체만 (부품은 UI 반영 후)
        logging.disable(logging.NOTSET)
        self.robot = robot or make_robot_from_config(
            draccus.decode(RobotConfig, yaml.safe_load(ra.CFG.read_text(encoding="utf-8"))["robot"]))
        self.features = {**hw_to_dataset_features(self.robot.observation_features, OBS_STR),
                         **hw_to_dataset_features(self.robot.action_features, ACTION)}
        self.model = YOLO("models/best.pt")
        self.lock = threading.Lock()
        self.cmd = None  # "pause" / "stop" (비상정지는 ra.ESTOP)
        self.boxes = []  # head 화면에 그릴 박스 [(이름, 신뢰도, xyxy, 지금 집는 것인지)]
        self.st = {"state": "idle", "step": None, "current": None, "message": "대기 중이에요",
                   "detected": [], "progress": {"done": 0, "failed": 0, "remaining": 0}, "notifications": []}
        missing = [o for o in ra.PLAN if o in BINS and o not in self.policies]
        self.robot.connect()  # 대기 중에도 실시간 화면이 나오게 바로 연결 (토크 켜짐 → 지금 자세 유지)
        if missing:
            self._notify(f"학습된 동작이 없어 정리하지 않는 물건: {', '.join(OBJECTS[o] for o in missing)}", "warn")

    # ---------- 화면이 부르는 메서드 (모두 바로 반환) ----------
    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.st))

    def frame(self, cam):
        """웹 요청 스레드에서 최신 사진만 꺼내 JPEG로 (로봇 제어 루프와 무관, 장당 약 0.5ms)"""
        try:
            img = cv2.cvtColor(self.robot.cameras[cam].read_latest(), cv2.COLOR_RGB2BGR)
        except Exception:  # 카메라 끊김·멈춤 (read_latest는 0.5초 넘은 사진이면 TimeoutError)
            return None
        if cam == "head":
            for name, conf, (x1, y1, x2, y2), target in list(self.boxes):
                color = (0, 200, 0) if target else (0, 200, 255)
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 3 if target else 1)
                cv2.putText(img, f"{name} {conf:.2f}", (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()

    def start(self):
        if self.st["state"] in ("cleaning", "paused"):
            return False
        self.cmd = None
        ra.ESTOP.clear()
        threading.Thread(target=self._run_safe, daemon=True).start()
        return True

    def pause(self):
        """지금 물건은 마저 정리하고 home에서 멈춤"""
        if self.st["state"] == "cleaning":
            self.cmd = "pause"
            self._set(message="지금 물건까지 정리하고 멈출게요")

    def resume(self):
        if self.st["state"] == "paused":
            self.cmd = None

    def stop(self):
        """정책 중이면 그 시도를 끊고 그리퍼 열고 home. 수거함으로 옮기는 중이면 놓고 나서 멈춤"""
        if self.st["state"] in ("cleaning", "paused"):
            self.cmd = "stop"
            self._set(message="멈추는 중이에요")

    def estop(self):
        ra.ESTOP.set()  # 정책 루프·move_to가 다음 명령 전에 멈춤 → _run_safe가 지금 자세 고정

    def release(self):
        """비상정지 후 잡고 있는 물건 놓기: 다른 관절은 그대로, 그리퍼만 0.5초에 걸쳐 열기"""
        if self.st["state"] != "estop":
            return False
        now = {k: v for k, v in self.robot.get_observation().items() if k.endswith(".pos")}
        grip = max(p["gripper.pos"] for k, p in ra.POSES.items() if k.endswith("_drop"))  # 수거함에서 놓을 때 가장 크게 여는 값
        for i in range(1, 16):
            self.robot.send_action({**now, "gripper.pos": now["gripper.pos"] + (grip - now["gripper.pos"]) * i / 15})
            time.sleep(1 / 30)
        self._set(message="물건을 놓았어요. 주변을 확인한 뒤 다시 시작하세요")
        self._notify("비상정지 상태에서 물건을 놓았어요")
        return True

    def get_settings(self):
        return self.settings

    def set_settings(self, new):
        if self.st["state"] in ("cleaning", "paused"):
            return False
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

    def _detect(self, names):
        found = ra.detect_all(self.model, self.robot.get_observation()["head"], names)
        self.boxes = [(n, c, b, False) for n, c, b in found]
        self._set(detected=[{"object": n, "conf": round(c, 2), "box": list(b)} for n, c, b in found])
        return found

    def _hold_here(self):
        """비상정지: 지금 자세를 목표로 다시 보내서 그 자리에 고정 (토크는 켜 둠: 끄면 팔이 떨어짐)"""
        now = {k: v for k, v in self.robot.get_observation().items() if k.endswith(".pos")}
        self.robot.send_action(now)

    def _log(self, name, conf, seconds, ok, reason):
        new = not LOG.exists()
        with LOG.open("a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "class", "conf", "seconds", "success", "reason"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), name, f"{conf:.2f}", f"{seconds:.1f}",
                        "y" if ok else "n", reason])

    def _run_safe(self):
        try:
            self._run()
        except Exception as e:  # 로봇·카메라 연결 끊김 등 → 화면에 오류로
            self._set(state="error", step=None, message=f"문제가 생겨 멈췄어요: {e}")
            self._notify(f"오류: {e}", "error")
            return
        if ra.ESTOP.is_set():
            self._hold_here()
            self._set(state="estop", step=None, current=None,
                      message="비상정지! 로봇이 그 자세로 멈췄어요. 주변을 확인한 뒤 다시 시작하세요")
            self._notify("비상정지 버튼이 눌렸어요", "error")

    def _run(self):
        s = self.settings
        names = [o for o in self.policies if s["objects"].get(o, True)]
        fps = FPS.get(s.get("speed"), 15)
        seconds = SECONDS * 15 / fps
        skipped = []  # 포기한 물건 (이름, 박스): 다음 탐지에서 같은 자리면 건너뜀
        done = failed = 0
        self._set(state="cleaning", step="homing", current=None, message="처음 자세로 가는 중이에요",
                  progress={"done": 0, "failed": 0, "remaining": 0})
        self._notify("정리를 시작했어요")
        ra.move_to(self.robot, ra.POSES["home"], 3.0)
        while not ra.ESTOP.is_set():
            while self.cmd == "pause":
                self._set(state="paused", step=None, message="일시정지 — 계속하려면 '계속'을 누르세요")
                time.sleep(0.2)
            if self.cmd == "stop":
                break
            self._set(state="cleaning", step="detecting", current=None, message="책상을 살펴보는 중이에요")
            todo = [d for d in self._detect(names) if not any(d[0] == n and near(d[2], b) for n, b in skipped)]
            self._set(progress={"done": done, "failed": failed, "remaining": len(todo)})
            if not todo:
                break
            order = s.get("order", PICK_ORDER)  # 앞에 있는 종류부터. 같은 종류끼리는 신뢰도 높은 것부터
            name, conf, box = min(todo, key=lambda d: (order.index(d[0]) if d[0] in order else len(order), -d[1]))
            self.boxes = [(n, c, b, (n, b) == (name, box)) for n, c, b, _ in self.boxes]
            ok, reason = False, ""
            for attempt in range(1 + s.get("max_retries", 1)):
                self._set(step="picking", current={"object": name, "bin": BINS[name], "attempt": attempt + 1},
                          message=f"{OBJECTS[name]} 집는 중 ({attempt + 1}번째)")
                t0 = time.perf_counter()
                key, hold = ra.run_policy(self.robot, *self.policies[name], self.features, seconds, fps, 0.3,
                                          ra.PAN_OFFSET.get(name, 0.0) + (s.get("pan_scale", 1.0) * ra.pan_fix(name, ra.step_label(name, self.step, self.ver), box) if s.get("pan_fit", True) else 0.0),
                                          extra=ra.reach_fix(name, ra.reach_px(name, ra.step_label(name, self.step, self.ver), box)), poll_key=lambda: "q" if self.cmd == "stop" else None,
                                          steps=STEPS, soft=SOFT_START,
                                          mask=[b for _, _, b in todo if b != box] if s.get("mask_others", True) else None)
                if ra.ESTOP.is_set():
                    return
                if hold is not None:
                    self._set(step="carrying", message=f"{OBJECTS[name]}을(를) {BINS[name]} 수거함으로 옮기는 중")
                    ra.carry_and_drop(self.robot, ra.PLAN[name], hold)
                else:
                    self._set(step="returning", message="처음 자세로 돌아가는 중")
                    ra.release_and_home(self.robot, ra.PLAN[name])
                if ra.ESTOP.is_set():
                    return
                if key == "q":  # 중지 버튼
                    break
                # 성공 판정: home에서 다시 봤을 때 그 물건이 원래 자리에 없으면 성공
                still = [d for d in self._detect([name]) if near(d[2], box)]
                ok = hold is not None and not still
                reason = "" if ok else ("집지 못함" if hold is None else "옮긴 뒤에도 그 자리에 있음")
                self._log(name, conf, time.perf_counter() - t0, ok, reason)
                if ok:
                    break
                if attempt < s.get("max_retries", 1):
                    self._notify(f"{OBJECTS[name]}을(를) 놓쳤어요. 다시 시도해요", "warn")
            if self.cmd == "stop":
                break
            if ok:
                done += 1
            else:
                failed += 1
                skipped.append((name, box))
                self._notify(f"{OBJECTS[name]}을(를) 집지 못해 건너뛰었어요. 직접 정리해 주세요", "warn")
        self.boxes = []
        if ra.ESTOP.is_set():
            return
        if self.cmd == "stop":
            self.cmd = None
            self._set(state="idle", step=None, current=None, message="중지했어요. 처음 자세로 돌아왔어요")
            self._notify("정리를 중지했어요")
        else:
            self._set(state="done", step=None, current=None, detected=[],
                      message=f"정리 끝! {done}개 정리, {failed}개 실패", progress={"done": done, "failed": failed, "remaining": 0})
            self._notify(f"정리를 마쳤어요 ({done}개 정리, {failed}개 실패)")
