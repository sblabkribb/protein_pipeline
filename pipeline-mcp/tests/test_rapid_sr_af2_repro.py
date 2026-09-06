"""재실행이 '재측정' 인지 확인한다.

패널 1 은 PDB 를 저장하지 않아서 RMSD 정의를 고치려면 다시 접어야 했다. 그러면
두 가지가 동시에 바뀐다: 지표 정의와, AF2 의 run-to-run 차이. 같은 서열을 다시
접었으므로 pLDDT 를 직접 대조해서 둘을 분리할 수 있다.

pLDDT 가 재현되면 통과율 변화는 전부 지표 정의 때문이다. 재현되지 않으면 두
효과가 섞였고, 그 사실을 결과에 적어야 한다.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "transcoder" / "20_af2_reproducibility_check.py"
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))


def _load():
    spec = importlib.util.spec_from_file_location("af2_repro", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(sid, plddt, rmsd, soluprot=0.8, **extra):
    row = {"sequence_id": sid, "backbone_key": "bb", "target_id": "t",
           "temperature": "0.1", "plddt": str(plddt), "rmsd": str(rmsd),
           "soluprot": str(soluprot), "status": "ok"}
    row.update({k: str(v) for k, v in extra.items()})
    return row


class ReproducibilityTests(unittest.TestCase):
    def test_identical_runs_report_zero_drift(self):
        module = _load()
        rows = [_row("a", 90.0, 1.0), _row("b", 80.0, 3.0)]
        out = module.compare_runs(rows, [dict(r) for r in rows])
        self.assertEqual(out["plddt"]["max_abs_delta"], 0.0)
        self.assertEqual(out["plddt"]["n_compared"], 2)

    def test_drift_is_reported_not_averaged_away(self):
        module = _load()
        old = [_row("a", 90.0, 1.0), _row("b", 90.0, 1.0)]
        new = [_row("a", 90.0, 1.0), _row("b", 70.0, 1.0)]
        out = module.compare_runs(old, new)
        self.assertAlmostEqual(out["plddt"]["max_abs_delta"], 20.0)
        self.assertIn("b", out["plddt"]["largest_deltas"][0]["sequence_id"])

    def test_gate_flips_are_counted_separately_from_the_mean(self):
        """평균이 작아도 임계값을 넘나든 서열이 있으면 통과율이 바뀐다."""
        module = _load()
        old = [_row("a", 85.2, 1.0)]
        new = [_row("a", 84.8, 1.0)]
        out = module.compare_runs(old, new)
        self.assertEqual(out["plddt"]["n_gate_flips"], 1)

    def test_only_sequences_present_in_both_runs_are_compared(self):
        module = _load()
        out = module.compare_runs([_row("a", 90.0, 1.0)],
                                  [_row("a", 90.0, 1.0), _row("b", 90.0, 1.0)])
        self.assertEqual(out["plddt"]["n_compared"], 1)
        self.assertEqual(out["n_only_in_new"], 1)

    def test_a_failed_row_is_excluded_rather_than_read_as_zero(self):
        module = _load()
        bad = _row("b", 90.0, 1.0)
        bad["status"] = "failed"
        bad["plddt"] = ""
        out = module.compare_runs([_row("a", 90.0, 1.0), bad],
                                  [_row("a", 90.0, 1.0), dict(bad)])
        self.assertEqual(out["plddt"]["n_compared"], 1)


class AttributionTests(unittest.TestCase):
    """통과율 변화를 지표 정의와 예측 차이로 나눈다."""

    def test_a_pass_change_from_rmsd_alone_is_attributed_to_the_metric(self):
        module = _load()
        old = [_row("a", 95.0, 22.0)]            # 전체 CA RMSD 로 탈락
        new = [_row("a", 95.0, 1.3)]             # non-loop RMSD 로 통과
        out = module.compare_runs(old, new)
        self.assertEqual(out["attribution"]["metric_definition_only"], 1)
        self.assertEqual(out["attribution"]["prediction_only"], 0)

    def test_a_pass_change_from_plddt_alone_is_attributed_to_the_prediction(self):
        module = _load()
        old = [_row("a", 95.0, 1.0)]
        new = [_row("a", 70.0, 1.0)]
        out = module.compare_runs(old, new)
        self.assertEqual(out["attribution"]["prediction_only"], 1)
        self.assertEqual(out["attribution"]["metric_definition_only"], 0)

    def test_both_changing_is_reported_as_confounded(self):
        module = _load()
        old = [_row("a", 95.0, 22.0)]
        new = [_row("a", 70.0, 1.3)]
        out = module.compare_runs(old, new)
        self.assertEqual(out["attribution"]["confounded"], 1)

    def test_the_verdict_says_whether_the_comparison_is_clean(self):
        module = _load()
        same = [_row("a", 90.0, 1.0)]
        out = module.compare_runs(same, [dict(same[0])])
        self.assertTrue(out["prediction_reproduced"])
        drifted = module.compare_runs([_row("a", 90.0, 1.0)], [_row("a", 60.0, 1.0)])
        self.assertFalse(drifted["prediction_reproduced"])

    def test_the_reproducibility_bar_is_declared(self):
        module = _load()
        self.assertIn("plddt_tolerance", module.REPRODUCIBILITY_BAR)
        self.assertIn("max_gate_flip_fraction", module.REPRODUCIBILITY_BAR)


if __name__ == "__main__":
    unittest.main()
