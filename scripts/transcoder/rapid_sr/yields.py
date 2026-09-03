"""백본 단위 yield 집계 (설계 6.1b).

세 지표를 별도로 낸다. 하나로 합치면 어느 게이트에서 걸렀는지 알 수 없다.
`n_backbones` 와 `n_sequences` 도 분리 보고해야 한다 — 서열을 늘린다고
백본 수준 표본이 늘지는 않는다.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .protocol import GATE0_THRESHOLDS
from .records import DesignRecord


def _soluprot_pass(rec: DesignRecord) -> bool | None:
    if rec.soluprot is None:
        return None
    return rec.soluprot >= GATE0_THRESHOLDS["soluprot_min"]


def _structural_pass(rec: DesignRecord) -> bool | None:
    if rec.plddt_af2 is None or rec.rmsd_af2 is None:
        return None
    return (
        rec.plddt_af2 >= GATE0_THRESHOLDS["plddt_min"]
        and rec.rmsd_af2 <= GATE0_THRESHOLDS["rmsd_max"]
    )


def _ratio(flags: list[bool]) -> float | None:
    return (sum(flags) / len(flags)) if flags else None


def backbone_yields(records: Iterable[DesignRecord]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[DesignRecord]] = defaultdict(list)
    for rec in records:
        grouped[rec.backbone_id].append(rec)

    out: dict[str, dict[str, object]] = {}
    for backbone_id, recs in grouped.items():
        solu_flags = [f for f in (_soluprot_pass(r) for r in recs) if f is not None]
        struct_flags = [f for f in (_structural_pass(r) for r in recs) if f is not None]
        joint_flags = [
            bool(_soluprot_pass(r)) and bool(_structural_pass(r))
            for r in recs
            if _soluprot_pass(r) is not None and _structural_pass(r) is not None
        ]

        regimes = {r.label_regime for r in recs}
        regime = next(iter(regimes)) if len(regimes) == 1 else "mixed"

        out[backbone_id] = {
            "backbone_id": backbone_id,
            "backbone_source": recs[0].backbone_source,
            "target_id": recs[0].target_id,
            "n_sequences": len(recs),
            "n_sequences_with_af2": len(struct_flags),
            "soluprot_pass_yield": _ratio(solu_flags),
            "af2_structural_pass_yield": _ratio(struct_flags),
            "joint_pass_yield": _ratio(joint_flags),
            "label_regime": regime,
            # 설계 3.5: 절단 표본의 구조 yield 는 편향되어 있다.
            "structural_yield_is_biased": regime != "af2_all_candidates",
        }
    return out
