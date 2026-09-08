# Guided 반응형 수정 + 계획 전문가 협의회 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** guided 콘솔이 좁은 창에서 중앙 패널을 항상 보장하도록 하고, 계획 생성 시 도메인 전문가 5인(LLM)이 병렬로 계획을 검토해 판정+승인형 수정 제안을 추가한다.

**Architecture:** 반응형은 프런트 로직만 고친다(복원 클램프 + resize 재클램프 + 좁은 창 기본값). 협의회는 백엔드 신규 모듈 `plan_council.py` + 도구 `pipeline.plan_council`(discuss_plan과 동일한 `runner.gemini.chat` 재사용, ThreadPoolExecutor 병렬) + 프런트 신규 모듈 `guided/council.js`(계획 생성 후 자동 발화, 세대 가드, 기존 proposal 흐름에 병합).

**Tech Stack:** Python stdlib (`concurrent.futures`, `json`, `re`), vanilla ES modules, `node --test`, pytest, vite.

**Spec:** `docs/specs/2026-09-07-guided-responsive-plan-council-design.md`

**주의:** 저장소에 관련 없는 dirty 파일이 많다. 각 태스크가 지정한 파일만 `git add` 한다. `git add -A`/`git commit -a` 금지. 테스트 실행은 프런트 `cd frontend && node --test …`, 백엔드 `PYTHONPATH=pipeline-mcp/src pytest …` (src 레이아웃이라 PYTHONPATH 필수).

---

### Task 1: 백엔드 `plan_council` 모듈 (TDD)

**Files:**
- Create: `pipeline-mcp/tests/test_plan_council.py`
- Create: `pipeline-mcp/src/pipeline_mcp/plan_council.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `pipeline-mcp/tests/test_plan_council.py` (전문 교체):

```python
import unittest

from pipeline_mcp.plan_council import (
    EXPERTS,
    Expert,
    build_expert_prompt,
    parse_expert_reply,
    review_suggestions,
    run_council,
)


class FakeGemini:
    """build_expert_prompt 가 '전문가 ID: <id>' 줄을 넣으므로 id 로 응답을 고른다."""

    def __init__(self, replies=None, raise_for=None, error_for=None):
        self.replies = dict(replies or {})
        self.raise_for = set(raise_for or ())
        self.error_for = set(error_for or ())

    def is_available(self) -> bool:
        return True

    def chat(self, system: str, user: str) -> str:
        for expert_id in self.raise_for:
            if f"전문가 ID: {expert_id}" in user:
                raise RuntimeError("boom")
        for expert_id in self.error_for:
            if f"전문가 ID: {expert_id}" in user:
                return "Error communicating with Gemini: quota"
        for expert_id, reply in self.replies.items():
            if f"전문가 ID: {expert_id}" in user:
                return reply
        return "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"


PLAN = {
    "objective": {
        "normalized_weights": {"solubility": 0.5, "structural_preservation": 0.3, "diversity": 0.2},
        "budget": {"designs": 48, "length_aa": 120},
    },
    "route": {"purpose": "monomer_solubility_redesign", "executable": True, "validated": True},
    "cost_estimate": {"estimated_seconds": 600},
    "decisions": [
        {"field": "design_purpose", "value": "monomer_solubility_redesign", "rationale": "기본 경로",
         "editable": False, "evidence": []},
        {"field": "use_soluble_model", "value": True, "rationale": "용해도 목표", "editable": True,
         "evidence": [{"kind": "literature", "statement": "ProteinMPNN soluble 가중치 공개",
                       "source": "Dauparas et al. 2022"}]},
        {"field": "soluprot_cutoff", "value": 0.5, "rationale": "게이트 1 임계값", "editable": True, "evidence": []},
        {"field": "sampling_temp", "value": 0.3, "rationale": "다양성 가중치", "editable": True, "evidence": []},
        {"field": "af2_verification", "value": "keep", "rationale": "검증됨", "editable": False, "evidence": []},
    ],
    "editable_fields": ["use_soluble_model", "soluprot_cutoff", "sampling_temp"],
    "locked_fields": ["design_purpose", "af2_verification"],
}


class TestExperts(unittest.TestCase):
    def test_expert_tables_are_disjoint(self) -> None:
        seen_fields = [f for e in EXPERTS for f in e.decision_fields]
        seen_weights = [w for e in EXPERTS for w in e.weight_scope]
        self.assertEqual(len(seen_fields), len(set(seen_fields)))
        self.assertEqual(len(seen_weights), len(set(seen_weights)))
        self.assertEqual(len(EXPERTS), 5)

    def test_prompt_contains_plan_and_ownership(self) -> None:
        expert = EXPERTS[0]
        prompt = build_expert_prompt(PLAN, expert)
        self.assertIn("전문가 ID: solubility", prompt)
        self.assertIn("당신이 제안할 수 있는 필드: ['use_soluble_model', 'soluprot_cutoff']", prompt)
        self.assertIn("고정 필드", prompt)


class TestParse(unittest.TestCase):
    def test_fenced_json_is_parsed(self) -> None:
        raw = "좋습니다.\n```json\n{\"verdict\": \"warn\", \"reasons\": [\"컷오프가 높다\"], \"suggestions\": []}\n```"
        parsed = parse_expert_reply(raw)
        self.assertEqual(parsed["verdict"], "warn")
        self.assertEqual(parsed["reasons"], ["컷오프가 높다"])
        self.assertEqual(parsed["parse_error"], "")

    def test_invalid_reply_is_unavailable(self) -> None:
        for raw in ("", "말만 있고 json 없음", "```json\nnot json\n```",
                    "```json\n{\"verdict\": \"maybe\"}\n```"):
            parsed = parse_expert_reply(raw)
            self.assertTrue(parsed["parse_error"], raw)
            self.assertEqual(parsed["verdict"], "")


