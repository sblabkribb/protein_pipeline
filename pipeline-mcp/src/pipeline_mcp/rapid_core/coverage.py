"""Coverage-preserving mode 의 상태와 지표.

Core 이므로 도메인 어휘가 없다. 무엇을 unit 이라 부르는지도, 무엇을 feasible
이라 판정하는지도 여기 나오지 않는다 - Core 가 아는 것은 coverage unit 의
목록과, 관측 하나가 feasible 이었는지를 이미 판정해서 넘겨준 결과뿐이다.
판정 기준은 profile 이 정한다.

EFBC 가 재는 것
---------------
feasible mass 가 여러 coverage unit 에 **얼마나 고르게 퍼져 있는가** 다.
feasible 후보의 개수가 아니다. 그래서 새 feasible 후보가 생겨도 EFBC 가 줄 수
있다 - 이미 몰려 있는 unit 에 하나 더 붙으면 집중이 심해지기 때문이다.
버그가 아니다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Sequence

from .evaluation import EvaluationResult, Validity


class OutcomeClass(str, Enum):
    """관측 하나가 과학적으로 무엇이었는가."""

    #: 목표 사건이 일어났다. coverage mass 가 는다.
    FEASIBLE = "feasible"
    #: 평가는 성립했고 목표 사건이 아니었다. 실패 관측으로 센다.
    VALID_NON_PASS = "valid_non_pass"
    #: 평가가 성립하지 않았다. **과학적 사후분포를 갱신하지 않는다.**
    #: 기술적 실패를 생물학적 실패로 읽으면 안 된다.
    NO_UPDATE = "no_update"


def classify_outcome(result: EvaluationResult, *, feasible: bool) -> OutcomeClass:
    """`feasible` 은 profile 이 판정해서 넘긴다. Core 는 그 기준을 모른다."""
    if result.validity is not Validity.OK:
        return OutcomeClass.NO_UPDATE
    return OutcomeClass.FEASIBLE if feasible else OutcomeClass.VALID_NON_PASS


def effective_coverage(counts: Sequence[float]) -> float:
    """exp(Shannon entropy). feasible mass 의 유효 unit 수.

    비어 있으면 0 이다. 0 과 1 은 다르다 - 아무 데도 없는 것과 한 곳에 있는
    것은 같지 않다.
    """
    total = float(sum(counts))
    if total <= 0.0:
        return 0.0
    entropy = 0.0
    for value in counts:
        if value <= 0:
            continue
        p = float(value) / total
        entropy -= p * math.log(p)
    return math.exp(entropy)


class FeasibleProbabilityModel(Protocol):
    """다음 유효 관측이 feasible 일 확률.

    **Phase 4 에는 구현이 없다.** 이 사건에 대한 사후분포 사양(분포족·사전분포·
    세기·풀링·갱신 규칙)이 동결돼 있지 않기 때문이다. 자세한 것은
    `docs/specs/rapid-v2-coverage-endpoint-freeze.md` 와 Phase 4 보고를 본다.
    """  # noqa: D401

    def probability(self, unit: tuple[str, ...]) -> float: ...


@dataclass
class CoverageState:
    """unit 별 feasible mass 와 유효 관측 수.

    두 수를 따로 센다. warm-up 은 유효 관측 수로 판정하고, EFBC 는 feasible
    mass 로 계산한다. 시도 횟수는 어느 쪽에도 들어가지 않는다.
    """

    units: tuple[tuple[str, ...], ...]
    feasible: dict[tuple[str, ...], int] = field(default_factory=dict)
    valid_observations: dict[tuple[str, ...], int] = field(default_factory=dict)
    #: 과학 예산과 별개로 기록만 하는 운영 수치.
    attempted: dict[tuple[str, ...], int] = field(default_factory=dict)
    no_update: dict[tuple[str, ...], int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.units:
            raise ValueError("coverage unit 이 최소 하나 필요하다")
        for unit in self.units:
            self.feasible.setdefault(unit, 0)
            self.valid_observations.setdefault(unit, 0)
            self.attempted.setdefault(unit, 0)
            self.no_update.setdefault(unit, 0)

    def _check(self, unit: tuple[str, ...]) -> None:
        if unit not in self.feasible:
            raise KeyError(f"등록되지 않은 coverage unit: {unit}")

    def record(self, unit: tuple[str, ...], outcome: OutcomeClass) -> None:
        self._check(unit)
        self.attempted[unit] += 1
        if outcome is OutcomeClass.NO_UPDATE:
            self.no_update[unit] += 1
            return
        self.valid_observations[unit] += 1
        if outcome is OutcomeClass.FEASIBLE:
            self.feasible[unit] += 1

    # ---- 지표 --------------------------------------------------------------

    @property
    def counts(self) -> list[int]:
        return [self.feasible[u] for u in self.units]

    @property
    def efbc(self) -> float:
        return effective_coverage(self.counts)

    def efbc_if_feasible(self, unit: tuple[str, ...]) -> float:
        self._check(unit)
        counts = [self.feasible[u] + (1 if u == unit else 0) for u in self.units]
        return effective_coverage(counts)

    def delta_if_feasible(self, unit: tuple[str, ...]) -> float:
        """이 unit 에서 feasible 이 하나 더 나올 때 EFBC 변화. 음수일 수 있다."""
        return self.efbc_if_feasible(unit) - self.efbc

    # ---- 예산 --------------------------------------------------------------

    @property
    def evaluable_slots_used(self) -> int:
        """유효 관측만 센다. 시도 횟수도, 기술적 실패도 예산을 쓰지 않는다."""
        return sum(self.valid_observations.values())

    @property
    def attempts_made(self) -> int:
        return sum(self.attempted.values())

    def to_dict(self) -> dict:
        return {
            "units": ["|".join(u) for u in self.units],
            "feasible": {"|".join(u): self.feasible[u] for u in self.units},
            "valid_observations": {"|".join(u): self.valid_observations[u]
                                   for u in self.units},
            "attempted": {"|".join(u): self.attempted[u] for u in self.units},
            "no_update": {"|".join(u): self.no_update[u] for u in self.units},
            "efbc": self.efbc,
            "evaluable_slots_used": self.evaluable_slots_used,
            "attempts_made": self.attempts_made,
        }
