"""제품 런타임 할당 정책이 논문 재현용 사본과 같은 결정을 내는지 고정한다.

두 사본이 있는 이유는 sequence_liabilities 와 같다. 분석은 서버 패키지 없이
돌아야 하고 (scripts/transcoder/rapid_sr), 제품은 scripts/ 에 의존하면 안 된다.
사본이 갈라지면 논문의 숫자와 제품의 행동이 달라지므로 여기서 묶는다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp import allocation as runtime  # noqa: E402
from pipeline_mcp.allocation import allocation_next_action  # noqa: E402
from rapid_sr import allocation as repro  # noqa: E402


def _decisions(module, observations):
    arms = [module.Arm(target_id="T", backbone_id=f"B{i}", condition="T0.1")
            for i in range(4)]
    allocator = module.HierarchicalAllocator(arms, seed=0)
    allocator.set_target_prior("T", mean=0.42, strength=3.0)
    for backbone, successes, trials in observations:
        allocator.observe(f"T|{backbone}|T0.1", successes=successes, trials=trials)
    return [allocator.next_action("T", f"B{i}") for i in range(4)]


class TestCopiesAgree(unittest.TestCase):
    def test_constants_match(self):
        for name in ("DEFAULT_PRIOR_MEAN", "DEFAULT_PRIOR_STRENGTH",
                     "MIN_PROBE_SEQUENCES", "MOVABILITY_FLOOR",
                     "DEFAULT_ETA_CONDITION_EXPLORATION",
                     "DEFAULT_POOLING_STRENGTH"):
            self.assertEqual(getattr(runtime, name), getattr(repro, name), name)

    def test_movability_matches(self):
        for p in (0.0, 0.05, 0.2, 0.5, 0.8, 0.95, 1.0):
            self.assertAlmostEqual(runtime.movability(p), repro.movability(p), places=12)

    def test_same_decisions(self):
        observations = [("B0", 0, 8), ("B1", 4, 8), ("B2", 2, 2), ("B3", 8, 8)]
        for a, b in zip(_decisions(runtime, observations),
                        _decisions(repro, observations)):
            self.assertEqual(a, b)


class TestPolicyBehaviour(unittest.TestCase):
    def test_thin_probe_asks_for_more(self):
        state = _decisions(runtime, [("B0", 2, 2)])[0]
        self.assertEqual(state["action"], "probe_more_sequences")

    def test_dead_backbone_is_abandoned(self):
        # 형제가 없으면 0/24 는 바닥에 붙는다. 풀링이 끌어올리지 않는다.
        arms = [runtime.Arm(target_id="T", backbone_id="B0", condition="T0.1")]
        allocator = runtime.HierarchicalAllocator(arms, seed=0)
        allocator.set_target_prior("T", mean=0.42, strength=3.0)
        allocator.observe("T|B0|T0.1", successes=0, trials=24)
        self.assertEqual(allocator.next_action("T", "B0")["action"],
                         "abandon_backbone")

    def test_saturated_high_backbone_goes_to_verification(self):
        arms = [runtime.Arm(target_id="T", backbone_id="B0", condition="T0.1")]
        allocator = runtime.HierarchicalAllocator(arms, seed=0)
        allocator.set_target_prior("T", mean=0.42, strength=3.0)
        allocator.observe("T|B0|T0.1", successes=24, trials=24)
        self.assertEqual(allocator.next_action("T", "B0")["action"],
                         "verify_with_af2")

    def test_true_yield_cannot_be_injected(self):
        arms = [runtime.Arm(target_id="T", backbone_id="B0", condition="T0.1")]
        allocator = runtime.HierarchicalAllocator(arms, seed=0)
        with self.assertRaises(TypeError):
            allocator.set_backbone_true_yield("T", "B0", 1.0)


class TestToolEntryPoint(unittest.TestCase):
    def test_requires_target_and_backbones(self):
        self.assertIn("error", allocation_next_action({"backbones": ["B0"]}))
        self.assertIn("error", allocation_next_action({"target_id": "T"}))

    def test_rejects_successes_above_trials(self):
        out = allocation_next_action({
            "target_id": "T", "backbones": ["B0"],
            "observations": [{"backbone_id": "B0", "trials": 2, "successes": 5}],
        })
        self.assertIn("error", out)

    def test_unknown_backbone_is_reported_not_silently_dropped(self):
        out = allocation_next_action({
            "target_id": "T", "backbones": ["B0"],
            "observations": [{"backbone_id": "ghost", "trials": 4, "successes": 1}],
        })
        self.assertEqual(len(out["observations_ignored"]), 1)
        self.assertEqual(out["observations_applied"], [])

    def test_records_what_information_it_used(self):
        out = allocation_next_action({"target_id": "T", "backbones": ["B0"],
                                      "prior_mean": 0.42})
        self.assertEqual(out["prior"]["source"], "gate0")
        self.assertIn("baseline yield (새 타겟에 없다)",
                      out["policy"]["information_not_used"])

    def test_prior_absent_is_labelled_uninformative(self):
        out = allocation_next_action({"target_id": "T", "backbones": ["B0"]})
        self.assertEqual(out["prior"]["source"], "uninformative_default")


if __name__ == "__main__":
    unittest.main()
