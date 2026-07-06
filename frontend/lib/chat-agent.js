// Pure helpers for the chatbot agent turn (build request, parse response).
// No DOM, no network. History items use {role:"user"|"ai", text}.

export const NAVIGABLE_PAGES = [
  "home", "fast", "advanced", "evolution", "studio", "monitor", "rounds", "analyze",
];

export function buildChatSendPayload(cfg, history, snapshot) {
  const provider = (cfg && cfg.provider) || "";
  const messages = (Array.isArray(history) ? history : []).map((h) => ({
    role: h && h.role === "user" ? "user" : "assistant",
    content: String((h && h.text) || ""),
  }));
  return {
    provider,
    model: (cfg && cfg.model) || "",
    api_key: (cfg && cfg.keys && cfg.keys[provider]) || "",
    messages,
    context: {
      tab: (snapshot && snapshot.tab) || "",
      run_id: (snapshot && (snapshot.runId || snapshot.run_id)) || "",
      lang: (snapshot && snapshot.lang) || "en",
    },
  };
}

export function parseChatSendResult(res) {
  if (res && res.error) {
    return { reply: "", actions: [], error: res.error };
  }
  return {
    reply: (res && res.reply) || "",
    actions: (res && Array.isArray(res.actions)) ? res.actions : [],
  };
}

export function navigateActions(actions) {
  return (Array.isArray(actions) ? actions : []).filter(
    (a) => a && a.type === "navigate" && NAVIGABLE_PAGES.includes(a.page),
  );
}
