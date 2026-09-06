"""구조 판정 지표의 동결 정의.

같은 임계값을 서로 다른 정의에 적용하면 결과가 조용히 뒤집힌다. 실제로
게이트 0 캠페인은 DSSP non-loop 위치에서, 1 차 온도 패널은 전체 CA 에서
RMSD 를 재면서 둘 다 2.0 A 를 적용했고, loop 가 많은 백본은 어떤 설계도
통과하지 못했다.

그래서 정의를 한 곳에 못박는다. 여기가 유일한 출처이고, Gate 0 과 sweep 이
같은 상수를 읽는다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.protocol import (
    AF2_SETTINGS_V1,
    GATE0_THRESHOLDS,
    STRUCTURAL_METRIC_V1,
)


class MetricFreezeTests(unittest.TestCase):
    def test_the_metric_names_every_choice_that_changes_the_answer(self):
        spec = STRUCTURAL_METRIC_V1["rmsd"]
        for key in ("method", "reference", "mask_source", "mask_scope",
                    "pairing", "superposition", "cutoff_angstrom"):
            self.assertIn(key, spec, key)

    def test_the_mask_comes_from_the_reference_not_the_prediction(self):
        """AF2 출력에서 마스크를 뽑으면 서열마다 다른 위치를 재게 된다."""
        self.assertEqual(STRUCTURAL_METRIC_V1["rmsd"]["mask_source"], "reference_backbone")

    def test_the_mask_is_defined_once_per_backbone(self):
        self.assertEqual(STRUCTURAL_METRIC_V1["rmsd"]["mask_scope"],
                         "once_per_backbone_applied_to_all_sequences_and_conditions")

    def test_the_cutoff_matches_the_gate0_threshold(self):
        self.assertEqual(STRUCTURAL_METRIC_V1["rmsd"]["cutoff_angstrom"],
                         GATE0_THRESHOLDS["rmsd_max"])

    def test_the_plddt_cutoff_matches_the_gate0_threshold(self):
        self.assertEqual(STRUCTURAL_METRIC_V1["plddt"]["cutoff"],
                         GATE0_THRESHOLDS["plddt_min"])

    def test_all_ca_rmsd_is_kept_as_a_secondary_metric(self):
        """버리지 않는다. 유연 영역이 얼마나 벌어졌는지는 그 자체로 정보다."""
        names = {m["name"] for m in STRUCTURAL_METRIC_V1["secondary_metrics"]}
        self.assertIn("rmsd_all_ca", names)
        self.assertIn("rmsd_all_positions", names)

    def test_continuous_endpoints_are_declared_beside_the_binary_one(self):
        """0/1 포화로 정보를 잃는 문제를 줄이려면 연속 endpoint 가 필요하다."""
        names = {m["name"] for m in STRUCTURAL_METRIC_V1["secondary_metrics"]}
        for expected in ("rmsd", "plddt", "soluprot"):
            self.assertIn(expected, names, expected)

    def test_the_definition_is_versioned_and_frozen(self):
        self.assertTrue(STRUCTURAL_METRIC_V1["metric_id"])
        self.assertTrue(STRUCTURAL_METRIC_V1["frozen"])

    def test_the_mismatch_that_caused_this_is_recorded_not_just_fixed(self):
        note = STRUCTURAL_METRIC_V1["why_frozen"]
        self.assertIn("non-loop", note)
        # 정렬 오류로 단정하지 않는다. 확인된 것은 측정 영역이 다르다는 것이다.
        self.assertNotIn("artifact", note.lower())


class Af2SettingsTests(unittest.TestCase):
    """재실행이 '재측정' 이 되려면 예측 설정이 같아야 한다."""

    def test_every_setting_that_changes_a_prediction_is_pinned(self):
        for key in ("model_preset", "db_preset", "max_template_date", "extra_flags"):
            self.assertIn(key, AF2_SETTINGS_V1, key)

    def test_the_settings_are_explicit_not_client_defaults(self):
        """클라이언트 기본값에 기대면 기본값이 바뀔 때 두 실행이 조용히 갈린다."""
        self.assertEqual(AF2_SETTINGS_V1["model_preset"], "monomer")
        self.assertEqual(AF2_SETTINGS_V1["db_preset"], "full_dbs")
        self.assertEqual(AF2_SETTINGS_V1["max_template_date"], "2020-05-14")

    def test_what_the_worker_owns_is_stated_rather_than_claimed(self):
        self.assertIn("not_controlled_here", AF2_SETTINGS_V1)
        self.assertIn("seed", " ".join(AF2_SETTINGS_V1["not_controlled_here"]))


class RunnerUsesTheFrozenSpecTests(unittest.TestCase):
    def _runner(self):
        import importlib.util

        path = PROJECT_ROOT / "scripts" / "transcoder" / "10_temperature_af2.py"
        spec = importlib.util.spec_from_file_location("temperature_af2", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_runner_reads_the_frozen_rmsd_method(self):
        self.assertEqual(self._runner().RMSD_METHOD,
                         STRUCTURAL_METRIC_V1["rmsd"]["method"])

    def test_the_runner_passes_the_pinned_af2_settings(self):
        source = (PROJECT_ROOT / "scripts" / "transcoder"
                  / "10_temperature_af2.py").read_text(encoding="utf-8")
        self.assertIn("AF2_SETTINGS_V1", source)
        self.assertIn("model_preset=", source)

    def test_the_runner_records_the_settings_it_ran_with(self):
        module = self._runner()
        for field in ("af2_model_preset", "af2_db_preset", "af2_max_template_date"):
            self.assertIn(field, module.OUTPUT_FIELDS, field)


if __name__ == "__main__":
    unittest.main()
