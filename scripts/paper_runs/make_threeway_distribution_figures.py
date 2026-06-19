#!/usr/bin/env python3
"""Distribution-aware figures (box-and-whisker + per-target strip + paired lines)
for the two structural-context three-arm diversity results, replacing means-only
bars so the spread/variance is visible.

  fig13_structural_context_threeway_N9.png  <- structural_context_threeway_N9.csv (N=9 CATH)
  fig_solu_monomer_threeway.png             <- solu_monomer_threeway/monomer_threeway_per_target.csv (N=5 enzymes)
"""
from __future__ import annotations
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PR = Path("/opt/protein_pipeline-work")
RES = PR / "public_data" / "benchmark" / "results"
FIG = PR / "figures" / "benchmark"
C = {"single": "#2D70B8", "pool": "#9CB3C9", "surr": "#2F8F5B"}


def _box_strip(ax, series, labels, colors, title, ylabel, paired_from=None, paired_to=None, seed=0):
    """series: list of arrays (one per arm). Draw box + jittered points; optional paired lines."""
    pos = np.arange(1, len(series) + 1)
    bp = ax.boxplot(series, positions=pos, widths=0.55, patch_artist=True,
                    showmeans=True, meanprops=dict(marker="D", markerfacecolor="black",
                    markeredgecolor="black", markersize=4),
                    medianprops=dict(color="#444444"), flierprops=dict(marker="", alpha=0))
    for patch, col in zip(bp["boxes"], colors):
        patch.set_facecolor(col); patch.set_alpha(0.45); patch.set_edgecolor(col)
    rng = np.random.default_rng(seed)
    # individual targets as jittered points only (no connecting lines, for a cleaner look;
    # the paired result is reported via the title/caption statistics)
    for idx in range(len(series)):
        xj = pos[idx] + rng.uniform(-0.10, 0.10, size=len(series[idx]))
        ax.scatter(xj, series[idx], s=24, color=colors[idx], edgecolor="white",
                   linewidth=0.5, zorder=3, alpha=0.9)
    ax.set_xticks(pos); ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=8.5)
    ax.set_title(title, fontsize=11, fontweight="bold"); ax.set_ylabel(ylabel, fontsize=9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)


def fig_n9():
    rows = list(csv.DictReader(open(RES / "structural_context_threeway_N9.csv")))
    g = lambda k: np.array([float(r[k]) for r in rows])
    div = [g("single_div"), g("ensRandom_div"), g("ensSurr_div")]
    pl = [g("single_plddt"), g("ensRandom_plddt"), g("ensSurr_plddt")]
    so = [g("single_soluprot"), g("ensRandom_soluprot"), g("ensSurr_soluprot")]
    labs = ["Single\n+surrogate", "RFD3+BioEmu\npool (random)", "RFD3+BioEmu\n+surrogate"]
    cols = [C["single"], C["pool"], C["surr"]]
    fig, ax = plt.subplots(1, 3, figsize=(12.5, 4.3))
    _box_strip(ax[0], div, labs, cols, "Top-K sequence diversity", "mean pairwise diversity",
               paired_from=0, paired_to=2, seed=1)
    _box_strip(ax[1], pl, labs, cols, "Selected-set pLDDT", "mean pLDDT", seed=2)
    _box_strip(ax[2], so, labs, cols, "Selected-set SoluProt", "mean SoluProt", seed=3)
    fig.suptitle("Structural-context three-arm comparison — 9 CATH targets "
                 "(diversity 9/9 up, 4.2x, paired Wilcoxon p=0.0039)", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    for e in ("png", "pdf"):
        fig.savefig(FIG / f"fig13_structural_context_threeway_N9.{e}", dpi=200, bbox_inches="tight")
    print("wrote", FIG / "fig13_structural_context_threeway_N9.png")


def fig_monomer():
    rows = list(csv.DictReader(open(RES / "solu_monomer_threeway" / "monomer_threeway_per_target.csv")))
    by = {}
    for r in rows:
        by.setdefault(r["arm"], {})[r["enzyme"]] = r
    enz = [r["enzyme"] for r in rows if r["arm"] == "single_surr"]
    col = lambda arm, k: np.array([float(by[arm][e][k]) for e in enz])
    div = [col("single_surr", "diversity"), col("ens_pool", "diversity"), col("ens_surr", "diversity")]
    so = [col("single_surr", "soluprot_mean"), col("ens_pool", "soluprot_mean"), col("ens_surr", "soluprot_mean")]
    pl = [col("single_surr", "plddt_mean"), col("ens_pool", "plddt_mean"), col("ens_surr", "plddt_mean")]
    labs3 = ["Single\n+surrogate", "RFD3+BioEmu\npool (random)", "RFD3+BioEmu\n+surrogate"]
    cols3 = [C["single"], C["pool"], C["surr"]]
    fig, ax = plt.subplots(1, 3, figsize=(12.5, 4.3))
    _box_strip(ax[0], div, labs3, cols3, "Top-K sequence diversity", "mean pairwise diversity",
               paired_from=0, paired_to=2, seed=1)
    _box_strip(ax[1], so, labs3, cols3, "Selected-set SoluProt", "mean SoluProt", seed=2)
    _box_strip(ax[2], pl, labs3, cols3, "pLDDT (pool = bootstrap labels)", "mean pLDDT", seed=3)
    fig.suptitle("Structural-context three-arm comparison — 5 Solu_pipeline_benchmark monomer enzymes "
                 "(diversity 5/5 up, 1.7x, paired Wilcoxon p=0.0625)", fontsize=10.5, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    for e in ("png", "pdf"):
        fig.savefig(FIG / f"fig_solu_monomer_threeway.{e}", dpi=200, bbox_inches="tight")
    print("wrote", FIG / "fig_solu_monomer_threeway.png")


if __name__ == "__main__":
    fig_n9()
    fig_monomer()
