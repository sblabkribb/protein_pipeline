import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "benchmark"))
# 리포에 conftest.py 도 pytest 설정도 없다. 이 경로가 테스트 본문 안에 있으면
# 그 본문을 먼저 실행하지 않는 선택(`pytest <nodeid>`, `-k`, xdist 샤딩,
# random-order)에서 `rapid_sr` import 가 깨진다 - "리뷰어가 직접 테스트를 다시
# 돌린다" 가드가 바로 그것들이므로 수집 시점에 한 번 넣는다.
sys.path.insert(0, str(ROOT / "scripts" / "transcoder"))

import _gate2d as G


def test_frozen_constants_match_spec():
    assert G.PLDDT_MIN == 85.0
    assert G.RMSD_MAX == 2.0
    assert G.SOLUPROT_MIN == 0.5
    assert G.TOP_K == 4
    assert G.GATE2_DELTA_MIN == 0.10
    assert G.GATE1_RHO_MIN == 0.25
    assert G.LCB_ONE_SIDED_ALPHA == 0.10
    assert G.MIN_INFORMATIVE_TARGETS == 8
    assert G.BOOTSTRAP_SEED == 20260910


def test_is_joint_pass_boundaries():
    # 문턱은 모두 포함(>=, <=)이다.
    assert G.is_joint_pass(85.0, 2.0, 0.5) is True
    assert G.is_joint_pass(84.99, 2.0, 0.5) is False
    assert G.is_joint_pass(85.0, 2.01, 0.5) is False
    assert G.is_joint_pass(85.0, 2.0, 0.49) is False


def test_delta_top4_oracle_and_worst():
    # 24개 중 6개만 통과. q_b = 0.25.
    labels = [True] * 6 + [False] * 18
    ids = [f"g{i}" for i in range(24)]
    oracle = [1.0] * 6 + [0.0] * 18
    # Top-4 전부 통과 -> 1.0 - 0.25
    assert abs(G.delta_top4(labels, oracle, ids) - 0.75) < 1e-12
    worst = [0.0] * 6 + [1.0] * 18
    # Top-4 전부 실패 -> 0.0 - 0.25
    assert abs(G.delta_top4(labels, worst, ids) - (-0.25)) < 1e-12


def test_delta_top4_tie_break_is_sequence_id_ascending():
    # 점수가 전부 같으면 sequence_id 오름차순 앞 4개를 고른다.
    labels = [False, False, True, True, True, True]
    ids = ["g0", "g1", "g2", "g3", "g4", "g5"]
    scores = [0.5] * 6
    # 선택 = g0,g1,g2,g3 -> 통과 2/4 = 0.5, q_b = 4/6
    assert abs(G.delta_top4(labels, scores, ids) - (0.5 - 4.0 / 6.0)) < 1e-12
    # 문자열 정렬이므로 g10 은 g2 보다 앞이다. 그 규칙을 명시적으로 고정한다.
    ids2 = ["g0", "g1", "g10", "g2", "g3", "g4"]
    labels2 = [False, False, True, False, False, False]
    assert abs(G.delta_top4(labels2, [0.5] * 6, ids2) - (1.0 / 4.0 - 1.0 / 6.0)) < 1e-12


def test_target_equal_mean_differs_from_backbone_equal():
    # 타겟 A 는 백본 3개(전부 0.0), 타겟 B 는 백본 1개(0.8).
    per_backbone = [0.0, 0.0, 0.0, 0.8]
    targets = ["A", "A", "A", "B"]
    # 백본 등가중 = 0.8/4 = 0.2
    assert abs(sum(per_backbone) / 4 - 0.2) < 1e-12
    # 타겟 등가중 = (0.0 + 0.8)/2 = 0.4
    per_target = G.per_target_means(per_backbone, targets)
    assert per_target == [0.0, 0.8]
    assert abs(G.target_equal_mean(per_backbone, targets) - 0.4) < 1e-12


def test_per_target_means_sorts_targets_deterministically():
    per_target = G.per_target_means([1.0, 2.0, 3.0], ["b", "a", "b"])
    # 타겟 정렬 오름차순: a -> 2.0, b -> (1.0+3.0)/2 = 2.0
    assert per_target == [2.0, 2.0]


def test_target_equal_mean_ignores_nan_backbones():
    per_target = G.per_target_means([float("nan"), 0.4], ["A", "A"])
    assert per_target == [0.4]


def test_msa_feature_missing_handling():
    import importlib
    prep = importlib.import_module("23_gate2d_prepare_msa_features")

    # test 타겟이 전부 undefined 여도 타겟은 유지되고 지시자가 1 이 된다.
    train = {"A": {"cons_mean": 0.8}, "B": {"cons_mean": 0.6}}
    out = prep.impute("C", None, train_stats=prep.train_stats(train))
    assert out["msa_undefined"] == 1
    assert abs(out["cons_mean"] - 0.7) < 1e-12

    # 정의된 타겟은 그대로 쓰고 지시자가 0 이다.
    out2 = prep.impute("A", {"cons_mean": 0.8}, train_stats=prep.train_stats(train))
    assert out2["msa_undefined"] == 0
    assert out2["cons_mean"] == 0.8

    # train fold 자체에서 정의 불가면 imputation statistic 이 없다 -> arm non-evaluable.
    assert prep.train_stats({}) is None


def test_impute_never_invents_a_constant_for_an_undefined_feature():
    """train fold 가 정의하지 못한 feature 를 0.0 으로 채우지 않는다.

    상수로 채우면 모든 타겟이 같은 값을 받아, 정보가 없는데도 측정값인 것처럼
    하류로 흐른다. 스펙 §4 규칙 5 는 그 경우를 arm non-evaluable 로 규정하지
    상수 채우기로 규정하지 않는다.
    """
    import importlib
    prep = importlib.import_module("23_gate2d_prepare_msa_features")

    # train fold 가 cons_mean 하나만 정의한 경우: 나머지 5 개는 나오지 않는다.
    ts = prep.train_stats({"A": {"cons_mean": 0.8}})
    assert set(ts) == {"cons_mean"}
    for out in (prep.impute("C", None, train_stats=ts),
                prep.impute("A", {"cons_mean": 0.8}, train_stats=ts)):
        assert set(out) == {"cons_mean", "msa_undefined"}

    # 실제 Step 6 산출물 모양(타겟 행이 전부 정의되거나 전부 null)에서는
    # 6 개 feature 가 그대로 나온다 - 스키마는 바뀌지 않는다.
    full = {n: 0.5 for n in prep.TARGET_FEATURES}
    ts2 = prep.train_stats({"A": full, "B": full})
    assert set(ts2) == set(prep.TARGET_FEATURES)
    undef = prep.impute("C", None, train_stats=ts2)
    assert set(undef) == set(prep.TARGET_FEATURES) | {"msa_undefined"}
    assert undef["msa_undefined"] == 1
    assert prep.impute("A", full, train_stats=ts2)["msa_undefined"] == 0


def test_dropping_a_measured_feature_is_surfaced_and_fails_the_arm():
    """통계가 없다고 **측정된 값**을 조용히 버리면 안 된다.

    규칙 2 는 계산된 feature 를 그대로 쓰라고 하고, 규칙 5 는 train fold 에
    통계가 없는 경우를 arm non-evaluable 로 기록하라고 한다. 좁아진 설계행렬을
    조용히 평가하면 6 개 중 5 개를 잃은 S4 도 정상 arm 처럼 보인다.
    """
    import importlib
    prep = importlib.import_module("23_gate2d_prepare_msa_features")

    # 측정값 3 개 vs 통계 1 개.
    row = prep.impute("C", {"cons_mean": 0.71, "cons_p25": 0.52, "coverage_median": 0.89},
                      train_stats={"cons_mean": 0.7})
    assert row["cons_mean"] == 0.71
    # 버려진 측정값이 보고된다 - msa_undefined == 0 만 보고 넘어갈 수 없다.
    assert row["dropped_measured"] == ["cons_p25", "coverage_median"]

    # arm 판정은 arm 수준에서 한다. 타겟은 그대로 남는다.
    verdict = prep.arm_verdict({"C": row}, stats={"cons_mean": 0.7})
    assert verdict["evaluable"] is False
    assert "cons_p25" in verdict["reason"] and "coverage_median" in verdict["reason"]
    assert verdict["dropped_measured_by_target"] == {"C": ["cons_p25", "coverage_median"]}

    # 아무것도 버리지 않았으면 arm 은 평가 가능하고 행에 그 키가 없다.
    full = {n: 0.5 for n in prep.TARGET_FEATURES}
    stats = prep.train_stats({"A": full, "B": full})
    ok = prep.impute("A", full, train_stats=stats)
    assert "dropped_measured" not in ok
    assert prep.arm_verdict({"A": ok}, stats=stats) == {"evaluable": True}


def test_arm_verdict_sees_a_feature_no_one_defined_at_all():
    """규칙 5 의 조건은 **train fold** 에 관한 것이다.

    train fold 가 feature F 를 정의하지 못했고 test 타겟도 아무도 F 를 측정하지
    않았으면 `dropped_measured` 는 비어 있다. 행만 보면 정상이고 설계행렬은
    조용히 F 를 잃는다 - 그래서 판정에 stats 가 들어간다.
    """
    import importlib
    prep = importlib.import_module("23_gate2d_prepare_msa_features")

    stats = prep.train_stats({"A": {"cons_mean": 0.8}, "B": {"cons_mean": 0.6}})
    row = prep.impute("C", {"cons_mean": 0.5}, train_stats=stats)
    assert "dropped_measured" not in row          # 버린 측정값은 없다
    assert row["msa_undefined"] == 0

    verdict = prep.arm_verdict({"C": row}, stats=stats)
    assert verdict["evaluable"] is False, "설계행렬이 5 개 feature 를 잃었는데 통과했다"
    assert verdict["undefined_in_train"] == [
        "cons_p25", "cons_p75", "usable_hits_log10", "coverage_median",
        "depth_median_log10"]
    assert "cons_p25" in verdict["reason"]

    # train fold 가 아무것도 정의하지 못하면 stats 자체가 None 이다.
    assert prep.arm_verdict({}, stats=None)["evaluable"] is False


def test_nan_is_undefined_not_a_value():
    """NaN 하나가 모든 fold 의 모든 타겟을 오염시키지 못하게 한다.

    json.dumps 는 기본값으로 bare NaN 을 쓰고 json.loads 는 그것을 float 로
    읽으므로 이 경로는 실재한다. 스펙 §5 는 NaN 을 fail-closed 로 규정한다.
    """
    import importlib
    import math
    prep = importlib.import_module("23_gate2d_prepare_msa_features")
    nan = float("nan")

    # train 타겟 하나가 NaN 이면 그 타겟만 빠지고 나머지 평균은 온전하다.
    stats = prep.train_stats({"A": {"cons_mean": nan}, "B": {"cons_mean": 0.6}})
    assert stats == {"cons_mean": 0.6}

    # 전부 NaN 인 train fold 는 "정의된 값 없음" 과 같다 -> arm non-evaluable.
    assert prep.train_stats({"A": {"cons_mean": nan}}) is None

    # NaN 을 들고 온 test 타겟은 undefined 로 취급되고 지시자가 1 이 된다.
    out = prep.impute("C", {"cons_mean": nan}, train_stats=stats)
    assert out["msa_undefined"] == 1
    assert out["cons_mean"] == 0.6
    assert not math.isnan(out["cons_mean"])

    # inf 도 같다 - usable_hits 0 에서 log10 이 -inf 를 낸다.
    assert prep.train_stats({"A": {"usable_hits_log10": float("-inf")}}) is None

    # 직렬화는 NaN 을 쓰지 않고 거절한다.
    import pytest
    with pytest.raises(ValueError):
        prep.dump_features({"per_target": {"C": {"cons_mean": nan}}})
    assert '"cons_mean": null' in prep.dump_features(
        {"per_target": {"C": {"cons_mean": None}}})


def test_an_unknown_feature_name_is_refused_not_dropped():
    """Step 6 의 오타 하나가 msa_undefined == 0 인 채로 사라지면 안 된다."""
    import importlib
    import pytest
    prep = importlib.import_module("23_gate2d_prepare_msa_features")
    with pytest.raises(ValueError, match="cons_meen"):
        prep.impute("C", {"cons_meen": 0.7}, train_stats={"cons_mean": 0.7})


def test_conserved_positions_are_zero_based_and_hash_verified():
    """Step 6 은 위치 집합을 0-기반으로 내고 manifest 해시로 검증한다.

    배포는 1-기반을 돌려주고 manifest 해시는 그 1-기반 목록으로 만들어졌다.
    검증과 출력의 기준을 섞으면 보존 마스크가 한 칸 밀린다.
    """
    import hashlib
    import importlib
    import json as _json
    import sys
    prep = importlib.import_module("23_gate2d_prepare_msa_features")
    sys.path.insert(0, str(ROOT / "pipeline-mcp" / "src"))
    from pipeline_mcp.bio.a3m import compute_conservation

    query = "ACDEFGHIKLMNPQRSTVWY" * 3
    a3m = ">q\n" + query + "\n" + "".join(
        f">h{i}\n" + query[:55] + "-----\n" for i in range(40))

    # 50_full_msa.py 의 measure() 와 **같은** 방식으로 manifest 해시를 만든다.
    cons = compute_conservation(a3m, tiers=list(prep.TIERS), mode="quantile",
                                weights=None)
    manifest_sha = {str(t): hashlib.sha256(_json.dumps(v).encode()).hexdigest()
                    for t, v in cons.fixed_positions_by_tier.items()}

    pos, verified = prep.conserved_positions(a3m, manifest_sha256=manifest_sha)
    assert verified is True
    assert set(pos) == {"0.3", "0.5", "0.7"}
    # 0-기반: 최소가 0 이고 최대가 L-1 을 넘지 않는다.
    assert min(min(v) for v in pos.values()) == 0
    assert max(max(v) for v in pos.values()) <= len(query) - 1
    # 1-기반 목록보다 정확히 1 씩 작다.
    assert pos["0.3"] == [p - 1 for p in cons.fixed_positions_by_tier[0.3]]
    # tier 는 포개진다 (더 느슨한 tier 가 더 많은 위치를 잡는다).
    assert set(pos["0.3"]) <= set(pos["0.5"]) <= set(pos["0.7"])
    # 해시가 다르면 검증이 실패한다 - provenance 가 맞는지 실제로 본다.
    _, bad = prep.conserved_positions(a3m, manifest_sha256={"0.3": "0" * 64})
    assert bad is False
    # manifest 를 주지 않으면 "검증 안 함" 이고 통과가 아니다.
    _, none = prep.conserved_positions(a3m)
    assert none is None


