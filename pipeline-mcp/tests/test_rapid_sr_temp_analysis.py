from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "transcoder" / "11_temperature_af2_analysis.py"


def _load():
    spec = importlib.util.spec_from_file_location("temp_analysis", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AnnotateTests(unittest.TestCase):
    def test_structural_pass_needs_both_plddt_and_rmsd(self):
        module = _load()
        rows = module.annotate([
            {"plddt": "90", "rmsd": "1.0", "soluprot": "0.9"},
            {"plddt": "90", "rmsd": "3.0", "soluprot": "0.9"},
            {"plddt": "70", "rmsd": "1.0", "soluprot": "0.9"},
            {"plddt": "90", "rmsd": "", "soluprot": "0.9"},
        ])
        self.assertEqual(rows[0]["_structural"], 1.0)
        self.assertEqual(rows[1]["_structural"], 0.0)
        self.assertEqual(rows[2]["_structural"], 0.0)
        self.assertIsNone(rows[3]["_structural"])

    def test_joint_requires_soluprot_too(self):
        module = _load()
        rows = module.annotate([
            {"plddt": "90", "rmsd": "1.0", "soluprot": "0.9"},
            {"plddt": "90", "rmsd": "1.0", "soluprot": "0.2"},
        ])
        self.assertEqual(rows[0]["_joint"], 1.0)
        self.assertEqual(rows[1]["_joint"], 0.0)


class UncertaintyDiagnosisTests(unittest.TestCase):
    def test_pure_sampling_noise_is_called_sequence_limited(self):
        """백본별 진짜 차이가 없고 흔들림이 전부 이항 표집이면 서열을 늘려야 한다."""
        module = _load()
        import numpy as np
        rng = np.random.default_rng(0)
        n = 8
        refs = [0.5] * 20
        alts = [0.5] * 20
        # 관측 차이를 표집 분산과 같은 크기로 만든다
        sd = (2 * 0.25 / n) ** 0.5
        diffs = list(rng.normal(0.0, sd, size=20))
        out = module.diagnose_uncertainty(diffs, refs, alts, n)
        self.assertEqual(out["verdict"], "sequence_limited")
        self.assertLess(out["fraction_backbone"], 0.5)

    def test_large_between_backbone_spread_is_backbone_limited(self):
        module = _load()
        diffs = [-0.6, -0.4, -0.1, 0.0, 0.2, 0.5, 0.7, 0.9]
        refs = [0.5] * 8
        alts = [0.5] * 8
        out = module.diagnose_uncertainty(diffs, refs, alts, 8)
        self.assertEqual(out["verdict"], "backbone_limited")
        self.assertGreater(out["fraction_backbone"], 0.5)

    def test_too_few_backbones_is_unknown_not_guessed(self):
        module = _load()
        self.assertEqual(module.diagnose_uncertainty([0.1, 0.2], [0.5, 0.5], [0.6, 0.7], 8)["verdict"],
                         "unknown")

    def test_more_sequences_shrinks_the_sampling_component(self):
        module = _load()
        diffs = [0.1, -0.1, 0.05, -0.05, 0.0, 0.2, -0.2, 0.1]
        few = module.diagnose_uncertainty(diffs, [0.5] * 8, [0.5] * 8, 4)
        many = module.diagnose_uncertainty(diffs, [0.5] * 8, [0.5] * 8, 64)
        self.assertLess(few["fraction_backbone"], many["fraction_backbone"])


class StoppingRuleTests(unittest.TestCase):
    def test_clear_effect_and_narrow_interval_stops(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({"ci95": [0.05, 0.12], "excludes_zero": True}),
            "stop_effect_confirmed")

    def test_null_but_precise_stops_without_more_af2(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({"ci95": [-0.04, 0.04], "excludes_zero": False}),
            "stop_no_effect")

    def test_wide_interval_from_sequence_noise_adds_the_second_half(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({
                "ci95": [0.01, 0.40], "excludes_zero": True,
                "uncertainty": {"verdict": "sequence_limited"},
            }),
            "add_second_half")

    def test_wide_interval_from_backbone_spread_expands_backbones_instead(self):
        """백본이 병목이면 같은 백본에서 서열을 더 뽑아도 구간이 안 좁아진다."""
        module = _load()
        self.assertEqual(
            module.decide_next_step({
                "ci95": [-0.25, 0.25], "excludes_zero": False,
                "uncertainty": {"verdict": "backbone_limited"},
            }),
            "expand_backbones")

    def test_unknown_diagnosis_prefers_expanding_backbones(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({
                "ci95": [-0.3, 0.3], "excludes_zero": False,
                "uncertainty": {"verdict": "unknown"},
            }),
            "expand_backbones")

    def test_missing_interval_expands_backbones(self):
        module = _load()
        self.assertEqual(module.decide_next_step({"ci95": None}), "expand_backbones")


class PairedDifferenceTests(unittest.TestCase):
    def test_pairs_only_backbones_present_at_both_temperatures(self):
        module = _load()
        rows = []
        for b in range(5):
            for t, v in (("0.1", 0.2), ("0.3", 0.6)):
                for _ in range(4):
                    rows.append({"backbone_key": f"bb{b}", "temperature": t, "_structural": v})
        rows.append({"backbone_key": "lonely", "temperature": "0.3", "_structural": 1.0})
        out = module.paired_yield_difference(rows, "0.3", "_structural")
        self.assertEqual(out["n_backbones_paired"], 5)
        self.assertAlmostEqual(out["point"], 0.4, places=4)


if __name__ == "__main__":
    unittest.main()


class SourceStratificationTests(unittest.TestCase):
    def _rows(self, sources):
        rows = []
        for src in sources:
            for b in range(4):
                for t in ("0.1", "0.3"):
                    for _ in range(6):
                        rows.append({
                            "backbone_key": f"{src}_bb{b}", "backbone_source": src,
                            "temperature": t, "_structural": 0.5, "_joint": 0.5,
                        })
        return rows

    def test_single_source_reports_unavailable_rather_than_pretending(self):
        module = _load()
        out = module.stratify_by_source(self._rows(["target"]), ["0.1", "0.3"])
        self.assertFalse(out["available"])
        self.assertIn("확장", out["note"])

    def test_multiple_sources_are_analysed_separately(self):
        module = _load()
        out = module.stratify_by_source(self._rows(["target", "rfd3"]), ["0.1", "0.3"])
        self.assertTrue(out["available"])
        self.assertEqual(set(out["per_source"]), {"target", "rfd3"})
        self.assertEqual(out["per_source"]["rfd3"]["n_backbones"], 4)

    def test_defaults_missing_source_to_target(self):
        module = _load()
        rows = self._rows(["rfd3"])
        for row in rows[:12]:
            row.pop("backbone_source")
        out = module.stratify_by_source(rows, ["0.1", "0.3"])
        self.assertEqual(set(out["sources"]), {"target", "rfd3"})


class SaturationTests(unittest.TestCase):
    """포화된 백본은 온도 질문에 답하지 못한다.

    structural_yield 가 모든 온도에서 0.000 이거나 1.000 인 백본은 차이가
    구조적으로 0 이다. 그 0 을 "온도가 영향 없다는 증거" 로 세면, 답을 못 하는
    실험이 답을 한 것처럼 보인다. 실제로 480 폴드 결과에서 15 개 백본 중 12 개가
    포화였고(9 개는 전부 0, 3 개는 전부 1), 판정은 stop_no_effect 로 나왔다.
    """

    def test_a_backbone_at_the_floor_in_every_condition_is_saturated(self):
        self.assertTrue(_load().is_saturated([0.0, 0.0, 0.0, 0.0]))

    def test_a_backbone_at_the_ceiling_in_every_condition_is_saturated(self):
        self.assertTrue(_load().is_saturated([1.0, 1.0, 1.0, 1.0]))

    def test_a_backbone_that_moves_at_all_is_informative(self):
        self.assertFalse(_load().is_saturated([1.0, 0.875, 1.0, 1.0]))

    def test_a_constant_mid_value_is_not_saturated(self):
        """0.5 에 붙어 있는 것은 바닥/천장이 아니라 그냥 변화가 없는 것이다."""
        self.assertFalse(_load().is_saturated([0.5, 0.5, 0.5, 0.5]))

    def test_informative_clusters_are_counted_separately_from_total(self):
        per_backbone = {
            "flat_low": [0.0, 0.0], "flat_high": [1.0, 1.0],
            "moves": [0.75, 0.5],
        }
        counts = _load().count_informative(per_backbone)
        self.assertEqual(counts["n_backbones"], 3)
        self.assertEqual(counts["n_informative"], 1)
        self.assertEqual(counts["n_saturated"], 2)

    def test_a_verdict_needs_enough_informative_clusters_not_just_clusters(self):
        entry = {
            "ci95": [-0.05, 0.0], "excludes_zero": False,
            "uncertainty": {"verdict": "sequence_limited"},
            "saturation": {"n_backbones": 15, "n_informative": 3, "n_saturated": 12},
        }
        self.assertEqual(_load().decide_next_step(entry), "expand_backbones")

    def test_the_same_interval_stops_when_the_clusters_are_informative(self):
        entry = {
            "ci95": [-0.05, 0.0], "excludes_zero": False,
            "uncertainty": {"verdict": "sequence_limited"},
            "saturation": {"n_backbones": 15, "n_informative": 15, "n_saturated": 0},
        }
        self.assertEqual(_load().decide_next_step(entry), "stop_no_effect")

    def test_saturation_is_ignored_when_it_was_not_measured(self):
        """예전 리포트에는 saturation 항목이 없다. 없다고 판정을 바꾸지 않는다."""
        entry = {"ci95": [-0.05, 0.0], "excludes_zero": False,
                 "uncertainty": {"verdict": "sequence_limited"}}
        self.assertEqual(_load().decide_next_step(entry), "stop_no_effect")


class BoundaryIntervalTests(unittest.TestCase):
    """구간 끝이 정확히 0 인 것과 0 을 품는 것은 다르다.

    백본별 차이가 1/8 격자 위에 있으면 부트스트랩 분포도 격자 위에 놓인다.
    T=0.2 의 97.5 분위수는 정확히 0.0000 이었지만 0 보다 큰 질량은 0.000 이었다.
    "CI 가 0 을 포함하므로 효과 없음" 은 그 경우 틀린 독해다.
    """

    def test_an_interval_touching_zero_from_below_is_not_a_null_result(self):
        entry = {"ci95": [-0.0917, 0.0], "excludes_zero": False,
                 "prob_above_zero": 0.0, "prob_below_zero": 0.966,
                 "uncertainty": {"verdict": "sequence_limited"}}
        self.assertNotEqual(_load().decide_next_step(entry), "stop_no_effect")

    def test_an_interval_with_real_mass_on_both_sides_is_a_null_result(self):
        entry = {"ci95": [-0.0333, 0.0167], "excludes_zero": False,
                 "prob_above_zero": 0.184, "prob_below_zero": 0.612,
                 "uncertainty": {"verdict": "sequence_limited"}}
        self.assertEqual(_load().decide_next_step(entry), "stop_no_effect")

    def test_tail_probabilities_are_reported_when_a_bootstrap_ran(self):
        rows = _rows_for_two_temperatures()
        result = _load().paired_yield_difference(rows, "0.2", "_structural")
        self.assertIn("prob_above_zero", result)
        self.assertIn("prob_below_zero", result)
        total = result["prob_above_zero"] + result["prob_below_zero"]
        self.assertLessEqual(total, 1.0 + 1e-9)


def _rows_for_two_temperatures():
    rows = []
    for index in range(6):
        for temp, plddt in (("0.1", 95.0), ("0.2", 95.0 if index < 4 else 50.0)):
            for seq in range(4):
                rows.append({
                    "backbone_key": f"bb{index}", "temperature": temp,
                    "_structural": 1.0 if plddt > 85 else 0.0,
                    "_joint": 1.0 if plddt > 85 else 0.0,
                    "_soluprot": 0.7,
                })
    return rows
