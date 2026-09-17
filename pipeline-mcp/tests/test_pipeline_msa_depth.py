"""MSA 가 얕으면 그 사실이 run 에 남아야 한다.

anjv72_kribb.re.kr_mrna10837 회귀: MMseqs 가 GPU 독점을 못 얻어 query-only 로
폴백했고, 보존도 439개가 전부 1.0 이 됐다. 그 상태로 tier 가 잔기 1-131 /
1-219 / 1-307 연속 구간으로 잘렸는데 run 은 성공으로 끝났다.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.pipeline import PipelineRunner


def _ca_pdb(n: int) -> str:
    lines = [
        f"ATOM      {i + 1:5d}  CA  ALA A {i + 1:4d}       "
        f"{i * 1.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00 20.00           C"
        for i in range(n)
    ]
    return "\n".join(lines + ["END"]) + "\n"


def _run(tmp_path):
    runner = PipelineRunner(
        output_root=str(tmp_path), mmseqs=None, proteinmpnn=None, soluprot=None, af2=None
    )
    request = PipelineRequest(
        target_fasta=">q1\nACDEFGHIK\n",
        target_pdb=_ca_pdb(9),
        dry_run=True,
        num_seq_per_tier=2,
        selected_tiers=[0.5],
        stop_after="soluprot",
    )
    return runner.run(request)


def test_conservation_artifact_always_states_its_information_content(tmp_path):
    """퇴화 여부는 늘 기록된다 - 사후에 판단할 수 있어야 한다."""
    result = _run(tmp_path)
    payload = json.loads(
        (Path(result.output_dir) / "conservation.json").read_text(encoding="utf-8")
    )
    assert payload["distinct_scores"] == len(set(payload["scores"]))
    assert payload["degenerate"] is (payload["distinct_scores"] < 2)


def _flat_conservation(monkeypatch, length: int = 9):
    """보존도를 평탄하게 만든다 - query-only MSA 가 실제로 이렇게 된다."""
    from pipeline_mcp import pipeline as pipeline_module
    from pipeline_mcp.bio.a3m import Conservation

    real = pipeline_module.compute_conservation

    def _flat(a3m_text, *, tiers, mode="quantile", weights=None):
        got = real(a3m_text, tiers=tiers, mode=mode, weights=weights)
        scores = [1.0] * got.query_length
        return Conservation(
            query_length=got.query_length,
            scores=scores,
            fixed_positions_by_tier=got.fixed_positions_by_tier,
        )

    monkeypatch.setattr(pipeline_module, "compute_conservation", _flat)


def test_flat_conservation_is_recorded_in_the_artifact(tmp_path, monkeypatch):
    _flat_conservation(monkeypatch)
    result = _run(tmp_path)
    payload = json.loads(
        (Path(result.output_dir) / "conservation.json").read_text(encoding="utf-8")
    )
    assert payload["degenerate"] is True
    assert payload["distinct_scores"] == 1


def test_flat_conservation_is_reported_in_errors(tmp_path, monkeypatch):
    _flat_conservation(monkeypatch)
    result = _run(tmp_path)
    joined = " | ".join(result.errors)
    assert "conservation" in joined, f"not reported: {result.errors}"
    assert "tier" in joined, joined
    # 어디를 봐야 하는지가 메시지에 있어야 한다.
    assert "usable_hits" in joined, joined
