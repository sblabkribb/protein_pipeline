#!/usr/bin/env python3
"""Plot Solu_monomer 5-enzyme paired comparison (Original vs Ensemble)."""
import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

DETAIL = Path("/opt/protein_pipeline-work/data/benchmark/results/solu_monomer_optA_per_target.csv")
OUT_PNG = Path("/opt/protein_pipeline-work/figures/benchmark/fig_solu_monomer_optA.png")

# Read data
rows = list(csv.DictReader(DETAIL.open()))
targets = sorted({r["target"] for r in rows})
data = {t: {} for t in targets}
for r in rows:
    data[r["target"]][r["condition"]] = r

metrics = [
    ("plddt_range", "pLDDT range", "(AF2 max - min)"),
    ("soluprot_range", "SoluProt range", "(max - min)"),
    ("mean_pairwise_diversity", "Mean pairwise diversity", "(1 - identity)"),
]
PALETTE = {"original": "#7f7f7f", "ensemble": "#1f77b4"}

fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))
for ax, (key, title, sub) in zip(axes, metrics):
    x_pos = np.array([0, 1])
    for i, t in enumerate(targets):
        try:
            ovals = float(data[t]["original"][key])
            evals = float(data[t]["ensemble"][key])
        except (KeyError, ValueError):
            continue
        ax.plot(x_pos, [ovals, evals], "o-", color="#bbbbbb", linewidth=0.9, markersize=4, zorder=2)
        ax.text(1.05, evals, t, fontsize=7, va="center", color="#444")
    # Group mean markers
    o_means = [float(data[t]["original"][key]) for t in targets if data[t]["original"].get(key)]
    e_means = [float(data[t]["ensemble"][key]) for t in targets if data[t]["ensemble"].get(key)]
    ax.scatter([0]*len(o_means), o_means, color=PALETTE["original"], s=44, zorder=3,
               edgecolor="black", linewidth=0.6, label="Original")
    ax.scatter([1]*len(e_means), e_means, color=PALETTE["ensemble"], s=44, zorder=3,
               edgecolor="black", linewidth=0.6, label="Ensemble")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Original\n(target backbone)", "Ensemble\n(RFD3+BioEmu)"])
    ax.set_xlim(-0.3, 1.45)
    ax.set_title(title, fontsize=10.5)
    ax.set_xlabel(sub, fontsize=8.5, color="#555")
    ax.grid(axis="y", linestyle=":", alpha=0.4)

axes[0].legend(loc="upper left", fontsize=8.5, frameon=False)
fig.suptitle(
    "Solu_monomer 5-enzyme corroboration: Ensemble broadens spread and diversity (5/5 targets, p = 0.0625)",
    fontsize=10.5, y=0.98, fontweight="bold"
)
fig.text(0.5, 0.005,
         "Original = single (target) backbone; Ensemble = bioemu + rfd3_single + rfd3_bioemu (combined). "
         "Tier 50% conservation; paired across 5 targets; Wilcoxon W+=15.",
         ha="center", fontsize=7.8, color="#555")
plt.tight_layout(rect=(0, 0.03, 1, 0.95))
OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT_PNG, dpi=180, bbox_inches="tight")
print(f"Wrote: {OUT_PNG}")
