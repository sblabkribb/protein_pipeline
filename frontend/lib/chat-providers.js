// Browser-only config + storage for the AI chatbot provider/model selection.
// Keys live here in localStorage and are sent to the server only per chat request.

export const PROVIDERS = [
  { id: "anthropic", label: "Claude" },
  { id: "openai", label: "OpenAI (Codex)" },
  { id: "gemini", label: "Gemini" },
];

const STORAGE_KEY = "rapid.chat.config.v1";

function defaults() {
  return { provider: "anthropic", model: "", keys: {} };
}

export function loadChatConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults();
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return defaults();
    return {
      provider: typeof parsed.provider === "string" ? parsed.provider : "anthropic",
      model: typeof parsed.model === "string" ? parsed.model : "",
      keys: parsed.keys && typeof parsed.keys === "object" ? parsed.keys : {},
    };
  } catch (_e) {
    return defaults();
  }
}

export function saveChatConfig(cfg) {
  const safe = {
    provider: (cfg && cfg.provider) || "anthropic",
    model: (cfg && cfg.model) || "",
    keys: (cfg && cfg.keys && typeof cfg.keys === "object") ? cfg.keys : {},
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(safe));
  } catch (_e) {
    /* storage full / disabled — non-fatal */
  }
  return safe;
}

export function chatConfigReady(cfg) {
  if (!cfg || typeof cfg !== "object") return false;
  const key = cfg.keys && cfg.keys[cfg.provider];
  return Boolean(cfg.provider && key && cfg.model);
}

export function providerLabel(id) {
  const found = PROVIDERS.find((p) => p.id === id);
  return found ? found.label : String(id || "");
}
