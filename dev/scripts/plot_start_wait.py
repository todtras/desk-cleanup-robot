"""보고서 그림: v5 시작 대기 문제와 대응 (11/13). 결과: doc/results/v5_start_wait.png
A = 시연 시작에서 1초 넘게 가만히 있던 에피소드 비율 (물병, 첫 동작과 팔 5관절 차이 합 5도 이내)
B = 같은 시작 화면 10개를 계속 넣었을 때 (= 로봇이 아직 안 움직였을 때), 화면을 다시 보기 전까지 팔이 첫 동작에서 최대 몇 도 벗어나나
    (팔 5관절 차이 합). 대응 전 = 40동작씩 → 첫 40동작, 대응 후 = 대기 건너뛰기 + 60 30 20 → 첫 60동작.
    거의 안 움직이면(STILL도 미만) 같은 화면을 다시 보게 되어 출발을 못 함
값은 11/13 오프라인 확인 결과 (scratchpad moved.py, idle_check.py). 사용: python scripts/plot_start_wait.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BEFORE, AFTER = "#eb6834", "#2a78d6"  # 기본 팔레트 2·1번
STILL = 15

demos = [("10/30 시연", 8, 50), ("11/6 시연", 33, 60)]
moved = {  # 체크포인트: (대응 전, 대응 후), 시작 화면 10개 순서 같음
    "v2 10만": ([99, 67, 64, 93, 114, 145, 123, 193, 117, 100], [279, 233, 71, 220, 214, 249, 248, 308, 309, 238]),
    "v4 10만": ([42, 54, 12, 56, 211, 63, 167, 48, 131, 44], [227, 212, 11, 151, 200, 217, 247, 216, 257, 198]),
    "v5 5만": ([109, 94, 10, 2, 294, 104, 6, 8, 5, 36], [280, 228, 9, 9, 216, 256, 130, 6, 107, 149]),
    "v5 10만": ([135, 101, 4, 3, 286, 129, 14, 2, 4, 74], [309, 232, 1, 12, 295, 185, 152, 20, 100, 119]),
    "v5 26만": ([120, 100, 4, 1, 278, 113, 10, 1, 4, 63], [295, 217, 11, 289, 208, 238, 175, 20, 106, 164]),
    "v5t 1만": ([186, 144, 5, 4, 291, 180, 60, 4, 32, 96], [315, 227, 2, 57, 222, 256, 234, 68, 184, 204]),
    "v5t 2만": ([215, 176, 3, 5, 316, 192, 89, 5, 57, 120], [315, 228, 3, 97, 248, 267, 257, 110, 211, 202]),
}

fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1, 2.6]}, facecolor=SURFACE)
for ax in (a, b):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)

pct = [100 * k / n for _, k, n in demos]
a.bar([d[0] for d in demos], pct, width=0.5, color=AFTER)
for i, (_, k, n) in enumerate(demos):
    a.text(i, pct[i] + 2, f"{pct[i]:.0f}% ({k}/{n})", ha="center", color=INK, fontsize=10)
a.set_ylim(0, 70)
a.set_ylabel("에피소드 비율 (%)", color=INK2)
a.set_title("A. 시작 전 1초 넘게 대기한 시연 (물병)", loc="left", color=INK, fontsize=11)

rng = np.random.default_rng(0)
for i, (name, (bef, aft)) in enumerate(moved.items()):
    for off, ys, c in ((-0.18, bef, BEFORE), (0.18, aft, AFTER)):
        b.scatter(i + off + rng.uniform(-0.07, 0.07, len(ys)), ys, s=30, color=c, edgecolor=SURFACE, lw=1.2, zorder=3)
    nb, na = sum(y < STILL for y in bef), sum(y < STILL for y in aft)
    b.text(i, 335, f"{nb} → {na}", ha="center", color=INK, fontsize=9)
b.axhline(STILL, color=INK2, lw=1, ls="--")
b.text(-0.45, STILL + 6, f"{STILL}도 미만 = 거의 안 움직이고 같은 화면을 다시 봄 (출발 못 함)", ha="left", color=INK2, fontsize=9)
b.set_xticks(range(len(moved)), list(moved))
b.set_ylim(-10, 355)
b.set_ylabel("다시 보기 전까지 움직인 각도 (도)", color=INK2)
b.set_title("B. 같은 시작 화면 10개에서 출발 여부 (위 숫자 = 출발 못 하는 화면 수, 대응 전 → 후)", loc="left", color=INK, fontsize=11)
b.scatter([], [], color=BEFORE, label="대응 전 (40동작씩)")
b.scatter([], [], color=AFTER, label="대응 후 (대기 건너뛰기 + 60·30·20)")
b.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False, labelcolor=INK2, fontsize=9)

fig.tight_layout()
out = Path(__file__).resolve().parents[2] / "doc/results/v5_start_wait.png"
fig.savefig(out, dpi=200, facecolor=SURFACE)
print(out)
