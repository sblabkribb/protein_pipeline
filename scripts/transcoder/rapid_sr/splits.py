"""누출 방지 split (설계 3.6 / 6.1b).

group 우선순위는 superfamily > target > backbone 이다. 가장 바깥 단위로 묶어야
같은 백본의 서열은 물론 같은 계열의 타겟까지 train/test 로 갈리지 않는다.
소스 암기를 잡기 위한 leave-one-source-out 도 함께 제공한다.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np

from .records import DesignRecord


def parse_cath_domain_list(path: Path) -> dict[str, str]:
    """CathDomainList -> {domain_id: "C.A.T.H"}.

    형식: `domain_id C A T H S O L I D length resolution`
    """
    mapping: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        mapping[parts[0]] = ".".join(parts[1:5])
    return mapping


def attach_superfamily(
    records: Sequence[DesignRecord], mapping: dict[str, str]
) -> list[DesignRecord]:
    return [replace(rec, superfamily=mapping.get(rec.target_id)) for rec in records]


# CATH 코드 깊이: 1=class, 2=architecture, 3=topology, 4=homologous superfamily.
#
# 이 저장소의 CATH 세트(1,472 타겟)를 실측한 결과 topology 와 superfamily 가
# 모두 싱글톤이었다. 즉 depth 3/4 group split 은 타겟 단위 LOTO 와 동일한 분할이
# 된다. 실제로 일반화를 시험하는 상위 그룹은 architecture(depth=2, 43 그룹)뿐이다.
CATH_DEPTH_SUPERFAMILY = 4
CATH_DEPTH_ARCHITECTURE = 2


def cath_group(code: str | None, *, depth: int) -> str | None:
    """CATH 코드를 원하는 깊이로 자른다."""
    if not code:
        return None
    return ".".join(str(code).split(".")[: max(1, int(depth))])


def group_key(rec: DesignRecord, *, cath_depth: int = CATH_DEPTH_SUPERFAMILY) -> str:
    grouped = cath_group(rec.superfamily, depth=cath_depth)
    if grouped:
        return f"cath{cath_depth}:{grouped}"
    if rec.target_id:
        return f"tgt:{rec.target_id}"
    return f"bb:{rec.backbone_id}"


def group_split(
    records: Sequence[DesignRecord],
    *,
    n_splits: int = 5,
    seed: int = 0,
    cath_depth: int = CATH_DEPTH_SUPERFAMILY,
) -> Iterator[dict[str, list[int]]]:
    """그룹 단위 k-fold. 한쪽이 비는 fold 는 내보내지 않는다.

    `cath_depth=2` 로 주면 architecture-holdout 이 된다(설계 6.2 의 어려운 분할).
    """
    keys = [group_key(rec, cath_depth=cath_depth) for rec in records]
    unique = sorted(set(keys))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(unique))

    buckets: list[set[str]] = [set() for _ in range(max(1, int(n_splits)))]
    for rank, idx in enumerate(order):
        buckets[rank % len(buckets)].add(unique[int(idx)])

    for bucket in buckets:
        if not bucket:
            continue
        test_idx = [i for i, key in enumerate(keys) if key in bucket]
        train_idx = [i for i, key in enumerate(keys) if key not in bucket]
        if not test_idx or not train_idx:
            continue
        yield {
            "train_idx": train_idx,
            "test_idx": test_idx,
            "test_groups": sorted(bucket),
            "cath_depth": int(cath_depth),
        }


def leave_one_source_out(
    records: Sequence[DesignRecord],
) -> Iterator[dict[str, object]]:
    """소스 암기 방지용 스트레스 테스트.

    소스가 하나뿐이면 fold 가 퇴화한다. 조용히 건너뛰지 않고 `is_degenerate`
    로 표시해서 호출부가 그 사실을 보고하게 한다.
    """
    for source in sorted({rec.backbone_source for rec in records}):
        test_idx = [i for i, r in enumerate(records) if r.backbone_source == source]
        train_idx = [i for i, r in enumerate(records) if r.backbone_source != source]
        yield {
            "held_out_source": source,
            "train_idx": train_idx,
            "test_idx": test_idx,
            "is_degenerate": not train_idx or not test_idx,
        }
