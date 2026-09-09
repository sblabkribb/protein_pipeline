"""BioEmu backbone 의 매핑·provenance 계약.

RFD3 경로에서는 `staged -> backbone` 이 항등이다 (RFD3 가 잔기 정체와 번호를
보존한다는 것을 실측으로 확인했다). **BioEmu 에서는 항등이 아니다.** BioEmu
topology PDB 는 resseq 0 에서 시작할 수 있고, 파이프라인은 그 경우 앞 잔기를
버리지 않기 위해 1 부터 다시 번호를 매긴다.

그래서 RFD3 의 매핑 가정을 BioEmu 에 그대로 재사용하면 **전 위치가 밀린 마스크로
실행이 성공한다.** 이 파일은 그 재사용을 막는다.

동결 문서: `docs/specs/rapid-v2-multisource-validation-freeze.md` §9
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))

BASE = ROOT / "public_data" / "benchmark" / "gate0"
PLAN = BASE / "multisource_validation_plan.json"
FREEZE = ROOT / "docs" / "specs" / "rapid-v2-multisource-validation-freeze.md"
#: BioEmu 매핑 검증 산출물. 아직 없으면 그 부분은 건너뛴다 (Step 8 에서 생긴다).
MAPPING = BASE / "bioemu_mapping_validation.json"


def _atom(resseq: int, name: str = " CA ", res: str = "ALA", chain: str = "A") -> str:
    return (f"ATOM  {1:>5} {name}{res} {chain}{resseq:>4}"
            f"{'':>4}{0.0:>8.3f}{0.0:>8.3f}{0.0:>8.3f}  1.00  0.00           C")


def _pdb(start: int, n: int = 3) -> str:
    return "\n".join(_atom(start + i) for i in range(n)) + "\nEND\n"


# ---- 코드에 이미 있는 계약 --------------------------------------------------

def test_bioemu_zero_resseq_is_renumbered_and_recorded():
    """0 에서 시작하면 앞 잔기를 버리지 않고 1 부터 다시 번호를 매긴다."""
    from pipeline_mcp.pipeline import _resolve_backbone_preprocess_options
    strip, renumber, detail = _resolve_backbone_preprocess_options(
        pdb_text=_pdb(0), source="bioemu",
        strip_nonpositive_resseq=True, renumber_resseq_from_1=False)
    assert strip is False, "0 을 버리면 N 말단 잔기가 사라지고 전 위치가 밀린다"
    assert renumber is True
    assert detail == "bioemu_zero_resseq_renumbered_from_1", (
        "번호를 다시 매겼는데 기록이 남지 않으면 조용한 오프셋이 된다")


def test_the_same_input_from_rfd3_is_not_silently_renumbered():
    """source 를 보고 다르게 처리한다. RFD3 쪽 동작이 바뀌면 안 된다."""
    from pipeline_mcp.pipeline import _resolve_backbone_preprocess_options
    strip, renumber, detail = _resolve_backbone_preprocess_options(
        pdb_text=_pdb(0), source="rfd3",
        strip_nonpositive_resseq=True, renumber_resseq_from_1=False)
    assert (strip, renumber, detail) == (True, False, None)


def test_bioemu_with_negative_resseq_is_not_renumbered_blindly():
    """음수가 있으면 0-시작 규칙을 적용하지 않는다 - 다른 상황이다."""
    from pipeline_mcp.pipeline import _resolve_backbone_preprocess_options
    text = _atom(-1) + "\n" + _atom(0) + "\n" + _atom(1) + "\nEND\n"
    strip, renumber, detail = _resolve_backbone_preprocess_options(
        pdb_text=text, source="bioemu",
        strip_nonpositive_resseq=True, renumber_resseq_from_1=False)
    assert detail is None
    assert (strip, renumber) == (True, False)


def test_bioemu_starting_at_one_needs_no_special_handling():
    from pipeline_mcp.pipeline import _resolve_backbone_preprocess_options
    strip, renumber, detail = _resolve_backbone_preprocess_options(
        pdb_text=_pdb(1), source="bioemu",
        strip_nonpositive_resseq=True, renumber_resseq_from_1=False)
    assert detail is None


def test_bioemu_takes_a_sequence_not_a_structure():
    """입력이 서열이므로 mapping 의 첫 구간이 RFD3 와 다르다."""
    from pipeline_mcp.clients.bioemu_runpod import BioEmuRunPodClient
    import inspect
    params = inspect.signature(BioEmuRunPodClient.sample).parameters
    assert "sequence" in params
    assert not any("pdb" in p or "structure" in p for p in
                   ("target_pdb", "structure")
                   if p in params), "BioEmu 가 구조를 받는다면 매핑 경로를 다시 봐야 한다"


# ---- 동결 문서가 선언해야 하는 것 -------------------------------------------

def _doc() -> str:
    if not FREEZE.exists():
        pytest.skip("multi-source 동결 문서 없음")
    return FREEZE.read_text(encoding="utf-8")


def test_the_freeze_declares_two_distinct_mapping_paths():
    doc = _doc()
    assert "renumbered_from_1" in doc
    assert "**항등이 아니다.**" in doc, "BioEmu 번호가 항등이 아니라는 선언이 없다"
    assert "bioemu_zero_resseq_renumbered_from_1" in doc, "코드 근거가 인용되지 않았다"


def test_the_freeze_declares_bioemu_specific_hard_fails():
    doc = _doc()
    for phrase in ("구조 서열 != 입력 서열", "잔기 수 != 입력 길이",
                   "사슬이 둘 이상", "1..L 연속이 아님",
                   "detail 이 기록되지 않음"):
        assert phrase in doc, f"BioEmu hard fail 조건 '{phrase}' 가 없다"


def test_silent_mask_shrinking_is_forbidden_for_both_sources():
    doc = _doc()
    assert "조용한 마스크 축소 금지는 두 source 에 똑같이 적용된다" in doc


def test_numbering_convention_is_recorded_per_position():
    doc = _doc()
    assert "numbering_convention" in doc
    assert "rfd3: identity" in doc and "bioemu: renumbered_from_1" in doc


def test_mapping_is_validated_per_source_before_generation():
    """실행 순서에서 매핑 검증이 backbone 생성 앞에 있어야 한다."""
    doc = _doc()
    i_map = doc.index("mapping validation")
    i_gen = doc.index("calibration backbone 생성")
    assert i_map < i_gen, "매핑 검증이 생성 뒤에 있으면 잘못된 마스크로 생성한다"


# ---- 산출물이 생기면 자동으로 켜지는 검증 -----------------------------------

def _mapping() -> dict:
    if not MAPPING.exists():
        pytest.skip("BioEmu 매핑 검증 산출물 없음 (Step 8 에서 생긴다)")
    return json.loads(MAPPING.read_text(encoding="utf-8"))


def test_every_bioemu_backbone_matches_the_input_sequence_exactly():
    """BioEmu 는 서열을 바꾸지 않는다. 다르면 잘못된 구조를 받은 것이다."""
    for target, m in _mapping()["targets"].items():
        assert m["source"] == "bioemu"
        assert m["sequence_identical_to_input"] is True, f"{target}: 서열 불일치"
        assert m["n_residues"] == m["n_input_residues"], (
            f"{target}: 잔기 {m['n_residues']} vs 입력 {m['n_input_residues']}")
        assert m["n_chains"] == 1, f"{target}: 사슬 {m['n_chains']}"
        assert m["numbering_is_1_to_L"] is True, f"{target}: 번호가 1..L 이 아니다"
        assert m["numbering_convention"] == "renumbered_from_1"


def test_no_bioemu_mask_was_silently_shrunk():
    for target, m in _mapping()["targets"].items():
        assert m["n_mapped"] == m["n_query_positions"], (
            f"{target}: query {m['n_query_positions']} 중 {m['n_mapped']} 만 "
            f"대응됐다 - 축소는 성공처럼 보이는 실패다")


def test_mapping_failures_are_only_missing_backbones():
    for target, why in _mapping().get("failures", {}).items():
        assert "backbone 이 없다" in why, f"{target}: 예상 밖 매핑 실패 - {why}"


def test_the_two_sources_get_the_same_conservation_mask():
    """MSA 는 target 수준이므로 두 source 의 query 마스크가 같아야 한다."""
    d = _mapping()
    if "rfd3_query_positions_sha256" not in d:
        pytest.skip("RFD3 쪽 마스크 해시가 아직 없다")
    assert d["rfd3_query_positions_sha256"] == d["bioemu_query_positions_sha256"], (
        "두 source 가 서로 다른 보존도 마스크를 받았다 - MSA 는 target 수준이다")


def test_plan_declares_bioemu_numbering_is_not_identity():
    if not PLAN.exists():
        pytest.skip("plan 없음")
    p = json.loads(PLAN.read_text(encoding="utf-8"))
    assert "bioemu" in p["sources"]["ids"]
    assert p["generation_rules"]["bioemu"]["input"].startswith("native")
