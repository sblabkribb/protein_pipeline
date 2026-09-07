import test from "node:test";
import assert from "node:assert/strict";
import { buildFunnelRow, summarizeCompare, HIT_COLUMNS, renderFunnelRowsTable } from "../guided/results.js";

// renderFunnelRowsTable 은 진짜 DOM API(insertRow/insertCell)로 테이블을 만든다.
// node 에는 document 가 없으므로 테스트가 검증하는 최소 형태만 흉내낸다 -
// chat-providers.test.js 가 localStorage 를 흉내내는 것과 같은 관행이다.
function stubNode(tag) {
  const upper = String(tag).toUpperCase();
  const node = {
    tagName: upper,
    className: "",
    textContent: "",
    title: "",
    style: {},
    children: [],
    rows: upper === "TABLE" ? [] : undefined,
    cells: upper === "TR" ? [] : undefined,
    appendChild(child) {
      node.children.push(child);
      if (node.rows) node.rows.push(child);
      if (node.cells) node.cells.push(child);
      return child;
    },
    append(...kids) { for (const kid of kids) node.appendChild(kid); },
    replaceChildren() { node.children.length = 0; },
    insertRow() { return node.appendChild(stubNode("tr")); },
    insertCell() { return node.appendChild(stubNode("td")); },
    classList: { add() {}, remove() {}, toggle() {} },
  };
  return node;
}
globalThis.document ??= { createElement: (tag) => stubNode(tag) };

test("buildFunnelRow counts designed -> soluprot -> af2 -> af2-selected", () => {
  const row = buildFunnelRow("50", {
    scores: { a: 0.8, b: 0.3, c: 0.9, d: 0.1 },
    passed_ids: ["a", "c"],
  }, {
    candidate_ids: ["a", "c", "e"],
    selected_ids: ["a"],
  });
  assert.deepEqual(row, { tier: "50", designed: 4, soluprot: 2, af2: 3, af2_selected: 1 });
});

test("buildFunnelRow tolerates missing halves", () => {
  const row = buildFunnelRow("30", null, { candidate_ids: ["x"], selected_ids: [] });
  assert.deepEqual(row, { tier: "30", designed: 0, soluprot: 0, af2: 1, af2_selected: 0 });
});

test("summarizeCompare flattens top-level scalars into cards and skips nested summary", () => {
  const cards = summarizeCompare({ run_id: "r1", baseline_run_id: "r0", notes: "x",
    summary: { soluprot_pass_rate: 0.7, plddt_median: 88 } });
  const labels = cards.map((c) => c.label);
  assert.ok(labels.includes("run_id"));
  assert.ok(labels.includes("summary.soluprot_pass_rate"));
  assert.ok(labels.includes("summary.plddt_median"));
  assert.ok(!labels.some((l) => l === "summary"));
  assert.ok(!labels.includes("notes"));
});

test("HIT_COLUMNS defines the render order", () => {
  assert.deepEqual([...HIT_COLUMNS], ["id", "score", "soluprot", "plddt", "rmsd", "novelty"]);
});

test("renderFunnelRowsTable builds one row per tier with the tier column first", () => {
  const table = renderFunnelRowsTable([
    { tier: "30", designed: 10, soluprot: 6, af2: 4, af2_selected: 2 },
    { tier: "50", designed: 12, soluprot: 5, af2: 3, af2_selected: 1 },
  ]);
  assert.equal(table.tagName, "TABLE");
  // buildFunnelRow 계약이 티어 포함 5열이다 - 열 수를 고정해 오탈자를 막는다.
  assert.equal(table.rows[0].cells.length, 5);
  assert.equal(table.rows[1].cells.length, 5);
  assert.equal(table.rows[0].cells[0].textContent, "tier");
  assert.equal(table.rows[1].cells[0].textContent, "30");
  assert.equal(table.rows[2].cells[4].textContent, "1");
});
