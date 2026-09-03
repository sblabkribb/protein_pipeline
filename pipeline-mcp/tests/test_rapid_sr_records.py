from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.records import DesignRecord, LABEL_REGIMES


class DesignRecordTests(unittest.TestCase):
    def test_missing_labels_are_none_not_zero(self):
        rec = DesignRecord(
            design_id="target:1",
            target_id="1a19A00",
            tier="30",
            backbone_id="target",
            backbone_source="target",
            sequence="MKT",
            soluprot=0.71,
            plddt_af2=None,
            rmsd_af2=None,
            label_regime="af2_all_candidates",
        )
        self.assertIsNone(rec.plddt_af2)
        self.assertEqual(rec.soluprot, 0.71)

    def test_label_regime_must_be_known(self):
        with self.assertRaises(ValueError):
            DesignRecord(
                design_id="d", target_id="t", tier="30",
                backbone_id="b", backbone_source="rfd3", sequence="MKT",
                soluprot=None, plddt_af2=None, rmsd_af2=None,
                label_regime="whatever",
            )

    def test_regimes_are_exactly_the_two_documented_values(self):
        self.assertEqual(
            set(LABEL_REGIMES), {"af2_all_candidates", "af2_after_soluprot_filter"}
        )

    def test_to_row_roundtrips_none(self):
        rec = DesignRecord(
            design_id="d", target_id="t", tier="50",
            backbone_id="b", backbone_source="bioemu", sequence="MK",
            soluprot=None, plddt_af2=91.2, rmsd_af2=1.1,
            label_regime="af2_after_soluprot_filter",
        )
        row = rec.to_row()
        self.assertIsNone(row["soluprot"])
        self.assertEqual(row["plddt_af2"], 91.2)
        self.assertEqual(row["backbone_source"], "bioemu")

    def test_unknown_backbone_source_rejected(self):
        with self.assertRaises(ValueError):
            DesignRecord(
                design_id="d", target_id="t", tier="30",
                backbone_id="b", backbone_source="esmfold", sequence="MK",
                soluprot=None, plddt_af2=None, rmsd_af2=None,
                label_regime="af2_all_candidates",
            )


if __name__ == "__main__":
    unittest.main()
