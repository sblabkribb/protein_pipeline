#!/usr/bin/env python3
"""Gate 0 AUC 가 정규화 강도에 얼마나 민감한가.

왜 재는가
---------
특징 384 개에 표적 62 개다(특징/표적 6.2). L2 정규화가 많은 일을 하고 있는데
강도는 sklearn 기본값 C=1.0 이고 조정하거나 보고한 적이 없다. 보고된 AUC
0.7247 이 그 기본값에 의존하는 값인지, 넓은 구간에서 안정한 값인지 알아야
한다. 안정하면 "조정하지 않았다" 가 한계가 아니라 사실 진술이 된다.

이것은 튜닝이 아니다
--------------------
최적 C 를 골라 그 AUC 를 보고하면 같은 데이터로 모형을 고르고 평가하는 것이
된다. 여기서는 **보고값의 안정성만** 본다. 기본값을 바꾸지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
C_GRID = (0.001, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 100.0)
REPORTED_C = 1.0


def _target_level_module():
    path = PROJECT_ROOT / "scripts" / "transcoder" / "13_gate0_target_level.py"
    spec = importlib.util.spec_from_file_location("gate0_target_level", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate_with_C(X, y, w, *, C, n_splits=5, n_repeats=20, seed=0):
    """13_gate0_target_level.evaluate_target_level 와 같은 절차, C 만 바꾼다."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    n = len(y)
    binary = (y >= 0.5).astype(int)
    aucs = []
    for rep in range(n_repeats):
        rng = np.random.default_rng(seed + rep)
        order = rng.permutation(n)
        preds = np.zeros(n)
        for fold in range(n_splits):
            test = np.zeros(n, dtype=bool)
            test[order[fold::n_splits]] = True
            if test.sum() < 2 or (~test).sum() < 10:
                continue
            tr = X[~test]
            mu, sd = tr.mean(0), tr.std(0)
            sd[sd == 0] = 1.0
            succ = np.rint(y[~test] * w[~test]).astype(int)
            fail = np.rint(w[~test]).astype(int) - succ
            xs = np.vstack([(tr - mu) / sd] * 2)
            ys = np.r_[np.ones(tr.shape[0]), np.zeros(tr.shape[0])]
            ws = np.r_[succ, fail].astype(float)
            keep = ws > 0
            if len(set(ys[keep])) < 2:
                preds[test] = float(np.average(y[~test], weights=w[~test]))
                continue
            model = LogisticRegression(max_iter=2000, C=C)
            model.fit(xs[keep], ys[keep], sample_weight=ws[keep])
            preds[test] = model.predict_proba((X[test] - mu) / sd)[:, 1]
        if len(set(binary)) == 2:
            aucs.append(float(roc_auc_score(binary, preds)))
    if not aucs:
        return None
    arr = np.sort(np.array(aucs))
    return {"auc": round(float(arr.mean()), 4),
            "ci95": [round(float(arr[int(0.025*len(arr))]), 4),
                     round(float(arr[min(len(arr)-1, int(0.975*len(arr)))]), 4)],
            "n_repeats": len(arr)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(BASE / "gate0_regularisation_sweep.json"))
    args = parser.parse_args(argv)

    m = _target_level_module()
    rows = list(csv.DictReader((BASE/"backbones"/"backbone_labels.csv").open(encoding="utf-8")))
    encoder = np.load(BASE/"backbones"/"mpnn_encoder.npy")
    desc = np.asarray([
        [m.descriptors(m.ca_coords((BASE/"backbones"/"pdb"/r["pdb_file"]).read_text(
            encoding="utf-8", errors="replace")))[k] for k in m.DESCRIPTOR_NAMES]
        for r in rows
    ])

    arms = {"C_raw_mpnn_encoder": encoder, "B_structural_descriptors": desc}
    report = {
        "question": "보고된 AUC 가 정규화 기본값에 의존하는가",
        "not_tuning": ("최적 C 를 골라 보고하면 같은 데이터로 모형을 고르고 평가하는 "
                       "것이 된다. 안정성만 보고 기본값은 바꾸지 않는다."),
        "reported_C": REPORTED_C,
        "features_per_target": round(encoder.shape[1] / 62, 2),
        "arms": {},
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    for name, features in arms.items():
        agg = m.aggregate_to_target(rows, features)
        X, y, w = agg["X"], agg["y"], agg["w"]
        alive = (X != 0).any(0) & (X.std(0) > 0)
        if alive.sum():
            X = X[:, alive]
        print(f"\n=== {name} (특징 {X.shape[1]} · 표적 {len(y)}) ===")
        print(f"{'C':>8} {'AUC':>8} {'CI95':>20}")
        results = {}
        for C in C_GRID:
            r = evaluate_with_C(X, y, w, C=C)
            if r is None:
                continue
            results[str(C)] = r
            mark = "  ← 보고값" if C == REPORTED_C else ""
            print(f"{C:>8g} {r['auc']:8.4f} [{r['ci95'][0]:.4f}, {r['ci95'][1]:.4f}]{mark}")
        aucs = [v["auc"] for v in results.values()]
        report["arms"][name] = {
            "n_features": int(X.shape[1]), "by_C": results,
            "range": [round(min(aucs), 4), round(max(aucs), 4)],
            "spread": round(max(aucs) - min(aucs), 4),
            "at_reported_C": results.get(str(REPORTED_C), {}).get("auc"),
            "best_C": max(results, key=lambda k: results[k]["auc"]),
        }
        a = report["arms"][name]
        print(f"  범위 {a['range']} · 폭 {a['spread']} · 최고는 C={a['best_C']}")

    enc = report["arms"]["C_raw_mpnn_encoder"]
    report["verdict"] = (
        f"C 를 0.001~100 으로 5 자리 바꿔도 AUC 가 {enc['range'][0]}~{enc['range'][1]} "
        f"(폭 {enc['spread']}) 다. 보고값 {enc['at_reported_C']} 는 기본값에 "
        f"의존하는 값이 아니다."
        if enc["spread"] < 0.05 else
        f"AUC 가 C 에 따라 {enc['range'][0]}~{enc['range'][1]} (폭 {enc['spread']}) 로 "
        f"움직인다. 보고값 {enc['at_reported_C']} 를 쓰려면 정규화 강도를 함께 "
        f"보고해야 하고, 강도 선택 자체가 근거를 요구한다."
    )
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\n판정: {report['verdict']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