def test_an_all_null_row_is_kept_not_crashed_on():
    """Step 6 은 정의되지 않은 값을 null 로 쓴다. 그 행은 truthy dict 다.

    규칙 4 는 그런 test 타겟을 **유지**하라고 한다. float(None) 으로 죽으면
    타겟이 사라지므로 그 자체가 규칙 위반이다.
    """
    import importlib
    prep = importlib.import_module("23_gate2d_prepare_msa_features")

    # Step 6 스키마가 쓰는 모양 그대로.
    null_row = {"cons_mean": None, "cons_p25": None, "cons_p75": None,
                "usable_hits_log10": None, "coverage_median": None,
                "depth_median_log10": None}
    full = {"cons_mean": 0.71, "cons_p25": 0.52, "cons_p75": 0.9,
            "usable_hits_log10": 3.39, "coverage_median": 0.89,
            "depth_median_log10": 3.37}

    # 전부 null 인 train 행은 "정의 안 됨" 으로 센다.
    assert prep.train_stats({"5xpdA02": null_row}) is None
    stats = prep.train_stats({"5xpdA02": null_row, "1sp0A00": full})
    assert stats == full

    out = prep.impute("5xpdA02", null_row, train_stats=stats)
    assert out["msa_undefined"] == 1
    assert set(out) == set(prep.TARGET_FEATURES) | {"msa_undefined"}
    assert out["cons_mean"] == 0.71

    # 일부만 null 이면 정의된 것은 그대로 쓰고 나머지만 대치한다.
    part = dict(null_row, cons_mean=0.4)
    out2 = prep.impute("X", part, train_stats=stats)
    assert out2["cons_mean"] == 0.4
    assert out2["cons_p25"] == full["cons_p25"]
    assert out2["msa_undefined"] == 1


def test_one_sided_lcb90_positive_and_null():
    from rapid_sr.clustered import one_sided_lcb

    # 전부 +0.5 인 표본이면 LCB 도 +0.5 여야 한다(재표집해도 값이 같다).
    out = one_sided_lcb([0.5] * 11, alpha=0.10, seed=20260910)
    assert abs(out["lcb"] - 0.5) < 1e-9
    assert out["exceeds_zero"] is True
    assert out["n"] == 11

    # 0 을 중심으로 대칭인 표본이면 LCB < 0 이어야 한다.
    sym = [-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, -0.05, 0.05]
    out2 = one_sided_lcb(sym, alpha=0.10, seed=20260910)
    assert out2["lcb"] < 0
    assert out2["exceeds_zero"] is False


def test_one_sided_lcb90_is_deterministic_for_a_seed():
    from rapid_sr.clustered import one_sided_lcb
    a = one_sided_lcb([0.1, 0.2, 0.05, 0.3, 0.0, 0.15, 0.25, 0.2, 0.1, 0.05, 0.3],
                      alpha=0.10, seed=20260910)
    b = one_sided_lcb([0.1, 0.2, 0.05, 0.3, 0.0, 0.15, 0.25, 0.2, 0.1, 0.05, 0.3],
                      alpha=0.10, seed=20260910)
    assert a["lcb"] == b["lcb"]


def test_one_sided_lcb90_withholds_below_three_units():
    from rapid_sr.clustered import one_sided_lcb
    out = one_sided_lcb([0.5, 0.5], alpha=0.10, seed=1)
    assert out["lcb"] is None
    assert out["n"] == 2


def test_load_holdout_grid_shapes():
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    # 1,728 폴드 중 status ok 이고 지표 결측 아닌 것이 1,680 이다.
    assert len(grid.folds) == 1680
    assert len(grid.backbones) == 70
    assert len(grid.targets) == 12


def test_gate2_informative_targets_is_eleven():
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    assert len(mixed) == 37
    # mixed 백본이 하나도 없는 타겟은 1sh6A02 뿐이다.
    assert sorted({b.target_id for b in mixed}) == sorted(set(grid.targets) - {"1sh6A02"})
    assert len({b.target_id for b in mixed}) == 11


def test_gate1_informative_targets_is_eleven():
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    inf = C.gate1_informative_targets(grid)
    # 백본 >= 3 이고 q_b 비상수. 1sh6A02 는 q_b 가 전부 1.00 이라 Spearman 미정의.
    assert len(inf) == 11
    assert "1sh6A02" not in inf


def test_reproduces_spec_reference_deltas():
    """스펙 §1: SoluProt −0.001, oracle +0.326 (타겟 등가중, mixed 백본 37개)."""
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    targets = [b.target_id for b in mixed]

    solu, oracle = [], []
    for b in mixed:
        labels = [f.joint_pass for f in b.folds]
        ids = [f.sequence_id for f in b.folds]
        solu.append(G.delta_top4(labels, [f.soluprot for f in b.folds], ids))
        oracle.append(G.delta_top4(labels, [1.0 if v else 0.0 for v in labels], ids))

    assert round(G.target_equal_mean(solu, targets), 3) == -0.001
    assert round(G.target_equal_mean(oracle, targets), 3) == 0.326


