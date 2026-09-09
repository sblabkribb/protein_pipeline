"""sequence-constraint protocol 동결이 코드의 실제 기본값과 맞는지.

문서에 적힌 프로토콜이 배포 기본값과 다르면, 이번 변경의 목적 자체가 사라진다 -
배포와 검증을 일치시키려고 하는 일이기 때문이다.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "transcoder"))

FREEZE = ROOT / "docs" / "specs" / "rapid-v2-sequence-constraint-protocol-freeze.md"


def _doc() -> str:
    if not FREEZE.exists():
        pytest.skip("동결 문서 없음")
    return FREEZE.read_text(encoding="utf-8")


def _default(name):
    from pipeline_mcp.models import PipelineRequest
    f = PipelineRequest.__dataclass_fields__[name]
    return f.default if f.default is not dataclasses.MISSING else f.default_factory()


@pytest.mark.parametrize("field,text", [
    ("conservation_tiers", "[0.3, 0.5, 0.7]"),
    ("conservation_mode", "quantile"),
    ("conservation_weighting", "none"),
    ("conservation_cluster_method", "linclust"),
    ("ligand_mask_distance", "6.0"),
])
def test_frozen_protocol_matches_the_deployment_default(field, text):
    """문서가 배포 기본값을 그대로 적었는가."""
    assert text in _doc(), f"{field} 값 {text} 가 문서에 없다"
    assert str(_default(field)) == text or text in str(_default(field)), (
        f"{field}: 코드 기본값 {_default(field)!r} 가 문서의 {text} 와 다르다")


def test_mpnn_settings_match_the_frozen_protocol():
    from rapid_sr.protocol import GATE0_MPNN_SETTINGS
    doc = _doc()
    for key, value in GATE0_MPNN_SETTINGS.items():
        assert str(value) in doc, f"MPNN {key}={value} 가 문서에 없다"


def test_joint_pass_thresholds_are_unchanged():
    from rapid_sr.protocol import GATE0_THRESHOLDS
    doc = _doc()
    for key, value in GATE0_THRESHOLDS.items():
        assert str(value) in doc, f"{key}={value} 가 문서에 없다"


def test_msa_rules_use_the_existing_quality_thresholds():
    """새 숫자를 만들지 않았는지. a3m.msa_quality 의 경계와 같아야 한다."""
    src = (ROOT / "pipeline-mcp" / "src" / "pipeline_mcp" / "bio" / "a3m.py").read_text(
        encoding="utf-8")
    assert "usable_hits < 10" in src, "코드의 저심도 경계가 바뀌었다"
    doc = _doc()
    assert "usable_hits < 10" in doc
    assert "MSA_INFEASIBLE" in doc and "MSA_INSUFFICIENT_DEPTH" in doc


def test_tier_is_not_an_allocation_arm():
    doc = _doc()
    assert "tier 를 allocation arm 으로 올리지 않는다" in doc
    assert "4/4/4" in doc or "tier30 4" in doc


def test_mapping_contract_forbids_silent_mask_shrinking():
    doc = _doc()
    assert "조용히 줄이는 것을 특히 금지" in doc
    for phrase in ("연속 부분열", "모호한 대응", "사슬이 둘 이상",
                   "아미노산 불일치", "범위 밖"):
        assert phrase in doc, f"hard fail 조건 {phrase} 가 없다"


def test_v1_is_retained_not_demoted():
    doc = _doc()
    assert "강등하지 않는다" in doc
    assert "unmasked" in doc and "three-tier conservation-masked" in doc


def test_ligand_claim_is_bounded():
    doc = _doc()
    assert "supported by the pipeline" in doc
    assert "was prospectively validated" in doc  # 금지 문구로 명시돼 있어야 한다


def test_rfd3_protocol_is_explicitly_unchanged():
    """backbone 재사용이 가능하려면 RFD3 쪽이 그대로여야 한다."""
    doc = _doc()
    for phrase in ("select_fixed_atoms 변경", "altLoc 전처리 변경",
                   "기존 51 backbone 재생성"):
        assert phrase in doc, f"'{phrase}' 가 금지 목록에 없다"


# ---- 검토에서 고친 세 가지 -------------------------------------------------

def test_confirmatory_candidate_count_supports_the_budget_grid():
    """후보 수가 budget grid 를 감당해야 한다.

    12/backbone 이면 타겟당 5×12=60 이라 B=80/100/120 이 존재할 수 없다.
    이 불일치가 검토에서 잡혔다.
    """
    doc = _doc()
    assert "24 candidates = 1,440 evaluations" in doc
    assert "8 / 8 / 8" in doc
    # grid 최대값과 타겟당 후보 수가 맞는지
    assert "5 × 24 = 120" in doc, "후보 수와 budget grid 의 관계가 적혀 있지 않다"
    assert "120" in doc


def test_tier_evaluation_order_is_frozen_for_prefix_balance():
    """예산이 앞에서 자르므로 prefix 도 균형이어야 한다."""
    doc = _doc()
    assert "prefix 도 균형" in doc
    assert "30 → 50 → 70" in doc
    assert "design index" in doc, "tier 안 후보 순서 동결이 없다"


def test_calibration_forbids_reserve_substitution():
    """예비 타겟에는 backbone 이 없다. §5 와 충돌하면 안 된다."""
    doc = _doc()
    assert "calibration-infeasible" in doc
    assert "예비 대체 금지" in doc
    assert "기존 51 backbone 만" in doc, "금지 근거가 적혀 있지 않다"
    # confirmatory 쪽은 반대로 허용돼야 한다
    assert "동결된 순서로 예비 교체 가능" in doc


def test_calibration_and_confirmatory_counts_are_consistent():
    """문서 안의 숫자가 서로 맞는가."""
    doc = _doc()
    assert "51 × 12 = 612" in doc or "51 backbone" in doc
    assert "12 targets × 5 RFD3 backbones × 24 candidates" in doc
    assert "1,440" in doc
