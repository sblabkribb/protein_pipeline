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

const { templateCardModels, renderTemplatesTab } = await import("../guided/templates.js");

const PAYLOAD = {
  purposes: [
    { purpose: "monomer_solubility_redesign", display_name_ko: "단일체 용해도 리디자인",
      executable: true, validated: true, unvalidated_stages: [] },
    { purpose: "binder_design", display_name_ko: "바인더 설계",
      executable: true, validated: false, unvalidated_stages: ["af2"] },
    { purpose: "enzyme_design", display_name_ko: "효소 설계",
      executable: false, validated: false, unvalidated_stages: [] },
  ],
};

test("templateCardModels absorbs routes", () => {
  const models = templateCardModels(PAYLOAD);
  assert.equal(models[0].name, "단일체 용해도 리디자인");
  assert.equal(models[0].state, "validated");
  assert.equal(models[1].state, "unvalidated");
  assert.deepEqual(models[1].unvalidatedStages, ["af2"]);
  assert.equal(models[2].state, "blocked");
  assert.equal(templateCardModels({}).length, 0);
  assert.equal(templateCardModels(null).length, 0);
});

test("renderTemplatesTab paints cards with start buttons and states", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderTemplatesTab(host, { state: "done", model: templateCardModels(PAYLOAD) });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("시작 →"));
  assert.ok(html.includes("단일체 용해도 리디자인"));
  assert.ok(html.includes("okchip") && html.includes("warnchip") && html.includes("badchip"));
  assert.ok(html.includes("미검증 단계: af2"));
});

test("renderTemplatesTab paints loading and error states", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderTemplatesTab(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /불러오는 중/);
  const h1 = make(); renderTemplatesTab(h1, { state: "error", message: "실패" });
  assert.match(h1.children[0].textContent, /실패/);
  assert.ok(h1.children.some((c) => c.tagName === "BUTTON"));
  const h2 = make(); renderTemplatesTab(h2, { state: "done", model: [] });
  assert.match(h2.children[0].textContent, /없습니다/);
});

test("the shell hosts the templates tab and wires start-from-purpose", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('data-sidetab="templates"'));
  assert.ok(html.includes('id="sideTemplates"'));
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"templates"'), "SIDE_TAB_NAMES must include templates");
  assert.ok(src.includes("__templatesTabLoad"));
  assert.ok(src.indexOf("__templatesTabLoad = ") < src.indexOf("initSideTabs();"),
            "hook must be defined before tab restore");
  assert.ok(src.includes("function startFromPurpose"), "facade helper must exist");
  assert.ok(src.includes("__templatesStart"), "cards must trigger the facade start action");
  const mod = readFileSync(new URL("../guided/templates.js", import.meta.url), "utf8");
  assert.ok(mod.includes("head.appendChild(start)"), "start action must live in the card head row");
  assert.ok(!mod.includes("row.appendChild(start)"), "start action must not be a standalone card row");
});

test("template cards use the quiet cardlink action styled in guided.css", () => {
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes(".cardlink"), "guided.css must style .cardlink");
});
