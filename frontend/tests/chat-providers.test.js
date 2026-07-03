import test from "node:test";
import assert from "node:assert/strict";

// Minimal localStorage stub (module reads it at call time, not import time).
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const { PROVIDERS, loadChatConfig, saveChatConfig, chatConfigReady, providerLabel } =
  await import("../lib/chat-providers.js");

test("PROVIDERS lists the three providers", () => {
  assert.deepEqual(PROVIDERS.map((p) => p.id), ["anthropic", "openai", "gemini"]);
});

test("loadChatConfig defaults on empty storage", () => {
  store.clear();
  const cfg = loadChatConfig();
  assert.equal(cfg.provider, "anthropic");
  assert.equal(cfg.model, "");
  assert.deepEqual(cfg.keys, {});
});

test("loadChatConfig tolerates corrupt storage", () => {
  store.clear();
  store.set("rapid.chat.config.v1", "{not json");
  const cfg = loadChatConfig();
  assert.equal(cfg.provider, "anthropic");
});

test("saveChatConfig round-trips", () => {
  store.clear();
  saveChatConfig({ provider: "openai", model: "gpt-4o", keys: { openai: "sk" } });
  const cfg = loadChatConfig();
  assert.equal(cfg.provider, "openai");
  assert.equal(cfg.model, "gpt-4o");
  assert.equal(cfg.keys.openai, "sk");
});

test("chatConfigReady requires provider, its key, and a model", () => {
  assert.equal(chatConfigReady({ provider: "openai", model: "", keys: { openai: "sk" } }), false);
  assert.equal(chatConfigReady({ provider: "openai", model: "gpt-4o", keys: {} }), false);
  assert.equal(chatConfigReady({ provider: "openai", model: "gpt-4o", keys: { openai: "sk" } }), true);
});

test("providerLabel maps id to label and falls back to id", () => {
  assert.equal(providerLabel("anthropic"), "Claude");
  assert.equal(providerLabel("mystery"), "mystery");
});
