import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

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

const { agentEventModels, renderAgentsTab } = await import("../guided/agents.js");

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
  assert.ok(h3.children[0].textContent.length > 0);
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
