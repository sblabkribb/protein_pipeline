"""MSA query 서열이 배포가 보내는 것과 같은가.

`pipeline.py` 는 `msa_source_pdb_text` 를 전처리한 뒤 `target_record` 를 만들고
그것으로 `target_query_fasta` 를 만든다. `effective_strip_nonpositive` 는
`request.pdb_strip_nonpositive_resseq` (기본 True) 이므로 **배포의 MSA query 는
staged 서열**이다.

전처리를 빼면 resseq <= 0 잔기를 가진 타겟에서 query 가 길어진다. 보존도의
quantile 컷 `floor(L*tier)` 이 달라지고 그 아래 인덱스가 전부 밀리는데, 실행은
성공하고 마스크만 틀린다. v2 24 타겟 중 3 개가 실제로 그랬다.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
PILOT = ROOT / "scripts" / "transcoder" / "48_msa_pilot.py"
FULL = ROOT / "scripts" / "transcoder" / "50_full_msa.py"

#: 실측된 영향 타겟과 손실 잔기 수. 값이 바뀌면 코호트나 전처리가 바뀐 것이다.
AFFECTED = {"2jvfA00": 2, "4yqiA01": 3, "4q68A01": 1}


def _load(path: Path, name: str):
    if not path.exists():
        pytest.skip(f"{name} 없음")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pilot():
    return _load(PILOT, "msa_pilot")


def _full():
    return _load(FULL, "full_msa")


def _default(name):
    from pipeline_mcp.models import PipelineRequest
    f = PipelineRequest.__dataclass_fields__[name]
    return f.default if f.default is not dataclasses.MISSING else f.default_factory()


def test_staging_config_comes_from_the_deployment_defaults():
    cfg = _pilot().deployment_staging()
    assert cfg["strip_nonpositive_resseq"] is bool(_default("pdb_strip_nonpositive_resseq"))
    assert cfg["renumber_resseq_from_1"] is bool(_default("pdb_renumber_resseq_from_1"))
    assert cfg["strip_nonpositive_resseq"] is True, (
        "배포 기본값이 False 로 바뀌었다면 query_sequence 의 전제를 다시 봐야 한다")
    src = PILOT.read_text(encoding="utf-8")
    assert "strip_nonpositive_resseq=True" not in src, "전처리 설정을 하드코딩했다"


def test_deployment_still_preprocesses_before_building_the_msa_query():
    """이 테스트가 깨지면 배포 경로가 바뀐 것이고 query 정의를 다시 봐야 한다."""
    src = (ROOT / "pipeline-mcp" / "src" / "pipeline_mcp" / "pipeline.py").read_text(
        encoding="utf-8")
    assert "effective_strip_nonpositive = bool(request.pdb_strip_nonpositive_resseq)" in src
    assert "_prepare_pdb_text_for_design_context(" in src
    assert "target_record = _target_record_from_pdb(" in src
    assert "target_query_fasta = to_fasta([target_record])" in src


def test_query_sequence_equals_the_staged_ca_sequence():
    """독립적으로 다시 계산해 대조한다."""
    from pipeline_mcp.bio.pdb import preprocess_pdb
    pilot, full = _pilot(), _full()
    cfg = pilot.deployment_staging()
    for row in full.targets():
        text = Path(row["pdb"]).read_text(errors="replace")
        staged, _ = preprocess_pdb(
            text, strip_nonpositive_resseq=cfg["strip_nonpositive_resseq"],
            renumber_resseq_from_1=cfg["renumber_resseq_from_1"])
        assert pilot.query_sequence(row["pdb"]) == pilot.ca_sequence(staged), row["domain"]


def test_the_affected_targets_are_exactly_the_measured_ones():
    """전처리가 실제로 무언가를 바꾸는 타겟이 기록과 같은가."""
    pilot, full = _pilot(), _full()
    got = {}
    for row in full.targets():
        raw = pilot.raw_ca_sequence(row["pdb"])
        staged = pilot.query_sequence(row["pdb"])
        if len(staged) != len(raw):
            got[row["domain"]] = len(raw) - len(staged)
    assert got == AFFECTED, got


def test_the_staged_query_is_a_unique_contiguous_subsequence_of_the_raw():
    """연속 부분열이 아니면 매핑 계약이 성립하지 않는다 (중간 결손)."""
    pilot, full = _pilot(), _full()
    for row in full.targets():
        raw = pilot.raw_ca_sequence(row["pdb"])
        staged = pilot.query_sequence(row["pdb"])
        assert staged in raw, f"{row['domain']}: staged 가 연속 부분열이 아니다"
        assert raw.count(staged) == 1, f"{row['domain']}: 대응이 모호하다"


def test_the_raw_sequence_is_not_used_as_the_query():
    """회귀 방지. 영향 타겟에서 두 값이 실제로 달라야 한다."""
    pilot = _pilot()
    full = _full()
    by = {r["domain"]: r["pdb"] for r in full.targets()}
    for domain in AFFECTED:
        assert pilot.query_sequence(by[domain]) != pilot.raw_ca_sequence(by[domain]), (
            f"{domain}: query 가 아직 원본 전체 서열이다")


def test_both_runners_share_one_query_definition():
    """50_ 이 자체 구현을 들고 있으면 두 경로가 갈라진다."""
    src = FULL.read_text(encoding="utf-8")
    assert "pilot_mod().query_sequence" in src
    assert "def ca_sequence(" not in src, "full 러너가 서열 추출을 따로 구현했다"
