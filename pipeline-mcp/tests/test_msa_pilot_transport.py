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
