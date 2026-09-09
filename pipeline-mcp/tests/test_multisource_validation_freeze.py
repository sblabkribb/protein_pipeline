"""v2.0 multi-source validation 동결의 숫자와 provenance.

이 파일이 지키는 것은 두 가지다.

1. **숫자가 문서·plan JSON·선정 코드에서 같은가.** 세 곳에 흩어진 상수가
   어긋나면 8,640 이라는 총량이 어디서 왔는지 아무도 재구성할 수 없다.
2. **이전 동결이 지워지지 않고 supersede 되었는가.** 새 freeze 가 이전 문서를
   덮어쓰면 "그때는 무엇을 약속했는가" 를 검증할 수 없다.

특히 `test_budget_grid_fits_the_ten_backbone_ceiling` 이 중요하다. 예산 격자와
후보 수가 어긋난 전례가 이미 한 번 있었다 (backbone 당 12 개로는 B=80 이 존재할
수 없었다). 같은 실수를 10-backbone 설계에서 반복하지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "public_data" / "benchmark" / "gate0"
PLAN = BASE / "multisource_validation_plan.json"
FREEZE = ROOT / "docs" / "specs" / "rapid-v2-multisource-validation-freeze.md"
SELECTOR = ROOT / "scripts" / "transcoder" / "46_select_calibration_targets.py"


def _plan() -> dict:
    if not PLAN.exists():
        pytest.skip("multi-source plan 없음")
    return json.loads(PLAN.read_text(encoding="utf-8"))


def _doc() -> str:
    if not FREEZE.exists():
        pytest.skip("multi-source 동결 문서 없음")
    return FREEZE.read_text(encoding="utf-8")


def _flow(text: str) -> str:
    """줄바꿈과 인용 표시를 지운 한 줄. 문단이 감겨 있어도 문장을 찾을 수 있다."""
    return re.sub(r"\s+", " ", text.replace("\n>", " "))


def _cohorts() -> dict:
    spec = importlib.util.spec_from_file_location("sel46", SELECTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.COHORTS


# ---- 숫자 교차 검산 ---------------------------------------------------------

def test_totals_are_arithmetically_consistent():
    """12 x 10 x 12 x 2 = 2880 · 12 x 10 x 24 x 2 = 5760 · 합 8640."""
    p = _plan()
    d = p["per_source_design"]
    n_targets = p["cohorts"]["calibration_v2"]["n_targets"]
    n_sources = len(p["sources"]["ids"])
    t = p["totals"]

    assert n_targets == 12
    assert n_sources == 2
    assert d["backbones_per_target"] == 10

    calib = n_targets * d["backbones_per_target"] * d["calibration_candidates_per_backbone"]
    confirm = n_targets * d["backbones_per_target"] * d["confirmatory_candidates_per_backbone"]

    assert calib == 1440, calib
    assert confirm == 2160, confirm
    assert t["calibration_per_source"] == calib
    assert t["confirmatory_per_source"] == confirm
    assert t["calibration_all_sources"] == calib * n_sources == 2880
    assert t["confirmatory_all_sources"] == confirm * n_sources == 4320
    assert t["grand_total"] == 2880 + 4320 == 7200


def test_warmup_and_ceiling_follow_from_ten_backbones():
    p = _plan()
    d = p["per_source_design"]
    t = p["totals"]
    assert t["warmup_per_target_per_source"] == (
        d["backbones_per_target"] * d["warmup_valid_observations_per_backbone"]) == 40
    assert t["ceiling_per_target_per_source"] == (
        d["backbones_per_target"] * d["confirmatory_candidates_per_backbone"]) == 180


def test_tier_counts_sum_to_the_candidate_counts():
    d = _plan()["per_source_design"]
    assert sum(d["calibration_tier_counts"].values()) == \
        d["calibration_candidates_per_backbone"] == 12
    assert sum(d["confirmatory_tier_counts"].values()) == \
        d["confirmatory_candidates_per_backbone"] == 18
    # 세 tier 가 균형이어야 prefix 도 균형일 수 있다
    assert len(set(d["calibration_tier_counts"].values())) == 1
    assert len(set(d["confirmatory_tier_counts"].values())) == 1
    assert d["tier_prefix_order"] == ["30", "50", "70"]


def test_budget_grid_fits_the_ten_backbone_ceiling():
    """격자가 warm-up 에서 시작하고 ceiling 을 넘지 않아야 한다."""
    p = _plan()
    grid = p["budget_grid"]["primary"]
    warmup = p["totals"]["warmup_per_target_per_source"]
    ceiling = p["totals"]["ceiling_per_target_per_source"]

    assert grid == sorted(grid), "격자가 정렬돼 있지 않다"
    assert len(set(grid)) == len(grid), "격자에 중복이 있다"
    assert min(grid) == warmup, f"최소 격자점 {min(grid)} != warm-up {warmup}"
    assert max(grid) == ceiling, f"최대 격자점 {max(grid)} != ceiling {ceiling}"
    for b in grid:
        assert warmup <= b <= ceiling


def test_both_grid_endpoints_are_anchors_not_judgement_points():
    """격자 양 끝은 구조적 앵커다. 어느 쪽의 null 도 '효과 없음' 이 아니다.

    아래쪽은 의무 probe 가 예산을 다 쓰기 때문이고, 위쪽은 unit 당 상한이
    모든 배분을 같게 강제하기 때문이다. v1 이 두 끝점을 primary 로 보고했다
    (-0.08 · -0.24). 같은 일을 반복하지 않는다.
    """
    p = _plan()
    g = p["budget_grid"]
    t = p["totals"]
    assert g["anchors"]["warmup"] == t["warmup_per_target_per_source"] == 40
    assert g["anchors"]["ceiling"] == t["ceiling_per_target_per_source"] == 180
    assert g["anchors"]["warmup"] == min(g["primary"])
    assert g["anchors"]["ceiling"] == max(g["primary"])
    assert g["anchors_excluded_from_primary_judgement"] is True
    for why in ("warmup_why", "ceiling_why"):
        assert g["anchors"][why], f"{why} 근거가 비어 있다"


def test_primary_informative_points_exclude_both_anchors():
    p = _plan()
    g = p["budget_grid"]
    inf = g["primary_informative"]
    assert inf == [60, 80, 100, 120, 140, 160], inf
    assert set(inf) <= set(g["primary"])
    assert g["anchors"]["warmup"] not in inf
    assert g["anchors"]["ceiling"] not in inf
    doc = _doc()
    assert "primary informative   60 - 160" in doc
    assert "판정점        B = 60 · 80 · 100 · 120 · 140 · 160" in doc


def test_the_grid_is_derived_from_the_ceiling_not_the_reverse():
    g = _plan()["budget_grid"]
    assert "ceiling 을 먼저 정하고" in g["derived_from"]
    r = g["revised_in_review"]
    assert r["from_candidates_per_backbone"] == 24
    assert r["to_candidates_per_backbone"] == 18
    assert r["never_frozen"] is True, "동결되지 않은 제안을 동결됐다고 적으면 안 된다"
    assert "5x24=120" in r["why"]


def test_candidate_depth_rationale_is_limited_to_three_grounds():
    r = _plan()["candidate_depth_rationale"]
    assert len(r["grounds"]) == 3, r["grounds"]
    joined = " ".join(r["grounds"])
    assert "12" in joined and "18" in joined and "24" in joined
    assert r["evidence_status"].startswith("design planning evidence")
    assert r["efbc_saturation_k"] == 12
    assert r["historical_max_difference_k"] == 16


def test_the_rationale_forbids_v1_policy_logic():
    """v2 CoverageAction 에 abandon 이 없다. 그것을 후보 깊이 근거로 쓰지 않는다."""
    import sys
    sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
    from pipeline_mcp.rapid_core.coverage_policy import CoverageAction
    actions = {a.value for a in CoverageAction}
    assert actions == {"probe_unit", "advance_unit", "stop",
                       "budget_exhausted", "execution_infeasible"}, actions
    assert not any("abandon" in a for a in actions), (
        "v2 action 집합에 abandon 이 생겼다면 §7.1 의 금지 근거를 다시 검토해야 한다")

    forbidden = " ".join(_plan()["candidate_depth_rationale"]["forbidden_grounds"])
    assert "abandon" in forbidden and "movability" in forbidden

    # 문서에서 abandon/movability 는 금지 목록 안에서만 등장해야 한다
    doc = _doc()
    block_start = doc.index("### 근거로 쓰지 않는 것")
    block_end = doc.index("### 7.2")
    for word in ("abandon", "movability"):
        for pos in [i for i in range(len(doc)) if doc.startswith(word, i)]:
            assert block_start < pos < block_end, (
                f"{word!r} 가 금지 목록 밖(offset {pos})에서 쓰였다 - "
                "v1 정책 논리가 v2 근거로 새어 들어갔다")


def test_the_historical_peak_is_not_called_a_requirement():
    """k=16 은 v1 에서 관측된 깊이다. 새 설계의 최적이라고 말하지 않는다."""
    r = _plan()["candidate_depth_rationale"]
    note = r["historical_max_difference_note"]
    assert "최적이라는 뜻이 아니다" in note
    joined = " ".join(r["grounds"]) + " " + " ".join(r["forbidden_grounds"])
    assert "최적 깊이로 간주하는 것" in joined
    doc = _doc()
    assert "정책이 요구하는 깊이" not in doc.replace(
        '"정책이 요구하는 깊이" 로 읽지 않는다', ""), (
        "k=16 을 정책 요구 깊이로 서술한 문장이 남아 있다")
    assert "informative interior depth" in doc


def test_the_superseded_grid_is_recorded_not_deleted():
    g = _plan()["budget_grid"]
    assert g["superseded_grid"], "이전 격자가 기록되지 않았다"
    assert max(g["superseded_grid"]) == 120, "이전 ceiling 은 120 이었다"
    assert max(g["revised_in_review"]["from_grid"]) == 240


def test_warmup_stays_four_for_v1_continuity_and_ess():
    w = _plan()["per_source_design"]["warmup_rationale"]
    assert w["value"] == 4
    grounds = " ".join(w["primary_grounds"])
    assert "v1 continuity" in grounds
    assert "ESS" in grounds or "ESS" in w["ess_note"]
    import sys
    sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
    from pipeline_mcp.rapid_core.profiles.rapid_structural_v1 import V1_MIN_PROBE
    assert w["value"] == V1_MIN_PROBE, "v1 continuity 를 근거로 쓰면서 값이 다르다"


def test_the_warmup_tier_imbalance_is_a_limitation_not_a_cancellation():
    """2/1/1 이 형제 간에 상쇄된다고 주장하지 않는다.

    backbone x tier interaction 이 있으면 순위에도 영향을 줄 수 있고, tier 별
    결과를 보고 확인하는 것은 금지다. 그러므로 한계로만 기록한다.
    """
    w = _plan()["per_source_design"]["warmup_rationale"]
    lim = w["prespecified_limitation"]
    assert "2/1/1" in lim
    assert "backbone x tier interaction" in lim
    assert "상쇄된다고 가정하지 않는다" in lim
    assert "상쇄" in w["not_claimed"] and "하지 않는다" in w["not_claimed"]

    doc = _doc()
    assert "상쇄된다고 가정하지 않는다" in doc
    for claim in ("형제 간에 상쇄되어", "순위는 영향을 받지 않"):
        assert claim not in doc, f"상쇄 주장이 문서에 남아 있다: {claim!r}"


def test_warmup_three_is_a_prespecified_secondary_sensitivity():
    s = _plan()["per_source_design"]["warmup_rationale"]["secondary_sensitivity"]
    assert s["warmup"] == 3
    assert s["prespecified"] is True
    assert s["extra_af2_cost"] == 0, "replay 이므로 폴딩이 늘지 않는다"
    banned = " ".join(s["not_used_for"])
    for x in ("primary policy", "GO/NO-GO", "kappa"):
        assert x in banned, f"{x} 금지가 없다"
    doc = _doc()
    assert "사전 등록된 secondary sensitivity" in doc
    assert "primary 는 warm-up 4 다" in doc


def test_the_tier_prefix_for_warmup_four_is_actually_two_one_one():
    """한계 문구가 실제 prefix 와 맞는지 계산해서 확인한다."""
    import collections
    order = _plan()["per_source_design"]["tier_prefix_order"]
    w = _plan()["per_source_design"]["warmup_valid_observations_per_backbone"]
    prefix = [order[i % len(order)] for i in range(w)]
    counts = collections.Counter(prefix)
    assert dict(counts) == {"30": 2, "50": 1, "70": 1}, dict(counts)
    # warm-up 3 은 정확히 균형이라는 secondary 근거도 계산으로 확인한다
    prefix3 = [order[i % len(order)] for i in range(3)]
    assert len(set(collections.Counter(prefix3).values())) == 1


def test_msa_is_one_run_per_target_shared_across_sources():
    p = _plan()
    assert p["msa"]["runs_per_target"] == 1
    assert p["msa"]["shared_across_sources"] is True
    assert p["msa"]["thresholds_unchanged"] is True
    n = p["cohorts"]["calibration_v2"]["n_targets"] + p["cohorts"]["confirmatory"]["n_targets"]
    assert p["totals"]["msa_targets"] == n == 24


def test_af2_cost_estimate_is_marked_as_a_four_point_fit():
    c = _plan()["af2_cost_estimate"]
    assert c["fit_n_points"] == 4
    assert "자릿수" in c["caveat"], "4 점 적합의 한계가 적혀 있지 않다"
    assert "af2_length_scaling.json" in c["fit_source"]
    assert (ROOT / "public_data" / "benchmark" / "gate0"
            / "af2_length_scaling.json").exists()


def test_backbone_generation_count():
    p = _plan()
    n = (p["cohorts"]["calibration_v2"]["n_targets"]
         + p["cohorts"]["confirmatory"]["n_targets"])
    want = n * p["per_source_design"]["backbones_per_target"] * len(p["sources"]["ids"])
    assert p["totals"]["backbones_to_generate"] == want == 480


# ---- source 독립성 ----------------------------------------------------------

def test_sources_are_declared_independent():
    s = _plan()["sources"]
    assert s["ids"] == ["rfd3", "bioemu"]
    for flag in ("independent", "no_shared_allocation_pool",
                 "no_shared_posterior", "no_shared_hyperparameter"):
        assert s[flag] is True, f"{flag} 가 선언되지 않았다"
    for name in ("q_b", "kappa_pool"):
        assert name in s["state_per_source"]


def test_kappa_is_identified_per_source_without_borrowing():
    k = _plan()["kappa_identification"]
    assert k["per_source"] is True
    assert k["grid"] == [0.5, 1, 2, 4, 8, 16, 32]
    assert k["criteria_unchanged"] is True
    assert "phase4b-calibration-freeze" in k["criteria_source"]
    assert k["borrowing_across_sources_forbidden"] is True
    assert "BLOCKED" in k["on_not_identified"]


def test_endpoints_are_never_pooled_across_sources():
    e = _plan()["endpoints"]
    assert e["per_source_independent"] is True
    assert e["primary"] == "EFBC@B"
    assert e["pooling_across_sources_forbidden"] is True
    assert "0.90" in e["guardrail"]
    assert "static/equal" in e["comparator_primary"]
    doc = _doc()
    assert "하나의 p-value" in doc, "합치지 않는다는 금지가 문서에 없다"


def test_cross_source_comparison_is_scale_normalised():
    """EFBC 상한은 unit 수다. u 가 다른 source 를 raw 로 비교할 수 없다."""
    doc = _doc()
    assert "EFBC / u" in doc, "정규화 지표가 사전 지정되지 않았다"
    assert "unit 수에 스케일이 걸린다" in doc


def test_unequal_unit_counts_have_a_preregistered_rule():
    """u < 10 이면 warm-up 4u · ceiling 24u 다. 미리 정해 두지 않으면 사후 선택이 된다."""
    g = _plan()["generation_rules"]
    assert "SOURCE_GENERATION_INFEASIBLE" in g["on_shortfall"]
    assert "타겟을 예비로 바꾸지 않는다" in g["on_shortfall"]
    assert "non-evaluable" in g["unequal_units"]

    # 문자열을 고정하지 않는다. 후보 수가 바뀌면 이 문장도 바뀌어야 하므로
    # 설계 상수에서 기대값을 만들어 대조한다. 24 -> 18 개정에서 이 문장만
    # 24u 로 남아 있었고, 문자열을 고정한 이전 판 테스트는 그것을 통과시켰다.
    d = _plan()["per_source_design"]
    f = g["unequal_units_formula"]
    assert f["warmup_per_unit"] == d["warmup_valid_observations_per_backbone"]
    assert f["ceiling_per_unit"] == d["confirmatory_candidates_per_backbone"]
    assert f["warmup"] == f"{f['warmup_per_unit']}u" in g["unequal_units"]
    assert f["ceiling"] == f"{f['ceiling_per_unit']}u" in g["unequal_units"]

    # 그리고 u = 10 에서 앵커와 일치하는지 - 공식과 총량이 같은 설계인지
    t = _plan()["totals"]
    u = d["backbones_per_target"]
    assert f["warmup_per_unit"] * u == t["warmup_per_target_per_source"]
    assert f["ceiling_per_unit"] * u == t["ceiling_per_target_per_source"]


# ---- 생성 규칙 --------------------------------------------------------------

def test_generation_rules_are_finite_and_frozen():
    g = _plan()["generation_rules"]
    for source in ("rfd3", "bioemu"):
        r = g[source]
        assert r["accepted_needed_per_target"] == 10
        assert "동결된" in r["order"], f"{source}: 순서 동결이 없다"
    assert g["rfd3"]["max_attempts_per_target"] >= 10
    assert g["bioemu"]["max_attempted_structures"] >= 10


def test_bioemu_generation_settings_match_the_pipeline_recommendation():
    """새 숫자를 고른 것이 아니라 파이프라인 권고를 쓴 것인지."""
    import sys
    sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
    from pipeline_mcp.pipeline import (
        _recommended_bioemu_num_samples,
        _recommended_bioemu_max_attempted_structures,
    )
    r = _plan()["generation_rules"]["bioemu"]
    want = r["max_return_structures"]
    assert r["num_samples"] == _recommended_bioemu_num_samples(want, True)
    assert r["max_attempted_structures"] == \
        _recommended_bioemu_max_attempted_structures(want, True)
    assert want == r["accepted_needed_per_target"] == 10


def test_acceptance_cutoffs_are_not_relaxed():
    g = _plan()["generation_rules"]
    assert g["bioemu"]["target_rmsd_cutoff"] == 2.0
    assert "2.0" in str(g["rfd3"]["accept_gate"])
    doc = _doc()
    assert "BioEmu target_rmsd_cutoff 완화" in doc, "완화 금지가 적혀 있지 않다"


def test_historical_source_rates_are_recorded_from_this_repo():
    """설계 근거가 이 저장소의 기록과 같은지."""
    g = _plan()["generation_rules"]
    ladder = json.loads((BASE / "gate0_ladder.json").read_text(encoding="utf-8"))
    assert ladder["n_targets"] == g["bioemu"]["historical_accept_rate"]["targets_attempted"]
    hold = json.loads((BASE / "holdout_targets.json").read_text(encoding="utf-8"))
    why = " ".join(hold["backbone_plan"]["why_not_bioemu"])
    assert "4 타겟" in why
    assert "8 개 실행 중 4 개" in why


# ---- provenance: supersede 는 삭제가 아니다 --------------------------------

def test_every_superseded_document_still_exists_and_points_forward():
    for item in _plan()["supersedes"]:
        path = ROOT / item["path"]
        assert path.exists(), f"{item['path']} 가 사라졌다 - supersede 는 삭제가 아니다"
        assert item["sections"], f"{item['path']}: 대체 절이 비어 있다"
        assert item["retained"], f"{item['path']}: 유지 절이 비어 있다"
        assert not (set(item["sections"]) & set(item["retained"])), \
            f"{item['path']}: 같은 절이 대체와 유지 양쪽에 있다"
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            assert "SUPERSEDED" in text, f"{item['path']}: 배너가 없다"
            assert "rapid-v2-multisource-validation-freeze.md" in text, \
                f"{item['path']}: 대체 문서를 가리키지 않는다"


def test_superseding_commits_are_real():
    for item in _plan()["supersedes"]:
        out = subprocess.run(["git", "cat-file", "-t", item["commit"]],
                             cwd=ROOT, capture_output=True, text=True)
        assert out.stdout.strip() == "commit", \
            f"{item['path']}: commit {item['commit']} 을 확인할 수 없다"


def test_prior_evidence_is_preserved_but_not_an_input():
    p = _plan()["preserved_not_input"]
    assert p["items"], "보존 목록이 비어 있다"
    joined = " ".join(p["items"])
    for keep in ("rapid_structural_v1", "51-backbone", "temperature", "surrogate"):
        assert keep in joined, f"{keep} 가 보존 목록에 없다"
    doc = _doc()
    assert "historical single-source calibration sensitivity" in doc


def test_the_frozen_confirmatory_selection_is_not_reselected():
    p = _plan()["cohorts"]["confirmatory"]
    assert p["reselection_forbidden"] is True
    import hashlib
    holdout = json.loads((BASE / "masked_holdout_targets.json").read_text(encoding="utf-8"))
    live = sorted(t["domain"] for t in holdout["selected"])
    assert live == sorted(p["selected"]), "동결된 타겟 목록과 계획이 다르다"
    digest = hashlib.sha256(json.dumps(live).encode()).hexdigest()
    assert digest == p["selected_sha256"], "타겟 목록이 바뀌었다"


def test_the_confirmatory_target_file_itself_is_untouched():
    """design 블록만 대체된다. 파일은 수정하지 않는다."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--",
         "public_data/benchmark/gate0/masked_holdout_targets.json"],
        cwd=ROOT, capture_output=True, text=True)
    assert not out.stdout.strip(), \
        "masked_holdout_targets.json 이 수정됐다 - 타겟 동결이 무효가 된다"


