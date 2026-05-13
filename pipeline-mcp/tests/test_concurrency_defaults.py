from __future__ import annotations

import runpy
from pathlib import Path

from pipeline_mcp import pipeline


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pipeline_gpu_http_worker_defaults_are_conservative(monkeypatch):
    monkeypatch.delenv("PIPELINE_AF2_MAX_WORKERS", raising=False)
    monkeypatch.delenv("PIPELINE_RELAX_MAX_WORKERS", raising=False)

    assert getattr(pipeline, "DEFAULT_AF2_MAX_WORKERS", None) == 1
    assert getattr(pipeline, "DEFAULT_RELAX_MAX_WORKERS", None) == 4
    assert (
        pipeline._parallel_worker_limit(
            10,
            env_name="PIPELINE_AF2_MAX_WORKERS",
            default=pipeline.DEFAULT_AF2_MAX_WORKERS,
            hard_cap=12,
        )
        == 1
    )
    assert (
        pipeline._parallel_worker_limit(
            10,
            env_name="PIPELINE_RELAX_MAX_WORKERS",
            default=pipeline.DEFAULT_RELAX_MAX_WORKERS,
            hard_cap=12,
        )
        == 4
    )


def test_cath_batch_defaults_start_with_two_target_workers():
    for relative in (
        "scripts/02_run_cath_batch.py",
        "public_release/scripts/02_run_cath_batch.py",
    ):
        namespace = runpy.run_path(str(REPO_ROOT / relative), run_name="__not_main__")
        assert namespace["MAX_CONCURRENT_PIPELINES"] == 2


def test_cath_ui_default_matches_batch_default():
    html = (REPO_ROOT / "frontend/index.html").read_text(encoding="utf-8")

    assert 'id="cathMaxWorkers" type="number" min="1" step="1" value="2"' in html
