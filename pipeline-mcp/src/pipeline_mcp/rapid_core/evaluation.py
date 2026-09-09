"""evaluator 출력의 공통 형태.

왜 validity 가 first-class 인가
--------------------------------
이번 캠페인에서 같은 실패를 세 번 겪었다.

  동결 지표가 대응을 거부한 48 행이 "값 없음" 과 구분되지 않았다.
  한 평가자 호출 8 건이 전부 예외 타입만 남아 원인을 알 수 없었다.
  한 평가자가 좌표를 0 개 냈는데 22/22 가 "ok" 로 기록됐다.

셋 다 형태가 같다: **호출 흐름에서 status 를 정하고 산출물을 보지 않았다.**
그래서 여기서는 값과 상태를 함께 강제하고, 상태가 ok 가 아니면 이유를 요구한다.

"값이 없다" 와 "실패했다" 와 "거부했다" 는 서로 다른 상태다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Validity(str, Enum):
    """관측이 성립했는가. 셋을 하나로 합치지 않는다."""

    #: 값이 나왔다.
    OK = "ok"
    #: 평가자가 계산을 **거부**했다. 입력이 그 지표의 정의에 맞지 않는다.
    #: 예: 서열 길이가 기준과 달라 대응을 정의할 수 없다. 실패가 아니다.
    REFUSED = "refused"
    #: 평가자가 오류를 냈다. 재시도로 달라질 수 있다.
    FAILED = "failed"
    #: 시도하지 않았다. 실패도 거부도 아니다.
    MISSING = "missing"


class Direction(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


@dataclass(frozen=True)
class EvaluationResult:
    """평가자 하나가 후보 하나에 대해 낸 관측.

    raw measurement 를 그대로 담는다. 여기서 0–1 로 정규화하지 않는다 - 그
    변환은 objective 에 따라 다르고, 평가자는 objective 를 모른다 (§L1).
    """

    evaluator: str
    objective: str
    validity: Validity
    #: 단위가 붙은 원값. validity 가 OK 일 때만 값이 있다.
    raw_value: float | None = None
    unit: str = ""
    direction: Direction | None = None
    uncertainty: float | None = None
    #: 무엇에 대한 값인가. 예: 이 백본 자신의 참조 구조.
    reference: str = ""
    #: 채널 등급. 모델 이름이 아니다.
    fidelity: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    artifact: str = ""
    #: validity 가 OK 가 아니면 반드시 채운다. 타입 이름만으로는 진단이 안 된다.
    failure_reason: str = ""

    def __post_init__(self) -> None:
        if not self.evaluator:
            raise ValueError("evaluator 가 필요하다")
        if not self.objective:
            raise ValueError("objective 가 필요하다")
        if not isinstance(self.validity, Validity):
            raise TypeError(f"validity 는 Validity 여야 한다: {self.validity!r}")
        if self.validity is Validity.OK:
            if self.raw_value is None:
                raise ValueError(
                    f"{self.evaluator}: validity=ok 인데 raw_value 가 없다. "
                    f"값 없이 성공으로 기록하면 산출물이 비어 있어도 성공이 된다.")
            if self.direction is None:
                raise ValueError(
                    f"{self.evaluator}: direction 을 모르면 이 값을 해석할 수 없다")
            if self.failure_reason:
                raise ValueError(
                    f"{self.evaluator}: validity=ok 인데 failure_reason 이 있다")
        else:
            if self.raw_value is not None:
                raise ValueError(
                    f"{self.evaluator}: validity={self.validity.value} 인데 "
                    f"raw_value 가 있다. 성립하지 않은 관측에 값을 붙이지 않는다.")
            if not self.failure_reason.strip():
                raise ValueError(
                    f"{self.evaluator}: validity={self.validity.value} 이면 이유가 "
                    f"필요하다. 예외 타입만 세면 경합인지 입력 오류인지 구분할 수 "
                    f"없다 - 실제로 그래서 8 건의 원인을 놓쳤다.")

    @property
    def usable(self) -> bool:
        return self.validity is Validity.OK

    def to_dict(self) -> dict:
        out = asdict(self)
        out["validity"] = self.validity.value
        out["direction"] = self.direction.value if self.direction else None
        return out
