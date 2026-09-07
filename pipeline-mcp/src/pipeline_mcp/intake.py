"""자유 서술을 목표(objective)로 모으는 대화 인테이크.

Ditto 의 intent 철학을 그대로 쓴다: 규칙 파싱이 먼저고, LLM 은 규칙이 못 본
빈 칸만 채운다. 규칙이 뽑은 값을 LLM 이 덮어쓰게 하면 "6 개 만들어줘" 가 조용히
다른 숫자가 된다. 실행은 이 모듈의 몫이 아니다 — 결과 objective 는 언제나
기존 plan_from_objective → approve_plan 게이트를 지난다.
"""

from __future__ import annotations

import json
import re

GEMINI_ERROR_PREFIX = "Error communicating with Gemini"

INTAKE_SYSTEM_INSTRUCTION = (
    "당신은 단백질 설계 목표 인테이크 도우미다. 사용자가 자유 서술로 말하는 설계 "
    "목표를 모아 기존 목표 폼(purpose, 가중치, 설계 수, 서열 길이)에 반영할 수 있는 "
    "형태로 만든다.\n"
    "규칙:\n"
    "1. 시스템 지시에 '규칙이 이미 확정한 값' 으로 적힌 것은 절대 바꾸지 않는다. "
    "빈 필드만 제안하거나 물어본다.\n"
    "2. 한 턴에 질문은 하나만. 한국어로, 산문은 최대 3문장.\n"
    "3. 목표 가중치는 지원 목적(solubility, structural_preservation, stability, "
    "activity, aggregation, developability, diversity, binding)만 쓰고 값은 0..1. "
    "합이 1 이 아니어도 된다 — 서버가 정규화한다.\n"
    "4. 설계 수(designs)와 서열 길이(length_aa)는 정수다.\n"
    "5. 모든 필수(타겟 서열/구조, 설계 수, 목표 가중치)가 모이면 마지막에 fenced "
    "json block 하나를 남긴다:\n"
    "```json\n"
    "{\"objective\": {\"weights\": {\"solubility\": 0.6}, "
    "\"budget\": {\"designs\": 40, \"length_aa\": 200}, \"purpose\": \"...\"}}\n"
    "```\n"
    "json block 뒤에는 아무것도 쓰지 않는다.\n"
    "6. 근거 없는 단백질 사실(서열, 기능, 수치)을 지어내지 않는다. 모르면 묻는다."
)

#: 레지스트리 목적 목록이 필요할 때만 로드한다. 실패하면 목적 검증을 건너뛴다.
def _known_purposes() -> list[str]:
    try:
        from .model_routing import load_registry  # noqa: PLC0415
        return [route.purpose for route in load_registry().routes()]
    except Exception:  # noqa: BLE001 — 레지스트리가 없어도 대화를 막지 않는다
        return []


def _rule_extract(text: str) -> dict:
    """규칙 라우팅에서 objective 로 옮길 수 있는 것만. 실패는 무시한다.

    route_prompt_with_errors 는 (routed, errors) 를 돌려주고 routed 에는
    purpose/n_designs 같은 키가 없다. 숫자 세기는 `num_seq_per_tier` 로 나오는데,
    인테이크 맥락에서 "N개" 는 설계 수를 뜻하므로 budget.designs 로 옮긴다.
    """
    try:
        from .router import route_prompt_with_errors  # noqa: PLC0415
        routed, _errors = route_prompt_with_errors(text)
    except Exception:  # noqa: BLE001
        return {}
    out: dict = {}
    if routed.get("purpose"):
        out["purpose"] = routed["purpose"]
    count = routed.get("num_seq_per_tier")
    if isinstance(count, int) and count > 0:
        out.setdefault("budget", {})["designs"] = count
    return out


def _coerce_int(value) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number


def _llm_json(raw: str) -> dict:
    """LLM 답변의 fenced json → objective dict. 없거나 깨지면 빈 dict."""
    match = re.search(r"```json\s*(.*?)```", str(raw or ""), re.DOTALL)
    if not match:
        return {}
    try:
        block = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(block, dict):
        return {}
    candidate = block.get("objective")
    if not isinstance(candidate, dict):
        # {"weights": ...} 를 통째로 준 낡은 계약도 흡수한다.
        if "weights" in block or "budget" in block or "purpose" in block:
            candidate = block
        else:
            return {}
    out: dict = {}
    weights = candidate.get("weights")
    if isinstance(weights, dict) and weights:
        out["weights"] = weights
    budget = candidate.get("budget")
    if isinstance(budget, dict) and budget:
        out["budget"] = budget
    if str(candidate.get("purpose") or "").strip():
        out["purpose"] = str(candidate["purpose"]).strip()
    return out


def _merge(rule_obj: dict, llm_obj: dict) -> dict:
    """규칙이 이긴다. LLM 은 규칙이 못 본 빈 칸만 채운다."""
    merged: dict = {}
    rule_budget = rule_obj.get("budget") if isinstance(rule_obj.get("budget"), dict) else {}
    llm_budget = llm_obj.get("budget") if isinstance(llm_obj.get("budget"), dict) else {}
    budget: dict = {}
    for key in ("designs", "length_aa"):
        value = rule_budget.get(key)
        if value is None:
            value = llm_budget.get(key)
        if value is not None:
            budget[key] = value
    if budget:
        merged["budget"] = budget
    purpose = rule_obj.get("purpose") or llm_obj.get("purpose")
    if purpose:
        merged["purpose"] = purpose
    if isinstance(llm_obj.get("weights"), dict) and llm_obj["weights"]:
        merged["weights"] = llm_obj["weights"]
    return merged


