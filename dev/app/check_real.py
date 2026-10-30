"""RealCleaner를 로봇 없이 점검: 가짜 로봇(녹화 영상 + 보낸 명령을 그대로 관절값으로)에 진짜 YOLO·ACT 정책을 붙여
웹 API로 시작 → 끝, 중지, 비상정지까지 돌려 본다. 파지 성공 여부는 볼 수 없음 (흐름·연결만 확인).
실행 (dev 폴더, lerobot venv): python -m app.check_real"""
import time

import cv2
from fastapi.testclient import TestClient

MOTORS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


class MockCam:
    def __init__(self, img):
        self.img = img

    def read_latest(self, max_age_ms=500):
        return self.img


class MockBus:
    def __init__(self, robot):
        self.robot = robot

    def sync_read(self, what):
        return {m: self.robot.pos[f"{m}.pos"] for m in MOTORS}


class MockRobot:
    """명령한 관절값이 곧바로 관측값이 되는 로봇. 카메라는 녹화 첫 화면 고정"""
    def __init__(self, head, wrist, home):
        self.cameras = {"head": MockCam(head), "wrist": MockCam(wrist)}
        self.pos = dict(home)
        self.bus = MockBus(self)
        self.sent = 0
        self.observation_features = {**{f"{m}.pos": float for m in MOTORS}, "head": (480, 640, 3), "wrist": (480, 640, 3)}
        self.action_features = {f"{m}.pos": float for m in MOTORS}

    def connect(self):
        pass

    def disconnect(self):
        pass

    def get_observation(self):
        return {**self.pos, **{k: c.read_latest() for k, c in self.cameras.items()}}

    def send_action(self, action):
        self.pos.update(action)
        self.sent += 1
        return action


def first_frames(clip):
    rgb = lambda p: cv2.cvtColor(cv2.VideoCapture(f"outputs/ui_pack/{p}").read()[1], cv2.COLOR_BGR2RGB)
    return rgb(clip["head"]), rgb(clip["wrist"])


def main():
    import json
    from pathlib import Path

    import app.real_cleaner as rc
    import app.server as server
    import run_auto as ra

    rc.SECONDS = 2  # 정책은 2초만 (흐름 확인용)
    clips = json.loads(Path("outputs/ui_pack/clips.json").read_text(encoding="utf-8"))
    head, wrist = first_frames(next(c for c in clips if c["object"] == "bottle"))
    robot = MockRobot(head, wrist, ra.POSES["home"])
    cleaner = rc.RealCleaner(robot=robot)
    cleaner.settings = {**cleaner.settings, "objects": {o: o == "bottle" for o in ra.PLAN}, "max_retries": 0}
    server.cleaner = cleaner  # 서버가 쓰는 Cleaner를 바꿔 끼움
    c = TestClient(server.app)

    def wait(cond, sec, what):
        t = time.time()
        while time.time() - t < sec:
            s = c.get("/api/status").json()
            if cond(s):
                return s
            time.sleep(0.2)
        raise AssertionError(f"{what}: {s}")

    assert cleaner.frame("head")[:2] == b"\xff\xd8", "head JPEG"
    assert c.post("/api/start").json()["ok"]
    s = wait(lambda s: s["step"] == "picking", 30, "탐지 → 집기")
    print("1. 집기 시작:", s["message"], s["detected"])
    assert s["detected"] and s["detected"][0]["object"] == "bottle"
    assert c.post("/api/start").json()["ok"] is False
    s = wait(lambda s: s["state"] == "done", 60, "한 바퀴")
    print("2. 끝:", s["message"], [n["text"] for n in s["notifications"]])
    assert s["progress"]["failed"] == 1  # 화면이 고정이라 놓은 뒤에도 그 자리에 보임 → 실패로 판정되는 게 맞음

    c.post("/api/start")
    wait(lambda s: s["step"] == "picking", 30, "두 번째 시작")
    c.post("/api/stop")
    s = wait(lambda s: s["state"] == "idle", 30, "중지")
    print("3. 중지:", s["message"])

    c.post("/api/start")
    wait(lambda s: s["step"] == "picking", 30, "세 번째 시작")
    t = time.time()
    c.post("/api/estop")
    s = wait(lambda s: s["state"] == "estop", 10, "비상정지")
    n = robot.sent
    time.sleep(1.0)
    print("4. 비상정지:", s["message"], f"(멈추기까지 {time.time() - t - 1.0:.2f}초)")
    assert robot.sent == n, "비상정지 상태인데 명령을 계속 보냄"
    print("ALL OK")


if __name__ == "__main__":
    main()
