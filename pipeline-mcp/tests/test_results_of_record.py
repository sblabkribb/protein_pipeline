"""docs/results_of_record.md 의 수치가 산출물과 어긋나면 실패한다.

초록에 옛 AUC 0.756 이 들어간 적이 있다. 설계 문서에 남아 있던 기대치였고
측정값은 0.7247 이었다. 인용할 수치를 한 파일로 모았지만, 그 파일도 손으로
쓴 이상 똑같이 낡는다. 그래서 여기서 지킨다.

수치의 출처는 산출물 JSON 이다. 이 테스트는 문서에 세 번째 사본을 만들지
않는다 - 산출물에서 값을 읽어 그 문자열이 문서 안에 있는지만 본다. 재계산으로
값이 바뀌면 테스트가 깨지고, 문서를 고쳐야 통과한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "results_of_record.md"
BASE = ROOT / "public_data" / "benchmark" / "gate0"


def _dig(obj, path: str):
    for part in path.split("."):
        obj = obj[part]
    return obj


#: (설명, 산출물, JSON 경로, 소수 자릿수)
CLAIMS = [
    ("Gate 0 인코더 AUC", "gate0_target_level.json", "arms.C_raw_mpnn_encoder.auc", 4),
    ("Gate 0 기술자 AUC", "gate0_target_level.json", "arms.B_structural_descriptors.auc", 4),
    ("Gate 0 전역평균 AUC", "gate0_target_level.json", "arms.A_global_mean.auc", 4),
    ("분산 타겟 수준", "holdout_grid/variance_decomposition_grid.json",
     "cohorts.rfd3_only_primary.sum_of_squares.structural_pass.target_level", 3),
    ("분산 백본 수준", "holdout_grid/variance_decomposition_grid.json",
     "cohorts.rfd3_only_primary.sum_of_squares.structural_pass.backbone_within_target", 3),
    ("분산 서열 수준", "holdout_grid/variance_decomposition_grid.json",
     "cohorts.rfd3_only_primary.sum_of_squares.structural_pass.sequence_within_backbone", 3),
    ("타겟+백본 귀속", "holdout_grid/variance_decomposition_grid.json",
     "cohorts.rfd3_only_primary.sum_of_squares.structural_pass."
     "attributed_to_target_and_backbone", 3),
    ("대체된 옛 분해 (부록용)", "variance_decomposition_structural.json",
     "components.target_level", 3),
    ("T=0.1 structural yield", "temperature_panel2/af2_analysis_order_complete.json",
     "per_temperature.0.1.structural_yield", 4),
]

BUDGET_CLAIMS = [("20", 2), ("24", 2), ("40", 2), ("60", 2), ("80", 2), ("120", 2)]


def _doc() -> str:
    assert DOC.exists(), f"{DOC} 가 없다"
    return DOC.read_text(encoding="utf-8")


def _load(name: str):
    path = BASE / name
    if not path.exists():
        pytest.skip(f"산출물 없음: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("label,artifact,path,places", CLAIMS)
def test_number_matches_artifact(label, artifact, path, places):
    if ".1." in path:  # per_temperature 의 키 "0.1" 은 점을 포함한다
        data = _load(artifact)
        value = data["per_temperature"]["0.1"]["structural_yield"]
    else:
        value = _dig(_load(artifact), path)
    if places == 3:  # 백분율은 문서에 % 로 적혀 있다
        text = f"{value * 100:.1f}%"
    else:
        text = f"{round(float(value), places):.{places}f}"
    assert text in _doc(), (
        f"{label}: 산출물 값 {text} 가 문서에 없다. 재계산으로 값이 바뀌었으면 "
        f"docs/results_of_record.md 를 고친다.")


@pytest.mark.parametrize("budget,places", BUDGET_CLAIMS)
def test_prospective_budget_row_matches(budget, places):
    data = _load("holdout_grid/prospective_allocation_validation_joint.json")
    row = data["results_by_budget"][budget]
    for value in (row["adaptive"]["mean_found"], row["primary_comparison"]["mean"]):
        text = f"{abs(round(float(value), places)):.{places}f}"
        assert text in _doc(), (
            f"예산 {budget}: 값 {text} 가 문서에 없다.")


def test_supersession_is_marked():
    """대체된 값이 현행처럼 보이면 안 된다. 그 혼동이 애초의 실패였다."""
    doc = _doc()
    assert "~~대체됨~~" in doc, "대체된 분해 값에 대체 표시가 없다"
    # 0.756 은 "왜 이 파일이 있는가" 설명에 나온다. 금지 대상은 인용되는 값,
    # 즉 표 안의 숫자다. 본문 전체를 막으면 그 설명을 지워야 통과하게 된다.
    rows = [ln for ln in doc.splitlines() if ln.lstrip().startswith("|")]
    assert not any("0.756" in ln for ln in rows), (
        "옛 AUC 0.756 이 인용 표에 들어왔다")


def test_panel2_not_used_for_policy_claims():
    """패널 2 는 개발 패널이다. 정책 성능 수치를 여기서 인용하면 안 된다."""
    data = _load("temperature_panel2/af2_analysis_order_complete.json")
    assert data.get("valid_for_policy_performance_claims") is False
    assert "개발 패널" in _doc()
