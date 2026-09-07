# Guided 단일화면 콘솔 재설계 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `guided.html`을 Ditto식 3-페인 단일 콘솔(B안 — 계획 폼 중심)로 재구성해 설계→계획→승인→실행→모니터→결과→구조·근거를 한 화면에서 이어지게 한다.

**Architecture:** 기존 guided.js(1,358줄)를 기능 모듈로 분해하고(`frontend/guided/`), 우측에 Run/Results/Structure/Evidence 탭을 새로 만든다. 로직은 기존 `lib/` 모듈(pipeline/compare/residue-picker/md)을 재사용하고, `index.html`/`app.js`는 수정하지 않는다. 백엔드 변경 없음.

**Tech Stack:** 바닐라 ES 모듈 + `node --test`, 3Dmol 2.0.4(CDN, 기존과 동일), vite build(기존 설정 유지).

**스펙:** `docs/specs/2026-09-07-guided-console-redesign-design.md`

**작업 디렉터리:** `/opt/protein_pipeline-work` (브랜치 `docs/figure-pipeline`). 모든 프런트 명령은 저장소 루트에서 실행한다.

---

## 파일 구조 (최종 상태)

```
frontend/
├── guided.html              # 수정 — B안 3페인 DOM (Task 3)
├── guided.css               # 수정 — 탭/퍼널/칩/사이드바 스타일 추가 (Task 3~9 각각)
├── guided.js                # 수정 — 얇은 facade(부팅/이벤트 연결)만 남김 (Task 2)
├── guided/
│   ├── api.js               # 신규 — apiBase/callTool/authHeaders/storedUserName (Task 2, 기존 코드 이동)
│   ├── plan.js              # 신규 — 레지스트리·목표·계획·대화 (Task 2, 기존 코드 이동)
│   ├── monitor.js           # 신규 — 상태/아티팩트/3D/폴링/취소/리포트 (Task 2, 5)
│   ├── sidebar.js           # 신규 — 좌측 실행 목록 (Task 4)
│   ├── results.js           # 신규 — 퍼널/히트리스트/비교 (Task 6)
│   ├── evidence.js          # 신규 — 근거 뷰 (Task 7)
│   └── structure.js         # 신규 — 구조 탭/잔기 피커 (Task 8)
└── tests/
    ├── guided.test.js       # 수정 — source 어서션을 모듈 합본으로 (Task 2)
    ├── guided-results.test.js  # 신규 (Task 6)
    └── guided-sidebar.test.js  # 신규 (Task 4)
```

책임 경계: `guided/api.js`는 DOM을 모른다(fetch/localStorage만). `guided/*.js`는 모듈 최상위에서 DOM을 만지지 않는다(함수 안에서만). DOM 연결은 `guided.js` facade가 전담한다.

---

### Task 1: 기준선 확인

**Files:** 없음(읽기만)

- [ ] **Step 1: 기존 guided 테스트가 녹색인지 확인**

Run: `cd frontend && node --test tests/guided.test.js`
Expected: `# pass 6`(또한 파일 내 전체 테스트), `# fail 0`

- [ ] **Step 2: 빌드 기준선**

Run: `cd /opt/protein_pipeline-work && npm --prefix frontend run build`
Expected: `✓ built` — 실패하면 여기서 멈추고 원인부터 해결한다.

---

### Task 2: guided.js 모듈 분해 (동작 보존)

**Files:**
- Create: `frontend/guided/api.js`
- Create: `frontend/guided/plan.js`
- Create: `frontend/guided/monitor.js`
- Modify: `frontend/guided.js`
- Modify: `frontend/tests/guided.test.js`

이동 규칙: 아래에 명시한 함수/상수는 **본문을 바꾸지 않고** guided.js에서 잘라 옮긴다. 유일한 수정은 (a) 파일 상단 import 추가, (b) 옮긴 뒤 guided.js에서 `export ... from` 재노출, (c) 절대경로 참조 없음 확인이다. DOM id는 전부 유지되므로 `getElementById` 호출은 그대로 작동한다.

- [ ] **Step 1: `frontend/guided/api.js` 생성** — guided.js 15~30행부(`resolveDefaultApiBase`/`unwrapToolResponse` import), 60~114행부(`apiBase`, `signIn`을 제외한 순수 부분)를 이동. signIn/signOut은 DOM(setSignedIn/setSignedOut)을 부르므로 facade에 남긴다.

```js
// frontend/guided/api.js — DOM 을 모르는 전송/세션 계층.
import { resolveDefaultApiBase } from "../lib/auth.js";
import { unwrapToolResponse } from "../lib/tool-call.js";

// 기존 앱과 같은 규칙. 빈 문자열이면 /tools/call 을 원점 기준으로 호출하는데,
// 배포 환경의 리버스 프록시는 /api/* 만 백엔드로 보내므로 그대로 404 가 난다.
export function apiBase() {
  const saved = (localStorage.getItem("kbf.apiBase") || "").replace(/\/+$/, "");
  if (saved && !/localhost|127\.0\.0\.1/.test(saved)) return saved;
  return resolveDefaultApiBase({
    origin: window.location.origin,
    pathname: window.location.pathname,
  }).replace(/\/+$/, "");
}

export function authHeaders() {
  const token = localStorage.getItem("kbf.token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function storedUserName() {
  try {
    const raw = JSON.parse(localStorage.getItem("kbf.user") || "null");
    return raw ? String(raw.username || raw.name || raw.id || "") : "";
  } catch {
    return "";
  }
}

export async function callTool(name, args) {
  const res = await fetch(`${apiBase()}/tools/call`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, arguments: args || {} }),
  });
  const payload = await res.json().catch(() => null);
  // 봉투를 벗겨서 도구 결과만 돌려준다. 봉투를 그대로 넘기면 호출자가 보는
  // 모든 필드가 undefined 가 되고, 200 응답이라 오류도 뜨지 않는다.
  return unwrapToolResponse({ ok: res.ok, status: res.status, payload });
}
```

- [ ] **Step 2: `frontend/guided/plan.js` 생성** — guided.js에서 아래를 **그대로** 이동한다(현재 줄 번호 기준):
  - 10~21행 `OBJECTIVES`, 122~137 `STAGE_LABEL`/`stageLabel`, 139~144 `formatSeconds`, 146~193 `stageRow`, 195~232 `renderCostBar`, 234~261 `renderStages`, 263~299 `loadRegistry`, 301~338 `renderTemplates`, 340~346 `mark`, 348~377 `renderConnections`, 681~708 `currentRoute`/`onPurposeChange`, 710~758 `renderWeights`/`weightRow`/`collectObjective`, 760~830 `evidenceNode`/`decisionNode`, 832~960 `REASON_LABEL`/`explainPlan`/`state`/`appendChat`/`renderProposals`/`sendChat`/`loadLlmModels`, 1102~1183 `generatePlan`/`approve`.
  - 파일 상단: `import { callTool } from "./api.js";`
  - 하단 export: `export { OBJECTIVES, registry, state, loadRegistry, renderTemplates, onPurposeChange, renderWeights, collectObjective, generatePlan, approve, sendChat, appendChat, decisionNode, evidenceNode, formatSeconds, stageRow, renderStages, renderCostBar, currentRoute, renderConnections, explainPlan };`
  - `showStep` 호출 1건(691행 `if (typeof showStep === "function" ...)`)은 삭제한다 — 위자드 단계가 사라지기 때문이다. 이 줄을 지우는 것이 이동 시 유일한 본문 수정이다.

