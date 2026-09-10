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


def test_msa_arms_are_an_unstubbed_seam():
    """S4-S6 는 아직 없다. **가짜 데이터로 채우지 않는다.**

    `non_evaluable` 로 기록하지 않는 이유: 그 상태는 스펙 §4 규칙 5 의
    "train fold 에서 imputation statistic 을 만들 수 없다" 라는 **데이터에 대한
    판정**이다. 코드가 아직 없는 것을 데이터 판정으로 적으면 나중에 진짜
    non-evaluable 과 구분되지 않는다.
    """
    import _gate2d_cohort as C
    import _gate2d_features as F
    grid = C.load_holdout_grid()
    for arm in ("S4", "S5", "S6"):
        assert "msa" in F.ARM_BLOCKS[arm]
        with pytest.raises(NotImplementedError, match="msa_features.json"):
            F.build_features(arm, grid.folds[:8])


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
    assert "interim" in payload["verdict_note"]
    assert payload["cohort"]["mixed_backbones"] == 37
    assert payload["cohort"]["informative_targets"] == 11
    s0 = payload["arms_joint_pass"]["S0"]
    assert s0["informative_targets"] == 11
    assert s0["status"] == "measured_reference"