# ---- 선정 코드와 계획이 같은가 ----------------------------------------------

def test_selector_has_a_matching_calibration_v2_cohort():
    cfg = _cohorts()["calibration_v2"]
    p = _plan()
    c = p["cohorts"]["calibration_v2"]
    d = p["per_source_design"]
    assert cfg["seed"] == c["seed"] == 20260911
    assert cfg["per_stratum"] == c["per_stratum"] == 4
    assert cfg["reserve_per_stratum"] == 2
    assert cfg["backbones_per_target"] == d["backbones_per_target"] == 10
    assert cfg["sequences_per_backbone"] == d["calibration_candidates_per_backbone"] == 12
    assert list(cfg["backbone_sources"]) == p["sources"]["ids"]
    assert cfg["out"] == Path(c["selection_artifact"]).name
    assert "multisource-validation-freeze" in cfg["freeze_doc"]


def test_calibration_v2_excludes_every_earlier_cohort():
    cfg = _cohorts()["calibration_v2"]
    assert set(cfg["exclude_cohorts"]) == {
        "calibration_targets.json", "masked_holdout_targets.json"}
    for name in cfg["exclude_cohorts"]:
        assert (BASE / name).exists(), f"{name} 이 없으면 제외가 성립하지 않는다"


def test_earlier_cohorts_keep_their_frozen_seeds():
    """seed 가 바뀌면 이전 코호트를 재현할 수 없다."""
    c = _cohorts()
    assert c["calibration"]["seed"] == 20260909
    assert c["masked_holdout"]["seed"] == 20260910
    assert len({c[k]["seed"] for k in c}) == len(c), "코호트끼리 seed 가 겹친다"


