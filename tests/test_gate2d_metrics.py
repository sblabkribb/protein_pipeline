import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "benchmark"))

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
    verdict = prep.arm_verdict({"C": row})
    assert verdict["evaluable"] is False
    assert "cons_p25" in verdict["reason"] and "coverage_median" in verdict["reason"]
    assert verdict["dropped_measured_by_target"] == {"C": ["cons_p25", "coverage_median"]}

    # 아무것도 버리지 않았으면 arm 은 평가 가능하고 행에 그 키가 없다.
    full = {n: 0.5 for n in prep.TARGET_FEATURES}
    ok = prep.impute("A", full, train_stats=prep.train_stats({"A": full, "B": full}))
    assert "dropped_measured" not in ok
    assert prep.arm_verdict({"A": ok}) == {"evaluable": True}


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
    sys.path.insert(0, str(ROOT / "scripts" / "transcoder"))
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
