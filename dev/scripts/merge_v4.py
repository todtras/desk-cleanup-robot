"""재학습용 합치기: 시연(_v2) + 사람 시연 보강(_demo) + 교정(_dagger) + 성공 시도(_success) → pick_<물체>_v4
지우개만 효과 비교용으로 v4a(성공 시도 제외) / v4b(포함) 두 개. 원본은 건드리지 않고, 추가 데이터가 없는 물체는 건너뜀.
노트북의 지우개·종이 _v2는 약한 위치 보강까지 들어간 것 (서버의 _v3와 같음)
사용 (dev 폴더에서): python scripts/merge_v4.py [물체 ...]   결과: outputs/datasets/pick_<물체>_v4
"""
import argparse
from pathlib import Path

from lerobot.datasets.dataset_tools import merge_datasets
from lerobot.datasets.lerobot_dataset import LeRobotDataset

OBJECTS = ("tape", "bottle", "pen", "eraser", "paper")
ROOT = Path(__file__).resolve().parent.parent / "outputs/datasets"


def load(root, name):
    return LeRobotDataset(f"local/{name}", root=root / name, video_backend="pyav")


def plan(obj):
    """{결과 이름: 합칠 데이터셋}"""
    base = [f"pick_{obj}_{kind}" for kind in ("v2", "demo", "dagger")]
    success = f"pick_{obj}_success"
    return {f"pick_{obj}_v4a": base, f"pick_{obj}_v4b": [*base, success]} if obj == "eraser" else {f"pick_{obj}_v4": [*base, success]}


def merge(root, out, parts):
    """있는 데이터셋만 합침. 결과가 이미 있으면 덮어쓰지 않음. 개수와 마지막 프레임을 확인하고 합친 개수 반환 (추가 데이터가 없으면 None)"""
    if not (root / parts[0] / "meta/info.json").exists():
        raise SystemExit(f"기준 데이터셋 없음: {root / parts[0]}")
    have = [p for p in parts if (root / p / "meta/info.json").exists()]
    if len(have) == 1:
        print(f"[건너뜀] {out}: 추가 데이터 없음")
        return None
    if (root / out).exists():
        raise SystemExit(f"이미 있음: {root / out} (확인 후 직접 지우고 다시 실행)")
    sources = [load(root, p) for p in have]
    merge_datasets(sources, f"local/{out}", output_dir=root / out)
    merged = load(root, out)
    want = sum(s.num_episodes for s in sources), sum(s.num_frames for s in sources)
    assert (merged.num_episodes, merged.num_frames) == want, f"{out}: 개수 불일치 {merged.num_episodes, merged.num_frames} != {want}"
    merged[len(merged) - 1]  # 마지막 프레임 영상까지 실제로 읽히는지
    print(f"{out}: {merged.num_episodes}개, {merged.num_frames}프레임 ← " + " + ".join(f"{p} {s.num_episodes}" for p, s in zip(have, sources)))
    return merged.num_episodes


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("objects", nargs="*", default=OBJECTS, help="물체 이름 (생략하면 전부)")
    for obj in ap.parse_args().objects:
        for out, parts in plan(obj).items():
            merge(ROOT, out, parts)
