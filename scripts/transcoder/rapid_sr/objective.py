"""설계 목표 명세와 계획 결정 기록.

두 가지를 강제한다.

1. **hard constraint 와 soft objective 를 분리한다.** 가중합 하나로 뭉치면
   "RMSD 2A 이내" 같은 절대 조건이 다른 점수로 상쇄될 수 있다.
2. **모든 결정에 근거 출처를 붙인다.** 근거는 우리가 측정한 값이거나 문헌이며,
   둘 다 아니면 `assumption` 으로 표시한다. 표시 없는 결정은 만들 수 없다.
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
