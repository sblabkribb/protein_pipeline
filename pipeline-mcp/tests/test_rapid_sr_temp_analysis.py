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


class ClusterUnitTests(unittest.TestCase):
    """재표집 단위는 데이터 구조가 정한다.

    1 차 패널은 백본 15 개가 곧 타겟 15 개여서 backbone_key 로 재표집해도 같았다.
    2 차 패널은 한 타겟에서 최대 3 개의 백본을 뽑으므로, 백본으로 재표집하면
    독립 클러스터를 실제보다 많이 세게 된다 - 포화 오류와 같은 종류의 과장이다.
    """

    def _nested_rows(self):
        rows = []
        for target in ("tA", "tB", "tC", "tD"):
            for bb in range(3):
                for temp in ("0.1", "0.2"):
                    for seq in range(4):
                        rows.append({
                            "backbone_key": f"{target}|bb{bb}", "target_id": target,
                            "temperature": temp,
                            "_structural": 1.0 if (temp == "0.1" or seq < 2) else 0.0,
                            "_joint": 1.0 if (temp == "0.1" or seq < 2) else 0.0,
                            "_soluprot": 0.7,
                        })
        return rows

    def test_clustering_by_target_reports_the_target_count(self):
        module = _load()
        result = module.paired_yield_difference(
            self._nested_rows(), "0.2", "_structural", cluster_unit="target_id")
        self.assertEqual(result["n_clusters_resampled"], 4)
        self.assertEqual(result["cluster_unit"], "target_id")

    def test_clustering_by_backbone_reports_the_backbone_count(self):
        module = _load()
        result = module.paired_yield_difference(
            self._nested_rows(), "0.2", "_structural", cluster_unit="backbone_key")
        self.assertEqual(result["n_clusters_resampled"], 12)

    def test_nesting_makes_the_target_interval_wider_than_the_backbone_one(self):
        """중첩을 무시하면 구간이 좁아진다. 좁아지는 쪽이 틀린 쪽이다."""
        module = _load()
        rows = self._nested_rows()
        # 타겟마다 효과 크기를 다르게 만들어 타겟 간 이질성을 넣는다.
        for r in rows:
            if r["target_id"] in ("tB", "tD") and r["temperature"] == "0.2":
                r["_structural"] = 1.0
                r["_joint"] = 1.0
        by_bb = module.paired_yield_difference(rows, "0.2", "_structural",
                                               cluster_unit="backbone_key")
        by_tg = module.paired_yield_difference(rows, "0.2", "_structural",
                                               cluster_unit="target_id")
        width = lambda r: r["ci95"][1] - r["ci95"][0]  # noqa: E731
        self.assertGreaterEqual(width(by_tg), width(by_bb))

    def test_the_default_cluster_unit_is_stated_not_implicit(self):
        module = _load()
        self.assertIn(module.DEFAULT_CLUSTER_UNIT, {"backbone_key", "target_id"})


class PanelScopeTests(unittest.TestCase):
    """중간-yield 패널의 결과는 전체 백본 집단의 평균 효과가 아니다."""

    def test_the_report_carries_an_interpretation_scope(self):
        module = _load()
        report = module.build_report_header(panel="panel2_informative",
                                            cluster_unit="target_id",
                                            selection_scope="mid-yield only")
        self.assertEqual(report["panel"], "panel2_informative")
        self.assertIn("conditional", report["interpretation"].lower())
        self.assertEqual(report["selection_scope"], "mid-yield only")

    def test_a_panel_without_a_stated_scope_says_so(self):
        module = _load()
        report = module.build_report_header(panel="panel1", cluster_unit="backbone_key",
                                            selection_scope="")
        self.assertIn("selection_scope", report)
        self.assertTrue(report["selection_scope_unknown"])


class DominanceTests(unittest.TestCase):
    """조건 하나를 제거하려면 근거의 문턱을 넘어야 한다.

    T=0.2 는 1 차 패널에서 두 primary endpoint 모두 음의 차이였고 0 위의 부트스트랩
    질량이 0.000 이었다. 그러나 정보를 주는 클러스터가 3 개뿐이었으므로 그것만으로
    arm 을 없앨 수는 없다. 제거는 자동이 아니라 명시적 결정이고, 이 함수는 그
    결정에 필요한 조건이 충족됐는지만 답한다.
    """

    def _entry(self, point, above=0.0, informative=12, excludes_zero=False):
        return {
            "point": point, "ci95": [point - 0.05, point + 0.01],
            "excludes_zero": excludes_zero, "prob_above_zero": above,
            "saturation": {"n_informative": informative, "n_backbones": informative},
        }

    def _report(self, **overrides):
        base = {
            "comparisons": {
                "structural_yield@T0.2": self._entry(-0.04),
                "joint_yield@T0.2": self._entry(-0.04),
                "structural_yield@T0.3": self._entry(-0.005, above=0.30),
                "joint_yield@T0.3": self._entry(-0.005, above=0.29),
            },
        }
        base["comparisons"].update(overrides)
        return base

    def test_a_condition_losing_on_both_primaries_is_flagged(self):
        module = _load()
        out = module.condition_dominance(self._report())
        self.assertIn("0.2", out["dominated"])

    def test_a_condition_with_mass_above_zero_is_not_flagged(self):
        module = _load()
        out = module.condition_dominance(self._report())
        self.assertNotIn("0.3", out["dominated"])

    def test_losing_on_only_one_primary_is_not_enough(self):
        module = _load()
        out = module.condition_dominance(self._report(**{
            "joint_yield@T0.2": self._entry(0.01, above=0.6)}))
        self.assertNotIn("0.2", out["dominated"])

    def test_too_few_informative_clusters_blocks_the_flag(self):
        module = _load()
        out = module.condition_dominance(self._report(**{
            "structural_yield@T0.2": self._entry(-0.04, informative=3),
            "joint_yield@T0.2": self._entry(-0.04, informative=3)}))
        self.assertNotIn("0.2", out["dominated"])
        self.assertIn("0.2", out["insufficient_evidence"])

    def test_the_reference_condition_can_never_be_dominated(self):
        module = _load()
        out = module.condition_dominance(self._report())
        self.assertNotIn(module.REFERENCE_T, out["dominated"])

    def test_the_result_never_prunes_by_itself(self):
        """이 함수는 판단만 한다. 제거는 사람이 하는 별도의 결정이다."""
        module = _load()
        out = module.condition_dominance(self._report())
        self.assertFalse(out["pruned"])
        self.assertIn("recommendation", out)

    def test_evidence_is_returned_for_each_verdict(self):
        module = _load()
        out = module.condition_dominance(self._report())
        self.assertIn("0.2", out["evidence"])
        for endpoint in ("structural_yield", "joint_yield"):
            self.assertIn(endpoint, out["evidence"]["0.2"])

    def test_two_panels_must_agree_before_a_condition_is_dominated(self):
        module = _load()
        agree = module.condition_dominance(self._report(), other_panel=self._report())
        self.assertIn("0.2", agree["dominated"])
        disagree = module.condition_dominance(self._report(), other_panel=self._report(**{
            "structural_yield@T0.2": self._entry(0.03, above=0.9)}))
        self.assertNotIn("0.2", disagree["dominated"])
        self.assertIn("0.2", disagree["panels_disagree"])
