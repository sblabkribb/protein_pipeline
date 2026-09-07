# 좌측 탭 2차: 연결·스킬·에이전트 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** guided 좌측 탭에 연결(엔드포인트 실측 프로브)·스킬(협의회 헌장 사용자 편집)·에이전트(agent panel 이벤트 뷰) 탭을 추가한다.

**Architecture:** 연결·에이전트는 기존 도구 재사용(프런트만). 스킬은 백엔드 신규 도구 3개(list/save/reset) + `<output_root>/_council_skills/<expert_id>.json` 사용자 치환 + `_ask_expert`의 호출시점 폴백. 프런트는 models.js/council.js 패턴의 모듈 3개.

**Tech Stack:** Python stdlib, vanilla ES modules, `node --test`, pytest, vite.

**Spec:** `docs/specs/2026-09-07-guided-side-tabs-connections-skills-agents-design.md`

**주의:** 지정한 파일만 `git add`. 백엔드 `PYTHONPATH=pipeline-mcp/src pytest`, 프런트 `cd frontend && node --test`, 빌드 `npm --prefix frontend run build`.

---

### Task 1: 백엔드 — 협의회 스킬 (사용자 헌장 치환)

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/plan_council.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py` (도구 정의 3개 + dispatch 3분기)
- Test: `pipeline-mcp/tests/test_council_skills.py`

- [ ] **Step 1: 실패하는 테스트** — `pipeline-mcp/tests/test_council_skills.py` (전문 교체):

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pipeline_mcp.plan_council as plan_council
from pipeline_mcp.plan_council import (
    EXPERTS,
    build_expert_prompt,
    user_charter_path,
    user_charter_root,
)
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher, tool_definitions


class TestSkillsStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.patcher = mock.patch.object(plan_council, "user_charter_root", lambda: self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_user_charter_path_joins_id(self) -> None:
        path = user_charter_path("solubility")
        self.assertEqual(path.parent.name, "_council_skills")
        self.assertEqual(path.name, "solubility.json")

    def test_list_merges_builtin_and_user(self) -> None:
        out = plan_council.list_council_skills()
        self.assertEqual([s["expert_id"] for s in out["skills"]], [e.id for e in EXPERTS])
        self.assertTrue(all(s["source"] == "builtin" for s in out["skills"]))
        (self.root / "_council_skills").mkdir(parents=True)
        (self.root / "_council_skills" / "solubility.json").write_text(
            json.dumps({"charter": "사용자 헌장", "updated_utc": "2026-09-07"}), encoding="utf-8")
        out = plan_council.list_council_skills()
        row = next(s for s in out["skills"] if s["expert_id"] == "solubility")
        self.assertEqual(row["source"], "user")
        self.assertEqual(row["charter"], "사용자 헌장")

    def test_broken_user_file_falls_back_to_builtin(self) -> None:
        (self.root / "_council_skills").mkdir(parents=True)
        (self.root / "_council_skills" / "stability.json").write_text("{broken", encoding="utf-8")
        out = plan_council.list_council_skills()
        row = next(s for s in out["skills"] if s["expert_id"] == "stability")
        self.assertEqual(row["source"], "builtin")

    def test_save_validates_expert_and_length(self) -> None:
        self.assertIn("error", plan_council.save_council_skill("nope", "헌장"))
        self.assertIn("error", plan_council.save_council_skill("solubility", "   "))
        self.assertIn("error", plan_council.save_council_skill("solubility", "x" * 8001))
        out = plan_council.save_council_skill("solubility", "바뀐 헌장")
        self.assertNotIn("error", out)
        saved = json.loads((self.root / "_council_skills" / "solubility.json").read_text())
        self.assertEqual(saved["charter"], "바뀐 헌장")

    def test_reset_removes_user_file(self) -> None:
        (self.root / "_council_skills").mkdir(parents=True)
        path = self.root / "_council_skills" / "solubility.json"
        path.write_text("{}", encoding="utf-8")
        plan_council.reset_council_skill("solubility")
        self.assertFalse(path.exists())
        plan_council.reset_council_skill("solubility")  # 없어도 ok

    def test_expert_charter_prefers_user_file(self) -> None:
        (self.root / "_council_skills").mkdir(parents=True)
        (self.root / "_council_skills" / "solubility.json").write_text(
            json.dumps({"charter": "사용자 헌장"}), encoding="utf-8")
        expert = next(e for e in EXPERTS if e.id == "solubility")
        self.assertEqual(plan_council.charter_for(expert), "사용자 헌장")
        self.assertIn("사용자 헌장", build_expert_prompt({}, expert) if False else "x")  # placeholder 제거용 아님 — 아래 Step에서 실제 검증

    def test_ask_expert_uses_user_charter(self) -> None:
        (self.root / "_council_skills").mkdir(parents=True)
        (self.root / "_council_skills" / "solubility.json").write_text(
            json.dumps({"charter": "사용자 헌장"}), encoding="utf-8")
        expert = next(e for e in EXPERTS if e.id == "solubility")
        seen = {}

        class FakeGemini:
            def is_available(self):
                return True
            def chat(self, system, prompt):
                seen["system"] = system
                return "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"

        plan_council._ask_expert(FakeGemini(), {}, expert)
        self.assertIn("사용자 헌장", seen["system"])
        self.assertIn("OUTPUT", seen["system"])  # 계약 텍스트는 유지된다

    def test_ask_expert_broken_user_file_falls_back(self) -> None:
        (self.root / "_council_skills").mkdir(parents=True)
        (self.root / "_council_skills" / "solubility.json").write_text("{", encoding="utf-8")
        expert = next(e for e in EXPERTS if e.id == "solubility")
        seen = {}

        class FakeGemini:
            def is_available(self):
                return True
            def chat(self, system, prompt):
                seen["system"] = system
                return "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"

        plan_council._ask_expert(FakeGemini(), {}, expert)
        self.assertIn(expert.charter[:20], seen["system"])


class TestRegistration(unittest.TestCase):
    def test_tools_are_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        for name in ("pipeline.list_council_skills", "pipeline.save_council_skill",
                     "pipeline.reset_council_skill"):
            self.assertIn(name, names)

    def test_dispatch_roundtrip(self) -> None:
        runner = PipelineRunner(output_root=tempfile.mkdtemp(prefix="skills_"),
                                mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
        dispatcher = ToolDispatcher(runner)
        out = dispatcher.call_tool("pipeline.save_council_skill",
                                   {"expert_id": "solubility", "charter": "헌장"})
        self.assertNotIn("error", out)
        listed = dispatcher.call_tool("pipeline.list_council_skills", {})
        row = next(s for s in listed["skills"] if s["expert_id"] == "solubility")
        self.assertEqual(row["source"], "user")
        dispatcher.call_tool("pipeline.reset_council_skill", {"expert_id": "solubility"})
        listed = dispatcher.call_tool("pipeline.list_council_skills", {})
        row = next(s for s in listed["skills"] if s["expert_id"] == "solubility")
        self.assertEqual(row["source"], "builtin")


if __name__ == "__main__":
    unittest.main()
```

