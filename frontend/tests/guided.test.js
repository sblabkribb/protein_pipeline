import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const sources = [
  new URL("../guided.js", import.meta.url),
  ...[
    "api.js", "plan.js", "monitor.js", "sidebar.js", "results.js",
    "evidence.js", "structure.js",
  ].map((name) => new URL(`../guided/${name}`, import.meta.url)),
];
const present = sources.filter((url) => existsSync(url));
const source = present.map((url) => readFileSync(url, "utf8")).join("\n");
const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");

for (const name of ["api.js", "plan.js", "monitor.js"]) {
  assert.ok(present.some((u) => u.href.endsWith(`/${name}`)), `${name} must exist and be concatenated`);
}

test("guided sources parse as ES modules", () => {
  for (const url of present) {
    const tempDir = mkdtempSync(join(tmpdir(), "kbf-guided-check-"));
    const tempFile = join(tempDir, "check.mjs");
    writeFileSync(tempFile, readFileSync(url, "utf8"), "utf8");
    let output = "";
    try {
      execFileSync(process.execPath, ["--check", tempFile], { encoding: "utf8", stdio: "pipe" });
    } catch (error) {
      output = `${error.stdout || ""}${error.stderr || ""}`.trim();
    }
    assert.equal(output, "", `${url.pathname} must parse`);
  }
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

test("approving and running are separate, deliberate actions", () => {
  // 이 화면만으로 쓸 수 있어야 하므로 실행도 여기서 한다. 다만 승인 버튼이
  // 실행하지는 않는다 - 실행은 별도 버튼이고, 시작 전에 확인을 받는다.
  const approveFn = source.slice(source.indexOf("async function approve("),
                                 source.indexOf("function boot("));
  assert.ok(!approveFn.includes("pipeline.run"), "approve must not launch by itself");
  assert.ok(/window\.confirm/.test(source), "starting a run needs confirmation");
  assert.ok(/runBtn"\)\.disabled = false/.test(source), "run unlocks only after approval");
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
  assert.ok(source.includes("est.breakdown"),
            "the unmeasured count must come from the same breakdown the bar draws");
  assert.ok(/미측정이라 하한값/.test(source), "the total must say it is a lower bound");
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

test("evidence comes from the server and sits with its decision", () => {
  // 별도 근거 패널은 같은 목록을 두 번 그려서 없앴다. 근거가 서버에서 온다는
  // 계약은 그대로다.
  assert.ok(source.includes("decision.evidence"));
  assert.ok(source.includes("evidenceNode"));
});

test("api base follows the shared resolver instead of an empty origin", () => {
  // 빈 apiBase 로 두면 /tools/call 이 원점으로 나가는데, 배포 환경의 프록시는
  // /api/* 만 백엔드로 보내므로 조용히 404 가 된다.
  assert.ok(source.includes("resolveDefaultApiBase"), "must reuse the shared resolver");
  const fn = source.slice(source.indexOf("function apiBase("),
                          source.indexOf("function setSignedIn("));
  assert.ok(!/return\s*"";/.test(fn), "apiBase must not fall back to an empty string");
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

test("an unauthorized failure returns the user to the login gate", () => {
  assert.ok(source.includes("unauthorized"), "must detect the auth failure");
  assert.ok(html.includes('id="authHint"'));
  assert.ok(/setSignedOut\("세션이 만료/.test(source), "a 401 must return to the gate");
});

test("tool responses are unwrapped instead of handed over as the envelope", () => {
  // 서버는 {"ok": true, "result": {...}} 로 감싼다. 봉투를 그대로 쓰면
  // out.purposes 와 plan.decisions 가 undefined 가 되고, 200 응답이라
  // 오류도 없이 드롭다운과 계획 검토가 비어버린다.
  assert.ok(source.includes("unwrapToolResponse"), "must unwrap the response envelope");
  assert.ok(!/return payload;\s*\n}/.test(source), "must not return the raw envelope");
});

test("each fact is rendered in exactly one place", () => {
  // 예전에는 근거가 결정 안과 우측 패널에 두 번, 경로 상태가 카드·안내문·단계
  // 목록·경고까지 네 곳에 나왔다. 같은 사실이 여러 곳에 있으면 어긋났을 때
  // 어느 쪽이 맞는지 판단할 근거가 없다.
  assert.ok(!source.includes("renderEvidencePanel"),
            "evidence belongs inside its decision, once");
  assert.ok(!source.includes("renderSkills"),
            "skills duplicated the stage list; both came from route.stages");
  assert.equal((source.match(/blocked_reason/g) || []).length, 1,
               "the blocked reason belongs on the template card badge only");
});

test("the layout is three rails: intent, plan, results", () => {
  // runSelect 는 B안 단일화면에서 실행 사이드바(다음 작업)로 이동했다.
  for (const id of ["templates", "weights", "stages", "decisions",
                    "artifactList", "connections"]) {
    assert.ok(html.includes(`id="${id}"`), `layout needs #${id}`);
  }
  assert.ok(html.includes('data-panel='), "results are grouped into tabs so the rail stays short");
});

test("the plan reads as a numbered sequence because the flow is gated", () => {
  // 번호는 장식이 아니다. 생성 전에 검토할 수 없고 검토 전에 승인할 수 없다.
  const sections = [...html.matchAll(/<section class="plan-section[^"]*" id="(objectiveSection|planSection)"/g)];
  assert.deepEqual(sections.map((m) => m[1]), ["objectiveSection", "planSection"]);
});

test("template cards show whether a route is executable and validated", () => {
  // 목적을 고르는 시점에 무엇이 돌고 무엇이 검증됐는지 보여야 한다.
  assert.ok(source.includes("renderTemplates"));
  assert.ok(source.includes("route.executable"));
  assert.ok(source.includes("route.validated"));
});

test("the screen shares the product's design tokens instead of its own palette", () => {
  // 이 화면은 어두운 GitHub 팔레트 복제였다. 같은 제품인데 다른 물건처럼 보였다.
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes("Instrument Sans"), "must use the product's typeface");
  assert.ok(css.includes("oklch("), "must use the product's colour space");
  assert.ok(!/#0d1117|#131a24|#3b82f6/.test(css), "the GitHub-clone palette must be gone");
});

test("colour carries evidence strength and nothing else", () => {
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  for (const token of ["--measured", "--assumed", "--absent"]) {
    assert.ok(css.includes(token), `the evidence scale needs ${token}`);
  }
});

test("numbers line up for comparison", () => {
  // CI 와 비용을 눈으로 대조하는 화면이다.
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes("tabular-nums"));
});

test("keyboard focus stays visible", () => {
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes(":focus-visible"));
  assert.ok(!/outline:\s*none/.test(css), "focus must never be removed without a replacement");
});

test("every input has a label and reduced motion is respected", () => {
  // 가이드라인은 <label> 또는 aria-label 을 요구한다. purpose 는 카드가 조작하는
  // 숨은 셀렉트라 aria-label 쪽이 맞다.
  for (const id of ["rmsdMax", "nDesigns", "lengthAa", "af2Budget", "compareBaseline"]) {
    assert.ok(new RegExp(`for="${id}"`).test(html), `#${id} needs a label`);
  }
  assert.ok(/id="purpose"[^>]*aria-label=/.test(html), "#purpose needs an accessible name");
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes("prefers-reduced-motion"));
});

test("async regions announce themselves", () => {
  assert.ok((html.match(/aria-live="polite"/g) || []).length >= 2);
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
  // pipeline.list_runs 단언은 실행 목록 로더가 돌아오면(loadRuns 교체 작업) 다시 넣는다.
  // runSelect 단언은 실행 사이드바 작업에서 다시 넣는다.
  assert.ok(source.includes("pipeline.status"));
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

// "실행이 없습니다" 단언은 loadRuns 교체 작업에서 실행 목록 로더와 함께 돌아온다.

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

test("the artifact name goes through the text-only helper", () => {
  assert.ok(/el\("span", "apath", name\)/.test(source),
            "the name must be passed as text, never assembled into markup");
  assert.ok(/row\.title = path/.test(source), "the full path belongs in the tooltip");
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

test("badge text clears WCAG AA against the light canvas", () => {
  // 본체의 amber 는 흰 배경에서 3.06:1, coral 은 3.46:1 이라 작은 글자에 못 쓴다.
  // 테두리용과 글자용을 나누고, 글자용은 계산해서 4.5 를 넘긴 값이다.
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  for (const token of ["--measured-ink", "--assumed-ink", "--absent-ink"]) {
    assert.ok(css.includes(token), `text needs ${token}`);
  }
  for (const rule of [".mark-warn", ".mark-bad", ".kind-assumption"]) {
    const block = css.slice(css.indexOf(rule), css.indexOf(rule) + 200);
    assert.ok(/color: var\(--[a-z]+-ink\)/.test(block), `${rule} must use the text-safe token`);
  }
});

test("the steps are not four identical cards", () => {
  // 같은 모서리·같은 테두리의 카드 묶음은 내용의 위계를 지운다.
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  const step = css.slice(css.indexOf("\n.step {"), css.indexOf("\n.step {") + 160);
  assert.ok(!/border-radius/.test(step) && !/border: 1px/.test(step),
            "steps should read as a sequence, not as a card kit");
});

test("directories are not offered as readable artifacts", () => {
  // list_artifacts 는 파일과 디렉터리를 함께 돌려준다 (type 필드). msa 와 tiers 는
  // 디렉터리이고, 그것을 read_artifact 에 넘기면 실패한다 - 사용자가 본
  // "msa, tiers 를 못 불러온다" 가 이것이다.
  assert.ok(source.includes('item.type'), "the artifact type must be inspected");
  assert.ok(/directory|dir\b/.test(source), "directories need their own handling");
});

test("run status is read from the nested status object", () => {
  // pipeline.status 는 {run_id, found, status:{stage,state,updated_at}} 를 돌려준다.
  // 최상위에서 읽으면 모든 값이 "-" 로 나온다.
  assert.ok(/out\.status\b/.test(source), "the fields live under .status");
  assert.ok(source.includes("found"), "a missing run must be told apart from an empty one");
});

test("artifacts are listed as deep as the main app lists them", () => {
  // 서버 기본값은 max_depth 4 이고 app.js 는 6 을 쓴다. 기본값에 기대면 깊은
  // 산출물이 조용히 빠진다.
  assert.ok(/max_depth:\s*6/.test(source));
});

test("the plan stays review-gated without wizard chrome", () => {
  // 마법사 단계 버튼은 사라졌지만 plan.js 가 showStep 을 부르므로 함수는 남는다.
  assert.ok(source.includes("showStep"));
  assert.ok(!/querySelectorAll\("\.step"\)/.test(source),
            "the wizard .step wiring must be gone with the chrome");
});

test("the results rail is tabbed rather than stacked", () => {
  for (const panel of ["run", "results", "structure", "evidence"]) {
    assert.ok(html.includes(`data-panel="${panel}"`), `right rail needs the ${panel} tab`);
  }
});

test("the screen can log in on its own", () => {
  // "기존 화면에서 로그인하고 오세요" 는 이 화면만으로 쓸 수 없다는 뜻이었다.
  assert.ok(html.includes('id="loginGate"'), "a login gate must exist here");
  assert.ok(html.includes('id="loginUser"') && html.includes('id="loginPass"'));
  assert.ok(source.includes("/auth/login"), "must call the same login endpoint as the app");
  assert.ok(source.includes('"kbf.token"'), "must store the token the app also reads");
});

test("logging out is possible without leaving the screen", () => {
  assert.ok(html.includes('id="logoutBtn"'));
  assert.ok(/removeItem\("kbf\.token"\)/.test(source));
});

test("a target sequence can be entered, because a run needs one", () => {
  // pipeline.run 은 target_fasta 를 받는다. 입력이 없으면 이 화면은 계획만
  // 만들고 아무것도 실행할 수 없다.
  assert.ok(html.includes('id="targetFasta"'));
  assert.ok(source.includes("target_fasta"));
});

test("approving can actually start the run", () => {
  assert.ok(source.includes('"pipeline.run"'), "approve must be able to launch");
  assert.ok(html.includes('id="runBtn"'));
});

test("running is guarded so it cannot fire without a target", () => {
  // 실행은 되돌릴 수 없다. 타겟 없이 눌리면 안 된다.
  assert.ok(/타겟 서열을 입력/.test(source));
});

test("the login gate hides the workspace instead of overlaying a broken one", () => {
  assert.ok(/id="loginGate"[^>]*class="[^"]*gate/.test(html));
});

test("links to the old console are confined to the ops nav", () => {
  // guided 만으로 쓸 수 있어야 한다. 운영 링크(전체 기능 콘솔)는 의도된 출구지만,
  // 그 외의 곳에서 기존 화면에 의존하면 안 된다.
  const code = source.replace(/^\s*\/\/.*$/gm, "");
  assert.ok(!/기존 화면/.test(code), "no dead ends back to index.html");
  const nav = html.match(/<nav class="oplinks"[^>]*>[\s\S]*?<\/nav>/);
  assert.ok(nav, "ops links live in their own nav");
  const rest = html.replace(/<!--[\s\S]*?-->/g, "").replace(nav[0], "");
  assert.ok(!/index\.html/.test(rest), "the page itself must not depend on the old screen");
});

test("a truncated artifact can be read further from here", () => {
  assert.ok(/두 배로 더 읽기/.test(source));
  assert.ok(/openArtifact\(runId, path, format, cap \* 2\)/.test(source));
});

test("directories are excluded by allowlisting files, not by guessing a name", () => {
  // list_artifacts 는 type 을 "dir" 로 준다. "directory" 를 제외하도록 짐작해서
  // 썼더니 msa 와 tiers 가 그대로 목록에 남았고, 누르면 "artifact is not a
  // file" 이 났다. 새 type 이 생겨도 안전하도록 파일만 허용한다.
  assert.ok(/=== "file"/.test(source), "files must be allowlisted");
  assert.ok(!/!== "directory"/.test(source), "do not exclude a guessed type name");
});

test("a run without a status file still shows its artifacts", () => {
  // test_relax_out 에는 status.json 이 없지만 .pdb 를 포함한 산출물이 있다.
  // 상태를 못 읽었다고 결과까지 막으면 볼 수 있는 것을 못 보게 된다.
  const fn = source.slice(source.indexOf("async function loadRunStatus("),
                          source.indexOf("async function loadArtifacts("));
  const guard = fn.slice(fn.indexOf("found === false"));
  assert.ok(/loadArtifacts/.test(guard), "artifacts must load even with no status");
  assert.ok(!/^\s*return;/m.test(guard.slice(0, guard.indexOf("loadArtifacts"))),
            "the missing-status branch must not return early");
});

test("panes can be resized, by pointer and by keyboard", () => {
  // 3D 를 볼 때와 계획을 읽을 때 필요한 폭이 다르다. 고정 폭이면 둘 중 하나는
  // 늘 좁다. 드래그만 지원하면 키보드 사용자는 폭을 바꿀 수 없다.
  assert.ok(html.includes('data-splitter="left"') && html.includes('data-splitter="right"'));
  assert.ok(/role="separator"/.test(html));
  assert.ok(/tabindex="0"/.test(html), "splitters must be focusable");
  assert.ok(source.includes("ArrowLeft") && source.includes("ArrowRight"));
  assert.ok(/localStorage\.setItem\(PANE_KEY/.test(source), "widths must survive a reload");
});

test("a structure can be opened full screen", () => {
  assert.ok(html.includes('id="stage"'));
  assert.ok(source.includes("openStage"));
  assert.ok(/Escape/.test(source), "the overlay must close on Escape");
});

test("3D failure falls back to the file contents", () => {
  // WebGL 은 원격 데스크톱이나 GPU 차단 목록에서 없을 수 있다. 그때 파일을
  // 못 여는 것이 아니라 그리지 못하는 것이다.
  const fn = source.slice(source.indexOf("function render3d("));
  assert.ok(/try\s*{/.test(fn), "createViewer can throw");
  assert.ok(/artifacttext/.test(fn), "the text must still be shown");
});

test("no error message can end up as undefined", () => {
  assert.ok(source.includes("function errorText("));
  // errorText 안의 error.message 는 정의 그 자체이므로 제외한다.
  // errorText 의 정의와, 서버가 돌려준 오류 객체(out.error.message)는 제외한다.
  // 규칙은 "던져진 것에 .message 를 직접 쓰지 말라" 이다.
  const code = source
    .replace(/function errorText\([\s\S]*?\n}/, "")
    .replace(/out\.error\.message/g, "");
  assert.ok(!/\berror\.message/.test(code), "use errorText, which handles non-Errors");
});

test("the default purpose is chosen by capability, not by list order", () => {
  assert.ok(/r\.executable && r\.validated/.test(source));
});

test("a target can be loaded from a file, not only pasted", () => {
  assert.ok(html.includes('id="targetFile"'));
  assert.ok(/accept="[^"]*\.fasta/.test(html));
  assert.ok(source.includes("sequenceFromFasta") && source.includes("sequenceFromStructure"));
});

test("structure files are read from ATOM CA only", () => {
  // HETATM 의 CA 는 알파탄소가 아니라 칼슘이거나 리간드 원자일 수 있다.
  const fn = source
    .slice(source.indexOf("function sequenceFromStructure("),
           source.indexOf("async function loadTargetFile("))
    .replace(/^\s*\/\/.*$/gm, "");
  assert.ok(/startsWith\("ATOM"\)/.test(fn));
  assert.ok(!/HETATM/.test(fn), "HETATM must not be read as a residue");
});

test("a file with more than one sequence says which one it used", () => {
  assert.ok(/첫 번째만 사용/.test(source));
});

test("the plan can be discussed and the model only proposes", () => {
  assert.ok(html.includes('id="chatForm"'));
  assert.ok(source.includes("pipeline.discuss_plan"));
  // 대화가 계획을 직접 고치면, 고정 필드를 지키는 규칙이 대화 한 번으로 무너진다.
  const fn = source.slice(source.indexOf("async function sendChat("),
                          source.indexOf("async function loadLlmModels("));
  assert.ok(!/state\.plan\.decisions/.test(fn), "chat must not mutate the plan");
  assert.ok(source.includes("applicable_edits") && source.includes("rejected_edits"));
});

test("rejected proposals are shown without an apply button", () => {
  assert.ok(/is-rejected/.test(source));
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes(".proposal.is-rejected"));
});

test("the LLM can be the server's or the user's own key", () => {
  assert.ok(html.includes('id="llmProvider"') && html.includes('id="llmKey"'));
  assert.ok(source.includes("chat.list_models"), "the user must be able to list their models");
  assert.ok(/브라우저에만/.test(html), "the page must say where the key lives");
});

test("a generated reply is labelled as generated", () => {
  assert.ok(source.includes("reply_is_generated"));
  assert.ok(/근거가 아닙니다/.test(source));
});