def test_calibration_v2_selection_inputs_exclude_both_sources_outcomes():
    forbidden = " ".join(_plan()["cohorts"]["calibration_v2"]["selection_forbidden_inputs"])
    for signal in ("MSA", "RFD3", "BioEmu", "pLDDT", "RMSD", "SoluProt",
                   "joint-pass", "Gate 0", "eligible"):
        assert signal in forbidden, f"{signal} 가 선정 금지 목록에 없다"


def test_the_pool_is_large_enough_for_the_new_cohort():
    c = _plan()["cohorts"]["calibration_v2"]
    need = c["pool_required_per_stratum"]
    assert need == c["per_stratum"] + c["reserve_per_stratum"] == 6
    for stratum, n in c["pool_by_stratum"].items():
        assert n >= need, f"{stratum} 층 후보 {n} < {need}"
    assert sum(c["pool_by_stratum"].values()) == c["pool_eligible_after_all_exclusions"]


# ---- 동결 상태 게이트 -------------------------------------------------------

def test_generation_does_not_start_before_the_plan_is_frozen():
    """선정 산출물이 있으면 계획은 이미 frozen 이어야 한다."""
    p = _plan()
    assert p["status"] in {"awaiting_user_review", "frozen"}, p["status"]
    artifact = ROOT / p["cohorts"]["calibration_v2"]["selection_artifact"]
    if artifact.exists():
        assert p["status"] == "frozen", (
            "calibration_v2 가 선정됐는데 계획이 아직 frozen 이 아니다")
        assert p["cohorts"]["calibration_v2"]["selection_committed"] is True


