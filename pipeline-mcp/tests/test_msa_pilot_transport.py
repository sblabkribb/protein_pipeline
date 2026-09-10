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
    """재개 동작 자체는 test_full_msa_resume.py 가 검증한다.

    여기서는 경로가 존재하는지와, 품질로 타겟을 골라내지 않는다는 선언만 본다.
    문자열을 고정하면 구현을 고칠 때마다 깨진다 - manifest 기반에서 산출물
    기반으로 바꿨을 때 실제로 그렇게 됐다.
    """
    src = FULL.read_text(encoding="utf-8")
    assert "def from_artifact(" in src, "재개 경로가 없다"
    assert "a3m_sha256" in src
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


def _grid_target_ids() -> set[str]:
    """격자 코호트의 진짜 타겟 집합. 후보 서열이 존재하는 타겟이 정의다."""
    import csv
    f = ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid" / "sequences.csv"
    with f.open(newline="", encoding="utf-8") as fh:
        return {row["target_id"] for row in csv.DictReader(fh)}


def test_the_grid_cohort_reads_resolved_targets_not_the_selected_wishlist():
    """`selected` 는 동결 전 희망 목록이다.

    선정 실패 4 개가 같은 stratum reserve 로 교체됐고(`resolved.rule`), 백본은
    교체 후 목록으로 만들어졌다. `selected` 로 MSA 를 돌리면 fold 가 없는 4 개를
    가져오고 fold 가 있는 4 개를 놓쳐 S4-S6 arm 이 코호트의 1/3 을 조용히 잃는다.
    """
    m = _full()
    d = json.loads((ROOT / "public_data" / "benchmark" / "gate0" /
                    "holdout_targets.json").read_text(encoding="utf-8"))
    wishlist = {t["domain"] for t in d["selected"]}
    resolved = {t["domain"] for t in d["resolved"]["targets"]}
    grid = _grid_target_ids()
    # 두 목록이 실제로 다르다는 것부터 고정한다. 같아지면 이 테스트는 무의미하다.
    assert wishlist != resolved, "교체가 없으면 이 회귀는 재현되지 않는다"
    assert len(wishlist - resolved) == len(resolved - wishlist) == 4
    assert resolved == grid, "resolved.targets 가 격자와 다르다"
    assert {r["domain"] for r in m.targets(m.resolve_cohorts("holdout_grid"))} == grid
    # 기본 두 코호트는 계속 `selected` 를 읽는다.
    assert m.DEFAULT_TARGET_KEY == ("selected",)
    assert set(m.COHORT_TARGET_KEY) == {"holdout_grid"}


def test_cohort_override_is_opt_in_and_leaves_the_default_untouched():
    """`--cohorts` 는 **덮어쓰기 전용**이다.

    동결 v2 흐름(24 타겟)이 `COHORTS` 기본값에 걸려 있다. 인자를 주지 않은
    호출은 이 변경 전과 같은 목록을 내야 한다. 격자 12 타겟은 옵트인으로만
    닿는다.
    """
    m = _full()
    assert m.COHORTS == (("calibration_v2", "calibration_v2_targets.json"),
                         ("confirmatory", "masked_holdout_targets.json"))
    # 인자 없음 == 기본값 명시 == None 해석. 세 경로가 같은 목록이다.
    assert m.resolve_cohorts(None) == m.COHORTS
    assert m.targets() == m.targets(m.COHORTS) == m.targets(m.resolve_cohorts(None))
    assert len(m.targets()) == 24

    grid = m.targets(m.resolve_cohorts("holdout_grid"))
    assert len(grid) == 12
    assert {r["cohort"] for r in grid} == {"holdout_grid"}
    # 기대 목록을 여기에 적지 않는다. 격자에 **실제로 백본이 있는** 타겟을
    # sequences.csv 에서 읽는다 - 목록을 손으로 적었기 때문에 `selected` 와
    # `resolved.targets` 의 4 개 차이를 놓쳤다.
    assert {r["domain"] for r in grid} == _grid_target_ids()
    # 행 스키마가 기본 코호트와 같아야 process() 가 그대로 돈다.
    assert all(set(r) == set(m.targets()[0]) for r in grid)
    # 두 코호트는 겹치지 않는다 - 공유 MSA_DIR 에서 A3M 이 충돌하지 않는 근거다.
    assert not ({r["domain"] for r in grid} & {r["domain"] for r in m.targets()})
    with pytest.raises(SystemExit):
        m.resolve_cohorts("없는코호트")