- [ ] **Step 3: `frontend/guided/monitor.js` 생성** — guided.js에서 아래를 **그대로** 이동:
  - 379~407 `runState`/`STRUCTURE_FORMATS`, 391~407 `errorText`/`formatBytes`/`isStructureArtifact`, 439~491 `setRunStatus`/`loadRunStatus`, 493~605 `loadArtifacts`/`openArtifact`, 607~649 `openStage`/`closeStage`/`render3d`, 651~679 `probeWorkers`.
  - 상단: `import { callTool } from "./api.js";` + `export { errorText, formatBytes, isStructureArtifact, loadRunStatus, loadArtifacts, openArtifact, openStage, closeStage, render3d, probeWorkers, runState };`
  - `loadRuns`(409~437행)는 이동하지 않는다 — Task 4의 sidebar가 대체한다. facade에서 제거한다.

- [ ] **Step 4: `frontend/guided.js`를 facade로 축소** — 남기는 것: import 목록, 로그인/세션 DOM 로직(75~120행의 signIn/setSignedIn/setSignedOut/storedUserName — storedUserName은 `./guided/api.js`에서 import), 스플리터(initSplitters), showStep/showPanel, 이벤트 연결, `boot()`. 하단 재노출:

```js
export { collectObjective, decisionNode, evidenceNode, formatSeconds, stageRow } from "./guided/plan.js";
```

- [ ] **Step 5: `frontend/tests/guided.test.js`의 source 합본 전환** — 7~8행을 교체:

```js
const sources = [
  new URL("../guided.js", import.meta.url),
  ...[
    "api.js", "plan.js", "monitor.js", "sidebar.js", "results.js",
    "evidence.js", "structure.js",
  ].map((name) => new URL(`../guided/${name}`, import.meta.url)),
];
const present = sources.filter((url) => existsSync(url));
const source = present
  .map((url) => readFileSync(url, "utf8"))
  .join("\n");
const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
```

상단 import에 `existsSync`를 `node:fs`에서 추가한다. 존재하지 않는 모듈(Task 3 이전)은 건너뛴다 — 어서션은 어느 파일에 패턴이 있든 통과한다.

- [ ] **Step 6: 파서 테스트 갱신** — "parses as an ES module" 테스트(11~26행)를 합본 각 파일마다 실행하도록 교체:

```js
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
```

- [ ] **Step 7: 녹색 확인**

Run: `cd frontend && node --test tests/guided.test.js`
Expected: 모두 PASS (이동 후에도 어서션 패턴이 각 모듈에 그대로 있으므로)

- [ ] **Step 8: 커밋**

```bash
git add frontend/guided frontend/guided.js frontend/guided.test.js frontend/tests/guided.test.js
git commit -m "refactor(rapid-guided): split guided.js into focused modules, behavior preserved"
```

---

### Task 3: guided.html B안 골격 + CSS

**Files:**
- Modify: `frontend/guided.html` (전면 교체)
- Modify: `frontend/guided.css` (추가)

- [ ] **Step 1: guided.html 교체** — 아래 전체로 덮어쓴다. 기존 id 중 `warnings`, `decisions`, `explainBox`, `explainText`, `explainSource`, `questions`, `chatLog`, `chatInput`, `chatSend`, `chatForm`, `proposals`, `purpose`, `templates`, `purposeNote`, `weights`, `rmsdMax`, `nDesigns`, `lengthAa`, `af2Budget`, `targetFasta`, `targetFile`, `targetFileBtn`, `targetClearBtn`, `targetNote`, `planBtn`, `planStatus`, `reviewState`, `approveBtn`, `approveState`, `runBtn`, `runNote`, `requestOut`, `authHint`, `runStatus`, `artifactList`, `artifactPreview`, `connections`, `monitorList`, `probeBtn`, `stage`, `stageTitle`, `stageBody`, `stageClose`, `loginGate`, `loginForm`, `loginUser`, `loginPass`, `loginBtn`, `loginError`, `whoami`, `logoutBtn`, `costBar`, `stages`, `routeMeta` 는 **전부 유지**된다(테스트 어서션 + JS 이동 코드 호환).

