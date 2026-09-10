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


def one_sided_lcb(values: Sequence[float], *, alpha: float = 0.10,
                  n_boot: int = 20000, seed: int = 0) -> dict[str, object]:
    """이미 클러스터 단위로 집계된 값들의 단측 하한.

    `clustered_bootstrap` 과 나누어 두는 이유: 그쪽은 행 인덱스를 받아 양측 95%
    구간을 내고 동결된 v1 수치가 그 동작에 묶여 있다. 여기는 **클러스터당 값
    하나**를 받아 단측 하한만 낸다.

    2026-09-10 게이트 스펙에서 클러스터 = 타겟이다. 호출자가 타겟 등가중으로
    집계한 뒤 넘긴다.
    """
    clean = [float(v) for v in values if float(v) == float(v)]
    n = len(clean)
    if n < 3:
        # 점추정은 낼 수 있다. 단위가 3개 미만이면 구간을 보류한다.
        point = sum(clean) / n if n else None
        return {"point": point, "lcb": None, "exceeds_zero": None, "n": n}

    rng = np.random.default_rng(seed)
    arr = np.asarray(clean, dtype=float)
    draws = rng.integers(0, n, size=(n_boot, n))
    means = arr[draws].mean(axis=1)
    lcb = float(np.percentile(means, alpha * 100.0))
    return {
        "point": round(float(arr.mean()), 6),
        "lcb": round(lcb, 6),
        "exceeds_zero": bool(lcb > 0.0),
        "n": n,
        "n_boot": int(n_boot),
        "alpha": float(alpha),
    }
