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
MANUSCRIPT = ROOT / "docs" / "manuscript.md"
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
    """보조 결과가 주 결과처럼 보이면 안 된다. 그 혼동이 애초의 실패였다."""
    doc = _doc()
    assert "_보조(consistency)_" in doc, "온도 패널 분해 값에 보조 표시가 없다"
    assert "두 값을 독립 반복으로 제시하면 안 된다" in doc, (
        "선별된 코호트를 독립 반복으로 읽지 말라는 경고가 없다")
    assert "타겟 12 개라는 한계는 유지된다" in doc, "12 타겟 한계가 빠졌다"
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


def test_primary_endpoint_is_not_redefined():
    """1 차 endpoint 는 사후에 바뀌지 않는다. 실현 계산량은 2 차로 따로 둔다."""
    rc = _load("holdout_grid/realized_compute_analysis.json")
    assert rc["relationship_to_primary"]["primary_unchanged"] is True
    doc = _doc()
    assert "### 2 차: 실제로 쓴 계산량" in doc, "2 차 분석이 1 차와 분리돼 있지 않다"
    # 상한 120 의 1 차 값은 불리하더라도 그대로 실려 있어야 한다.
    assert "-0.24" in doc, "상한 120 의 1 차 값 -0.24 가 문서에서 빠졌다"


def test_ligand_is_not_a_performance_claim():
    """배선 점검을 성능 검증으로 인용하면 안 된다."""
    doc = _doc()
    assert "**성능 검증이 아니다.**" in doc
    data = _load("ligand_pocket/self_docking.json")
    # 사본별 채점이 적용돼 있어야 두 지표가 같은 자리를 가리킨다.
    ok = [x for x in data["results"] if x["status"] == "ok"]
    assert ok and all("n_crystal_copies" in x or "n_copies" in x for x in ok), (
        "사본 정보가 없다 - 사본을 합쳐 채점하던 판본일 수 있다")


def test_stability_stays_annotation_only():
    """pooled 상관을 랭킹 근거로 승격하지 않는다."""
    doc = _doc()
    assert "annotation 과 tie-break 로만" in doc
    assert "SPURS 를 중재자로 추가하지 않는다" in doc


# ---- 원고 ---------------------------------------------------------------
# 원고가 인용하는 전향 수치도 산출물에 묶는다. 초록에 옛 AUC 0.756 이 들어간 것도
# 원고였다. 여기서도 세 번째 사본을 만들지 않고 산출물에서 읽어 대조한다.

def _manuscript() -> str:
    if not MANUSCRIPT.exists():
        pytest.skip(f"원고 없음: {MANUSCRIPT}")
    return MANUSCRIPT.read_text(encoding="utf-8")


def test_manuscript_variance_matches_artifact():
    c = _load("holdout_grid/variance_decomposition_grid.json")["cohorts"]["rfd3_only_primary"]
    ss = c["sum_of_squares"]["structural_pass"]
    doc = _manuscript()
    for key in ("target_level", "backbone_within_target", "sequence_within_backbone",
                "attributed_to_target_and_backbone"):
        text = f"{ss[key] * 100:.1f}%"
        assert text in doc, f"원고에 {key}={text} 가 없다"


@pytest.mark.parametrize("cap", ["24", "40", "60", "80", "120"])
def test_manuscript_allocation_matches_artifact(cap):
    pc = _load("holdout_grid/prospective_allocation_validation_joint.json")[
        "results_by_budget"][cap]["primary_comparison"]
    doc = _manuscript()
    assert f"{abs(pc['mean']):.2f}" in doc, f"상한 {cap} 의 차이가 원고에 없다"
    assert f"{abs(pc['ci95'][0]):.2f}" in doc, f"상한 {cap} 의 CI 하한이 원고에 없다"


def test_manuscript_reports_the_unfavourable_saturation_result():
    """상한 120 의 1 차 값은 불리해도 원고에 남아 있어야 한다."""
    doc = _manuscript()
    assert "-0.24" in doc, "상한 120 의 1 차 결과가 원고에서 빠졌다"
    rc = _load("holdout_grid/realized_compute_analysis.json")["by_cap"]["120"]
    assert f"{rc['adaptive_spent']['mean']:.1f}" in doc, (
        "실제로 쓴 호출 수가 함께 적혀 있지 않다 - 두 값은 같이 읽어야 한다")


