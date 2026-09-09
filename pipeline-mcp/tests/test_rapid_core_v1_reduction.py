"""Phase 3 acceptance — generic Core 가 frozen v1 을 정확히 재현하는가.

"거의 같다" 는 실패다. tolerance 를 넓혀서 통과시키지 않는다.

단계별로 내부 상태까지 대조한다. 최종 행동만 보면 계산이 다른데 우연히 같은
답이 나온 경우를 놓친다. 그리고 UI 의 "왜 이쪽인가" 가 score_parts 를 보여줄
예정이므로, 설명 가능성 contract 도 여기서 함께 고정한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.allocation import Arm as V1Arm  # noqa: E402
from pipeline_mcp.allocation import HierarchicalAllocator as V1Allocator  # noqa: E402
from pipeline_mcp.rapid_core.profiles import build_v1_core  # noqa: E402

#: golden test 와 같은 fixture. 값을 바꾸지 않는다.
OBSERVATIONS = [
    ("T|B0|T0.1", 1, 2),
    ("T|B1|T0.1", 6, 8),
    ("T|B0|T0.1", 1, 2),
    ("T|B2|T0.1", 0, 8),
    ("T|B0|T0.1", 0, 8),
    ("T|B0|T0.1", 0, 12),
]
N_BACKBONES = 4
PRIOR = (0.42, 3.0)
REF = "T0.1"


def _pair():
    specs = [("T", f"B{i}", REF) for i in range(N_BACKBONES)]
    v1 = V1Allocator([V1Arm(target_id="T", backbone_id=f"B{i}", condition=REF)
                      for i in range(N_BACKBONES)],
                     seed=0, reference_condition=REF)
    v1.set_target_prior("T", mean=PRIOR[0], strength=PRIOR[1])
    v2 = build_v1_core(specs, reference_condition=REF,
                       prior_mean=PRIOR[0], prior_strength=PRIOR[1])
    return v1, v2


def _v1_state(v1, backbone="B0"):
    s = v1.probe_state("T", backbone)
    return (s["n_observed"], s["p_hat"], s["uncertainty"], s["movability"])


def _v2_state(v2, backbone="B0"):
    s = v2.model.unit_state(("T", backbone))
    return (s["n_observed"], s["p_hat"], s["uncertainty"], s["allocation_signal"])


# ---- 1. 단계별 내부 상태 --------------------------------------------------

def test_step_by_step_unit_state_is_identical():
    """행동이 아니라 상태를 먼저 본다. 반올림 없이 원값으로 비교한다."""
    v1, v2 = _pair()
    for step, (key, s, t) in enumerate(OBSERVATIONS):
        v1.observe(key, successes=s, trials=t)
        v2.model.observe(key, successes=s, trials=t)
        for backbone in [f"B{i}" for i in range(N_BACKBONES)]:
            got, want = _v2_state(v2, backbone), _v1_state(v1, backbone)
            assert got == want, (
                f"step {step} · {backbone}: v1 {want} vs core {got}")


def test_step_by_step_raw_posteriors_are_bit_identical():
    """반올림 전 원값이 같아야 한다. 반올림 뒤만 보면 4 자리 아래가 갈라져도 통과한다."""
    v1, v2 = _pair()
    for step, (key, s, t) in enumerate(OBSERVATIONS):
        v1.observe(key, successes=s, trials=t)
        v2.model.observe(key, successes=s, trials=t)
        for arm_key in v2.arm_keys:
            a1, a2 = v1.posterior(arm_key), v2.model.posterior(arm_key)
            assert (a1.alpha, a1.beta) == (a2.alpha, a2.beta), (
                f"step {step} · {arm_key} arm 사후분포: "
                f"v1 ({a1.alpha}, {a1.beta}) vs core ({a2.alpha}, {a2.beta})")
            b1, b2 = v1.backbone_posterior(arm_key), v2.model.unit_posterior(arm_key)
            assert (b1.alpha, b1.beta) == (b2.alpha, b2.beta), (
                f"step {step} · {arm_key} 단위 사후분포가 다르다")
            assert a1.mean == a2.mean and a1.sd == a2.sd


# ---- 2. score_parts (설명 가능성 contract) --------------------------------

def test_step_by_step_score_parts_are_identical():
    """UI 의 "왜 이쪽인가" 가 이 값에서 만들어진다."""
    v1, v2 = _pair()
    mapping = {
        "posterior_mean": "expected_utility",
        "uncertainty": "uncertainty",
        "diversity": "diversity",
        "cost": "cost",
        "condition_exploration": "variation_exploration",
        "movability": "allocation_signal",
        "is_reference_condition": "is_reference_variation",
    }
    for step, (key, s, t) in enumerate(OBSERVATIONS):
        v1.observe(key, successes=s, trials=t)
        v2.model.observe(key, successes=s, trials=t)
        for selected in ([], [v2.arm_keys[0]], v2.arm_keys[:2]):
            for arm_key in v2.arm_keys:
                p1 = v1.score_parts(arm_key, selected=selected)
                p2 = v2.score_parts(arm_key, selected=selected)
                for old, new in mapping.items():
                    assert p1[old] == p2[new], (
                        f"step {step} · {arm_key} · selected={selected} · "
                        f"{old}: v1 {p1[old]} vs core {p2[new]}")
                assert v1.score(arm_key, selected=selected) == \
                    v2.score(arm_key, selected=selected)


# ---- 3. 행동 열 -----------------------------------------------------------

def test_action_sequence_is_identical():
    v1, v2 = _pair()
    a1, a2 = [], []
    for key, s, t in OBSERVATIONS:
        v1.observe(key, successes=s, trials=t)
        v2.model.observe(key, successes=s, trials=t)
        a1.append(v1.next_action("T", "B0")["action"])
        a2.append(v2.next_action(("T", "B0")).action)
    assert a2 == a1
    # golden 이 고정한 열과도 같아야 한다.
    assert a2 == ["probe_more_sequences", "probe_more_sequences",
                  "explore_generation_condition", "explore_generation_condition",
                  "explore_generation_condition", "explore_generation_condition"]


def test_reasons_match_too():
    """행동만 같고 이유가 다르면 UI 설명이 갈라진다."""
    v1, v2 = _pair()
    for key, s, t in OBSERVATIONS:
        v1.observe(key, successes=s, trials=t)
        v2.model.observe(key, successes=s, trials=t)
        assert v2.next_action(("T", "B0")).reason == v1.next_action("T", "B0")["reason"]


# ---- 4. acquisition 순위 --------------------------------------------------

def test_allocation_order_is_identical():
    v1, v2 = _pair()
    for key, s, t in OBSERVATIONS:
        v1.observe(key, successes=s, trials=t)
        v2.model.observe(key, successes=s, trials=t)
        for budget in (1, 2, 4, 8):
            assert v2.allocate(budget=budget) == v1.allocate(budget=budget), (
                f"budget {budget} 에서 배분 순서가 다르다")


def test_golden_acquisition_ranking_reproduces():
    """golden test 가 고정한 순위."""
    specs = [("T", f"B{i}", REF) for i in range(4)]
    v2 = build_v1_core(specs, reference_condition=REF,
                       prior_mean=0.42, prior_strength=3.0)
    v2.model.observe("T|B0|T0.1", successes=0, trials=8)
    v2.model.observe("T|B1|T0.1", successes=4, trials=8)
    v2.model.observe("T|B2|T0.1", successes=8, trials=8)
    ranked = sorted(v2.arm_keys, key=lambda k: (-v2.score(k), k))
    assert ranked == ["T|B2|T0.1", "T|B3|T0.1", "T|B1|T0.1", "T|B0|T0.1"]


# ---- 5. 부분 풀링 ---------------------------------------------------------

def test_partial_pooling_value_reproduces_exactly():
    """형제 8/8 이 미관측 arm 을 0.42 -> 0.8418181818 로 옮긴다."""
    specs = [("T", f"B{i}", REF) for i in range(2)]
    v2 = build_v1_core(specs, reference_condition=REF,
                       prior_mean=0.42, prior_strength=3.0)
    before = v2.model.expected_utility("T|B1|T0.1")
    v2.model.observe("T|B0|T0.1", successes=8, trials=8)
    after = v2.model.expected_utility("T|B1|T0.1")
    assert round(before, 10) == 0.42
    assert round(after, 10) == 0.8418181818


# ---- 6. leakage guard -----------------------------------------------------

def test_true_yield_cannot_be_injected():
    v2 = build_v1_core([("T", "B0", REF)], reference_condition=REF)
    with pytest.raises(TypeError):
        v2.model.set_true_yield(0.9)


def test_signal_does_not_decay_with_more_observations():
    """allocation_signal 은 관측 수에 무관하다 - information gain 이 아니다."""
    thin = build_v1_core([("T", "B0", REF)], reference_condition=REF)
    thick = build_v1_core([("T", "B0", REF)], reference_condition=REF)
    thin.model.observe("T|B0|T0.1", successes=2, trials=4)
    thick.model.observe("T|B0|T0.1", successes=200, trials=400)
    assert thin.model.allocation_signal("T|B0|T0.1") == pytest.approx(
        thick.model.allocation_signal("T|B0|T0.1"), abs=0.02)
    assert thin.model.uncertainty("T|B0|T0.1") > \
        5 * thick.model.uncertainty("T|B0|T0.1")
