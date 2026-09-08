"""목적 기반 모델 라우팅.

`model_registry/MODEL_REGISTRY_V1.yaml` 를 읽어서 설계 목적 하나를 고정된
스테이지 목록으로 바꾼다. 여기에는 점수도 학습도 없다. 결정적 조회다.

이 모듈이 지키는 두 가지 구분:

* **실행 가능(executable)** 과 **검증됨(validated)** 은 다른 사실이다.
  클라이언트가 붙어 있으면 돌릴 수는 있다. 그것이 그 경로를 측정했다는 뜻은
  아니다.
* **선언된 가용성** 과 **지금 살아 있는지** 는 다른 사실이다. `probe_liveness`
  는 워커에 물어보지만 그 답으로 레지스트리를 고쳐 쓰지 않는다.

비용은 provenance 없이 존재하지 못한다. 측정하지 않은 스테이지는 0 초가 아니라
`unknown_stages` 로 보고된다. 모르는 값을 0 으로 더하면 예산이 거짓말이 된다.
"""

from __future__ import annotations

import os

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
import json
import urllib.request

_REGISTRY_DIR = Path(__file__).resolve().parent / "model_registry"

#: 사람이 쓰는 원본. 이 파일의 주석이 레지스트리의 문서다.
REGISTRY_PATH = _REGISTRY_DIR / "MODEL_REGISTRY_V1.yaml"

#: 런타임이 실제로 읽는 파일. 표준 라이브러리만으로 읽을 수 있다.
#:
#: 왜 JSON 을 따로 두는가. 배포는 파일 복사 + systemd 재시작이고 그 사이에
#: pip install 단계가 없다. 그런 경로에 서드파티 파서 의존을 넣으면 그
#: 라이브러리가 우연히 있는 환경에서만 동작한다 - 실제로 prod venv 에는 PyYAML
#: 이 있었고 dev venv 에는 없어서, guided 화면의 세 툴이 전부 죽었다.
REGISTRY_JSON_PATH = _REGISTRY_DIR / "MODEL_REGISTRY_V1.json"

ROLES = (
    "msa",
    "backbone_generator",
    "conformational_ensemble",
    "sequence_designer",
    "representation",
    "cheap_filter",
    "structure_validator",
    "interface_scorer",
    "ligand_docking",
    "antibody_numbering",
    "refinement",
    "stability_evaluator",
)

COST_PROVENANCE = ("measured", "reported", "unmeasured")

#: 여기 있는 것만 "지금 이 저장소에서 돌릴 수 있다".
RUNNABLE_AVAILABILITY = ("production", "wired_unvalidated")

_GATE_ORDER = {"gate0": 0, "gate1": 1, "gate2": 2}


class RegistryError(RuntimeError):
    """레지스트리 파일이 자기 계약을 어겼다."""


class UnknownPurposeError(KeyError):
    """모르는 목적. 비슷한 것으로 대신 라우팅하지 않는다."""


