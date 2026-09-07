import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// agents.js 는 monitor.js 를 경유해 facade(guided.js)까지 import 한다. facade 는
// document 가 있으면 모듈 최상위에서 배선을 시작하므로, 스텁을 만들기 전에 모듈을
// 먼저 적재해야 한다 - 가드가 브라우저 밖 배선을 건너뛴다. 스텁은 렌더 시점의
// document.createElement 를 위해 그 뒤에 둔다.
const { agentEventModels, renderAgentsTab, rememberAgentEvents, currentAgentEvents } = await import("../guided/agents.js");

globalThis.document ??= {
  createElement(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      className: "",
      textContent: "",
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  },
};

// agent_panel.jsonl 의 실제 행 모양(build_agent_panel_event). state 필드는 없고
// 실패는 error + consensus.decision("proceed"|"monitor"|"recover")로 온다.
const EVENTS = [
  { id: "e1", kind: "agent_panel", stage: "msa", stage_base: "msa", tier: null,
    detail: null, error: null, recovery: null,
    consensus: { decision: "proceed", confidence: 0.9, rationale: "", actions: [],
      interpretations: ["인터프리트 1", "인터프리트 2"] },
    created_at: "2026-09-07T00:00:00Z" },
  { id: "e2", kind: "agent_panel", stage: "af2_tier1", stage_base: "af2", tier: "tier1",
    detail: "tier1 완료", error: "af2 실패", recovery: null,
    consensus: { decision: "recover", confidence: 0.1, rationale: "structure: af2 실패",
      actions: ["다시 시도"], interpretations: [] },
    created_at: "2026-09-07T00:01:00Z" },
  { id: "e3", kind: "agent_panel", stage: "proteinmpnn_tier1", stage_base: "proteinmpnn",
    tier: "tier1", detail: null, error: null, recovery: null,
    consensus: { decision: "monitor", confidence: 0.5, rationale: "", actions: [],
      interpretations: ["해석 1", "해석 2", "해석 3", "해석 4"] },
    created_at: "2026-09-07T00:02:00Z" },
];

test("agentEventModels absorbs rows, exposes decision and caps interpretations", () => {
  const models = agentEventModels(EVENTS);
  assert.equal(models[0].stage, "msa");
  assert.equal(models[0].decision, "proceed");
  assert.equal(models[0].interpretations.length, 2);
  assert.equal(models[1].stage, "af2_tier1");
  assert.equal(models[1].decision, "recover");
  assert.equal(models[1].error, "af2 실패");
  assert.equal(models[2].interpretations.length, 3);
  assert.equal(agentEventModels(null).length, 0);
  assert.equal(agentEventModels([null])[0].stage, "");
});

test("renderAgentsTab paints event cards with stage and chips", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderAgentsTab(host, { state: "done", events: EVENTS, runId: "run_x" });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("msa"));
  assert.ok(html.includes("인터프리트 1"));
  assert.ok(html.includes("af2 실패") || html.includes("복구"));
  assert.ok(html.includes("· 해석 1"), "interpretations render as prefixed note lines");
});

test("renderAgentsTab paints no-run, loading, error and empty states", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderAgentsTab(h0, { state: "no-run" });
  assert.match(h0.children[0].textContent, /실행을/);
  const h1 = make(); renderAgentsTab(h1, { state: "loading" });
  assert.match(h1.children[0].textContent, /확인하는 중|불러오는 중/);
  const h2 = make(); renderAgentsTab(h2, { state: "error", message: "실패" });
  assert.match(h2.children[0].textContent, /실패/);
  const h3 = make(); renderAgentsTab(h3, { state: "empty", runId: "run_x" });
  // 빈 상태는 현재 상태 헤더 카드에 이어 안내 노드를 그린다.
  assert.ok(h3.children.some((c) => c.textContent.length > 0));
});

test("the shell hosts the agents tab wired to the selected run", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('data-sidetab="agents"'));
  assert.ok(html.includes('id="sideAgents"'));
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"agents"'));
  assert.ok(src.includes("__agentsTabLoad"));
  assert.ok(src.indexOf("__agentsTabLoad = ") < src.indexOf("initSideTabs();"));
  assert.ok(src.includes("runState.runId"), "hook reads the selected run");
  const mod = readFileSync(new URL("../guided/agents.js", import.meta.url), "utf8");
  assert.ok(mod.includes("pipeline.list_agent_events"));
});

test("renderAgentsTab paints a current-status header from the live run state", () => {
  const mod = readFileSync(new URL("../guided/agents.js", import.meta.url), "utf8");
  assert.ok(mod.includes("currentRunStatus"), "header reads the live run status");
  assert.ok(mod.includes("현재") || mod.includes("current-status"), "header is painted");

  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const host = make();
  renderAgentsTab(host, { state: "done", events: EVENTS, runId: "run_x",
                          status: { stage: "af2_50", state: "running" } });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("af2_50"), "stage chip shows the running stage");
  assert.ok(html.includes("진행 중"), "running state renders as 진행 중");

  const failed = make();
  renderAgentsTab(failed, { state: "done", events: EVENTS, runId: "run_x",
                            status: { stage: "af2_50", state: "failed" } });
  assert.ok(JSON.stringify(failed.children).includes("실패"), "failed state renders as 실패");

  const cancelled = make();
  renderAgentsTab(cancelled, { state: "done", events: EVENTS, runId: "run_x",
                               status: { stage: "af2_50", state: "cancelled" } });
  assert.ok(JSON.stringify(cancelled.children).includes("취소됨"), "cancelled state renders as 취소됨");
});

test("rememberAgentEvents keeps the last successful read per run", () => {
  rememberAgentEvents("run_a", EVENTS);
  assert.deepEqual(currentAgentEvents("run_a"), EVENTS);
  // 다른 실행을 물으면 빈 목록 - 낡은 실행의 판정이 새 실행의 헤더에 그려지지 않게.
  assert.deepEqual(currentAgentEvents("run_b"), []);
});

test("the facade repaints the agents header from cached events on ticks", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes("currentAgentEvents"), "onTick repaint reads the cached events");
  assert.ok(src.includes("rememberAgentEvents"), "successful loads must remember the events");
  assert.ok(src.includes('dataset.sidetab === "agents"'),
            "repaint only while the agents tab is active");
});

test("agents header falls back to 상태 없음 when the run has no status yet", () => {
  // status 인자를 넘기지 않으면 monitor runState 의 live 값을 읽는다. 이 테스트
  // 프로세스는 상태를 조회한 적이 없으므로 null 이고, 칩은 상태 없음이어야 한다.
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderAgentsTab(host, { state: "empty", runId: "run_x" });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("상태 없음"), "missing status renders 상태 없음");
  assert.ok(html.includes("run_x"), "empty note still names the run");
});
