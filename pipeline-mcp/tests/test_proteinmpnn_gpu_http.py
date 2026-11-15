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

        # ProteinMPNNClient delegates the actual HTTP call to LocalHttpRunClient
        # (see local_http.py) -- that's where requests.post is actually called.
        with patch("pipeline_mcp.clients.local_http.requests.post", fake_post):
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
        # The submit call uses the caller's full configured timeout, since a
        # worker not yet migrated to the async pattern won't answer /run
        # until the job is actually done.
        self.assertEqual(calls[0]["timeout"], 123.0)
        sent_input = calls[0]["json"]["input"]
        self.assertEqual(sent_input["pdb_name"], "target")
        self.assertEqual(sent_input["fixed_positions"], {"A": [1, 2]})
        self.assertEqual(base64.b64decode(sent_input["pdb_base64"]).decode("utf-8"), "ATOM\nEND\n")

    def test_polls_status_when_the_worker_answers_pending(self):
        # Regression test: the ProteinMPNN worker on bop was migrated to the
        # async submit+poll pattern (answers /run with PENDING immediately,
        # finishes in the background). ProteinMPNNClient used to make its own
        # raw requests.post call here instead of going through
        # LocalHttpRunClient, so it treated the immediate PENDING response as
        # the final (invalid) result and crashed every real job with
        # "ProteinMPNN GPU output missing/invalid: {'status': 'PENDING'}".
        get_calls = []

        def fake_post(url, *, headers, json, timeout):
            return _FakeResponse({"id": "job-1", "status": "PENDING"})

        def fake_get(url, *, headers, params, timeout):
            get_calls.append(params)
            if len(get_calls) < 2:
                return _FakeResponse({"id": "job-1", "status": "RUNNING"})
            return _FakeResponse(
                {
                    "id": "job-1",
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
            gpu_timeout_s=60.0,
        )

        with patch("pipeline_mcp.clients.local_http.requests.post", fake_post), \
             patch("pipeline_mcp.clients.local_http.requests.get", fake_get), \
             patch("time.sleep", lambda _s: None):
            native, samples, raw = client.design(
                pdb_text="ATOM\nEND\n",
                pdb_name="target",
                num_seq_per_target=2,
                fixed_positions={"A": [1, 2]},
            )

        self.assertEqual(native.sequence, "AAA")
        self.assertEqual(samples[0].sequence, "AFA")
        self.assertEqual(len(get_calls), 2)
        self.assertTrue(all(call["id"] == "job-1" for call in get_calls))


class ProteinMPNNGpuHttpConfigTest(unittest.TestCase):
    def test_gpu_http_provider_does_not_require_runpod_proteinmpnn_endpoint(self):
        env = {
            "RUNPOD_API_KEY": "runpod-key",
            "MMSEQS_ENDPOINT_ID": "mmseqs-endpoint",
            "PROTEINMPNN_PROVIDER": "gpu_http",
            "PROTEINMPNN_GPU_URL": "http://proteinmpnn-gpu.example.org:18101",
            "PROTEINMPNN_GPU_TOKEN": "worker-secret",
            "PROTEINMPNN_GPU_TIMEOUT_S": "456",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()

        self.assertEqual(cfg.proteinmpnn.provider, "gpu_http")
        self.assertIsNone(cfg.runpod.proteinmpnn_endpoint_id)
        self.assertEqual(cfg.proteinmpnn.gpu_url, "http://proteinmpnn-gpu.example.org:18101")
        self.assertEqual(cfg.proteinmpnn.gpu_token, "worker-secret")
        self.assertEqual(cfg.proteinmpnn.gpu_timeout_s, 456.0)


if __name__ == "__main__":
    unittest.main()


class ProteinMPNNSeedRecordTest(unittest.TestCase):
    """ProteinMPNN reads seed 0 as "draw a random seed yourself" and never says
    which one it drew, so a run launched with the pipeline default could not be
    replayed afterwards. The client now resolves the sentinel itself and records
    both the requested and the effective seed."""

    @staticmethod
    def _client():
        return ProteinMPNNClient(
            runpod=None,
            endpoint_id=None,
            gpu_url="http://gpu.internal:18101/",
            gpu_token=None,
            gpu_timeout_s=10.0,
        )

    @staticmethod
    def _fake_post(calls):
        def fake_post(url, *, headers, json, timeout):
            calls.append(json["input"])
            return _FakeResponse(
                {
                    "status": "COMPLETED",
                    "output": {
                        "native": {"name": "n", "header": "n", "sequence": "AAA"},
                        "samples": [
                            {"name": f"s{i}", "header": f"s{i}", "sequence": "AFA"}
                            for i in range(1, 4)
                        ],
                    },
                }
            )

        return fake_post

    def _design(self, calls, **kwargs):
        with patch("pipeline_mcp.clients.local_http.requests.post", self._fake_post(calls)):
            return self._client().design(pdb_text="ATOM\nEND\n", **kwargs)

    def test_seed_zero_is_resolved_to_a_concrete_seed_and_recorded(self):
        calls = []
        _n, _s, raw = self._design(calls, num_seq_per_target=2, seed=0)

        self.assertEqual(raw["requested_seed"], 0)
        effective = raw["effective_seed"]
        self.assertNotEqual(effective, 0, "seed 0 must not reach the worker")
        # What the worker was told is what we recorded -- that is the whole point.
        self.assertEqual(calls[0]["seed"], effective)

    def test_resolved_seed_differs_between_runs(self):
        # Resolving the sentinel must not make the default deterministic.
        seeds = set()
        for _ in range(5):
            calls = []
            _n, _s, raw = self._design(calls, num_seq_per_target=2, seed=0)
            seeds.add(raw["effective_seed"])
        self.assertGreater(len(seeds), 1, "default runs must still differ from each other")

    def test_explicit_seed_is_passed_through_untouched(self):
        calls = []
        _n, _s, raw = self._design(calls, num_seq_per_target=2, seed=4242)
        self.assertEqual(raw["requested_seed"], 4242)
        self.assertEqual(raw["effective_seed"], 4242)
        self.assertEqual(calls[0]["seed"], 4242)

    def test_chunked_run_offsets_from_the_resolved_seed(self):
        calls = []
        with patch.dict(os.environ, {"PROTEINMPNN_MAX_SEQS_PER_JOB": "2"}):
            _n, _s, raw = self._design(calls, num_seq_per_target=5, seed=100)

        self.assertTrue(raw["chunked"])
        self.assertEqual([c["seed"] for c in calls], [100, 101, 102])
        self.assertEqual([c["seed"] for c in raw["chunks"]], [100, 101, 102])
        self.assertEqual(raw["effective_seed"], 100)

    def test_chunked_run_with_seed_zero_never_sends_the_sentinel(self):
        # The bug this guards: chunk_seed = 0 + chunk_index - 1 left chunk 1
        # random and pinned every later chunk to a fixed seed (1, 2, 3, ...),
        # so two different runs produced identical sequences after chunk 1.
        calls = []
        with patch.dict(os.environ, {"PROTEINMPNN_MAX_SEQS_PER_JOB": "2"}):
            _n, _s, raw = self._design(calls, num_seq_per_target=5, seed=0)

        sent = [c["seed"] for c in calls]
        self.assertNotIn(0, sent, "the sentinel must never reach a chunked worker call")
        self.assertNotIn(1, sent, "chunk 2 must not fall back to a fixed seed of 1")
        base = raw["effective_seed"]
        self.assertEqual(sent, [base, base + 1, base + 2])

    def test_direct_chunked_call_keeps_the_sentinel_for_every_chunk(self):
        # Defensive: a caller reaching _design_chunked without going through
        # design() must get "random" for every chunk, not 0, 1, 2, ...
        calls = []
        with patch("pipeline_mcp.clients.local_http.requests.post", self._fake_post(calls)):
            self._client()._design_chunked(
                pdb_text="ATOM\nEND\n",
                pdb_name="t",
                pdb_path_chains=None,
                fixed_positions=None,
                use_soluble_model=True,
                model_name="v_48_020",
                num_seq_per_target=5,
                max_seq_per_job=2,
                batch_size=1,
                sampling_temp=0.1,
                seed=0,
                backbone_noise=0.0,
                on_job_id=None,
            )
        self.assertEqual([c["seed"] for c in calls], [0, 0, 0])
