"""bio model portal MCP 클라이언트.

포털은 antifold / anarcii / alphafold3 / esmfold / boltz2 를 노출한다. 그 경로를
붙이면 모델별 클라이언트를 쓰지 않고도 그 모델들에 닿는다.

닿는 것과 쓸 수 있는 것은 다르다. 항체 경로는 마스크 정책이 없어서 여전히
막혀 있고, 그것은 이 클라이언트로 풀리지 않는다.

프로토콜: POST /mcp 에 JSON-RPC 2.0, Bearer PAT. tools/call 결과는
`content[0].text` 안에 JSON 문자열로 들어오고 `isError` 가 따로 온다.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.clients.portal_mcp import (
    PortalMcpClient,
    PortalMcpError,
    portal_config_from_env,
)


class _Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, payload, headers, timeout):
        self.calls.append({"url": url, "payload": payload, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _result(obj, is_error=False):
    return {"jsonrpc": "2.0", "id": 1, "result": {
        "content": [{"type": "text", "text": json.dumps(obj)}], "isError": is_error}}


class ConfigTests(unittest.TestCase):
    def test_no_url_means_not_configured_rather_than_a_guessed_default(self):
        cfg = portal_config_from_env({})
        self.assertFalse(cfg["configured"])
        self.assertEqual(cfg["base_url"], "")

    def test_a_url_without_a_token_is_still_not_configured(self):
        cfg = portal_config_from_env({"RAPID_PORTAL_MCP_URL": "https://portal.example"})
        self.assertFalse(cfg["configured"])
        self.assertIn("token", cfg["missing"])

    def test_both_present_is_configured(self):
        cfg = portal_config_from_env({
            "RAPID_PORTAL_MCP_URL": "https://portal.example",
            "RAPID_PORTAL_MCP_TOKEN": "pat",
        })
        self.assertTrue(cfg["configured"])
        self.assertEqual(cfg["missing"], [])

    def test_the_token_is_never_echoed_back(self):
        cfg = portal_config_from_env({
            "RAPID_PORTAL_MCP_URL": "https://portal.example",
            "RAPID_PORTAL_MCP_TOKEN": "secret-pat",
        })
        self.assertNotIn("secret-pat", json.dumps(cfg))


class ProtocolTests(unittest.TestCase):
    def _client(self, transport):
        return PortalMcpClient(base_url="https://portal.example", token="pat",
                               transport=transport)

    def test_a_tool_result_is_parsed_out_of_the_text_content(self):
        transport = _Transport([_result({"ok": True, "models": [{"key": "antifold"}]})])
        out = self._client(transport).call_tool("list_models", {})
        self.assertEqual(out["models"][0]["key"], "antifold")

    def test_the_request_is_json_rpc_with_the_tool_name(self):
        transport = _Transport([_result({"ok": True})])
        self._client(transport).call_tool("run_model", {"pipeline": "antifold"})
        payload = transport.calls[0]["payload"]
        self.assertEqual(payload["jsonrpc"], "2.0")
        self.assertEqual(payload["method"], "tools/call")
        self.assertEqual(payload["params"]["name"], "run_model")
        self.assertEqual(payload["params"]["arguments"]["pipeline"], "antifold")

    def test_the_pat_is_sent_as_a_bearer_header(self):
        transport = _Transport([_result({"ok": True})])
        self._client(transport).call_tool("list_models", {})
        self.assertEqual(transport.calls[0]["headers"]["Authorization"], "Bearer pat")

    def test_is_error_raises_rather_than_returning_a_body(self):
        transport = _Transport([_result({"ok": False, "error": "unknown tool"}, is_error=True)])
        with self.assertRaises(PortalMcpError) as ctx:
            self._client(transport).call_tool("nope", {})
        self.assertIn("unknown tool", str(ctx.exception))

    def test_a_json_rpc_error_is_surfaced(self):
        transport = _Transport([{"jsonrpc": "2.0", "id": 1,
                                 "error": {"code": -32601, "message": "method not found"}}])
        with self.assertRaises(PortalMcpError) as ctx:
            self._client(transport).call_tool("list_models", {})
        self.assertIn("method not found", str(ctx.exception))

    def test_a_transport_failure_becomes_a_client_error(self):
        with self.assertRaises(PortalMcpError):
            self._client(_Transport([OSError("connection refused")])).call_tool("x", {})

    def test_unparsable_content_is_an_error_not_an_empty_result(self):
        transport = _Transport([{"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "not json"}], "isError": False}}])
        with self.assertRaises(PortalMcpError):
            self._client(transport).call_tool("list_models", {})

    def test_a_client_without_a_url_refuses_to_be_constructed(self):
        with self.assertRaises(ValueError):
            PortalMcpClient(base_url="", token="pat")

    def test_the_endpoint_path_is_mcp(self):
        transport = _Transport([_result({"ok": True})])
        self._client(transport).call_tool("list_models", {})
        self.assertTrue(transport.calls[0]["url"].endswith("/mcp"))


class ModelListingTests(unittest.TestCase):
    def test_list_models_returns_the_portal_pipeline_keys(self):
        transport = _Transport([_result({"ok": True, "models": [
            {"key": "antifold"}, {"key": "alphafold3"}]})])
        client = PortalMcpClient(base_url="https://p", token="t", transport=transport)
        self.assertEqual(sorted(client.list_model_keys()), ["alphafold3", "antifold"])

    def test_a_missing_models_field_is_an_error_not_an_empty_list(self):
        transport = _Transport([_result({"ok": True})])
        client = PortalMcpClient(base_url="https://p", token="t", transport=transport)
        with self.assertRaises(PortalMcpError):
            client.list_model_keys()


if __name__ == "__main__":
    unittest.main()
