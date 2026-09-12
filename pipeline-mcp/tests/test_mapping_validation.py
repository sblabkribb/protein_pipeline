"""Step 8 — target 쪽 매핑 검증의 결과 계약.

동결 §9 의 사슬은 두 구간이다. 이 파일은 앞 구간(backbone 이전)만 본다.

    query -> first model -> staged        ← 여기
    staged -> backbone -> fixed positions ← Step 9 이후, source 별

가장 중요한 것은 `test_no_conservation_position_was_silently_dropped` 다. 마스크가
조용히 줄면 실행은 성공하고 설계만 틀린다 - 동결 문서가 특별히 금지하는 실패
양식이다.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "public_data" / "benchmark" / "gate0"
REPORT = BASE / "mapping_validation.json"


def _r() -> dict:
    if not REPORT.exists():
        pytest.skip("매핑 검증 결과 없음")
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_every_target_passed():
    d = _r()
    assert d["n_total"] == 24
    assert d["n_pass"] == d["n_total"], [
        (e["domain"], e["failures"]) for e in d["targets"] if not e["passed"]]


def test_the_query_is_the_staged_sequence_everywhere():
    for e in _r()["targets"]:
        assert e["query_equals_staged"] is True, e["domain"]
        assert e["query_equals_query_sequence"] is True, e["domain"]
        assert e["a3m_query_length"] == e["n_staged_residues"], e["domain"]
        assert e.get("n_aa_mismatch", 0) == 0, e["domain"]


def test_no_conservation_position_was_silently_dropped():
    """대응되지 않는 위치가 하나라도 있으면 실패여야 한다."""
    for e in _r()["targets"]:
        assert e["all_positions_mapped"] is True, e["domain"]
        for tier, t in e["tiers"].items():
            assert t["n_mapped"] == t["n_query_positions"], (e["domain"], tier)


def test_tier_counts_follow_the_frozen_quantile_rule():
    """quantile 모드에서 고정 위치 수는 floor(L * tier) 다."""
    for e in _r()["targets"]:
        L = e["n_staged_residues"]
        for tier, t in e["tiers"].items():
            assert t["n_query_positions"] == math.floor(L * float(tier)), (
                e["domain"], tier, L, t["n_query_positions"])


def test_staging_is_an_unambiguous_contiguous_prefix_drop():
    for e in _r()["targets"]:
        assert e["staged_is_contiguous_subsequence"] is True, e["domain"]
        assert e["staged_occurrences_in_raw"] == 1, e["domain"]
        assert e["staging_offset"] == e["residues_dropped_by_staging"], e["domain"]
        assert len(e["dropped_prefix"]) == e["residues_dropped_by_staging"], e["domain"]


def test_only_the_three_recorded_targets_lose_residues():
    got = {e["domain"]: e["residues_dropped_by_staging"]
           for e in _r()["targets"] if e["residues_dropped_by_staging"]}
    assert got == {"2jvfA00": 2, "4yqiA01": 3, "4q68A01": 1}, got
    prefixes = {e["domain"]: e["dropped_prefix"]
                for e in _r()["targets"] if e["residues_dropped_by_staging"]}
    assert prefixes == {"2jvfA00": "HM", "4yqiA01": "GSH", "4q68A01": "G"}, prefixes


def test_multi_model_targets_were_reduced_before_staging():
    """NMR 앙상블에서 staged 잔기 수가 한 모델 분량이어야 한다."""
    multi = {e["domain"]: e for e in _r()["targets"] if e["n_models_in_file"]}
    assert set(multi) == {"2jvfA00", "1ct7A00", "2m9xA01", "1x3aA00", "1sohA00"}
    for domain, e in multi.items():
        n = e["n_models_in_file"]
        assert e["n_staged_residues"] < e["length_aa"] * 2, (
            f"{domain}: staged {e['n_staged_residues']} 가 {n} 모델 분량에 가깝다")


def test_every_target_is_single_chain():
    for e in _r()["targets"]:
        assert len(e["chains"]) == 1, (e["domain"], e["chains"])


def test_staged_pdbs_exist_and_match_their_digest():
    import hashlib
    for e in _r()["targets"]:
        p = ROOT / e["staged_pdb"]
        assert p.exists(), e["domain"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == e["staged_sha256"], (
            f"{e['domain']}: staged PDB 가 검증 이후 바뀌었다")


def test_the_deferred_leg_is_named():
    """무엇을 아직 검증하지 않았는지가 적혀 있어야 한다."""
    d = _r()
    assert "backbone" in d["chain_deferred"]
    assert "Step 9" in d["chain_deferred"]
    assert d["staging"]["strip_nonpositive_resseq"] is True
