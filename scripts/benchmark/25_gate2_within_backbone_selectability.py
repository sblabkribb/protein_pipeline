#!/usr/bin/env python3
"""Gate 2. mixed 백본 안에서 joint-pass 후보를 골라낼 수 있는가.

코호트 : mixed 백본 37개 / informative 타겟 11개
split  : LOTO (12 타겟). 백본을 쪼개지 않는다.
1차    : 타겟 등가중 Delta_Top4, 판정 arm 은 S6 하나

GO <=> 점추정 Delta_Top4 >= +0.10 AND 단측 90% LCB > 0 AND informative >= 8

기준점(측정 완료): SoluProt -0.001, oracle +0.326.

**S6 가 없으면 판정하지 않는다.** S0-S3 만 돌린 결과는 interim/descriptive 이며
그것으로 GO/NO-GO 문장을 쓰면 스펙 위반이다. 그 경우 verdict 는 UNDECIDED 다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "benchmark"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

import _gate2d as G                     # noqa: E402
import _gate2d_cohort as C              # noqa: E402
import _gate2d_features as F            # noqa: E402
from rapid_sr.clustered import one_sided_lcb  # noqa: E402

GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

#: Ridge 의 정칙화. 결과를 보고 고르지 않는다.
RIDGE_ALPHA = 100.0

#: 스펙 §5 가 동결한 NO-GO 해석 문구. 프로덕션 primitive 재생성값 0.93 이다
#: (최초 동결본의 0.94 는 controller 임시 실행값이었고 스펙이 이미 정정했다).
NO_GO_READING = (
    "Under the prespecified simulation model, the gate has approximately 93% "
    "probability of GO for an effect corresponding to AUC ≈ 0.70. Therefore, NO-GO "
    "would constitute evidence against an effect of approximately this magnitude "
    "under the assumed operating conditions, rather than proving the absence of any "
    "AUC ≥ 0.70 predictor."
)


def _summarise(values: Sequence[float]) -> dict:
    """타겟 등가중 점추정 + 단측 90% LCB. 두 endpoint·두 코호트가 같은 규칙을 쓴다."""
    lcb = one_sided_lcb(values, alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    point = float(np.mean(values)) if len(values) else float("nan")
    return {
        "delta_top4_target_equal": round(point, 4),
        "one_sided_90_lcb": lcb.get("lcb"),
        "informative_targets": len(values),
        "meets_threshold": bool(point >= G.GATE2_DELTA_MIN),
        "lcb_exceeds_zero": bool(lcb.get("exceeds_zero")),
    }


def _low_depth_sensitivity(per_target: dict[str, float],
                           low_depth_targets: Sequence[str]) -> dict:
    """저심도 타겟을 뺀 민감도 (스펙 §4 규칙 6).

    **타겟을 빼는 것이 아니다** - 1 차 판정은 informative 타겟 전체로 내고, 이
    민감도를 그 옆에 나란히 보고한다. 민감도 코호트가 floor 미만이면 "교차 확인이
    불가능했다" 를 명시한다. 조용히 확인 없는 판정으로 두지 않는다.
    """
    excluded = sorted(set(low_depth_targets) & set(per_target))
    kept = {t: v for t, v in sorted(per_target.items()) if t not in set(excluded)}
    out: dict = {
        "excluded_low_depth_targets": excluded,
        "n_excluded": len(excluded),
        "cohort_targets": sorted(kept),
    }
    if not excluded:
        out["evaluable"] = None
        out["reason"] = "저심도 타겟이 없다 - 민감도가 1 차 판정과 같다 (규칙 6, 구간 0)."
        return out
    if len(kept) < G.MIN_INFORMATIVE_TARGETS:
        out["evaluable"] = False
        out["informative_targets"] = len(kept)
        out["reason"] = (
            f"민감도 코호트 {len(kept)} 이 floor {G.MIN_INFORMATIVE_TARGETS} 미만이라 "
            "non-evaluable 이다. 1 차 판정은 그대로 내되 교차 확인이 불가능했다 "
            "(스펙 §4 규칙 6, 구간 '4 이상')."
        )
        return out
    out["evaluable"] = True
    out.update(_summarise([kept[t] for t in sorted(kept)]))
    return out


def evaluate_arm(arm: str, grid: C.Grid, mixed: list[C.Backbone],
                 endpoint: str = "joint",
                 low_depth_targets: Sequence[str] = ()) -> dict:
    """한 arm 의 타겟 등가중 Delta_Top4. LOTO 로 낸 예측만 쓴다."""
    from sklearn.linear_model import Ridge

    all_folds = grid.folds
    targets = [f.target_id for f in all_folds]
    y = np.array([(f.joint_pass if endpoint == "joint" else f.structural_pass)
                  for f in all_folds], dtype=float)
    uses_msa = "msa" in F.ARM_BLOCKS[arm]

    pred = np.zeros(len(all_folds))
    active_by_fold: dict[str, list[str]] = {}
    n_features = 0
    for train_idx, test_idx, held in F.loto_splits(targets):
        x_fold, defect = F.assemble(arm, all_folds, train_idx)
        if x_fold is None:
            return {"arm": arm, "label": F.ARM_LABELS[arm], "endpoint": endpoint,
                    "status": "non_evaluable",
                    "reason": ("train fold 에 정의된 MSA feature 가 없어 imputation "
                               "statistic 을 만들 수 없다" if defect is None
                               else "측정된 MSA feature 가 버려졌다 - 규칙 2 위반"),
                    "defect": defect}
        n_features = int(x_fold.shape[1])
        if uses_msa:
            # fold 별 사용 열을 남긴다. 없으면 narrowing 을 감사할 수 없다.
            active_by_fold[held] = F.active_msa_feature_names(all_folds, train_idx)
        model = Ridge(alpha=RIDGE_ALPHA)
        model.fit(x_fold[train_idx], y[train_idx])
        pred[test_idx] = model.predict(x_fold[test_idx])

    score_of = {f.sequence_id: float(p) for f, p in zip(all_folds, pred)}
    per_backbone, bb_targets = [], []
    for b in mixed:
        labels = [(f.joint_pass if endpoint == "joint" else f.structural_pass)
                  for f in b.folds]
        per_backbone.append(G.delta_top4(
            labels, [score_of[f.sequence_id] for f in b.folds],
            [f.sequence_id for f in b.folds]))
        bb_targets.append(b.target_id)

    per_target = G.per_target_mean_map(per_backbone, bb_targets)
    out = {"arm": arm, "label": F.ARM_LABELS[arm], "status": F.ARM_STATUS[arm],
           "endpoint": endpoint}
    out.update(_summarise([per_target[t] for t in sorted(per_target)]))
    out["per_target_delta_top4"] = {t: round(v, 4) for t, v in sorted(per_target.items())}
    out["sensitivity_excluding_low_depth"] = _low_depth_sensitivity(
        per_target, low_depth_targets)
    out["n_features"] = n_features
    if uses_msa:
        out["active_msa_feature_names"] = active_by_fold
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default=",".join(F.ARMS))
    parser.add_argument("--out",
                        default=str(GATE0 / "gate2_within_backbone_selectability.json"))
    args = parser.parse_args(argv)

    # 서열 축은 hard precondition 이다 (스펙 §4). 보존 마스크와 변이 인덱스가
    # 어긋난 좌표에서 계산되면 아무 오류도 나지 않는다. 먼저 막는다.
    C.assert_sequence_axis(F.wt_by_target())

    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    requested = [a.strip() for a in args.arms.split(",") if a.strip()]

    msa = F.load_msa_features()
    low_depth = msa["low_depth"]
    low_depth_targets = list(low_depth["targets"])

    arms = {a: evaluate_arm(a, grid, mixed, low_depth_targets=low_depth_targets)
            for a in requested}
    arms_structural = {a: evaluate_arm(a, grid, mixed, endpoint="structural",
                                       low_depth_targets=low_depth_targets)
                       for a in requested}

    primary = arms.get(F.PRIMARY_ARM)

    # 판정 arm 이 **돌지 않은** 실행은 interim 이다 - 요청되지 않았거나 코드가 아직
    # 없거나. 기계가 읽을 수 있게 최상위에 박는다: verdict_note 문장에만 두면 이
    # 파일을 나중에 Gate 2 결과로 인용하는 것을 막지 못한다.
    #
    # 규칙 5 의 `non_evaluable` 은 interim 이 **아니다.** 그것은 판정 arm 을 실제로
    # 돌려서 얻은 데이터에 대한 결론이고 그대로 기록으로 남아야 한다.
    interim = primary is None or primary.get("status") == "not_implemented"
    if primary is None or primary.get("status") in ("non_evaluable", "not_implemented"):
        verdict, note = "UNDECIDED", (
            f"판정 arm {F.PRIMARY_ARM} 이 실행되지 않았다. S0-S3 만 돌린 결과는 "
            "interim/descriptive only 이며 공식 Gate 2 판정이 아니다."
        )
    else:
        go = primary["meets_threshold"] and primary["lcb_exceeds_zero"] \
             and primary["informative_targets"] >= G.MIN_INFORMATIVE_TARGETS
        verdict, note = ("GO" if go else "NO-GO"), ""

    result = {
        "purpose": "Gate 2 - within-backbone selectability. 정책 비교가 아니다.",
        "spec": "docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md",
        "cohort": {"mixed_backbones": len(mixed),
                   "informative_targets": len({b.target_id for b in mixed}),
                   "usable_folds": len(grid.folds),
                   "backbones": len(grid.backbones),
                   "targets": len(grid.targets)},
        "split": "LOTO over 12 targets (_gate2d_features.loto_splits)",
        "model": {"estimator": "sklearn.linear_model.Ridge", "alpha": RIDGE_ALPHA},
        "primary_arm": F.PRIMARY_ARM,
        "frozen_go_rule": {
            "delta_top4_min": G.GATE2_DELTA_MIN,
            "lcb_alpha": G.LCB_ONE_SIDED_ALPHA,
            "min_informative_targets": G.MIN_INFORMATIVE_TARGETS,
            "auc_is_descriptive_only": True,
        },
        "reference_points": {"soluprot": -0.001, "oracle": 0.326},
        "msa_low_depth_report": {
            "status": "reported",
            "threshold": low_depth["threshold"],
            "threshold_inherited_from": low_depth["threshold_inherited_from"],
            "low_depth_targets": low_depth_targets,
            "n_low_depth": low_depth["n"],
            "registered_band": (
                "1-3 : 민감도 코호트 10-8 이므로 계산 가능하고 1 차 판정과 나란히 "
                "보고한다 (스펙 §4 규칙 6 의 scope 반응표)."),
            "depth_profile": low_depth["depth_profile"],
            "borderline_note": (
                "2jokA01 은 usable 46 · median_depth 24 로 문턱 10 을 넘으므로 규칙상 "
                "저심도가 아니지만 나머지 아홉이 상한 3000 에 붙어 있는 것에 비하면 "
                "얇다. 분포는 사실상 이봉이다 (3 · 46 · 866 · 3000×9). **문턱을 46 "
                "위로 올리지 않는다** - 결과를 본 뒤의 문턱 쇼핑이다."),
            "never_dropped": (
                "어느 경우에도 타겟을 코호트에서 빼지 않는다. 저심도 처리는 제외가 "
                "아니라 가시화이며, msa_low_depth 지시자와 이 민감도가 그 전부다."),
            "sensitivity_is_reported_per_arm": (
                "각 arm 의 sensitivity_excluding_low_depth 를 본다."),
        },
        "msa_features_provenance": {
            "artifact": "public_data/benchmark/gate0/holdout_grid/msa_features.json",
            "conserved_positions_sha256_verified":
                msa["conserved_positions_sha256_verified"],
            "index_base": ("보존 위치는 0-기반(conserved_positions_0based), "
                           "mutation_sites 도 0-기반. manifest 해시 검증만 1-기반으로 "
                           "되돌려서 한다."),
            "undefined_targets": msa["undefined_targets"],
            "msa_run_code_sha": (msa.get("msa_run_provenance") or {}).get("code_sha"),
        },
        "s6_cheap_block_deviation": {
            "spec_says": "S6 = S5 + 기존 cheap feature (조성, MPNN score) [스펙 §4]",
            "implemented": "조성 20 열만. MPNN score 열은 없다.",
            "reason": ("격자의 sequences.csv 에 per-sequence MPNN score 열이 없고"
                       "(열: sequence_id·sequence·backbone_key·target_id·"
                       "backbone_source·temperature·soluprot), "
                       "mpnn_score_analysis.json 은 다른 코호트다(88 타겟/10,360 설계). "
                       "격자 1,728 서열 id 와 score 열을 가진 다른 코호트"
                       "(temperature_panel2·temperature_sweep) 의 교집합은 0 이다. "
                       "없는 feature 를 있는 것처럼 쓰지 않는다."),
            "effect_on_verdict": ("S6 가 스펙보다 좁다. 즉 판정 arm 이 스펙이 허용한 "
                                  "것보다 적은 정보를 받았고, NO-GO 라면 그만큼 약한 "
                                  "증거다. 이 차이를 결과에 기록한다."),
        },
        "arms_joint_pass": arms,
        "arms_structural_pass_secondary": arms_structural,
        "verdict": verdict,
        "verdict_note": note,
        "interim": interim,
        "no_go_reading": NO_GO_READING,
        **G.run_provenance(
            "scripts/benchmark/25_gate2_within_backbone_selectability.py",
            "scripts/benchmark/_gate2d.py",
            "scripts/benchmark/_gate2d_cohort.py",
            "scripts/benchmark/_gate2d_features.py",
            "scripts/benchmark/22_gate2d_prepare_esm.py",
            "scripts/benchmark/23_gate2d_prepare_msa_features.py",
            "scripts/transcoder/rapid_sr/clustered.py",
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"Gate 2 {verdict}  primary={F.PRIMARY_ARM} "
          f"delta={primary and primary.get('delta_top4_target_equal')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
