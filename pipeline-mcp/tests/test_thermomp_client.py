from __future__ import annotations

import json as json_module

import pytest

from pipeline_mcp.clients.thermomp import LocalHTTPThermoMPNNClient
from pipeline_mcp.clients.runpod import RunPodClient
from pipeline_mcp.model_providers import ModelProviderStore, provider_api_base


class _Response:
    def __init__(self, payload: dict, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_thermomp_client_sends_pdb_and_mutations_and_parses_output(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[no-untyped-def]
        json_module.dumps(json)
        calls.append({"url": url, "body": json})
        return _Response(
            {
                "id": "thermomp-job-1",
                "status": "COMPLETED",
                "output": {
                    "chain": "A",
                    "n_mutations": 2,
                    "additive_ddg_kcal_mol": 1.42,
                    "mutations": [
                        {"wildtype": "A", "resseq": 12, "mutation": "W", "ddG_kcal_mol": 0.9},
                        {"wildtype": "T", "resseq": 45, "mutation": "G", "ddG_kcal_mol": 0.52},
                    ],
                },
            }
        )

    monkeypatch.setattr("pipeline_mcp.clients.local_http.requests.post", fake_post)

    result = LocalHTTPThermoMPNNClient("http://bop.example:18114").predict(
        pdb_text="ATOM\n",
        target_id="design_1",
        chain="A",
        mutations=["A12W", "T45G"],
    )

    assert calls[0]["url"] == "http://bop.example:18114/run"
    assert calls[0]["body"]["input"]["pdb_content"] == "ATOM\n"
    assert calls[0]["body"]["input"]["mutations"] == ["A12W", "T45G"]
    assert calls[0]["body"]["input"]["target_id"] == "design_1"
    assert result["additive_ddg_kcal_mol"] == 1.42
    assert len(result["mutations"]) == 2


def test_thermomp_client_requires_pdb_text():
    with pytest.raises(ValueError):
        LocalHTTPThermoMPNNClient("http://bop.example:18114").predict(pdb_text="  ")


# --- RunPod 호환 게이트웨이 (biomodel) ---------------------------------------


def test_runpod_client_uses_api_base_for_job_urls(monkeypatch):
    urls: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None, verify=None):  # type: ignore[no-untyped-def]
        urls.append(url)
        return _Response({"id": "job-1", "status": "PENDING"})

    def fake_get(url, headers=None, timeout=None, verify=None):  # type: ignore[no-untyped-def]
        urls.append(url)
        return _Response({"id": "job-1", "status": "COMPLETED", "output": {"ok": True}})

    monkeypatch.setattr("pipeline_mcp.clients.runpod.requests.post", fake_post)
    monkeypatch.setattr("pipeline_mcp.clients.runpod.requests.get", fake_get)

    client = RunPodClient(api_key="key", api_base="https://biomodel.kbiofoundry.kr/v2/")
    data = client.run_and_wait("proteinmpnn-local", {"input": {}})

    assert urls[0] == "https://biomodel.kbiofoundry.kr/v2/proteinmpnn-local/run"
    assert urls[1] == "https://biomodel.kbiofoundry.kr/v2/proteinmpnn-local/status/job-1"
    assert data["output"] == {"ok": True}


def test_runpod_client_falls_back_to_official_api(monkeypatch):
    urls: list[str] = []

    def fake_get(url, headers=None, timeout=None, verify=None):  # type: ignore[no-untyped-def]
        urls.append(url)
        return _Response({"status": {"workers": []}})

    monkeypatch.setattr("pipeline_mcp.clients.runpod.requests.get", fake_get)
    RunPodClient(api_key="key").health("ep-1")
    assert urls == ["https://api.runpod.ai/v2/ep-1/health"]


def test_runpod_client_env_base_wins_over_official(monkeypatch):
    urls: list[str] = []
    monkeypatch.setenv("RUNPOD_API_BASE", "https://gateway.example/v2")

    def fake_post(url, headers=None, json=None, timeout=None, verify=None):  # type: ignore[no-untyped-def]
        urls.append(url)
        return _Response({"id": "job-2"})

    monkeypatch.setattr("pipeline_mcp.clients.runpod.requests.post", fake_post)
    RunPodClient(api_key="key").run("ep-1", {})
    assert urls == ["https://gateway.example/v2/ep-1/run"]


# --- provider store api_base -------------------------------------------------


def test_provider_store_round_trips_api_base(tmp_path):
    store = ModelProviderStore(tmp_path)
    record = store.upsert(
        "proteinmpnn",
        {"provider_type": "runpod", "endpoint_id": "proteinmpnn-local", "api_base": "https://biomodel.kbiofoundry.kr/v2"},
    )
    assert record["api_base"] == "https://biomodel.kbiofoundry.kr/v2"
    assert store.get_effective("proteinmpnn")["api_base"] == "https://biomodel.kbiofoundry.kr/v2"


def test_provider_api_base_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNPOD_API_BASE", raising=False)
    # 저장값 > 환경변수 > 공식 API.
    assert provider_api_base({"api_base": "https://stored/v2"}) == "https://stored/v2"
    monkeypatch.setenv("RUNPOD_API_BASE", "https://env/v2")
    assert provider_api_base({}) == "https://env/v2"
    assert provider_api_base({"api_base": "https://stored/v2"}) == "https://stored/v2"
    monkeypatch.delenv("RUNPOD_API_BASE", raising=False)
    assert provider_api_base({}) == "https://api.runpod.ai/v2"