class TestReview(unittest.TestCase):
    def test_owned_and_editable_suggestion_applies(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [{
            "field": "soluprot_cutoff", "value": 0.4, "rationale": "완화",
            "evidence": [{"kind": "assumption", "statement": "낮춰도 안전하다고 본다"}],
        }])
        self.assertEqual(applicable, {"soluprot_cutoff": 0.4})
        self.assertEqual(rejected, {})

    def test_ownership_violation_is_rejected(self) -> None:
        expert = EXPERTS[0]  # solubility: use_soluble_model, soluprot_cutoff
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "sampling_temp", "value": 0.5, "rationale": "x",
             "evidence": [{"kind": "assumption", "statement": "s"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("sampling_temp", rejected)
        self.assertIn("소유", rejected["sampling_temp"]["reason"])

    def test_locked_field_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("af2_verification",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "af2_verification", "value": "drop", "rationale": "x",
             "evidence": [{"kind": "assumption", "statement": "s"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("고정", rejected["af2_verification"]["reason"])

    def test_out_of_range_value_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "soluprot_cutoff", "value": 1.5, "rationale": "x",
             "evidence": [{"kind": "assumption", "statement": "s"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("범위", rejected["soluprot_cutoff"]["reason"])

    def test_evidence_without_source_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "soluprot_cutoff", "value": 0.4, "rationale": "x",
             "evidence": [{"kind": "literature", "statement": "어딘가에 있다"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("근거", rejected["soluprot_cutoff"]["reason"])

    def test_suggestion_without_evidence_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "soluprot_cutoff", "value": 0.4, "rationale": "x", "evidence": []},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("근거 없는 제안", rejected["soluprot_cutoff"]["reason"])


class TestCouncil(unittest.TestCase):
    def test_without_gemini_skips(self) -> None:
        for gemini in (None, object()):
            out = run_council(PLAN, gemini)
            self.assertEqual(out["council"], [])
            self.assertTrue(out["notes"])

    def test_all_experts_answer(self) -> None:
        reply = ("```json\n{\"verdict\": \"warn\", \"reasons\": [\"r\"], "
                 "\"suggestions\": [{\"field\": \"soluprot_cutoff\", \"value\": 0.4, "
                 "\"rationale\": \"완화\", \"evidence\": "
                 "[{\"kind\": \"assumption\", \"statement\": \"s\"}]}]}\n```")
        gemini = FakeGemini(replies={e.id: reply for e in EXPERTS})
        out = run_council(PLAN, gemini)
        self.assertEqual(len(out["council"]), 5)
        self.assertEqual([row["status"] for row in out["council"]], ["ok"] * 5)
        self.assertEqual(out["applicable_edits"], {"soluprot_cutoff": 0.4})

    def test_gemini_error_string_marks_error(self) -> None:
        gemini = FakeGemini(error_for={"stability"})
        out = run_council(PLAN, gemini)
        row = next(r for r in out["council"] if r["expert_id"] == "stability")
        self.assertEqual(row["status"], "error")

    def test_raising_expert_is_error_and_others_survive(self) -> None:
        gemini = FakeGemini(raise_for={"experiment"})
        out = run_council(PLAN, gemini)
        row = next(r for r in out["council"] if r["expert_id"] == "experiment")
        self.assertEqual(row["status"], "error")
        self.assertEqual(sum(1 for r in out["council"] if r["status"] == "ok"), 4)

    def test_council_is_sorted_by_expert_order(self) -> None:
        gemini = FakeGemini()
        out = run_council(PLAN, gemini)
        self.assertEqual([r["expert_id"] for r in out["council"]], [e.id for e in EXPERTS])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `cd /opt/protein_pipeline-work && PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_plan_council.py -q`
Expected: FAIL (`ModuleNotFoundError: pipeline_mcp.plan_council`)

- [ ] **Step 3: 모듈 구현** — `pipeline-mcp/src/pipeline_mcp/plan_council.py` (전문 교체):

```python
"""계획을 도메인 전문가 5인에게 병렬로 검토시키는 모듈.

계약은 세 가지다.

1. 전문가는 계획을 고치지 못한다 — 제안만 하고, 적용은 approve_plan 이 담당한다.
2. 각 전문가는 자기 소유 decision 필드만 제안할 수 있다. 소유권 밖 제안은
   거부 사유와 함께 돌려보낸다.
3. 근거 없는 제안은 만들 수 없다(objective_planner.Evidence 규칙을 그대로 쓴다).

LLM 호출은 discuss_plan 과 같은 runner.gemini(GeminiClient) 를 쓴다. chat 은
동기 블로킹이라 ThreadPoolExecutor 로 병렬화한다. 어느 전문가 하나가 실패해도
나머지 결과는 살아 있고, 도구 자체는 항상 계약 응답을 돌려준다.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .objective_planner import Evidence

EXPERT_TIMEOUT_SECONDS = 30.0
GEMINI_ERROR_PREFIX = "Error communicating with Gemini"


class Expert:
    __slots__ = ("id", "name", "charter", "decision_fields", "weight_scope")

    def __init__(self, expert_id: str, name: str, charter: str,
                 decision_fields: tuple = (), weight_scope: tuple = ()):
        self.id = expert_id
        self.name = name
        self.charter = charter
        self.decision_fields = tuple(decision_fields)
        self.weight_scope = tuple(weight_scope)


COUNCIL_OUTPUT_CONTRACT = (
    "출력 계약: 마지막에 fenced json block 하나만 남긴다.\n"
    "```json\n"
    "{\"verdict\": \"ok\" | \"warn\" | \"block\", \"reasons\": [\"…\"], "
    "\"suggestions\": [{\"field\": \"필드명\", \"value\": 값, \"rationale\": \"…\", "
    "\"evidence\": [{\"kind\": \"internal_measurement\" | \"literature\" | \"assumption\", "
    "\"statement\": \"…\", \"source\": \"…\", \"value\": \"…\"}]}]}\n"
    "```\n"
    "규칙:\n"
    "1. 제안은 '당신이 제안할 수 있는 필드'에 적힌 것만 한다. 다른 필드를 제안하면 시스템이 거부한다.\n"
    "2. 근거 없는 제안을 하지 않는다. 측정/문헌 근거에는 source 가 필수다. 모르면 제안하지 않는다.\n"
    "3. 계획에 없는 수치·인용·데이터셋 이름을 지어내지 않는다.\n"
    "4. reasons 는 한국어로 각 1문장, 최대 5개. 제안 권한이 없으면 판정과 reasons 만 낸다.\n"
    "5. 산문은 최대 4문장. json block 뒤에는 아무것도 쓰지 않는다."
)

_EXPERT_SOLUBILITY = (
    "당신은 단백질 용해도와 응집 전문가다. 계획의 용해도·응집 측면 — soluble 모델 "
    "사용 여부, 게이트 1(soluprot) 컷오프, solubility/aggregation 가중치 — 를 검토한다. "
    "컷오프를 낮추면 통과율이 올라가지만 품질이 희석될 수 있고, 높이면 그 반대다. "
    "가중치는 제안할 수 없으니 문제가 보이면 reasons 로 지적한다."
)
_EXPERT_STABILITY = (
    "당신은 단백질 안정성 전문가다. 계획의 안정성 측면 — stability 가중치, 열안정성 "
    "평가(ThermoMPNN ΔΔG, WT 비교)가 계획에 반영되어 있는지 — 를 검토한다. 안정성은 "
    "용해도·구조 목표와 상충할 수 있다. 제안 권한이 없으니 판정과 reasons 로만 의견을 낸다."
)
_EXPERT_STRUCTURE = (
    "당신은 구조 보존과 결합 전문가다. 계획의 구조 검증 측면 — AF2 검증 유지 여부, "
    "structural_preservation/binding 가중치 — 를 검토한다. AF2 를 값싼 대체물로 바꾸는 "
    "제안이 나오면 근거 수준을 엄격히 따진다."
)
_EXPERT_DESIGN_SPACE = (
    "당신은 설계 공간과 예산 전문가다. 설계 수, 백본당 서열 수, sampling_temp, "
    "다양성 가중치, 비용 추정의 균형을 검토한다. 수를 늘리면 비용이 그만큼 든다 — "
    "cost_estimate 를 보고 판단한다."
)
_EXPERT_EXPERIMENT = (
    "당신은 실험 실현성 전문가다. 모티프 리아빌리티(탈아미드 NG, 이성질화 DG, 산화 MW, "
    "유리 시스테인), developability, 발현·합성 관점에서 계획을 검토한다. 제안 권한이 "
    "없으니 판정과 reasons 로만 의견을 낸다."
)

EXPERTS = (
    Expert("solubility", "용해도·응집 전문가", _EXPERT_SOLUBILITY,
           decision_fields=("use_soluble_model", "soluprot_cutoff"),
           weight_scope=("solubility", "aggregation")),
    Expert("stability", "안정성 전문가", _EXPERT_STABILITY,
           decision_fields=(), weight_scope=("stability",)),
    Expert("structure", "구조 보존·결합 전문가", _EXPERT_STRUCTURE,
           decision_fields=("af2_verification",),
           weight_scope=("structural_preservation", "binding")),
    Expert("design_space", "설계 공간·예산 전문가", _EXPERT_DESIGN_SPACE,
           decision_fields=("sequences_per_backbone", "sampling_temp", "gate0_feature"),
           weight_scope=("diversity",)),
    Expert("experiment", "실험 실현성 전문가", _EXPERT_EXPERIMENT,
           decision_fields=(), weight_scope=("developability",)),
)


def build_expert_prompt(plan: dict, expert: Expert) -> str:
    """모든 전문가에게 같은 계획 본문을 주고, 소유 필드만 다르게 붙인다."""
    lines = ["다음은 이미 확정된 설계 계획입니다.", ""]
    objective = plan.get("objective") or {}
    if objective.get("normalized_weights"):
        lines.append(f"목표 가중치: {objective['normalized_weights']}")
    budget = objective.get("budget") or {}
    if budget:
        lines.append(f"예산: {budget}")
    route = plan.get("route") or {}
    if route.get("purpose"):
        lines.append(f"설계 목적: {route.get('purpose')} "
                     f"(실행 가능 {route.get('executable')}, 검증됨 {route.get('validated')})")
    if plan.get("cost_estimate"):
        lines.append(f"비용 추정: {plan['cost_estimate']}")
    lines.append("")
    for decision in plan.get("decisions", []):
        editable = "수정 가능" if decision.get("editable") else "고정"
        lines.append(f"- {decision.get('field')} = {decision.get('value')} [{editable}]")
        lines.append(f"  이유: {decision.get('rationale')}")
        for ev in decision.get("evidence", []):
            source = f" [출처 {ev.get('source')}]" if ev.get("source") else ""
            lines.append(f"  근거({ev.get('kind')}): {ev.get('statement')}{source}")
    for warning in plan.get("warnings", []):
        lines.append(f"- 경고: {warning}")
    lines.append("")
    lines.append(f"전문가 ID: {expert.id}")
    lines.append(f"당신이 제안할 수 있는 필드: {list(expert.decision_fields)}")
    lines.append(f"수정 가능 필드(전체): {plan.get('editable_fields') or []}")
    lines.append(f"고정 필드(편집 거부됨): {plan.get('locked_fields') or []}")
    return "\n".join(lines)


def parse_expert_reply(raw: str) -> dict:
    """전문가 응답을 판정/이유/제안으로 갈라낸다. 실패는 unavailable 근거가 된다."""
    text = str(raw or "")
    excerpt = text[:400]
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if not match:
        return {"verdict": "", "reasons": [], "suggestions": [],
                "parse_error": "json block 없음", "raw_excerpt": excerpt}
    try:
        block = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return {"verdict": "", "reasons": [], "suggestions": [],
                "parse_error": "json 파싱 실패", "raw_excerpt": excerpt}
    if not isinstance(block, dict):
        return {"verdict": "", "reasons": [], "suggestions": [],
                "parse_error": "json 이 객체가 아님", "raw_excerpt": excerpt}
    verdict = str(block.get("verdict") or "")
    if verdict not in ("ok", "warn", "block"):
        return {"verdict": "", "reasons": [], "suggestions": [],
                "parse_error": f"알 수 없는 verdict: {verdict!r}", "raw_excerpt": excerpt}
    reasons = [str(r) for r in (block.get("reasons") or []) if str(r).strip()]
    suggestions = [s for s in (block.get("suggestions") or []) if isinstance(s, dict)]
    return {"verdict": verdict, "reasons": reasons, "suggestions": suggestions,
            "parse_error": "", "raw_excerpt": ""}


#: 필드별 허용 값 범위. (하한, 상한) — 상한 None 은 무한대.
FIELD_VALUE_RULES = {
    "soluprot_cutoff": (0.0, 1.0),
    "sequences_per_backbone": (1, None),
    "sampling_temp": (0.0, None),
}


def _value_in_range(field: str, value) -> bool:
    rule = FIELD_VALUE_RULES.get(field)
    if not rule:
        return True
    low, high = rule
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if number < low:
        return False
    return high is None or number <= high


def review_suggestions(plan: dict, expert: Expert, suggestions) -> tuple[dict, dict]:
    """제안을 적용 가능/거부로 갈라낸다. 소유권 → 고정 → 값 → 근거 순서로 검증한다."""
    editable = set(plan.get("editable_fields") or [])
    applicable: dict = {}
    rejected: dict = {}
    for item in suggestions or []:
        field = str(item.get("field") or "")
        value = item.get("value")
        if not field:
            rejected["(필드 없음)"] = {"value": value, "reason": "필드명이 없는 제안"}
            continue
        if field not in expert.decision_fields:
            rejected[field] = {"value": value, "reason": f"{expert.name}의 소유 필드가 아님"}
            continue
        if field not in editable:
            rejected[field] = {"value": value, "reason": "계획에서 고정된 필드"}
            continue
        if not _value_in_range(field, value):
            rejected[field] = {"value": value, "reason": "허용 범위 밖 값"}
            continue
        try:
            checked = tuple(
                Evidence(**dict(e)) for e in (item.get("evidence") or []) if isinstance(e, dict)
            )
        except (TypeError, ValueError) as exc:
            rejected[field] = {"value": value, "reason": f"근거 규칙 위반: {exc}"}
            continue
        if not checked:
            rejected[field] = {"value": value, "reason": "근거 없는 제안"}
            continue
        applicable[field] = value
    return applicable, rejected


def _ask_expert(gemini, plan: dict, expert: Expert) -> dict:
    raw = str(gemini.chat(expert.charter, build_expert_prompt(plan, expert)))
    base = {"expert_id": expert.id, "name": expert.name, "verdict": "", "reasons": [],
            "suggestions_count": 0, "applicable": {}, "rejected": {}}
    if raw.startswith(GEMINI_ERROR_PREFIX):
        return {**base, "status": "error", "raw_excerpt": raw[:400]}
    parsed = parse_expert_reply(raw)
    applicable, rejected = review_suggestions(plan, expert, parsed["suggestions"])
    return {**base,
            "verdict": parsed["verdict"],
            "reasons": parsed["reasons"],
            "suggestions_count": len(parsed["suggestions"]),
            "status": "ok" if not parsed["parse_error"] else "unavailable",
            "applicable": applicable,
            "rejected": rejected,
            **({"parse_error": parsed["parse_error"], "raw_excerpt": parsed["raw_excerpt"]}
               if parsed["parse_error"] else {})}


def run_council(plan: dict, gemini, *, timeout: float = EXPERT_TIMEOUT_SECONDS) -> dict:
    """전문가 5인을 병렬로 돌린다. gemini 가 없으면 생략. 실패가 계획을 막지 않는다."""
    if gemini is None or not getattr(gemini, "is_available", lambda: False)():
        return {"council": [], "applicable_edits": {}, "rejected_edits": {},
                "notes": ["LLM 연결 없음 — 전문가 검토를 생략합니다"]}
    council: list[dict] = []
    applicable_edits: dict = {}
    rejected_edits: dict = {}
    notes: list[str] = []
    pool = ThreadPoolExecutor(max_workers=len(EXPERTS))
    futures = {pool.submit(_ask_expert, gemini, plan, expert): expert for expert in EXPERTS}
    try:
        for future in as_completed(futures, timeout=timeout):
            expert = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                council.append({"expert_id": expert.id, "name": expert.name, "verdict": "",
                                "reasons": [], "suggestions_count": 0, "status": "error",
                                "raw_excerpt": f"{type(exc).__name__}: {exc}"})
                continue
            council.append({key: result[key] for key in
                            ("expert_id", "name", "verdict", "reasons",
                             "suggestions_count", "status")})
            if result.get("parse_error"):
                council[-1]["parse_error"] = result["parse_error"]
                council[-1]["raw_excerpt"] = result["raw_excerpt"]
            applicable_edits.update(result["applicable"])
            rejected_edits.update(result["rejected"])
    except TimeoutError:
        notes.append(f"일부 전문가가 {timeout:.0f}초 안에 답하지 못했습니다.")
    finally:
        # 답한 결과는 이미 수집했다. hung thread 가 있어도 응답을 막지 않는다.
        pool.shutdown(wait=False, cancel_futures=True)
    answered = {row["expert_id"] for row in council}
    for expert in EXPERTS:
        if expert.id not in answered:
            council.append({"expert_id": expert.id, "name": expert.name, "verdict": "",
                            "reasons": [], "suggestions_count": 0, "status": "unavailable",
                            "raw_excerpt": "timeout"})
    order = {expert.id: index for index, expert in enumerate(EXPERTS)}
    council.sort(key=lambda row: order.get(row["expert_id"], len(order)))
    return {"council": council, "applicable_edits": applicable_edits,
            "rejected_edits": rejected_edits, "notes": notes}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /opt/protein_pipeline-work && PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_plan_council.py -q`
Expected: PASS (15 tests)

- [ ] **Step 5: 커밋**

```bash
git add pipeline-mcp/src/pipeline_mcp/plan_council.py pipeline-mcp/tests/test_plan_council.py
git commit -m "feat(rapid): plan council module with five parallel expert reviewers"
```

---

### Task 2: 도구 등록 `pipeline.plan_council`

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py` — 도구 정의 목록(`"pipeline.discuss_plan"` 항목 뒤, ~8865행 부근)과 dispatch 분기(`if name == "pipeline.discuss_plan":` 블록 다음, ~9706행 부근)
- Test: `pipeline-mcp/tests/test_plan_council.py` (클래스 추가)

- [ ] **Step 1: 실패하는 테스트 추가** — `test_plan_council.py`의 상단 import 블록에 추가:

```python
import shutil
import tempfile

from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher, tool_definitions
```

그리고 파일 끝(`if __name__ == "__main__":` 직전)에 클래스 추가:

```python
class TestRegistration(unittest.TestCase):
    def test_tool_is_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        self.assertIn("pipeline.plan_council", names)

    def test_dispatch_rejects_non_object_plan(self) -> None:
        runner = PipelineRunner(output_root="/tmp/unused-council", mmseqs=None,
                                proteinmpnn=None, soluprot=None, af2=None)
        out = ToolDispatcher(runner).call_tool("pipeline.plan_council", {"plan": "nope"})
        self.assertIn("error", out)

    def test_dispatch_uses_runner_gemini(self) -> None:
        tmp = tempfile.mkdtemp(prefix="council_")
        try:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None,
                                    soluprot=None, af2=None)
            runner.gemini = FakeGemini(replies={e.id: (
                "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"
            ) for e in EXPERTS})
            out = ToolDispatcher(runner).call_tool("pipeline.plan_council", {"plan": PLAN})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(len(out["council"]), 5)
        self.assertEqual(out["notes"], [])
```

- [ ] **Step 2: 실패 확인**

Run: `cd /opt/protein_pipeline-work && PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_plan_council.py -k Registration -q`
Expected: FAIL (도구가 목록/분기에 없음)

- [ ] **Step 3: 도구 정의 추가** — `tools.py`의 tool 목록에서 `"pipeline.discuss_plan"` 항목(8865행 부근) 뒤에 삽입:

```python
        {
            "name": "pipeline.plan_council",
            "description": (
                "Have five domain experts (solubility, stability, structure, design "
                "space/budget, experimental developability) review a generated plan in "
                "parallel. Each returns a verdict (ok/warn/block), reasons, and edit "
                "suggestions limited to its own editable decision fields. Suggestions "
                "are proposals only: applying them still goes through "
                "pipeline.approve_plan. Returns skip notes when no LLM is configured."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"plan": {"type": "object"}},
                "required": ["plan"],
            },
        },
```

- [ ] **Step 4: dispatch 분기 추가** — `if name == "pipeline.discuss_plan":` 블록이 끝나고 `if name == "pipeline.approve_plan":`이 나오기 직전(~9706행)에 삽입:

```python
        if name == "pipeline.plan_council":
            from .plan_council import run_council

            plan = arguments.get("plan")
            if not isinstance(plan, dict):
                return {"error": "plan must be an object"}
            return run_council(plan, getattr(self.runner, "gemini", None))
```

- [ ] **Step 5: 통과 확인 + 기존 백엔드 회귀 없음**

Run: `cd /opt/protein_pipeline-work && PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_plan_council.py -q`
Expected: PASS (18 tests)

Run: `cd /opt/protein_pipeline-work && PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_http_server_auth.py pipeline-mcp/tests/test_mcp_http_route.py pipeline-mcp/tests/test_oidc_auth.py pipeline-mcp/tests/test_session_auth.py pipeline-mcp/tests/test_runpod_admin.py -q`
Expected: PASS (68 tests — CI 서브셋)

- [ ] **Step 6: 커밋**

```bash
git add pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/tests/test_plan_council.py
git commit -m "feat(rapid): register pipeline.plan_council tool"
```

---

### Task 3: 프런트 협의회 UI (council.js + plan.js 연결)

**Files:**
- Create: `frontend/guided/council.js`
- Create: `frontend/tests/guided-council.test.js`
- Modify: `frontend/guided.html` — `#decisions`(114행) 다음에 협의회 섹션 추가
- Modify: `frontend/guided/plan.js` — import, state, generatePlan 발화, sendChat 병합
- Modify: `frontend/guided.css` — `.councilbox` 최소 스타일

- [ ] **Step 1: 실패하는 테스트** — `frontend/tests/guided-council.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// renderCouncil 은 함수 안에서만 document 를 만진다 — import 시점엔 불필요.
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

const { councilCardModels, renderCouncil, requestCouncil } = await import("../guided/council.js");

const COUNCIL = [
  { expert_id: "solubility", name: "용해도·응집 전문가", verdict: "warn", status: "ok",
    reasons: ["컷오프가 높다"], suggestions_count: 1 },
  { expert_id: "stability", name: "안정성 전문가", verdict: "", status: "unavailable",
    reasons: [], suggestions_count: 0, raw_excerpt: "timeout" },
];

test("councilCardModels maps verdicts to labels and chips", () => {
  const models = councilCardModels(COUNCIL);
  assert.equal(models[0].label, "경고");
  assert.equal(models[0].chipClass, "warnchip");
  assert.equal(models[1].label, "");
  assert.equal(models[1].chipClass, "");
  assert.equal(models[1].status, "unavailable");
});

test("councilCardModels tolerates missing fields", () => {
  const models = councilCardModels([null, {}, "x"]);
  assert.equal(models.length, 3);
  assert.equal(models[0].name, "");
});

test("renderCouncil pending shows the reviewing note", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(host, [], { pending: true });
  assert.match(host.children[0].textContent, /검토하는 중/);
});

test("renderCouncil paints a card per expert with chip and reasons", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(host, COUNCIL, { notes: [] });
  const cards = host.children.filter((c) => c.className === "skill");
  assert.equal(cards.length, 2);
  const chip = cards[0].children[0].children.find((c) => c.className === "warnchip");
  assert.equal(chip.textContent, "경고");
});

test("renderCouncil shows raw excerpt as details and notes when empty", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(host, COUNCIL, { notes: [] });
  assert.ok(host.children.some((c) => c.tagName === "DETAILS"));
  const empty = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderCouncil(empty, [], { notes: ["LLM 연결 없음"] });
  assert.match(empty.children[0].textContent, /LLM 연결 없음/);
});

test("plan.js fires the council with a generation guard and merges proposals", () => {
  const src = readFileSync(new URL("../guided/plan.js", import.meta.url), "utf8");
  assert.ok(src.includes("fireCouncil(plan)"), "generatePlan must fire the council");
  assert.ok(src.includes("councilGen"), "council calls must be generation-guarded");
  assert.ok(src.includes("currentProposals()"), "proposals must merge council and chat edits");
});

test("guided.html hosts the council box", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('id="councilBox"'));
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /opt/protein_pipeline-work/frontend && node --test tests/guided-council.test.js`
Expected: FAIL (`Cannot find module ../guided/council.js`)

- [ ] **Step 3: `frontend/guided/council.js` 작성** (전문 교체):

```js
// frontend/guided/council.js — 계획 전문가 협의회. 순수 모델 함수와 그리는
// 함수를 나눠 node 테스트가 가능하게 한다. 서버 도구는 pipeline.plan_council.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export const VERDICT_LABEL = { ok: "적합", warn: "경고", block: "차단" };
export const VERDICT_CHIP = { ok: "okchip", warn: "warnchip", block: "badchip" };

export function councilCardModels(council) {
  const rows = Array.isArray(council) ? council : [];
  return rows.map((row) => {
    const item = row && typeof row === "object" ? row : {};
    return {
      id: String(item.expert_id || ""),
      name: String(item.name || item.expert_id || ""),
      status: String(item.status || "ok"),
      verdict: String(item.verdict || ""),
      label: VERDICT_LABEL[item.verdict] || "",
      chipClass: VERDICT_CHIP[item.verdict] || "",
      reasons: Array.isArray(item.reasons) ? item.reasons.map(String) : [],
      suggestionsCount: Number(item.suggestions_count || 0),
      rawExcerpt: String(item.raw_excerpt || ""),
    };
  });
}

export function renderCouncil(host, council, { pending = false, notes = [] } = {}) {
  host.replaceChildren();
  if (pending) {
    host.appendChild(el("p", "note", "전문가 5인이 계획을 검토하는 중…"));
    return;
  }
  const models = councilCardModels(council);
  if (!models.length) {
    for (const note of notes.length ? notes : ["전문가 검토가 생략되었습니다."]) {
      host.appendChild(el("p", "note", note));
    }
    return;
  }
  for (const note of notes) host.appendChild(el("p", "note", note));
  for (const model of models) {
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.append(el("span", "name", model.name));
    if (model.label) {
      head.appendChild(el("span", model.chipClass, model.label));
    } else {
      head.appendChild(el("span", "chip", model.status === "error" ? "오류" : "검토 불가"));
    }
    if (model.suggestionsCount) {
      head.appendChild(el("span", "chip", `제안 ${model.suggestionsCount}건`));
    }
    card.appendChild(head);
    for (const reason of model.reasons) {
      card.appendChild(el("p", "note", `· ${reason}`));
    }
    if (model.rawExcerpt) {
      // 원문은 LLM 산출물이라 그대로 믿지 않는다 - 접이식으로만 참조를 남긴다.
      // (구현 확정: details 는 카드 안이 아니라 호스트에 카드 바로 뒤에 붙는다 -
      //  계약 테스트가 host.children 기준이고, 카드 chrome 을 깨지 않는다.)
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "원문 보기";
      details.appendChild(summary);
      const pre = document.createElement("pre");
      pre.className = "artifacttext";
      pre.textContent = model.rawExcerpt;
      details.appendChild(pre);
      host.appendChild(details);
    }
    host.appendChild(card);
  }
}

export async function requestCouncil(plan) {
  const out = await callTool("pipeline.plan_council", { plan });
  if (out && out.error) throw new Error(out.error);
  return out;
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd /opt/protein_pipeline-work/frontend && node --test tests/guided-council.test.js`
Expected: PASS (7 tests)

- [ ] **Step 5: plan.js 연결** — 네 곳:

1. import 추가 (1-7행 부근, 기존 import 아래):
```js
import { renderCouncil, requestCouncil } from "./council.js";
```

2. state 확장 (475행):
```js
const state = { plan: null, edits: {}, overrides: null, chat: [], llm: {},
                councilGen: 0, councilApplicable: {}, councilRejected: {},
                chatApplicable: {}, chatRejected: {} };
```

3. `generatePlan()` 안 — `document.getElementById("proposals").replaceChildren();`(633행) 다음에 발화 추가:
```js
    fireCouncil(plan);
```
그리고 `generatePlan` 함수 뒤(649행 `}` 다음)에 두 함수 추가:
```js
// 계획이 생기면 곧바로 전문가 협의회를 돌린다. 계획 렌더를 막지 않는다 - 
// 협의회는 도착하는 대로 판정 카드와 제안을 채운다. 재생성되면 세대가 바뀌어
// 늦게 도착한 옛 판정은 버린다.
function fireCouncil(plan) {
  const host = document.getElementById("councilBox");
  const gen = ++state.councilGen;
  state.councilApplicable = {};
  state.councilRejected = {};
  state.chatApplicable = {};
  state.chatRejected = {};
  renderCouncil(host, [], { pending: true });
  requestCouncil(plan).then((out) => {
    if (gen !== state.councilGen) return;
    state.councilApplicable = out.applicable_edits || {};
    state.councilRejected = out.rejected_edits || {};
    renderCouncil(host, out.council || [], { notes: out.notes || [] });
    renderProposals(...currentProposals());
  }).catch((error) => {
    if (gen !== state.councilGen) return;
    renderCouncil(host, [], { notes: [`전문가 검토에 실패했습니다: ${errorText(error)}`] });
  });
}

function currentProposals() {
  return [
    { ...(state.councilApplicable || {}), ...(state.chatApplicable || {}) },
    { ...(state.councilRejected || {}), ...(state.chatRejected || {}) },
  ];
}
```

4. `sendChat()` 성공 경로 (549행) — `renderProposals(out.applicable_edits, out.rejected_edits);`를 교체:
```js
    state.chatApplicable = out.applicable_edits || {};
    state.chatRejected = out.rejected_edits || {};
    renderProposals(...currentProposals());
```

- [ ] **Step 6: guided.html — `#decisions`(114행) 다음에 추가:**

```html
          <h3>전문가 협의회</h3>
          <div id="councilBox" class="councilbox" aria-live="polite"></div>
```

- [ ] **Step 7: guided.css — `.councilbox` 규칙 추가** (`.proposals` 스타일 근처):

```css
.councilbox { display: grid; gap: 8px; margin-top: 6px; }
.councilbox .skill { padding: 10px 12px; }
```

- [ ] **Step 8: 전체 확인**

Run: `cd /opt/protein_pipeline-work/frontend && node --test tests/guided-council.test.js tests/guided.test.js`
Expected: PASS (78 tests = 7 + 71)

Run: `cd /opt/protein_pipeline-work && npm --prefix frontend run build`
Expected: `✓ built`

- [ ] **Step 9: 커밋**

```bash
git add frontend/guided/council.js frontend/tests/guided-council.test.js frontend/guided/plan.js frontend/guided.html frontend/guided.css
git commit -m "feat(rapid-guided): automatic expert council review on plan generation"
```

---

### Task 4: 반응형 레이아웃 클램프

**Files:**
- Modify: `frontend/guided.js` — 상수·순수 함수 추가, `initSplitters()` 교체 (393-448행 부근)
- Create: `frontend/tests/guided-layout.test.js`

- [ ] **Step 1: 실패하는 테스트** — `frontend/tests/guided-layout.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { clampPanes, choosePaneDefault } = await import("../guided.js");

test("wide saved panes are clamped so the center stays visible", () => {
  const out = clampPanes({ left: 600, right: 600 }, 1200);
  assert.equal(out.left + out.right, 1200 - 12 - 360);
});

test("asymmetric saved panes shrink proportionally", () => {
  const out = clampPanes({ left: 1000, right: 400 }, 1200);
  assert.equal(out.left + out.right, 828);
  assert.ok(out.left > out.right, "bigger pane keeps a bigger share");
});

test("a pane floored at the minimum pushes the shrink to the other side", () => {
  const out = clampPanes({ left: 1400, right: 200 }, 1200);
  assert.equal(out.right, 200);
  assert.equal(out.left + out.right, 828);
});

test("panes within budget pass through untouched", () => {
  const out = clampPanes({ left: 264, right: 340 }, 1440);
  assert.deepEqual(out, { left: 264, right: 340 });
});

test("at or below 1100px the stacked mode takes over and clamping is a no-op", () => {
  assert.deepEqual(clampPanes({ left: 900, right: 900 }, 1100), { left: 900, right: 900 });
});

test("saved values win; the narrow default only applies between 1101 and 1280", () => {
  assert.deepEqual(choosePaneDefault(1150, null), { left: 232, right: 300 });
  assert.deepEqual(choosePaneDefault(1440, null), { left: 264, right: 340 });
  assert.deepEqual(choosePaneDefault(1150, { left: 500, right: 500 }), { left: 500, right: 500 });
  assert.deepEqual(choosePaneDefault(1000, null), { left: 264, right: 340 });
});

test("initSplitters clamps on restore and re-clamps on resize", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  const section = src.slice(src.indexOf("function initSplitters"), src.indexOf("function showPanel") > 0 ? src.indexOf("function showPanel") : undefined);
  assert.ok(section.includes("clampPanes("), "restore must go through the clamp");
  assert.ok(section.includes('addEventListener("resize"'), "resize must re-clamp");
  assert.ok(section.includes("choosePaneDefault("));
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /opt/protein_pipeline-work/frontend && node --test tests/guided-layout.test.js`
Expected: FAIL (`clampPanes is not exported`)

- [ ] **Step 3: guided.js 수정** — 393-413행 부근(상수 + readPanes + applyPanes + initSplitters 시작):

상수 블록을 교체:
```js
const PANE_KEY = "kbf.guided.panes";
const PANE_MIN = 200;
const PANE_DEFAULT = { left: 264, right: 340 };
const PANE_DEFAULT_NARROW = { left: 232, right: 300 };
const SPLITTER_TOTAL_PX = 12;
const CENTER_MIN_PX = 360;
```

`applyPanes` 아래에 순수 함수 2개 추가:
```js
// 저장된 폭은 화면이 바뀌면 무의미해진다. 중앙 패널은 항상 CENTER_MIN_PX 를
// 보장한다 - 넓은 모니터에서 넓힌 레일이 노트북 절반 창에서 중앙을 짜부뜨린
// 적이 있다. 초과분은 두 레일의 현재 폭 비율로 나눠 차감한다.
export function clampPanes(panes, layoutWidth) {
  const width = Number(layoutWidth) || 0;
  const left = Math.max(PANE_MIN, Number(panes?.left) || PANE_MIN);
  const right = Math.max(PANE_MIN, Number(panes?.right) || PANE_MIN);
  if (width <= 1100) return { left, right };   // 스택 모드가 CSS 로 덮는다
  const budget = width - SPLITTER_TOTAL_PX - CENTER_MIN_PX;
  const total = left + right;
  if (total <= budget) return { left, right };
  const excess = total - budget;
  const share = total > 0 ? left / total : 0.5;
  let newLeft = left - excess * share;
  let newRight = right - excess * (1 - share);
  // 하한에 닿은 쪽은 고정하고 남은 초과분을 다른 쪽에서 더 뺀다.
  if (newRight < PANE_MIN) {
    newLeft = Math.max(PANE_MIN, budget - PANE_MIN);
    newRight = PANE_MIN;
  } else if (newLeft < PANE_MIN) {
    newLeft = PANE_MIN;
    newRight = Math.max(PANE_MIN, budget - PANE_MIN);
  }
  return { left: Math.round(newLeft), right: Math.round(newRight) };
}

export function choosePaneDefault(width, saved) {
  if (saved && Number(saved.left) > 0 && Number(saved.right) > 0) return saved;
  if (width > 1100 && width <= 1280) return { ...PANE_DEFAULT_NARROW };
  return { ...PANE_DEFAULT };
}
```

`initSplitters()`의 시작 3줄을 교체 (기존):
```js
  const layout = document.querySelector(".layout");
  const panes = readPanes();
  applyPanes(panes);
```
→
```js
  const layout = document.querySelector(".layout");
  const panes = clampPanes(choosePaneDefault(layout.clientWidth, readPanes()), layout.clientWidth);
  applyPanes(panes);
```

`initSplitters()` 함수 본문 끝(키보드 핸들러 for 루프가 닫힌 뒤, 함수 닫기 `}` 직전)에 resize 리스너 추가:
```js
  // 창 크기가 변하면 저장된 폭을 다시 클램프한다. 저장값은 건드리지 않는다 -
  // 창을 다시 넓히면 사용자가 정한 폭으로 돌아간다.
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      panes = clampPanes(panes, layout.clientWidth);
      applyPanes(panes);
    }, 100);
  });
```

- [ ] **Step 4: 통과 확인**

Run: `cd /opt/protein_pipeline-work/frontend && node --test tests/guided-layout.test.js tests/guided.test.js`
Expected: PASS (78 tests = 7 + 71)

Run: `cd /opt/protein_pipeline-work && npm --prefix frontend run build`
Expected: `✓ built`

- [ ] **Step 5: 커밋**

```bash
git add frontend/guided.js frontend/tests/guided-layout.test.js
git commit -m "fix(rapid-guided): clamp splitter panes on restore and resize so the center stays visible"
```

---

### Task 5: 전체 검증 + dev 배포

- [ ] **Step 1: 백엔드 CI 서브셋 + 신규**

Run: `cd /opt/protein_pipeline-work && PYTHONPATH=pipeline-mcp/src python -m pytest pipeline-mcp/tests/test_http_server_auth.py pipeline-mcp/tests/test_mcp_http_route.py pipeline-mcp/tests/test_oidc_auth.py pipeline-mcp/tests/test_session_auth.py pipeline-mcp/tests/test_runpod_admin.py pipeline-mcp/tests/test_plan_council.py -q`
Expected: PASS (86 tests)

- [ ] **Step 2: 프런트 CI 서브셋 + guided 전체**

Run: `node --test frontend/tests/app-syntax.test.js frontend/tests/auth-session.test.js frontend/tests/auth.test.js frontend/tests/login-bootstrap.test.js frontend/tests/mcp-tab.test.js frontend/tests/runpod-admin.test.js && (cd frontend && node --test tests/logout-bridge.test.js)`

Run: `cd frontend && node --test tests/guided-topbar.test.js tests/guided.test.js tests/guided-sidebar.test.js tests/guided-progress.test.js tests/guided-results.test.js tests/guided-evidence.test.js tests/guided-structure.test.js tests/guided-council.test.js tests/guided-layout.test.js`
Expected: PASS (142 tests = 128 + 7 + 7)

- [ ] **Step 3: 빌드**

Run: `npm --prefix frontend run build`
Expected: `✓ built`

- [ ] **Step 4: push + CI**

```bash
git fetch origin develop --quiet
git log --oneline HEAD..origin/develop | wc -l   # 0 이어야 함 — 아니면 재배치 필요
git push origin HEAD:develop
gh run watch --exit-status $(gh run list --branch develop --limit 1 --json databaseId --jq '.[0].databaseId')
```
Expected: CI green

- [ ] **Step 5: 배포 확인 + 수동 스모크**

```bash
curl -sS http://127.0.0.1:18087/healthz    # {"ok": true}
curl -sSI https://rapid.example.internal/guided.html | head -3   # HTTP/2 200
```

브라우저 확인 목록:
1. 창을 절반으로 줄여도 중앙 패널이 항상 보임 (스플리터 저장값 무관)
2. 계획 생성 → "전문가 검토하는 중…" → 판정 카드 5개(또는 LLM 없으면 생략 노트)
3. 경고/차단 판정의 reasons 표시, 제안은 기존 적용/거부 흐름으로 도착
4. 계획 재생성 시 이전 판정 카드가 남지 않음

롤백: `git revert` 후 재push.