@dataclass(frozen=True)
class Cost:
    provenance: str
    unit: str = ""
    value: float | None = None
    scope: str = ""
    source: str = ""
    note: str = ""
    #: 길이 등에 따라 비용이 변하는 스테이지의 적합 모델.
    model: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.provenance not in COST_PROVENANCE:
            raise RegistryError(f"cost.provenance 는 {COST_PROVENANCE} 중 하나여야 한다: {self.provenance!r}")
        if self.provenance == "unmeasured":
            if self.value is not None:
                raise RegistryError("측정하지 않은 비용에 숫자를 붙일 수 없다")
        else:
            if self.value is None:
                raise RegistryError(f"{self.provenance} 비용에 값이 없다")
            if not self.source:
                raise RegistryError(f"{self.provenance} 비용에 source 가 없다")
            if not self.scope:
                raise RegistryError(f"{self.provenance} 비용에 scope 가 없다 — 범위 없는 숫자는 측정이 아니다")

    def seconds_for(self, *, length_aa: int | None = None) -> float | None:
        """설계 1 개당 예상 초. 모르면 None (0 이 아니다).

        affine 모델은 호출 고정비를 포함하므로 '단위당' 이라는 개념이 없다.
        그런 스테이지는 `total_seconds` 를 써야 한다.
        """
        if self.value is None:
            return None
        spec = self.model or {}
        if spec.get("kind") == "power_law" and spec.get("variable") == "length_aa":
            if length_aa is None:
                return float(self.value)
            return float(spec["coefficient"]) * (float(length_aa) ** float(spec["exponent"]))
        if spec.get("kind") == "affine":
            return float(spec["slope"])
        return float(self.value)

    def total_seconds(self, *, n_designs: int, length_aa: int | None = None) -> float | None:
        """설계 n 개를 이 스테이지에 통과시키는 총 초. 모르면 None.

        모델 형태를 잘못 적용하면 예산이 조용히 틀린다:

        * `power_law` (AF2) 는 설계마다 한 번씩 접으므로 n 배가 맞다.
        * `affine` (ProteinMPNN) 은 한 번의 호출이 n 개를 만든다. 고정비를 n 번
          청구하면 16 개 요청의 비용이 실제의 4 배가 된다.
        """
        if self.value is None:
            return None
        spec = self.model or {}
        if spec.get("kind") == "affine":
            return float(spec["intercept"]) + float(spec["slope"]) * float(n_designs)
        per_unit = self.seconds_for(length_aa=length_aa)
        if per_unit is None:
            return None
        return per_unit * float(n_designs)

    def to_dict(self) -> dict:
        out = {"provenance": self.provenance, "unit": self.unit, "value": self.value}
        for key in ("scope", "source", "note"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.model:
            out["model"] = dict(self.model)
        return out


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    display_name: str
    role: str
    availability: str
    cost: Cost
    endpoint: str = ""
    client: str = ""
    measures: tuple[str, ...] = ()
    replicas: tuple[str, ...] = ()
    worker_concurrency: int | None = None
    performance: Mapping[str, Any] | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def runnable(self) -> bool:
        return self.availability in RUNNABLE_AVAILABILITY

    def to_dict(self) -> dict:
        out = {
            "model_id": self.model_id,
            "display_name": self.display_name,
            "role": self.role,
            "availability": self.availability,
            "runnable": self.runnable,
            "endpoint": self.endpoint,
            "client": self.client,
            "measures": list(self.measures),
            "cost": self.cost.to_dict(),
        }
        if self.worker_concurrency is not None:
            out["worker_concurrency"] = self.worker_concurrency
        if self.performance:
            out["performance"] = dict(self.performance)
        out.update({k: v for k, v in self.extra.items() if k not in out})
        return out


@dataclass(frozen=True)
class RouteStage:
    stage: str
    model_id: str
    required: bool
    validated: bool
    gate: str | None = None
    #: 이 스테이지를 돌리려면 모델에 닿는 것만으로 부족하고, 무엇을 바꿔도 되는지
    #: 정하는 정책이 있어야 한다. 빈 문자열이면 그런 정책이 필요 없다는 뜻이다.
    requires_design_policy: str = ""

    def to_dict(self) -> dict:
        return {
            "stage": self.stage, "model_id": self.model_id, "gate": self.gate,
            "required": self.required, "validated": self.validated,
            "requires_design_policy": self.requires_design_policy,
        }


@dataclass(frozen=True)
class Route:
    purpose: str
    display_name_en: str
    display_name_ko: str
    description: str
    objectives: tuple[str, ...]
    stages: tuple[RouteStage, ...]
    executable: bool
    blocked_reason: str
    #: 막힌 이유를 종류별로 나눈다. transport 는 모델에 닿을 수 없는 것,
    #: design_policy 는 닿을 수 있어도 무엇을 바꿔도 되는지 모르는 것이다.
    #: 전자는 배선으로 풀리고 후자는 풀리지 않는다.
    blockers: Mapping[str, list]
    cost_driver: str
    _models: Mapping[str, ModelEntry] = field(repr=False, default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def validation_coverage(self) -> dict | None:
        """이 경로가 실제로 몇 개 타겟에서 산출됐는가.

        `validated` 는 "이 저장소가 이 경로를 측정했다" 는 뜻이지 "잘 된다" 가
        아니다. 그런데 UI 의 "검증됨" 과 논문의 "validated purpose" 는 후자로
        읽힌다. BioEmu 경로는 62 개 중 4 개에서만 백본이 나왔고, 같은 n=4 를
        근거로 온도 결론은 탐색적이라고 표시했다. 두 진술이 양립하려면 비율이
        표시와 함께 다녀야 한다.
        """
        raw = self.extra.get("validation_coverage")
        return dict(raw) if isinstance(raw, dict) else None

    @property
    def unvalidated_stages(self) -> tuple[RouteStage, ...]:
        return tuple(s for s in self.stages if not s.validated)

    @property
    def validated(self) -> bool:
        """모든 필수 스테이지가 이 저장소에서 측정되었는가."""
        return self.executable and not self.unvalidated_stages

    def model(self, model_id: str) -> ModelEntry:
        return self._models[model_id]

    def cost_estimate(self, *, n_designs: int, length_aa: int | None = None) -> dict:
        """알려진 비용만 더하고, 모르는 스테이지는 따로 이름으로 보고한다."""
        known = 0.0
        unknown: list[str] = []
        breakdown: list[dict] = []
        for stage in self.stages:
            model = self._models[stage.model_id]
            total = model.cost.total_seconds(n_designs=n_designs, length_aa=length_aa)
            if total is None:
                unknown.append(stage.stage)
                breakdown.append({
                    "stage": stage.stage, "model_id": stage.model_id,
                    "seconds": None, "reason": model.cost.note or "측정된 비용 없음",
                })
                continue
            known += total
            entry = {
                "stage": stage.stage, "model_id": stage.model_id,
                "seconds": round(total, 1),
                "per_design_seconds": round(model.cost.seconds_for(length_aa=length_aa) or 0.0, 3),
                "provenance": model.cost.provenance, "source": model.cost.source,
            }
            # 클라이언트가 만드는 추가 비용은 모델 비용과 섞지 않고 옆에 적는다.
            overhead = model.extra.get("client_overhead")
            if overhead and overhead.get("value") is not None:
                entry["client_overhead_seconds"] = float(overhead["value"])
                entry["client_overhead_note"] = overhead.get("scope", "")
            breakdown.append(entry)
        return {
            "n_designs": int(n_designs),
            "length_aa": length_aa,
            "known_seconds": round(known, 1),
            "unknown_stages": unknown,
            "complete": not unknown,
            "breakdown": breakdown,
            "note": (
                "unknown_stages 는 0 초가 아니라 '측정하지 않음' 이다. "
                "known_seconds 는 하한이다."
            ),
        }

    def evidence(self) -> list[dict]:
        """objective_planner.Evidence 로 바로 만들 수 있는 dict 목록."""
        items: list[dict] = []
        for stage in self.stages:
            model = self._models[stage.model_id]
            if model.performance:
                perf = model.performance
                value = f"{perf.get('metric')}={perf.get('value')}"
                ci = perf.get("ci95")
                if ci:
                    value += f" (95% CI {ci[0]}-{ci[1]})"
                items.append({
                    "kind": "internal_measurement",
                    "statement": f"{model.display_name}: {perf.get('caveat') or perf.get('comparator') or ''}".strip().rstrip(":"),
                    "source": str(perf.get("source") or ""),
                    "value": value,
                })
            cost = model.cost
            if cost.provenance in {"measured", "reported"}:
                items.append({
                    "kind": "internal_measurement",
                    "statement": f"{model.display_name} 비용 측정 범위: {cost.scope}",
                    "source": cost.source,
                    "value": f"{cost.value} {cost.unit}",
                })
            else:
                items.append({
                    "kind": "assumption",
                    "statement": (
                        f"{model.display_name} 의 비용은 측정되지 않았다. "
                        f"{cost.note or '예산 추정에서 제외한다.'}"
                    ),
                    "source": "",
                    "value": "",
                })
            if not stage.validated:
                items.append({
                    "kind": "assumption",
                    "statement": (
                        f"{stage.stage} ({model.display_name}) 는 이 경로에서 검증되지 않았다. "
                        "돌아가는 것과 맞는 것은 다르다."
                    ),
                    "source": "",
                    "value": "",
                })
        return items

    def to_dict(self) -> dict:
        out = {
            "purpose": self.purpose,
            "display_name_en": self.display_name_en,
            "display_name_ko": self.display_name_ko,
            "description": self.description,
            "objectives": list(self.objectives),
            "stages": [s.to_dict() for s in self.stages],
            "executable": self.executable,
            "validated": self.validated,
            "validation_coverage": self.validation_coverage,
            "blocked_reason": self.blocked_reason,
            "blockers": {k: list(v) for k, v in self.blockers.items()},
            "unvalidated_stages": [s.stage for s in self.unvalidated_stages],
            "cost_driver": self.cost_driver,
        }
        out.update({k: v for k, v in self.extra.items() if k not in out})
        return out


def _default_probe(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8") or "{}")


@dataclass(frozen=True)
class ModelRegistry:
    policy_version: str
    version: str
    freeze_state: str
    models: Mapping[str, ModelEntry]
    registry_access: Mapping[str, object] = field(default_factory=dict)
    #: 목표마다 왜 못 재는지. 하나로 뭉뚱그리면 모델을 붙이면 되는 것과
    #: 그렇지 않은 것이 같아 보인다.
    objective_status: Mapping[str, dict] = field(default_factory=dict)
    _purposes: Mapping[str, Route] = field(repr=False, default_factory=dict)

    @property
    def purposes(self) -> tuple[str, ...]:
        return tuple(self._purposes)

    def is_runnable(self, model_id: str) -> bool:
        return self.models[model_id].runnable

    def route(self, purpose: str) -> Route:
        try:
            return self._purposes[purpose]
        except KeyError:
            raise UnknownPurposeError(
                f"알 수 없는 설계 목적 {purpose!r}. 지원: {list(self._purposes)}"
            ) from None

    def routes(self) -> tuple[Route, ...]:
        return tuple(self._purposes.values())

    def measurable_objectives(self, *, include_unvalidated: bool = False) -> set[str]:
        """RAPID 가 실제로 점수를 매길 수 있는 목표.

        기본값은 보수적이다. 검증되지 않은 평가자가 붙어 있다는 이유만으로
        목표가 '반영되었다' 고 말하지 않는다.
        """
        allowed = set(RUNNABLE_AVAILABILITY) if include_unvalidated else {"production"}
        out: set[str] = set()
        for model in self.models.values():
            if model.availability in allowed:
                out.update(model.measures)
        return out

    def evaluators_for(self, objective: str, *, include_unvalidated: bool = False) -> tuple[ModelEntry, ...]:
        allowed = set(RUNNABLE_AVAILABILITY) if include_unvalidated else {"production"}
        return tuple(
            m for m in self.models.values()
            if objective in m.measures and m.availability in allowed
        )

    def purposes_for_objectives(self, objectives: Iterable[str]) -> tuple[Route, ...]:
        """요청된 목표를 가장 많이 덮는 순으로 목적을 제안한다.

        점수가 아니라 커버리지다. 동점이면 선언 순서를 유지해 결정적이다.
        """
        wanted = {str(o) for o in objectives}
        scored = [
            (len(wanted & set(route.objectives)), -index, route)
            for index, route in enumerate(self._purposes.values())
        ]
        scored.sort(key=lambda item: (-item[0], -item[1]))
        return tuple(route for covered, _, route in scored if covered)

    def probe_liveness(
        self,
        *,
        probe: Callable[[str, float], dict] | None = None,
        timeout: float = 6.0,
        host: str = "",   # RAPID_GPU_HOST 로 주입한다. 내부 호스트를 저장소에 적지 않는다.
    ) -> dict[str, dict]:
        """워커가 지금 응답하는지 확인한다. 레지스트리는 바꾸지 않는다."""
        call = probe or _default_probe
        out: dict[str, dict] = {}
        for model in self.models.values():
            endpoint = model.endpoint
            if not endpoint or not endpoint.startswith("bop:"):
                continue
            port = endpoint.split(":", 1)[1]
            url = f"http://{host}:{port}/healthz"
            entry: dict[str, Any] = {
                "endpoint": endpoint,
                "declared_availability": model.availability,
            }
            try:
                payload = call(url, timeout)
            except Exception as exc:  # noqa: BLE001 - 어떤 실패든 '도달 불가' 다
                entry.update({"reachable": False, "error": str(exc)})
            else:
                reported = str(payload.get("model") or payload.get("model_name") or "")
                entry.update({
                    "reachable": bool(payload.get("ok", True)),
                    "ready": payload.get("ready"),
                    "reported_model": reported,
                    "model_mismatch": bool(reported) and not _names_agree(model, reported),
                })
            out[model.model_id] = entry
        return out

    def to_dict(self) -> dict:
        return {
            "policy_version": self.policy_version,
            "version": self.version,
            "freeze_state": self.freeze_state,
            "models": {k: v.to_dict() for k, v in self.models.items()},
            "purposes": [r.to_dict() for r in self._purposes.values()],
        }


def _names_agree(model: ModelEntry, reported: str) -> bool:
    """워커가 보고한 이름이 우리가 등록한 모델과 같은 것을 가리키는가.

    워커마다 무엇을 보고하는지가 다르다. ProteinMPNN 워커는 `proteinmpnn` 을,
    ESM 임베딩 워커는 체크포인트 이름 `facebook/esm2_t6_8M_UR50D` 를 보고한다.
    그래서 등록된 체크포인트 이름까지 후보에 넣는다 - 그러지 않으면 정상인
    워커가 매번 불일치로 잡히고, 진짜 불일치가 묻힌다.
    """
    normalise = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())  # noqa: E731
    declared_checkpoint = str((model.extra.get("checkpoint") or {}).get("model_name") or "")
    ours = {
        normalise(model.model_id),
        normalise(model.display_name),
        normalise(declared_checkpoint),
    }
    theirs = normalise(reported)
    return any(name and (name in theirs or theirs in name) for name in ours)


_KNOWN_MODEL_KEYS = {
    "display_name", "role", "endpoint", "availability", "client", "measures",
    "cost", "replicas", "worker_concurrency", "performance",
}
_KNOWN_PURPOSE_KEYS = {
    "display_name_en", "display_name_ko", "description", "objectives", "stages",
    "cost_driver",
}


def _build_model(model_id: str, raw: Mapping[str, Any]) -> ModelEntry:
    cost_raw = dict(raw.get("cost") or {})
    cost = Cost(
        provenance=str(cost_raw.get("provenance", "unmeasured")),
        unit=str(cost_raw.get("unit", "")),
        value=cost_raw.get("value"),
        scope=str(cost_raw.get("scope", "")),
        source=str(cost_raw.get("source", "")),
        note=str(cost_raw.get("note", "")),
        model=cost_raw.get("model"),
    )
    availability = str(raw.get("availability", ""))
    role = str(raw.get("role", ""))
    if role not in ROLES:
        raise RegistryError(f"{model_id}: 알 수 없는 role {role!r}")
    return ModelEntry(
        model_id=model_id,
        display_name=str(raw.get("display_name", model_id)),
        role=role,
        availability=availability,
        cost=cost,
        endpoint=str(raw.get("endpoint", "")),
        client=str(raw.get("client", "")),
        measures=tuple(raw.get("measures") or ()),
        replicas=tuple(raw.get("replicas") or ()),
        worker_concurrency=raw.get("worker_concurrency"),
        performance=raw.get("performance"),
        extra={k: v for k, v in raw.items() if k not in _KNOWN_MODEL_KEYS},
    )


def _build_route(purpose: str, raw: Mapping[str, Any], models: Mapping[str, ModelEntry]) -> Route:
    stages: list[RouteStage] = []
    for item in raw.get("stages") or ():
        model_id = str(item["model_id"])
        if model_id not in models:
            raise RegistryError(f"{purpose}/{item.get('stage')}: 미등록 모델 {model_id!r}")
        gate = item.get("gate")
        stages.append(RouteStage(
            stage=str(item["stage"]),
            model_id=model_id,
            required=bool(item.get("required", True)),
            validated=bool(item.get("validated", False)),
            gate=str(gate) if gate else None,
            requires_design_policy=str(item.get("requires_design_policy", "")),
        ))
    gates = [_GATE_ORDER[s.gate] for s in stages if s.gate]
    if gates != sorted(gates):
        raise RegistryError(f"{purpose}: 게이트 순서가 뒤집혔다 — 비싼 검증이 싼 필터보다 먼저 온다")

    transport = [s for s in stages if s.required and not models[s.model_id].runnable]
    policy = [s for s in stages if s.required and s.requires_design_policy]
    blockers = {
        "transport": [
            {"stage": s.stage, "model_id": s.model_id,
             "availability": models[s.model_id].availability,
             "access": dict(models[s.model_id].extra.get("access") or {})}
            for s in transport
        ],
        "design_policy": [
            {"stage": s.stage, "model_id": s.model_id,
             "requirement": s.requires_design_policy}
            for s in policy
        ],
    }

    parts = []
    if transport:
        detail = ", ".join(
            f"{s.stage}: {s.model_id} ({models[s.model_id].availability})" for s in transport
        )
        reachable = [
            s.model_id for s in transport
            if (models[s.model_id].extra.get("access") or {}).get("portal_mcp")
        ]
        parts.append(
            f"필요한 모델을 여기서 호출할 수 없다 — {detail}."
            + (f" 이 중 {', '.join(reachable)} 은 bio model portal MCP 가 노출하므로 "
               f"그 경로를 붙이면 전송 문제는 사라진다." if reachable else "")
        )
    if policy:
        detail = "; ".join(f"{s.stage}: {s.requires_design_policy}" for s in policy)
        parts.append(
            f"모델에 닿아도 실행할 수 없다. 무엇을 바꿔도 되는지 정하는 설계 정책이 "
            f"없다 — {detail} 이 정책은 배선으로 풀리지 않는다."
        )
    reason = " ".join(parts)
    if reason:
        reason += " 다른 모델로 대체하지 않는다."
    blocking = transport or policy

    return Route(
        purpose=purpose,
        display_name_en=str(raw.get("display_name_en", purpose)),
        display_name_ko=str(raw.get("display_name_ko", purpose)),
        description=str(raw.get("description", "")).strip(),
        objectives=tuple(raw.get("objectives") or ()),
        stages=tuple(stages),
        executable=not blocking,
        blocked_reason=reason,
        blockers=blockers,
        cost_driver=str(raw.get("cost_driver", "")),
        _models=models,
        extra={k: v for k, v in raw.items() if k not in _KNOWN_PURPOSE_KEYS},
    )


def read_yaml_source(path: str | Path) -> dict:
    """YAML 원본을 읽는다. PyYAML 이 필요하므로 런타임 경로에서는 쓰지 않는다."""
    import yaml  # noqa: PLC0415 - 여기서만 필요한 선택적 의존성

    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def registry_drift(yaml_path: Path | None = None, json_path: Path | None = None) -> list[str]:
    """JSON 미러가 YAML 원본과 어긋난 최상위 키를 돌려준다.

    PyYAML 이 없으면 대조할 원본을 읽을 수 없으므로 빈 목록을 돌려준다 - 그
    환경에서는 JSON 이 유일한 진실이고, 어긋남은 원본이 있는 곳에서 잡는다.
    """
    yaml_file = Path(yaml_path or REGISTRY_PATH)
    json_file = Path(json_path or REGISTRY_JSON_PATH)
    if not yaml_file.exists() or not json_file.exists():
        return []
    try:
        source = read_yaml_source(yaml_file)
    except ModuleNotFoundError:
        return []
    mirror = json.loads(json_file.read_text(encoding="utf-8"))
    keys = set(source) | set(mirror)
    return sorted(key for key in keys if source.get(key) != mirror.get(key))


def _read_registry_document(path: Path | None) -> dict:
    """레지스트리 문서를 읽는다. 표준 라이브러리만으로 되는 경로를 먼저 쓴다."""
    if path is not None:
        resolved = Path(path)
        if resolved.suffix == ".json":
            return json.loads(resolved.read_text(encoding="utf-8"))
        return read_yaml_source(resolved)
    if REGISTRY_JSON_PATH.exists():
        return json.loads(REGISTRY_JSON_PATH.read_text(encoding="utf-8"))
    # 미러가 없으면 원본을 읽어본다. PyYAML 이 없으면 여기서 실패하는데, 그
    # 메시지는 무엇을 해야 하는지 말해야 한다.
    try:
        return read_yaml_source(REGISTRY_PATH)
    except ModuleNotFoundError as exc:
        raise RegistryError(
            f"{REGISTRY_JSON_PATH.name} 이 없고 PyYAML 도 없어서 모델 레지스트리를 "
            f"읽을 수 없다. scripts/transcoder/19_sync_model_registry.py 로 JSON "
            f"미러를 만들어 함께 배포한다."
        ) from exc


_CACHE: dict[Path, ModelRegistry] = {}


def load_registry(path: str | Path | None = None, *, use_cache: bool = True) -> ModelRegistry:
    resolved = Path(path) if path else REGISTRY_JSON_PATH
    if use_cache and resolved in _CACHE:
        return _CACHE[resolved]
    raw = _read_registry_document(Path(path) if path else None)

    models = {
        model_id: _build_model(model_id, spec)
        for model_id, spec in (raw.get("models") or {}).items()
    }
    allowed = set(raw.get("availability_values") or ())
    for model in models.values():
        if allowed and model.availability not in allowed:
            raise RegistryError(f"{model.model_id}: 알 수 없는 availability {model.availability!r}")

    purposes = {
        purpose: _build_route(purpose, spec, models)
        for purpose, spec in (raw.get("purposes") or {}).items()
    }
    registry = ModelRegistry(
        policy_version=str(raw.get("policy_version", "")),
        version=str(raw.get("version", "")),
        freeze_state=str((raw.get("freeze") or {}).get("state", "draft")),
        models=models,
        registry_access=dict(raw.get("registry_access") or {}),
        objective_status={k: dict(v) for k, v in (raw.get("objective_status") or {}).items()},
        _purposes=purposes,
    )
    if use_cache:
        _CACHE[resolved] = registry
    return registry
