from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "transcoder" / "04f_af2_msa_mode_probe.py"


def _load():
    spec = importlib.util.spec_from_file_location("af2_msa_mode_probe", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProbeSummaryTests(unittest.TestCase):
    def test_speedup_is_baseline_over_fast(self):
        module = _load()
        out = module.summarise([
            {"name": "full_dbs", "status": "ok", "elapsed_s": 600.0},
            {"name": "single_sequence", "status": "ok", "elapsed_s": 60.0},
        ])
        self.assertEqual(out["speedup"], 10.0)
        self.assertEqual(out["saved_s"], 540.0)

    def test_failed_arm_suppresses_the_ratio(self):
        module = _load()
        out = module.summarise([
            {"name": "full_dbs", "status": "failed", "elapsed_s": 5.0},
            {"name": "single_sequence", "status": "ok", "elapsed_s": 60.0},
        ])
        self.assertNotIn("speedup", out)

    def test_zero_elapsed_does_not_divide_by_zero(self):
        module = _load()
        out = module.summarise([
            {"name": "full_dbs", "status": "ok", "elapsed_s": 60.0},
            {"name": "single_sequence", "status": "ok", "elapsed_s": 0.0},
        ])
        self.assertIsNone(out["speedup"])

    def test_single_sequence_flag_matches_worker_contract(self):
        module = _load()
        self.assertEqual(module.SINGLE_SEQUENCE_FLAGS, "--msa-mode single_sequence")


if __name__ == "__main__":
    unittest.main()


class ProbeAggregateTests(unittest.TestCase):
    def test_aggregate_averages_each_arm(self):
        module = _load()
        reps = [
            {"arms": [
                {"name": "full_dbs", "status": "ok", "elapsed_s": 90.0, "best_plddt": 87.0},
                {"name": "single_sequence", "status": "ok", "elapsed_s": 60.0, "best_plddt": 66.0},
            ]},
            {"arms": [
                {"name": "full_dbs", "status": "ok", "elapsed_s": 110.0, "best_plddt": 89.0},
                {"name": "single_sequence", "status": "ok", "elapsed_s": 80.0, "best_plddt": 70.0},
            ]},
        ]
        out = module.aggregate(reps)
        self.assertEqual(out["per_arm"]["full_dbs"]["mean_elapsed_s"], 100.0)
        self.assertEqual(out["per_arm"]["single_sequence"]["mean_elapsed_s"], 70.0)
        self.assertEqual(out["speedup"], round(100.0 / 70.0, 2))

    def test_aggregate_reports_plddt_cost_of_dropping_msa(self):
        module = _load()
        reps = [{"arms": [
            {"name": "full_dbs", "status": "ok", "elapsed_s": 90.0, "best_plddt": 87.0},
            {"name": "single_sequence", "status": "ok", "elapsed_s": 60.0, "best_plddt": 66.0},
        ]}]
        out = module.aggregate(reps)
        self.assertEqual(out["plddt_delta"], -21.0)

    def test_aggregate_skips_failed_arms(self):
        module = _load()
        reps = [{"arms": [
            {"name": "full_dbs", "status": "failed", "elapsed_s": 5.0},
            {"name": "single_sequence", "status": "ok", "elapsed_s": 60.0, "best_plddt": 66.0},
        ]}]
        out = module.aggregate(reps)
        self.assertNotIn("speedup", out)
        self.assertEqual(out["per_arm"]["single_sequence"]["n"], 1)
