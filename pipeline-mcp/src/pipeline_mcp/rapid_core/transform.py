"""raw measurement → objective 별 해석.

정규화를 evaluator 안에서 하지 않는 이유는 같은 값이 objective 에 따라 다르게
읽히기 때문이다. pLDDT 85 는 structural_preservation 에서는 통과선이지만 다른
objective 에서는 아무 뜻이 없다. evaluator 는 objective 를 모른다.

registry 키에 TaskProfile 이 들어가는 것이 v1 설계와 다른 점이다. 같은
evaluator 가 같은 objective 를 재더라도 task 가 다르면 해석과 허용 역할이
달라질 수 있다 - Gate 0 의 AUC 가 monomer 에서만 측정된 것이 그 예다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .evaluation import EvaluationResult, Validity
from .permission import PermissionSet, ScientificPermission


@dataclass(frozen=True)
class TransformKey:
    task_profile: str
    evaluator: str
    objective: str
    role: ScientificPermission

    def __str__(self) -> str:
        return (f"{self.task_profile}/{self.evaluator}/{self.objective}"
                f"/{self.role.value}")


@dataclass(frozen=True)
class ScoreTransform:
    """버전이 붙은 변환. 버전 없이 결과를 재현할 수 없다."""

    name: str
    version: str
    fn: Callable[[float], float]
    #: 변환 결과가 무엇을 뜻하는지. 0–1 로 강제하지 않는다.
    output_meaning: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ValueError("ScoreTransform 에는 name 과 version 이 필요하다")

    def apply(self, result: EvaluationResult) -> float:
        """성립하지 않은 관측을 숫자로 바꾸지 않는다."""
        if result.validity is not Validity.OK:
            raise ValueError(
                f"{self.name}: validity={result.validity.value} 인 관측은 변환할 수 "
                f"없다 ({result.failure_reason[:80]}). 거부와 실패를 0 으로 바꾸면 "
                f"그 0 이 나쁜 값처럼 집계된다.")
        if result.raw_value is None:
            raise ValueError(f"{self.name}: raw_value 가 없다")
        return float(self.fn(float(result.raw_value)))


class TransformRegistry:
    """(task, evaluator, objective, role) → ScoreTransform.

    등록되지 않은 조합은 비슷한 것으로 대체하지 않고 실패한다.
    """

    def __init__(self) -> None:
        self._by_key: dict[TransformKey, ScoreTransform] = {}
        self._permissions: dict[tuple[str, str, str], PermissionSet] = {}

    def register_permission(self, permission: PermissionSet) -> None:
        key = (permission.task_profile, permission.evaluator, permission.objective)
        if key in self._permissions:
            raise ValueError(f"허가 중복 등록: {key}")
        self._permissions[key] = permission

    def register(self, key: TransformKey, transform: ScoreTransform) -> None:
        permission = self._permissions.get(
            (key.task_profile, key.evaluator, key.objective))
        if permission is None:
            raise KeyError(
                f"{key}: 허가가 먼저 등록돼야 한다. 변환을 붙였다는 이유로 "
                f"쓸 수 있게 되지 않는다.")
        permission.require(key.role)
        if key in self._by_key:
            raise ValueError(f"변환 중복 등록: {key}")
        self._by_key[key] = transform

    def resolve(self, key: TransformKey) -> ScoreTransform:
        transform = self._by_key.get(key)
        if transform is None:
            known = sorted(str(k) for k in self._by_key)
            raise KeyError(
                f"{key} 에 등록된 ScoreTransform 이 없다. 등록된 것: {known or '없음'}. "
                f"유사한 변환으로 대체하지 않는다.")
        return transform

    def transform(self, key: TransformKey, result: EvaluationResult) -> float:
        if result.evaluator != key.evaluator or result.objective != key.objective:
            raise ValueError(
                f"결과({result.evaluator}/{result.objective})와 "
                f"키({key.evaluator}/{key.objective})가 다르다")
        return self.resolve(key).apply(result)
