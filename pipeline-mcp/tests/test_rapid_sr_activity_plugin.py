"""활성 평가 플러그인 계약.

활성은 다른 셋과 다르다. 모델을 붙여서 풀리지 않는다 - 활성은 타겟마다 다른
실험으로 정의되고(효소 회전수, 결합 저해, 형광), 그 타겟의 assay 라벨 없이는
어떤 예측기도 맞춰볼 대상이 없다.

그래서 여기서 구현하는 것은 예측기가 아니라 **계약** 이다. 라벨을 가진 사람이
자기 평가자를 끼워 넣을 수 있게 하되, 라벨 없이는 아무것도 돌지 않게 막는다.
사양에도 활성 라벨을 지어내지 않는다고 적혀 있고, 이 계약이 그것을 코드로
강제한다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.activity import (
    ActivityAssay,
    ActivityPlugin,
    ActivityPluginError,
    registered_assays,
)


def _assay(**overrides):
    spec = {
        "assay_id": "tev_cleavage_v1",
        "target_id": "tev",
        "readout": "cleaved fraction at 4h, 25C",
        "unit": "fraction",
        "higher_is_better": True,
        "labels": {"design_a": 0.8, "design_b": 0.2},
        "source": "internal plate reader, 2026-05",
    }
    spec.update(overrides)
    return ActivityAssay(**spec)


class AssayTests(unittest.TestCase):
    def test_an_assay_must_say_what_it_measured(self):
        with self.assertRaises(ActivityPluginError):
            _assay(readout="")

    def test_an_assay_must_name_its_source(self):
        """출처 없는 라벨은 지어낸 것과 구별되지 않는다."""
        with self.assertRaises(ActivityPluginError):
            _assay(source="")

    def test_an_assay_without_labels_is_refused(self):
        with self.assertRaises(ActivityPluginError):
            _assay(labels={})

    def test_the_direction_of_better_must_be_stated(self):
        with self.assertRaises(ActivityPluginError):
            _assay(higher_is_better=None)

    def test_a_valid_assay_reports_its_coverage(self):
        assay = _assay()
        self.assertEqual(assay.n_labels, 2)
        self.assertEqual(assay.target_id, "tev")


class PluginTests(unittest.TestCase):
    def test_scoring_without_an_assay_is_refused(self):
        plugin = ActivityPlugin()
        with self.assertRaises(ActivityPluginError) as ctx:
            plugin.score(["design_a"])
        self.assertIn("라벨", str(ctx.exception))

    def test_an_unlabelled_design_is_reported_not_guessed(self):
        plugin = ActivityPlugin(assay=_assay())
        out = plugin.score(["design_a", "design_unknown"])
        self.assertEqual(out["scored"]["design_a"], 0.8)
        self.assertEqual(out["unlabelled"], ["design_unknown"])
        self.assertNotIn("design_unknown", out["scored"])

    def test_coverage_is_reported_so_partial_labels_are_visible(self):
        out = ActivityPlugin(assay=_assay()).score(["design_a", "design_b", "design_c"])
        self.assertAlmostEqual(out["coverage"], 2 / 3, places=3)

    def test_the_result_carries_the_assay_provenance(self):
        out = ActivityPlugin(assay=_assay()).score(["design_a"])
        self.assertEqual(out["assay_id"], "tev_cleavage_v1")
        self.assertIn("plate reader", out["source"])

    def test_an_assay_for_another_target_is_refused(self):
        """한 타겟의 활성 라벨을 다른 타겟에 쓰면 그것이 라벨 조작이다."""
        plugin = ActivityPlugin(assay=_assay())
        with self.assertRaises(ActivityPluginError):
            plugin.score(["design_a"], target_id="different_target")

    def test_the_plugin_never_invents_a_default_score(self):
        source = (PROJECT_ROOT / "scripts" / "transcoder" / "rapid_sr"
                  / "activity.py").read_text(encoding="utf-8")
        code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
        self.assertNotIn("or 0.0", code)
        self.assertNotIn(".get(design, 0", code)


class RegistryTests(unittest.TestCase):
    def test_no_assay_is_registered_by_default(self):
        """RAPID 는 어떤 타겟의 활성도 알지 못한다. 빈 목록이 정직한 상태다."""
        self.assertEqual(registered_assays(), {})
