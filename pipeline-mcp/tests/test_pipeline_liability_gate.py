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


def _run(tmp: str, fasta: str, pdb: str) -> Path:
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
    assert result.errors == [], result.errors
    return Path(result.output_dir)


def test_liability_gate_writes_artifacts_and_drops_failing_designs(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LIABILITY_GATE", "1")
    # dry-run 합성 설계는 타겟 서열을 물려받는다. Cys 1개면 free_cysteine
    # 게이트(임시 상한 0)에 걸려 탈락한다.
    fasta = ">q1\nACDEFGHIK\n"
    out = _run(str(tmp_path), fasta, _ca_pdb(["ALA"] * 9))

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
