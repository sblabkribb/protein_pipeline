#!/usr/bin/env python3
"""Fold-fidelity check: does high pLDDT imply the target backbone fold?

pLDDT is an AF2/ColabFold confidence proxy, not a measure of target-backbone
fidelity. Using the pooled CATH labels that carry BOTH pLDDT and Calpha RMSD to
the input backbone, we quantify how often a confident design still folds away
from the target (RMSD > 2.0 A, the same gate RAPID applies to RFD3/BioEmu arms).

Reproduces the numbers reported in Results 3.2 / the fold-fidelity paragraph.
"""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT") or Path(__file__).resolve().parents[2])
CSV = ROOT / "public_data" / "benchmark" / "results" / "pooled_surrogate_cath_labels.csv"
GATE = 2.0


def main() -> int:
    df = pd.read_csv(CSV).dropna(subset=["plddt", "rmsd_ca"])
    p = df["plddt"].to_numpy(float)
    r = df["rmsd_ca"].to_numpy(float)
    rho, pv = stats.spearmanr(p, r)
    print(f"N={len(df)} candidates over {df['target'].nunique()} targets")
    print(f"pLDDT median {np.median(p):.1f} (range {p.min():.1f}-{p.max():.1f})")
    print(f"RMSD_ca median {np.median(r):.2f} A (range {r.min():.2f}-{r.max():.2f})")
    print(f"Spearman(pLDDT, RMSD_ca) = {rho:.3f} (p={pv:.1e})")
    print(f"overall pass {GATE} A gate: {(r <= GATE).mean()*100:.1f}%")
    for thr in (70, 80, 90):
        hi = df[df["plddt"] >= thr]
        off = (hi["rmsd_ca"] > GATE).mean() * 100
        print(f"  pLDDT>={thr}: n={len(hi)} ({len(hi)/len(df)*100:.1f}%)  "
              f"off-target(RMSD>{GATE}A) = {off:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
