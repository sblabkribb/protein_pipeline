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

#: 실측된 strip 영향 타겟과 손실 잔기 수. 값이 바뀌면 코호트나 전처리가 바뀐 것이다.
AFFECTED = {"2jvfA00": 2, "4yqiA01": 3, "4q68A01": 1}

#: 다중 모델(NMR 앙상블) 타겟과 MODEL 수. 두 번째 축이고 별도로 고정한다.
MULTI_MODEL = {"2jvfA00": 20, "1ct7A00": 5, "2m9xA01": 20,
               "1x3aA00": 20, "1sohA00": 18}


def deployment_query(pdb_path: str) -> str:
    """**배포 순서 그대로** query 를 만든다. 이것이 대조 기준이다.

    테스트에서 기대 문자열을 다시 도출하면 같은 버그로 함께 틀릴 수 있다.
    그래서 배포가 쓰는 함수들을 그 순서로 부른다.

      request.target_pdb
        -> normalize_structure_text        ingest. 다중 모델이면 첫 모델만.
        -> _prepare_pdb_text_for_design_context(strip/renumber)
        -> _target_record_from_pdb(...).sequence
    """
    from pipeline_mcp.bio.pdb import normalize_structure_text
    from pipeline_mcp.pipeline import (_prepare_pdb_text_for_design_context,
                                       _target_record_from_pdb)
    cfg = _pilot().deployment_staging()
    text = normalize_structure_text(Path(pdb_path).read_text(errors="replace"))
    staged = _prepare_pdb_text_for_design_context(
        text, chains=None,
        strip_nonpositive_resseq=cfg["strip_nonpositive_resseq"],
        renumber_resseq_from_1=cfg["renumber_resseq_from_1"])
    return _target_record_from_pdb(staged, design_chains=None).sequence


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


def test_the_query_matches_the_deployment_query_builder_on_every_target():
    """기대값을 다시 도출하지 않고 **배포 함수 출력**과 대조한다.

    재도출한 기대값은 같은 버그로 함께 틀릴 수 있다. 24 타겟 전부에서
    strip 축과 multi-model 축을 동시에 덮는 검사다.
    """
    pilot, full = _pilot(), _full()
    for row in full.targets():
        assert pilot.query_sequence(row["pdb"]) == deployment_query(row["pdb"]), (
            row["domain"])


def test_the_multi_model_targets_are_reduced_to_one_model():
    """NMR 앙상블을 안 자르면 92 잔기 도메인이 1840 잔기 query 가 된다.

    두 겹의 방어가 있다. 배포는 ingest 의 `normalize_structure_text` 에서 첫
    모델만 남기고, `ca_sequence` 는 첫 ENDMDL 에서 멈추면서 `(chain, resseq,
    icode)` 로 중복도 제거한다. 어느 한쪽이 사라져도 다른 쪽이 막아야 한다.
    """
    pilot, full = _pilot(), _full()
    by = {r["domain"]: r["pdb"] for r in full.targets()}
    seen = {}
    for domain, path in by.items():
        n = sum(1 for line in Path(path).read_text(errors="replace").splitlines()
                if line.startswith("MODEL "))
        if n:
            seen[domain] = n
    assert seen == MULTI_MODEL, seen

    for domain, n in MULTI_MODEL.items():
        text = Path(by[domain]).read_text(errors="replace")
        ca_rows = sum(1 for line in text.splitlines()
                      if line.startswith("ATOM") and line[12:16].strip() == "CA")
        q = len(pilot.query_sequence(by[domain]))
        # 파일에는 모델 수만큼의 CA 행이 있는데 query 는 한 모델 분량이어야 한다
        assert ca_rows >= q * (n - 1), (domain, n, ca_rows, q)
        assert q < ca_rows / (n - 1), (
            f"{domain}: query {q} 가 {n} 모델 분량({ca_rows} 행)에 가깝다 - "
            f"모델이 잘리지 않았다")

    # ENDMDL 방어가 없어도 중복 제거가 막는지 - 두 겹인지 확인한다
    text = Path(by["2jvfA00"]).read_text(errors="replace")
    no_endmdl = pilot.ca_sequence(text.replace("ENDMDL", "REMARK"))
    first_only = pilot.ca_sequence(text)
    assert len(no_endmdl) - len(first_only) <= 2, (
        "ENDMDL 을 없애면 길이가 배수로 늘어난다 - 중복 제거 방어가 없다")


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


