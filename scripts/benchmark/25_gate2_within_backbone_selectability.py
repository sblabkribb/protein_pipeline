#!/usr/bin/env python3
"""Gate 2. mixed 백본 안에서 joint-pass 후보를 골라낼 수 있는가.

코호트 : mixed 백본 37개 / informative 타겟 11개
split  : LOTO (12 타겟). 백본을 쪼개지 않는다.
1차    : 타겟 등가중 Delta_Top4, 판정 arm 은 S6 하나

GO <=> 점추정 Delta_Top4 >= +0.10 AND 단측 90% LCB > 0 AND informative >= 8

기준점(측정 완료): SoluProt -0.001, oracle +0.326.

사전 등록된 민감도 **두 개**를 1 차 판정 옆에 나란히 낸다. 코호트를 줄이는 것이
아니라 함께 보고하는 것이다.

  - `sensitivity_rfd3_only`      : RFD3-only(mixed 34 / informative 11) [스펙 §3]
  - `sensitivity_excluding_low_depth` : 저심도 타겟 제외 [스펙 §4 규칙 6]

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

#: §3 이 Gate 2 에 사전 등록한 민감도 코호트의 source 집합. Gate 1 primary 와 같다.
RFD3_SOURCES = ("rfd3",)

#: §3 이 인쇄한 그 코호트의 기하. 재생성값이 이것과 다르면 산출물이 스스로 말한다.
RFD3_SPEC_GEOMETRY = {"mixed_backbones": 34, "informative_targets": 11}

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


def _per_target_delta_top4(mixed: Sequence[C.Backbone],
                           score_of: dict[str, float],
                           endpoint: str) -> dict[str, float]:
    """백본별 Δ_Top4 -> 타겟 등가중 map. **코호트만 바꿔 두 번 부른다.**

    1 차와 RFD3-only 민감도가 같은 함수를 쓴다 - 민감도용 집계를 따로 적으면
    두 숫자가 같은 규칙으로 나왔다는 보장이 사라진다.
    """
    per_backbone, bb_targets = [], []
    for b in mixed:
        labels = [(f.joint_pass if endpoint == "joint" else f.structural_pass)
                  for f in b.folds]
        per_backbone.append(G.delta_top4(
            labels, [score_of[f.sequence_id] for f in b.folds],
            [f.sequence_id for f in b.folds]))
        bb_targets.append(b.target_id)
    return G.per_target_mean_map(per_backbone, bb_targets)


def _rfd3_only_sensitivity(grid: C.Grid, mixed: Sequence[C.Backbone],
                           score_of: dict[str, float], endpoint: str) -> dict:
    """RFD3-only 코호트 민감도 (스펙 §3).

    > "Gate 2 의 1차 코호트는 mixed 백본 37 개를 유지한다. … RFD3-only
    > (mixed 34, informative 11)를 민감도로 함께 보고한다."

    **1 차 판정은 mixed 37 그대로다.** Δ_Top4 는 백본 **내부**에서 계산되므로 각
    백본이 자기 단위이고 source 는 Gate 2 에서 교란이 아니다 - 그래서 코호트를
    줄이는 것이 아니라 나란히 둔다. 바뀌는 것은 평가 단위 집합 하나뿐이고, §3 이
    native 를 배분 풀에서 comparator 로 옮겼으므로 "배분 대상만" 의 값이 함께
    있어야 한다.

    **모델을 다시 적합하지 않는다.** 같은 LOTO 예측(`score_of`)을 그대로 쓴다.
    RFD3 폴드로만 다시 학습하면 그것은 코호트 민감도가 아니라 여덟 번째 arm 이고,
    동결된 ladder 는 S0-S6 일곱 개다. 학습 쪽 정렬은 Gate 1 에만 있는 조항이다.

    코호트는 `_gate2d_cohort.restrict_to_sources` 로 자른다 -
    26_gate2d_operating_characteristics.py 의 `OC_primary_rfd3_only` 와 같은
    slicer 이며 여기서 두 번째를 만들지 않는다.
    """
    sub = C.mixed_backbones(C.restrict_to_sources(grid, RFD3_SOURCES))
    excluded = sorted({b.backbone_key for b in mixed}
                      - {b.backbone_key for b in sub})
    per_target = _per_target_delta_top4(sub, score_of, endpoint)
    out: dict = {
        "status": "pre-registered sensitivity (스펙 §3)",
        "cohort": "RFD3-only mixed backbones",
        "sources": list(RFD3_SOURCES),
        "mixed_backbones": len(sub),
        "cohort_targets": sorted(per_target),
        "excluded_backbones": len(excluded),
        "excluded_backbone_keys": excluded,
        "primary_cohort_unchanged": True,
        "model_refit": False,
        "cohort_slicer": "_gate2d_cohort.restrict_to_sources",
    }
    if len(per_target) < G.MIN_INFORMATIVE_TARGETS:
        out["evaluable"] = False
        out["informative_targets"] = len(per_target)
        out["reason"] = (
            f"민감도 코호트 {len(per_target)} 이 floor "
            f"{G.MIN_INFORMATIVE_TARGETS} 미만이라 non-evaluable 이다. 1 차 판정은 "
            "그대로 내되 교차 확인이 불가능했다."
        )
        return out
    out["evaluable"] = True
    out.update(_summarise([per_target[t] for t in sorted(per_target)]))
    out["per_target_delta_top4"] = {t: round(v, 4)
                                    for t, v in sorted(per_target.items())}
    out["matches_spec_geometry"] = bool(
        len(sub) == RFD3_SPEC_GEOMETRY["mixed_backbones"]
        and len(per_target) == RFD3_SPEC_GEOMETRY["informative_targets"])
    out["spec_geometry"] = dict(RFD3_SPEC_GEOMETRY)
    return out


def _rfd3_refit_alternative_reading(grid: C.Grid, arm: str,
                                    blocks: Sequence[str], endpoint: str) -> dict:
    """RFD3 폴드로 **다시 적합한** 판. 보고 민감도가 아니라 기록된 대안 독법이다.

    `docs/results_of_record.md` 의 규칙은 모든 수가 산출물 경로를 달고 있어야
    한다는 것이다. 이 판은 산문에만 있었다 - 다르게 읽는 사람이 재유도 없이
    반박할 수 있어야 하므로 수를 산출물에 적는다.

    **보고되는 것은 여전히 `sensitivity_rfd3_only`(model_refit: false) 다.**
    RFD3 폴드로만 다시 학습하면 코호트 민감도가 아니라 동결되지 않은 여덟 번째
    arm 이 된다 - 동결된 ladder 는 S0-S6 일곱 개이고 "학습 쪽도 정렬한다" 는
    §3 의 Gate 1 조항이다. 그래서 이 블록은 판정에 들어가지 않는다.

    평가 단위(RFD3 mixed 34)와 집계(`_per_target_delta_top4`·`_summarise`)는
    부모 민감도와 같은 함수를 쓴다. 바뀌는 것은 학습 폴드 집합 하나다.
    """
    sub = C.restrict_to_sources(grid, RFD3_SOURCES)
    out: dict = {
        "status": "recorded alternative reading - NOT the reported sensitivity",
        "reported_sensitivity_is": ("이 블록의 부모인 sensitivity_rfd3_only "
                                    "(model_refit: false). 판정도 그쪽이다."),
        "model_refit": True,
        "cohort": "RFD3-only mixed backbones (평가 단위는 부모와 같다)",
        "train_folds": len(sub.folds),
        "train_folds_primary": len(grid.folds),
        "why_recorded": (
            "docs/results_of_record.md 는 모든 수가 산출물 경로를 달고 있어야 한다고 "
            "정한다. 이 판은 산문에만 있었다."),
        "why_it_is_not_the_sensitivity": (
            "RFD3 폴드로만 다시 학습하면 코호트 민감도가 아니라 동결되지 않은 여덟 "
            "번째 arm 이다. 동결된 ladder 는 S0-S6 일곱 개다."),
    }
    score_of, _n_features, _active, defect = _loto_scores(sub.folds, arm, blocks, endpoint)
    if score_of is None:
        out["evaluable"] = False
        out["defect"] = defect
        return out
    per_target = _per_target_delta_top4(C.mixed_backbones(sub), score_of, endpoint)
    out["evaluable"] = True
    out.update(_summarise([per_target[t] for t in sorted(per_target)]))
    out["per_target_delta_top4"] = {t: round(v, 4) for t, v in sorted(per_target.items())}
    out["verdict_if_this_were_the_arm"] = (
        "GO" if (out["meets_threshold"] and out["lcb_exceeds_zero"]
                 and out["informative_targets"] >= G.MIN_INFORMATIVE_TARGETS) else "NO-GO")
    return out


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


def _loto_scores(folds: Sequence[C.Fold], arm: str, blocks: Sequence[str],
                 endpoint: str) -> tuple[dict[str, float] | None, int, dict, dict | None]:
    """LOTO 예측. `(score_of, n_features, active_by_fold, defect)`.

    1 차 적합과 RFD3 재적합 대안 독법이 **같은 루프**를 쓴다 - LOTO 규칙을 두 번
    적으면 두 수가 같은 절차에서 나왔다는 보장이 사라진다. `score_of` 가 None
    이면 `defect` 가 이유다 (스펙 §4 규칙 5).
    """
    from sklearn.linear_model import Ridge

    targets = [f.target_id for f in folds]
    y = np.array([(f.joint_pass if endpoint == "joint" else f.structural_pass)
                  for f in folds], dtype=float)
    uses_msa = "msa" in blocks

    pred = np.zeros(len(folds))
    active_by_fold: dict[str, list[str]] = {}
    n_features = 0
    for train_idx, test_idx, held in F.loto_splits(targets):
        x_fold, defect = F.assemble(arm, folds, train_idx, blocks)
        if x_fold is None:
            return None, 0, {}, defect
        n_features = int(x_fold.shape[1])
        if uses_msa:
            # fold 별 사용 열을 남긴다. 없으면 narrowing 을 감사할 수 없다.
            active_by_fold[held] = F.active_msa_feature_names(folds, train_idx)
        model = Ridge(alpha=RIDGE_ALPHA)
        model.fit(x_fold[train_idx], y[train_idx])
        pred[test_idx] = model.predict(x_fold[test_idx])
    return ({f.sequence_id: float(p) for f, p in zip(folds, pred)},
            n_features, active_by_fold, None)


def evaluate_arm(arm: str, grid: C.Grid, mixed: list[C.Backbone],
                 endpoint: str = "joint",
                 low_depth_targets: Sequence[str] = (),
                 block_names: Sequence[str] | None = None,
                 refit_alternative_reading: bool = False) -> dict:
    """한 arm 의 타겟 등가중 Delta_Top4. LOTO 로 낸 예측만 쓴다.

    `block_names` 는 동결 블록 목록 대신 쓸 목록이다. arm 을 추가하는 수단이
    아니고, 이미 실행돼 기록된 realized-S6 를 planned-S6 와 나란히 재현하는
    데만 쓴다 (`F.REALIZED_S6_BLOCKS_2026_09_11`).

    `refit_alternative_reading` 은 RFD3 재적합 판을 **기록**할지다 (기본 False).
    보고되는 민감도와 판정은 그 값과 무관하다 -
    `_rfd3_refit_alternative_reading` 의 docstring 을 본다.
    """
    blocks = F.ARM_BLOCKS[arm] if block_names is None else tuple(block_names)
    score_of, n_features, active_by_fold, defect = _loto_scores(
        grid.folds, arm, blocks, endpoint)
    if score_of is None:
        return {"arm": arm, "label": F.ARM_LABELS[arm], "endpoint": endpoint,
                "status": "non_evaluable",
                "reason": ("train fold 에 정의된 MSA feature 가 없어 imputation "
                           "statistic 을 만들 수 없다" if defect is None
                           else "측정된 MSA feature 가 버려졌다 - 규칙 2 위반"),
                "defect": defect}
    uses_msa = "msa" in blocks
    per_target = _per_target_delta_top4(mixed, score_of, endpoint)
    out = {"arm": arm, "label": F.ARM_LABELS[arm], "status": F.ARM_STATUS[arm],
           "endpoint": endpoint}
    out.update(_summarise([per_target[t] for t in sorted(per_target)]))
    out["per_target_delta_top4"] = {t: round(v, 4) for t, v in sorted(per_target.items())}
    # 사전 등록된 민감도 둘. 둘 다 **1 차 판정 옆에** 놓는다 - 보고되지 않은 사전
    # 등록 분석은 숨긴 것과 구별되지 않는다.
    out["sensitivity_excluding_low_depth"] = _low_depth_sensitivity(
        per_target, low_depth_targets)
    out["sensitivity_rfd3_only"] = _rfd3_only_sensitivity(
        grid, mixed, score_of, endpoint)
    if refit_alternative_reading:
        out["sensitivity_rfd3_only"]["alternative_reading_model_refit"] = \
            _rfd3_refit_alternative_reading(grid, arm, blocks, endpoint)
    out["n_features"] = n_features
    out["feature_blocks"] = list(blocks)
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

    # §3 의 사전 등록 민감도 코호트. 1 차 코호트(mixed 37)는 그대로 두고 기하만
    # 미리 읽어 최상위에 적는다 - arm 이 하나도 요청되지 않은 실행에서도 이 분석이
    # 존재한다는 사실이 산출물에 남아야 한다.
    rfd3_mixed = C.mixed_backbones(C.restrict_to_sources(grid, RFD3_SOURCES))
    rfd3_report = {
        "status": "reported",
        "spec_says": ("Gate 2 의 1차 코호트는 mixed 백본 37 개를 유지한다. … "
                      "RFD3-only(mixed 34, informative 11)를 민감도로 함께 "
                      "보고한다. [스펙 §3]"),
        "primary_cohort_unchanged": True,
        "sources": list(RFD3_SOURCES),
        "mixed_backbones": len(rfd3_mixed),
        "informative_targets": len({b.target_id for b in rfd3_mixed}),
        "excluded_backbones": len(mixed) - len(rfd3_mixed),
        "spec_geometry": dict(RFD3_SPEC_GEOMETRY),
        "why_primary_keeps_native": (
            "Δ_Top4 는 백본 내부에서 계산되므로 각 백본이 자기 단위이고 source 는 "
            "Gate 2 에서 교란이 아니다. Gate 1 과 달리 코호트를 좁힐 이유가 없다."),
        "why_the_sensitivity_exists": (
            "그럼에도 §3 이 native 를 배분 풀에서 comparator 로 옮겼으므로, RAPID "
            "이 실제로 배분하는 대상만으로 좁힌 값을 1 차 옆에 함께 둔다."),
        "cohort_slicer": ("_gate2d_cohort.restrict_to_sources - "
                          "26_gate2d_operating_characteristics.py 의 "
                          "OC_primary_rfd3_only 와 같은 slicer 다."),
        "model_is_not_refit": (
            "같은 LOTO 예측을 그대로 쓴다. RFD3 폴드로만 다시 적합하면 코호트 "
            "민감도가 아니라 동결되지 않은 여덟 번째 arm 이 된다."),
        "sensitivity_is_reported_per_arm": (
            "각 arm 의 sensitivity_rfd3_only 를 본다."),
    }

    # 재적합 대안 독법은 **판정 arm 의 1 차 endpoint 에서만** 기록한다. 산문이
    # 인용하는 수가 그것 하나이고, 다른 arm 까지 돌리면 보고되지 않는 수를 열두 개
    # 더 만든다.
    arms = {a: evaluate_arm(a, grid, mixed, low_depth_targets=low_depth_targets,
                            refit_alternative_reading=(a == F.PRIMARY_ARM))
            for a in requested}
    arms_structural = {a: evaluate_arm(a, grid, mixed, endpoint="structural",
                                       low_depth_targets=low_depth_targets)
                       for a in requested}

    primary = arms.get(F.PRIMARY_ARM)

    # planned-S6(스펙대로, MPNN score 포함)와 realized-S6(2026-09-11 이전 실행,
    # MPNN score 없음)를 나란히 낸다. arm 을 하나 더 만든 것이 아니라 같은 arm 의
    # 구현 두 판이고, 판정은 planned 하나로만 낸다.
    s6_comparison: dict = {"status": "not_run"}
    if primary is not None and primary.get("status") == "primary":
        realized = evaluate_arm(F.PRIMARY_ARM, grid, mixed,
                                low_depth_targets=low_depth_targets,
                                block_names=F.REALIZED_S6_BLOCKS_2026_09_11)
        planned_go = (primary["meets_threshold"] and primary["lcb_exceeds_zero"]
                      and primary["informative_targets"] >= G.MIN_INFORMATIVE_TARGETS)
        realized_go = (realized["meets_threshold"] and realized["lcb_exceeds_zero"]
                       and realized["informative_targets"] >= G.MIN_INFORMATIVE_TARGETS)
        s6_comparison = {
            "status": "compared",
            "planned": {"blocks": list(F.ARM_BLOCKS[F.PRIMARY_ARM]),
                        "n_features": primary["n_features"],
                        "delta_top4_target_equal": primary["delta_top4_target_equal"],
                        "one_sided_90_lcb": primary["one_sided_90_lcb"],
                        "informative_targets": primary["informative_targets"],
                        "verdict": "GO" if planned_go else "NO-GO"},
            "realized_2026_09_11": {
                "blocks": list(F.REALIZED_S6_BLOCKS_2026_09_11),
                "n_features": realized["n_features"],
                "delta_top4_target_equal": realized["delta_top4_target_equal"],
                "one_sided_90_lcb": realized["one_sided_90_lcb"],
                "informative_targets": realized["informative_targets"],
                "verdict": "GO" if realized_go else "NO-GO",
                "note": "MPNN score 열이 없어 S5 와 같았다. PRIMARY DEVIATION 기록."},
            "verdicts_agree": bool(planned_go == realized_go),
            "delta_shift": round(primary["delta_top4_target_equal"]
                                 - realized["delta_top4_target_equal"], 4),
            "decided_by": "planned only. realized 는 기록이고 판정에 쓰지 않는다.",
        }

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
        "rfd3_only_cohort_report": rfd3_report,
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
            "status": "resolved 2026-09-11",
            "spec_says": "S6 = S5 + 기존 cheap feature (조성, MPNN score) [스펙 §4]",
            "implemented": ("조성 20 열 + per-sequence MPNN score 1 열. 스펙과 같다."),
            "history": ("2026-09-11 이전 실행의 S6 에는 MPNN score 열이 없었다 - 격자의 "
                        "sequences.csv 에 그 열이 없고(열: sequence_id·sequence·"
                        "backbone_key·target_id·backbone_source·temperature·soluprot), "
                        "mpnn_score_analysis.json 은 다른 코호트이며(88 타겟/10,360 설계) "
                        "격자 1,728 서열 id 와의 교집합이 0 이었다. 그 실행의 S6 는 "
                        "S5 와 bit-for-bit 같았고 Gate 2 판정이 PRIMARY DEVIATION 으로 "
                        "남았다."),
            "resolution": ("27_gate2d_prepare_mpnn_scores.py 가 격자 1,680 폴드의 score 를 "
                           "직접 계산한다(새 AF2 0 개). 이제 S6 가 스펙대로다."),
            "comparison": "s6_planned_vs_realized 를 본다.",
        },
        "s6_planned_vs_realized": s6_comparison,
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
