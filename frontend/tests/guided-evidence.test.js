import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  LOW_CONSERVATION_DEFAULT,
  LIABILITY_COLUMNS,
  buildLiabilityRows,
  liabilitySummary,
  liabilityArtifactPaths,
  renderLiabilityRowsTable,
  summarizeConservation,
} from "../guided/evidence.js";

// renderLiabilityRowsTable 은 진짜 DOM API(insertRow/insertCell)로 테이블을 만든다.
// node 에는 document 가 없으므로 테스트가 검증하는 최소 형태만 흉내낸다 -
// guided-results.test.js 가 localStorage 를 흉내내는 것과 같은 관행이다.
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

test("summarizeConservation sorts low positions by score with 1-indexed residue numbers", () => {
  // 파이프라인의 fixed_positions 도 잔기를 1-인덱스로 센다 (bio/a3m.py).
  const summary = summarizeConservation([0.9, 0.1, 0.5, 0.2], { lowThreshold: 0.3 });
  assert.deepEqual(summary.low, [
    { i: 2, score: 0.1 },
    { i: 4, score: 0.2 },
  ]);
  assert.equal(summary.count, 2);
  assert.equal(summary.median, 0.35);
});

test("summarizeConservation takes the even median and honours the threshold boundary", () => {
  const summary = summarizeConservation([0.3, 0.7], { lowThreshold: 0.3 });
  // 임계값은 미만이다 - 경계값(0.3)은 고정 후보로 남고 낮은 목록에 들지 않는다.
  assert.deepEqual(summary.low, []);
  assert.equal(summary.count, 0);
  assert.equal(summary.median, 0.5);
});

test("summarizeConservation on empty scores says there is nothing to show", () => {
  assert.deepEqual(summarizeConservation([]), { median: null, low: [], count: 0 });
});

test("summarizeConservation defaults the threshold to the module constant", () => {
  assert.equal(LOW_CONSERVATION_DEFAULT, 0.3);
  const summary = summarizeConservation([0.9, 0.2, 0.8, 0.1, 0.5]);
  assert.deepEqual(summary.low.map((p) => p.i), [4, 2]);
});

test("LIABILITIES_COLUMNS defines the render order", () => {
  // liabilities.json 의 계약 필드를 그대로 쓴다. ng_dg 만 게이트가 쓰는 합
  // (deamidation_NG + isomerisation_DG)으로 묶어 놓았다.
  assert.deepEqual([...LIABILITY_COLUMNS], [
    "seq_id", "passed", "net_charge", "max_hydrophobic_patch",
    "aggregation_prone_fraction", "ng_dg", "free_cysteine", "reasons",
  ]);
});

test("buildLiabilityRows normalizes the liabilities.json contract into flat rows", () => {
  // pipeline.py 가 tiers/<tier>/liabilities.json 에 쓰는 형태 그대로:
  // {summary, thresholds, sequences:[{id, ..., motifs, gate}]}
  const rows = buildLiabilityRows({
    summary: { evaluated: 2, failed: 1 },
    sequences: [
      {
        id: "d007",
        net_charge: 2,
        max_hydrophobic_patch: 5,
        aggregation_prone_fraction: 0.12,
        motifs: { deamidation_NG: 1, isomerisation_DG: 2, oxidation_MW: 0, free_cysteine: 0 },
        gate: { enabled: true, passed: false, reasons: ["developability: deamidation_NG+isomerisation_DG 3 > 2"] },
      },
      {
        id: "d003",
        net_charge: -1,
        max_hydrophobic_patch: 3,
        aggregation_prone_fraction: 0.05,
        motifs: { deamidation_NG: 0, isomerisation_DG: 0, oxidation_MW: 1, free_cysteine: 0 },
        gate: { enabled: true, passed: true, reasons: [] },
      },
    ],
  });
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0], {
    seq_id: "d007",
    passed: "fail",
    net_charge: 2,
    max_hydrophobic_patch: 5,
    aggregation_prone_fraction: 0.12,
    ng_dg: 3,
    free_cysteine: 0,
    reasons: "developability: deamidation_NG+isomerisation_DG 3 > 2",
  });
  assert.equal(rows[1].passed, "pass");
  assert.equal(rows[1].ng_dg, 0);
});

test("buildLiabilityRows marks a disabled gate as unavailable, not as a pass", () => {
  // gate.enabled 가 거짓이면 passed 는 null 이다. 그것을 "pass" 로 렌더링하면
  // 검사하지 않은 것을 통과한 것처럼 보인다.
  const rows = buildLiabilityRows({
    sequences: [{ id: "d001", motifs: {}, gate: { enabled: false, passed: null, reasons: [] } }],
  });
  assert.equal(rows[0].passed, "-");
});

