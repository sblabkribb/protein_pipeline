"""informative backbone panel 선정.

이 선정이 지켜야 하는 것:

* **온도 실행 이후의 정보를 쓰지 않는다.** baseline joint/structural yield 만
  본다. global_score 나 sweep 결과가 들어가면 선정과 평가가 같은 데이터를 쓰게
  된다.
* **포화될 백본을 뽑지 않는다.** baseline 이 정확히 0 이나 1 이면 8 서열 패널
  에서도 움직이지 못한다. 15 개 패널에서 12 개가 그래서 무의미했다.
* **한 구간에 몰리지 않는다.** 중간 대역 안에서도 yield 밴드를 고르게 덮어야
  온도 효과가 yield 수준에 따라 달라지는지 볼 수 있다.
* **결정적이고 동결 가능하다.** 같은 입력과 seed 면 같은 목록이 나오고, 그
  목록은 실행 전에 provenance 와 함께 고정된다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.panel import (
    SELECTION_CRITERIA,
    YIELD_BANDS,
    build_manifest,
    eligible_backbones,
    saturation_risk,
    select_panel,
    yield_band,
)


def _row(key, target, source, joint, struct, n=40):
    return {
        "backbone_key": key, "target_id": target, "backbone_source": source,
        "backbone_id": source, "pdb_file": f"{key}.pdb",
        "joint_pass_yield": "" if joint is None else str(joint),
        "af2_structural_pass_yield": "" if struct is None else str(struct),
        "n_sequences_with_af2": str(n), "n_sequences": str(n),
        "label_regime": "af2_all_candidates", "tier": "50",
    }


def _pool(n_per_source=12):
    rows = []
    for source in ("target", "rfd3", "bioemu"):
        for i in range(n_per_source):
            y = 0.05 + 0.9 * (i / max(1, n_per_source - 1))
            rows.append(_row(f"t{i}|{source}|b{i}", f"t{i}", source, round(y, 3), round(y, 3)))
    return rows


class EligibilityTests(unittest.TestCase):
    def test_a_saturated_backbone_is_excluded(self):
        rows = [_row("a", "t1", "target", 0.0, 0.0), _row("b", "t2", "target", 1.0, 1.0),
                _row("c", "t3", "target", 0.5, 0.5)]
        self.assertEqual([r["backbone_key"] for r in eligible_backbones(rows)], ["c"])

    def test_saturation_on_either_endpoint_disqualifies(self):
        """joint 는 중간인데 structural 이 천장이면 구조 endpoint 는 못 움직인다."""
        rows = [_row("a", "t1", "target", 0.625, 1.0), _row("b", "t2", "target", 0.6, 0.6)]
        self.assertEqual([r["backbone_key"] for r in eligible_backbones(rows)], ["b"])

    def test_a_missing_label_is_excluded_rather_than_imputed(self):
        rows = [_row("a", "t1", "target", None, 0.5), _row("b", "t2", "target", 0.5, 0.5)]
        self.assertEqual([r["backbone_key"] for r in eligible_backbones(rows)], ["b"])

    def test_a_yield_from_too_few_sequences_is_excluded(self):
        """서열 4 개에서 나온 0.25 는 1/4 이다. 중간이라 부를 정밀도가 없다."""
        rows = [_row("a", "t1", "target", 0.25, 0.25, n=4),
                _row("b", "t2", "target", 0.25, 0.25, n=40)]
        self.assertEqual([r["backbone_key"] for r in eligible_backbones(rows)], ["b"])

    def test_the_minimum_sequence_count_is_declared_not_hidden(self):
        self.assertIn("min_sequences_with_af2", SELECTION_CRITERIA)


class BandTests(unittest.TestCase):
    def test_bands_cover_the_open_interval_without_gaps_or_overlap(self):
        edges = [YIELD_BANDS[0][0]] + [hi for _, hi in YIELD_BANDS]
        self.assertEqual(edges[0], 0.0)
        self.assertEqual(edges[-1], 1.0)
        for lower, upper in zip(edges, edges[1:]):
            self.assertLess(lower, upper)

    def test_every_eligible_yield_lands_in_exactly_one_band(self):
        for value in (0.01, 0.25, 0.2500001, 0.5, 0.75, 0.99):
            self.assertIsNotNone(yield_band(value), value)

    def test_a_saturated_value_has_no_band(self):
        self.assertIsNone(yield_band(0.0))
        self.assertIsNone(yield_band(1.0))


class SelectionTests(unittest.TestCase):
    def test_selection_size_stays_inside_the_requested_range(self):
        picked = select_panel(_pool(), target_size=27, seed=0)
        self.assertGreaterEqual(len(picked), 24)
        self.assertLessEqual(len(picked), 30)

    def test_selection_is_deterministic(self):
        a = [r["backbone_key"] for r in select_panel(_pool(), target_size=27, seed=0)]
        b = [r["backbone_key"] for r in select_panel(_pool(), target_size=27, seed=0)]
        self.assertEqual(a, b)

    def test_no_selected_backbone_is_saturated(self):
        rows = _pool() + [_row("z0", "tz", "target", 0.0, 0.0), _row("z1", "tz", "rfd3", 1.0, 1.0)]
        keys = {r["backbone_key"] for r in select_panel(rows, target_size=27, seed=0)}
        self.assertNotIn("z0", keys)
        self.assertNotIn("z1", keys)

    def test_every_populated_band_is_represented(self):
        picked = select_panel(_pool(), target_size=27, seed=0)
        bands = {yield_band(float(r["joint_pass_yield"])) for r in picked}
        self.assertEqual(len(bands), len(YIELD_BANDS))

    def test_no_band_takes_more_than_its_share_when_all_are_populated(self):
        picked = select_panel(_pool(), target_size=28, seed=0)
        counts = {}
        for r in picked:
            band = yield_band(float(r["joint_pass_yield"]))
            counts[band] = counts.get(band, 0) + 1
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 2)

    def test_a_scarce_source_is_not_starved(self):
        rows = _pool(12)
        rows = [r for r in rows if r["backbone_source"] != "bioemu"]
        rows += [_row(f"e{i}|bioemu|b", f"e{i}", "bioemu", 0.4 + 0.05 * i, 0.4 + 0.05 * i)
                 for i in range(3)]
        picked = select_panel(rows, target_size=27, seed=0)
        sources = {r["backbone_source"] for r in picked}
        self.assertIn("bioemu", sources)

    def test_a_source_cannot_exceed_what_it_has(self):
        rows = _pool(12)
        picked = select_panel(rows, target_size=27, seed=0)
        for source in ("target", "rfd3", "bioemu"):
            available = sum(1 for r in rows if r["backbone_source"] == source)
            chosen = sum(1 for r in picked if r["backbone_source"] == source)
            self.assertLessEqual(chosen, available)

    def test_targets_are_spread_rather_than_concentrated(self):
        """한 타겟에서 여러 개를 뽑으면 클러스터 수가 늘지 않는다."""
        rows = [_row(f"x{i}|rfd3|b{i}", "onlytarget", "rfd3", 0.3 + 0.01 * i, 0.3 + 0.01 * i)
                for i in range(20)]
        rows += _pool(8)
        picked = select_panel(rows, target_size=24, seed=0)
        counts = {}
        for r in picked:
            counts[r["target_id"]] = counts.get(r["target_id"], 0) + 1
        self.assertLessEqual(counts.get("onlytarget", 0), SELECTION_CRITERIA["max_per_target"])

    def test_fewer_eligible_than_requested_returns_what_exists(self):
        rows = [_row(f"a{i}", f"t{i}", "target", 0.5, 0.5) for i in range(5)]
        self.assertEqual(len(select_panel(rows, target_size=27, seed=0)), 5)

    def test_selection_reads_no_temperature_or_score_column(self):
        """선정이 온도 이후 정보를 못 보게 컬럼 자체를 막는다."""
        rows = _pool()
        for r in rows:
            r["global_score"] = "0.9"
            r["temperature"] = "0.3"
        with self.assertRaises(ValueError):
            select_panel(rows, target_size=27, seed=0, forbid_columns=("global_score", "temperature"))


class ManifestTests(unittest.TestCase):
    def test_manifest_records_criteria_seed_and_source_file(self):
        rows = _pool()
        picked = select_panel(rows, target_size=27, seed=3)
        manifest = build_manifest(picked, source_path=Path("labels.csv"), seed=3,
                                  source_sha256="abc123")
        self.assertEqual(manifest["seed"], 3)
        self.assertEqual(manifest["source_sha256"], "abc123")
        self.assertEqual(manifest["criteria"], SELECTION_CRITERIA)
        self.assertEqual(manifest["n_selected"], len(picked))

    def test_manifest_carries_each_backbone_with_the_yield_that_selected_it(self):
        picked = select_panel(_pool(), target_size=27, seed=0)
        manifest = build_manifest(picked, source_path=Path("labels.csv"), seed=0,
                                  source_sha256="x")
        for entry in manifest["backbones"]:
            for key in ("backbone_key", "target_id", "backbone_source",
                        "baseline_joint_yield", "baseline_structural_yield",
                        "n_sequences_with_af2", "yield_band"):
                self.assertIn(key, entry)

    def test_manifest_states_that_selection_used_no_temperature_data(self):
        manifest = build_manifest(select_panel(_pool(), target_size=27, seed=0),
                                  source_path=Path("labels.csv"), seed=0, source_sha256="x")
        self.assertIn("selection_inputs", manifest)
        self.assertNotIn("global_score", manifest["selection_inputs"])

    def test_manifest_reports_the_band_and_source_distribution(self):
        manifest = build_manifest(select_panel(_pool(), target_size=27, seed=0),
                                  source_path=Path("labels.csv"), seed=0, source_sha256="x")
        self.assertIn("band_distribution", manifest)
        self.assertIn("source_distribution", manifest)
        self.assertIn("target_distribution", manifest)


if __name__ == "__main__":
    unittest.main()


class ClusterStructureTests(unittest.TestCase):
    """백본이 타겟 안에 중첩되면 클러스터 수는 타겟 수다.

    1 차 패널은 백본 15 개가 곧 타겟 15 개였다. 2 차 패널은 한 타겟에서 여러
    백본을 뽑으므로 백본으로 재표집하면 독립 클러스터를 실제보다 많이 세게 된다.
    """

    def test_manifest_reports_the_effective_cluster_count(self):
        rows = [_row(f"a{i}|rfd3|b{i}", "t1", "rfd3", 0.4, 0.4) for i in range(3)]
        rows += [_row(f"b{i}|rfd3|b{i}", f"t{i + 2}", "rfd3", 0.6, 0.6) for i in range(3)]
        manifest = build_manifest(select_panel(rows, target_size=6, seed=0),
                                  source_path=Path("l.csv"), seed=0, source_sha256="x")
        self.assertEqual(manifest["n_selected"], len(manifest["backbones"]))
        self.assertEqual(manifest["n_effective_clusters"], len(manifest["target_distribution"]))
        self.assertLessEqual(manifest["n_effective_clusters"], manifest["n_selected"])

    def test_manifest_names_the_clustering_unit_for_the_analysis(self):
        manifest = build_manifest(select_panel(_pool(), target_size=27, seed=0),
                                  source_path=Path("l.csv"), seed=0, source_sha256="x")
        self.assertEqual(manifest["bootstrap_cluster_unit"], "target_id")


class SaturationRiskTests(unittest.TestCase):
    """8 서열 패널에서 이 백본이 또 바닥/천장에 깔릴 확률.

    baseline 이 0.05 인 백본은 (0,1) 안에 있지만 8 서열 x 4 조건에서 전부 0 이
    나올 확률이 낮지 않다. 밴드를 덮으라는 요구와 정보량 사이의 거래를 숨기지
    않고 숫자로 남긴다.
    """

    def test_a_mid_yield_backbone_has_negligible_saturation_risk(self):
        self.assertLess(saturation_risk(0.5, n_per_condition=8, n_conditions=4), 0.01)

    def test_a_near_floor_backbone_carries_real_risk(self):
        self.assertGreater(saturation_risk(0.05, n_per_condition=8, n_conditions=4), 0.1)

    def test_risk_is_symmetric_around_a_half(self):
        self.assertAlmostEqual(saturation_risk(0.05, n_per_condition=8, n_conditions=4),
                               saturation_risk(0.95, n_per_condition=8, n_conditions=4),
                               places=9)

    def test_more_sequences_reduce_the_risk(self):
        self.assertLess(saturation_risk(0.1, n_per_condition=16, n_conditions=4),
                        saturation_risk(0.1, n_per_condition=8, n_conditions=4))

    def test_manifest_carries_the_risk_per_backbone_and_the_panel_expectation(self):
        manifest = build_manifest(select_panel(_pool(), target_size=27, seed=0),
                                  source_path=Path("l.csv"), seed=0, source_sha256="x")
        for entry in manifest["backbones"]:
            self.assertIn("saturation_risk", entry)
        self.assertIn("expected_saturated_backbones", manifest)
        self.assertIn("expected_informative_backbones", manifest)


class StructureCriteriaTests(unittest.TestCase):
    """구조 자체로 판단하는 기준. 온도 결과와 무관하므로 선정에 써도 된다.

    첫 동결에서 16 사슬 3428 잔기짜리 조립체가 뽑혔다. 이 실험은 서열 하나를
    단량체로 접으므로, 다중 사슬 기준 구조에는 RMSD 를 잴 대상 자체가 없다.
    MPNN 호출도 60 초 타임아웃에서 터졌다.
    """

    def _info(self, mapping):
        return lambda row: mapping[row["backbone_key"]]

    def test_a_multi_chain_reference_is_excluded(self):
        rows = [_row("mono", "t1", "target", 0.5, 0.5), _row("multi", "t2", "target", 0.5, 0.5)]
        info = self._info({"mono": {"n_chains": 1, "n_residues": 100},
                           "multi": {"n_chains": 7, "n_residues": 900}})
        keys = [r["backbone_key"] for r in eligible_backbones(rows, structure_info=info)]
        self.assertEqual(keys, ["mono"])

    def test_an_oversized_backbone_is_excluded(self):
        rows = [_row("small", "t1", "target", 0.5, 0.5), _row("huge", "t2", "target", 0.5, 0.5)]
        info = self._info({"small": {"n_chains": 1, "n_residues": 200},
                           "huge": {"n_chains": 1, "n_residues": 3000}})
        keys = [r["backbone_key"] for r in eligible_backbones(rows, structure_info=info)]
        self.assertEqual(keys, ["small"])

    def test_the_limits_are_declared_in_the_criteria(self):
        self.assertIn("single_chain_only", SELECTION_CRITERIA)
        self.assertIn("max_residues", SELECTION_CRITERIA)

    def test_without_structure_info_the_structural_filter_is_skipped_not_guessed(self):
        rows = [_row("a", "t1", "target", 0.5, 0.5)]
        self.assertEqual(len(eligible_backbones(rows)), 1)

    def test_manifest_records_the_structure_of_each_selected_backbone(self):
        rows = [_row(f"a{i}", f"t{i}", "target", 0.4 + 0.05 * i, 0.4 + 0.05 * i) for i in range(4)]
        info = self._info({f"a{i}": {"n_chains": 1, "n_residues": 100 + i} for i in range(4)})
        picked = select_panel(rows, target_size=4, seed=0, structure_info=info)
        manifest = build_manifest(picked, source_path=Path("l.csv"), seed=0, source_sha256="x")
        for entry in manifest["backbones"]:
            self.assertIn("n_residues", entry)
            self.assertIn("n_chains", entry)

    def test_manifest_reports_the_expected_af2_cost(self):
        """896 폴드를 돌리기 전에 얼마나 걸리는지 알아야 한다."""
        rows = [_row(f"a{i}", f"t{i}", "target", 0.4 + 0.05 * i, 0.4 + 0.05 * i) for i in range(4)]
        info = self._info({f"a{i}": {"n_chains": 1, "n_residues": 200} for i in range(4)})
        picked = select_panel(rows, target_size=4, seed=0, structure_info=info)
        manifest = build_manifest(picked, source_path=Path("l.csv"), seed=0, source_sha256="x")
        self.assertIn("expected_af2_folds", manifest)
        self.assertIn("expected_af2_worker_seconds", manifest)
        self.assertEqual(manifest["expected_af2_folds"], 4 * 4 * 8)
