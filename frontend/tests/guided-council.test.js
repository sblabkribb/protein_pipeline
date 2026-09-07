import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// renderCouncil 은 함수 안에서만 document 를 만진다 — import 시점엔 불필요.
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

const { councilCardModels, renderCouncil } = await import("../guided/council.js");

const COUNCIL = [
  { expert_id: "solubility", name: "용해도·응집 전문가", verdict: "warn", status: "ok",
    reasons: ["컷오프가 높다"], suggestions_count: 1 },
  { expert_id: "stability", name: "안정성 전문가", verdict: "", status: "unavailable",
    reasons: [], suggestions_count: 0, raw_excerpt: "timeout" },
];

test("councilCardModels maps verdicts to labels and chips", () => {
  const models = councilCardModels(COUNCIL);
  assert.equal(models[0].label, "경고");
  assert.equal(models[0].chipClass, "warnchip");
  assert.equal(models[1].label, "");
  assert.equal(models[1].chipClass, "");
  assert.equal(models[1].status, "unavailable");
});

test("councilCardModels tolerates missing fields", () => {
  const models = councilCardModels([null, {}, "x"]);
  assert.equal(models.length, 3);
  assert.equal(models[0].name, "");
});

test("renderCouncil pending shows the reviewing note", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(host, [], { pending: true });
  assert.match(host.children[0].textContent, /검토하는 중/);
});

test("renderCouncil paints a card per expert with chip and reasons", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(host, COUNCIL, { notes: [] });
  const cards = host.children.filter((c) => c.className === "skill");
  assert.equal(cards.length, 2);
  const chip = cards[0].children[0].children.find((c) => c.className === "warnchip");
  assert.equal(chip.textContent, "경고");
});

test("renderCouncil shows raw excerpt as details and notes when empty", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(host, COUNCIL, { notes: [] });
  assert.ok(host.children.some((c) => c.tagName === "DETAILS"));
  const empty = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(empty, [], { notes: ["LLM 연결 없음"] });
  assert.match(empty.children[0].textContent, /LLM 연결 없음/);
});

test("plan.js fires the council with a generation guard and merges proposals", () => {
  const src = readFileSync(new URL("../guided/plan.js", import.meta.url), "utf8");
  assert.ok(src.includes("fireCouncil(plan)"), "generatePlan must fire the council");
  assert.ok(src.includes("councilGen"), "council calls must be generation-guarded");
  assert.ok(src.includes("currentProposals()"), "proposals must merge council and chat edits");
});

test("guided.html hosts the council box", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('id="councilBox"'));
});