def test_soluprot_reference_fails_the_gate2_threshold():
    """현행 cheap predictor 는 GO 문턱에 한참 미달한다 - 그것이 실험의 출발점이다."""
    import _gate2d_cohort as C
    from rapid_sr.clustered import one_sided_lcb
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    per_backbone = [
        G.delta_top4([f.joint_pass for f in b.folds],
                     [f.soluprot for f in b.folds],
                     [f.sequence_id for f in b.folds])
        for b in mixed
    ]
    per_target = G.per_target_means(per_backbone, [b.target_id for b in mixed])
    point = sum(per_target) / len(per_target)
    out = one_sided_lcb(per_target, alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    assert point < G.GATE2_DELTA_MIN
    assert out["exceeds_zero"] is False


def test_top_k_indices_refuses_a_nan_score():
    """스펙 §5: **점수 배열**의 NaN 은 fail-closed 다.

    NaN 비교는 전부 False 이므로 정렬은 NaN 을 입력 행 순서가 놓는 자리에 그냥
    둔다. 전 후보가 NaN 인 최악의 경우 Top-4 가 `sequence_id` 앞 4개가 되어
    **Δ_Top4 가 고장 대신 잡음처럼 보인다.** 그래서 정렬 전에 거절한다.
    """
    ids = [f"g{i}" for i in range(6)]
    scores = [0.9, 0.8, float("nan"), 0.6, 0.5, 0.4]
    # 메시지가 몇 개인지와 첫 인덱스를 말한다 - 어느 후보가 고장인지 바로 보인다.
    with pytest.raises(ValueError, match=r"비유한 점수 1 개.*첫 인덱스 2"):
        G.top_k_indices(scores, ids)

    # NaN 이 여러 개면 개수도 그대로 센다.
    with pytest.raises(ValueError, match=r"비유한 점수 3 개.*첫 인덱스 0"):
        G.top_k_indices([float("nan")] * 3 + [0.1] * 3, ids)

    # 유한한 점수만 있으면 그대로 동작한다 - 가드가 정상 경로를 막지 않는다.
    assert G.top_k_indices([0.9, 0.8, 0.7, 0.6, 0.5, 0.4], ids) == [0, 1, 2, 3]


def test_top_k_indices_refuses_inf_scores():
    """±Inf 도 같다. usable hits 0 에서 log10 이 -inf 를 내는 경로가 실재한다."""
    ids = [f"g{i}" for i in range(4)]
    with pytest.raises(ValueError, match=r"비유한 점수 1 개.*첫 인덱스 1"):
        G.top_k_indices([0.5, float("inf"), 0.3, 0.2], ids)
    with pytest.raises(ValueError, match=r"비유한 점수 1 개.*첫 인덱스 3"):
        G.top_k_indices([0.5, 0.4, 0.3, float("-inf")], ids)


def test_delta_top4_inherits_the_score_guard_without_repeating_it():
    """검사는 metric 경계에서 한 번만 한다.

    `delta_top4` 는 `top_k_indices` 를 통해 보호받는다. 중복 검사를 두면 규칙이
    두 곳에 살게 되고 한쪽만 고쳐지는 경로가 생긴다.
    """
    labels = [True, False, True, False, False, False]
    ids = [f"g{i}" for i in range(6)]
    with pytest.raises(ValueError, match=r"비유한 점수 1 개.*첫 인덱스 4"):
        G.delta_top4(labels, [0.9, 0.8, 0.7, 0.6, float("nan"), 0.4], ids)


def test_delta_top4_still_returns_nan_for_an_uncountable_backbone():
    """반환 NaN 은 금지 대상이 아니다 - 사용가능 설계 0 인 백본의 sentinel 이다.

    스펙 §3 의 `3es1A01`·`3h7eA02` native arm 이 그 2개다. 점수 입력의 NaN 만
    금지된다. 두 용법을 섞으면 "셀 수 없는 백본" 이 예외가 되어 집계가 죽는다.
    """
    empty = G.delta_top4([], [], [])
    assert empty != empty, "사용가능 설계 0 인 백본은 NaN 이어야 한다"
    assert G.delta_top4([True], [1.0], ["g0"], k=0) != G.delta_top4([True], [1.0], ["g0"], k=0)

    # 그 sentinel 은 타겟 등가중 집계에서 제외된다(예외가 되지 않는다).
    assert G.per_target_means([empty, 0.4], ["A", "A"]) == [0.4]


def test_within_target_spearman_excludes_targets_it_cannot_define():
    """스펙 §5: 백본 3개 미만인 타겟은 제외하고 그 수를 보고한다.

    q_b 가 상수인 타겟도 정의되지 않는다 - `1sh6A02` 가 그 경우다(6 백본 전부
    q_b = 1.00). 상수 타겟에 0 을 넣으면 존재하지 않는 관측이 평균을 끌어내린다.
    """
    # 타겟 A: 완전 일치 -> +1. 타겟 B: 완전 역순 -> -1.
    predicted = [0.1, 0.2, 0.3, 0.3, 0.2, 0.1]
    actual = [0.1, 0.2, 0.3, 0.1, 0.2, 0.3]
    targets = ["A", "A", "A", "B", "B", "B"]
    rhos = G.within_target_spearman(predicted, actual, targets)
    assert sorted(rhos) == ["A", "B"]
    assert abs(rhos["A"] - 1.0) < 1e-12
    assert abs(rhos["B"] + 1.0) < 1e-12
    # 타겟 등가중 평균은 기존 primitive 로 낸다 - 별도 평균을 만들지 않는다.
    assert abs(G.target_equal_mean(list(rhos.values()), list(rhos))) < 1e-12

    # 백본 2개인 타겟은 빠진다(상관이 불안정하다).
    assert G.within_target_spearman([0.1, 0.2], [0.1, 0.2], ["C", "C"]) == {}
    # q_b 가 상수인 타겟도 빠진다 - 제외 사유는 다르지만 결과는 미정의다.
    assert G.within_target_spearman([0.1, 0.2, 0.3], [1.0, 1.0, 1.0],
                                    ["D"] * 3) == {}
    # 예측이 상수여도 미정의다(순위 정보가 0 인 것과 -1..+1 은 다르다).
    assert G.within_target_spearman([0.5, 0.5, 0.5], [0.1, 0.2, 0.3],
                                    ["E"] * 3) == {}


def test_top1_regret_is_the_q_b_a_perfect_picker_would_have_got():
    """2차 지표. q_b(실제 최선) − q_b(예측 최선). 0 이 최선이다."""
    # 타겟 A: 예측 최선이 q_b 0.5 인 백본, 실제 최선은 0.9 -> regret 0.4.
    predicted = [0.9, 0.1, 0.2, 0.1, 0.5, 0.9]
    actual = [0.5, 0.9, 0.3, 0.2, 0.4, 0.8]
    targets = ["A", "A", "A", "B", "B", "B"]
    regret = G.top1_regret(predicted, actual, targets)
    assert abs(regret["A"] - 0.4) < 1e-12
    # 타겟 B: 예측 최선(0.9)이 실제 최선(0.8)과 같은 백본 -> regret 0.
    assert abs(regret["B"]) < 1e-12
    # 백본 3개 미만인 타겟은 Spearman 과 같은 이유로 빠진다.
    assert G.top1_regret([0.1, 0.2], [0.5, 0.9], ["C", "C"]) == {}


def test_rfd3_only_is_a_cohort_the_loader_can_hand_over():
    """§3 개정: Gate 1 의 1차 코호트는 RFD3-only 다. native 는 comparator 다.

    source 는 `af2_order_metric.csv` 의 `backbone_source` 열이다 - backbone_key
    를 문자열로 쪼개 추측하면 파일 형식 지식이 두 곳에 살게 된다.
    """
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()

    rfd3 = C.restrict_to_sources(grid, ("rfd3",))
    # variance_decomposition_grid.json 의 rfd3_only_primary 와 같은 기하다.
    assert len(rfd3.backbones) == 60
    assert len(rfd3.folds) == 1440
    assert {b.backbone_source for b in rfd3.backbones} == {"rfd3"}
    # §3: RFD3-only 로도 informative 타겟은 11 개 그대로다(검정력 손실 거의 없음).
    assert len(C.gate1_informative_targets(rfd3)) == 11
    # §3: Gate 2 민감도 코호트는 mixed 34 · informative 11.
    assert len(C.mixed_backbones(rfd3)) == 34
    assert len({b.target_id for b in C.mixed_backbones(rfd3)}) == 11

    # native 라벨은 10/12 타겟에만 있다 - 3es1A01·3h7eA02 는 대응 거부로 폴드 0.
    native = C.restrict_to_sources(grid, ("target",))
    assert len(native.backbones) == 10
    assert "3es1A01" not in native.targets and "3h7eA02" not in native.targets
    # 두 코호트를 합치면 전체 70 백본이다 - 조용히 사라지는 백본이 없다.
    assert len(rfd3.backbones) + len(native.backbones) == len(grid.backbones)

    # 없는 source 를 주면 빈 코호트다(조용히 전체를 돌려주지 않는다).
    assert C.restrict_to_sources(grid, ("bioemu",)).backbones == []


# --------------------------------------------------------------------------
# OC 표 생성기 (`26_gate2d_operating_characteristics.py`) 의 회귀 가드.
#
# 스펙 §3·§5 에 인쇄된 표는 커밋되지 않은 임시 실행이 만들었다. 배포된
# `one_sided_lcb` 가 그 표를 여전히 재현하는지 확인하는 것이 아무것도 없었다 -
# 아래가 그 계약이다. **스펙 파일은 고치지 않는다**: 인쇄값을 여기에 적어 두고
# 산출물과 대조하며, 차이는 controller 가 판단한다.
# --------------------------------------------------------------------------

OC_ARTIFACT = (ROOT / "public_data" / "benchmark" / "gate0"
               / "gate2d_operating_characteristics.json")

#: 스펙 §5 교정표 인쇄값. delta -> (mean AUC, Δ_Top4).
SPEC_GATE2_CALIBRATION = {
    0.0: (0.502, -0.001), 0.25: (0.568, 0.053), 0.5: (0.640, 0.101),
    0.6: (0.665, 0.120), 0.75: (0.701, 0.146), 1.0: (0.760, 0.187),
}

#: 스펙 §5 작동특성표 인쇄값. delta -> (참 Δ_Top4, P(점추정≥.10), P(LCB>0), P(GO)).
SPEC_GATE2_OC = {
    0.0: (0.001, 0.00, 0.12, 0.00), 0.25: (0.053, 0.09, 0.65, 0.09),
    0.5: (0.103, 0.54, 0.96, 0.54), 0.6: (0.122, 0.77, 0.99, 0.77),
    0.75: (0.148, 0.94, 0.99, 0.94),
}

#: 스펙 §3 Gate 1 OC 인쇄값. sigma -> (E[mean rho], E[top-1 regret], P(GO) 네 문턱).
SPEC_GATE1_OC = {
    "null": (-0.002, 0.245, (0.12, 0.06, 0.03, 0.01)),
    1.0: (0.184, 0.165, (0.53, 0.47, 0.34, 0.20)),
    0.5: (0.340, 0.111, (0.92, 0.89, 0.79, 0.63)),
    0.35: (0.441, 0.081, (0.98, 0.97, 0.96, 0.90)),
    0.25: (0.529, 0.055, (1.00, 1.00, 1.00, 0.99)),
}

#: 확률 셀의 허용오차. n=600 이항 SE 는 p=0.5 에서 0.020 이므로 2.5 SE 다.
#: 인쇄값을 만든 임시 실행은 power 루프 안에서 부트스트랩 800 회를 썼고
#: 프로덕션 `one_sided_lcb` 는 20,000 회다 - P(LCB>0) 이 그만큼 더 흔들린다.
PROB_TOL = 0.05


def _oc() -> dict:
    import json
    assert OC_ARTIFACT.exists(), f"{OC_ARTIFACT} 가 없다 - 생성기를 돌려야 한다"
    return json.loads(OC_ARTIFACT.read_text(encoding="utf-8"))


def test_oc_artifact_records_the_seed_and_the_frozen_cohort_geometry():
    """산출물이 자기 provenance 를 들고 있어야 재현이 가능하다.

    시드·반복수·부트스트랩 수·코호트 크기·호출한 primitive 이름을 모두 적는다.
    """
    art = _oc()
    assert art["seed"] == G.BOOTSTRAP_SEED
    assert art["lcb"] == {
        "primitive": "rapid_sr.clustered.one_sided_lcb",
        "alpha": G.LCB_ONE_SIDED_ALPHA, "n_boot": 20000,
        "seed": G.BOOTSTRAP_SEED,
        "note": "게이트가 부르는 것과 같은 인자·같은 시드로 부른다",
    }
    assert art["go_rules"] == {
        "gate2_delta_min": G.GATE2_DELTA_MIN, "gate1_rho_min": G.GATE1_RHO_MIN,
        "min_informative_targets": G.MIN_INFORMATIVE_TARGETS, "top_k": G.TOP_K,
    }
    # 스펙 §5 의 반복수. 연습 실행 결과가 커밋되면 여기서 걸린다.
    assert art["gate2_auc_calibration"]["reps"] == 400
    assert art["gate2_go_operating_characteristics"]["reps"] == 600
    for table in art["gate1_operating_characteristics"].values():
        assert table["reps"] == 600

    # 코호트는 로더에서 읽은 실제 기하다 - 합성 격자가 아니다.
    assert art["cohorts"]["gate2_mixed_all_sources"] == {
        "n_backbones": 37, "n_targets": 11, "n_folds": 888}
    assert art["cohorts"]["OC_primary_rfd3_only"] == {
        "n_backbones": 60, "n_informative_targets": 11, "n_folds": 1440}
    assert art["cohorts"]["OC_legacy_all_sources"] == {
        "n_backbones": 70, "n_informative_targets": 11, "n_folds": 1680}

    # 어떤 primitive 를 불렀는지 산출물이 말한다 - 재구현하면 이름이 어긋난다.
    assert art["primitives"]["lcb"] == "rapid_sr.clustered.one_sided_lcb"
    assert art["primitives"]["delta_top4"] == "_gate2d.delta_top4"
    assert art["primitives"]["within_target_spearman"] == "_gate2d.within_target_spearman"


def test_oc_artifact_reproduces_the_spec_gate2_calibration_table():
    """스펙 §5 AUC ↔ Δ_Top4 교정표를 재현한다 (400 반복, 타겟 등가중)."""
    rows = {r["delta"]: r for r in _oc()["gate2_auc_calibration"]["rows"]}
    for delta, (auc, delta_top4) in SPEC_GATE2_CALIBRATION.items():
        got = rows[delta]
        assert abs(got["mean_auc"] - auc) <= 0.005, (delta, got["mean_auc"], auc)
        # 400 반복 MC 노이즈. 최대 편차는 delta=0.60 의 0.005 다.
        assert abs(got["mean_delta_top4"] - delta_top4) <= 0.006, (
            delta, got["mean_delta_top4"], delta_top4)
    # oracle 열은 결정적이다 - 노이즈가 없으므로 인쇄된 자릿수에서 정확히 같다.
    assert round(rows["oracle"]["mean_delta_top4"], 3) == 0.326
    assert rows["oracle"]["mean_auc"] == 1.0


def test_oc_artifact_reproduces_the_spec_gate2_go_operating_characteristics():
    """스펙 §5 작동특성표 (n=11, 600 반복).

    **한 셀이 인쇄값과 다르다.** 귀무의 거짓 GO 가 0/600 이 아니라 1/600 이다.
    P(GO) 는 여전히 0.00 으로 인쇄되지만(0.0017), 스펙이 동결한 문장
    *"No false GO was observed in 600 null simulations (0/600)"* 의 **개수**는
    프로덕션 부트스트랩에서 재현되지 않는다. 임시 실행은 power 루프 안에서
    800 회를 썼고 여기는 20,000 회다. 문턱 +0.10 은 움직이지 않는다.
    스펙 문장을 고칠지는 controller 가 결정한다 - 여기서는 실제 값을 고정한다.
    """
    table = _oc()["gate2_go_operating_characteristics"]
    rows = {r["delta"]: r for r in table["rows"]}
    for delta, (true_delta, p_point, p_lcb, p_go) in SPEC_GATE2_OC.items():
        got = rows[delta]
        assert abs(got["true_mean_delta_top4"] - true_delta) <= 0.002, delta
        assert abs(got["p_point_ge_0.10"] - p_point) <= PROB_TOL, delta
        assert abs(got["p_lcb_gt_0"] - p_lcb) <= PROB_TOL, delta
        assert abs(got["p_go"] - p_go) <= PROB_TOL, delta

    # 세 조항 중 점추정이 통제를 담당한다 - P(GO) 는 P(점추정) 과 같아야 한다.
    for row in table["rows"]:
        assert row["p_go"] == row["p_point_ge_0.10"], row["delta"]

    false_go = table["false_go"]
    assert false_go["reps"] == 600
    assert false_go["count"] == 1, "인쇄된 0/600 이 아니다 - 보고 대상이다"
    assert false_go["frozen_sentence"] == (
        "observed false-GO rate 1/600 = 0.002; one-sided 95% upper bound 0.008")
    # rule-of-three 는 0 관측에만 유효하다 - 0 이 아닌 관측에 3/n 을 붙이지 않는다.
    assert false_go["upper_95_one_sided"] > 3.0 / 600


def test_oc_artifact_keeps_the_gate1_geometries_apart_by_name():
    """Gate 1 은 두 기하를 계산하고 이름으로 권위를 구분한다.

    §3 개정이 native 를 배분 풀에서 comparator 로 옮겼으므로 **판정 기하는
    RFD3-only** 다. 스펙 §3 에 인쇄된 표는 개정 전 70 백본(native 포함) 기하에서
    계산됐고, 아래가 그 사실을 데이터로 고정한다 - legacy 는 인쇄값을 재현하고
    primary 는 재현하지 않는다. **인쇄값과 맞는다는 것이 권위의 근거가 아니다.**
    """
    tables = _oc()["gate1_operating_characteristics"]
    assert tables["OC_primary_rfd3_only"]["status"] == "authoritative"
    assert tables["OC_legacy_all_sources"]["status"] == "historical reference only"
    # 실제 백본 수가 다르다: RFD3-only 는 타겟당 5, native 포함은 5~6.
    assert tables["OC_primary_rfd3_only"]["n_backbones_in_informative_targets"] == 55
    assert tables["OC_legacy_all_sources"]["n_backbones_in_informative_targets"] == 64
    for table in tables.values():
        assert table["n_informative_targets"] == 11  # 어느 기하에서도 11 이다

    # legacy 기하가 스펙 §3 인쇄값을 재현한다.
    rows = {r["sigma"]: r for r in tables["OC_legacy_all_sources"]["rows"]}
    for sigma, (rho, regret, p_go) in SPEC_GATE1_OC.items():
        got = rows[sigma]
        assert abs(got["mean_rho"] - rho) <= 0.01, sigma
        assert abs(got["mean_top1_regret"] - regret) <= 0.005, sigma
        for threshold, expected in zip(("0.00", "0.20", "0.25", "0.30"), p_go):
            assert abs(got["p_go"][f"rho>={threshold}"] - expected) <= PROB_TOL, (
                sigma, threshold)


def test_gate1_primary_geometry_is_frozen_with_its_own_numbers():
    """판정 기하(RFD3-only)의 재프리즈 대상 값.

    타겟당 백본이 6 -> 5 로 줄면 타겟내 Spearman 이 더 흔들리므로 귀무의 거짓
    GO 가 올라간다: ρ≥0.25 에서 **30/600 = 0.050** (legacy 인쇄값 0.03). 검정력도
    같은 이유로 조금 낮다(ρ≈0.33 에서 0.74, ρ≈0.44 에서 0.94). 문턱을 바꿀지는
    controller 가 결정한다 - 이 테스트는 판정 기하의 실제 값을 고정할 뿐이다.
    """
    table = _oc()["gate1_operating_characteristics"]["OC_primary_rfd3_only"]
    rows = {r["sigma"]: r for r in table["rows"]}
    frozen = "rho>=0.25"
    assert rows["null"]["p_go"][frozen] == 0.05
    assert rows[1.0]["p_go"][frozen] == 0.3133
    assert rows[0.5]["p_go"][frozen] == 0.7383
    assert rows[0.35]["p_go"][frozen] == 0.9383
    assert rows[0.25]["p_go"][frozen] == 0.9967
    assert [rows[s]["mean_rho"] for s in ("null", 1.0, 0.5, 0.35, 0.25)] == [
        0.0055, 0.1764, 0.3337, 0.4391, 0.5471]
    false_go = table["false_go_at_frozen_threshold"]
    assert (false_go["count"], false_go["reps"]) == (30, 600)
    assert false_go["frozen_sentence"] == (
        "observed false-GO rate 30/600 = 0.050; one-sided 95% upper bound 0.067")


def test_oc_artifact_is_bound_to_the_shipped_bootstrap_and_primitives():
    """표를 만든 코드가 바뀌면 여기서 먼저 깨진다.

    표 전체를 다시 돌리면 분 단위이므로, 산출물에 적힌 단일 반복 fixture 를
    **실제로 다시 계산해** 대조한다. `delta_top4`·`per_target_means`·
    `within_target_spearman`·`one_sided_lcb` 중 하나라도 동작이 바뀌면 이 두
    벡터나 두 LCB 가 어긋난다 - 그것이 이 산출물의 존재 이유다.
    """
    import importlib
    from rapid_sr.clustered import one_sided_lcb
    gen = importlib.import_module("26_gate2d_operating_characteristics")
    import _gate2d_cohort as C

    contracts = _oc()["contracts"]
    grid = C.load_holdout_grid()

    g2 = contracts["gate2_delta_top4"]
    deltas, _aucs, targets = gen.simulate_gate2_rep(
        C.mixed_backbones(grid), delta=0.50, rep=0)
    assert G.per_target_means(deltas, targets) == g2["per_target"]
    assert one_sided_lcb(g2["per_target"], alpha=G.LCB_ONE_SIDED_ALPHA,
                         n_boot=20000, seed=G.BOOTSTRAP_SEED) == g2["lcb"]

    g1 = contracts["gate1_spearman"]
    rfd3 = C.restrict_to_sources(grid, ("rfd3",))
    names, q_b = gen.gate1_units(rfd3)
    rhos, _regret = gen.simulate_gate1_rep(names, q_b, sigma=0.50, rep=0)
    assert list(rhos) == g1["targets"]
    assert list(rhos.values()) == g1["per_target"]
    assert one_sided_lcb(g1["per_target"], alpha=G.LCB_ONE_SIDED_ALPHA,
                         n_boot=20000, seed=G.BOOTSTRAP_SEED) == g1["lcb"]


def test_mutation_sites_against_wt():
    import importlib
    prep = importlib.import_module("22_gate2d_prepare_esm")
    # 길이가 같은 경우: 다른 위치만 돌려준다.
    assert prep.mutation_sites("AAAA", "ABAA") == [1]
    assert prep.mutation_sites("AAAA", "AAAA") == []
    # 길이가 다르면 비교가 성립하지 않는다 - 조용히 자르지 않고 예외를 낸다.
    try:
        prep.mutation_sites("AAAA", "AAA")
    except ValueError:
        pass
    else:
        raise AssertionError("길이 불일치에서 ValueError 가 나와야 한다")


def test_wt_sequence_from_pdb_handles_altloc_insertion_and_models(tmp_path):
    import importlib
    prep = importlib.import_module("22_gate2d_prepare_esm")
    pdb = tmp_path / "t.pdb"
    pdb.write_text(
        # 잔기 1 (altloc 두 개 - 하나로 세야 한다)
        "ATOM      1  CA AALA A   1      0.000   0.000   0.000  0.50 0.00           C\n"
        "ATOM      2  CA BALA A   1      0.000   0.000   0.000  0.50 0.00           C\n"
        # 삽입코드 - 1 과 1A 는 다른 잔기다
        "ATOM      3  CA  GLY A   1A     1.000   0.000   0.000  1.00 0.00           C\n"
        # CA 가 없는 잔기는 서열에 들어가지 않는다
        "ATOM      4  N   SER A   2      2.000   0.000   0.000  1.00 0.00           N\n"
        "ATOM      5  CA  VAL A   3      3.000   0.000   0.000  1.00 0.00           C\n"
        # 표준이 아닌 잔기는 X
        "ATOM      6  CA  MSE A   4      4.000   0.000   0.000  1.00 0.00           C\n",
        encoding="utf-8")
    assert prep.wt_sequence_from_pdb(pdb) == "AGVX"


def test_wt_sequence_from_pdb_collapses_nmr_models():
    """격자에 26 모델(1tm9A00)과 20 모델(2jokA01) NMR 앙상블이 있다.

    모델을 접지 않으면 WT 길이가 26 배가 되어 mutation_sites 가 전부 raise 하고
    두 타겟이 조용히 S3/S5/S6 에서 사라진다.
    """
    import importlib, os
    from pathlib import Path
    prep = importlib.import_module("22_gate2d_prepare_esm")
    root = Path(os.environ.get("PROTEIN_PIPELINE_ROOT", ".")).resolve()
    d = root / "public_data" / "benchmark" / "gate0" / "holdout_targets_pdb"
    # 스펙 §3 이 고정한 길이. 26 개 모델을 접은 결과여야 한다.
    assert len(prep.wt_sequence_from_pdb(d / "1tm9A00.pdb")) == 137
    assert len(prep.wt_sequence_from_pdb(d / "2jokA01.pdb")) == 184


def test_frozen_wt_covers_the_grid_and_matches_the_reader():
    """층 2: 실제 홀드아웃 회귀. parser·normalization drift 를 잡는다."""
    import importlib
    from pathlib import Path
    import _gate2d_cohort as C
    prep = importlib.import_module("22_gate2d_prepare_esm")
    grid = C.load_holdout_grid()
    assert set(C.FROZEN_WT) == set(grid.targets)          # 12 타겟 전부
    d = C.GATE0 / "holdout_targets_pdb"
    wt = {t: prep.wt_sequence_from_pdb(d / f"{t}.pdb") for t in grid.targets}
    C.assert_sequence_axis(wt)                            # 통과해야 한다

    # 한 글자만 바꿔도 fail-closed 인지 확인한다 - 길이는 그대로다.
    broken = dict(wt)
    t0 = sorted(wt)[0]
    broken[t0] = ("A" if wt[t0][0] != "A" else "C") + wt[t0][1:]
    assert len(broken[t0]) == len(wt[t0])
    try:
        C.assert_sequence_axis(broken)
    except SystemExit:
        pass
    else:
        raise AssertionError("같은 길이의 다른 서열이 통과했다 - 길이만 보고 있다")


def test_assert_sequence_axis_reports_a_missing_target():
    """서열이 없는 타겟도 fail-closed 다 - 조용히 건너뛰지 않는다."""
    import _gate2d_cohort as C
    with pytest.raises(SystemExit) as excinfo:
        C.assert_sequence_axis({})
    message = str(excinfo.value)
    for target in C.FROZEN_WT:
        assert f"{target}: WT 서열이 없다" in message


# --- Step 5 정렬 가드 -------------------------------------------------------
# 원래 가드(`tokens.shape[0] != len(seq)`)는 발동할 수 없었다. `hidden` 이 배치
# 최대 폭으로 padding 되므로 slice 가 항상 정확히 `len(seq)` 행을 낸다. 개정된
# 가드는 attention 기준 잔기 수와 0 번 토큰의 정체를 본다. 아래 두 테스트가
# 그 두 조건을 각각 발동시킨다.

class _StubTokenizer:
    """ESM char-level tokenizer 의 padding 동작을 흉내낸다.

    `drop_bos=True` 는 **개수를 유지하면서 BOS 를 빼는** 변화다 - attention
    길이는 그대로 `len(seq) + 2` 이므로 잔기 수 검사는 통과하고, 잔기는 한 칸
    밀린다. 이것이 원래 가드의 사각지대였다.
    """

    cls_token_id = 0
    eos_token_id = 2
    pad_token_id = 1

    def __init__(self, *, drop_bos: bool = False, short_mask: bool = False):
        self._drop_bos = drop_bos
        self._short_mask = short_mask

    def __call__(self, chunk, return_tensors=None, padding=None):
        import torch
        width = max(len(s) for s in chunk) + 2
        ids = torch.full((len(chunk), width), self.pad_token_id, dtype=torch.long)
        mask = torch.zeros((len(chunk), width), dtype=torch.long)
        for row, seq in enumerate(chunk):
            n = len(seq)
            if self._drop_bos:
                ids[row, :n] = 7                     # <cls> 없이 잔기부터
                ids[row, n] = self.eos_token_id
                ids[row, n + 1] = self.eos_token_id  # 폭을 채워 개수를 유지한다
            else:
                ids[row, 0] = self.cls_token_id
                ids[row, 1:1 + n] = 7
                ids[row, 1 + n] = self.eos_token_id
            attended = n + 2 - (1 if self._short_mask else 0)
            mask[row, :attended] = 1
        return {"input_ids": ids, "attention_mask": mask}


def _stub_hidden(input_ids, dim):
    """hidden[row, pos, :] == pos. 슬라이스가 어디를 읽는지 값으로 보인다."""
    import torch
    rows, width = input_ids.shape
    return (torch.arange(width, dtype=torch.float32)
            .reshape(1, width, 1).repeat(rows, 1, dim).contiguous())


class _StubModel:
    def __init__(self, dim):
        self._dim = dim

    def to(self, device):
        return self

    def eval(self):
        return self

    def __call__(self, **batch):
        import types
        return types.SimpleNamespace(
            last_hidden_state=_stub_hidden(batch["input_ids"], self._dim))


def _patch_embed_backends(monkeypatch, prep, tokenizer):
    import types
    monkeypatch.setattr(prep, "AutoTokenizer", types.SimpleNamespace(
        from_pretrained=lambda name: tokenizer))
    monkeypatch.setattr(prep, "EsmModel", types.SimpleNamespace(
        from_pretrained=lambda name: _StubModel(prep.EMB_DIM)))


def test_embed_is_aligned_and_the_old_guard_could_not_fire(monkeypatch):
    """정상 경로: BOS 를 건너뛴 슬라이스가 잔기 1..len(seq) 를 읽는다."""
    import importlib
    import torch
    prep = importlib.import_module("22_gate2d_prepare_esm")
    chunk = ["ACDEF", "GHI"]
    tokenizer = _StubTokenizer()
    _patch_embed_backends(monkeypatch, prep, tokenizer)

    pooled, per_token = prep.embed(chunk, device=torch.device("cpu"), batch_size=8)
    assert pooled.shape == (2, prep.EMB_DIM)
    for seq, tokens in zip(chunk, per_token):
        assert tokens.shape == (len(seq), prep.EMB_DIM)
        # hidden[row, pos] == pos 이므로 1..len(seq) 가 나와야 정렬이 맞다.
        assert tokens[:, 0].tolist() == [float(p) for p in range(1, 1 + len(seq))]


def test_embed_guard_catches_bos_drop_that_preserves_the_residue_count(monkeypatch):
    """사각지대: 개수는 맞고 BOS 만 없는 입력. 원래 가드는 통과시켰다."""
    import importlib
    import torch
    prep = importlib.import_module("22_gate2d_prepare_esm")
    chunk = ["ACDEF", "GHI"]
    tokenizer = _StubTokenizer(drop_bos=True)

    # 1) 원래 가드가 왜 무력했는지 같은 입력으로 보인다 - 슬라이스 행 수는 맞고,
    #    attention 기준 잔기 수도 맞다. 다른 것은 0 번 토큰뿐이다.
    batch = tokenizer(chunk, return_tensors="pt", padding=True)
    hidden = _stub_hidden(batch["input_ids"], prep.EMB_DIM)
    for row, seq in enumerate(chunk):
        assert hidden[row, 1:1 + len(seq)].shape[0] == len(seq)   # 원래 가드: 통과
        assert int(batch["attention_mask"][row].sum()) - 2 == len(seq)
        assert int(batch["input_ids"][row, 0]) != tokenizer.cls_token_id
        # 그리고 실제로 잔기가 한 칸 밀린다 - 0 번 잔기를 읽지 못한다.
        assert hidden[row, 1:1 + len(seq)][0, 0].item() == 1.0

    # 2) 개정된 가드는 잡는다.
    _patch_embed_backends(monkeypatch, prep, tokenizer)
    with pytest.raises(SystemExit, match="<cls>"):
        prep.embed(chunk, device=torch.device("cpu"), batch_size=8)


def test_embed_guard_catches_a_residue_count_that_disagrees(monkeypatch):
    """두 번째 조건: attention 기준 잔기 수가 서열과 다르면 중단한다."""
    import importlib
    import torch
    prep = importlib.import_module("22_gate2d_prepare_esm")
    tokenizer = _StubTokenizer(short_mask=True)
    _patch_embed_backends(monkeypatch, prep, tokenizer)
    with pytest.raises(SystemExit, match="attention 기준 잔기"):
        prep.embed(["ACDEF"], device=torch.device("cpu"), batch_size=8)


# ---------------------------------------------------------------------------
# Task 11 - Gate 2 feature ladder. S0-S3 구간만 구현돼 있고 S4-S6 는 msa_features.json
# 이 도착한 뒤에 붙는다. 아래 테스트는 그 경계를 계약으로 고정한다.
# ---------------------------------------------------------------------------


def test_arm_ladder_is_frozen_and_s6_is_primary():
    import _gate2d_features as F
    assert list(F.ARMS) == ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
    assert F.PRIMARY_ARM == "S6"
    # S2 는 known null 이 아니다 - LOTO 에서 타겟별 translation 이므로 S1 과 다르다.
    assert F.ARM_STATUS["S1"] == "known_null"
    assert F.ARM_STATUS["S2"] == "untested_low_expectation"
    assert F.ARM_STATUS["S6"] == "primary"


def test_loto_splits_never_share_a_target():
    import _gate2d_features as F
    targets = ["A", "A", "B", "B", "C"]
    for train_idx, test_idx, held in F.loto_splits(targets):
        train_targets = {targets[i] for i in train_idx}
        test_targets = {targets[i] for i in test_idx}
        assert test_targets == {held}
        assert held not in train_targets
        assert not (train_targets & test_targets)
    assert len(list(F.loto_splits(targets))) == 3


def test_build_features_shapes_and_non_evaluable():
    """S0-S3 의 shape. S6 > S5 열수 비교는 MSA 블록이 붙은 뒤에 온다.

    스펙 §4 의 ladder 는 7 arm 이지만 `msa_features.json` 이 아직 없다. 없는
    데이터를 가짜로 채우지 않으므로 여기서는 S0-S3 만 검증하고, S4-S6 는 아래
    `test_msa_arms_are_an_unstubbed_seam` 이 "아직 구현되지 않았다" 를 계약으로
    고정한다.
    """
    import numpy as np
    import _gate2d_cohort as C
    import _gate2d_features as F
    grid = C.load_holdout_grid()

    # S0 은 SoluProt 한 열이다.
    x0 = F.build_features("S0", grid.folds)
    assert x0.shape == (len(grid.folds), 1)

    # S1 은 ESM mean 320 열, S2 도 320 열(값은 다르다).
    x1 = F.build_features("S1", grid.folds)
    x2 = F.build_features("S2", grid.folds)
    assert x1.shape == (len(grid.folds), 320)
    assert x2.shape == (len(grid.folds), 320)
    # 같은 shape 이지만 같은 행렬이 아니다 - ΔESM_global 은 타겟별 translation 이다.
    assert not np.allclose(x1, x2)

    # S3 은 ΔESM_mut 320 열 + 결측 지시자 1 열이다.
    x3 = F.build_features("S3", grid.folds)
    assert x3.shape == (len(grid.folds), 321)

    # 알 수 없는 arm 은 조용히 넘어가지 않는다.
    try:
        F.build_features("S9", grid.folds)
    except KeyError:
        pass
    else:
        raise AssertionError("정의되지 않은 arm 에서 KeyError 가 나와야 한다")


def test_msa_arms_need_a_train_fold_and_never_fabricate_one():
    """이 테스트의 이전 판(`..._are_an_unstubbed_seam`)은 S4-S6 가 아직 구현되지
    않았다는 것을 계약으로 고정하고 있었다. 2026-09-11 에 MSA 12/12 가 도착해
    구현이 붙었으므로 그 계약은 더 이상 참이 아니다. **계약을 지우는 것이 아니라
    옮긴다** - 지금 지켜야 하는 것은 "가짜 데이터로 채우지 않는다" 쪽이다.

    MSA 블록의 대치 통계량은 LOTO train fold 의 **타겟 평균**이므로 fold 밖에서는
    정의되지 않는다. train fold 없이 불렀을 때 코호트 전체를 train 으로 삼아
    조용히 행렬을 내놓으면 그것이 누수다. 그래서 거절한다.
    """
    import _gate2d_cohort as C
    import _gate2d_features as F
    grid = C.load_holdout_grid()
    for arm in ("S4", "S5", "S6"):
        assert "msa" in F.ARM_BLOCKS[arm]
        with pytest.raises(ValueError, match="train fold"):
            F.build_features(arm, grid.folds[:8])
        # train fold 를 주면 실제 행렬이 나온다 - seam 이 채워졌다.
        matrix, defect = F.assemble(arm, grid.folds[:8], train_idx=[0, 1, 2, 3])
        assert defect is None
        assert matrix.shape[0] == 8


def test_delta_esm_mut_uses_sequence_mutation_sites_not_embedding_difference():
    """S3 의 변이 위치는 **서열 비교**에서 온다. 임베딩 차이에서 오지 않는다.

    ESM 토큰은 문맥 의존이므로 한 잔기만 바뀌어도 **모든** 위치의 임베딩이
    달라진다. `|design_tok - wt_tok|` 이 0 이 아닌 위치를 "변이" 로 삼으면 전
    위치가 뽑히고, 그 평균은 mean-pool(design) - mean-pool(WT) 즉 **ΔESM_global
    과 정확히 같아진다.** 그러면 S3 이 S2 의 복제가 되어 ladder 가 한 칸 무너진다.
    """
    import importlib
    import numpy as np
    import _gate2d_cohort as C
    import _gate2d_features as F

    grid = C.load_holdout_grid()
    folds = grid.folds[:24]
    prep = importlib.import_module("22_gate2d_prepare_esm")
    wt = F.wt_by_target()

    # 1) 실제 코호트에서 변이 위치는 전 위치가 아니다.
    n_mut = len(prep.mutation_sites(wt[folds[0].target_id], F.SEQ_OF[folds[0].sequence_id]))
    seq_len = len(wt[folds[0].target_id])
    assert 0 < n_mut < seq_len, "이 서열이 전위치 변이면 이 테스트가 무의미하다"

    # 2) 따라서 S3 블록은 S2 블록과 같지 않다.
    mut = F.build_features("S3", folds)[:, :320]
    glob = F.build_features("S2", folds)
    assert not np.allclose(mut, glob), "S3 이 ΔESM_global 로 붕괴했다"


def test_s3_keeps_a_length_mismatched_design_with_an_indicator():
    """스펙 §4 결측 규칙: 위치 대응이 불가하면 대치 + 지시자다. 타겟을 빼지 않는다.

    `3es1A01|target|target` 의 24 설계는 길이가 WT 와 달라 `mutation_sites` 가
    raise 한다. 그 행이 조용히 사라지거나 예외로 실행을 죽이면 규칙 4 위반이다.
    """
    import numpy as np
    import _gate2d_cohort as C
    import _gate2d_features as F

    grid = C.load_holdout_grid()
    healthy = [f for f in grid.folds if f.target_id == "3es1A01"][:3]
    assert healthy, "3es1A01 이 코호트에 있어야 한다"
    broken_id = "3es1A01|target|target|g0"
    assert broken_id in F.SEQ_OF
    broken = C.Fold(broken_id, "3es1A01|target|target", "3es1A01",
                    90.0, 1.0, 0.9, "target")
    folds = [*healthy, broken]

    x = F.build_features("S3", folds)
    assert x.shape == (4, 321)                     # 행이 사라지지 않았다
    assert x[:3, -1].tolist() == [0.0, 0.0, 0.0]   # 건강한 행은 지시자 0
    assert x[3, -1] == 1.0                         # 결측 행은 지시자 1
    assert np.allclose(x[3, :320], 0.0)            # 결측 행의 ΔESM 은 채워진 값
    assert not np.allclose(x[0, :320], 0.0)


def test_assemble_returns_a_matrix_and_no_defect_for_msa_free_arms():
    """`assemble` 이 `build_features` 를 대체한다 (Step 8b 정정).

    MSA 없는 arm 은 fold 에 의존하지 않으므로 train_idx 가 무엇이든 같은 행렬이다.
    """
    import numpy as np
    import _gate2d_cohort as C
    import _gate2d_features as F
    folds = C.load_holdout_grid().folds[:48]
    a, defect_a = F.assemble("S3", folds, train_idx=[0, 1, 2])
    b, defect_b = F.assemble("S3", folds, train_idx=list(range(24)))
    assert defect_a is None and defect_b is None
    assert np.array_equal(a, b)


def test_gate2_runner_fails_closed_on_a_perturbed_sequence_axis(monkeypatch, tmp_path):
    """서열 축은 hard precondition 이다 (스펙 §4). 게이트는 그것을 **호출한다.**

    호출하지 않으면 보존 마스크와 변이 인덱스가 어긋난 좌표에서 계산되고
    아무 오류도 나지 않는다.
    """
    import importlib
    import _gate2d_features as F
    gate2 = importlib.import_module("25_gate2_within_backbone_selectability")

    good = F.wt_by_target()
    target = sorted(good)[0]
    seq = good[target]
    # 길이는 같고 잔기 두 개만 뒤바뀐 서열. 길이 검사만 하는 가드는 통과시킨다.
    perturbed = dict(good)
    perturbed[target] = seq[1] + seq[0] + seq[2:]
    assert len(perturbed[target]) == len(seq) and perturbed[target] != seq

    monkeypatch.setattr(F, "wt_by_target", lambda: perturbed)
    with pytest.raises(SystemExit) as excinfo:
        gate2.main(["--arms", "S0", "--out", str(tmp_path / "x.json")])
    assert "서열 축" in str(excinfo.value)
    assert target in str(excinfo.value)


def test_gate2_reports_undecided_without_the_primary_arm(tmp_path, monkeypatch):
    """S6 없이 GO/NO-GO 를 내면 스펙 위반이다. S0-S3 만 돌면 UNDECIDED 다."""
    import importlib
    import json as _json
    gate2 = importlib.import_module("25_gate2_within_backbone_selectability")
    out = tmp_path / "interim.json"
    assert gate2.main(["--arms", "S0", "--out", str(out)]) == 0
    payload = _json.loads(out.read_text(encoding="utf-8"))
    assert payload["verdict"] == "UNDECIDED"
    assert payload["primary_arm"] == "S6"
    assert payload["interim"] is True
    assert "interim" in payload["verdict_note"]
    assert payload["cohort"]["mixed_backbones"] == 37
    assert payload["cohort"]["informative_targets"] == 11
    s0 = payload["arms_joint_pass"]["S0"]
    assert s0["informative_targets"] == 11
    assert s0["status"] == "measured_reference"


# ---------------------------------------------------------------------------
# Task 9 Step 6 / Task 11 S4-S6. MSA conservation feature 와 그 대치.
# 2026-09-11, MSA 12/12 완료 후 추가.
# ---------------------------------------------------------------------------


def test_mutation_sites_and_conserved_positions_share_a_zero_base():
    """두 인덱스가 같은 base 위에 있음을 **주석이 아니라 테스트로** 고정한다.

    보존 마스크(1-기반 배포 출력)와 변이 위치(0-기반 enumerate)를 섞으면 마스크가
    한 칸 밀리고 `|M_i ∩ F_tier|` 는 아무 오류도 내지 않으면서 잡음을 잰다.
    """
    import importlib
    import json as _json
    esm = importlib.import_module("22_gate2d_prepare_esm")
    # mutation_sites 는 enumerate 기반이므로 첫 잔기가 다르면 0 을 돌려준다.
    # 1-기반이라면 이 값이 1 이어야 한다. 0 이 나오는 것이 base 를 고정한다.
    assert esm.mutation_sites("AAAA", "BAAA") == [0]

    # 산출물 쪽도 0-기반이다. 키 이름에 base 가 박혀 있다.
    path = (ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
            / "msa_features.json")
    feats = _json.loads(path.read_text(encoding="utf-8"))
    assert "conserved_positions_0based" in feats
    assert "conserved_positions" not in feats, "base 없는 키 이름은 섞는 실수를 부른다"
    import _gate2d_cohort as C
    for target, tiers in feats["conserved_positions_0based"].items():
        length = C.FROZEN_WT[target][1]
        for _tier, positions in tiers.items():
            # 0-기반이면 [0, L-1] 안에 있다. 1-기반이면 L 이 나올 수 있다.
            assert min(positions) >= 0
            assert max(positions) <= length - 1
    # 적어도 한 타겟은 0 번 위치를 잡는다 - 전부 1 이상이면 1-기반과 구분되지 않는다.
    assert any(0 in positions
               for tiers in feats["conserved_positions_0based"].values()
               for positions in tiers.values())


def test_msa_features_artifact_verified_its_provenance_against_the_manifest():
    """Step 6 산출물은 manifest 의 `fixed_positions_sha256` 과 대조돼 있어야 한다.

    manifest 는 tier 의 **개수와 해시만** 담는다. 위치 집합은 P3 가 다시 계산하므로
    provenance 를 확인하지 않으면 다른 a3m 에서 나온 마스크가 조용히 들어올 수 있다.
    """
    import json as _json
    gate0 = ROOT / "public_data" / "benchmark" / "gate0"
    feats = _json.loads((gate0 / "holdout_grid" / "msa_features.json")
                        .read_text(encoding="utf-8"))
    manifest = _json.loads((gate0 / "holdout_grid" / "holdout_msa_manifest.json")
                           .read_text(encoding="utf-8"))

    assert len(feats["per_target"]) == 12
    assert set(feats["conserved_positions_sha256_verified"].values()) == {True}

    tiers_by_target = {e["domain"]: e["conservation"]["tiers"] for e in manifest["targets"]}
    for target, tiers in feats["conserved_positions_0based"].items():
        assert {t: len(v) for t, v in tiers.items()} == tiers_by_target[target]

    # 서열 축: a3m query 의 sha256 이 동결 WT 와 같다 (스펙 §4 규칙 8).
    import _gate2d_cohort as C
    for target, sha in feats["query_sequence_sha256"].items():
        assert sha == C.FROZEN_WT[target][0]


def test_msa_features_records_usable_hits_and_the_low_depth_indicator():
    """스펙 §4 규칙 6. 저심도는 **제외가 아니라 가시화**다."""
    import importlib
    import json as _json
    prep = importlib.import_module("23_gate2d_prepare_msa_features")
    feats = _json.loads((ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
                         / "msa_features.json").read_text(encoding="utf-8"))

    assert prep.LOW_DEPTH_MIN_USABLE_HITS == 10
    for target, row in feats["per_target"].items():
        assert "usable_hits" in row, f"{target}: usable_hits 를 그대로 기록해야 한다"
        assert row["msa_low_depth"] == prep.is_low_depth(row["usable_hits"])

    # 실측: 저심도는 1tm9A00 하나이고 타겟은 12 개 그대로다.
    assert feats["low_depth"]["targets"] == ["1tm9A00"]
    assert feats["low_depth"]["n"] == 1
    assert feats["per_target"]["1tm9A00"]["usable_hits"] == 3
    # 문턱 위에 있는 borderline 은 저심도가 아니다 - 문턱을 46 위로 올리지 않는다.
    assert feats["per_target"]["2jokA01"]["usable_hits"] == 46
    assert feats["per_target"]["2jokA01"]["msa_low_depth"] == 0
    assert len(feats["per_target"]) == 12, "어떤 경우에도 타겟을 빼지 않는다"


def test_usable_hits_is_metadata_not_a_feature():
    """`usable_hits` 는 `per_target` 에 실리지만 설계행렬로 가지 않는다.

    그대로 `impute()` 에 넘기면 `_defined()` 의 오타 가드가 이름을 모른다고
    거절한다 - 그 가드를 죽이지 않으면서 규칙 6 을 지키는 경로가 `feature_view` 다.
    """
    import importlib
    import pytest as _pytest
    prep = importlib.import_module("23_gate2d_prepare_msa_features")
    row = {"cons_mean": 0.7, "usable_hits": 3, "msa_low_depth": 1}
    assert prep.feature_view(row) == {"cons_mean": 0.7}
    assert prep.feature_view(None) is None
    # 모르는 이름은 여전히 거절된다 - feature_view 가 오타를 삼키지 않는다.
    with _pytest.raises(ValueError, match="cons_meen"):
        prep.impute("C", prep.feature_view({"cons_meen": 0.7, "usable_hits": 3}),
                    train_stats={"cons_mean": 0.7})


def test_s4_distinguishes_two_designs_that_hit_different_conservation():
    """이 테스트가 통과하지 않으면 S4 를 Gate 2 feature 라고 부를 수 없다.

    타겟 수준 상수만 넣으면 같은 백본의 24 설계가 동일한 행을 받고 백본 **내부**
    순위가 원리상 만들어지지 않는다.
    """
    import _gate2d_features as F
    conserved = {"0.3": [0, 1, 2, 3], "0.5": [0, 1, 2, 3, 4, 5], "0.7": list(range(8))}
    # 같은 타겟·같은 백본·변이 수 동일(4개). A 는 tier30 보존 위치만, B 는 비보존만.
    a = F.conservation_burden([0, 1, 2, 3], conserved)
    b = F.conservation_burden([20, 21, 22, 23], conserved)
    assert a == [1.0, 1.0, 1.0]
    assert b == [0.0, 0.0, 0.0]
    assert a != b, "S4 가 보존 위치를 건드린 설계를 구분하지 못한다"

    # 변이가 없으면 0으로 나누지 않는다.
    assert F.conservation_burden([], conserved) == [0.0, 0.0, 0.0]


def test_s4_actually_varies_within_a_backbone_in_the_real_cohort():
    """합성 예제가 아니라 실제 격자에서 백본 내부 변동이 0 이 아님을 본다.

    스펙 §4 의 측정: 24 설계의 변이 위치 집합은 전부 distinct 하다. 그러면
    `r_tier` 도 백본 안에서 달라야 한다 - 정확히 0 이면 S4 는 tie-break 만 남는다.
    """
    import numpy as np
    import _gate2d_cohort as C
    import _gate2d_features as F
    grid = C.load_holdout_grid()
    one_backbone = [f for f in grid.folds
                    if f.backbone_key == grid.folds[0].backbone_key
                    and f.target_id == grid.folds[0].target_id]
    assert len(one_backbone) > 1
    block = F._msa_candidate_block(one_backbone)
    burden = block[:, :3]
    assert (burden.std(axis=0) > 0).all(), "백본 안에서 r_tier 가 상수다"
    # 채움 지시자는 이 코호트에서 0 이다 (길이 불일치 설계는 사용가능 폴드에 없다).
    assert np.allclose(block[:, -1], 0.0)


def test_conservation_burden_reads_mutation_sites_from_sequences_only():
    """"차이가 0 인 곳" 을 마스크로 쓰지 않는다.

    S3 이 그 방식으로 무너진 전례가 있다 (ESM 토큰은 문맥 의존이라 전 위치가
    "변이" 로 뽑혔다). S4 의 변이 위치는 서열 비교 하나에서만 온다.
    """
    import importlib
    import _gate2d_cohort as C
    import _gate2d_features as F
    esm = importlib.import_module("22_gate2d_prepare_esm")

    grid = C.load_holdout_grid()
    fold = grid.folds[0]
    wt = F.wt_by_target()[fold.target_id]
    design = F.SEQ_OF[fold.sequence_id]
    sites = esm.mutation_sites(wt, design)
    assert 0 < len(sites) < len(wt), "전 위치가 변이면 이 테스트가 무의미하다"

    conserved = F.load_msa_features()["conserved_positions_0based"][fold.target_id]
    expected = F.conservation_burden(sites, conserved)
    got = F._msa_candidate_block([fold])[0]
    assert list(got[:3]) == expected
    assert abs(got[3] - len(sites) / len(wt)) < 1e-12


def test_msa_imputation_weights_targets_equally_not_rows():
    """타겟마다 행 수가 120/144 로 다르다. 행 평균은 타겟을 불균등 가중한다."""
    import importlib
    import _gate2d_features as F
    prep = importlib.import_module("23_gate2d_prepare_msa_features")

    # 타겟 A 는 행 2개, B 는 행 1개. 값은 A=0.0, B=0.9. C 는 정의되지 않음.
    names = list(prep.TARGET_FEATURES)
    per_target = {"A": {n: 0.0 for n in names}, "B": {n: 0.9 for n in names},
                  "C": None}
    row_targets = ["A", "A", "B", "C"]
    train_idx = [0, 1, 2]          # A, A, B
    block, defect = F.impute_msa_block(per_target, row_targets, train_idx, names)
    assert defect is None
    # 타겟 등가중 = (0.0 + 0.9)/2 = 0.45.  행 평균이면 (0+0+0.9)/3 = 0.30.
    c_row = row_targets.index("C")
    assert abs(block[c_row][0] - 0.45) < 1e-12, "행 평균으로 대치하고 있다"
    # 마지막 두 열은 지시자다: msa_undefined, msa_low_depth.
    assert block[c_row][-2] == 1.0            # msa_undefined
    assert block[0][-2] == 0.0                # A 는 정의됨
    assert F._active_target_names({n: 0.0 for n in names}, names)[-2:] == [
        "msa_undefined", "msa_low_depth"]


def test_msa_low_depth_indicator_is_never_imputed_away():
    """저심도 지시자는 대치 대상이 아니다.

    train 평균으로 번지면 "얼마나 얕은가" 가 다른 타겟으로 새어 나가고, 홀드아웃
    타겟이 자기 depth 가 아니라 이웃의 depth 를 들고 들어간다.
    """
    import importlib
    import _gate2d_features as F
    prep = importlib.import_module("23_gate2d_prepare_msa_features")
    names = list(prep.TARGET_FEATURES)
    per_target = {
        "shallow": {**{n: 0.1 for n in names}, "usable_hits": 3},
        "deep1": {**{n: 0.5 for n in names}, "usable_hits": 3000},
        "deep2": {**{n: 0.9 for n in names}, "usable_hits": 3000},
    }
    row_targets = ["shallow", "deep1", "deep2"]
    # shallow 를 홀드아웃했다 - train 은 deep 둘뿐이라 평균 지시자는 0 이 된다.
    block, defect = F.impute_msa_block(per_target, row_targets, [1, 2], names)
    assert defect is None
    assert block[0][-1] == 1.0, "홀드아웃 저심도 타겟의 지시자가 사라졌다"
    assert block[1][-1] == 0.0 and block[2][-1] == 0.0


def test_msa_arm_is_non_evaluable_when_the_train_fold_defines_nothing():
    """스펙 §4 규칙 5 - 유일한 non-evaluable 사유다. **타겟을 빼지 않는다.**"""
    import importlib
    import _gate2d_features as F
    prep = importlib.import_module("23_gate2d_prepare_msa_features")
    names = list(prep.TARGET_FEATURES)
    per_target = {"A": None, "B": None, "C": {n: 0.5 for n in names}}
    block, defect = F.impute_msa_block(per_target, ["A", "B", "C"], [0, 1], names)
    assert block is None
    assert defect is None      # train_stats 자체가 None 인 경우

    # 측정값을 버려야 하는 경우는 결함으로 표면화된다 (규칙 2 위반).
    per_target2 = {"A": {"cons_mean": 0.5}, "B": {"cons_mean": 0.6},
                   "C": {n: 0.5 for n in names}}
    block2, defect2 = F.impute_msa_block(per_target2, ["A", "B", "C"], [0, 1], names)
    assert block2 is None
    assert defect2["evaluable"] is False
    assert defect2["dropped_measured_by_target"]["C"]


def test_full_ladder_shapes_and_s6_is_wider_than_s5():
    """동결된 Step 7 계약 - S6 는 S5 보다 열이 많다.

    2026-09-11: cheap 블록이 스펙 §4 대로 "조성 + MPNN score" 가 되어 S6 의 열이
    20 에서 21 로 늘었다. 계약(S6 > S5)은 그대로이고 폭만 바뀐다 - 이전 +20 은
    MPNN score 열이 없던 PRIMARY DEVIATION 을 굳혀 둔 값이었다.
    """
    import _gate2d_cohort as C
    import _gate2d_features as F
    grid = C.load_holdout_grid()
    folds = grid.folds
    train_idx = list(range(len(folds) - 144))

    x4, _ = F.assemble("S4", folds, train_idx)
    x5, _ = F.assemble("S5", folds, train_idx)
    x6, _ = F.assemble("S6", folds, train_idx)
    # S4 = candidate 5 열 + 타겟 6 열 + 지시자 2 열.
    assert x4.shape == (len(folds), len(F.CANDIDATE_MSA_FEATURES) + 6 + 2)
    assert x5.shape == (len(folds), 321 + x4.shape[1])       # ΔESM_mut + MSA
    assert x6.shape == (len(folds), x5.shape[1] + 21)        # + 조성 20 + MPNN score 1
    assert x6.shape[1] > x5.shape[1]
    assert len(F.active_msa_feature_names(folds, train_idx)) == x4.shape[1]


def test_gate2_official_artifact_is_the_frozen_verdict():
    """공식 산출물. 판정 arm 은 S6 하나이고 GO 규칙은 스펙 §5 그대로다."""
    import json as _json
    payload = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0"
         / "gate2_within_backbone_selectability.json").read_text(encoding="utf-8"))

    assert payload["primary_arm"] == "S6"
    assert payload["interim"] is False
    assert payload["verdict"] in ("GO", "NO-GO")
    assert payload["cohort"]["mixed_backbones"] == 37
    assert payload["cohort"]["informative_targets"] == 11

    primary = payload["arms_joint_pass"]["S6"]
    assert primary["status"] == "primary"
    assert primary["informative_targets"] == 11
    go = (primary["meets_threshold"] and primary["lcb_exceeds_zero"]
          and primary["informative_targets"] >= 8)
    assert payload["verdict"] == ("GO" if go else "NO-GO")

    # 동결 문구는 93% 다. 최초 동결본의 94% 는 controller 임시 실행값이었다.
    assert "93%" in payload["no_go_reading"]
    assert "94%" not in payload["no_go_reading"]

    # 규칙 6: 저심도 목록·수와 민감도가 1 차 판정과 나란히 있어야 한다.
    report = payload["msa_low_depth_report"]
    assert report["low_depth_targets"] == ["1tm9A00"]
    assert report["n_low_depth"] == 1
    sens = primary["sensitivity_excluding_low_depth"]
    assert sens["evaluable"] is True
    assert sens["informative_targets"] == 10        # floor 8 을 넘는다
    assert sens["excluded_low_depth_targets"] == ["1tm9A00"]

    # fold 별 사용 열이 남아 있어야 narrowing 을 감사할 수 있다.
    assert len(primary["active_msa_feature_names"]) == 12

    # 스펙과의 차이가 기록돼 있다 (격자에 per-sequence MPNN score 가 없다).
    assert "MPNN" in payload["s6_cheap_block_deviation"]["implemented"] or \
           "MPNN" in payload["s6_cheap_block_deviation"]["reason"]

    # 모든 arm 이 두 endpoint 에서 11 타겟을 그대로 쓴다 - 타겟을 빼지 않았다.
    for key in ("arms_joint_pass", "arms_structural_pass_secondary"):
        for arm, row in payload[key].items():
            assert row["informative_targets"] == 11, arm


