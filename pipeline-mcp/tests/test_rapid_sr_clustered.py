from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.clustered import clustered_bootstrap, kabsch_rmsd


class KabschTests(unittest.TestCase):
    def test_identical_structures_have_zero_rmsd(self):
        rng = np.random.default_rng(0)
        a = rng.normal(size=(20, 3))
        self.assertAlmostEqual(kabsch_rmsd(a, a.copy()), 0.0, places=6)

    def test_rigid_rotation_and_translation_are_removed(self):
        rng = np.random.default_rng(1)
        a = rng.normal(size=(30, 3))
        theta = 0.7
        rot = np.array([[np.cos(theta), -np.sin(theta), 0],
                        [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
        b = a @ rot.T + np.array([5.0, -3.0, 2.0])
        self.assertAlmostEqual(kabsch_rmsd(a, b), 0.0, places=6)

    def test_reflection_is_not_used_to_fake_a_fit(self):
        rng = np.random.default_rng(2)
        a = rng.normal(size=(30, 3))
        mirrored = a * np.array([1.0, 1.0, -1.0])
        self.assertGreater(kabsch_rmsd(a, mirrored), 0.5)

    def test_too_short_returns_nan(self):
        self.assertNotEqual(kabsch_rmsd(np.zeros((2, 3)), np.zeros((2, 3))),
                            kabsch_rmsd(np.zeros((2, 3)), np.zeros((2, 3))))


class ClusteredBootstrapTests(unittest.TestCase):
    def test_clustered_ci_is_wider_than_ignoring_clusters(self):
        """같은 백본 안의 서열은 상관돼 있다. 서열 단위로 재표집하면 구간이
        실제보다 좁아진다."""
        rng = np.random.default_rng(0)
        values, clusters = [], []
        for c in range(12):
            offset = rng.normal(scale=1.0)
            for _ in range(40):
                values.append(offset + rng.normal(scale=0.1))
                clusters.append(f"bb{c}")
        values = np.asarray(values)
        stat = lambda idx: float(values[idx].mean())

        clustered = clustered_bootstrap(clusters, stat, n_boot=2000)
        naive = clustered_bootstrap([f"row{i}" for i in range(len(values))], stat, n_boot=2000)
        self.assertGreater(clustered["ci_width"], naive["ci_width"] * 2)

    def test_point_estimate_uses_all_rows(self):
        values = np.arange(10, dtype=float)
        out = clustered_bootstrap(["a"] * 5 + ["b"] * 5, lambda idx: float(values[idx].mean()))
        self.assertAlmostEqual(out["point"], 4.5)

    def test_excludes_zero_flag(self):
        rng = np.random.default_rng(3)
        values = rng.normal(loc=5.0, scale=0.1, size=60)
        clusters = [f"bb{i//5}" for i in range(60)]
        out = clustered_bootstrap(clusters, lambda idx: float(values[idx].mean()))
        self.assertTrue(out["excludes_zero"])

    def test_too_few_clusters_is_reported_not_guessed(self):
        out = clustered_bootstrap(["a", "a", "b"], lambda idx: 1.0)
        self.assertIsNone(out["ci95"])
        self.assertEqual(out["n_clusters"], 2)


if __name__ == "__main__":
    unittest.main()
