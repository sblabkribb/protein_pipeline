#!/usr/bin/env python3
"""Shared style knob for all RAPID paper figures.

Purpose: ONE place to control the font across every figure. Change FONT (or call
apply(font=...)) and re-run build_all_figures.py to restyle everything.

Deliberately minimal — it only sets the font family and PDF/PS font embedding, so
importing it never changes a figure's layout/sizes (each generator controls those).
The shared PALETTE is provided for optional consistent coloring.
"""
import matplotlib as mpl

FONT = "DejaVu Sans"        # <-- single global font knob (e.g. "Arial" for submission)

# Wong colorblind-safe palette used across Fig2E / Fig3 / Fig4
PALETTE = {
    "single": "#BDBDBD", "bioemu": "#009E73", "rfd3": "#E69F00",
    "rfd3_bioemu": "#0072B2", "learned": "#0072B2",
    "baseline_light": "#D9D9D9", "baseline_mid": "#A6A6A6",
    "random_line": "#D55E00", "point": "#222222", "grid": "#dddddd",
}


def apply(font=FONT):
    """Set the global font only (no size/spine changes → existing figures unchanged)."""
    mpl.rcParams["font.family"] = font
    mpl.rcParams["pdf.fonttype"] = 42     # embed TrueType (editable text) — journal-friendly
    mpl.rcParams["ps.fonttype"] = 42
