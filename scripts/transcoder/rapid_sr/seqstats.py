"""생성된 서열 집합의 다양성·조성 통계 (temperature sweep 용).

MPNN 이 내놓는 score 는 서열 하나마다 나오지만, temperature 효과는 **집합의
분포**로 나타난다. 그래서 위치별 엔트로피와 쌍별 거리도 함께 잰다.
"""

from __future__ import annotations

import math
from collections import Counter

AA = "ACDEFGHIKLMNPQRSTVWY"


def positional_entropy(sequences: list[str]) -> float:
    """위치별 Shannon 엔트로피(nat)의 평균.

    서열이 하나뿐이면 엔트로피가 0 이지만 그건 다양성이 없는 게 아니라 잴 수
    없는 것이므로 0.0 을 돌려주되 호출부가 n 을 함께 보게 한다.
    """
    if len(sequences) < 2:
        return 0.0
    length = min(len(s) for s in sequences)
    if length == 0:
        return 0.0
    total = 0.0
    for i in range(length):
        counts = Counter(s[i] for s in sequences)
        n = sum(counts.values())
        total += -sum((c / n) * math.log(c / n) for c in counts.values() if c)
    return total / length


def mean_pairwise_distance(sequences: list[str]) -> float:
    """쌍별 Hamming 거리를 길이로 정규화한 평균 (1 - identity)."""
    if len(sequences) < 2:
        return 0.0
    length = min(len(s) for s in sequences)
    if length == 0:
        return 0.0
    total, pairs = 0.0, 0
    for i in range(len(sequences)):
        for j in range(i + 1, len(sequences)):
            a, b = sequences[i], sequences[j]
            total += sum(1 for k in range(length) if a[k] != b[k]) / length
            pairs += 1
    return total / pairs if pairs else 0.0


def composition(sequences: list[str]) -> dict[str, float]:
    """집합 전체의 아미노산 빈도와 물리화학 요약."""
    joined = "".join(sequences).upper()
    n = max(1, len(joined))
    out = {f"aa_{aa}": joined.count(aa) / n for aa in AA}
    out["charged"] = sum(joined.count(c) for c in "DEKRH") / n
    out["hydrophobic"] = sum(joined.count(c) for c in "AILMFWVY") / n
    out["polar"] = sum(joined.count(c) for c in "STNQCY") / n
    return out


def n_unique(sequences: list[str]) -> int:
    return len(set(sequences))
