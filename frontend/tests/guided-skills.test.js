import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.document ??= {
  createElement(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      className: "",
      textContent: "",
      value: "",
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  },
};

const { skillCardModels, renderSkillsTab } = await import("../guided/skills.js");

const SKILLS = [
  { expert_id: "solubility", name: "용해도·응집 전문가", source: "user",
    charter: "사용자 헌장", updated_utc: "2026-09-07" },
  { expert_id: "stability", name: "안정성 전문가", source: "builtin", charter: "빌트인 헌장" },
];

test("skillCardModels absorbs fields", () => {
  const models = skillCardModels(SKILLS);
  assert.equal(models[0].source, "user");
  assert.equal(models[0].updatedUtc, "2026-09-07");
  assert.equal(models[1].source, "builtin");
  assert.equal(models[1].updatedUtc, "");
  assert.equal(skillCardModels(null).length, 0);
  assert.equal(skillCardModels([null])[0].name, "");
});

test("renderSkillsTab paints cards with source chips and charter text", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderSkillsTab(host, { state: "done", skills: SKILLS });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("용해도·응집 전문가"));
  assert.ok(html.includes("사용자 헌장"));
  assert.ok(html.includes("사용자 편집"));
  assert.ok(html.includes("빌트인"));
  assert.ok(html.includes("2026-09-07"));
});

test("updated_utc renders as a kv row, not a chip", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderSkillsTab(host, { state: "done", skills: SKILLS });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes('"className":"kv"'), "updated_utc uses the kv grid");
  assert.ok(html.includes("마지막 수정"), "kv row is labeled 마지막 수정");
  // 출처 칩은 유지된다.
  assert.ok(html.includes("warnchip") && html.includes("chip"));
});

test("renderSkillsTab editing card renders a textarea with save and cancel", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderSkillsTab(host, { state: "done", skills: SKILLS, editingId: "stability" });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("TEXTAREA"), "textarea rendered for the editing card");
  assert.ok(html.includes("헌장 저장"));
  assert.ok(html.includes("취소"));
});

test("renderSkillsTab paints loading and error states", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderSkillsTab(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /불러오는 중/);
  const h1 = make(); renderSkillsTab(h1, { state: "error", message: "실패" });
  assert.match(h1.children[0].textContent, /실패/);
});

test("the shell hosts the skills tab with save and reset wiring", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('data-sidetab="skills"'));
  assert.ok(html.includes('id="sideSkills"'));
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"skills"'));
  assert.ok(src.includes("__skillsTabLoad"));
  assert.ok(src.indexOf("__skillsTabLoad = ") < src.indexOf("initSideTabs();"));
  const mod = readFileSync(new URL("../guided/skills.js", import.meta.url), "utf8");
  assert.ok(mod.includes("pipeline.save_council_skill"));
  assert.ok(mod.includes("pipeline.reset_council_skill"));
  assert.ok(mod.includes("pipeline.list_council_skills"));
});
