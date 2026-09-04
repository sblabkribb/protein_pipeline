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
