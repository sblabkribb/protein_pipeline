// Pure-ish helpers for chat attachments. FileReader-based reading lives in app.js;
// these are the testable formatting/session bits.

const SESSION_KEY = "rapid.chat.session.v1";

export function getChatSessionId() {
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = (globalThis.crypto && globalThis.crypto.randomUUID)
        ? globalThis.crypto.randomUUID()
        : `s-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch (_e) {
    return "default";
  }
}

export function attachmentChipLabel(a) {
  const kb = Math.round(((a && a.size) || 0) / 1024);
  return `${(a && a.name) || "file"} (${kb} KB)`;
}

export function withAttachments(payload, attachments, sessionId) {
  return {
    ...payload,
    attachments: Array.isArray(attachments) ? attachments : [],
    session_id: sessionId || "",
  };
}
