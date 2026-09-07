// frontend/guided/api.js — DOM 을 모르는 전송/세션 계층.
import { resolveDefaultApiBase } from "../lib/auth.js";
import { unwrapToolResponse } from "../lib/tool-call.js";

// 기존 앱과 같은 규칙. 빈 문자열이면 /tools/call 을 원점 기준으로 호출하는데,
// 배포 환경의 리버스 프록시는 /api/* 만 백엔드로 보내므로 그대로 404 가 난다.
export function apiBase() {
  const saved = (localStorage.getItem("kbf.apiBase") || "").replace(/\/+$/, "");
  if (saved && !/localhost|127\.0\.0\.1/.test(saved)) return saved;
  return resolveDefaultApiBase({
    origin: window.location.origin,
    pathname: window.location.pathname,
  }).replace(/\/+$/, "");
}

export function authHeaders() {
  const token = localStorage.getItem("kbf.token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function storedUserName() {
  try {
    const raw = JSON.parse(localStorage.getItem("kbf.user") || "null");
    return raw ? String(raw.username || raw.name || raw.id || "") : "";
  } catch {
    return "";
  }
}

export async function callTool(name, args) {
  const res = await fetch(`${apiBase()}/tools/call`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, arguments: args || {} }),
  });
  const payload = await res.json().catch(() => null);
  // 봉투를 벗겨서 도구 결과만 돌려준다. 봉투를 그대로 넘기면 호출자가 보는
  // 모든 필드가 undefined 가 되고, 200 응답이라 오류도 뜨지 않는다.
  return unwrapToolResponse({ ok: res.ok, status: res.status, payload });
}

// 던져진 것이 Error 가 아닐 수 있다. 메시지가 없으면 그 사실을 말한다.
export function errorText(error) {
  if (!error) return "알 수 없는 오류";
  if (typeof error === "string") return error;
  return (error && error.message) || String(error) || "알 수 없는 오류";
}
