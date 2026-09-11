"""docs/results_of_record.md 의 수치가 산출물과 어긋나면 실패한다.

초록에 옛 AUC 0.756 이 들어간 적이 있다. 설계 문서에 남아 있던 기대치였고
측정값은 0.7247 이었다. 인용할 수치를 한 파일로 모았지만, 그 파일도 손으로
쓴 이상 똑같이 낡는다. 그래서 여기서 지킨다.

수치의 출처는 산출물 JSON 이다. 이 테스트는 문서에 세 번째 사본을 만들지
않는다 - 산출물에서 값을 읽어 그 문자열이 문서 안에 있는지만 본다. 재계산으로
값이 바뀌면 테스트가 깨지고, 문서를 고쳐야 통과한다.

**어디에 어떤 부호로 있는지까지 본다 (2026-09-11).** 예전 판본은 "문서 어딘가"
에 있으면 통과했다. 0.7247 은 문서에 두 번 나온다 - 인용 표에 한 번, "왜 이
파일이 있는가" 설명에 한 번 - 그리고 인용되는 것은 표다. 그래서 표의 칸만
고치면 이 파일은 통과했고 전체 파일 digest 하나만 실패했다. 짐작이 아니라
red/green 으로 잰 사실이다:

    0.7247 -> 0.7999, 첫 번째 한 곳만  -> CLAIMS 통과, digest 만 실패
    0.7247 -> 0.7999, 두 곳 모두       -> CLAIMS 실패

그래서 이제 **절 → 표의 행 → 부호**까지 좁혀 대조한다. 행 키가 없는 (산문에만
있는) claim 은 절 단위로 남기고 `row=None` 으로 그 사실을 드러낸다.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Callable, NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "results_of_record.md"
MANUSCRIPT = ROOT / "docs" / "manuscript.md"
BASE = ROOT / "public_data" / "benchmark" / "gate0"
FREEZE = BASE / "RAPID_STRUCTURAL_V1_FREEZE.json"

VARIANCE = "holdout_grid/variance_decomposition_grid.json"
PRIMARY = "rfd3_only_primary"
TEMPERATURE = "temperature_panel2/af2_analysis_order_complete.json"
ALLOCATION = "holdout_grid/prospective_allocation_validation_joint.json"


def _dig(obj, path):
    """점으로 끊은 경로. 키 자체에 점이 있으면 튜플로 준다.

    `per_temperature` 의 키 `"0.1"` 과 `comparisons` 의 키
    `"structural_yield@T0.05"` 가 그 경우다. 예전 판본은 경로에 `".1."` 이
    있는지 보고 한 군데만 손으로 우회했는데, 튜플 경로가 그 우회를 대신한다 -
    같은 문제를 한 번 더 만나도 새 우회를 넣을 필요가 없다.
    """
    parts = path.split(".") if isinstance(path, str) else path
    for part in parts:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


class Claim(NamedTuple):
    """인용된 수치 하나. `row` 가 None 이면 그 값은 표가 아니라 산문에 있다."""

    label: str
    heading: str
    row: str | None
    artifact: str
    path: object
    places: int
    percent: bool = False


#: v1 인용 표 세 개의 모든 칸. 등기부의 규칙이 "이 표에 없는 수치는 원고에
#: 넣지 않는다" 이므로, 표의 칸 하나하나가 인용면이고 전부 산출물에 묶는다.
CLAIMS = [
    # --- Gate 0 · 타겟 수준 라우팅 -----------------------------------------
    Claim("Gate 0 인코더 AUC", "Gate 0 · 타겟 수준 라우팅",
          "out-of-fold AUC (ProteinMPNN 인코더)",
          "gate0_target_level.json", "arms.C_raw_mpnn_encoder.auc", 4),
    Claim("Gate 0 인코더 AUC CI 하한", "Gate 0 · 타겟 수준 라우팅",
          "out-of-fold AUC (ProteinMPNN 인코더)",
          "gate0_target_level.json", "arms.C_raw_mpnn_encoder.auc_ci95.0", 4),
    Claim("Gate 0 인코더 AUC CI 상한", "Gate 0 · 타겟 수준 라우팅",
          "out-of-fold AUC (ProteinMPNN 인코더)",
          "gate0_target_level.json", "arms.C_raw_mpnn_encoder.auc_ci95.1", 4),
    Claim("Gate 0 기술자 AUC", "Gate 0 · 타겟 수준 라우팅", "구조 기술자 기준선",
          "gate0_target_level.json", "arms.B_structural_descriptors.auc", 4),
    Claim("Gate 0 기술자 AUC CI 하한", "Gate 0 · 타겟 수준 라우팅", "구조 기술자 기준선",
          "gate0_target_level.json", "arms.B_structural_descriptors.auc_ci95.0", 4),
    Claim("Gate 0 기술자 AUC CI 상한", "Gate 0 · 타겟 수준 라우팅", "구조 기술자 기준선",
          "gate0_target_level.json", "arms.B_structural_descriptors.auc_ci95.1", 4),
    Claim("Gate 0 전역평균 AUC", "Gate 0 · 타겟 수준 라우팅", "전역 평균 기준선",
          "gate0_target_level.json", "arms.A_global_mean.auc", 4),
    Claim("Gate 0 전역평균 AUC CI 하한", "Gate 0 · 타겟 수준 라우팅", "전역 평균 기준선",
          "gate0_target_level.json", "arms.A_global_mean.auc_ci95.0", 4),
    Claim("Gate 0 전역평균 AUC CI 상한", "Gate 0 · 타겟 수준 라우팅", "전역 평균 기준선",
          "gate0_target_level.json", "arms.A_global_mean.auc_ci95.1", 4),
    # 행 키에 U+2212 가 들어 있다. _table_row 가 키도 정규화한다.
    Claim("Gate 0 짝지음 차이", "Gate 0 · 타겟 수준 라우팅", "인코더 − 기술자 (짝지음)",
          "gate0_target_level.json",
          "paired.C_minus_B_structural_descriptors_auc.mean_difference", 4),
    Claim("Gate 0 짝지음 CI 하한", "Gate 0 · 타겟 수준 라우팅", "인코더 − 기술자 (짝지음)",
          "gate0_target_level.json",
          "paired.C_minus_B_structural_descriptors_auc.ci95.0", 4),
    Claim("Gate 0 짝지음 CI 상한", "Gate 0 · 타겟 수준 라우팅", "인코더 − 기술자 (짝지음)",
          "gate0_target_level.json",
          "paired.C_minus_B_structural_descriptors_auc.ci95.1", 4),
    # --- 분산 분해 · 구조 결과 ---------------------------------------------
    Claim("분산 타겟 수준", "분산 분해 · 구조 결과", "**현행** structural_pass (제곱합)",
          VARIANCE, f"cohorts.{PRIMARY}.sum_of_squares.structural_pass.target_level",
          1, percent=True),
    Claim("분산 백본 수준", "분산 분해 · 구조 결과", "**현행** structural_pass (제곱합)",
          VARIANCE,
          f"cohorts.{PRIMARY}.sum_of_squares.structural_pass.backbone_within_target",
          1, percent=True),
    Claim("분산 서열 수준", "분산 분해 · 구조 결과", "**현행** structural_pass (제곱합)",
          VARIANCE,
          f"cohorts.{PRIMARY}.sum_of_squares.structural_pass.sequence_within_backbone",
          1, percent=True),
    Claim("혼합모형 pLDDT 타겟", "분산 분해 · 구조 결과", "현행 pLDDT (혼합모형)",
          VARIANCE, f"cohorts.{PRIMARY}.mixed_model.plddt.percent.target", 1,
          percent=True),
    Claim("혼합모형 pLDDT 백본", "분산 분해 · 구조 결과", "현행 pLDDT (혼합모형)",
          VARIANCE,
          f"cohorts.{PRIMARY}.mixed_model.plddt.percent.backbone_within_target", 1,
          percent=True),
    Claim("혼합모형 pLDDT 서열", "분산 분해 · 구조 결과", "현행 pLDDT (혼합모형)",
          VARIANCE,
          f"cohorts.{PRIMARY}.mixed_model.plddt.percent.residual_sequence", 1,
          percent=True),
    Claim("혼합모형 RMSD 타겟", "분산 분해 · 구조 결과", "현행 RMSD (혼합모형)",
          VARIANCE,
          f"cohorts.{PRIMARY}.mixed_model.rmsd_nonloop_order.percent.target", 1,
          percent=True),
    Claim("혼합모형 RMSD 백본", "분산 분해 · 구조 결과", "현행 RMSD (혼합모형)",
          VARIANCE,
          f"cohorts.{PRIMARY}.mixed_model.rmsd_nonloop_order.percent."
          f"backbone_within_target", 1, percent=True),
    Claim("혼합모형 RMSD 서열", "분산 분해 · 구조 결과", "현행 RMSD (혼합모형)",
          VARIANCE,
          f"cohorts.{PRIMARY}.mixed_model.rmsd_nonloop_order.percent."
          f"residual_sequence", 1, percent=True),
    Claim("대체된 옛 분해 타겟 (부록용)", "분산 분해 · 구조 결과",
          "_보조(consistency)_ structural_pass",
          "variance_decomposition_structural.json", "components.target_level", 1,
          percent=True),
    Claim("대체된 옛 분해 백본 (부록용)", "분산 분해 · 구조 결과",
          "_보조(consistency)_ structural_pass",
          "variance_decomposition_structural.json",
          "components.backbone_within_target", 1, percent=True),
    Claim("대체된 옛 분해 서열 (부록용)", "분산 분해 · 구조 결과",
          "_보조(consistency)_ structural_pass",
          "variance_decomposition_structural.json",
          "components.sequence_within_backbone", 1, percent=True),
    # 이 둘은 표가 아니라 본문 진술이다 (주 결과 문장과 "표현:" 예문). 행 키가
    # 없으므로 절 단위로 남긴다 - 없는 키를 발명하지 않는다.
    Claim("타겟+백본 귀속 (산문)", "분산 분해 · 구조 결과", None,
          VARIANCE,
          f"cohorts.{PRIMARY}.sum_of_squares.structural_pass."
          f"attributed_to_target_and_backbone", 1, percent=True),
    Claim("보조 코호트 귀속 (산문)", "분산 분해 · 구조 결과", None,
          "variance_decomposition_structural.json",
          "attributed_to_target_and_backbone", 1, percent=True),
    # --- 생성 조건 · 온도 ---------------------------------------------------
    Claim("T=0.1 structural yield", "생성 조건 · 온도", "T=0.1 structural yield",
          TEMPERATURE, ("per_temperature", "0.1", "structural_yield"), 4),
    Claim("T=0.05 대비", "생성 조건 · 온도", "T=0.05 대비",
          TEMPERATURE, ("comparisons", "structural_yield@T0.05", "point"), 4),
    Claim("T=0.2 대비", "생성 조건 · 온도", "T=0.2 대비",
          TEMPERATURE, ("comparisons", "structural_yield@T0.2", "point"), 4),
    Claim("T=0.3 대비", "생성 조건 · 온도", "T=0.3 대비",
          TEMPERATURE, ("comparisons", "structural_yield@T0.3", "point"), 4),
]

BUDGET_HEADING = "전향 배분 검증 · 미지 타겟"

#: 1 차 표의 예산 상한 행. 문서의 행 키가 곧 산출물의 키다.
BUDGET_CAPS = ["20", "24", "40", "60", "80", "100", "120"]

#: (열 이름, 행에서 값을 뽑는 함수, 문서에 적힌 소수 자릿수)
#:
#: "최적 정적" 열은 사후에 고른 k 의 값이므로 `posthoc_best_static_k` 를 거쳐
#: 뽑는다. 어느 k 였는지를 테스트에 적어두면 그것이 네 번째 사본이 된다.
BUDGET_COLUMNS: list[tuple[str, Callable[[dict], float], int]] = [
    ("적응", lambda row: row["adaptive"]["mean_found"], 2),
    ("적응이 실제로 쓴 호출", lambda row: row["adaptive_spent_mean"], 1),
    ("최적 정적 (사후 k)",
     lambda row: row[f"static_k{row['posthoc_best_static_k']}"]["mean_found"], 2),
    ("oracle", lambda row: row["oracle"]["mean_found"], 2),
    ("차이 점추정", lambda row: row["primary_comparison"]["mean"], 2),
    ("차이 CI 하한", lambda row: row["primary_comparison"]["ci95"][0], 2),
    ("차이 CI 상한", lambda row: row["primary_comparison"]["ci95"][1], 2),
]


def _doc() -> str:
    assert DOC.exists(), f"{DOC} 가 없다"
    return DOC.read_text(encoding="utf-8")


def _normalised_doc() -> str:
    """U+2212 MINUS SIGN 을 ASCII 하이픈으로. 문서는 −, 파이썬은 - 를 쓴다."""
    return _doc().replace("−", "-")


def _section(heading: str, *, until_subsection: bool = False) -> str:
    """`## <heading>` 부터 다음 `## ` 직전까지. 없으면 빈 문자열.

    `until_subsection` 이면 첫 `### ` 에서도 끊는다. 전향 배분 절이 그 경우다 -
    `### 2 차: 실제로 쓴 계산량` 표가 같은 예산 상한을 행 키로 다시 쓰므로,
    끊지 않으면 1 차 claim 이 2 차 행으로 만족될 수 있다.
    """
    lines = _normalised_doc().splitlines()
    out, inside = [], False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = heading in line
            if inside:
                continue
        if inside and until_subsection and line.startswith("### "):
            break
        if inside:
            out.append(line)
    return "\n".join(out)


def _table_row(body: str, key: str) -> str | None:
    """markdown 파이프 표에서 첫 칸이 `key` 인 줄.

    절까지만 좁히면 한 절 안에 같은 수가 두 번 있을 때 엉뚱한 줄을 고쳐도
    통과한다. 인용되는 것은 표의 그 칸이므로 그 줄까지 좁힌다.
    """
    want = key.replace("−", "-").strip()
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == want:
            return line
    return None


def _shown(value: float, places: int, percent: bool = False) -> str:
    """문서에 적혀야 하는 형태 (부호 포함). 실패 메시지용."""
    scaled = float(value) * 100 if percent else float(value)
    return f"{round(scaled, places):+.{places}f}" + ("%" if percent else "")


def _cited(body: str, value: float, places: int, *, percent: bool = False) -> bool:
    """산출물 값이 `body` 안에 **부호까지 같게** 인용돼 있는가.

    부호를 abs() 로 지우면 안 된다. 상한 120 의 차이 -0.24 는 스펙이 일부러
    남긴 불리한 포화 결과이고 (`test_primary_endpoint_is_not_redefined` 가
    문서에 남아 있는지도 따로 본다), abs() 는 그것이 +0.24 로 뒤집혀도
    통과시킨다. 부호는 주장의 일부다. 문서의 U+2212 는 `_normalised_doc` 에서
    이미 ASCII 하이픈이 됐으므로 여기서는 정규화를 가정한다.

    앞뒤 경계도 본다. 앞에 숫자·부호가 붙어 있으면 다른 수의 일부다 - 전향
    배분 절에는 `+6.44` 와 `-6.44` 가 실제로 함께 있어서, 단순 부분문자열
    검사는 양수 claim 을 음수 값으로 만족시킨다.
    """
    scaled = float(value) * 100 if percent else float(value)
    rounded = round(scaled, places)
    mag = f"{abs(rounded):.{places}f}" + ("%" if percent else "")
    if rounded > 0:
        sign = r"\+?"      # 문서는 양수에 + 를 붙이기도 하고 생략하기도 한다
    elif rounded < 0:
        sign = r"-"        # 음수는 반드시 부호가 있어야 한다
    else:
        sign = r"[-+]?"
    return re.search(rf"(?<![-+\d.]){sign}{re.escape(mag)}(?![\d.])", body) is not None


def _scope(heading: str, row: str | None, *, until_subsection: bool = False) -> str:
    """claim 하나를 대조할 범위. 행 키가 있으면 그 줄, 없으면 절 전체."""
    body = _section(heading, until_subsection=until_subsection)
    assert body, f"'{heading}' 절을 찾지 못했다"
    if row is None:
        return body
    line = _table_row(body, row)
    assert line is not None, (
        f"'{heading}' 절에 첫 칸이 {row!r} 인 표 행이 없다. 행 이름을 바꿨으면 "
        f"이 테스트의 행 키도 함께 바꾼다 - 인용되는 수치는 주소가 있어야 한다.")
    return line


def _load(name: str):
    path = BASE / name
    if not path.exists():
        pytest.skip(f"산출물 없음: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("claim", CLAIMS, ids=[c.label for c in CLAIMS])
def test_number_matches_artifact(claim: Claim):
    value = _dig(_load(claim.artifact), claim.path)
    body = _scope(claim.heading, claim.row)
    where = f"'{claim.heading}' 절" if claim.row is None else f"{claim.row!r} 행"
    assert _cited(body, value, claim.places, percent=claim.percent), (
        f"{claim.label}: 산출물 값 {_shown(value, claim.places, claim.percent)} 가 "
        f"{where} 에 그 부호로 없다. 재계산으로 값이 바뀌었으면 "
        f"docs/results_of_record.md 를 고친다.\n  범위: {body.strip()[:200]}")


@pytest.mark.parametrize("cap", BUDGET_CAPS)
@pytest.mark.parametrize("column,pick,places", BUDGET_COLUMNS,
                         ids=[c[0] for c in BUDGET_COLUMNS])
def test_prospective_budget_row_matches(cap, column, pick, places):
    """1 차 배분 표의 각 칸을 그 행에서 대조한다 (부호 포함)."""
    row = _load(ALLOCATION)["results_by_budget"][cap]
    value = pick(row)
    line = _scope(BUDGET_HEADING, cap, until_subsection=True)
    assert _cited(line, value, places), (
        f"예산 {cap} · {column}: 산출물 값 {_shown(value, places)} 가 그 행에 "
        f"그 부호로 없다.\n  행: {line.strip()}")


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
#
# **절만으로는 부족했다 (같은 날 확인).** Gate 2 의 planned S6 -0.0313 은 판정
# 표(행 `S6 (판정 arm) Δ_Top4`)와 `### PRIMARY DEVIATION 해소` 표에 각각 한 번,
# 즉 **같은 절 안에 두 번** 나온다. 그래서 판정 표의 칸만 -0.0333 으로 고쳐도
# 절 검사는 통과했다 - CLAIMS 에서 고친 것과 똑같은 구멍이 한 층 아래에 있었다.
# 이제 행 키가 있는 claim 은 그 줄까지 좁힌다.

GATE_CLAIMS = [
    Claim("Gate 1 primary rho", "Gate 1 · 백본 예측 가능성",
          "primary 타겟 등가중 mean within-target Spearman",
          "gate1_backbone_predictability.json", "arms.primary.point", 4),
    Claim("Gate 1 primary LCB", "Gate 1 · 백본 예측 가능성", "primary 단측 90% LCB",
          "gate1_backbone_predictability.json", "arms.primary.one_sided_90_lcb", 4),
    Claim("Gate 1 top-1 regret", "Gate 1 · 백본 예측 가능성",
          "primary top-1 백본 regret (2 차)",
          "gate1_backbone_predictability.json",
          "arms.primary.top1_backbone_regret_mean", 4),
    Claim("Gate 2 planned S6 Delta_Top4", "Gate 2 · 백본 내부 서열 선택성",
          "S6 (판정 arm) Δ_Top4",
          "gate2_within_backbone_selectability.json",
          "arms_joint_pass.S6.delta_top4_target_equal", 4),
    Claim("Gate 2 planned S6 LCB", "Gate 2 · 백본 내부 서열 선택성",
          "S6 단측 90% LCB",
          "gate2_within_backbone_selectability.json",
          "arms_joint_pass.S6.one_sided_90_lcb", 4),
    Claim("Gate 2 RFD3-only sensitivity", "Gate 2 · 백본 내부 서열 선택성",
          "RFD3-only 민감도 (mixed 34 / informative 11)",
          "gate2_within_backbone_selectability.json",
          "arms_joint_pass.S6.sensitivity_rfd3_only.delta_top4_target_equal", 4),
    Claim("Gate 2 RFD3-only sensitivity LCB", "Gate 2 · 백본 내부 서열 선택성",
          "RFD3-only 민감도 (mixed 34 / informative 11)",
          "gate2_within_backbone_selectability.json",
          "arms_joint_pass.S6.sensitivity_rfd3_only.one_sided_90_lcb", 4),
    # 최종 판정 절의 "판정 근거 두 줄". 같은 수치가 게이트 절에서 옮겨 적힌
    # 곳이므로, 두 사본이 같이 움직이는지 여기서 따로 본다.
    Claim("최종 판정 Gate 1 rho", "최종 판정 · Surrogate × RAPID 2축 확장", "Gate 1",
          "gate1_backbone_predictability.json", "arms.primary.point", 4),
    Claim("최종 판정 Gate 1 LCB", "최종 판정 · Surrogate × RAPID 2축 확장", "Gate 1",
          "gate1_backbone_predictability.json", "arms.primary.one_sided_90_lcb", 4),
    Claim("최종 판정 Gate 2 Delta_Top4", "최종 판정 · Surrogate × RAPID 2축 확장",
          "Gate 2", "gate2_within_backbone_selectability.json",
          "arms_joint_pass.S6.delta_top4_target_equal", 4),
    Claim("최종 판정 Gate 2 LCB", "최종 판정 · Surrogate × RAPID 2축 확장", "Gate 2",
          "gate2_within_backbone_selectability.json",
          "arms_joint_pass.S6.one_sided_90_lcb", 4),
]


# `_normalised_doc` 과 `_section` 은 위로 옮겼다 - 이제 CLAIMS·BUDGET_CLAIMS 도
# 같은 것을 쓴다. 절 단위 대조는 여기서 시작했고, 위의 v1 claim 들이 뒤늦게
# 따라온 것이다.


@pytest.mark.parametrize("claim", GATE_CLAIMS, ids=[c.label for c in GATE_CLAIMS])
def test_gate_number_is_in_its_own_section(claim: Claim):
    """절 → 행 → 부호. 절은 겉 범위이고 행이 실제 인용면이다."""
    value = _dig(_load(claim.artifact), claim.path)
    body = _scope(claim.heading, claim.row)
    where = f"'{claim.heading}' 절" if claim.row is None else f"{claim.row!r} 행"
    assert _cited(body, value, claim.places, percent=claim.percent), (
        f"{claim.label}: 산출물 값 {_shown(value, claim.places)} 가 {where} 에 "
        f"그 부호로 없다. 재계산으로 값이 바뀌었으면 "
        f"docs/results_of_record.md 를 고친다.\n  범위: {body.strip()[:200]}")


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
#
#
# ---- 동결 경계를 고친다: 해시를 버리는 것이 아니라 읽는 방식을 바꾼다 ------
#
# 잘못된 경계였다. 이 문서는 설계상 **결과가 쌓이는 인용 등기부**다 - 문서
# 첫머리의 규칙이 "이 표에 없는 수치는 원고에 넣지 않는다. 필요하면 먼저 여기에
# 추가한다" 이다. 그런 파일에 불변 산출물의 전체 파일 SHA256 을 걸면, 옳은
# 내용을 규칙대로 덧붙이는 것만으로 27/27 이 26/27 이 된다. 실제로 Gate 1/2 절을
# 등재한 시점부터 그랬다.
#
# **그렇다고 해시 검사를 먼저 지우면 보호가 실제로 준다.** 지우기 전에 red/green
# 을 돌렸고, 그 시점에는 인용 표의 한 칸을 고치는 것을 잡는 것이 digest 하나뿐
# 이었다 (0.7247 이 문서에 두 번 있었기 때문이다). 그래서 순서가 결론이다 -
# 위의 좁은 가드를 절·행·부호까지 조이고 (그 red/green 은 모듈 docstring 에
# 적어 뒀다), **그 다음에** 이 경계를 좁힌다. digest 는 쓸데없이 엄격한 검사가
# 아니었다. 좁은 가드의 구멍을 우연히 덮고 있었다.
#
# 새 경계. 지키는 것은 그대로고, 요구하지 않는 것 하나만 뺀다:
#
#   지킨다  · 동결 v1 산출물·manifest·코드의 해시 (test_v1_freeze.py 가 본다)
#   지킨다  · 등기부의 v1 수치가 그 동결 산출물과 일치할 것 (위의 CLAIMS ·
#             BUDGET_COLUMNS · GATE_CLAIMS, 절 → 행 → 부호)
#   지킨다  · v1 시점 본문의 **모든 줄**이 지금도 그대로 있을 것. 수정·삭제·
#             재해석은 실패한다.
#   뺀다    · 살아 있는 등기부의 현재 전체 파일 SHA256 이 과거 freeze SHA 와
#             같을 것. 이것만이 등재를 막던 요구다.
#
# manifest 의 digest 는 여전히 필수다. 다만 "현재 파일의 상태" 가 아니라 **v1
# 본문의 좌표**로 쓴다 - v1 본문을 git 에서 되찾아 그것과 대조한다. manifest 를
# 재발행하지 않고 기대 digest 를 새 값으로 바꾸지도 않는다. 그래서 이 검사는
# manifest 를 고칠 권한이 없어도 성립한다.
#
# 본문의 정본은 **태그 `rapid_structural_v1`** 이다. manifest 는 사람이 다시
# 만들 수 있으므로 (`test_v1_immutable.py` 가 정책 코드에 같은 논리를 쓴다)
# manifest 만 믿으면 재발행으로 아래 검사가 조용히 느슨해진다. 태그는 논문이
# 검증한 시점을 가리키고 freeze 스크립트가 다시 쓰지 못한다. 지금 둘은
# 일치하며, 일치 자체를 따로 본다 - 어긋나면 재발행이 있었다는 신호다.

REGISTRY_REL = "docs/results_of_record.md"
V1_TAG = "rapid_structural_v1"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def _recorded_registry_sha() -> str | None:
    """freeze manifest 가 등기부에 적어 둔 SHA256."""
    if not FREEZE.exists():
        return None
    man = json.loads(FREEZE.read_text(encoding="utf-8"))
    for group in ("artifacts", "code"):
        for entry in man.get(group, {}).values():
            if isinstance(entry, dict) and entry.get("path") == REGISTRY_REL:
                return entry.get("sha256")
    return None


def _tagged_registry_blob() -> bytes | None:
    """태그 시점의 등기부 본문."""
    if _git("rev-parse", "--verify", V1_TAG).returncode != 0:
        return None
    got = _git("show", f"{V1_TAG}:{REGISTRY_REL}")
    return got.stdout if got.returncode == 0 else None


def _frozen_registry_snapshot() -> tuple[str, list[str]] | None:
    """v1 시점 본문을 (출처, 줄들) 로 돌려준다.

    태그가 있으면 태그가 정본이다. 태그가 없는 체크아웃(얕은 클론 등)에서는
    기록된 digest 를 좌표로 써서 히스토리에서 찾는다 - 그때도 찾은 blob 을
    다시 해시해 manifest 값과 같을 때만 인정하므로, manifest 를 신뢰하는 것이
    아니라 manifest 와 대조하는 것이다.
    """
    blob = _tagged_registry_blob()
    if blob is not None:
        return V1_TAG, blob.decode("utf-8").splitlines()
    recorded = _recorded_registry_sha()
    if recorded is None:
        return None
    log = _git("log", "--format=%H", "--all", "--", REGISTRY_REL)
    for rev in log.stdout.decode().split():
        got = _git("show", f"{rev}:{REGISTRY_REL}")
        if got.returncode == 0 and hashlib.sha256(got.stdout).hexdigest() == recorded:
            return rev, got.stdout.decode("utf-8").splitlines()
    return None


def test_the_recorded_registry_digest_matches_the_v1_tag():
    """manifest 의 digest 와 태그 시점의 본문이 같은 것을 가리켜야 한다.

    이 검사가 없으면 digest 를 지금 파일로 재발행하는 것만으로 아래의 "v1
    본문이 그대로 있는가" 가 느슨해질 수 있다. 재발행 자체가 금지는 아니지만
    조용히 일어나서는 안 된다 - 재발행하면 이 테스트가 먼저 말한다.
    """
    recorded = _recorded_registry_sha()
    if recorded is None:
        pytest.skip("manifest 에 results_of_record 항목이 없다")
    blob = _tagged_registry_blob()
    if blob is None:
        pytest.skip(f"태그 {V1_TAG} 에 {REGISTRY_REL} 이 없다")
    assert hashlib.sha256(blob).hexdigest() == recorded, (
        f"manifest 의 {REGISTRY_REL} digest 가 태그 {V1_TAG} 의 본문과 다르다.\n"
        f"  manifest = {recorded}\n"
        f"  {V1_TAG}  = {hashlib.sha256(blob).hexdigest()}\n"
        f"manifest 가 재발행됐거나 태그가 움직였다. 둘 다 조용히 일어나서는 안 "
        f"되는 일이다 - 구 digest·신 digest·'v1 수치는 바뀌지 않았다'는 확인을 "
        f"함께 기록해야 한다.")
    # v1 의 가장 오래된 인용값. 이 파일이 존재하는 이유이기도 하다.
    assert "0.7247" in blob.decode("utf-8"), (
        f"태그 {V1_TAG} 의 본문에 v1 정본 AUC 0.7247 이 없다.")


def test_the_frozen_v1_body_is_still_present_verbatim():
    """v1 시점 본문의 모든 줄이 지금도 그대로 있어야 한다. 덧붙이기만 허용한다.

    이것이 전체 파일 digest 를 대신한다. digest 는 "한 바이트도 달라지면 안
    된다" 였고, 그래서 등재를 막았다. 여기서는 "v1 이었던 줄은 한 줄도 달라지면
    안 된다" 만 요구한다 - 절을 끼워 넣는 것은 통과하고, v1 수치를 고치거나
    지우거나 문맥을 바꿔 다시 해석하게 만드는 것은 실패한다.
    """
    found = _frozen_registry_snapshot()
    if found is None:
        pytest.skip(f"v1 본문을 복원할 수 없다 (태그 {V1_TAG} 도 없고 manifest "
                    f"digest 를 가진 커밋도 없다)")
    rev, frozen = found
    current = _doc().splitlines()
    ops = difflib.SequenceMatcher(None, frozen, current, autojunk=False).get_opcodes()
    lost = [(i + 1, frozen[i]) for tag, i1, i2, _, _ in ops
            if tag in ("replace", "delete") for i in range(i1, i2)]
    assert not lost, (
        f"v1 본문의 줄이 {len(lost)} 개 바뀌거나 사라졌다 "
        f"(v1 스냅샷 = {rev if rev == V1_TAG else rev[:12]}). 처음 다섯 개:\n"
        + "\n".join(f"  v1 {n}행: {text}" for n, text in lost[:5])
        + "\n\n덧붙이는 것은 허용된다 - 이 문서는 결과가 쌓이는 등기부다. "
          "허용되지 않는 것은 이미 인용된 v1 줄을 고치거나 지우는 것이다.\n"
          "되돌리는 것이 기본 조치다. 값이 정말로 바뀌었다면 그것은 v1 결과의 "
          "변경이므로 문서 수정이 아니라 동결 재발행 문제다 - "
          "RAPID_STRUCTURAL_V1_FREEZE.json 소유자와 처리한다.")
