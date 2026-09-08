# 좌측 탭 껍질 + 모델 탭 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** guided 콘솔 좌측 레일에 탭 내비게이션(실행 목록 | 모델)을 두고, 모델 탭에서 `pipeline.list_models`의 목적 경로·목표별 평가자 상태·모델 카탈로그를 보여준다.

**Architecture:** 프런트 전용. 껍질은 `.side`에 탭 스트립 + 기존 콘텐츠를 `#sideRuns`로 래핑 + `#sideModels` 패널 추가. 모델 탭은 새 모듈 `guided/models.js`(council.js 패턴: 순수 모델 + 렌더)와 탭 첫 진입 1회 로드 캐시.

**Tech Stack:** vanilla ES modules, `node --test`, vite. 백엔드 변경 없음.

**Spec:** `docs/specs/2026-09-07-guided-side-tabs-models-design.md`

**주의:** 관련 없는 dirty 파일이 많다 — 지정한 파일만 `git add`. 프런트 테스트 `cd frontend && node --test …`, 빌드 `npm --prefix frontend run build`.

---

### Task 1: 탭 껍질 (Shell)

**Files:**
- Modify: `frontend/guided.html` (~33-53행, `.side` 내부)
- Modify: `frontend/guided.js` (브라우저 전용 초기화 블록)
- Modify: `frontend/guided.css`
- Test: `frontend/tests/guided-side-tabs.test.js`

- [ ] **Step 1: 실패하는 테스트** — `frontend/tests/guided-side-tabs.test.js` (전문 교체):

```js
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { showSideTab, SIDE_TAB_KEY } = await import("../guided.js");

test("side tab strip exists with runs and models tabs", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('class="sidetabs"'));
  assert.ok(html.includes('data-sidetab="runs"'));
  assert.ok(html.includes('data-sidetab="models"'));
  assert.ok(html.includes('id="sideRuns"'));
  assert.ok(html.includes('id="sideModels"'));
});

test("existing side content is wrapped in sideRuns", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  const start = html.indexOf('id="sideRuns"');
  const end = html.indexOf('id="sideModels"');
  const between = html.slice(start, end);
  assert.ok(between.includes('id="runList"'), "runList lives inside sideRuns");
  assert.ok(between.includes('id="monitorList"'), "ops block lives inside sideRuns");
});

test("showSideTab toggles panels and persists the choice", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('localStorage.setItem(SIDE_TAB_KEY'), "choice must persist");
  assert.ok(src.includes('localStorage.getItem(SIDE_TAB_KEY'), "choice must restore");
  assert.ok(src.includes("initSideTabs"), "init function must exist");
  assert.ok(/initSideTabs\(\);/.test(src), "init must be called");
});

test("an unknown stored tab falls back to runs", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"runs"') && src.includes('"models"'),
            "only two tab names are accepted");
});
```

NOTE: `guided.js`에서 `SIDE_TAB_KEY`를 export 해야 한다 — `export const SIDE_TAB_KEY = "kbf.guided.sidetab";` (상수 export는 node import용; `showSideTab`도 export). facade는 기존 top-level 브라우저 전용 블록 패턴 유지.

- [ ] **Step 2: 실패 확인** — `cd frontend && node --test tests/guided-side-tabs.test.js` → FAIL

- [ ] **Step 3: guided.html 교체** — `<aside class="side">` 내부 전체를:

```html
      <aside class="side">
        <nav class="sidetabs" role="tablist" aria-label="좌측 패널">
          <button class="sidetab active" data-sidetab="runs" role="tab" aria-selected="true" type="button">실행 목록</button>
          <button class="sidetab" data-sidetab="models" role="tab" aria-selected="false" type="button">모델</button>
        </nav>
        <div id="sideRuns">
          <section class="block">
            <h3>실행</h3>
            <button id="newDesignBtn" class="ghost newrun" type="button">＋ 새 설계</button>
            <div id="runList" class="runlist empty">실행을 불러오는 중…</div>
          </section>
          <section class="block">
            <h3>운영</h3>
            <nav class="oplinks" aria-label="운영">
              <a href="./index.html">기존 콘솔(전체 기능)</a>
              <a href="./index.html" data-op="runpod">RunPod Admin</a>
              <a href="./index.html" data-op="mcp">MCP 설정</a>
            </nav>
            <div id="connections" class="conns"></div>
            <button id="probeBtn" class="ghost">워커 확인</button>
            <div id="monitorList" class="empty">확인을 누르면 표시됩니다.</div>
          </section>
        </div>
        <div id="sideModels" class="hidden modelstab" role="tabpanel"></div>
      </aside>
```

