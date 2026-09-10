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


def top_k_indices(scores: Sequence[float], seq_ids: Sequence[str], k: int = TOP_K) -> list[int]:
    """점수 내림차순 상위 k. 동점은 sequence_id 오름차순으로 끊는다.

    무작위 동점 처리를 쓰지 않는다 - 재현되지 않는다.
    """
    order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), str(seq_ids[i])))
    return order[:k]


def delta_top4(labels: Sequence[bool], scores: Sequence[float],
               seq_ids: Sequence[str], k: int = TOP_K) -> float:
    """(Top-k 통과율) − q_b.

    q_b 는 Top-k 를 고르는 것과 **같은 candidate universe** 위의 base rate 다.
    분모는 다르다(k vs n) - 같아야 하는 것은 후보 모집단이다.
    """
    n = len(labels)
    if n == 0 or k <= 0:
        return float("nan")
    q_b = sum(1 for v in labels if v) / n
    picked = top_k_indices(scores, seq_ids, k)
    top_rate = sum(1 for i in picked if labels[i]) / len(picked)
    return top_rate - q_b
