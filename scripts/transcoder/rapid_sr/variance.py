"""타겟/백본/설계의 nested 분산 분해와 ICC (설계 3.4).

두 SD 를 나란히 놓고 "백본 효과가 더 크다"고 말할 수 없다. 설계는 백본에
nested 되어 있어 두 SD 는 직접 비교 가능한 양이 아니다. 여기서는 각 수준의
분산 성분을 추정하고 백본 수준이 설명하는 비율(ICC)과 그 신뢰구간을 낸다.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import numpy as np

_EMPTY = {"var_target": 0.0, "var_backbone": 0.0, "var_design": 0.0}


def _components(rows: Sequence[dict]) -> dict[str, float]:
    """불균형 설계에서도 동작하는 moment estimator.

    음수 성분은 0 으로 절단한다 — 분산은 음수일 수 없고, 표본이 작으면
    moment estimator 가 음수를 낼 수 있다.
    """
    if not rows:
        return dict(_EMPTY)

    by_backbone: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        by_backbone[(str(row["target"]), str(row["backbone"]))].append(float(row["value"]))

    backbone_means: dict[str, list[float]] = defaultdict(list)
    within_var: list[float] = []
    for (target, _backbone), values in by_backbone.items():
        arr = np.asarray(values, dtype=float)
        backbone_means[target].append(float(arr.mean()))
        if arr.size > 1:
            within_var.append(float(arr.var(ddof=1)))

    var_design = float(np.mean(within_var)) if within_var else 0.0
    n_per_backbone = float(np.mean([len(v) for v in by_backbone.values()])) or 1.0

    between_backbone: list[float] = []
    target_means: list[float] = []
    for means in backbone_means.values():
        arr = np.asarray(means, dtype=float)
        target_means.append(float(arr.mean()))
        if arr.size > 1:
            between_backbone.append(float(arr.var(ddof=1)))

    var_backbone = max(
        0.0,
        (float(np.mean(between_backbone)) if between_backbone else 0.0)
        - var_design / n_per_backbone,
    )

    var_target = 0.0
    if len(target_means) > 1:
        n_bb_per_target = float(np.mean([len(v) for v in backbone_means.values()])) or 1.0
        var_target = max(
            0.0,
            float(np.var(target_means, ddof=1))
            - (var_backbone + var_design / n_per_backbone) / n_bb_per_target,
        )

    return {
        "var_target": var_target,
        "var_backbone": var_backbone,
        "var_design": var_design,
    }


def nested_variance_components(
    rows: Sequence[dict], *, n_boot: int = 0, seed: int = 0
) -> dict[str, object]:
    base = _components(rows)
    total = base["var_target"] + base["var_backbone"] + base["var_design"]
    icc_backbone = (base["var_backbone"] / total) if total > 0 else 0.0
    icc_target = (base["var_target"] / total) if total > 0 else 0.0

    out: dict[str, object] = {
        **base,
        "var_total": total,
        "icc_backbone": icc_backbone,
        "icc_target": icc_target,
        "n_rows": len(rows),
        "n_backbones": len({(str(r["target"]), str(r["backbone"])) for r in rows}),
        "n_targets": len({str(r["target"]) for r in rows}),
    }

    if n_boot > 0 and rows:
        rng = np.random.default_rng(seed)
        by_backbone: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            by_backbone[(str(row["target"]), str(row["backbone"]))].append(row)
        keys = sorted(by_backbone)

        samples: list[float] = []
        for _ in range(int(n_boot)):
            picked = rng.integers(0, len(keys), size=len(keys))
            resampled: list[dict] = []
            for slot, index in enumerate(picked):
                key = keys[int(index)]
                for row in by_backbone[key]:
                    clone = dict(row)
                    # 재표집된 백본에 고유 id 를 줘야 중복이 하나로 합쳐지지 않는다.
                    clone["backbone"] = f"{key[1]}#boot{slot}"
                    resampled.append(clone)
            comp = _components(resampled)
            tot = comp["var_target"] + comp["var_backbone"] + comp["var_design"]
            samples.append((comp["var_backbone"] / tot) if tot > 0 else 0.0)

        low, high = np.percentile(samples, [2.5, 97.5])
        out["icc_backbone_ci95"] = (
            float(min(low, icc_backbone)),
            float(max(high, icc_backbone)),
        )
        out["n_boot"] = int(n_boot)
    return out
