#!/usr/bin/env python3
"""Figure 1 — RAPID orchestration overview (code-generated, reproducible).

Replaces the hand-made PPT export with a matplotlib diagram so terminology and
layout stay in sync with the manuscript (seed labels, run record, local/GPU/
RunPod execution, LLM-agent entry). Run:

    python scripts/benchmark/make_figure1_orchestration.py

Output: figures/benchmark/figure1_orchestration.png (+ .pdf)
"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figures" / "benchmark" / "figure1_orchestration.png"

C = {
    "ink": "#111827", "muted": "#4b5563",
    "navy": "#1f2d3d", "navy_box": "#33475b",
    "tool": "#D9E2F3", "tool_edge": "#9bb0d0",
    "teal": "#00796B", "green": "#A4C8A4", "green_edge": "#6f9c6f",
    "neutral": "#EEF1F5", "neutral_edge": "#c7ced8",
    "amber": "#FFE5A0", "amber_edge": "#d9b84e",
    "highlight": "#00796B",
}


def box(ax, x, y, w, h, *, fc, ec, lw=1.0, r=0.025):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.0,rounding_size={r}",
        linewidth=lw, facecolor=fc, edgecolor=ec, zorder=2))


def text(ax, x, y, s, *, fs=9, color="#111827", weight="normal", ha="center", va="center", rotation=0):
    ax.text(x, y, s, fontsize=fs, color=color, fontweight=weight, ha=ha, va=va,
            rotation=rotation, zorder=4)


def varrow(ax, x, y0, y1, *, color="#6b7280", lw=1.6):
    ax.add_patch(FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>", mutation_scale=12,
                                 linewidth=lw, color=color, zorder=3))


def harrow(ax, x0, x1, y, *, color="#6b7280", lw=1.3):
    ax.add_patch(FancyArrowPatch((x0, y), (x1, y), arrowstyle="-|>", mutation_scale=10,
                                 linewidth=lw, color=color, zorder=3))


def main() -> Path:
    fig, ax = plt.subplots(figsize=(11.6, 7.0))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

    # ---- Title ----
    text(ax, 50, 97, "RAPID: orchestration-driven, resource-aware protein redesign",
         fs=15.5, weight="bold")
    text(ax, 50, 92.4,
         "A single request flows through the orchestration + MCP layer to modular model tools and a resource-aware surrogate, "
         "all preserved under one run record.",
         fs=9.2, color=C["muted"])

    # ---- 1. REQUEST ----
    box(ax, 6, 82, 88, 6.6, fc=C["neutral"], ec=C["neutral_edge"])
    text(ax, 9.5, 85.3, "①\nREQUEST", fs=9, weight="bold", color=C["teal"])
    text(ax, 40, 86.4, "design request   ·   target · mask / position constraints · resource budget · mode",
         fs=9.3, weight="bold")
    text(ax, 40, 83.7, "entry: web UI  ·  MCP client  ·  API  ·  LLM agent (natural language)",
         fs=8.4, color=C["muted"])
    varrow(ax, 50, 81.8, 79.2)

    # ---- 2. ORCHESTRATION LAYER ----
    box(ax, 6, 69.5, 88, 9.5, fc=C["navy"], ec=C["navy"])
    text(ax, 11, 74.2, "②\nORCHESTRATION\nLAYER (MCP)", fs=8.8, weight="bold", color="white")
    sub = ["command\ninterpreter", "stage\nsequencing", "standard tool\ninterface (MCP)",
           "rule-based\nQC", "auto-\nrecovery"]
    sx, sw, sgap = 24.5, 12.3, 2.0
    for i, s in enumerate(sub):
        x = sx + i * (sw + sgap)
        box(ax, x, 71.2, sw, 6.2, fc=C["navy_box"], ec="#52677d", r=0.03)
        text(ax, x + sw / 2, 74.3, s, fs=8.0, color="white")
    varrow(ax, 50, 69.3, 66.8)

    # ---- 3. MODEL TOOLS ----
    box(ax, 6, 55.5, 88, 11.0, fc="#F7F9FC", ec=C["neutral_edge"])
    text(ax, 50, 64.6, "③  MODEL TOOLS   —   executed on local · institutional · cloud GPU (config-selected)",
         fs=9.2, weight="bold")
    tools = [("MMseqs2", "MSA search"), ("RFD3", "backbone gen"), ("BioEmu", "conformer ens."),
             ("ProteinMPNN", "sequence design"), ("SoluProt", "solubility"), ("AF2/ColabFold", "structure check")]
    tx, tw, tgap = 8.5, 12.6, 1.8
    for i, (nm, dt) in enumerate(tools):
        x = tx + i * (tw + tgap)
        box(ax, x, 56.6, tw, 5.6, fc=C["tool"], ec=C["tool_edge"], r=0.04)
        text(ax, x + tw / 2, 60.1, nm, fs=8.7, weight="bold")
        text(ax, x + tw / 2, 57.9, dt, fs=7.4, color=C["muted"])
        if i < len(tools) - 1:
            harrow(ax, x + tw + 0.2, x + tw + tgap - 0.2, 59.4, lw=0.9, color="#9aa6b4")
    varrow(ax, 50, 55.3, 52.6)

    # ---- 4. RESOURCE-AWARE SURROGATE TRIAGE ----
    box(ax, 6, 27.5, 88, 24.5, fc="#F1F6F2", ec=C["green_edge"])
    text(ax, 50, 49.4, "④  RESOURCE-AWARE SURROGATE TRIAGE", fs=10.0, weight="bold", color=C["teal"])
    text(ax, 50, 46.6, "a local surrogate ranks the post-SoluProt design pool so only the most promising candidates spend a structure-prediction call",
         fs=8.2, color=C["muted"])
    flow = ["~10,000\ndesigns", "SoluProt\nfilter", "ESM-2 8M\nembed",
            "K-means\nseed (N=30)", "surrogate\nCV select", "Top-K = 20\nacquire", "AF2/ColabFold\nfold"]
    fcs = [C["neutral"], C["amber"], C["tool"], C["green"], C["green"], C["green"], "#F4B8AB"]
    fes = [C["neutral_edge"], C["amber_edge"], C["tool_edge"], C["green_edge"], C["green_edge"], C["green_edge"], "#d68b79"]
    fx, fw, fgap = 7.5, 10.7, 1.7
    for i, s in enumerate(flow):
        x = fx + i * (fw + fgap)
        box(ax, x, 35.0, fw, 7.0, fc=fcs[i], ec=fes[i], r=0.04)
        text(ax, x + fw / 2, 38.5, s, fs=7.9)
        if i < len(flow) - 1:
            harrow(ax, x + fw + 0.15, x + fw + fgap - 0.15, 38.5, lw=1.0, color="#7f8a98")
    # highlight callout
    box(ax, 28, 29.2, 44, 4.4, fc=C["teal"], ec=C["teal"], r=0.06)
    text(ax, 50, 31.4, "≈0.5% of candidates folded   —   99.5% fewer AF2/ColabFold calls",
         fs=9.4, weight="bold", color="white")
    varrow(ax, 50, 27.3, 24.6)

    # ---- Footer: outputs + run record ----
    box(ax, 6, 17.5, 88, 6.6, fc=C["neutral"], ec=C["neutral_edge"])
    text(ax, 50, 21.6, "ranked candidates   ·   WT-relative shortlist   ·   results exported",
         fs=9.3, weight="bold")
    text(ax, 50, 19.0, "every request · tool call · output · QC record · label preserved under a single run record",
         fs=8.3, color=C["muted"])

    # ---- assay-guided loop (right side, footer -> request) ----
    ax.add_patch(FancyArrowPatch((94.2, 20.8), (94.2, 85.3),
                                 connectionstyle="arc3,rad=-0.32", arrowstyle="-|>",
                                 mutation_scale=13, linewidth=1.5, color=C["teal"], zorder=1))
    text(ax, 99.3, 53, "assay-guided next round", fs=8.3, color=C["teal"], weight="bold", rotation=90)

    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=350, bbox_inches="tight")
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight")
    print(OUT)
    return OUT


if __name__ == "__main__":
    main()
