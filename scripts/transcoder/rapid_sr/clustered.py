"""백본 단위 clustered bootstrap 과 CA RMSD.

temperature 비교에서 실제 독립 단위는 서열이 아니라 **백본**이다. 480개 서열을
독립 표본처럼 다루면 신뢰구간이 실제보다 좁아진다. 그래서 재표집을 백본 단위로 한다.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np


def kabsch_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    """최적 중첩 후 CA RMSD. 길이가 다르면 앞쪽 공통 길이만 쓴다."""
    n = min(a.shape[0], b.shape[0])
    if n < 3:
        return float("nan")
    x = a[:n] - a[:n].mean(axis=0)
    y = b[:n] - b[:n].mean(axis=0)
    u, _s, vt = np.linalg.svd(x.T @ y)
    d = np.sign(np.linalg.det(u @ vt))
    rot = u @ np.diag([1.0, 1.0, d]) @ vt
    aligned = x @ rot
    return float(np.sqrt(((aligned - y) ** 2).sum(axis=1).mean()))


def clustered_bootstrap(
    clusters: Sequence[str],
    statistic: Callable[[np.ndarray], float],
    *,
    n_boot: int = 4000,
    seed: int = 0,
) -> dict[str, object]:
    """클러스터(백본)를 재표집해 통계량의 95% 구간을 낸다.

    `statistic` 은 선택된 **행 인덱스 배열**을 받아 스칼라를 돌려준다.
    """
    clusters = np.asarray(clusters)
    by_cluster: dict[str, list[int]] = defaultdict(list)
    for index, name in enumerate(clusters):
        by_cluster[str(name)].append(index)
    keys = sorted(by_cluster)
    point = statistic(np.arange(len(clusters)))
    if len(keys) < 3:
        # 점추정은 낼 수 있다. 클러스터가 3개 미만이면 구간만 보류한다.
        return {
            "point": round(float(point), 4) if point == point else None,
            "ci95": None, "n_clusters": len(keys),
        }

    rng = np.random.default_rng(seed)
    samples: list[float] = []
    for _ in range(n_boot):
        picked = rng.integers(0, len(keys), size=len(keys))
        rows: list[int] = []
        for index in picked:
            rows.extend(by_cluster[keys[int(index)]])
        value = statistic(np.asarray(rows))
        if value == value:
            samples.append(float(value))
    if not samples:
        return {"point": point, "ci95": None, "n_clusters": len(keys)}
    low, high = np.percentile(samples, [2.5, 97.5])
    return {
        "point": round(float(point), 4) if point == point else None,
        "ci95": [round(float(low), 4), round(float(high), 4)],
        "excludes_zero": bool(low > 0 or high < 0),
        "ci_width": round(float(high - low), 4),
        "n_clusters": len(keys),
        "n_boot": len(samples),
    }
