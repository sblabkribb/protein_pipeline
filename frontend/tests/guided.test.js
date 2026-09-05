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
  assert.ok(html.includes("실행은 아직 하지 않습니다"));
});

test("api base follows the shared resolver instead of an empty origin", () => {
  // 빈 apiBase 로 두면 /tools/call 이 원점으로 나가는데, 배포 환경의 프록시는
  // /api/* 만 백엔드로 보내므로 조용히 404 가 된다.
  assert.ok(source.includes("resolveDefaultApiBase"), "must reuse the shared resolver");
  assert.ok(!/return\s*"";/.test(source), "apiBase must not fall back to an empty string");
});
