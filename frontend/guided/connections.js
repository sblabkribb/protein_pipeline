// frontend/guided/connections.js — 연결 탭. "연결됨"을 상수로 주장하지 않고
// 매번 실측한다(list_models check_liveness). 선언된 가용성 옆에 실측을 나란히 둔다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function connectionRowModels(liveness) {
  const rows = Object.entries(liveness || {});
  return rows
    .map(([id, info]) => {
      const item = info && typeof info === "object" ? info : {};
      return {
        id: String(id),
        endpoint: String(item.endpoint || ""),
        reachable: Boolean(item.reachable),
        ready: item.ready == null ? null : Boolean(item.ready),
        mismatch: Boolean(item.model_mismatch),
        declared: String(item.declared_availability || ""),
        error: String(item.error || ""),
      };
    })
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function renderConnectionsTab(host, { state = "idle", data = null, message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "엔드포인트를 확인하는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "확인하지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    if (typeof retry.addEventListener === "function") {
      retry.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__connectionsTabLoad) window.__connectionsTabLoad(true);
      });
    }
    host.appendChild(retry);
    return;
  }
  const payload = data && typeof data === "object" ? data : {};
  const rows = connectionRowModels(payload.liveness);
  if (!rows.length) {
    host.appendChild(el("p", "note", "확인할 엔드포인트가 없습니다."));
    return;
  }

  host.appendChild(el("h3", "", "엔드포인트 실측"));
  for (const row of rows) {
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", row.id));
    head.appendChild(el("span", row.reachable ? "okchip" : "badchip", row.reachable ? "도달" : "도달 불가"));
    if (row.ready === true) head.appendChild(el("span", "okchip", "준비됨"));
    if (row.ready === false) head.appendChild(el("span", "warnchip", "미준비"));
    if (row.mismatch) head.appendChild(el("span", "warnchip", "모델 불일치"));
    card.appendChild(head);
    const meta = [row.endpoint, row.declared && `선언 ${row.declared}`, row.error].filter(Boolean).join(" · ");
    if (meta) card.appendChild(el("p", "note", meta));
    host.appendChild(card);
  }

  const bop = payload.connections && payload.connections.bop_workers;
  if (bop) {
    host.appendChild(el("h3", "", "BOP 워커 요약"));
    host.appendChild(el("p", "note", `선언 ${bop.declared ?? 0}개 · 실측 도달 ${bop.reachable ?? 0}개`));
  }

  const portal = payload.connections && payload.connections.portal_mcp;
  if (portal) {
    host.appendChild(el("h3", "", "포털 연결"));
    const configured = Boolean(portal.configured);
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", "바이오모델 포털"));
    head.appendChild(el("span", configured ? "okchip" : "warnchip", configured ? "설정됨" : "미설정"));
    card.appendChild(head);
    const unlocks = Array.isArray(portal.would_unlock) ? portal.would_unlock : [];
    const note = [portal.integration && `통합: ${portal.integration}`,
      unlocks.length && `열리는 모델: ${unlocks.join(", ")}`,
      portal.still_blocked_note].filter(Boolean).join(" — ");
    if (note) card.appendChild(el("p", "note", note));
    host.appendChild(card);
  }
}

export async function requestConnections() {
  const out = await callTool("pipeline.list_models", { check_liveness: true });
  if (out && out.error) throw new Error(out.error);
  return out;
}
