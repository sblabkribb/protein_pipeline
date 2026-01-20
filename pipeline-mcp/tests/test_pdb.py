import unittest

from pipeline_mcp.bio.pdb import ligand_proximity_mask
from pipeline_mcp.bio.pdb import preprocess_pdb
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

    def test_atom_chain_as_ligand(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2      20.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  GLY B   1       0.000   0.000   5.000  1.00 20.00           C\n"
            "END\n"
        )
        mask = ligand_proximity_mask(pdb, chains=["A"], distance_angstrom=6.0, ligand_atom_chains=["B"])
        self.assertEqual(mask, {"A": [1]})

    def test_atom_chain_overlap_with_masked_chain_is_ignored(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2      20.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        mask = ligand_proximity_mask(pdb, chains=["A"], distance_angstrom=6.0, ligand_atom_chains=["A"])
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


class TestPdbPreprocess(unittest.TestCase):
    def test_strips_nonpositive_resseq(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A  -1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  SER A   2       2.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        out, mapping = preprocess_pdb(pdb, chains=["A"], strip_nonpositive_resseq=True, renumber_resseq_from_1=False)
        self.assertNotIn("  -1", out)
        self.assertIn("   1", out)
        self.assertIn("   2", out)
        self.assertEqual(
            mapping,
            {
                "A": [
                    {"index": 1, "original_resseq": 1, "original_icode": "", "processed_resseq": 1, "processed_icode": ""},
                    {"index": 2, "original_resseq": 2, "original_icode": "", "processed_resseq": 2, "processed_icode": ""},
                ]
            },
        )

    def test_renumbers_selected_chains_only(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A  10       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A  20       1.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ALA B  10       0.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      4  CA  GLY B  20       1.000   1.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        out, mapping = preprocess_pdb(pdb, chains=["A"], strip_nonpositive_resseq=False, renumber_resseq_from_1=True)
        self.assertIn("A   1", out)
        self.assertIn("A   2", out)
        self.assertIn("B  10", out)
        self.assertIn("B  20", out)
        self.assertEqual(
            mapping.get("A"),
            [
                {"index": 1, "original_resseq": 10, "original_icode": "", "processed_resseq": 1, "processed_icode": ""},
                {"index": 2, "original_resseq": 20, "original_icode": "", "processed_resseq": 2, "processed_icode": ""},
            ],
        )


if __name__ == "__main__":
    unittest.main()
