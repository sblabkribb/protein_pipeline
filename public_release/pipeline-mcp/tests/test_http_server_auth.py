from __future__ import annotations

from pipeline_mcp import http_server
from pipeline_mcp.http_server import Handler
from pipeline_mcp.session_auth import SessionConfig
from pipeline_mcp.session_auth import SessionManager


def test_handler_accepts_cookie_session_without_authorization_header(tmp_path, monkeypatch):
    manager = SessionManager(
        SessionConfig(
            store_path=tmp_path / "sessions.json",
            cookie_name="pipeline_session",
            local_ttl_s=3600,
            oidc_refresh_leeway_s=60,
            oidc_fallback_ttl_s=300,
        )
    )
    user = {"username": "tester", "role": "user", "run_prefix": "tester", "created_at": ""}
    session_id = manager.create_local_session(user)

    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", manager, raising=False)

    handler = Handler.__new__(Handler)
    handler.headers = {"Cookie": f"{manager.config.cookie_name}={session_id}"}

    assert handler._require_user() == user


def test_handler_accepts_api_prefixed_healthz_route():
    captured = {}

    handler = Handler.__new__(Handler)
    handler.path = "/api/healthz"
    handler.headers = {}
    handler._json = lambda status, payload, extra_headers=None: captured.update(  # noqa: ARG005
        status=status,
        payload=payload,
    )

    handler.do_GET()

    assert captured["status"] == 200
    assert captured["payload"] == {"ok": True}


def test_handler_accepts_api_prefixed_tools_call_route():
    captured = {}

    handler = Handler.__new__(Handler)
    handler.path = "/api/tools/call"
    handler.headers = {}
    handler._auth_enabled = lambda: False
    handler._require_auth = lambda: None
    handler._read_json = lambda: {"name": "pipeline.list_runs", "arguments": {"limit": 1}}
    handler._call_tool_for_user = lambda user, name, arguments: {  # noqa: ARG005
        "name": name,
        "arguments": arguments,
    }
    handler._json = lambda status, payload, extra_headers=None: captured.update(  # noqa: ARG005
        status=status,
        payload=payload,
    )
    handler.log_error = lambda *args, **kwargs: None  # noqa: ARG005

    handler.do_POST()

    assert captured["status"] == 200
    assert captured["payload"] == {
        "ok": True,
        "result": {"name": "pipeline.list_runs", "arguments": {"limit": 1}},
    }