def test_gate2_reference_points_reproduce_the_interim_s0_to_s3():
    """S4-S6 를 붙이면서 S0-S3 를 건드리지 않았음을 산출물로 고정한다."""
    import json as _json
    payload = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0"
         / "gate2_within_backbone_selectability.json").read_text(encoding="utf-8"))
    joint = payload["arms_joint_pass"]
    assert joint["S0"]["delta_top4_target_equal"] == -0.0014
    assert joint["S1"]["delta_top4_target_equal"] == 0.0384
    assert joint["S2"]["delta_top4_target_equal"] == -0.0188
    assert joint["S3"]["delta_top4_target_equal"] == -0.0029


def test_low_depth_sensitivity_withholds_itself_below_the_floor():
    """규칙 6 의 '4 이상' 구간 - 민감도가 floor 미달이면 non-evaluable 이다.

    조용히 확인 없는 판정으로 두지 않는다.
    """
    import importlib
    gate2 = importlib.import_module("25_gate2_within_backbone_selectability")
    per_target = {f"t{i}": 0.2 for i in range(11)}

    ok = gate2._low_depth_sensitivity(per_target, ["t0"])
    assert ok["evaluable"] is True and ok["informative_targets"] == 10

    thin = gate2._low_depth_sensitivity(per_target, [f"t{i}" for i in range(4)])
    assert thin["evaluable"] is False
    assert "교차 확인" in thin["reason"]
    assert "delta_top4_target_equal" not in thin

    none = gate2._low_depth_sensitivity(per_target, [])
    assert none["evaluable"] is None


