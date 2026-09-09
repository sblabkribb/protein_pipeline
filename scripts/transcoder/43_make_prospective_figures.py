#!/usr/bin/env python3
"""전향 홀드아웃 결과 그림. 수치는 전부 동결된 산출물에서 읽는다.

그림에 숫자를 손으로 적지 않는다. 원고·기록 문서·그림이 각각 사본을 들고 있으면
재계산할 때마다 셋이 어긋나고, 그게 초록에 옛 AUC 가 남았던 경로다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
FIGURES = PROJECT_ROOT / "figures" / "benchmark"

PALETTE = {"adaptive": "#00796B", "uniform": "#E69F00", "oracle": "#6B7280",
           "static": "#56B4E9", "accent": "#CC79A7", "dark": "#111827",
           "light": "#E5E7EB"}


def style() -> None:
    plt.rcParams.update({
        "figure.dpi": 120, "savefig.dpi": 350,
        "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.6,
        "legend.frameon": False, "legend.fontsize": 8,
    })


def panel_a(ax, alloc) -> None:
    caps = sorted((int(k) for k in alloc["results_by_budget"]), key=int)
    rows = [alloc["results_by_budget"][str(c)] for c in caps]
    ax.plot(caps, [r["oracle"]["mean_found"] for r in rows], color=PALETTE["oracle"],
            ls=":", lw=1.4, label="oracle (true yields known)")
    ax.plot(caps, [r["adaptive"]["mean_found"] for r in rows], color=PALETTE["adaptive"],
            lw=2.0, label="hierarchical adaptive")
    ax.plot(caps, [r[f"static_k{r['posthoc_best_static_k']}"]["mean_found"] for r in rows],
            color=PALETTE["uniform"], lw=1.6, label="static, post-hoc best $k$")
    ax.set_xlabel("budget cap (AF2 calls per target)")
    ax.set_ylabel("joint-pass designs found")
    ax.set_title("A  Primary endpoint: yield at matched cap", loc="left", weight="bold")
    ax.legend(loc="upper left")


def panel_b(ax, alloc) -> None:
    caps = sorted((int(k) for k in alloc["results_by_budget"]), key=int)
    rows = [alloc["results_by_budget"][str(c)]["primary_comparison"] for c in caps]
    mean = [r["mean"] for r in rows]
    lo = [r["ci95"][0] for r in rows]
    hi = [r["ci95"][1] for r in rows]
    ax.axhline(0.0, color=PALETTE["dark"], lw=0.8)
    ax.fill_between(caps, lo, hi, color=PALETTE["adaptive"], alpha=0.18, lw=0)
    ax.plot(caps, mean, color=PALETTE["adaptive"], lw=1.8)
    sig = [(c, m) for c, m, r in zip(caps, mean, rows) if r["excludes_zero"]]
    if sig:
        ax.scatter(*zip(*sig), s=14, color=PALETTE["adaptive"], zorder=3,
                   label="95% CI excludes 0")
    first = min((c for c, r in zip(caps, rows) if r["excludes_zero"]), default=None)
    if first is not None:
        ax.axvline(first, color=PALETTE["accent"], ls="--", lw=1.0)
        ax.annotate(f"probe floor\nends at cap {first}", xy=(first, min(lo)),
                    xytext=(first + 6, min(lo)), fontsize=7.5,
                    color=PALETTE["accent"], va="bottom")
    ax.set_xlabel("budget cap (AF2 calls per target)")
    ax.set_ylabel("adaptive − static (designs)")
    ax.set_title("B  Difference, target-clustered 95% CI", loc="left", weight="bold")
    ax.legend(loc="upper left")


def panel_c(ax, realized) -> None:
    """실현 계산량 대 성공 수. 예산 상한이 아니라 실제로 쓴 호출이 x 축이다."""
    for policy, colour, label in (("adaptive", PALETTE["adaptive"], "hierarchical adaptive"),
                                  (None, PALETTE["uniform"], "uniform allocation")):
        pts = [p for p in realized["pareto"]
               if (p["policy"] == "adaptive") == (policy == "adaptive")]
        pts.sort(key=lambda p: p["calls"])
        ax.plot([p["calls"] for p in pts], [p["successes"] for p in pts],
                color=colour, lw=1.6, marker="o", ms=3.2, label=label)
        front = [p for p in pts if p["on_frontier"]]
        if front:
            ax.scatter([p["calls"] for p in front], [p["successes"] for p in front],
                       s=42, facecolors="none", edgecolors=colour, lw=1.3, zorder=3)
    ax.set_xlabel("AF2 calls actually used")
    ax.set_ylabel("joint-pass designs found")
    ax.set_title("C  Realized compute (rings = Pareto frontier)", loc="left", weight="bold")
    ax.legend(loc="upper left")


def panel_d(ax, variance) -> None:
    roles = variance["result_roles"]
    prim, supp = roles["primary"], roles["supplementary_consistency"]
    n = variance["cohorts"]["rfd3_only_primary"]["n_designs"]
    # barh 는 아래에서 위로 쌓으므로, 주 결과가 위에 오도록 순서를 뒤집는다.
    labels = ["temperature panel\n(supplementary check)",
              f"balanced prospective\n(primary, {n:,} designs)"]
    keys = ("target", "backbone_within_target", "sequence_within_backbone")
    names = ("target", "backbone within target", "sequence within backbone")
    colours = (PALETTE["adaptive"], PALETTE["static"], PALETTE["light"])
    left = [0.0, 0.0]
    for key, name, colour in zip(keys, names, colours):
        vals = [supp["values"][key] * 100, prim["values"][key] * 100]
        ax.barh(labels, vals, left=left, color=colour, label=name,
                edgecolor="white", height=0.42)
        for i, (v, l) in enumerate(zip(vals, left)):
            ax.text(l + v / 2, i, f"{v:.1f}", ha="center", va="center", fontsize=7.5,
                    color=PALETTE["dark"] if colour == PALETTE["light"] else "white")
        left = [a + b for a, b in zip(left, vals)]
    ax.set_xlabel("% of structural-pass variance attributed")
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.75, 1.9)
    ax.set_title("D  Variance attribution (sum of squares)", loc="left", weight="bold")
    # 범례를 막대 위 여백에 가로로 눕힌다. 오른쪽 아래에 두면 21.9 라벨을 덮는다.
    ax.legend(loc="lower center", ncol=3, fontsize=7.2,
              bbox_to_anchor=(0.5, -0.34), columnspacing=1.1, handlelength=1.3)
    ax.grid(axis="y", visible=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(FIGURES / "fig5_prospective_allocation.png"))
    args = ap.parse_args()

    alloc = json.loads((BASE / "holdout_grid" /
                        "prospective_allocation_validation_joint.json").read_text(encoding="utf-8"))
    realized = json.loads((BASE / "holdout_grid" /
                           "realized_compute_analysis.json").read_text(encoding="utf-8"))
    variance = json.loads((BASE / "holdout_grid" /
                           "variance_decomposition_grid.json").read_text(encoding="utf-8"))

    style()
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.4))
    panel_a(axes[0][0], alloc)
    panel_b(axes[0][1], alloc)
    panel_c(axes[1][0], realized)
    panel_d(axes[1][1], variance)
    fig.tight_layout(pad=1.6)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    print(f"wrote {out}\nwrote {out.with_suffix('.pdf')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
