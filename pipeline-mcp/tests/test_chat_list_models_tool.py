from pipeline_mcp import tools
from pipeline_mcp.chat_providers import ChatProviderError


def test_tool_returns_models(monkeypatch):
    monkeypatch.setattr(
        tools, "list_chat_models",
        lambda provider, api_key: [{"id": "gpt-4o", "label": "gpt-4o"}],
    )
    out = tools._chat_list_models_tool(None, {"provider": "openai", "api_key": "sk"})
    assert out == {"provider": "openai", "models": [{"id": "gpt-4o", "label": "gpt-4o"}]}


def test_tool_returns_error_shape(monkeypatch):
    def boom(provider, api_key):
        raise ChatProviderError("auth", "provider rejected the API key")
    monkeypatch.setattr(tools, "list_chat_models", boom)
    out = tools._chat_list_models_tool(None, {"provider": "anthropic", "api_key": "bad"})
    assert out == {"error": {"kind": "auth", "message": "provider rejected the API key"},
                   "provider": "anthropic"}
