from __future__ import annotations

import os
from unittest.mock import patch

from pipeline_mcp.app import build_runner
from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client
from pipeline_mcp.clients.local_http import LocalHTTPBioEmuClient
from pipeline_mcp.clients.local_http import LocalHTTPDiffDockClient
from pipeline_mcp.clients.local_http import LocalHTTPMMseqsClient
from pipeline_mcp.clients.local_http import LocalHTTPRFD3Client
from pipeline_mcp.clients.local_http import LocalHTTPRosettaRelaxClient
from pipeline_mcp.model_providers import ModelProviderStore


def test_build_runner_uses_http_model_provider_registry(tmp_path):
    store = ModelProviderStore(tmp_path)
    for model_key, port in {
        "mmseqs": 18106,
        "bioemu": 18103,
        "rfd3": 18104,
        "diffdock": 18105,
        "colabfold": 18161,
        "rosetta_relax": 18102,
    }.items():
        store.upsert(
            model_key,
            {
                "provider_type": "http_api",
                "base_url": f"http://gpu.example:{port}",
                "timeout_s": 222,
                "enabled": True,
            },
            actor="test",
        )

    env = {
        "RUNPOD_API_KEY": "runpod-key",
        "MMSEQS_ENDPOINT_ID": "mmseqs-runpod",
        "PROTEINMPNN_PROVIDER": "gpu_http",
        "PROTEINMPNN_GPU_URL": "http://gpu.example:18101",
        "PIPELINE_OUTPUT_ROOT": str(tmp_path),
    }
    with patch.dict(os.environ, env, clear=True):
        runner = build_runner()

    assert isinstance(runner.mmseqs, LocalHTTPMMseqsClient)
    assert isinstance(runner.bioemu, LocalHTTPBioEmuClient)
    assert isinstance(runner.rfd3, LocalHTTPRFD3Client)
    assert isinstance(runner.diffdock, LocalHTTPDiffDockClient)
    assert isinstance(runner.colabfold, LocalHTTPAlphaFold2Client)
    assert isinstance(runner.rosetta_relax, LocalHTTPRosettaRelaxClient)
    assert runner.mmseqs.base_url == "http://gpu.example:18106"
    assert runner.colabfold.base_url == "http://gpu.example:18161"
    assert runner.rosetta_relax.base_url == "http://gpu.example:18102"


def test_build_runner_registry_runpod_provider_overrides_legacy_proteinmpnn_env(tmp_path):
    store = ModelProviderStore(tmp_path)
    store.upsert(
        "proteinmpnn",
        {
            "provider_type": "runpod",
            "endpoint_id": "registry-proteinmpnn",
            "enabled": True,
        },
        actor="test",
    )

    env = {
        "RUNPOD_API_KEY": "runpod-key",
        "MMSEQS_ENDPOINT_ID": "mmseqs-runpod",
        "PROTEINMPNN_PROVIDER": "gpu_http",
        "PROTEINMPNN_GPU_URL": "http://legacy-gpu.example:18101",
        "PIPELINE_OUTPUT_ROOT": str(tmp_path),
    }
    with patch.dict(os.environ, env, clear=True):
        runner = build_runner()

    assert runner.proteinmpnn.endpoint_id == "registry-proteinmpnn"
    assert runner.proteinmpnn.gpu_url is None
