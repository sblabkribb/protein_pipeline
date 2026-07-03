import pytest
from pipeline_mcp import chat_agent as ca
from pipeline_mcp.chat_agent import run_chat_turn


def _fake_complete(monkeypatch, scripted):
    seq = list(scripted)
    calls = {"msgs": []}
    def fake(provider, model, api_key, messages, tools, *, system=None, timeout=60.0):
        calls["msgs"].append([dict(m) for m in messages])
        return seq.pop(0)
    monkeypatch.setattr(ca, "_complete", fake)
    return calls


def test_read_tool_round_trip(monkeypatch):
    _fake_complete(monkeypatch, [
        {"text": "", "tool_calls": [{"id": "t1", "name": "pipeline.status", "args": {"run_id": "r1"}}]},
        {"text": "Run r1 is running at the design stage.", "tool_calls": []},
    ])
    seen = {}
    def executor(name, args):
        seen["name"] = name; seen["args"] = args
        return {"state": "running", "stage": "design"}
    out = run_chat_turn("anthropic", "m", "k", [{"role": "user", "content": "status?"}], executor)
    assert out["reply"] == "Run r1 is running at the design stage."
    assert out["actions"] == []
    assert seen == {"name": "pipeline.status", "args": {"run_id": "r1"}}


def test_navigate_collects_action_and_stops(monkeypatch):
    _fake_complete(monkeypatch, [
        {"text": "Taking you to the Fast page.",
         "tool_calls": [{"id": "n1", "name": "navigate", "args": {"page": "fast"}}]},
    ])
    called = {"n": 0}
    def executor(name, args):
        called["n"] += 1
        return {}
    out = run_chat_turn("openai", "m", "k", [{"role": "user", "content": "start a run"}], executor)
    assert out["actions"] == [{"type": "navigate", "page": "fast"}]
    assert out["reply"] == "Taking you to the Fast page."
    assert called["n"] == 0


def test_navigate_invalid_page_coerced_home(monkeypatch):
    _fake_complete(monkeypatch, [
        {"text": "ok", "tool_calls": [{"id": "n1", "name": "navigate", "args": {"page": "bogus"}}]},
    ])
    out = run_chat_turn("gemini", "m", "k", [{"role": "user", "content": "go"}], lambda n, a: {})
    assert out["actions"] == [{"type": "navigate", "page": "home"}]


def test_unknown_tool_feeds_error_and_continues(monkeypatch):
    _fake_complete(monkeypatch, [
        {"text": "", "tool_calls": [{"id": "x1", "name": "pipeline.delete_run", "args": {}}]},
        {"text": "I cannot do that.", "tool_calls": []},
    ])
    called = {"n": 0}
    def executor(name, args):
        called["n"] += 1
        return {}
    out = run_chat_turn("anthropic", "m", "k", [{"role": "user", "content": "delete"}], executor)
    assert out["reply"] == "I cannot do that."
    assert called["n"] == 0


def test_max_steps_cap(monkeypatch):
    _fake_complete(monkeypatch, [
        {"text": "", "tool_calls": [{"id": "t", "name": "pipeline.status", "args": {}}]}
    ] * 10)
    out = run_chat_turn("openai", "m", "k", [{"role": "user", "content": "loop"}],
                        lambda n, a: {"state": "x"}, max_steps=3)
    assert out["steps"] == 3
    assert isinstance(out["reply"], str)


def test_tool_specs_shape():
    specs = ca.tool_specs()
    names = {s["name"] for s in specs}
    assert "navigate" in names
    assert "pipeline.status" in names
    for s in specs:
        assert set(s) >= {"name", "description", "parameters"}
