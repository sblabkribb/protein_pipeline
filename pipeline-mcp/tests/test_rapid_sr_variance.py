from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.variance import nested_variance_components


class VarianceTests(unittest.TestCase):
    def test_all_variance_at_backbone_level(self):
        rows = [
            {"target": f"t{t}", "backbone": f"t{t}b{b}", "value": float(b)}
            for t in range(3) for b in range(4) for _ in range(5)
        ]
        out = nested_variance_components(rows)
        self.assertGreater(out["icc_backbone"], 0.9)
        self.assertLess(out["var_design"], 1e-9)

    def test_all_variance_at_design_level(self):
        rows = [
            {"target": f"t{t}", "backbone": f"t{t}b{b}", "value": v}
            for t in range(3) for b in range(4) for v in (0.0, 1.0, 2.0, 3.0, 4.0)
        ]
        out = nested_variance_components(rows)
        self.assertLess(out["icc_backbone"], 0.1)
        self.assertGreater(out["var_design"], 1.0)

    def test_components_are_non_negative_and_sum_to_total(self):
        rows = [
            {"target": "t0", "backbone": "b0", "value": 1.0},
            {"target": "t0", "backbone": "b0", "value": 2.0},
            {"target": "t0", "backbone": "b1", "value": 5.0},
            {"target": "t1", "backbone": "b2", "value": 9.0},
            {"target": "t1", "backbone": "b2", "value": 9.5},
        ]
        out = nested_variance_components(rows)
        for key in ("var_target", "var_backbone", "var_design"):
            self.assertGreaterEqual(out[key], 0.0)
        self.assertAlmostEqual(
            out["var_total"],
            out["var_target"] + out["var_backbone"] + out["var_design"],
            places=6,
        )

    def test_bootstrap_ci_brackets_the_point_estimate(self):
        rows = [
            {"target": f"t{t}", "backbone": f"t{t}b{b}", "value": b + 0.1 * k}
            for t in range(4) for b in range(5) for k in range(6)
        ]
        out = nested_variance_components(rows, n_boot=50, seed=1)
        low, high = out["icc_backbone_ci95"]
        self.assertLessEqual(low, out["icc_backbone"])
        self.assertLessEqual(out["icc_backbone"], high)
        self.assertEqual(out["n_boot"], 50)

    def test_counts_are_reported_separately(self):
        rows = [
            {"target": "t0", "backbone": "t0b0", "value": 1.0},
            {"target": "t0", "backbone": "t0b0", "value": 2.0},
            {"target": "t0", "backbone": "t0b1", "value": 3.0},
        ]
        out = nested_variance_components(rows)
        self.assertEqual(out["n_rows"], 3)
        self.assertEqual(out["n_backbones"], 2)
        self.assertEqual(out["n_targets"], 1)

    def test_empty_input_does_not_crash(self):
        out = nested_variance_components([])
        self.assertEqual(out["n_rows"], 0)
        self.assertEqual(out["icc_backbone"], 0.0)


if __name__ == "__main__":
    unittest.main()