def _validate(merged: dict) -> list[str]:
    """Objective 의 규칙을 미리 적용한다. 문제 문장 목록을 돌려준다."""
    from .objective_planner import KNOWN_OBJECTIVES  # noqa: PLC0415

    problems: list[str] = []
    weights = merged.get("weights")
    if isinstance(weights, dict):
        unknown = sorted(set(weights) - set(KNOWN_OBJECTIVES))
        if unknown:
            problems.append(f"알 수 없는 objective: {unknown}. 지원: {list(KNOWN_OBJECTIVES)}")
        for name, value in weights.items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                problems.append(f"{name} weight 는 숫자여야 한다: {value!r}")
                continue
            if not 0.0 <= number <= 1.0:
                problems.append(f"{name} weight 는 0..1 이어야 한다: {value}")
    purpose = merged.get("purpose")
    if purpose:
        known = _known_purposes()
        if known and purpose not in known:
            problems.append(f"알 수 없는 설계 목적: {purpose}. 지원: {known}")
    budget = merged.get("budget")
    if isinstance(budget, dict):
        for key in ("designs", "length_aa"):
            if key in budget and not (_coerce_int(budget[key]) or 0) > 0:
                problems.append(f"{key} 는 양의 정수여야 한다: {budget[key]!r}")
    return problems


def _missing_list(has_target: bool, has_designs: bool, has_weights: bool,
                  problems: list[str]) -> list[str]:
    missing: list[str] = []
    if not has_target:
        missing.append("타겟 서열/구조 — FASTA 나 PDB 를 붙여넣거나 첨부해 주세요.")
    if not has_designs:
        missing.append("설계 수 (예: 40개)")
    if not has_weights:
        missing.append("목표 가중치 (예: 용해도 0.6, 구조 보존 0.4)")
    missing.extend(problems)
    return missing


def strip_fence(raw: str) -> str:
    """fenced json block 을 빼고 산문만 남긴다."""
    text = str(raw or "")
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if not match:
        return text.strip()
    prose = (text[: match.start()] + text[match.end():]).strip()
    return prose


def build_intake_prompt(messages, has_target: bool) -> str:
    """LLM 에게 넘길 대화 로그. 빈 칸이 무엇인지 규칙으로 알려준다."""
    lines = ["다음은 설계 목표 인테이크 대화입니다.", "", "대화:"]
    for message in messages or []:
        role = "사용자" if message.get("role") == "user" else "도우미"
        lines.append(f"{role}: {message.get('content', '')}")
    lines.append("")
    lines.append("필수 필드: 타겟 서열/구조(FASTA·PDB), 설계 수, 목표 가중치, 설계 목적.")
    lines.append(
        "아직 없는 필수: 타겟 서열/구조 — 붙여넣거나 파일 첨부를 요청하세요."
        if not has_target else "타겟 서열/구조는 이미 첨부되어 있습니다.")
    lines.append("빈 필드를 한 턴에 하나씩 묻고, 모두 모이면 출력 계약의 json 을 남깁니다.")
    return "\n".join(lines)


def intake_chat(messages, gemini, *, attached_fasta: str = "", attached_pdb: str = "") -> dict:
    """한 턴을 처리한다. 규칙 먼저, LLM 은 빈 칸만. 실행은 approve_plan 게이트가 담당."""
    msgs = [m for m in (messages or []) if isinstance(m, dict) and str(m.get("content") or "").strip()]
    last_user = next((str(m.get("content")) for m in reversed(msgs) if m.get("role") == "user"), "")
    if not last_user:
        return {"error": "messages with a user turn are required"}

    base = {"messages": msgs}
    if gemini is None or not getattr(gemini, "is_available", lambda: False)():
        return {**base, "llm_unavailable": True,
                "reply": "LLM 연결 없음 — 아래 카드에서 목적과 목표를 선택해 주세요.",
                "objective_ready": False}

    # 1) 규칙 먼저 — 대화 전체를 한 번 보고 확정 값을 뽑는다.
    full_text = "\n".join(str(m.get("content")) for m in msgs if m.get("role") == "user")
    rule_obj = _rule_extract(full_text)
    # fasta/pdb 첨부는 필수 필드를 채운다 (값 자체는 프런트가 plan 단계로 전달)
    has_target = bool(str(attached_fasta or "").strip() or str(attached_pdb or "").strip())

    # 2) LLM 은 빈 칸만 — system instruction 에 확정 값을 fixed 로 명시한다.
    fixed_note = json.dumps(rule_obj, ensure_ascii=False) if rule_obj else "(규칙이 뽑은 확정 값 없음)"
    try:
        raw = str(gemini.chat(
            INTAKE_SYSTEM_INSTRUCTION + "\n\n규칙이 이미 확정한 값(절대 바꾸지 말 것): " + fixed_note,
            build_intake_prompt(msgs, has_target),
        ))
    except Exception as exc:  # noqa: BLE001 — LLM 실패는 계약 응답으로 돌려준다
        raw = f"{GEMINI_ERROR_PREFIX}: {type(exc).__name__}: {exc}"
    if raw.startswith(GEMINI_ERROR_PREFIX):
        return {**base, "llm_unavailable": True, "reply": raw[:200], "objective_ready": False}

    llm_obj = _llm_json(raw)
    merged = _merge(rule_obj, llm_obj)  # rule wins on conflict

    # 3) 검증 — 목적은 레지스트리 목록에, 가중치는 0..1 known 목적만.
    problems = _validate(merged)
    has_designs = bool((merged.get("budget") or {}).get("designs"))
    has_weights = bool(merged.get("weights"))
    ready = has_target and has_designs and has_weights and not problems

    return {**base,
            "reply": strip_fence(raw),
            "reply_is_generated": True,
            "objective_ready": ready,
            "missing": _missing_list(has_target, has_designs, has_weights, problems),
            **({"objective": merged} if merged else {})}
