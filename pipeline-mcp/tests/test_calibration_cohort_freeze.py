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


# 결과의 5/4/2 형태를 고정하지 않는다. 그 수는 정당하게 바뀔 수 있고
# (프로토콜을 고쳐 전부 재생성하는 경우), 고정하면 오히려 옳은 재생성을 막는다.
# 대신 campaign provenance 를 고정한다 - 무엇을 어떤 설정으로 몇 번 시도해
# 무엇을 받았는지.

PROV = ROOT / "public_data" / "benchmark" / "gate0" / "calibration_generation_provenance.json"


def _prov() -> dict:
    if not PROV.exists():
        pytest.skip("생성 provenance 없음")
    return json.loads(PROV.read_text(encoding="utf-8"))


def test_frozen_target_list_is_unchanged():
    """생성에 쓴 타겟 목록이 동결된 목록과 같아야 한다."""
    import hashlib
    prov = _prov()
    want = sorted(t["domain"] for t in _cohort()["selected"])
    assert prov["frozen_target_list"] == want
    digest = hashlib.sha256(json.dumps(want).encode()).hexdigest()
    assert prov["frozen_target_list_sha256"] == digest


def test_one_protocol_signature_across_every_target():
    """타겟마다 다른 설정으로 돌렸다면 코호트가 아니라 잡탕이다."""
    sig = _prov()["protocol_signature"]
    assert sig["n_distinct"] == 1, (
        f"생성 프로토콜이 {sig['n_distinct']} 종이다: {sig['by_signature']}")


def test_calibration_protocol_matches_the_deployment_cohort():
    """calibration 과 holdout 의 생성 분포가 같아야 보정이 전이된다."""
    import hashlib, re
    root = Path("/opt/protein_pipeline/outputs")
    hold = [t["domain"] for t in json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0" / "holdout_targets.json")
        .read_text(encoding="utf-8"))["resolved"]["targets"]]

    def signature(mode, spec):
        m = dict(mode)
        m.pop("target_gate_reference_sha256", None)
        m.pop("target_gate_design_chains", None)
        s = dict(spec)
        s["contig"] = re.sub(r"\d+", "N", str(s.get("contig", "")))
        s["unindex"] = re.sub(r"\d+", "N", str(s.get("unindex", "")))
        s["select_fixed_atoms"] = {re.sub(r"\d+", "N", k): v
                                   for k, v in (s.get("select_fixed_atoms") or {}).items()}
        return hashlib.sha256(json.dumps({"mode": m, "spec": s},
                                         sort_keys=True).encode()).hexdigest()

    hsig = set()
    for t in hold:
        r = root / f"holdout_{t}_rfd3" / "rfd3"
        if (r / "mode.json").exists() and (r / "inputs.json").exists():
            hsig.add(signature(json.loads((r / "mode.json").read_text()),
                               json.loads((r / "inputs.json").read_text())["spec-1"]))
    if not hsig:
        pytest.skip("holdout 생성 산출물 없음")
    csig = set(_prov()["protocol_signature"]["by_signature"])
    assert csig == hsig, (
        f"calibration 서명 {csig} 가 holdout 서명 {hsig} 와 다르다 - "
        f"생성 분포가 어긋나면 보정이 전이되지 않는다")


OUTPUTS = Path("/opt/protein_pipeline/outputs")


def test_accepted_backbones_still_match_their_recorded_hashes():
    """디스크의 파일을 다시 해시해서 대조한다.

    기록된 값끼리 비교하면 기록이 자기 자신과 일치하는지만 본다 - 파일이
    바뀌어도 통과한다. 실제로 이 테스트의 첫 판이 그랬다.
    """
    import hashlib
    prov = _prov()
    checked = 0
    for target, run in prov["runs"].items():
        if not run.get("present"):
            continue
        d = OUTPUTS / run["run_id"] / "rfd3" / "designs"
        if not d.exists():
            assert run["n_accepted_backbones"] == 0
            continue
        for entry in run["accepted_backbones"]:
            f = d / entry["file"]
            assert f.exists(), f"{target}: {entry['file']} 이 사라졌다"
            got = hashlib.sha256(f.read_bytes()).hexdigest()
            assert got == entry["sha256"], (
                f"{target}/{entry['file']} 내용이 바뀌었다")
            checked += 1
        on_disk = len(list(d.glob("*.pdb")))
        assert on_disk == run["n_accepted_backbones"], (
            f"{target}: 디스크 {on_disk} 개 vs 기록 {run['n_accepted_backbones']} 개 "
            f"- 추가 생성이나 삭제가 있었다")
        gate = run.get("gate") or {}
        if gate:
            assert gate["accepted"] == run["n_accepted_backbones"]
    assert checked, "확인한 backbone 이 없다"


