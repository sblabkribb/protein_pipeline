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
    designed_length,
    model_positions,
    non_loop_indices,
    positional_non_loop_rmsd,
    sequence_indices,
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


class AltLocTests(unittest.TestCase):
    """대체 위치(altLoc)는 한 잔기가 두 번 기록된 것이다.

    1c8zA00 은 CA 레코드가 284 개인데 고유 잔기는 265 개다 - 19 개 잔기가 A/B
    두 벌로 들어 있다. 그대로 세면 모델(265)과 길이가 달라 fail-closed 에
    걸리고, 걸리지 않았다면 그 뒤가 통째로 밀렸을 것이다.
    """

    def _alt(self):
        return (
            "ATOM      1  CA AALA A   1       0.000   0.000   0.000  0.60\n"
            "ATOM      2  CA BALA A   1       9.000   0.000   0.000  0.40\n"
            "ATOM      3  CA  ALA A   2       3.800   0.000   0.000  1.00\n"
        )

    def test_one_record_per_residue(self):
        self.assertEqual(len(ca_records(self._alt())), 2)

    def test_the_first_alternate_is_kept(self):
        first = ca_records(self._alt())[0]
        self.assertAlmostEqual(first.xyz[0], 0.0)

    def test_a_blank_altloc_is_kept_as_is(self):
        self.assertEqual(len(ca_records(_pdb(4))), 4)

    def test_the_same_residue_number_in_two_chains_is_two_residues(self):
        text = _pdb(2, chain="A") + _pdb(2, chain="B")
        self.assertEqual(len(ca_records(text)), 4)


class SequenceIndexTests(unittest.TestCase):
    """설계 서열에서의 인덱스는 파일 순서가 아니라 잔기 번호 구간에서 나온다.

    ProteinMPNN 은 잔기 번호 구간 전체에 걸쳐 서열을 만들고 빠진 자리를 X 로
    채운다. 확인된 예:

        1bxmA00  잔기 -1..98, 0 번 없음  -> 서열 100 자, X 가 인덱스 1
        2wejA00  잔기 3..261, 126 번 없음 -> 서열 259 자, X 가 인덱스 123

    그래서 대응은 `잔기번호 - 최소잔기번호` 다. 파일 순서로 짝지으면 빈 자리
    뒤가 통째로 한 칸씩 밀린다.
    """

    def _with_gap(self, nums=(1, 2, 4)):
        lines = []
        for i, num in enumerate(nums):
            lines.append(
                f"ATOM  {i + 1:5d}  CA  ALA A{num:4d}    "
                f"{num * 3.8:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00           C"
            )
        return "\n".join(lines) + "\n"

    def test_indices_come_from_the_numbering_span(self):
        self.assertEqual(sequence_indices(self._with_gap()), [0, 1, 3])

    def test_shifting_every_number_leaves_the_indices_unchanged(self):
        shifted = self._with_gap().replace("A   1", "A 101").replace(
            "A   2", "A 102").replace("A   4", "A 104")
        self.assertEqual(sequence_indices(shifted), sequence_indices(self._with_gap()))

    def test_the_span_is_longer_than_the_residue_count_when_there_is_a_gap(self):
        self.assertEqual(designed_length(self._with_gap()), 4)
        self.assertEqual(len(ca_records(self._with_gap())), 3)

    def test_a_model_matching_the_span_is_accepted(self):
        # 잔기 1..7 에서 3 번이 빠진 것: 서열 길이 7, 잔기 6 개.
        nums = (1, 2, 4, 5, 6, 7)
        mask = {"A": {(n, "") for n in nums}}
        self.assertIsNotNone(
            positional_non_loop_rmsd(self._with_gap(nums), _pdb(7), mask))

    def test_a_model_matching_the_residue_count_is_the_x_stripped_case(self):
        """AF2 는 X 를 빼고 접는다. 그 길이는 유효하고, 파일 순서로 대응한다."""
        nums = (1, 2, 4, 5, 6, 7)
        self.assertIsNotNone(
            positional_non_loop_rmsd(self._with_gap(nums), _pdb(6),
                                     {"A": {(n, "") for n in nums}}))

    def test_a_length_matching_neither_convention_is_refused(self):
        nums = (1, 2, 4, 5, 6, 7)
        with self.assertRaises(ValueError):
            positional_non_loop_rmsd(self._with_gap(nums), _pdb(5),
                                     {"A": {(n, "") for n in nums}})

    def test_multi_chain_references_are_refused_rather_than_guessed(self):
        text = _pdb(3, chain="A") + _pdb(3, chain="B")
        with self.assertRaises(ValueError):
            sequence_indices(text)


class ModelPositionTests(unittest.TestCase):
    """모델의 어느 잔기가 기준의 어느 잔기인가.

    ProteinMPNN 은 번호 구간 전체에 서열을 만들고 빈 자리를 X 로 채운다. 그런데
    AF2 는 그 X 를 빼고 접는다 - 1bxmA00 은 서열 100 자(X 1 개)인데 모델은 99
    잔기로 돌아왔다. 그래서 대응은 "접힌 서열" 을 기준으로 정해야 한다.

    서열을 알면 정확하다: X 가 아닌 자리들이 순서대로 기준 잔기에 대응한다.
    서열이 없으면 길이로 판별하고, 어느 쪽도 아니면 거부한다.
    """

    def _gapped(self):
        # 잔기 1,2,4,5,6,7 (3 번 없음) -> 구간 7, 잔기 6
        lines = []
        for i, num in enumerate((1, 2, 4, 5, 6, 7)):
            lines.append(
                f"ATOM  {i + 1:5d}  CA  ALA A{num:4d}    "
                f"{num * 3.8:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00           C"
            )
        return "\n".join(lines) + "\n"

    def test_a_model_without_the_x_maps_in_file_order(self):
        positions = model_positions(self._gapped(), _pdb(6), sequence="AA" + "X" + "AAAA")
        self.assertEqual(positions, [0, 1, 2, 3, 4, 5])

    def test_a_model_including_the_x_maps_by_span(self):
        positions = model_positions(self._gapped(), _pdb(7), sequence="AA" + "X" + "AAAA")
        self.assertEqual(positions, [0, 1, 3, 4, 5, 6])

    def test_a_length_that_matches_neither_is_refused(self):
        with self.assertRaises(ValueError):
            model_positions(self._gapped(), _pdb(5), sequence="AAXAAAA")

    def test_a_sequence_that_disagrees_with_the_reference_is_refused(self):
        """서열의 비-X 개수가 기준 잔기 수와 다르면 그 서열은 이 백본의 것이 아니다."""
        with self.assertRaises(ValueError):
            model_positions(self._gapped(), _pdb(6), sequence="AAAA")

    def test_without_a_sequence_the_length_decides(self):
        self.assertEqual(model_positions(self._gapped(), _pdb(6)), [0, 1, 2, 3, 4, 5])
        self.assertEqual(model_positions(self._gapped(), _pdb(7)), [0, 1, 3, 4, 5, 6])

    def test_an_ungapped_backbone_is_unaffected(self):
        self.assertEqual(model_positions(_pdb(5, start=163), _pdb(5)), [0, 1, 2, 3, 4])

    def test_the_rmsd_uses_the_resolved_positions(self):
        mask = {"A": {(n, "") for n in (1, 2, 4, 5, 6, 7)}}
        with_x = positional_non_loop_rmsd(self._gapped(), _pdb(7), mask, sequence="AAXAAAA")
        without = positional_non_loop_rmsd(self._gapped(), _pdb(6), mask, sequence="AAXAAAA")
        self.assertIsNotNone(with_x)
        self.assertIsNotNone(without)