- [ ] **Step 4: guided.js 추가** — 브라우저 전용 초기화 블록(`typeof document !== "undefined"` 내부, `initLiteratureSearch();` 근처)에:

```js
  initSideTabs();
```

그리고 모듈 스코프(브라우저 전용 블록 바깥, 상수 근처)에:

```js
export const SIDE_TAB_KEY = "kbf.guided.sidetab";
const SIDE_TAB_NAMES = ["runs", "models"];
let sideTabWired = false;

// 좌측 탭은 기능 패널을 갈아끼운다. 중앙·우측 워크플로와는 무관하다 —
// 실행 선택·폴링·계획 흐름을 건드리지 않는다.
function showSideTab(name) {
  const wanted = SIDE_TAB_NAMES.includes(name) ? name : "runs";
  for (const tab of document.querySelectorAll(".sidetab")) {
    const on = tab.dataset.sidetab === wanted;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", String(on));
  }
  document.getElementById("sideRuns").classList.toggle("hidden", wanted !== "runs");
  document.getElementById("sideModels").classList.toggle("hidden", wanted !== "models");
  localStorage.setItem(SIDE_TAB_KEY, wanted);
  if (wanted === "models" && typeof window.__modelsTabLoad === "function") {
    window.__modelsTabLoad();
  }
}

function initSideTabs() {
  if (sideTabWired) return;
  sideTabWired = true;
  for (const tab of document.querySelectorAll(".sidetab")) {
    tab.addEventListener("click", () => showSideTab(tab.dataset.sidetab));
  }
  let saved = null;
  try { saved = localStorage.getItem(SIDE_TAB_KEY); } catch { /* 저장값이 깨졌으면 기본값 */ }
  showSideTab(saved || "runs");
}
```

NOTE: `showSideTab`/`SIDE_TAB_KEY`는 node 테스트가 import하므로 브라우저 전용 블록 **바깥**에 두되, `showSideTab` 내부 DOM 접근은 함수 안이므로 node import 시점엔 안전하다(호출만 하지 않으면 됨). `window.__modelsTabLoad`는 Task 2에서 채운다(껍질은 훅만 제공).

- [ ] **Step 5: guided.css 추가:**

```css
.sidetabs { display: flex; gap: 4px; border-bottom: 1px solid var(--rule); margin-bottom: 14px; }
.sidetab { font: inherit; font-size: 13px; padding: 7px 10px; cursor: pointer; color: var(--quiet);
  background: transparent; border: 0; border-bottom: 2px solid transparent; }
.sidetab:hover { color: var(--ink); }
.sidetab.active { color: var(--ink); border-bottom-color: var(--action); }
```

- [ ] **Step 6: 통과 확인**

```bash
cd frontend && node --test tests/guided-side-tabs.test.js tests/guided.test.js
cd /opt/protein_pipeline-work && npm --prefix frontend run build
```
Expected: 76 tests pass (5 + 71), build ✓.

- [ ] **Step 7: 커밋**

```bash
git add frontend/guided.html frontend/guided.js frontend/guided.css frontend/tests/guided-side-tabs.test.js
git commit -m "feat(rapid-guided): side tab shell for the left rail"
```

---

### Task 2: 모델 탭

**Files:**
- Create: `frontend/guided/models.js`
- Create: `frontend/tests/guided-models.test.js`
- Modify: `frontend/guided.js` — `window.__modelsTabLoad` 연결
- Modify: `frontend/guided.css` — `.modelstab` 간격

- [ ] **Step 1: 실패하는 테스트** — `frontend/tests/guided-models.test.js` (전문 교체):

```js
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
    thermomp_ddg: { endpoint: "http://…:18114", display_name: "ThermoMPNN ΔΔG",
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
  assert.ok(JSON.stringify(h1.children).includes("다시 시도") || h1.children.some((c) => c.tagName === "BUTTON"));
});

test("the facade loads the models tab on first entry", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes("__modelsTabLoad"), "shell hook must be filled");
  assert.ok(src.includes('from "./guided/models.js"'));
});
```

