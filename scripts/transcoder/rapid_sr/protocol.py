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
GATE0_SEQUENCES_PER_BACKBONE = 40


def protocol_fingerprint() -> dict[str, object]:
    """artifact 에 그대로 실릴 프로토콜 스냅숏."""
    return {
        "thresholds": dict(GATE0_THRESHOLDS),
        "mpnn_settings": dict(GATE0_MPNN_SETTINGS),
        "sequences_per_backbone": GATE0_SEQUENCES_PER_BACKBONE,
    }
