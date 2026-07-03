"""Chat-LLM provider adapters: list a user's chat-capable models given an API key.

Single responsibility: turn (provider, api_key) into a normalized list of
[{"id","label"}] chat models by calling the provider's models endpoint over a
hardcoded host. No key is stored or logged; the key is used only for the request.
"""
from __future__ import annotations

import requests

CHAT_PROVIDERS = ("anthropic", "openai", "gemini")

_ALIASES = {
    "anthropic": "anthropic", "claude": "anthropic",
    "openai": "openai", "gpt": "openai", "codex": "openai",
    "gemini": "gemini", "google": "gemini",
}

# OpenAI /v1/models returns non-chat models too; drop these by id substring.
_OPENAI_EXCLUDE = ("embedding", "whisper", "tts", "dall-e", "moderation",
                   "audio", "realtime", "image")


class ChatProviderError(Exception):
    """kind: 'auth' | 'upstream' | 'unknown_provider'."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _normalize_provider(provider: str) -> str:
    key = str(provider or "").strip().lower()
    if key not in _ALIASES:
        raise ChatProviderError("unknown_provider", f"unknown provider: {provider}")
    return _ALIASES[key]


def _get(url: str, headers: dict, timeout: float) -> dict:
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise ChatProviderError("upstream", f"request failed: {exc}") from exc
    if resp.status_code in (401, 403):
        raise ChatProviderError("auth", "provider rejected the API key")
    if resp.status_code >= 400:
        raise ChatProviderError("upstream", f"provider returned HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ChatProviderError("upstream", "provider returned invalid JSON") from exc
    return data if isinstance(data, dict) else {}


def _anthropic_models(api_key: str, timeout: float) -> list[dict]:
    data = _get(
        "https://api.anthropic.com/v1/models",
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout,
    )
    out: list[dict] = []
    for m in data.get("data", []):
        mid = str((m or {}).get("id") or "").strip()
        if mid:
            out.append({"id": mid, "label": str(m.get("display_name") or mid)})
    return out


def _openai_models(api_key: str, timeout: float) -> list[dict]:
    data = _get(
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {api_key}"},
        timeout,
    )
    out: list[dict] = []
    for m in data.get("data", []):
        mid = str((m or {}).get("id") or "").strip()
        if not mid:
            continue
        low = mid.lower()
        if any(tok in low for tok in _OPENAI_EXCLUDE):
            continue
        out.append({"id": mid, "label": mid})
    return out


def _gemini_models(api_key: str, timeout: float) -> list[dict]:
    data = _get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
        {},
        timeout,
    )
    out: list[dict] = []
    for m in data.get("models", []):
        methods = (m or {}).get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        name = str(m.get("name") or "").strip()
        mid = name[len("models/"):] if name.startswith("models/") else name
        if mid:
            out.append({"id": mid, "label": str(m.get("displayName") or mid)})
    return out


def list_chat_models(provider: str, api_key: str, *, timeout: float = 15.0) -> list[dict]:
    """Return chat-capable models as sorted, de-duplicated [{"id","label"}]."""
    canonical = _normalize_provider(provider)
    key = str(api_key or "").strip()
    if not key:
        raise ChatProviderError("auth", "API key is required")
    if canonical == "anthropic":
        rows = _anthropic_models(key, timeout)
    elif canonical == "openai":
        rows = _openai_models(key, timeout)
    else:
        rows = _gemini_models(key, timeout)
    dedup = {r["id"]: r for r in rows}
    return sorted(dedup.values(), key=lambda r: r["id"])
