from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pipeline_mcp import sequence_liabilities as sl


REPO_ROOT = Path(__file__).resolve().parents[2]
REPRO_COPY = REPO_ROOT / "scripts" / "transcoder" / "rapid_sr" / "liabilities.py"


# --- 기본 지표 ---------------------------------------------------------------

def test_max_hydrophobic_patch_matches_hand_computed_window():
    # "ALVFA" 한 창: (1.8 + 3.8 + 4.2 + 2.8 + 1.8) / 5 = 2.88
    assert sl.max_hydrophobic_patch("GALVFA") == 2.88


def test_aggregation_prone_fraction_counts_hydrophobic_uncharged_windows():
    # 한 창(5 잔기). 소수성 2.88 ≥ 2.0 이고 전하 0 ≤ 1.0 → 위험 창.
    assert sl.aggregation_prone_fraction("AALVF") == 1.0
    # 소수성은 2.02 로 같은 높이지만 |전하| 합 2 > 1.0 → 전하가 녹여낸다.
    assert sl.aggregation_prone_fraction("DKLVA") == 0.0


def test_net_charge_counts_kr_de_his_partial():
    # K(+1) R(+1) D(-1) E(-1) H(+0.1) = 0.1
    assert sl.net_charge("KRDEH") == pytest.approx(0.1)


def test_motif_counts_separate_known_liabilities():
    counts = sl.motif_counts("NGDGC")
    assert counts["deamidation_NG"] == 1
    assert counts["isomerisation_DG"] == 1
    assert counts["free_cysteine"] == 1


def test_empty_sequence_gives_none_patch_not_zero():
    assert sl.max_hydrophobic_patch("") is None


# --- 게이트 -------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in list(sl.gate_thresholds()) + ["PIPELINE_LIABILITY_GATE"]:
        monkeypatch.delenv(name.upper() if not name.startswith("PIPELINE_") else name, raising=False)
    monkeypatch.delenv("PIPELINE_LIABILITY_GATE", raising=False)
    monkeypatch.delenv("PIPELINE_AGGREGATION_GATE_MAX_PATCH", raising=False)
    monkeypatch.delenv("PIPELINE_AGGREGATION_GATE_MAX_FRACTION", raising=False)
    monkeypatch.delenv("PIPELINE_DEVELOPABILITY_GATE_MAX_FREE_CYS", raising=False)
    monkeypatch.delenv("PIPELINE_DEVELOPABILITY_GATE_MAX_NG_DG_MOTIFS", raising=False)


def test_gate_judges_by_default_and_reports_calibrated_false():
    report = sl.liability_gate_report("GALVFA")
    gate = report["gate"]
    assert gate["enabled"] is True
    assert gate["passed"] is False  # patch 2.88 > 2.5 임시 상한
    assert gate["calibrated"] is False
    assert gate["thresholds"]["max_hydrophobic_patch"] == 2.5
    assert "항체" in gate["threshold_basis"]


def test_gate_passes_a_benign_sequence():
    report = sl.liability_gate_report("AAAAAKRDE")
    assert report["gate"]["passed"] is True
    assert report["gate"]["reasons"] == []


def test_free_cysteine_fails_developability_leg():
    report = sl.liability_gate_report("AAACAAAA")
    reasons = report["gate"]["reasons"]
    assert any(r.startswith("developability:") for r in reasons)


def test_gate_can_be_disabled_and_then_records_values_only(monkeypatch):
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "0")
    report = sl.liability_gate_report("GALVFA")
    assert report["gate"]["enabled"] is False
    assert report["gate"]["passed"] is None  # 판정을 내지 않는다
    assert report["max_hydrophobic_patch"] == 2.88  # 값은 계속 기록된다


