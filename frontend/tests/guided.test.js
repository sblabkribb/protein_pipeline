import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const source = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");

test("guided screen source parses as an ES module", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "kbf-guided-check-"));
  const tempFile = join(tempDir, "guided-check.mjs");
  writeFileSync(tempFile, source, "utf8");

  let output = "";
  try {
    execFileSync(process.execPath, ["--check", tempFile], {
      encoding: "utf8",
      stdio: "pipe",
    });
  } catch (error) {
    output = `${error.stdout || ""}${error.stderr || ""}`.trim();
  }
  assert.equal(output, "");
});

test("the screen never invents decisions or evidence text of its own", () => {
  // 근거 문구를 프런트에서 만들면 출처 추적이 깨진다. 서버가 준 것만 그려야 한다.
  assert.ok(!/rationale\s*=\s*["'`]/.test(source), "rationale must come from the server");
  assert.ok(!/statement\s*:\s*["'`]/.test(source), "evidence statements must come from the server");
});

test("plan and approve go through the documented MCP tools", () => {
  assert.ok(source.includes("pipeline.plan_from_objective"));
  assert.ok(source.includes("pipeline.approve_plan"));
  assert.ok(source.includes("/tools/call"), "must use the shared tools endpoint");
});

test("locked decisions are rendered as disabled inputs", () => {
  assert.ok(source.includes("input.disabled = !decision.editable"));
});

test("all three evidence kinds have a label and a style", () => {
  for (const kind of ["internal_measurement", "literature", "assumption"]) {
    assert.ok(source.includes(kind), `guided.js must handle ${kind}`);
  }
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  for (const kind of ["internal_measurement", "literature", "assumption"]) {
    assert.ok(css.includes(`.kind-${kind}`), `guided.css must style ${kind}`);
  }
});

test("warnings from the server are surfaced, not swallowed", () => {
  assert.ok(source.includes("plan.warnings"));
  assert.ok(html.includes('id="warnings"'));
});

test("approval does not run the pipeline", () => {
  assert.ok(!source.includes("pipeline.run"), "the review screen must not launch runs");
  assert.ok(html.includes("실행하지 않습니다"), "the page must say it does not run");
});

test("all three steps are visible before a plan exists", () => {
  // 카드를 hidden 으로 시작하면 로그인 전 사용자에게는 미구현으로 보인다.
  assert.ok(!/id="planCard"[^>]*hidden/.test(html));
  assert.ok(!/id="applyCard"[^>]*hidden/.test(html));
  assert.ok(html.includes("계획 검토"));
  assert.ok(html.includes("승인"));
});

test("approve stays disabled until a plan is generated", () => {
  assert.ok(/id="approveBtn"[^>]*disabled/.test(html), "approve must start disabled");
  assert.ok(source.includes('getElementById("approveBtn").disabled = !approvable'),
            "approve is enabled only after an approvable plan arrives");
});

test("a route the server cannot run is not approvable", () => {
  // 실행할 수 없는 경로에 승인 버튼을 열어두면 사용자는 무언가 시작됐다고 믿는다.
  assert.ok(source.includes("plan.approvable"), "must read the server's approvable flag");
});

test("stage costs come from the server, never hard-coded in the browser", () => {
  // 프런트에 숫자를 박아두면 실측이 갱신돼도 화면만 옛 값을 계속 보여준다.
  // 실제로 62 잔기 프로브에서 나온 "91s / fold" 가 59-274 잔기 백본 옆에 붙어 있었다.
  // 주석으로 남기는 것은 기록이고, 값으로 쓰는 것이 문제다. 후자만 막는다.
  const code = source.replace(/^\s*\/\/.*$/gm, "");
  assert.ok(!/91s/.test(code), "the 62-residue probe figure must not be a value in the code");
  assert.ok(!/cost:\s*["'`]/.test(code), "cost chips must not be string literals");
  assert.ok(!/const STAGES\s*=/.test(code), "the stage list must not be a browser constant");
  assert.ok(source.includes("pipeline.list_models"), "stages must come from the model registry");
  assert.ok(source.includes("cost_estimate"), "cost chips must come from the server estimate");
});

test("an unmeasured cost is shown as unmeasured, not as zero", () => {
  assert.ok(source.includes("미측정"), "unmeasured stages must be labelled");
  assert.ok(source.includes("unknown_stages"), "the total must exclude unmeasured stages");
  assert.ok(/하한/.test(source), "the total must say it is a lower bound");
});

test("runnable and validated are shown as separate facts", () => {
  // 돌아간다는 것과 측정했다는 것은 다르다. 한 칸에 합치면 구분이 사라진다.
  assert.ok(source.includes("stage.validated"), "must read the per-stage validated flag");
  assert.ok(source.includes("미검증"), "unvalidated stages must be badged");
  assert.ok(source.includes("model.runnable"), "the dot must reflect runnability");
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes(".warnchip"), "the unvalidated badge needs its own style");
});

test("the design purpose is selectable and decides the route", () => {
  assert.ok(html.includes('id="purpose"'), "the page needs a purpose selector");
  assert.ok(source.includes("purpose: document.getElementById"), "the plan request must carry it");
});

test("the evidence panel aggregates server-provided evidence only", () => {
  assert.ok(source.includes("renderEvidencePanel"));
  assert.ok(source.includes("decision.evidence"));
});

test("api base follows the shared resolver instead of an empty origin", () => {
  // 빈 apiBase 로 두면 /tools/call 이 원점으로 나가는데, 배포 환경의 프록시는
  // /api/* 만 백엔드로 보내므로 조용히 404 가 된다.
  assert.ok(source.includes("resolveDefaultApiBase"), "must reuse the shared resolver");
  assert.ok(!/return\s*"";/.test(source), "apiBase must not fall back to an empty string");
});

test("the LLM explanation is kept separate from evidence", () => {
  // 생성된 산문이 측정 근거처럼 보이면 출처 추적이 무의미해진다.
  assert.ok(source.includes("pipeline.explain_plan"));
  assert.ok(source.includes("explanation_is_generated"), "must show whether an LLM wrote it");
  assert.ok(html.includes('id="explainBox"'));
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes(".explain"), "explanation needs its own visual treatment");
  assert.ok(css.includes(".genbadge"), "generated text needs a badge");
});

test("questions come from the server, not composed in the browser", () => {
  assert.ok(source.includes("result.questions"));
  assert.ok(!/question\s*:\s*["'`]/.test(source), "questions must not be written client-side");
});

test("an unauthorized failure tells the user to log in", () => {
  assert.ok(source.includes("unauthorized"), "must detect the auth failure");
  assert.ok(html.includes('id="authHint"'));
  assert.ok(html.includes("로그인이 필요합니다"));
});

test("tool responses are unwrapped instead of handed over as the envelope", () => {
  // 서버는 {"ok": true, "result": {...}} 로 감싼다. 봉투를 그대로 쓰면
  // out.purposes 와 plan.decisions 가 undefined 가 되고, 200 응답이라
  // 오류도 없이 드롭다운과 계획 검토가 비어버린다.
  assert.ok(source.includes("unwrapToolResponse"), "must unwrap the response envelope");
  assert.ok(!/return payload;\s*\n}/.test(source), "must not return the raw envelope");
});
