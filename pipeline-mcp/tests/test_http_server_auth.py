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


def test_require_auth_rejects_non_admin_when_admin_required(monkeypatch):
    captured = {}

    monkeypatch.setenv("PIPELINE_REQUIRE_ADMIN", "true")

    handler = Handler.__new__(Handler)
    handler._auth_enabled = lambda: True
    handler._require_user = lambda: {"username": "tester", "role": "user"}
    handler._json = lambda status, payload, extra_headers=None: captured.update(  # noqa: ARG005
        status=status,
        payload=payload,
    )

    assert handler._require_auth() is None
    assert captured == {"status": 403, "payload": {"ok": False, "error": "admin required"}}


def test_require_auth_allows_admin_when_admin_required(monkeypatch):
    user = {"username": "admin", "role": "admin"}

    monkeypatch.setenv("PIPELINE_REQUIRE_ADMIN", "true")

    handler = Handler.__new__(Handler)
    handler._auth_enabled = lambda: True
    handler._require_user = lambda: user

    assert handler._require_auth() == user


def test_model_provider_global_update_requires_model_manager_but_user_scope_is_allowed(monkeypatch):
    handler = Handler.__new__(Handler)

    assert handler._can_manage_models({"username": "admin", "role": "admin"}) is True
    assert handler._can_manage_models({"username": "manager", "role": "model_manager"}) is True
    assert handler._can_manage_models({"username": "user", "role": "user"}) is False

    calls = []
    monkeypatch.setattr(
        http_server,
        "_DISPATCHER",
        type(
        "FakeDispatcher",
        (),
        {
            "call_tool": lambda _self, name, arguments: calls.append((name, arguments)) or {"ok": True},
        },
        )(),
        raising=False,
    )

    try:
        handler._call_tool_for_user(
            {"username": "user", "role": "user"},
            "pipeline.model_provider_update",
            {"model_key": "esmfold", "scope": "global"},
        )
    except Exception as exc:
        assert "model manager required" in str(exc)
    else:
        raise AssertionError("plain users must not update global model providers")

    out = handler._call_tool_for_user(
        {"username": "user", "role": "user"},
        "pipeline.model_provider_update",
        {"model_key": "esmfold", "scope": "user", "provider": {"provider_type": "disabled"}},
    )

    assert out == {"ok": True}
    assert calls[0][0] == "pipeline.model_provider_update"
    assert calls[0][1]["scope"] == "user"
    assert calls[0][1]["user"]["username"] == "user"


def test_pending_oidc_user_is_rejected(monkeypatch):
    captured = {}

    handler = Handler.__new__(Handler)
    handler._auth_enabled = lambda: True
    handler._require_user = lambda: {"username": "new.user@example.org", "role": "user", "status": "pending"}
    handler._json = lambda status, payload, extra_headers=None: captured.update(  # noqa: ARG005
        status=status,
        payload=payload,
    )

    assert handler._require_auth() is None
    assert captured == {
        "status": 403,
        "payload": {"ok": False, "error": "approval required"},
    }


def test_admin_can_list_and_update_users(monkeypatch):
    captured = {}

    class FakeAuth:
        enabled = True

        @staticmethod
        def list_users():
            return [{"username": "new.user@example.org", "role": "user", "status": "pending"}]

        @staticmethod
        def update_user(*, username, role=None, status=None):
            assert username == "new.user@example.org"
            assert role == "model_manager"
            assert status == "approved"
            return {"username": username, "role": role, "status": status}

    monkeypatch.setattr(http_server, "_AUTH", FakeAuth(), raising=False)

    handler = Handler.__new__(Handler)
    handler.path = "/auth/list_users"
    handler.headers = {}
    handler._require_auth = lambda: {"username": "admin", "role": "admin", "status": "approved"}
    handler._json = lambda status, payload, extra_headers=None: captured.update(  # noqa: ARG005
        status=status,
        payload=payload,
    )
    handler.log_error = lambda *args, **kwargs: None  # noqa: ARG005

    handler.do_POST()

    assert captured == {
        "status": 200,
        "payload": {
            "ok": True,
            "users": [{"username": "new.user@example.org", "role": "user", "status": "pending"}],
        },
    }

    handler.path = "/auth/update_user"
    handler._read_json = lambda: {
        "username": "new.user@example.org",
        "role": "model_manager",
        "status": "approved",
    }

    handler.do_POST()

    assert captured == {
        "status": 200,
        "payload": {
            "ok": True,
            "user": {"username": "new.user@example.org", "role": "model_manager", "status": "approved"},
        },
    }


def test_local_login_does_not_create_session_for_non_admin_when_admin_required(monkeypatch):
    captured = {}

    class FakeAuth:
        enabled = True

        @staticmethod
        def authenticate(username, password):
            assert username == "tester"
            assert password == "secret"
            return {"user": {"username": "tester", "role": "user"}, "token": "token"}

    class FakeSessions:
        @staticmethod
        def create_local_session(_user):
            raise AssertionError("non-admin users must not get sessions")

    monkeypatch.setenv("PIPELINE_REQUIRE_ADMIN", "true")
    monkeypatch.setattr(http_server, "_AUTH", FakeAuth(), raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", FakeSessions(), raising=False)

    handler = Handler.__new__(Handler)
    handler.path = "/auth/login"
    handler.headers = {}
    handler._read_json = lambda: {"username": "tester", "password": "secret"}
    handler._json = lambda status, payload, extra_headers=None: captured.update(  # noqa: ARG005
        status=status,
        payload=payload,
    )
    handler.log_error = lambda *args, **kwargs: None  # noqa: ARG005

    handler.do_POST()

    assert captured == {"status": 403, "payload": {"ok": False, "error": "admin required"}}


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


def test_auth_me_returns_public_session_type(monkeypatch):
    captured = {}

    class FakeSessions:
        config = type("Config", (), {"cookie_name": "kbf_session"})()

        @staticmethod
        def get_session(session_id, *, oidc_settings=None):  # noqa: ARG004
            assert session_id == "sid"
            return {"auth_type": "local"}

    monkeypatch.setattr(http_server, "_SESSIONS", FakeSessions(), raising=False)

    handler = Handler.__new__(Handler)
    handler.path = "/auth/me"
    handler.headers = {"Cookie": "kbf_session=sid"}
    handler._require_auth = lambda: {"username": "admin", "role": "admin", "status": "approved"}
    handler._json = lambda status, payload, extra_headers=None: captured.update(  # noqa: ARG005
        status=status,
        payload=payload,
    )

    handler.do_GET()

    assert captured == {
        "status": 200,
        "payload": {
            "ok": True,
            "user": {"username": "admin", "role": "admin", "status": "approved"},
            "session": {"auth_type": "local"},
        },
    }


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
