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
    fig, ax = plt.subplots(figsize=(13.8, 7.2))
    ax.set_xlim(0, 13.8)
    ax.set_ylim(0, 7.2)
    ax.axis("off")

    def labeled_box(
        x,
        y,
        w,
        h,
        title,
        body,
        color,
        *,
        title_fs=9.2,
        body_fs=7.5,
        lw=1.05,
    ):
        rect = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.05,rounding_size=0.12",
            facecolor=color,
            edgecolor=EDGE,
            linewidth=lw,
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
            color="#1f2933",
        )
        ax.text(
            x + w / 2,
            y + h * 0.42,
            body,
            ha="center",
            va="center",
            fontsize=body_fs,
            color="#263238",
            linespacing=1.2,
        )

    ax.text(
        6.9,
        6.88,
        "RAPID provenance-centered redesign substrate",
        ha="center",
        va="center",
        fontsize=12.5,
        fontweight="bold",
    )
    ax.text(
        6.9,
        6.55,
        "The linear stage order is one operational view; the scientific unit is the reusable run_id-centered artifact record.",
        ha="center",
        va="center",
        fontsize=8.7,
        color="#4b5563",
    )

    stages = [
        ("MMseqs2", "MSA /\nconstraints", COLOR_CHEAP_GATE_STAGE),
        ("RFD3", "backbone\ncontext", COLOR_HEAVY_GPU_STAGE),
        ("BioEmu", "ensemble\ncontext", COLOR_HEAVY_GPU_STAGE),
        ("ProteinMPNN", "multiple-mutant\nlibrary", COLOR_NEUTRAL_STAGE),
        ("SoluProt", "cheap soluble-\nexpression gate", COLOR_CHEAP_GATE_STAGE),
        ("AF2/ColabFold", "structural\nconfidence", COLOR_HEAVY_GPU_STAGE),
        ("Novelty", "compare /\nscore", COLOR_NEUTRAL_STAGE),
    ]
    sx0 = 0.45
    sy = 5.48
    sw = 1.55
    sgap = 0.34
    sh = 0.68
    for i, (title, body, color) in enumerate(stages):
        x = sx0 + i * (sw + sgap)
        labeled_box(x, sy, sw, sh, title, body, color, title_fs=7.8, body_fs=6.5)
        if i < len(stages) - 1:
            arrow(ax, x + sw + 0.02, sy + sh / 2, x + sw + sgap - 0.02, sy + sh / 2, lw=0.9)

    ax.text(
        0.52,
        5.18,
        "Replaceable stage modules",
        ha="left",
        va="center",
        fontsize=8.2,
        color="#4b5563",
        fontweight="bold",
    )

    labeled_box(
        0.65,
        3.55,
        2.0,
        0.92,
        "Input target",
        "FASTA / PDB\ncampaign settings\noperator constraints",
        "#F7F3E8",
        title_fs=8.8,
        body_fs=7.1,
    )
    labeled_box(
        4.15,
        2.88,
        5.55,
        2.12,
        "Run-scoped artifact store",
        "run_id = provenance anchor\nrequest.json + stage outputs\nstatus + trace + QC\nmetrics + experiment records\nfinal summary",
        "#E9EEF7",
        title_fs=10.4,
        body_fs=7.8,
        lw=1.25,
    )
    arrow(ax, 2.65, 4.01, 4.15, 4.01, lw=1.1)
    arrow(ax, 7.85, sy, 7.85, 5.02, lw=1.0, color="#4b5563", ls="--")
    ax.text(
        8.05,
        5.18,
        "writes standardized outputs",
        ha="left",
        va="center",
        fontsize=7.0,
        color="#4b5563",
        style="italic",
    )

    action_y = 0.98
    action_h = 1.12
    action_w = 2.45
    action_x = [0.52, 3.48, 6.44, 9.40]
    actions = [
        ("Safe rerun path", "restart from valid\nstored artifacts\nwithout unsafe reuse", "#DFF2F1"),
        ("Retrospective analysis", "rebuild surrogate,\nscaling, variance, and\nQC analyses", "#D8EBC8"),
        ("Experiment feedback", "assay labels enter\nexperiments.jsonl\nfor next candidates", "#FFF0C8"),
        ("Model replacement", "swap any stage\nbackend if artifact\nfields stay compatible", "#F7D6CE"),
    ]
    for x, (title, body, color) in zip(action_x, actions):
        lw = 1.25 if title in {"Retrospective analysis", "Experiment feedback"} else 1.05
        title_fs = 8.9 if title in {"Retrospective analysis", "Experiment feedback"} else 8.5
        labeled_box(x, action_y, action_w, action_h, title, body, color, title_fs=title_fs, body_fs=6.9, lw=lw)
        arrow(ax, 6.95, 2.88, x + action_w / 2, action_y + action_h + 0.02, lw=1.05 if title in {"Retrospective analysis", "Experiment feedback"} else 0.95)

    arrow(
        ax,
        action_x[2] + action_w / 2,
        action_y + action_h,
        2.65,
        4.01,
        lw=1.35,
        color="#8A6D00",
        ls="--",
    )
    ax.text(
        4.65,
        2.40,
        "next design-test-learn cycle",
        ha="center",
        va="center",
        fontsize=7.4,
        color="#6b5500",
        style="italic",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1.5},
    )

    ax.text(
        0.68,
        0.44,
        "Key distinction: RAPID preserves provenance and reusable records, so completed runs become a substrate for rerun, analysis, feedback, and backend replacement.",
        ha="left",
        va="center",
        fontsize=7.4,
        color="#4b5563",
    )

    legend_x = 10.9
    legend_y = 6.88
    swatch_w = 0.25
    swatch_h = 0.15
    items = [
        ("GPU-heavy", COLOR_HEAVY_GPU_STAGE),
        ("cheap gate", COLOR_CHEAP_GATE_STAGE),
        ("neutral", COLOR_NEUTRAL_STAGE),
    ]
    for j, (lbl, col) in enumerate(items):
        x = legend_x + j * 0.92
        rect = FancyBboxPatch(
            (x, legend_y - swatch_h / 2),
            swatch_w,
            swatch_h,
            boxstyle="round,pad=0.004,rounding_size=0.035",
            facecolor=col,
            edgecolor=EDGE,
            linewidth=0.7,
        )
        ax.add_patch(rect)
        ax.text(x + swatch_w + 0.035, legend_y, lbl, ha="left", va="center", fontsize=6.6)

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
