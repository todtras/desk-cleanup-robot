"""lerobot-record 그대로 + 네 가지 수정
1) 음성 안내를 영어 목소리로 (윈도우 기본 TTS가 한국어 목소리라 영어를 콩글리시로 읽음)
2) 키를 꾹 누를 때 생기는 반복 입력 무시 (→ 반복 입력이 리셋 시간까지 건너뛰던 문제)
3) 저장 위치 기본값 outputs/datasets/<이름> (lerobot 기본은 ~/.cache)
4) 녹화가 끝나도 Ctrl+C 전까지 텔레옵 유지
사용 (dev 폴더에서): python scripts/record.py --config_path=configs/robot/record_pick.yaml [lerobot-record 인자 그대로]
"""
import subprocess
import sys
import time
import traceback
from pathlib import Path

import lerobot.scripts.lerobot_record as rec
import lerobot.utils.utils as lu
import yaml
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from pynput import keyboard

VOICE = "Microsoft Zira Desktop"  # 설치된 영어 목소리. 목록: 설정 > 시간 및 언어 > 음성
KEYS = {keyboard.Key.right: ("exit_early",),
        keyboard.Key.left: ("rerecord_episode", "exit_early"),
        keyboard.Key.esc: ("stop_recording", "exit_early")}


def say(text, blocking=False):
    cmd = ["PowerShell", "-Command", "Add-Type -AssemblyName System.Speech; "
           "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
           f"$s.SelectVoice('{VOICE}'); $s.Speak('{text}')"]
    (subprocess.run if blocking else subprocess.Popen)(cmd, creationflags=subprocess.CREATE_NO_WINDOW)


_orig_listener = rec.init_keyboard_listener


def init_keyboard_listener():
    listener, events = _orig_listener()
    if listener is None:  # 키보드 없는 환경
        return listener, events
    listener.stop()  # 원래 리스너를 반복 입력을 거르는 것으로 교체
    held = set()

    def on_press(key):
        if key in held:  # 누르고 있는 동안 들어오는 반복 입력
            return
        held.add(key)
        for e in KEYS.get(key, ()):
            events[e] = True
        if key in KEYS:
            print(f"key: {key.name}")

    listener = keyboard.Listener(on_press=on_press, on_release=lambda key: held.discard(key))
    listener.start()
    return listener, events


# 저장 위치 기본값: outputs/datasets/<repo_id의 이름> (--dataset.root를 주면 그쪽 우선)
if not any(a.startswith("--dataset.root") for a in sys.argv):
    repo = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--dataset.repo_id=")), None)
    if repo:
        sys.argv.append(f"--dataset.root=outputs/datasets/{repo.split('/')[-1]}")

def arg(key, cfg):
    """CLI 값 우선, 없으면 yaml 값. key 예: 'robot.port'"""
    for a in sys.argv:
        if a.startswith(f"--{key}="):
            return a.split("=", 1)[1]
    sec, name = key.split(".")
    return cfg[sec][name]


def keep_teleop():
    """녹화가 끝난 뒤에도 Ctrl+C 전까지 텔레옵 유지 (물체 내려놓고 팔 정리용, 녹화는 안 됨)"""
    cfg_path = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--config_path="))
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    follower = SO101Follower(SO101FollowerConfig(port=arg("robot.port", cfg), id=arg("robot.id", cfg)))
    leader = SO101Leader(SO101LeaderConfig(port=arg("teleop.port", cfg), id=arg("teleop.id", cfg)))
    leader.connect()
    follower.connect()
    print("\n녹화 끝. 텔레옵 계속 중 (녹화 안 됨). 팔을 home에 내려놓고 Ctrl+C로 종료")
    try:
        while True:
            follower.send_action(leader.get_action())
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        pass
    finally:
        leader.disconnect()
        follower.disconnect()


lu.say = say  # log_say가 이 모듈의 say를 부름
rec.init_keyboard_listener = init_keyboard_listener  # record()가 이 모듈의 이름으로 부름
sys.argv.append("--robot.disable_torque_on_disconnect=false")  # 녹화 끝나도 팔이 처지지 않게 (텔레옵이 바로 이어받음)
try:
    rec.main()
except Exception:  # 끝날 때 그리퍼 과부하 같은 연결 해제 오류가 나도 데이터는 이미 저장됨 → 텔레옵은 계속
    traceback.print_exc()
keep_teleop()
