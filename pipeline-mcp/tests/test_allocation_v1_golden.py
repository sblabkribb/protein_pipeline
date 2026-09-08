"""rapid_structural_v1 정책의 관찰 가능한 동작을 동결한다.

무엇을 위한 테스트인가
----------------------
v2 (objective-pluggable) 리팩터링이 v1 을 바꾸지 않았음을 보장하는 안전망이다.
v1 은 현재 논문이 전향적으로 검증하는 대상이므로, 리팩터링이 그 대상을 바꾸면
검증 결과가 무엇에 대한 것인지 알 수 없게 된다.

**이 테스트가 통과하는 동안만 리팩터링한다.** 실패하면 v1 이 바뀐 것이고,
그것은 리팩터링이 아니라 정책 변경이다.

무엇을 고정하는가
-----------------
내부 구현이 아니라 **관찰 가능한 동작**이다. 사후분포를 어떻게 저장하는지는
바뀔 수 있지만, 같은 관측에서 같은 결정이 나와야 한다.

    사전분포와 부분 풀링       형제 관측이 arm 사후평균을 끌어당기는 정도
    사후평균·SD·movability     정확한 수치
    4 갈래 행동 경계           MIN_PROBE_SEQUENCES 와 MOVABILITY_FLOOR 에서의 전환
    acquisition 순위           arm 이름의 순서 (점수 자체가 아니라 순서)
    누출 가드                  참값 yield 주입 경로가 없음
    결정적 재생                고정된 관측 열 -> 고정된 행동 열

기대값은 현재 구현에서 읽어 적은 것이다. 값 자체가 옳다는 주장이 아니라,
**바뀌지 않았다는 것**을 재는 것이다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.allocation import (  # noqa: E402
    DEFAULT_POOLING_STRENGTH,
    DEFAULT_PRIOR_MEAN,
    DEFAULT_PRIOR_STRENGTH,
    MIN_PROBE_SEQUENCES,
    MOVABILITY_FLOOR,
    Arm,
    BetaPosterior,
    HierarchicalAllocator,
    movability,
)

PROFILE = "rapid_structural_v1"


def allocator(n_backbones: int = 4, conditions=("T0.1",), *, prior=None):
    arms = [Arm(target_id="T", backbone_id=f"B{i}", condition=c)
            for i in range(n_backbones) for c in conditions]
    a = HierarchicalAllocator(arms, seed=0)
    if prior is not None:
        a.set_target_prior("T", mean=prior[0], strength=prior[1])
    return a


class TestFrozenConstants(unittest.TestCase):
    """상수가 바뀌면 모든 경계가 움직인다. 먼저 고정한다."""

    def test_constants(self):
        self.assertEqual(DEFAULT_PRIOR_MEAN, 0.5)
        self.assertEqual(DEFAULT_PRIOR_STRENGTH, 2.0)
        self.assertEqual(MIN_PROBE_SEQUENCES, 4)
        self.assertEqual(MOVABILITY_FLOOR, 0.2)
        self.assertEqual(DEFAULT_POOLING_STRENGTH, 4.0)


class TestPosteriorArithmetic(unittest.TestCase):
    def test_prior_construction(self):
        p = BetaPosterior.from_prior(mean=0.42, strength=3.0)
        self.assertAlmostEqual(p.alpha, 1.26, places=10)
        self.assertAlmostEqual(p.beta, 1.74, places=10)
        self.assertAlmostEqual(p.mean, 0.42, places=10)

    def test_update_and_mean_sd(self):
        p = BetaPosterior.from_prior(mean=0.5, strength=2.0)
        p.update(successes=3, trials=8)
        self.assertAlmostEqual(p.alpha, 4.0, places=10)
        self.assertAlmostEqual(p.beta, 6.0, places=10)
        self.assertAlmostEqual(p.mean, 0.4, places=10)
        self.assertAlmostEqual(p.sd, 0.1477097892, places=9)

    def test_zero_trials_is_a_noop(self):
        p = BetaPosterior.from_prior(mean=0.5, strength=2.0)
        p.update(successes=0, trials=0)
        self.assertAlmostEqual(p.mean, 0.5, places=10)

    def test_movability_is_scaled_bernoulli_variance(self):
        self.assertAlmostEqual(movability(0.5), 1.0, places=10)
        self.assertAlmostEqual(movability(0.0), 0.0, places=10)
        self.assertAlmostEqual(movability(1.0), 0.0, places=10)
        self.assertAlmostEqual(movability(0.1), 0.36, places=10)
        # 경계값 p: movability == MOVABILITY_FLOOR 근처
        self.assertLess(movability(0.05), MOVABILITY_FLOOR)
        self.assertGreater(movability(0.06), 0.2 - 0.02)

    def test_movability_does_not_decay_with_more_observations(self):
        """movability 는 expected information gain 이 아니다.

        관측이 4 개든 400 개든 p 가 0.5 면 값은 1 이다. v2 에서 이 슬롯을
        allocation_signal 로 부르는 이유이고, EI 나 information gain 으로
        해석하면 안 된다는 근거다.
        """
        thin = BetaPosterior.from_prior(mean=0.5, strength=2.0)
        thin.update(successes=2, trials=4)
        thick = BetaPosterior.from_prior(mean=0.5, strength=2.0)
        thick.update(successes=200, trials=400)
        self.assertAlmostEqual(movability(thin.mean), movability(thick.mean), places=10)
        # 반면 uncertainty 는 줄어든다 - 두 양이 다르다는 증거.
        self.assertGreater(thin.sd, thick.sd * 5)


class TestPartialPooling(unittest.TestCase):
    """형제 관측이 arm 사후평균을 끌어당기는 정도를 고정한다."""

    def test_arm_prior_is_the_target_posterior(self):
        a = allocator(prior=(0.42, 3.0))
        # 관측 전: arm 사후평균 == 타겟 사전평균
        self.assertAlmostEqual(a.posterior_mean("T|B0|T0.1"), 0.42, places=10)

    def test_sibling_observation_moves_an_unobserved_arm(self):
        a = allocator(prior=(0.42, 3.0))
        before = a.posterior_mean("T|B1|T0.1")
        a.observe("T|B0|T0.1", successes=8, trials=8)
        after = a.posterior_mean("T|B1|T0.1")
        self.assertGreater(after, before)
        self.assertAlmostEqual(before, 0.42, places=10)
        self.assertAlmostEqual(after, 0.8418181818, places=9)

    def test_own_observation_dominates_the_pooled_prior(self):
        """pooling_strength 가 고정이므로 타겟이 많이 관측돼도 arm 데이터를
        압도하지 못한다."""
        a = allocator(prior=(0.42, 3.0))
        for i in range(1, 4):
            a.observe(f"T|B{i}|T0.1", successes=24, trials=24)
        a.observe("T|B0|T0.1", successes=0, trials=24)
        # 형제가 전부 1.0 인데도 자기 관측 0/24 가 이긴다
        self.assertLess(a.posterior_mean("T|B0|T0.1"), 0.2)

    def test_pooling_is_deterministic(self):
        first = allocator(prior=(0.42, 3.0))
        second = allocator(prior=(0.42, 3.0))
        for a in (first, second):
            a.observe("T|B0|T0.1", successes=3, trials=8)
        self.assertEqual(first.posterior_mean("T|B0|T0.1"),
                         second.posterior_mean("T|B0|T0.1"))


class TestActionBoundaries(unittest.TestCase):
    """4 갈래 경계. 여기가 움직이면 정책이 바뀐 것이다."""

    def _action(self, successes, trials, *, prior=(0.42, 3.0), siblings=()):
        a = allocator(prior=prior)
        for key, s, t in siblings:
            a.observe(key, successes=s, trials=t)
        if trials:
            a.observe("T|B0|T0.1", successes=successes, trials=trials)
        return a.next_action("T", "B0")["action"]

    def test_below_min_probe_asks_for_more(self):
        for trials in range(0, MIN_PROBE_SEQUENCES):
            self.assertEqual(self._action(trials, trials), "probe_more_sequences",
                             f"trials={trials}")

    def test_at_min_probe_decides(self):
        self.assertNotEqual(self._action(2, MIN_PROBE_SEQUENCES),
                            "probe_more_sequences")

    def test_dead_arm_alone_is_abandoned(self):
        self.assertEqual(self._action(0, 24), "abandon_backbone")

    def test_saturated_high_arm_goes_to_verification(self):
        self.assertEqual(self._action(24, 24), "verify_with_af2")

    def test_mid_yield_explores_condition(self):
        self.assertEqual(self._action(4, 8), "explore_generation_condition")

    def test_siblings_can_rescue_a_thin_zero(self):
        """0/8 도 형제가 좋으면 탐색을 받는다. 홀로면 버려진다.

        백본을 홀로 판정하지 않는 것이 계층 구조의 요점이므로, 이 두 결과가
        갈리는 것 자체를 고정한다.
        """
        alone = self._action(0, 8)
        with_siblings = self._action(0, 8, siblings=[("T|B1|T0.1", 4, 8)])
        self.assertEqual(alone, "abandon_backbone")
        self.assertEqual(with_siblings, "explore_generation_condition")

    def test_probe_state_reports_both_signals_separately(self):
        a = allocator(prior=(0.42, 3.0))
        a.observe("T|B0|T0.1", successes=3, trials=8)
        state = a.probe_state("T", "B0")
        self.assertIn("uncertainty", state)
        self.assertIn("movability", state)
        self.assertNotAlmostEqual(state["uncertainty"], state["movability"], places=3)
        self.assertEqual(state["source"], "probe")
        self.assertEqual(state["information_used"], ["gate0_prior", "observed_probes"])

    def test_prior_only_is_labelled(self):
        a = allocator(prior=(0.42, 3.0))
        self.assertEqual(a.probe_state("T", "B0")["source"], "prior_only")


class TestAcquisitionRanking(unittest.TestCase):
    """점수 자체가 아니라 순서를 고정한다. 순서가 관찰 가능한 동작이다."""

    def test_ranking_is_deterministic_and_pinned(self):
        a = allocator(n_backbones=4, prior=(0.42, 3.0))
        a.observe("T|B0|T0.1", successes=0, trials=8)
        a.observe("T|B1|T0.1", successes=4, trials=8)
        a.observe("T|B2|T0.1", successes=8, trials=8)
        ranked = sorted(a.arm_keys, key=lambda k: (-a.score(k), k))
        self.assertEqual(ranked, ["T|B2|T0.1", "T|B3|T0.1",
                                  "T|B1|T0.1", "T|B0|T0.1"])

    def test_allocate_respects_budget_and_is_deterministic(self):
        first = allocator(n_backbones=4, prior=(0.42, 3.0))
        second = allocator(n_backbones=4, prior=(0.42, 3.0))
        for a in (first, second):
            a.observe("T|B0|T0.1", successes=1, trials=8)
        self.assertEqual(first.allocate(budget=6), second.allocate(budget=6))
        self.assertEqual(len(first.allocate(budget=6)), 6)

    def test_zero_budget_allocates_nothing(self):
        self.assertEqual(allocator().allocate(budget=0), [])

    def test_score_parts_sum_to_score(self):
        """항을 따로 낸다는 계약. 왜 그 arm 에 썼는지 설명하려면 필요하다."""
        a = allocator(prior=(0.42, 3.0))
        a.observe("T|B0|T0.1", successes=3, trials=8)
        parts = a.score_parts("T|B0|T0.1")
        total = (parts["posterior_mean"] + parts["uncertainty"]
                 + parts["diversity"] + parts["cost"]
                 + parts["condition_exploration"])
        self.assertAlmostEqual(total, a.score("T|B0|T0.1"), places=10)


class TestLeakageGuard(unittest.TestCase):
    def test_true_yield_cannot_be_injected(self):
        a = allocator()
        with self.assertRaises(TypeError):
            a.set_backbone_true_yield("T", "B0", 1.0)

    def test_unknown_arm_is_rejected(self):
        a = allocator()
        with self.assertRaises(KeyError):
            a.observe("T|ghost|T0.1", successes=1, trials=1)

    def test_successes_above_trials_is_rejected(self):
        a = allocator()
        with self.assertRaises(ValueError):
            a.observe("T|B0|T0.1", successes=5, trials=2)

    def test_unregistered_backbone_state_is_rejected(self):
        a = allocator()
        with self.assertRaises(KeyError):
            a.probe_state("T", "ghost")


class TestDeterministicReplay(unittest.TestCase):
    """고정된 관측 열 -> 고정된 행동 열. 전체 궤적을 동결한다."""

    #: (arm, successes, trials) 를 순서대로 넣으면서 B0 의 행동을 기록한다.
    OBSERVATIONS = [
        ("T|B0|T0.1", 1, 2),
        ("T|B1|T0.1", 6, 8),
        ("T|B0|T0.1", 1, 2),
        ("T|B2|T0.1", 0, 8),
        ("T|B0|T0.1", 0, 8),
        ("T|B0|T0.1", 0, 12),
    ]
    #: 마지막이 abandon 이 아닌 것이 이 fixture 의 요점이다. B0 은 0/24 인데도
    #: 형제 B1 (6/8) 이 타겟 사후분포를 끌어올려 p_hat 0.1022 · movability
    #: 0.3670 으로 floor(0.2) 위에 남는다. 홀로 있는 0/24 는 버려진다
    #: (TestActionBoundaries.test_dead_arm_alone_is_abandoned).
    #: 부분 풀링이 조기 포기를 막는다는 것이 v1 의 동작이므로 그것을 고정한다.
    EXPECTED_ACTIONS = [
        "probe_more_sequences",
        "probe_more_sequences",
        "explore_generation_condition",
        "explore_generation_condition",
        "explore_generation_condition",
        "explore_generation_condition",
    ]

    #: 같은 열의 (n_observed, p_hat, movability). 행동만 고정하면 경계 근처에서
    #: 값이 크게 움직여도 통과할 수 있다.
    EXPECTED_STATE = [
        (2, 0.4680, 0.9959),
        (2, 0.5903, 0.9674),
        (4, 0.5587, 0.9862),
        (4, 0.4513, 0.9905),
        (12, 0.1997, 0.6392),
        (24, 0.1022, 0.3670),
    ]

    def _trace(self):
        a = allocator(n_backbones=4, prior=(0.42, 3.0))
        actions, states = [], []
        for key, s, t in self.OBSERVATIONS:
            a.observe(key, successes=s, trials=t)
            state = a.probe_state("T", "B0")
            actions.append(a.next_action("T", "B0")["action"])
            states.append((state["n_observed"], state["p_hat"], state["movability"]))
        return actions, states

    def test_replay_matches_the_frozen_trace(self):
        self.assertEqual(self._trace()[0], self.EXPECTED_ACTIONS)

    def test_replay_state_matches(self):
        for got, want in zip(self._trace()[1], self.EXPECTED_STATE):
            self.assertEqual(got[0], want[0])
            self.assertAlmostEqual(got[1], want[1], places=4)
            self.assertAlmostEqual(got[2], want[2], places=4)

    def test_replay_is_reproducible(self):
        self.assertEqual(self._trace(), self._trace())

    def test_pooling_is_what_prevents_abandonment_here(self):
        """형제를 빼면 같은 관측이 abandon 으로 간다. 차이의 원인을 고정한다."""
        alone = allocator(n_backbones=1, prior=(0.42, 3.0))
        alone.observe("T|B0|T0.1", successes=0, trials=24)
        self.assertEqual(alone.next_action("T", "B0")["action"], "abandon_backbone")

    def test_profile_name_is_recorded(self):
        """무엇을 동결했는지 이름으로 남긴다. v2 결과와 섞이지 않게."""
        self.assertEqual(PROFILE, "rapid_structural_v1")


if __name__ == "__main__":
    unittest.main()
