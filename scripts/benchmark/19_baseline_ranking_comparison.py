#!/usr/bin/env python3
"""Table 2: cheap non-learned baselines vs the learned surrogate triage.

Same per-target protocol as 02_model_comparison.py (kmeans-selected 30 train,
5 seeds, evaluate ranking quality on the held-out pool with identical
topk_recall / bo_uplift). Non-learned baselines rank the held-out pool by a
cheap precomputed signal instead of a trained model:

    - SoluProt score      (already computed for every candidate)
    - pLDDT score          (cross-signal; only as predictor of SoluProt)
    - Sequence length      (trivial structural proxy)
    - ESM-2 8M PLL         (zero-shot protein-LM naturalness, single forward)

The learned RF / Ridge rows and the Random control are read back from
exp1_model_comparison.parquet so the table is internally consistent with the
published numbers (RF pLDDT Top-20 = 0.419, Random = 0.218, etc.).

Not computable from the public per-design records, and therefore omitted with a
note rather than fabricated:
    - ProteinMPNN score    (not retained as a column in cath_pilot_dataset.csv)
    - embedding-distance   (label-free embedding geometry gives no ranking
                            direction for a score-prediction baseline)
"""
from __future__ import annotations
import os, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _selection import select_train_indices

ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT") or Path(__file__).resolve().parents[2])
REFRESH = ROOT / "public_data" / "benchmark" / "refresh"
RESULTS = ROOT / "data" / "benchmark" / "results"
CSV = REFRESH / "cath_pilot_dataset.csv"
EMB = REFRESH / "cath_pilot_emb_320d.npy"
PLL = RESULTS / "baseline_esm_pll.npy"
EXP1 = RESULTS / "exp1_model_comparison.parquet"

SEEDS = [42, 123, 7, 2024, 31337]
N_TRAIN = 30
TOPK = [5, 20]


# --- identical metric functions to 02_model_comparison.py ---
def topk_recall(y_true, y_pred, k):
    if k > len(y_true):
        return float("nan")
    true_top = set(np.argsort(y_true)[::-1][:k])
    pred_top = set(np.argsort(y_pred)[::-1][:k])
    return len(true_top & pred_top) / k


def bo_uplift(y_true, y_pred, k, seed):
    if k > len(y_true):
        return float("nan")
    pred_top_idx = np.argsort(y_pred)[::-1][:k]
    rng = np.random.default_rng(seed)
    rand_idx = rng.choice(len(y_true), size=k, replace=False)
    return float(y_true[pred_top_idx].mean() - y_true[rand_idx].mean())


def main() -> int:
    df = pd.read_csv(CSV)
    emb = np.load(EMB)
    pll = np.load(PLL) if PLL.exists() else None
    if pll is None:
        print("WARNING: ESM PLL cache missing; skipping that baseline")
    seqlen = df["sequence"].str.len().to_numpy(dtype=np.float64)

    # baseline signal columns (row-aligned to df). value = higher-is-predicted-better
    signals = {
        "SoluProt score": df["soluprot"].to_numpy(dtype=np.float64),
        "pLDDT score": df["plddt"].to_numpy(dtype=np.float64),
        "Sequence length": seqlen,
    }
    if pll is not None:
        signals["ESM-2 8M PLL"] = pll

    # which baseline applies to which surrogate target (exclude the trivially-leaking
    # self-signal: don't rank SoluProt-target by SoluProt, nor pLDDT-target by pLDDT)
    applicable = {
        "plddt": ["SoluProt score", "Sequence length", "ESM-2 8M PLL"],
        "soluprot": ["pLDDT score", "Sequence length", "ESM-2 8M PLL"],
    }

    targets = sorted(df["target"].unique())
    rows = []
    for surrogate in ["plddt", "soluprot"]:
        for tgt in targets:
            mask = (df["target"] == tgt) & df[surrogate].notna()
            sub_idx = df.index[mask].to_numpy()
            if len(sub_idx) < N_TRAIN + 5:
                continue
            X_full = emb[sub_idx]
            y_full = df.loc[sub_idx, surrogate].to_numpy(dtype=np.float64)
            n = len(sub_idx)
            for seed in SEEDS:
                tr = select_train_indices(X_full, N_TRAIN, seed, "kmeans")
                te = np.setdiff1d(np.arange(n), tr, assume_unique=False)
                y_te = y_full[te]
                for bname in applicable[surrogate]:
                    sig_full = signals[bname][sub_idx]
                    pred = sig_full[te]
                    for k in TOPK:
                        rows.append({
                            "surrogate": surrogate, "target": tgt, "seed": seed,
                            "baseline": bname, "k": k,
                            "recall": topk_recall(y_te, pred, k),
                            "uplift": bo_uplift(y_te, pred, k, seed),
                        })

    res = pd.DataFrame(rows)
    agg = (res.groupby(["surrogate", "baseline", "k"])[["recall", "uplift"]]
           .mean().reset_index())

    # pull learned + control rows from exp1 (kmeans selection)
    e = pd.read_parquet(EXP1)
    e = e[e.selection == "kmeans"]
    learned = []
    for surrogate in ["plddt", "soluprot"]:
        for model in ["Random", "RF", "Ridge"]:
            sub = e[(e.surrogate == surrogate) & (e.model == model)]
            for k in TOPK:
                learned.append({
                    "surrogate": surrogate, "baseline": model, "k": k,
                    "recall": sub[f"top{k}_recall"].mean(),
                    "uplift": sub[f"bo_uplift_top{k}"].mean(),
                })
    learned = pd.DataFrame(learned)
    full = pd.concat([agg, learned], ignore_index=True)

    out_csv = RESULTS / "baseline_ranking_comparison.csv"
    full.to_csv(out_csv, index=False)

    # pretty print as the two manuscript tables
    def fmt(surrogate, order, label_map):
        piv = full[full.surrogate == surrogate].pivot_table(
            index="baseline", columns="k", values=["recall", "uplift"])
        print(f"\n===== surrogate target = {surrogate} =====")
        print(f"{'method':<22}{'Top-20 recall':>15}{'Top-5 recall':>15}{'uplift@20':>12}")
        for b in order:
            if b not in piv.index:
                continue
            r20 = piv.loc[b, ("recall", 20)]
            r5 = piv.loc[b, ("recall", 5)]
            u20 = piv.loc[b, ("uplift", 20)]
            print(f"{label_map.get(b,b):<22}{r20:>15.3f}{r5:>15.3f}{u20:>12.3f}")

    fmt("plddt",
        ["Random", "SoluProt score", "Sequence length", "ESM-2 8M PLL", "RF"],
        {"RF": "Random Forest (RAPID)"})
    fmt("soluprot",
        ["Random", "pLDDT score", "Sequence length", "ESM-2 8M PLL", "Ridge"],
        {"Ridge": "Ridge (RAPID)"})
    print(f"\nsaved {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
