"""CATH run 디렉터리를 DesignRecord 로 읽는다.

두 종류의 오염을 걸러낸다.

1. **ProteinMPNN 퇴화 unit (설계 3.2).** MPNN 이 실패하면
   `pipeline.py:8231` 이 `fallback_NNN` 샘플을 `num_seq_per_tier` 개 만드는데
   전부 **동일한 야생형 서열**이다. 설계가 아니므로 unit 째로 버린다.
   로컬 CATH 미러에서 이런 행이 15,120 중 5,280(34.9%)이었고, SoluProt 점수는
   정상적으로 붙어 있어 그대로 두면 동일 서열 수천 행이 학습에 들어간다.

2. **AF2 결측.** pLDDT `0` 은 값이 아니라 미수행/실패다. SoluProt·RMSD 의 0 은
   유효값이므로 구분해서 다룬다.
"""

from __future__ import annotations

import json
from pathlib import Path

from .records import DesignRecord

TIERS = ("30", "50", "70")
_SPLIT_PREFIXES = ("cath_train_", "cath_val_", "cath_test_")
_DEFAULT_BACKBONE_ID = "target"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _target_id_from_run(run_dir: Path) -> str:
    name = run_dir.name
    for prefix in _SPLIT_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _primary_backbone_id(run_dir: Path) -> str:
    """CATH run 은 backbone source 가 항상 `target` 인 단일 백본이다."""
    backbones = _load_json(run_dir / "backbones.json").get("backbones") or []
    for entry in backbones:
        if entry.get("primary") and entry.get("id"):
            return str(entry["id"])
    if backbones and backbones[0].get("id"):
        return str(backbones[0]["id"])
    return _DEFAULT_BACKBONE_ID


def _normalize_design_id(raw_id: str, *, backbone_id: str) -> str:
    """id 체계를 점수 쪽(`<backbone>:<n>`)에 맞춘다.

    실데이터에서 `proteinmpnn.json` 의 sample id 는 `1`, `2` 처럼 접두사가 없고
    `soluprot.json`/`af2_scores.json` 은 `target:1` 을 쓴다. 정규화하지 않으면
    두 집합의 교집합이 비어 서열이 라벨에 조인되지 않는다.
    """
    text = str(raw_id)
    return text if ":" in text else f"{backbone_id}:{text}"


def _is_degenerate_unit(samples: list[dict]) -> bool:
    """ProteinMPNN 이 설계를 못 만들고 야생형 복사본만 낸 unit 인가.

    두 신호를 함께 본다. 로컬 CATH 미러 378 unit 에서 두 판정은 완전히
    일치했지만(불일치 0), id 명명 규칙이 바뀌어도 잡히도록 서열 중복도 본다.
    서열이 하나뿐인 unit 은 중복이 아니라 표본이 작은 것이므로 제외한다.
    """
    if not samples:
        return False
    ids = [str(sample.get("id") or "") for sample in samples]
    if ids and all(name.startswith("fallback_") for name in ids):
        return True
    sequences = {str(sample.get("sequence") or "") for sample in samples}
    return len(samples) > 1 and len(sequences) == 1


def _float_or_none(value: object) -> float | None:
    """SoluProt/RMSD 용. 0.0 은 유효값이므로 보존한다."""
    return float(value) if isinstance(value, (int, float)) else None


def _plddt_or_none(value: object) -> float | None:
    """pLDDT 전용. 0.0 은 미수행/실패 표시이므로 결측으로 바꾼다."""
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return None if number == 0.0 else number


def load_cath_run(run_dir: Path) -> list[DesignRecord]:
    target_id = _target_id_from_run(run_dir)
    backbone_id = _primary_backbone_id(run_dir)
    records: list[DesignRecord] = []
    for tier in TIERS:
        tier_dir = run_dir / "tiers" / tier
        if not tier_dir.exists():
            continue

        af2 = _load_json(tier_dir / "af2_scores.json")
        solu = _load_json(tier_dir / "soluprot.json").get("scores") or {}
        mpnn = _load_json(tier_dir / "proteinmpnn.json")
        samples = [s for s in (mpnn.get("samples") or []) if s.get("id") is not None]
        if _is_degenerate_unit(samples):
            # 설계가 아니라 야생형 복사본이다. 마스킹이 아니라 통째로 버린다.
            continue
        seqs = {
            _normalize_design_id(sample.get("id"), backbone_id=backbone_id): str(
                sample.get("sequence") or ""
            )
            for sample in samples
        }

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
            plddt = (
                None if design_id in failed else _plddt_or_none(plddt_scores.get(design_id))
            )
            records.append(
                DesignRecord(
                    design_id=design_id,
                    target_id=target_id,
                    tier=tier,
                    backbone_id=backbone_id,
                    backbone_source="target",
                    sequence=seqs.get(design_id, ""),
                    soluprot=_float_or_none(solu.get(design_id)),
                    plddt_af2=plddt,
                    rmsd_af2=_float_or_none(rmsd_scores.get(design_id)),
                    label_regime=regime,
                    provenance=f"cath:{run_dir.name}:{tier}",
                )
            )
    return records
