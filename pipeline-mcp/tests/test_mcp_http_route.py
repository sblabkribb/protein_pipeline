from __future__ import annotations

from pipeline_mcp import http_server
from pipeline_mcp.http_server import Handler


class _FakeDispatcher:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self):
        return {
            "tools": [
                {"name": "pipeline.run", "description": "Run pipeline", "inputSchema": {"type": "object"}},
                {
                    "name": "pipeline.runpod_list_endpoints",
                    "description": "Admin tool",
                    "inputSchema": {"type": "object"},
                },
            ]
        }

    def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, dict(arguments)))
        return {"name": name, "arguments": dict(arguments)}


def _make_handler(path: str, payload: dict, captured: dict):
    handler = Handler.__new__(Handler)
    handler.path = path
    handler.headers = {}
    handler._read_json = lambda: payload
    handler._json = lambda code, payload, extra_headers=None: captured.update(
        {"code": code, "payload": payload, "extra_headers": extra_headers}
    )
    return handler


def test_mcp_initialize_returns_capabilities(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)

    handler.do_POST()

    assert captured["code"] == 200
    assert captured["payload"]["id"] == 1
    assert captured["payload"]["result"]["capabilities"]["tools"] == {"listChanged": False}


def test_mcp_tools_list_filters_admin_tools_for_non_admin(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)
    handler._require_auth = lambda: {"username": "tester", "role": "user", "run_prefix": "tester"}

    handler.do_POST()

    tools = captured["payload"]["result"]["tools"]
    assert [item["name"] for item in tools] == ["pipeline.run"]


def test_mcp_tools_call_injects_run_id_for_non_admin(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "pipeline.run",
                "arguments": {"target_fasta": ">a\nAAAA"},
            },
        },
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)
    monkeypatch.setattr(http_server, "new_run_id", lambda prefix: f"{prefix}_job")
    handler._require_auth = lambda: {"username": "tester@example.org", "role": "user", "run_prefix": "tester_example.org"}

    handler.do_POST()

    assert captured["code"] == 200
    assert dispatcher.calls == [
        (
            "pipeline.run",
            {
                "target_fasta": ">a\nAAAA",
                "run_id": "tester_example.org_job",
                "user": {
                    "username": "tester@example.org",
                    "role": "user",
                    "run_prefix": "tester_example.org",
                },
            },
        )
    ]
    assert captured["payload"]["result"]["content"][0]["json"]["arguments"]["run_id"] == "tester_example.org_job"


def test_mcp_tools_call_injects_user_for_pipeline_run(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "pipeline.run",
                "arguments": {"target_fasta": ">a\nAAAA", "project_id": "tev", "round_id": "round_01"},
            },
        },
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)
    monkeypatch.setattr(http_server, "new_run_id", lambda prefix: f"{prefix}_job")
    handler._require_auth = lambda: {"username": "tester@example.org", "role": "user", "run_prefix": "tester_example.org"}

    handler.do_POST()

    assert captured["code"] == 200
    assert dispatcher.calls == [
        (
            "pipeline.run",
            {
                "target_fasta": ">a\nAAAA",
                "project_id": "tev",
                "round_id": "round_01",
                "run_id": "tester_example.org_job",
                "user": {
                    "username": "tester@example.org",
                    "role": "user",
                    "run_prefix": "tester_example.org",
                },
            },
        )
    ]


def test_mcp_tools_call_injects_user_for_pipeline_preflight(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "pipeline.preflight",
                "arguments": {"target_fasta": ">a\nAAAA", "project_id": "tev", "round_id": "round_01"},
            },
        },
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)
    handler._require_auth = lambda: {"username": "tester@example.org", "role": "user", "run_prefix": "tester_example.org"}

    handler.do_POST()

    assert captured["code"] == 200
    assert dispatcher.calls == [
        (
            "pipeline.preflight",
            {
                "target_fasta": ">a\nAAAA",
                "project_id": "tev",
                "round_id": "round_01",
                "user": {
                    "username": "tester@example.org",
                    "role": "user",
                    "run_prefix": "tester_example.org",
                },
            },
        )
    ]


def test_mcp_tools_call_injects_user_for_round_delete_archive_tools(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "pipeline.delete_round",
                "arguments": {"project_id": "tev", "round_id": "round_01"},
            },
        },
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)
    handler._require_auth = lambda: {"username": "tester@example.org", "role": "user", "run_prefix": "tester_example.org"}

    handler.do_POST()

    assert captured["code"] == 200
    assert dispatcher.calls == [
        (
            "pipeline.delete_round",
            {
                "project_id": "tev",
                "round_id": "round_01",
                "user": {
                    "username": "tester@example.org",
                    "role": "user",
                    "run_prefix": "tester_example.org",
                },
            },
        )
    ]


def test_mcp_unknown_method_returns_jsonrpc_error(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}},
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)

    handler.do_POST()

    assert captured["code"] == 200
    assert captured["payload"]["error"]["code"] == -32601


def test_mcp_tools_call_injects_user_for_round_restore_tools(monkeypatch):
    captured: dict = {}
    dispatcher = _FakeDispatcher()
    handler = _make_handler(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "pipeline.restore_round",
                "arguments": {"project_id": "tev", "round_id": "round_01"},
            },
        },
        captured,
    )

    monkeypatch.setattr(http_server, "_DISPATCHER", dispatcher, raising=False)
    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)
    handler._require_auth = lambda: {"username": "tester@example.org", "role": "user", "run_prefix": "tester_example.org"}

    handler.do_POST()

    assert captured["code"] == 200
    assert dispatcher.calls == [
        (
            "pipeline.restore_round",
            {
                "project_id": "tev",
                "round_id": "round_01",
                "user": {
                    "username": "tester@example.org",
                    "role": "user",
                    "run_prefix": "tester_example.org",
                },
            },
        )
    ]