test("buildLiabilityRows tolerates missing halves", () => {
  assert.deepEqual(buildLiabilityRows(null), []);
  assert.deepEqual(buildLiabilityRows({}), []);
  const rows = buildLiabilityRows({ sequences: [{ id: "d002", gate: {} }] });
  assert.equal(rows[0].seq_id, "d002");
  assert.equal(rows[0].passed, "-");
  assert.equal(rows[0].reasons, "");
});

test("liabilitySummary reads the tier summary and defaults to honest zeros", () => {
  assert.deepEqual(liabilitySummary({ summary: { evaluated: 4, failed: 1 } }),
    { evaluated: 4, failed: 1, enabled: false, calibrated: false, error: null });
  assert.deepEqual(liabilitySummary(null),
    { evaluated: 0, failed: 0, enabled: false, calibrated: false, error: null });
  // 게이트 계산 실패의 fallback 형태 (pipeline.py:9768). 이것을 enabled:false 로
  // 읽으면 "검사했는데 꺼져 있다"가 되어 거짓말이다 - 오류는 별도 필드로 노출한다.
  assert.deepEqual(
    liabilitySummary({
      summary: { gate_id: "sequence_liability_gate_v1", error: "liability gate failed: boom" },
    }),
    {
      evaluated: 0, failed: 0, enabled: false, calibrated: false,
      error: "liability gate failed: boom",
    },
  );
});

test("liabilityArtifactPaths finds tier liabilities; nesting stays forward-compatible", () => {
  // 백엔드는 오늘 루트 tiers/<티어>/liabilities.json 에만 쓴다 (pipeline.py:9742 -
  // bb_tier_dir 은 liabilities 를 받지 않는다). 정규식은 백엔드가 중첩 경로
  // (backbones/<이름>/tiers/...)를 쓰더라도 유지된다 - 현재 백엔드는 루트만 씀.
  const tiers = liabilityArtifactPaths([
    { type: "file", path: "tiers/50/liabilities.json" },
    { type: "file", path: "backbones/bb1/tiers/30/liabilities.json" },
    { type: "file", path: "wt/liabilities.json" },
    { type: "dir", path: "tiers/50" },
    { type: "file", path: "tiers/50/soluprot.json" },
  ]);
  assert.equal(tiers.get("50"), "tiers/50/liabilities.json");
  assert.equal(tiers.get("30"), "backbones/bb1/tiers/30/liabilities.json");
  assert.equal(tiers.size, 2);
});

test("renderLiabilityRowsTable pins the column order", () => {
  const table = renderLiabilityRowsTable([
    { seq_id: "d007", passed: "fail", net_charge: 2, max_hydrophobic_patch: 5,
      aggregation_prone_fraction: 0.12, ng_dg: 3, free_cysteine: 0, reasons: "r" },
  ]);
  assert.equal(table.tagName, "TABLE");
  // buildLiabilityRows 계약이 8열이다 - 열 수를 고정해 오탈자를 막는다.
  assert.equal(table.rows[0].cells.length, LIABILITY_COLUMNS.length);
  assert.equal(table.rows[0].cells[0].textContent, "seq_id");
  assert.equal(table.rows[1].cells[0].textContent, "d007");
  assert.equal(table.rows[1].cells[1].textContent, "fail");
  assert.equal(table.rows[1].cells[5].textContent, "3");
});

test("source contract: evidence reads the artifacts the pipeline writes, wired stale-guarded", () => {
  // 전용 조회 도구(get_conservation/get_liabilities)는 없다. 파이프라인이 쓴
  // 산출물 계약(conservation.json, tiers/*/liabilities.json)을 read_artifact 로
  // 읽는 것이 계약이다.
  const evidence = readFileSync(new URL("../guided/evidence.js", import.meta.url), "utf8");
  assert.ok(evidence.includes("pipeline.read_artifact"));
  assert.ok(evidence.includes('"conservation.json"'));
  assert.ok(evidence.includes("liabilities.json"));

  const facade = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  // Results 와 같은 자리에서, 같은 isStale 술어로 채운다.
  assert.ok(facade.includes("refreshEvidence(runId, { isStale"));
  assert.ok(facade.includes('getElementById("evidenceView")'));
  assert.ok(facade.includes("근거를 불러오지 못했습니다"));
});
