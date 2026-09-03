"""게이트 0 고정 평가 프로토콜 (설계 6.1b).

백본끼리 yield 를 비교하려면 백본마다 조건이 같아야 한다. 여기 값이 바뀌면
artifact 에 기록되는 지문도 바뀌므로, 캠페인 도중에는 바꾸지 않는다.
"""

from __future__ import annotations

GATE0_THRESHOLDS = {
    "soluprot_min": 0.5,
    "plddt_min": 85.0,
    "rmsd_max": 2.0,
}

# 모든 백본에서 동일해야 하는 ProteinMPNN 설정.
GATE0_MPNN_SETTINGS = {
    "use_soluble_model": True,
    "model_name": "v_48_020",
    "sampling_temp": 0.1,
    "seed": 0,
    "batch_size": 1,
}

# 백본당 생성할 서열 수. 백본 간 동일해야 yield 비교가 성립한다.
#
# 예산 근거: AF2 호출 수 = (백본 수) x (백본당 서열 수) x (tier 수).
# `num_seq_per_tier` 는 파이프라인에서 **백본당** 값이므로
# (백본 10 x 서열 40 x tier 3) 은 run 당 1,200 폴딩이 되어 비현실적이다.
# 게이트 0 의 라벨은 백본 단위 yield 이고 tier 는 별개의 설계 축이므로
# 단일 tier 로 고정해 비용을 1/3 로 줄인다.
# 서열 20개면 비율 추정 표준오차는 p=0.5 에서 약 0.11 이다. 첫 learning curve 에는
# 충분하고, 포화 판정 후 필요하면 늘린다.
GATE0_SEQUENCES_PER_BACKBONE = 20

# 게이트 0 은 단일 tier 로 설계 프로토콜을 고정한다. tier 비교는 SP2 의 축이다.
GATE0_TIERS = [0.5]

# run 당 생성할 백본 수. run 당 AF2 = 5 x 20 x 1 = 100 회.
GATE0_BACKBONES_PER_RUN = 5


def protocol_fingerprint() -> dict[str, object]:
    """artifact 에 그대로 실릴 프로토콜 스냅숏."""
    return {
        "thresholds": dict(GATE0_THRESHOLDS),
        "mpnn_settings": dict(GATE0_MPNN_SETTINGS),
        "sequences_per_backbone": GATE0_SEQUENCES_PER_BACKBONE,
        "tiers": list(GATE0_TIERS),
        "backbones_per_run": GATE0_BACKBONES_PER_RUN,
        "af2_calls_per_run": (
            GATE0_BACKBONES_PER_RUN * GATE0_SEQUENCES_PER_BACKBONE * len(GATE0_TIERS)
        ),
    }
