"""Phase 4B calibration 코호트가 동결된 규칙대로 뽑혔는지.

가장 중요한 것은 `test_eligibility_is_not_taken_from_the_legacy_manifest` 다.
legacy `rapid_target_manifest.csv` 는 옛 길이 기준을 써서 이번 코호트의 정상
타겟도 eligible=False 로 적고 있다. 그 열을 재사용하면 250-400 층이 통째로
빠지는데, 테스트가 없으면 조용히 그렇게 된다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "public_data" / "benchmark" / "gate0" / "calibration_targets.json"
HOLDOUT = ROOT / "public_data" / "benchmark" / "gate0" / "holdout_targets.json"
LEGACY = ROOT / "public_data" / "benchmark" / "results" / "rapid_target_manifest.csv"


def _cohort() -> dict:
    if not COHORT.exists():
        pytest.skip("calibration 코호트 없음")
    return json.loads(COHORT.read_text(encoding="utf-8"))


def test_design_matches_the_freeze():
    d = _cohort()["design"]
    assert d["n_targets"] == 12
    assert d["backbones_per_target"] == 5
    assert d["sequences_per_backbone"] == 8
    assert d["total_folds"] == 480
    assert d["temperature"] == 0.1


def test_length_strata_are_balanced():
    import collections
    c = collections.Counter(t["stratum"] for t in _cohort()["selected"])
    assert dict(c) == {"50-150": 4, "150-250": 4, "250-400": 4}


def test_no_overlap_with_anything_already_used():
    d = _cohort()
    picked = {t["domain"] for t in d["selected"]} | {t["domain"] for t in d["reserve"]}
    used = set(d["exclusions"]["used_targets"])
    assert not (picked & used), f"이미 쓴 타겟과 겹친다: {sorted(picked & used)}"


def test_superfamilies_are_isolated():
    """근접 중복이 남으면 이름만 독립 코호트다."""
    d = _cohort()
    picked_sf = {t["superfamily"] for t in d["selected"]}
    assert len(picked_sf) == len(d["selected"]), "선정 안에 superfamily 중복이 있다"
    if HOLDOUT.exists():
        hold = json.loads(HOLDOUT.read_text(encoding="utf-8"))
        hold_sf = {t["superfamily"] for t in hold["resolved"]["targets"]}
        assert not (picked_sf & hold_sf), f"holdout superfamily 와 겹친다: {picked_sf & hold_sf}"


def test_eligibility_is_not_taken_from_the_legacy_manifest():
    """옛 manifest 의 eligible 열을 쓰면 250-400 층이 통째로 빠진다."""
    if not LEGACY.exists():
        pytest.skip("legacy manifest 없음")
    legacy = {}
    for row in csv.DictReader(LEGACY.open(encoding="utf-8")):
        key = row.get("target") or row.get("domain")
        if key:
            legacy[key] = row.get("eligible", "")
    picked = [t["domain"] for t in _cohort()["selected"]]
    marked_false = [t for t in picked if legacy.get(t) == "False"]
    # 옛 기준으로는 False 인 타겟이 코호트에 들어 있어야 정상이다 - 들어 있다는
    # 것이 곧 그 열을 쓰지 않았다는 증거다.
    assert marked_false, (
        "옛 manifest 에서 eligible=False 인 타겟이 하나도 없다. 그 열을 재사용해 "
        "거른 것은 아닌지 확인이 필요하다.")
    for t in marked_false:
        row = next(r for r in csv.DictReader(LEGACY.open(encoding="utf-8"))
                   if (r.get("target") or r.get("domain")) == t)
        length = int(row["length"])
        assert 50 <= length <= 400, f"{t} 길이 {length} 가 동결 기준 밖이다"


def test_selection_inputs_exclude_every_outcome_signal():
    d = _cohort()
    excluded = " ".join(d["selection_excluded_inputs"])
    for signal in ("yield", "SoluProt", "structural-success", "joint-pass", "Gate 0"):
        assert signal in excluded, f"{signal} 가 제외 목록에 없다"
    assert d["selection_inputs"] == ["적격성", "길이"]


def test_cohort_is_marked_not_for_performance_claims():
    d = _cohort()
    for claim in ("policy 비교", "EFBC 계산", "confirmatory 주장"):
        assert claim in d["not_for"], f"{claim} 가 금지 목록에 없다"


# ---- 생성 후 확정된 코호트 -------------------------------------------------

def _realized():
    d = _cohort()
    if "realized_cohort" not in d:
        pytest.skip("아직 생성 전")
    return d["realized_cohort"]


def test_cohort_was_not_topped_up_or_trimmed():
    """생성 결과를 보고 코호트를 수선하지 않았다."""
    r = _realized()
    counts = r["backbones_per_target"]
    # 부족한 타겟이 5 로 채워졌다면 추가 생성을 준 것이다.
    assert min(counts.values()) < 5, (
        "모든 타겟이 5 개다 - 부족분을 사후에 채운 것은 아닌지 확인이 필요하다")
    # 형제가 둘 이상인 타겟은 전부 남아 있어야 한다 (complete-case 아님)
    partial = [t for t, n in counts.items() if 2 <= n < 5]
    assert partial, "부분 형제 집합이 사라졌다 - complete-case 선택이 의심된다"
    for t in partial:
        assert t in r["informative_targets"], f"{t} 가 informative 에서 빠졌다"


def test_only_zero_backbone_targets_are_excluded():
    r = _realized()
    for t, n in r["backbones_per_target"].items():
        if n == 0:
            assert t in r["generation_infeasible"]
        else:
            assert t in r["informative_targets"], f"{t} ({n} 개) 가 빠졌다"


def test_fold_count_follows_from_the_realized_backbones():
    r = _realized()
    assert r["total_folds"] == r["n_backbones"] * r["sequences_per_backbone"]


def test_loto_weighting_is_target_equal():
    """불균형 코호트에서 단순 합산은 5-backbone 타겟을 과대 가중한다."""
    r = _realized()
    assert "타겟 동일 가중" in r["loto_weighting"]
    freeze = (ROOT / "docs" / "specs" /
              "rapid-v2-phase4b-calibration-freeze.md").read_text(encoding="utf-8")
    assert "타겟 동일 가중" in freeze
    assert "target-equal estimand" in freeze