def test_the_six_decisions_are_tracked_in_both_states():
    """검토 대기면 미결로, 동결이면 승인 기록으로 남아 있어야 한다.

    동결로 바꾸는 순간 검증이 꺼지면 안 된다 - 그러면 승인된 6 항목이 조용히
    사라져도 아무도 모른다.
    """
    p = _plan()
    if p["status"] == "awaiting_user_review":
        items = p["review_required"]
        assert not p.get("approved_decisions"), "미검토인데 승인 기록이 있다"
    else:
        assert p["status"] == "frozen", p["status"]
        items = p["approved_decisions"]
        assert p["review_required"] == [], "동결인데 미결 항목이 남아 있다"
        assert p["frozen_utc"], "동결 시각이 없다"
        assert "historical v1 planning evidence" in p["approval_note"]
        assert "최적이라는 주장으로 확대하지 않는다" in p["approval_note"]
        assert "version 을 올리고" in p["change_policy"]

    assert len(items) == 6, items
    joined = " ".join(items)
    assert "18/backbone" in joined, "후보 수 결정이 목록에 없다"
    assert "ceiling anchor" in joined
    assert "M1-BioEmu" in joined
    assert "non-evaluable" in joined
    assert "bioemu 유한 생성 규칙" in joined
    assert "rfd3 max_attempts_per_target" in joined
    assert "검토가 필요한 결정" in _doc()


