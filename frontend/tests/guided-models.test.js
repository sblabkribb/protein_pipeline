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

// objective_status 없는 구 페이로드 - 폴백 경로와 모델 평탄화를 검증한다.
const PAYLOAD = {
  purposes: [
    { purpose: "monomer_solubility_redesign", executable: true, validated: true },
    { purpose: "binder_design", executable: true, validated: false },
    { purpose: "enzyme_design", executable: false, validated: false },
  ],
  models: {
    mpnn_soluble: { endpoint: "bop:proteinmpnn", display_name: "ProteinMPNN soluble" },
    thermomp_ddg: { endpoint: "http://x:18114", display_name: "ThermoMPNN ddG",
                    access: { portal_mcp: true } },
    binder_ab: { endpoint: "http://y:18114", display_name: "BinderAB",
                 access: { portal_mcp: true, direct_client: true } },
  },
  measurable_objectives: ["solubility", "structural_preservation", "diversity"],
  runnable_but_unvalidated_objectives: ["stability", "developability"],
};

// 레지스트리 objective_status 가 내려오는 페이로드. evaluators 에 파이썬 repr
// 문자열을 일부러 섞어 낡은 직렬화도 흡수하는지 본다.
const STATUS_PAYLOAD = {
  purposes: [
    { purpose: "monomer_solubility_redesign", executable: true, validated: true,
      stages: [
        { stage: "msa", model_id: "mmseqs2", validated: true },
        { stage: "soluprot", model_id: "soluprot", validated: false },
      ] },
  ],
  models: {},
  objective_status: {
    solubility: { status: "measured", evaluators: ["soluprot"],
                  detail: "SoluProt 이 게이트 1 에서 돈다." },
    binding: { status: "evaluator_unvalidated", evaluators: "['ppiformer_ddg', 'diffdock']",
               detail: "결합 라벨에 맞춰본 적 없다.",
               to_enable: "결합 라벨 코호트에서 두 지표를 맞춰본다." },
    aggregation: { status: "needs_experimental_labels", evaluators: [],
                   detail: "응집 라벨이 필요하다." },
    developability: { status: "evaluator_not_wired", evaluators: "", detail: "" },
    activity: { status: "no_evaluator_available" },
  },
};

test("objective_status drives the five honest states", () => {
  const model = modelsTabModels(STATUS_PAYLOAD);
  const byKey = Object.fromEntries(model.objectives.map((o) => [o.key, o]));
  assert.equal(byKey.solubility.status, "measured");
  assert.equal(byKey.solubility.cls, "okchip");
  assert.equal(byKey.solubility.label, "측정됨");
  assert.deepEqual(byKey.solubility.evaluators, ["soluprot"]);
  assert.equal(byKey.binding.status, "evaluator_unvalidated");
  assert.equal(byKey.binding.cls, "warnchip");
  assert.equal(byKey.binding.label, "평가자 있음 · 미검증");
  // 파이썬 repr 문자열("['ppiformer_ddg', 'diffdock']")에서 이름을 복원한다.
  assert.deepEqual(byKey.binding.evaluators, ["ppiformer_ddg", "diffdock"]);
  assert.equal(byKey.binding.toEnable, "결합 라벨 코호트에서 두 지표를 맞춰본다.");
  assert.equal(byKey.aggregation.cls, "chip");
  assert.equal(byKey.aggregation.label, "실험 라벨 필요");
  assert.equal(byKey.developability.cls, "warnchip");
  assert.equal(byKey.developability.label, "구현 있음 · 미배선");
  assert.equal(byKey.activity.cls, "chip");
  assert.equal(byKey.activity.label, "평가자 없음");
  assert.deepEqual(byKey.activity.evaluators, []);
});

test("renderModels paints detail, to_enable and evaluator chips", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderModels(host, { state: "done", model: modelsTabModels(STATUS_PAYLOAD) });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("측정됨") && html.includes("평가자 있음 · 미검증"));
  assert.ok(html.includes("SoluProt 이 게이트 1 에서 돈다."), "detail renders as a note");
  assert.ok(html.includes("활성화하려면: 결합 라벨 코호트에서 두 지표를 맞춰본다."),
            "to_enable renders as an activation note");
  assert.ok(html.includes("ppiformer_ddg") && html.includes("diffdock"),
            "evaluators render as chips");
  assert.ok(html.includes("soluprot"));
});

test("fallback without objective_status keeps the measured/unvalidated split", () => {
  const model = modelsTabModels(PAYLOAD);
  const byKey = Object.fromEntries(model.objectives.map((o) => [o.key, o.state]));
  assert.equal(byKey.solubility, "measured");
  assert.equal(byKey.stability, "unvalidated");
  // 어휘 미러는 없다 - 응답이 말한 목표만 보인다. 말하지 않은 목표를 지어내면
  // 화면이 레지스트리와 갈라진다.
  assert.ok(!("activity" in byKey), "no vocabulary mirror");
  // 접근 정보는 평탄화된 item.access 로 온다 (ModelEntry.to_dict). 포털 전용만
  // 포털 칩이 붙고, direct_client 도 열려 있으면 칩이 없다.
  assert.equal(model.models[1].portalOnly, true);
  assert.equal(model.models[2].portalOnly, false);
  assert.equal(model.models[0].portalOnly, false);
  assert.ok(model.purposes[0].validated);
});

