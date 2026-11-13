"""보고서 그림: 출발 대응(대기 건너뛰기 + 예측별 동작 수 60 30 20)의 효과 (11/13). 결과: doc/results/v5_start_fix.png
A = 같은 시작 화면 10개 중 출발 못 하는 화면 수 (다시 보기 전까지 팔 5관절 합 15도 미만 이동), 대응 전(40동작씩) vs 후
B, C = 실제 예시: 같은 시작 화면을 계속 넣고(= 로봇이 아직 안 움직였을 때) 실행되는 동작을 따라감. 세로축 = 첫 동작에서 벗어난 정도
    대응 전은 40동작마다 같은 화면을 다시 보고 같은 짧은 동작을 반복 (실물의 움찔거림, 출발 못 함)
    대응 후는 첫 예측에서 대기를 건너뛰고 60동작을 이어서 실행해 멀리 움직임 (실물이면 여기서 새 화면을 봄)
사용 (dev 폴더): python scripts/plot_start_fix.py   (B, C는 체크포인트로 다시 계산, 1~2분)
"""
import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
logging.disable(logging.WARNING)
import run_auto as ra  # noqa: E402
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # noqa: E402

plt.rcParams["font.family"] = "Malgun Gothic"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BEFORE, AFTER = "#eb6834", "#2a78d6"
STILL = 15
STUCK = {"v2 10만": (0, 0), "v4 10만": (1, 1), "v5 5만": (5, 3), "v5 10만": (5, 2), "v5 26만": (5, 1), "v5t 1만": (3, 1), "v5t 2만": (3, 1)}  # scratchpad moved.py
EXAMPLES = [("v5", "100000", 8, "B. v5 10만: 출발 못 함"), ("v5t", "010000", 7, "C. v5t 1만: 움찔거림")]  # (버전, 스텝, 시작 화면 번호, 제목)


def traces(ver, step, k):
    ds = LeRobotDataset("local/pick_bottle_v5", root="outputs/datasets/pick_bottle_v5")
    n = ds.meta.total_episodes
    f = ds[int(ds.meta.episodes[n - 1 - 3 * k]["dataset_from_index"])]
    obs = {key: v.unsqueeze(0) for key, v in f.items() if key.startswith("observation.")}
    pol, pre, post = ra.load_policy(ra.ckpt_path("bottle", step, ver), "cpu", 40)
    out = []
    for plan, skip, length in (((40,), False, 120), ((60, 30, 20), True, 60)):
        pol.reset()
        ra.plan_chunks(pol, post, plan, skip)
        acts = [post(pol.select_action(pre(obs)))[0]]
        first = len(pol._action_queue) + 1  # 첫 예측에서 실행하는 동작 수 (이 뒤는 실물이면 새 화면을 봄)
        acts = torch.stack(acts + [post(pol.select_action(pre(obs)))[0] for _ in range(length - 1)])
        d = (acts - acts[0]).abs()[:, :5].sum(1).numpy()
        out.append(d if not skip else d[:first])  # 대응 후는 첫 예측까지만 (오프라인은 화면이 안 바뀌어 그 뒤가 의미 없음)
    return out


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), gridspec_kw={"width_ratios": [1.3, 1, 1]}, facecolor=SURFACE)
a = axes[0]
style(a)
xs = range(len(STUCK))
w = 0.36
a.bar([x - w / 2 - 0.01 for x in xs], [v[0] for v in STUCK.values()], w, color=BEFORE, label="대응 전 (40동작씩)")
a.bar([x + w / 2 + 0.01 for x in xs], [v[1] for v in STUCK.values()], w, color=AFTER, label="대응 후 (대기 건너뛰기 + 60·30·20)")
for x, (b0, b1) in zip(xs, STUCK.values()):
    a.text(x - w / 2, b0 + 0.15, str(b0), ha="center", color=INK, fontsize=9)
    a.text(x + w / 2, b1 + 0.15, str(b1), ha="center", color=INK, fontsize=9)
a.set_xticks(list(xs), list(STUCK), fontsize=9)
a.set_ylim(0, 7)
a.set_ylabel("출발 못 하는 시작 화면 (10개 중)", color=INK2)
a.set_title("A. 출발 못 하는 화면 수", loc="left", color=INK, fontsize=11)
a.legend(loc="upper left", frameon=False, labelcolor=INK2, fontsize=9)

for ax, (ver, step, k, title) in zip(axes[1:], EXAMPLES):
    style(ax)
    before, after = traces(ver, step, k)
    ax.plot(range(len(before)), before, color=BEFORE, lw=2, label="대응 전")
    ax.plot(range(len(after)), after, color=AFTER, lw=2, label="대응 후")
    for r in (40, 80):
        ax.axvline(r, color=GRID, lw=1)
    ax.text(80, max(before) + max(after) * 0.05, f"대응 전: 40동작마다 같은 화면을 다시 보고\n같은 짧은 동작만 반복 (최대 {max(before):.0f}도)",
            color=BEFORE, fontsize=8.5, ha="center", va="bottom")
    ax.annotate(f"대응 후: {after[-1]:.0f}도 이동 → 출발\n(실물은 여기서 새 화면을 봄)", (len(after) - 1, after[-1]), xytext=(8, -2),
                textcoords="offset points", ha="left", va="top", color=AFTER, fontsize=9)
    ax.set_xlim(0, 120)
    ax.set_ylim(-5, max(after) * 1.12)
    ax.set_xlabel("실행한 동작 수", color=INK2)
    ax.set_ylabel("첫 동작에서 벗어난 정도 (팔 5관절 합, 도)", color=INK2)
    ax.set_title(title, loc="left", color=INK, fontsize=11)

fig.tight_layout()
out = Path(__file__).resolve().parents[2] / "doc/results/v5_start_fix.png"
fig.savefig(out, dpi=200, facecolor=SURFACE)
print(out)
