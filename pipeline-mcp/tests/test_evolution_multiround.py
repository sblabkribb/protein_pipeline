import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from pipeline_mcp import evolution
from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.storage import init_run
from pipeline_mcp.tools import pipeline_request_from_args


class _FakeRunner:
    def __init__(self, output_root: Path):
        self.output_root = str(output_root)
        self.rosetta_relax = None
        self.pool_run_ids: list[str] = []

    def run(self, request: PipelineRequest, *, run_id: str | None = None):
        assert run_id is not None
        self.pool_run_ids.append(run_id)
        paths = init_run(self.output_root, run_id)
        tier_dir = paths.root / "tiers" / "30"
        tier_dir.mkdir(parents=True, exist_ok=True)
        round_no = len(self.pool_run_ids)
        records = []
        scores = {}
        for i in range(8):
            seq_id = f"r{round_no}_seq{i}"
            records.append(f">{seq_id}\nACDEFGHIK{i % 10}\n")
            scores[seq_id] = 0.9
        (tier_dir / "designs.fasta").write_text("".join(records), encoding="utf-8")
        (tier_dir / "soluprot.json").write_text(
            json.dumps({"scores": scores}), encoding="utf-8"
        )
        return SimpleNamespace(run_id=run_id)


def test_pipeline_request_defaults_to_paper_four_round_budget() -> None:
    assert PipelineRequest(target_fasta=">q\nACDE\n", target_pdb="").evolution_rounds == 4
    req = pipeline_request_from_args({"target_fasta": ">q\nACDE\n"})
    assert req.evolution_rounds == 4


def test_run_evolution_executes_initial_training_then_topk_each_round(
    tmp_path, monkeypatch
) -> None:
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        device=lambda name: name,
    )
    monkeypatch.setattr(evolution, "torch", fake_torch)
    monkeypatch.setattr(evolution, "mlflow", None)
    monkeypatch.setattr(evolution.ncp_storage, "sync_outputs", lambda run_id: None)
    fake_module_file = tmp_path / "fakepkg" / "src" / "pipeline_mcp" / "evolution.py"
    monkeypatch.setattr(evolution, "__file__", str(fake_module_file))

    def fake_embeddings(sequences, device):
        values = np.arange(len(sequences) * 2, dtype=np.float64).reshape(len(sequences), 2)
        values[:, 1] = values[:, 1] * 0.5
        return values

    monkeypatch.setattr(evolution, "get_esm_embeddings", fake_embeddings)

    def fake_af2_predict(runner, payload):
        fasta = str(payload["target_fasta"])
        seq_id = fasta.splitlines()[0].lstrip(">")
        eval_paths = init_run(runner.output_root, str(payload["run_id"]))
        (eval_paths.root / "af2" / seq_id).mkdir(parents=True, exist_ok=True)
        (eval_paths.root / "status.json").write_text(
            json.dumps({"run_id": payload["run_id"], "state": "completed"}),
            encoding="utf-8",
        )
        score = 70.0 + float(seq_id.rsplit("seq", 1)[-1])
        return {"summary": {"af2": {seq_id: {"best_plddt": score}}}}

    import pipeline_mcp.tools as tools

    monkeypatch.setattr(tools, "_run_af2_predict", fake_af2_predict)

    runner = _FakeRunner(tmp_path / "outputs")
    request = PipelineRequest(
        target_fasta=">q\nACDEFGHIK\n",
        target_pdb="",
        evolution_mode=True,
        evolution_initial_samples=3,
        evolution_oracle_samples=2,
        evolution_rounds=3,
        evolution_pool_size=12,
        soluprot_cutoff=0.1,
    )

    result = evolution.run_evolution(runner, request, "evo_multi")
    summary = json.loads((Path(result.output_dir) / "summary.json").read_text())

    assert len(runner.pool_run_ids) == 3
    subrun_manifest = json.loads(
        (Path(result.output_dir) / "evolution" / "subruns" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    subruns = subrun_manifest["subruns"]
    assert len(subruns) == 12
    assert sum(1 for item in subruns if item["category"] == "pool") == 3
    assert sum(1 for item in subruns if item["category"] == "oracle") == 9
    for pool_run_id in runner.pool_run_ids:
        assert not (Path(runner.output_root) / pool_run_id).exists()
        assert (
            Path(result.output_dir) / "evolution" / "subruns" / pool_run_id
        ).is_dir()
    assert summary["pool_statistics"]["rounds"] == 3
    assert summary["pool_statistics"]["oracle_train"] == 3
    assert summary["pool_statistics"]["oracle_top_k_per_round"] == 2
    assert summary["pool_statistics"]["oracle_total"] == 9
    assert len(summary["evaluated_samples"]) == 9

    phases = [row["phase"] for row in summary["evaluated_samples"]]
    assert phases.count("round_1_train") == 3
    assert phases.count("round_1_top_k") == 2
    assert phases.count("round_2_top_k") == 2
    assert phases.count("round_3_top_k") == 2