```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>RAPID — 설계 콘솔</title>
    <link rel="stylesheet" href="./guided.css" />
    <script src="https://cdn.jsdelivr.net/npm/3dmol@2.0.4/build/3Dmol-min.js"
            integrity="sha384-gCVNmzC8IyU7AmfDiNbHLpM9ac5VhQb2mfDURiTqHrnEcI2qp/JsQVeeEd3sLdfq"
            crossorigin="anonymous"
            referrerpolicy="no-referrer"></script>
  </head>
  <body>
    <div id="loginGate" class="gate">
      <form id="loginForm" class="gatecard">
        <h1>RAPID</h1>
        <p class="lede">목표를 말하면 경로와 근거를 제안하고, 승인한 것만 실행합니다.</p>
        <label for="loginUser">사용자<input id="loginUser" name="username" autocomplete="username" required /></label>
        <label for="loginPass">비밀번호<input id="loginPass" name="password" type="password" autocomplete="current-password" required /></label>
        <button id="loginBtn" class="primary" type="submit">로그인</button>
        <p id="loginError" class="gateerror" role="alert"></p>
      </form>
    </div>

    <header class="topbar">
      <div class="brand"><b>RAPID</b> <span>단일화면 설계 콘솔</span></div>
      <div class="runheader" id="topbarChips" aria-live="polite"></div>
      <div class="badges">
        <span class="badge" id="whoami"></span>
        <button class="badge link" id="logoutBtn" type="button">로그아웃</button>
      </div>
    </header>

    <main class="layout hidden" id="workspace">
      <aside class="side">
        <section class="block">
          <h3>실행</h3>
          <button id="newDesignBtn" class="ghost newrun" type="button">＋ 새 설계</button>
          <div id="runList" class="runlist empty">실행을 불러오는 중…</div>
        </section>
        <section class="block">
          <h3>운영</h3>
          <nav class="oplinks">
            <a href="./index.html">기존 콘솔(전체 기능)</a>
            <a href="./index.html" data-op="runpod">RunPod Admin</a>
            <a href="./index.html" data-op="mcp">MCP 설정</a>
          </nav>
          <div id="connections" class="conns"></div>
          <button id="probeBtn" class="ghost">워커 확인</button>
          <div id="monitorList" class="empty">확인을 누르면 표시됩니다.</div>
        </section>
      </aside>

      <div class="splitter" data-splitter="left" role="separator" aria-orientation="vertical" aria-label="왼쪽 폭 조절" tabindex="0"></div>

      <section class="center">
        <section class="plan-section" id="objectiveSection">
          <h2>설계 목표</h2>
          <div id="templates" class="cards">불러오는 중…</div>
          <select id="purpose" class="visually-hidden" aria-label="설계 목적"></select>
          <p id="purposeNote" class="note detail"></p>
          <div class="plan-grid">
            <div>
              <div id="stages" class="stages">목적을 고르면 단계가 표시됩니다.</div>
              <div id="costBar" class="costwrap"></div>
            </div>
            <div>
              <p class="note">가중치는 상대값이라 정규화됩니다. 제약은 다른 점수로 상쇄되지 않습니다.</p>
              <div id="weights"></div>
              <div class="fields">
                <label for="rmsdMax">RMSD 상한 <span class="unit">Å</span>
                  <input id="rmsdMax" type="number" step="0.1" value="2.0" /></label>
                <label for="nDesigns">설계 수
                  <input id="nDesigns" type="number" step="8" value="16" /></label>
                <label for="lengthAa">서열 길이 <span class="unit">aa</span>
                  <input id="lengthAa" type="number" step="10" value="200" /></label>
                <label for="af2Budget">AF2 예산 <span class="unit">호출</span>
                  <input id="af2Budget" type="number" step="10" value="500" /></label>
              </div>
            </div>
          </div>
          <div class="field">
            <div class="fieldhead">
              <label for="targetFasta">타겟 서열</label>
              <div class="actions">
                <input id="targetFile" type="file" class="visually-hidden"
                       accept=".fasta,.fa,.faa,.seq,.txt,.pdb,.cif" />
                <button id="targetFileBtn" class="ghost" type="button">파일 선택</button>
                <button id="targetClearBtn" class="ghost" type="button">지우기</button>
              </div>
            </div>
            <textarea id="targetFasta" rows="3" spellcheck="false"
                      placeholder="MKTAYIAKQRQISFVKSHFSRQ… 붙여넣거나 FASTA·PDB 파일을 고르세요"></textarea>
            <p id="targetNote" class="note" role="status" aria-live="polite"></p>
          </div>
          <div class="actions">
            <button id="planBtn" class="primary">계획 생성</button>
            <span id="planStatus" class="status" role="status" aria-live="polite"></span>
          </div>
          <div id="authHint" class="callout coral hidden">세션이 만료되었습니다. 다시 로그인하세요.</div>
        </section>

        <section class="plan-section hidden" id="planSection">
          <h2>계획 <span id="reviewState" class="stepmeta"></span></h2>
          <div id="warnings"></div>
          <div id="explainBox" class="explain hidden">
            <div class="explainhead">
              <b>설명</b>
              <span class="genbadge" id="explainSource"></span>
            </div>
            <p id="explainText"></p>
            <div id="questions"></div>
          </div>
          <div id="decisions" class="empty">계획을 생성하면 결정과 근거가 여기 표시됩니다.</div>
          <div class="actions">
            <button id="approveBtn" class="primary" disabled>승인하고 요청 만들기</button>
            <button id="runBtn" class="ghost" disabled>실행 시작</button>
            <span id="approveState" class="stepmeta"></span>
          </div>
          <p id="runNote" class="note" role="status" aria-live="polite"></p>
          <pre id="requestOut" class="empty">아직 승인하지 않았습니다.</pre>

          <section class="discuss" id="discuss" hidden>
            <div class="discusshead">
              <h3>계획에 대해 물어보기</h3>
              <details class="evidence llmsetup">
                <summary id="llmSummary">LLM: 서버 연결</summary>
                <label for="llmProvider">제공자
                  <select id="llmProvider">
                    <option value="">서버에 연결된 것 사용</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="openai">OpenAI</option>
                    <option value="gemini">Gemini</option>
                  </select>
                </label>
                <label for="llmKey">API 키
                  <input id="llmKey" type="password" autocomplete="off"
                         placeholder="브라우저에만 보관됩니다" />
                </label>
                <div class="actions">
                  <button id="llmLoadBtn" class="ghost" type="button">모델 불러오기</button>
                </div>
                <label for="llmModel">모델
                  <select id="llmModel"><option value="">먼저 모델을 불러오세요</option></select>
                </label>
                <p class="note">키는 이 브라우저에만 있고 서버에 저장되지 않습니다.</p>
              </details>
            </div>
            <div id="chatLog" class="chatlog empty">계획에 대해 궁금한 것을 물어보세요.</div>
            <div id="proposals" class="proposals"></div>
            <form id="chatForm" class="chatform">
              <label class="visually-hidden" for="chatInput">질문</label>
              <input id="chatInput" placeholder="예: 온도를 0.3으로 올리면 무엇이 달라지나요?" />
              <button id="chatSend" class="primary" type="submit">보내기</button>
            </form>
          </section>
        </section>
      </section>

      <div class="splitter" data-splitter="right" role="separator" aria-orientation="vertical" aria-label="오른쪽 폭 조절" tabindex="0"></div>

      <aside class="side right">
        <nav class="tabs" aria-label="결과 보기">
          <button class="tab is-active" data-panel="run">Run</button>
          <button class="tab" data-panel="results">Results</button>
          <button class="tab" data-panel="structure">Structure</button>
          <button class="tab" data-panel="evidence">Evidence</button>
        </nav>

        <section class="block panel" data-panelfor="run">
          <div id="runStatus" class="empty" role="status" aria-live="polite">실행을 고르면 상태가 표시됩니다.</div>
          <div id="runProgress" class="progress hidden">
            <div class="progressbar"><i id="runProgressFill"></i></div>
            <span id="runProgressLabel" class="note"></span>
          </div>
          <div class="actions hidden" id="runActions">
            <button id="reportGenBtn" class="ghost">리포트 생성</button>
            <button id="reportLoadBtn" class="ghost">리포트 불러오기</button>
            <button id="cancelRunBtn" class="ghost danger">실행 취소</button>
          </div>
          <div id="reportView" class="report hidden"></div>
          <div id="artifactList" class="empty">실행을 고르면 산출물이 표시됩니다.</div>
          <div id="artifactPreview" class="preview"></div>
        </section>

        <section class="block panel hidden" data-panelfor="results">
          <div class="actions">
            <label class="visually-hidden" for="compareBaseline">비교 기준</label>
            <select id="compareBaseline"><option value="">비교 기준 실행 선택…</option></select>
            <button id="compareBtn" class="ghost">비교</button>
          </div>
          <div id="funnelBox" class="funnelbox"><p class="note">실행을 고르면 게이트 퍼널이 표시됩니다.</p></div>
          <div id="hitList" class="hitlist"><p class="note">실행을 고르면 히트리스트가 표시됩니다.</p></div>
        </section>

        <section class="block panel hidden" data-panelfor="structure">
          <div id="structureFiles" class="empty">구조 파일(.pdb/.cif/.sdf)이 여기 나열됩니다.</div>
          <div id="structureViewer" class="preview"></div>
          <div id="residueStrip" class="residuestrip"></div>
          <p class="note">잔기를 누르면 3D 뷰에서 하이라이트됩니다. 선택 목록은 설계 제약으로 쓸 수 있습니다.</p>
          <div id="residueSelection" class="residuesel"></div>
        </section>

        <section class="block panel hidden" data-panelfor="evidence">
          <div id="evidenceView" class="empty">계획을 생성하면 근거가 여기 모입니다.</div>
        </section>
      </aside>
    </main>

    <div id="stage" class="stage-overlay hidden" role="dialog" aria-modal="true" aria-labelledby="stageTitle">
      <header class="stagehead">
        <span id="stageTitle" class="stagetitle"></span>
        <button id="stageClose" class="ghost stageclose" type="button">닫기 (Esc)</button>
      </header>
      <div id="stageBody" class="stagebody"></div>
    </div>

    <script type="module" src="./guided.js"></script>
  </body>
</html>
```

