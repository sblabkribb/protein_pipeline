from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        s = line.decode("utf-8", errors="replace").strip()
        if not s:
            break
        if ":" in s:
            k, v = s.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8", errors="replace"))


def _write_message(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _result_text(obj: object) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False, indent=2)}]}


def _error(err: Exception) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"ERROR: {err}"}], "isError": True}


def _post_json(url: str, payload: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
    r = requests.post(url, json=payload, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON response: {data!r}")
    return data


def main(argv: list[str] | None = None) -> None:
    pipeline_mcp_dir = Path(__file__).resolve().parents[1]
    _load_dotenv(pipeline_mcp_dir / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PIPELINE_MCP_HTTP_URL")
        or os.environ.get("PIPELINE_MCP_BASE_URL")
        or os.environ.get("PIPELINE_HTTP_URL")
        or "http://127.0.0.1:8000",
        help="Base URL for pipeline-mcp HTTP server (expects /tools/list and /tools/call).",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.environ.get("PIPELINE_MCP_HTTP_TIMEOUT_S") or "3600"),
        help="HTTP timeout (seconds) for remote tool calls.",
    )
    args = parser.parse_args(argv)
    base_url = str(args.base_url).rstrip("/")
    timeout_s = float(args.timeout_s)

    while True:
        msg = _read_message()
        if msg is None:
            break
        method = msg.get("method")
        msg_id = msg.get("id")

        try:
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": result}
                _write_message(resp)
                continue

            if method == "tools/list":
                data = _post_json(f"{base_url}/tools/list", {}, timeout_s=timeout_s)
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": data}
                _write_message(resp)
                continue

            if method == "tools/call":
                params = msg.get("params") or {}
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise ValueError("Invalid tools/call params")

                data = _post_json(
                    f"{base_url}/tools/call",
                    {"name": name, "arguments": arguments},
                    timeout_s=timeout_s,
                )
                if not data.get("ok", False):
                    raise RuntimeError(data.get("error") or "Remote /tools/call failed")
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": _result_text(data.get("result"))}
                _write_message(resp)
                continue

            if msg_id is not None:
                resp = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}
                _write_message(resp)
        except Exception as exc:
            if msg_id is None:
                continue
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": _error(exc)}
            _write_message(resp)


if __name__ == "__main__":
    main()
