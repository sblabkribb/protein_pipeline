# 좌측 탭 3차: 템플릿·프로젝트 + 스킬 겹침 수정 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 좌측 탭 카드의 좁은 화면 텍스트 겹침을 고치고, 연결 탭에 재실측 버튼을 넣고, 템플릿·프로젝트 탭을 추가한다.

**Architecture:** 겹침은 CSS 한 규칙(`.modelstab .skill { display: block }`). 템플릿·프로젝트 탭은 기존 도구 재사용(프런트만) — 템플릿은 `list_models` purposes + 중앙 목적 선택 헬퍼, 프로젝트는 `list_projects`/`list_rounds` 드릴다운.

**Tech Stack:** vanilla ES modules, `node --test`, vite. 백엔드 변경 없음.

**Spec:** `docs/specs/2026-09-07-guided-side-tabs-templates-projects-design.md`

**주의:** 지정한 파일만 `git add`. 프런트 테스트 `cd frontend && node --test`, 빌드 `npm --prefix frontend run build`.

---

### Task 1: 겹침 수정 + 연결 재실측 버튼

**Files:**
- Modify: `frontend/guided.css` (`.modelstab .skill` 규칙), `frontend/guided/connections.js` (done 상단 버튼)
- Modify: `frontend/tests/guided-connections.test.js`, `frontend/tests/guided-models.test.js`

- [ ] **Step 1: 실패하는 테스트 추가**

`guided-models.test.js` 끝에:
```js
test("side tab cards stack vertically so narrow rails do not overlap text", () => {
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  assert.ok(css.includes(".modelstab .skill { display: block"), "cards must not be flex rows");
});
```

`guided-connections.test.js`의 done 렌더 테스트에 추가:
```js
  assert.ok(html.includes("다시 실측"), "done state offers a re-probe button");
```

- [ ] **Step 2: 실패 확인** — `cd frontend && node --test tests/guided-models.test.js tests/guided-connections.test.js` → FAIL

- [ ] **Step 3: 구현**

`guided.css` — `.modelstab` 규칙 아래:
```css
.modelstab .skill { display: block; padding: 8px 10px; }
```

`frontend/guided/connections.js` — `renderConnectionsTab`의 done 경로, 첫 블록("엔드포인트 실측" h3) **앞**에:
```js
  const reprobe = document.createElement("button");
  reprobe.type = "button";
  reprobe.className = "ghost";
  reprobe.textContent = "다시 실측";
  reprobe.addEventListener("click", () => {
    if (typeof window !== "undefined" && window.__connectionsTabLoad) window.__connectionsTabLoad(true);
  });
  host.appendChild(reprobe);
```

- [ ] **Step 4: 통과** — 두 파일 PASS; `npm --prefix frontend run build` ✓

- [ ] **Step 5: 커밋**

```bash
git add frontend/guided.css frontend/guided/connections.js frontend/tests/guided-connections.test.js frontend/tests/guided-models.test.js
git commit -m "fix(rapid-guided): stack side-tab cards and add a connections re-probe button"
```

---

### Task 2: 템플릿 탭

**Files:**
- Create: `frontend/guided/templates.js`, `frontend/tests/guided-templates.test.js`
- Modify: `frontend/guided.html` (sidetab + `#sideTemplates`), `frontend/guided.js` (SIDE_TAB_NAMES + 훅 + `startFromPurpose`), `frontend/guided.css`(불필요 시 제외)

- [ ] **Step 1: 실패하는 테스트** — `guided-templates.test.js` (문서 스텁 패턴):

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

const { templateCardModels, renderTemplatesTab } = await import("../guided/templates.js");

const PAYLOAD = {
  purposes: [
    { purpose: "monomer_solubility_redesign", display_name_ko: "단일체 용해도 리디자인",
      executable: true, validated: true, unvalidated_stages: [] },
    { purpose: "binder_design", display_name_ko: "바인더 설계",
      executable: true, validated: false, unvalidated_stages: ["af2"] },
  ],
};

