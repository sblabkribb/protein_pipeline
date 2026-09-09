"""frozen v1 을 generic Core 위에 표현한 profile.

이 파일의 목적은 하나다: **generic abstraction 이 frozen v1 정책을 정확히
표현할 수 있는지 증명한다.** 새 알고리즘을 만드는 자리가 아니다.

여기 적힌 상수는 전부 `pipeline_mcp.allocation` 에서 온 값이고, 그 파일은
동결돼 있어 수정하지 않는다. 값이 어긋나면 이 파일을 고친다 - 반대가 아니다.

`generation_condition` 같은 도메인 어휘가 여기 나타나는 것은 정상이다. profile
은 Core 가 아니다. Core (`rapid_core/core.py`) 에는 이 어휘가 없다.
"""

from __future__ import annotations

from ..arm import ArmSchema, DesignArm
from ..core import PolicyProfile, RapidCore
from ..observation import BetaBernoulliModel

#: v1 의 arm 계층. 부분 풀링은 target 에서 일어나고, 판정 단위는 backbone 이다.
V1_SCHEMA = ArmSchema(hierarchy=("target", "backbone"), variation=("condition",))

#: 전부 frozen v1 의 값이다.
V1_PRIOR_MEAN = 0.5
V1_PRIOR_STRENGTH = 2.0
V1_POOLING_STRENGTH = 4.0
V1_MIN_PROBE = 4
V1_SIGNAL_FLOOR = 0.2
V1_BETA = 0.5
V1_GAMMA = 0.2
V1_LAMBDA = 0.1
V1_ETA = 0.5

RAPID_STRUCTURAL_V1 = PolicyProfile(
    profile_id="rapid_structural_v1",
    beta_uncertainty=V1_BETA,
    gamma_diversity=V1_GAMMA,
    lambda_cost=V1_LAMBDA,
    eta_variation_exploration=V1_ETA,
    min_observations=V1_MIN_PROBE,
    allocation_signal_floor=V1_SIGNAL_FLOOR,
    reference_variation=None,      # 호출자가 생산 기준 조건을 넣는다
    variation_key="condition",
    # v1 의 행동 이름을 그대로 쓴다. 이름을 "일반화" 하면 환원이 아니게 된다.
    action_names={
        "probe_more": "probe_more_sequences",
        "verify": "verify_with_af2",
        "abandon": "abandon_backbone",
        "explore_variation": "explore_generation_condition",
    },
    # frozen v1 의 문구를 그대로 옮긴다. 다듬으면 재현이 아니다.
    reason_templates={
        "probe_more": ("관측 {n_observed} 개는 판정하기에 얇다 "
                       "(최소 {min_observations})."),
        "verify": "이미 높은 수율에 붙어 있다. 조건을 바꿔 배울 것이 없다.",
        "abandon": "바닥에 붙어 있다. 조건을 바꿔도 움직일 여지가 없다.",
        "explore_variation": "중간 수율이라 조건을 바꾸면 결과가 움직일 수 있다.",
    },
)


def build_v1_core(arm_specs, *, reference_condition: str | None = None,
                  prior_mean: float = V1_PRIOR_MEAN,
                  prior_strength: float = V1_PRIOR_STRENGTH,
                  pooling_strength: float = V1_POOLING_STRENGTH,
                  costs: dict[str, float] | None = None) -> RapidCore:
    """`(target, backbone, condition)` 목록으로 v1 등가 Core 를 만든다."""
    costs = costs or {}
    arms = []
    for target, backbone, condition in arm_specs:
        dims = {"target": target, "backbone": backbone, "condition": condition}
        key = f"{target}|{backbone}|{condition}"
        arms.append(DesignArm(dimensions=dims, cost_seconds=costs.get(key),
                              _schema=V1_SCHEMA))
    model = BetaBernoulliModel({a.key: a for a in arms}, V1_SCHEMA,
                               prior_mean=prior_mean, prior_strength=prior_strength,
                               pooling_strength=pooling_strength)
    from dataclasses import replace
    policy = replace(RAPID_STRUCTURAL_V1, reference_variation=reference_condition)
    return RapidCore(arms, V1_SCHEMA, model, policy)