- [ ] **Step 2: guided.css에 아래 블록 추가** (기존 규칙 유지; `.kind-*` 등 기존 셀렉터는 삭제 금지 — 테스트가 본다)

```css
/* --- B안 단일화면 ------------------------------------------------------- */
.plan-section { padding: 14px 16px 20px; border-bottom: 1px solid var(--line); }
.plan-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.runheader { display: flex; gap: 8px; align-items: center; }
.runheader .chip { font-size: 12px; }
.runlist { display: flex; flex-direction: column; gap: 4px; max-height: 46vh; overflow: auto; }
.runitem { display: flex; flex-direction: column; gap: 2px; text-align: left; background: transparent;
           border: 1px solid var(--line); border-radius: 8px; padding: 6px 8px; color: inherit; cursor: pointer; }
.runlist .run-item.is-active { border-color: var(--accent, #38bdf8); }
.run-item .rid { font-weight: 600; font-size: 12px; }
.run-item .rmeta { color: var(--muted, #94a3b8); font-size: 11px; display: flex; gap: 6px; align-items: center; }
.oplinks { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.oplinks a { color: var(--accent, #38bdf8); font-size: 12px; text-decoration: none; }
.progressbar { height: 6px; border-radius: 6px; background: var(--line, #334155); overflow: hidden; }
.progressbar i { display: block; height: 100%; width: 0; background: var(--accent, #38bdf8); transition: width .4s; }
.progress.hidden, .report.hidden, #runActions.hidden { display: none; }
.report { border: 1px solid var(--line); border-radius: 8px; padding: 8px; max-height: 300px; overflow: auto; }
.funnelbox .funnel { display: flex; align-items: flex-end; gap: 6px; height: 90px; margin: 8px 0; }
.funnelbox .funnel i { flex: 1; background: linear-gradient(180deg, #38bdf8, #1d4ed8); border-radius: 3px 3px 0 0; }
.hitlist table { width: 100%; font-size: 11px; border-collapse: collapse; }
.hitlist th, .hitlist td { border-bottom: 1px solid var(--line); padding: 3px 4px; text-align: left; }
.residuestrip { display: flex; flex-wrap: wrap; gap: 1px; }
.residuestrip button { min-width: 18px; font-size: 9px; padding: 1px 2px; border: 1px solid var(--line); background: transparent; color: inherit; cursor: pointer; border-radius: 3px; }
.residuestrip button.is-sel { outline: 2px solid var(--accent, #38bdf8); }
.residuesel .chip { margin: 2px 2px 0 0; }
.actions .danger { color: #fda4af; border-color: #7f1d1d; }
```

(실제 변수명은 기존 guided.css의 이름을 따른다 — `--accent`, `--muted`, `--line` 이 없으면 기존 파일의 대응 변수로 바꿔 쓴다.)

- [ ] **Step 3: html 어서션 확인** — `id="warnings"`, `id="explainBox"`, `id="purpose"` 가 새 HTML에 있음을 확인.

Run: `cd frontend && node --test tests/guided.test.js`
Expected: PASS. `id="runSelect"` 어서션이 있다면(`grep "runSelect" tests/guided.test.js`) 그 어서션은 sidebar의 `run-item` 버튼으로 대체했음을 반영해 수정한다(어서션 삭제 + Task 4의 새 어서션으로 대체).

- [ ] **Step 4: 커밋**

```bash
git add frontend/guided.html frontend/guided.css frontend/tests/guided.test.js
git commit -m "feat(rapid-guided): rebuild guided.html into the three-pane console skeleton"
```

---

### Task 4: 좌측 실행 목록 (sidebar)

**Files:**
- Create: `frontend/guided/sidebar.js`
- Create: `frontend/tests/guided-sidebar.test.js`
- Modify: `frontend/guided.js`, `frontend/guided.css`

- [ ] **Step 1: 실패하는 테스트 작성**

```js
// frontend/tests/guided-sidebar.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { normalizeRuns, runItemLabel } from "../guided/sidebar.js";

test("normalizeRuns accepts string lists and object lists and dedupes", () => {
  const runs = normalizeRuns(["run_b", "run_a", "run_b", { run_id: "run_c", stage: "af2_50" }]);
  assert.deepEqual(runs.map((r) => r.run_id), ["run_b", "run_a", "run_c"]);
  assert.equal(runs[2].stage, "af2_50");
});

test("runItemLabel shows the stage chip and state", () => {
  assert.equal(runItemLabel({ run_id: "r1", stage: "af2_50", state: "running" }), "af2_50 · running");
  assert.equal(runItemLabel({ run_id: "r1" }), "idle");
});
```

- [ ] **Step 2: 실패 확인** — `cd frontend && node --test tests/guided-sidebar.test.js` → 모듈 없음으로 FAIL

- [ ] **Step 3: `frontend/guided/sidebar.js` 구현**

```js
// 좌측 실행 목록. list_runs 는 문자열 목록을 돌려주는 배포본과 객체를 돌려주는
// 배포본이 둘 다 있었다 (guided.js loadRuns 의 주석). 둘 다 받는다.
export function normalizeRuns(raw) {
  const seen = new Set();
  const rows = [];
  for (const run of Array.isArray(raw) ? raw : []) {
    const id = typeof run === "string" ? run : String(run.run_id || run.id || "");
    if (!id || seen.has(id)) continue;
    seen.add(id);
    rows.push({
      run_id: id,
      stage: typeof run === "object" ? String(run.stage || "") : "",
      state: typeof run === "object" ? String(run.state || "") : "",
      updated_at: typeof run === "object" ? String(run.updated_at || "") : "",
    });
  }
  return rows;
}

export function runItemLabel(run) {
  const parts = [run.stage, run.state].filter(Boolean);
  return parts.length ? parts.join(" · ") : "idle";
}
```

- [ ] **Step 4: 녹색 확인** — `node --test tests/guided-sidebar.test.js` → PASS

- [ ] **Step 5: 렌더/선택 연결** — `frontend/guided/sidebar.js`에 추가(파일 하단, DOM 부분):

```js
import { callTool } from "./api.js";

export async function loadRunList(onSelect) {
  const host = document.getElementById("runList");
  host.classList.remove("empty");
  host.textContent = "불러오는 중…";
  try {
    const out = await callTool("pipeline.list_runs", { limit: 30 });
    if (out && out.error) throw new Error(out.error);
    const runs = normalizeRuns(out.runs || out.items || []);
    host.replaceChildren();
    if (!runs.length) {
      host.classList.add("empty");
      host.textContent = "실행이 없습니다.";
      return [];
    }
    for (const run of runs) {
      const node = document.createElement("button");
      node.type = "button";
      node.className = "run-item";
      node.dataset.runId = run.run_id;
      node.appendChild(Object.assign(document.createElement("span"), {
        className: "rid", textContent: run.run_id,
      }));
      node.appendChild(Object.assign(document.createElement("span"), {
        className: "rmeta", textContent: runItemLabel(run),
      }));
      node.addEventListener("click", () => {
        for (const item of host.querySelectorAll(".run-item")) item.classList.toggle("is-active", item === node);
        onSelect(run.run_id);
      });
      host.appendChild(node);
    }
    return runs;
  } catch (error) {
    host.classList.add("empty");
    host.textContent = `실행 목록을 불러오지 못했습니다: ${error?.message || error}`;
    return [];
  }
}
```

