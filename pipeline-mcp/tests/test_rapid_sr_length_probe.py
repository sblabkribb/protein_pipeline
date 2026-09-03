from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "transcoder" / "04g_af2_length_scaling_probe.py"


def _load():
    spec = importlib.util.spec_from_file_location("af2_length_scaling_probe", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SequenceFromPdbTests(unittest.TestCase):
    def _pdb(self, body: str) -> Path:
        tmp = Path(tempfile.mkdtemp()) / "x.pdb"
        tmp.write_text(body)
        return tmp

    def test_reads_only_the_first_model(self):
        module = _load()
        body = (
            "MODEL        1\n"
            "ATOM      1  CA  ALA A   1       0.0   0.0   0.0  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       0.0   0.0   0.0  1.00 20.00           C\n"
            "ENDMDL\n"
            "MODEL        2\n"
            "ATOM      3  CA  ALA A   1       0.0   0.0   0.0  1.00 20.00           C\n"
            "ENDMDL\n"
        )
        self.assertEqual(module.sequence_from_pdb(self._pdb(body)), "AG")

    def test_duplicate_residue_keys_counted_once(self):
        module = _load()
        body = (
            "ATOM      1  CA AALA A   1       0.0   0.0   0.0  0.50 20.00           C\n"
            "ATOM      2  CA BALA A   1       0.0   0.0   0.0  0.50 20.00           C\n"
            "ATOM      3  CA  GLY A   2       0.0   0.0   0.0  1.00 20.00           C\n"
        )
        self.assertEqual(module.sequence_from_pdb(self._pdb(body)), "AG")

    def test_unknown_residue_becomes_x(self):
        module = _load()
        body = "ATOM      1  CA  XYZ A   1       0.0   0.0   0.0  1.00 20.00           C\n"
        self.assertEqual(module.sequence_from_pdb(self._pdb(body)), "X")


class ScalingFitTests(unittest.TestCase):
    def test_recovers_a_known_power_law(self):
        module = _load()
        points = [
            {"status": "ok", "length": 100, "elapsed_s": 100.0},
            {"status": "ok", "length": 200, "elapsed_s": 400.0},
            {"status": "ok", "length": 400, "elapsed_s": 1600.0},
        ]
        fit = module.fit_scaling(points)
        self.assertAlmostEqual(fit["exponent"], 2.0, places=2)

    def test_needs_two_points(self):
        module = _load()
        fit = module.fit_scaling([{"status": "ok", "length": 100, "elapsed_s": 10.0}])
        self.assertIsNone(fit["exponent"])

    def test_failed_points_excluded(self):
        module = _load()
        fit = module.fit_scaling([
            {"status": "ok", "length": 100, "elapsed_s": 100.0},
            {"status": "failed", "length": 200, "elapsed_s": 3.0},
        ])
        self.assertIsNone(fit["exponent"])

    def test_prediction_uses_the_fit(self):
        module = _load()
        fit = module.fit_scaling([
            {"status": "ok", "length": 100, "elapsed_s": 100.0},
            {"status": "ok", "length": 200, "elapsed_s": 400.0},
        ])
        self.assertAlmostEqual(module.predict_seconds(fit, 400), 1600.0, delta=5.0)


if __name__ == "__main__":
    unittest.main()
