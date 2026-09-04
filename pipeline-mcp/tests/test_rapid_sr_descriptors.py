from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.descriptors import ca_coords, descriptors, DESCRIPTOR_NAMES


def _atom(i, x, y, z, res="ALA", chain="A"):
    return (f"ATOM  {i:5d}  CA  {res} {chain}{i:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C")


class CoordTests(unittest.TestCase):
    def test_reads_only_first_model(self):
        pdb = "\n".join([
            "MODEL        1", _atom(1, 0, 0, 0), _atom(2, 3.8, 0, 0), "ENDMDL",
            "MODEL        2", _atom(1, 9, 9, 9), "ENDMDL",
        ])
        self.assertEqual(ca_coords(pdb).shape, (2, 3))

    def test_duplicate_residue_key_counted_once(self):
        pdb = "\n".join([_atom(1, 0, 0, 0), _atom(1, 1, 1, 1)])
        self.assertEqual(ca_coords(pdb).shape, (1, 3))


class DescriptorTests(unittest.TestCase):
    def test_short_chain_returns_zeros_not_crash(self):
        out = descriptors(np.zeros((0, 3)))
        self.assertEqual(set(out), set(DESCRIPTOR_NAMES))
        self.assertTrue(all(v == 0.0 for v in out.values()))

    def test_extended_chain_has_larger_end_to_end_than_compact(self):
        line = np.stack([np.arange(30) * 3.8, np.zeros(30), np.zeros(30)], axis=1)
        rng = np.random.default_rng(0)
        blob = rng.normal(scale=5.0, size=(30, 3))
        self.assertGreater(
            descriptors(line)["end_to_end_over_rg"],
            descriptors(blob)["end_to_end_over_rg"],
        )

    def test_compact_blob_has_higher_contact_density(self):
        line = np.stack([np.arange(40) * 3.8, np.zeros(40), np.zeros(40)], axis=1)
        rng = np.random.default_rng(1)
        blob = rng.normal(scale=6.0, size=(40, 3))
        self.assertGreater(
            descriptors(blob)["contact_density"], descriptors(line)["contact_density"]
        )

    def test_chain_neighbours_are_not_counted_as_contacts(self):
        line = np.stack([np.arange(10) * 3.8, np.zeros(10), np.zeros(10)], axis=1)
        # 3.8A 간격 직선: 이웃은 8A 안이지만 sep<=3 이라 접촉이 아니다.
        self.assertEqual(descriptors(line)["contact_density"], 0.0)

    def test_n_residues_matches_input(self):
        rng = np.random.default_rng(2)
        self.assertEqual(descriptors(rng.normal(size=(25, 3)))["n_residues"], 25.0)


if __name__ == "__main__":
    unittest.main()
