"""merge_v4 확인: 실제 Collector 저장 형식의 가짜 에피소드를 시연 데이터셋과 합쳐 봄 (로봇 없이, 임시 폴더에서).
실행 (dev 폴더에서): python scripts/test_merge_v4.py [임시 폴더]
"""
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import merge_v4
import run_auto
from lerobot.datasets.utils import hw_to_dataset_features
from lerobot.utils.constants import ACTION, OBS_STR

tmp = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
shutil.copytree(merge_v4.ROOT / "pick_tape_v2", tmp / "pick_tape_v2")
base = merge_v4.load(tmp, "pick_tape_v2")

assert merge_v4.merge(tmp, "pick_tape_v4", merge_v4.plan("tape")["pick_tape_v4"]) is None  # 추가 데이터 없으면 건너뜀

joints = [n.removeprefix("observation.state.") for n in base.features["observation.state"]["names"]]
hw = {j: float for j in joints}
cams = {"head": (480, 640, 3), "wrist": (480, 640, 3)}
features = {**hw_to_dataset_features({**hw, **cams}, OBS_STR), **hw_to_dataset_features(hw, ACTION)}
run_auto.DATA_ROOT = tmp
collector = run_auto.Collector(features, base.meta.robot_type, "pick up the object and lift it")
for kind, n in (("dagger", 2), ("success", 1)):
    for _ in range(n):
        frame = {**{j: 1.0 for j in joints}, **{c: np.zeros(s, np.uint8) for c, s in cams.items()}}
        collector.save(kind, "tape", [(frame, {j: 2.0 for j in joints})] * 30)
collector.close()

n = merge_v4.merge(tmp, "pick_tape_v4", merge_v4.plan("tape")["pick_tape_v4"])
assert n == base.num_episodes + 3, n
merged = merge_v4.load(tmp, "pick_tape_v4")
last = merged[len(merged) - 1]
assert last["action"].allclose(last["action"] * 0 + 2.0), last["action"]  # 합친 뒤에도 교정 프레임의 명령이 그대로
assert last["observation.images.head"].shape == (3, 480, 640)
try:
    merge_v4.merge(tmp, "pick_tape_v4", merge_v4.plan("tape")["pick_tape_v4"])
    raise AssertionError("덮어쓰면 안 됨")
except SystemExit:
    pass
assert set(merge_v4.plan("eraser")) == {"pick_eraser_v4a", "pick_eraser_v4b"} and "pick_eraser_success" not in merge_v4.plan("eraser")["pick_eraser_v4a"]
print("OK", tmp)
