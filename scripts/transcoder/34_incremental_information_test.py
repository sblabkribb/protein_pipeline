#!/usr/bin/env python3
"""응집 지표가 SoluProt 위에 정보를 더하는가 (증분 정보 검정).

무엇을 묻는가
-------------
"응집 지표가 SoluProt 과 상관이 있는가" 가 아니다. 그건 이미 쟀고, SoluProt 이
소수성 계열 특징을 쓴다면 부분적으로 구성상 예견된 값이라 약한 근거다.

여기서 묻는 것은 하나다. **SoluProt 만 쓸 때보다 AF2 구조 성공을 더 잘
가려내는가.** 안 준다면 AggreProt 이나 CamSol 을 붙여도 같은 축이라 안 줄
가능성이 크고, 워커를 띄우기 전에 그것을 알 수 있다.

라벨
----
AF2 structural success = plddt >= 85 AND rmsd_nonloop_order <= 2.0.
**SoluProt 을 포함하지 않는다.** joint yield 를 라벨로 쓰면 SoluProt 이 라벨 안에
들어가 M0 가 자기 자신을 예측하게 된다.

분할
----
target_id 로 묶은 GroupKFold. 서열 무작위 분할은 금지한다 - 같은 타겟의 설계가
학습과 평가에 나뉘어 들어가면 타겟을 외우고도 높은 점수가 나온다.

모형
----
표준화 + 로지스틱 회귀. 용량이 큰 모형을 쓰면 특징이 준 정보인지 용량이 준
차이인지 구별되지 않는다. 스케일러는 폴드 안에서만 적합한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.liabilities import (  # noqa: E402
    aggregation_prone_fraction, max_hydrophobic_patch, net_charge,
)
from rapid_sr.protocol import GATE0_THRESHOLDS  # noqa: E402

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
PANELS = ("temperature_sweep", "temperature_panel2")
M0 = ["soluprot"]
M1 = ["soluprot", "aggregation_prone_fraction", "max_hydrophobic_patch", "net_charge"]
TOP_FRACTIONS = (0.05, 0.10, 0.20)


def load() -> list[dict]:
    rows = []
    for panel in PANELS:
        seqs = {r["sequence_id"]: r for r in
                csv.DictReader((BASE / panel / "sequences.csv").open(encoding="utf-8"))}
        for r in csv.DictReader((BASE / panel / "af2_order_metric.csv").open(encoding="utf-8")):
            if r.get("status") != "ok":
                continue
            src = seqs.get(r["sequence_id"])
            if src is None:
                continue
            try:
                plddt = float(r["plddt"])
                rmsd = float(r["rmsd_nonloop_order"])
                solu = float(src["soluprot"])
            except (TypeError, ValueError, KeyError):
                continue
            sequence = (src.get("sequence") or "").replace("X", "")
            patch = max_hydrophobic_patch(sequence)
            if not sequence or patch is None:
                continue
            rows.append({
                "sequence_id": r["sequence_id"], "target_id": r["target_id"],
                "panel": panel,
                # 라벨에 SoluProt 이 들어가면 M0 가 자기 자신을 예측한다.
                "label": int(plddt >= GATE0_THRESHOLDS["plddt_min"]
                             and rmsd <= GATE0_THRESHOLDS["rmsd_max"]),
                "soluprot": solu,
                "aggregation_prone_fraction": aggregation_prone_fraction(sequence),
                "max_hydrophobic_patch": patch,
                "net_charge": net_charge(sequence),
            })
    return rows


def oof_predictions(rows, features, *, n_splits, seed) -> np.ndarray:
    X = np.array([[r[f] for f in features] for r in rows], dtype=float)
    y = np.array([r["label"] for r in rows], dtype=int)
    groups = np.array([r["target_id"] for r in rows])
    out = np.full(len(rows), np.nan)
    splitter = GroupKFold(n_splits=min(n_splits, len(set(groups))))
    for train_idx, test_idx in splitter.split(X, y, groups):
        if len(set(y[train_idx])) < 2:
            # 학습 폴드에 한 클래스만 있으면 그 폴드는 학습이 안 된다.
            out[test_idx] = y[train_idx].mean()
            continue
        scaler = StandardScaler().fit(X[train_idx])
        model = LogisticRegression(max_iter=2000, random_state=seed)
        model.fit(scaler.transform(X[train_idx]), y[train_idx])
        out[test_idx] = model.predict_proba(scaler.transform(X[test_idx]))[:, 1]
    return out


def metrics(y, p) -> dict:
    if len(set(y)) < 2:
        return {"auroc": None, "auprc": None, "brier": None, "n": len(y),
                "positives": int(y.sum())}
    out = {"auroc": float(roc_auc_score(y, p)),
           "auprc": float(average_precision_score(y, p)),
           "brier": float(brier_score_loss(y, p)),
           "n": int(len(y)), "positives": int(y.sum())}
    order = np.argsort(-p)
    for frac in TOP_FRACTIONS:
        k = max(1, int(round(len(y) * frac)))
        out[f"top{int(frac*100)}_yield"] = float(y[order[:k]].mean())
    return out


def within_target_auroc(rows, y, p) -> dict:
    """타겟 안에서만 순위를 매겼을 때의 성능.

    왜 이것을 따로 재는가
    ---------------------
    pooled AUROC 는 타겟 사이의 차이와 타겟 안의 차이를 섞는다. 그런데 cheap
    filter 가 실제로 하는 일은 **한 타겟 안에서 어느 서열을 접을지 고르는 것**이다.
    타겟 난이도를 잘 맞히는 특징은 라우팅에는 쓸모가 있어도 그 일에는 쓸모가 없다.

    실제로 이 데이터에서 둘이 반대 방향이다. SoluProt 은 타겟 평균이 높을수록
    구조 성공률이 낮고(1bctA00 은 0.914 인데 성공률 0.000), 타겟 안에서는 약하게
    양의 방향이다. pooled 만 보면 결론이 뒤집힌다.
    """
    import collections
    by = collections.defaultdict(list)
    for i, row in enumerate(rows):
        by[row["target_id"]].append(i)
    scores, sizes = [], []
    for idx in by.values():
        yy = y[idx]
        if len(set(yy)) < 2:
            continue          # 포화된 타겟은 순위를 매길 대상이 없다
        scores.append(float(roc_auc_score(yy, p[idx])))
        sizes.append(len(idx))
    if not scores:
        return {"n_informative_targets": 0, "median": None, "mean": None}
    arr = np.array(scores)
    return {"n_informative_targets": len(scores),
            "median": round(float(np.median(arr)), 4),
            "mean": round(float(arr.mean()), 4),
            "per_target": [round(v, 4) for v in scores]}


def within_target_bootstrap(rows, y, p0, p1, *, n_boot, seed) -> dict:
    """타겟 내 AUROC 차이의 타겟 단위 재표집 구간."""
    import collections
    by = collections.defaultdict(list)
    for i, row in enumerate(rows):
        by[row["target_id"]].append(i)
    usable = [idx for idx in by.values() if len(set(y[idx])) >= 2]
    if not usable:
        return {}
    diffs_per_target = [
        float(roc_auc_score(y[idx], p1[idx])) - float(roc_auc_score(y[idx], p0[idx]))
        for idx in usable
    ]
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        drawn = rng.choice(len(diffs_per_target), size=len(diffs_per_target), replace=True)
        means.append(float(np.mean([diffs_per_target[d] for d in drawn])))
    arr = np.sort(np.array(means))
    lo = float(arr[int(0.025 * len(arr))])
    hi = float(arr[min(len(arr) - 1, int(0.975 * len(arr)))])
    return {"n_targets": len(diffs_per_target),
            "mean_diff": round(float(np.mean(diffs_per_target)), 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "excludes_zero": bool(lo > 0 or hi < 0)}


def clustered_bootstrap(rows, y, p0, p1, *, n_boot, seed) -> dict:
    targets = sorted({r["target_id"] for r in rows})
    index = {t: np.array([i for i, r in enumerate(rows) if r["target_id"] == t])
             for t in targets}
    rng = np.random.default_rng(seed)
    keys = ["auroc", "auprc", "brier"] + [f"top{int(f*100)}_yield" for f in TOP_FRACTIONS]
    diffs: dict[str, list] = {k: [] for k in keys}
    for _ in range(n_boot):
        drawn = rng.choice(len(targets), size=len(targets), replace=True)
        idx = np.concatenate([index[targets[d]] for d in drawn])
        m0, m1 = metrics(y[idx], p0[idx]), metrics(y[idx], p1[idx])
        if m0["auroc"] is None or m1["auroc"] is None:
            continue
        for k in keys:
            diffs[k].append(m1[k] - m0[k])
    out = {}
    for k, values in diffs.items():
        if not values:
            out[k] = None
            continue
        arr = np.sort(np.array(values))
        lo = float(arr[int(0.025 * len(arr))])
        hi = float(arr[min(len(arr) - 1, int(0.975 * len(arr)))])
        out[k] = {"mean_diff": round(float(arr.mean()), 4),
                  "ci95": [round(lo, 4), round(hi, 4)],
                  "excludes_zero": bool(lo > 0 or hi < 0),
                  "n_boot": len(arr)}
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--out", default=str(BASE / "incremental_information_test.json"))
    args = parser.parse_args(argv)

    rows = load()
    y = np.array([r["label"] for r in rows], dtype=int)
    targets = sorted({r["target_id"] for r in rows})
    print(f"설계 {len(rows)} · 타겟 {len(targets)} · 구조 성공 {int(y.sum())} "
          f"({y.mean():.1%})")
    print(f"라벨: plddt >= {GATE0_THRESHOLDS['plddt_min']} AND "
          f"rmsd_nonloop_order <= {GATE0_THRESHOLDS['rmsd_max']} (SoluProt 제외)")

    p0 = oof_predictions(rows, M0, n_splits=args.n_splits, seed=args.seed)
    p1 = oof_predictions(rows, M1, n_splits=args.n_splits, seed=args.seed)
    m0, m1 = metrics(y, p0), metrics(y, p1)

    print(f"\n{'지표':>14} {'M0 (SoluProt)':>15} {'M1 (+응집)':>13} {'차이':>9}")
    for key in ("auroc", "auprc", "brier") + tuple(f"top{int(f*100)}_yield" for f in TOP_FRACTIONS):
        print(f"{key:>14} {m0[key]:15.4f} {m1[key]:13.4f} {m1[key]-m0[key]:+9.4f}")

    boot = clustered_bootstrap(rows, y, p0, p1, n_boot=args.n_boot, seed=args.seed)
    print(f"\n타겟 단위 clustered bootstrap ({args.n_boot} 회) · M1 - M0")
    for key, val in boot.items():
        if val is None:
            continue
        mark = "  ← 0 제외" if val["excludes_zero"] else ""
        print(f"  {key:>16} {val['mean_diff']:+8.4f}  CI [{val['ci95'][0]:+.4f}, "
              f"{val['ci95'][1]:+.4f}]{mark}")

    # cheap filter 가 하는 일은 타겟 안에서 고르는 것이다. 여기가 주 판정이다.
    w0 = within_target_auroc(rows, y, p0)
    w1 = within_target_auroc(rows, y, p1)
    wboot = within_target_bootstrap(rows, y, p0, p1, n_boot=args.n_boot, seed=args.seed)
    raw = {name: float(roc_auc_score(y, np.array([r[name] for r in rows])))
           for name in M1}
    print(f"\n타겟 안에서만 (cheap filter 가 실제로 하는 일) · 정보 타겟 "
          f"{w0['n_informative_targets']}/{len(targets)}")
    print(f"  M0 중앙값 {w0['median']}  평균 {w0['mean']}")
    print(f"  M1 중앙값 {w1['median']}  평균 {w1['mean']}")
    if wboot:
        mark = "  ← 0 제외" if wboot["excludes_zero"] else ""
        print(f"  차이 {wboot['mean_diff']:+.4f}  CI [{wboot['ci95'][0]:+.4f}, "
              f"{wboot['ci95'][1]:+.4f}]{mark}")

    any_gain = bool(wboot and wboot["excludes_zero"] and wboot["mean_diff"] > 0)
    brier_gain = False

    report = {
        "question": "응집 지표가 SoluProt 위에 AF2 구조 성공 예측 정보를 더하는가",
        "label": "plddt >= 85 AND rmsd_nonloop_order <= 2.0 (SoluProt 미포함)",
        "why_label_excludes_soluprot": "joint yield 를 쓰면 SoluProt 이 라벨 안에 들어가 "
                                       "M0 가 자기 자신을 예측한다",
        "split": "GroupKFold by target_id. 서열 무작위 분할 금지.",
        "model": "StandardScaler + LogisticRegression. 용량 차이가 아니라 특징 차이를 재려면 "
                 "단순 모형이어야 한다. 스케일러는 폴드 안에서만 적합.",
        "M0": M0, "M1": M1,
        "n_designs": len(rows), "n_targets": len(targets),
        "n_positive": int(y.sum()), "base_rate": round(float(y.mean()), 4),
        "primary": "타겟 내 AUROC. cheap filter 는 한 타겟 안에서 어느 서열을 접을지 "
                   "고르므로, 타겟 난이도를 맞히는 능력은 이 일에 쓸모가 없다.",
        "within_target": {"M0": w0, "M1": w1, "bootstrap": wboot},
        "pooled": {"M0": m0, "M1": m1},
        "pooled_warning": "pooled 지표는 타겟 간 차이와 타겟 내 차이를 섞는다. 이 "
                          "데이터에서 둘은 반대 방향이라 pooled 만 보면 결론이 뒤집힌다.",
        "raw_feature_pooled_auroc": {k: round(v, 4) for k, v in raw.items()},
        "clustered_bootstrap": boot,
        "verdict": {
            "adds_information": bool(any_gain or brier_gain),
            "basis": "타겟 내 AUROC 차이 (pooled 아님)",
            "reading": ("타겟 안에서도 이득이 있다. 응집 축에 투자할 근거가 된다."
                        if any_gain else
                        "타겟 안에서는 이득이 없다. pooled 지표의 이득은 타겟 난이도를 "
                        "더 잘 맞힌 것이고, cheap filter 가 하는 일이 아니다. "
                        "AggreProt/CamSol 은 같은 축이므로 같은 결과가 나올 가능성이 크다 - "
                        "다만 이 검정은 그 두 모형이 아니라 우리 서열 휴리스틱을 잰 것이다."),
        },
        "limits": [
            "선형 모형이다. 비선형 상호작용이 있으면 놓친다.",
            "타겟 25 개다. clustered bootstrap 이 그만큼만 안다.",
            "여기서 잰 것은 우리 서열 휴리스틱이지 AggreProt/CamSol 이 아니다.",
            "포화된 타겟(성공률 0 또는 1)은 타겟 내 순위를 매길 수 없어 빠진다.",
        ],
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\n판정: {report['verdict']['reading']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
