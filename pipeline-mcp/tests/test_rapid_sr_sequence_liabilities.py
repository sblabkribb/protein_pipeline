"""서열에서 직접 읽는 응집·개발가능성 지표.

antigen 파이프라인이 항체용으로 만든 계산을 옮겨 온 것이다. 옮기면서 두 가지를
분명히 한다.

* 이것은 **휴리스틱** 이다. Kyte-Doolittle 소수성과 전하로 만든 창 통계이고,
  RAPID 는 어떤 응집 측정에도 맞춰본 적이 없다. 임계값은 항체 문맥에서 정해진
  것이라 단량체에 그대로 쓰면 뜻이 달라진다.
* 그래서 값은 내되 통과/탈락을 정하지 않는다. 게이트로 쓰려면 먼저 무엇에
  맞출지를 정해야 한다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.liabilities import (
    LIABILITY_METRIC,
    aggregation_prone_fraction,
    liability_report,
    max_hydrophobic_patch,
    motif_counts,
    net_charge,
)


class ChargeTests(unittest.TestCase):
    def test_lysine_and_arginine_are_positive(self):
        self.assertAlmostEqual(net_charge("KR"), 2.0)

    def test_aspartate_and_glutamate_are_negative(self):
        self.assertAlmostEqual(net_charge("DE"), -2.0)

    def test_histidine_counts_as_a_fraction_not_zero(self):
        # 완전히 0 으로 두면 His 가 많은 설계가 무전하로 보고된다.
        self.assertGreater(net_charge("HHHH"), 0.0)
        self.assertLess(net_charge("HHHH"), 1.0)

    def test_an_empty_sequence_is_neutral(self):
        self.assertEqual(net_charge(""), 0.0)


class PatchTests(unittest.TestCase):
    def test_a_greasy_stretch_scores_above_a_polar_one(self):
        self.assertGreater(max_hydrophobic_patch("IIIIIIIII"),
                           max_hydrophobic_patch("SSSSSSSSS"))

    def test_a_short_sequence_still_returns_a_number(self):
        self.assertIsInstance(max_hydrophobic_patch("IV"), float)

    def test_an_aggregation_window_needs_both_greasy_and_uncharged(self):
        # 소수성이 높아도 전하가 있으면 응집 창으로 세지 않는다 - 전하가
        # 기름진 구간을 녹여 두는 것이 이 휴리스틱의 근거다.
        greasy_charged = "IIKIIKIIKIIK"
        greasy_neutral = "IIIIIIIIIIII"
        self.assertLess(aggregation_prone_fraction(greasy_charged),
                        aggregation_prone_fraction(greasy_neutral))

    def test_the_fraction_stays_between_zero_and_one(self):
        for sequence in ("", "A", "IIIIIIIIII", "DEDEDEDEDE"):
            value = aggregation_prone_fraction(sequence)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


class MotifTests(unittest.TestCase):
    def test_deamidation_and_isomerisation_motifs_are_counted(self):
        counts = motif_counts("NGXXDGXX")
        self.assertEqual(counts["deamidation_NG"], 1)
        self.assertEqual(counts["isomerisation_DG"], 1)

    def test_oxidation_prone_residues_are_counted(self):
        self.assertEqual(motif_counts("MWMW")["oxidation_MW"], 4)

    def test_a_clean_sequence_reports_zeros(self):
        self.assertEqual(set(motif_counts("AAAAAA").values()), {0})


class ReportTests(unittest.TestCase):
    def test_the_report_carries_every_metric_and_its_provenance(self):
        report = liability_report("MKTAYIAKQRQISFVKSHFSRQ")
        for key in ("net_charge", "max_hydrophobic_patch",
                    "aggregation_prone_fraction", "motifs"):
            self.assertIn(key, report)
        self.assertEqual(report["metric_id"], LIABILITY_METRIC["metric_id"])

    def test_the_report_refuses_to_call_anything_pass_or_fail(self):
        """게이트로 쓰려면 먼저 무엇에 맞출지를 정해야 한다."""
        report = liability_report("MKTAYIAKQRQ")
        self.assertNotIn("passed", report)
        self.assertFalse(report["calibrated"])
        self.assertIn("항체", report["scope_note"])

    def test_the_thresholds_it_inherited_are_recorded_not_hidden(self):
        for key in ("patch_window", "aggregation_hydropathy", "aggregation_charge"):
            self.assertIn(key, LIABILITY_METRIC["inherited_thresholds"])

    def test_an_empty_sequence_is_reported_as_such_not_as_zero_risk(self):
        self.assertIsNone(liability_report("")["max_hydrophobic_patch"])


if __name__ == "__main__":
    unittest.main()
