import test from "node:test";
import assert from "node:assert/strict";

const { buildChatSendPayload, parseChatSendResult, navigateActions, NAVIGABLE_PAGES } =
  await import("../lib/chat-agent.js");

test("buildChatSendPayload maps cfg/history/snapshot", () => {
  const cfg = { provider: "openai", model: "gpt-4o", keys: { openai: "sk" } };
  const history = [
    { role: "user", text: "hi" },
    { role: "ai", text: "hello" },
  ];
  const p = buildChatSendPayload(cfg, history, { tab: "monitor", runId: "r1" });
  assert.equal(p.provider, "openai");
  assert.equal(p.model, "gpt-4o");
  assert.equal(p.api_key, "sk");
  assert.deepEqual(p.messages, [
    { role: "user", content: "hi" },
    { role: "assistant", content: "hello" },
  ]);
  assert.deepEqual(p.context, { tab: "monitor", run_id: "r1" });
});

test("parseChatSendResult extracts reply + actions", () => {
  const r = parseChatSendResult({ reply: "ok", actions: [{ type: "navigate", page: "fast" }] });
  assert.equal(r.reply, "ok");
  assert.deepEqual(r.actions, [{ type: "navigate", page: "fast" }]);
  assert.equal(r.error, undefined);
});

test("parseChatSendResult surfaces error", () => {
  const r = parseChatSendResult({ error: { kind: "auth", message: "bad key" } });
  assert.deepEqual(r.error, { kind: "auth", message: "bad key" });
  assert.equal(r.reply, "");
});

test("navigateActions keeps valid pages only", () => {
  const a = navigateActions([
    { type: "navigate", page: "fast" },
    { type: "navigate", page: "bogus" },
    { type: "other", page: "fast" },
  ]);
  assert.deepEqual(a, [{ type: "navigate", page: "fast" }]);
});

test("NAVIGABLE_PAGES matches the backend enum", () => {
  assert.deepEqual(NAVIGABLE_PAGES,
    ["home", "fast", "advanced", "evolution", "studio", "monitor", "rounds", "analyze"]);
});

test("navigateActions preserves prefill", () => {
  const a = navigateActions([
    { type: "navigate", page: "fast", prefill: { attachment: "seq.fasta" } },
    { type: "navigate", page: "bogus", prefill: { attachment: "x" } },
  ]);
  assert.deepEqual(a, [{ type: "navigate", page: "fast", prefill: { attachment: "seq.fasta" } }]);
});
