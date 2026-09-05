"""목표를 계획으로 바꾸는 모듈. MCP 도구와 CLI 가 같은 코드를 쓴다.

두 가지를 강제한다.

1. **hard constraint 와 soft objective 를 분리한다.** 가중합 하나로 뭉치면
   "RMSD 2A 이내" 같은 절대 조건이 다른 점수로 상쇄될 수 있다.
2. **모든 결정에 근거 출처를 붙인다.** 근거는 우리가 측정한 값이거나 문헌이며,
   둘 다 아니면 `assumption` 으로 표시한다. 근거 없는 결정은 만들 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

# 근거의 종류. 측정과 문헌과 가정을 섞어 부르지 않는다.
EVIDENCE_KINDS = ("internal_measurement", "literature", "assumption")

KNOWN_OBJECTIVES = (
    "solubility", "structural_preservation", "stability", "activity",
    "aggregation", "developability", "diversity",
)


@dataclass(frozen=True)
class Evidence:
    kind: str
    statement: str
    source: str = ""
    value: str = ""

    def __post_init__(self) -> None:
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(f"evidence kind must be one of {EVIDENCE_KINDS}, got {self.kind!r}")
        if self.kind != "assumption" and not self.source:
            raise ValueError("측정과 문헌 근거에는 source 가 반드시 있어야 한다")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Decision:
    """계획의 결정 하나. 사람이 고칠 수 있도록 editable 을 명시한다."""

    field_name: str
    value: object
    rationale: str
    evidence: tuple[Evidence, ...] = ()
    editable: bool = True

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError(f"{self.field_name}: 근거 없는 결정은 만들 수 없다")

    def to_dict(self) -> dict:
        return {
            "field": self.field_name, "value": self.value,
            "rationale": self.rationale, "editable": self.editable,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class Objective:
    """사용자 설계 목표.

    weights 는 soft objective 이고 constraints 는 hard 다. 둘을 섞지 않는다.
    """

    weights: dict[str, float] = field(default_factory=dict)
    constraints: dict[str, object] = field(default_factory=dict)
    budget: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = sorted(set(self.weights) - set(KNOWN_OBJECTIVES))
        if unknown:
            raise ValueError(f"알 수 없는 objective: {unknown}. 지원: {list(KNOWN_OBJECTIVES)}")
        for name, value in self.weights.items():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} weight 는 0..1 이어야 한다: {value}")

    def normalized_weights(self) -> dict[str, float]:
        total = sum(float(v) for v in self.weights.values())
        if total <= 0:
            return {}
        return {k: round(float(v) / total, 4) for k, v in self.weights.items()}

    def unsupported(self) -> list[str]:
        """현재 RAPID 가 실제로 평가하지 못하는 목표.

        가중치를 받아놓고 조용히 무시하면 사용자는 반영된 줄 안다.
        """
        measurable = {"solubility", "structural_preservation", "diversity"}
        return sorted(set(self.weights) - measurable)

    def to_dict(self) -> dict:
        return {
            "weights": dict(self.weights),
            "normalized_weights": self.normalized_weights(),
            "constraints": dict(self.constraints),
            "budget": dict(self.budget),
            "unsupported_objectives": self.unsupported(),
        }


# 게이트 1 통과 임계값. rapid_sr.protocol 과 같은 값을 쓴다.
SOLUPROT_PASS_THRESHOLD = 0.5


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
            field_name="soluprot_cutoff", value=SOLUPROT_PASS_THRESHOLD,
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




# 계획의 결정 이름 -> PipelineRequest 필드. 여기 없는 결정은 요청에 반영되지 않고
# 설명용으로만 남는다(예: gate0_routing_unit 은 라우팅 정책이지 요청 필드가 아니다).
DECISION_TO_REQUEST_FIELD = {
    "use_soluble_model": "use_soluble_model",
    "soluprot_cutoff": "soluprot_cutoff",
    "sequences_per_backbone": "num_seq_per_tier",
    "sampling_temp": "sampling_temp",
}


def plan_to_request_overrides(plan: dict) -> dict:
    """승인된 계획을 PipelineRequest 인자로 바꾼다.

    매핑되지 않는 결정은 조용히 버리지 않고 `unmapped` 로 돌려준다. 사용자가
    고친 값이 반영되지 않았는데 반영된 줄 아는 상황을 막는다.
    """
    overrides: dict[str, object] = {}
    unmapped: list[str] = []
    for decision in plan.get("decisions", []):
        field_name = decision.get("field")
        if field_name in DECISION_TO_REQUEST_FIELD:
            overrides[DECISION_TO_REQUEST_FIELD[field_name]] = decision.get("value")
        else:
            unmapped.append(str(field_name))

    constraints = (plan.get("objective") or {}).get("constraints") or {}
    if "rmsd_max" in constraints:
        overrides["af2_rmsd_cutoff"] = float(constraints["rmsd_max"])
    return {"request_overrides": overrides, "unmapped_decisions": sorted(unmapped)}


def apply_edits(plan: dict, edits: dict) -> dict:
    """사람이 고친 값을 계획에 반영한다. 고정 필드는 거부한다."""
    locked = set(plan.get("locked_fields") or [])
    rejected: list[str] = []
    applied: dict[str, object] = {}
    decisions = []
    for decision in plan.get("decisions", []):
        item = dict(decision)
        name = item.get("field")
        if name in edits:
            if name in locked:
                rejected.append(str(name))
            else:
                item["value"] = edits[name]
                item["edited_by_user"] = True
                applied[str(name)] = edits[name]
        decisions.append(item)
    out = dict(plan)
    out["decisions"] = decisions
    out["applied_edits"] = applied
    if rejected:
        out["rejected_edits"] = sorted(rejected)
    return out


# LLM 에게 주는 지시. 계획에 없는 근거를 만들어내지 못하게 범위를 좁힌다.
EXPLAIN_SYSTEM_INSTRUCTION = (
    "You explain an already-made protein design plan to a scientist, in Korean.\n"
    "Rules you must follow:\n"
    "1. Explain ONLY the decisions and evidence given to you. Do not add facts, "
    "numbers, citations, or mechanisms that are not in the input.\n"
    "2. If a decision rests on an assumption rather than a measurement, say so "
    "plainly.\n"
    "3. Do not claim a decision is validated when its evidence is an assumption.\n"
    "4. Be concise: at most 6 sentences.\n"
    "5. Do not invent PubMed IDs, DOIs, or dataset names."
)


def suggest_questions(plan: dict) -> list[dict]:
    """무엇을 물어볼지 계획에서 직접 고른다.

    LLM 에게 질문을 짓게 하면 근거 없는 항목을 물어볼 수 있다. 대신 계획 안에서
    **실제로 불확실한 지점**을 고른다: 근거가 가정뿐인 편집 가능한 결정, 그리고
    평가하지 못하는 목표.
    """
    questions: list[dict] = []
    locked = set(plan.get("locked_fields") or [])
    for decision in plan.get("decisions", []):
        name = str(decision.get("field"))
        if name in locked:
            continue
        kinds = {e.get("kind") for e in decision.get("evidence", [])}
        if kinds and kinds <= {"assumption"}:
            questions.append({
                "field": name,
                "question": f"'{name}' 는 측정 근거 없이 정한 값입니다. "
                            f"현재 {decision.get('value')} 로 두시겠습니까?",
                "reason": "evidence_is_assumption_only",
            })
        elif "assumption" in kinds:
            questions.append({
                "field": name,
                "question": f"'{name}' 는 일부만 측정으로 뒷받침됩니다. "
                            f"{decision.get('value')} 를 유지할지 확인이 필요합니다.",
                "reason": "evidence_partially_assumption",
            })
    for warning in plan.get("warnings", []):
        questions.append({
            "field": "", "question": f"{warning} 이 목표를 계속 두시겠습니까?",
            "reason": "objective_not_measurable",
        })
    return questions


def build_explain_prompt(plan: dict) -> str:
    """LLM 에 넘길 사용자 프롬프트. 계획 내용만 담는다."""
    lines = ["다음은 이미 확정된 설계 계획입니다. 사용자에게 설명해 주세요.", ""]
    objective = plan.get("objective") or {}
    if objective.get("normalized_weights"):
        lines.append(f"목표 가중치: {objective['normalized_weights']}")
    if objective.get("constraints"):
        lines.append(f"절대 제약: {objective['constraints']}")
    lines.append("")
    for decision in plan.get("decisions", []):
        lines.append(f"- {decision.get('field')} = {decision.get('value')}"
                     f"{' (고정)' if not decision.get('editable') else ''}")
        lines.append(f"  이유: {decision.get('rationale')}")
        for ev in decision.get("evidence", []):
            source = f" [출처 {ev.get('source')}]" if ev.get("source") else ""
            lines.append(f"  근거({ev.get('kind')}): {ev.get('statement')}{source}")
    for warning in plan.get("warnings", []):
        lines.append(f"- 경고: {warning}")
    return "\n".join(lines)


def fallback_explanation(plan: dict) -> str:
    """LLM 이 없을 때. 지어내지 않고 계획을 세어서 말한다."""
    decisions = plan.get("decisions", [])
    assumption_fields = [
        d.get("field") for d in decisions
        if any(e.get("kind") == "assumption" for e in d.get("evidence", []))
    ]
    parts = [
        f"결정 {len(decisions)}건 중 {len(plan.get('locked_fields') or [])}건은 "
        f"측정 결과가 반대를 지지해 고정되어 있습니다."
    ]
    if assumption_fields:
        parts.append("가정에 기대는 결정: " + ", ".join(str(f) for f in assumption_fields) + ".")
    if plan.get("warnings"):
        parts.append(f"평가할 수 없는 목표가 {len(plan['warnings'])}건 있습니다.")
    parts.append("LLM 설명이 설정되지 않아 계획 요약만 표시합니다.")
    return " ".join(parts)
