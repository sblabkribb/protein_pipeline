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
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .objective_planner import Evidence

logger = logging.getLogger(__name__)

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
    # 헌장이 출력 계약을 포함해야 한다는 스펙 B2 — 계약 텍스트는 모듈 상수로 관리한다.
    system = expert.charter + "\n\n" + COUNCIL_OUTPUT_CONTRACT
    raw = str(gemini.chat(system, build_expert_prompt(plan, expert)))
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
                logger.warning("전문가 %s 검토 실패: %s", expert.id, exc)
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
