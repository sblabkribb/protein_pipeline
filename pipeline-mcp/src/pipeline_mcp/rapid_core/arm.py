"""배분의 결정 단위 — task 가 모양을 정한다.

v1 은 `arm = backbone × generation_condition` 이고 그 정의는 frozen profile 에서
그대로 유지된다. 다만 그것을 모든 task 의 arm 정의로 못 박지 않는다 - 형제
pipeline 의 반복 단위는 다르다.

Core 는 arm 을 불투명 식별자로 다루고, 계층 구조만 schema 로 받는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ArmSchema:
    """arm dimension 의 구조. TaskProfile 이 선언한다.

    hierarchy 는 바깥에서 안으로 가는 grouping 축이다. 부분 풀링은 hierarchy[0]
    에서 일어나고, 판정 단위(움직일 수 있는지 보고 그만둘지 정하는 단위)는
    hierarchy 전체다. variation 은 그 아래에서 arm 을 가르는 축이다.

    v1: hierarchy = ("target", "backbone"), variation = ("condition",)
    """

    hierarchy: tuple[str, ...]
    variation: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.hierarchy:
            raise ValueError("hierarchy 가 비어 있으면 풀링 수준을 정할 수 없다")
        overlap = set(self.hierarchy) & set(self.variation)
        if overlap:
            raise ValueError(f"hierarchy 와 variation 이 겹친다: {sorted(overlap)}")

    @property
    def dimensions(self) -> tuple[str, ...]:
        return self.hierarchy + self.variation

    @property
    def pooling_key(self) -> str:
        return self.hierarchy[0]


@dataclass(frozen=True)
class DesignArm:
    """dimensions 의 키는 schema 가 정한다. Core 는 그 뜻을 모른다."""

    dimensions: Mapping[str, str]
    #: 한 번 관측하는 비용(초). 모르면 None - 0 이 아니다. 0 으로 두면
    #: 비용을 모르는 arm 이 가장 싼 것처럼 보인다.
    cost_seconds: float | None = None
    _schema: ArmSchema | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._schema is not None:
            missing = [d for d in self._schema.dimensions if d not in self.dimensions]
            if missing:
                raise ValueError(f"dimension 누락: {missing}")

    @property
    def key(self) -> str:
        """v1 과 같은 형식: 값들을 '|' 로 이은 것."""
        return "|".join(str(self.dimensions[d]) for d in sorted(self.dimensions)) \
            if self._schema is None else \
            "|".join(str(self.dimensions[d]) for d in self._schema.dimensions)

    def group(self, schema: ArmSchema, depth: int | None = None) -> tuple[str, ...]:
        levels = schema.hierarchy if depth is None else schema.hierarchy[:depth]
        return tuple(str(self.dimensions[d]) for d in levels)

    def matched_depth(self, other: "DesignArm", schema: ArmSchema) -> int:
        """앞에서부터 몇 개 계층이 같은가. 다양성 벌점의 재료다."""
        depth = 0
        for level in schema.hierarchy:
            if self.dimensions.get(level) != other.dimensions.get(level):
                break
            depth += 1
        if depth == len(schema.hierarchy):
            # 계층이 전부 같으면 variation 까지 봐야 같은 arm 인지 안다.
            if all(self.dimensions.get(v) == other.dimensions.get(v)
                   for v in schema.variation):
                return depth
        return depth