주의: `test_expert_charter_prefers_user_file`의 마지막 assert는 제대로 된 검증이 아니다 — Step 3 구현 시 아래 형태로 교체한다:

```python
        system = plan_council._expert_system(expert)
        self.assertIn("사용자 헌장", system)
        self.assertIn("OUTPUT", system)
```
(즉 `_ask_expert`의 시스템 프롬프트 조립을 `_expert_system(expert)` 헬퍼로 추출하고 두 테스트가 모두 그것을 검증하게 한다. `plan_council.py` 리팩터: `system = expert.charter + "\n\n" + COUNCIL_OUTPUT_CONTRACT` → `system = _expert_system(expert)`.)

- [ ] **Step 2: 실패 확인** — `PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_council_skills.py -q` → FAIL

- [ ] **Step 3: 구현** — `plan_council.py`에 추가:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIRNAME = "_council_skills"
CHARTER_MAX_CHARS = 8000


def user_charter_root() -> Path:
    """사용자 헌장 저장소. 테스트에서 패치하는 유일한 지점이다."""
    from .config import get_config  # noqa: PLC0415 - 도구 호출 시에만 필요

    return Path(get_config().output_root)


def user_charter_path(expert_id: str) -> Path:
    return user_charter_root() / SKILL_DIRNAME / f"{expert_id}.json"
