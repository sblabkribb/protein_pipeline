"""RAPID Core — 다음 계산을 어디에 쓸 것인가.

여기에는 평가 모델 이름도, 도메인 개념도 없다. Core 가 아는 것은 arm 계층,
관측 모형이 내놓는 세 값(expected_utility · uncertainty · allocation_signal),
비용, 그리고 profile 이 준 가중치와 문턱뿐이다.

무엇이 "백본" 이고 무엇이 "조건" 인지 Core 는 모른다. `ArmSchema.hierarchy`
가 몇 단계인지만 안다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .arm import ArmSchema, DesignArm
from .observation import ObservationModel


@dataclass(frozen=True)
class PolicyProfile:
    """가중치와 문턱. 알고리즘이 아니라 데이터다."""

    profile_id: str
    beta_uncertainty: float
    gamma_diversity: float
    lambda_cost: float
    eta_variation_exploration: float
    #: 판정하기에 충분한 최소 관측 수. 이보다 얇으면 판정하지 않는다.
    min_observations: int
    #: 이 아래면 결과가 한쪽 끝에 붙어 있다고 본다.
    allocation_signal_floor: float
    #: 탐색이 아닌 기준 variation. None 이면 variation 탐색 개념이 없다.
    reference_variation: str | None = None
    #: variation 축의 이름. reference_variation 과 비교할 dimension.
    variation_key: str = ""
    #: 행동 이름. profile 이 정한다 - Core 는 문자열을 만들지 않는다.
    action_names: Mapping[str, str] = field(default_factory=dict)
    #: 이유 문구도 profile 이 정한다. Core 가 문장을 지으면 도메인 어휘가
    #: Core 로 새어 들어오고, frozen profile 의 문구를 재현할 수도 없다.
    #: probe_more 는 {n_observed} 와 {min_observations} 를 받는다.
    reason_templates: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    unit: tuple[str, ...]
    state: Mapping[str, object]


class RapidCore:
    def __init__(self, arms: Sequence[DesignArm], schema: ArmSchema,
                 model: ObservationModel, policy: PolicyProfile) -> None:
        if not arms:
            raise ValueError("arm 이 최소 하나 필요하다")
        self.schema = schema
        self.policy = policy
        self.model = model
        self.arms: dict[str, DesignArm] = {a.key: a for a in arms}
        self.arm_keys = list(self.arms)
        self._cost_scale = self._build_cost_scale()

    # ---- 비용 ---------------------------------------------------------------

    def _build_cost_scale(self) -> float | None:
        known = [a.cost_seconds for a in self.arms.values() if a.cost_seconds is not None]
        if not known:
            return None
        top = max(known)
        return top if top > 0 else None

    def _cost_term(self, arm: DesignArm) -> float:
        if self._cost_scale is None:
            return 0.0
        if arm.cost_seconds is None:
            # 모르는 비용을 0 으로 두면 가장 싼 arm 으로 보인다. 관측된 최대치로
            # 취급해서, 모른다는 사실이 유리하게 작용하지 않게 한다.
            return 1.0
        return float(arm.cost_seconds) / self._cost_scale

    # ---- 다양성 (배치 안에서만. 누적 coverage 가 아니다) --------------------

    def _diversity_term(self, arm: DesignArm, selected: Iterable[str]) -> float:
        """이미 고른 것과 얼마나 겹치는가. 깊은 계층이 같을수록 큰 벌점.

        계층이 n 단계면 앞에서부터 d 단계가 같을 때 d/n 을 문다. n=2 면
        전부 같을 때 1.0, 첫 단계만 같을 때 0.5 다.

        **이것은 배치 안의 중복 벌점이지 portfolio coverage 가 아니다.**
        누적 coverage 는 Phase 4 의 별도 항이다.
        """
        selected = list(selected)
        if not selected:
            return 0.0
        depth = len(self.schema.hierarchy)
        penalty = 0.0
        for key in selected:
            penalty += arm.matched_depth(self.arms[key], self.schema) / depth
        return penalty / len(selected)

    # ---- 탐색 보너스 --------------------------------------------------------

    def exploration_bonus(self, arm_key: str) -> float:
        p = self.policy
        if p.eta_variation_exploration == 0.0 or p.reference_variation is None:
            return 0.0
        if self.arms[arm_key].dimensions.get(p.variation_key) == p.reference_variation:
            return 0.0
        return (p.eta_variation_exploration
                * self.model.allocation_signal(arm_key)
                * self.model.uncertainty(arm_key))

    # ---- 점수 ---------------------------------------------------------------

    def score_parts(self, arm_key: str, *, selected: Iterable[str] = ()) -> dict:
        """항별 기여. UI 의 "왜 이쪽인가" 가 이 값에서 만들어진다."""
        arm = self.arms[arm_key]
        p = self.policy
        return {
            "expected_utility": self.model.expected_utility(arm_key),
            "uncertainty": p.beta_uncertainty * self.model.uncertainty(arm_key),
            "diversity": -p.gamma_diversity * self._diversity_term(arm, selected),
            "cost": -p.lambda_cost * self._cost_term(arm),
            "variation_exploration": self.exploration_bonus(arm_key),
            "allocation_signal": self.model.allocation_signal(arm_key),
            "is_reference_variation":
                arm.dimensions.get(p.variation_key) == p.reference_variation,
        }

    def score(self, arm_key: str, *, selected: Iterable[str] = ()) -> float:
        arm = self.arms[arm_key]
        p = self.policy
        return (
            self.model.expected_utility(arm_key)
            + p.beta_uncertainty * self.model.uncertainty(arm_key)
            - p.gamma_diversity * self._diversity_term(arm, selected)
            - p.lambda_cost * self._cost_term(arm)
            + self.exploration_bonus(arm_key)
        )

    # ---- 배분 ---------------------------------------------------------------

    def allocate(self, *, budget: int) -> list[str]:
        """예산만큼 arm 을 고른다. 다양성 항 때문에 한 번에 하나씩 고른다."""
        if budget <= 0:
            return []
        picks: list[str] = []
        for _ in range(budget):
            best = max(
                self.arm_keys,
                # 동점은 arm 이름으로 깨서 seed 와 무관하게 결정적으로 만든다.
                key=lambda k: (self.score(k, selected=picks), k),
            )
            picks.append(best)
        return picks

    # ---- 다음 행동 ----------------------------------------------------------

    def next_action(self, unit: tuple[str, ...]) -> Decision:
        """이 단위에 다음 계산을 무엇으로 쓸지.

        순서가 중요하다. 관측이 얇으면 판정하지 않고 더 본다 - 2/2 에서 나온
        추정으로 단위를 버리면 되돌릴 수 없다.
        """
        p = self.policy
        state = self.model.unit_state(unit)
        names = p.action_names
        reasons = p.reason_templates
        if state["n_observed"] < p.min_observations:
            slot = "probe_more"
            why = reasons.get(slot, "").format(
                n_observed=state["n_observed"], min_observations=p.min_observations)
        elif state["allocation_signal"] < p.allocation_signal_floor:
            slot = "verify" if state["p_hat"] >= 0.5 else "abandon"
            why = reasons.get(slot, "")
        else:
            slot = "explore_variation"
            why = reasons.get(slot, "")
        action = names[slot]
        return Decision(action=action, reason=why, unit=unit, state=state)
