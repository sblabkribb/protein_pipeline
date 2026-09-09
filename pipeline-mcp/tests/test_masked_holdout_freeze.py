"""새 masked confirmatory holdout 의 선정 동결.

이 코호트는 calibration 결과를 보기 전에 잠긴다. 나중에 "κ 를 정한 뒤 이미
잠겨 있던 새 코호트에 한 번 적용했다" 고 말하려면 그 잠금이 검증 가능해야 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "public_data" / "benchmark" / "gate0"
HOLDOUT = BASE / "masked_holdout_targets.json"


def _d() -> dict:
    if not HOLDOUT.exists():
        pytest.skip("masked holdout 목록 없음")
    return json.loads(HOLDOUT.read_text(encoding="utf-8"))


def test_design_matches_the_sequence_constraint_freeze():
    d = _d()["design"]
    assert d["n_targets"] == 12
    assert d["backbones_per_target"] == 5
    assert d["sequences_per_backbone"] == 24     # 8/8/8, budget grid 120 을 위해
    assert d["total_folds"] == 1440


def test_strata_are_balanced_with_reserves():
    import collections
    d = _d()
    assert dict(collections.Counter(t["stratum"] for t in d["selected"])) == {
        "50-150": 4, "150-250": 4, "250-400": 4}
    assert dict(collections.Counter(t["stratum"] for t in d["reserve"])) == {
        "50-150": 2, "150-250": 2, "250-400": 2}


def test_isolated_from_every_earlier_cohort():
    d = _d()
    picked = {t["domain"] for t in d["selected"]} | {t["domain"] for t in d["reserve"]}
    used = set(d["exclusions"]["used_targets"])
    assert not (picked & used)
    srcs = d["exclusions"]["used_target_sources"]
    # calibration 이 제외 목록에 실제로 들어갔는지
    assert any("calibration" in k for k in srcs), "calibration 이 제외되지 않았다"


def test_superfamilies_isolated():
    d = _d()
    sf = {t["superfamily"] for t in d["selected"]}
    assert len(sf) == len(d["selected"]), "선정 안에 superfamily 중복"
    for other, key in ((BASE / "calibration_targets.json", "selected"),
                       (BASE / "holdout_targets.json", None)):
        if not other.exists():
            continue
        o = json.loads(other.read_text(encoding="utf-8"))
        rows = o["resolved"]["targets"] if key is None else o[key]
        assert not (sf & {t["superfamily"] for t in rows}), f"{other.name} 와 겹친다"


def test_selection_used_no_outcome_signal():
    d = _d()
    excluded = " ".join(d["selection_excluded_inputs"])
    for signal in ("yield", "SoluProt", "structural-success", "joint-pass",
                   "Gate 0", "MSA 심도", "RFD3 성공률", "eligible"):
        assert signal in excluded, f"{signal} 가 제외 목록에 없다"
    assert d["selection_inputs"] == ["적격성", "길이"]


def test_selector_reads_only_identity_from_outcome_files():
    """선정 코드가 결과 파일에서 target_id 말고 다른 열을 읽지 않는지."""
    src = (ROOT / "scripts" / "transcoder" /
           "46_select_calibration_targets.py").read_text(encoding="utf-8")
    body = "\n".join(l.split("#")[0] for l in src.splitlines())
    for column in ('"plddt"', '"soluprot"', '"rmsd_nonloop_order"', '"status"'):
        assert column not in body, f"선정 경로가 결과 열 {column} 을 읽는다"
    assert 'r["target_id"]' in body, "target_id 만 읽는 경로가 사라졌다"


def test_msa_pilot_is_frozen_before_msa_runs():
    d = _d()
    pilot = d["msa_pilot"]
    assert pilot["frozen_before_msa"] is True
    assert len(pilot["targets"]) == 3, "층마다 하나씩 3 개여야 한다"
    # 규칙대로 층별 첫 primary 인지 다시 계산해 대조한다
    import collections
    by = collections.defaultdict(list)
    for t in d["selected"]:
        by[t["stratum"]].append(t["domain"])
    want = {k: sorted(v)[0] for k, v in by.items()}
    assert pilot["targets"] == want, "pilot 이 결정적 규칙과 다르다"
    for banned in ("MSA threshold 변경", "타겟 선정 규칙 변경", "tier 변경"):
        assert banned in pilot["forbidden_actions"]
