"""어떤 산출물이 어떤 지표로 만들어졌는지, 그래서 지금 유효한지.

구조 지표의 대응 방식이 세 번 바뀌었다. 그 사이에 만들어진 파일들이 디스크에
그대로 남아 있고, 파일만 봐서는 어느 대응으로 잰 것인지 알 수 없다. 표시하지
않으면 누군가 - 나를 포함해 - 그 숫자를 다시 읽는다.

RMSD 와 무관한 결과(SoluProt, 생성 다양성)는 그대로 유효하다. 전부 무효로
묶으면 멀쩡한 결과까지 버리게 된다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.provenance import (
    CORRESPONDENCE_HISTORY,
    METRIC_STATUS,
    VALID_CORRESPONDENCE,
    artifact_status,
    is_rmsd_derived,
)


class HistoryTests(unittest.TestCase):
    def test_every_correspondence_ever_used_is_recorded(self):
        for name in ("kabsch_all_ca_file_order", "ca_rmsd_dssp_non_loop_resnum",
                     "folded_sequence_order"):
            self.assertIn(name, CORRESPONDENCE_HISTORY, name)

    def test_only_one_correspondence_is_valid(self):
        valid = [k for k, v in CORRESPONDENCE_HISTORY.items() if v["valid"]]
        self.assertEqual(valid, [VALID_CORRESPONDENCE])

    def test_each_superseded_one_says_what_was_wrong(self):
        for name, entry in CORRESPONDENCE_HISTORY.items():
            if entry["valid"]:
                continue
            self.assertTrue(entry["defect"], name)
            self.assertTrue(entry["evidence"], name)


class ArtifactStatusTests(unittest.TestCase):
    def test_a_file_from_a_superseded_correspondence_is_invalid(self):
        status = artifact_status("temperature_sweep/af2_stage1.csv")
        self.assertEqual(status["status"], "invalid")
        self.assertIn("correspondence", status["reason"])

    def test_the_reproducibility_report_is_partially_valid(self):
        """pLDDT 대조는 RMSD 와 무관하다. 통과율 귀속만 무효다."""
        status = artifact_status("temperature_sweep/af2_rerun_reproducibility.json")
        self.assertEqual(status["status"], "partially_valid")
        self.assertIn("plddt", " ".join(status["still_valid"]).lower())

    def test_soluprot_and_diversity_stay_valid(self):
        for path in ("temperature_sweep/conditions.csv",
                     "temperature_panel2/conditions.csv"):
            self.assertEqual(artifact_status(path)["status"], "valid")

    def test_the_gate0_labels_stay_valid_with_the_reason_recorded(self):
        status = artifact_status("backbones/backbone_labels.csv")
        self.assertEqual(status["status"], "valid")
        self.assertIn("renumber", status["reason"])

    def test_an_unlisted_artifact_is_unknown_not_assumed_valid(self):
        self.assertEqual(artifact_status("something/else.json")["status"], "unknown")

    def test_every_listed_artifact_names_a_status(self):
        allowed = {"valid", "invalid", "partially_valid", "superseded"}
        for path, entry in METRIC_STATUS.items():
            self.assertIn(entry["status"], allowed, path)
            self.assertTrue(entry["reason"], path)


class RmsdDependenceTests(unittest.TestCase):
    def test_structural_and_joint_yield_depend_on_rmsd(self):
        self.assertTrue(is_rmsd_derived("structural_yield"))
        self.assertTrue(is_rmsd_derived("joint_yield"))

    def test_soluprot_and_diversity_do_not(self):
        for endpoint in ("soluprot", "positional_entropy", "mean_pairwise_distance"):
            self.assertFalse(is_rmsd_derived(endpoint), endpoint)

    def test_plddt_alone_does_not(self):
        self.assertFalse(is_rmsd_derived("plddt"))
