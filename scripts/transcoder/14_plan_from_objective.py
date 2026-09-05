#!/usr/bin/env python3
"""설계 목표를 받아 사람이 검토·수정할 계획을 만든다.

계획의 모든 결정에는 근거가 붙는다. 근거는 우리가 측정한 값이거나 문헌이며,
둘 다 없으면 `assumption` 으로 표시한다. 근거 없는 결정은 만들 수 없다
(`Decision` 이 강제).

산출물은 그대로 실행되지 않는다. `--apply` 로 승인해야 PipelineRequest 가 된다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.objective import Decision, Evidence, Objective  # noqa: E402
from rapid_sr.protocol import GATE0_THRESHOLDS  # noqa: E402

MEASUREMENTS = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"


def _measurement(statement: str, source: str, value: str = "") -> Evidence:
    return Evidence(kind="internal_measurement", statement=statement,
                    source=source, value=value)


def _literature(statement: str, source: str) -> Evidence:
    return Evidence(kind="literature", statement=statement, source=source)


def build_plan(objective: Objective) -> dict:
    """목표에서 계획을 만든다. 목표가 바꾸는 것과 안 바꾸는 것을 분리한다."""
    weights = objective.normalized_weights()
    wants_diversity = weights.get("diversity", 0.0) >= 0.2

    decisions: list[Decision] = [
        Decision(
            field_name="gate0_routing_unit", value="target",
            rationale="검증된 라우팅 단위는 백본이 아니라 타겟이다. native 백본은 "
                      "타겟당 1개뿐이고 RFD3 는 타겟 내부 yield sd 가 0.044 로 "
                      "고를 것이 거의 없다.",
            evidence=(
                _measurement("타겟 수준 게이트 0 AUC 0.725 (CI 0.709-0.740), n=62 타겟",
                             "gate0_target_level.json", "AUC=0.725"),
                _measurement("타겟 내부 백본 순위 예측 실패 rho -0.257 (CI -0.579~+0.118)",
                             "gate0 within-target analysis", "rho=-0.257"),
            ),
            editable=False,
        ),
        Decision(
            field_name="gate0_feature", value="raw_mpnn_encoder",
            rationale="구조 기술자보다 유의하게 낫고, 희소 표현은 아직 붙일 근거가 없다.",
            evidence=(
                _measurement("paired C-B AUC +0.073 (CI 0.050-0.096), 타겟 수준",
                             "gate0_target_level.json", "+0.073"),
            ),
        ),
        Decision(
            field_name="use_soluble_model", value=True,
            rationale="용해도 목표가 있으면 soluble 가중치를 쓴다.",
            evidence=(
                _literature(
                    "ProteinMPNN 설계 서열의 88%가 가용성으로 보고됨. soluble 가중치"
                    "(v_48_020)가 공개 배포본에 포함되어 있다.",
                    "Dauparas et al., Science 378(6615):49-56, 2022. PMID 36108050"),
            ),
        ),
        Decision(
            field_name="af2_verification", value="keep",
            rationale="AF2 를 값싼 대체물로 바꾸지 않는다. 서열 표현으로 pLDDT 순위를 "
                      "맞히려는 시도가 전부 실패했다.",
            evidence=(
                _measurement(
                    "서열축 5개 arm 모두 타겟 내부 pLDDT CI 가 0 을 포함 "
                    "(조성 0.047 / ESM 0.021 / ESM+조성 0.014 / PLT 0.008 / CLT -0.030)",
                    "sequence_axis_ablation.json"),
            ),
            editable=False,
        ),
        Decision(
            field_name="soluprot_cutoff", value=GATE0_THRESHOLDS["soluprot_min"],
            rationale="게이트 1 임계값. SoluProt 은 조성으로 거의 재현되므로 값싼 "
                      "대체가 가능하지만 대체 자체가 목적은 아니다.",
            evidence=(
                _measurement("조성 특징만으로 SoluProt 타겟 내부 rho 0.983, Top-5 regret 0.000",
                             "gate_feasibility_ridge.json", "rho=0.983"),
            ),
        ),
        Decision(
            field_name="sequences_per_backbone", value=16,
            rationale="yield 추정 정밀도와 AF2 비용의 절충. 애매한 백본만 32개로 올린다.",
            evidence=(
                _measurement("n=16 에서 비율 추정 표준오차 약 0.125, n=32 에서 약 0.088",
                             "rapid_sr.protocol"),
            ),
        ),
    ]

    if wants_diversity:
        decisions.append(Decision(
            field_name="sampling_temp", value=0.3,
            rationale="다양성 가중치가 높다. 높은 온도가 탐색 폭을 넓히고, 지금까지 "
                      "용해도 손실은 관측되지 않았다.",
            evidence=(
                _measurement("T=0.3 에서 위치 엔트로피 +0.265 (CI +0.224~+0.318), "
                             "쌍별 거리 +0.121 (CI +0.103~+0.143)",
                             "temperature_sweep/conditions.csv"),
                _measurement("같은 조건에서 SoluProt 통과율 차이 0.000 (CI -0.033~+0.033)",
                             "temperature_sweep/conditions.csv"),
                Evidence(kind="assumption",
                         statement="구조 품질(structural_yield)에 대한 온도 효과는 "
                                   "AF2 480 결과가 나오기 전까지 미검증이다."),
            ),
        ))
    else:
        decisions.append(Decision(
            field_name="sampling_temp", value=0.1,
            rationale="기존 RAPID 기본값. 온도의 구조 품질 효과가 아직 미검증이라 "
                      "기본값에서 벗어날 근거가 없다.",
            evidence=(
                Evidence(kind="assumption",
                         statement="AF2 480 결과 전까지 T 변경 근거 없음. 기존 데이터는 "
                                   "전부 T=0.1 로 생성되었다."),
            ),
        ))

    plan = {
        "objective": objective.to_dict(),
        "decisions": [d.to_dict() for d in decisions],
        "review_required": True,
        "editable_fields": [d.field_name for d in decisions if d.editable],
        "locked_fields": [d.field_name for d in decisions if not d.editable],
    }
    if objective.unsupported():
        plan["warnings"] = [
            f"'{name}' 은 현재 RAPID 가 평가하지 못한다. 가중치를 받아도 반영되지 않는다."
            for name in objective.unsupported()
        ]
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective", default="", help="목표 JSON 파일")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    if args.objective:
        raw = json.loads(Path(args.objective).read_text(encoding="utf-8"))
    else:
        raw = {"weights": {"solubility": 0.4, "structural_preservation": 0.4,
                           "diversity": 0.2},
               "constraints": {"rmsd_max": 2.0}, "budget": {"af2_calls": 500}}
    objective = Objective(weights=raw.get("weights", {}),
                          constraints=raw.get("constraints", {}),
                          budget=raw.get("budget", {}))
    plan = build_plan(objective)

    print(json.dumps(plan["objective"], indent=2, ensure_ascii=False))
    print("\n=== 결정 ===")
    for decision in plan["decisions"]:
        lock = "" if decision["editable"] else "  [고정]"
        print(f"\n{decision['field']} = {decision['value']}{lock}")
        print(f"  근거: {decision['rationale']}")
        for ev in decision["evidence"]:
            src = f" <- {ev['source']}" if ev["source"] else ""
            print(f"    [{ev['kind']}] {ev['statement']}{src}")
    for warning in plan.get("warnings", []):
        print(f"\n[경고] {warning}")
    print(f"\n검토 필요: {plan['review_required']} | 수정 가능 {len(plan['editable_fields'])}개 "
          f"| 고정 {len(plan['locked_fields'])}개")
    if args.out:
        Path(args.out).write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
