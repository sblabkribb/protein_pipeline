#!/usr/bin/env python3
"""Gate 1. AF2 를 보기 전 cheap feature 로 백본 q_b 순위를 예측할 수 있는가.

feature 는 ProteinMPNN encoder 384-D 다. train(dev)과 test(홀드아웃)가 같은 공간에
있다는 것은 가정이 아니라 검증된 사실이다 - `21_gate2d_prepare_encoder.py
--verify-dev` 가 dev 157 백본을 재현한다 (max abs diff 9.06e-06).

**네 arm 이 동결돼 있다** (설계 스펙 §3 "학습 쪽도 정렬한다"). GO 판정은 primary
하나로만 낸다 - arm 을 골라 GO 를 선언하면 model selection multiplicity 다.

| arm | train | test | 지위 |
|---|---|---|---|
| primary | RFD3-only dev (80 · 16) | RFD3-only holdout | **GO 판정** |
| sensitivity_1 | RFD3+BioEmu dev (100 · 16) | RFD3-only holdout | 사전 등록 동반 보고 |
| descriptive_legacy | 전체 dev (157 · 62) | RFD3-only holdout | Gate 0 과의 연속성 |
| comparator | RFD3-only dev | native holdout (10 타겟) | Δ_generated 부수 분석. GO 제외 |

GO  <=>  타겟 등가중 mean within-target Spearman >= 0.25
         AND 단측 90% LCB > 0
         AND informative 타겟 >= 8

모델은 절대 q_b 로 학습하고 **평가만 타겟 내에서** 한다. dev 코호트에서 백본이
2개 이상인 타겟이 RFD3-only 는 16/16 이지만 legacy 는 16/62 뿐이므로 타겟 내 순위를
직접 학습할 수 없다. 이 구별을 결과 문장에서 지우지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "benchmark"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

import _gate2d as G                     # noqa: E402
import _gate2d_cohort as C              # noqa: E402
from rapid_sr.clustered import one_sided_lcb  # noqa: E402

GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

#: 동결된 arm 정의. 사후에 arm 을 추가하지 않는다.
ARMS = {
    "primary": {
        "train_sources": ("rfd3",),
        "test_sources": ("rfd3",),
        "status": "primary",
        "label": "RFD3-only dev -> RFD3-only holdout",
    },
    "sensitivity_1": {
        "train_sources": ("rfd3", "bioemu"),
        "test_sources": ("rfd3",),
        "status": "pre-registered companion",
        "label": "RFD3+BioEmu dev -> RFD3-only holdout",
    },
    "descriptive_legacy": {
        "train_sources": ("rfd3", "bioemu", "target"),
        "test_sources": ("rfd3",),
        "status": "descriptive / legacy",
        "label": "all-sources dev -> RFD3-only holdout",
    },
    "comparator": {
        "train_sources": ("rfd3",),
        "test_sources": ("target",),
        "status": "comparator - excluded from GO",
        "label": "RFD3-only dev -> native holdout",
    },
}

GO_ARM = "primary"

#: 동결된 재현 합격선 (21_gate2d_prepare_encoder.REPRO_ATOL). 여기서 다시 읽는 것은
#: index 가 합격선 자체를 느슨하게 적고 통과했다고 말하는 경우를 막기 위해서다.
REPRO_ATOL_MAX = 1e-4

#: 로지스틱 솔버의 수렴 설정. **결과를 보고 고른 값이 아니다.**
#:
#: sklearn 기본값 tol=1e-4 에서는 보고값이 데이터가 아니라 솔버가 멈춘 자리로
#: 정해졌다. lbfgs 가 최적점에 닿기 전에 서고, 어디서 서는지가 sklearn·scipy
#: 판본에 따라 달라서 같은 입력·같은 시드로 primary ρ 가 +0.0935(sklearn 1.9.0)
#: 와 +0.0743(sklearn 1.8.0) 으로 갈렸다. 갈림의 전부는 타겟 `5pc8A00` 의 백본
#: 두 개 순서 하나였고, 그 두 예측확률의 간격은 4.4e-4 였다 - feature 가
#: float32 이므로 float32 epsilon 아래의 섭동으로도 뒤집히는 자리다.
#:
#: tol 을 10 배씩 조이면 두 판본이 tol <= 1e-5 에서 같은 값으로 수렴한다. 그
#: 값은 이 estimator 의 목적함수(L2 penalised logistic, C=1)의 **정확한 최적점**
#: 에서 나오는 값과 같다 - 독립 Newton 해(|grad|_inf ~ 1e-13)로 확인했다. 즉
#: 보고값이 솔버의 정지 조건이 아니라 데이터로 정해진다.
#:
#: tol 은 산출물의 `numerics.solver_tol_stability` 가 매 실행마다 다시 재는
#: 안정 구간의 가운데다. max_iter 는 그 tol 에서 반복이 잘리지 않는 값이고,
#: 잘렸는지는 `fit_predict` 가 fail-closed 로 확인한다.
SOLVER_TOL = 1e-8
SOLVER_MAX_ITER = 20000

#: sklearn 기본값. 산출물에 함께 적어 "기본값이 아닌 이유" 를 읽을 수 있게 한다.
SKLEARN_DEFAULT_TOL = 1e-4

#: 안정성을 **주장하지 않고 측정한다** - 판정 arm 에서 이 tol 들을 다 돌려
#: 보고값이 변하지 않는 구간을 산출물에 남긴다. 첫 항목은 sklearn 기본값이다.
SOLVER_TOL_DECADES = (1e-4, 1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10)


def _reproduction_defect(index: dict) -> str | None:
    """index 가 dev 재현 검증을 **실제로 측정해서** 통과했는가. 아니면 그 이유.

    예전에는 `dev_reproduction.passed` 하나만 봤고, 그 값은
    21_gate2d_prepare_encoder.py 가 무조건 True 로 적던 상수였다 - 발동할 수 없는
    가드는 아무것도 지키지 않는다 (`bcfecdb`·`3927b5b` 와 같은 결함). 그래서
    플래그가 아니라 **측정 기록**을 본다: 그 실행이 검증을 돌렸는지, 잰 숫자가
    무엇인지, 그 숫자가 동결된 합격선 안인지.
    """
    repro = index.get("dev_reproduction") or {}
    if not repro.get("verified_in_this_invocation"):
        return ("이 index 를 만든 실행이 dev 재현 검증을 돌리지 않았다 "
                "(verified_in_this_invocation != true). "
                + str(repro.get("reason") or ""))
    diff, atol = repro.get("max_abs_diff"), repro.get("atol")
    if not isinstance(diff, (int, float)) or isinstance(diff, bool):
        return "측정된 max_abs_diff 가 없다 - 통과 플래그만으로는 인정하지 않는다."
    if not isinstance(atol, (int, float)) or isinstance(atol, bool):
        return "합격선 atol 이 기록돼 있지 않다."
    if atol > REPRO_ATOL_MAX:
        return f"atol 이 {atol:g} 다. 동결된 합격선은 {REPRO_ATOL_MAX:g} 이하다."
    if diff > atol:
        return f"max abs diff {diff:g} 가 atol {atol:g} 를 넘는다."
    if not repro.get("passed"):
        return f"검증이 통과로 기록되지 않았다 (max abs diff {diff:g})."
    return None


def load_dev(sources: tuple[str, ...] | None = None):
    """dev 백본: encoder feature, joint_pass_yield, 설계 수 가중치, source, target."""
    rows = list(csv.DictReader((GATE0 / "backbones" / "backbone_labels.csv")
                               .open(encoding="utf-8")))
    features = np.load(GATE0 / "backbones" / "mpnn_encoder.npy")
    if features.shape[0] != len(rows):
        raise SystemExit(
            f"encoder 행 {features.shape[0]} 과 라벨 행 {len(rows)} 이 다르다. "
            "행 정렬이 깨졌으므로 중단한다."
        )
    keep = [i for i, r in enumerate(rows)
            if sources is None or r["backbone_source"] in sources]
    x = features[keep]
    y = np.array([float(rows[i]["joint_pass_yield"]) for i in keep])
    w = np.array([max(float(rows[i]["n_sequences_with_af2"] or 0), 1.0) for i in keep])
    src = [rows[i]["backbone_source"] for i in keep]
    tgt = [rows[i]["target_id"] for i in keep]
    return x, y, w, src, tgt


def fit_predict(x_train, y_train, w_train, x_test, *,
                tol: float = SOLVER_TOL,
                max_iter: int = SOLVER_MAX_ITER) -> tuple[np.ndarray, int]:
    """설계 수로 가중한 이항 로지스틱. 13_gate0_target_level.py 와 같은 형태.

    `(예측확률, 실제 반복수)` 를 돌려준다. 반복수는 산출물에 적는다 - 보고값이
    솔버의 정지 자리에 의존하지 않는다는 것을 사람이 확인할 수 있어야 한다
    (`SOLVER_TOL` 주석).

    **반복이 잘리면 멈춘다.** max_iter 에 걸린 적합은 수렴한 적합이 아니고,
    sklearn 은 그 경우 ConvergenceWarning 하나만 낸다 - 경고는 파이프라인을
    세우지 못하므로 여기서 fail-closed 한다.
    """
    from sklearn.linear_model import LogisticRegression

    mu, sd = x_train.mean(0), x_train.std(0)
    sd = sd.copy()
    sd[sd == 0] = 1.0
    succ = np.rint(y_train * w_train).astype(int)
    fail = np.rint(w_train).astype(int) - succ
    xs = np.vstack([(x_train - mu) / sd] * 2)
    ys = np.r_[np.ones(len(x_train)), np.zeros(len(x_train))]
    ws = np.r_[succ, fail].astype(float)
    keep = ws > 0
    model = LogisticRegression(max_iter=max_iter, tol=tol)
    model.fit(xs[keep], ys[keep], sample_weight=ws[keep])
    n_iter = int(np.max(model.n_iter_))
    if n_iter >= max_iter:
        raise SystemExit(
            f"로지스틱 적합이 max_iter={max_iter} 에서 잘렸다 (tol={tol:g}). "
            "잘린 적합의 예측은 데이터가 아니라 반복 예산이 정한 값이므로 "
            "Gate 1 을 보고하지 않는다."
        )
    return model.predict_proba((x_test - mu) / sd)[:, 1], n_iter


def _test_cohort(grid, sources, row_of):
    sub = C.restrict_to_sources(grid, sources)
    labelled = [b for b in sub.backbones if b.backbone_key in row_of]
    missing = [b.backbone_key for b in sub.backbones if b.backbone_key not in row_of]
    if missing:
        raise SystemExit(f"encoder feature 없는 백본 {len(missing)} 개: {missing[:5]}")
    return labelled


def _arm_inputs(name: str, grid, x_test_all, row_of):
    """arm 의 (train, test) 재료. `evaluate_arm` 과 tol 안정성 표가 같은 것을 쓴다."""
    spec = ARMS[name]
    x_dev, y_dev, w_dev, _src_dev, tgt_dev = load_dev(spec["train_sources"])
    labelled = _test_cohort(grid, spec["test_sources"], row_of)
    x_test = x_test_all[[row_of[b.backbone_key] for b in labelled]]
    return spec, (x_dev, y_dev, w_dev, tgt_dev), labelled, x_test


def _gate1_metrics(q_pred, q_true, targets) -> dict:
    """한 예측 벡터의 Gate 1 지표 전부. **집계 규칙은 이 한 군데다.**

    인자 순서는 (predicted, actual, targets) 다. `top1_regret` 은 대칭이 아니므로
    뒤집으면 조용히 엉뚱한 수를 낸다 - argmax 를 실제값에서 잡고 regret 을
    예측값에서 재게 된다.

    **regret 의 코호트를 이름으로 못 박는다.** `top1_regret` 은 백본이 3 개
    이상인 타겟 **전부**(RFD3 홀드아웃에서 12)를 돌지만, 1 차 지표의 informative
    코호트는 q_b 가 상수인 타겟을 뺀 11 이다 - `1sh6A02` 는 RFD3 백본 5 개가
    모두 q_b = 1.00 이라 타겟 내 순위가 없고 regret 이 구조적으로 0 이다.
    26_gate2d_operating_characteristics.py 의 귀무 regret 은 informative 11 로
    계산된다(`gate1_units` → `C.gate1_informative_targets`). 관측값을 그 귀무값
    옆에 놓으려면 같은 코호트 판이어야 하므로 두 판을 각각 이름으로 적는다.
    """
    rhos = G.within_target_spearman(q_pred, q_true, targets)     # dict[target] -> rho
    regrets = G.top1_regret(q_pred, q_true, targets)             # dict[target] -> regret
    # 반환형이 dict 다. np.mean(dict) 나 one_sided_lcb(dict) 를 쓰면 안 된다.
    informative = sorted(rhos)          # 1 차 지표가 정의된 타겟 = OC 의 코호트
    ranked = sorted(regrets)            # 백본 >= 3 인 타겟 전부
    out = {"rhos": rhos, "regrets": regrets,
           "informative_cohort": informative, "ranked_cohort": ranked}
    if not informative:
        return out
    out["lcb"] = one_sided_lcb([rhos[t] for t in informative],
                               alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    out["point"] = G.target_equal_mean([rhos[t] for t in informative], informative)
    out["regret_ranked"] = G.target_equal_mean(
        [regrets[t] for t in ranked], ranked)
    out["regret_informative"] = G.target_equal_mean(
        [regrets[t] for t in informative], informative)
    return out


def solver_tol_stability(name: str, grid, x_test_all, row_of,
                         tols=SOLVER_TOL_DECADES) -> list[dict]:
    """tol 10 배씩에서 보고값이 변하는지 **매 실행마다 다시 잰다**.

    안정성을 주석으로 주장하지 않는다. 표가 산출물에 들어가므로, 어떤 환경에서
    보고값이 tol 에 의존하면 그 사실이 그 환경의 산출물에 남는다.
    """
    spec, (x_dev, y_dev, w_dev, _tgt), labelled, x_test = _arm_inputs(
        name, grid, x_test_all, row_of)
    q_true = [b.q_b for b in labelled]
    targets = [b.target_id for b in labelled]
    rows = []
    for tol in tols:
        q_pred, n_iter = fit_predict(x_dev, y_dev, w_dev, x_test,
                                     tol=tol, max_iter=SOLVER_MAX_ITER)
        m = _gate1_metrics(q_pred, q_true, targets)
        rows.append({
            "tol": float(tol),
            "is_sklearn_default": bool(tol == SKLEARN_DEFAULT_TOL),
            "is_reported": bool(tol == SOLVER_TOL),
            "n_iter": n_iter,
            "point": round(m["point"], 4),
            "one_sided_90_lcb": m["lcb"].get("lcb"),
            "top1_backbone_regret_mean_informative_cohort":
                round(m["regret_informative"], 4),
            "top1_backbone_regret_mean_all_ranked_targets":
                round(m["regret_ranked"], 4),
            "informative_targets": len(m["informative_cohort"]),
            "per_target_spearman_5pc8A00": round(m["rhos"].get("5pc8A00", float("nan")), 4),
        })
    # "보고값과 같은가" 를 주석이 아니라 측정으로 남긴다. 기본값 행은 여기서
    # false 로 찍히며, 그 행의 값 자체는 판본에 따라 달라진다.
    reported = next(r for r in rows if r["is_reported"])
    keys = ("point", "one_sided_90_lcb", "informative_targets",
            "top1_backbone_regret_mean_informative_cohort",
            "top1_backbone_regret_mean_all_ranked_targets")
    for row in rows:
        row["matches_reported_value"] = all(row[k] == reported[k] for k in keys)
    return rows


def evaluate_arm(name: str, grid, x_test_all, row_of) -> dict:
    spec, (x_dev, y_dev, w_dev, tgt_dev), labelled, x_test = _arm_inputs(
        name, grid, x_test_all, row_of)
    q_true = [b.q_b for b in labelled]
    targets = [b.target_id for b in labelled]

    q_pred, n_iter = fit_predict(x_dev, y_dev, w_dev, x_test)
    metrics = _gate1_metrics(q_pred, q_true, targets)
    rhos, regrets = metrics["rhos"], metrics["regrets"]
    informative = len(metrics["informative_cohort"])
    row = {
        "label": spec["label"],
        "status": spec["status"],
        "train": {"sources": list(spec["train_sources"]),
                  "n_backbones": int(len(y_dev)),
                  "n_targets": len(set(tgt_dev))},
        "test": {"sources": list(spec["test_sources"]),
                 "n_backbones": len(labelled),
                 "n_targets": len(set(targets))},
        "informative_targets": informative,
    }
    if informative == 0:
        # 타겟당 백본 1개인 코호트(native)에서는 타겟 내 순위가 존재하지 않는다.
        # 0 으로 대입하지 않는다 - 재지 못한 것과 0 은 다르다.
        row["evaluable"] = False
        row["reason"] = ("타겟당 백본이 3개 미만이라 타겟 내 Spearman 이 정의되지 "
                         "않는다. 미정의를 0 으로 대입하지 않는다.")
        row["mean_predicted"] = round(float(np.mean(q_pred)), 4)
        row["mean_q_b"] = round(float(G.target_equal_mean(q_true, targets)), 4)
        row["solver"] = {"tol": SOLVER_TOL, "max_iter": SOLVER_MAX_ITER, "n_iter": n_iter}
        return row

    # informative 코호트가 OC 의 코호트와 **같은 집합인지** 확인한다. 두 쪽이
    # 갈리면 regret 의 귀무 대조가 like-for-like 가 아니게 되고, 그것은 조용히
    # 일어난다 - 그래서 이름을 비교해 fail-closed 한다.
    oc_cohort = C.gate1_informative_targets(
        C.restrict_to_sources(grid, spec["test_sources"]))
    if metrics["informative_cohort"] != oc_cohort:
        raise SystemExit(
            "informative 코호트가 OC 의 코호트(_gate2d_cohort."
            f"gate1_informative_targets)와 다르다: {metrics['informative_cohort']} vs "
            f"{oc_cohort}. regret 을 귀무값과 나란히 놓을 수 없으므로 중단한다."
        )

    lcb, point = metrics["lcb"], metrics["point"]
    go = bool(point >= G.GATE1_RHO_MIN
              and lcb.get("exceeds_zero")
              and informative >= G.MIN_INFORMATIVE_TARGETS)
    row.update({
        "evaluable": True,
        "metric": "target-equal mean within-target Spearman(q_hat_b, q_b)",
        "point": round(point, 4),
        "one_sided_90_lcb": lcb.get("lcb"),
        "lcb_exceeds_zero": lcb.get("exceeds_zero"),
        "per_target_spearman": {t: round(rhos[t], 4) for t in sorted(rhos)},
        # regret 은 코호트를 이름에 담아 두 판을 함께 낸다 (`_gate1_metrics`).
        "top1_backbone_regret_mean_informative_cohort":
            round(metrics["regret_informative"], 4),
        "top1_backbone_regret_mean_all_ranked_targets":
            round(metrics["regret_ranked"], 4),
        # 예전 키. 값의 뜻(= all_ranked_targets)을 바꾸지 않는다 - 조용히 코호트를
        # 갈아치우면 이 키를 인용한 문장이 소리 없이 다른 수를 가리킨다.
        "top1_backbone_regret_mean": round(metrics["regret_ranked"], 4),
        "top1_backbone_regret_mean_cohort": (
            "all_ranked_targets - 예전 키이며 코호트가 이름에 없다. OC 귀무값과 "
            "비교할 때는 top1_backbone_regret_mean_informative_cohort 를 쓴다."),
        "regret_cohorts": {
            "informative_cohort": {
                "n_targets": len(metrics["informative_cohort"]),
                "targets": metrics["informative_cohort"],
                "value": round(metrics["regret_informative"], 4),
                "definition": ("1 차 지표가 정의된 타겟 = 백본 >= 3 AND q_b 비상수. "
                               "_gate2d_cohort.gate1_informative_targets 와 같은 집합이다."),
                "compare_to": ("gate2d_operating_characteristics.json → "
                               "gate1_operating_characteristics.OC_primary_rfd3_only."
                               "rows[sigma=null].mean_top1_regret (0.2274, "
                               "n_informative_targets 11). 귀무값이 이 코호트로 "
                               "계산되므로 이 값이 like-for-like 다."),
            },
            "all_ranked_targets": {
                "n_targets": len(metrics["ranked_cohort"]),
                "targets": metrics["ranked_cohort"],
                "value": round(metrics["regret_ranked"], 4),
                "definition": ("백본 >= 3 인 타겟 전부. `_gate2d.top1_regret` 의 "
                               "기본 코호트다."),
                "why_it_differs": ("q_b 가 상수인 타겟이 들어온다 - `1sh6A02` 는 "
                                   "RFD3 백본 5 개가 모두 q_b = 1.00 이라 어느 백본을 "
                                   "골라도 regret 이 0 이다. 구조적 0 이므로 평균을 "
                                   "끌어내리고, OC 귀무값은 이 타겟을 빼고 계산된다."),
            },
        },
        "per_target_regret": {t: round(regrets[t], 4) for t in sorted(regrets)},
        "per_target_regret_cohort": "all_ranked_targets",
        "mean_q_b": round(float(G.target_equal_mean(q_true, targets)), 4),
        "arm_meets_frozen_rule": go,
        "solver": {"tol": SOLVER_TOL, "max_iter": SOLVER_MAX_ITER, "n_iter": n_iter},
    })
    if spec["status"].startswith("comparator"):
        row["arm_meets_frozen_rule"] = None
        row["note"] = "comparator 는 GO 판정에 들어가지 않는다 (설계 스펙 §3)."
    return row


def delta_generated(grid) -> dict:
    """Δ_generated = q_b(생성 백본) − q_b(native 백본). 부수 분석, GO 제외.

    native 라벨이 있는 타겟에서만 정의된다. 타겟 등가중이고, 클러스터 = 타겟인
    단측 90% LCB 를 같은 primitive 로 붙인다.
    """
    rfd3 = C.restrict_to_sources(grid, ("rfd3",))
    native = C.restrict_to_sources(grid, ("target",))
    rfd3_by_target = G.per_target_mean_map([b.q_b for b in rfd3.backbones],
                                           [b.target_id for b in rfd3.backbones])
    native_by_target = G.per_target_mean_map([b.q_b for b in native.backbones],
                                             [b.target_id for b in native.backbones])
    shared = sorted(set(rfd3_by_target) & set(native_by_target))
    deltas = [rfd3_by_target[t] - native_by_target[t] for t in shared]
    lcb = one_sided_lcb(deltas, alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    return {
        "definition": "target-equal mean of [mean q_b(rfd3) - q_b(native)] per target",
        "status": "side analysis - not an endpoint, excluded from GO",
        "n_targets": len(shared),
        "targets_without_native_labels": sorted(set(rfd3_by_target) - set(native_by_target)),
        "point": lcb.get("point"),
        "one_sided_90_lcb": lcb.get("lcb"),
        "per_target": {t: round(rfd3_by_target[t] - native_by_target[t], 4) for t in shared},
        "mean_q_b_rfd3": round(float(np.mean([rfd3_by_target[t] for t in shared])), 4),
        "mean_q_b_native": round(float(np.mean([native_by_target[t] for t in shared])), 4),
    }


def numerics(stability: list[dict]) -> dict:
    """이 수를 낸 **수치 설정**. 시드 옆에 솔버와 판본을 같이 둔다.

    부트스트랩 시드만 적혀 있으면 재현되는 것은 LCB 뿐이다. 점추정은 솔버가
    어디서 멈췄는지에 달려 있었고(`SOLVER_TOL` 주석), 그 정지 자리는 sklearn·
    scipy 판본에 따라 달랐다. 그래서 tol·max_iter·판본·실제 반복수를 함께 적어
    보고값이 우연히 재현되는 것이 아니라 재현되게 한다.
    """
    import platform

    import scipy
    import sklearn

    return {
        "why_this_block_exists": (
            "Gate 1 의 점추정이 한때 solver stopping point 로 정해졌다 - sklearn "
            "기본값 tol=1e-4 에서 판본에 따라 ρ 가 +0.0935 / +0.0743 으로 갈렸다. "
            "tol 을 조여 데이터로 정해지게 하고, 그 설정을 여기 적는다."),
        "bootstrap_seed": G.BOOTSTRAP_SEED,
        "lcb_primitive": "rapid_sr.clustered.one_sided_lcb (n_boot=20000, PCG64)",
        "estimator": ("sklearn.linear_model.LogisticRegression"
                      "(solver='lbfgs', penalty='l2', C=1.0)"),
        "solver_tol": SOLVER_TOL,
        "solver_max_iter": SOLVER_MAX_ITER,
        "sklearn_default_tol": SKLEARN_DEFAULT_TOL,
        "solver_tol_stability": stability,
        "solver_tol_stability_arm": GO_ARM,
        "stability_reading": (
            "tol <= 1e-5 에서 point·LCB·regret·informative 가 모두 같은 값이다"
            "(`matches_reported_value`). 기본값 1e-4 행만 다르며, 그 행은 최적점에 "
            "닿기 전에 멈춘 적합이다 - **그 행의 값 자체는 sklearn·scipy 판본에 "
            "따라 달라지므로** 재현 대조에 쓰지 않는다."),
        "rank_statistics_only": (
            "보고되는 1 차·2 차 지표는 전부 타겟 내 **순위** 통계다 - 수렴한 tol 에서 "
            "두 판본이 같은 순위를 주므로 값이 비트 단위로 같다. 반대로 순위가 아닌 "
            "기술값(`arms.comparator.mean_predicted`)은 솔버가 멈춘 자리에 4 번째 "
            "소수에서 의존한다. 그 값은 non-evaluable arm 의 기술값이며 어떤 판정에도 "
            "들어가지 않는다 - 숨기지 않고 여기 적어 둔다."),
        "n_iter_is_environment_dependent": (
            "`solver.n_iter` 와 `solver_tol_stability[].n_iter` 는 판본에 따라 다르다. "
            "sklearn 1.9 는 목적함수를 sum(sample_weight) 로 나누므로 같은 tol 이 "
            "같은 정지 조건이 아니다. 보고값이 아니라 진단값이다."),
        "cross_environment_check": (
            "환경 사이 일치는 주석으로 주장하지 않는다 - tests/test_gate2d_metrics.py"
            "::test_gate1_committed_verdict_reproduces 가 입력에서 다시 계산해 이 "
            "산출물과 대조하므로, 보고값이 환경에 의존하면 그 환경에서 테스트가 "
            "깨진다."),
        "package_versions": {
            "python": platform.python_version(),
            "scikit-learn": sklearn.__version__,
            "scipy": scipy.__version__,
            "numpy": np.__version__,
        },
        "feature_dtype": "float32 (backbone_encoder.npy 그대로)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(GATE0 / "gate1_backbone_predictability.json"))
    args = parser.parse_args()

    grid = C.load_holdout_grid()
    index = json.loads((GATE0 / "holdout_grid" / "backbone_encoder.index.json")
                       .read_text(encoding="utf-8"))
    if index["dim"] != 384 or index["ckpt"] != "v_48_020":
        raise SystemExit(f"encoder index 가 dev 공간과 다르다: {index['ckpt']} / {index['dim']}")
    defect = _reproduction_defect(index)
    if defect:
        raise SystemExit(
            "홀드아웃 encoder feature 가 dev 재현 검증을 통과한 기록이 없다. train 과 "
            "test 가 다른 공간에 놓일 수 있으므로 Gate 1 을 돌리지 않는다.\n  " + defect
        )
    x_test_all = np.load(GATE0 / "holdout_grid" / "backbone_encoder.npy")
    row_of = {k: i for i, k in enumerate(index["backbone_keys"])}

    arms = {name: evaluate_arm(name, grid, x_test_all, row_of) for name in ARMS}
    stability = solver_tol_stability(GO_ARM, grid, x_test_all, row_of)

    primary = arms[GO_ARM]
    informative = primary["informative_targets"]
    if informative != 11:
        raise SystemExit(
            f"primary informative 타겟이 {informative} 다. 스펙 §3 은 11 이라고 "
            "동결했다 - 코호트 구성이 스펙과 다르므로 중단한다."
        )
    go = bool(primary["arm_meets_frozen_rule"])

    result = {
        "purpose": "Gate 1 - backbone predictability. 정책 비교가 아니다.",
        "spec": "docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md",
        "numerics": numerics(stability),
        "provenance": G.run_provenance(
            "scripts/benchmark/24_gate1_backbone_predictability.py",
            "scripts/benchmark/21_gate2d_prepare_encoder.py",
            "scripts/benchmark/_mpnn_encoder.py",
            "scripts/benchmark/_gate2d.py",
            "scripts/benchmark/_gate2d_cohort.py",
        ),
        "does_not_do": [
            "알고리즘 제안",
            "타겟 내 순위 직접 학습 (dev 코호트가 허용하지 않는다)",
            "동결된 RAPID v2 전향 검증 수정",
            "arm 선택 (GO 는 primary 하나로만 낸다)",
        ],
        "feature": {
            "kind": "ProteinMPNN encoder, 3-layer mask-mean pooled concat",
            "dim": 384,
            "ckpt": "v_48_020 (soluble)",
            "train_test_same_space": True,
            # 손으로 적지 않는다 - index 가 실제로 잰 값을 그대로 옮긴다.
            "dev_reproduction_max_abs_diff": index["dev_reproduction"]["max_abs_diff"],
            "dev_reproduction_atol": index["dev_reproduction"]["atol"],
            "dev_reproduction_verified_in_that_invocation":
                index["dev_reproduction"]["verified_in_this_invocation"],
            "note": ("dev 추출기는 커밋되지 않아 재구현했다. 그 재구현이 커밋된 dev "
                     "산출물을 allclose(atol=1e-4) 로 재현했기 때문에 train/test 가 "
                     "같은 공간이라는 것이 가정이 아니라 확인된 사실이다."),
        },
        "go_arm": GO_ARM,
        "arms": arms,
        "delta_generated_side_analysis": delta_generated(grid),
        "frozen_go_rule": {
            "rho_min": G.GATE1_RHO_MIN,
            "lcb_alpha": G.LCB_ONE_SIDED_ALPHA,
            "min_informative_targets": G.MIN_INFORMATIVE_TARGETS,
            "decided_by": "primary arm only",
        },
        "verdict": "GO" if go else "NO-GO",
        "no_go_reading": (
            "사전 지정된 시뮬레이션 모형(OC_primary_rfd3_only) 아래에서, NO-GO 는 "
            "rho ~ 0.44 규모의 효과에 대한 증거이고(P(GO)=0.94) rho ~ 0.18 규모"
            "(검정력 0.31)에 대해서는 약한 증거일 뿐이다. primary 는 백본 80 개에 "
            "384 차원이므로 '신호 없음' 이 아니라 '이 표본에서 미검출' 로 읽는다."
        ),
        "prior_attempt": (
            "13_gate0_target_level.py 는 백본 수준을 시도했다가 타겟 수준으로 바꿨고 "
            "rfd3 타겟 내 rho -0.257 을 기록했다. 그 측정의 라벨은 correspondence "
            "metric 교체(2026-09-06)로 무효화됐다 - 같은 코호트를 현재 라벨로 재면 "
            "내부 sd 가 0.044 가 아니라 0.150 이다. standing negative result 로 "
            "인용하지 않되, 선행 시도가 있었다는 사실은 함께 보고한다."
        ),
        "bioemu_caveat": (
            "BioEmu 에 대한 B 의 일반화는 주장하지 않는다 - 독립 BioEmu test 가 없다. "
            "sensitivity_1 은 같은 16 타겟에 백본 20 개를 더해 타겟내 대조를 늘린 것이다."
        ),
        "leakage_check": {
            "dev_holdout_target_overlap": 0,
            "note": "dev 세 source 전부 홀드아웃 12 타겟과 교집합이 공집합이다.",
        },
    }
    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"Gate 1 {result['verdict']}  (판정 arm = {GO_ARM})")
    for name, row in arms.items():
        if row.get("evaluable") is False:
            print(f"  {name:19s} non-evaluable  informative={row['informative_targets']}"
                  f"  ({row['reason'][:34]}...)")
        else:
            print(f"  {name:19s} rho={row['point']:+.4f}  LCB={row['one_sided_90_lcb']:+.4f}"
                  f"  informative={row['informative_targets']}"
                  f"  regret(info {row['regret_cohorts']['informative_cohort']['n_targets']})="
                  f"{row['top1_backbone_regret_mean_informative_cohort']:.4f}"
                  f"  regret(ranked {row['regret_cohorts']['all_ranked_targets']['n_targets']})="
                  f"{row['top1_backbone_regret_mean_all_ranked_targets']:.4f}"
                  f"  n_iter={row['solver']['n_iter']}")
    side = result["delta_generated_side_analysis"]
    print(f"  Delta_generated  {side['point']:+.4f}  LCB={side['one_sided_90_lcb']:+.4f}"
          f"  (n_targets={side['n_targets']}, side analysis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