test("templateCardModels absorbs routes", () => {
  const models = templateCardModels(PAYLOAD);
  assert.equal(models[0].name, "단일체 용해도 리디자인");
  assert.equal(models[1].state, "unvalidated");
  assert.equal(templateCardModels({}).length, 0);
});

test("renderTemplatesTab paints cards with start buttons and states", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderTemplatesTab(host, { state: "done", model: templateCardModels(PAYLOAD) });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("이 목적으로 시작"));
  assert.ok(html.includes("검증됨") && (html.includes("미검증") || html.includes("badchip") || html.includes("warnchip")));
});

test("renderTemplatesTab paints loading and error states", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderTemplatesTab(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /불러오는 중/);
  const h1 = make(); renderTemplatesTab(h1, { state: "error", message: "실패" });
  assert.match(h1.children[0].textContent, /실패/);
  assert.ok(h1.children.some((c) => c.tagName === "BUTTON"));
});

test("the shell hosts the templates tab and wires start-from-purpose", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('data-sidetab="templates"'));
  assert.ok(html.includes('id="sideTemplates"'));
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"templates"'));
  assert.ok(src.includes("__templatesTabLoad"));
  assert.ok(src.indexOf("__templatesTabLoad = ") < src.indexOf("initSideTabs();"));
  assert.ok(src.includes("function startFromPurpose"), "facade helper must exist");
  assert.ok(src.includes("__templatesStart"), "cards must trigger the facade start action");
});
```

- [ ] **Step 2: 실패 확인**

- [ ] **Step 3: 구현 `frontend/guided/templates.js`**

```js
// frontend/guided/templates.js — 템플릿 탭. 목적 경로를 카드로 보고 "이 목적으로
// 시작"으로 중앙 목표 단계에 진입시킨다. 데이터는 모델 탭과 같은 list_models.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function templateCardModels(payload) {
  const data = payload && typeof payload === "object" ? payload : {};
  return (Array.isArray(data.purposes) ? data.purposes : [])
    .filter((p) => p && typeof p === "object")
    .map((p) => ({
      purpose: String(p.purpose || ""),
      name: String(p.display_name_ko || p.purpose || ""),
      executable: Boolean(p.executable),
      validated: Boolean(p.validated),
      state: !p.executable ? "blocked" : p.validated ? "validated" : "unvalidated",
      unvalidatedStages: Array.isArray(p.unvalidated_stages) ? p.unvalidated_stages.map(String) : [],
    }));
}

export function renderTemplatesTab(host, { state = "idle", model = [], message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") { host.appendChild(el("p", "note", "템플릿을 불러오는 중…")); return; }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "템플릿을 불러오지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    retry.addEventListener("click", () => {
      if (typeof window !== "undefined" && window.__templatesTabLoad) window.__templatesTabLoad(true);
    });
    host.appendChild(retry);
    return;
  }
  if (state === "idle") { host.appendChild(el("p", "note", "템플릿 탭입니다.")); return; }
  if (!model.length) { host.appendChild(el("p", "note", "사용할 수 있는 목적이 없습니다.")); return; }
  for (const card of model) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.append(el("span", "name", card.name));
    if (card.state === "validated") head.appendChild(el("span", "okchip", "검증됨"));
    else if (card.state === "unvalidated") head.appendChild(el("span", "warnchip", "미검증"));
    else head.appendChild(el("span", "badchip", "실행 불가"));
    row.appendChild(head);
    if (card.unvalidatedStages.length) {
      row.appendChild(el("p", "note", `미검증 단계: ${card.unvalidatedStages.join(", ")}`));
    }
    const start = document.createElement("button");
    start.type = "button";
    start.className = "ghost";
    start.textContent = "이 목적으로 시작";
    if (typeof start.addEventListener === "function") {
      start.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__templatesStart) window.__templatesStart(card.purpose);
      });
    }
    row.appendChild(start);
    host.appendChild(row);
  }
}

