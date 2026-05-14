import base64
import os
import unittest
from unittest.mock import patch

from pipeline_mcp.clients.proteinmpnn import ProteinMPNNClient
from pipeline_mcp.config import load_config


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class ProteinMPNNGpuHttpClientTest(unittest.TestCase):
    def test_posts_runpod_payload_to_gpu_worker_and_parses_output(self):
        calls = []

        def fake_post(url, *, headers, json, timeout):
            calls.append(
                {
                    "url": url,
                    "headers": headers,
                    "json": json,
                    "timeout": timeout,
                }
            )
            return _FakeResponse(
                {
                    "status": "COMPLETED",
                    "output": {
                        "native": {"name": "native", "header": "native", "sequence": "AAA"},
                        "samples": [{"name": "s1", "header": "sample 1", "sequence": "AFA"}],
                    },
                }
            )

        client = ProteinMPNNClient(
            runpod=None,
            endpoint_id=None,
            gpu_url="http://gpu.internal:18101/",
            gpu_token="worker-secret",
            gpu_timeout_s=123.0,
        )

        with patch("pipeline_mcp.clients.proteinmpnn.requests.post", fake_post):
            native, samples, raw = client.design(
                pdb_text="ATOM\nEND\n",
                pdb_name="target",
                num_seq_per_target=2,
                fixed_positions={"A": [1, 2]},
            )

        self.assertEqual(native.sequence, "AAA")
        self.assertEqual(samples[0].sequence, "AFA")
        self.assertEqual(raw["native"]["sequence"], "AAA")
        self.assertEqual(calls[0]["url"], "http://gpu.internal:18101/run")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer worker-secret")
        self.assertEqual(calls[0]["timeout"], 123.0)
        sent_input = calls[0]["json"]["input"]
        self.assertEqual(sent_input["pdb_name"], "target")
        self.assertEqual(sent_input["fixed_positions"], {"A": [1, 2]})
        self.assertEqual(base64.b64decode(sent_input["pdb_base64"]).decode("utf-8"), "ATOM\nEND\n")


class ProteinMPNNGpuHttpConfigTest(unittest.TestCase):
    def test_gpu_http_provider_does_not_require_runpod_proteinmpnn_endpoint(self):
        env = {
            "RUNPOD_API_KEY": "runpod-key",
            "MMSEQS_ENDPOINT_ID": "mmseqs-endpoint",
            "PROTEINMPNN_PROVIDER": "gpu_http",
            "PROTEINMPNN_GPU_URL": "http://211.188.35.221:18101",
            "PROTEINMPNN_GPU_TOKEN": "worker-secret",
            "PROTEINMPNN_GPU_TIMEOUT_S": "456",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()

        self.assertEqual(cfg.proteinmpnn.provider, "gpu_http")
        self.assertIsNone(cfg.runpod.proteinmpnn_endpoint_id)
        self.assertEqual(cfg.proteinmpnn.gpu_url, "http://211.188.35.221:18101")
        self.assertEqual(cfg.proteinmpnn.gpu_token, "worker-secret")
        self.assertEqual(cfg.proteinmpnn.gpu_timeout_s, 456.0)


if __name__ == "__main__":
    unittest.main()
