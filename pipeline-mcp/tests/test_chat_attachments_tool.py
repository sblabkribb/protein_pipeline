import base64
from pipeline_mcp import tools


def _b64(d): return base64.b64encode(d).decode("ascii")


def test_chat_send_saves_attachments_and_injects_note(monkeypatch, tmp_path):
    captured = {}

    class R:  # fake runner
        output_root = str(tmp_path)
    def fake_run(provider, model, api_key, messages, tool_executor, *, system=None, **kw):
        captured["messages"] = messages
        return {"reply": "ok", "actions": [], "steps": 1}
    monkeypatch.setattr(tools, "run_chat_turn", fake_run)

    out = tools._chat_send_tool(R(), {
        "provider": "openai", "model": "m", "api_key": "k",
        "messages": [{"role": "user", "content": "look at this"}],
        "session_id": "sess1",
        "attachments": [{"name": "seq.fasta", "base64": _b64(b">a\nACDEFG")}],
    })
    # saved metadata returned
    assert out["saved"][0]["name"] == "seq.fasta"
    # file persisted
    assert (tmp_path / "_chat_uploads" / "sess1" / "seq.fasta").exists()
    # note injected into the last user message the model sees
    last_user = [m for m in captured["messages"] if m["role"] == "user"][-1]
    assert "seq.fasta" in last_user["content"]


def test_chat_list_attachments_tool(tmp_path):
    class R:
        output_root = str(tmp_path)
    tools._chat_send_tool(R(), {"provider": "openai", "model": "m", "api_key": "k",
                                "messages": [{"role": "user", "content": "x"}],
                                "session_id": "s2",
                                "attachments": [{"name": "a.txt", "base64": _b64(b"hi")}]}) \
        if False else None
    # save directly then list
    from pipeline_mcp.chat_attachments import save_chat_attachments
    save_chat_attachments(str(tmp_path), "s2", [{"name": "a.txt", "base64": _b64(b"hi")}])
    out = tools._chat_list_attachments_tool(R(), {"session_id": "s2"})
    assert out["attachments"][0]["name"] == "a.txt"