def test_msa_pilot_is_isolated_as_operational_only():
    iso = _plan()["msa"]["pilot_isolation"]
    assert iso["artifact"] == "operational_only"
    for banned in ("target 선정", "threshold", "tier"):
        assert any(banned in x for x in iso["may_not_change"]), \
            f"{banned} 변경 금지가 없다"


# ---- coverage_unit 은 source 마다 근거가 필요하다 ---------------------------

def test_coverage_unit_is_not_transferred_to_bioemu_without_evidence():
    """M1 은 RFD3 backbone 60 개로만 돌렸다. BioEmu 에 그대로 옮기지 않는다."""
    doc = _doc()
    assert "M1-BioEmu" in doc
    assert "RFD3 backbone 60 개로만" in doc
    # 세 결과가 모두 미리 적혀 있어야 한다 - 붕괴하는 경우를 포함해서
    assert "전부 한 클러스터로 붕괴" in doc


# ---- 원고 문장은 대기 상태다 -----------------------------------------------
#
# manuscript.md 와 results_of_record.md 는 v1 freeze manifest 의 27 해시에
# 들어 있다. 문장을 지금 적용하면 27/27 을 잃는다. 그래서 문서에 대기시키고,
# 여기서 **내용과 숫자를 지금 검증한다** - 적용할 때 다시 확인할 필요가 없도록.

