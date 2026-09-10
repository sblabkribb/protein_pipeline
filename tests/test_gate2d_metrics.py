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
