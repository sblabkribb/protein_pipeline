"""Phase 1 acceptance — contract 만. 실행 경로에 연결되지 않는다.

이 테스트들이 막는 것은 이번 캠페인에서 실제로 일어난 실패들이다:
값 없이 ok 로 기록, 예외 타입만 남고 메시지 소실, 거부와 실패의 혼동,
허가 없이 평가자 연결.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.rapid_core import (  # noqa: E402
    EvaluationResult, Validity, OperationalStatus, PermissionSet,
    ScientificPermission, ScoreTransform, TransformKey, TransformRegistry,
)
from pipeline_mcp.rapid_core.evaluation import Direction  # noqa: E402

OK = dict(evaluator="e1", objective="structural_preservation",
          validity=Validity.OK, raw_value=88.0, unit="plddt",
          direction=Direction.HIGHER_IS_BETTER)


# ---- EvaluationResult -----------------------------------------------------

def test_ok_result_requires_a_value():
    """pose 0 개를 22/22 ok 로 적게 만든 형태를 막는다."""
    with pytest.raises(ValueError, match="raw_value"):
        EvaluationResult(evaluator="e1", objective="o", validity=Validity.OK)


def test_ok_result_requires_a_direction():
    with pytest.raises(ValueError, match="direction"):
        EvaluationResult(evaluator="e1", objective="o", validity=Validity.OK,
                         raw_value=1.0)


@pytest.mark.parametrize("validity", [Validity.REFUSED, Validity.FAILED, Validity.MISSING])
def test_non_ok_result_requires_a_reason(validity):
    """예외 타입만 세면 경합인지 입력 오류인지 구분할 수 없다."""
    with pytest.raises(ValueError, match="이유가 필요"):
        EvaluationResult(evaluator="e1", objective="o", validity=validity)


@pytest.mark.parametrize("validity", [Validity.REFUSED, Validity.FAILED, Validity.MISSING])
def test_non_ok_result_cannot_carry_a_value(validity):
    with pytest.raises(ValueError, match="raw_value 가 있다"):
        EvaluationResult(evaluator="e1", objective="o", validity=validity,
                         raw_value=1.0, failure_reason="x")


def test_refused_failed_and_missing_are_distinct():
    """세 상태를 하나로 합치지 않는다."""
    kinds = {Validity.REFUSED, Validity.FAILED, Validity.MISSING, Validity.OK}
    assert len(kinds) == 4
    refused = EvaluationResult(evaluator="e1", objective="o",
                               validity=Validity.REFUSED,
                               failure_reason="서열 길이가 기준과 다르다")
    assert not refused.usable
    assert refused.to_dict()["validity"] == "refused"


# ---- Permission -----------------------------------------------------------

def _perm(*allowed, evidence=""):
    return PermissionSet(task_profile="fixed_backbone_redesign", evaluator="e1",
                         objective="structural_preservation",
                         operational=OperationalStatus(True, True, True),
                         allowed=frozenset(allowed), evidence=evidence)


def test_allocation_permission_requires_evidence():
    """사용자가 골랐다는 것은 증거가 아니다 (Invariant 6)."""
    with pytest.raises(ValueError, match="evidence"):
        _perm(ScientificPermission.ALLOCATION)
    ok = _perm(ScientificPermission.ALLOCATION, evidence="prospective holdout")
    assert ok.permits(ScientificPermission.ALLOCATION)


def test_wet_validated_requires_evidence():
    with pytest.raises(ValueError, match="evidence"):
        _perm(ScientificPermission.WET_VALIDATED)


def test_require_names_the_current_permissions():
    p = _perm(ScientificPermission.COMPUTED, ScientificPermission.ANNOTATION)
    with pytest.raises(PermissionError) as exc:
        p.require(ScientificPermission.GATE)
    msg = str(exc.value)
    assert "gate" in msg and "annotation" in msg
    assert "자동 대체하지 않는다" in msg


def test_operational_and_scientific_are_independent():
    """서비스가 살아 있어도 배분에 쓸 수 있는 것은 아니다."""
    p = PermissionSet(task_profile="t", evaluator="ppi_like", objective="binding",
                      operational=OperationalStatus(True, True, True),
                      allowed=frozenset({ScientificPermission.ANNOTATION}))
    assert p.operational.runnable is True
    assert p.permits(ScientificPermission.ALLOCATION) is False


# ---- ScoreTransform -------------------------------------------------------

def test_transform_needs_a_version():
    with pytest.raises(ValueError, match="version"):
        ScoreTransform(name="t", version="", fn=float)


def test_transform_refuses_a_non_ok_result():
    """거부와 실패를 0 으로 바꾸면 그 0 이 나쁜 값처럼 집계된다."""
    t = ScoreTransform(name="t", version="1", fn=lambda v: v / 100.0)
    bad = EvaluationResult(evaluator="e1", objective="o", validity=Validity.REFUSED,
                           failure_reason="대응 불가")
    with pytest.raises(ValueError, match="변환할 수 없다"):
        t.apply(bad)


def test_registry_requires_permission_before_transform():
    """변환을 붙였다는 이유로 쓸 수 있게 되지 않는다."""
    reg = TransformRegistry()
    key = TransformKey("fixed_backbone_redesign", "e1", "structural_preservation",
                       ScientificPermission.RANKING)
    with pytest.raises(KeyError, match="허가가 먼저"):
        reg.register(key, ScoreTransform(name="t", version="1", fn=float))


def test_registry_enforces_the_role():
    reg = TransformRegistry()
    reg.register_permission(_perm(ScientificPermission.ANNOTATION))
    key = TransformKey("fixed_backbone_redesign", "e1", "structural_preservation",
                       ScientificPermission.ALLOCATION)
    with pytest.raises(PermissionError):
        reg.register(key, ScoreTransform(name="t", version="1", fn=float))


def test_registry_does_not_substitute():
    reg = TransformRegistry()
    with pytest.raises(KeyError, match="유사한 변환으로 대체하지 않는다"):
        reg.resolve(TransformKey("other_task", "e1", "o", ScientificPermission.RANKING))


def test_task_profile_is_part_of_the_key():
    """같은 evaluator·objective 라도 task 가 다르면 다른 항목이다."""
    reg = TransformRegistry()
    reg.register_permission(_perm(ScientificPermission.RANKING))
    key = TransformKey("fixed_backbone_redesign", "e1", "structural_preservation",
                       ScientificPermission.RANKING)
    reg.register(key, ScoreTransform(name="t", version="1", fn=lambda v: v / 100.0))
    assert reg.transform(key, EvaluationResult(**OK)) == pytest.approx(0.88)
    other = TransformKey("antigen", "e1", "structural_preservation",
                         ScientificPermission.RANKING)
    with pytest.raises(KeyError):
        reg.resolve(other)


# ---- Invariant 5: Core 에 모델 이름이 없다 --------------------------------

FORBIDDEN = ("AF2", "AF3", "ESMFold", "SoluProt", "PPIformer", "Rosetta",
             "ThermoMPNN", "AntiFold", "ProteinMPNN", "colabfold", "alphafold",
             "IMGT", "epitope", "antibody")


def test_core_package_has_no_model_names():
    """Core 는 무엇으로 쟀는지 몰라야 한다 (설계 §B2, Invariant 5)."""
    core = ROOT / "pipeline-mcp" / "src" / "pipeline_mcp" / "rapid_core"
    hits = []
    for path in sorted(core.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in FORBIDDEN:
            # 금지 목록을 정의한 이 테스트 자신은 대상이 아니다.
            if name.lower() in text.lower():
                hits.append(f"{path.relative_to(ROOT)}: {name}")
    assert not hits, "Core 에 모델 이름이 있다:\n  " + "\n  ".join(hits)
