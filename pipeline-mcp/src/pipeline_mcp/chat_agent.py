"""Provider-agnostic chat tool-calling loop for the site AI chatbot.

The loop (`run_chat_turn`) is provider-neutral: it calls `_complete`, which
dispatches to a raw-HTTP adapter per provider. Read tools run server-side via an
injected `tool_executor`; a `navigate` call is returned as a client action.
API keys are used transiently and never logged (errors are redacted).
"""
from __future__ import annotations

import json
import re

import requests

from .chat_providers import ChatProviderError, _normalize_provider

READ_TOOLS = ("pipeline.status", "pipeline.queue_eta",
              "pipeline.list_runs", "pipeline.list_artifacts")
NAVIGATE_PAGES = ("home", "fast", "advanced", "evolution",
                  "studio", "monitor", "rounds", "analyze")


def tool_specs() -> list[dict]:
    """Common tool definitions the model sees: read tools + navigate."""
    run_id = {"type": "object", "properties": {"run_id": {"type": "string",
              "description": "run id; optional, defaults to the latest run"}}}
    return [
        {"name": "pipeline.status", "description": "Get the state/stage of a run.",
         "parameters": run_id},
        {"name": "pipeline.queue_eta", "description": "Approximate worker-queue wait/finish ETA for a run.",
         "parameters": run_id},
        {"name": "pipeline.list_runs", "description": "List recent runs.",
         "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
        {"name": "pipeline.list_artifacts", "description": "List a run's output artifacts.",
         "parameters": run_id},
        {"name": "navigate", "description": "Take the user to a workspace page. "
         "Use this to guide the user to start a run (they click the run button themselves).",
         "parameters": {"type": "object",
                        "properties": {"page": {"type": "string", "enum": list(NAVIGATE_PAGES)}},
                        "required": ["page"]}},
    ]


def run_chat_turn(provider, model, api_key, messages, tool_executor, *,
                  system=None, max_steps=6, timeout=60.0) -> dict:
    """One user turn. Returns {"reply", "actions", "steps"}.
    Raises ChatProviderError on provider auth/upstream failure."""
    msgs = [dict(m) for m in (messages or [])]
    actions: list[dict] = []
    reply = ""
    steps = 0
    specs = tool_specs()
    for steps in range(1, max_steps + 1):
        result = _complete(provider, model, api_key, msgs, specs, system=system, timeout=timeout)
        reply = result.get("text") or reply
        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            return {"reply": reply, "actions": actions, "steps": steps}
        msgs.append({"role": "assistant", "content": result.get("text") or "", "tool_calls": tool_calls})
        stop = False
        for call in tool_calls:
            name = str(call.get("name") or "")
            args = call.get("args") or {}
            cid = call.get("id") or name
            if name == "navigate":
                page = str(args.get("page") or "").strip().lower()
                if page not in NAVIGATE_PAGES:
                    page = "home"
                actions.append({"type": "navigate", "page": page})
                msgs.append({"role": "tool", "tool_call_id": cid, "name": name,
                             "content": {"ok": True, "navigated": page}})
                stop = True
            elif name in READ_TOOLS:
                out = tool_executor(name, args)
                msgs.append({"role": "tool", "tool_call_id": cid, "name": name, "content": out})
            else:
                msgs.append({"role": "tool", "tool_call_id": cid, "name": name,
                             "content": {"error": "tool not available"}})
        if stop:
            return {"reply": reply, "actions": actions, "steps": steps}
    return {"reply": reply or "(stopped after the step limit)", "actions": actions, "steps": steps}


def _post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.RequestException as exc:
        detail = re.sub(r"key=[^&\s]+", "key=***", str(exc))
        raise ChatProviderError("upstream", f"request failed: {detail}") from exc
    if resp.status_code in (401, 403):
        raise ChatProviderError("auth", "provider rejected the API key")
    if resp.status_code >= 400:
        raise ChatProviderError("upstream", f"provider returned HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ChatProviderError("upstream", "provider returned invalid JSON") from exc
    return data if isinstance(data, dict) else {}


def _complete(provider, model, api_key, messages, tools, *, system=None, timeout=60.0) -> dict:
    canonical = _normalize_provider(provider)
    key = str(api_key or "").strip()
    if not key:
        raise ChatProviderError("auth", "API key is required")
    if canonical == "anthropic":
        return _anthropic_complete(model, key, messages, tools, system, timeout)
    if canonical == "openai":
        return _openai_complete(model, key, messages, tools, system, timeout)
    return _gemini_complete(model, key, messages, tools, system, timeout)


def _anthropic_complete(model, key, messages, tools, system, timeout):  # implemented in Task 2
    raise NotImplementedError


def _openai_complete(model, key, messages, tools, system, timeout):  # implemented in Task 3
    raise NotImplementedError


def _gemini_complete(model, key, messages, tools, system, timeout):  # implemented in Task 4
    raise NotImplementedError
