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

test("the left rail carries templates, skills, models and connections", () => {
  for (const id of ["templates", "skills", "stages", "connections"]) {
    assert.ok(html.includes(`id="${id}"`), `left rail needs #${id}`);
  }
  assert.ok(/<h3>템플릿<\/h3>/.test(html));
  assert.ok(/<h3>스킬<\/h3>/.test(html));
  assert.ok(/<h3>연결<\/h3>/.test(html));
});

test("the right rail carries analysis and monitor beside evidence and policy", () => {
  for (const panel of ["analysis", "monitor", "evidence", "policy"]) {
    assert.ok(html.includes(`data-panel="${panel}"`), `right rail needs ${panel} tab`);
    assert.ok(html.includes(`id="panel-${panel}"`), `right rail needs ${panel} panel`);
  }
});

test("template cards show whether a route is executable and validated", () => {
  // 목적을 고르는 시점에 무엇이 돌고 무엇이 검증됐는지 보여야 한다.
  assert.ok(source.includes("renderTemplates"));
  assert.ok(source.includes("route.executable"));
  assert.ok(source.includes("route.validated"));
});

test("skills are derived from the route, not hard-coded", () => {
  assert.ok(source.includes("renderSkills"));
  assert.ok(source.includes("stage.requires_design_policy"),
            "a stage needing a design policy must surface as an unmet skill");
  assert.ok(!/const SKILLS\s*=/.test(source), "the skill list must not be a browser constant");
});

test("connections separate not-configured from unreachable", () => {
  assert.ok(source.includes("renderConnections"));
  assert.ok(source.includes("portal.configured"));
  assert.ok(source.includes("미설정"), "an unconfigured portal must say so, not look down");
});

test("the monitor probes liveness on demand rather than on every load", () => {
  // 페이지를 열 때마다 워커 16개를 두드리면 공유 서버에 부담이 된다.
  assert.ok(source.includes("check_liveness: true"));
  assert.ok(source.includes("probeBtn"));
  assert.ok(!/loadRegistry[\s\S]{0,400}check_liveness/.test(source),
            "liveness must not be probed during the initial load");
});

test("the monitor uses the pipeline's own run tools, not a summary of its own", () => {
  // 기존 RAPID 의 모니터가 쓰는 도구를 그대로 쓴다. 새로 요약을 만들면
  // 같은 사실이 두 곳에서 갈라진다.
  assert.ok(source.includes("pipeline.list_runs"));
  assert.ok(source.includes("pipeline.status"));
  assert.ok(html.includes('id="runSelect"'));
  assert.ok(html.includes('id="runStatus"'));
});

test("analysis lists a run's artifacts and reads them", () => {
  assert.ok(source.includes("pipeline.list_artifacts"));
  assert.ok(source.includes("pipeline.read_artifact"));
  assert.ok(html.includes('id="artifactList"'));
});

test("structure artifacts render in 3D with the same library the app uses", () => {
  assert.ok(html.includes("3Dmol"), "the page must load 3Dmol");
  assert.ok(source.includes("$3Dmol"), "structures must render, not just download");
  assert.ok(/cartoon/.test(source), "protein structures need a cartoon representation");
});

test("a non-structure artifact is shown as text rather than fed to the viewer", () => {
  assert.ok(source.includes("isStructureArtifact"));
});

test("a truncated artifact says it was truncated", () => {
  // read_artifact 는 max_bytes 로 자른다. 잘렸다고 말하지 않으면 사용자는
  // 파일이 그게 전부인 줄 안다.
  assert.ok(/truncated|잘렸/.test(source));
});

test("an empty run list is reported as empty, not as a failure", () => {
  assert.ok(/실행이 없습니다|no runs/i.test(source));
});

test("no server value is ever interpolated into innerHTML", () => {
  // 아티팩트 경로와 실행 상태는 서버에서 오고, 산출물 경로에는 사용자가 정한
  // 이름(run id, design id)이 섞인다. 템플릿 문자열로 innerHTML 을 만들면
  // 그 이름 안의 마크업이 실행된다. textContent 로만 넣는다.
  const offenders = source
    .split("\n")
    .map((line, index) => [index + 1, line])
    .filter(([, line]) => /innerHTML\s*=\s*[`'"].*\$\{/.test(line));
  assert.deepEqual(offenders, [], `interpolated innerHTML at lines ${offenders.map(([n]) => n)}`);
});

test("the artifact path goes through the text-only helper", () => {
  assert.ok(/el\("span", "apath", path\)/.test(source),
            "the path must be passed as text, never assembled into markup");
});

test("the text helper only ever sets textContent", () => {
  const helper = source.slice(source.indexOf("function el("), source.indexOf("function dot("));
  assert.ok(helper.includes("textContent"));
  assert.ok(!helper.includes("innerHTML"), "the helper must not have an escape hatch");
});

test("run status values are set as text", () => {
  assert.ok(source.includes("function el("), "a text-only element helper keeps this consistent");
});

test("the 3D viewer is loaded with subresource integrity", () => {
  // CDN 응답이 바뀌면 사용자 세션 안에서 임의 코드가 실행된다. 버전 고정만으로는
  // 막지 못한다 - 같은 URL 이 다른 바이트를 줄 수 있기 때문이다.
  const tag = html.match(/<script[^>]*3Dmol-min\.js[^>]*>/s);
  assert.ok(tag, "the page must load 3Dmol");
  assert.ok(/integrity="sha384-/.test(tag[0]), "3Dmol must be pinned by hash");
  assert.ok(/crossorigin="anonymous"/.test(tag[0]), "SRI needs CORS to be enforced");
  assert.ok(/3dmol@\d+\.\d+\.\d+\//.test(tag[0]), "the version must be exact, not a range");
});
