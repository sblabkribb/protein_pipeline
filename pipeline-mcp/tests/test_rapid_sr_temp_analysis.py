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


class StoppingRuleTests(unittest.TestCase):
    def test_clear_effect_and_narrow_interval_stops(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({"ci95": [0.05, 0.12], "excludes_zero": True}),
            "stop_effect_confirmed")

    def test_significant_but_wide_interval_adds_more(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({"ci95": [0.01, 0.40], "excludes_zero": True}),
            "add_second_half")

    def test_null_but_precise_stops_without_more_af2(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({"ci95": [-0.04, 0.04], "excludes_zero": False}),
            "stop_no_effect")

    def test_null_and_wide_adds_more(self):
        module = _load()
        self.assertEqual(
            module.decide_next_step({"ci95": [-0.25, 0.25], "excludes_zero": False}),
            "add_second_half")

    def test_missing_interval_adds_more(self):
        module = _load()
        self.assertEqual(module.decide_next_step({"ci95": None}), "add_second_half")


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
