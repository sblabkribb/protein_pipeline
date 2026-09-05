from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "transcoder" / "10_temperature_af2.py"


def _load():
    spec = importlib.util.spec_from_file_location("temperature_af2", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(n_backbones=3, temps=("0.05", "0.1", "0.2", "0.3"), n=16):
    out = []
    for b in range(n_backbones):
        for t in temps:
            for i in range(n):
                out.append({
                    "backbone_key": f"t{b}|target|bb{b}", "target_id": f"t{b}",
                    "temperature": t, "sequence_id": f"t{b}|target|bb{b}|T{t}|{i}",
                    "sequence": "MKT", "soluprot": "0.7", "global_score": "1.0",
                })
    return out


class SelectPairedTests(unittest.TestCase):
    def test_same_indices_chosen_at_every_temperature(self):
        module = _load()
        picked = module.select_paired(_rows(), n_per_condition=8, offset=0)
        by_temp = {}
        for row in picked:
            idx = int(row["sequence_id"].rsplit("|", 1)[-1])
            by_temp.setdefault(row["temperature"], set()).add(idx)
        self.assertEqual(len(set(map(frozenset, by_temp.values()))), 1)
        self.assertEqual(next(iter(by_temp.values())), set(range(8)))

    def test_counts_are_balanced_across_temperatures(self):
        module = _load()
        picked = module.select_paired(_rows(n_backbones=15), n_per_condition=8, offset=0)
        counts = {}
        for row in picked:
            counts[row["temperature"]] = counts.get(row["temperature"], 0) + 1
        self.assertEqual(set(counts.values()), {15 * 8})
        self.assertEqual(len(picked), 15 * 8 * 4)

    def test_offset_selects_the_second_half(self):
        module = _load()
        picked = module.select_paired(_rows(), n_per_condition=8, offset=8)
        indices = {int(r["sequence_id"].rsplit("|", 1)[-1]) for r in picked}
        self.assertEqual(indices, set(range(8, 16)))

    def test_stage_one_and_two_do_not_overlap(self):
        module = _load()
        rows = _rows()
        first = {r["sequence_id"] for r in module.select_paired(rows, n_per_condition=8, offset=0)}
        second = {r["sequence_id"] for r in module.select_paired(rows, n_per_condition=8, offset=8)}
        self.assertEqual(first & second, set())

    def test_selection_ignores_scores(self):
        """global_score 로 고르면 온도 효과와 선택 효과가 교란된다."""
        module = _load()
        rows = _rows(n_backbones=1)
        for i, row in enumerate(rows):
            row["global_score"] = str(100 - i)
        picked = module.select_paired(rows, n_per_condition=4, offset=0)
        indices = {int(r["sequence_id"].rsplit("|", 1)[-1]) for r in picked}
        self.assertEqual(indices, {0, 1, 2, 3})


if __name__ == "__main__":
    unittest.main()


class RmsdDefinitionTests(unittest.TestCase):
    """온도 패널의 RMSD 는 게이트 0 캠페인과 같은 정의여야 한다.

    같은 AF2 모델에서 측정한 값 (1bg5A03, 254 잔기, DSSP non-loop 85 개):

        kabsch, 파일 순서, 전체 CA   22.6 A
        ca_rmsd, resnum, 전체 위치   37.7 A
        ca_rmsd, resnum, non-loop     1.32 A

    GATE0_THRESHOLDS['rmsd_max'] = 2.0 은 마지막 정의 위에서 정해진 값이다.
    앞의 두 정의에 그 임계값을 적용하면 사실상 아무 설계도 통과하지 못한다.
    """

    def test_the_panel_uses_the_campaign_rmsd_definition(self):
        module = _load()
        self.assertEqual(module.RMSD_METHOD, "ca_rmsd_dssp_non_loop")

    def test_the_naive_all_ca_helper_is_not_the_primary_metric(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
        self.assertNotIn('entry["rmsd"] = round(kabsch_rmsd(', code,
                         "기본 rmsd 컬럼이 전체 CA kabsch 면 게이트 0 임계값과 어긋난다")

    def test_all_three_variants_are_recorded_for_provenance(self):
        module = _load()
        for field in ("rmsd", "rmsd_all_ca", "rmsd_all_positions",
                      "rmsd_method", "rmsd_n_positions"):
            self.assertIn(field, module.OUTPUT_FIELDS, field)

    def test_a_backbone_with_no_non_loop_positions_yields_no_rmsd(self):
        """DSSP 가 구조를 하나도 못 찾으면 임계값을 적용할 근거가 없다."""
        module = _load()
        self.assertIsNone(module.rmsd_against_reference("", {}, reference_text="")["rmsd"])