def test_holdout_backbone_pdb_paths_all_resolve():
    import importlib
    prep = importlib.import_module("21_gate2d_prepare_encoder")
    resolved = prep.resolve_backbone_pdbs()
    # 72 개 백본 전부 해석돼야 한다. rfd3 60 + native 12.
    assert len(resolved) == 72
    assert sum(1 for r in resolved.values() if r["source"] == "rfd3") == 60
    assert sum(1 for r in resolved.values() if r["source"] == "target") == 12
    assert all(Path(r["pdb_path"]).exists() for r in resolved.values())


def test_encoder_extraction_reproduces_the_committed_dev_features():
    """추출기를 새로 쓴 것의 유일한 자격 - dev 157 백본 재현 (Task 7 Step 5a).

    dev feature 를 만든 스크립트는 커밋된 적이 없다. 재현이 깨지면 Gate 1 의
    train(dev)과 test(홀드아웃)가 다른 feature 공간에 놓이고 그 수치는 해석할 수
    없다. 그래서 이것은 성능 테스트가 아니라 **전제조건**이다.

    두 백본만 확인한다 - 157 개 전부는 CPU 로 100 초가 걸린다. 전수 검증은
    `21_gate2d_prepare_encoder.py --verify-dev` 이고 홀드아웃 추출 직전에 돈다.
    """
    import csv as _csv
    import importlib

    import numpy as np

    enc = importlib.import_module("_mpnn_encoder")
    if not enc.MPNN_CKPT.exists():
        pytest.skip(f"ProteinMPNN ckpt 없음: {enc.MPNN_CKPT}")

    backbones = ROOT / "public_data" / "benchmark" / "gate0" / "backbones"
    ref = np.load(backbones / "mpnn_encoder.npy")
    rows = list(_csv.DictReader((backbones / "backbone_labels.csv").open(encoding="utf-8")))
    assert ref.shape == (157, 384)
    assert len(rows) == 157

    model = enc.load_model()
    for i in (0, 50):  # native 한 개, rfd3 한 개.
        got = enc.encode_backbone_pdb(backbones / "pdb" / rows[i]["pdb_file"], model=model)
        assert got.shape == (384,)
        assert np.allclose(ref[i], got, atol=1e-4), rows[i]["backbone_key"]


