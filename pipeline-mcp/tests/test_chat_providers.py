import pytest

from pipeline_mcp import chat_providers as cp
from pipeline_mcp.chat_providers import ChatProviderError, list_chat_models


class FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _patch_get(monkeypatch, resp, capture=None):
    def fake_get(url, headers=None, timeout=None):
        if capture is not None:
            capture["url"] = url
            capture["headers"] = headers or {}
        if isinstance(resp, Exception):
            raise resp
        return resp
    monkeypatch.setattr(cp.requests, "get", fake_get)


def test_anthropic_maps_id_and_display_name(monkeypatch):
    cap = {}
    _patch_get(monkeypatch, FakeResp(200, {"data": [
        {"id": "claude-opus-4-8", "display_name": "Claude Opus 4.8"},
        {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5"},
    ]}), cap)
    models = list_chat_models("anthropic", "sk-ant-xxx")
    assert {"id": "claude-opus-4-8", "label": "Claude Opus 4.8"} in models
    assert cap["headers"].get("anthropic-version") == "2023-06-01"
    assert cap["headers"].get("x-api-key") == "sk-ant-xxx"
    assert [m["id"] for m in models] == sorted(m["id"] for m in models)


def test_openai_filters_non_chat(monkeypatch):
    _patch_get(monkeypatch, FakeResp(200, {"data": [
        {"id": "gpt-4o"},
        {"id": "text-embedding-3-large"},
        {"id": "whisper-1"},
        {"id": "dall-e-3"},
    ]}))
    ids = [m["id"] for m in list_chat_models("openai", "sk-xxx")]
    assert ids == ["gpt-4o"]


def test_gemini_keeps_only_generate_content_and_strips_prefix(monkeypatch):
    _patch_get(monkeypatch, FakeResp(200, {"models": [
        {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro",
         "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/embedding-001", "displayName": "Embedding",
         "supportedGenerationMethods": ["embedContent"]},
    ]}))
    models = list_chat_models("gemini", "key-xxx")
    assert models == [{"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"}]


def test_auth_error_on_401(monkeypatch):
    _patch_get(monkeypatch, FakeResp(401, {}))
    with pytest.raises(ChatProviderError) as exc:
        list_chat_models("anthropic", "bad")
    assert exc.value.kind == "auth"


def test_upstream_error_on_network_failure(monkeypatch):
    _patch_get(monkeypatch, cp.requests.RequestException("boom"))
    with pytest.raises(ChatProviderError) as exc:
        list_chat_models("openai", "sk-xxx")
    assert exc.value.kind == "upstream"


def test_unknown_provider_no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not call network")
    monkeypatch.setattr(cp.requests, "get", boom)
    with pytest.raises(ChatProviderError) as exc:
        list_chat_models("mistral", "k")
    assert exc.value.kind == "unknown_provider"


def test_empty_key_no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not call network")
    monkeypatch.setattr(cp.requests, "get", boom)
    with pytest.raises(ChatProviderError) as exc:
        list_chat_models("anthropic", "  ")
    assert exc.value.kind == "auth"


def test_provider_aliases(monkeypatch):
    _patch_get(monkeypatch, FakeResp(200, {"data": [{"id": "gpt-4o"}]}))
    assert list_chat_models("codex", "sk")[0]["id"] == "gpt-4o"


def test_gemini_network_error_does_not_leak_key(monkeypatch):
    secret = "AIzaSecretKey123"
    _patch_get(monkeypatch, cp.requests.RequestException(
        f"HTTPSConnectionPool: Max retries exceeded with url: "
        f"/v1beta/models?key={secret} (Caused by ...)"))
    with pytest.raises(ChatProviderError) as exc:
        list_chat_models("gemini", secret)
    assert exc.value.kind == "upstream"
    assert secret not in exc.value.message
    assert secret not in str(exc.value)
