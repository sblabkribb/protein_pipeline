"""`pipeline.list_models` MCP 툴 계약."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp import tools


class _Runner:
    gemini = None


def _call(name, arguments=None):
    return tools.ToolDispatcher(_Runner()).call_tool(name, arguments or {})


class ListModelsToolTests(unittest.TestCase):
    def test_tool_is_listed(self):
        names = {t["name"] for t in tools.tool_definitions()}
        self.assertIn("pipeline.list_models", names)

    def test_returns_purposes_and_models(self):
        out = _call("pipeline.list_models")
        self.assertTrue(out["purposes"])
        self.assertTrue(out["models"])
        self.assertTrue(out["policy_version"])

    def test_each_purpose_reports_executable_and_validated(self):
        for route in _call("pipeline.list_models")["purposes"]:
            self.assertIn("executable", route)
            self.assertIn("validated", route)

    def test_liveness_is_off_by_default_so_the_call_stays_cheap(self):
        self.assertNotIn("liveness", _call("pipeline.list_models"))

    def test_filtering_by_purpose_returns_one_route(self):
        out = _call("pipeline.list_models", {"purpose": "protein_binder_design"})
        self.assertEqual(len(out["purposes"]), 1)
        self.assertEqual(out["purposes"][0]["purpose"], "protein_binder_design")

    def test_unknown_purpose_returns_a_message_not_an_exception(self):
        out = _call("pipeline.list_models", {"purpose": "nope"})
        self.assertIn("error", out)
        self.assertIn("nope", out["error"])

    def test_objectives_filter_suggests_purposes_by_coverage(self):
        out = _call("pipeline.list_models", {"objectives": ["binding"]})
        self.assertTrue(out["purposes"])
        for route in out["purposes"]:
            self.assertIn("binding", route["objectives"])

    def test_cost_estimate_is_returned_when_a_budget_is_given(self):
        out = _call("pipeline.list_models", {
            "purpose": "monomer_solubility_redesign", "n_designs": 40, "length_aa": 200,
        })
        est = out["purposes"][0]["cost_estimate"]
        self.assertGreater(est["known_seconds"], 0)
        self.assertTrue(est["unknown_stages"])


if __name__ == "__main__":
    unittest.main()
