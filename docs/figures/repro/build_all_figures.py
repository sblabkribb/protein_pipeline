#!/usr/bin/env python3
"""Rebuild all reproducible RAPID paper figures (the repro/ generators).

Style (font/sizes/palette) is centralized in figstyle.py — change FONT there once
to restyle every figure below, then re-run this script.

Run: /opt/protein_pipeline/venv/bin/python build_all_figures.py
"""
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent      # docs/figures/repro
FIGDIR = HERE.parent                         # docs/figures (relative outputs land here)

# generators with available inputs (self-contained). Fig2 A-D / Fig3 / supp S1-S12
# need the benchmark data/env and are run separately from scripts/benchmark/.
GENERATORS = [
    ("Figure 1  (pipeline flow)",        "make_fig1_fullflow.py"),
    ("Figure 2E (baselines vs learned)", "make_fig2E_baseline.py"),
    ("Figure 4  (three-arm diversity)",  "make_fig4_threeway_matched.py"),
    ("Figure 5  (ensemble diversity)",   "analyze_S14.py"),
    ("Supp S13  (sequence-space cov.)",  "big_sweep.py"),
]

def main() -> int:
    fails = []
    for label, script in GENERATORS:
        print(f"\n=== {label}  [{script}] ===", flush=True)
        rc = subprocess.run([sys.executable, str(HERE / script)], cwd=str(FIGDIR)).returncode
        if rc:
            fails.append(script); print(f"  ! FAILED (rc={rc})")
    print("\n" + ("done, all ok" if not fails else f"done with failures: {fails}"))
    print("Note: Fig2 A-D, Fig3, supp S1-S12 need benchmark data/env — run from scripts/benchmark/.")
    return 1 if fails else 0

if __name__ == "__main__":
    raise SystemExit(main())
