from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any

from .tools import ToolDispatcher


_DISPATCHER: ToolDispatcher | None = None


class Handler(BaseHTTPRequestHandler):
    _MAX_BODY_BYTES = 50 * 1024 * 1024
    _MAX_CHUNK_LINE_BYTES = 1024

    @property
    def dispatcher(self) -> ToolDispatcher:
        if _DISPATCHER is None:
            raise RuntimeError("Server not initialized")
        return _DISPATCHER

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
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

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/healthz":
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path.rstrip("/") == "/tools/list":
                self._json(200, self.dispatcher.list_tools())
                return
            if self.path.rstrip("/") == "/tools/call":
                body = self._read_json()
                name = body.get("name")
                arguments = body.get("arguments") or {}
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise ValueError("Expected {name: str, arguments: object}")
                out = self.dispatcher.call_tool(name, arguments)
                self._json(200, {"ok": True, "result": out})
                return
            self._json(404, {"error": "not found"})
        except Exception as exc:
            self.log_error("error handling %s: %s", self.path, exc)
            self._json(400, {"ok": False, "error": str(exc)})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    from .app import build_runner

    global _DISPATCHER
    _DISPATCHER = ToolDispatcher(build_runner())

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"listening: http://{args.host}:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
