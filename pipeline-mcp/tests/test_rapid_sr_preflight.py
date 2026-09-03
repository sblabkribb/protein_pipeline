from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "transcoder" / "04c_preflight_bop.py"


def _load():
    spec = importlib.util.spec_from_file_location("preflight_bop", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreflightTests(unittest.TestCase):
    def test_missing_required_endpoint_blocks(self):
        module = _load()
        summary = module.summarise([
            {"name": "proteinmpnn", "ok": False, "detail": "refused", "required": True},
            {"name": "colabfold", "ok": True, "detail": "200", "required": True},
        ])
        self.assertFalse(summary["ready"])
        self.assertEqual(summary["blocking"], ["proteinmpnn"])

    def test_optional_failure_degrades_but_does_not_block(self):
        module = _load()
        summary = module.summarise([
            {"name": "proteinmpnn", "ok": True, "detail": "200", "required": True},
            {"name": "bioemu", "ok": False, "detail": "timeout", "required": False},
        ])
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["degraded"], ["bioemu"])

    def test_all_ok_is_ready(self):
        module = _load()
        summary = module.summarise(
            [{"name": "colabfold", "ok": True, "detail": "200", "required": True}]
        )
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["degraded"], [])
        self.assertEqual(summary["blocking"], [])

    def test_available_arms_drop_bioemu_when_worker_is_down(self):
        module = _load()
        summary = module.summarise([
            {"name": "proteinmpnn", "ok": True, "detail": "200", "required": True},
            {"name": "rfd3", "ok": True, "detail": "200", "required": False},
            {"name": "bioemu", "ok": False, "detail": "refused", "required": False},
        ])
        self.assertEqual(summary["available_arms"], ["target", "rfd3"])

    def test_available_arms_always_include_target(self):
        module = _load()
        summary = module.summarise([
            {"name": "rfd3", "ok": False, "detail": "refused", "required": False},
            {"name": "bioemu", "ok": False, "detail": "refused", "required": False},
        ])
        self.assertEqual(summary["available_arms"], ["target"])


if __name__ == "__main__":
    unittest.main()