def test_encoder_relative_position_is_the_load_bearing_setting():
    """dev feature 는 relative positional encoding 을 끈 상태에서 나왔다.

    켜면 값이 전부 달라진다 (max abs diff ~0.49). 기본값이 조용히 바뀌면 Gate 1
    의 train/test 가 갈라지므로 여기서 고정한다.
    """
    import csv as _csv
    import importlib

    import numpy as np

    enc = importlib.import_module("_mpnn_encoder")
    if not enc.MPNN_CKPT.exists():
        pytest.skip(f"ProteinMPNN ckpt 없음: {enc.MPNN_CKPT}")

    backbones = ROOT / "public_data" / "benchmark" / "gate0" / "backbones"
    ref = np.load(backbones / "mpnn_encoder.npy")
    rows = list(_csv.DictReader((backbones / "backbone_labels.csv").open(encoding="utf-8")))
    pdb = backbones / "pdb" / rows[50]["pdb_file"]

    model = enc.load_model()
    with_pos = enc.encode_backbone_pdb(pdb, model=model, relative_position=True)
    assert not np.allclose(ref[50], with_pos, atol=1e-4)
    assert float(np.abs(ref[50] - with_pos).max()) > 0.1


def test_gate1_arm_ladder_is_frozen_and_only_primary_decides():
    import importlib
    gate1 = importlib.import_module("24_gate1_backbone_predictability")
    assert list(gate1.ARMS) == [
        "primary", "sensitivity_1", "descriptive_legacy", "comparator"]
    assert gate1.GO_ARM == "primary"
    assert gate1.ARMS["primary"]["train_sources"] == ("rfd3",)
    assert gate1.ARMS["primary"]["test_sources"] == ("rfd3",)
    assert gate1.ARMS["sensitivity_1"]["train_sources"] == ("rfd3", "bioemu")
    assert gate1.ARMS["descriptive_legacy"]["train_sources"] == ("rfd3", "bioemu", "target")
    assert gate1.ARMS["comparator"]["test_sources"] == ("target",)


def test_gate1_metrics_are_called_in_predicted_actual_order():
    """`top1_regret` 은 대칭이 아니다 - 뒤집으면 그럴듯한 쓰레기가 나온다.

    완전 역상관 예측기에서 (predicted, actual) 은 최악 regret 을 내고 뒤집은
    호출은 0 을 낸다. 두 값이 다르다는 것을 고정해 두면 호출 순서가 조용히
    뒤집히는 것을 잡는다.
    """
    pred = [0.9, 0.8, 0.1]
    actual = [0.4, 0.5, 1.0]
    targets = ["T", "T", "T"]
    # 맞는 호출: 예측 1위(0.9)를 고르면 실제 0.4, 실제 최선은 1.0 -> regret 0.6.
    assert G.top1_regret(pred, actual, targets)["T"] == pytest.approx(0.6)
    # 뒤집은 호출: 실제 1위(1.0)를 고르고 regret 을 예측값에서 잰다 -> 0.8.
    # 예외가 나지 않으므로 조용히 틀린다. Spearman 은 대칭이라 같은 값이다.
    assert G.top1_regret(actual, pred, targets)["T"] == pytest.approx(0.8)
    assert (G.within_target_spearman(pred, actual, targets)
            == G.within_target_spearman(actual, pred, targets))


def _gate1_payload():
    import json as _json
    return _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0"
         / "gate1_backbone_predictability.json").read_text(encoding="utf-8"))


def _gate1_recompute_inputs():
    """산출물이 아니라 **입력**에서 판정 arm 을 다시 적합할 재료."""
    import importlib
    import json as _json

    import numpy as np

    import _gate2d_cohort as C

    gate1 = importlib.import_module("24_gate1_backbone_predictability")
    grid = C.load_holdout_grid()
    index = _json.loads((gate1.GATE0 / "holdout_grid" / "backbone_encoder.index.json")
                        .read_text(encoding="utf-8"))
    x_test_all = np.load(gate1.GATE0 / "holdout_grid" / "backbone_encoder.npy")
    row_of = {k: i for i, k in enumerate(index["backbone_keys"])}
    return gate1, grid, x_test_all, row_of


