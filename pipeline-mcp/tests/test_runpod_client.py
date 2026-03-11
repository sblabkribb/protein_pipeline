import unittest

import requests

from pipeline_mcp.clients.runpod import RunPodClient


class _FakeResponse:
    def __init__(self, status_code: int, payload: bytes = b"{}") -> None:
        self.status_code = status_code
        self.content = payload

    def raise_for_status(self) -> None:
        raise requests.HTTPError(response=self)


class TestRunPodClient(unittest.TestCase):
    def test_raise_for_status_rewrites_unauthorized_message(self) -> None:
        client = RunPodClient(api_key="bad-key")
        with self.assertRaisesRegex(RuntimeError, "RUNPOD_API_KEY was rejected"):
            client._raise_for_status(_FakeResponse(401))

    def test_raise_for_status_rewrites_forbidden_message(self) -> None:
        client = RunPodClient(api_key="bad-key")
        with self.assertRaisesRegex(RuntimeError, "does not have permission"):
            client._raise_for_status(_FakeResponse(403))


if __name__ == "__main__":
    unittest.main()
