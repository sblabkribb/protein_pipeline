"""S3 pull 이 outputs/ 밖으로 파일을 쓰지 않는지 고정한다.

이 코드는 prod 서버에서 회수한 것이고 회수 시점에는 검증이 없었다. run_id 는
MCP 인자에서 오므로 경로 조각으로 그대로 쓰면 "../" 하나로 대상 디렉터리를
벗어난다. 원격 key 의 꼬리도 같은 문제를 낸다 - 버킷에 이상한 key 가 있으면
그것도 경로가 된다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.s3 import NCPStorage, _inside, _safe_run_id  # noqa: E402


class FakeClient:
    """download_file 이 어디에 쓰려고 했는지만 기록한다."""

    def __init__(self, keys):
        self._keys = keys
        self.attempted: list[str] = []

    def get_paginator(self, _name):
        keys = self._keys

        class _P:
            def paginate(self, **_kw):
                return [{"Contents": [{"Key": k} for k in keys]}]

        return _P()

    def download_file(self, _bucket, key, dest):
        self.attempted.append(dest)
        Path(dest).write_text("x", encoding="utf-8")


def _storage(client):
    storage = NCPStorage()
    storage._client = client
    storage._initialized = True
    storage.bucket_name = "bucket"
    return storage


class TestRunIdValidation(unittest.TestCase):
    def test_accepts_ordinary_ids(self):
        for value in ("run_2026", "a.b-c_1", "gate0_w2_rfd3_1af7A01"):
            self.assertEqual(_safe_run_id(value), value)

    def test_rejects_traversal_and_separators(self):
        for value in ("../etc", "..", ".", "a/b", "a\\b", "", None, "x" * 129):
            self.assertIsNone(_safe_run_id(value), value)

    def test_rejects_null_byte(self):
        self.assertIsNone(_safe_run_id("run\x00id"))


class TestInside(unittest.TestCase):
    def test_detects_escape(self):
        base = Path("outputs")
        self.assertTrue(_inside(base, base / "a" / "b"))
        self.assertFalse(_inside(base, base / ".." / "x"))


class TestPullRefusesEscape(unittest.TestCase):
    def test_pull_outputs_refuses_bad_run_id(self):
        client = FakeClient([])
        self.assertFalse(_storage(client).pull_outputs("../../etc"))
        self.assertEqual(client.attempted, [])

    def test_pull_summary_refuses_bad_run_id(self):
        client = FakeClient([])
        self.assertFalse(_storage(client).pull_summary("../../etc"))
        self.assertEqual(client.attempted, [])

    def test_pull_outputs_skips_keys_that_escape(self):
        # 버킷이 준 key 의 꼬리가 밖을 가리키는 경우.
        keys = ["outputs/run1/ok.json", "outputs/run1/../../escaped.json"]
        client = FakeClient(keys)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "outputs"
            self.assertTrue(_storage(client).pull_outputs("run1", local_root=str(root)))
            for dest in client.attempted:
                self.assertTrue(_inside(root / "run1", Path(dest)), dest)
            self.assertEqual(len(client.attempted), 1)
            self.assertFalse((Path(tmp) / "escaped.json").exists())


if __name__ == "__main__":
    unittest.main()