- [ ] **Step 6: facade 연결** — `frontend/guided.js`: 기존 `loadRuns`/`runSelect` 관련 코드 제거, `boot()`에서 `loadRunList(selectRun)` 호출, `selectRun(runId)`는 `loadRunStatus(runId)` + `startPolling(runId)` + Results/Evidence 갱신을 부른다(Task 5~7에서 채움). `pipeline.run` 성공 후에도 `loadRunList` 재호출 + 해당 항목 active.
- [ ] **Step 7: 전체 guided 테스트 + 커밋**

```bash
cd frontend && node --test tests/guided.test.js tests/guided-sidebar.test.js
git add frontend/guided/sidebar.js frontend/guided.js frontend/guided.css frontend/tests/guided-sidebar.test.js
git commit -m "feat(rapid-guided): runs sidebar with stage/state items replacing the dropdown"
```

---

### Task 5: Run 탭 — 진행바·취소·리포트

**Files:**
- Modify: `frontend/guided/monitor.js`
- Create: `frontend/tests/guided-progress.test.js`
- Modify: `frontend/guided.js`, `frontend/guided.css`

- [ ] **Step 1: 실패하는 테스트**

```js
// frontend/tests/guided-progress.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { mapStatusStageToStep, stageProgressPercent, nextPollDelayMs } from "../guided/monitor.js";

test("tier-suffixed status stages map to their base step", () => {
  assert.equal(mapStatusStageToStep("af2_50"), "af2");
  assert.equal(mapStatusStageToStep("relax_30"), "relax");
  assert.equal(mapStatusStageToStep("wt_diff"), "wt");
  assert.equal(mapStatusStageToStep("init"), "msa");
});

test("progress percent walks the request's step plan", () => {
  const steps = ["msa", "design", "soluprot", "af2", "done"];
  assert.equal(stageProgressPercent("msa", "running", steps), 20);
  assert.equal(stageProgressPercent("af2", "running", steps), 80);
  assert.equal(stageProgressPercent("done", "done", steps), 100);
  assert.equal(stageProgressPercent("unknown", "running", steps), 0);
});

test("polling backs off by activity and stops after repeated failures", () => {
  assert.equal(nextPollDelayMs(0, true), 5000);
  assert.equal(nextPollDelayMs(0, false), 30000);
  assert.equal(nextPollDelayMs(2, true), 5000);
  assert.equal(nextPollDelayMs(3, true), 0);
});
```

- [ ] **Step 2: 실패 확인** → `node --test tests/guided-progress.test.js` FAIL

- [ ] **Step 3: monitor.js에 순수 헬퍼 + 폴링 구현**

```js
import { progressStepsForRequest } from "../lib/pipeline.js";
import { renderMarkdown } from "../lib/md.js";
import { callTool } from "./api.js";

const POLL_ACTIVE_MS = 5000;
const POLL_IDLE_MS = 30000;
const POLL_MAX_FAILURES = 3;

export function nextPollDelayMs(consecutiveFailures, isActive) {
  if (consecutiveFailures >= POLL_MAX_FAILURES) return 0;
  return isActive ? POLL_ACTIVE_MS : POLL_IDLE_MS;
}

const STAGE_ALIASES = { wt_diff: "wt", init: "msa" };

export function mapStatusStageToStep(stage) {
  const raw = String(stage || "").trim();
  if (!raw) return "";
  if (STAGE_ALIASES[raw]) return STAGE_ALIASES[raw];
  return raw.replace(/_[0-9]+$/, "");   // design_50 -> design
}

export function stageProgressPercent(stage, state, steps) {
  if (!Array.isArray(steps) || !steps.length) return 0;
  if (String(state) === "done") return 100;
  const idx = steps.indexOf(mapStatusStageToStep(stage));
  return idx < 0 ? 0 : Math.round(((idx + 1) / steps.length) * 100);
}

// 폴링 상태. 실행이 끝나거나 실패가 3회 연속되면 멈춘다.
const poll = { runId: "", timer: 0, failures: 0, active: false };

export function stopPolling() {
  if (poll.timer) clearTimeout(poll.timer);
  poll.timer = 0;
  poll.runId = "";
}

export function startPolling(runId, { onTick } = {}) {
  stopPolling();
  poll.runId = runId;
  poll.failures = 0;
  poll.active = true;
  const tick = async () => {
    try {
      const out = await callTool("pipeline.status", { run_id: poll.runId });
      if (out && out.error) throw new Error(out.error);
      poll.failures = 0;
      const info = (out && typeof out.status === "object" && out.status) || out;
      const done = ["done", "failed", "cancelled"].includes(String(info.state));
      poll.active = !done;
      if (onTick) onTick(info);
      if (done) { stopPolling(); return; }
    } catch {
      poll.failures += 1;
      if (poll.failures >= POLL_MAX_FAILURES) {
        poll.active = false;
        if (onTick) onTick({ poll_stalled: true });
        stopPolling();
        return;
      }
    }
    const delay = nextPollDelayMs(poll.failures, poll.active);
    if (delay > 0) poll.timer = setTimeout(tick, delay);
  };
  poll.timer = setTimeout(tick, POLL_ACTIVE_MS);
}

export async function renderRunProgress(info) {
  const wrap = document.getElementById("runProgress");
  const fill = document.getElementById("runProgressFill");
  const label = document.getElementById("runProgressLabel");
  if (!info || info.poll_stalled) { wrap.classList.add("hidden"); return; }
  const steps = progressStepsForRequest({ mode: "pipeline", noveltyEnabled: true, wtCompare: true })
    .filter((step) => step !== "done");
  const percent = stageProgressPercent(info.stage, info.state, steps);
  wrap.classList.remove("hidden");
  fill.style.width = `${percent}%`;
  label.textContent = `${mapStatusStageToStep(info.stage) || info.stage || "-"} · ${info.state || "-"} · ${percent}%`
    + (info.error_summary ? ` · 오류: ${info.error_summary}` : "");
}

export async function cancelRun(runId) {
  return callTool("pipeline.cancel_run", { run_id: runId });
}

export async function generateReport(runId) {
  return callTool("pipeline.generate_report", { run_id: runId });
}

export async function getReport(runId) {
  return callTool("pipeline.get_report", { run_id: runId });
}

export function renderReport(host, markdown) {
  host.classList.remove("hidden");
  host.innerHTML = renderMarkdown(String(markdown || ""));
}
```

(기존 `loadRunStatus`는 `renderRunProgress(info)`를 마지막에 호출하도록 한 줄 추가하고, `openArtifact`/`loadArtifacts`는 그대로 둔다.)

- [ ] **Step 4: 녹색 확인** → `node --test tests/guided-progress.test.js tests/guided.test.js` PASS
- [ ] **Step 5: facade 연결** — `selectRun`에서 `startPolling(runId, { onTick: (info) => { renderRunProgress(info); renderTopbarChips(info); } })`; `cancelRunBtn` 클릭 → `window.confirm` → `cancelRun(runId)` → 상태 재조회; `reportGenBtn` → `generateReport` → `getReport` → `renderReport`; `runActions`는 실행 선택 시 `hidden` 제거.
- [ ] **Step 6: 커밋**

```bash
git add frontend/guided/monitor.js frontend/guided.js frontend/tests/guided-progress.test.js frontend/guided.css
git commit -m "feat(rapid-guided): Run tab with stage progress, polling backoff, cancel and report view"
```