export async function requestTemplates() {
  const out = await callTool("pipeline.list_models", {});
  if (out && out.error) throw new Error(out.error);
  return out;
}
```

- [ ] **Step 4: 배선**

1. guided.html: sidetab 버튼(모델 다음, 연결 앞이 자연스러움 — 순서는 실행 목록 | 템플릿 | 모델 | 연결 | 스킬 | 에이전트로 정리) + `<div id="sideTemplates" class="hidden modelstab" role="tabpanel"></div>`.
2. guided.js: `SIDE_TAB_NAMES`에 "templates" 삽입(배열 순서 = 표시 순서); showSideTab 패널 토글 + 훅 호출 추가; `__templatesTabLoad` 훅(기존 패턴)을 `initSideTabs();` 이전에; import 추가.
3. guided.js: facade 헬퍼(브라우저 전용 블록):
```js
  window.__templatesStart = (purpose) => {
    const select = document.getElementById("purpose");
    if (select) {
      select.value = purpose;
      if (typeof onPurposeChange === "function") onPurposeChange();
    }
    showPanel("plan");
    showStep(1);
  };
```
(`onPurposeChange`는 plan.js export를 guided.js가 이미 import 중인지 확인 — renderWeights 등과 함께 import 돼 있을 것. showPanel/showStep은 facade 내부 함수. objective 섹션의 패널 이름은 guided.html의 data-panelfor 값을 확인하고 맞춘다 — 계획 폼이 속한 패널명. `showStep(1)`은 계획 단계 네비게이션의 1단계.)

- [ ] **Step 5: 통과 + 커밋**

```bash
git add frontend/guided/templates.js frontend/tests/guided-templates.test.js frontend/guided.html frontend/guided.js
git commit -m "feat(rapid-guided): templates tab with start-from-purpose entry"
```

---

### Task 3: 프로젝트 탭

**Files:**
- Create: `frontend/guided/projects.js`, `frontend/tests/guided-projects.test.js`
- Modify: `frontend/guided.html` (sidetab + `#sideProjects`), `frontend/guided.js` (SIDE_TAB_NAMES + 훅), `frontend/guided.css`(불필요 시 제외)

- [ ] **Step 1: 실패하는 테스트** — `guided-projects.test.js`:

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

const { projectCardModels, roundRowModels, renderProjectsTab } = await import("../guided/projects.js");

const PROJECTS = [
  { project_id: "p1", name: "프로젝트 하나", owner_username: "kim", description: "설명",
    archived: false, created_utc: "2026-09-01" },
  { project_id: "p2", name: "보관된 것", archived: true },
];

const ROUNDS = [
  { round_id: "r1", created_utc: "2026-09-02", note: "1차", run_id: "run_x" },
  { round_id: "r2" },
];

test("projectCardModels absorbs records", () => {
  const models = projectCardModels(PROJECTS);
  assert.equal(models[0].id, "p1");
  assert.equal(models[0].archived, false);
  assert.equal(models[1].archived, true);
  assert.equal(projectCardModels(null).length, 0);
});

test("roundRowModels absorbs rounds", () => {
  const rows = roundRowModels(ROUNDS);
  assert.equal(rows[0].runId, "run_x");
  assert.equal(rows[1].runId, "");
  assert.equal(roundRowModels(null).length, 0);
});

test("renderProjectsTab paints projects and expanded rounds", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderProjectsTab(host, { state: "done", projects: projectCardModels(PROJECTS),
                            expandedId: "p1", rounds: roundRowModels(ROUNDS) });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("프로젝트 하나"));
  assert.ok(html.includes("보관된 것"));
  assert.ok(html.includes("r1"));
  assert.ok(html.includes("run_x"));
});

test("renderProjectsTab paints loading, error, empty states", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderProjectsTab(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /불러오는 중/);
  const h1 = make(); renderProjectsTab(h1, { state: "error", message: "실패" });
  assert.match(h1.children[0].textContent, /실패/);
  const h2 = make(); renderProjectsTab(h2, { state: "done", projects: [] });
  assert.ok(h2.children[0].textContent.length > 0);
});

