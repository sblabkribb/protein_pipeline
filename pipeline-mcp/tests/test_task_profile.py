"""Phase 2 acceptance — TaskProfile 은 레지스트리 선언에서만 파생된다.

가장 중요한 테스트는 `test_refusal_is_data_driven_not_hardcoded` 다. 거부가
일어난다는 것만 확인하면 `if objective == "binding"` 으로 구현해도 통과한다.
데이터를 바꿨을 때 거부가 사라지는지를 봐야 데이터 기반임이 증명된다.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp import task_profile as tp  # noqa: E402
from pipeline_mcp.model_routing import load_registry  # noqa: E402

SNAPSHOT = ROOT / "pipeline-mcp" / "tests" / "data" / "routing_snapshot.json"


def _registry():
    return load_registry(use_cache=False)


def _routing_view(registry) -> dict:
    snap = {r.purpose: r.to_dict() for r in registry.routes()}
    snap["_measurable_objectives"] = sorted(registry.measurable_objectives())
    snap["_measurable_incl_unvalidated"] = sorted(
        registry.measurable_objectives(include_unvalidated=True))
    return snap


# ---- 1. 기존 routing 보존 -------------------------------------------------

def test_existing_routing_is_unchanged_except_for_the_added_field():
    """새 필드 하나만 추가되고 기존 값은 어느 것도 바뀌지 않았다."""
    if not SNAPSHOT.exists():
        pytest.skip("스냅샷 없음")
    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    after = _routing_view(_registry())
    assert set(before) == set(after), "purpose 집합이 바뀌었다"
    for purpose, old in before.items():
        new = after[purpose]
        if not isinstance(old, dict):
            assert old == new, f"{purpose} 가 바뀌었다"
            continue
        added = set(new) - set(old)
        assert added <= {"task_profile"}, f"{purpose}: 예상 밖 신규 키 {added}"
        assert not (set(old) - set(new)), f"{purpose}: 키가 사라졌다"
        for key, value in old.items():
            assert new[key] == value, f"{purpose}.{key} 값이 바뀌었다"


# ---- 2. 허용 objective ----------------------------------------------------

def test_structural_objective_is_allowed():
    task = tp.resolve_for_purpose("monomer_solubility_redesign")
    assert task.task_id == "fixed_backbone_redesign"
    assert tp.validate_objective(task, "structural_preservation") is None
    assert tp.validate_objective(task, "solubility") is None


def test_binding_is_refused_with_structure():
    task = tp.resolve_for_purpose("monomer_solubility_redesign")
    refusal = tp.validate_objective(task, "binding")
    assert refusal is not None
    d = refusal.to_dict()
    assert d["status"] == "refused"
    assert d["reason_code"] == "objective_not_supported_for_task"
    assert d["task_profile"] == "fixed_backbone_redesign"
    assert d["requested_objective"] == "binding"
    assert d["required_capability"] == "fixed_backbone_design"
    # 대안은 데이터에서 유도된다 - 이름을 손으로 적어둔 것이 아니다.
    assert "protein_binder_design" in d["alternatives"]


def test_refusal_is_data_driven_not_hardcoded():
    """레지스트리에서 objective 를 넣고 빼면 판정이 따라 움직여야 한다.

    거부가 일어난다는 것만 보면 하드코딩된 분기와 구별되지 않는다.
    """
    registry = _registry()
    task = tp.resolve_for_purpose("monomer_solubility_redesign", registry=registry)
    assert tp.validate_objective(task, "binding", registry=registry) is not None

    # 같은 코드에, binding 을 선언한 task 를 주면 통과해야 한다.
    widened = copy.replace(task, available_objectives=task.available_objectives + ("binding",)) \
        if hasattr(copy, "replace") else None
    if widened is None:  # py<3.13
        import dataclasses
        widened = dataclasses.replace(
            task, available_objectives=task.available_objectives + ("binding",))
    assert tp.validate_objective(widened, "binding", registry=registry) is None, (
        "선언을 넓혔는데도 거부됐다 - objective 이름으로 분기하고 있다")

    # 반대로 구조 objective 를 선언에서 빼면 거부돼야 한다.
    import dataclasses
    narrowed = dataclasses.replace(task, available_objectives=("solubility",))
    assert tp.validate_objective(narrowed, "structural_preservation",
                                 registry=registry) is not None


def test_no_task_or_objective_name_branches_in_the_resolver():
    """resolver 안에 task/objective 이름 리터럴이 없어야 한다."""
    text = (ROOT / "pipeline-mcp" / "src" / "pipeline_mcp" / "task_profile.py").read_text(
        encoding="utf-8")
    code = "\n".join(
        line.split("#")[0] for line in text.splitlines()
        if not line.strip().startswith("#"))
    # docstring 안의 설명은 제외하고, 실행 코드에 이름이 박혀 있는지 본다.
    import ast
    tree = ast.parse(text)
    literals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    banned = {"binding", "fixed_backbone_redesign", "antibody_antigen",
              "antibody_design", "monomer_solubility_redesign", "solubility"}
    hit = {b for b in banned
           if any(b == lit or (b in lit and "task_profiles" not in lit) for lit in literals
                  if len(lit) < 60)}
    assert not hit, f"resolver 코드에 이름 리터럴이 있다: {hit}"


# ---- 3. referral ----------------------------------------------------------

def test_antibody_task_refers_out_using_the_registry_field():
    task = tp.resolve_for_purpose("antibody_design")
    assert task.task_id == "antibody_antigen"
    refusal = tp.check_executable(task)
    assert refusal is not None
    d = refusal.to_dict()
    assert d["reason_code"] == "task_not_executable_here"
    # referral 문구는 레지스트리에서 온다 - 코드가 만든 문장이 아니다.
    declared = load_registry().route("antibody_design").extra["referral"]
    assert d["referral"] == declared
    assert d["required_capability"] == "binder_or_complex_design"


def test_fixed_backbone_task_is_executable_here():
    task = tp.resolve_for_purpose("monomer_solubility_redesign")
    assert tp.check_executable(task) is None


# ---- 4. fail closed -------------------------------------------------------

def test_unknown_purpose_fails_closed():
    with pytest.raises(tp.TaskProfileError) as exc:
        tp.resolve_for_purpose("no_such_purpose")
    assert exc.value.refusal.reason_code is tp.RefusalCode.UNKNOWN_PURPOSE


def test_purpose_without_a_task_profile_fails_closed():
    """가장 비슷한 task 로 배정하지 않는다."""
    with pytest.raises(tp.TaskProfileError) as exc:
        tp.resolve_for_purpose("protein_binder_design")
    assert exc.value.refusal.reason_code is tp.RefusalCode.PURPOSE_HAS_NO_TASK_PROFILE


def test_unknown_task_profile_fails_closed():
    with pytest.raises(tp.TaskProfileError) as exc:
        tp.get("no_such_task")
    assert exc.value.refusal.reason_code is tp.RefusalCode.UNKNOWN_TASK_PROFILE


def test_unavailable_optimization_mode_is_refused_with_its_reason():
    task = tp.get("antibody_antigen")
    refusal = tp.validate_optimization_mode(task, "structural_yield")
    assert refusal is not None
    assert refusal.reason_code is tp.RefusalCode.UNKNOWN_OPTIMIZATION_MODE
    # 레지스트리가 적어 둔 이유가 함께 나온다.
    assert "wet" in refusal.reason or "evaluator" in refusal.reason
    assert tp.validate_optimization_mode(task, "coverage_preserving") is None


# ---- 5. coverage_unit 이 동결대로 실린다 ----------------------------------

def test_fixed_backbone_coverage_unit_is_frozen_as_backbone_id():
    task = tp.get("fixed_backbone_redesign")
    assert task.coverage_unit == "backbone_id"
    sem = task.coverage_semantics
    assert sem.get("unit_is_operational") is True, (
        "운영 정의라는 표시가 없으면 basin 과 같다고 읽힌다")
    assert sem.get("frozen_by"), "어느 문서가 동결했는지 적혀 있어야 한다"


# ---- 6. YAML ↔ JSON 미러 -------------------------------------------------

def test_json_mirror_regenerates_with_zero_diff():
    script = ROOT / "scripts" / "regenerate_registry_mirror.py"
    if not script.exists():
        pytest.skip("생성기 없음")
    done = subprocess.run([sys.executable, str(script), "--check"],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, (
        "JSON 미러가 YAML 과 다르다. 미러는 생성물이므로 손으로 고치지 않는다.\n"
        + done.stdout + done.stderr)
