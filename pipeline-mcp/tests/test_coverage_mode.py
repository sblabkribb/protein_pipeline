"""Phase 4 acceptance — coverage-preserving mode.

q_b 사후분포 사양이 동결되지 않았으므로 adaptive acquisition 은 구현하지
않았다. acquisition **공식** 은 명시적 stub 확률로 검증한다 - 공식을 재는 것과
사전분포를 고르는 것은 다른 일이다.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.rapid_core.coverage import (  # noqa: E402
    CoverageState, OutcomeClass, classify_outcome, effective_coverage,
)
from pipeline_mcp.rapid_core.coverage_policy import (  # noqa: E402
    CoverageAction, CoveragePolicy, CoverageReason, PosteriorNotFrozenError,
)
from pipeline_mcp.rapid_core.evaluation import (  # noqa: E402
    Direction, EvaluationResult, Validity,
)

U = [("T", f"B{i}") for i in range(5)]


def _state(feasible=None, valid=None):
    s = CoverageState(units=tuple(U))
    for i, n in enumerate(feasible or []):
        s.feasible[U[i]] = n
    for i, n in enumerate(valid or []):
        s.valid_observations[U[i]] = n
    return s


class _Stub:
    """명시적 확률. 사전분포를 고르는 것이 아니라 공식을 재기 위한 것이다."""

    def __init__(self, mapping): self.mapping = mapping
    def probability(self, unit): return self.mapping[unit]


# ---- B. EFBC math ---------------------------------------------------------

def test_zero_mass_is_zero():
    assert effective_coverage([0, 0, 0, 0, 0]) == 0.0


def test_one_occupied_context_is_one():
    assert effective_coverage([0, 0, 1, 0, 0]) == pytest.approx(1.0)
    assert effective_coverage([0, 0, 37, 0]) == pytest.approx(1.0)


@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 8])
def test_equal_mass_across_k_contexts_is_k(k):
    assert effective_coverage([10] * k) == pytest.approx(float(k))


def test_zero_and_one_are_different():
    """아무 데도 없는 것과 한 곳에 있는 것은 같지 않다."""
    assert effective_coverage([0, 0]) != effective_coverage([1, 0])


def test_concentration_lowers_efbc():
    assert effective_coverage([20, 2, 2, 2]) < effective_coverage([7, 7, 6, 6])


def test_permutation_invariant():
    import itertools
    base = [7, 3, 1, 0, 5]
    want = effective_coverage(base)
    for perm in itertools.islice(itertools.permutations(base), 30):
        assert effective_coverage(list(perm)) == pytest.approx(want)


def test_efbc_can_decrease_when_a_feasible_candidate_is_added():
    """비단조성은 버그가 아니라 지표의 성질이다."""
    s = _state(feasible=[20, 2, 2, 2, 0])
    assert s.delta_if_feasible(U[0]) < 0.0
    assert s.delta_if_feasible(U[4]) > 0.0


# ---- C. observation semantics ---------------------------------------------

def _result(validity, **kw):
    if validity is Validity.OK:
        return EvaluationResult(evaluator="e", objective="o", validity=validity,
                                raw_value=1.0, direction=Direction.HIGHER_IS_BETTER)
    return EvaluationResult(evaluator="e", objective="o", validity=validity,
                            failure_reason="reason")


def test_joint_pass_is_a_success_update():
    assert classify_outcome(_result(Validity.OK), feasible=True) is OutcomeClass.FEASIBLE


def test_valid_non_pass_is_a_failure_update():
    assert classify_outcome(_result(Validity.OK), feasible=False) is \
        OutcomeClass.VALID_NON_PASS


@pytest.mark.parametrize("validity",
                         [Validity.FAILED, Validity.MISSING, Validity.REFUSED])
def test_technical_outcomes_never_become_biological_failure(validity):
    """기술적 실패를 생물학적 실패로 읽으면 안 된다."""
    assert classify_outcome(_result(validity), feasible=False) is OutcomeClass.NO_UPDATE
    # feasible=True 로 잘못 넘겨도 성립하지 않은 관측은 갱신하지 않는다.
    assert classify_outcome(_result(validity), feasible=True) is OutcomeClass.NO_UPDATE


@pytest.mark.parametrize("validity",
                         [Validity.FAILED, Validity.MISSING, Validity.REFUSED])
def test_technical_outcomes_consume_no_budget_and_no_mass(validity):
    s = _state()
    s.record(U[0], classify_outcome(_result(validity), feasible=False))
    assert s.feasible[U[0]] == 0
    assert s.valid_observations[U[0]] == 0
    assert s.evaluable_slots_used == 0
    # 다만 시도했다는 사실은 운영 수치로 남는다.
    assert s.attempts_made == 1
    assert s.no_update[U[0]] == 1


def test_valid_outcomes_consume_budget():
    s = _state()
    s.record(U[0], OutcomeClass.FEASIBLE)
    s.record(U[0], OutcomeClass.VALID_NON_PASS)
    assert s.evaluable_slots_used == 2
    assert s.feasible[U[0]] == 1


# ---- D. warm-up -----------------------------------------------------------

def test_stop_is_inadmissible_before_warmup():
    p = CoveragePolicy(state=_state(), min_valid_observations=4)
    d = p.decide()
    assert d.action is CoverageAction.PROBE_UNIT
    assert d.reason_code is CoverageReason.WARMUP_INCOMPLETE


def test_warmup_counts_valid_observations_not_attempts():
    s = _state()
    for _ in range(10):
        s.record(U[0], OutcomeClass.NO_UPDATE)     # 시도 10, 유효 0
    p = CoveragePolicy(state=s, min_valid_observations=4)
    assert s.attempted[U[0]] == 10
    assert p._needs_warmup(U[0]) is True


def test_adaptive_only_after_every_unit_is_warmed_up():
    s = _state(valid=[4, 4, 4, 4, 3])
    p = CoveragePolicy(state=s, min_valid_observations=4,
                       probability_model=_Stub({u: 0.5 for u in U}))
    assert p.decide().action is CoverageAction.PROBE_UNIT
    s.valid_observations[U[4]] = 4
    assert p.decide().action in (CoverageAction.ADVANCE_UNIT, CoverageAction.STOP)


def test_warmup_blocked_by_execution_is_infeasible_not_stop():
    s = _state(valid=[4, 4, 4, 4, 0])
    p = CoveragePolicy(state=s, min_valid_observations=4)
    p.mark_execution_unavailable(U[4])
    d = p.decide()
    assert d.action is CoverageAction.EXECUTION_INFEASIBLE
    assert d.reason_code is CoverageReason.WARMUP_BLOCKED_BY_EXECUTION
    assert d.action is not CoverageAction.STOP


# ---- E. acquisition -------------------------------------------------------

def test_acquisition_is_exactly_q_times_delta():
    """손계산과 정확히 일치. 몬테카를로로 근사하지 않는다."""
    s = _state(feasible=[3, 1, 0, 0, 0], valid=[4, 4, 4, 4, 4])
    q = {U[0]: 0.9, U[1]: 0.5, U[2]: 0.25, U[3]: 0.1, U[4]: 0.05}
    p = CoveragePolicy(state=s, min_valid_observations=4, probability_model=_Stub(q))
    d = p.decide()
    for unit in U:
        before = effective_coverage([3, 1, 0, 0, 0])
        after_counts = [3, 1, 0, 0, 0]
        after_counts[U.index(unit)] += 1
        want = q[unit] * (effective_coverage(after_counts) - before)
        got = d.record["per_unit"]["|".join(unit)]["expected_marginal_efbc_gain"]
        assert got == pytest.approx(want, abs=1e-15)


def test_acquisition_has_no_extra_terms():
    """uncertainty bonus·diversity scalar·yield term 이 섞이면 값이 달라진다."""
    s = _state(feasible=[2, 2, 0, 0, 0], valid=[4] * 5)
    q = {u: 0.4 for u in U}
    p = CoveragePolicy(state=s, min_valid_observations=4, probability_model=_Stub(q))
    d = p.decide()
    for unit in U:
        entry = d.record["per_unit"]["|".join(unit)]
        assert entry["expected_marginal_efbc_gain"] == pytest.approx(
            entry["q"] * entry["delta_efbc_if_feasible"], abs=1e-15)
        assert set(entry) == {"q", "delta_efbc_if_feasible",
                              "expected_marginal_efbc_gain"}


def test_argmax_selects_the_highest_expected_gain():
    s = _state(feasible=[5, 0, 0, 0, 0], valid=[4] * 5)
    q = {U[0]: 0.99, U[1]: 0.30, U[2]: 0.05, U[3]: 0.05, U[4]: 0.05}
    p = CoveragePolicy(state=s, min_valid_observations=4, probability_model=_Stub(q))
    d = p.decide()
    assert d.action is CoverageAction.ADVANCE_UNIT
    assert d.unit == U[1]      # 큰 q 를 가진 U0 이 아니다 - delta 가 음수다


# ---- F. STOP --------------------------------------------------------------

def test_stop_when_no_positive_gain():
    s = _state(feasible=[10, 10, 10, 10, 10], valid=[4] * 5)
    p = CoveragePolicy(state=s, min_valid_observations=4,
                       probability_model=_Stub({u: 0.5 for u in U}))
    d = p.decide()
    assert d.action is CoverageAction.STOP
    assert d.reason_code is CoverageReason.NO_POSITIVE_EXPECTED_GAIN
    assert all(e["expected_marginal_efbc_gain"] <= 0
               for e in d.record["per_unit"].values())


def test_stop_is_not_execution_infeasible():
    assert CoverageAction.STOP is not CoverageAction.EXECUTION_INFEASIBLE


def test_budget_exhausted_is_not_stop():
    s = _state(feasible=[1, 1, 1, 1, 1], valid=[4] * 5)
    p = CoveragePolicy(state=s, min_valid_observations=4, evaluable_budget=20,
                       probability_model=_Stub({u: 0.5 for u in U}))
    d = p.decide()
    assert d.action is CoverageAction.BUDGET_EXHAUSTED
    assert d.action is not CoverageAction.STOP


# ---- G. execution unavailable ---------------------------------------------

def test_unavailable_unit_changes_no_scientific_state():
    s = _state(feasible=[1, 1, 1, 1, 1], valid=[4] * 5)
    p = CoveragePolicy(state=s, min_valid_observations=4,
                       probability_model=_Stub({u: 0.5 for u in U}))
    before = (dict(s.feasible), dict(s.valid_observations), s.evaluable_slots_used)
    p.mark_execution_unavailable(U[0])
    after = (dict(s.feasible), dict(s.valid_observations), s.evaluable_slots_used)
    assert before == after


def test_unavailable_unit_is_not_reselected():
    s = _state(feasible=[5, 0, 0, 0, 0], valid=[4] * 5)
    q = {U[0]: 0.05, U[1]: 0.99, U[2]: 0.1, U[3]: 0.1, U[4]: 0.1}
    p = CoveragePolicy(state=s, min_valid_observations=4, probability_model=_Stub(q))
    assert p.decide().unit == U[1]
    p.mark_execution_unavailable(U[1])
    again = p.decide()
    assert again.unit != U[1]
    assert "|".join(U[1]) not in again.record["per_unit"]
    assert "|".join(U[1]) in again.record["execution_unavailable"]


def test_all_units_unavailable_after_warmup_is_infeasible():
    s = _state(feasible=[1] * 5, valid=[4] * 5)
    p = CoveragePolicy(state=s, min_valid_observations=4,
                       probability_model=_Stub({u: 0.5 for u in U}))
    for u in U:
        p.mark_execution_unavailable(u)
    d = p.decide()
    assert d.action is CoverageAction.EXECUTION_INFEASIBLE
    assert d.reason_code is CoverageReason.NO_ADMISSIBLE_UNIT


def test_recovery_makes_a_unit_admissible_again():
    s = _state(feasible=[5, 0, 0, 0, 0], valid=[4] * 5)
    q = {U[0]: 0.05, U[1]: 0.99, U[2]: 0.1, U[3]: 0.1, U[4]: 0.1}
    p = CoveragePolicy(state=s, min_valid_observations=4, probability_model=_Stub(q))
    p.mark_execution_unavailable(U[1])
    assert p.decide().unit != U[1]
    p.mark_execution_recovered(U[1])
    assert p.decide().unit == U[1]


# ---- q_b hard gate --------------------------------------------------------

def test_adaptive_stage_refuses_to_run_without_a_frozen_posterior():
    """임의 사전분포로 조용히 진행하지 않는다."""
    s = _state(valid=[4] * 5)
    p = CoveragePolicy(state=s, min_valid_observations=4)   # 모형 없음
    with pytest.raises(PosteriorNotFrozenError, match="동결"):
        p.decide()


def test_warmup_does_not_need_the_posterior():
    """q_b 없이도 warm-up 은 돌 수 있다 - 그 단계는 확률을 쓰지 않는다."""
    p = CoveragePolicy(state=_state(), min_valid_observations=4)
    assert p.decide().action is CoverageAction.PROBE_UNIT


# ---- H. mode isolation ----------------------------------------------------

def test_decision_record_has_the_documented_fields():
    s = _state(feasible=[1, 0, 0, 0, 0], valid=[4] * 5)
    p = CoveragePolicy(state=s, min_valid_observations=4,
                       probability_model=_Stub({u: 0.5 for u in U}))
    r = p.decide().record
    for key in ("current_efbc", "feasible_counts", "valid_observations",
                "warmup_complete", "evaluable_slots_used", "attempts_made",
                "execution_unavailable", "per_unit", "selected_action",
                "selected_unit", "reason_code"):
        assert key in r, f"결정 기록에 {key} 가 없다"


def test_coverage_modules_have_no_domain_literals():
    forbidden = ("backbone", "AF2", "SoluProt", "antibody", "temperature",
                 "RFD3", "plddt", "rmsd", "joint-pass", "joint_pass")
    core = ROOT / "pipeline-mcp" / "src" / "pipeline_mcp" / "rapid_core"
    hits = []
    for name in ("coverage.py", "coverage_policy.py"):
        text = (core / name).read_text(encoding="utf-8")
        for word in forbidden:
            if word.lower() in text.lower():
                hits.append(f"{name}: {word}")
    assert not hits, "coverage Core 에 도메인 어휘가 있다:\n  " + "\n  ".join(hits)