def test_gate1_committed_verdict_reproduces():
    """산출물을 **입력에서 다시 계산해** 대조한다. 읽은 값을 되읽지 않는다.

    예전 판은 파일을 읽어 그 파일의 값을 자기에게 다시 단정했다 - 계산이 흘러가도
    깨질 수 없는 테스트였고(`a63eda9` 의 `passed: True` 상수, `bcfecdb`·`3927b5b`
    와 같은 결함), 실제로 이 테스트가 전부 통과하는 환경에서 Gate 1 은 기록값이
    아닌 ρ 를 냈다. 그 결함이 첫 리뷰를 살아남은 이유다.

    판정 arm 을 dev 라벨·홀드아웃 격자·encoder feature 에서 다시 적합한다. 전부
    재계산해도 1 초 미만이므로 부분 재계산으로 타협하지 않는다. 추가로 `5pc8A00`
    의 타겟 내 Spearman 을 따로 단정한다 - 솔버 정지 자리가 뒤집던 타겟이고,
    ρ 가 우연히 같은 평균을 내는 경우까지 잡는다.

    **환경마다 달라지는 진단값은 대조하지 않는다**: `solver.n_iter`,
    `numerics.package_versions`, sklearn 기본값(tol=1e-4) 안정성 행, 그리고
    순위 통계가 아닌 `arms.comparator.mean_predicted` (산출물의
    `numerics.rank_statistics_only` 가 그 이유를 적어 둔다).
    """
    payload = _gate1_payload()
    gate1, grid, x_test_all, row_of = _gate1_recompute_inputs()

    # 동결값 - 결과를 보고 고치지 않는다.
    assert payload["go_arm"] == gate1.GO_ARM == "primary"
    assert payload["frozen_go_rule"]["rho_min"] == G.GATE1_RHO_MIN == 0.25
    assert payload["numerics"]["bootstrap_seed"] == G.BOOTSTRAP_SEED
    # 산출물의 수와 지금 코드의 솔버 설정이 같은 설정이어야 한다. 다르면 산출물은
    # 다른 설정에서 나온 수이고, 아래 재계산이 그것을 재현할 이유가 없다.
    assert payload["numerics"]["solver_tol"] == gate1.SOLVER_TOL
    assert payload["numerics"]["solver_max_iter"] == gate1.SOLVER_MAX_ITER

    recomputed = gate1.evaluate_arm("primary", grid, x_test_all, row_of)
    primary = payload["arms"]["primary"]
    for key in ("informative_targets", "point", "one_sided_90_lcb",
                "lcb_exceeds_zero", "per_target_spearman",
                "top1_backbone_regret_mean_informative_cohort",
                "top1_backbone_regret_mean_all_ranked_targets",
                "top1_backbone_regret_mean", "per_target_regret",
                "mean_q_b", "arm_meets_frozen_rule"):
        assert recomputed[key] == primary[key], f"{key}: 재계산 != 기록"
    assert recomputed["train"] == primary["train"]
    assert recomputed["test"] == primary["test"]
    assert primary["train"]["n_backbones"] == 80
    assert primary["test"]["n_backbones"] == 60
    assert primary["informative_targets"] == 11

    # 이 테스트가 존재하는 이유인 타겟. `5pc8A00` 의 순서가 뒤집히면 위의
    # `per_target_spearman` 딕셔너리 대조에서 **이미** 깨진다 - 여기서 "먼저
    # 깨진다" 고 적어 두면 실제로는 덮이지 않는 것을 덮인다고 읽게 한다.
    # 그래서 값을 한 번 더 비교하지 않고, 그 타겟이 대조 대상 안에 실제로
    # 들어 있는지만 확인한다.
    assert "5pc8A00" in recomputed["per_target_spearman"]

    # 판정도 다시 낸다 - 기록된 verdict 를 되읽지 않는다.
    go = bool(recomputed["point"] >= G.GATE1_RHO_MIN
              and recomputed["lcb_exceeds_zero"]
              and recomputed["informative_targets"] >= G.MIN_INFORMATIVE_TARGETS)
    assert go is False
    assert payload["verdict"] == ("GO" if go else "NO-GO") == "NO-GO"

    # comparator 는 타겟당 백본 1개라 타겟 내 순위가 없다. 0 으로 대입하지 않는다.
    comparator = payload["arms"]["comparator"]
    assert comparator["evaluable"] is False
    assert comparator["informative_targets"] == 0
    assert "point" not in comparator

    # train/test 가 같은 feature 공간이라는 것이 산출물에 박혀 있어야 한다.
    assert payload["feature"]["train_test_same_space"] is True
    assert payload["feature"]["dev_reproduction_max_abs_diff"] < 1e-4


def test_gate1_reported_value_is_not_a_solver_stopping_point():
    """보고값이 tol 에 의존하지 않는다는 것을 **다시 재서** 확인한다.

    blocker 였던 상태: sklearn 기본값 tol=1e-4 에서 lbfgs 가 최적점 전에 서고,
    어디서 서는지가 판본에 따라 달라 primary ρ 가 +0.0935 / +0.0743 으로 갈렸다.
    갈림의 전부는 `5pc8A00` 의 백본 두 개 순서 하나였다.

    그래서 tol 을 10 배씩 조인 표를 산출물에 남기고, 여기서 그 표를 다시 계산해
    **보고 tol 이하의 모든 행이 보고값과 같은지** 본다. 어떤 환경에서 보고값이
    솔버 정지 자리에 의존하면 그 환경에서 이 테스트가 깨진다 - 환경 사이 일치를
    주석으로 주장하지 않고 기계가 확인한다.

    기본값 행(1e-4)의 값은 **대조하지 않는다**. 그 행이 판본에 따라 달라지는
    것이 바로 이 결함의 내용이고, 그 사실은 산출물의 `matches_reported_value`
    가 기록한다.
    """
    payload = _gate1_payload()
    gate1, grid, x_test_all, row_of = _gate1_recompute_inputs()
    reported = payload["arms"]["primary"]
    keys = ("point", "one_sided_90_lcb", "informative_targets",
            "top1_backbone_regret_mean_informative_cohort",
            "top1_backbone_regret_mean_all_ranked_targets")

    assert gate1.SOLVER_TOL <= 1e-5, "1e-4 는 안정 구간 밖이다 (기본값 결함)"
    rows = gate1.solver_tol_stability("primary", grid, x_test_all, row_of)
    converged = [r for r in rows if r["tol"] <= 1e-5]
    assert len(converged) >= 3, "적어도 세 decade 를 확인한다"
    for row in converged:
        for key in keys:
            assert row[key] == reported[key], f"tol={row['tol']:g} {key}"
        assert row["matches_reported_value"] is True
        assert row["per_target_spearman_5pc8A00"] == \
            reported["per_target_spearman"]["5pc8A00"]
    # `n_iter < max_iter` 는 여기서 **주장하지 않는다** - 잘린 적합은 애초에
    # `fit_predict` 가 SystemExit 으로 세우므로 이 자리까지 행이 오지 못한다.
    # 발화할 수 없는 assertion 대신, 그 상류 가드가 실제로 서는지를 아래
    # `test_gate1_truncated_fit_fails_closed` 가 red/green 으로 확인한다.

    # 수렴 구간이 **두 dtype 모두에서** 같은 값인지. 판본 사이의 갈림이 dtype
    # 때문이었으므로, 한 판본 안에서 두 dtype 을 다 봐야 그 주장이 측정이 된다.
    assert {r["input_dtype"] for r in rows} == {"float32", "float64"}
    for dtype in ("float32", "float64"):
        got = [r for r in converged if r["input_dtype"] == dtype]
        assert len(got) >= 3, f"{dtype} 수렴 행이 세 decade 미만이다"

    # 기본값 행이 갈리는 기준은 **입력 dtype 이 아니라 실제 적합 dtype** 이다.
    # 이 구분이 정정의 내용 전부다: sklearn 1.9 계열은 float32 입력을 보존해 두
    # 행이 갈리고, 1.8 계열은 둘 다 float64 로 올려 두 행이 같아진다. 어느
    # 환경에서든 "같은 정밀도로 풀면 같은 값, 다른 정밀도로 풀면 다른 값" 이
    # 성립해야 하며, 입력 dtype 으로 조건을 걸면 1.8 에서 거짓이 된다.
    default = {r["input_dtype"]: r for r in rows if r["tol"] == 1e-4}
    f32, f64 = default["float32"], default["float64"]
    if f32["fit_dtype"] == f64["fit_dtype"]:
        assert f32["point"] == f64["point"], (
            "같은 정밀도로 푼 두 행이 다른 값을 냈다 - dtype 말고 다른 것이 "
            "기본 tol 의 갈림을 만들고 있다.")
    else:
        assert f32["point"] != f64["point"], (
            "정밀도가 다른데 tol=1e-4 에서 같은 값이 나왔다 - 판본 차이의 "
            "원인을 dtype 으로 적은 것이 이 환경에서 재현되지 않는다.")

    # 표가 산출물에도 그 모습으로 남아 있어야 한다 (기본값 행은 값이 아니라
    # 존재와 flag 만 본다).
    stability = payload["numerics"]["solver_tol_stability"]
    assert {r["tol"] for r in stability} >= {1e-4, 1e-5, 1e-6, 1e-7, 1e-8}
    assert {r["input_dtype"] for r in stability} == {"float32", "float64"}
    assert sum(r["is_reported"] for r in stability) == 1
    for row in stability:
        if row["tol"] <= 1e-5:
            assert row["matches_reported_value"] is True
            for key in keys:
                assert row[key] == reported[key], f"기록된 tol={row['tol']:g} {key}"

    # 보고 적합의 정밀도는 손으로 적힌 것이 아니라 그 행이 잰 값이어야 한다.
    # 여기서는 **산출물 내부의 일관성만** 본다 - dtype 은 n_iter 과 같은 진단값
    # 이고, 환경에 따라 달라지는 것이 정상이다. 재계산본과 대조하면 float32 를
    # 올려 버리는 환경에서 정당한 실행이 빨간불이 된다. 보고 *값* 이 환경을
    # 넘어 같은지는 `test_gate1_committed_verdict_reproduces` 가 본다.
    reported_row = next(r for r in stability if r["is_reported"])
    assert reported_row["is_production_dtype"] is True
    assert payload["numerics"]["reported_fit_dtype"] == reported_row["fit_dtype"]
    assert reported["solver"]["fit_dtype"] == reported_row["fit_dtype"]


def test_gate1_truncated_fit_fails_closed():
    """반복이 잘린 적합은 예측을 내놓지 못하고 멈춰야 한다.

    `fit_predict` 의 `n_iter >= max_iter` 가드는 실제 산출물 경로에서는 한 번도
    서지 않는다 - 그래서 "잘리지 않았다" 를 산출물 행에 대고 확인하려던 assertion
    은 발화할 수 없었다. 가드가 살아 있다는 것은 여기서 강제로 잘라 확인한다.
    """
    gate1, grid, x_test_all, row_of = _gate1_recompute_inputs()
    _spec, (x_dev, y_dev, w_dev, _tgt), _labelled, x_test = gate1._arm_inputs(
        "primary", grid, x_test_all, row_of)

    # 정상 예산에서는 돈다.
    _q, n_iter, _dt = gate1.fit_predict(x_dev, y_dev, w_dev, x_test)
    assert 0 < n_iter < gate1.SOLVER_MAX_ITER

    # 예산을 1 로 줄이면 데이터가 아니라 반복 예산이 예측을 정하게 되므로 선다.
    with pytest.raises(SystemExit) as excinfo:
        gate1.fit_predict(x_dev, y_dev, w_dev, x_test, max_iter=1)
    assert "max_iter=1" in str(excinfo.value)


def test_gate1_regret_cohorts_are_named_and_the_oc_comparison_is_like_for_like():
    """regret 의 두 코호트가 이름을 달고 있고, 귀무 대조가 같은 코호트인가.

    blocker 였던 상태: `G.top1_regret` 은 백본 >= 3 인 타겟 **12** 개를 돌고
    (`1sh6A02` 는 RFD3 백본 5 개가 전부 q_b = 1.00 이라 regret 이 구조적으로 0),
    그 값을 informative **11** 개로 계산된 OC 귀무값과 나란히 비교했다. 방향은
    살아남지만 비교 자체가 like-for-like 가 아니었다.
    """
    import json as _json

    import _gate2d_cohort as C

    payload = _gate1_payload()
    primary = payload["arms"]["primary"]
    cohorts = primary["regret_cohorts"]

    informative = cohorts["informative_cohort"]
    ranked = cohorts["all_ranked_targets"]
    assert informative["n_targets"] == 11
    assert ranked["n_targets"] == 12
    assert set(ranked["targets"]) - set(informative["targets"]) == {"1sh6A02"}
    # 두 값이 이름과 함께 있고, 각 이름이 실제로 그 코호트의 값이다.
    assert primary["top1_backbone_regret_mean_informative_cohort"] == informative["value"]
    assert primary["top1_backbone_regret_mean_all_ranked_targets"] == ranked["value"]
    # 예전 키는 뜻이 바뀌지 않았다 - all_ranked_targets 판이다.
    assert primary["top1_backbone_regret_mean"] == ranked["value"]
    assert "all_ranked_targets" in primary["top1_backbone_regret_mean_cohort"]
    assert primary["per_target_regret_cohort"] == "all_ranked_targets"
    assert set(primary["per_target_regret"]) == set(ranked["targets"])
    # 구조적 0 이 들어오므로 12 개 판이 11 개 판보다 작다.
    assert ranked["value"] < informative["value"]

    # informative 코호트가 OC 의 코호트와 **같은 집합**인가. 두 쪽 정의를 각각
    # 다시 계산해 비교한다 - 산출물의 이름만 믿지 않는다.
    grid = C.load_holdout_grid()
    oc_cohort = C.gate1_informative_targets(C.restrict_to_sources(grid, ("rfd3",)))
    assert informative["targets"] == oc_cohort
    assert set(primary["per_target_spearman"]) == set(oc_cohort)

    # OC 귀무값이 그 코호트로 계산돼 있는가.
    oc = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0"
         / "gate2d_operating_characteristics.json").read_text(encoding="utf-8"))
    null_row = oc["gate1_operating_characteristics"]["OC_primary_rfd3_only"]["rows"][0]
    assert null_row["sigma"] == "null"
    assert null_row["n_informative_targets"] == informative["n_targets"] == 11
    # 방향 진술("관측 regret < 귀무 regret")이 같은 코호트에서 성립하는가.
    assert informative["value"] < null_row["mean_top1_regret"]


def test_mpnn_score_block_is_part_of_s6_and_never_fails_open(monkeypatch, tmp_path):
    """스펙 §4 의 cheap 은 "조성, MPNN score" 다. 없으면 멈춘다.

    이 fail-closed 가 없으면 score 산출물이 사라진 환경에서 S6 가 조용히 다시
    조성 전용이 되고, 그것이 PRIMARY DEVIATION 을 만든 경로다.
    """
    import _gate2d_features as F

    assert F.ARM_BLOCKS["S6"] == ("esm_delta_mut", "msa", "cheap", "mpnn_score")
    assert "mpnn_score" not in F.ARM_BLOCKS["S5"]
    # realized 판은 arm 이 아니라 기록이다 - ladder 는 여전히 일곱 개다.
    assert F.REALIZED_S6_BLOCKS_2026_09_11 == ("esm_delta_mut", "msa", "cheap")
    assert len(F.ARMS) == 7

    monkeypatch.setattr(F, "GRID", tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        F.load_mpnn_scores()
    assert "mpnn_scores.json" in str(excinfo.value)
    assert "27_gate2d_prepare_mpnn_scores" in str(excinfo.value)


def test_mpnn_scores_vary_within_backbone():
    """백본 내부 순위 feature 이므로 백본 안에서 변해야 한다.

    백본마다 상수면 Δ_Top4 에 기여할 수 없고, S6 에 열을 하나 더한 것이 아무 일도
    하지 않는다. 그 경우를 조용히 넘기지 않는다.
    """
    import collections

    import numpy as np

    import _gate2d_cohort as C
    import _gate2d_features as F

    scores = F.load_mpnn_scores()
    grid = C.load_holdout_grid()
    assert len(grid.folds) == 1680
    assert all(f.sequence_id in scores for f in grid.folds)

    by_backbone = collections.defaultdict(list)
    for fold in grid.folds:
        by_backbone[fold.backbone_key].append(scores[fold.sequence_id])
    sds = np.array([np.std(v) for v in by_backbone.values()])
    assert len(sds) == 70
    assert (sds > 0).all()          # 상수 백본이 하나도 없어야 한다
    assert float(sds.mean()) > 0.01


def test_gate2_planned_s6_is_compared_with_the_realized_deviation():
    """PRIMARY DEVIATION 이 해소됐다는 것을 산출물이 스스로 말해야 한다."""
    import json as _json
    payload = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0"
         / "gate2_within_backbone_selectability.json").read_text(encoding="utf-8"))

    s6 = payload["arms_joint_pass"]["S6"]
    assert s6["feature_blocks"] == ["esm_delta_mut", "msa", "cheap", "mpnn_score"]
    assert s6["n_features"] == payload["arms_joint_pass"]["S5"]["n_features"] + 21

    cmp_ = payload["s6_planned_vs_realized"]
    assert cmp_["status"] == "compared"
    assert cmp_["realized_2026_09_11"]["delta_top4_target_equal"] == -0.0366
    assert cmp_["realized_2026_09_11"]["one_sided_90_lcb"] == -0.085366
    assert cmp_["realized_2026_09_11"]["verdict"] == "NO-GO"
    assert cmp_["planned"]["verdict"] == payload["verdict"]
    assert payload["s6_cheap_block_deviation"]["status"] == "resolved 2026-09-11"

    # planned 가 판정이고 realized 는 기록이다.
    assert "planned only" in cmp_["decided_by"]


