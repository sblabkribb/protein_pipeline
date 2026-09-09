"""MSA pilot 진단 스크립트가 배포 경로와 같은 응답 키를 읽는가.

pilot 이 처음에 `a3m`/`a3m_text` 만 읽어서, MMseqs 서버가 정상 응답한 세 타겟을
모두 `MSA_INFEASIBLE` 로 기록했다. 서버는 A3M 을 `a3m_gz_b64` (gzip+base64) 로
주고 배포 경로는 그 키를 읽는다. 약 42 분씩 세 번을 쓰고 나서야 드러났다.

진단 도구가 배포 경로와 다른 키를 읽으면 그 도구의 판정은 파이프라인에 대한
진술이 아니다. 두 경로를 여기서 묶는다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
PILOT = ROOT / "scripts" / "transcoder" / "48_msa_pilot.py"
ARTIFACT = ROOT / "public_data" / "benchmark" / "gate0" / "msa_pilot.json"
PIPELINE = ROOT / "pipeline-mcp" / "src" / "pipeline_mcp" / "pipeline.py"


def _pilot():
    if not PILOT.exists():
        pytest.skip("pilot 스크립트 없음")
    spec = importlib.util.spec_from_file_location("msa_pilot", PILOT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pilot_reads_the_same_response_key_as_the_deployment_path():
    key = _pilot().A3M_RESPONSE_KEY
    src = PIPELINE.read_text(encoding="utf-8")
    assert f'out.get("{key}")' in src, (
        f"배포 경로가 {key!r} 를 읽지 않는다 - pilot 이 다른 키를 보고 있다")


def test_the_pilot_decodes_with_the_shared_helper():
    """자체 디코더를 만들면 배포와 갈라진다."""
    src = PILOT.read_text(encoding="utf-8")
    assert "decode_a3m_gz_b64" in src
    assert "gzip.decompress" not in src, "pilot 이 디코딩을 따로 구현했다"
    from pipeline_mcp.bio.a3m import decode_a3m_gz_b64
    import base64
    import gzip
    text = ">q\nACDE\n>h1\nACDF\n"
    blob = base64.b64encode(gzip.compress(text.encode())).decode()
    assert decode_a3m_gz_b64(blob) == text


def test_the_recorded_failure_is_attributed_to_the_script_not_the_pipeline():
    if not ARTIFACT.exists():
        pytest.skip("pilot 산출물 없음")
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    rc = d["root_cause"]
    assert rc["classification"].startswith("diagnostic script bug")
    assert "48_msa_pilot.py" in rc["where"]
    assert "decode_a3m_gz_b64" in rc["not_where"]
    assert rc["scientific_thresholds_changed"] is False
    assert "usable_hits" in rc["still_unknown"], "무엇을 못 쟀는지 적혀 있어야 한다"


def test_the_operational_timing_result_is_kept_separate_from_the_bug():
    """벽시계 시간은 버그와 무관하게 유효하다. 그것만 남긴다."""
    if not ARTIFACT.exists():
        pytest.skip("pilot 산출물 없음")
    op = json.loads(ARTIFACT.read_text(encoding="utf-8"))["root_cause"][
        "operational_result_that_stands"]
    assert len(op["wall_seconds"]) == 3
    mean_min = sum(op["wall_seconds"]) / 3 / 60
    assert abs(mean_min - op["mean_minutes"]) < 0.1, "평균이 기록과 다르다"
    assert "use_gpu=False" in op["note"], "어떤 설정에서 측정했는지 없다"


def test_the_infeasible_verdicts_are_not_treated_as_target_properties():
    if not ARTIFACT.exists():
        pytest.skip("pilot 산출물 없음")
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert "타겟의 성질이" in d["classification_note"]
    assert "threshold 에 쓰지 않는다" in d["classification_note"]


# ---- Step 7 러너도 같은 경로를 써야 한다 --------------------------------

FULL = ROOT / "scripts" / "transcoder" / "50_full_msa.py"


def _full():
    if not FULL.exists():
        pytest.skip("full MSA 러너 없음")
    spec = importlib.util.spec_from_file_location("full_msa", FULL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_full_runner_uses_the_same_response_key_and_settings_as_the_pilot():
    """pilot 에서 검증한 경로와 다른 경로로 24 타겟을 돌리면 검증이 무의미하다."""
    full, pilot = _full(), _pilot()
    assert full.A3M_RESPONSE_KEY == pilot.A3M_RESPONSE_KEY
    for attr in ("TARGET_DB", "MAX_SEQS", "THREADS", "USE_GPU"):
        assert getattr(full, attr) == getattr(pilot, attr), (
            f"{attr} 가 pilot 과 다르다 - 검증한 설정으로 돌아야 한다")


def test_full_runner_reads_conservation_from_the_deployment_defaults():
    """상수를 다시 적으면 배포와 갈라진다. 그것이 이번 검증의 존재 이유였다."""
    import dataclasses
    from pipeline_mcp.models import PipelineRequest
    cfg = _full().deployment_defaults()

    def d(name):
        f = PipelineRequest.__dataclass_fields__[name]
        return f.default if f.default is not dataclasses.MISSING else f.default_factory()

    assert cfg["conservation_tiers"] == list(d("conservation_tiers")) == [0.3, 0.5, 0.7]
    assert cfg["conservation_mode"] == d("conservation_mode") == "quantile"
    assert cfg["conservation_weighting"] == d("conservation_weighting") == "none"
    src = FULL.read_text(encoding="utf-8")
    assert "[0.3, 0.5, 0.7]" not in src, "tier 를 스크립트에 하드코딩했다"


def test_full_runner_covers_exactly_the_twenty_four_frozen_targets():
    rows = _full().targets()
    assert len(rows) == 24
    import collections
    assert dict(collections.Counter(r["cohort"] for r in rows)) == {
        "calibration_v2": 12, "confirmatory": 12}
    assert len({r["domain"] for r in rows}) == 24, "타겟이 중복됐다"
    # 동결된 두 코호트의 selected 와 정확히 같아야 한다
    for fname, cohort in (("calibration_v2_targets.json", "calibration_v2"),
                          ("masked_holdout_targets.json", "confirmatory")):
        d = json.loads((ROOT / "public_data" / "benchmark" / "gate0" / fname)
                       .read_text(encoding="utf-8"))
        want = sorted(t["domain"] for t in d["selected"])
        got = sorted(r["domain"] for r in rows if r["cohort"] == cohort)
        assert got == want, f"{cohort} 가 동결 목록과 다르다"


def test_full_runner_is_resumable_and_does_not_reselect_on_quality():
    src = FULL.read_text(encoding="utf-8")
    assert "a3m_sha256" in src and "해시 일치" in src, "재개 경로가 없다"
    assert "품질로 타겟 골라내기" in src, "품질 기반 선별 금지가 없다"
    # MSA 는 타겟 수준이므로 실행 경로가 source 로 갈라지지 않아야 한다.
    # docstring 의 설명("두 source 에 동일하게 매핑")은 허용한다.
    rows = _full().targets()
    assert all("source" not in r for r in rows), "타겟 행에 source 축이 있다"
    for branch in ('== "bioemu"', "for source in", "for src in COHORT_SOURCES"):
        assert branch not in src, f"실행 경로가 source 로 갈라진다: {branch}"


def test_the_four_frozen_quality_metrics_are_extracted_from_percentiles():
    """coverage 와 depth 는 백분위 dict 다. 스칼라로 읽으면 값이 정상인데도
    '계산 안 됨' 으로 보인다 - pilot 재실행에서 실제로 그렇게 나왔다."""
    pilot = _pilot()
    q = {"usable_hits": 42,
         "coverage": {"p25": 0.3, "p50": 0.55, "p75": 0.8},
         "depth": {"p10": 3.0, "p50": 21.0, "p90": 40.0},
         "full_length_fraction": 0.31}
    m = pilot.quality_medians(q)
    assert m == {"usable_hits": 42, "median_coverage": 0.55,
                 "median_depth": 21.0, "full_length_fraction": 0.31}
    assert all(isinstance(v, (int, float)) for v in m.values())
    assert set(pilot.quality_medians(None)) == set(m)
    assert all(v is None for v in pilot.quality_medians(None).values())


def test_the_medians_match_the_thresholds_the_code_warns_on():
    """동결 8 절의 네 기준이 코드의 경고 경계와 같은 값을 읽는가."""
    src = (ROOT / "pipeline-mcp" / "src" / "pipeline_mcp" / "bio" / "a3m.py").read_text(
        encoding="utf-8")
    assert 'cov_stats.get("p50"' in src, "코드가 median coverage 로 경고한다"
    assert 'depth_stats.get("p50"' in src, "코드가 median depth 로 경고한다"
    assert "usable_hits < 10" in src
    assert "full_length_fraction < 0.05" in src


def test_the_run_loop_and_reevaluate_share_one_acceptance_function():
    """실행 중 판정과 사후 재평가가 갈라지면 둘 중 어느 것이 맞는지 알 수 없다."""
    src = (ROOT / "scripts" / "transcoder" / "48_msa_pilot.py").read_text(encoding="utf-8")
    assert src.count("evaluate_acceptance(") >= 3, (
        "실행 루프 · reevaluate 두 곳이 같은 함수를 쓰지 않는다")
    assert "quality_medians(entry.get(" in src, "median 추출을 공용 함수로 하지 않는다"
    # 루프가 checks 를 직접 만들지 않아야 한다
    assert '"5_quality_metrics_computed": all(' in src
    assert src.count('"5_quality_metrics_computed"') == 1, (
        "acceptance 정의가 두 군데 있다")

    # 그리고 두 경로가 같은 결과를 내는지 실제로 확인한다
    pilot = _pilot()
    e = _entry()
    a = pilot.evaluate_acceptance(e)
    e2 = dict(e)
    e2.update(a)
    b = pilot.evaluate_acceptance(e2)
    assert a["acceptance"] == b["acceptance"], "재평가가 멱등이 아니다"
    assert a["quality_medians"] == b["quality_medians"]


# ---- acceptance 는 계측 판정이다. 과학 판정이 아니다. --------------------

def _entry(**over):
    e = {"domain": "t", "length": 200, "wall_seconds": 2400.0,
         "endpoint_status": "ok", "a3m_key_present": True, "decode_ok": True,
         "a3m_bytes": 1234, "a3m_empty": False, "hit_count": 800,
         "query_consistent": {"id_match": True, "length_match": True},
         "classification": "OK",
         "msa_quality": {"usable_hits": 790,
                         "coverage": {"p50": 0.71}, "depth": {"p50": 410.0},
                         "full_length_fraction": 0.52, "warnings": []}}
    e.update(over)
    return e


def test_a_shallow_msa_is_a_scientific_observation_not_an_acceptance_failure():
    """usable_hits < 10 은 frozen protocol 에 따른 정상 feasibility 결과다.

    이것을 계측 실패로 세면 "품질 좋은 타겟만 통과" 가 되고, 그 다음 단계는
    threshold 를 만지는 것이다. 사용자가 명시적으로 금지한 경로다.
    """
    pilot = _pilot()
    shallow = _entry(classification="MSA_INSUFFICIENT_DEPTH", hit_count=6,
                     msa_quality={"usable_hits": 5, "coverage": {"p50": 0.44},
                                  "depth": {"p50": 3.0},
                                  "full_length_fraction": 0.2,
                                  "warnings": ["usable_hits=5 (<10)"]})
    r = pilot.evaluate_acceptance(shallow)
    assert r["acceptance_pass"] is True, r["acceptance"]
    assert r["acceptance"]["5_quality_metrics_computed"] is True
    assert r["acceptance"]["6_frozen_rule_applied"] is True
    assert "acceptance 실패가 아니다" in r["acceptance_note"]


def test_a_missing_payload_is_an_acceptance_failure():
    """전송/파싱이 깨지면 계측 실패다 - 그것이 이 pilot 의 목적이다."""
    pilot = _pilot()
    r = pilot.evaluate_acceptance(_entry(
        a3m_key_present=False, decode_ok=None, a3m_bytes=0, a3m_empty=True,
        classification="MSA_INFEASIBLE", msa_quality=None))
    assert r["acceptance_pass"] is False
    bad = {k for k, v in r["acceptance"].items() if not v}
    assert "2_a3m_key_present_and_decoded" in bad
    assert "3_decoded_non_empty" in bad
    assert "5_quality_metrics_computed" in bad
    # 이것이 첫 실행에서 실제로 일어난 상태다
    assert r["acceptance"]["1_endpoint_ok"] is True, "endpoint 는 정상이었다"


def test_a_query_mismatch_is_an_acceptance_failure():
    """길이가 어긋나면 보존도 마스크가 다른 서열에 붙는다."""
    pilot = _pilot()
    r = pilot.evaluate_acceptance(_entry(
        query_consistent={"id_match": True, "length_match": False}))
    assert r["acceptance_pass"] is False
    assert r["acceptance"]["4_query_consistent"] is False


def test_a_decode_failure_is_separated_from_an_endpoint_failure():
    pilot = _pilot()
    r = pilot.evaluate_acceptance(_entry(
        decode_ok=False, a3m_bytes=0, a3m_empty=True,
        classification="MSA_INFEASIBLE", msa_quality=None))
    assert r["acceptance"]["1_endpoint_ok"] is True
    assert r["acceptance"]["2_a3m_key_present_and_decoded"] is False


def test_the_verdict_is_go_only_when_every_target_passes_instrumentation():
    pilot = _pilot()
    rows = [dict(_entry(domain="a"), **pilot.evaluate_acceptance(_entry())),
            dict(_entry(domain="b"), **pilot.evaluate_acceptance(_entry()))]
    assert pilot.print_table(rows) == "GO"
    broken = _entry(domain="c", a3m_bytes=0, a3m_empty=True, msa_quality=None)
    rows.append(dict(broken, **pilot.evaluate_acceptance(broken)))
    assert pilot.print_table(rows) == "BLOCK"
    assert pilot.print_table([]) == "BLOCK", "빈 결과를 GO 로 읽으면 안 된다"


# ---- 24 타겟을 무슨 코드로 돌렸는지 남는가 ------------------------------

def test_run_provenance_is_pinned_once_and_names_the_code():
    """`_write` 마다 HEAD 를 다시 읽으면 17 시간 실행 중 커밋이 생기면 타겟마다
    다른 SHA 가 박힌다. 그러면 '무슨 코드로 돌렸는가' 에 답할 수 없다."""
    prov = _full().run_provenance()
    assert prov["pinned_at_start"] is True
    assert len(prov["code_sha"]) == 40
    assert prov["code_sha"].startswith(prov["code_sha_short"])
    # HEAD 만으로는 부족하다 - 작업 트리가 더러우면 HEAD 가 실행 코드가 아니다
    assert isinstance(prov["worktree_clean_for_code_paths"], bool)
    assert "50_full_msa.py" in prov["script_sha256"]
    assert "48_msa_pilot.py" in prov["script_sha256"]
    for name, digest in prov["script_sha256"].items():
        assert len(digest) == 64, name
        import hashlib
        f = ROOT / "scripts" / "transcoder" / name
        assert hashlib.sha256(f.read_bytes()).hexdigest() == digest


def test_dirty_paths_are_parsed_without_an_offset_slip():
    """porcelain 출력을 고정 오프셋으로 자르면 선행 공백 때문에 한 칸 밀린다."""
    prov = _full().run_provenance()
    for path in prov["dirty_paths"]:
        assert (ROOT / path).exists(), f"경로가 어긋났다: {path!r}"
        assert not path.startswith(("M ", "?", " ")), path


def test_the_manifest_carries_the_pinned_provenance():
    src = FULL.read_text(encoding="utf-8")
    assert '"run_provenance": prov' in src
    assert '"code_sha": prov["code_sha"]' in src
    # _write 안에서 git 을 다시 호출하지 않아야 한다
    body = src[src.index("def _write("):src.index("def _summary(")]
    assert "rev-parse" not in body, "_write 가 HEAD 를 다시 읽는다"