def test_gate_thresholds_are_env_tunable(monkeypatch):
    monkeypatch.setenv("PIPELINE_AGGREGATION_GATE_MAX_PATCH", "3.0")
    monkeypatch.setenv("PIPELINE_AGGREGATION_GATE_MAX_FRACTION", "1.0")
    report = sl.liability_gate_report("GALVFA")
    assert report["gate"]["thresholds"]["max_hydrophobic_patch"] == 3.0
    assert report["gate"]["passed"] is True


def test_summarize_gate_counts_by_objective():
    reports = [
        sl.liability_gate_report("GALVFA"),   # aggregation 실패
        sl.liability_gate_report("AAACAAAA"),  # developability 실패
        sl.liability_gate_report("AAAAAKRDE"),  # 통과
    ]
    summary = sl.summarize_gate(reports)
    assert summary["evaluated"] == 3
    assert summary["failed"] == 2
    assert summary["failed_by_objective"]["aggregation"] == 1
    assert summary["failed_by_objective"]["developability"] == 1
    assert summary["calibrated"] is False


# --- 논문 재현 사본과의 일치 --------------------------------------------------

def test_repro_copy_matches_package_computation():
    """pipeline_mcp 사본과 scripts/transcoder 사본(논문 재현)이 같은 값을 내야 한다."""
    spec = importlib.util.spec_from_file_location("rapid_sr_liabilities_copy", REPRO_COPY)
    assert spec is not None and spec.loader is not None
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)

    sequences = [
        "GALVFA",
        "MKTAYIAKQRQISFVKSHFSRQ",
        "AAAAA:LLLLL",  # 복합체 표기
        "NGDGCW",
    ]
    for seq in sequences:
        for fn in ("net_charge", "max_hydrophobic_patch", "aggregation_prone_fraction"):
            assert getattr(sl, fn)(seq) == getattr(copy, fn)(seq), (fn, seq)
        assert sl.motif_counts(seq) == copy.motif_counts(seq)
        assert sl.liability_report(seq)["calibrated"] is False
        assert copy.liability_report(seq)["calibrated"] is False


# --- 강제(enforce) 여부 -------------------------------------------------------

def test_gate_defaults_to_record_only_and_still_judges():
    """기본값은 기록 전용이다. 판정은 내되 설계를 버리지 않는다."""
    report = sl.liability_gate_report("GALVFA")
    gate = report["gate"]
    assert gate["mode"] == "record"
    assert gate["enforced"] is False
    # 기록 전용이어도 판정과 근거는 그대로 남는다.
    assert gate["enabled"] is True
    assert gate["passed"] is False
    assert gate["reasons"]


def test_gate_blocks_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "block")
    gate = sl.liability_gate_report("GALVFA")["gate"]
    assert gate["mode"] == "block"
    assert gate["enforced"] is True
    assert gate["passed"] is False


def test_gate_legacy_truthy_value_still_blocks(monkeypatch):
    """기존 배포가 쓰던 PIPELINE_LIABILITY_GATE=1 은 계속 차단이다."""
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "1")
    gate = sl.liability_gate_report("GALVFA")["gate"]
    assert gate["mode"] == "block"
    assert gate["enforced"] is True


def test_gate_off_records_no_verdict():
    """off 는 판정 자체를 내지 않는다 (기록 전용과 구분된다)."""
    import os
    os.environ["PIPELINE_LIABILITY_GATE"] = "off"
    try:
        gate = sl.liability_gate_report("GALVFA")["gate"]
    finally:
        del os.environ["PIPELINE_LIABILITY_GATE"]
    assert gate["mode"] == "off"
    assert gate["enforced"] is False
    assert gate["enabled"] is False
    assert gate["passed"] is None


def test_summarize_gate_carries_enforcement_mode():
    reports = [sl.liability_gate_report("GALVFA")]
    summary = sl.summarize_gate(reports)
    assert summary["mode"] == "record"
    assert summary["enforced"] is False
    # 기록 전용이어도 탈락 집계는 남아야 캘리브레이션에 쓸 수 있다.
    assert summary["failed"] == 1
