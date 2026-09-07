// frontend/guided/templates.js — 템플릿 탭. 목적 경로를 카드로 보고 "이 목적으로
// 시작"으로 중앙 목표 단계에 진입시킨다. 데이터는 모델 탭과 같은 list_models.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function templateCardModels(payload) {
  const data = payload && typeof payload === "object" ? payload : {};
  return (Array.isArray(data.purposes) ? data.purposes : [])
    .filter((p) => p && typeof p === "object")
    .map((p) => ({
      purpose: String(p.purpose || ""),
      name: String(p.display_name_ko || p.purpose || ""),
      executable: Boolean(p.executable),
      validated: Boolean(p.validated),
      state: !p.executable ? "blocked" : p.validated ? "validated" : "unvalidated",
      unvalidatedStages: Array.isArray(p.unvalidated_stages) ? p.unvalidated_stages.map(String) : [],
    }));
}

export function renderTemplatesTab(host, { state = "idle", model = [], message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "템플릿을 불러오는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "템플릿을 불러오지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    if (typeof retry.addEventListener === "function") {
      retry.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__templatesTabLoad) window.__templatesTabLoad(true);
      });
    }
    host.appendChild(retry);
    return;
  }
  if (state === "idle") {
    host.appendChild(el("p", "note", "템플릿 탭입니다."));
    return;
  }
  if (!model.length) {
    host.appendChild(el("p", "note", "사용할 수 있는 목적이 없습니다."));
    return;
  }
  for (const card of model) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", card.name));
    if (card.state === "validated") head.appendChild(el("span", "okchip", "검증됨"));
    else if (card.state === "unvalidated") head.appendChild(el("span", "warnchip", "미검증"));
    else head.appendChild(el("span", "badchip", "실행 불가"));
    row.appendChild(head);
    if (card.unvalidatedStages.length) {
      row.appendChild(el("p", "note", `미검증 단계: ${card.unvalidatedStages.join(", ")}`));
    }
    const start = document.createElement("button");
    start.type = "button";
    start.className = "ghost";
    start.textContent = "이 목적으로 시작";
    if (typeof start.addEventListener === "function") {
      start.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__templatesStart) window.__templatesStart(card.purpose);
      });
    }
    row.appendChild(start);
    host.appendChild(row);
  }
}

export async function requestTemplates() {
  const out = await callTool("pipeline.list_models", {});
  if (out && out.error) throw new Error(out.error);
  return out;
}
