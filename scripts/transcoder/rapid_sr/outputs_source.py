"""로컬 `outputs/` run 디렉터리를 DesignRecord 로 읽는다.

CATH 미러와 달리 백본이 여럿이므로 설계 id 접두사(`<backbone_id>:<sample>`)로
백본을 구분하고, 소스는 `backbones.json` 에서 찾는다. 퇴화 unit 처리는
`cath_source` 와 동일하다.
"""

from __future__ import annotations

import json
from pathlib import Path

from .cath_source import _is_degenerate_unit, _float_or_none, _plddt_or_none
from .records import BACKBONE_SOURCES, DesignRecord

TIERS = ("30", "50", "70")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _target_id_from_run(run_dir: Path) -> str:
    # gate0_w1_rfd3_2wejA00 -> 2wejA00
    return run_dir.name.rsplit("_", 1)[-1]


def _backbone_id(design_id: str) -> str:
    return design_id.rsplit(":", 1)[0] if ":" in design_id else "target"


def _tier_samples(run_dir: Path, tier_dir: Path) -> list[dict]:
    """설계 샘플을 모은다.

    단일 백본 run 은 tier 레벨 `proteinmpnn.json` 에 전부 들어 있다.
    다중 백본 run 은 tier 레벨에 `proteinmpnn_backbones.json` 만 있고 실제 샘플은
    `backbones/<id>/tiers/<tier>/proteinmpnn.json` 에 흩어져 있다. 후자를 따라가지
    않으면 모든 서열이 빈 문자열이 되어 특징이 전부 같아진다.
    """
    direct = _load_json(tier_dir / "proteinmpnn.json").get("samples") or []
    if direct:
        return [s for s in direct if s.get("id") is not None]

    index = _load_json(tier_dir / "proteinmpnn_backbones.json").get("backbones") or []
    samples: list[dict] = []
    for entry in index:
        backbone_id = str(entry.get("id") or "")
        raw_path = entry.get("proteinmpnn_json")
        path = Path(raw_path) if raw_path else None
        if path is None or not path.exists():
            # 경로가 절대경로로 굳어 있을 수 있으므로 run 기준으로도 찾아본다.
            path = run_dir / "backbones" / backbone_id / tier_dir.relative_to(
                run_dir
            ) / "proteinmpnn.json"
        for sample in _load_json(path).get("samples") or []:
            sample_id = str(sample.get("id") or "")
            if not sample_id:
                continue
            qualified = sample_id if ":" in sample_id else f"{backbone_id}:{sample_id}"
            samples.append({"id": qualified, "sequence": sample.get("sequence")})
    return samples


def load_output_run(run_dir: Path) -> list[DesignRecord]:
    backbones = _load_json(run_dir / "backbones.json").get("backbones") or []
    source_by_id = {
        str(entry.get("id")): str(entry.get("source") or "target")
        for entry in backbones
        if entry.get("id")
    }
    target_id = _target_id_from_run(run_dir)

    records: list[DesignRecord] = []
    for tier in TIERS:
        tier_dir = run_dir / "tiers" / tier
        if not tier_dir.exists():
            continue

        samples = _tier_samples(run_dir, tier_dir)
        if not samples or _is_degenerate_unit(samples):
            continue
        seqs = {str(s["id"]): str(s.get("sequence") or "") for s in samples}

        af2 = _load_json(tier_dir / "af2_scores.json")
        solu = _load_json(tier_dir / "soluprot.json").get("scores") or {}
        plddt_scores = af2.get("scores") or {}
        rmsd_scores = af2.get("rmsd_scores") or af2.get("target_rmsd_scores") or {}
        failed = set(af2.get("failed_ids") or [])
        failed |= set((af2.get("prediction_errors") or {}).keys())
        regime = (
            "af2_after_soluprot_filter"
            if af2.get("candidate_budget_applied")
            else "af2_all_candidates"
        )

        for design_id in sorted(set(seqs) | set(solu) | set(plddt_scores)):
            backbone_id = _backbone_id(design_id)
            source = source_by_id.get(backbone_id, "target")
            if source not in BACKBONE_SOURCES:
                source = "target"
            sequence = seqs.get(design_id, "")
            if not sequence:
                # 서열 없는 행은 특징이 전부 같아져 조용히 학습을 망친다.
                continue
            plddt = (
                None if design_id in failed else _plddt_or_none(plddt_scores.get(design_id))
            )
            records.append(
                DesignRecord(
                    design_id=design_id,
                    target_id=target_id,
                    tier=tier,
                    backbone_id=backbone_id,
                    backbone_source=source,
                    sequence=sequence,
                    soluprot=_float_or_none(solu.get(design_id)),
                    plddt_af2=plddt,
                    rmsd_af2=_float_or_none(rmsd_scores.get(design_id)),
                    label_regime=regime,
                    provenance=f"outputs:{run_dir.name}:{tier}",
                )
            )
    return records
