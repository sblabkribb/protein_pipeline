import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { chipLabel, topbarChipModels } from "../guided.js";

const source = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");

// --- 순수 매퍼 --------------------------------------------------------------

test("chipLabel maps the pipeline states to Korean labels and state classes", () => {
  assert.deepEqual(chipLabel("running"), { label: "실행 중", cls: "" });
  assert.deepEqual(chipLabel("done"), { label: "완료", cls: "okchip" });
  assert.deepEqual(chipLabel("failed"), { label: "실패", cls: "badchip" });
  assert.deepEqual(chipLabel("cancelled"), { label: "취소됨", cls: "" });
  assert.deepEqual(chipLabel("stalled"), { label: "폴링 중단", cls: "warnchip" });
});

test("chipLabel tolerates unknown, oddly-cased and empty states", () => {
  // 모르는 상태는 서버가 준 값 그대로 보인다 - 프런트가 해석을 덧붙이면
  // Run 탭과 말이 갈라진다.
  assert.deepEqual(chipLabel("queued"), { label: "queued", cls: "" });
  assert.deepEqual(chipLabel("DONE"), { label: "완료", cls: "okchip" });
  assert.deepEqual(chipLabel(" done "), { label: "완료", cls: "okchip" });
  assert.deepEqual(chipLabel(""), { label: "-", cls: "" });
  assert.deepEqual(chipLabel(null), { label: "-", cls: "" });
});

test("topbarChipModels builds run, stage, state and session chips in order", () => {
  const models = topbarChipModels({
    runId: "run_9", state: "done", stage: "af2_50", user: "kim", signedIn: true,
  });
  assert.deepEqual(models.map((m) => m.text), ["run_9", "af2", "완료", "세션 · kim"]);
  assert.deepEqual(models.map((m) => m.cls), ["", "", "okchip", ""]);
});

test("the stage chip reuses the monitor's stage-to-step mapping", () => {
  const models = topbarChipModels({ runId: "r", state: "running", stage: "proteinmpnn_50" });
  assert.equal(models[1].text, "design");
});

test("the stage chip only appears when the server reported a stage", () => {
  const withStage = topbarChipModels({ runId: "r", state: "running", stage: "rfd3" });
  assert.deepEqual(withStage.map((m) => m.text), ["r", "backbone", "실행 중", "로그아웃됨"]);
  const withoutStage = topbarChipModels({ runId: "r", state: "running" });
  assert.deepEqual(withoutStage.map((m) => m.text), ["r", "실행 중", "로그아웃됨"]);
});

test("topbarChipModels tolerates a missing run and a name-less session", () => {
  assert.equal(topbarChipModels({ state: "running" })[0].text, "-");
  assert.equal(topbarChipModels({ signedIn: true }).at(-1).text, "세션 있음");
  assert.equal(topbarChipModels({ signedIn: false, user: "kim" }).at(-1).text, "로그아웃됨");
});

// --- 배선 계약 --------------------------------------------------------------

test("the topbar keeps its live-region chip host", () => {
  assert.match(html, /id="topbarChips"[^>]*aria-live="polite"/);
});

test("the run chip is painted synchronously on run selection, before the first await", () => {
  const fn = source.slice(source.indexOf("async function selectRun("),
                          source.indexOf("async function refreshResults("));
  assert.match(fn, /updateTopbarChips\(\{ runId \}\)/);
  assert.ok(fn.indexOf("updateTopbarChips") < fn.indexOf("await loadRunStatus"),
            "the chip must not wait for the status fetch");
});

test("the polling tick feeds the same status to the chips, behind the existing generation guard", () => {
  const tick = source.slice(source.indexOf("onTick: (info) => {"),
                            source.indexOf('if (info.state === "done"'));
  assert.match(tick, /updateTopbarChips\(/);
  assert.match(tick, /gen !== selectGen/, "onTick must stay behind the staleness guard");
  assert.match(tick, /poll_stalled/, "a stalled poll must say so instead of the last state");
});

test("updateTopbarChips does not guard staleness twice", () => {
  const fn = source.slice(source.indexOf("function updateTopbarChips("),
                          source.indexOf("--- 타겟 파일"));
  assert.ok(!fn.includes("selectGen"),
            "staleness belongs to the caller's generation guard");
});

test("a successful cancel updates the chip immediately", () => {
  const handler = source.slice(source.indexOf('"cancelRunBtn"'),
                               source.indexOf('"reportGenBtn"'));
  assert.match(handler, /updateTopbarChips\(\{ runId, state: "cancelled" \}\)/);
});

test("the session chip reuses the session helpers the facade already uses", () => {
  const fn = source.slice(source.indexOf("function updateTopbarChips("),
                          source.indexOf("--- 타겟 파일"));
  assert.match(fn, /shouldRestoreStoredSession/, "lib/auth.js session restore");
  assert.match(fn, /storedUserName/, "guided/api.js stored user");
});

test("chips are painted as text into the topbar host", () => {
  const paint = source.slice(source.indexOf("function paintTopbarChips("),
                             source.indexOf("function updateTopbarChips("));
  assert.match(paint, /getElementById\("topbarChips"\)/);
  assert.match(paint, /textContent/);
  assert.ok(!paint.includes("innerHTML"), "server-sourced chip text stays text-only");
});

// --- 스타일 계약 -----------------------------------------------------------

test("chip state classes have their evidence-strength styles", () => {
  assert.match(css, /\.okchip\b/);
  assert.match(css, /\.badchip\b/);
  assert.match(css, /\.warnchip\b/);
});

test("no cost chip in the topbar - costs keep their provenance in the plan card", () => {
  // 스펙의 provenance 규칙: 비용은 출처(측정 범위)가 붙는 값이라 계획 카드의
  // cost bar 에서만 보여준다.
  const code = source
    .slice(source.indexOf("--- 상단바 칩"), source.indexOf("--- 타겟 파일"))
    .replace(/^\s*\/\/.*$/gm, "");
  assert.ok(!/cost|비용/.test(code), "the topbar must not render cost values");
});
