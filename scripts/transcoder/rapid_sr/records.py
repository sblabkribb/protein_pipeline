from __future__ import annotations

from dataclasses import asdict, dataclass

# 설계 문서 3.5절. AF2 라벨이 어떤 조건에서 생성됐는지를 반드시 구분한다.
# af2_all_candidates       : tier 의 모든 후보에 AF2 를 실행 (편향 없음)
# af2_after_soluprot_filter: SoluProt 점수/순위로 걸러진 후보만 AF2 실행 (절단 표본)
LABEL_REGIMES = ("af2_all_candidates", "af2_after_soluprot_filter")

BACKBONE_SOURCES = ("target", "rfd3", "bioemu")


@dataclass(frozen=True)
class DesignRecord:
    """설계 하나에 대한 라벨 레코드.

    결측 라벨은 반드시 None 이다. 0.0 으로 채우면 pLDDT 실패가 유효값으로
    둔갑한다(설계 3.2).
    """

    design_id: str
    target_id: str
    tier: str
    backbone_id: str
    backbone_source: str
    sequence: str
    soluprot: float | None
    plddt_af2: float | None
    rmsd_af2: float | None
    label_regime: str
    superfamily: str | None = None
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.label_regime not in LABEL_REGIMES:
            raise ValueError(
                f"label_regime must be one of {LABEL_REGIMES}, got {self.label_regime!r}"
            )
        if self.backbone_source not in BACKBONE_SOURCES:
            raise ValueError(
                f"backbone_source must be one of {BACKBONE_SOURCES}, "
                f"got {self.backbone_source!r}"
            )

    def to_row(self) -> dict[str, object]:
        return asdict(self)