```

주의: `config.get_config`의 실제 함수명/시그니처를 확인하고 맞춘다(`pipeline-mcp/src/pipeline_mcp/config.py` — `load_config`일 수 있음). `runner.output_root` 접근이 더 자연스러우면 도구 핸들러에서 root를 인자로 넘기는 형태로 바꾼다(테스트는 `user_charter_root` 패치이므로 `user_charter_root` 시그니처 유지 필수).

```python
def _read_user_charter(expert_id: str) -> dict | None:
    """깨진 파일은 없는 것과 같다 - builtin 으로 폴백한다."""
    try:
        payload = json.loads(user_charter_path(expert_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    charter = str(payload.get("charter") or "").strip()
    return {"charter": charter, "updated_utc": str(payload.get("updated_utc") or "")} if charter else None


def charter_for(expert: Expert) -> str:
    payload = _read_user_charter(expert.id)
    return payload["charter"] if payload else expert.charter


def _expert_system(expert: Expert) -> str:
    return charter_for(expert) + "\n\n" + COUNCIL_OUTPUT_CONTRACT


def list_council_skills() -> dict:
    skills = []
    for expert in EXPERTS:
        payload = _read_user_charter(expert.id)
        skills.append({
            "expert_id": expert.id,
            "name": expert.name,
            "source": "user" if payload else "builtin",
            "charter": payload["charter"] if payload else expert.charter,
            **({"updated_utc": payload["updated_utc"]} if payload and payload["updated_utc"] else {}),
        })
    return {"skills": skills}


def save_council_skill(expert_id: str, charter: str) -> dict:
    expert = next((e for e in EXPERTS if e.id == expert_id), None)
    if expert is None:
        return {"error": f"알 수 없는 전문가: {expert_id}"}
    charter = str(charter or "").strip()
    if not charter:
        return {"error": "charter is required"}
    if len(charter) > CHARTER_MAX_CHARS:
        return {"error": f"charter must be at most {CHARTER_MAX_CHARS} chars"}
    path = user_charter_path(expert_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "charter": charter,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }, ensure_ascii=False), encoding="utf-8")
    return {"expert_id": expert_id, "source": "user"}


def reset_council_skill(expert_id: str) -> dict:
    if expert_id not in {e.id for e in EXPERTS}:
        return {"error": f"알 수 없는 전문가: {expert_id}"}
    try:
        user_charter_path(expert_id).unlink()
    except OSError:
        pass
    return {"expert_id": expert_id, "source": "builtin"}
```

`_ask_expert`의 첫 두 줄을 교체:
```python
    system = _expert_system(expert)
```

`tools.py`: 도구 정의 3개(`pipeline.plan_council` 정의 뒤) + dispatch 3분기(`plan_council` 분기 뒤):

```python
        if name == "pipeline.list_council_skills":
            from .plan_council import list_council_skills
            return list_council_skills()

        if name == "pipeline.save_council_skill":
            from .plan_council import save_council_skill
            return save_council_skill(
                str(arguments.get("expert_id") or ""),
                str(arguments.get("charter") or ""),
            )

        if name == "pipeline.reset_council_skill":
            from .plan_council import reset_council_skill
            return reset_council_skill(str(arguments.get("expert_id") or ""))