---

### Task 6: Results 탭 — 퍼널·히트리스트·비교

**Files:**
- Create: `frontend/guided/results.js`
- Create: `frontend/tests/guided-results.test.js`
- Modify: `frontend/guided.js`, `frontend/guided.css`

- [ ] **Step 1: 실패하는 테스트**

```js
// frontend/tests/guided-results.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { buildFunnelRow, summarizeCompare, HIT_COLUMNS } from "../guided/results.js";

test("buildFunnelRow counts designed -> soluprot -> af2 -> af2-selected", () => {
  const row = buildFunnelRow("50", {
    scores: { a: 0.8, b: 0.3, c: 0.9, d: 0.1 },
    passed_ids: ["a", "c"],
  }, {
    candidate_ids: ["a", "c", "e"],
    selected_ids: ["a"],
  });
  assert.deepEqual(row, { tier: "50", designed: 4, soluprot: 2, af2: 3, af2_selected: 1 });
});

test("buildFunnelRow tolerates missing halves", () => {
  const row = buildFunnelRow("30", null, { candidate_ids: ["x"], selected_ids: [] });
  assert.deepEqual(row, { tier: "30", designed: 0, soluprot: 0, af2: 1, af2_selected: 0 });
});

test("summarizeCompare flattens top-level scalars into cards", () => {
  const cards = summarizeCompare({ run_id: "r1", baseline_run_id: "r0", notes: "x",
    summary: { soluprot_pass_rate: 0.7, plddt_median: 88 } });
  const labels = cards.map((c) => c.label);
  assert.ok(labels.includes("soluprot_pass_rate"));
  assert.ok(!labels.includes("summary"));
});

test("HIT_COLUMNS defines the render order", () => {
  assert.deepEqual([...HIT_COLUMNS], ["id", "score", "soluprot", "plddt", "rmsd", "novelty"]);
});
```

- [ ] **Step 2: 실패 확인** → FAIL (모듈 없음)

- [ ] **Step 3: `frontend/guided/results.js` 구현**

```js
import { callTool } from "./api.js";

export const HIT_COLUMNS = ["id", "score", "soluprot", "plddt", "rmsd", "novelty"];

// 티어 한 개의 퍼널 행. soluprot.json / af2_scores.json 은 파이프라인이 쓰는
// 계약 필드(scores, passed_ids / candidate_ids, selected_ids)를 그대로 읽는다.
export function buildFunnelRow(tier, soluprot, af2) {
  const scores = (soluprot && soluprot.scores) || {};
  return {
    tier: String(tier),
    designed: Object.keys(scores).length,
    soluprot: Array.isArray(soluprot?.passed_ids) ? soluprot.passed_ids.length : 0,
    af2: Array.isArray(af2?.candidate_ids) ? af2.candidate_ids.length : 0,
    af2_selected: Array.isArray(af2?.selected_ids) ? af2.selected_ids.length : 0,
  };
}

export function renderFunnel(host, rows) {
  host.replaceChildren();
  if (!rows.length) {
    host.appendChild(Object.assign(document.createElement("p"), {
      className: "note", textContent: "이 실행에는 티어 결과가 없습니다.",
    }));
    return;
  }
  const max = Math.max(...rows.map((r) => Math.max(r.designed, 1)));
  const bar = document.createElement("div");
  bar.className = "funnel";
  for (const row of rows) {
    for (const key of ["designed", "soluprot", "af2", "af2_selected"]) {
      const col = document.createElement("i");
      col.style.height = `${Math.max(6, (row[key] / max) * 100)}%`;
      col.title = `${row.tier} ${key}: ${row[key]}`;
      bar.appendChild(col);
    }
  }
  host.appendChild(bar);
  const table = document.createElement("table");
  const head = table.insertRow();
  for (const key of ["tier", ...Object.keys(rows[0]).filter((k) => k !== "tier")]) {
    head.appendChild(Object.assign(document.createElement("th"), { textContent: key }));
  }
  for (const row of rows) {
    const tr = table.insertRow();
    for (const key of ["tier", "designed", "soluprot", "af2", "af2_selected"]) {
      tr.insertCell().textContent = String(row[key]);
    }
  }
  host.appendChild(table);
}

export async function loadFunnel(runId, artifacts) {
  const tiers = new Map();
  for (const item of artifacts) {
    const path = String(item.path || item.name || "");
    const match = path.match(/tiers\/([0-9.]+)\/(soluprot|af2_scores)\.json$/);
    if (!match) continue;
    const [, tier, kind] = match;
    if (!tiers.has(tier)) tiers.set(tier, {});
    tiers.get(tier)[kind] = path;
  }
  const rows = [];
  for (const [tier, paths] of [...tiers.entries()].sort()) {
    const fetchJson = async (path) => {
      if (!path) return null;
      try {
        const out = await callTool("pipeline.read_artifact", { run_id: path ? runId : "", path, max_bytes: 400000 });
        return out && out.text ? JSON.parse(out.text) : null;
      } catch { return null; }
    };
    const soluprot = await fetchJson(paths.soluprot);
    const af2 = await fetchJson(paths.af2_scores);
    rows.push(buildFunnelRow(tier, soluprot, af2));
  }
  return rows;
}

// 비교 결과의 최상위 스칼라만 카드로 꺼낸다. 구조는 배포본마다 조금씩 다르므로
// 모르는 키를 버리지 않고 남은 것만 정중히 보여준다.
export function summarizeCompare(result) {
  const cards = [];
  const walk = (obj, prefix = "") => {
    for (const [key, value] of Object.entries(obj || {})) {
      if (key === "summary") continue;
      const label = prefix ? `${prefix}.${key}` : key;
      if (value != null && typeof value !== "object") cards.push({ label, value: String(value) });
      else if (value != null && typeof value === "object" && !Array.isArray(value)) walk(value, label);
    }
  };
  walk(result);
  return cards;
}

export function renderHitList(host, rows) {
  host.replaceChildren();
  if (!Array.isArray(rows) || !rows.length) {
    host.appendChild(Object.assign(document.createElement("p"), {
      className: "note", textContent: "히트리스트가 비어 있습니다.",
    }));
    return;
  }
  const table = document.createElement("table");
  const head = table.insertRow();
  for (const key of HIT_COLUMNS) head.appendChild(Object.assign(document.createElement("th"), { textContent: key }));
  for (const row of rows) {
    const tr = table.insertRow();
    for (const key of HIT_COLUMNS) {
      const cell = tr.insertCell();
      const value = row[key];
      cell.textContent = value == null ? "-" : String(value);
    }
  }
  host.appendChild(table);
}

export async function loadHitList(runId) {
  const out = await callTool("pipeline.get_hit_list", { run_id: runId, limit: 20 });
  if (out && out.error) throw new Error(out.error);
  return out.rows || out.hits || out.items || [];
}
```

- [ ] **Step 4: 녹색 확인** → `node --test tests/guided-results.test.js` PASS
- [ ] **Step 5: facade 연결** — 실행 선택 시: `const arts = (await callTool("pipeline.list_artifacts", { run_id, max_depth: 6, limit: 400 })).artifacts || []` → `loadFunnel(runId, arts).then((rows) => renderFunnel(funnelHost, rows))`, `loadHitList(runId).then((rows) => renderHitList(hitHost, rows))`. `compareBtn` → `callTool("pipeline.compare_runs", { run_id: 선택된 실행, baseline_run_id: compareBaseline.value })` → `summarizeCompare` → 카드 렌더. `compareBaseline` 옵션은 좌측 실행 목록과 함께 채운다.
- [ ] **Step 6: 커밋**

