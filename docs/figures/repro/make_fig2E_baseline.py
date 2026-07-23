#!/usr/bin/env python3
"""Figure 2 panel E — non-learned baselines vs learned surrogate (Top-20 recall).
Reproduces the E panel (previously an untracked ad-hoc figure) from
baseline_ranking_comparison.csv, and draws the 'E' panel label to match A-D.
Run: /opt/protein_pipeline/venv/bin/python make_fig2E_baseline.py"""
import csv, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).parent))
import figstyle; figstyle.apply()

ROOT = Path("/opt/protein_pipeline-work")
CSV = next(p for p in [ROOT/"public_data/benchmark/results/baseline_ranking_comparison.csv",
                       ROOT/"data/benchmark/results/baseline_ranking_comparison.csv"] if p.exists())
OUT = ROOT/"docs/figures/fig2E_baseline.png"
P = figstyle.PALETTE
rows = list(csv.DictReader(open(CSV)))
def rec(surr, base, k=20):
    return float(next(r["recall"] for r in rows if r["surrogate"]==surr and r["baseline"]==base and int(r["k"])==k))

panels = [
 ("pLDDT target", "plddt",
  [("Random","Random"),("SoluProt","SoluProt score"),("Seq length","Sequence length"),
   ("ESM-2 PLL","ESM-2 8M PLL"),("Random Forest\n(RAPID, learned)","RF")]),
 ("SoluProt target", "soluprot",
  [("Random","Random"),("pLDDT","pLDDT score"),("Seq length","Sequence length"),
   ("ESM-2 PLL","ESM-2 8M PLL"),("Ridge\n(RAPID, learned)","Ridge")]),
]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
for ax,(title,surr,bars) in zip(axes,panels):
    labels=[b[0] for b in bars]; vals=[rec(surr,b[1]) for b in bars]; rand=vals[0]
    colors=[P["baseline_light"]]+[P["baseline_mid"]]*3+[P["learned"]]
    x=list(range(len(bars)))
    ax.bar(x,vals,color=colors,edgecolor="#333333",linewidth=0.6,width=0.72,zorder=3)
    ax.axhline(rand, ls="--", color=P["random_line"], lw=1.4, zorder=2)
    ax.text(len(bars)-0.45, rand+0.006, "random level", color=P["random_line"], fontsize=8, ha="right", va="bottom")
    for xi,v in zip(x,vals):
        ax.text(xi, v+0.012, f"{v:.3f}", ha="center", va="bottom", fontsize=8.5)
    ax.set_title(title, fontsize=12, fontweight="bold"); ax.set_ylabel("Top-20 recall", fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8.5); ax.tick_params(axis="y", labelsize=9)
    ax.set_ylim(0, max(vals)*1.18)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
axes[0].text(-0.16, 1.14, "E", transform=axes[0].transAxes, fontsize=16, fontweight="bold", va="top", ha="left")
fig.tight_layout()
fig.savefig(OUT, dpi=200, bbox_inches="tight")
print("wrote", OUT)
