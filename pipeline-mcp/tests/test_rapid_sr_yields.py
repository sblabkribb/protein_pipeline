from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.protocol import GATE0_THRESHOLDS, protocol_fingerprint
from rapid_sr.records import DesignRecord
from rapid_sr.yields import backbone_yields


def _rec(bid, solu, plddt, rmsd, regime="af2_all_candidates", n=[0]):
    n[0] += 1
    return DesignRecord(
        design_id=f"{bid}:{n[0]}", target_id="t1", tier="30",
        backbone_id=bid, backbone_source="rfd3", sequence="MKT",
        soluprot=solu, plddt_af2=plddt, rmsd_af2=rmsd, label_regime=regime,
    )


class BackboneYieldTests(unittest.TestCase):
    def test_three_yields_computed_separately(self):
        recs = [
            _rec("bb1", 0.9, 90.0, 1.0),
            _rec("bb1", 0.9, 70.0, 1.0),
            _rec("bb1", 0.2, 90.0, 1.0),
            _rec("bb1", 0.2, 70.0, 5.0),
        ]
        out = backbone_yields(recs)["bb1"]
        self.assertAlmostEqual(out["soluprot_pass_yield"], 0.5)
        self.assertAlmostEqual(out["af2_structural_pass_yield"], 0.5)
        self.assertAlmostEqual(out["joint_pass_yield"], 0.25)
        self.assertEqual(out["n_sequences"], 4)

    def test_rmsd_gate_is_part_of_structural_pass(self):
        out = backbone_yields([_rec("bb2", 0.9, 90.0, 3.0)])["bb2"]
        self.assertAlmostEqual(out["af2_structural_pass_yield"], 0.0)
        self.assertAlmostEqual(out["joint_pass_yield"], 0.0)

    def test_missing_plddt_excluded_from_structural_denominator(self):
        recs = [_rec("bb3", 0.9, 90.0, 1.0), _rec("bb3", 0.9, None, None)]
        out = backbone_yields(recs)["bb3"]
        self.assertEqual(out["n_sequences"], 2)
        self.assertEqual(out["n_sequences_with_af2"], 1)
        self.assertAlmostEqual(out["af2_structural_pass_yield"], 1.0)

    def test_filtered_regime_is_flagged_as_biased(self):
        out = backbone_yields(
            [_rec("bb4", 0.9, 90.0, 1.0, regime="af2_after_soluprot_filter")]
        )["bb4"]
        self.assertEqual(out["label_regime"], "af2_after_soluprot_filter")
        self.assertTrue(out["structural_yield_is_biased"])

    def test_unbiased_regime_is_not_flagged(self):
        out = backbone_yields([_rec("bb5", 0.9, 90.0, 1.0)])["bb5"]
        self.assertFalse(out["structural_yield_is_biased"])

    def test_mixed_regime_within_backbone_is_flagged(self):
        recs = [
            _rec("bb6", 0.9, 90.0, 1.0),
            _rec("bb6", 0.9, 90.0, 1.0, regime="af2_after_soluprot_filter"),
        ]
        out = backbone_yields(recs)["bb6"]
        self.assertEqual(out["label_regime"], "mixed")
        self.assertTrue(out["structural_yield_is_biased"])

    def test_yields_are_none_when_no_labels(self):
        out = backbone_yields([_rec("bb7", None, None, None)])["bb7"]
        self.assertIsNone(out["soluprot_pass_yield"])
        self.assertIsNone(out["af2_structural_pass_yield"])
        self.assertIsNone(out["joint_pass_yield"])

    def test_thresholds_match_documented_defaults(self):
        self.assertEqual(GATE0_THRESHOLDS["soluprot_min"], 0.5)
        self.assertEqual(GATE0_THRESHOLDS["plddt_min"], 85.0)
        self.assertEqual(GATE0_THRESHOLDS["rmsd_max"], 2.0)

    def test_fingerprint_carries_thresholds_and_sequence_count(self):
        fp = protocol_fingerprint()
        self.assertEqual(fp["thresholds"]["plddt_min"], 85.0)
        self.assertEqual(fp["sequences_per_backbone"], 40)
        self.assertIn("mpnn_settings", fp)


if __name__ == "__main__":
    unittest.main()
