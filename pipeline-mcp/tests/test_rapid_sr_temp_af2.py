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
