"""활성 평가 플러그인 계약.

활성은 다른 목표와 다르다. 용해도는 SoluProt 이, 구조 보존은 AF2 가, 안정성은
Rosetta 가 예측을 내놓는다. 활성은 그런 예측기가 없어서 못 하는 것이 아니라,
**타겟마다 다른 실험으로 정의되기 때문에** 못 한다. 효소 회전수, 결합 저해,
형광 - 어떤 모델을 붙여도 그 타겟의 assay 라벨 없이는 맞춰볼 대상이 없다.

그래서 여기서 만드는 것은 예측기가 아니라 계약이다. 라벨을 가진 사람이 자기
assay 를 끼워 넣을 수 있게 하되, 라벨 없이는 아무것도 돌지 않는다.

지어내지 않기 위해 이 파일이 하는 일
------------------------------------
* assay 는 무엇을 쟀는지(readout), 어떤 단위인지, 어느 방향이 좋은지, 그리고
  출처를 반드시 말해야 한다. 출처 없는 라벨은 지어낸 것과 구별되지 않는다.
* 라벨이 없는 설계는 점수를 받지 않는다. 기본값도, 평균 대치도 없다. 목록으로
  따로 돌려주고 coverage 를 함께 낸다.
* 한 타겟의 라벨을 다른 타겟에 쓰지 못한다. 그것이 가장 흔한 라벨 조작이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ActivityPluginError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActivityAssay:
    """한 타겟에서 실제로 측정된 활성 라벨."""

    assay_id: str
    target_id: str
    readout: str
    unit: str
    higher_is_better: bool | None
    labels: dict[str, float]
    source: str

    def __post_init__(self) -> None:
        if not str(self.assay_id).strip():
            raise ActivityPluginError("assay_id 가 필요하다")
        if not str(self.target_id).strip():
            raise ActivityPluginError("target_id 가 필요하다 - 활성은 타겟에 붙는다")
        if not str(self.readout).strip():
            raise ActivityPluginError(
                "readout 이 필요하다. 무엇을 쟀는지 말하지 않은 숫자는 해석할 수 없다"
            )
        if self.higher_is_better is None:
            raise ActivityPluginError(
                "higher_is_better 를 정해야 한다. 방향을 모르면 순위를 매길 수 없다"
            )
        if not self.labels:
            raise ActivityPluginError(
                "라벨이 비어 있다. 활성은 예측이 아니라 측정에서 온다"
            )
        if not str(self.source).strip():
            raise ActivityPluginError(
                "source 가 필요하다. 출처 없는 라벨은 지어낸 것과 구별되지 않는다"
            )

    @property
    def n_labels(self) -> int:
        return len(self.labels)

    def to_dict(self) -> dict:
        return {
            "assay_id": self.assay_id, "target_id": self.target_id,
            "readout": self.readout, "unit": self.unit,
            "higher_is_better": self.higher_is_better,
            "n_labels": self.n_labels, "source": self.source,
        }


#: 등록된 assay. RAPID 는 어떤 타겟의 활성도 알지 못하므로 비어 있는 것이
#: 정직한 기본 상태다. 여기에 무엇이든 미리 넣어두면 그것이 지어낸 라벨이 된다.
_ASSAYS: dict[str, ActivityAssay] = {}


def register_assay(assay: ActivityAssay) -> None:
    _ASSAYS[assay.assay_id] = assay


def registered_assays() -> dict[str, dict]:
    return {key: value.to_dict() for key, value in _ASSAYS.items()}


@dataclass
class ActivityPlugin:
    assay: ActivityAssay | None = None
    _unused: dict = field(default_factory=dict, repr=False)

    def score(self, design_ids, *, target_id: str | None = None) -> dict:
        """라벨이 있는 설계만 점수를 돌려준다.

        없는 설계에 기본값을 주면 그 순간 활성 라벨을 지어내는 것이 된다.
        그래서 따로 목록으로 돌려주고 coverage 를 함께 낸다 - 절반만 라벨된
        코호트에서 순위를 매기면 그 사실이 보여야 한다.
        """
        if self.assay is None:
            raise ActivityPluginError(
                "활성 라벨이 없다. 활성은 타겟마다 다른 실험으로 정의되므로 "
                "예측기를 붙여서 대신할 수 없다. ActivityAssay 를 주입해야 한다."
            )
        if target_id is not None and target_id != self.assay.target_id:
            raise ActivityPluginError(
                f"이 assay 는 {self.assay.target_id} 의 것이다. {target_id} 에 쓰면 "
                f"다른 타겟의 활성 라벨을 옮겨 붙이는 것이 된다."
            )

        ids = [str(design) for design in design_ids]
        scored = {i: self.assay.labels[i] for i in ids if i in self.assay.labels}
        unlabelled = [i for i in ids if i not in self.assay.labels]
        return {
            **self.assay.to_dict(),
            "scored": scored,
            "unlabelled": unlabelled,
            "coverage": round(len(scored) / len(ids), 4) if ids else 0.0,
            "note": (
                "라벨이 없는 설계에는 점수를 주지 않는다. 기본값이나 평균 대치는 "
                "활성 라벨을 지어내는 것과 같다."
            ),
        }
