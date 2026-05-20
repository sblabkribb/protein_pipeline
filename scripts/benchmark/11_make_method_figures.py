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


def lever_box(ax, x1, x2, y, text, *, h=0.72, fs=8.3):
    w = x2 - x1
    rect = FancyBboxPatch(
        (x1, y),
        w,
        h,
        boxstyle="round,pad=0.04,rounding_size=0.12",
        facecolor=COLOR_DIVERSIFICATION_LEVER,
        edgecolor=EDGE,
        linewidth=1.0,
        alpha=0.85,
    )
    ax.add_patch(rect)
    ax.text(
        x1 + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color="#1d1d1d",
        linespacing=1.18,
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
    fig, ax = plt.subplots(figsize=(13.8, 5.6))
    ax.set_xlim(0, 13.8)
    ax.set_ylim(0, 5.6)
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
    margin = 0.55
    gap = 0.34
    total_w = 13.8 - 2 * margin
    box_w = (total_w - gap * (n - 1)) / n
    box_h = 0.88
    y = 3.55

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
        6.9,
        5.25,
        "Pipeline stage order",
        ha="center",
        va="center",
        fontsize=12.5,
        fontweight="bold",
    )
    ax.text(
        6.9,
        4.92,
        "msa  \u2192  rfd3  \u2192  bioemu  \u2192  design  \u2192  soluprot  \u2192  af2  \u2192  novelty",
        ha="center",
        va="center",
        fontsize=9.5,
        color="#333",
        family="monospace",
    )

    legend_x = 9.55
    legend_y = 5.25
    swatch_w = 0.30
    swatch_h = 0.18
    items = [
        ("Heavy GPU", COLOR_HEAVY_GPU_STAGE),
        ("Cheap gate", COLOR_CHEAP_GATE_STAGE),
        ("Neutral", COLOR_NEUTRAL_STAGE),
    ]
    for j, (lbl, col) in enumerate(items):
        x = legend_x + j * 1.25
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

    rfd3_c, _, _ = centers[1]
    lever_box(
        ax,
        rfd3_c - 1.4,
        rfd3_c + 1.4,
        2.35,
        "Across-backbone diversification (topology)\nRFD3 \u2014 de novo backbones, default 10",
        h=0.62,
        fs=8.1,
    )
    arrow(ax, rfd3_c, 2.97, rfd3_c, y - 0.07, lw=1.0, color="#558055")

    bioemu_c, _, _ = centers[2]
    lever_box(
        ax,
        bioemu_c - 1.4,
        bioemu_c + 1.4,
        1.42,
        "Across-backbone diversification (conformation)\nBioEmu \u2014 ensemble, num_samples=10",
        h=0.62,
        fs=8.1,
    )
    arrow(ax, bioemu_c, 2.04, bioemu_c, y - 0.07, lw=1.0, color="#558055")

    design_c, _, _ = centers[3]
    msa_c, _, _ = centers[0]
    lever_box(
        ax,
        msa_c - 0.8,
        design_c + 0.8,
        0.35,
        "Within-backbone diversification (sequence)\n"
        "MSA conservation tiers [0.3, 0.5, 0.7] drive ProteinMPNN masking",
        h=0.72,
        fs=8.1,
    )
    arrow(ax, msa_c, 1.07, msa_c, y - 0.07, lw=1.0, color="#558055", ls="--")
    arrow(ax, design_c, 1.07, design_c, y - 0.07, lw=1.0, color="#558055", ls="--")

    out = FIG_DIR / "fig1_pipeline_overview.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def draw_active_learning_loop() -> Path:
    fig, ax = plt.subplots(figsize=(13.8, 6.2))
    ax.set_xlim(0, 13.8)
    ax.set_ylim(0, 6.2)
    ax.axis("off")

    ax.text(
        6.9,
        5.78,
        "AF2-budgeted surrogate triage",
        ha="center",
        va="center",
        fontsize=12.5,
        fontweight="bold",
    )
    ax.text(
        6.9,
        5.45,
        "One standard pipeline run: conservation-tier candidates are pooled before one shared AF2/ColabFold triage budget.",
        ha="center",
        va="center",
        fontsize=8.8,
        color="#555",
    )

    box_h = 1.08
    box_w = 2.28
    y_top = 4.05
    y_bottom = 2.25
    step_x = [0.45, 3.05, 5.65, 8.25, 10.85]

    step_box(
        ax,
        step_x[0],
        y_top,
        box_w,
        box_h,
        "Step 1",
        "Tiered design pool\nProteinMPNN\n3 × 3333 ≈ 9999",
        COLOR_LOOP_DATA,
    )

    step_box(
        ax,
        step_x[1],
        y_top,
        box_w,
        box_h,
        "SoluProt gate",
        "soluprot_cutoff = 0.5\npool tiers together\n\u2192 P candidates",
        COLOR_CHEAP_GATE_STAGE,
    )
    arrow(
        ax,
        step_x[0] + box_w,
        y_top + box_h / 2,
        step_x[1],
        y_top + box_h / 2,
    )

    step_box(
        ax,
        step_x[2],
        y_top,
        box_w,
        box_h,
        "Step 2",
        "K-means bootstrap\nESM-2 8M (320-D)\nN_TRAIN = 30",
        COLOR_LOOP_DATA,
    )
    arrow(
        ax,
        step_x[1] + box_w,
        y_top + box_h / 2,
        step_x[2],
        y_top + box_h / 2,
    )

    ax.text(
        step_x[2] + box_w / 2,
        y_top - 0.34,
        "30 labelled seeds + pooled unlabeled tier candidates",
        ha="center",
        va="center",
        fontsize=8.5,
        color="#444",
        style="italic",
    )

    step_box(
        ax,
        step_x[3],
        y_top,
        box_w,
        box_h,
        "Step 3",
        "AF2 on training set\n30 AF2 calls\nlabel: pLDDT",
        COLOR_LOOP_AF2,
    )
    arrow(
        ax,
        step_x[2] + box_w,
        y_top + box_h / 2,
        step_x[3],
        y_top + box_h / 2,
    )

    step_box(
        ax,
        step_x[3],
        y_bottom,
        box_w,
        box_h * 1.16,
        "Step 4",
        "Fit and compare\nRF/Ridge/GBM policies\nrank pooled remainder",
        COLOR_LOOP_SURROGATE,
        body_fs=7.9,
    )
    arrow(
        ax,
        step_x[3] + box_w / 2,
        y_top,
        step_x[3] + box_w / 2,
        y_bottom + box_h * 1.16,
    )

    arrow(
        ax,
        step_x[2] + box_w,
        y_top + 0.08,
        step_x[3],
        y_bottom + box_h * 1.16 / 2,
        lw=1.0,
        color="#558055",
        ls="--",
    )
    step_box(
        ax,
        step_x[4],
        y_top,
        box_w,
        box_h,
        "Step 5",
        "AF2 on pooled Top-K\nTOP_K = 20\n20 AF2 calls",
        COLOR_LOOP_AF2,
    )
    arrow(
        ax,
        step_x[3] + box_w,
        y_bottom + box_h * 1.16 / 2,
        step_x[4],
        y_top + box_h / 2,
        color="#555",
    )

    step_box(
        ax,
        step_x[4],
        y_bottom,
        box_w,
        box_h * 1.16,
        "Step 6",
        "Composite score\n0.4\u00b7pLDDT + 30\u00b7SoluProt\n\u2013 relax_penalty\n\u2192 best design",
        COLOR_LOOP_DATA,
        body_fs=7.9,
    )
    arrow(
        ax,
        step_x[4] + box_w / 2,
        y_top,
        step_x[4] + box_w / 2,
        y_bottom + box_h * 1.16,
    )

    ax.text(
        6.9,
        1.05,
        "Pooled triage AF2 calls = 30 (training) + 20 (top-K) = 50",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#1d1d1d",
    )
    ax.text(
        6.9,
        0.58,
        "Full-folding baseline scales with P; RAPID keeps one shared AF2 budget across selected conservation tiers",
        ha="center",
        va="center",
        fontsize=9,
        color="#333",
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