# --- I2: 사전 등록된 RFD3-only 민감도 (스펙 §3) --------------------------------
#
# 스펙 §3: "Gate 2 의 1차 코호트는 mixed 백본 37 개를 유지한다. … RFD3-only
# (mixed 34, informative 11)를 민감도로 함께 보고한다." 이 분석은 한동안 어디에도
# 없었고, **없다는 사실조차 기록돼 있지 않았다.** 보고되지 않은 사전 등록 분석은
# 숨긴 분석과 구별되지 않는다. 그래서 산출물에 있는지를 여기서 지킨다.

def test_gate2_reports_the_preregistered_rfd3_only_sensitivity():
    """1 차(mixed 37)는 그대로이고 RFD3-only(mixed 34)가 그 옆에 있어야 한다."""
    import json as _json
    payload = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0"
         / "gate2_within_backbone_selectability.json").read_text(encoding="utf-8"))

    # 1 차 코호트는 건드리지 않았다.
    assert payload["cohort"]["mixed_backbones"] == 37
    assert payload["cohort"]["informative_targets"] == 11

    report = payload["rfd3_only_cohort_report"]
    assert report["status"] == "reported"
    assert report["primary_cohort_unchanged"] is True
    assert report["sources"] == ["rfd3"]
    assert report["mixed_backbones"] == 34          # 스펙 §3 이 인쇄한 값
    assert report["informative_targets"] == 11      # 스펙 §3 이 인쇄한 값
    assert report["excluded_backbones"] == 37 - 34
    # 두 번째 코호트 slicer 를 만들지 않았다 - 26_ 의 OC_primary_rfd3_only 와 같다.
    assert "restrict_to_sources" in report["cohort_slicer"]

    # 모든 arm 이 두 endpoint 에서 이 민감도를 함께 낸다. S6 만 내면 "판정 arm 에서만
    # 계산했다" 가 되어 ladder 를 가로질러 읽을 수 없다.
    for key in ("arms_joint_pass", "arms_structural_pass_secondary"):
        for arm, row in payload[key].items():
            sens = row["sensitivity_rfd3_only"]
            assert sens["evaluable"] is True, arm
            assert sens["mixed_backbones"] == 34, arm
            assert sens["informative_targets"] == 11, arm
            assert sens["model_refit"] is False, arm
            assert sens["matches_spec_geometry"] is True, arm

    primary = payload["arms_joint_pass"]["S6"]
    sens = primary["sensitivity_rfd3_only"]
    # 1 차는 움직이지 않았고 민감도는 그 옆의 별개 수치다.
    assert primary["delta_top4_target_equal"] == -0.0313
    assert primary["one_sided_90_lcb"] == -0.080303
    assert sens["delta_top4_target_equal"] == -0.0225
    assert sens["one_sided_90_lcb"] == -0.075505
    # 민감도도 문턱에 닿지 않는다 - 1 차 판정과 같은 방향이다.
    assert sens["meets_threshold"] is False
    assert sens["lcb_exceeds_zero"] is False

    # 재적합 판은 **기록된 대안 독법**으로만 존재한다. 산문에만 있던 수여서
    # 산출물에 넣었고(모든 수는 산출물 경로를 달아야 한다), 보고되는 민감도가
    # 바뀌지 않았다는 것을 여기서 지킨다.
    alt = sens["alternative_reading_model_refit"]
    assert alt["model_refit"] is True
    assert sens["model_refit"] is False          # 부모는 그대로 재적합 안 함
    assert "NOT the reported sensitivity" in alt["status"]
    assert alt["informative_targets"] == 11
    assert alt["delta_top4_target_equal"] == 0.0097
    assert alt["one_sided_90_lcb"] == -0.023359
    assert alt["verdict_if_this_were_the_arm"] == "NO-GO"
    assert alt["train_folds"] == 1440 and alt["train_folds_primary"] == 1680
    # 판정 arm 의 1 차 endpoint 에만 있다 - 다른 arm·endpoint 에 보고되지 않는
    # 수를 열두 개 더 만들지 않는다.
    for key in ("arms_joint_pass", "arms_structural_pass_secondary"):
        for arm, row in payload[key].items():
            has_alt = "alternative_reading_model_refit" in row["sensitivity_rfd3_only"]
            assert has_alt == (arm == "S6" and key == "arms_joint_pass"), (key, arm)


def test_gate2_rfd3_refit_alternative_reading_recomputes():
    """기록된 재적합 수를 **다시 계산해** 대조한다. 9 초쯤 걸리고, 그만큼 값어치다.

    이 수는 산문에만 있었다. 산출물에 옮겨 적으면서 "적어 두기만 하고 아무도
    반증할 수 없는 수" 를 하나 더 만들지 않는다 - 산출물의 값을 되읽는 대신
    LOTO 를 RFD3 폴드 1,440 개로 다시 돌려 맞춘다.

    같은 이유로 이것이 **보고되는 민감도가 아니라는 사실**도 함께 본다: 부모는
    `model_refit: false` 이고 판정 arm 의 수(−0.0313)는 그대로다.
    """
    import importlib
    import json as _json

    import _gate2d_cohort as C
    import _gate2d_features as F

    gate2 = importlib.import_module("25_gate2_within_backbone_selectability")
    payload = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0"
         / "gate2_within_backbone_selectability.json").read_text(encoding="utf-8"))
    recorded = (payload["arms_joint_pass"]["S6"]["sensitivity_rfd3_only"]
                ["alternative_reading_model_refit"])

    grid = C.load_holdout_grid()
    recomputed = gate2._rfd3_refit_alternative_reading(
        grid, F.PRIMARY_ARM, F.ARM_BLOCKS[F.PRIMARY_ARM], "joint")
    for key in ("delta_top4_target_equal", "one_sided_90_lcb", "informative_targets",
                "per_target_delta_top4", "meets_threshold", "lcb_exceeds_zero",
                "verdict_if_this_were_the_arm", "train_folds"):
        assert recomputed[key] == recorded[key], f"{key}: 재계산 != 기록"

    # 재적합은 판정 arm 의 수를 건드리지 않는다.
    assert payload["arms_joint_pass"]["S6"]["delta_top4_target_equal"] == -0.0313
    assert payload["arms_joint_pass"]["S6"]["one_sided_90_lcb"] == -0.080303


def test_rfd3_only_sensitivity_slices_the_cohort_and_withholds_below_the_floor(monkeypatch):
    """코호트만 바뀌고 모델은 다시 적합되지 않는다. floor 미달이면 non-evaluable.

    점수는 결정적인 더미다 - 여기서 검사하는 것은 Ridge 가 아니라 **어느 백본이
    집계에 들어가는가** 이고, 그것이 스펙 §3 이 고정한 부분이다.
    """
    import importlib

    import _gate2d_cohort as C

    gate2 = importlib.import_module("25_gate2_within_backbone_selectability")
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    score_of = {f.sequence_id: float(i) for i, f in enumerate(grid.folds)}

    out = gate2._rfd3_only_sensitivity(grid, mixed, score_of, "joint")
    assert out["mixed_backbones"] == 34
    assert out["informative_targets"] == 11
    assert out["excluded_backbones"] == 3
    # 빠진 셋은 전부 native 다 - source 로 잘랐지 다른 규칙이 끼어들지 않았다.
    assert all("|target|" in key for key in out["excluded_backbone_keys"])

    # 같은 slicer 위에서 같은 집계 함수를 쓴다.
    sub = C.mixed_backbones(C.restrict_to_sources(grid, ("rfd3",)))
    assert [b.backbone_key for b in sub] == sorted(
        {b.backbone_key for b in mixed} - set(out["excluded_backbone_keys"]))
    per_target = gate2._per_target_delta_top4(sub, score_of, "joint")
    assert out["per_target_delta_top4"] == {
        t: round(v, 4) for t, v in sorted(per_target.items())}

    # floor 미달이면 숫자를 내지 않고 사유를 남긴다 (규칙 6 과 같은 처리).
    monkeypatch.setattr(gate2, "RFD3_SOURCES", ("a_source_that_does_not_exist",))
    thin = gate2._rfd3_only_sensitivity(grid, mixed, score_of, "joint")
    assert thin["evaluable"] is False
    assert "교차 확인" in thin["reason"]
    assert "delta_top4_target_equal" not in thin


# --- I3: encoder 재현 가드가 실제로 발동한다 -----------------------------------
#
# `21_gate2d_prepare_encoder.py` 는 `"passed": True` 를 무조건 적었고
# `24_gate1_backbone_predictability.py` 는 그 플래그 하나로 Gate 1 실행 여부를
# 정했다. 즉 게이트가 상수를 읽었다 - `bcfecdb`·`3927b5b` 가 고친 것과 같은 결함
# ("발동할 수 없는 가드는 아무것도 지키지 않는다").

def test_encoder_index_records_a_measurement_not_a_constant():
    """커밋된 index 의 dev_reproduction 은 측정 기록이어야 한다."""
    import json as _json
    index = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
         / "backbone_encoder.index.json").read_text(encoding="utf-8"))
    repro = index["dev_reproduction"]
    assert repro["verified_in_this_invocation"] is True
    assert repro["passed"] is True
    assert repro["allclose"] is True
    assert isinstance(repro["max_abs_diff"], float)
    assert 0.0 < repro["max_abs_diff"] <= repro["atol"] == 1e-4
    assert repro["n_backbones_verified"] == 157


def test_skip_verify_can_no_longer_stamp_a_pass():
    """`passed` 는 유도값이다. 호출자가 주장해도 측정이 없으면 false 다."""
    import importlib
    import inspect

    prep = importlib.import_module("21_gate2d_prepare_encoder")

    # 측정 없이 index 를 쓸 수 있는 호출 형태가 남아 있으면 안 된다.
    assert inspect.signature(prep.extract).parameters[
        "verification"].default is inspect.Parameter.empty

    skipped = prep.dev_reproduction_record(prep.skipped_verification())
    assert skipped["verified_in_this_invocation"] is False
    assert skipped["passed"] is False
    assert skipped["max_abs_diff"] is None
    assert "--skip-verify" in skipped["reason"]

    # 통과를 주장하지만 돌지 않은 기록 - 그래도 false 다.
    forged = prep.dev_reproduction_record(
        {"verified_in_this_invocation": False, "allclose": True,
         "max_abs_diff": 9.06e-06, "atol": 1e-4, "passed": True})
    assert forged["passed"] is False

    # 돌았지만 합격선을 넘긴 기록.
    failed = prep.dev_reproduction_record(
        {"verified_in_this_invocation": True, "allclose": False,
         "max_abs_diff": 0.49, "atol": 1e-4})
    assert failed["passed"] is False
    assert failed["max_abs_diff"] == 0.49

    # 실제로 재고 통과한 기록만 true 다.
    passed = prep.dev_reproduction_record(
        {"verified_in_this_invocation": True, "allclose": True,
         "max_abs_diff": 9.06e-06, "atol": 1e-4, "n_backbones": 157})
    assert passed["passed"] is True
    assert passed["max_abs_diff"] == 9.06e-06
    assert passed["n_backbones_verified"] == 157


def test_gate1_reproduction_guard_names_each_defect():
    """가드가 보는 것은 플래그가 아니라 측정 기록이다."""
    import importlib
    gate1 = importlib.import_module("24_gate1_backbone_predictability")
    good = {"dev_reproduction": {"verified_in_this_invocation": True,
                                 "max_abs_diff": 9.06e-06, "atol": 1e-4,
                                 "allclose": True, "passed": True}}
    assert gate1._reproduction_defect(good) is None

    def defect(**changes):
        index = {"dev_reproduction": {**good["dev_reproduction"], **changes}}
        return gate1._reproduction_defect(index)

    assert "돌리지 않았다" in defect(verified_in_this_invocation=False)
    assert "max_abs_diff" in defect(max_abs_diff=None)
    # 옛 형식(플래그만 있는 index)도 거절된다 - 그것이 결함의 본체였다.
    assert gate1._reproduction_defect({"dev_reproduction": {"passed": True}})
    assert gate1._reproduction_defect({}) is not None
    # 합격선 자체를 느슨하게 적고 통과했다고 말하는 index.
    assert "동결된 합격선" in defect(atol=1.0, max_abs_diff=0.5)
    assert "atol" in defect(max_abs_diff=1e-3)
    assert "통과로 기록되지 않았다" in defect(passed=False)


def test_gate1_refuses_an_index_whose_verification_did_not_pass(tmp_path, monkeypatch):
    """가드가 실제로 발동한다 - 검증이 통과하지 않은 index 로는 Gate 1 이 안 돈다."""
    import importlib
    import json as _json

    gate1 = importlib.import_module("24_gate1_backbone_predictability")
    real = _json.loads(
        (ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
         / "backbone_encoder.index.json").read_text(encoding="utf-8"))

    grid_dir = tmp_path / "holdout_grid"
    grid_dir.mkdir()
    bad = dict(real)
    bad["dev_reproduction"] = {**real["dev_reproduction"],
                               "verified_in_this_invocation": False,
                               "max_abs_diff": None,
                               "allclose": None,
                               "passed": False,
                               "reason": "--skip-verify 로 검증을 건너뛰었다"}
    (grid_dir / "backbone_encoder.index.json").write_text(
        _json.dumps(bad, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(gate1, "GATE0", tmp_path)
    monkeypatch.setattr(sys, "argv",
                        ["24_gate1", "--out", str(tmp_path / "out.json")])
    with pytest.raises(SystemExit) as excinfo:
        gate1.main()
    message = str(excinfo.value)
    assert "Gate 1 을 돌리지 않는다" in message
    assert "돌리지 않았다" in message
    assert not (tmp_path / "out.json").exists()   # 산출물을 쓰지 않는다
