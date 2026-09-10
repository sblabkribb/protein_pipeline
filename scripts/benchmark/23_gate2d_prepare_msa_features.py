#!/usr/bin/env python3
"""P3. a3m -> conservation feature. 결측 규칙은 스펙 §4 에 동결돼 있다.

핵심 제약 두 개.
  - conservation 프로파일은 **타겟/reference 로 한 번** 계산된다. candidate 의
    AF2 결과나 Gate 2 label 에 따라 달라지는 항이 들어가면 leakage 다.
  - MSA 가 얕거나 없다고 test 타겟을 코호트에서 빼지 않는다. depth 로 타겟을
    걸러내면 그 자체가 selection 문제가 된다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

#: 타겟 수준 conservation feature 이름. candidate 와 무관한 값만 둔다.
TARGET_FEATURES = ("cons_mean", "cons_p25", "cons_p75", "usable_hits_log10",
                   "coverage_median", "depth_median_log10")


def train_stats(train_by_target: Mapping[str, Mapping[str, float] | None]
                ) -> dict[str, float] | None:
    """train fold 의 feature 평균. 하나도 정의되지 않으면 None.

    None 은 "이 arm 을 non-evaluable 로 기록" 이라는 뜻이다. 타겟을 빼는 것이
    아니다 - 스펙 §4 규칙 5.
    """
    usable = [v for v in train_by_target.values() if v]
    if not usable:
        return None
    out: dict[str, float] = {}
    for name in TARGET_FEATURES:
        vals = [float(v[name]) for v in usable if name in v]
        if vals:
            out[name] = sum(vals) / len(vals)
    return out or None


def impute(target_id: str, features: Mapping[str, float] | None, *,
           train_stats: dict[str, float] | None) -> dict[str, float]:
    """정의된 값은 그대로, 정의되지 않은 값은 train fold 평균 + 지시자 1.

    test 타겟이 전부 undefined 여도 타겟을 유지한다.
    """
    if train_stats is None:
        raise ValueError(
            f"{target_id}: train fold 에 정의된 MSA feature 가 없어 imputation "
            "statistic 을 만들 수 없다. 이 arm 은 non-evaluable 이다."
        )
    if features:
        out = {name: float(features[name]) for name in TARGET_FEATURES if name in features}
        # 지시자는 **대치가 실제로 일어났는가**를 뜻한다. train fold 어디에서도
        # 정의되지 않은 이름은 imputation statistic 자체가 없어 모든 타겟이 같은
        # 상수로 채워진다 - 정보가 없으므로 지시자를 켜지 않는다 (스펙 §4 규칙 3).
        imputed = [n for n in train_stats if n not in out]
        for name in TARGET_FEATURES:
            if name not in out:
                out[name] = train_stats.get(name, 0.0)
        out["msa_undefined"] = 1 if imputed else 0
        return out
    out = {name: train_stats.get(name, 0.0) for name in TARGET_FEATURES}
    out["msa_undefined"] = 1
    return out
