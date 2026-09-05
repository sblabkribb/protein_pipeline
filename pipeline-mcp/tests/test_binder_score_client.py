"""ipSAE binder-score 워커 클라이언트 (bop:18108) 계약.

이 클라이언트가 지켜야 하는 것:
  * 워커가 실패했는데 성공한 것처럼 보이지 않는다.
  * 점수를 못 낸 후보와 컷오프에 걸린 후보를 섞지 않는다. 전자는 정보가 없는
    것이고 후자는 정보가 있는 것이다.
  * 복합체의 global ipTM 을 인터페이스 신뢰도로 되돌려주지 않는다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.clients.binder_score import (
    BinderScoreClient,
    BinderScoreError,
)


class _FakeTransport:
    """POST 를 가로채는 최소 스텁."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, payload, timeout):
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(results):
    return {
        "id": "job-1",
        "status": "COMPLETED",
        "output": {
            "results": results,
            "count": len(results),
            "passed_ids": [r["id"] for r in results if r.get("passed") is True],
            "unscored_ids": [r["id"] for r in results if r.get("passed") is None],
        },
    }


class ScoreTests(unittest.TestCase):
    def _client(self, transport):
        return BinderScoreClient(base_url="http://worker:18108", transport=transport)

    def test_scores_are_returned_in_request_order(self):
        transport = _FakeTransport([_ok([
            {"id": "b", "ipsae": 0.4, "passed": False},
            {"id": "a", "ipsae": 0.8, "passed": True},
        ])])
        client = self._client(transport)
        out = client.score(candidates=[
            {"id": "a", "structure": "ATOM  a"},
            {"id": "b", "structure": "ATOM  b"},
        ])
        self.assertEqual([r["id"] for r in out["results"]], ["a", "b"])

    def test_failed_status_raises_instead_of_returning_empty(self):
        transport = _FakeTransport([{"ok": False, "status": "FAILED", "error": "no PAE"}])
        with self.assertRaises(BinderScoreError) as ctx:
            self._client(transport).score(candidates=[{"id": "a", "structure": "x"}])
        self.assertIn("no PAE", str(ctx.exception))

    def test_missing_candidate_in_response_is_an_error(self):
        transport = _FakeTransport([_ok([{"id": "a", "ipsae": 0.5, "passed": True}])])
        with self.assertRaises(BinderScoreError):
            self._client(transport).score(candidates=[
                {"id": "a", "structure": "x"}, {"id": "b", "structure": "y"},
            ])

    def test_unscored_candidates_are_reported_separately_from_failures(self):
        transport = _FakeTransport([_ok([
            {"id": "a", "ipsae": 0.8, "passed": True},
            {"id": "b", "ipsae": None, "passed": None, "reason": "single chain"},
        ])])
        out = self._client(transport).score(candidates=[
            {"id": "a", "structure": "x"}, {"id": "b", "structure": "y"},
        ])
        self.assertEqual(out["unscored_ids"], ["b"])
        self.assertEqual(out["passed_ids"], ["a"])

    def test_candidates_need_unique_ids(self):
        transport = _FakeTransport([])
        with self.assertRaises(BinderScoreError):
            self._client(transport).score(candidates=[
                {"id": "a", "structure": "x"}, {"id": "a", "structure": "y"},
            ])

    def test_candidate_without_structure_is_rejected_before_the_call(self):
        transport = _FakeTransport([])
        with self.assertRaises(BinderScoreError):
            self._client(transport).score(candidates=[{"id": "a"}])
        self.assertEqual(transport.calls, [])

    def test_request_declares_the_score_task(self):
        transport = _FakeTransport([_ok([{"id": "a", "ipsae": 0.5, "passed": True}])])
        self._client(transport).score(candidates=[{"id": "a", "structure": "x"}])
        self.assertEqual(transport.calls[0]["payload"]["input"]["task"], "score")

    def test_primary_metric_is_ipsae_not_global_iptm(self):
        self.assertEqual(BinderScoreClient.PRIMARY_METRIC, "ipsae")

    def test_global_iptm_is_never_promoted_to_the_primary_metric(self):
        transport = _FakeTransport([_ok([
            {"id": "a", "iptm": 0.95, "ipsae": None, "passed": None},
        ])])
        out = self._client(transport).score(candidates=[{"id": "a", "structure": "x"}])
        self.assertIsNone(out["results"][0]["ipsae"])
        self.assertEqual(out["unscored_ids"], ["a"])

    def test_batches_are_split_and_reassembled_in_order(self):
        transport = _FakeTransport([
            _ok([{"id": "a", "ipsae": 0.1, "passed": True}, {"id": "b", "ipsae": 0.2, "passed": True}]),
            _ok([{"id": "c", "ipsae": 0.3, "passed": True}]),
        ])
        client = BinderScoreClient(
            base_url="http://worker:18108", transport=transport, max_batch_size=2,
        )
        out = client.score(candidates=[
            {"id": i, "structure": "x"} for i in ("a", "b", "c")
        ])
        self.assertEqual([r["id"] for r in out["results"]], ["a", "b", "c"])
        self.assertEqual(len(transport.calls), 2)

    def test_transport_failure_surfaces_as_a_client_error(self):
        transport = _FakeTransport([OSError("connection refused")])
        with self.assertRaises(BinderScoreError):
            self._client(transport).score(candidates=[{"id": "a", "structure": "x"}])

    def test_epitope_spec_is_forwarded_when_given(self):
        transport = _FakeTransport([_ok([{"id": "a", "ipsae": 0.5, "passed": True}])])
        self._client(transport).score(
            candidates=[{"id": "a", "structure": "x"}], epitope="B:12,B:15",
        )
        self.assertEqual(transport.calls[0]["payload"]["input"]["epitope"], "B:12,B:15")


if __name__ == "__main__":
    unittest.main()
