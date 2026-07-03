from pipeline_mcp import tools
from pipeline_mcp.chat_agent import ChatProviderError


def test_chat_send_success(monkeypatch):
    captured = {}
    def fake_run(provider, model, api_key, messages, tool_executor, *, system=None, **kw):
        captured["system"] = system
        captured["executor"] = tool_executor
        return {"reply": "hello", "actions": [{"type": "navigate", "page": "fast"}], "steps": 2}
    monkeypatch.setattr(tools, "run_chat_turn", fake_run)
    out = tools._chat_send_tool(object(), {
        "provider": "openai", "model": "gpt-x", "api_key": "sk",
        "messages": [{"role": "user", "content": "hi"}],
        "context": {"tab": "monitor", "run_id": "r1"},
    })
    assert out["provider"] == "openai" and out["model"] == "gpt-x"
    assert out["reply"] == "hello"
    assert out["actions"] == [{"type": "navigate", "page": "fast"}]
    assert "monitor" in captured["system"] and "r1" in captured["system"]


def test_chat_send_error_shape(monkeypatch):
    def fake_run(*a, **k):
        raise ChatProviderError("auth", "provider rejected the API key")
    monkeypatch.setattr(tools, "run_chat_turn", fake_run)
    out = tools._chat_send_tool(object(), {"provider": "anthropic", "model": "m",
                                           "api_key": "bad", "messages": []})
    assert out == {"error": {"kind": "auth", "message": "provider rejected the API key"},
                   "provider": "anthropic"}


def test_chat_send_executor_allowlist(monkeypatch):
    holder = {}
    def fake_run(provider, model, api_key, messages, tool_executor, *, system=None, **kw):
        holder["executor"] = tool_executor
        return {"reply": "", "actions": [], "steps": 1}
    monkeypatch.setattr(tools, "run_chat_turn", fake_run)
    dispatched = {"names": []}
    monkeypatch.setattr(tools.ToolDispatcher, "call_tool",
                        lambda self, name, args: dispatched["names"].append(name) or {"ok": True})
    tools._chat_send_tool(object(), {"provider": "openai", "model": "m", "api_key": "k",
                                     "messages": []})
    executor = holder["executor"]
    assert executor("pipeline.delete_run", {}) == {"error": "tool not available"}
    assert executor("pipeline.status", {"run_id": "r1"}) == {"ok": True}
    assert dispatched["names"] == ["pipeline.status"]
