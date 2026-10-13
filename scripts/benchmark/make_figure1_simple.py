#!/usr/bin/env python3
"""Polished main Figure 1 for the BiB submission.

A single landscape schematic of the resource-aware triage flow, with visual
grouping (cheap/local vs the AlphaFold2/ColabFold budget), stage badges, a
budget bracket, and a reduction callout. Implementation detail (standardized
tool interface / agents / cloud backends / QC-recovery) is intentionally
omitted here and shown in the Supplementary implementation figure instead.
"""
from __future__ import annotations
import os
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT") or Path(__file__).resolve().parents[2])
OUT = ROOT / "figures" / "fig1_simple.png"

# palette
INK = "#1F2A37"
STAGES = [
    # (title, subtitle, face, edge, group)
    ("ProteinMPNN\ncandidates", "~10,000 / target", "#E8EDF4", "#4A6FA5", "local"),
    ("SoluProt filter\n+ ESM-2 embedding", "cheap, local", "#E8EDF4", "#4A6FA5", "local"),
    ("AF2/ColabFold\nseed labels", "30 calls", "#FBE7CC", "#C77F2E", "af2"),
    ("Local surrogate\nmodel", "per-run CV", "#D8EDDE", "#3E8E5E", "surrogate"),
    ("AF2/ColabFold\nacquisition", "Top-20 · 20 calls", "#FBE7CC", "#C77F2E", "af2"),
    ("Ranked candidates\n+ run record", "reproducible", "#EAE1F2", "#6F4B9A", "out"),
]


def rounded(ax, x, y, w, h, face, edge, lw=2.0, z=3):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0.02,rounding_size=0.14",
                 linewidth=lw, edgecolor=edge, facecolor=face, zorder=z))


def main() -> int:
    n = len(STAGES)
    pitch, bw, bh, y = 3.0, 2.35, 1.9, 1.35
    fig, ax = plt.subplots(figsize=(17, 5.2))
    ax.set_xlim(0, n * pitch)
    ax.set_ylim(-0.1, 5.0)
    ax.axis("off")

    xs = [i * pitch + (pitch - bw) / 2 for i in range(n)]

    # --- group background bands ---
    def band(i0, i1, face, edge, label, ly):
        x0 = xs[i0] - 0.18
        x1 = xs[i1] + bw + 0.18
        ax.add_patch(FancyBboxPatch((x0, y - 0.5), x1 - x0, bh + 1.0,
                     boxstyle="round,pad=0.02,rounding_size=0.12",
                     linewidth=1.3, edgecolor=edge, facecolor=face,
                     linestyle=(0, (5, 3)), zorder=1))
        ax.text((x0 + x1) / 2, ly, label, ha="center", va="center",
                fontsize=12.5, fontweight="bold", color=edge, zorder=2)

    band(0, 1, "#F5F8FC", "#4A6FA5", "Cheap / local — no structure prediction", y + bh + 0.72)
    band(2, 4, "#FEF7EC", "#C77F2E",
         "AlphaFold2 / ColabFold budget — 50 calls per target", y + bh + 0.72)

    # --- boxes with soft shadow + number badge ---
    for i, (title, sub, face, edge, grp) in enumerate(STAGES):
        x = xs[i]
        rounded(ax, x + 0.05, y - 0.06, bw, bh, "#0000000F", "#0000000F", lw=0, z=2)  # shadow
        rounded(ax, x, y, bw, bh, face, edge, lw=2.4 if grp == "af2" else 2.0, z=3)
        ax.text(x + bw / 2, y + bh * 0.60, title, ha="center", va="center",
                fontsize=14.5, fontweight="bold", color=INK, zorder=4)
        ax.text(x + bw / 2, y + bh * 0.22, sub, ha="center", va="center",
                fontsize=11, style="italic", color=edge, zorder=4)
        # number badge
        bx, by = x + 0.30, y + bh - 0.02
        ax.add_patch(Circle((bx, by), 0.20, facecolor=edge, edgecolor="white", lw=1.5, zorder=6))
        ax.text(bx, by, str(i + 1), ha="center", va="center", fontsize=11,
                fontweight="bold", color="white", zorder=7)

    # --- arrows between boxes ---
    for i in range(n - 1):
        arr = FancyArrowPatch((xs[i] + bw + 0.02, y + bh / 2),
                              (xs[i + 1] - 0.02, y + bh / 2),
                              arrowstyle="-|>", mutation_scale=24, linewidth=2.4,
                              color="#4B5563", zorder=5)
        ax.add_patch(arr)

    # --- reduction callout (funnel) below, labels UNDER the arrow to avoid the bands ---
    cy = 0.62
    ax.annotate("", xy=(xs[5] + bw / 2, cy), xytext=(xs[0] + bw / 2, cy),
                arrowprops=dict(arrowstyle="-|>", lw=2.2, color="#9CA3AF"), zorder=2)
    ax.text(xs[0] + bw / 2, cy - 0.30, "~10,000 candidates", ha="center", va="top",
            fontsize=11.5, color="#374151", fontweight="bold")
    ax.text((xs[2] + xs[4]) / 2 + bw / 2, cy - 0.30, "50 folded  (~0.5%, 1/200)",
            ha="center", va="top", fontsize=11.5, color="#7B241C", fontweight="bold")
    ax.text(xs[5] + bw / 2, cy - 0.30, "20 ranked", ha="center", va="top",
            fontsize=11.5, color="#374151", fontweight="bold")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=220, bbox_inches="tight", facecolor="white")
    print("saved", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