V1_PINNED = ("docs/manuscript.md", "docs/results_of_record.md")


def test_v1_pinned_documents_are_untouched():
    out = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", *V1_PINNED],
                         cwd=ROOT, capture_output=True, text=True)
    assert not out.stdout.strip(), (
        f"v1 해시에 묶인 문서가 수정됐다: {out.stdout.strip()} - "
        "42_freeze_v1_results.py --verify 가 27/27 을 잃는다")


def test_the_staged_manuscript_paragraph_is_complete():
    assert "원고에 들어갈 문장" in _doc()
    doc = _flow(_doc())
    for phrase in ("unmasked ProteinMPNN candidate distribution",
                   "three-tier conservation-masked deployment pipeline",
                   "single generator",
                   "independent backbone-source cohorts",
                   "No outcome of that protocol is claimed here"):
        assert phrase in doc, f"대기 중인 원고 문단에 {phrase!r} 가 없다"


def test_the_staged_source_composition_matches_the_released_grid():
    """대기 중인 표의 숫자가 실제 격자 열과 같은가."""
    import collections
    import csv
    path = BASE / "holdout_grid" / "af2_order_metric.csv"
    if not path.exists():
        pytest.skip("격자 CSV 없음")
    by = collections.Counter(
        r["backbone_source"] for r in csv.DictReader(path.open(encoding="utf-8")))
    assert by["rfd3"] == 1440 and by["target"] == 288 and sum(by.values()) == 1728, by
    assert "1,440 come from RFD3 backbones and 288" in _flow(_doc())
    doc = _doc()
    assert "| `rfd3` | 1,440 |" in doc
    assert "| `target` (native) | 288 |" in doc


