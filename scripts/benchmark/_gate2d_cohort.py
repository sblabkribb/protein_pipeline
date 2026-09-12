"""홀드아웃 격자 라벨 로딩과 코호트 구성.

코호트 정의는 스펙 §3·§4 다. 여기서 새로 정하는 것은 없다.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import _gate2d as G

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID = GATE0 / "holdout_grid"

#: 격자 12 타겟의 WT 서열 동결값. (sha256, length).
#: 2026-09-10 측정. MSA query 와 전체 문자열이 일치함을 확인한 그 서열이다.
#: 손으로 적은 값이며 production 코드에서 재유도하지 않는다 - 재유도하면 같은
#: 버그를 공유해 검사가 무력해진다.
FROZEN_WT = {
    "1sh6A02": ("abf7c6204f82b0c7034a70fd878adf9442dd590bd2a4279a1f8ebd3f05aed31c", 230),
    "1sp0A00": ("58f21f24e9fac2607e4e029e3d657b77febb747f59541ec61d79c0d3e01887ca", 131),
    "1tm9A00": ("5099d90033bf6c0068e65a7707ee1fcfe596be31c9189e5f3125a8b38cee4224", 137),
    "1vsrA00": ("8a35c3c4ee024f1f9f0cadbd0e97af3d3ec25447937056491efcc34aee98b5c1", 134),
    "2jokA01": ("8d2f4fd28efbc44c0ca0fb5ae3fb54784e0a6a03a785051d0c372e50e02aff8f", 184),
    "3bqwA01": ("82f108d0b59db5bb6f2dd85346a0fd2e71732ebcf4a5e38a6603c2c6120a546c", 347),
    "3es1A01": ("9e5e66f08e4806562ab98e47494a917e7e539cb692a8e4539bc0e6cbe72d9377", 160),
    "3f2pA01": ("6c2f5afe1898a8e8aeae320b424ce10220ddd6ccacd82ee560e6f32adea6a79f", 316),
    "3h7eA02": ("7d3111c347d074c01d18634d91606bb6ba84139fe720ae45f1e464595dfc07ef", 220),
    "5fwaA02": ("eb440991c6d67301671b011c414b26abcb0646cc1fc6f861954f8c43c530e15a", 339),
    "5pc8A00": ("657a831019aba488acccb4c4b658451c32964eee4ea626b20a2bd9b41f6cf685", 115),
    "5xpdA02": ("790302898055f2b9581dc5e4d556ccc0e4cc2b33d530f944bd8d412cb40f36c9", 269),
}


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


def assert_sequence_axis(wt_by_target: Mapping[str, str]) -> None:
    """WT 서열이 동결값과 일치하지 않으면 예외. P3 와 Task 11 의 전제조건.

    보존 마스크와 변이 인덱스가 같은 서열 위에 있어야 한다. 어긋나도 오류가 나지
    않으므로 여기서 fail-closed 한다.
    """
    import hashlib

    problems = []
    for target, (want_sha, want_len) in sorted(FROZEN_WT.items()):
        seq = wt_by_target.get(target)
        if seq is None:
            problems.append(f"{target}: WT 서열이 없다")
            continue
        got = hashlib.sha256(seq.encode()).hexdigest()
        if got != want_sha:
            problems.append(
                f"{target}: sha256 {got[:16]} != {want_sha[:16]} "
                f"(길이 {len(seq)} vs {want_len})")
    if problems:
        raise SystemExit(
            "서열 축이 동결값과 다르다. 보존 마스크와 변이 인덱스가 어긋난 서열 "
            "위에서 계산되면 S4 는 조용히 잡음을 잰다. 중단한다:\n  "
            + "\n  ".join(problems))