def test_manuscript_states_the_scope_limits():
    doc = _manuscript()
    for phrase, why in (
        ("twelve targets", "12 타겟 한계"),
        ("single ProteinMPNN temperature", "단일 조건 한계"),
        ("exact replay", "재생이지 온라인 실행이 아니라는 것"),
        ("annotation and tie-break only", "ThermoMPNN 를 랭킹에 쓰지 않는다는 것"),
        ("not a binding-performance claim", "리간드가 성능 주장이 아니라는 것"),
    ):
        assert phrase in doc, f"원고에 {why} 진술이 없다 ({phrase!r})"


# --- 2 축 게이트 (2026-09-11) -------------------------------------------------
#
# 아래는 값이 문서 "어딘가" 에 있는지가 아니라 **해당 Gate 절 안에** 있는지를 본다.
# 전역 검색이면 다른 절의 우연한 같은 숫자가 통과시킨다 - 게이트 두 개가 같은
# 지표군을 쓰므로 실제로 일어날 수 있다.

#: (설명, 절 제목, 산출물, JSON 경로, 소수 자릿수)
GATE_CLAIMS = [
    ("Gate 1 primary rho", "Gate 1 · 백본 예측 가능성",
     "gate1_backbone_predictability.json", "arms.primary.point", 4),
    ("Gate 1 primary LCB", "Gate 1 · 백본 예측 가능성",
     "gate1_backbone_predictability.json", "arms.primary.one_sided_90_lcb", 4),
    ("Gate 1 top-1 regret", "Gate 1 · 백본 예측 가능성",
     "gate1_backbone_predictability.json", "arms.primary.top1_backbone_regret_mean", 4),
    ("Gate 2 planned S6 Delta_Top4", "Gate 2 · 백본 내부 서열 선택성",
     "gate2_within_backbone_selectability.json",
     "arms_joint_pass.S6.delta_top4_target_equal", 4),
    ("Gate 2 planned S6 LCB", "Gate 2 · 백본 내부 서열 선택성",
     "gate2_within_backbone_selectability.json",
     "arms_joint_pass.S6.one_sided_90_lcb", 4),
    ("Gate 2 RFD3-only sensitivity", "Gate 2 · 백본 내부 서열 선택성",
     "gate2_within_backbone_selectability.json",
     "arms_joint_pass.S6.sensitivity_rfd3_only.delta_top4_target_equal", 4),
    ("Gate 2 RFD3-only sensitivity LCB", "Gate 2 · 백본 내부 서열 선택성",
     "gate2_within_backbone_selectability.json",
     "arms_joint_pass.S6.sensitivity_rfd3_only.one_sided_90_lcb", 4),
]


def _normalised_doc() -> str:
    """U+2212 MINUS SIGN 을 ASCII 하이픈으로. 문서는 −, 파이썬은 - 를 쓴다."""
    return _doc().replace("−", "-")


def _section(heading: str) -> str:
    """`## <heading>` 부터 다음 `## ` 직전까지. 없으면 빈 문자열."""
    lines = _normalised_doc().splitlines()
    out, inside = [], False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = heading in line
            if inside:
                continue
        if inside:
            out.append(line)
    return "\n".join(out)


@pytest.mark.parametrize("label,heading,artifact,path,places", GATE_CLAIMS)
def test_gate_number_is_in_its_own_section(label, heading, artifact, path, places):
    value = _dig(_load(artifact), path)
    body = _section(heading)
    assert body, f"{label}: '{heading}' 절을 찾지 못했다"
    rounded = round(float(value), places)
    # 문서는 양수에 + 를 붙이고 음수는 − 를 쓴다. 둘 다 허용하되 값은 정확해야 한다.
    forms = {f"{rounded:+.{places}f}", f"{rounded:.{places}f}"}
    assert any(f in body for f in forms), (
        f"{label}: 산출물 값 {sorted(forms)} 중 어느 것도 '{heading}' 절에 없다. "
        f"재계산으로 값이 바뀌었으면 docs/results_of_record.md 를 고친다.")


def test_both_gate_verdicts_are_recorded_as_final():
    for artifact in ("gate1_backbone_predictability.json",
                     "gate2_within_backbone_selectability.json"):
        assert _load(artifact)["verdict"] == "NO-GO", f"{artifact} 판정이 NO-GO 가 아니다"
    doc = _normalised_doc()
    assert "NO-GO [FINAL]" in doc, "두 게이트의 최종 판정 표시가 문서에 없다"