def test_applying_the_paragraph_requires_a_deliberate_manifest_reissue():
    doc = _doc()
    assert "조용히 다시 해시하지 않는다" in doc
    assert "이전 digest 와 새 digest" in doc


# ---- 계획의 격자가 실제 정책 객체에서 성립하는가 ---------------------------
#
# 문서·JSON 안에서만 맞는 숫자는 검산이 아니다. CoveragePolicy 는 의무 probe 를
# 채울 수 없는 예산을 **생성 시점에** 거부한다. 격자를 그 게이트에 통과시켜 본다.

def _policy(budget: int, n_units: int = 10, min_valid: int = 4):
    import sys
    sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
    from pipeline_mcp.rapid_core.coverage import CoverageState
    from pipeline_mcp.rapid_core.coverage_policy import CoveragePolicy
    units = tuple(("t1", f"bb{i:02d}") for i in range(n_units))
    return CoveragePolicy(state=CoverageState(units=units),
                          min_valid_observations=min_valid,
                          evaluable_budget=budget)


def test_every_primary_budget_point_is_admissible_to_the_policy():
    p = _plan()
    n_units = p["per_source_design"]["backbones_per_target"]
    min_valid = p["per_source_design"]["warmup_valid_observations_per_backbone"]
    for b in p["budget_grid"]["primary"]:
        policy = _policy(b, n_units, min_valid)
        assert policy.warmup_complete is False, f"B={b}: 시작부터 warm-up 완료"


