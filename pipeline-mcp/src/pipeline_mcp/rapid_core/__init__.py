"""RAPID Core — task 에 무관한 계산 배분.

이 패키지 안에는 **평가 모델의 이름이 하나도 나타나지 않는다.** 구조 예측기도,
용해도 예측기도, 계면 점수기도, 안정성 예측기도. 무엇으로 쟀는지는 TaskProfile
의 관심사이고, Core 는 "다음 계산을 어디에 쓸 것인가" 만 답한다.

이 규칙은 주석과 docstring 에도 적용된다 - 설명하려고 이름을 적어 두면 다음
사람이 그 자리에 진짜 분기를 넣는다. 구체적인 사례가 필요하면 설계 문서
(`docs/specs/rapid-task-profile-adaptive-allocation-v2-design.md`) 를 본다.
테스트 `test_core_package_has_no_model_names` 가 이것을 강제한다.

v1 (`pipeline_mcp.allocation`) 은 동결돼 있고 이 패키지가 그것을 대체하지
않는다. v1 은 `rapid_structural_v1` 프로파일로 재현되며, 그 재현이 깨지지
않는 동안에만 v2 작업을 진행한다.

Phase 1 범위: contract 만. 어떤 실행 경로에도 연결하지 않는다.
"""

from .arm import ArmSchema, DesignArm
from .core import Decision, PolicyProfile, RapidCore
from .evaluation import EvaluationResult, Validity
from .observation import (
    BetaBernoulliModel, BetaPosterior, ObservationModel, scaled_variance_signal,
)
from .permission import OperationalStatus, ScientificPermission, PermissionSet
from .transform import ScoreTransform, TransformKey, TransformRegistry

__all__ = [
    "ArmSchema", "DesignArm",
    "Decision", "PolicyProfile", "RapidCore",
    "BetaBernoulliModel", "BetaPosterior", "ObservationModel",
    "scaled_variance_signal",
    "EvaluationResult", "Validity",
    "OperationalStatus", "ScientificPermission", "PermissionSet",
    "ScoreTransform", "TransformKey", "TransformRegistry",
]
