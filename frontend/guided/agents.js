// frontend/guided/agents.js — 에이전트 탭. 선택된 실행의 agent panel 이벤트를
// 보여준다. 규칙 기반 전문가(구조·단백질·리간드·실험)의 스테이지별 판정이
// 여기 쌓인다. 행 모양은 agent_panel.jsonl 의 것 - state 필드는 없고 실패는
// error 와 consensus.decision("proceed"|"monitor"|"recover")으로 온다.
import { callTool } from "./api.js";
import { el } from "./dom.js";
// 순환 import: monitor 는 facade(guided.js)를 다시 참조한다. 함수 선언 hoisting
// 과 facade 의 브라우저 가드로 안전하고, 모듈 최상위에서 호출하지 않는다.
import { currentRunStatus } from "./monitor.js";

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

// 마지막으로 성공한 판정 읽기. facade 가 성공 응답에서 기록하고, 폴링 tick 이
// 헤더를 다시 그릴 때 같은 실행의 판정인지 가리는 근거로 쓴다. 다른 실행을
// 물으면 빈 목록을 돌려준다 - 낡은 실행의 판정이 새 실행 화면에 그려지지 않게.
let lastEvents = [];
let lastRunId = "";

export function rememberAgentEvents(runId, events) {
  lastRunId = String(runId || "");
  lastEvents = Array.isArray(events) ? events : [];
  return lastEvents;
}

export function currentAgentEvents(runId) {
  return String(runId || "") === lastRunId ? lastEvents : [];
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

// 실행 상태 칩. 모르는 상태는 받은 값 그대로 보인다 - 프런트가 상태를 새로
// 해석하면 Run 탭과 말이 갈라진다. cancelled 는 상태 해석이 아니라 번역이다 -
// 상단바 칩과 같은 말을 하게 한다.
function runStateChip(state) {
  const key = String(state || "").trim().toLowerCase();
  if (key === "done" || key === "completed") return { cls: "okchip", label: "완료" };
  if (key === "running") return { cls: "warnchip", label: "진행 중" };
  if (key === "failed" || key === "error") return { cls: "badchip", label: "실패" };
  if (key === "cancelled") return { cls: "chip", label: "취소됨" };
  return { cls: "chip", label: key || "-" };
}

// 지금 어디를 돌고 있는지 - 판정 목록 위에 현재 상태를 고정 표시한다. 상태는
// monitor runState 가 기억한 마지막 조회값이다 (status 인자로 겹쳐 쓸 수 있다).
function statusHeader(status) {
  const card = el("div", "skill");
  card.appendChild(el("span", "", "현재"));
  if (!status) {
    card.appendChild(el("span", "chip", "상태 없음"));
    return card;
  }
  if (status.stage) card.appendChild(el("span", "chip", String(status.stage)));
  const chip = runStateChip(status.state);
  card.appendChild(el("span", chip.cls, chip.label));
  return card;
}

export function renderAgentsTab(host, { state = "idle", events = [], runId = "", message = "", status = null } = {}) {
  const live = status ?? currentRunStatus();
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
    if (runId) host.appendChild(statusHeader(live));
    host.appendChild(el("p", "note",
      `이 실행에는 에이전트 판정 기록이 없습니다. (${runId})`));
    return;
  }

  const models = agentEventModels(events);
  if (runId) host.appendChild(statusHeader(live));
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
