"""v2.0 multi-source calibration 코호트(calibration_v2)의 선정 동결.

이 코호트가 존재하는 이유는 하나다 - 기존 51-backbone calibration 이 단일
source · 불균형 backbone(5/4/2) 이라 `kappa_pool` 을 source 별로 식별할 수
없었다. 그래서 새로 뽑았고, **결과 정보를 하나도 쓰지 않았다**는 것이 검증
가능해야 한다.

가장 중요한 것은 `test_the_pool_matches_the_count_committed_before_selection` 다.
풀 크기(183 · 80/36/67)를 선정 **전에** plan JSON 에 적어 커밋했다. 선정 후
산출물의 풀이 그 값과 다르면 제외 목록이 달라진 것이고, 그러면 미선별 코호트가
아니다.
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "public_data" / "benchmark" / "gate0"
COHORT = BASE / "calibration_v2_targets.json"
PLAN = BASE / "multisource_validation_plan.json"


def _c() -> dict:
    if not COHORT.exists():
        pytest.skip("calibration_v2 코호트 없음")
    return json.loads(COHORT.read_text(encoding="utf-8"))


def _plan() -> dict:
    if not PLAN.exists():
        pytest.skip("plan 없음")
    return json.loads(PLAN.read_text(encoding="utf-8"))


def test_design_matches_the_multisource_freeze():
    d = _c()["design"]
    p = _plan()["per_source_design"]
    assert d["n_targets"] == 12
    assert d["backbone_sources"] == ["rfd3", "bioemu"]
    assert d["backbones_per_target"] == p["backbones_per_target"] == 10
    assert d["sequences_per_backbone"] == p["calibration_candidates_per_backbone"] == 12
    assert d["total_folds_per_source"] == 12 * 10 * 12 == 1440
    assert d["total_folds"] == 1440 * 2 == 2880
    assert d["total_folds"] == _plan()["totals"]["calibration_all_sources"]
    assert d["temperature"] == 0.1


def test_strata_are_balanced_with_reserves():
    c = _c()
    assert dict(collections.Counter(t["stratum"] for t in c["selected"])) == {
        "50-150": 4, "150-250": 4, "250-400": 4}
    assert dict(collections.Counter(t["stratum"] for t in c["reserve"])) == {
        "50-150": 2, "150-250": 2, "250-400": 2}


def test_the_pool_matches_the_count_committed_before_selection():
    """선정 전에 커밋한 풀과 같아야 한다. 다르면 제외 목록이 달라진 것이다."""
    c, cv = _c(), _plan()["cohorts"]["calibration_v2"]
    assert c["pool"]["n_eligible"] == cv["pool_eligible_after_all_exclusions"] == 183
    assert c["pool"]["by_stratum"] == cv["pool_by_stratum"]
    assert c["seed"] == cv["seed"] == 20260911
    need = cv["per_stratum"] + cv["reserve_per_stratum"]
    for stratum, n in c["pool"]["by_stratum"].items():
        assert n >= need, f"{stratum} 층 {n} < {need}"


def test_the_selection_is_recorded_with_a_digest():
    c, cv = _c(), _plan()["cohorts"]["calibration_v2"]
    assert cv["selection_committed"] is True
    sel = sorted(t["domain"] for t in c["selected"])
    assert sel == sorted(cv["selected"])
    assert hashlib.sha256(json.dumps(sel).encode()).hexdigest() == cv["selected_sha256"]
    assert len(cv["reserve_order"]) == 6


def test_isolated_from_every_earlier_cohort():
    c = _c()
    picked = {t["domain"] for t in c["selected"]} | {t["domain"] for t in c["reserve"]}
    used = set(c["exclusions"]["used_targets"])
    assert len(used) == 74, f"제외 타겟 수가 {len(used)} 로 바뀌었다"
    assert not (picked & used), sorted(picked & used)
    # 키 이름은 산출물의 `cohort` 필드 유무에 따라 갈린다 (옛 파일은 파일명
    # 스템으로 떨어진다). 이름을 고정하지 않고 **어느 코호트가 기여했는지**를 본다.
    srcs = c["exclusions"]["used_target_sources"]
    contributed = {
        "기존 calibration": [k for k in srcs if k.startswith("calibration")],
        "masked_holdout": [k for k in srcs if k.startswith("masked_holdout")],
        "원 holdout": [k for k in srcs if k.startswith("holdout")],
        "온도 패널": [k for k in srcs if k.startswith("temperature")],
    }
    for label, keys in contributed.items():
        assert keys, f"{label} 이 제외 출처에 없다: {sorted(srcs)}"
        assert any(srcs[k] for k in keys), f"{label} 의 목록이 비었다"
    # 모든 출처의 합집합이 실제 제외 집합과 같아야 한다 - 일부만 반영되면 안 된다
    union = {t for v in srcs.values() for t in v}
    assert union == used, f"출처 합집합 {len(union)} != 제외 {len(used)}"


def test_superfamilies_isolated_from_all_three_prior_cohorts():
    c = _c()
    sf = {t["superfamily"] for t in c["selected"]}
    assert len(sf) == len(c["selected"]), "선정 안에 superfamily 중복"
    for name, key in (("calibration_targets.json", "selected"),
                      ("masked_holdout_targets.json", "selected")):
        o = json.loads((BASE / name).read_text(encoding="utf-8"))
        other = {t["superfamily"] for t in o[key]} | {t["superfamily"] for t in o["reserve"]}
        assert not (sf & other), f"{name} 와 겹친다: {sorted(sf & other)}"
    h = json.loads((BASE / "holdout_targets.json").read_text(encoding="utf-8"))
    assert not (sf & {t["superfamily"] for t in h["resolved"]["targets"]})


def test_selection_used_no_outcome_signal_from_either_source():
    c = _c()
    assert c["selection_inputs"] == ["적격성", "길이"]
    excluded = " ".join(c["selection_excluded_inputs"])
    for signal in ("yield", "SoluProt", "structural-success", "joint-pass",
                   "Gate 0", "MSA 심도", "RFD3 성공률", "BioEmu 성공률", "eligible"):
        assert signal in excluded, f"{signal} 가 제외 목록에 없다"


def test_msa_outcome_could_not_have_been_used():
    """MSA pilot 은 이 선정과 무관해야 한다 - 다른 코호트의 타겟이었다."""
    c = _c()
    picked = {t["domain"] for t in c["selected"]} | {t["domain"] for t in c["reserve"]}
    holdout = json.loads((BASE / "masked_holdout_targets.json").read_text(encoding="utf-8"))
    pilot = set(holdout["msa_pilot"]["targets"].values())
    assert not (picked & pilot), "MSA pilot 타겟이 새 calibration 에 들어갔다"


def test_reserve_substitution_is_pre_generation_only():
    rule = _c()["substitution_rule"]
    assert "생성 시작 전에" in rule
    assert "SOURCE_GENERATION_INFEASIBLE" in rule
    assert "타겟을 바꾸지 않는다" in rule


def test_cohort_is_marked_not_for_performance_claims():
    for claim in ("policy 비교", "EFBC 계산", "confirmatory 주장"):
        assert claim in _c()["not_for"], f"{claim} 가 금지 목록에 없다"


def test_it_points_at_the_multisource_freeze():
    assert "multisource-validation-freeze" in _c()["freeze_doc"]
