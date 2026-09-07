// frontend/guided/agents.js — 에이전트 탭. 선택된 실행의 agent panel 이벤트를
// 보여준다. 규칙 기반 전문가(구조·단백질·리간드·실험)의 스테이지별 판정이
// 여기 쌓인다. 행 모양은 agent_panel.jsonl 의 것 - state 필드는 없고 실패는
// error 와 consensus.decision("proceed"|"monitor"|"recover")으로 온다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function agentEventModels(events) {
  const rows = Array.isArray(events) ? events : [];
  return rows.map((row) => {
    const item = row && typeof row === "object" ? row : {};
    const consensus = item.consensus && typeof item.consensus === "object" ? item.consensus : {};
    const interpretations = Array.isArray(consensus.interpretations)
      ? consensus.interpretations.map(String).filter(Boolean).slice(0, 3) : [];
    const actions = Array.isArray(consensus.actions)
      ? consensus.actions.map(String).filter(Boolean).slice(0, 3) : [];
    return {
      stage: String(item.stage || ""),
      decision: String(consensus.decision || ""),
      detail: String(item.detail || ""),
      error: String(item.error || ""),
      interpretations,
      actions,
    };
  });
}

// 판정 칩. 서버의 decision 이 유일한 근거다 - 프런트가 성공·실패를 재해석하지
// 않는다. error 가 붙은 행은 decision 이 recover 인 것이 보통이지만, 두 근거가
// 어긋나도 error 를 먼저 말한다.
function decisionChip(model) {
  if (model.error) return { cls: "badchip", label: "실패" };
  if (model.decision === "proceed") return { cls: "okchip", label: "진행" };
  if (model.decision === "monitor") return { cls: "warnchip", label: "관찰" };
  if (model.decision === "recover") return { cls: "badchip", label: "복구" };
  return { cls: "chip", label: model.decision || "-" };
}

export function renderAgentsTab(host, { state = "idle", events = [], runId = "", message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "에이전트 판정을 확인하는 중…"));
    return;
  }
  if (state === "no-run") {
    host.appendChild(el("p", "note", "실행을 선택하면 에이전트 판정이 여기 표시됩니다."));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "에이전트 판정을 확인하지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    if (typeof retry.addEventListener === "function") {
      retry.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__agentsTabLoad) window.__agentsTabLoad(true);
      });
    }
    host.appendChild(retry);
    return;
  }
  if (state === "empty") {
    host.appendChild(el("p", "note",
      `이 실행에는 에이전트 판정 기록이 없습니다. (${runId})`));
    return;
  }

  const models = agentEventModels(events);
  host.appendChild(el("h3", "", "에이전트 판정"));
  host.appendChild(el("p", "note",
    "스테이지마다 규칙 기반 전문가(구조·단백질·리간드·실험)가 산 출한 합의 판정입니다. 최근 20건."));
  for (const model of models) {
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", model.stage || "-"));
    const chip = decisionChip(model);
    head.appendChild(el("span", chip.cls, chip.label));
    card.appendChild(head);
    for (const line of model.interpretations) {
      card.appendChild(el("p", "note", `· ${line}`));
    }
    if (model.detail) card.appendChild(el("p", "note", model.detail));
    if (model.error) card.appendChild(el("p", "warn", model.error));
    host.appendChild(card);
  }
}

export async function requestAgentEvents(runId) {
  const out = await callTool("pipeline.list_agent_events", { run_id: runId, limit: 20 });
  if (out && out.error) throw new Error(out.error);
  return out;
}
