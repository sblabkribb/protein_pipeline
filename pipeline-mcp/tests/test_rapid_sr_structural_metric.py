"""구조 지표: 기준 백본과 AF2 모델을 어떻게 짝지을 것인가.

동결 정의는 잔기 번호로 짝지었다. 그것이 캠페인 코드가 하는 일이었기 때문인데,
AF2 모델에 대해 맞는 대응인지는 확인하지 않았다. 맞지 않는다.

CATH 도메인 PDB 는 원래 사슬의 번호를 그대로 갖는다 (1af7A01 은 11..284,
1bctA00 은 163..231). AF2 는 접은 서열을 1..N 으로 번호매긴다. 그래서 번호로
짝지으면 겹치는 구간이 통째로 밀리거나 아예 비어 버린다.

같은 모델(pLDDT 92.98)에서 측정한 값:
    번호 대응 + non-loop   29.58 A
    순서 대응 + 전체 CA     2.44 A

ProteinMPNN 은 백본의 잔기 순서대로 서열을 만들고 AF2 는 그 서열을 순서대로
접는다. 그러므로 대응은 **순서** 다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from rapid_sr.structural import (
    ca_records,
    non_loop_indices,
    positional_non_loop_rmsd,
)


def _pdb(n_residues, *, start=1, chain="A", offset=0.0):
    lines = []
    for i in range(n_residues):
        num = start + i
        x = i * 3.8 + offset
        lines.append(
            f"ATOM  {i + 1:5d}  CA  ALA {chain}{num:4d}    "
            f"{x:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00           C"
        )
    return "\n".join(lines) + "\n"


class CaRecordTests(unittest.TestCase):
    def test_records_keep_file_order_and_carry_their_numbering(self):
        records = ca_records(_pdb(3, start=163))
        self.assertEqual([r.index for r in records], [0, 1, 2])
        self.assertEqual([r.resnum for r in records], [163, 164, 165])

    def test_only_ca_atoms_are_taken(self):
        text = _pdb(2) + "ATOM      9  CB  ALA A   1       0.000   0.000   0.000\n"
        self.assertEqual(len(ca_records(text)), 2)


class NonLoopIndexTests(unittest.TestCase):
    def test_non_loop_positions_become_file_order_indices(self):
        reference = _pdb(5, start=163)
        mask = {"A": {(164, ""), (166, "")}}
        self.assertEqual(non_loop_indices(reference, mask), [1, 3])

    def test_a_mask_position_absent_from_the_reference_is_dropped(self):
        self.assertEqual(non_loop_indices(_pdb(3, start=1), {"A": {(99, "")}}), [])

    def test_an_empty_mask_gives_no_indices(self):
        self.assertEqual(non_loop_indices(_pdb(3), {}), [])


class PositionalRmsdTests(unittest.TestCase):
    def test_identical_structures_give_zero(self):
        reference = _pdb(10, start=163)
        model = _pdb(10, start=1)
        mask = {"A": {(163 + i, "") for i in range(10)}}
        self.assertAlmostEqual(positional_non_loop_rmsd(reference, model, mask), 0.0, places=6)

    def test_numbering_offset_does_not_change_the_answer(self):
        """이것이 고치려는 결함 그 자체다."""
        model = _pdb(10, start=1)
        mask_a = {"A": {(1 + i, "") for i in range(10)}}
        mask_b = {"A": {(163 + i, "") for i in range(10)}}
        a = positional_non_loop_rmsd(_pdb(10, start=1), model, mask_a)
        b = positional_non_loop_rmsd(_pdb(10, start=163), model, mask_b)
        self.assertAlmostEqual(a, b, places=9)

    def test_only_masked_positions_are_compared(self):
        reference = _pdb(6)
        model = _pdb(6)
        # 마스크 밖의 잔기를 크게 움직여도 결과가 변하지 않아야 한다.
        moved = model.splitlines()
        moved[5] = moved[5][:30] + f"{999.0:8.3f}" + moved[5][38:]
        mask = {"A": {(1, ""), (2, ""), (3, "")}}
        self.assertAlmostEqual(
            positional_non_loop_rmsd(reference, "\n".join(moved) + "\n", mask),
            positional_non_loop_rmsd(reference, model, mask), places=6)

    def test_a_length_mismatch_is_refused_rather_than_truncated(self):
        """길이가 다르면 순서 대응이 성립하지 않는다. 앞쪽만 잘라 쓰면 조용히 틀린다."""
        with self.assertRaises(ValueError):
            positional_non_loop_rmsd(_pdb(10), _pdb(9), {"A": {(1, ""), (2, ""), (3, "")}})

    def test_too_few_masked_positions_returns_none(self):
        # 세 점으로는 강체 정합이 의미를 갖지 못한다.
        self.assertIsNone(positional_non_loop_rmsd(_pdb(10), _pdb(10), {"A": {(1, ""), (2, "")}}))

    def test_a_rigid_translation_is_removed(self):
        mask = {"A": {(1 + i, "") for i in range(8)}}
        self.assertAlmostEqual(
            positional_non_loop_rmsd(_pdb(8), _pdb(8, offset=25.0), mask), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()


class LigandTests(unittest.TestCase):
    """HETATM 의 CA 는 알파탄소가 아니다.

    "CA" 는 알파탄소이기도 하고 칼슘이기도 하며, 리간드도 CA 라는 이름의 원자를
    가질 수 있다. 1af7A01 의 SAH 가 그래서 기준 잔기 수를 275 로 만들었고,
    모델 274 와 어긋나 길이 가드에 걸렸다.
    """

    def test_a_ligand_ca_is_not_counted_as_a_residue(self):
        text = _pdb(3) + (
            "HETATM 2227  CA  SAH A 287      29.488  21.434  42.668  1.00 14.98           C\n"
        )
        self.assertEqual(len(ca_records(text)), 3)

    def test_a_calcium_ion_is_not_counted_either(self):
        text = _pdb(2) + (
            "HETATM  900 CA    CA A 301       1.000   2.000   3.000  1.00 20.00          CA\n"
        )
        self.assertEqual(len(ca_records(text)), 2)