def test_attempt_log_is_recorded_for_every_target():
    """몇 번 시도했는지가 남아 있어야 사후 추가 생성을 알아볼 수 있다."""
    for target, run in _prov()["runs"].items():
        if not run.get("present"):
            continue
        gate = run.get("gate") or {}
        assert gate.get("attempted"), f"{target}: 시도 횟수 기록이 없다"
        assert gate["attempted"] >= gate["accepted"]


def test_no_unrecorded_backbone_appeared():
    """기록에 없는 backbone 파일이 생겼다면 사후 추가 생성이다.

    mtime 을 쓰지 않는다. 내용이 같아도 파일을 복사하면 mtime 이 바뀌므로
    (실제로 변이 테스트를 되돌리다 그렇게 됐다) 거짓 양성이 난다. 내용은
    해시가 보고, 추가 생성은 "기록에 없는 파일" 로 본다.
    """
    prov = _prov()
    checked = 0
    for target, run in prov["runs"].items():
        if not run.get("present"):
            continue
        d = OUTPUTS / run["run_id"] / "rfd3" / "designs"
        if not d.exists():
            # backbone 0 개인 타겟은 designs 디렉터리가 없다. 기록과 일치하면 정상.
            assert run["n_accepted_backbones"] == 0, (
                f"{target}: 기록은 {run['n_accepted_backbones']} 개인데 "
                f"designs 디렉터리가 없다")
            continue
        recorded = {e["file"] for e in run["accepted_backbones"]}
        on_disk = {f.name for f in d.glob("*.pdb")}
        extra = on_disk - recorded
        assert not extra, f"{target}: 기록에 없는 backbone {sorted(extra)}"
        missing = recorded - on_disk
        assert not missing, f"{target}: 기록된 backbone 이 사라졌다 {sorted(missing)}"
        checked += 1
    assert checked, "확인한 타겟이 없다"


def test_partial_sibling_sets_are_kept():
    """형제가 둘 이상인 타겟은 informative 에 남아야 한다 (complete-case 아님)."""
    r = _realized()
    for t, n in r["backbones_per_target"].items():
        if n >= 2:
            assert t in r["informative_targets"], f"{t} ({n} 개) 가 빠졌다"


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


# ---- v2.0 multi-source 로의 supersede ---------------------------------------

FREEZE_DOC = ROOT / "docs" / "specs" / "rapid-v2-phase4b-calibration-freeze.md"
PLAN = ROOT / "public_data" / "benchmark" / "gate0" / "multisource_validation_plan.json"


def test_the_calibration_freeze_keeps_its_identification_criteria():
    """§9 는 대체되지 않는다. source 마다 독립으로 적용되는 것뿐이다."""
    if not FREEZE_DOC.exists():
        pytest.skip("동결 문서 없음")
    head = FREEZE_DOC.read_text(encoding="utf-8")[:1400]
    assert "SUPERSEDED" in head
    assert "§9 식별 판정" in head
    assert "유지되는 절" in head
    # 대체 목록에 §9 가 들어가면 판정 기준이 사후에 바뀔 수 있게 된다
    superseded = head.split("대체된 절")[1].split("|")[1]
    assert "§9" not in superseded, "§9 가 대체 목록에 있다"
    assert "§7" not in superseded, "§7 LOTO 가 대체 목록에 있다"


def test_this_cohort_is_no_longer_a_primary_statistical_input():
    """보존하지만 새 primary calibration 의 input 은 아니다."""
    if not PLAN.exists():
        pytest.skip("multi-source plan 없음")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    joined = " ".join(plan["preserved_not_input"]["items"])
    assert "51-backbone" in joined
    allowed = plan["preserved_not_input"]["roles_allowed"]
    assert "ablation/sensitivity" in allowed
    assert not any("primary" in r for r in allowed)
    # 새 코호트가 이 코호트의 타겟을 제외해야 한다
    assert "calibration_selected" in plan["cohorts"]["calibration_v2"]["excludes_cohorts"]