test("the shell hosts the projects tab with drill-down wiring", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('data-sidetab="projects"'));
  assert.ok(html.includes('id="sideProjects"'));
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"projects"'));
  assert.ok(src.includes("__projectsTabLoad"));
  assert.ok(src.indexOf("__projectsTabLoad = ") < src.indexOf("initSideTabs();"));
  const mod = readFileSync(new URL("../guided/projects.js", import.meta.url), "utf8");
  assert.ok(mod.includes("pipeline.list_projects"));
  assert.ok(mod.includes("pipeline.list_rounds"));
});
```

- [ ] **Step 2: 실패 확인**

- [ ] **Step 3: 구현 `frontend/guided/projects.js`**

계약:
- `projectCardModels(projects)` → `{id, name, owner, description, archived}` (name: `String(p.name || p.project_id || "")`, owner: `owner_username || ""`, archived: Boolean)
- `roundRowModels(rounds)` → `{id, createdUtc, note, runId}` (note: `note || description || ""`)
- `renderProjectsTab(host, {state, projects, expandedId, rounds, message})`:
  - loading/error(+retry)/empty(빈 프로젝트 노트)
  - done: 프로젝트 카드마다 이름+owner 칩+아카이브 칩(archived), 설명 note. 카드(또는 "라운드 보기" 버튼) 클릭 → `window.__projectsExpand?.(project_id)` (이미 펼쳐진 카드면 다시 클릭 시 접기 — 훅이 토글).
  - `expandedId`가 있으면 그 카드 아래 라운드 목록(라운드 id + 생성시각 + note + run_id 있으면 `chip`으로 run_id 표시) + 라운드가 비면 "라운드 없음" note.
- `requestProjects()`, `requestRounds(projectId)` → `list_projects {limit: 200}` / `list_rounds {project_id, limit: 100}` (error → throw).

- [ ] **Step 4: 배선** — 템플릿 탭과 동일 패턴. 훅:
```js
  window.__projectsTabLoad = (force = false) => { ... list_projects 로드, dataset.loaded ... };
  window.__projectsExpand = async (projectId) => {
    // 토글: 이미 펼쳐진 id면 접고 끝
    if (projectsExpandedId === projectId) { projectsExpandedId = ""; await paintProjects(); return; }
    projectsExpandedId = projectId;
    await paintProjects();           // 로딩 표시 후
    try { projectsRounds = (await requestRounds(projectId)).rounds || []; }
    catch (error) { projectsRounds = []; /* 노트로 실패 표시 */ }
    await paintProjects();
  };
```
(모듈 상태 `projectsExpandedId`/`projectsRounds`는 guided.js가 아니라 projects.js 모듈에 두고, 훅은 모듈 함수 `expandProject(id)`/`loadProjects(force)`를 호출하는 얇은 래퍼로 — connections/skills 훅과 일관. 렌더에 현재 상태를 반영하려면 모듈이 자기 상태를 가진 형태가 깔끔하다. `guided.test.js`의 renderSkills 계열 가드와 충돌 없는지 확인.)

- [ ] **Step 5: 통과 + 커밋**

```bash
git add frontend/guided/projects.js frontend/tests/guided-projects.test.js frontend/guided.html frontend/guided.js
git commit -m "feat(rapid-guided): projects tab with rounds drill-down"
```

---

### Task 4: 전체 검증 + dev 배포

- [ ] **Step 1: 프런트** — guided 패밀리 18파일 → 전부 통과(기존 169 + 신규 ~14); CI 프런트 서브셋 fail 0; 빌드 ✓
- [ ] **Step 2: 백엔드 회귀** — CI 서브셋 97+11 PASS (변경 없음 확인)
- [ ] **Step 3: push + CI watch** — `git push origin HEAD:develop` (fast-forward 확인)
- [ ] **Step 4: 배포 확인 + 스모크** — healthz; 브라우저: 스킬/모델 탭 텍스트 겹침 없음(좁은 창 포함), 연결 탭 "다시 실측", 템플릿 탭 시작 버튼 → 중앙 목표 선택 이동, 프로젝트 탭 드릴다운.

롤백: `git revert` 후 재push.
