from __future__ import annotations

import json as json_module

from pipeline_mcp.clients.local_http import LocalHTTPBioEmuClient
from pipeline_mcp.clients.local_http import LocalHTTPDiffDockClient
from pipeline_mcp.clients.local_http import LocalHTTPRFD3Client


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_local_http_rfd3_does_not_send_callback_in_json_payload(monkeypatch):
    calls: list[dict] = []
    seen_job_ids: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[no-untyped-def]
        json_module.dumps(json)
        calls.append(json)
        return _Response({"status": "COMPLETED", "job_id": "rfd3-local-job", "output": {"selected_pdb": "ATOM\n"}})

    monkeypatch.setattr("pipeline_mcp.clients.local_http.requests.post", fake_post)

    result = LocalHTTPRFD3Client("http://gpu.example:18104").design(
        inputs={"spec-1": {"contig": "A1-10"}},
        on_job_id=seen_job_ids.append,
    )

    assert result["selected_pdb"] == "ATOM\n"
    assert "on_job_id" not in calls[0]["input"]
    assert seen_job_ids == ["rfd3-local-job"]


def test_local_http_bioemu_does_not_send_callback_in_json_payload(monkeypatch):
    calls: list[dict] = []
    seen_job_ids: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[no-untyped-def]
        json_module.dumps(json)
        calls.append(json)
        return _Response({"status": "COMPLETED", "job_id": "bioemu-local-job", "output": {"samples": []}})

    monkeypatch.setattr("pipeline_mcp.clients.local_http.requests.post", fake_post)

    result = LocalHTTPBioEmuClient("http://gpu.example:18103").sample(
        sequence="ACDE",
        on_job_id=seen_job_ids.append,
    )

    assert result["samples"] == []
    assert "on_job_id" not in calls[0]["input"]
    assert seen_job_ids == ["bioemu-local-job"]


def test_local_http_diffdock_does_not_send_callback_in_json_payload(monkeypatch):
    calls: list[dict] = []
    seen_job_ids: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[no-untyped-def]
        json_module.dumps(json)
        calls.append(json)
        return _Response(
            {
                "status": "COMPLETED",
                "job_id": "diffdock-local-job",
                "output": {"sdf_text": "ligand"},
            }
        )

    monkeypatch.setattr("pipeline_mcp.clients.local_http.requests.post", fake_post)

    result = LocalHTTPDiffDockClient("http://gpu.example:18105").dock(
        protein_pdb="ATOM\n",
        ligand_smiles="CCO",
        on_job_id=seen_job_ids.append,
    )

    assert result["sdf_text"] == "ligand"
    assert "on_job_id" not in calls[0]["input"]
    assert seen_job_ids == ["diffdock-local-job"]
