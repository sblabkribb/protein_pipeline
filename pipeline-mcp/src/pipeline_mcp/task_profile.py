"""TaskProfile 해석 — 레지스트리 선언에서만 파생된다.

이 모듈에는 task 이름이나 objective 이름으로 분기하는 코드가 없다.
`fixed_backbone_redesign` 에서 `binding` 이 거부되는 것은 `if objective ==
"binding"` 때문이 아니라, 그 task 에 속한 purpose 들이 `binding` 을 선언하지
않았기 때문이다. 나중에 enzyme 이나 binder task 가 생겨도 이 파일은 그대로다.

fail-closed 다. 알 수 없는 purpose, 선언되지 않은 objective, task_profile 을
선언하지 않은 purpose, 없는 referral 대상 - 어느 것도 가장 비슷한 것으로
대체하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .model_routing import ModelRegistry, Route, UnknownPurposeError, load_registry


class RefusalCode(str, Enum):
    """UI 와 API 는 이 코드를 쓴다. `reason` 은 사람이 읽는 설명이다."""

    UNKNOWN_PURPOSE = "unknown_purpose"
    #: purpose 가 어느 task 에 속하는지 선언돼 있지 않다. 짐작하지 않는다.
    PURPOSE_HAS_NO_TASK_PROFILE = "purpose_has_no_task_profile"
    UNKNOWN_TASK_PROFILE = "unknown_task_profile"
    #: 이 task 의 design space 에서 그 objective 가 성립하지 않는다.
    OBJECTIVE_NOT_SUPPORTED_FOR_TASK = "objective_not_supported_for_task"
    #: task 는 맞는데 여기서 실행되지 않는다. 다른 서비스로 보낸다.
    TASK_NOT_EXECUTABLE_HERE = "task_not_executable_here"
    UNKNOWN_OPTIMIZATION_MODE = "unknown_optimization_mode"


@dataclass(frozen=True)
class TaskRefusal:
    """구조화된 거부. 문자열 하나로 돌려주지 않는다."""

    reason_code: RefusalCode
    reason: str
    task_profile: str = ""
    requested_objective: str = ""
    #: 지금 고른 profile 이 가진 capability. **요청을 수행하는 데 필요한 것이
    #: 아니다.** 두 개를 한 필드에 담았다가 "binding 을 쓰려면
    #: fixed_backbone_design 이 필요하다" 는 정반대 문장이 나올 뻔했다.
    current_capability: str = ""
    #: 요청한 objective 를 실제로 수행할 수 있는 capability. 그 objective 를
    #: 선언한 purpose 들의 task profile 에서 유도한다. 복수형인 이유는 앞으로
    #: 여러 task 가 같은 objective 를 지원할 수 있고, 하나로 줄이면 조용히
    #: 정보를 잃기 때문이다. 유도할 수 없으면 빈 튜플이다.
    required_capabilities: tuple[str, ...] = ()
    #: 레지스트리가 정한 대안. 이름을 특별 취급해 만든 값이 아니다.
    referral: str = ""
    #: 이 objective 를 선언한 다른 purpose 들. 데이터에서 유도한다.
    alternatives: tuple[str, ...] = ()
    status: str = "refused"

    def to_dict(self) -> dict:
        return {
            "status": self.status, "reason_code": self.reason_code.value,
            "reason": self.reason, "task_profile": self.task_profile,
            "requested_objective": self.requested_objective,
            "current_capability": self.current_capability,
            "required_capabilities": list(self.required_capabilities),
            "referral": self.referral, "alternatives": list(self.alternatives),
        }


@dataclass(frozen=True)
class TaskProfile:
    """레지스트리 `task_profiles` 항목 + 그 task 에 속한 purpose 들."""

    task_id: str
    display_name_en: str
    display_name_ko: str
    description: str
    required_inputs: tuple[str, ...]
    required_capability: str
    executable_here: bool
    design_arm_schema: Mapping[str, Any]
    coverage_semantics: Mapping[str, Any]
    available_optimization_modes: tuple[str, ...]
    minimum_exploration_policy: Mapping[str, Any]
    allowed_actions: tuple[str, ...]
    purposes: tuple[str, ...]
    #: 이 task 에 속한 purpose 들이 선언한 objective 의 합집합.
    available_objectives: tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def coverage_unit(self) -> str:
        return str(self.coverage_semantics.get("coverage_unit", ""))

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "display_name_en": self.display_name_en,
            "display_name_ko": self.display_name_ko,
            "description": self.description,
            "required_inputs": list(self.required_inputs),
            "required_capability": self.required_capability,
            "executable_here": self.executable_here,
            "design_arm_schema": dict(self.design_arm_schema),
            "coverage_semantics": dict(self.coverage_semantics),
            "coverage_unit": self.coverage_unit,
            "available_optimization_modes": list(self.available_optimization_modes),
            "minimum_exploration_policy": dict(self.minimum_exploration_policy),
            "allowed_actions": list(self.allowed_actions),
            "purposes": list(self.purposes),
            "available_objectives": list(self.available_objectives),
        }


class TaskProfileError(KeyError):
    """구조화된 거부를 담아 던진다."""

    def __init__(self, refusal: TaskRefusal) -> None:
        super().__init__(refusal.reason)
        self.refusal = refusal


def _build(registry: ModelRegistry, task_id: str) -> TaskProfile:
    spec = registry.task_profiles[task_id]
    purposes = tuple(sorted(
        r.purpose for r in registry.routes() if r.task_profile == task_id))
    objectives: list[str] = []
    for name in purposes:
        for obj in registry.route(name).objectives:
            if obj not in objectives:
                objectives.append(obj)
    known = {"display_name_en", "display_name_ko", "description", "required_inputs",
             "required_capability", "executable_here", "design_arm_schema",
             "coverage_semantics", "available_optimization_modes",
             "minimum_exploration_policy", "allowed_actions"}
    return TaskProfile(
        task_id=task_id,
        display_name_en=str(spec.get("display_name_en", task_id)),
        display_name_ko=str(spec.get("display_name_ko", task_id)),
        description=str(spec.get("description", "")).strip(),
        required_inputs=tuple(spec.get("required_inputs") or ()),
        required_capability=str(spec.get("required_capability", "")),
        executable_here=bool(spec.get("executable_here", False)),
        design_arm_schema=dict(spec.get("design_arm_schema") or {}),
        coverage_semantics=dict(spec.get("coverage_semantics") or {}),
        available_optimization_modes=tuple(spec.get("available_optimization_modes") or ()),
        minimum_exploration_policy=dict(spec.get("minimum_exploration_policy") or {}),
        allowed_actions=tuple(spec.get("allowed_actions") or ()),
        purposes=purposes,
        available_objectives=tuple(objectives),
        extra={k: v for k, v in spec.items() if k not in known},
    )


def resolve_for_purpose(purpose: str, *, registry: ModelRegistry | None = None
                        ) -> TaskProfile:
    """purpose 가 속한 TaskProfile. 선언이 없으면 짐작하지 않고 실패한다."""
    registry = registry or load_registry()
    try:
        route: Route = registry.route(purpose)
    except UnknownPurposeError as exc:
        raise TaskProfileError(TaskRefusal(
            reason_code=RefusalCode.UNKNOWN_PURPOSE,
            reason=str(exc),
            alternatives=tuple(sorted(r.purpose for r in registry.routes())),
        )) from None
    if not route.task_profile:
        raise TaskProfileError(TaskRefusal(
            reason_code=RefusalCode.PURPOSE_HAS_NO_TASK_PROFILE,
            reason=(f"purpose {purpose!r} 에 task_profile 이 선언돼 있지 않다. "
                    f"가장 비슷한 task 로 배정하지 않는다 - 레지스트리에 선언한다."),
            alternatives=tuple(sorted(registry.task_profiles)),
        ))
    if route.task_profile not in registry.task_profiles:
        raise TaskProfileError(TaskRefusal(
            reason_code=RefusalCode.UNKNOWN_TASK_PROFILE,
            reason=f"선언된 task_profile {route.task_profile!r} 이 레지스트리에 없다",
            task_profile=route.task_profile,
            alternatives=tuple(sorted(registry.task_profiles)),
        ))
    return _build(registry, route.task_profile)


def get(task_id: str, *, registry: ModelRegistry | None = None) -> TaskProfile:
    registry = registry or load_registry()
    if task_id not in registry.task_profiles:
        raise TaskProfileError(TaskRefusal(
            reason_code=RefusalCode.UNKNOWN_TASK_PROFILE,
            reason=f"알 수 없는 task_profile {task_id!r}",
            task_profile=task_id,
            alternatives=tuple(sorted(registry.task_profiles)),
        ))
    return _build(registry, task_id)


def _purposes_declaring(registry: ModelRegistry, objective: str) -> tuple[str, ...]:
    """그 objective 를 실제로 선언한 purpose 들. 데이터에서 유도한다."""
    return tuple(sorted(r.purpose for r in registry.routes()
                        if objective in r.objectives))


def _capabilities_for(registry: ModelRegistry, purposes: tuple[str, ...]) -> tuple[str, ...]:
    """이 purpose 들이 속한 task profile 의 capability. 데이터에서 유도한다."""
    out: list[str] = []
    for name in purposes:
        task_id = registry.route(name).task_profile
        if not task_id or task_id not in registry.task_profiles:
            continue
        cap = str(registry.task_profiles[task_id].get("required_capability", "") or "")
        if cap and cap not in out:
            out.append(cap)
    return tuple(out)


def validate_objective(task: TaskProfile, objective: str, *,
                       registry: ModelRegistry | None = None) -> TaskRefusal | None:
    """이 task 에서 그 objective 가 성립하는가. 성립하면 None."""
    registry = registry or load_registry()
    if objective in task.available_objectives:
        return None
    alternatives = _purposes_declaring(registry, objective)
    referral = str(task.extra.get("referral", "") or "")
    if not referral:
        for name in task.purposes:
            declared = registry.route(name).extra.get("referral")
            if declared:
                referral = str(declared)
                break
    return TaskRefusal(
        reason_code=RefusalCode.OBJECTIVE_NOT_SUPPORTED_FOR_TASK,
        reason=(f"{objective} is not supported by {task.task_id}. "
                f"이 task 가 선언한 objective: {list(task.available_objectives)}."
                + (f" 이 objective 를 선언한 경로: {list(alternatives)}."
                   if alternatives else " 이 objective 를 선언한 경로가 없다.")),
        task_profile=task.task_id,
        requested_objective=objective,
        current_capability=task.required_capability,
        required_capabilities=_capabilities_for(registry, alternatives),
        referral=referral,
        alternatives=alternatives,
    )


def check_executable(task: TaskProfile, *, registry: ModelRegistry | None = None
                     ) -> TaskRefusal | None:
    """여기서 실행되는 task 인가. 아니면 레지스트리가 정한 곳으로 보낸다."""
    if task.executable_here:
        return None
    registry = registry or load_registry()
    referral = str(task.extra.get("referral", "") or "")
    if not referral:
        for name in task.purposes:
            declared = registry.route(name).extra.get("referral")
            if declared:
                referral = str(declared)
                break
    return TaskRefusal(
        reason_code=RefusalCode.TASK_NOT_EXECUTABLE_HERE,
        reason=referral or f"{task.task_id} 는 여기서 실행되지 않는다",
        task_profile=task.task_id,
        current_capability=task.required_capability,
        # 이 경우엔 task 자체는 맞다. capability 가 틀린 것이 아니라
        # 여기서 실행되지 않을 뿐이다.
        required_capabilities=(task.required_capability,) if task.required_capability else (),
        referral=referral,
        alternatives=task.purposes,
    )


def validate_optimization_mode(task: TaskProfile, mode: str) -> TaskRefusal | None:
    if mode in task.available_optimization_modes:
        return None
    why = dict(task.extra.get("modes_not_available") or {}).get(mode, "")
    return TaskRefusal(
        reason_code=RefusalCode.UNKNOWN_OPTIMIZATION_MODE,
        reason=(f"{task.task_id} 에서 optimization mode {mode!r} 을 쓸 수 없다. "
                f"가능한 mode: {list(task.available_optimization_modes)}."
                + (f" 이유: {why}" if why else "")),
        task_profile=task.task_id,
        current_capability=task.required_capability,
        alternatives=task.available_optimization_modes,
    )
