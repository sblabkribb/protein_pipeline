# Guided Evidence 탭 문헌 검색 (Europe PMC) — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** guided 콘솔 Evidence 탭에서 Europe PMC 문헌을 검색해 참조 목록(제목·인용수·OA·링크)으로 보여준다. 실행과 무관한 읽기 전용 참조 도구.

**Architecture:** 백엔드 신규 모듈 `literature.py`(urllib, API 키 불필요) + 도구 `pipeline.search_literature` 등록. 프런트 신규 모듈 `guided/literature.js`(council.js 패턴: 순수 모델 + 렌더) + Evidence 패널에 `#evidenceView`의 **형제**로 검색 폼·결과 박스 배치(런 전환 리셋 회피).

**Tech Stack:** Python stdlib (`urllib.request`, `json`), vanilla ES modules, `node --test`, pytest, vite.

**Spec:** `docs/specs/2026-09-07-guided-literature-search-design.md`

**주의:** 저장소에 관련 없는 dirty 파일이 많다. 각 태스크가 지정한 파일만 `git add` 한다. `git add -A`/`git commit -a` 금지. 백엔드 테스트는 `PYTHONPATH=pipeline-mcp/src pytest …`, 프런트는 `cd frontend && node --test …`.

---

### Task 1: 백엔드 `literature.py` 모듈 (TDD)

**Files:**
- Create: `pipeline-mcp/tests/test_literature.py`
- Create: `pipeline-mcp/src/pipeline_mcp/literature.py`

- [ ] **Step 1: 실패하는 테스트** — `pipeline-mcp/tests/test_literature.py` (전문 교체):