test("modelsTabModels absorbs missing fields", () => {
  const model = modelsTabModels({});
  assert.deepEqual(model.purposes, []);
  assert.deepEqual(model.objectives, []);
  assert.deepEqual(model.models, []);
});

test("purpose stages are capped at eight and tolerant of junk", () => {
  const many = {
    purposes: [{
      purpose: "long_path",
      stages: Array.from({ length: 12 }, (_, i) => (
        { stage: `s${i}`, model_id: `m${i}`, validated: i % 2 === 0 })),
    }],
  };
  const stages = modelsTabModels(many).purposes[0].stages;
  assert.equal(stages.length, 8);
  assert.equal(stages[0].modelId, "m0");
  assert.equal(stages[0].validated, true);
  assert.equal(stages[1].validated, false);
  assert.deepEqual(modelsTabModels({ purposes: [{ stages: "junk" }] }).purposes[0].stages, []);
  assert.deepEqual(modelsTabModels({ purposes: [{ stages: [null, 3] }] }).purposes[0].stages, []);
});

test("renderModels paints the stages line with warn dots on unvalidated stages", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderModels(host, { state: "done", model: modelsTabModels(STATUS_PAYLOAD) });
  const html = JSON.stringify(host.children);
  // 칩에는 스테이지 이름만, 모델 id 는 title 로 - 긴 칩이 좁은 레일을 밀지 않게.
  assert.ok(html.includes('"textContent":"msa"') && html.includes('"title":"mmseqs2"'),
            "stage chips show the stage name and carry the model id as title");
  assert.ok(html.includes('"title":"soluprot"'));
  assert.ok(html.includes("sdot-warn"), "unvalidated stages carry a warn dot");
});

test("purpose rows prefer the Korean display name and keep the raw key as a chip", () => {
  const model = modelsTabModels({ purposes: [
    { purpose: "monomer_solubility_redesign", display_name_ko: "단일체 용해도 리디자인",
      executable: true, validated: true },
    { purpose: "binder_design", executable: true, validated: false },
  ] });
  assert.equal(model.purposes[0].name, "단일체 용해도 리디자인");
  assert.equal(model.purposes[0].key, "monomer_solubility_redesign");
  // display_name_ko 가 없으면 영어 키가 이름 대신 쓰인다 - 칩은 겹치지 않게.
  assert.equal(model.purposes[1].name, "binder_design");
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderModels(host, { state: "done", model });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("단일체 용해도 리디자인"));
  assert.equal(html.split("monomer_solubility_redesign").length - 1, 1,
               "the raw key appears once as a chip, not as the card name");
  assert.equal(html.split("binder_design").length - 1, 1,
               "key === name rows do not repeat the key as a chip");
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
  assert.ok(src.indexOf("__modelsTabLoad = ") < src.indexOf("initSideTabs();"),
            "the hook must exist before init restores the last tab");
  assert.ok(src.includes('from "./guided/models.js"'));
});

test("side tab cards stack vertically so narrow rails do not overlap text", () => {
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes(".modelstab .skill { display: block"), "cards must not be flex rows");
});

test("modelsTabModels carries measured coverage so 'validated' cannot read as 'works'", () => {
  const out = modelsTabModels({
      purposes: [
        {
          key: "conformational_ensemble_redesign",
          name: "구조 앙상블 기반 재설계",
          executable: true,
          validated: true,
          stages: [],
          validation_coverage: {
            stage: "backbone_generate",
            targets_attempted: 62,
            targets_with_output: 4,
            fraction: 0.06,
            note: "BioEmu produced backbones for 4 of 62 targets.",
          },
        },
        {
          key: "de_novo_backbone_design",
          name: "신규 백본 설계",
          executable: true,
          validated: true,
          stages: [],
          validation_coverage: {
            stage: "backbone_generate",
            targets_attempted: 62,
            targets_with_output: 16,
            fraction: 0.26,
            improved: { targets_attempted: 18, targets_with_output: 13, fraction: 0.72 },
          },
        },
        { key: "protein_binder_design", name: "바인더", executable: true, validated: false, stages: [] },
      ],
      objectives: [],
  });

  const bioemu = out.purposes[0];
  assert.equal(bioemu.validated, true);
  assert.equal(bioemu.coverage.attempted, 62);
  assert.equal(bioemu.coverage.withOutput, 4);
  assert.ok(bioemu.coverage.fraction < 0.3, "6% must stay below the warn threshold");

  const rfd3 = out.purposes[1];
  assert.equal(rfd3.coverage.improvedWithOutput, 13);
  assert.equal(rfd3.coverage.improvedAttempted, 18);

  // 커버리지가 없는 목적은 null 이어야 하고, 0/0 으로 꾸며내면 안 된다.
  assert.equal(out.purposes[2].coverage, null);
});
