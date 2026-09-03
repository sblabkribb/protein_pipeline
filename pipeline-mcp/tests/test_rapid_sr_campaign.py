from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "transcoder" / "04d_run_gate0_campaign.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_gate0_campaign", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CampaignTests(unittest.TestCase):
    def test_wave_plan_accumulates_backbones(self):
        module = _load()
        waves = module.plan_waves(existing_backbones=68, wave_sizes=[32, 64, 128])
        self.assertEqual([w["wave_index"] for w in waves], [1, 2, 3])
        self.assertEqual([w["cumulative_backbones"] for w in waves], [100, 164, 292])

    def test_run_id_is_deterministic_and_distinct(self):
        module = _load()
        first = module.build_run_id("2wejA00", "rfd3", wave=1)
        self.assertEqual(first, module.build_run_id("2wejA00", "rfd3", wave=1))
        self.assertNotEqual(first, module.build_run_id("2wejA00", "target", wave=1))
        self.assertNotEqual(first, module.build_run_id("2wejA00", "rfd3", wave=2))
        self.assertTrue(first.startswith("gate0_"))

    def test_manifest_pins_protocol_fingerprint(self):
        module = _load()
        manifest = module.build_manifest(wave=1, targets=["2wejA00"], arms=["rfd3"], seed=0)
        self.assertEqual(manifest["protocol"]["thresholds"]["plddt_min"], 85.0)
        self.assertEqual(manifest["protocol"]["sequences_per_backbone"], 20)
        self.assertEqual(manifest["protocol"]["af2_calls_per_run"], 100)
        self.assertEqual(manifest["wave"], 1)

    def test_plan_runs_skips_targets_without_pdb(self):
        module = _load()
        planned = module.plan_runs(
            targets=["aaa", "bbb"], arms=["rfd3"], wave=1,
            pdb_lookup=lambda t: Path(f"/x/{t}.pdb") if t == "aaa" else None,
        )
        self.assertEqual([item["target"] for item in planned], ["aaa"])

    def test_plan_runs_is_arm_major_per_target(self):
        module = _load()
        planned = module.plan_runs(
            targets=["aaa"], arms=["target", "rfd3"], wave=2,
            pdb_lookup=lambda t: Path(f"/x/{t}.pdb"),
        )
        self.assertEqual([item["arm"] for item in planned], ["target", "rfd3"])
        self.assertEqual(planned[0]["run_id"], "gate0_w2_target_aaa")

    def test_unknown_arm_is_rejected_early(self):
        module = _load()
        with self.assertRaises(ValueError):
            module.plan_runs(targets=["aaa"], arms=["nope"], wave=1,
                             pdb_lookup=lambda t: Path("/x/a.pdb"))


if __name__ == "__main__":
    unittest.main()
