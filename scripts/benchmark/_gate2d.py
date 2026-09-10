"""2축 게이팅 실험의 동결된 상수와 측정 primitive.

정의의 출처는 docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md 하나다.
이 파일의 숫자를 바꾸면 스펙을 위반한다 - 결과를 보고 바꾸지 않는다.
"""

from __future__ import annotations

#: joint-pass 문턱. THRESHOLD_PROVENANCE 에서 고정됐고 이 실험에서 다시 고르지 않는다.
PLDDT_MIN = 85.0
RMSD_MAX = 2.0
SOLUPROT_MIN = 0.5

#: Δ_Top4 의 K. m2_endpoint_dynamic_range.json 의 min_probe_per_unit 과 같은 값.
TOP_K = 4

#: GO 문턱.
GATE2_DELTA_MIN = 0.10
GATE1_RHO_MIN = 0.25

#: 단측 LCB 의 alpha. 90% LCB 이므로 0.10.
LCB_ONE_SIDED_ALPHA = 0.10

#: 이보다 적으면 판정하지 않는다. holdout_experiment_spec.json 규칙 승계.
MIN_INFORMATIVE_TARGETS = 8

#: 부트스트랩 시드. 스펙의 시뮬레이션과 같은 값을 쓴다.
BOOTSTRAP_SEED = 20260910


from collections.abc import Sequence


def is_joint_pass(plddt: float, rmsd: float, soluprot: float) -> bool:
    """스펙의 joint-pass. 세 문턱 모두 등호를 포함한다."""
    return (plddt >= PLDDT_MIN) and (rmsd <= RMSD_MAX) and (soluprot >= SOLUPROT_MIN)


def is_structural_pass(plddt: float, rmsd: float) -> bool:
    """SoluProt 을 뺀 2차 endpoint. 순환성 없는 대조에 쓴다."""
    return (plddt >= PLDDT_MIN) and (rmsd <= RMSD_MAX)


import math


def _reject_nonfinite_scores(scores: Sequence[float]) -> None:
    """점수의 NaN·±Inf 를 fail-closed 로 거절한다 (스펙 §5).

    NaN 비교는 전부 False 이므로 정렬은 NaN 을 입력 행 순서가 놓는 자리에 그냥
    둔다. 전 후보가 NaN 인 최악의 경우 Top-4 가 `sequence_id` 앞 4개가 되고
    **Δ_Top4 가 고장 대신 잡음처럼 보인다.** surrogate 가 어떤 후보에 점수를
    못 매기면 그것은 feature 파이프라인의 버그이므로 조용히 뒤로 미루지 않는다.
    """
    bad = [i for i, v in enumerate(scores) if not math.isfinite(float(v))]
    if not bad:
        return
    raise ValueError(
        f"비유한 점수 {len(bad)} 개 (첫 인덱스 {bad[0]}, 값 {float(scores[bad[0]])!r}). "
        "스펙 §5 는 점수의 NaN·±Inf 를 fail-closed 로 규정한다 - 뒤로 정렬하면 "
        "Δ_Top4 가 고장 대신 잡음처럼 읽힌다."
    )


def top_k_indices(scores: Sequence[float], seq_ids: Sequence[str], k: int = TOP_K) -> list[int]:
    """점수 내림차순 상위 k. 동점은 sequence_id 오름차순으로 끊는다.

    무작위 동점 처리를 쓰지 않는다 - 재현되지 않는다.

    **정렬 전에** 점수를 검사하고 NaN·±Inf 가 하나라도 있으면 `ValueError` 다.
    검사는 이 metric 경계에서 한 번만 한다 - `delta_top4` 는 여기를 지나므로
    같은 검사를 되풀이하지 않는다.

    이 금지는 **점수 입력**에만 적용된다. `delta_top4` 가 **돌려주는** NaN 은
    "이 백본은 셀 수 없다" 는 별개의 sentinel 이며 유지된다.
    """
    _reject_nonfinite_scores(scores)
    order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), str(seq_ids[i])))
    return order[:k]


def delta_top4(labels: Sequence[bool], scores: Sequence[float],
               seq_ids: Sequence[str], k: int = TOP_K) -> float:
    """(Top-k 통과율) − q_b.

    q_b 는 Top-k 를 고르는 것과 **같은 candidate universe** 위의 base rate 다.
    분모는 다르다(k vs n) - 같아야 하는 것은 후보 모집단이다.

    NaN 의 두 용법을 섞지 않는다 (스펙 §5).
      - **점수 입력의 NaN·±Inf 는 금지**다. `top_k_indices` 가 `ValueError` 를
        내며, 여기서 같은 검사를 되풀이하지 않는다.
      - **반환값의 NaN 은 유지**한다. 사용가능 설계가 0 인 백본은 셀 수 없다는
        sentinel 이고 격자에 2개 있다(`3es1A01`·`3h7eA02` 의 native arm).
        타겟 등가중 집계가 그 백본을 제외한다.
    """
    n = len(labels)
    if n == 0 or k <= 0:
        return float("nan")
    q_b = sum(1 for v in labels if v) / n
    picked = top_k_indices(scores, seq_ids, k)
    top_rate = sum(1 for i in picked if labels[i]) / len(picked)
    return top_rate - q_b


from collections import defaultdict


def per_target_means(per_backbone: Sequence[float],
                     targets: Sequence[str]) -> list[float]:
    """백본별 값을 타겟 내에서 먼저 평균한다. 타겟 이름 오름차순으로 돌려준다.

    NaN 백본은 제외한다. 어떤 타겟의 백본이 전부 NaN 이면 그 타겟도 빠진다.
    """
    grouped: dict[str, list[float]] = defaultdict(list)
    for value, target in zip(per_backbone, targets):
        v = float(value)
        if v == v:  # NaN 제외
            grouped[str(target)].append(v)
    return [sum(vals) / len(vals) for _t, vals in sorted(grouped.items()) if vals]


def target_equal_mean(per_backbone: Sequence[float],
                      targets: Sequence[str]) -> float:
    """타겟 등가중 평균. 백본 수가 많은 타겟이 과대대표되지 않는다."""
    per_target = per_target_means(per_backbone, targets)
    if not per_target:
        return float("nan")
    return sum(per_target) / len(per_target)
