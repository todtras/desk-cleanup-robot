"""텔레오퍼레이션 하면서 팔로워의 현재 관절 각도를 이름 붙여 저장.
사용: python scripts/save_poses.py   (s=저장, l=목록, q=종료)
저장 위치: configs/robot/poses.json  예) home, bin_pen_above, bin_pen_drop ...
"""
import json
import msvcrt
import time
from pathlib import Path

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

FOLLOWER_PORT, LEADER_PORT = "COM4", "COM3"  # 포트가 바뀌면 여기만 수정
OUT = Path("configs/robot/poses.json")

follower = SO101Follower(SO101FollowerConfig(port=FOLLOWER_PORT, id="fd_follower"))
leader = SO101Leader(SO101LeaderConfig(port=LEADER_PORT, id="fd_leader"))
leader.connect()
follower.connect()

poses = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
print("s=저장  l=목록  q=종료 (시작하면 팔로워가 리더 자세로 움직임)")
try:
    while True:
        follower.send_action(leader.get_action())
        if msvcrt.kbhit():
            k = msvcrt.getwch()
            if k == "q":
                break
            if k == "l":
                print(list(poses))
            if k == "s":
                pose = {j: round(v, 2) for j, v in follower.get_observation().items() if j.endswith(".pos")}  # s 누른 순간 값
                name = input("\n포즈 이름 (그동안 리더를 놓아도 됨): ").strip()
                if name:
                    poses[name] = pose
                    OUT.parent.mkdir(parents=True, exist_ok=True)
                    OUT.write_text(json.dumps(poses, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"저장: {name} {poses[name]}")
        time.sleep(1 / 60)
finally:
    leader.disconnect()
    follower.disconnect()
