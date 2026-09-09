"""운영 상태와 과학적 허가를 분리한다.

두 축은 서로 다른 질문이다.

  operational   지금 실행할 수 있는가
  scientific    이 결과를 이 목적으로 써도 되는가

한 값으로 합치면 표현할 수 없는 조합이 생긴다. 워커가 살아 있고
(`service_alive`) 주석으로는 쓸 수 있지만 (`annotation`) 배분 보상으로는 쓸 수
없는 (`allocation` 없음) 평가자가 실재한다.

`computed` 를 별도 값으로 두는 이유: "숫자가 나온다" 는 "그 숫자를 쓸 수 있다"
가 아니다. 레지스트리에서 한 objective 에 `status: measured` 를 적었다가
"수를 계산한다" 와 "objective 가 측정됐다" 를 혼동한 적이 있고, 테스트가 그것을
잡았다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ScientificPermission(str, Enum):
    """이 evaluator 결과를 어디까지 쓸 수 있는가. 포함 관계가 아니라 목록이다."""

    #: 숫자가 나온다. 그뿐이다.
    COMPUTED = "computed"
    #: 기록하고 보여줄 수 있다.
    ANNOTATION = "annotation"
    #: 후보 순위를 매기는 데 쓸 수 있다.
    RANKING = "ranking"
    #: 후보를 탈락시키는 데 쓸 수 있다.
    GATE = "gate"
    #: 다음 계산을 어디에 쓸지 정하는 보상으로 쓸 수 있다.
    ALLOCATION = "allocation"
    #: 전향적 실험 증거가 있다.
    WET_VALIDATED = "wet_validated"


@dataclass(frozen=True)
class OperationalStatus:
    """실행 가능성. 과학적 허가와 섞지 않는다."""

    installed: bool = False
    service_alive: bool = False
    wired: bool = False

    @property
    def runnable(self) -> bool:
        return self.installed and self.service_alive and self.wired


@dataclass(frozen=True)
class PermissionSet:
    """한 (task, evaluator, objective) 조합에 허용된 역할."""

    task_profile: str
    evaluator: str
    objective: str
    operational: OperationalStatus
    allowed: frozenset[ScientificPermission] = field(default_factory=frozenset)
    #: 왜 이 허가인지. 승격에는 증거가 필요하다.
    evidence: str = ""

    def __post_init__(self) -> None:
        for name in ("task_profile", "evaluator", "objective"):
            if not getattr(self, name):
                raise ValueError(f"{name} 이 필요하다")
        bad = [p for p in self.allowed if not isinstance(p, ScientificPermission)]
        if bad:
            raise TypeError(f"알 수 없는 허가: {bad}")
        # allocation 이나 wet_validated 는 증거 없이 붙일 수 없다. 사용자가 UI 에서
        # 골랐다는 것은 증거가 아니다 (Invariant 6).
        heavy = {ScientificPermission.ALLOCATION, ScientificPermission.WET_VALIDATED}
        if (set(self.allowed) & heavy) and not self.evidence.strip():
            raise ValueError(
                f"{self.evaluator}/{self.objective}: allocation 또는 wet_validated "
                f"허가에는 evidence 가 필요하다. 두 예측기가 어긋난다는 사실이 "
                f"세 번째를 심판으로 만들어 주지 않는다.")

    def permits(self, role: ScientificPermission) -> bool:
        return role in self.allowed

    def require(self, role: ScientificPermission) -> None:
        """허용되지 않으면 조용히 넘기지 않고 크게 실패한다 (§K3)."""
        if not self.permits(role):
            allowed = sorted(p.value for p in self.allowed) or ["없음"]
            raise PermissionError(
                f"{self.evaluator} 는 {self.task_profile}/{self.objective} 에서 "
                f"{role.value} 로 허용되지 않았다. 현재 허가: {allowed}. "
                f"유사한 평가자로 자동 대체하지 않는다.")

    def to_dict(self) -> dict:
        return {
            "task_profile": self.task_profile, "evaluator": self.evaluator,
            "objective": self.objective,
            "operational": {"installed": self.operational.installed,
                            "service_alive": self.operational.service_alive,
                            "wired": self.operational.wired,
                            "runnable": self.operational.runnable},
            "allowed": sorted(p.value for p in self.allowed),
            "evidence": self.evidence,
        }