def test_realized_s6_is_kept_but_marked_superseded():
    """정본은 planned S6 다. realized 판은 provenance 로만 남는다.

    지우면 왜 -0.0366 이 중간에 있었는지 설명할 수 없고, 정본처럼 두면 이 파일이
    존재하는 이유였던 그 혼동이 재발한다.
    """
    body = _section("Gate 2 · 백본 내부 서열 선택성")
    assert "-0.0313" in body, "정본 planned S6 값이 없다"
    assert "-0.0366" in body, "superseded realized S6 값이 지워졌다 - provenance 손실"
    assert "realized S6" in body and "planned S6" in body, "둘을 구분하는 표기가 없다"
    assert "MPNN score 없음" in body, "realized 판이 왜 다른지가 적혀 있지 않다"


def test_gate1_interpretation_limits_travel_with_the_numbers():
    """수치만 복사되는 것을 막는다. 금지 문장이 같은 절에 있어야 한다."""
    body = _section("Gate 1 · 백본 예측 가능성")
    assert "이 표본에서 미검출" in body, "NO-GO 를 '신호 없음' 으로 읽지 말라는 단서가 없다"
    assert "n/p = 0.21" in body, "80 백본 / 384 차원 한계가 빠졌다"
    assert "존재하지 않는다" in body, "금지 문장 목록이 빠졌다"


def test_stop_is_scoped_to_the_surrogate_axis_not_rapid():
    """STOP 이 RAPID 자체를 접는 것으로 읽히면 안 된다."""
    body = _section("최종 판정 · Surrogate × RAPID 2축 확장")
    assert body, "최종 판정 절을 찾지 못했다"
    assert "RAPID 자체를 접는다는 뜻이 아니다" in body, "STOP 의 범위 제한이 없다"
    assert "RAPID v2" in body and "별개" in body, "v2 전향 검증이 별개라는 표시가 없다"


# ---- 이 문서에는 가드가 둘이고, 서로를 몰랐다 ------------------------------
#
# 이 파일은 "인용된 수치가 산출물과 맞는가" 를 본다. `test_v1_freeze.py` 는 같은
# 문서의 **전체 해시**를 본다. 문서를 고친 사람이 자연스럽게 돌리는 것은 이
# 파일이고, 이 파일은 해시 파손을 볼 수 없다. 실제로 다섯 커밋 동안 빨간 상태가
# 유지됐고 아무도 몰랐다 - 최초 파손은 8ede362 다.
#
# 그래서 여기서 교차 확인한다. 중복 검사가 아니라 **가시성**이다.

def test_this_document_still_matches_its_v1_freeze_digest():
    import hashlib
    import json as _json

    manifest = (ROOT / "public_data" / "benchmark" / "gate0"
                / "RAPID_STRUCTURAL_V1_FREEZE.json")
    if not manifest.exists():
        pytest.skip("v1 freeze manifest 없음")
    man = _json.loads(manifest.read_text(encoding="utf-8"))

    recorded, key = None, None
    def walk(o, path=""):
        nonlocal recorded, key
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and len(v) == 64 and "results_of_record" in f"{path}/{k}":
                    recorded, key = v, f"{path}/{k}"
                elif isinstance(v, (dict, list)):
                    walk(v, f"{path}/{k}")
    walk(man)
    if recorded is None:
        pytest.skip("manifest 에 results_of_record 항목이 없다")

    actual = hashlib.sha256(MANUSCRIPT.parent.joinpath("results_of_record.md").read_bytes()).hexdigest()
    assert actual == recorded, (
        f"docs/results_of_record.md 가 v1 freeze 해시와 다르다.\n"
        f"  manifest {key} = {recorded}\n"
        f"  현재            = {actual}\n"
        f"이 파일은 v1 freeze manifest 의 27 개 중 하나다. 내용이 옳더라도 "
        f"편집하면 `42_freeze_v1_results.py --verify` 가 27/27 을 잃는다.\n"
        f"최초 파손은 8ede362 이고, 정당화할 diff 범위는 00a6931..HEAD 다 "
        f"(마지막 커밋 하나가 아니다).\n"
        f"고치는 방법은 둘뿐이다 - 되돌리거나, manifest 를 의도적으로 재발행하고 "
        f"구 digest·신 digest·'v1 수치는 바뀌지 않았다'는 확인을 함께 기록하는 것.")
