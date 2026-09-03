from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from rapid_sr.gate0_request import GATE0_ARMS, build_gate0_request

PDB = "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"


class Gate0RequestTests(unittest.TestCase):
    def test_af2_runs_on_all_candidates(self):
        req = build_gate0_request(PDB, "rfd3", seed=3)
        self.assertEqual(req.af2_max_candidates_per_tier, 0)
        self.assertEqual(req.soluprot_cutoff, 0.0)
        self.assertEqual(req.af2_top_k, 0)

    def test_mpnn_settings_identical_across_arms(self):
        reqs = [build_gate0_request(PDB, arm, seed=3) for arm in GATE0_ARMS]
        self.assertEqual(len({r.num_seq_per_tier for r in reqs}), 1)
        self.assertEqual(len({r.sampling_temp for r in reqs}), 1)
        self.assertEqual(len({r.seed for r in reqs}), 1)
        self.assertEqual(len({r.batch_size for r in reqs}), 1)

    def test_arms_differ_only_in_backbone_source(self):
        rfd3 = build_gate0_request(PDB, "rfd3", seed=3)
        bioemu = build_gate0_request(PDB, "bioemu", seed=3)
        target = build_gate0_request(PDB, "target", seed=3)
        self.assertTrue(rfd3.rfd3_use)
        self.assertFalse(rfd3.bioemu_use)
        self.assertTrue(bioemu.bioemu_use)
        self.assertFalse(bioemu.rfd3_use)
        self.assertFalse(target.rfd3_use)
        self.assertFalse(target.bioemu_use)

    def test_stops_after_af2_and_skips_optional_stages(self):
        req = build_gate0_request(PDB, "rfd3", seed=3)
        self.assertEqual(req.stop_after, "af2")
        self.assertFalse(req.relax_enabled)
        self.assertFalse(req.novelty_enabled)
        self.assertFalse(req.wt_compare)

    def test_unknown_arm_rejected(self):
        with self.assertRaises(ValueError):
            build_gate0_request(PDB, "esmfold", seed=1)

    def test_sequences_per_backbone_comes_from_protocol(self):
        from rapid_sr.protocol import GATE0_SEQUENCES_PER_BACKBONE
        req = build_gate0_request(PDB, "target", seed=0)
        self.assertEqual(req.num_seq_per_tier, GATE0_SEQUENCES_PER_BACKBONE)

    def test_single_tier_is_requested(self):
        req = build_gate0_request(PDB, "rfd3", seed=0)
        self.assertEqual(req.conservation_tiers, [0.5])

    def test_af2_budget_per_run_is_bounded(self):
        from rapid_sr.protocol import protocol_fingerprint
        # 백본 수 x 서열 수 x tier 수 = run 당 AF2 호출 수
        self.assertEqual(protocol_fingerprint()["af2_calls_per_run"], 100)


if __name__ == "__main__":
    unittest.main()
