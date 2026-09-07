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
      disabled: false,
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  },
};

const intake = await import("../guided/intake.js");
const { intakeMsgModels, renderIntake } = intake;

const host = () => ({
  children: [],
  replaceChildren() { this.children = []; },
  appendChild(c) { this.children.push(c); },
});

function allText(node) {
  let out = String(node.textContent || "");
  for (const child of node.children || []) out += allText(child);
  return out;
}

test("intakeMsgModels absorbs junk and keeps both roles", () => {
  const models = intakeMsgModels([
    { role: "user", content: "용해도 좋은 걸로 40개" },
    { role: "assistant", content: "타겟 서열을 붙여넣어 주세요." },
    null,
    "not-an-object",
    { role: "user", content: "   " },
  ]);
  assert.equal(models.length, 2);
  assert.equal(models[0].role, "user");
  assert.equal(models[1].role, "assistant");
  assert.deepEqual(intakeMsgModels(), []);
});

test("renderIntake paints the idle card with input and hint", () => {
  const h = host();
  renderIntake(h, { state: "idle" });
  const text = allText(h);
  assert.match(text, /무엇을 만들고 싶으신가요/);
  assert.match(text, /계획 카드 검토·승인/);
  assert.match(text, /예: /);
  const input = h.children.flatMap((c) => c.children || []).find((c) => c.tagName === "INPUT");
  assert.ok(input, "idle card must have an input");
  assert.equal(input.disabled, false);
});

test("renderIntake paints busy, ready and unavailable states", () => {
  const busy = host(); renderIntake(busy, { state: "busy" });
  assert.match(allText(busy), /정리하는 중/);

  const ready = host();
  renderIntake(ready, { state: "ready", objectiveReady: true, messages: [
    { role: "user", content: "40개" }, { role: "assistant", content: "정리했습니다." },
  ] });
  const readyText = allText(ready);
  assert.match(readyText, /계획 카드로 옮겼습니다/);
  assert.match(readyText, /정리했습니다/);

  const off = host(); renderIntake(off, { state: "unavailable" });
  const offText = allText(off);
  assert.match(offText, /LLM 연결 없음/);
  const input = off.children.flatMap((c) => c.children || []).find((c) => c.tagName === "INPUT");
  assert.equal(input.disabled, true, "unavailable card disables the input");
});

test("renderIntake lists server-computed missing fields and dedupes reply", () => {
  const h = host();
  const messages = [
    { role: "user", content: "40개" },
    { role: "assistant", content: "타겟 서열을 주세요." },
  ];
  renderIntake(h, { state: "chat", messages, reply: "타겟 서열을 주세요.",
                    missing: ["타겟 서열/구조 — FASTA 나 PDB 를 붙여넣어 주세요."] });
  const text = allText(h);
  assert.match(text, /타겟 서열을 주세요/);
  // 같은 산문이 한 번만 그려진다.
  assert.equal(text.split("타겟 서열을 주세요").length - 1, 1);
  assert.match(text, /타겟 서열\/구조/);
});

test("requestIntake calls pipeline.intake_chat and throws on error", async () => {
  const src = readFileSync(new URL("../guided/intake.js", import.meta.url), "utf8");
  assert.ok(src.includes("pipeline.intake_chat"));
  assert.ok(src.includes("attached_fasta"));
});

test("the intake card sits above the objective section in guided.html", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('id="intakeSection"'));
  assert.ok(html.includes('id="intakeBox"'));
  assert.ok(html.indexOf('id="intakeSection"') < html.indexOf('id="objectiveSection"'));
});

test("the facade wires intake send/apply and applies ready objectives", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes("window.__intakeApply"));
  assert.ok(src.includes("window.__intakeSend"));
  assert.ok(src.includes("requestIntake"));
  assert.ok(src.includes("applyObjectiveForm"));
  assert.ok(src.includes("objective_ready"));
});

test("plan.js exposes the form-mutation owner", () => {
  const src = readFileSync(new URL("../guided/plan.js", import.meta.url), "utf8");
  assert.ok(src.includes("function applyObjectiveForm"));
  assert.match(src, /export \{[^}]*applyObjectiveForm/);
});
