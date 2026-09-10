"""홀드아웃 격자 라벨 로딩과 코호트 구성.

코호트 정의는 스펙 §3·§4 다. 여기서 새로 정하는 것은 없다.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import _gate2d as G

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID = GATE0 / "holdout_grid"


@dataclass(frozen=True)
class Fold:
    sequence_id: str
    backbone_key: str
    target_id: str
    plddt: float
    rmsd: float
    soluprot: float
    #: `af2_order_metric.csv` 의 `backbone_source` 열. rfd3 / target(native).
    #: §3 개정이 native 를 배분 풀에서 comparator 로 옮겼으므로 코호트 구성에 필요하다.
    backbone_source: str = ""

    @property
    def joint_pass(self) -> bool:
        return G.is_joint_pass(self.plddt, self.rmsd, self.soluprot)

    @property
    def structural_pass(self) -> bool:
        return G.is_structural_pass(self.plddt, self.rmsd)


@dataclass
class Backbone:
    backbone_key: str
    target_id: str
    folds: list[Fold] = field(default_factory=list)

    @property
    def q_b(self) -> float:
        """joint-pass base rate. Top-4 와 같은 candidate universe 위에서 센다."""
        return sum(1 for f in self.folds if f.joint_pass) / len(self.folds)

    @property
    def is_mixed(self) -> bool:
        return 0.0 < self.q_b < 1.0

    @property
    def backbone_source(self) -> str:
        """이 백본의 source. 한 백본의 폴드는 전부 같은 source 다."""
        return self.folds[0].backbone_source if self.folds else ""


@dataclass
class Grid:
    folds: list[Fold]
    backbones: list[Backbone]

    @property
    def targets(self) -> list[str]:
        return sorted({b.target_id for b in self.backbones})


def _f(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_holdout_grid(path: Path | None = None) -> Grid:
    """af2_order_metric.csv 를 읽는다. status != ok 나 지표 결측 행은 버린다."""
    path = path or (GRID / "af2_order_metric.csv")
    folds: list[Fold] = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "ok":
                continue
            plddt = _f(row.get("plddt", ""))
            rmsd = _f(row.get("rmsd_nonloop_order", ""))
            solu = _f(row.get("soluprot", ""))
            if None in (plddt, rmsd, solu):
                continue
            folds.append(Fold(row["sequence_id"], row["backbone_key"],
                              row["target_id"], plddt, rmsd, solu,
                              row.get("backbone_source", "")))

    grouped: dict[tuple[str, str], Backbone] = {}
    for fold in folds:
        key = (fold.target_id, fold.backbone_key)
        if key not in grouped:
            grouped[key] = Backbone(fold.backbone_key, fold.target_id)
        grouped[key].folds.append(fold)
    backbones = [grouped[k] for k in sorted(grouped)]
    return Grid(folds=folds, backbones=backbones)


def restrict_to_sources(grid: Grid, sources: Sequence[str]) -> Grid:
    """backbone_source 로 코호트를 자른다. 다른 규칙은 그대로 적용된다.

    §3 개정이 native 를 **배분 풀에서 comparator 로** 옮겼다: RAPID 이 계산을
    배분하는 대상은 생성 백본이고, native 를 섞으면 "백본 예측 가능성" 이
    source 를 나타내는 1 비트로 점수를 벌 수 있다 - 타겟내 q_b 분산 분해에서
    between-source 성분이 24.8% 였다(관측된 귀속이지 인과가 아니다).
    그래서 Gate 1 의 1차 코호트는 `("rfd3",)` 다.

    잘린 Grid 를 그대로 `mixed_backbones`·`gate1_informative_targets` 에 넘길 수
    있다 - 코호트 규칙을 source 별로 두 번 쓰지 않는다.
    """
    wanted = {str(s) for s in sources}
    folds = [f for f in grid.folds if f.backbone_source in wanted]
    backbones = [b for b in grid.backbones if b.backbone_source in wanted]
    return Grid(folds=folds, backbones=backbones)


def mixed_backbones(grid: Grid) -> list[Backbone]:
    """Gate 2 코호트. q_b 가 0 도 1 도 아닌 백본."""
    return [b for b in grid.backbones if b.is_mixed]


def gate1_informative_targets(grid: Grid) -> list[str]:
    """Gate 1 informative 타겟. 백본 >= 3 이고 q_b 비상수.

    q_b 가 상수면 타겟 내 Spearman 이 정의되지 않는다. Gate 2 의 제외 사유
    (mixed 백본 0개)와 결과적으로 같은 타겟이지만 사유는 다르다.
    """
    by_target: dict[str, list[float]] = defaultdict(list)
    for b in grid.backbones:
        by_target[b.target_id].append(b.q_b)
    return sorted(t for t, qs in by_target.items()
                  if len(qs) >= 3 and len(set(qs)) > 1)
