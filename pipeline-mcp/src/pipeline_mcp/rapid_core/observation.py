"""관측으로 arm 상태를 갱신하는 모형. objective 마다 다를 수 있다.

Core 는 이 인터페이스만 본다. 어떤 분포를 쓰는지, 어떻게 풀링하는지는 profile
이 고른다. v1 은 이진 결과에 대한 Beta-Bernoulli + 계층 부분 풀링이다.

`allocation_signal` 을 information gain 이라고 부르지 않는다. v1 의 신호는
`4p(1-p)` 이고 관측 수에 무관하다 - 2/4 와 200/400 이 같은 값이다. 정보량이라면
그럴 수 없다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Protocol

from .arm import ArmSchema, DesignArm


@dataclass
class BetaPosterior:
    """이항 관측에 대한 켤레 사후분포.

    frozen v1 (`pipeline_mcp.allocation.BetaPosterior`) 과 **연산 순서까지**
    같아야 한다. 같은 식을 다른 순서로 쓰면 IEEE754 에서 마지막 자리가
    갈라지고, 그러면 환원 테스트가 tolerance 를 넓혀야 통과한다 - 그것은
    환원이 아니다.
    """

    alpha: float
    beta: float

    @classmethod
    def from_prior(cls, *, mean: float, strength: float) -> "BetaPosterior":
        if not 0.0 < mean < 1.0:
            raise ValueError(f"prior mean 은 0 과 1 사이여야 한다: {mean}")
        if strength <= 0:
            raise ValueError(f"prior strength 는 양수여야 한다: {strength}")
        return cls(alpha=mean * strength, beta=(1.0 - mean) * strength)

    def update(self, *, successes: int, trials: int) -> None:
        successes, trials = int(successes), int(trials)
        if trials < 0 or successes < 0:
            raise ValueError("successes 와 trials 는 음수일 수 없다")
        if successes > trials:
            raise ValueError(f"successes({successes}) 가 trials({trials}) 보다 클 수 없다")
        if trials == 0:
            return
        self.alpha += successes
        self.beta += trials - successes

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def sd(self) -> float:
        total = self.alpha + self.beta
        return math.sqrt(self.alpha * self.beta / (total * total * (total + 1.0)))


def scaled_variance_signal(p: float) -> float:
    """`4p(1-p)`. 베르누이 분산을 최대값 0.25 로 나눈 것.

    p=0.5 에서 1, p=0 이나 1 에서 0. 결과가 한쪽 끝에 붙어 있는 arm 은 조건을
    바꿔도 움직일 여지가 없다는 뜻이다.
    """
    p = min(max(float(p), 0.0), 1.0)
    return 4.0 * p * (1.0 - p)


class ObservationModel(Protocol):
    """Core 가 요구하는 것. 분포도 풀링도 여기 뒤에 숨는다."""

    def observe(self, arm_key: str, *, successes: int, trials: int) -> None: ...
    def expected_utility(self, arm_key: str) -> float: ...
    def uncertainty(self, arm_key: str) -> float: ...
    def allocation_signal(self, arm_key: str) -> float: ...
    def unit_state(self, unit: tuple[str, ...]) -> dict: ...


class BetaBernoulliModel:
    """이진 결과 + 계층 부분 풀링. v1 이 쓰는 모형.

    풀링 통로는 하나다: 어떤 arm 의 관측이든 hierarchy[0] 수준 사후분포를
    갱신하고, 그것이 모든 형제 arm 의 사전분포가 된다. 세기를 고정하므로
    상위 수준이 아무리 많이 관측돼도 arm 자신의 데이터를 압도하지 못한다.
    """

    def __init__(self, arms: Mapping[str, DesignArm], schema: ArmSchema, *,
                 prior_mean: float, prior_strength: float,
                 pooling_strength: float) -> None:
        self.arms = dict(arms)
        self.schema = schema
        self.pooling_strength = float(pooling_strength)
        self._observed: dict[str, tuple[int, int]] = {k: (0, 0) for k in self.arms}
        self._groups: dict[tuple[str, ...], BetaPosterior] = {}
        self._by_unit: dict[tuple[str, ...], list[str]] = {}
        for key, arm in self.arms.items():
            self._groups.setdefault(
                arm.group(schema, 1),
                BetaPosterior.from_prior(mean=prior_mean, strength=prior_strength))
            self._by_unit.setdefault(arm.group(schema), []).append(key)

    # ---- 사전분포 주입 ----------------------------------------------------

    def set_group_prior(self, group: tuple[str, ...], *, mean: float,
                        strength: float) -> None:
        if group not in self._groups:
            raise KeyError(f"등록되지 않은 그룹: {group}")
        self._groups[group] = BetaPosterior.from_prior(mean=mean, strength=strength)

    def set_true_yield(self, *args, **kwargs):
        """존재하지 않는다. 이 이름으로 부르는 것 자체가 설계 위반이다."""
        raise TypeError(
            "정책에 참값을 주입할 수 없다. 새 타겟에서 쓸 수 있는 것은 사전분포와 "
            "실제 관측뿐이므로 observe() 를 쓴다.")

    # ---- 관측 --------------------------------------------------------------

    def observe(self, arm_key: str, *, successes: int, trials: int) -> None:
        if arm_key not in self.arms:
            raise KeyError(f"등록되지 않은 arm: {arm_key}")
        successes, trials = int(successes), int(trials)
        if successes > trials:
            raise ValueError(f"successes({successes}) 가 trials({trials}) 보다 클 수 없다")
        if trials == 0:
            return
        seen_s, seen_n = self._observed[arm_key]
        self._observed[arm_key] = (seen_s + successes, seen_n + trials)
        group = self.arms[arm_key].group(self.schema, 1)
        self._groups[group].update(successes=successes, trials=trials)

    # ---- 사후분포 -----------------------------------------------------------

    def posterior(self, arm_key: str) -> BetaPosterior:
        arm = self.arms[arm_key]
        group = self._groups[arm.group(self.schema, 1)]
        successes, trials = self._observed[arm_key]
        post = BetaPosterior.from_prior(mean=group.mean, strength=self.pooling_strength)
        post.update(successes=successes, trials=trials)
        return post

    def unit_posterior(self, arm_key: str) -> BetaPosterior:
        """이 판정 단위의 모든 variation 을 합친 사후분포.

        variation 하나에서 우연히 0/8 이 나왔다고 단위 전체가 바닥이라고
        판단하면 그 단위는 다시 탐색되지 않는다.
        """
        arm = self.arms[arm_key]
        siblings = self._by_unit[arm.group(self.schema)]
        successes = sum(self._observed[key][0] for key in siblings)
        trials = sum(self._observed[key][1] for key in siblings)
        group = self._groups[arm.group(self.schema, 1)]
        post = BetaPosterior.from_prior(mean=group.mean, strength=self.pooling_strength)
        post.update(successes=successes, trials=trials)
        return post

    # ---- Core 가 보는 면 ----------------------------------------------------

    def expected_utility(self, arm_key: str) -> float:
        return self.posterior(arm_key).mean

    def uncertainty(self, arm_key: str) -> float:
        return self.posterior(arm_key).sd

    def allocation_signal(self, arm_key: str) -> float:
        return scaled_variance_signal(self.unit_posterior(arm_key).mean)

    def unit_state(self, unit: tuple[str, ...]) -> dict:
        keys = self._by_unit.get(unit)
        if keys is None:
            raise KeyError(f"등록되지 않은 단위: {unit}")
        successes = sum(self._observed[k][0] for k in keys)
        trials = sum(self._observed[k][1] for k in keys)
        post = self.unit_posterior(keys[0])
        return {
            "unit": unit,
            "n_observed": trials,
            "n_successes": successes,
            "p_hat": round(post.mean, 4),
            "uncertainty": round(post.sd, 4),
            "allocation_signal": round(scaled_variance_signal(post.mean), 4),
            "source": "observed" if trials else "prior_only",
        }
