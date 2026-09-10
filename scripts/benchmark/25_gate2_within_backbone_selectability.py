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
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
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


def _code_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def evaluate_arm(arm: str, grid: C.Grid, mixed: list[C.Backbone],
                 endpoint: str = "joint") -> dict:
    """한 arm 의 타겟 등가중 Delta_Top4. LOTO 로 낸 예측만 쓴다."""
    from sklearn.linear_model import Ridge

    all_folds = grid.folds
    targets = [f.target_id for f in all_folds]
    y = np.array([(f.joint_pass if endpoint == "joint" else f.structural_pass)
                  for f in all_folds], dtype=float)

    pred = np.zeros(len(all_folds))
    for train_idx, test_idx, _held in F.loto_splits(targets):
        try:
            x_fold, defect = F.assemble(arm, all_folds, train_idx)
        except NotImplementedError as exc:
            # 데이터 판정이 아니다. 규칙 5 의 non_evaluable 과 구분해 적는다 -
            # 섞으면 나중에 진짜 non_evaluable 을 알아볼 수 없다.
            return {"arm": arm, "label": F.ARM_LABELS[arm], "endpoint": endpoint,
                    "status": "not_implemented", "reason": str(exc)}
        if x_fold is None:
            return {"arm": arm, "label": F.ARM_LABELS[arm], "endpoint": endpoint,
                    "status": "non_evaluable",
                    "reason": ("train fold 에 정의된 MSA feature 가 없어 imputation "
                               "statistic 을 만들 수 없다" if defect is None
                               else "측정된 MSA feature 가 버려졌다 - 규칙 2 위반"),
                    "defect": defect}
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

    per_target = G.per_target_means(per_backbone, bb_targets)
    lcb = one_sided_lcb(per_target, alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    point = float(np.mean(per_target))
    return {
        "arm": arm, "label": F.ARM_LABELS[arm], "status": F.ARM_STATUS[arm],
        "endpoint": endpoint,
        "delta_top4_target_equal": round(point, 4),
        "one_sided_90_lcb": lcb.get("lcb"),
        "informative_targets": len(per_target),
        "meets_threshold": bool(point >= G.GATE2_DELTA_MIN),
        "lcb_exceeds_zero": bool(lcb.get("exceeds_zero")),
    }


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

    arms = {a: evaluate_arm(a, grid, mixed) for a in requested}
    arms_structural = {a: evaluate_arm(a, grid, mixed, endpoint="structural")
                       for a in requested}

    primary = arms.get(F.PRIMARY_ARM)
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
            "status": "pending",
            "reason": ("스펙 §4 규칙 6 은 저심도 타겟 목록·수와 그 타겟을 뺀 "
                       "민감도를 요구한다. MSA 실행이 끝나야 낼 수 있다. "
                       "여기에 자리만 두고 값을 지어내지 않는다."),
        },
        "arms_joint_pass": arms,
        "arms_structural_pass_secondary": arms_structural,
        "verdict": verdict,
        "verdict_note": note,
        "no_go_reading": NO_GO_READING,
        "code_sha": _code_sha(),
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"Gate 2 {verdict}  primary={F.PRIMARY_ARM} "
          f"delta={primary and primary.get('delta_top4_target_equal')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
