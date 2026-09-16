from __future__ import annotations

import json
from pathlib import Path

from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.pipeline import PipelineRunner


def _ca_pdb(resnames: list[str]) -> str:
    lines = [
        f"ATOM      {i + 1:5d}  CA  {resname:>3s} A {i + 1:4d}       "
        f"{i * 1.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00 20.00           C"
        for i, resname in enumerate(resnames)
    ]
    return "\n".join(lines + ["END"]) + "\n"


def _panel_events(out: Path) -> list[dict]:
    path = out / "agent_panel.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run(tmp: str, fasta: str, pdb: str, *, allow_errors: bool = False) -> Path:
    runner = PipelineRunner(
        output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None
    )
    request = PipelineRequest(
        target_fasta=fasta,
        target_pdb=pdb,
        dry_run=True,
        num_seq_per_tier=2,
        selected_tiers=[0.5],
    )
    result = runner.run(request)
    if not allow_errors:
        assert result.errors == [], result.errors
    _LAST_ERRORS.clear()
    _LAST_ERRORS.extend(result.errors)
    return Path(result.output_dir)


_LAST_ERRORS: list[str] = []


def test_liability_gate_writes_artifacts_and_drops_failing_designs(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "1")
    # dry-run 합성 설계는 타겟 서열을 물려받는다. Cys 1개면 free_cysteine
    # 게이트(임시 상한 0)에 걸려 탈락한다.
    fasta = ">q1\nACDEFGHIK\n"
    # 차단 모드에서 전부 탈락하면 AF2 후보가 0이 된다. 그건 이제 errors 에 남는다.
    out = _run(str(tmp_path), fasta, _ca_pdb(["ALA"] * 9), allow_errors=True)
    assert any("no candidates" in e for e in _LAST_ERRORS), _LAST_ERRORS

    tier_dir = out / "tiers" / "50"
    payload = json.loads((tier_dir / "liabilities.json").read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["enabled"] is True
    assert summary["evaluated"] > 0
    assert summary["failed"] == summary["evaluated"]
    assert summary["failed_by_objective"]["developability"] == summary["failed"]
    assert summary["calibrated"] is False

    per_sequence = payload["sequences"]
    assert per_sequence, "gate must record per-sequence reports"
    for record in per_sequence:
        gate = record["gate"]
        assert gate["calibrated"] is False
        assert gate["thresholds"]["max_free_cysteine"] == 0
        assert "항체" in gate["threshold_basis"]
    # 탈락하면 AF2 입력이 비어 스테이지가 아예 돌지 않는다 - af2_scores.json
    # 이 없거나, 있으면 비어 있어야 한다.
    af2_scores_path = tier_dir / "af2_scores.json"
    if af2_scores_path.exists():
        af2_scores = json.loads(af2_scores_path.read_text(encoding="utf-8"))
        assert af2_scores.get("candidate_ids", []) == []


def test_liability_gate_disabled_keeps_designs_and_still_records_values(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "0")
    fasta = ">q1\nACDEFGHIK\n"
    out = _run(str(tmp_path), fasta, _ca_pdb(["ALA"] * 9))

    tier_dir = out / "tiers" / "50"
    payload = json.loads((tier_dir / "liabilities.json").read_text(encoding="utf-8"))
    assert payload["summary"]["enabled"] is False
    assert payload["summary"]["failed"] == 0
    for record in payload["sequences"]:
        assert record["gate"]["passed"] is None
        # 게이트가 꺼져도 값 자체는 계속 기록된다.
        assert isinstance(record["max_hydrophobic_patch"], float)
    af2_scores = json.loads((tier_dir / "af2_scores.json").read_text(encoding="utf-8"))
    assert af2_scores["candidate_ids"], "disabled gate must not drop designs"


def test_liability_gate_passes_cysteine_free_designs(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "1")
    monkeypatch.setenv("PIPELINE_DEVELOPABILITY_GATE_MAX_FREE_CYS", "0")
    fasta = ">q1\nADVEGHIK\n"
    out = _run(str(tmp_path), fasta, _ca_pdb(["ALA"] * 9))

    payload = json.loads(
        ((out / "tiers" / "50") / "liabilities.json").read_text(encoding="utf-8")
    )
    assert payload["summary"]["failed"] == 0
    af2_scores = json.loads(
        ((out / "tiers" / "50") / "af2_scores.json").read_text(encoding="utf-8")
    )
    assert af2_scores["candidate_ids"]


def test_liability_gate_default_records_failures_without_dropping_designs(
    tmp_path, monkeypatch
):
    """기본값(미설정)은 기록 전용이다.

    anjv72_kribb.re.kr_mrna10837 회귀: 미보정 항체 임계값이 전 tier 설계를
    조용히 전멸시키고 AF2 가 통째로 스킵됐다. 판정은 계속 기록하되 설계는
    살아남아야 한다.
    """
    monkeypatch.delenv("PIPELINE_LIABILITY_GATE", raising=False)
    fasta = ">q1\nACDEFGHIK\n"  # Cys 1개 -> free_cysteine 임시 상한 0 에 걸린다
    out = _run(str(tmp_path), fasta, _ca_pdb(["ALA"] * 9))

    tier_dir = out / "tiers" / "50"
    payload = json.loads((tier_dir / "liabilities.json").read_text(encoding="utf-8"))
    summary = payload["summary"]
    # 판정과 근거는 그대로 기록된다.
    assert summary["enabled"] is True
    assert summary["evaluated"] > 0
    assert summary["failed"] == summary["evaluated"]
    # 하지만 강제하지 않는다.
    assert summary["enforced"] is False
    assert summary["mode"] == "record"

    af2_scores = json.loads((tier_dir / "af2_scores.json").read_text(encoding="utf-8"))
    assert af2_scores["candidate_ids"], "record-only gate must not drop designs"


def test_liability_gate_is_visible_in_the_agent_panel(tmp_path, monkeypatch):
    """게이트가 판정을 내렸으면 패널에 그 사실이 보여야 한다."""
    monkeypatch.delenv("PIPELINE_LIABILITY_GATE", raising=False)
    fasta = ">q1\nACDEFGHIK\n"
    out = _run(str(tmp_path), fasta, _ca_pdb(["ALA"] * 9))

    stages = [e.get("stage") for e in _panel_events(out)]
    assert "liabilities_50" in stages, f"gate missing from panel: {stages}"

    entry = next(e for e in _panel_events(out) if e.get("stage") == "liabilities_50")
    detail = entry.get("detail") or ""
    assert "record" in detail, detail
    # 몇 개가 걸렸는지가 detail 에 있어야 눈에 띈다.
    assert "failed" in detail, detail


def test_empty_af2_pool_is_reported_instead_of_silently_done(tmp_path, monkeypatch):
    """anjv72_kribb.re.kr_mrna10837 회귀: 후보가 0이면 조용히 넘어가면 안 된다.

    AF2 에 넘길 설계가 하나도 없으면 errors 와 패널 양쪽에 남아야 한다.
    """
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "block")
    fasta = ">q1\nACDEFGHIK\n"
    out = _run(str(tmp_path), fasta, _ca_pdb(["ALA"] * 9), allow_errors=True)

    joined = " | ".join(_LAST_ERRORS)
    assert "af2_50" in joined, f"empty AF2 pool not in errors: {_LAST_ERRORS}"
    assert "no candidates" in joined, joined

    entry = next(
        (e for e in _panel_events(out) if e.get("stage") == "af2_50"), None
    )
    assert entry is not None, "skipped AF2 stage missing from panel"
    assert "skipped" in (entry.get("detail") or ""), entry.get("detail")