```

도구 정의는 plan_council 항목을 복제해 name/description/schema만 바꾼다:
- list: 설명 "List the five plan-council expert charters, marking which are user-overridden." schema `{}`.
- save: `{expert_id: string(필수), charter: string(필수)}` — 설명에 "Overrides the builtin charter for the next council run only; 8000-char cap."
- reset: `{expert_id: string(필수)}` — "Removes the user charter; the builtin charter applies again."

- [ ] **Step 4: 통과 + 회귀**

```bash
PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_council_skills.py -q
PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_plan_council.py pipeline-mcp/tests/test_http_server_auth.py pipeline-mcp/tests/test_mcp_http_route.py pipeline-mcp/tests/test_oidc_auth.py pipeline-mcp/tests/test_session_auth.py pipeline-mcp/tests/test_runpod_admin.py -q
```
Expected: 11 tests PASS / 106 tests PASS (plan_council 19 + CI 68 + literature 10 + council_skills 11 — 실제 합계로 보고)

- [ ] **Step 5: 커밋**

```bash
git add pipeline-mcp/src/pipeline_mcp/plan_council.py pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/tests/test_council_skills.py
git commit -m "feat(rapid): user-overridable council expert charters"
```

---

### Task 2: 연결 탭 (프런트)

**Files:**
- Create: `frontend/guided/connections.js`, `frontend/tests/guided-connections.test.js`
- Modify: `frontend/guided.html` (sidetabs에 연결 버튼), `frontend/guided.js` (SIDE_TAB_NAMES + hook), `frontend/guided.css`

- [ ] **Step 1: 실패하는 테스트** — `guided-connections.test.js`: models.test.js와 같은 문서 스텁 패턴으로:
  - `connectionRowModels(liveness)` — 정렬(id순), reachable/ready/mismatch/error 흡수
  - `renderConnectionsTab(host, {state, data, message})` — loading/empty(엔드포인트 없음)/error/done 3블록(엔드포인트 실측 테이블, BOP 요약, 포털 카드), mismatch 경고 표시
  - 소스 계약: sidetabs에 `data-sidetab="connections"` 존재, `SIDE_TAB_NAMES`에 "connections", `__connectionsTabLoad` 훅 존재 + `initSideTabs` 이전 정의(모델 탭의 복원 버그 재발 방지)

- [ ] **Step 2: 실패 확인** 후 구현 — `guided/connections.js`:

```js
// frontend/guided/connections.js — 연결 탭. "연결됨"을 상수로 주장하지 않고
// 매번 실측한다(list_models check_liveness). 선언된 가용성 옆에 실측을 나란히 둔다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function connectionRowModels(liveness) {
  const rows = Object.entries(liveness || {});
  return rows
    .map(([id, info]) => {
      const item = info && typeof info === "object" ? info : {};
      return {
        id: String(id),
        endpoint: String(item.endpoint || ""),
        reachable: Boolean(item.reachable),
        ready: item.ready == null ? null : Boolean(item.ready),
        mismatch: Boolean(item.model_mismatch),
        declared: String(item.declared_availability || ""),
        error: String(item.error || ""),
      };
    })
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function renderConnectionsTab(host, { state = "idle", data = null, message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "엔드포인트를 확인하는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "확인하지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    retry.addEventListener("click", () => {
      if (typeof window !== "undefined" && window.__connectionsTabLoad) window.__connectionsTabLoad(true);
    });
    host.appendChild(retry);
    return;
  }
  const payload = data && typeof data === "object" ? data : {};
  const rows = connectionRowModels(payload.liveness);
  if (!rows.length) {
    host.appendChild(el("p", "note", "확인할 엔드포인트가 없습니다."));
    return;
  }

  host.appendChild(el("h3", "", "엔드포인트 실측"));
  for (const row of rows) {
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.append(el("span", row.reachable ? "name" : "name is-rejected", row.id));
    head.appendChild(el("span", row.reachable ? "okchip" : "badchip", row.reachable ? "도달" : "도달 불가"));
    if (row.ready === true) head.appendChild(el("span", "okchip", "준비됨"));
    if (row.ready === false) head.appendChild(el("span", "warnchip", "미준비"));
    if (row.mismatch) head.appendChild(el("span", "warnchip", "모델 불일치"));
    card.appendChild(head);
    const meta = [row.endpoint, row.declared && `선언 ${row.declared}`, row.error].filter(Boolean).join(" · ");
    if (meta) card.appendChild(el("p", "note", meta));
    host.appendChild(card);
  }

  const bop = payload.connections && payload.connections.bop_workers;
  if (bop) {
    host.appendChild(el("h3", "", "BOP 워커 요약"));
    host.appendChild(el("p", "note", `선언 ${bop.declared ?? 0}개 · 실측 도달 ${(bop.reachable ?? 0)}개`));
  }

  const portal = payload.connections && payload.connections.portal_mcp;
  if (portal) {
    host.appendChild(el("h3", "", "포털 연결"));
    const configured = Boolean(portal.configured);
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.append(el("span", "name", "바이오모델 포털"));
    head.appendChild(el("span", configured ? "okchip" : "warnchip", configured ? "설정됨" : "미설정"));
    card.appendChild(head);
    const unlocks = Array.isArray(portal.would_unlock) ? portal.would_unlock : [];
    const note = [portal.integration && `통합: ${portal.integration}`,
      unlocks.length && `열리는 모델: ${unlocks.join(", ")}`,
      portal.still_blocked_note].filter(Boolean).join(" — ");
    if (note) card.appendChild(el("p", "note", note));
    host.appendChild(card);
  }
}

export async function requestConnections() {
  const out = await callTool("pipeline.list_models", { check_liveness: true });
  if (out && out.error) throw new Error(out.error);
  return out;
}
```

- [ ] **Step 3: 배선** — guided.html sidetabs에 `<button class="sidetab" data-sidetab="connections" role="tab" aria-selected="false" type="button">연결</button>` 추가 (모델 다음). guided.js: `SIDE_TAB_NAMES`에 "connections" 추가, `__connectionsTabLoad` 훅(모델 탭 훅과 동일한 first-entry/force 패턴, `#sideConnections` 패널), guided.html에 `<div id="sideConnections" class="hidden modelstab" role="tabpanel"></div>` 추가, showSideTab의 패널 토글 3패널로 확장.

- [ ] **Step 4: 통과 + 커밋** — `feat(rapid-guided): connections tab with live endpoint probing`

---

