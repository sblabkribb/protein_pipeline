from __future__ import annotations

import argparse
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Iterable

import requests
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import CallToolResult, TextContent, Tool


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
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


def _post_json(url: str, payload: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
    resp = requests.post(url, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid JSON response: {data!r}")
    return data


def _fetch_tools(base_url: str, *, timeout_s: float) -> list[Tool]:
    data = _post_json(f"{base_url}/tools/list", {}, timeout_s=timeout_s)
    tools_raw = data.get("tools") if isinstance(data, dict) else None
    if not isinstance(tools_raw, list):
        raise RuntimeError("Invalid tools/list response (expected {'tools': [...]})")

    tools: list[Tool] = []
    for item in tools_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        tools.append(
            Tool(
                name=name,
                description=item.get("description"),
                inputSchema=item.get("inputSchema") or {"type": "object", "properties": {}},
                outputSchema=item.get("outputSchema"),
                icons=item.get("icons"),
                annotations=item.get("annotations"),
                meta=item.get("_meta") or item.get("meta"),
            )
        )
    return tools


def _tool_result_payload(result: object) -> CallToolResult:
    if isinstance(result, (dict, list)):
        text = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        text = json.dumps({"value": result}, ensure_ascii=False, indent=2)
    structured = result if isinstance(result, dict) else None
    return CallToolResult(content=[TextContent(type="text", text=text)], structuredContent=structured)


def _as_dict(value: object | None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"value": value}


def build_app(
    *,
    base_url: str,
    timeout_s: float,
    path: str,
    json_response: bool,
    stateless: bool,
) -> Starlette:
    server = Server("protein-pipeline (streamable HTTP MCP proxy)")

    @server.list_tools()
    async def list_tools() -> Iterable[Tool]:
        return _fetch_tools(base_url, timeout_s=timeout_s)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]):
        payload = {"name": name, "arguments": arguments or {}}
        data = _post_json(f"{base_url}/tools/call", payload, timeout_s=timeout_s)
        if not data.get("ok", False):
            error = data.get("error")
            raise RuntimeError(error or "Remote tools/call failed")
        result = data.get("result")
        return _tool_result_payload(result)

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=json_response,
        stateless=stateless,
    )

    @asynccontextmanager
    async def lifespan(_: Starlette):
        async with session_manager.run():
            yield

    route_path = path if path.startswith("/") else f"/{path}"
    return Starlette(
        routes=[Route(route_path, session_manager.handle_request)],
        lifespan=lifespan,
    )


def main(argv: list[str] | None = None) -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))
    _load_dotenv(os.path.join(repo_root, ".env"))

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PIPELINE_MCP_HTTP_URL")
        or os.environ.get("PIPELINE_MCP_BASE_URL")
        or os.environ.get("PIPELINE_HTTP_URL")
        or "http://127.0.0.1:8000",
        help="Base URL for pipeline-mcp HTTP server (expects /tools/list and /tools/call).",
    )
    parser.add_argument("--host", default=os.environ.get("MCP_HTTP_HOST") or "0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_HTTP_PORT") or "18081"))
    parser.add_argument("--path", default=os.environ.get("MCP_HTTP_PATH") or "/mcp")
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.environ.get("PIPELINE_MCP_HTTP_TIMEOUT_S") or "3600"),
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        help="Return JSON responses instead of SSE streams.",
    )
    parser.add_argument(
        "--stateless",
        action="store_true",
        help="Disable session tracking (stateless StreamableHTTP).",
    )
    args = parser.parse_args(argv)

    base_url = str(args.base_url).rstrip("/")
    app = build_app(
        base_url=base_url,
        timeout_s=float(args.timeout_s),
        path=str(args.path),
        json_response=bool(args.json_response),
        stateless=bool(args.stateless),
    )

    uvicorn.run(app, host=str(args.host), port=int(args.port), log_level="info")


if __name__ == "__main__":
    main()
