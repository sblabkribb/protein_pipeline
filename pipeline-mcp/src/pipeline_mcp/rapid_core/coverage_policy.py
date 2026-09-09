"""Coverage-preserving mode 의 결정 규칙.

myopic 이다. 여기서 계산하는 것은 **one-step posterior-predictive expected
marginal EFBC gain** 이고 그 이상이 아니다. 다음 관측의 예측 불확실성은
들어가지만 미래 학습 가치, value of information, knowledge gradient,
장기 최적성은 들어가지 않는다. 명시적 설계 선택이다.

과학적 실패 · 기술적 실패 · 실행 불가를 서로 다른 것으로 다룬다. 셋을 하나로
합치면 "이 unit 은 성과가 없다" 와 "이 unit 을 돌리지 못했다" 가 구분되지
않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from .coverage import CoverageState, FeasibleProbabilityModel


class CoverageAction(str, Enum):
    #: warm-up. 아직 판정하지 않는다.
    PROBE_UNIT = "probe_unit"
    ADVANCE_UNIT = "advance_unit"
    #: 양의 기대 이득을 주는 행동이 없다. 전역 최적도, 정보 소진도 아니다.
    STOP = "stop"
    #: 과학 예산 상한에 도달했다. STOP 과 다르다.
    BUDGET_EXHAUSTED = "budget_exhausted"
    #: 실행 계층 때문에 확증 종점을 낼 수 없다. 과학적 결론이 아니다.
    EXECUTION_INFEASIBLE = "execution_infeasible"


class CoverageReason(str, Enum):
    WARMUP_INCOMPLETE = "warmup_incomplete"
    POSITIVE_EXPECTED_GAIN = "positive_expected_gain"
    NO_POSITIVE_EXPECTED_GAIN = "no_positive_expected_gain"
    BUDGET_EXHAUSTED = "budget_exhausted"
    WARMUP_BLOCKED_BY_EXECUTION = "warmup_blocked_by_execution"
    NO_ADMISSIBLE_UNIT = "no_admissible_unit"


class PosteriorNotFrozenError(RuntimeError):
    """확률 모형 사양이 과학적으로 동결되지 않았다."""


class InvalidCampaignConfiguration(ValueError):
    """설정만 보고도 확증 종점을 낼 수 없다고 알 수 있다."""


@dataclass
class CoveragePolicy:
    state: CoverageState
    #: warm-up 기준. **유효 관측 수**이지 시도 횟수가 아니다.
    min_valid_observations: int
    #: 유효 관측 슬롯 상한. None 이면 상한 없음.
    evaluable_budget: int | None = None
    #: 다음 유효 관측이 feasible 일 확률. 동결된 사양이 없으면 None 이고,
    #: 그 상태에서 adaptive 단계에 들어가면 실패한다 - 임의 사전분포로
    #: 조용히 진행하지 않는다.
    probability_model: FeasibleProbabilityModel | None = None
    _unavailable: set[tuple[str, ...]] = field(default_factory=set)

    def __post_init__(self) -> None:
        """의무 probe 를 채울 수 없는 예산이면 시작 전에 거부한다.

        돌려보고 EXECUTION_INFEASIBLE 로 끝내면 실행 실패처럼 보이지만, 이것은
        실행 문제가 아니라 캠페인 설정 오류다. 두 상태를 구분한다.
        """
        need = self.min_valid_observations * len(self.state.units)
        if self.evaluable_budget is not None and self.evaluable_budget < need:
            raise InvalidCampaignConfiguration(
                f"예산 {self.evaluable_budget} 슬롯으로는 의무 probe 를 채울 수 "
                f"없다 (unit {len(self.state.units)} × {self.min_valid_observations} "
                f"= {need} 필요). 실행 실패가 아니라 설정 오류이므로 시작하지 "
                f"않는다.")

    # ---- 실행 가용성 --------------------------------------------------------

    def mark_execution_unavailable(self, unit: tuple[str, ...]) -> None:
        """재시도 정책이 소진됐다. 상태를 바꾸지 않고 후보에서만 뺀다."""
        if unit not in self.state.feasible:
            raise KeyError(f"등록되지 않은 unit: {unit}")
        self._unavailable.add(unit)

    def mark_execution_recovered(self, unit: tuple[str, ...]) -> None:
        self._unavailable.discard(unit)

    @property
    def unavailable(self) -> frozenset[tuple[str, ...]]:
        return frozenset(self._unavailable)

    def _admissible(self) -> list[tuple[str, ...]]:
        return [u for u in self.state.units if u not in self._unavailable]

    # ---- warm-up ------------------------------------------------------------

    def _needs_warmup(self, unit: tuple[str, ...]) -> bool:
        return self.state.valid_observations[unit] < self.min_valid_observations

    @property
    def warmup_complete(self) -> bool:
        return not any(self._needs_warmup(u) for u in self.state.units)

    # ---- 결정 ---------------------------------------------------------------

    def decide(self) -> "CoverageDecision":
        admissible = self._admissible()
        pending = [u for u in self.state.units if self._needs_warmup(u)]

        # 1) warm-up 이 끝나지 않았으면 STOP 은 후보가 아니다.
        if pending:
            ready = [u for u in pending if u in admissible]
            if not ready:
                # 실행 때문에 의무 probe 를 끝낼 수 없다. 과학적 결론이 아니고,
                # 문제 unit 을 빼고 계속하지도 않는다.
                return self._decision(
                    CoverageAction.EXECUTION_INFEASIBLE,
                    None, CoverageReason.WARMUP_BLOCKED_BY_EXECUTION,
                    blocked=tuple(sorted(pending)))
            unit = min(ready)      # 결정적 순서. 점수를 쓰지 않는다.
            return self._decision(CoverageAction.PROBE_UNIT, unit,
                                  CoverageReason.WARMUP_INCOMPLETE)

        # 2) 예산 상한. STOP 과 구분한다.
        if (self.evaluable_budget is not None
                and self.state.evaluable_slots_used >= self.evaluable_budget):
            return self._decision(CoverageAction.BUDGET_EXHAUSTED, None,
                                  CoverageReason.BUDGET_EXHAUSTED)

        if not admissible:
            return self._decision(CoverageAction.EXECUTION_INFEASIBLE, None,
                                  CoverageReason.NO_ADMISSIBLE_UNIT,
                                  blocked=tuple(sorted(self.state.units)))

        # 3) adaptive. 여기서부터 q_b 가 필요하다.
        if self.probability_model is None:
            raise PosteriorNotFrozenError(
                "coverage 확률 모형 사양이 동결되지 않았다. 분포족·사전분포·"
                "세기·풀링·갱신 규칙이 이 feasible 사건에 대해 명시적으로 "
                "고정되기 전에는 adaptive 단계를 돌리지 않는다. "
                "결과를 보고 사전분포를 고르는 것은 금지다.")

        scored = {}
        for unit in admissible:
            q = float(self.probability_model.probability(unit))
            delta = self.state.delta_if_feasible(unit)
            scored[unit] = {"q": q, "delta_efbc_if_feasible": delta,
                            "expected_marginal_efbc_gain": q * delta}
        best = max(admissible, key=lambda u: (scored[u]["expected_marginal_efbc_gain"],
                                              tuple(reversed(u))))
        gain = scored[best]["expected_marginal_efbc_gain"]
        # A_STOP = 0. 양의 이득이 없으면 멈춘다.
        if gain > 0.0:
            return self._decision(CoverageAction.ADVANCE_UNIT, best,
                                  CoverageReason.POSITIVE_EXPECTED_GAIN,
                                  scored=scored)
        return self._decision(CoverageAction.STOP, None,
                              CoverageReason.NO_POSITIVE_EXPECTED_GAIN,
                              scored=scored)

    def _decision(self, action, unit, reason, *, scored=None,
                  blocked=()) -> "CoverageDecision":
        return CoverageDecision(
            action=action, unit=unit, reason_code=reason,
            record={
                "current_efbc": self.state.efbc,
                "feasible_counts": {"|".join(u): self.state.feasible[u]
                                    for u in self.state.units},
                "valid_observations": {"|".join(u): self.state.valid_observations[u]
                                       for u in self.state.units},
                "warmup_complete": self.warmup_complete,
                "min_valid_observations": self.min_valid_observations,
                "evaluable_slots_used": self.state.evaluable_slots_used,
                "evaluable_budget": self.evaluable_budget,
                "attempts_made": self.state.attempts_made,
                "execution_unavailable": sorted("|".join(u) for u in self._unavailable),
                "blocked_units": sorted("|".join(u) for u in blocked),
                "per_unit": {"|".join(u): v for u, v in (scored or {}).items()},
                "selected_action": action.value,
                "selected_unit": "|".join(unit) if unit else "",
                "reason_code": reason.value,
            })


@dataclass(frozen=True)
class CoverageDecision:
    action: CoverageAction
    unit: tuple[str, ...] | None
    reason_code: CoverageReason
    #: 구조화된 결정 기록. UI 의 "왜 이쪽인가" 는 여기서 만든다 -
    #: Core 는 자연어 설명을 만들지 않는다.
    record: Mapping[str, object]