def test_the_methods_sentence_and_the_dependency_are_recorded():
    """왜 strip 이 옳은지, 되돌리면 무엇이 깨지는지가 남아 있어야 한다.

    처음에는 "cloning artifacts" · "no evolutionary signal" 로 적었다. 근거는
    서열 접두 하나였고, 전자는 construct metadata 가 필요하고 후자는 절대명제다.
    지금은 기탁 annotation(SEQADV)과 열 깊이 측정으로 바뀌었다. 이 테스트가 옛
    표현이 되돌아오는 것을 막는다.
    """
    import json
    rec = ROOT / "public_data" / "benchmark" / "gate0" / "msa_query_correction.json"
    if not rec.exists():
        pytest.skip("교정 기록 없음")
    d = json.loads(rec.read_text(encoding="utf-8"))

    prefixes = {t["domain"]: t["dropped_prefix"] for t in d["targets"]}
    assert prefixes == {"2jvfA00": "HM", "4yqiA01": "GSH", "4q68A01": "G"}, prefixes
    for t in d["targets"]:
        assert t["raw_query_length"] - t["staged_query_length"] == len(t["dropped_prefix"])
        assert t["superseded_a3m"]["classification"] in {
            "OK", "MSA_INSUFFICIENT_DEPTH", "MSA_INFEASIBLE"}
        assert t["superseded_a3m"]["sha256_verified"] is True

    dep = d["downstream_dependency"]
    assert dep["items"], "downstream 의존이 비어 있다"
    assert any("S4" in i["what"] for i in dep["items"])
    assert any("아무 예외도 나지 않는다" in i["how"] for i in dep["items"])


def test_the_tag_claim_is_sourced_per_target_not_inferred_from_the_prefix():
    """3 중 2 만 기탁 annotation 이 있다. 셋 다 단정하면 과장이다."""
    import json
    rec = ROOT / "public_data" / "benchmark" / "gate0" / "msa_query_correction.json"
    if not rec.exists():
        pytest.skip("교정 기록 없음")
    ev = {t["domain"]: t["provenance_evidence"] for t in
          json.loads(rec.read_text(encoding="utf-8"))["targets"]}
    annotated = {k for k, v in ev.items() if v["seqadv_expression_tag"]}
    assert annotated == {"4yqiA01", "4q68A01"}, annotated
    assert ev["2jvfA00"]["seqadv_expression_tag"] is False
    assert "확정되지 않았다" in ev["2jvfA00"]["status"]
    for k in annotated:
        assert "UNP" in ev[k]["dbref"], k
        assert "추론이 아니다" in ev[k]["status"], k


def test_the_absolute_claim_was_replaced_by_a_measurement():
    """'진화적 신호가 없다' 대신 열 깊이를 쟀는지."""
    import json
    rec = ROOT / "public_data" / "benchmark" / "gate0" / "msa_query_correction.json"
    if not rec.exists():
        pytest.skip("교정 기록 없음")
    d = json.loads(rec.read_text(encoding="utf-8"))
    ev = {t["domain"]: t["provenance_evidence"] for t in d["targets"]}
    for k in ("4yqiA01", "4q68A01"):
        e = ev[k]
        assert e["column_depth_measurable"] is True
        # 태그 열이 나머지보다 훨씬 얕아야 그 주장이 성립한다
        assert max(e["tag_column_non_gap"]) < e["rest_median_non_gap"] / 10, k
    assert ev["2jvfA00"]["column_depth_measurable"] is False, (
        "hit 1 개로는 태그 열과 나머지를 구분할 수 없다")
    c = d["claim_correction"]
    assert "절대명제" in c["what_was_wrong"]
    assert c["specific_attributions_that_were_wrong"], "틀린 귀속을 적지 않았다"


def test_the_forbidden_phrasings_are_not_in_the_staged_manuscript_text():
    doc = (ROOT / "docs" / "specs" / "rapid-v2-multisource-validation-freeze.md"
           ).read_text(encoding="utf-8")
    flat = doc.replace("\n> ", " ").replace("\n", " ")
    # 플래튼하면 인용 표시 "> " 가 사라지므로 본문으로 자른다
    start = flat.index("Conservation profiles were computed")
    quoted = flat[start:flat.index("쓰지 않는다:", start)]
    for banned in ("were cloning artifacts", "carry no evolutionary signal",
                   "GST-cleavage scar"):
        assert banned not in quoted, f"원고 문장에 과장이 남아 있다: {banned!r}"
    for needed in ("annotated `EXPRESSION TAG`", "SEQADV", "DBREF",
                   "without being established as one",
                   "0.8-2.7% of homologous sequences"):
        assert needed in quoted, f"근거 {needed!r} 가 원고 문장에 없다"
    # 금지 목록 자체는 남아 있어야 재발을 막는다
    assert "construct metadata 확인이 필요하다" in doc
    assert "절대명제다" in doc
