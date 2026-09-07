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

const { modelsTabModels, renderModels } = await import("../guided/models.js");

const PAYLOAD = {
  purposes: [
    { purpose: "monomer_solubility_redesign", executable: true, validated: true },
    { purpose: "binder_design", executable: true, validated: false },
    { purpose: "enzyme_design", executable: false, validated: false },
  ],
  models: {
    mpnn_soluble: { endpoint: "bop:proteinmpnn", display_name: "ProteinMPNN soluble" },
    thermomp_ddg: { endpoint: "http://x:18114", display_name: "ThermoMPNN ddG",
                    extra: { access: { portal_mcp: true } } },
  },
  measurable_objectives: ["solubility", "structural_preservation", "diversity"],
  runnable_but_unvalidated_objectives: ["stability", "developability"],
};

test("modelsTabModels classifies objectives into three states", () => {
  const model = modelsTabModels(PAYLOAD);
  const byKey = Object.fromEntries(model.objectives.map((o) => [o.key, o.state]));
  assert.equal(byKey.solubility, "measured");
  assert.equal(byKey.stability, "unvalidated");
  assert.equal(byKey.activity, "none");
  assert.ok(model.purposes[0].validated);
  assert.equal(model.models[1].portalOnly, true);
  assert.equal(model.models[0].portalOnly, false);
});

test("modelsTabModels absorbs missing fields", () => {
  const model = modelsTabModels({});
  assert.deepEqual(model.purposes, []);
  assert.deepEqual(model.objectives, []);
  assert.deepEqual(model.models, []);
});

test("renderModels paints purpose cards, objective chips and model rows", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderModels(host, { state: "done", model: modelsTabModels(PAYLOAD) });
  assert.ok(host.children.length >= 3, "three blocks");
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("monomer_solubility_redesign"));
  assert.ok(html.includes("okchip") && html.includes("warnchip"));
  assert.ok(html.includes("ThermoMPNN"));
});

test("renderModels paints loading and error with retry", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderModels(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /불러오는 중/);
  const h1 = make(); renderModels(h1, { state: "error", message: "실패" });
  assert.match(h1.children[0].textContent, /실패/);
  assert.ok(h1.children.some((c) => c.tagName === "BUTTON"), "retry button present");
});

test("the facade loads the models tab on first entry", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes("__modelsTabLoad"), "shell hook must be filled");
  assert.ok(src.includes('from "./guided/models.js"'));
});