def test_a_non_default_cohort_cannot_write_the_frozen_v2_manifest():
    """`--out` 기본값은 동결된 v2 산출물이다. 다른 코호트로 그것을 덮어쓰지 않는다."""
    m = _full()
    frozen = m.BASE / "full_msa_manifest.json"
    assert m.OUT == frozen, "기본 --out 이 v2 manifest 가 아니다"
    with pytest.raises(SystemExit):
        m.check_out_path(frozen, m.resolve_cohorts("holdout_grid"))
    # 기본 코호트는 지금까지처럼 그 파일에 쓴다.
    m.check_out_path(frozen, m.COHORTS)
    # 순서만 바꾼 경우도 거절한다 - 타겟 순서가 바뀌면 동결 산출물과 다른
    # 바이트가 되므로 그것도 덮어쓰기다. 다만 메시지는 "코호트를 바꿨다" 가
    # 아니라 무엇이 요청됐고 왜 거절인지를 말해야 한다.
    with pytest.raises(SystemExit) as exc:
        m.check_out_path(frozen, m.resolve_cohorts("confirmatory,calibration_v2"))
    msg = str(exc.value)
    assert "'confirmatory', 'calibration_v2'" in msg, "요청된 순서를 보여주지 않는다"
    assert "기본 순서" in msg, "왜 거절인지 말하지 않는다"


def test_a_non_default_cohort_does_not_stamp_the_v2_provenance(tmp_path):
    """격자 실행이 v2 동결 문서를 자기 provenance 로 찍으면 안 된다.

    `_write` 는 재구성하지 않는다 - 기본 경로의 출력 바이트를 지키는 것이
    그것을 건드리지 않는 이유다. 기본 코호트가 아닐 때만 키가 나온다.
    """
    m = _full()
    rows = m.targets()
    results = [dict(r, classification="OK") for r in rows[:1]]
    cons = {"conservation_tiers": [0.3, 0.5, 0.7], "conservation_mode": "quantile",
            "conservation_weighting": "none"}
    prov = {"code_sha": "x" * 40, "code_sha_short": "xxxxxxx"}

    a, b = tmp_path / "a.json", tmp_path / "b.json"
    m._write(a, results, rows, cons, prov)                 # 인자 생략 = 기존 호출
    m._write(b, results, rows, cons, prov, m.COHORTS)      # 기본 코호트 명시
    da = json.loads(a.read_text(encoding="utf-8"))
    db = json.loads(b.read_text(encoding="utf-8"))
    da.pop("updated_utc"), db.pop("updated_utc")
    assert da == db
    assert "cohorts" not in da, "기본 경로에 새 키가 새어 나왔다"
    assert da["purpose"].startswith("Step 7 - 24 타겟")
    assert da["freeze_doc"] == "docs/specs/rapid-v2-multisource-validation-freeze.md"

    g = tmp_path / "g.json"
    m._write(g, results, rows, cons, prov, m.resolve_cohorts("holdout_grid"))
    dg = json.loads(g.read_text(encoding="utf-8"))
    dg.pop("updated_utc")
    assert dg["cohorts"] == ["holdout_grid"]
    assert "24 타겟" not in dg["purpose"]
    assert dg["freeze_doc"] != da["freeze_doc"]
    # 키 집합은 cohorts 하나만 늘어난다 - _write 를 재구성하지 않았다는 증거.
    assert set(dg) - set(da) == {"cohorts"}
    assert list(dg)[:len(da)] == list(da), "키 순서가 바뀌었다"


def test_the_frozen_default_run_is_decided_in_one_place():
    """`--out` 가드와 manifest provenance 가 같은 사실에 걸려 있다.

    두 곳에 따로 적으면 한쪽만 느슨해져도 조용히 갈라진다.
    """
    m = _full()
    src = FULL.read_text(encoding="utf-8")
    assert src.count("tuple(cohorts) == COHORTS") == 1, "판정이 두 번 적혀 있다"
    assert "tuple(cohorts) != COHORTS" not in src, "부정형이 따로 적혀 있다"
    assert src.count("is_default_run(") >= 3, "정의 1 + 사용 2 가 아니다"
    assert m.is_default_run(m.COHORTS) is True
    assert m.is_default_run(m.resolve_cohorts(None)) is True
    assert m.is_default_run(m.resolve_cohorts("holdout_grid")) is False
    # 순서가 바뀌면 기본 실행이 아니다 - manifest 의 타겟 순서가 바뀐다.
    assert m.is_default_run(m.resolve_cohorts("confirmatory,calibration_v2")) is False


def test_the_module_docstring_carries_the_operating_rules():
    """이 파일의 운영 규칙은 docstring 에 있다.

    새 하드 규칙(--cohorts 를 바꾸면 --out 도 바꿔야 한다)이 argparse help
    안에만 있으면, 이 파일을 읽고 운영하는 사람에게는 없는 것과 같다.
    """
    doc = _full().__doc__
    assert "--cohorts" in doc, "옵트인 코호트 모드가 docstring 에 없다"
    assert "resolved.targets" in doc, "격자가 어느 목록을 읽는지 없다"
    assert "--out" in doc and "읽기 전용" in doc, "동결 manifest 규칙이 없다"