### Task 3: 스킬 탭 (프런트)

**Files:**
- Create: `frontend/guided/skills.js`, `frontend/tests/guided-skills.test.js`
- Modify: `frontend/guided.html` (sidetab + `#sideSkills`), `frontend/guided.js` (SIDE_TAB_NAMES + 훅), `frontend/guided.css`

- [ ] **Step 1: 실패하는 테스트** — `guided-skills.test.js`:
  - `skillCardModels(skills)` — id/name/source/charter/updated_utc 흡수
  - `renderSkillsTab(host, {state, skills, message, editingId})` — loading/error/done(카드 5장, 출처 칩, 헌장 본문), `editingId`가 있으면 그 카드는 textarea+저장/취소 폼으로 렌더(소스 계약으로 검증: "charterText", "헌장 저장", "취소" 문자열)
  - 소스 계약: sidetab "skills", `SIDE_TAB_NAMES` 포함, `__skillsTabLoad` 훅, 저장 액션이 `pipeline.save_council_skill` 호출, 초기화 액션이 `pipeline.reset_council_skill` 호출

- [ ] **Step 2: 구현** — `guided/skills.js`: `skillCardModels`, `renderSkillsTab`, `requestSkills()`(list_council_skills), `saveSkill(expertId, charter)`, `resetSkill(expertId)`. 편집 상태는 모듈 변수 `let editingId = ""` + `let editingText = ""`; 저장 성공/취소 시 초기화·재렌더. 각 카드에 "편집"/"초기화" ghost 버튼(초기화는 source==="user"일 때만). 저장·초기화 후 `requestSkills` 재로드.

- [ ] **Step 3: 배선** — 연결 탭과 동일(sidetab 버튼, SIDE_TAB_NAMES, `#sideSkills`, `__skillsTabLoad` 훅).

- [ ] **Step 4: 통과 + 커밋** — `feat(rapid-guided): skills tab for editing council expert charters`

---

### Task 4: 에이전트 탭 (프런트)

**Files:**
- Create: `frontend/guided/agents.js`, `frontend/tests/guided-agents.test.js`
- Modify: `frontend/guided.html` (sidetab + `#sideAgents`), `frontend/guided.js` (SIDE_TAB_NAMES + 훅 + selectRun 연동), `frontend/guided.css`

- [ ] **Step 1: 실패하는 테스트** — `guided-agents.test.js`:
  - `agentEventModels(events)` — stage/state/consensus 요약 흡수(합의 interpretations 배열 → 최대 3줄)
  - `renderAgentsTab(host, {state, events, runId, message})` — 런 미선택 note / loading / error / done(이벤트 카드: 스테이지 + 상태 칩 + 해석 목록) / 빈 이벤트 note
  - 소스 계약: sidetab "agents", `SIDE_TAB_NAMES` 포함, `__agentsTabLoad` 훅, selectRun에서 에이전트 탭 활성 시 재조회(`showSideTab`/`selectRun` 어느 쪽에서 트리거하는지 구현이 결정 — 테스트는 훅과 runState 사용만 고정)

- [ ] **Step 2: 구현** — `guided/agents.js`: 위 계약대로. `requestAgentEvents(runId)` → `callTool("pipeline.list_agent_events", {run_id: runId, limit: 20})`. guided.js 훅: `runState.runId` 없으면 런-미선택 렌더; selectRun 성공 경로에서 현재 사이드 탭이 "agents"면 재조회 1줄 추가(staleness 가드는 selectRun의 gen 사용).

- [ ] **Step 3: 배선** — 동일 패턴.

- [ ] **Step 4: 통과 + 커밋** — `feat(rapid-guided): agents tab with per-run agent panel events`

---

### Task 5: 전체 검증 + dev 배포

- [ ] **Step 1: 백엔드** — CI 서브셋 + plan_council + council_skills + literature → PASS
- [ ] **Step 2: 프런트** — guided 패밀리 16파일(기존 12 + connections/skills/agents) → 전부 통과; CI 프런트 서브셋 fail 0
- [ ] **Step 3: 빌드** → `✓ built`
- [ ] **Step 4: push + CI watch** — fast-forward 확인 후 `git push origin HEAD:develop`
- [ ] **Step 5: 배포 확인 + 스모크**

```bash
curl -sS http://127.0.0.1:18087/healthz
```
브라우저: 연결 탭(실측 테이블·포털 카드·재프로브), 스킬 탭(5카드·편집→저장→출처 칩 전환→초기화), 에이전트 탭(런 선택 시 이벤트) 확인.

롤백: `git revert` 후 재push.
