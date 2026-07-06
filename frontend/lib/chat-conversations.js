// Browser-stored copilot conversation history (BMP-style). No DOM/network.
// A conversation: { id, title, messages:[{role:"user"|"ai", text}], updatedAt }.

const KEY = "rapid.chat.conversations.v1";
const MAX = 30;

export function loadConversations() {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_e) {
    return [];
  }
}

function persist(list) {
  try {
    const trimmed = [...list]
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
      .slice(0, MAX);
    localStorage.setItem(KEY, JSON.stringify(trimmed));
    return trimmed;
  } catch (_e) {
    return list;
  }
}

export function conversationTitle(messages) {
  const first = (Array.isArray(messages) ? messages : []).find((m) => m && m.role === "user");
  const t = String((first && first.text) || "").trim();
  return t ? t.slice(0, 40) : "New chat";
}

export function upsertConversation(id, messages, now) {
  const others = loadConversations().filter((c) => c.id !== id);
  const entry = {
    id,
    title: conversationTitle(messages),
    messages: Array.isArray(messages) ? messages : [],
    updatedAt: typeof now === "number" ? now : Date.now(),
  };
  return persist([entry, ...others]);
}

export function deleteConversation(id) {
  return persist(loadConversations().filter((c) => c.id !== id));
}

export function newConversationId() {
  return (globalThis.crypto && globalThis.crypto.randomUUID)
    ? globalThis.crypto.randomUUID()
    : `c-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}