```bash
git add frontend/guided/results.js frontend/tests/guided-results.test.js frontend/guided.js frontend/guided.css
git commit -m "feat(rapid-guided): Results tab with tier funnel, hit list and run comparison"
```

---

### Task 7: Evidence 탭

**Files:**
- Create: `frontend/guided/evidence.js`
- Modify: `frontend/guided.js`, `frontend/guided.css`

- [ ] **Step 1: `frontend/guided/evidence.js` 구현** — 계획이 있을 때만 의미가 있으므로 plan.js의 `state`를 import해 읽는다.

```js
import { state } from "./plan.js";
import { evidenceNode } from "./plan.js";

export function evidenceItems(plan) {
  const items = [];
  for (const decision of plan?.decisions || []) {
    for (const ev of decision.evidence || []) {
      items.push({ field: decision.field, ...ev });
    }
  }
  return items;
}

export function renderEvidenceView(host, plan) {
  host.replaceChildren();
  if (!plan) {
    host.className = "empty";
    host.textContent = "계획을 생성하면 근거가 여기 모입니다.";
    return;
  }
  host.className = "";
  const kinds = [["internal_measurement", "측정"], ["literature", "문헌"], ["assumption", "가정"]];
  const filterRow = document.createElement("div");
  filterRow.className = "evfilter";
  for (const [kind, label] of kinds) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "ghost";
    chip.dataset.kind = kind;
    chip.textContent = label;
    chip.addEventListener("click", () => {
      for (const node of host.querySelectorAll(".ev")) {
        node.classList.toggle("hidden", chip.dataset.kind !== "all"
          && !node.classList.contains(`kind-${chip.dataset.kind}`));
      }
    });
    filterRow.appendChild(chip);
  }
  host.appendChild(filterRow);

  const objectiveStatus = plan.objective_status || [];
  if (objectiveStatus.length) {
    const box = document.createElement("details");
    box.className = "evidence";
    box.appendChild(Object.assign(document.createElement("summary"), { textContent: `평가 불가/미검증 목표 ${objectiveStatus.length}건` }));
    for (const entry of objectiveStatus) {
      const node = document.createElement("div");
      node.className = "ev";
      node.appendChild(Object.assign(document.createElement("b"), { textContent: entry.objective }));
      node.appendChild(Object.assign(document.createElement("p"), {
        className: "rationale", textContent: [entry.detail, entry.to_enable].filter(Boolean).join(" 활성화하려면: "),
      }));
      box.appendChild(node);
    }
    host.appendChild(box);
  }

  for (const item of evidenceItems(plan)) {
    const node = evidenceNode(item);
    node.prepend(Object.assign(document.createElement("b"), { textContent: `${item.field} · ` }));
    host.appendChild(node);
  }
}
```

- [ ] **Step 2: facade 연결** — `generatePlan` 성공 후(plan.js의 state가 채워진 뒤) `renderEvidenceView(document.getElementById("evidenceView"), state.plan)` 호출을 facade에 추가.
- [ ] **Step 3: 테스트 + 커밋** — `node --test tests/guided.test.js` (source 어서션들이 plan.js에서 여전히 통과) 후:

```bash
git add frontend/guided/evidence.js frontend/guided.js frontend/guided.css
git commit -m "feat(rapid-guided): Evidence tab aggregating decision evidence and objective status"
```

---

### Task 8: Structure 탭 — 3D + 잔기 피커

**Files:**
- Create: `frontend/guided/structure.js`
- Create: `frontend/tests/guided-structure.test.js`
- Modify: `frontend/guided.js`, `frontend/guided.css`

- [ ] **Step 1: 실패하는 테스트**

```js
// frontend/tests/guided-structure.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { structureFiles, sequenceByChainFromPdb } from "../guided/structure.js";

test("structureFiles keeps only viewable structure artifacts", () => {
  const files = structureFiles([
    { path: "tiers/50/af2/ranked_0.pdb", type: "file" },
    { path: "msa/result.a3m", type: "file" },
    { path: "report.md", type: "file" },
    { path: "ligand.sdf", type: "file" },
  ]);
  assert.deepEqual(files.map((f) => f.path), ["tiers/50/af2/ranked_0.pdb", "ligand.sdf"]);
});

test("sequenceByChainFromPdb parses per-chain CA sequences with resseq", () => {
  const pdb = [
    "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C",
    "ATOM      2  CA  CYS A   2       1.000   0.000   0.000  1.00 20.00           C",
    "ATOM      3  CA  GLY B   1       2.000   0.000   0.000  1.00 20.00           C",
  ].join("\n");
  const chains = sequenceByChainFromPdb(pdb);
  assert.equal(chains.A.seq, "AC");
  assert.deepEqual(chains.A.resseqs, [1, 2]);
  assert.equal(chains.B.seq, "G");
});
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: `frontend/guided/structure.js` 구현**

```js
const STRUCTURE_FORMATS = { pdb: "pdb", cif: "cif", mmcif: "cif", ent: "pdb", sdf: "sdf" };
const THREE_TO_ONE = {
  ALA:"A", ARG:"R", ASN:"N", ASP:"D", CYS:"C", GLN:"Q", GLU:"E", GLY:"G",
  HIS:"H", ILE:"I", LEU:"L", LYS:"K", MET:"M", PHE:"F", PRO:"P", SER:"S",
  THR:"T", TRP:"W", TYR:"Y", VAL:"V", MSE:"M",
};

export function structureFiles(artifacts) {
  return (artifacts || []).filter((item) => {
    if (String(item.type || "file") !== "file") return false;
    const ext = String(item.path || item.name || "").toLowerCase().split(".").pop();
    return Boolean(STRUCTURE_FORMATS[ext]);
  });
}

export function sequenceByChainFromPdb(pdbText) {
  // CA 만 읽는다. HETATM 의 CA 는 칼슘일 수 있다 (guided.js 의 주석과 같은 함정).
  const chains = {};
  const seen = new Set();
  for (const line of String(pdbText || "").split(/\r?\n/)) {
    if (!line.startsWith("ATOM")) continue;
    if (line.slice(12, 16).trim() !== "CA") continue;
    const chain = line[21] || "A";
    const key = line.slice(21, 27);
    if (seen.has(key)) continue;
    seen.add(key);
    const resseq = parseInt(line.slice(22, 26).trim(), 10);
    const aa = THREE_TO_ONE[line.slice(17, 20).trim().toUpperCase()] || "X";
    chains[chain] = chains[chain] || { seq: "", resseqs: [] };
    chains[chain].seq += aa;
    chains[chain].resseqs.push(resseq);
  }
  return chains;
}

