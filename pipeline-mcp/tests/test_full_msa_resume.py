"""Step 7 러너의 재개와 병렬. 16 시간짜리 실행을 지키는 장치다.

재개를 manifest 가 아니라 **A3M 산출물**에서 한다. 그래야 probe 가 만든 A3M 도,
다른 manifest 에 적힌 A3M 도 그대로 재사용된다. 품질과 보존도 마스크는 A3M 의
결정적 함수이므로 다시 계산해도 같은 값이다.

병렬은 타겟 간에만 한다. per-job 파라미터가 하나도 바뀌지 않아야 배포 일치가
유지되고, 그것을 테스트로 고정한다.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
FULL = ROOT / "scripts" / "transcoder" / "50_full_msa.py"


def _m():
    if not FULL.exists():
        pytest.skip("Step 7 러너 없음")
    spec = importlib.util.spec_from_file_location("full_msa", FULL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CONS = {"conservation_tiers": [0.3, 0.5, 0.7], "conservation_mode": "quantile",
        "conservation_weighting": "none"}

QUERY = "ACDEFGHIKLMNPQRSTVWY" * 3          # 60 aa
A3M = ">q\n" + QUERY + "\n" + "".join(
    f">h{i}\n" + QUERY[:55] + "-----" + "\n" for i in range(40))


def _write_a3m(tmp: Path, domain: str, text: str = A3M) -> Path:
    d = tmp / domain
    d.mkdir(parents=True, exist_ok=True)
    f = d / "result.a3m"
    f.write_text(text, encoding="utf-8")
    return f


def _row(domain="tX"):
    return {"cohort": "calibration_v2", "domain": domain, "stratum": "50-150",
            "length_aa": len(QUERY), "pdb": "/nonexistent.pdb",
            "superfamily": "1.2.3.4"}


def test_measure_is_a_deterministic_function_of_the_a3m():
    m = _m()
    a = m.measure(A3M, len(QUERY), CONS)
    b = m.measure(A3M, len(QUERY), CONS)
    assert a == b, "같은 A3M 에서 다른 값이 나온다"
    assert a["quality_medians"]["usable_hits"] == 40
    assert isinstance(a["quality_medians"]["median_coverage"], float)
    # 보존도 마스크가 tier 마다 나오고 길이가 서열과 맞아야 한다
    assert set(a["conservation"]["tiers"]) == {"0.3", "0.5", "0.7"}
    assert a["conservation"]["query_length_matches_sequence"] is True
    # quantile 이므로 tier 가 커지면 고정 위치가 늘어난다
    n = [a["conservation"]["tiers"][t] for t in ("0.3", "0.5", "0.7")]
    assert n == sorted(n), n
    assert n[2] == int(len(QUERY) * 0.7)


def test_resume_reads_the_artifact_and_recomputes_quality(tmp_path):
    m = _m()
    f = _write_a3m(tmp_path, "tX")
    e = m.from_artifact(_row(), len(QUERY), CONS, {}, msa_dir=tmp_path)
    assert e is not None
    assert e["resumed_from_file"] is True
    assert e["a3m_sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert e["quality_medians"]["usable_hits"] == 40
    assert e["classification"] == "OK"
    # 런타임 값은 파일에서 나오지 않는다
    assert e["endpoint_status"] == "resumed"
    assert "hit_count" not in e


def test_resume_carries_runtime_values_from_any_prior_manifest(tmp_path):
    """probe 가 쓴 manifest 의 hit_count/wall_seconds 를 잃지 않는다."""
    m = _m()
    _write_a3m(tmp_path, "tX")
    prev = {"tX": {"hit_count": 812, "wall_seconds": 2400.0,
                   "endpoint_status": "ok", "decode_ok": True,
                   "query_consistent": {"id_match": True, "length_match": True}}}
    e = m.from_artifact(_row(), len(QUERY), CONS, prev, msa_dir=tmp_path)
    assert e["hit_count"] == 812
    assert e["wall_seconds"] == 2400.0
    assert e["endpoint_status"] == "ok"
    assert e["query_consistent"]["length_match"] is True


def test_resume_flags_a_changed_artifact(tmp_path):
    """파일이 바뀌었으면 조용히 넘어가지 않고 이전 해시를 남긴다."""
    m = _m()
    _write_a3m(tmp_path, "tX")
    prev = {"tX": {"a3m_sha256": "0" * 64}}
    e = m.from_artifact(_row(), len(QUERY), CONS, prev, msa_dir=tmp_path)
    assert e["sha_changed_since"] == "0" * 64
    assert e["a3m_sha256"] != "0" * 64


def test_resume_refuses_an_empty_or_missing_artifact(tmp_path):
    m = _m()
    assert m.from_artifact(_row(), len(QUERY), CONS, {}, msa_dir=tmp_path) is None
    _write_a3m(tmp_path, "tEmpty", text="   \n")
    assert m.from_artifact(_row("tEmpty"), len(QUERY), CONS, {},
                           msa_dir=tmp_path) is None


def test_the_frozen_rule_is_the_only_classifier():
    m = _m()
    assert m.finish({"quality_medians": {"usable_hits": 9}})["classification"] \
        == "MSA_INSUFFICIENT_DEPTH"
    assert m.finish({"quality_medians": {"usable_hits": 10}})["classification"] == "OK"
    # 이미 정해진 판정은 덮지 않는다 (MSA_INFEASIBLE 경로)
    assert m.finish({"classification": "MSA_INFEASIBLE",
                     "quality_medians": {"usable_hits": 500}})["classification"] \
        == "MSA_INFEASIBLE"


def test_a_shallow_msa_resumes_as_a_scientific_observation(tmp_path):
    """usable_hits < 10 인 A3M 도 재개 대상이다. 다시 돌려서 바꾸지 않는다."""
    m = _m()
    shallow = ">q\n" + QUERY + "\n" + "".join(
        f">h{i}\n" + QUERY + "\n" for i in range(4))
    _write_a3m(tmp_path, "tShallow", text=shallow)
    e = m.from_artifact(_row("tShallow"), len(QUERY), CONS, {}, msa_dir=tmp_path)
    assert e["quality_medians"]["usable_hits"] == 4
    assert e["classification"] == "MSA_INSUFFICIENT_DEPTH"
    assert e["resumed_from_file"] is True


def test_parallelism_does_not_touch_per_job_settings():
    """타겟 간 병렬만 한다. per-job 파라미터가 바뀌면 배포 일치가 깨진다."""
    src = FULL.read_text(encoding="utf-8")
    assert "--workers" in src and "ThreadPoolExecutor" in src
    # search 호출이 상수를 그대로 넘기는지 - worker 수에 따라 갈리면 안 된다
    call = src[src.index("resp = client.search("):]
    call = call[:call.index(")")]
    for token in ("target_db=TARGET_DB", "threads=THREADS", "use_gpu=USE_GPU",
                  "max_seqs=MAX_SEQS"):
        assert token in call, f"{token} 이 호출에 없다"
    assert "args.workers" not in call, "worker 수가 검색 설정에 들어간다"
    assert "per-job 설정 불변" in src


def test_prior_manifests_are_all_consulted_for_resume():
    src = FULL.read_text(encoding="utf-8")
    for name in ("full_msa_manifest.json", "msa_probe_concurrency.json"):
        assert name in src, f"{name} 을 재개 후보로 읽지 않는다"
    assert "prev.setdefault" in src, "먼저 읽은 기록을 덮어쓴다"


# ---- 동시성은 측정해서 기각했다. 다시 논쟁하지 않는다. ------------------

PROBE = ROOT / "public_data" / "benchmark" / "gate0" / "msa_probe_concurrency.json"


def test_the_concurrency_verdict_is_recorded_with_its_evidence():
    """측정 없이 worker 를 늘리지 않도록 판정과 근거를 남긴다."""
    if not PROBE.exists():
        pytest.skip("동시성 probe 없음")
    f = json.loads(PROBE.read_text(encoding="utf-8"))["concurrency_finding"]
    assert f["verdict"] == "SERIALIZED"
    assert len(f["evidence"]) >= 3
    joined = " ".join(f["evidence"])
    assert "4171.3" in joined, "probe 실측이 없다"
    assert "2566.1" in joined, "main 이 느려지지 않았다는 근거가 없다"
    assert f["consequence"]["parallel_workers"].startswith("이득 없음")
    assert f["consequence"]["chosen"].startswith("직렬 수용")


def test_the_queue_caveat_on_wall_seconds_is_recorded():
    """큐가 있으면 client wall_seconds 에 대기가 섞인다. 비용으로 읽으면 틀린다."""
    if not PROBE.exists():
        pytest.skip("동시성 probe 없음")
    c = json.loads(PROBE.read_text(encoding="utf-8"))["concurrency_finding"]["consequence"]
    assert "2jvfA00" in c["wall_seconds_caveat"], "영향받은 타겟이 지목되지 않았다"
    assert "타겟별 비용으로 읽지 않는다" in c["wall_seconds_caveat"]


def test_gpu_and_threads_are_still_ruled_out_for_deployment_match():
    if not PROBE.exists():
        pytest.skip("동시성 probe 없음")
    opts = " ".join(json.loads(PROBE.read_text(encoding="utf-8"))
                    ["concurrency_finding"]["consequence"]["remaining_options"])
    assert "배포 불일치이므로 하지 않는다" in opts
    assert "use_gpu" in opts
    # 러너 상수가 실제로 배포 기본값과 같은지 다시 확인한다
    import dataclasses
    from pipeline_mcp.models import PipelineRequest

    def d(name):
        fl = PipelineRequest.__dataclass_fields__[name]
        return fl.default if fl.default is not dataclasses.MISSING else fl.default_factory()

    m = _m()
    assert m.USE_GPU == d("mmseqs_use_gpu") is False
    assert m.THREADS == d("mmseqs_threads") == 4
    assert m.MAX_SEQS == d("mmseqs_max_seqs") == 3000
    assert m.TARGET_DB == d("mmseqs_target_db") == "uniref90"


def test_the_probe_target_is_one_of_the_twenty_four():
    """probe 가 목록 밖 타겟을 썼다면 40 분을 버린 것이다."""
    if not PROBE.exists():
        pytest.skip("동시성 probe 없음")
    d = json.loads(PROBE.read_text(encoding="utf-8"))
    probed = {e["domain"] for e in d["targets"]}
    planned = {r["domain"] for r in _m().targets()}
    assert probed <= planned, sorted(probed - planned)
    assert "1ct7A00" in d["concurrency_finding"]["work_not_wasted"]