- [ ] **Step 2: 실패 확인** — `cd frontend && node --test tests/guided-models.test.js` → FAIL (module missing)

- [ ] **Step 3: `frontend/guided/models.js`** (전문 교체):

```js
// frontend/guided/models.js — 모델 탭. 레지스트리(목적 경로·목표 평가 상태·모델
// 카탈로그)를 pipeline.list_models 로 읽어 보여준다. 정적 데이터라 탭 첫 진입
// 1회 로드 후 캐시한다. 목적 목록을 프런트에 박지 않는다 — 레지스트리가 진실이다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function modelsTabModels(payload) {
  const data = payload && typeof payload === "object" ? payload : {};
  const measured = new Set(data.measurable_objectives || []);
  const unvalidated = new Set(data.runnable_but_unvalidated_objectives || []);
  const keys = [...new Set([...measured, ...unvalidated])];
  return {
    purposes: (Array.isArray(data.purposes) ? data.purposes : [])
      .filter((p) => p && typeof p === "object")
      .map((p) => ({
        purpose: String(p.purpose || ""),
        executable: Boolean(p.executable),
        validated: Boolean(p.validated),
      })),
    objectives: keys.map((key) => ({
      key: String(key),
      state: measured.has(key) ? "measured"
        : unvalidated.has(key) ? "unvalidated" : "none",
    })),
    models: Object.entries(data.models || {}).map(([id, m]) => {
      const item = m && typeof m === "object" ? m : {};
      const access = (item.extra && item.extra.access) || {};
      return {
        id: String(id),
        name: String(item.display_name || id),
        endpoint: String(item.endpoint || "").slice(0, 40),
        portalOnly: Boolean(access.portal_mcp) && !access.direct_client,
      };
    }),
  };
}

export function renderModels(host, { state = "idle", model = null, message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "모델 레지스트리를 불러오는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "레지스트리를 불러오지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    retry.addEventListener("click", () => { if (typeof window !== "undefined" && window.__modelsTabLoad) window.__modelsTabLoad(true); });
    host.appendChild(retry);
    return;
  }
  if (state === "idle") {
    host.appendChild(el("p", "note", "모델 탭입니다."));
    return;
  }
  const data = model || { purposes: [], objectives: [], models: [] };

  host.appendChild(el("h3", "", "설계 목적 경로"));
  for (const purpose of data.purposes) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.append(el("span", "name", purpose.purpose));
    if (purpose.validated) head.appendChild(el("span", "okchip", "검증됨"));
    else if (purpose.executable) head.appendChild(el("span", "warnchip", "실행 가능·미검증"));
    else head.appendChild(el("span", "badchip", "실행 불가"));
    row.appendChild(head);
    host.appendChild(row);
  }

  host.appendChild(el("h3", "", "목표별 평가자 상태"));
  for (const objective of data.objectives) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.append(el("span", "name", objective.key));
    if (objective.state === "measured") head.appendChild(el("span", "okchip", "측정됨"));
    else if (objective.state === "unvalidated") head.appendChild(el("span", "warnchip", "평가자 있으나 미검증"));
    else head.appendChild(el("span", "chip", "평가자 없음"));
    row.appendChild(head);
    host.appendChild(row);
  }

  host.appendChild(el("h3", "", "모델 카탈로그"));
  for (const model2 of data.models) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.append(el("span", "name", model2.name));
    if (model2.portalOnly) head.appendChild(el("span", "chip", "포털 경유"));
    row.appendChild(head);
    if (model2.endpoint) {
      row.appendChild(el("p", "note", model2.endpoint));
    }
    host.appendChild(row);
  }
}

export async function requestModels() {
  const out = await callTool("pipeline.list_models", {});
  if (out && out.error) throw new Error(out.error);
  return out;
}
```

- [ ] **Step 4: 통과 확인** — `cd frontend && node --test tests/guided-models.test.js` → PASS (5)

- [ ] **Step 5: guided.js 연결** — 두 곳:

