from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any

from .storage import new_run_id
from .auth import AuthError
from .auth import load_auth_manager
from .auth import safe_run_prefix
from .tools import ToolDispatcher


_DISPATCHER: ToolDispatcher | None = None
_AUTH = None
_ALLOW_ALL_ORIGINS = True
_ALLOWED_ORIGINS: set[str] = set()


def _init_cors() -> None:
    raw = os.environ.get("PIPELINE_CORS_ORIGINS", "*")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    global _ALLOW_ALL_ORIGINS, _ALLOWED_ORIGINS
    if not parts or "*" in parts:
        _ALLOW_ALL_ORIGINS = True
        _ALLOWED_ORIGINS = set()
    else:
        _ALLOW_ALL_ORIGINS = False
        _ALLOWED_ORIGINS = set(parts)


class Handler(BaseHTTPRequestHandler):
    _MAX_BODY_BYTES = 50 * 1024 * 1024
    _MAX_CHUNK_LINE_BYTES = 1024

    @property
    def dispatcher(self) -> ToolDispatcher:
        if _DISPATCHER is None:
            raise RuntimeError("Server not initialized")
        return _DISPATCHER

    @property
    def auth(self):
        return _AUTH

    def _set_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if _ALLOW_ALL_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in _ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "600")

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_chunked(self) -> bytes:
        body = bytearray()
        while True:
            line = self.rfile.readline(self._MAX_CHUNK_LINE_BYTES + 2)
            if not line:
                raise ValueError("Unexpected EOF while reading chunked request body")
            if len(line) > self._MAX_CHUNK_LINE_BYTES + 1 and not line.endswith(b"\n"):
                raise ValueError("Chunk size line too long")

            size_token = line.strip().split(b";", 1)[0].strip()
            try:
                chunk_size = int(size_token, 16)
            except ValueError as exc:
                raise ValueError("Invalid chunk size") from exc

            if chunk_size == 0:
                while True:
                    trailer = self.rfile.readline(self._MAX_CHUNK_LINE_BYTES + 2)
                    if not trailer or trailer in (b"\r\n", b"\n"):
                        break
                break

            if len(body) + chunk_size > self._MAX_BODY_BYTES:
                raise ValueError("Request body too large")

            chunk = self.rfile.read(chunk_size)
            if len(chunk) != chunk_size:
                raise ValueError("Unexpected EOF while reading chunk data")
            body.extend(chunk)

            terminator = self.rfile.readline(2)
            if terminator not in (b"\r\n", b"\n"):
                raise ValueError("Invalid chunk terminator")

        return bytes(body)

    def _read_body(self) -> bytes:
        transfer_encoding = str(self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in transfer_encoding:
            return self._read_chunked()

        length_raw = self.headers.get("Content-Length")
        if not length_raw:
            return b""
        try:
            length = int(length_raw)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header") from exc
        if length < 0:
            raise ValueError("Invalid Content-Length header")
        if length > self._MAX_BODY_BYTES:
            raise ValueError("Request body too large")
        return self.rfile.read(length) if length else b""

    def _read_json(self) -> dict[str, Any]:
        raw = self._read_body() or b"{}"
        data = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _require_user(self) -> dict[str, Any] | None:
        auth = self.auth
        if auth is None or not getattr(auth, "enabled", False):
            return None
        header = self.headers.get("Authorization") or ""
        token = ""
        if header.startswith("Bearer "):
            token = header.removeprefix("Bearer ").strip()
        if not token:
            return None
        return auth.verify_token(token)

    def _is_admin(self, user: dict[str, Any] | None) -> bool:
        return bool(user and str(user.get("role") or "") == "admin")

    def _require_auth(self) -> dict[str, Any] | None:
        auth = self.auth
        if auth is None or not getattr(auth, "enabled", False):
            return None
        user = self._require_user()
        if user is None:
            self._json(401, {"ok": False, "error": "unauthorized"})
        return user

    def _enforce_run_access(self, user: dict[str, Any] | None, run_id: str) -> None:
        if user is None or self._is_admin(user):
            return
        prefix = safe_run_prefix(str(user.get("username") or "user")) + "_"
        if not str(run_id or "").startswith(prefix):
            raise AuthError("run_id not allowed for this user")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/auth/me":
            user = self._require_auth()
            if user is None:
                return
            self._json(200, {"ok": True, "user": user})
            return
        if self.path.rstrip("/") == "/healthz":
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path.rstrip("/") == "/auth/login":
                auth = self.auth
                if auth is None or not getattr(auth, "enabled", False):
                    self._json(400, {"ok": False, "error": "auth disabled"})
                    return
                body = self._read_json()
                username = str(body.get("username") or "")
                password = str(body.get("password") or "")
                result = auth.authenticate(username, password)
                if result is None:
                    self._json(401, {"ok": False, "error": "invalid credentials"})
                    return
                self._json(200, {"ok": True, **result})
                return

            if self.path.rstrip("/") == "/auth/create_user":
                auth = self.auth
                if auth is None or not getattr(auth, "enabled", False):
                    self._json(400, {"ok": False, "error": "auth disabled"})
                    return
                user = self._require_auth()
                if user is None:
                    return
                if not self._is_admin(user):
                    self._json(403, {"ok": False, "error": "admin required"})
                    return
                body = self._read_json()
                username = str(body.get("username") or "")
                password = str(body.get("password") or "")
                role = str(body.get("role") or "user")
                created = auth.create_user(username=username, password=password, role=role)
                self._json(200, {"ok": True, "user": created})
                return

            if self.path.rstrip("/") == "/tools/list":
                user = self._require_auth()
                if user is None and self.auth is not None and getattr(self.auth, "enabled", False):
                    return
                self._json(200, self.dispatcher.list_tools())
                return
            if self.path.rstrip("/") == "/tools/call":
                user = self._require_auth()
                if user is None and self.auth is not None and getattr(self.auth, "enabled", False):
                    return
                body = self._read_json()
                name = body.get("name")
                arguments = body.get("arguments") or {}
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise ValueError("Expected {name: str, arguments: object}")
                if name in {"pipeline.status", "pipeline.list_artifacts", "pipeline.read_artifact"}:
                    run_id = str(arguments.get("run_id") or "")
                    if run_id:
                        self._enforce_run_access(user, run_id)
                if name in {"pipeline.run", "pipeline.run_from_prompt"} and user is not None and not self._is_admin(user):
                    prefix = safe_run_prefix(str(user.get("username") or "user"))
                    run_id = arguments.get("run_id")
                    if run_id:
                        self._enforce_run_access(user, str(run_id))
                    else:
                        arguments["run_id"] = new_run_id(prefix)
                out = self.dispatcher.call_tool(name, arguments)
                if name == "pipeline.list_runs" and user is not None and not self._is_admin(user):
                    prefix = safe_run_prefix(str(user.get("username") or "user")) + "_"
                    runs = out.get("runs") if isinstance(out, dict) else None
                    if isinstance(runs, list):
                        out["runs"] = [r for r in runs if str(r).startswith(prefix)]
                self._json(200, {"ok": True, "result": out})
                return
            self._json(404, {"error": "not found"})
        except Exception as exc:
            self.log_error("error handling %s: %s", self.path, exc)
            status = 403 if isinstance(exc, AuthError) else 400
            self._json(status, {"ok": False, "error": str(exc)})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    from .app import build_runner

    global _DISPATCHER
    _DISPATCHER = ToolDispatcher(build_runner())
    global _AUTH
    _AUTH = load_auth_manager()
    _init_cors()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"listening: http://{args.host}:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
