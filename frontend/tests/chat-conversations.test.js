import test from "node:test";
import assert from "node:assert/strict";

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const {
  loadConversations, upsertConversation, deleteConversation, conversationTitle, newConversationId,
} = await import("../lib/chat-conversations.js");

test("empty by default", () => {
  store.clear();
  assert.deepEqual(loadConversations(), []);
});

test("conversationTitle uses first user message, capped 40", () => {
  assert.equal(conversationTitle([{ role: "ai", text: "hi" }, { role: "user", text: "hello world" }]), "hello world");
  assert.equal(conversationTitle([{ role: "user", text: "x".repeat(60) }]).length, 40);
  assert.equal(conversationTitle([]), "New chat");
});

test("upsert adds/updates and sorts newest-first", () => {
  store.clear();
  upsertConversation("a", [{ role: "user", text: "first" }], 100);
  upsertConversation("b", [{ role: "user", text: "second" }], 200);
  upsertConversation("a", [{ role: "user", text: "first again" }], 300); // update a
  const list = loadConversations();
  assert.equal(list[0].id, "a");
  assert.equal(list[0].title, "first again");
  assert.equal(list.length, 2);
});

test("delete removes by id", () => {
  store.clear();
  upsertConversation("a", [{ role: "user", text: "x" }], 1);
  upsertConversation("b", [{ role: "user", text: "y" }], 2);
  const after = deleteConversation("a");
  assert.deepEqual(after.map((c) => c.id), ["b"]);
});

test("newConversationId is unique-ish and stable string", () => {
  const a = newConversationId();
  assert.ok(typeof a === "string" && a.length >= 6);
});

test("caps at 30 newest", () => {
  store.clear();
  for (let i = 0; i < 35; i++) upsertConversation(`c${i}`, [{ role: "user", text: `m${i}` }], i);
  assert.equal(loadConversations().length, 30);
  assert.equal(loadConversations()[0].id, "c34");
});
