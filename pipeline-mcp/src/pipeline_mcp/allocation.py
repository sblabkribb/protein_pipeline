"""적응적 계산 할당 정책 (제품 런타임).

게이트 0 사전분포 -> 프로브 -> p_hat/불확실성 -> movability -> 다음 계산 선택.

왜 여기 있는가
--------------
이 정책은 지금까지 분석 코드로만 존재했고 (scripts/transcoder/rapid_sr/allocation.py),
파이프라인은 이것을 부르지 않았다. 그래서 "resource-aware" 를 만드는 부분이
제품에 없었다. 여기가 정본이고, rapid_sr 쪽은 논문 재현용 사본이다 - 두 사본의
일치는 테스트가 고정한다 (sequence_liabilities 와 같은 방식).

정책이 볼 수 있는 것
--------------------
새 타겟에서 실제로 지불할 수 있는 정보뿐이다. 게이트 0 사전분포와 `observe()`
로 들어온 실제 관측. 개발 데이터의 baseline yield 를 주입하는 경로는 없고,
`set_backbone_true_yield` 는 부르면 예외를 낸다. 그 값을 쓰면 "compute 를
아꼈다" 는 주장이 무너진다.

여기에 없는 것
--------------
비교용 기준 정책(Uniform/Random/StaticTopK)과 시뮬레이션·부트스트랩은 분석
전용이라 rapid_sr 에만 있다. 런타임은 결정만 내린다.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random


#: 타겟 사전분포를 말해주지 않았을 때 쓰는 값. 관측 전에는 아무 것도 모른다는
#: 뜻이고, strength 가 작아서 첫 관측이 바로 우세하다.
DEFAULT_PRIOR_MEAN = 0.5
DEFAULT_PRIOR_STRENGTH = 2.0

#: 판단을 내리기 전에 필요한 최소 probe 서열 수. 2/2 에서 나온 p_hat=1.0 으로
#: 백본을 판정하면 대부분 틀린다. 새 타겟에서 실제로 지불할 수 있는 크기이면서
#: 비율 추정이 의미를 갖기 시작하는 지점이다.
MIN_PROBE_SEQUENCES = 4

#: 이 아래면 조건을 바꿔도 배울 것이 거의 없다고 보고 탐색 예산을 주지 않는다.
#: movability = 4p(1-p) 이므로 0.2 는 p 가 약 0.05 또는 0.95 인 지점이다.
MOVABILITY_FLOOR = 0.2

#: 생성 조건 탐색 보너스의 기본 가중치. 조건을 바꿔봐야 알 수 있는 것에만 쓴다.
DEFAULT_ETA_CONDITION_EXPLORATION = 0.5

#: arm 이 타겟 사후분포를 사전분포로 받을 때의 세기. 크면 형제끼리 강하게
#: 묶이고(=풀링이 세고), 작으면 arm 이 독립에 가까워진다.
DEFAULT_POOLING_STRENGTH = 4.0


@dataclass
class BetaPosterior:
    """이항 관측에 대한 켤레 사후분포."""

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

    def copy(self) -> "BetaPosterior":
        return BetaPosterior(alpha=self.alpha, beta=self.beta)


def movability(p: float) -> float:
    """이 백본의 yield 가 조건을 바꿨을 때 움직일 수 있는 여지. 0..1.

    `4·p(1-p)` 는 베르누이 분산을 최대값 0.25 로 나눈 것이다. p=0.5 에서 1,
    p=0 이나 1 에서 0 이 된다.

    왜 이것이 필요한가. 1 차 온도 패널의 15 개 백본 중 12 개가 모든 온도에서
    yield 0.000 또는 1.000 이었다. 그 백본에서 온도를 비교하는 것은 정보가
    0 이다 - 조건이 무엇이든 결과가 같은 값에 붙어 있기 때문이다. 그런데도
    예산의 80% 가 거기로 갔다. movability 는 그 낭비를 점수 안에서 막는다.
    """
    p = min(max(float(p), 0.0), 1.0)
    return 4.0 * p * (1.0 - p)


@dataclass(frozen=True)
class Arm:
    """배분의 결정 단위: 이 백본을 이 생성 조건으로 만들어 평가할 것인가."""

    target_id: str
    backbone_id: str
    condition: str
    #: 이 arm 을 한 번 평가하는 비용(초). 측정하지 않았으면 None - 0 이 아니다.
    cost_seconds: float | None = None

    @property
    def key(self) -> str:
        return f"{self.target_id}|{self.backbone_id}|{self.condition}"


class _Policy:
    """모든 정책의 공용 인터페이스. 같은 예산으로 비교하려면 같은 모양이어야 한다."""

    def __init__(self, arms, *, seed: int = 0) -> None:
        self.arms = {arm.key: arm for arm in arms}
        if not self.arms:
            raise ValueError("정책에는 arm 이 최소 하나 필요하다")
        self.arm_keys = list(self.arms)
        self.rng = random.Random(seed)
        self.counts = {key: 0 for key in self.arm_keys}

    def allocate(self, *, budget: int) -> list[str]:
        raise NotImplementedError

    def observe(self, arm_key: str, *, successes: int, trials: int) -> None:
        if arm_key not in self.arms:
            raise KeyError(f"등록되지 않은 arm: {arm_key}")
        self.counts[arm_key] += int(trials)



class HierarchicalAllocator(_Policy):
    """RAPID 적응 정책.

        A(b,g) = p̂ + β·U − λ·C − γ·D

    p̂ 는 부분 풀링된 사후평균, U 는 사후 표준편차(탐색 보너스), C 는 정규화된
    비용, D 는 이미 고른 것과의 중복이다. 부호를 눈으로 확인할 수 있게 항을
    따로 계산한다.
    """

    def __init__(
        self,
        arms,
        *,
        seed: int = 0,
        prior_mean: float = DEFAULT_PRIOR_MEAN,
        prior_strength: float = DEFAULT_PRIOR_STRENGTH,
        pooling_strength: float = DEFAULT_POOLING_STRENGTH,
        beta_uncertainty: float = 0.5,
        gamma_diversity: float = 0.2,
        lambda_cost: float = 0.1,
        eta_condition_exploration: float = DEFAULT_ETA_CONDITION_EXPLORATION,
        reference_condition: str | None = None,
    ) -> None:
        super().__init__(arms, seed=seed)
        self.pooling_strength = float(pooling_strength)
        self.beta_uncertainty = float(beta_uncertainty)
        self.gamma_diversity = float(gamma_diversity)
        self.lambda_cost = float(lambda_cost)
        self.eta_condition_exploration = float(eta_condition_exploration)
        #: 생산 기본 조건. 이것과 다른 조건을 쓰는 arm 만 '조건 탐색' 이다.
        #: 지정하지 않으면 조건 탐색이라는 개념 자체가 없으므로 항이 꺼진다.
        self.reference_condition = reference_condition
        self._by_backbone: dict[tuple[str, str], list[str]] = {}
        for key, arm in self.arms.items():
            self._by_backbone.setdefault((arm.target_id, arm.backbone_id), []).append(key)

        self._targets = {
            arm.target_id: BetaPosterior.from_prior(mean=prior_mean, strength=prior_strength)
            for arm in self.arms.values()
        }
        #: arm 자신의 관측만 담는다. 사전분포는 조회 시점에 타겟에서 가져온다 -
        #: 그래야 나중에 도착한 형제의 관측이 이 arm 에도 반영된다.
        self._observed = {key: (0, 0) for key in self.arm_keys}
        self._cost_scale = self._build_cost_scale()

    # ---- 사전분포 -----------------------------------------------------------

    def set_target_prior(self, target_id: str, *, mean: float, strength: float) -> None:
        """게이트 0 점수를 타겟 사전분포로 넣는다.

        하드 컷이 아니다. 타겟 수준 AUC 0.725 는 순위를 매기기에는 쓸 만하지만
        후보를 잘라내기에는 부족하고, 잘라낸 것은 되돌릴 수 없다.
        """
        if target_id not in self._targets:
            raise KeyError(f"등록되지 않은 타겟: {target_id}")
        self._targets[target_id] = BetaPosterior.from_prior(mean=mean, strength=strength)

    # ---- 관측 ---------------------------------------------------------------

    def observe(self, arm_key: str, *, successes: int, trials: int) -> None:
        super().observe(arm_key, successes=successes, trials=trials)
        successes, trials = int(successes), int(trials)
        if successes > trials:
            raise ValueError(f"successes({successes}) 가 trials({trials}) 보다 클 수 없다")
        if trials == 0:
            return
        seen_s, seen_n = self._observed[arm_key]
        self._observed[arm_key] = (seen_s + successes, seen_n + trials)
        # 같은 관측이 타겟 수준도 갱신한다. 이것이 형제 arm 으로 정보가 흐르는
        # 유일한 통로다.
        self._targets[self.arms[arm_key].target_id].update(successes=successes, trials=trials)

    # ---- 사후분포 -----------------------------------------------------------

    def posterior(self, arm_key: str) -> BetaPosterior:
        arm = self.arms[arm_key]
        target = self._targets[arm.target_id]
        successes, trials = self._observed[arm_key]
        # arm 사전분포 = 타겟 사후평균을 pooling_strength 만큼의 가상 관측으로.
        # 세기를 고정하므로 타겟이 아무리 많이 관측돼도 arm 자신의 데이터를
        # 압도하지 못한다.
        post = BetaPosterior.from_prior(mean=target.mean, strength=self.pooling_strength)
        post.update(successes=successes, trials=trials)
        return post

    def posterior_mean(self, arm_key: str) -> float:
        return self.posterior(arm_key).mean

    def backbone_posterior(self, arm_key: str) -> BetaPosterior:
        """이 백본의 모든 조건을 합친 사후분포.

        조건 하나에서 우연히 0/8 이 나왔다고 백본이 바닥이라고 판단하면, 그
        백본은 다시는 탐색되지 않는다. movability 는 백본 수준에서 잰다.
        """
        arm = self.arms[arm_key]
        siblings = self._by_backbone[(arm.target_id, arm.backbone_id)]
        successes = sum(self._observed[key][0] for key in siblings)
        trials = sum(self._observed[key][1] for key in siblings)
        target = self._targets[arm.target_id]
        post = BetaPosterior.from_prior(mean=target.mean, strength=self.pooling_strength)
        post.update(successes=successes, trials=trials)
        return post

    def probe_state(self, target_id: str, backbone_id: str) -> dict:
        """이 백본에 대해 **지금까지 관측한 것만으로** 아는 상태.

        개발 데이터에는 백본마다 56 서열까지 돌린 baseline yield 가 있지만, 새
        타겟에는 그것이 없다. 정책이 그 값을 쓰면 "compute 를 아꼈다" 는 주장이
        무너진다. 그래서 여기서 나오는 p_hat 은 Gate 0 사전분포와 실제 probe
        관측에서만 온다.
        """
        keys = self._by_backbone.get((target_id, backbone_id))
        if keys is None:
            raise KeyError(f"등록되지 않은 백본: {target_id}|{backbone_id}")
        successes = sum(self._observed[key][0] for key in keys)
        trials = sum(self._observed[key][1] for key in keys)
        post = self.backbone_posterior(keys[0])
        return {
            "target_id": target_id,
            "backbone_id": backbone_id,
            "n_observed": trials,
            "n_successes": successes,
            "p_hat": round(post.mean, 4),
            "uncertainty": round(post.sd, 4),
            "movability": round(movability(post.mean), 4),
            "source": "probe" if trials else "prior_only",
            "information_used": ["gate0_prior", "observed_probes"],
        }

    def set_backbone_true_yield(self, *args, **kwargs):
        """존재하지 않는다. 이 이름으로 부르는 것 자체가 설계 위반이다.

        개발 데이터의 baseline yield 를 정책에 주입하면 새 타겟에서는 쓸 수 없는
        정보로 결정을 내리게 된다. 정책은 `observe` 로 들어온 관측만 본다.
        """
        raise TypeError(
            "정책에 참값 yield 를 주입할 수 없다. 새 타겟에서 쓸 수 있는 것은 "
            "Gate 0 사전분포와 실제 probe 관측뿐이므로 observe() 를 쓴다."
        )

    def next_action(self, target_id: str, backbone_id: str) -> dict:
        """이 백본에 다음 계산을 무엇으로 쓸지. probe 상태만 보고 정한다.

            Gate 0 prior -> 초기 probe -> p_hat, uncertainty
            -> movability -> 다음 계산 선택

        순서가 중요하다. probe 가 얇으면 판정하지 않고 서열을 더 뽑는다 - 2/2 에서
        나온 p_hat 으로 백본을 버리면 되돌릴 수 없다.
        """
        state = self.probe_state(target_id, backbone_id)
        if state["n_observed"] < MIN_PROBE_SEQUENCES:
            action, why = ("probe_more_sequences",
                           f"관측 {state['n_observed']} 개는 판정하기에 얇다 "
                           f"(최소 {MIN_PROBE_SEQUENCES}).")
        elif state["movability"] < MOVABILITY_FLOOR:
            if state["p_hat"] >= 0.5:
                action, why = ("verify_with_af2",
                               "이미 높은 수율에 붙어 있다. 조건을 바꿔 배울 것이 없다.")
            else:
                action, why = ("abandon_backbone",
                               "바닥에 붙어 있다. 조건을 바꿔도 움직일 여지가 없다.")
        else:
            action, why = ("explore_generation_condition",
                           "중간 수율이라 조건을 바꾸면 결과가 움직일 수 있다.")
        return {**state, "action": action, "reason": why,
                "movability_floor": MOVABILITY_FLOOR,
                "min_probe_sequences": MIN_PROBE_SEQUENCES}

    def exploration_bonus(self, arm_key: str) -> float:
        """조건을 바꿔보는 데 쓰는 값어치.

        기준 조건은 탐색이 아니므로 0 이다. 그 외에는 백본이 움직일 수 있는
        여지(movability)와 이 조건에 대한 불확실성의 곱이다. 둘 중 하나라도
        0 이면 배울 것이 없다.
        """
        if self.eta_condition_exploration == 0.0 or self.reference_condition is None:
            return 0.0
        if self.arms[arm_key].condition == self.reference_condition:
            return 0.0
        return (
            self.eta_condition_exploration
            * movability(self.backbone_posterior(arm_key).mean)
            * self.posterior(arm_key).sd
        )

    def score_parts(self, arm_key: str, *, selected=()) -> dict:
        """점수를 항별로 돌려준다. 왜 이 arm 에 예산을 썼는지 설명하기 위해서다."""
        arm = self.arms[arm_key]
        post = self.posterior(arm_key)
        return {
            "posterior_mean": post.mean,
            "uncertainty": self.beta_uncertainty * post.sd,
            "diversity": -self.gamma_diversity * self._diversity_term(arm, selected),
            "cost": -self.lambda_cost * self._cost_term(arm),
            "condition_exploration": self.exploration_bonus(arm_key),
            "movability": movability(self.backbone_posterior(arm_key).mean),
            "is_reference_condition": arm.condition == self.reference_condition,
        }

    # ---- 점수 ---------------------------------------------------------------

    def _build_cost_scale(self) -> float | None:
        """비용을 0..1 로 정규화할 기준. 아무도 비용을 모르면 None (비용항 끔)."""
        known = [a.cost_seconds for a in self.arms.values() if a.cost_seconds is not None]
        if not known:
            return None
        top = max(known)
        return top if top > 0 else None

    def _cost_term(self, arm: Arm) -> float:
        if self._cost_scale is None:
            return 0.0
        if arm.cost_seconds is None:
            # 모르는 비용을 0 으로 두면 가장 싼 arm 으로 보인다. 관측된 최대치로
            # 취급해서, 모른다는 사실이 유리하게 작용하지 않게 한다.
            return 1.0
        return float(arm.cost_seconds) / self._cost_scale

    def _diversity_term(self, arm: Arm, selected) -> float:
        """이미 고른 것과 얼마나 겹치는가. 같은 백본 > 같은 타겟 순으로 벌점."""
        if not selected:
            return 0.0
        penalty = 0.0
        for key in selected:
            other = self.arms[key]
            if other.backbone_id == arm.backbone_id and other.target_id == arm.target_id:
                penalty += 1.0
            elif other.target_id == arm.target_id:
                penalty += 0.5
        return penalty / len(selected)

    def score(self, arm_key: str, *, selected=()) -> float:
        arm = self.arms[arm_key]
        post = self.posterior(arm_key)
        return (
            post.mean
            + self.beta_uncertainty * post.sd
            - self.gamma_diversity * self._diversity_term(arm, selected)
            - self.lambda_cost * self._cost_term(arm)
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




def allocation_next_action(arguments: dict) -> dict:
    """MCP 도구 진입점. 사전분포와 관측만 받아 백본마다 다음 행동을 돌려준다.

    참값 yield 를 받는 인자는 없다. 새 타겟에서 쓸 수 없는 정보로 결정하면
    절감 주장이 성립하지 않으므로, 입력은 게이트 0 사전분포와 실제 관측뿐이다.
    """
    target_id = str(arguments.get("target_id") or "").strip()
    backbones = [str(b) for b in (arguments.get("backbones") or []) if str(b).strip()]
    if not target_id:
        return {"error": "target_id is required"}
    if not backbones:
        return {"error": "backbones must be a non-empty list"}

    conditions = [str(c) for c in (arguments.get("conditions") or []) if str(c).strip()]
    conditions = conditions or ["T0.1"]

    arms = [
        Arm(target_id=target_id, backbone_id=backbone, condition=condition)
        for backbone in backbones
        for condition in conditions
    ]
    allocator = HierarchicalAllocator(arms, seed=0)

    prior_mean = arguments.get("prior_mean")
    if prior_mean is not None:
        allocator.set_target_prior(
            target_id,
            mean=float(prior_mean),
            strength=float(arguments.get("prior_strength") or DEFAULT_PRIOR_STRENGTH),
        )

    applied, ignored = [], []
    for item in arguments.get("observations") or []:
        backbone = str(item.get("backbone_id") or "")
        condition = str(item.get("condition") or conditions[0])
        key = f"{target_id}|{backbone}|{condition}"
        if key not in allocator.arms:
            ignored.append({"backbone_id": backbone, "condition": condition,
                            "why": "등록되지 않은 백본/조건"})
            continue
        trials = int(item.get("trials") or 0)
        successes = int(item.get("successes") or 0)
        if successes > trials:
            return {"error": f"successes {successes} > trials {trials} for {key}"}
        allocator.observe(key, successes=successes, trials=trials)
        applied.append({"backbone_id": backbone, "condition": condition,
                        "trials": trials, "successes": successes})

    actions = [allocator.next_action(target_id, backbone) for backbone in backbones]
    counts: dict[str, int] = {}
    for action in actions:
        counts[action["action"]] = counts.get(action["action"], 0) + 1

    return {
        "target_id": target_id,
        "prior": {
            "mean": float(prior_mean) if prior_mean is not None else DEFAULT_PRIOR_MEAN,
            "strength": float(arguments.get("prior_strength")
                              or DEFAULT_PRIOR_STRENGTH),
            "source": "gate0" if prior_mean is not None else "uninformative_default",
        },
        "conditions": conditions,
        "observations_applied": applied,
        "observations_ignored": ignored,
        "actions": actions,
        "summary": counts,
        "policy": {
            "rule": "gate0 prior -> probe -> p_hat/uncertainty -> movability -> action",
            "movability": "4p(1-p)",
            "movability_floor": MOVABILITY_FLOOR,
            "min_probe_sequences": MIN_PROBE_SEQUENCES,
            "pooling": "backbones under one target share the target posterior as prior",
            "information_used": ["gate0_prior", "observed_probes"],
            "information_not_used": ["baseline yield (새 타겟에 없다)"],
        },
    }
