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


class ConnectionsTests(unittest.TestCase):
    """화면의 '연결' 블록이 읽는 값. 설정 안 됨과 연결 실패를 구별한다."""

    def test_connections_are_reported(self):
        out = _call("pipeline.list_models")
        self.assertIn("connections", out)
        self.assertIn("bop_workers", out["connections"])
        self.assertIn("portal_mcp", out["connections"])

    def test_an_unconfigured_portal_says_what_is_missing(self):
        portal = _call("pipeline.list_models")["connections"]["portal_mcp"]
        self.assertIn("configured", portal)
        self.assertIn("missing", portal)
        self.assertIn("url_env", portal)

    def test_the_portal_token_is_never_returned(self):
        import json

        self.assertNotIn("RAPID_PORTAL_MCP_TOKEN\": \"",
                         json.dumps(_call("pipeline.list_models")))

    def test_the_portal_reports_which_models_it_would_unlock(self):
        portal = _call("pipeline.list_models")["connections"]["portal_mcp"]
        self.assertIn("would_unlock", portal)
        for model_id in ("antifold", "anarcii", "alphafold3"):
            self.assertIn(model_id, portal["would_unlock"])

    def test_models_already_wired_here_are_not_listed_as_unlocked(self):
        portal = _call("pipeline.list_models")["connections"]["portal_mcp"]
        self.assertNotIn("proteinmpnn", portal["would_unlock"])

    def test_the_portal_does_not_claim_to_unlock_the_antibody_route(self):
        """전송이 열려도 마스크 정책이 없으면 항체 경로는 실행되지 않는다."""
        portal = _call("pipeline.list_models")["connections"]["portal_mcp"]
        self.assertIn("design_policy", portal["still_blocked_note"])

    def test_bop_worker_count_matches_the_declared_endpoints(self):
        out = _call("pipeline.list_models")
        declared = sum(1 for m in out["models"].values()
                       if str(m.get("endpoint", "")).startswith("bop:"))
        self.assertEqual(out["connections"]["bop_workers"]["declared"], declared)
