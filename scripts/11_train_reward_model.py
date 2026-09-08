#!/usr/bin/env python3
"""Train and evaluate CATH reward/judge models (pLDDT pass filter + SoluProt).

Data:  cath_outputs/cath_73_dataset.csv (ProteinMPNN designs, soluprot + AF2 pLDDT labels)
Eval:  GroupKFold grouped by target (cross-target generalization)
Judge: predicted pLDDT ranking -> AF2 call-reduction curve at pipeline cutoff 85.0
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import average_precision_score, mean_squared_error, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path("/opt/protein_pipeline")
DATASET_CSV = PROJECT_ROOT / "cath_outputs" / "cath_73_dataset.csv"
META_ROOT = PROJECT_ROOT / "meta_surrogate_prototype"
MODEL_ROOT = PROJECT_ROOT / "pipeline-mcp" / "models"
EMBED_URL = os.getenv("ESM_EMBEDDING_URL", "http://211.188.35.221:18170")
MLFLOW_URI = "http://127.0.0.1:18050"
PLDDT_CUTOFF = 85.0
RANDOM_STATE = 42

MODEL_650M = "facebook/esm2_t33_650M_UR50D"
MODEL_150M = "facebook/esm2_t30_150M_UR50D"
MODEL_8M = "facebook/esm2_t6_8M_UR50D"


def _iso() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.gmtime())


def _embed_request(sequences: list[str], model_name: str, timeout: float = 7200.0) -> np.ndarray:
    payload = {
        "model_name": model_name,
        "batch_size": 64,
        "max_length": 1024,
        "sequences": [{"id": f"seq_{i}", "sequence": s} for i, s in enumerate(sequences)],
    }
    response = requests.post(f"{EMBED_URL.rstrip('/')}/embed", json=payload, timeout=timeout)
    response.raise_for_status()
    encoded = response.json()["embeddings_npz_b64"]
    with np.load(io.BytesIO(base64.b64decode(encoded))) as loaded:
        return np.asarray(loaded["embeddings"], dtype=np.float32)


def _embed_local(sequences: list[str], model_name: str) -> np.ndarray:
    import torch
    from transformers import AutoTokenizer, EsmModel

    device = torch.device("cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = EsmModel.from_pretrained(model_name).to(device).eval()
    out: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(sequences), 16):
            batch = sequences[start : start + 16]
            enc = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=1024)
            hidden = model(**enc).last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            out.append(pooled.numpy())
    return np.vstack(out).astype(np.float32)


def build_embeddings(sequences: list[str], *, prefer: str = MODEL_650M, budget_s: float = 1800.0) -> tuple[np.ndarray, str]:
    cache_key = f"reward_embeddings_{prefer.split('/')[-1]}.npz"
    cache_path = META_ROOT / cache_key
    unique = list(dict.fromkeys(sequences))
    if cache_path.exists():
        with np.load(cache_path, allow_pickle=False) as z:
            if list(z["sequences"]) == unique:
                print(f"[embed] cache hit: {cache_path} ({z['embeddings'].shape[0]} seqs)")
                index = {s: i for i, s in enumerate(unique)}
                rows = np.vstack([z["embeddings"][index[s]] for s in sequences])
                return rows, prefer

    chosen = MODEL_8M
    if requests.get(EMBED_URL, timeout=5).status_code < 500:
        _embed_request(unique[:2], MODEL_8M, timeout=120)
        probe = unique[:128] if len(unique) >= 128 else unique
        t0 = time.time()
        _embed_request(probe, prefer, timeout=1200)
        per_seq = (time.time() - t0) / len(probe)
        estimate = per_seq * len(unique)
        if estimate <= budget_s:
            chosen = prefer
        else:
            t0 = time.time()
            _embed_request(probe, MODEL_150M, timeout=1200)
            per_seq_150 = (time.time() - t0) / len(probe)
            chosen = MODEL_150M if per_seq_150 * len(unique) <= budget_s else MODEL_8M
        print(f"[embed] model={chosen} estimated {chosen and (per_seq if chosen == prefer else per_seq_150) * len(unique):.0f}s total")

    chunks: list[np.ndarray] = []
    chunk_size = 256
    t_start = time.time()
    for start in range(0, len(unique), chunk_size):
        batch = unique[start : start + chunk_size]
        try:
            chunks.append(_embed_request(batch, chosen))
        except Exception as exc:
            print(f"[embed] endpoint chunk failed ({exc}); falling back to local {MODEL_8M}")
            return build_embeddings(sequences, prefer=MODEL_8M, budget_s=budget_s)
        done = min(start + chunk_size, len(unique))
        rate = done / max(time.time() - t_start, 1e-9)
        print(f"[embed] {done}/{len(unique)} ({rate:.0f} seq/s, eta {(len(unique) - done) / max(rate, 1e-9):.0f}s)")
    matrix = np.vstack(chunks)
    np.savez(cache_path, sequences=np.array(unique), embeddings=matrix)
    index = {s: i for i, s in enumerate(unique)}
    rows = np.vstack([matrix[index[s]] for s in sequences])
    return rows, chosen


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_CSV)
    df = df.dropna(subset=["target", "sequence"])
    agg = (
        df.groupby(["target", "sequence"], as_index=False)
        .agg(plddt=("plddt", "mean"), soluprot=("soluprot", "mean"), n_obs=("seq_id", "size"))
    )
    agg["pass85"] = (agg["plddt"] >= PLDDT_CUTOFF).astype(float)
    agg.loc[agg["plddt"].isna(), "pass85"] = np.nan
    print(f"[data] rows={len(df)} -> unique(target,sequence)={len(agg)}")
    return agg


def _regressors() -> dict[str, object]:
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "histgb": HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, random_state=RANDOM_STATE),
        "mlp": make_pipeline(
            StandardScaler(),
            MLPRegressor(hidden_layer_sizes=(256, 128), max_iter=500, early_stopping=True, n_iter_no_change=20, random_state=RANDOM_STATE),
        ),
    }


def _spearman(y: np.ndarray, p: np.ndarray) -> float:
    if len(y) < 3 or np.std(y) == 0 or np.std(p) == 0:
        return float("nan")
    return float(spearmanr(y, p).statistic)


def grouped_cv(df: pd.DataFrame, X: np.ndarray, target_col: str) -> dict[str, dict[str, float]]:
    groups = df["target"].to_numpy()
    n_splits = min(5, len(np.unique(groups)))
    folds = list(GroupKFold(n_splits=n_splits).split(X, groups=groups))
    results: dict[str, dict[str, float]] = {}
    for name, make_model in _regressors().items():
        oof = np.full(len(df), np.nan)
        for tr, te in folds:
            y = df[target_col].to_numpy()
            mask_tr = ~np.isnan(y[tr])
            if mask_tr.sum() < 50 or (~np.isnan(y[te])).sum() == 0:
                continue
            model = make_model
            model.fit(X[tr][mask_tr], y[tr][mask_tr])
            oof[te] = model.predict(X[te])
        valid = ~np.isnan(oof) & ~np.isnan(df[target_col].to_numpy())
        y_true = df[target_col].to_numpy()[valid]
        y_pred = oof[valid]
        per_fold = [
            _spearman(df[target_col].to_numpy()[te], oof[te][~np.isnan(oof[te])])
            for _, te in folds
            if (~np.isnan(oof[te])).sum() > 2
        ]
        results[name] = {
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "spearman_oof": _spearman(y_true, y_pred),
            "spearman_fold_mean": float(np.nanmean(per_fold)),
            "n_eval": int(valid.sum()),
        }
    return results


def judge_metrics(df: pd.DataFrame, X: np.ndarray, best_key: str = "histgb") -> dict[str, object]:
    y = df["plddt"].to_numpy()
    labeled = ~np.isnan(y)
    groups = df["target"].to_numpy()
    n_splits = min(5, labeled.sum())
    folds = list(GroupKFold(n_splits=n_splits).split(X, groups=groups))

    oof_reg = np.full(len(df), np.nan)
    oof_clf = np.full(len(df), np.nan)
    for tr, te in folds:
        tr = [i for i in tr if ~np.isnan(y[i])]
        if len(tr) < 50:
            continue
        reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, random_state=RANDOM_STATE)
        reg.fit(X[tr], y[tr])
        oof_reg[te] = reg.predict(X[te])
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, random_state=RANDOM_STATE)
        clf.fit(X[tr], (y[tr] >= PLDDT_CUTOFF).astype(int))
        oof_clf[te] = clf.predict_proba(X[te])[:, 1]

    valid = labeled & ~np.isnan(oof_reg)
    y_true = y[valid]
    pass_true = (y_true >= PLDDT_CUTOFF).astype(int)
    score_reg = oof_reg[valid]
    score_clf = oof_clf[valid]

    order = np.argsort(-score_reg)
    cum_pass = np.cumsum(pass_true[order]) / max(pass_true.sum(), 1)
    fractions = (np.arange(1, len(order)) + 1) / len(order)
    capture_target = 0.90
    idx = int(np.searchsorted(cum_pass, capture_target))
    k_for_90 = float(fractions[min(idx, len(fractions) - 1)])
    top20 = max(int(0.20 * len(order)), 1)
    precision_top20 = float(pass_true[order[:top20]].mean())

    return {
        "pass_rate": float(pass_true.mean()),
        "n_labeled": int(valid.sum()),
        "reg_roc_auc": float(roc_auc_score(pass_true, score_reg)),
        "reg_pr_auc": float(average_precision_score(pass_true, score_reg)),
        "clf_roc_auc": float(roc_auc_score(pass_true, score_clf)),
        "clf_pr_auc": float(average_precision_score(pass_true, score_clf)),
        "top_k_pct_for_90pct_pass_capture": k_for_90,
        "af2_call_reduction_at_90pct_capture": 1.0 - k_for_90,
        "precision_top20pct": precision_top20,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed-model", default=MODEL_650M)
    parser.add_argument("--skip-cv", action="store_true")
    args = parser.parse_args()

    df = load_dataset()
    X, embed_model = build_embeddings(df["sequence"].tolist(), prefer=args.embed_model)
    print(f"[embed] X={X.shape} model={embed_model}")

    report: dict[str, object] = {
        "dataset": str(DATASET_CSV),
        "rows_unique": int(len(df)),
        "plddt_labeled": int(df["plddt"].notna().sum()),
        "plddt_cutoff": PLDDT_CUTOFF,
        "embedding_model": embed_model,
        "embedding_dim": int(X.shape[1]),
        "generated_at": _iso(),
    }

    if not args.skip_cv:
        report_path = META_ROOT / "reward_model_report.json"

        def _save_report() -> None:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        print("[cv] soluprot regression (all rows, grouped by target)")
        report["soluprot_cv"] = grouped_cv(df, X, "soluprot")
        for name, m in report["soluprot_cv"].items():
            print(f"  soluprot/{name}: " + ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in m.items()))
        _save_report()
        print("[cv] plddt regression (labeled rows, grouped by target)")
        report["plddt_cv"] = grouped_cv(df, X, "plddt")
        for name, m in report["plddt_cv"].items():
            print(f"  plddt/{name}: " + ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in m.items()))
        _save_report()
        print("[judge] cross-target pass-filter metrics")
        report["judge"] = judge_metrics(df, X)
        print("  judge: " + json.dumps(report["judge"], indent=None))
        _save_report()

    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    for target_col, model_name in (("plddt", "reward_plddt_v2"), ("soluprot", "reward_soluprot_v2")):
        y = df[target_col].to_numpy()
        mask = ~np.isnan(y)
        model = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.08, random_state=RANDOM_STATE)
        model.fit(X[mask], y[mask])
        path = MODEL_ROOT / f"{model_name}.pkl"
        with path.open("wb") as handle:
            pickle.dump(model, handle)
        artifacts[target_col] = str(path)
        print(f"[export] {path}")

    report["artifacts"] = artifacts
    report_path = META_ROOT / "reward_model_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[report] {report_path}")

    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment("CATH_Reward_Model")
        with mlflow.start_run(run_name=f"reward_model_{_iso()}"):
            mlflow.log_param("dataset", str(DATASET_CSV))
            mlflow.log_param("embedding_model", embed_model)
            mlflow.log_param("rows_unique", len(df))
            mlflow.log_param("plddt_cutoff", PLDDT_CUTOFF)
            for section in ("soluprot_cv", "plddt_cv"):
                for name, metrics in (report.get(section) or {}).items():
                    for key, value in metrics.items():
                        mlflow.log_metric(f"{section}.{name}.{key}", float(value))
            for key, value in (report.get("judge") or {}).items():
                mlflow.log_metric(f"judge.{key}", float(value))
            mlflow.log_artifact(str(report_path))
            for path in artifacts.values():
                mlflow.log_artifact(path)
        print(f"[mlflow] logged to {MLFLOW_URI} (CATH_Reward_Model)")
    except Exception as exc:
        print(f"[mlflow] logging failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