```python
import json
import unittest
from unittest import mock

from pipeline_mcp.literature import (
    EUROPEPMC_BASE,
    _clamp_limit,
    _row,
    search_literature,
)


class TestRow(unittest.TestCase):
    def test_doi_wins_over_pmid(self) -> None:
        row = _row({"doi": "10.1/x", "pmid": "123", "id": "456",
                    "title": "T", "authorString": "A, B", "journalTitle": "J",
                    "pubYear": "2022", "citedByCount": 7, "isOpenAccess": "Y",
                    "source": "MED"})
        self.assertEqual(row["url"], "https://doi.org/10.1/x")
        self.assertEqual(row["identifier"], "10.1/x")
        self.assertTrue(row["open_access"])
        self.assertEqual(row["citations"], 7)

    def test_pmid_fallback_url(self) -> None:
        row = _row({"pmid": "123", "id": "456", "title": "T", "source": "MED"})
        self.assertEqual(row["identifier"], "123")
        self.assertEqual(row["url"], "https://europepmc.org/article/MED/123")

    def test_id_only_and_authors_truncated(self) -> None:
        row = _row({"id": "789", "source": "PPR", "title": "T",
                    "authorString": "x" * 200})
        self.assertEqual(row["url"], "https://europepmc.org/article/PPR/789")
        self.assertEqual(len(row["authors"]), 80)
        self.assertFalse(row["open_access"])
        self.assertEqual(row["citations"], 0)


class TestClamp(unittest.TestCase):
    def test_clamps_and_defaults(self) -> None:
        self.assertEqual(_clamp_limit(0), 1)
        self.assertEqual(_clamp_limit(99), 25)
        self.assertEqual(_clamp_limit(8), 8)
        self.assertEqual(_clamp_limit("bad"), 8)
        self.assertEqual(_clamp_limit(None), 8)


class TestSearch(unittest.TestCase):
    def test_empty_query_is_error(self) -> None:
        self.assertIn("error", search_literature("  "))

    def test_network_failure_is_error_contract(self) -> None:
        with mock.patch("pipeline_mcp.literature.urllib.request.urlopen",
                        side_effect=OSError("down")):
            out = search_literature("protein design")
        self.assertIn("error", out)

    def test_parses_result_list(self) -> None:
        payload = {"resultList": {"result": [
            {"id": "1", "doi": "10.1/a", "title": "Paper A",
             "authorString": "A", "journalTitle": "J", "pubYear": "2023",
             "citedByCount": 3, "isOpenAccess": "Y", "source": "MED"},
            {"not": "a row"},
        ]}}
        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__.return_value = response
        with mock.patch("pipeline_mcp.literature.urllib.request.urlopen",
                        return_value=response) as urlopen:
            out = search_literature("protein", limit=5)
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["items"][0]["title"], "Paper A")
        self.assertEqual(out["query"], "protein")
        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.startswith(f"{EUROPEPMC_BASE}/search?"))
        self.assertIn("pageSize=5", request.full_url)
        self.assertIn("sort=CITED+desc", request.full_url)
        self.assertIn("resultType=lite", request.full_url)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인** — `PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_literature.py -q` → FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현** — `pipeline-mcp/src/pipeline_mcp/literature.py` (전문 교체):

```python
"""Europe PMC 문헌 검색. 결과는 published 참조용이다.

근거 철학: 계획의 결정 근거는 우리가 측정한 값이거나 검증된 문헌이다. 이 도구가
돌려주는 검색 결과는 그보다 약한 '누군가의 주장'이다 - 참조로 보여주되, 계획의
측정 근거와 같은 칸에 두지 않는다. UI 도 출처 라벨로 이 둘을 섞지 않는다.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
LITERATURE_TIMEOUT_SECONDS = 10.0


def _clamp_limit(limit) -> int:
    try:
        return max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        return 8


def _row(record: dict) -> dict:
    doi = str(record.get("doi") or "").strip()
    pmid = str(record.get("pmid") or "").strip()
    identifier = doi or pmid or str(record.get("id") or "")
    if doi:
        url = f"https://doi.org/{doi}"
    else:
        url = f"https://europepmc.org/article/{record.get('source', 'MED')}/{record.get('id')}"
    try:
        citations = int(record.get("citedByCount") or 0)
    except (TypeError, ValueError):
        citations = 0
    return {
        "title": str(record.get("title") or "").strip(),
        "authors": str(record.get("authorString") or "")[:80],
        "journal": str(record.get("journalTitle") or "").strip(),
        "year": str(record.get("pubYear") or "").strip(),
        "citations": citations,
        "open_access": record.get("isOpenAccess") == "Y",
        "identifier": identifier,
        "url": url,
    }


def search_literature(query: str, limit: int = 8) -> dict:
    """문헌 검색. 실패는 예외 대신 {"error": ...} 계약으로 돌려준다."""
    query = str(query or "").strip()
    if not query:
        return {"error": "query is required"}
    params = urllib.parse.urlencode({
        "query": query,
        "format": "json",
        "pageSize": _clamp_limit(limit),
        "resultType": "lite",
        "sort": "CITED desc",
    })
    request = urllib.request.Request(f"{EUROPEPMC_BASE}/search?{params}")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=LITERATURE_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Europe PMC 요청 실패: {type(exc).__name__}"}
    records = (payload.get("resultList") or {}).get("result") or []
    return {"items": [_row(record) for record in records if isinstance(record, dict)],
            "query": query}
```

- [ ] **Step 4: 통과 확인** — 같은 명령 → PASS (7 tests)

- [ ] **Step 5: 커밋**

```bash
git add pipeline-mcp/src/pipeline_mcp/literature.py pipeline-mcp/tests/test_literature.py
git commit -m "feat(rapid): Europe PMC literature search module"
```

---

### Task 2: 도구 등록 `pipeline.search_literature`

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py` — 도구 정의(`"pipeline.plan_council"` 항목 뒤, ~8902행 부근) + dispatch 분기(`if name == "pipeline.plan_council":` 블록 뒤, ~9747행 부근)
- Modify: `pipeline-mcp/tests/test_literature.py` — Registration 클래스 추가

- [ ] **Step 1: 실패하는 테스트 추가** — 상단 import에 추가:

```python
import shutil
import tempfile

from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher, tool_definitions
import pipeline_mcp.literature as literature_mod
```

파일 끝(`if __name__ == "__main__":` 직전):

```python
class TestRegistration(unittest.TestCase):
    def test_tool_is_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        self.assertIn("pipeline.search_literature", names)

    def test_dispatch_rejects_blank_query(self) -> None:
        runner = PipelineRunner(output_root="/tmp/unused-lit", mmseqs=None,
                                proteinmpnn=None, soluprot=None, af2=None)
        out = ToolDispatcher(runner).call_tool("pipeline.search_literature", {"query": "  "})
        self.assertIn("error", out)

    def test_dispatch_delegates(self) -> None:
        tmp = tempfile.mkdtemp(prefix="lit_")
        try:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None,
                                    soluprot=None, af2=None)
            with mock.patch.object(literature_mod, "search_literature",
                                   return_value={"items": [{"title": "T"}], "query": "q"}) as fake:
                out = ToolDispatcher(runner).call_tool(
                    "pipeline.search_literature", {"query": "q", "limit": 3})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(out["items"], [{"title": "T"}])
        fake.assert_called_once_with("q", 3)
```

- [ ] **Step 2: 실패 확인** — `PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_literature.py -k Registration -q` → FAIL

- [ ] **Step 3: 도구 정의 추가** — `tools.py`의 `"pipeline.plan_council"` 정의 항목 뒤에:

```python
        {
            "name": "pipeline.search_literature",
            "description": (
                "Read-only Europe PMC literature search. Published sources are "
                "weaker than internal measurements: results are reference only "
                "and never replace measured evidence."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "search terms"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25,
                              "description": "default 8"},
                },
                "required": ["query"],
            },
        },
```

- [ ] **Step 4: dispatch 분기 추가** — `if name == "pipeline.plan_council":` 블록 다음:

```python
        if name == "pipeline.search_literature":
            from .literature import search_literature

            query = str(arguments.get("query") or "").strip()
            if not query:
                return {"error": "query is required"}
            return search_literature(query, int(arguments.get("limit") or 8))
```

- [ ] **Step 5: 통과 확인 + 회귀**

```bash
PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_literature.py -q
PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_http_server_auth.py pipeline-mcp/tests/test_mcp_http_route.py pipeline-mcp/tests/test_oidc_auth.py pipeline-mcp/tests/test_session_auth.py pipeline-mcp/tests/test_runpod_admin.py pipeline-mcp/tests/test_plan_council.py -q
```
Expected: 10 tests PASS / 87 tests PASS

- [ ] **Step 6: 커밋**

```bash
git add pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/tests/test_literature.py
git commit -m "feat(rapid): register pipeline.search_literature tool"
```

---

### Task 3: 프런트 문헌 검색 UI

**Files:**
- Create: `frontend/guided/literature.js`
- Create: `frontend/tests/guided-literature.test.js`
- Modify: `frontend/guided.html` — Evidence 패널(~205행)에 형제 섹션 추가
- Modify: `frontend/guided.js` — `initLiteratureSearch()` + boot 호출
- Modify: `frontend/guided.css` — 최소 규칙

- [ ] **Step 1: 실패하는 테스트** — `frontend/tests/guided-literature.test.js` (전문 교체):

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
      href: "",
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  },
};

const { literatureRowModels, renderLiterature } = await import("../guided/literature.js");

const ITEMS = [
  { title: "Paper A", authors: "A, B", journal: "J", year: "2023",
    citations: 12, open_access: true, identifier: "10.1/a", url: "https://doi.org/10.1/a" },
  { title: "Paper B", citations: 0, open_access: false, url: "https://europepmc.org/article/MED/9" },
];

test("literatureRowModels maps rows and tolerates junk", () => {
  const models = literatureRowModels(ITEMS);
  assert.equal(models[0].citations, 12);
  assert.equal(models[0].openAccess, true);
  assert.ok(models[0].meta.includes("2023"));
  assert.equal(models[1].citations, 0);
  assert.equal(literatureRowModels([null, "x"]).length, 2);
  assert.equal(literatureRowModels()[0], undefined);
});

test("renderLiterature paints loading/empty/error/idle states", () => {
  const host = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = host(); renderLiterature(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /찾는 중/);
  const h1 = host(); renderLiterature(h1, { state: "empty" });
  assert.match(h1.children[0].textContent, /결과 없음/);
  const h2 = host(); renderLiterature(h2, { state: "error", message: "실패" });
  assert.match(h2.children[0].textContent, /실패/);
  const h3 = host(); renderLiterature(h3, { state: "idle" });
  assert.ok(h3.children[0].textContent.length > 0);
});

test("renderLiterature paints rows with chips and links", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderLiterature(host, { state: "done", items: ITEMS });
  const cards = host.children.filter((c) => c.className === "skill");
  assert.equal(cards.length, 2);
  const link = cards[0].children[0].children.find((c) => c.tagName === "A");
  assert.equal(link.href, "https://doi.org/10.1/a");
  assert.ok(cards[0].children[0].children.some((c) => c.className === "okchip"));
});

test("the literature box is a sibling of evidenceView and survives run switches", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  const panel = html.slice(html.indexOf('data-panelfor="evidence"'));
  assert.ok(panel.includes('id="evidenceView"'));
  assert.ok(panel.includes('id="literatureBox"'));
  assert.ok(panel.includes("이 검색은 실행과 무관합니다"));
  const evidence = readFileSync(new URL("../guided/evidence.js", import.meta.url), "utf8");
  assert.ok(!evidence.includes("literatureBox"), "evidence.js must not reset the literature box");
});

test("the facade wires the search form once", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes("function initLiteratureSearch"));
  assert.ok(src.includes("initLiteratureSearch();"));
  assert.ok(src.includes('id="literatureForm"') || src.includes("literatureForm"));
});
```

- [ ] **Step 2: 실패 확인** — `cd frontend && node --test tests/guided-literature.test.js` → FAIL (module missing)

- [ ] **Step 3: `frontend/guided/literature.js`** (전문 교체):

```js
// frontend/guided/literature.js — Europe PMC 문헌 검색. 실행과 무관한 참조
// 도구라 런 전환에도 결과가 유지된다. 순수 모델과 렌더를 나눠 node 테스트가
// 가능하게 한다. 결과는 published 출처 — 측정 근거와 섞지 않는다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function literatureRowModels(items) {
  const rows = Array.isArray(items) ? items : [];
  return rows.map((item) => {
    const row = item && typeof item === "object" ? item : {};
    const meta = [row.authors, row.journal, row.year].map(String).filter(Boolean).join(" · ");
    return {
      title: String(row.title || "").trim() || "제목 없음",
      meta,
      citations: Number(row.citations || 0),
      openAccess: Boolean(row.open_access),
      url: String(row.url || ""),
    };
  });
}

export function renderLiterature(host, { state = "idle", items = [], message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "문헌을 찾는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "문헌을 찾지 못했습니다."));
    return;
  }
  if (state === "empty") {
    host.appendChild(el("p", "note", "결과 없음"));
    return;
  }
  if (state === "done") {
    for (const model of literatureRowModels(items)) {
      const card = el("div", "skill");
      const head = el("div", "cardtitle");
      if (model.url) {
        // identifier 에서 조립된 서버 URL 만 연다 - 임의 href 는 받지 않는다.
        const link = document.createElement("a");
        link.href = model.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.className = "lit-title";
        link.textContent = model.title;
        head.appendChild(link);
      } else {
        head.appendChild(el("span", "name", model.title));
      }
      if (model.citations) head.appendChild(el("span", "chip", `인용 ${model.citations}`));
      if (model.openAccess) head.appendChild(el("span", "okchip", "OA"));
      card.appendChild(head);
      if (model.meta) card.appendChild(el("p", "note", model.meta));
      host.appendChild(card);
    }
    return;
  }
  host.appendChild(el("p", "note", "검색어를 넣고 검색하세요."));
}

export async function requestLiterature(query) {
  const out = await callTool("pipeline.search_literature", { query, limit: 8 });
  if (out && out.error) throw new Error(out.error);
  return out;
}
```

- [ ] **Step 4: 통과 확인** — `cd frontend && node --test tests/guided-literature.test.js` → PASS (5)

- [ ] **Step 5: guided.html** — Evidence 패널 섹션(`data-panelfor="evidence"`, ~205행)을 교체:

```html
        <section class="block panel hidden" data-panelfor="evidence">
          <div id="evidenceView" class="empty">계획을 생성하면 근거가 여기 모입니다.</div>
          <h3>문헌 검색</h3>
          <p class="note">이 검색은 실행과 무관합니다 — 런을 바꿔도 결과가 유지됩니다.</p>
          <form id="literatureForm" class="literatureform">
            <label class="visually-hidden" for="literatureInput">문헌 검색어</label>
            <input id="literatureInput" placeholder="예: de novo enzyme design solubility" />
            <button id="literatureSearch" class="primary" type="submit">검색</button>
          </form>
          <div id="literatureBox" class="literaturebox"></div>
        </section>
```

- [ ] **Step 6: guided.js** — 세 곳:

1. import (기존 guided/ import 근처):
```js
import { renderLiterature, requestLiterature } from "./guided/literature.js";
```
2. `initStructureTab()` 정의 근처에 추가:
```js
// 문헌 검색은 실행과 무관하다 - 런 전환 리셋 대상이 아니므로 Evidence 패널의
// evidenceView 형제로 두고 여기서 한 번만 연결한다.
async function runLiteratureSearch() {
  const host = document.getElementById("literatureBox");
  const query = document.getElementById("literatureInput").value.trim();
  if (!query) {
    renderLiterature(host, { state: "idle" });
    return;
  }
  renderLiterature(host, { state: "loading" });
  try {
    const out = await requestLiterature(query);
    const items = Array.isArray(out.items) ? out.items : [];
    renderLiterature(host, items.length ? { state: "done", items } : { state: "empty" });
  } catch (error) {
    renderLiterature(host, { state: "error", message: `문헌을 찾지 못했습니다: ${errorText(error)}` });
  }
}

function initLiteratureSearch() {
  const form = document.getElementById("literatureForm");
  if (!form || form.dataset.wired) return;
  form.dataset.wired = "1";
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runLiteratureSearch();
  });
}
```
(`errorText`가 guided.js에 import 돼 있는지 확인 — compareBtn에서 쓰므로 이미 있을 것. 없으면 `./guided/api.js`에서 추가.)
3. `boot()` 안의 `initStructureTab();` 다음에:
```js
  initLiteratureSearch();
```

- [ ] **Step 7: guided.css** — `.literatureform` 규칙(기존 `.chiform` 근처):

```css
.literatureform { display: flex; gap: 8px; margin: 8px 0; }
.literatureform input { flex: 1; min-width: 0; padding: 8px 11px; }
.literaturebox { display: grid; gap: 8px; }
.literaturebox .skill { display: block; padding: 8px 10px; }
.lit-title { color: var(--ink); }
```

- [ ] **Step 8: 전체 확인**

```bash
cd frontend && node --test tests/guided-literature.test.js tests/guided.test.js tests/guided-council.test.js
cd /opt/protein_pipeline-work && npm --prefix frontend run build
```
Expected: 83 tests pass (5 + 71 + 7), build ✓.

- [ ] **Step 9: 커밋**

```bash
git add frontend/guided/literature.js frontend/tests/guided-literature.test.js frontend/guided.html frontend/guided.js frontend/guided.css
git commit -m "feat(rapid-guided): Europe PMC literature search in the Evidence tab"
```

---

### Task 4: 전체 검증 + dev 배포

- [ ] **Step 1: 백엔드** — CI 서브셋 + 신규:

```bash
PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_http_server_auth.py pipeline-mcp/tests/test_mcp_http_route.py pipeline-mcp/tests/test_oidc_auth.py pipeline-mcp/tests/test_session_auth.py pipeline-mcp/tests/test_runpod_admin.py pipeline-mcp/tests/test_plan_council.py pipeline-mcp/tests/test_literature.py -q
```
Expected: PASS (97 tests)

- [ ] **Step 2: 프런트** — guided 전체 + CI 서브셋:

```bash
cd frontend && node --test tests/guided-topbar.test.js tests/guided.test.js tests/guided-sidebar.test.js tests/guided-progress.test.js tests/guided-results.test.js tests/guided-evidence.test.js tests/guided-structure.test.js tests/guided-council.test.js tests/guided-layout.test.js tests/guided-literature.test.js
```
Expected: PASS (147 tests = 142 + 5)

```bash
node --test frontend/tests/app-syntax.test.js frontend/tests/auth-session.test.js frontend/tests/auth.test.js frontend/tests/login-bootstrap.test.js frontend/tests/mcp-tab.test.js frontend/tests/runpod-admin.test.js && (cd frontend && node --test tests/logout-bridge.test.js)
```
Expected: fail 0

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

브라우저: guided.html → Evidence 탭 → "문헌 검색" 섹션에서 검색 → 결과 행(제목 링크·인용수·OA 칩) 확인. 런을 바꿔도 결과 유지 확인. 빈 검색어 → 안내 노트.

롤백: `git revert` 후 재push.
