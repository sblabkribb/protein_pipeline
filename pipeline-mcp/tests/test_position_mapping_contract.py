"""위치 매핑 계약. 조용한 off-by-k 를 막는 것이 전부다.

보존도 마스크는 원본 query 번호로, ProteinMPNN fixed position 은 backbone 번호로
표현된다. 그 사이에 번호가 세 번 바뀌고, 틀려도 실행은 성공한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPIKE = ROOT / "public_data" / "benchmark" / "gate0" / "position_mapping_spike.json"


def _spike() -> dict:
    if not SPIKE.exists():
        pytest.skip("매핑 spike 결과 없음")
    return json.loads(SPIKE.read_text(encoding="utf-8"))


def test_mapping_holds_for_every_target_with_a_backbone():
    d = _spike()
    assert d["n_targets_mapped"] >= 1
    for t, m in d["targets"].items():
        assert m["n_staged_residues"] == m["n_backbone_residues"], (
            f"{t}: staged {m['n_staged_residues']} vs backbone "
            f"{m['n_backbone_residues']}")
        assert m["n_mapped"] == m["n_backbone_residues"]


def test_only_generation_infeasible_targets_fail_mapping():
    """매핑 실패는 backbone 부재 때문이어야 한다. 다른 이유면 계약 위반이다."""
    for t, why in _spike()["failures"].items():
        assert "backbone 이 없다" in why, f"{t}: 예상 밖 매핑 실패 - {why}"


def test_resseq_alone_would_be_wrong_for_most_targets():
    """원본 resseq 를 그대로 쓰면 안 된다는 근거를 수치로 고정한다.

    이 테스트가 깨진다면 코호트가 바뀐 것이고, 매핑 방식을 다시 확인해야 한다.
    """
    d = _spike()
    preserved = [t for t, m in d["targets"].items() if m["resseq_is_preserved"]]
    total = len(d["targets"])
    assert len(preserved) < total, (
        "모든 타겟에서 resseq 가 보존된다 - 그렇다면 이 코호트는 실측과 다르다")
    # 실측: 11 중 5 만 보존. 과반이 어긋난다는 사실이 계약의 존재 이유다.
    assert len(preserved) <= total * 0.6


def test_targets_that_lost_leading_residues_are_recorded():
    """앞 잔기가 잘린 타겟은 서열 인덱스에도 오프셋이 생긴다."""
    d = _spike()
    dropped = {t: m["leading_residues_dropped"] for t, m in d["targets"].items()
               if m["leading_residues_dropped"]}
    assert dropped, "앞 잔기가 잘린 타겟이 하나도 없다 - 실측과 다르다"
    for t, n in dropped.items():
        m = d["targets"][t]
        assert m["n_original_residues"] - n == m["n_staged_residues"], (
            f"{t}: 소실 {n} 개로 원본{m['n_original_residues']} → "
            f"staged{m['n_staged_residues']} 가 설명되지 않는다")


def test_hard_fail_conditions_are_declared():
    conditions = " ".join(_spike()["hard_fail_conditions"])
    for phrase in ("연속 부분열", "모호한 대응", "사슬", "아미노산 불일치",
                   "조용한 마스크 축소 금지", "범위 밖"):
        assert phrase in conditions, f"hard fail 목록에 {phrase} 가 없다"
