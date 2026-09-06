"""적응적 예산 배분 정책.

RAPID 의 주장은 "같은 예산에서 더 많은 통과 후보를 얻는다" 이다. 그 주장을
검사할 수 있으려면 정책이 다음을 지켜야 한다.

* **관측만으로 움직인다.** 라벨을 지어내지 않는다. 아직 안 본 arm 은 사전분포
  그대로다.
* **결정적이다.** 같은 관측과 같은 seed 면 같은 배분이 나온다. 그러지 않으면
  비교 실험이 성립하지 않는다.
* **모르는 비용을 0 으로 두지 않는다.** 0 으로 두면 측정 안 한 스테이지가
  공짜로 보여서 예산이 그쪽으로 몰린다.
* **계층을 쓴다.** arm 당 관측이 2-3 개뿐인 예산에서 평평한 20-arm 밴딧은
  움직이지 않는다. 같은 타겟 안의 arm 들이 정보를 나눠야 한다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.allocation import (
    Arm,
    BetaPosterior,
    HierarchicalAllocator,
    RandomPolicy,
    StaticTopKPolicy,
    UniformPolicy,
    simulate,
    surrogate_with_auc,
)


def _arms(n_targets=2, n_backbones=2, conditions=("T0.1", "T0.3"), cost=180.0):
    out = []
    for t in range(n_targets):
        for b in range(n_backbones):
            for condition in conditions:
                out.append(Arm(
                    target_id=f"tgt{t}", backbone_id=f"bb{t}_{b}",
                    condition=condition, cost_seconds=cost,
                ))
    return out


class PosteriorTests(unittest.TestCase):
    def test_prior_mean_is_the_prior_not_zero(self):
        post = BetaPosterior.from_prior(mean=0.4, strength=10.0)
        self.assertAlmostEqual(post.mean, 0.4, places=6)

    def test_observation_moves_the_mean_toward_the_data(self):
        post = BetaPosterior.from_prior(mean=0.5, strength=4.0)
        post.update(successes=8, trials=8)
        self.assertGreater(post.mean, 0.5)

    def test_more_trials_shrink_the_sd(self):
        weak = BetaPosterior.from_prior(mean=0.5, strength=4.0)
        strong = BetaPosterior.from_prior(mean=0.5, strength=4.0)
        weak.update(successes=2, trials=4)
        strong.update(successes=20, trials=40)
        self.assertLess(strong.sd, weak.sd)

    def test_successes_cannot_exceed_trials(self):
        post = BetaPosterior.from_prior(mean=0.5, strength=2.0)
        with self.assertRaises(ValueError):
            post.update(successes=5, trials=3)

    def test_zero_trials_is_a_no_op_not_an_update(self):
        post = BetaPosterior.from_prior(mean=0.5, strength=2.0)
        before = (post.alpha, post.beta)
        post.update(successes=0, trials=0)
        self.assertEqual((post.alpha, post.beta), before)


class HierarchyTests(unittest.TestCase):
    def test_an_unobserved_arm_inherits_its_target_prior(self):
        alloc = HierarchicalAllocator(_arms())
        alloc.set_target_prior("tgt0", mean=0.8, strength=6.0)
        alloc.set_target_prior("tgt1", mean=0.2, strength=6.0)
        self.assertGreater(alloc.posterior_mean("tgt0|bb0_0|T0.1"),
                           alloc.posterior_mean("tgt1|bb1_0|T0.1"))

    def test_evidence_on_one_arm_moves_its_siblings_in_the_same_target(self):
        """부분 풀링이 없으면 arm 당 2-3 관측으로는 아무것도 안 움직인다."""
        alloc = HierarchicalAllocator(_arms())
        sibling = "tgt0|bb0_1|T0.1"
        before = alloc.posterior_mean(sibling)
        alloc.observe("tgt0|bb0_0|T0.1", successes=8, trials=8)
        self.assertGreater(alloc.posterior_mean(sibling), before)

    def test_evidence_does_not_leak_across_targets(self):
        alloc = HierarchicalAllocator(_arms())
        other = "tgt1|bb1_0|T0.1"
        before = alloc.posterior_mean(other)
        alloc.observe("tgt0|bb0_0|T0.1", successes=8, trials=8)
        self.assertAlmostEqual(alloc.posterior_mean(other), before, places=9)

    def test_an_arms_own_evidence_outweighs_its_siblings(self):
        alloc = HierarchicalAllocator(_arms())
        alloc.observe("tgt0|bb0_0|T0.1", successes=0, trials=8)
        alloc.observe("tgt0|bb0_1|T0.1", successes=8, trials=8)
        self.assertLess(alloc.posterior_mean("tgt0|bb0_0|T0.1"),
                        alloc.posterior_mean("tgt0|bb0_1|T0.1"))

    def test_unknown_arm_is_an_error_not_a_silent_new_arm(self):
        alloc = HierarchicalAllocator(_arms())
        with self.assertRaises(KeyError):
            alloc.observe("nope|nope|T0.1", successes=1, trials=1)


class ScoreTests(unittest.TestCase):
    def test_uncertainty_bonus_favours_the_less_observed_arm(self):
        alloc = HierarchicalAllocator(_arms(), beta_uncertainty=1.0, lambda_cost=0.0)
        alloc.observe("tgt0|bb0_0|T0.1", successes=4, trials=8)
        alloc.observe("tgt0|bb0_1|T0.1", successes=20, trials=40)
        # 같은 사후평균, 다른 확신도 -> 덜 본 쪽이 더 높은 점수를 받는다.
        self.assertGreater(alloc.score("tgt0|bb0_0|T0.1"), alloc.score("tgt0|bb0_1|T0.1"))

    def test_cost_penalty_favours_the_cheaper_arm(self):
        arms = [
            Arm("t", "cheap", "T0.1", cost_seconds=10.0),
            Arm("t", "dear", "T0.1", cost_seconds=1000.0),
        ]
        alloc = HierarchicalAllocator(arms, beta_uncertainty=0.0, lambda_cost=1.0)
        self.assertGreater(alloc.score("t|cheap|T0.1"), alloc.score("t|dear|T0.1"))

    def test_an_unknown_cost_is_not_treated_as_free(self):
        """비용을 모르는 arm 이 0 원짜리로 보이면 예산이 거기로 몰린다."""
        arms = [
            Arm("t", "known", "T0.1", cost_seconds=10.0),
            Arm("t", "unknown", "T0.1", cost_seconds=None),
        ]
        alloc = HierarchicalAllocator(arms, beta_uncertainty=0.0, lambda_cost=1.0)
        self.assertLessEqual(alloc.score("t|unknown|T0.1"), alloc.score("t|known|T0.1"))

    def test_cost_term_is_off_when_no_arm_declares_a_cost(self):
        arms = [Arm("t", f"b{i}", "T0.1", cost_seconds=None) for i in range(3)]
        alloc = HierarchicalAllocator(arms, lambda_cost=1.0)
        scores = {alloc.score(k) for k in alloc.arm_keys}
        self.assertEqual(len(scores), 1, "비용 정보가 전혀 없으면 비용항은 아무 것도 구분하지 못해야 한다")

    def test_diversity_term_penalises_repeating_the_same_backbone(self):
        alloc = HierarchicalAllocator(_arms(), gamma_diversity=1.0, beta_uncertainty=0.0)
        plain = alloc.score("tgt0|bb0_0|T0.3")
        crowded = alloc.score("tgt0|bb0_0|T0.3", selected=["tgt0|bb0_0|T0.1"])
        self.assertLess(crowded, plain)


class AllocationTests(unittest.TestCase):
    def test_allocation_respects_the_budget(self):
        alloc = HierarchicalAllocator(_arms())
        picks = alloc.allocate(budget=7)
        self.assertEqual(len(picks), 7)

    def test_allocation_is_deterministic_for_a_given_seed(self):
        a = HierarchicalAllocator(_arms(), seed=0).allocate(budget=9)
        b = HierarchicalAllocator(_arms(), seed=0).allocate(budget=9)
        self.assertEqual(a, b)

    def test_a_budget_larger_than_the_arm_count_still_allocates_every_call(self):
        alloc = HierarchicalAllocator(_arms(n_targets=1, n_backbones=1, conditions=("T0.1",)))
        self.assertEqual(len(alloc.allocate(budget=5)), 5)

    def test_allocation_prefers_the_arm_the_evidence_favours(self):
        alloc = HierarchicalAllocator(_arms(), beta_uncertainty=0.0, lambda_cost=0.0,
                                      gamma_diversity=0.0)
        alloc.observe("tgt0|bb0_0|T0.1", successes=16, trials=16)
        alloc.observe("tgt1|bb1_0|T0.1", successes=0, trials=16)
        picks = alloc.allocate(budget=4)
        self.assertIn("tgt0|bb0_0|T0.1", picks)
        self.assertNotIn("tgt1|bb1_0|T0.1", picks)

    def test_zero_budget_allocates_nothing(self):
        self.assertEqual(HierarchicalAllocator(_arms()).allocate(budget=0), [])


class BaselinePolicyTests(unittest.TestCase):
    """비교 대상. RAPID 가 이겨야 할 상대를 코드로 고정해 둔다."""

    def test_uniform_spreads_the_budget_evenly(self):
        picks = UniformPolicy(_arms(), seed=0).allocate(budget=8)
        self.assertEqual(len(picks), 8)
        self.assertEqual(len(set(picks)), 8)

    def test_uniform_round_robins_across_successive_calls(self):
        """배치마다 처음부터 다시 고르면 uniform 이 아니라 '앞쪽 arm 만' 이 된다.

        시뮬레이터는 예산을 배치로 쪼개서 allocate 를 여러 번 부른다. 커서가
        없으면 uniform 은 매 배치마다 같은 앞쪽 arm 을 반복해 뽑고, arm 순서가
        운 좋게 좋은 타겟부터면 uniform 이 적응 정책보다 잘 나온다.
        """
        policy = UniformPolicy(_arms(n_targets=3, n_backbones=1, conditions=("T0.1",)), seed=0)
        picks = policy.allocate(budget=1) + policy.allocate(budget=1) + policy.allocate(budget=1)
        self.assertEqual(sorted(picks), sorted(policy.arm_keys))

    def test_uniform_visit_counts_stay_within_one_of_each_other(self):
        policy = UniformPolicy(_arms(n_targets=2, n_backbones=2, conditions=("T0.1",)), seed=0)
        seen = {}
        for _ in range(5):
            for key in policy.allocate(budget=3):
                seen[key] = seen.get(key, 0) + 1
        self.assertLessEqual(max(seen.values()) - min(seen.values()), 1)

    def test_uniform_is_deterministic(self):
        self.assertEqual(UniformPolicy(_arms(), seed=1).allocate(budget=5),
                         UniformPolicy(_arms(), seed=1).allocate(budget=5))

    def test_random_differs_by_seed_but_repeats_within_a_seed(self):
        one = RandomPolicy(_arms(), seed=1).allocate(budget=6)
        again = RandomPolicy(_arms(), seed=1).allocate(budget=6)
        other = RandomPolicy(_arms(), seed=2).allocate(budget=6)
        self.assertEqual(one, again)
        self.assertNotEqual(one, other)

    def test_static_topk_replicates_within_its_top_k_instead_of_descending(self):
        """예산이 k 보다 크면 상위 k 를 반복해야지 랭킹을 내려가면 안 된다.

        내려가면 배치 크기가 커질수록 나쁜 arm 을 집게 되어, 대조군이 예산 탓에
        약해진다. 그건 적응성의 값어치가 아니라 대조군 구현의 결함이다.
        """
        arms = _arms(n_targets=2, n_backbones=2, conditions=("T0.1",))
        scores = {a.key: (1.0 if a.target_id == "tgt0" else 0.0) for a in arms}
        policy = StaticTopKPolicy(arms, scores=scores, k=2, seed=0)
        picks = policy.allocate(budget=8)
        self.assertEqual({p.split("|")[0] for p in picks}, {"tgt0"})

    def test_static_topk_round_robins_within_the_top_k_across_calls(self):
        arms = _arms(n_targets=2, n_backbones=2, conditions=("T0.1",))
        scores = {a.key: (1.0 if a.target_id == "tgt0" else 0.0) for a in arms}
        policy = StaticTopKPolicy(arms, scores=scores, k=2, seed=0)
        picks = policy.allocate(budget=1) + policy.allocate(budget=1)
        self.assertEqual(len(set(picks)), 2)

    def test_static_topk_k_defaults_to_every_arm(self):
        arms = _arms(n_targets=2, n_backbones=1, conditions=("T0.1",))
        scores = {a.key: 0.5 for a in arms}
        policy = StaticTopKPolicy(arms, scores=scores, seed=0)
        self.assertEqual(sorted(set(policy.allocate(budget=4))), sorted(policy.arm_keys))

    def test_static_topk_rejects_a_k_that_selects_nothing(self):
        arms = _arms(n_targets=1, n_backbones=1, conditions=("T0.1",))
        with self.assertRaises(ValueError):
            StaticTopKPolicy(arms, scores={a.key: 0.5 for a in arms}, k=0, seed=0)

    def test_static_topk_uses_the_surrogate_and_never_updates(self):
        arms = _arms()
        scores = {f"{a.target_id}|{a.backbone_id}|{a.condition}": i for i, a in enumerate(arms)}
        policy = StaticTopKPolicy(arms, scores=scores, k=4, seed=0)
        before = list(policy.selected)
        # 최악의 관측을 줘도 선택 집합은 그대로여야 한다. 그것이 static 의 정의다.
        policy.observe(before[0], successes=0, trials=16)
        self.assertEqual(policy.selected, before)
        self.assertEqual(before, sorted(scores, key=lambda k: (-scores[k], k))[:4])

    def test_every_policy_shares_one_interface(self):
        arms = _arms()
        scores = {f"{a.target_id}|{a.backbone_id}|{a.condition}": 0.5 for a in arms}
        for policy in (
            UniformPolicy(arms, seed=0), RandomPolicy(arms, seed=0),
            StaticTopKPolicy(arms, scores=scores, seed=0), HierarchicalAllocator(arms, seed=0),
        ):
            picks = policy.allocate(budget=3)
            self.assertEqual(len(picks), 3, type(policy).__name__)
            policy.observe(picks[0], successes=1, trials=2)


class SurrogateTests(unittest.TestCase):
    """대리모형은 완벽하지 않다. 완벽하다고 두면 대조군이 오라클이 된다."""

    def test_a_perfect_surrogate_ranks_every_good_arm_above_every_bad_one(self):
        keys = [f"a{i}" for i in range(40)]
        labels = {k: (1 if i < 20 else 0) for i, k in enumerate(keys)}
        scores = surrogate_with_auc(labels, auc=1.0, seed=0)
        good = min(scores[k] for k in keys if labels[k])
        bad = max(scores[k] for k in keys if not labels[k])
        self.assertGreater(good, bad)

    def test_a_chance_level_surrogate_carries_no_signal(self):
        keys = [f"a{i}" for i in range(200)]
        labels = {k: (1 if i < 100 else 0) for i, k in enumerate(keys)}
        scores = surrogate_with_auc(labels, auc=0.5, seed=0)
        self.assertLess(abs(_empirical_auc(scores, labels) - 0.5), 0.08)

    def test_the_requested_auc_is_approximately_delivered(self):
        keys = [f"a{i}" for i in range(400)]
        labels = {k: (1 if i < 200 else 0) for i, k in enumerate(keys)}
        scores = surrogate_with_auc(labels, auc=0.725, seed=0)
        self.assertLess(abs(_empirical_auc(scores, labels) - 0.725), 0.05)

    def test_surrogate_is_deterministic_for_a_seed(self):
        labels = {f"a{i}": i % 2 for i in range(20)}
        self.assertEqual(surrogate_with_auc(labels, auc=0.7, seed=3),
                         surrogate_with_auc(labels, auc=0.7, seed=3))


def _empirical_auc(scores, labels):
    pos = [scores[k] for k in labels if labels[k]]
    neg = [scores[k] for k in labels if not labels[k]]
    if not pos or not neg:
        return 0.5
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


class SimulationTests(unittest.TestCase):
    def test_simulation_reports_successes_and_cost_per_policy(self):
        arms = _arms()
        truth = {f"{a.target_id}|{a.backbone_id}|{a.condition}":
                 (0.8 if a.target_id == "tgt0" else 0.1) for a in arms}
        out = simulate(arms, truth=truth, budget=24, batch_size=4, seed=0)
        for name in ("uniform", "random", "static_topk_oracle_best", "rapid_adaptive"):
            self.assertIn(name, out)
            self.assertEqual(out[name]["calls"], 24)
            self.assertIn("successes", out[name])

    def test_every_policy_spends_the_same_budget(self):
        arms = _arms()
        truth = {f"{a.target_id}|{a.backbone_id}|{a.condition}": 0.5 for a in arms}
        out = simulate(arms, truth=truth, budget=20, batch_size=5, seed=0)
        self.assertEqual({v["calls"] for v in out.values()}, {20})

    def test_adaptive_beats_uniform_when_arms_actually_differ(self):
        arms = _arms(n_targets=4, n_backbones=3)
        truth = {}
        for arm in arms:
            key = f"{arm.target_id}|{arm.backbone_id}|{arm.condition}"
            truth[key] = 0.9 if arm.target_id == "tgt0" else 0.05
        out = simulate(arms, truth=truth, budget=96, batch_size=8, seed=0, repeats=20)
        self.assertGreater(out["rapid_adaptive"]["successes"], out["uniform"]["successes"])

    def test_adaptive_does_not_claim_a_win_when_every_arm_is_identical(self):
        """차이가 없을 때 이겼다고 나오면 그건 정책이 아니라 우연이다.

        repeats 를 넉넉히 준다. 40 회에서는 부트스트랩 CI 가 (0.15, 3.6) 으로
        0 을 제외했는데, 200 회로 늘리면 네 개의 seed 모두 0 을 포함한다 -
        즉 그것은 정책의 편향이 아니라 반복 부족이었다. 귀무 조건을 검사하는
        테스트가 스스로 검정력이 없으면 아무 것도 보장하지 못한다.
        """
        arms = _arms(n_targets=4, n_backbones=3)
        truth = {f"{a.target_id}|{a.backbone_id}|{a.condition}": 0.5 for a in arms}
        out = simulate(arms, truth=truth, budget=96, batch_size=8, seed=0, repeats=200)
        difference = out["rapid_adaptive"]["successes"] - out["uniform"]["successes"]
        low, high = out["rapid_adaptive"]["vs_uniform_ci95"]
        self.assertLessEqual(low, difference)
        self.assertGreaterEqual(high, difference)
        self.assertTrue(low <= 0 <= high, f"동일한 arm 인데 CI 가 0 을 제외한다: {(low, high)}")

    def test_policies_face_the_same_label_for_the_same_arm_pull(self):
        """공통 난수. 정책 사이의 차이가 배분에서 와야지 운에서 오면 안 된다.

        모든 arm 의 성공확률을 0 또는 1 로 두면 라벨에 무작위성이 없으므로,
        차이가 남아 있다면 그것은 순수하게 어떤 arm 을 골랐는가의 차이다.
        """
        arms = _arms(n_targets=2, n_backbones=2)
        truth = {a.key: (1.0 if a.target_id == "tgt0" else 0.0) for a in arms}
        out = simulate(arms, truth=truth, budget=16, batch_size=4, seed=3, repeats=3)
        self.assertEqual(out["uniform"]["successes"], 8.0,
                         "uniform 은 절반이 좋은 arm 이므로 정확히 절반을 맞혀야 한다")
        self.assertEqual(out["static_topk_oracle_best"]["successes"], 16.0,
                         "완벽한 대리모형이면 static top-K 는 전부 맞혀야 한다")
        self.assertTrue(out["static_topk_oracle_best"]["k_chosen_in_hindsight"],
                        "사후 선택이라는 사실이 결과에 남아야 한다")

    def test_a_repeat_uses_a_different_label_stream(self):
        arms = _arms(n_targets=3, n_backbones=2)
        truth = {a.key: 0.5 for a in arms}
        out = simulate(arms, truth=truth, budget=24, batch_size=6, seed=0, repeats=6)
        self.assertGreater(len(set(out["uniform"]["successes_per_repeat"])), 1,
                           "모든 repeat 이 같은 값이면 난수열이 재사용되고 있다")

    def test_a_realistic_surrogate_arm_is_reported_alongside_the_oracle_one(self):
        """게이트 0 의 실측 AUC 0.725 로 만든 대조군도 같이 돌아야 한다.

        완벽한 대리모형만 대조군으로 두면 적응 정책은 절대 못 이기고, 실제로
        가진 대리모형의 성능은 0.725 이지 1.0 이 아니다.
        """
        arms = _arms(n_targets=4, n_backbones=3)
        truth = {a.key if hasattr(a, "key") else f"{a.target_id}|{a.backbone_id}|{a.condition}":
                 (0.9 if a.target_id == "tgt0" else 0.05) for a in arms}
        out = simulate(arms, truth=truth, budget=48, batch_size=8, seed=0, repeats=10,
                       surrogate_auc=0.725)
        self.assertIn("static_topk_measured_auc_best", out)
        self.assertIn("static_topk_oracle_best", out)
        self.assertGreaterEqual(out["static_topk_oracle_best"]["successes"],
                                out["static_topk_measured_auc_best"]["successes"])

    def test_the_adaptive_policy_starts_from_the_same_gate0_signal_as_the_baseline(self):
        """static 대조군만 대리모형을 보고 적응 정책은 못 보면 비교가 불공정하다.

        RAPID 의 설계는 "게이트 0 -> 소량 탐색 -> 관측 기반 재배분" 이다. 게이트 0
        점수는 하드 컷이 아니라 **사전분포** 로 들어간다. 그것을 빼면 적응 정책은
        평평한 0.5 에서 출발해 대조군이 이미 아는 것을 처음부터 다시 배운다.
        """
        arms = _arms(n_targets=4, n_backbones=2, conditions=("T0.1",))
        truth = {a.key: (0.9 if a.target_id in ("tgt0",) else 0.05) for a in arms}
        with_prior = simulate(arms, truth=truth, budget=40, batch_size=8, seed=0,
                              repeats=40, surrogate_auc=1.0)
        without = simulate(arms, truth=truth, budget=40, batch_size=8, seed=0,
                           repeats=40, surrogate_auc=1.0, use_gate0_prior=False)
        self.assertGreater(with_prior["rapid_adaptive"]["successes"],
                           without["rapid_adaptive"]["successes"])

    def test_the_gate0_prior_is_a_prior_not_a_hard_filter(self):
        """사전분포는 관측으로 뒤집힐 수 있어야 한다. 잘라내면 되돌릴 수 없다."""
        arms = _arms(n_targets=2, n_backbones=1, conditions=("T0.1",))
        alloc = HierarchicalAllocator(arms, beta_uncertainty=0.0, lambda_cost=0.0,
                                      gamma_diversity=0.0)
        alloc.set_target_prior("tgt0", mean=0.9, strength=4.0)
        alloc.set_target_prior("tgt1", mean=0.1, strength=4.0)
        self.assertGreater(alloc.posterior_mean("tgt0|bb0_0|T0.1"),
                           alloc.posterior_mean("tgt1|bb1_0|T0.1"))
        # 사전분포가 틀렸다는 관측이 충분히 쌓이면 순서가 뒤집혀야 한다.
        alloc.observe("tgt0|bb0_0|T0.1", successes=0, trials=40)
        alloc.observe("tgt1|bb1_0|T0.1", successes=40, trials=40)
        self.assertLess(alloc.posterior_mean("tgt0|bb0_0|T0.1"),
                        alloc.posterior_mean("tgt1|bb1_0|T0.1"))

    def test_a_target_aggregated_static_baseline_isolates_adaptation_from_aggregation(self):
        """적응 정책은 대리모형을 타겟 수준으로 모아서 사전분포로 쓴다.

        대조군이 arm 수준 원점수만 본다면, 둘의 차이에는 '온라인 갱신' 뿐 아니라
        '타겟 집계로 잡음을 줄인 것' 까지 섞인다. 같은 집계를 받은 static 대조군을
        같이 돌려야 이득이 어디서 왔는지 말할 수 있다.
        """
        arms = _arms(n_targets=5, n_backbones=3)
        truth = {a.key: (0.8 if a.target_id in ("tgt0", "tgt1") else 0.1) for a in arms}
        out = simulate(arms, truth=truth, budget=120, batch_size=12, seed=0, repeats=30,
                       surrogate_auc=0.725)
        self.assertIn("static_topk_target_agg_best", out)
        adaptive = out["rapid_adaptive"]
        self.assertIn("vs_static_target_agg", adaptive)
        self.assertIn("vs_static_target_agg_ci95", adaptive)

    def test_the_headline_comparison_is_against_the_realistic_static_baseline(self):
        """논문이 주장할 것은 uniform 이 아니라 '실제로 가진 대리모형' 대비 이득이다.

        uniform 을 이기는 것은 쉽다. 어려운 상대는 게이트 0 점수로 상위를 고른
        static 정책이고, 그게 지금 RAPID 가 대체하려는 것이다.
        """
        arms = _arms(n_targets=5, n_backbones=3, conditions=("T0.05", "T0.1", "T0.2", "T0.3"))
        truth = {a.key: (0.75 if a.target_id in ("tgt0", "tgt1") else 0.08) for a in arms}
        out = simulate(arms, truth=truth, budget=240, batch_size=24, seed=0, repeats=50,
                       surrogate_auc=0.725)
        adaptive = out["rapid_adaptive"]
        self.assertIn("vs_static_best", adaptive)
        low, high = adaptive["vs_static_best_ci95"]
        self.assertGreater(low, 0, f"실측 수준 대조군을 못 이긴다: {(low, high)}")

    def test_no_headline_comparison_without_a_realistic_baseline(self):
        arms = _arms()
        truth = {a.key: 0.5 for a in arms}
        out = simulate(arms, truth=truth, budget=16, batch_size=4, seed=0)
        self.assertNotIn("vs_static_best", out["rapid_adaptive"])

    def test_simulation_is_reproducible(self):
        arms = _arms()
        truth = {f"{a.target_id}|{a.backbone_id}|{a.condition}": 0.4 for a in arms}
        first = simulate(arms, truth=truth, budget=16, batch_size=4, seed=7, repeats=5)
        second = simulate(arms, truth=truth, budget=16, batch_size=4, seed=7, repeats=5)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()


class ClusteredUncertaintyTests(unittest.TestCase):
    """불확실성은 타겟 재표집에서 와야 한다.

    yield 가 0 또는 1 로 양극화되어 있으면 라벨 뽑기에 무작위성이 거의 없다.
    실제로 200 회 반복이 전부 같은 값을 냈다. 그 위에서 계산한 CI 는 "다른
    타겟에서도 성립하는가" 라는 질문에 아무 답도 하지 않는다. 타겟을 클러스터로
    보고 재표집해야 그 질문에 답한다.
    """

    def setUp(self):
        from rapid_sr.allocation import clustered_policy_bootstrap
        self.run = clustered_policy_bootstrap

    def _fixture(self, n_targets=8):
        arms = _arms(n_targets=n_targets, n_backbones=2, conditions=("T0.1",))
        truth = {a.key: (0.9 if int(a.target_id[3:]) % 2 == 0 else 0.05) for a in arms}
        return arms, truth

    def test_reports_a_ci_over_resampled_targets(self):
        arms, truth = self._fixture()
        out = self.run(arms, truth=truth, budget=40, batch_size=8, n_boot=40, seed=0)
        low, high = out["vs_static_best_ci95"]
        self.assertLess(low, high, "타겟 재표집 CI 가 한 점으로 붕괴하면 안 된다")

    def test_the_clustered_ci_is_wider_than_the_repeat_ci(self):
        """타겟 간 이질성을 반영하면 CI 는 넓어져야 한다. 좁아지면 뭔가 틀렸다."""
        arms, truth = self._fixture()
        clustered = self.run(arms, truth=truth, budget=40, batch_size=8, n_boot=60, seed=0)
        repeats = simulate(arms, truth=truth, budget=40, batch_size=8, seed=0, repeats=60,
                           surrogate_auc=0.725)["rapid_adaptive"]
        c_low, c_high = clustered["vs_static_best_ci95"]
        r_low, r_high = repeats["vs_static_best_ci95"]
        self.assertGreater(c_high - c_low, r_high - r_low)

    def test_resampling_keeps_whole_targets_together(self):
        """타겟 하나를 뽑으면 그 타겟의 arm 이 전부 따라와야 한다."""
        arms, truth = self._fixture(n_targets=6)
        out = self.run(arms, truth=truth, budget=24, batch_size=6, n_boot=20, seed=0)
        for draw in out["resampled_target_counts"]:
            self.assertEqual(sum(draw.values()), 6)

    def test_it_is_deterministic_for_a_seed(self):
        arms, truth = self._fixture()
        a = self.run(arms, truth=truth, budget=24, batch_size=6, n_boot=20, seed=2)
        b = self.run(arms, truth=truth, budget=24, batch_size=6, n_boot=20, seed=2)
        self.assertEqual(a["vs_static_best_ci95"], b["vs_static_best_ci95"])

    def test_it_refuses_to_run_with_too_few_targets_to_resample(self):
        arms = _arms(n_targets=1, n_backbones=2, conditions=("T0.1",))
        truth = {a.key: 0.5 for a in arms}
        with self.assertRaises(ValueError):
            self.run(arms, truth=truth, budget=8, batch_size=4, n_boot=10, seed=0)


class ConditionExplorationTests(unittest.TestCase):
    """생성 조건 탐색 예산은 움직일 수 있는 백본에만 써야 한다.

    1 차 온도 패널이 이것을 비싸게 가르쳐 주었다. 15 개 백본 중 12 개가 모든
    온도에서 yield 0.000 또는 1.000 이었고, 그 백본들에 쓴 폴드 384 개는 온도에
    대해 아무것도 알려주지 못했다. yield 가 바닥이나 천장에 붙어 있으면 조건을
    바꿔도 결과가 움직일 수 없으므로, 그 백본에서 조건을 비교하는 것은 정의상
    정보가 0 이다.

    그래서 점수에 항을 하나 더한다.

        A(b,g) = p̂ + β·U + γ·D − λ·C + η·E
        E = 0                        g 가 기준 조건이면 (그건 탐색이 아니다)
          = movability(b) · U        아니면
        movability(b) = 4·p̄(1−p̄)    백본 수준 사후평균에서, 0.5 에서 최대
    """

    def _arms_with_conditions(self, targets=("t0", "t1")):
        return [
            Arm(target_id=t, backbone_id=f"{t}_bb", condition=c, cost_seconds=180.0)
            for t in targets for c in ("T0.05", "T0.1", "T0.2", "T0.3")
        ]

    def _alloc(self, **kwargs):
        from rapid_sr.allocation import HierarchicalAllocator as H
        defaults = dict(beta_uncertainty=0.0, gamma_diversity=0.0, lambda_cost=0.0,
                        eta_condition_exploration=1.0, reference_condition="T0.1")
        defaults.update(kwargs)
        return H(self._arms_with_conditions(), **defaults)

    def test_movability_peaks_at_a_half_and_vanishes_at_the_extremes(self):
        from rapid_sr.allocation import movability
        self.assertAlmostEqual(movability(0.5), 1.0, places=6)
        self.assertAlmostEqual(movability(0.0), 0.0, places=6)
        self.assertAlmostEqual(movability(1.0), 0.0, places=6)
        self.assertAlmostEqual(movability(0.1), movability(0.9), places=9)

    def test_a_floor_backbone_gets_almost_no_exploration_bonus(self):
        alloc = self._alloc()
        alloc.observe("t0|t0_bb|T0.1", successes=0, trials=40)
        self.assertLess(alloc.exploration_bonus("t0|t0_bb|T0.3"), 0.02)

    def test_a_ceiling_backbone_gets_almost_no_exploration_bonus(self):
        alloc = self._alloc()
        alloc.observe("t0|t0_bb|T0.1", successes=40, trials=40)
        self.assertLess(alloc.exploration_bonus("t0|t0_bb|T0.3"), 0.02)

    def test_a_mid_yield_backbone_gets_the_largest_exploration_bonus(self):
        alloc = self._alloc()
        alloc.observe("t0|t0_bb|T0.1", successes=20, trials=40)
        alloc.observe("t1|t1_bb|T0.1", successes=0, trials=40)
        self.assertGreater(alloc.exploration_bonus("t0|t0_bb|T0.3"),
                           alloc.exploration_bonus("t1|t1_bb|T0.3"))

    def test_the_reference_condition_is_not_exploration(self):
        alloc = self._alloc()
        alloc.observe("t0|t0_bb|T0.1", successes=20, trials=40)
        self.assertEqual(alloc.exploration_bonus("t0|t0_bb|T0.1"), 0.0)

    def test_movability_uses_the_backbone_level_estimate_not_one_condition(self):
        """한 조건에서 우연히 0/8 이 나왔다고 백본이 바닥이라고 판단하면 안 된다."""
        alloc = self._alloc()
        alloc.observe("t0|t0_bb|T0.3", successes=0, trials=8)
        alloc.observe("t0|t0_bb|T0.1", successes=8, trials=8)
        alloc.observe("t0|t0_bb|T0.2", successes=4, trials=8)
        self.assertGreater(alloc.exploration_bonus("t0|t0_bb|T0.05"), 0.05)

    def test_exploration_budget_concentrates_on_the_movable_backbone(self):
        alloc = self._alloc(beta_uncertainty=0.3)
        alloc.observe("t0|t0_bb|T0.1", successes=20, trials=40)   # 중간
        alloc.observe("t1|t1_bb|T0.1", successes=0, trials=40)    # 바닥
        picks = alloc.allocate(budget=20)
        explore = [k for k in picks if not k.endswith("|T0.1")]
        movable = [k for k in explore if k.startswith("t0|")]
        self.assertGreater(len(movable), len(explore) - len(movable),
                           f"탐색 예산이 움직일 수 없는 백본으로 샜다: {explore}")

    def test_turning_the_term_off_restores_the_previous_scores(self):
        off = self._alloc(eta_condition_exploration=0.0)
        off.observe("t0|t0_bb|T0.1", successes=20, trials=40)
        self.assertEqual(off.exploration_bonus("t0|t0_bb|T0.3"), 0.0)

    def test_without_a_reference_condition_nothing_counts_as_exploration(self):
        alloc = self._alloc(reference_condition=None)
        alloc.observe("t0|t0_bb|T0.1", successes=20, trials=40)
        self.assertEqual(alloc.exploration_bonus("t0|t0_bb|T0.3"), 0.0)

    def test_an_unobserved_backbone_is_treated_as_movable(self):
        """아직 안 본 백본을 바닥이라고 가정하면 영영 안 보게 된다."""
        alloc = self._alloc()
        self.assertGreater(alloc.exploration_bonus("t0|t0_bb|T0.3"), 0.0)

    def test_the_policy_records_why_it_spent_on_a_condition(self):
        alloc = self._alloc()
        alloc.observe("t0|t0_bb|T0.1", successes=20, trials=40)
        parts = alloc.score_parts("t0|t0_bb|T0.3")
        for key in ("posterior_mean", "uncertainty", "diversity", "cost",
                    "condition_exploration", "movability"):
            self.assertIn(key, parts)


class ProbeDrivenMovabilityTests(unittest.TestCase):
    """movability 의 p 는 새 타겟에서 얻을 수 있는 정보에서만 나와야 한다.

    개발 데이터에서는 백본마다 baseline yield 를 56 서열까지 돌려서 알고 있다.
    그 값을 정책에 넣으면 새 타겟에서는 존재하지 않는 정보를 쓰는 것이고,
    "compute 를 아꼈다" 는 주장이 무너진다.

    실제 순서:
        Gate 0 prior -> 초기 4-8 probe -> p_hat, uncertainty
        -> movability -> 다음 계산(온도 / 서열 추가 / 새 백본 / AF2) 선택
    """

    def _arms(self):
        return [
            Arm(target_id="t0", backbone_id="bb", condition=c, cost_seconds=180.0)
            for c in ("T0.05", "T0.1", "T0.2", "T0.3")
        ]

    def test_a_fresh_allocator_has_no_baseline_yield_to_lean_on(self):
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        state = alloc.probe_state("t0", "bb")
        self.assertEqual(state["n_observed"], 0)
        self.assertEqual(state["source"], "prior_only")

    def test_after_a_probe_the_estimate_comes_from_the_probe(self):
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        alloc.observe("t0|bb|T0.1", successes=3, trials=8)
        state = alloc.probe_state("t0", "bb")
        self.assertEqual(state["n_observed"], 8)
        self.assertEqual(state["source"], "probe")
        self.assertGreater(state["movability"], 0.5)

    def test_the_policy_refuses_to_take_an_externally_supplied_true_yield(self):
        """개발 데이터의 baseline yield 를 정책에 주입하지 못하게 막는다."""
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        with self.assertRaises(TypeError):
            alloc.set_backbone_true_yield("t0", "bb", 0.5)

    def test_the_next_action_is_chosen_from_probe_state_not_from_labels(self):
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        alloc.observe("t0|bb|T0.1", successes=4, trials=8)
        action = alloc.next_action("t0", "bb")
        self.assertIn(action["action"], {
            "probe_more_sequences", "explore_generation_condition",
            "verify_with_af2", "abandon_backbone",
        })
        self.assertIn("p_hat", action)
        self.assertIn("movability", action)

    def test_a_backbone_that_probes_all_zero_is_not_given_condition_budget(self):
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        alloc.observe("t0|bb|T0.1", successes=0, trials=8)
        action = alloc.next_action("t0", "bb")
        self.assertNotEqual(action["action"], "explore_generation_condition")

    def test_a_mid_yield_probe_earns_condition_exploration(self):
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        alloc.observe("t0|bb|T0.1", successes=4, trials=8)
        self.assertEqual(alloc.next_action("t0", "bb")["action"],
                         "explore_generation_condition")

    def test_a_thin_probe_asks_for_more_sequences_before_deciding(self):
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        alloc.observe("t0|bb|T0.1", successes=1, trials=2)
        self.assertEqual(alloc.next_action("t0", "bb")["action"], "probe_more_sequences")

    def test_the_minimum_probe_size_is_declared(self):
        from rapid_sr.allocation import MIN_PROBE_SEQUENCES

        self.assertGreaterEqual(MIN_PROBE_SEQUENCES, 4)
        self.assertLessEqual(MIN_PROBE_SEQUENCES, 8)

    def test_the_action_records_what_information_it_used(self):
        """새 타겟에서 쓸 수 없는 정보가 섞였는지 나중에 검증할 수 있어야 한다."""
        from rapid_sr.allocation import HierarchicalAllocator as H

        alloc = H(self._arms(), reference_condition="T0.1")
        alloc.observe("t0|bb|T0.1", successes=4, trials=8)
        action = alloc.next_action("t0", "bb")
        self.assertEqual(sorted(action["information_used"]),
                         ["gate0_prior", "observed_probes"])
