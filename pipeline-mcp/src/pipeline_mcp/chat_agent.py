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

READ_TOOLS = ("pipeline_status", "pipeline_queue_eta",
              "pipeline_list_runs", "pipeline_list_artifacts")
NAVIGATE_PAGES = ("home", "fast", "advanced", "evolution",
                  "studio", "monitor", "rounds", "analyze")


def tool_specs() -> list[dict]:
    """Common tool definitions the model sees: read tools + navigate."""
    run_id = {"type": "object", "properties": {"run_id": {"type": "string",
              "description": "run id; optional, defaults to the latest run"}}}
    return [
        {"name": "pipeline_status", "description": "Get the state/stage of a run.",
         "parameters": run_id},
        {"name": "pipeline_queue_eta", "description": "Approximate worker-queue wait/finish ETA for a run.",
         "parameters": run_id},
        {"name": "pipeline_list_runs", "description": "List recent runs.",
         "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
        {"name": "pipeline_list_artifacts", "description": "List a run's output artifacts.",
         "parameters": run_id},
        {"name": "navigate", "description": "Take the user to a workspace page. "
         "Use this to guide the user to start a run (they click the run button themselves). "
         "To run an attached file, navigate to 'fast' with prefill={\"attachment\": \"<the file name>\"} "
         "so the file is pre-loaded as the target; the user then clicks Run.",
         "parameters": {"type": "object",
                        "properties": {
                            "page": {"type": "string", "enum": list(NAVIGATE_PAGES)},
                            "prefill": {"type": "object",
                                        "properties": {"attachment": {"type": "string"}}},
                        },
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
                action = {"type": "navigate", "page": page}
                if isinstance(args.get("prefill"), dict):
                    action["prefill"] = args["prefill"]
                actions.append(action)
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
        body = ""
        try:
            body = re.sub(r"key=[^&\s]+", "key=***", resp.text or "")[:300]
        except Exception:
            body = ""
        detail = f"provider returned HTTP {resp.status_code}"
        if body:
            detail = f"{detail}: {body}"
        raise ChatProviderError("upstream", detail)
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


def _to_anthropic_messages(messages):
    out = []
    for m in messages:
        role = m.get("role")
        if role == "user":
            out.append({"role": "user", "content": [{"type": "text", "text": str(m.get("content") or "")}]})
        elif role == "assistant":
            if not m.get("content") and not (m.get("tool_calls") or []):
                continue
            content = []
            if m.get("content"):
                content.append({"type": "text", "text": str(m["content"])})
            for tc in m.get("tool_calls") or []:
                content.append({"type": "tool_use", "id": tc.get("id") or tc.get("name"),
                                "name": tc.get("name"), "input": tc.get("args") or {}})
            out.append({"role": "assistant", "content": content or [{"type": "text", "text": ""}]})
        elif role == "tool":
            out.append({"role": "user", "content": [{"type": "tool_result",
                        "tool_use_id": m.get("tool_call_id") or m.get("name"),
                        "content": json.dumps(m.get("content"))}]})
    return out


def _anthropic_complete(model, key, messages, tools, system, timeout):
    body = {
        "model": model, "max_tokens": 1024,
        "messages": _to_anthropic_messages(messages),
        "tools": [{"name": t["name"], "description": t["description"],
                   "input_schema": t["parameters"]} for t in tools],
    }
    if system:
        body["system"] = system
    data = _post_json("https://api.anthropic.com/v1/messages",
                      {"x-api-key": key, "anthropic-version": "2023-06-01",
                       "content-type": "application/json"}, body, timeout)
    text = ""
    calls = []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text += block.get("text") or ""
        elif block.get("type") == "tool_use":
            calls.append({"id": block.get("id"), "name": block.get("name"),
                          "args": block.get("input") or {}})
    return {"text": text, "tool_calls": calls}


def _to_openai_messages(messages, system):
    out = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m.get("role")
        if role == "user":
            out.append({"role": "user", "content": str(m.get("content") or "")})
        elif role == "assistant":
            if not m.get("content") and not (m.get("tool_calls") or []):
                continue
            msg = {"role": "assistant", "content": m.get("content") or None}
            tcs = m.get("tool_calls") or []
            if tcs:
                msg["tool_calls"] = [{"id": tc.get("id") or tc.get("name"), "type": "function",
                                      "function": {"name": tc.get("name"),
                                                   "arguments": json.dumps(tc.get("args") or {})}}
                                     for tc in tcs]
            out.append(msg)
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id") or m.get("name"),
                        "content": json.dumps(m.get("content"))})
    return out


def _openai_complete(model, key, messages, tools, system, timeout):
    body = {
        "model": model,
        "messages": _to_openai_messages(messages, system),
        "tools": [{"type": "function", "function": {"name": t["name"],
                   "description": t["description"], "parameters": t["parameters"]}} for t in tools],
        "tool_choice": "auto",
    }
    data = _post_json("https://api.openai.com/v1/chat/completions",
                      {"Authorization": f"Bearer {key}", "content-type": "application/json"},
                      body, timeout)
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        calls.append({"id": tc.get("id"), "name": fn.get("name"), "args": args})
    return {"text": text, "tool_calls": calls}


def _to_gemini_contents(messages):
    out = []
    for m in messages:
        role = m.get("role")
        if role == "user":
            out.append({"role": "user", "parts": [{"text": str(m.get("content") or "")}]})
        elif role == "assistant":
            if not m.get("content") and not (m.get("tool_calls") or []):
                continue
            parts = []
            if m.get("content"):
                parts.append({"text": str(m["content"])})
            for tc in m.get("tool_calls") or []:
                parts.append({"functionCall": {"name": tc.get("name"), "args": tc.get("args") or {}}})
            out.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif role == "tool":
            out.append({"role": "user", "parts": [{"functionResponse": {
                "name": m.get("name"), "response": {"result": m.get("content")}}}]})
    return out


def _gemini_complete(model, key, messages, tools, system, timeout):
    body = {
        "contents": _to_gemini_contents(messages),
        "tools": [{"function_declarations": [{"name": t["name"], "description": t["description"],
                   "parameters": t["parameters"]} for t in tools]}],
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
           f":generateContent?key={key}")
    data = _post_json(url, {"content-type": "application/json"}, body, timeout)
    cand = (data.get("candidates") or [{}])[0]
    parts = ((cand.get("content") or {}).get("parts")) or []
    text = ""
    calls = []
    for i, p in enumerate(parts):
        if "text" in p:
            text += p.get("text") or ""
        fc = p.get("functionCall")
        if fc:
            calls.append({"id": f"{fc.get('name')}-{i}", "name": fc.get("name"),
                          "args": fc.get("args") or {}})
    return {"text": text, "tool_calls": calls}
