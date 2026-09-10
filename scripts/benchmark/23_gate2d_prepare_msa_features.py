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


def _defined(features: Mapping[str, float] | None) -> dict[str, float]:
    """정의된 값만 남긴다. Step 6 은 정의되지 않은 값을 **null 로** 쓴다.

    전부 null 인 행은 truthy dict 이므로 그대로 두면 "값이 있다" 분기로 들어가
    `float(None)` 에서 죽는다. 규칙 4 는 그 타겟을 **유지**하라고 하므로, 죽는
    것은 규칙 위반이다 - null 은 "없음" 으로 정규화한다.
    """
    if not features:
        return {}
    return {k: float(v) for k, v in features.items()
            if k in TARGET_FEATURES and v is not None}


def train_stats(train_by_target: Mapping[str, Mapping[str, float] | None]
                ) -> dict[str, float] | None:
    """train fold 의 feature 평균. 하나도 정의되지 않으면 None.

    None 은 "이 arm 을 non-evaluable 로 기록" 이라는 뜻이다. 타겟을 빼는 것이
    아니다 - 스펙 §4 규칙 5.
    """
    usable = [d for d in (_defined(v) for v in train_by_target.values()) if d]
    if not usable:
        return None
    out: dict[str, float] = {}
    for name in TARGET_FEATURES:
        vals = [v[name] for v in usable if name in v]
        if vals:
            out[name] = sum(vals) / len(vals)
    return out or None


def impute(target_id: str, features: Mapping[str, float] | None, *,
           train_stats: dict[str, float] | None) -> dict[str, float]:
    """정의된 값은 그대로, 정의되지 않은 값은 train fold 평균 + 지시자 1.

    test 타겟이 전부 undefined 여도 타겟을 유지한다.

    train fold 에 통계가 없어 **측정된 값을 버려야 하는** 이름은
    `dropped_measured` 로 보고한다. arm 판정은 `arm_verdict()` 가 한다.
    """
    # 모듈 함수 train_stats() 와 이름이 겹치므로 아래에서는 stats 를 쓴다.
    # 인자 이름은 동결된 Step 2 테스트가 `train_stats=` 로 부르므로 못 바꾼다.
    stats = train_stats
    if stats is None:
        raise ValueError(
            f"{target_id}: train fold 에 정의된 MSA feature 가 없어 imputation "
            "statistic 을 만들 수 없다. 이 arm 은 non-evaluable 이다."
        )
    have = _defined(features)
    # 대치는 train fold 평균이 **있는** 이름으로만 한다. 통계가 없는 이름을 0.0
    # 같은 상수로 채우면 모든 타겟이 같은 값을 받아, 정보가 없는데도 측정값인
    # 것처럼 하류로 흐른다.
    names = [name for name in TARGET_FEATURES if name in stats]
    # 그런데 그 좁히기가 **측정된 값**까지 버릴 수 있다. 규칙 2 는 계산된
    # feature 를 그대로 쓰라고 하고, 규칙 5 는 그 경우를 arm non-evaluable 로
    # 기록하라고 한다. 조용히 좁아진 설계행렬로 평가하면 6 개 중 5 개를 잃은
    # arm 도 정상 arm 처럼 보인다 - 그래서 버린 이름을 반드시 남긴다.
    dropped = [name for name in TARGET_FEATURES if name in have and name not in stats]
    if have:
        out = {name: have[name] for name in names if name in have}
        # 지시자는 **대치가 실제로 일어났는가**를 뜻한다 (스펙 §4 규칙 3).
        imputed = [name for name in names if name not in out]
        for name in imputed:
            out[name] = stats[name]
        out["msa_undefined"] = 1 if imputed else 0
    else:
        out = {name: stats[name] for name in names}
        out["msa_undefined"] = 1
    if dropped:
        out["dropped_measured"] = dropped
    return out


def arm_verdict(rows: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    """arm 수준 판정 - 스펙 §4 규칙 5. **타겟을 빼지 않는다.**

    측정값이 버려진 타겟이 하나라도 있으면 그 arm 의 설계행렬이 조용히 좁아진
    것이므로 non-evaluable 로 기록하고 이유에 feature 이름을 남긴다. 이 판정은
    타겟 하나가 아니라 arm 전체에 대한 것이라 `impute()` 안이 아니라 여기에
    있다.
    """
    dropped = {tid: list(row["dropped_measured"])
               for tid, row in rows.items() if row.get("dropped_measured")}
    if not dropped:
        return {"evaluable": True}
    names = sorted({n for v in dropped.values() for n in v})
    return {
        "evaluable": False,
        "reason": (f"train fold 에 imputation statistic 이 없어 측정값을 버린 "
                   f"feature {names} · 타겟 {sorted(dropped)}. 스펙 §4 규칙 5."),
        "dropped_measured_by_target": dropped,
    }