1. import (기존 `./guided/` import 근처):
```js
import { renderModels, requestModels, modelsTabModels } from "./guided/models.js";
```
(`modelsTabModels`는 facade에서 미사용이면 import에서 뺀다 — 렌더만 필요.)
2. 브라우저 전용 초기화 블록(`initSideTabs();` 근처):
```js
  window.__modelsTabLoad = (force = false) => {
    const host = document.getElementById("sideModels");
    if (host.dataset.loaded && !force) return;   // 첫 진입 1회 로드
    if (host.dataset.loading) return;            // 중복 요청 억제
    host.dataset.loading = "1";
    renderModels(host, { state: "loading" });
    requestModels().then((payload) => {
      host.dataset.loaded = "1";
      delete host.dataset.loading;
      renderModels(host, { state: "done", model: modelsTabModels(payload) });
    }).catch((error) => {
      delete host.dataset.loading;
      renderModels(host, { state: "error", message: `레지스트리를 불러오지 못했습니다: ${errorText(error)}` });
    });
  };
```
(주의: `modelsTabModels`를 여기서 쓰므로 import에 포함. `showSideTab`의 `window.__modelsTabLoad()` 호출은 인자 없음 → force=undefined → falsy → 캐시 존중.)

- [ ] **Step 6: guided.css — `.modelstab` 규칙:**

```css
.modelstab { padding-top: 4px; display: grid; gap: 6px; }
.modelstab h3 { margin-top: 8px; }
```

- [ ] **Step 7: 전체 확인**

```bash
cd frontend && node --test tests/guided-models.test.js tests/guided-side-tabs.test.js tests/guided.test.js
cd /opt/protein_pipeline-work && npm --prefix frontend run build
```
Expected: 81 tests pass (5 + 5 + 71), build ✓.

- [ ] **Step 8: 커밋**

```bash
git add frontend/guided/models.js frontend/tests/guided-models.test.js frontend/guided.js frontend/guided.css
git commit -m "feat(rapid-guided): models tab with purpose routes, objective states and catalog"
```

---

### Task 3: 전체 검증 + dev 배포

- [ ] **Step 1: 프런트 전체**

```bash
cd frontend && node --test tests/guided-topbar.test.js tests/guided.test.js tests/guided-sidebar.test.js tests/guided-progress.test.js tests/guided-results.test.js tests/guided-evidence.test.js tests/guided-structure.test.js tests/guided-council.test.js tests/guided-layout.test.js tests/guided-literature.test.js tests/guided-side-tabs.test.js tests/guided-models.test.js
```
Expected: PASS (157 tests = 147 + 5 + 5)

```bash
node --test frontend/tests/app-syntax.test.js frontend/tests/auth-session.test.js frontend/tests/auth.test.js frontend/tests/login-bootstrap.test.js frontend/tests/mcp-tab.test.js frontend/tests/runpod-admin.test.js && (cd frontend && node --test tests/logout-bridge.test.js)
```
Expected: fail 0

- [ ] **Step 2: 백엔드 회귀** (변경 없음 확인)

```bash
PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_http_server_auth.py pipeline-mcp/tests/test_mcp_http_route.py pipeline-mcp/tests/test_oidc_auth.py pipeline-mcp/tests/test_session_auth.py pipeline-mcp/tests/test_runpod_admin.py pipeline-mcp/tests/test_plan_council.py pipeline-mcp/tests/test_literature.py -q
```
Expected: PASS (97)

- [ ] **Step 3: 빌드** — `npm --prefix frontend run build` → `✓ built`

- [ ] **Step 4: push + CI**

```bash
git fetch origin develop --quiet
git log --oneline HEAD..origin/develop | wc -l   # 0 이어야 함
git push origin HEAD:develop
gh run watch --exit-status $(gh run list --branch develop --limit 1 --json databaseId --jq '.[0].databaseId')
```

- [ ] **Step 5: 배포 확인 + 스모크**

```bash
curl -sS http://127.0.0.1:18087/healthz
curl -sSI https://rapid.example.internal/guided.html | head -1
```

브라우저: guided.html → 좌측 상단 탭 스트립 확인 → 모델 탭 클릭 → 목적 경로(칩 3색)·목표별 평가자 상태·모델 카탈로그 표시 → 실행 목록 탭 복귀 → 기존 실행 목록/운영 블록 그대로인지 확인 → 새로고침 후 탭 유지 확인.

롤백: `git revert` 후 재push.