export function renderStructureTab(files, { readArtifact }) {
  const listHost = document.getElementById("structureFiles");
  const viewerHost = document.getElementById("structureViewer");
  listHost.replaceChildren();
  if (!files.length) {
    listHost.className = "empty";
    listHost.textContent = "이 실행에는 3D 구조 파일이 없습니다.";
    return;
  }
  listHost.className = "";
  for (const item of files) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "artifact";
    row.appendChild(Object.assign(document.createElement("span"), {
      className: "apath", textContent: item.path || item.name,
    }));
    row.addEventListener("click", async () => {
      viewerHost.replaceChildren(Object.assign(document.createElement("div"), {
        className: "empty", textContent: "불러오는 중…",
      }));
      const out = await readArtifact(item.path || item.name);
      const text = out?.text || "";
      viewerHost.replaceChildren();
      render3dFromMonitor(text, STRUCTURE_FORMATS[String(item.path).toLowerCase().split(".").pop()], viewerHost);
      renderResidueStrip(text, viewerHost);
    });
    listHost.appendChild(row);
  }
}

function render3dFromMonitor(text, format, host) {
  // 3D 렌더는 monitor.js 의 render3d 를 재사용한다 (같은 뷰어, 같은 스타일).
  import("./monitor.js").then(({ render3d }) => render3d(text, format, host));
}

function renderResidueStrip(pdbText, viewerHost) {
  const stripHost = document.getElementById("residueStripHost") || viewerHost;
  const chains = sequenceByChainFromPdb(pdbText);
  const strip = document.getElementById("residueStrip");
  strip.replaceChildren();
  const selection = document.getElementById("residueSelection");
  selection.replaceChildren();
  for (const [chain, info] of Object.entries(chains)) {
    const row = document.createElement("div");
    row.className = "resrow";
    row.appendChild(Object.assign(document.createElement("b"), { textContent: chain }));
    info.seq.split("").forEach((aa, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = aa;
      btn.title = `${chain}${info.resseqs[index]}`;
      btn.addEventListener("click", () => {
        btn.classList.toggle("is-sel");
        const chip = Object.assign(document.createElement("span"), {
          className: "chip", textContent: `${chain}${info.resseqs[index]}${aa}`,
        });
        if (btn.classList.contains("is-sel")) selection.appendChild(chip);
        else chip.remove();
        highlightResidue(viewerHost, chain, info.resseqs[index], btn.classList.contains("is-sel"));
      });
      row.appendChild(btn);
    });
    strip.appendChild(row);
  }
}

function highlightResidue(viewerHost, chain, resseq, on) {
  const viewer = viewerHost.querySelector("canvas")?.__viewer
    || window.__guidedViewer;
  if (!viewer) return;
  const selector = { chain, resi: resseq };
  if (on) viewer.addStyle(selector, { sphere: { radius: 1.2, color: "orange" } });
  else viewer.removeStyle(selector);
  viewer.render();
}
```

(viewer 인스턴스 접근을 위해 Task 2에서 이동한 `render3d`는 `window.__guidedViewer = viewer` 한 줄을 추가한다 — 계획상 이 한 줄 변경은 monitor.js의 render3d에 포함된다.)

- [ ] **Step 4: 녹색 확인** → `node --test tests/guided-structure.test.js tests/guided.test.js` PASS
- [ ] **Step 5: facade 연결** — 실행 선택 시 `structureFiles(arts)` → `renderStructureTab(files, { readArtifact: (path) => callTool("pipeline.read_artifact", { run_id, path, max_bytes: 4000000 }) })`. HTML의 `structureViewer` 아래에 `<div id="residueStrip" class="residuestrip"></div>` 포함(Task 3 HTML에 이미 있음).
- [ ] **Step 6: 커밋**

```bash
git add frontend/guided/structure.js frontend/tests/guided-structure.test.js frontend/guided/monitor.js frontend/guided.js frontend/guided.css
git commit -m "feat(rapid-guided): Structure tab with 3D viewer, residue strip and selection chips"
```

---

### Task 9: 상단바 칩

**Files:**
- Modify: `frontend/guided.js`, `frontend/guided.css`

- [ ] **Step 1: facade에 칩 렌더 추가** (순수 로직은 monitor.js의 mapStatusStageToStep 재사용):

```js
import { mapStatusStageToStep } from "./guided/monitor.js";

function renderTopbarChips(info) {
  const host = document.getElementById("topbarChips");
  host.replaceChildren();
  if (!info || info.poll_stalled) return;
  const chip = (text, cls = "") => {
    const node = document.createElement("span");
    node.className = `chip${cls ? ` ${cls}` : ""}`;
    node.textContent = text;
    return node;
  };
  host.append(
    chip(runState.runId || "-"),
    chip(`${mapStatusStageToStep(info.stage) || info.stage || "-"}`),
    chip(info.state || "-", info.state === "done" ? "okchip" : ""),
  );
}
```

비용 칩은 넣지 않는다 — 비용은 근거(출처/범위)가 붙는 값이라 계획 카드의 cost bar(출처 표시 유지)에서만 보여주는 것이 스펙의 provenance 규칙과 맞다.

- [ ] **Step 2: 커밋**

```bash
git add frontend/guided.js frontend/guided.css
git commit -m "feat(rapid-guided): topbar run chips driven by the polling status"
```

---

### Task 10: 전체 검증 + dev 배포

- [ ] **Step 1: 전체 프런트 테스트**

Run: `cd frontend && node --test`
Expected: 기존 통과 분 모두 유지 + 신규 테스트 통과 (이 작업 전부터 있던 58건의 기존 실패는 본 계획과 무관 — HEAD와 동일한지 `git stash` 비교로 확인)

- [ ] **Step 2: 빌드**

Run: `cd /opt/protein_pipeline-work && npm --prefix frontend run build`
Expected: `✓ built` (vite input에 guided.html 이미 등록)

- [ ] **Step 3: 수동 스모크 체크리스트 (dev 배포 후)**

1. `https://rapid-dev.kbiofoundry.kr/guided.html` 로그인 → 좌측 실행 목록 표시
2. 목적 카드 선택 → 중앙에 단계/비용바
3. 목표 슬라이더 → 계획 생성 → 결정/근거/경고 표시 → Evidence 탭 동기화
4. 대화로 수정 제안 → 적용 → 승인 → 실행 → Run 탭 진행바 상승
5. 완료 실행 선택 → Results 퍼널/히트리스트, Structure 3D + 잔기 클릭
6. 취소 버튼, 폴링 중단(네트워크 차단 3회) 확인

- [ ] **Step 4: 커밋 + push**

```bash
git add -A frontend/guided frontend/guided.js frontend/guided.html frontend/guided.css frontend/tests
git commit -m "feat(rapid-guided): single-screen console polish and verification"
git push origin HEAD:develop --force-with-lease
```

- [ ] **Step 5: CI 확인** — `gh run watch` → dev healthz + 화면 확인. 롤백: `git revert` 후 재push.

---

## Self-Review 기록

- **스펙 커버**: 3페인/4탭(Task 3), 실행 목록(4), Run 진행·취소·리포트(5), 퍼널·히트·비교(6), 근거(Evidence, 7), 3D+피커(8), 폴링 백오프·칩(5, 9→Task 5에 통합), 기존 테스트 유지(Task 2) — 스펙 전 섹션 커버. Compare Studio 전체는 스펙대로 2차(제외).
- **플레이스홀더**: 없음 — 신규 코드는 전문 수록, 이동 코드는 현재 줄 번호로 명시.
- **타입 일치**: `buildFunnelRow`/`summarizeCompare`/`structureFiles`/`sequenceByChainFromPdb`/`nextPollDelayMs` 서명이 테스트와 본문에서 동일.
