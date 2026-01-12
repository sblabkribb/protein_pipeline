import unittest

from pipeline_mcp.bio.pdb import ligand_proximity_mask
from pipeline_mcp.bio.pdb import sequence_by_chain


class TestPdbLigandMask(unittest.TestCase):
    def test_ligand_mask_distance(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2      20.000   0.000   0.000  1.00 20.00           C\n"
            "HETATM    3  C1  LIG A 100       0.000   0.000   5.000  1.00 20.00           C\n"
            "END\n"
        )
        mask = ligand_proximity_mask(pdb, chains=["A"], distance_angstrom=6.0)
        self.assertEqual(mask, {"A": [1]})

    def test_ligand_resname_filter(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "HETATM    3  C1  LIG A 100       0.000   0.000   5.000  1.00 20.00           C\n"
            "END\n"
        )
        mask = ligand_proximity_mask(pdb, chains=["A"], distance_angstrom=6.0, ligand_resnames=["XXX"])
        self.assertEqual(mask, {"A": []})


class TestPdbSequenceExtraction(unittest.TestCase):
    def test_sequence_by_chain_from_atom_records(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "HETATM    3  C1  LIG A 100       0.000   0.000   5.000  1.00 20.00           C\n"
            "END\n"
        )
        seqs = sequence_by_chain(pdb)
        self.assertEqual(seqs, {"A": "AG"})


if __name__ == "__main__":
    unittest.main()
