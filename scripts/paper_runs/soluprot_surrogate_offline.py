#!/usr/bin/env python3
"""Offline SoluProt-objective surrogate triage, faithfully reusing the live
pipeline's surrogate components (ESM embeddings, K-means bootstrap, the 4 model
policies, KFold CV with spearman-based auto selection).

Unlike the live pooled triage (which trains on best_plddt), this trains on the
*SoluProt* label that is already computed for every design (tiers/*/soluprot.json),
so we can ask the question that actually matters: does the structurally-expanded
pool (RFD3+BioEmu) let a SoluProt-targeted surrogate select more soluble Top-K
candidates than the single-backbone control, at the same 30-bootstrap/20-acquire
budget? No AF2 is needed (labels already exist).

Model selection is auto-CV (rf/ridge/lightgbm/xgboost compete; CV spearman picks
the winner per pool) -- NOT a forced Ridge.
"""
from __future__ import annotations
import csv, json, os, sys
from pathlib import Path
from statistics import mean

PR = Path("/opt/protein_pipeline-work")
sys.path.insert(0, str(PR / "pipeline-mcp" / "src"))
from dotenv import load_dotenv
load_dotenv("/opt/protein_pipeline/pipeline-mcp/.env", override=True)
os.environ["PIPELINE_OUTPUT_ROOT"] = str(PR / "outputs")

import numpy as np
from sklearn.model_selection import KFold
from pipeline_mcp import pipeline as P
from pipeline_mcp import evolution
from pipeline_mcp.app import build_runner

MODELS = ("rf", "ridge", "lightgbm", "xgboost")
TRAIN_COUNT = 30
TOP_K = 20
SEED = 0  # request.seed default in the pilot/control

# build the ESM embedding provider exactly like the live runner
_runner = build_runner()
_esm_provider = getattr(_runner, "esm_embedding", None)


def _load_pool(run_dir: Path):
    """Return list of dicts: {global_id, tier, seq_id, sequence, soluprot}."""
    mp = run_dir / "surrogate_triage" / "model_predictions.csv"
    if not mp.is_file():
        return []
    # soluprot per tier: scores[seq_id] -> value
    sol_by_tier: dict[str, dict[str, float]] = {}
    for sp in (run_dir / "tiers").glob("*/soluprot.json"):
        tier = sp.parent.name
        try:
            j = json.load(open(sp))
            sol_by_tier[tier] = {k: float(v) for k, v in (j.get("scores") or {}).items()
                                 if isinstance(v, (int, float))}
        except Exception:
            pass
    out = []
    for r in csv.DictReader(open(mp)):
        tier = str(r.get("tier") or "")
        sid = r.get("seq_id") or ""
        seq = r.get("sequence") or ""
        sol = sol_by_tier.get(tier, {}).get(sid)
        if seq and sol is not None:
            out.append({"global_id": r.get("global_seq_id") or sid, "tier": tier,
                        "seq_id": sid, "sequence": seq, "soluprot": float(sol)})
    return out


def _source(seq_id: str) -> str:
    s = seq_id.lower()
    return "rfd3" if "rfd3" in s else ("bioemu" if ("sample_" in s or "bioemu" in s) else "?")


