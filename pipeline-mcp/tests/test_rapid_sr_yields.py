from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.protocol import GATE0_THRESHOLDS, protocol_fingerprint
from rapid_sr.records import DesignRecord
from rapid_sr.yields import backbone_yields


def _rec(bid, solu, plddt, rmsd, regime="af2_all_candidates", target="t1",
         source="rfd3", n=[0]):
    n[0] += 1
    return DesignRecord(
        design_id=f"{bid}:{n[0]}", target_id=target, tier="30",
        backbone_id=bid, backbone_source=source, sequence="MKT",
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
        out = backbone_yields(recs)["t1|rfd3|bb1"]
        self.assertAlmostEqual(out["soluprot_pass_yield"], 0.5)
        self.assertAlmostEqual(out["af2_structural_pass_yield"], 0.5)
        self.assertAlmostEqual(out["joint_pass_yield"], 0.25)
        self.assertEqual(out["n_sequences"], 4)

    def test_rmsd_gate_is_part_of_structural_pass(self):
        out = backbone_yields([_rec("bb2", 0.9, 90.0, 3.0)])["t1|rfd3|bb2"]
        self.assertAlmostEqual(out["af2_structural_pass_yield"], 0.0)
        self.assertAlmostEqual(out["joint_pass_yield"], 0.0)

    def test_missing_plddt_excluded_from_structural_denominator(self):
        recs = [_rec("bb3", 0.9, 90.0, 1.0), _rec("bb3", 0.9, None, None)]
        out = backbone_yields(recs)["t1|rfd3|bb3"]
        self.assertEqual(out["n_sequences"], 2)
        self.assertEqual(out["n_sequences_with_af2"], 1)
        self.assertAlmostEqual(out["af2_structural_pass_yield"], 1.0)

    def test_filtered_regime_is_flagged_as_biased(self):
        out = backbone_yields(
            [_rec("bb4", 0.9, 90.0, 1.0, regime="af2_after_soluprot_filter")]
        )["t1|rfd3|bb4"]
        self.assertEqual(out["label_regime"], "af2_after_soluprot_filter")
        self.assertTrue(out["structural_yield_is_biased"])

    def test_unbiased_regime_is_not_flagged(self):
        out = backbone_yields([_rec("bb5", 0.9, 90.0, 1.0)])["t1|rfd3|bb5"]
        self.assertFalse(out["structural_yield_is_biased"])

    def test_mixed_regime_within_backbone_is_flagged(self):
        recs = [
            _rec("bb6", 0.9, 90.0, 1.0),
            _rec("bb6", 0.9, 90.0, 1.0, regime="af2_after_soluprot_filter"),
        ]
        out = backbone_yields(recs)["t1|rfd3|bb6"]
        self.assertEqual(out["label_regime"], "mixed")
        self.assertTrue(out["structural_yield_is_biased"])

    def test_yields_are_none_when_no_labels(self):
        out = backbone_yields([_rec("bb7", None, None, None)])["t1|rfd3|bb7"]
        self.assertIsNone(out["soluprot_pass_yield"])
        self.assertIsNone(out["af2_structural_pass_yield"])
        self.assertIsNone(out["joint_pass_yield"])

    def test_same_backbone_id_in_different_targets_stays_separate(self):
        """backbone_id 는 run 안에서만 고유하다. CATH run 은 전부 `target` 을 쓰므로
        backbone_id 로만 묶으면 82개 타겟이 백본 1개로 합쳐진다."""
        recs = [
            _rec("target", 0.9, 90.0, 1.0, target="t1", source="target"),
            _rec("target", 0.1, 40.0, 9.0, target="t2", source="target"),
        ]
        out = backbone_yields(recs)
        self.assertEqual(len(out), 2)
        self.assertEqual({v["target_id"] for v in out.values()}, {"t1", "t2"})
        self.assertEqual({v["n_sequences"] for v in out.values()}, {1})

    def test_same_id_from_different_sources_stays_separate(self):
        recs = [
            _rec("bb_0", 0.9, 90.0, 1.0, target="t1", source="rfd3"),
            _rec("bb_0", 0.2, 50.0, 5.0, target="t1", source="bioemu"),
        ]
        out = backbone_yields(recs)
        self.assertEqual(len(out), 2)
        self.assertEqual({v["backbone_source"] for v in out.values()}, {"rfd3", "bioemu"})

    def test_key_is_composite_and_backbone_id_is_preserved(self):
        recs = [_rec("bb_0", 0.9, 90.0, 1.0, target="t1", source="rfd3")]
        out = backbone_yields(recs)
        key = next(iter(out))
        self.assertEqual(key, "t1|rfd3|bb_0")
        self.assertEqual(out[key]["backbone_id"], "bb_0")
        self.assertEqual(out[key]["backbone_key"], "t1|rfd3|bb_0")

    def test_topup_flag_marks_only_ambiguous_backbones(self):
        """yield 가 0 이나 1 에 가까우면 표본을 늘려도 판정이 안 바뀐다.
        애매한 구간에만 2차 생성 예산을 쓴다."""
        from rapid_sr.yields import needs_topup
        self.assertFalse(needs_topup(0.0))
        self.assertFalse(needs_topup(0.1))
        self.assertTrue(needs_topup(0.25))
        self.assertTrue(needs_topup(0.5))
        self.assertTrue(needs_topup(0.75))
        self.assertFalse(needs_topup(0.9))
        self.assertFalse(needs_topup(1.0))

    def test_topup_not_requested_without_labels(self):
        from rapid_sr.yields import needs_topup
        self.assertFalse(needs_topup(None))

    def test_backbone_row_carries_topup_flag(self):
        recs = [_rec("bb9", 0.9, 90.0, 1.0), _rec("bb9", 0.9, 40.0, 9.0)]
        out = backbone_yields(recs)["t1|rfd3|bb9"]
        self.assertAlmostEqual(out["af2_structural_pass_yield"], 0.5)
        self.assertTrue(out["needs_topup"])

    def test_thresholds_match_documented_defaults(self):
        self.assertEqual(GATE0_THRESHOLDS["soluprot_min"], 0.5)
        self.assertEqual(GATE0_THRESHOLDS["plddt_min"], 85.0)
        self.assertEqual(GATE0_THRESHOLDS["rmsd_max"], 2.0)

    def test_fingerprint_carries_thresholds_and_sequence_count(self):
        fp = protocol_fingerprint()
        self.assertEqual(fp["thresholds"]["plddt_min"], 85.0)
        self.assertEqual(fp["sequences_per_backbone"], 16)
        self.assertEqual(fp["topup_sequences"], 16)
        self.assertEqual(fp["af2_calls_per_run"], 80)
        self.assertIn("mpnn_settings", fp)


if __name__ == "__main__":
    unittest.main()
