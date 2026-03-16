from __future__ import annotations

from pipeline_mcp import http_server
from pipeline_mcp.http_server import Handler
from pipeline_mcp.session_auth import SessionConfig
from pipeline_mcp.session_auth import SessionManager


def test_handler_accepts_cookie_session_without_authorization_header(tmp_path, monkeypatch):
    manager = SessionManager(
        SessionConfig(
            store_path=tmp_path / "sessions.json",
            cookie_name="kbf_session",
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
