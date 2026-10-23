"""lerobot-record 그대로 + 다섯 가지 수정
1) 음성 안내를 영어 목소리로 (윈도우 기본 TTS가 한국어 목소리라 영어를 콩글리시로 읽음)
2) 키를 꾹 누를 때 생기는 반복 입력 무시 (→ 반복 입력이 리셋 시간까지 건너뛰던 문제)
3) 저장 위치 기본값 outputs/datasets/<이름> (lerobot 기본은 ~/.cache)
4) 녹화가 끝나도 끊김 없이 Ctrl+C 전까지 텔레옵 유지 (연결도 그대로 → 끝날 때 그리퍼 과부하 방지)
5) 에피소드 저장 중에 누른 → 무시 (다음 에피소드가 0프레임으로 끝나 녹화가 멈추던 문제)
사용 (dev 폴더에서): python scripts/record.py --config_path=configs/robot/record_pick.yaml [lerobot-record 인자 그대로]
"""
import subprocess
import sys
import threading
import time
import traceback

import lerobot.scripts.lerobot_record as rec
import lerobot.utils.utils as lu
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
_events = []


def init_keyboard_listener():
    listener, events = _orig_listener()
    _events.append(events)  # log_say에서 남은 키 입력을 지우려고 잡아둠
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

_robots, _teleops, _threads = [], [], []
_stop = threading.Event()
_orig_make_robot = rec.make_robot_from_config
_orig_make_teleop = rec.make_teleoperator_from_config
_orig_log_say = rec.log_say


def make_robot_from_config(cfg):
    _robots.append(_orig_make_robot(cfg))  # 녹화 끝난 뒤 텔레옵을 이어가려고 잡아둠
    return _robots[-1]


def make_teleoperator_from_config(cfg):
    _teleops.append(_orig_make_teleop(cfg))
    return _teleops[-1]


def teleop_loop(robot, teleop):
    while not _stop.is_set():
        robot.send_action(teleop.get_action())
        time.sleep(1 / 60)


def log_say(text, *args, **kwargs):
    """- 에피소드/리셋 시작 때 남은 → 입력 지우기: 저장 중에 누른 →가 남아 있으면 다음 에피소드가
      0프레임으로 바로 끝나고, 저장할 때 'add_frame' 에러로 녹화가 멈춤
    - "Stop recording" 순간부터 같은 연결로 텔레옵 계속: lerobot은 마무리(약 6초) 동안 명령을 안 보내고
      연결도 끊음 → 그동안 그리퍼가 쥔 채로 멈춰 과부하(6번 모터 응답 없음)로 재연결 실패하던 문제"""
    if text.startswith(("Recording episode", "Reset the environment")) and _events:
        _events[-1]["exit_early"] = False
    if text == "Stop recording" and _robots and _teleops and _robots[-1].is_connected and _teleops[-1].is_connected:
        robot, teleop = _robots[-1], _teleops[-1]
        for dev in (robot, teleop):  # lerobot이 끊지 못하게. 진짜 끊기는 Ctrl+C 뒤에
            dev.real_disconnect, dev.disconnect = dev.disconnect, lambda: None
        _threads.append(threading.Thread(target=teleop_loop, args=(robot, teleop), daemon=True))
        _threads[-1].start()
    _orig_log_say(text, *args, **kwargs)


lu.say = say  # log_say가 이 모듈의 say를 부름
rec.init_keyboard_listener = init_keyboard_listener  # record()가 이 모듈의 이름으로 부름
rec.make_robot_from_config = make_robot_from_config
rec.make_teleoperator_from_config = make_teleoperator_from_config
rec.log_say = log_say
try:
    rec.main()
except Exception:  # 끝날 때 오류가 나도 데이터는 이미 저장됨 → 텔레옵은 계속
    traceback.print_exc()
if _threads:
    print("\n녹화 끝. 텔레옵 계속 중 (녹화 안 됨). 팔을 home에 내려놓고 Ctrl+C로 종료")
    try:
        while _threads[-1].is_alive():
            _threads[-1].join(0.5)  # 타임아웃을 줘야 윈도우에서 Ctrl+C가 먹음
    except KeyboardInterrupt:
        pass
    _stop.set()
    _threads[-1].join()
    _teleops[-1].real_disconnect()
    _robots[-1].real_disconnect()  # 기본 설정대로 토크 해제 (팔이 처지니 home에 내려놓고 끄기)
