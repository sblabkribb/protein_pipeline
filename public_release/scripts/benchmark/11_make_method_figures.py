#!/usr/bin/env python3
"""
Generate two method-section schematics for the manuscript.

Outputs:
    figures/benchmark/fig1_pipeline_overview.png
    figures/benchmark/fig2_active_learning_loop.png

Run:
    python scripts/benchmark/11_make_method_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = PROJECT_ROOT / "figures" / "benchmark"

COLOR_HEAVY_GPU_STAGE = "#F4B8AB"
COLOR_CHEAP_GATE_STAGE = "#FFE5A0"
COLOR_NEUTRAL_STAGE = "#D9E2F3"
COLOR_DIVERSIFICATION_LEVER = "#A4C8A4"
COLOR_LOOP_DATA = "#E0E7F1"
COLOR_LOOP_AF2 = "#F4B8AB"
COLOR_LOOP_SURROGATE = "#A4C8A4"
EDGE = "#222"


def stage_box(ax, x, y, w, h, label, color, fs=10):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.03,rounding_size=0.12",
        facecolor=color,
        edgecolor=EDGE,
        linewidth=1.1,
    )
    ax.add_patch(box)
    ax.text(
        x + w / 2,
        y + h / 2,
        label,
        ha="center",
        va="center",
        fontsize=fs,
        fontweight="bold",
        color="#222",
    )


def arrow(ax, x1, y1, x2, y2, *, style="->", lw=1.2, color="#333", ls="-"):
    a = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle=style,
        mutation_scale=12,
        linewidth=lw,
        color=color,
        linestyle=ls,
    )
    ax.add_patch(a)


def lever_box(ax, x1, x2, y, text):
    w = x2 - x1
    rect = FancyBboxPatch(
        (x1, y),
        w,
        0.85,
        boxstyle="round,pad=0.04,rounding_size=0.12",
        facecolor=COLOR_DIVERSIFICATION_LEVER,
        edgecolor=EDGE,
        linewidth=1.0,
        alpha=0.85,
    )
    ax.add_patch(rect)
    ax.text(
        x1 + w / 2,
        y + 0.42,
        text,
        ha="center",
        va="center",
        fontsize=8.6,
        color="#1d1d1d",
    )


def step_box(ax, x, y, w, h, title, body, color, *, title_fs=10, body_fs=8.2):
    rect = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.04,rounding_size=0.12",
        facecolor=color,
        edgecolor=EDGE,
        linewidth=1.1,
    )
    ax.add_patch(rect)
    ax.text(
        x + w / 2,
        y + h - 0.17,
        title,
        ha="center",
        va="top",
        fontsize=title_fs,
        fontweight="bold",
        color="#1d1d1d",
    )
    ax.text(
        x + w / 2,
        y + h * 0.43,
        body,
        ha="center",
        va="center",
        fontsize=body_fs,
        color="#222",
        linespacing=1.25,
    )


def draw_pipeline_overview() -> Path:
    fig, ax = plt.subplots(figsize=(13.0, 4.6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 4.6)
    ax.axis("off")

    stages = [
        ("MSA",      COLOR_CHEAP_GATE_STAGE, "MMseqs2"),
        ("RFD3",     COLOR_HEAVY_GPU_STAGE,  "RFdiffusion"),
        ("BioEmu",   COLOR_HEAVY_GPU_STAGE,  "Conf. ensemble"),
        ("design",   COLOR_NEUTRAL_STAGE,    "ProteinMPNN"),
        ("SoluProt", COLOR_CHEAP_GATE_STAGE, "Developability"),
        ("AF2",      COLOR_HEAVY_GPU_STAGE,  "ColabFold"),
        ("novelty",  COLOR_NEUTRAL_STAGE,    "Compare/score"),
    ]

    n = len(stages)
    margin = 0.4
    gap = 0.28
    total_w = 13 - 2 * margin
    box_w = (total_w - gap * (n - 1)) / n
    box_h = 0.95
    y = 3.0

    centers = []
    for i, (label, color, sub) in enumerate(stages):
        x = margin + i * (box_w + gap)
        stage_box(ax, x, y, box_w, box_h, label, color, fs=11)
        ax.text(
            x + box_w / 2,
            y - 0.22,
            sub,
            ha="center",
            va="top",
            fontsize=8,
            color="#444",
            style="italic",
        )
        centers.append((x + box_w / 2, x, x + box_w))
        if i < n - 1:
            arrow(
                ax,
                x + box_w + 0.02,
                y + box_h / 2,
                x + box_w + gap - 0.02,
                y + box_h / 2,
            )

    ax.text(
        6.5,
        4.25,
        "Pipeline stage order",
        ha="center",
        va="center",
        fontsize=12.5,
        fontweight="bold",
    )
    ax.text(
        6.5,
        3.95,
        "msa  \u2192  rfd3  \u2192  bioemu  \u2192  design  \u2192  soluprot  \u2192  af2  \u2192  novelty",
        ha="center",
        va="center",
        fontsize=9.5,
        color="#333",
        family="monospace",
    )

    legend_x = 10.4
    legend_y = 4.3
    swatch_w = 0.30
    swatch_h = 0.18
    items = [
        ("Heavy GPU", COLOR_HEAVY_GPU_STAGE),
        ("Cheap gate", COLOR_CHEAP_GATE_STAGE),
        ("Neutral", COLOR_NEUTRAL_STAGE),
    ]
    for j, (lbl, col) in enumerate(items):
        x = legend_x + j * 0.85
        rect = FancyBboxPatch(
            (x, legend_y - swatch_h / 2),
            swatch_w,
            swatch_h,
            boxstyle="round,pad=0.005,rounding_size=0.04",
            facecolor=col,
            edgecolor=EDGE,
            linewidth=0.8,
        )
        ax.add_patch(rect)
        ax.text(
            x + swatch_w + 0.05,
            legend_y,
            lbl,
            ha="left",
            va="center",
            fontsize=7.5,
            color="#222",
        )

    lever_y = 1.55

    rfd3_c, _, _ = centers[1]
    lever_box(
        ax,
        rfd3_c - 1.4,
        rfd3_c + 1.4,
        lever_y,
        "Across-backbone diversification (topology)\nRFD3 \u2014 de novo backbones, default 10",
    )
    arrow(ax, rfd3_c, lever_y + 0.45, rfd3_c, y - 0.05, lw=1.0, color="#558055")

    bioemu_c, _, _ = centers[2]
    lever_box(
        ax,
        bioemu_c - 1.4,
        bioemu_c + 1.4,
        lever_y - 1.0,
        "Across-backbone diversification (conformation)\nBioEmu \u2014 ensemble, num_samples=10",
    )
    arrow(ax, bioemu_c, lever_y - 1.0 + 0.45, bioemu_c, y - 0.05, lw=1.0, color="#558055")

    design_c, _, _ = centers[3]
    msa_c, _, _ = centers[0]
    lever_box(
        ax,
        msa_c - 0.8,
        design_c + 0.8,
        0.05,
        "Within-backbone diversification (sequence)\n"
        "MSA conservation tiers [0.3, 0.5, 0.7] drive ProteinMPNN masking",
    )
    arrow(ax, msa_c, 0.05 + 0.45, msa_c, y - 0.05, lw=1.0, color="#558055", ls="--")
    arrow(ax, design_c, 0.05 + 0.45, design_c, y - 0.05, lw=1.0, color="#558055", ls="--")

    out = FIG_DIR / "fig1_pipeline_overview.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def draw_active_learning_loop() -> Path:
    fig, ax = plt.subplots(figsize=(13.2, 6.2))
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 6.2)
    ax.axis("off")

    ax.text(
        6.6,
        5.78,
        "Active-learning loop \u2014 single run-evolution invocation",
        ha="center",
        va="center",
        fontsize=12.5,
        fontweight="bold",
    )
    ax.text(
        6.6,
        5.45,
        "The diagram shows one implemented loop; multi-round reuse is an orchestration-level budget model.",
        ha="center",
        va="center",
        fontsize=8.8,
        color="#555",
    )

    box_h = 1.08
    box_w = 2.55
    col_x = 0.55

    step_box(
        ax,
        col_x,
        4.05,
        box_w,
        box_h,
        "Step 1",
        "Pool generation\nProteinMPNN\npool_size = 1000",
        COLOR_LOOP_DATA,
    )

    step_box(
        ax,
        col_x,
        2.65,
        box_w,
        box_h,
        "SoluProt gate",
        "soluprot_cutoff = 0.5\n\u2192 ~90 candidates",
        COLOR_CHEAP_GATE_STAGE,
    )
    arrow(ax, col_x + box_w / 2, 4.05, col_x + box_w / 2, 2.65 + box_h)

    step_box(
        ax,
        col_x,
        1.25,
        box_w,
        box_h,
        "Step 2",
        "K-means selection\nESM-2 8M (320-D)\nN_TRAIN = 20",
        COLOR_LOOP_DATA,
    )
    arrow(ax, col_x + box_w / 2, 2.65, col_x + box_w / 2, 1.25 + box_h)

    ax.text(
        col_x + box_w / 2,
        0.88,
        "\u2192 20 training + ~70 unlabeled",
        ha="center",
        va="center",
        fontsize=8.5,
        color="#444",
        style="italic",
    )

    mid_x = 4.65
    step_box(
        ax,
        mid_x,
        4.05,
        box_w,
        box_h,
        "Step 3",
        "AF2 on training set\n20 AF2 calls\nlabel: best pLDDT",
        COLOR_LOOP_AF2,
    )
    arrow(ax, col_x + box_w, 1.25 + box_h / 2, mid_x, 4.05 + box_h / 2,
          color="#555")

    step_box(
        ax,
        mid_x,
        2.25,
        box_w,
        box_h * 1.16,
        "Step 4",
        "Surrogate fit + rank\nlocal model\n(default RF, swappable)\npredict on ~70 pool",
        COLOR_LOOP_SURROGATE,
        body_fs=7.9,
    )
    arrow(ax, mid_x + box_w / 2, 4.05, mid_x + box_w / 2, 2.25 + box_h * 1.16)

    right_x = 8.95
    step_box(
        ax,
        right_x,
        4.05,
        box_w,
        box_h,
        "Step 5",
        "AF2 on top-K\nTOP_K = 20\n20 AF2 calls",
        COLOR_LOOP_AF2,
    )
    arrow(ax, mid_x + box_w, 2.25 + box_h * 1.16 / 2, right_x,
          4.05 + box_h / 2, color="#555")

    step_box(
        ax,
        right_x,
        2.25,
        box_w,
        box_h * 1.16,
        "Step 6",
        "Composite score\n0.4\u00b7pLDDT + 30\u00b7SoluProt\n\u2013 relax_penalty\n\u2192 best design",
        COLOR_LOOP_DATA,
        body_fs=7.9,
    )
    arrow(ax, right_x + box_w / 2, 4.05, right_x + box_w / 2, 2.25 + box_h * 1.16)

    ax.text(
        6.6,
        1.05,
        "Total AF2 calls per run = 20 (training) + 20 (top-K) = 40",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#1d1d1d",
    )
    ax.text(
        6.6,
        0.58,
        "Without surrogate (AF2 every gated candidate): \u2248 90 calls per run  \u2192  ~56% reduction",
        ha="center",
        va="center",
        fontsize=9,
        color="#333",
        style="italic",
    )

    ax.text(
        mid_x + box_w + 0.05,
        4.45,
        "Surrogate replaces oracle\non the unlabeled pool",
        ha="left",
        va="center",
        fontsize=8.0,
        color="#558055",
        style="italic",
    )

    out = FIG_DIR / "fig2_active_learning_loop.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    p1 = draw_pipeline_overview()
    p2 = draw_active_learning_loop()
    print(f"wrote: {p1}")
    print(f"wrote: {p2}")


if __name__ == "__main__":
    main()
