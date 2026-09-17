"""ESM embedding 워커의 유휴 언로드.

이 워커는 GPU 카드를 다른 워커와 공유한다. 8M 모델이라 가중치는 작지만,
PyTorch 캐싱 할당자가 과거 배치 피크를 반납하지 않아 상주 프로세스가 카드를
수십 GB 물고 있을 수 있다 (2026-09-17: 18 GB 점유 실측). 그래서 유휴가 지속되면
모델을 내리고 캐시를 비운다.
"""

import importlib.util
from pathlib import Path
import sys
import unittest


def _load_embedder():
    path = Path(__file__).resolve().parents[1] / "workers" / "esm_embedding" / "embedder.py"
    spec = importlib.util.spec_from_file_location("esm_embedder_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # @dataclass 가 sys.modules 로 자기 모듈을 찾으므로 exec 전에 등록한다.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeModel:
    def to(self, device):  # pragma: no cover - 편의용
        return self


class EsmEmbeddingIdleUnloadTest(unittest.TestCase):
    def setUp(self):
        self.m = _load_embedder()
        # 실제 모델을 올리지 않고 "올라간 상태"만 만든다.
        self.m._TOKENIZER = object()
        self.m._MODEL = _FakeModel()
        self.m._MODEL_NAME = "facebook/esm2_t6_8M_UR50D"
        self.m._DEVICE = "cpu"

    def test_model_is_unloaded_after_the_idle_window(self):
        self.m._LAST_USED = 1000.0
        freed = self.m.maybe_unload_idle(now=1000.0 + self.m.idle_unload_s() + 1)
        self.assertTrue(freed)
        self.assertIsNone(self.m._MODEL)
        self.assertIsNone(self.m._TOKENIZER)

    def test_model_is_kept_inside_the_idle_window(self):
        self.m._LAST_USED = 1000.0
        freed = self.m.maybe_unload_idle(now=1000.0 + 1.0)
        self.assertFalse(freed)
        self.assertIsNotNone(self.m._MODEL)

    def test_zero_disables_idle_unload(self):
        import os

        os.environ["ESM_IDLE_UNLOAD_S"] = "0"
        try:
            self.m._LAST_USED = 1000.0
            self.assertFalse(self.m.maybe_unload_idle(now=1e9))
            self.assertIsNotNone(self.m._MODEL)
        finally:
            del os.environ["ESM_IDLE_UNLOAD_S"]

    def test_never_used_model_is_not_unloaded(self):
        self.m._LAST_USED = None
        self.assertFalse(self.m.maybe_unload_idle(now=1e9))

    def test_health_reports_whether_the_model_is_resident(self):
        payload = self.m.embed_payload({"health": True})
        self.assertTrue(payload["loaded"])
        self.assertEqual(payload["idle_unload_s"], self.m.idle_unload_s())
        self.m.unload_model()
        self.assertFalse(self.m.embed_payload({"health": True})["loaded"])


class EsmEmbeddingReaperTest(unittest.TestCase):
    def test_idle_reaper_runs_in_a_daemon_thread(self):
        m = _load_embedder()
        thread = m.start_idle_reaper(interval_s=0.01)
        self.assertTrue(thread.daemon, "reaper must not block process exit")
        self.assertTrue(thread.is_alive())

    def test_idle_reaper_actually_unloads(self):
        import time as _t

        m = _load_embedder()
        m._TOKENIZER = object()
        m._MODEL = _FakeModel()
        m._LAST_USED = _t.monotonic() - 10_000.0
        m.start_idle_reaper(interval_s=0.01)
        for _ in range(200):
            if m._MODEL is None:
                break
            _t.sleep(0.01)
        self.assertIsNone(m._MODEL, "reaper should have unloaded the idle model")

    def test_server_starts_the_reaper(self):
        path = Path(__file__).resolve().parents[1] / "workers" / "esm_embedding" / "http_server.py"
        self.assertIn("start_idle_reaper", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
