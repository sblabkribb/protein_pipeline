#!/usr/bin/env python3
"""보고서 본문 그림 - 표로 두면 안 읽히는 것만 그래프로 바꾼다.

    fig_exp2_forest   실험 2 의 8 예산점 x 신뢰구간. 표에서는 독자가 구간
                      8 개를 눈으로 0 과 비교해야 한다. forest plot 이 정석이다.
    fig_exp3_budget   실험 3 의 여지 회수율과 백본 퍼짐을 나란히. "수확은 같고
                      폭만 좁다" 가 한 화면에서 보여야 결론이 선다.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[2]
G = ROOT / "public_data" / "benchmark" / "gate0"
FIG = ROOT / "figures" / "benchmark"

_CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if Path(_CJK).exists():
    font_manager.fontManager.addfont(_CJK)
    KR = font_manager.FontProperties(fname=_CJK).get_name()
else:
    KR = "DejaVu Sans"
plt.rcParams.update({"font.family": KR, "font.size": 9})


def forest() -> None:
    """실험 2 · RF − ProteinMPNN · 생성원 2 x 예산 4."""
    j = json.loads((G / "v2_mpnn_baseline.json").read_text())["groups"]
    rows = []
    for src, lbl, col in (("bioemu", "BioEmu", "#2F8F5B"), ("rfd3", "RFD3", "#2D70B8")):
        for B in (100, 80, 60, 40):
            e = j[f"{src}_pooled_cohorts"]["by_budget"][str(B)]["paired_vs"]["rf_probe-mpnn_score"]
            rows.append((f"{lbl}  B={B}", e["delta"], e["ci95"], e["ci99375_bonf8"], col))

    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    for i, (lbl, dlt, ci, bf, col) in enumerate(rows):
        ax.plot(bf, [i, i], color=col, lw=1.2, alpha=.35,
                solid_capstyle="butt", zorder=2)          # 다중성 보정 구간
        ax.plot(ci, [i, i], color=col, lw=3.0, alpha=.9,
                solid_capstyle="butt", zorder=3)          # 명목 95%
        ax.scatter([dlt], [i], s=42, color=col, zorder=4,
                   edgecolor="white", linewidth=.8)
        keep = "보정 후 유지" if (bf[0] > 0 or bf[1] < 0) else ""
        if keep:
            ax.text(bf[1] + .4, i, keep, va="center", fontsize=7.5, color=col)
    ax.axvline(0, color="black", ls="--", lw=1.0, zorder=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.5)
    ax.set_xlabel("표적당 joint-pass 확보량 차이  (RF − ProteinMPNN 점수)")
    ax.set_title("실험 2 · 같은 folding 예산에서의 차이 (29 target×source)\n"
                 "굵은 선 = 명목 95% · 옅은 선 = 다중성 보정(8 검정, 99.375%)",
                 fontsize=10, fontweight="bold")
    ax.grid(axis="x", alpha=.25, lw=.6)
    ax.set_xlim(-6.5, 17)
    fig.tight_layout()
    for e in ("png", "pdf"):
        fig.savefig(FIG / f"fig_exp2_forest.{e}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("fig_exp2_forest")


def budget_and_spread() -> None:
    """실험 3 · 왼쪽 여지 회수율, 오른쪽 닿은 백본 수."""
    h = json.loads((G / "hierarchical_replay.json").read_text())
    e = h["sources"]["rfd3"]["by_budget"]["80"]["point"]
    head = e["oracle_paid"] - e["equal_random"]
    arms = [("mpnn_only_paid", "ProteinMPNN 점수"), ("equal_random", "균등·무작위"),
            ("backbone_only", "백본 배분만"), ("warmup_informed", "RF + 백본 배분"),
            ("rf_only", "RF 순위화만")]
    vals = [(lbl, (e[k] - e["equal_random"]) / head * 100) for k, lbl in arms]
    s = json.loads((G / "backbone_spread.json").read_text())["policies"]

    fig, ax = plt.subplots(1, 2, figsize=(10.4, 3.9),
                           gridspec_kw={"width_ratios": [1.65, 1]})
    cols = ["#B0B0B0" if v[1] <= 0 else "#9CB3C9" for v in vals]
    cols[-1] = "#2D70B8"; cols[-2] = "#2F8F5B"
    ax[0].barh([v[0] for v in vals], [v[1] for v in vals], color=cols, height=.62)
    for i, (lbl, v) in enumerate(vals):
        ax[0].text(v + (.9 if v >= 0 else -.9), i, f"{v:.1f}%", va="center",
                   ha="left" if v >= 0 else "right", fontsize=8.5)
    ax[0].axvline(0, color="black", lw=.9)
    ax[0].set_xlim(-12, 72)
    ax[0].set_xlabel("여지 회수율  (균등·무작위 0% → oracle 100%)")
    ax[0].set_title("수확: 배분을 얹어도 +2.1%p", fontsize=10)
    ax[0].grid(axis="x", alpha=.25, lw=.6)

    names = [("rf_only", "RF 순위화만", "#2D70B8"),
             ("greedy_fill", "RF + 백본 배분", "#2F8F5B")]
    nb = [s[k]["mean_backbones_touched"] for k, _, _ in names]
    ax[1].bar([n[1] for n in names], nb, color=[n[2] for n in names], width=.5)
    for i, (k, _, _) in enumerate(names):
        ax[1].text(i, nb[i] + .2, f"{nb[i]:.1f}개\n최대 편중 "
                   f"{s[k]['mean_max_share']*100:.0f}%", ha="center", fontsize=8.5)
    ax[1].axhline(10, color="#888", ls=":", lw=1.0)
    ax[1].text(1.42, 10.15, "가용 10", fontsize=7.5, color="#666", ha="right")
    ax[1].set_ylim(0, 12)
    ax[1].set_ylabel("선택이 닿은 서로 다른 백본 수")
    ax[1].set_title("폭: 배분은 2개 백본에 91%", fontsize=10)
    ax[1].grid(axis="y", alpha=.25, lw=.6)

    fig.suptitle("실험 3 · RFD3 confirmatory · B=80 — 수확은 같고 폭만 좁다",
                 fontsize=10.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for e_ in ("png", "pdf"):
        fig.savefig(FIG / f"fig_exp3_budget_spread.{e_}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("fig_exp3_budget_spread")


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    forest()
    budget_and_spread()
