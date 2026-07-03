import json

from pipeline_mcp.runpod_metrics import get_runpod_metrics_store
from pipeline_mcp.queue_stats import QueueStatsStore
from pipeline_mcp.tools import compute_queue_eta


def test_compute_queue_eta(tmp_path):
    store = get_runpod_metrics_store(str(tmp_path))
    store.set_state("health:epA", json.dumps({"queued": 2, "running": 1, "workers": 1, "t": "t"}))
    QueueStatsStore(tmp_path).record_duration("epA", 60.0)
    out = compute_queue_eta(
        output_root=tmp_path, store=store,
        remaining_stages=[{"stage": "af2", "endpoint_id": "epA"}],
    )
    s = out["per_stage"][0]
    assert s["stage"] == "af2" and s["queued"] == 2 and s["wait_s"] == 120.0
    assert out["est_finish_s"] == 180.0 and out["approximate"] is True


def test_compute_queue_eta_fallback_when_no_duration(tmp_path):
    store = get_runpod_metrics_store(str(tmp_path))
    store.set_state("health:epB", json.dumps({"queued": 5, "running": 0, "workers": 1, "t": "t"}))
    out = compute_queue_eta(
        output_root=tmp_path, store=store,
        remaining_stages=[{"stage": "msa", "endpoint_id": "epB"}],
    )
    s = out["per_stage"][0]
    assert s["queued"] == 5 and s["fallback"] is True and s["wait_s"] is None
    assert out["fallback"] is True