def run_pool(run_dir: Path, label: str):
    pool = _load_pool(run_dir)
    if len(pool) < TRAIN_COUNT + TOP_K + 5:
        return {"label": label, "error": f"pool too small ({len(pool)})"}
    seqs = [p["sequence"] for p in pool]
    y_all = np.array([p["soluprot"] for p in pool], dtype=np.float64)
    emb = P._surrogate_triage_embeddings(seqs, provider=_esm_provider)
    emb = np.asarray(emb, dtype=np.float64)

    train_idx = P._surrogate_triage_training_indices(emb, TRAIN_COUNT, seed=SEED + 42)
    train_set = set(int(i) for i in train_idx)
    X_tr, y_tr = emb[list(train_idx)], y_all[list(train_idx)]

    # auto-CV over the 4 models (spearman), exactly like the live triage
    folds = min(5, len(y_tr))
    splitter = KFold(n_splits=folds, shuffle=True, random_state=SEED + 137)
    cv = {}
    for m in MODELS:
        oof = np.full(len(y_tr), np.nan)
        try:
            for tr_f, va_f in splitter.split(X_tr):
                mdl = evolution._make_surrogate(m, seed=42)
                mdl.fit(X_tr[tr_f], y_tr[tr_f])
                oof[va_f] = np.asarray(mdl.predict(X_tr[va_f]), dtype=np.float64)
            sp = P._surrogate_regression_metrics(y_tr, oof).get("spearman")
        except Exception as e:
            sp = None
        cv[m] = sp
    scored = {m: s for m, s in cv.items() if s is not None}
    selected = max(scored, key=scored.get) if scored else MODELS[0]

    # fit selected on full train, predict whole pool, acquire Top-K among non-train
    mdl = evolution._make_surrogate(selected, seed=42)
    mdl.fit(X_tr, y_tr)
    pred = np.asarray(mdl.predict(emb), dtype=np.float64)
    cand = [i for i in range(len(pool)) if i not in train_set]
    cand_sorted = sorted(cand, key=lambda i: pred[i], reverse=True)
    topk = cand_sorted[:TOP_K]

    sel_true = [y_all[i] for i in topk]
    # baselines among candidates
    oracle = sorted((y_all[i] for i in cand), reverse=True)[:TOP_K]
    rng = np.random.default_rng(123)
    rand = [y_all[i] for i in rng.choice(cand, TOP_K, replace=False)]
    # recall: how many of the pool's true top-K are in the surrogate's top-K
    true_topk_ids = set(sorted(cand, key=lambda i: y_all[i], reverse=True)[:TOP_K])
    recall = len(set(topk) & true_topk_ids) / TOP_K
    src = {}
    for i in topk:
        src.setdefault(_source(pool[i]["seq_id"]), []).append(y_all[i])

    return {
        "label": label, "pool": len(pool), "selected_model": selected,
        "cv_spearman": round(scored.get(selected, float("nan")), 3) if scored else None,
        "cv_all": {m: (round(s, 3) if s is not None else None) for m, s in cv.items()},
        "topk_sol_mean": round(mean(sel_true), 3), "topk_sol_best": round(max(sel_true), 3),
        "oracle_mean": round(mean(oracle), 3), "oracle_best": round(max(oracle), 3),
        "random_mean": round(mean(rand), 3),
        "uplift_vs_random": round(mean(sel_true) - mean(rand), 3),
        "regret_vs_oracle": round(mean(oracle) - mean(sel_true), 3),
        "recall_topk": round(recall, 2),
        "src_split": {k: f"n={len(v)} mean={mean(v):.3f}" for k, v in src.items()},
    }


def main():
    targets = sys.argv[1:] or ["1a8rG01", "1a6jA00", "1a19A00"]
    pilot_root = PR / "outputs"
    ctrl_map = {  # single-backbone control run dirs (pooled9999, original backbone)
        "1a8rG01": "paper_surrogate_pooled9999_strict_20260520_cath_train_1a8rG01",
        "1a6jA00": "paper_surrogate_pooled9999_strict_20260520_cath_train_1a6jA00",
        "1a19A00": "paper_surrogate_pooled9999_strict_20260520_cath_val_1a19A00",
        "1advA02": "paper_surrogate_pooled9999_strict_20260520_cath_val_1advA02",
        "1h6wA03": "paper_surrogate_pooled9999_strict_20260520_cath_val_1h6wA03",
    }
    for t in targets:
        print(f"\n========== {t} ==========", flush=True)
        exp = run_pool(pilot_root / f"pilot_ctx_triage_{t}", f"{t} EXPANDED(RFD3+BioEmu)")
        print("  [확장]", json.dumps(exp, ensure_ascii=False), flush=True)
        cdir = pilot_root / ctrl_map.get(t, "")
        if cdir.name and cdir.is_dir():
            ctl = run_pool(cdir, f"{t} CONTROL(single)")
            print("  [대조]", json.dumps(ctl, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