def test_a_budget_below_the_warmup_is_rejected_at_construction():
    """B<40 을 primary 로 쓰지 않는 이유가 코드에도 있다."""
    from pipeline_mcp.rapid_core.coverage_policy import InvalidCampaignConfiguration
    p = _plan()
    warmup = p["totals"]["warmup_per_target_per_source"]
    with pytest.raises(InvalidCampaignConfiguration):
        _policy(warmup - 1)
    # 경계는 정확히 warm-up 이다
    _policy(warmup)


def test_both_anchors_leave_the_policy_no_room():
    """아래쪽은 자유 슬롯이 0, 위쪽은 unit 당 상한이 배분을 강제한다."""
    p = _plan()
    d = p["per_source_design"]
    g = p["budget_grid"]
    u = d["backbones_per_target"]
    w = d["warmup_valid_observations_per_backbone"]
    n = d["confirmatory_candidates_per_backbone"]

    # warm-up 앵커: 자유 슬롯 0
    assert g["anchors"]["warmup"] - u * w == 0

    # ceiling 앵커: 총예산 = u x N 이고 unit 당 상한 N 이므로 unit 당 정확히 N
    assert g["anchors"]["ceiling"] == u * n
    assert g["anchors"]["ceiling"] // u == n

    # 첫 informative 지점에는 실제로 자유 슬롯이 남는다
    first = min(g["primary_informative"])
    free = first - u * w
    assert free > 0
    assert first == 60 and free == 20
    # 한 unit 이 더 받을 수 있는 최대는 n - w 다. 자유 슬롯이 그보다 많으면
    # 정책은 최소 몇 개 unit 에 퍼져야 하는지가 정해진다.
    per_unit_headroom = n - w
    assert per_unit_headroom == 14
    min_units_touched = math.ceil(free / per_unit_headroom)
    assert min_units_touched == 2, min_units_touched
    # ceiling 에서는 모든 unit 이 소진되므로 배분의 자유도가 0 이다
    assert math.ceil((g["anchors"]["ceiling"] - u * w) / per_unit_headroom) == u


def test_unequal_unit_counts_shrink_both_warmup_and_ceiling():
    """u<10 이면 4u/24u 라는 규칙이 산술적으로 맞는지."""
    p = _plan()
    d = p["per_source_design"]
    for u in (1, 4, 7, 9, 10):
        warmup = 4 * u
        ceiling = 18 * u
        assert warmup <= ceiling
        _policy(warmup, n_units=u, min_valid=4)     # 거부되지 않아야 한다
        with pytest.raises(Exception):
            _policy(warmup - 1, n_units=u, min_valid=4)
        if u == d["backbones_per_target"]:
            assert warmup == p["totals"]["warmup_per_target_per_source"]
            assert ceiling == p["totals"]["ceiling_per_target_per_source"]


def test_the_execution_order_quotes_the_current_totals():
    """§15 의 폴드 수가 totals 와 어긋나면 문서 안에서 숫자가 갈라진다.

    실제로 24 -> 18 개정에서 이 줄만 5,760 으로 남아 있었다.
    """
    import re
    doc = _doc()
    t = _plan()["totals"]
    order = doc[doc.index("## 15. 실행 순서"):doc.index("## 16.")]
    quoted = {int(x.replace(",", "")) for x in re.findall(r"\(([\d,]{3,})\)", order)}
    assert t["calibration_all_sources"] in quoted, (
        f"calibration {t['calibration_all_sources']} 가 실행 순서에 없다: {quoted}")
    assert t["confirmatory_all_sources"] in quoted, (
        f"confirmatory {t['confirmatory_all_sources']} 가 실행 순서에 없다: {quoted}")
    stale = {5760, 8640, 1440} & quoted
    assert not stale, f"개정 전 숫자가 실행 순서에 남아 있다: {sorted(stale)}"


def test_the_freeze_blocks_full_msa_without_touching_scientific_thresholds():
    """MSA 는 실행 blocker 다. 설계를 막지 않고, 기준을 바꾸지도 않는다."""
    doc = _doc()
    head = doc[:doc.index("## 0.")]
    assert "full MSA 24 타겟" in head and "시작 금지" in head
    assert "calibration_v2 타겟 선정      진행 가능" in head
    assert "transport /" in head or "transport" in head
    assert "실행 blocker" in head
    # 추적 순서가 적혀 있어야 실행 계층을 고칠 수 있다
    for step in ("response_keys", "raw response", "parser expected key",
                 "파일 write path"):
        assert step in head, f"추적 순서에 {step} 이 없다"
    # scientific 기준은 건드리지 않는다
    assert "usable_hits < 10" in head
    assert "고치지 않는다" in head
    p = _plan()
    assert p["msa"]["thresholds_unchanged"] is True
