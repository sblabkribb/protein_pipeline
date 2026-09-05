"""적응적 예산 배분.

RAPID 가 논문에서 하려는 주장은 "같은 AF2 예산에서 더 많은 통과 후보를
얻는다" 이다. 그 주장을 검사 가능하게 만들려면 배분을 정책으로 명시하고,
같은 예산을 쓰는 대조 정책과 나란히 돌려야 한다. 이 모듈은 그 네 정책과
공용 시뮬레이터를 담는다.

왜 계층인가
-----------
결정 단위를 (backbone, generation condition) 으로 두면 arm 수가 금방 는다.
백본 5개 x 온도 4개 = 20 arm 인데 AF2 예산이 50 콜이면 arm 당 2.5 관측이다.
평평한 20-arm 밴딧의 사후분포는 그 정도로는 움직이지 않는다 - 관측을 다
쓰고도 사전분포와 구별이 안 되는 결과가 나온다.

그래서 arm 을 독립으로 두지 않고 **같은 타겟 안에서 정보를 나눈다**. 타겟
수준 사후분포가 그 타겟의 모든 arm 을 갱신하고, arm 은 그것을 사전분포로
받는다. 한 arm 의 8 관측이 형제 arm 도 움직이므로 예산이 적어도 신호가 쌓인다.
게이트 0 의 인코더 점수는 여기서 타겟 사전분포로 들어간다 - 하드 컷이 아니라
사전분포다. 0.725 AUC 는 순위를 매기기에는 쓸 만하고 잘라내기에는 부족하다.

무엇을 하지 않는가
------------------
* 라벨을 지어내지 않는다. 관측하지 않은 arm 은 사전분포 그대로다.
* 비용을 모르는 arm 을 공짜로 취급하지 않는다. 0 으로 두면 측정하지 않은
  스테이지가 가장 싸 보여서 예산이 그쪽으로 쏠린다.
* 무작위성을 숨기지 않는다. 모든 정책이 seed 를 받고 결정적이다.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import statistics

#: 타겟 사전분포를 말해주지 않았을 때 쓰는 값. 관측 전에는 아무 것도 모른다는
#: 뜻이고, strength 가 작아서 첫 관측이 바로 우세하다.
DEFAULT_PRIOR_MEAN = 0.5
DEFAULT_PRIOR_STRENGTH = 2.0

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


class UniformPolicy(_Policy):
    """예산을 arm 에 고르게 돌린다. 관측을 보지 않는다.

    커서를 호출 사이에 유지한다. 예산은 배치로 쪼개져 들어오는데 매 배치마다
    목록 처음으로 돌아가면 앞쪽 arm 만 반복해서 뽑힌다 - 그건 uniform 이 아니라
    "arm 순서 상위 K" 이고, arm 순서가 우연히 좋은 타겟부터면 대조군이 부당하게
    강해진다.
    """

    def __init__(self, arms, *, seed: int = 0) -> None:
        super().__init__(arms, seed=seed)
        self._cursor = 0

    def allocate(self, *, budget: int) -> list[str]:
        if budget <= 0:
            return []
        picks = []
        for _ in range(budget):
            picks.append(self.arm_keys[self._cursor % len(self.arm_keys)])
            self._cursor += 1
        return picks


class RandomPolicy(_Policy):
    """복원추출. 아무 구조도 쓰지 않는 하한선."""

    def allocate(self, *, budget: int) -> list[str]:
        if budget <= 0:
            return []
        return [self.rng.choice(self.arm_keys) for _ in range(budget)]


class StaticTopKPolicy(_Policy):
    """대리모형 점수 상위 k 를 한 번 고르고 끝. 관측이 와도 바꾸지 않는다.

    이것이 RAPID 가 넘어야 할 진짜 상대다. 게이트 0 점수만으로 상위를 고르는
    것과, 그 위에 관측 기반 재배분을 얹는 것의 차이가 곧 적응성의 값어치다.

    예산이 k 보다 크면 상위 k 안에서 **반복**한다. 랭킹을 내려가며 배치를 채우면
    배치가 커질수록 나쁜 arm 을 집게 되는데, 그건 대조군이 원래 약한 것이 아니라
    구현이 대조군을 약하게 만든 것이다.
    """

    def __init__(
        self, arms, *, scores: dict[str, float], k: int | None = None, seed: int = 0,
    ) -> None:
        super().__init__(arms, seed=seed)
        missing = [key for key in self.arm_keys if key not in scores]
        if missing:
            raise ValueError(f"대리모형 점수가 없는 arm: {missing}")
        self.scores = dict(scores)
        self.k = len(self.arm_keys) if k is None else int(k)
        if self.k <= 0:
            raise ValueError(f"k 는 양수여야 한다: {k}")
        self.k = min(self.k, len(self.arm_keys))
        # 동점은 arm 이름으로 깨서 결정적으로 만든다.
        self.selected = sorted(self.arm_keys, key=lambda key: (-self.scores[key], key))[: self.k]
        self._cursor = 0

    def allocate(self, *, budget: int) -> list[str]:
        if budget <= 0:
            return []
        picks = []
        for _ in range(budget):
            picks.append(self.selected[self._cursor % len(self.selected)])
            self._cursor += 1
        return picks


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


def surrogate_with_auc(labels: dict[str, int], *, auc: float, seed: int = 0) -> dict[str, float]:
    """주어진 AUC 를 갖는 대리모형 점수를 만든다.

    대조군에 완벽한 대리모형을 주면 적응 정책은 원리적으로 못 이기고, 비교는
    무의미해진다. 우리가 실제로 가진 것은 타겟 수준 AUC 0.725 (95% CI
    0.709-0.740) 짜리 인코더이지 오라클이 아니다.

    구성: 양성/음성 각각에 정규분포 점수를 주되 평균 차이를 원하는 AUC 에서
    역산한다. 이항 정규 모형에서 AUC = Phi(d / sqrt(2)) 이므로
    d = sqrt(2) * Phi^-1(AUC) 다.
    """
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"auc 는 0 과 1 사이여야 한다: {auc}")
    separation = math.sqrt(2.0) * _probit(min(max(auc, 1e-6), 1 - 1e-6))
    rng = random.Random(seed)
    return {
        key: rng.gauss(separation if labels[key] else 0.0, 1.0)
        for key in sorted(labels)
    }


def _probit(p: float) -> float:
    """표준정규 분위수. 이분법으로 충분히 정확하고 의존성이 없다."""
    low, high = -12.0, 12.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0))) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _target_aggregated(arms, surrogate: dict[str, float]) -> dict[str, float]:
    """arm 점수를 그 arm 이 속한 타겟의 평균으로 바꾼다.

    타겟 안에서 평균을 내면 arm 단위 잡음이 줄어든다. 그 이득은 적응성과 무관한
    전처리 효과이므로, 두 정책 모두에게 주거나 둘 다에게 주지 않아야 한다.
    """
    by_target: dict[str, list[float]] = {}
    for arm in arms:
        by_target.setdefault(arm.target_id, []).append(surrogate[arm.key])
    means = {target: statistics.fmean(values) for target, values in by_target.items()}
    return {arm.key: means[arm.target_id] for arm in arms}


def _adaptive_with_prior(arms, *, seed, surrogate, strength):
    """게이트 0 점수를 타겟 사전분포로 넣은 적응 정책.

    대리모형 점수는 임의 척도라서 확률이 아니다. 타겟 안에서 평균을 낸 뒤 전체
    타겟에 대한 순위를 0.1..0.9 로 늘려 사전평균으로 쓴다. 순위만 쓰는 이유는
    점수의 절대값이 통과율과 같은 단위가 아니기 때문이다 - 절대값을 확률로
    읽으면 근거 없는 정밀도를 주장하게 된다.
    """
    allocator = HierarchicalAllocator(arms, seed=seed)
    if not surrogate:
        return allocator
    by_target: dict[str, list[float]] = {}
    for arm in arms:
        by_target.setdefault(arm.target_id, []).append(surrogate[arm.key])
    means = {target: statistics.fmean(values) for target, values in by_target.items()}
    order = sorted(means, key=lambda target: (means[target], target))
    n = len(order)
    for rank, target in enumerate(order):
        prior = 0.1 + 0.8 * (rank / max(1, n - 1)) if n > 1 else 0.5
        allocator.set_target_prior(target, mean=prior, strength=strength)
    return allocator


def _bootstrap_ci(values, *, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        means.append(statistics.fmean(values[rng.randrange(n)] for _ in range(n)))
    means.sort()
    return (round(means[int(0.025 * n_boot)], 4), round(means[int(0.975 * n_boot) - 1], 4))


def simulate(
    arms,
    *,
    truth: dict[str, float],
    budget: int,
    batch_size: int,
    seed: int = 0,
    repeats: int = 1,
    surrogate_scores: dict[str, float] | None = None,
    surrogate_auc: float | None = None,
    measured_surrogate_scores: dict[str, float] | None = None,
    static_k_grid=None,
    success_threshold: float = 0.5,
    use_gate0_prior: bool = True,
    gate0_prior_strength: float = 4.0,
) -> dict:
    """네 정책을 같은 예산으로 돌려 비교한다.

    `truth` 는 arm 별 실제 성공 확률이다. 이것은 **시뮬레이션 전용**이며 실제
    실행에서는 존재하지 않는다. 여기서 라벨을 뽑아 쓰는 것은 정책의 성질을
    보기 위한 것이지, 성능을 주장하기 위한 것이 아니다.

    적응 정책은 `batch_size` 만큼 배분하고 관측한 뒤 다시 배분한다. 배치가
    없으면 적응할 기회가 없다 - 그건 static 정책이다.

    static top-K 의 k 는 자유 파라미터다. 하나를 골라 두면 그 값에 따라 대조군이
    임의로 약해지거나 강해진다. 그래서 k 를 훑고, 그 중 **사후적으로 가장 좋았던**
    k 를 `*_best` 로 함께 보고한다. 사후 선택은 대조군에 유리한 반칙이지만, 그
    반칙을 주고도 적응 정책이 이긴다면 주장은 그만큼 단단해진다.
    """
    missing = [arm.key for arm in arms if arm.key not in truth]
    if missing:
        raise ValueError(f"truth 에 없는 arm: {missing}")
    if batch_size <= 0:
        raise ValueError("batch_size 는 양수여야 한다")

    # 오라클 대리모형: 상한선이지 현실이 아니다. 이것만 대조군으로 두면 적응
    # 정책은 원리적으로 못 이긴다.
    oracle_surrogate = surrogate_scores or {arm.key: truth[arm.key] for arm in arms}
    # 실측 수준 대리모형: 게이트 0 의 타겟 수준 AUC 로 만든 것. 우리가 실제로
    # 가진 대조군은 이쪽이다.
    labels = {arm.key: int(truth[arm.key] >= success_threshold) for arm in arms}
    measured_surrogate = None
    target_agg_surrogate = None
    if measured_surrogate_scores is not None:
        # 실제 out-of-fold 예측. 합성 AUC 가정을 쓰지 않는다.
        missing = [arm.key for arm in arms if arm.key not in measured_surrogate_scores]
        if missing:
            raise ValueError(f"대리모형 점수가 없는 arm: {missing[:5]}")
        measured_surrogate = dict(measured_surrogate_scores)
    elif surrogate_auc is not None and 0 < sum(labels.values()) < len(labels):
        measured_surrogate = surrogate_with_auc(labels, auc=surrogate_auc, seed=seed)
    if measured_surrogate is not None:
        # 적응 정책의 사전분포와 **똑같은** 신호를 static 대조군에도 준다. 그래야
        # 남는 차이가 온라인 갱신에서 온 것이라고 말할 수 있다.
        target_agg_surrogate = _target_aggregated(arms, measured_surrogate)

    n_arms = len(arms)
    if static_k_grid is None:
        grid = sorted({max(1, round(fraction * n_arms)) for fraction in (0.1, 0.25, 0.5, 1.0)})
    else:
        grid = sorted({max(1, min(int(k), n_arms)) for k in static_k_grid})

    per_repeat: dict[str, list[int]] = {}
    totals: dict[str, dict] = {}

    for repeat in range(repeats):
        # 공통 난수. arm 별로 라벨을 미리 정해두면, 어떤 정책이 그 arm 을 k 번째로
        # 뽑든 같은 라벨을 받는다. 정책마다 별도 난수열을 쓰면 배분의 차이와 운의
        # 차이가 섞여서, 짝비교 CI 가 실제보다 넓어진다.
        labels = {}
        for index, arm in enumerate(arms):
            stream = random.Random((seed * 1000003 + repeat * 7919 + index))
            labels[arm.key] = [1 if stream.random() < truth[arm.key] else 0
                               for _ in range(budget)]
        builders = {
            "uniform": lambda s: UniformPolicy(arms, seed=s),
            "random": lambda s: RandomPolicy(arms, seed=s),
            "rapid_adaptive": lambda s: _adaptive_with_prior(
                arms, seed=s,
                surrogate=(measured_surrogate or oracle_surrogate) if use_gate0_prior else None,
                strength=gate0_prior_strength,
            ),
        }
        for k in grid:
            builders[f"static_topk_oracle_k{k}"] = (
                lambda s, k=k: StaticTopKPolicy(arms, scores=oracle_surrogate, k=k, seed=s)
            )
            if measured_surrogate is not None:
                builders[f"static_topk_measured_auc_k{k}"] = (
                    lambda s, k=k: StaticTopKPolicy(arms, scores=measured_surrogate, k=k, seed=s)
                )
                builders[f"static_topk_target_agg_k{k}"] = (
                    lambda s, k=k: StaticTopKPolicy(arms, scores=target_agg_surrogate, k=k, seed=s)
                )
        for name, build in builders.items():
            policy = build(seed + repeat)
            pulls = {arm.key: 0 for arm in arms}
            spent = 0
            successes = 0
            cost = 0.0
            while spent < budget:
                take = min(batch_size, budget - spent)
                for key in policy.allocate(budget=take):
                    hit = labels[key][pulls[key] % budget]
                    pulls[key] += 1
                    successes += hit
                    arm = policy.arms[key]
                    if arm.cost_seconds is not None:
                        cost += arm.cost_seconds
                    policy.observe(key, successes=hit, trials=1)
                    spent += 1
            per_repeat.setdefault(name, []).append(successes)
            entry = totals.setdefault(name, {"calls": 0, "successes": 0, "cost_seconds": 0.0})
            entry["calls"] = budget
            entry["successes"] += successes
            entry["cost_seconds"] += cost

    # 사후적으로 가장 좋았던 k 를 대조군의 대표값으로 승격한다. 이것은 대조군에
    # 주는 이점이며, 그 사실을 이름과 필드에 남긴다.
    for family, prefix in (("static_topk_oracle_best", "static_topk_oracle_k"),
                           ("static_topk_measured_auc_best", "static_topk_measured_auc_k"),
                           ("static_topk_target_agg_best", "static_topk_target_agg_k")):
        members = {name: values for name, values in per_repeat.items() if name.startswith(prefix)}
        if not members:
            continue
        best_name = max(members, key=lambda name: (statistics.fmean(members[name]), name))
        per_repeat[family] = list(members[best_name])
        totals[family] = dict(totals[best_name])
        totals[family]["chosen_k"] = int(best_name.rsplit("k", 1)[1])
        totals[family]["k_chosen_in_hindsight"] = True

    out: dict[str, dict] = {}
    baseline = per_repeat.get("uniform", [])
    for name, values in per_repeat.items():
        entry = {
            "calls": budget,
            "successes": round(statistics.fmean(values), 4),
            "successes_per_repeat": values,
            "repeats": repeats,
            "cost_seconds": round(totals[name]["cost_seconds"] / max(1, repeats), 1),
        }
        if "chosen_k" in totals[name]:
            entry["chosen_k"] = totals[name]["chosen_k"]
            entry["k_chosen_in_hindsight"] = True
        if baseline and name != "uniform":
            diffs = [a - b for a, b in zip(values, baseline)]
            entry["vs_uniform"] = round(statistics.fmean(diffs), 4)
            entry["vs_uniform_ci95"] = _bootstrap_ci(diffs, seed=seed)
        out[name] = entry

    # 논문이 실제로 주장할 비교. uniform 을 이기는 것은 쉽다 - 어려운 상대는
    # 우리가 실제로 가진 대리모형으로 상위를 고른 static 정책이다.
    adaptive = per_repeat.get("rapid_adaptive")
    for label, reference in (("vs_static_best", "static_topk_measured_auc_best"),
                             ("vs_static_target_agg", "static_topk_target_agg_best")):
        other = per_repeat.get(reference)
        if not (other and adaptive):
            continue
        diffs = [a - b for a, b in zip(adaptive, other)]
        out["rapid_adaptive"][label] = round(statistics.fmean(diffs), 4)
        out["rapid_adaptive"][f"{label}_ci95"] = _bootstrap_ci(diffs, seed=seed)
        out["rapid_adaptive"][f"{label}_reference"] = reference
    return out


def clustered_policy_bootstrap(
    arms,
    *,
    truth: dict[str, float],
    budget: int,
    batch_size: int,
    n_boot: int = 200,
    seed: int = 0,
    surrogate_auc: float | None = 0.7247,
    measured_surrogate_scores: dict[str, float] | None = None,
    reference: str = "static_topk_measured_auc_best",
) -> dict:
    """타겟을 클러스터로 보고 재표집해 정책 차이의 CI 를 낸다.

    왜 반복 재실행만으로는 부족한가. 이 데이터의 yield 는 0 또는 1 에 몰려 있어서
    라벨 뽑기에 사실상 무작위성이 없다 - 200 회 반복이 전부 같은 값을 냈다. 그
    위에서 계산한 CI 는 "시뮬레이션을 다시 돌리면 얼마나 달라지는가" 를 재는데,
    아무도 그것을 묻지 않는다. 물어야 할 것은 **다른 타겟에서도 성립하는가** 이고,
    그러려면 타겟을 통째로 재표집해야 한다.

    설계는 배열이 아니라 타겟 단위다. 한 타겟이 뽑히면 그 타겟의 백본과 설계가
    전부 따라온다 - 타겟 안의 관측은 독립이 아니기 때문이다.
    """
    targets = sorted({arm.target_id for arm in arms})
    if len(targets) < 2:
        raise ValueError(f"타겟이 {len(targets)} 개면 재표집할 것이 없다")
    if n_boot < 2:
        raise ValueError("n_boot 는 2 이상이어야 한다")

    by_target: dict[str, list] = {}
    for arm in arms:
        by_target.setdefault(arm.target_id, []).append(arm)

    rng = random.Random(seed)
    diffs: list[float] = []
    adaptive_values: list[float] = []
    reference_values: list[float] = []
    counts: list[dict[str, int]] = []

    for draw in range(n_boot):
        picked = [targets[rng.randrange(len(targets))] for _ in targets]
        counts.append({target: picked.count(target) for target in set(picked)})
        # 같은 타겟이 두 번 뽑히면 arm key 가 겹친다. 복제본마다 접미사를 붙여
        # 별개의 arm 으로 둔다 - 그것이 복원추출의 의미다.
        resampled = []
        resampled_truth = {}
        for copy_index, target in enumerate(picked):
            for arm in by_target[target]:
                clone = Arm(
                    target_id=f"{target}#{copy_index}",
                    backbone_id=arm.backbone_id,
                    condition=arm.condition,
                    cost_seconds=arm.cost_seconds,
                )
                resampled.append(clone)
                resampled_truth[clone.key] = truth[arm.key]
        surrogate = None
        if measured_surrogate_scores is not None:
            surrogate = {}
            for copy_index, target in enumerate(picked):
                for arm in by_target[target]:
                    clone_key = f"{target}#{copy_index}|{arm.backbone_id}|{arm.condition}"
                    surrogate[clone_key] = measured_surrogate_scores[arm.key]
        result = simulate(
            resampled, truth=resampled_truth, budget=budget, batch_size=batch_size,
            seed=seed * 7919 + draw, repeats=1,
            surrogate_auc=surrogate_auc, measured_surrogate_scores=surrogate,
        )
        adaptive = result["rapid_adaptive"]["successes"]
        other = result.get(reference, {}).get("successes")
        adaptive_values.append(adaptive)
        if other is not None:
            reference_values.append(other)
            diffs.append(adaptive - other)

    def summarise(values):
        if not values:
            return None
        ordered = sorted(values)
        lo = ordered[max(0, int(0.025 * len(ordered)))]
        hi = ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))]
        return [round(float(lo), 4), round(float(hi), 4)]

    return {
        "n_targets": len(targets),
        "n_boot": n_boot,
        "budget": budget,
        "reference": reference,
        "rapid_adaptive": round(statistics.fmean(adaptive_values), 4),
        "rapid_adaptive_ci95": summarise(adaptive_values),
        "reference_successes": round(statistics.fmean(reference_values), 4) if reference_values else None,
        "reference_ci95": summarise(reference_values),
        "vs_static_best": round(statistics.fmean(diffs), 4) if diffs else None,
        "vs_static_best_ci95": summarise(diffs),
        "excludes_zero": bool(diffs) and (summarise(diffs)[0] > 0 or summarise(diffs)[1] < 0),
        "resampled_target_counts": counts,
        "note": (
            "CI 는 타겟을 클러스터로 복원추출해서 얻은 것이다. 같은 타겟이 여러 번 "
            "뽑히면 그 복제본은 별개의 arm 집합으로 취급된다. 이 CI 는 '다른 타겟 "
            "집합에서도 성립하는가' 에 답하며, 시뮬레이션 재실행 분산과는 다른 것이다."
        ),
    }
