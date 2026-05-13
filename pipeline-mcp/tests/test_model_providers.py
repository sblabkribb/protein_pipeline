from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pipeline_mcp.model_providers import ModelProviderStore
from pipeline_mcp.model_providers import build_provider_summary
from pipeline_mcp.tools import ToolDispatcher


def test_model_provider_store_lists_env_fallbacks_and_masks_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("PROTEINMPNN_PROVIDER", "gpu_http")
    monkeypatch.setenv("PROTEINMPNN_GPU_URL", "http://gpu.example:18101")
    monkeypatch.setenv("PROTEINMPNN_GPU_TOKEN", "secret-token")
    monkeypatch.setenv("BIOEMU_ENDPOINT_ID", "bioemu-runpod")

    store = ModelProviderStore(tmp_path)
    providers = {item["model_key"]: item for item in store.list_effective()}

    assert providers["proteinmpnn"]["provider_type"] == "http_api"
    assert providers["proteinmpnn"]["base_url"] == "http://gpu.example:18101"
    assert providers["proteinmpnn"]["token_masked"] == "********oken"
    assert "token" not in providers["proteinmpnn"]
    assert providers["bioemu"]["provider_type"] == "runpod"
    assert providers["bioemu"]["endpoint_id"] == "bioemu-runpod"


def test_model_provider_store_persists_http_provider_with_encrypted_token(tmp_path):
    store = ModelProviderStore(tmp_path)
    saved = store.upsert(
        "esmfold",
        {
            "provider_type": "http_api",
            "base_url": "http://gpu.example:18162/",
            "token": "worker-token",
            "timeout_s": 123,
            "enabled": True,
        },
        actor="admin",
    )

    assert saved["model_key"] == "esmfold"
    assert saved["token_masked"] == "********oken"
    raw_text = (Path(tmp_path) / "_model_providers" / "providers.json").read_text(encoding="utf-8")
    assert "worker-token" not in raw_text

    reloaded = ModelProviderStore(tmp_path)
    effective = reloaded.get_effective("esmfold", include_secret=True)
    assert effective["provider_type"] == "http_api"
    assert effective["base_url"] == "http://gpu.example:18162"
    assert effective["token"] == "worker-token"


def test_provider_tools_list_and_update_model_providers(tmp_path):
    runner = SimpleNamespace(output_root=str(tmp_path))
    dispatcher = ToolDispatcher(runner)  # type: ignore[arg-type]

    listed = dispatcher.call_tool("pipeline.model_provider_list", {})
    assert any(item["model_key"] == "esmfold" for item in listed["providers"])

    updated = dispatcher.call_tool(
        "pipeline.model_provider_update",
        {
            "model_key": "esmfold",
            "provider": {
                "provider_type": "http_api",
                "base_url": "http://gpu.example:18162",
                "timeout_s": 600,
            },
            "user": {"username": "admin", "role": "admin"},
        },
    )
    assert updated["provider"]["model_key"] == "esmfold"
    assert updated["provider"]["provider_type"] == "http_api"


def test_build_provider_summary_marks_missing_required_fields(tmp_path):
    store = ModelProviderStore(tmp_path)
    store.upsert("rfd3", {"provider_type": "http_api", "enabled": True}, actor="admin")

    summary = build_provider_summary(store)
    rfd3 = next(item for item in summary if item["model_key"] == "rfd3")

    assert rfd3["configured"] is False
    assert rfd3["missing"] == ["base_url"]


def test_custom_model_provider_can_be_added_and_listed(tmp_path):
    store = ModelProviderStore(tmp_path)

    created = store.upsert(
        "esmfold_large",
        {
            "custom": True,
            "label": "ESMFold Large",
            "provider_type": "http_api",
            "base_url": "http://gpu.example:18162",
            "enabled": True,
        },
        actor="admin",
    )

    assert created["model_key"] == "esmfold_large"
    assert created["label"] == "ESMFold Large"
    assert created["custom"] is True

    listed = store.list_effective()
    custom = next(row for row in listed if row["model_key"] == "esmfold_large")
    assert custom["base_url"] == "http://gpu.example:18162"
    assert custom["provider_type"] == "http_api"
