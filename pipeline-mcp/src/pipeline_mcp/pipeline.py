from __future__ import annotations

import copy
from dataclasses import MISSING
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import fields
import base64
import hashlib
import json
import math
import os
import shutil
import time
from pathlib import Path
import re
from typing import Any
from collections.abc import Callable

from .af2_utils import af2_error_is_missing_pdb_outputs
from .af2_utils import af2_payload_has_missing_pdb_failure
from .agent_panel import emit_agent_panel_event
from .agent_panel import write_agent_panel_report
from .bio.a3m import compute_conservation
from .bio.a3m import decode_a3m_gz_b64
from .bio.a3m import filter_a3m
from .bio.a3m import msa_quality
from .bio.a3m import strip_insertions
from .bio.a3m import weights_from_mmseqs_cluster_tsv
from .bio.fasta import FastaRecord
from .bio.fasta import parse_fasta
from .bio.fasta import to_fasta
from .bio.ligand_text import normalize_diffdock_ligand_inputs
from .bio.alignment import global_alignment_mapping
from .bio.pdb import ca_rmsd
from .bio.pdb import dssp_non_loop_positions_by_chain
from .bio.pdb import ligand_atoms_present
from .bio.pdb import ligand_proximity_mask
from .bio.pdb import preprocess_pdb
from .bio.pdb import residues_by_chain
from .bio.pdb import sequence_by_chain
from .bio.pdb import surface_positions_by_chain
from .bio.sequence import filter_records_by_pi
from .bio.sdf import append_ligand_pdb
from .bio.sdf import sdf_to_pdb
from .clients.mmseqs import MMseqsClient
from .clients.proteinmpnn import ProteinMPNNClient
from .clients.soluprot import SoluProtClient
from .models import PipelineRequest
from .models import PipelineResult
from .models import SequenceRecord
from .models import TierResult
from .mutation_report import write_mutation_reports
from .storage import RunPaths
from .storage import clear_cancel_requested
from .storage import init_run
from .storage import is_cancel_requested
from .storage import new_run_id
from .storage import set_status
from .storage import write_json
from .evolution import run_evolution


_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_AF2_ALLOWED_AA = set("ACDEFGHIKLMNPQRSTVWYX")
_AF2_PROVIDER_COLABFOLD = "colabfold"
_AF2_PROVIDER_AF2 = "af2"
_AF2_RMSD_REFERENCE_MODE_PARENT_BACKBONE = "parent_backbone"
_PIPELINE_STAGE_ORDER = [
    "msa",
    "rfd3",
    "bioemu",
    "design",
    "soluprot",
    "af2",
    "novelty",
]
_SUMMARY_ARTIFACTS = (
    "summary.json",
    "comparisons.json",
    "report.md",
    "report_ko.md",
    "agent_panel_report.md",
    "agent_panel_report_ko.md",
    "agent_panel.jsonl",
)
_PARTIAL_RERUN_IGNORED_FIELDS = {
    "project_id",
    "round_id",
    "start_from",
    "stop_after",
    "force",
    "auto_recover",
    "agent_panel_enabled",
    "selected_tiers",
}
_PARTIAL_RERUN_DESIGN_FIELDS = {
    "target_fasta",
    "target_pdb",
    "rfd3_inputs",
    "rfd3_inputs_text",
    "rfd3_input_files",
    "rfd3_input_pdb",
    "rfd3_mode",
    "rfd3_spec_name",
    "rfd3_contig",
    "rfd3_hotspots",
    "rfd3_infer_ori_strategy",
    "rfd3_is_non_loopy",
    "rfd3_unindex",
    "rfd3_length",
    "rfd3_select_fixed_atoms",
    "rfd3_ligand",
    "rfd3_select_unfixed_sequence",
    "rfd3_cli_args",
    "rfd3_env",
    "rfd3_design_index",
    "rfd3_use_ensemble",
    "rfd3_max_return_designs",
    "rfd3_partial_t",
    "rfd3_sampling_strategy",
    "rfd3_fail_on_duplicate_backbones",
    "rfd3_target_rmsd_cutoff",
    "rfd3_max_attempted_designs",
    "bioemu_use",
    "bioemu_sequence",
    "bioemu_num_samples",
    "bioemu_batch_size_100",
    "bioemu_model_name",
    "bioemu_filter_samples",
    "bioemu_base_seed",
    "bioemu_steering_config_text",
    "bioemu_max_return_structures",
    "bioemu_target_rmsd_cutoff",
    "bioemu_max_attempted_structures",
    "bioemu_env",
    "design_chains",
    "fixed_positions_extra",
    "conservation_tiers",
    "conservation_mode",
    "conservation_weighting",
    "conservation_cluster_method",
    "conservation_cluster_min_seq_id",
    "conservation_cluster_coverage",
    "conservation_cluster_cov_mode",
    "conservation_cluster_kmer_per_seq",
    "ligand_mask_distance",
    "ligand_resnames",
    "ligand_atom_chains",
    "ligand_mask_use_original_target",
    "surface_only",
    "surface_min_rel",
    "surface_min_abs",
    "pdb_strip_nonpositive_resseq",
    "pdb_renumber_resseq_from_1",
    "num_seq_per_tier",
    "batch_size",
    "sampling_temp",
    "seed",
    "mmseqs_target_db",
    "mmseqs_max_seqs",
    "mmseqs_threads",
    "mmseqs_use_gpu",
    "msa_min_coverage",
    "msa_min_identity",
    "query_pdb_min_identity",
    "query_pdb_policy",
    "mask_consensus_apply",
    "dry_run",
}
_PARTIAL_RERUN_SOLUPROT_FIELDS = {"soluprot_cutoff", "pi_min", "pi_max"}
_PARTIAL_RERUN_AF2_FIELDS = {
    "af2_model_preset",
    "af2_db_preset",
    "af2_max_template_date",
    "af2_extra_flags",
    "af2_provider",
    "af2_plddt_cutoff",
    "af2_rmsd_cutoff",
    "af2_max_candidates_per_tier",
    "af2_top_k",
    "af2_sequence_ids",
    "relax_enabled",
    "relax_score_per_residue_cutoff",
    "relax_nstruct",
    "relax_extra_flags",
}
_PARTIAL_RERUN_NOVELTY_FIELDS = {"novelty_enabled", "novelty_target_db", "wt_compare"}


def _normalize_pipeline_stage(value: object | None) -> str | None:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"wt_diff", "wtdiff"}:
        raw = "novelty"
    if not raw:
        return None
    if raw not in _PIPELINE_STAGE_ORDER:
        return None
    return raw


def _stage_index(stage: str) -> int:
    return _PIPELINE_STAGE_ORDER.index(stage)


def _remove_path_if_exists(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return True
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _cleanup_selected_tier_keys(selected_tier_keys: set[str] | None) -> list[str]:
    if not selected_tier_keys:
        return []
    return sorted({str(key).strip() for key in selected_tier_keys if str(key).strip()})


def _clear_tier_outputs_from_stage(
    root: Path,
    *,
    start_from: str,
    selected_tier_keys: set[str] | None = None,
) -> list[str]:
    removed: list[str] = []
    tiers_dir = root / "tiers"
    if not tiers_dir.exists():
        return removed
    tier_keys = _cleanup_selected_tier_keys(selected_tier_keys)

    if start_from == "design":
        if not tier_keys:
            if _remove_path_if_exists(tiers_dir):
                removed.append("tiers/")
        else:
            for tier_key in tier_keys:
                tier_path = tiers_dir / tier_key
                if _remove_path_if_exists(tier_path):
                    removed.append(f"tiers/{tier_key}/")
            backbones_dir = root / "backbones"
            if backbones_dir.exists():
                for backbone_dir in sorted(
                    p for p in backbones_dir.iterdir() if p.is_dir()
                ):
                    for tier_key in tier_keys:
                        tier_path = backbone_dir / "tiers" / tier_key
                        if _remove_path_if_exists(tier_path):
                            removed.append(
                                f"backbones/{backbone_dir.name}/tiers/{tier_key}/"
                            )
        return removed

    for tier_dir in sorted(tiers_dir.iterdir()):
        if not tier_dir.is_dir():
            continue
        if tier_keys and tier_dir.name not in tier_keys:
            continue
        rel_prefix = f"tiers/{tier_dir.name}"

        def _remove(rel_name: str) -> None:
            path = tier_dir / rel_name
            if _remove_path_if_exists(path):
                suffix = "/" if path.is_dir() else ""
                removed.append(f"{rel_prefix}/{rel_name}{suffix}")

        if start_from == "soluprot":
            _remove("soluprot.json")
            _remove("designs_filtered.fasta")
            _remove("af2")
            _remove("af2_scores.json")
            _remove("af2_selected.fasta")
            _remove("relax")
            _remove("relax_scores.json")
            _remove("relax_selected.fasta")
            _remove("novelty.tsv")
            _remove("novelty.json")
            continue

        if start_from == "af2":
            _remove("af2")
            _remove("af2_scores.json")
            _remove("af2_selected.fasta")
            _remove("relax")
            _remove("relax_scores.json")
            _remove("relax_selected.fasta")
            _remove("novelty.tsv")
            _remove("novelty.json")
            continue

        if start_from == "novelty":
            _remove("novelty.tsv")
            _remove("novelty.json")

    return removed


def _clear_stage_outputs_from(
    root: Path,
    *,
    start_from: str,
    selected_tier_keys: set[str] | None = None,
) -> list[str]:
    removed: list[str] = []

    def _remove(rel_path: str) -> None:
        path = root / rel_path
        if _remove_path_if_exists(path):
            suffix = "/" if path.is_dir() else ""
            removed.append(f"{rel_path}{suffix}")

    # These are regenerated from current run outputs and should not be stale across partial reruns.
    for rel in _SUMMARY_ARTIFACTS:
        _remove(rel)

    if start_from == "msa":
        for rel in (
            "msa",
            "conservation.json",
            "rfd3",
            "bioemu",
            "backbones",
            "backbones.json",
            "chain_strategy.json",
            "query_pdb_alignment.json",
            "query_pdb_check.json",
            "ligand_mask.json",
            "surface_mask.json",
            "mask_consensus.json",
            "wt",
            "diffdock",
            "tiers",
            "target.pdb",
            "target.original.pdb",
            "af2_target_runpod_job.json",
        ):
            _remove(rel)
        return removed

    if start_from == "rfd3":
        for rel in (
            "rfd3",
            "bioemu",
            "backbones",
            "backbones.json",
            "chain_strategy.json",
            "query_pdb_alignment.json",
            "query_pdb_check.json",
            "ligand_mask.json",
            "surface_mask.json",
            "mask_consensus.json",
            "wt",
            "diffdock",
            "tiers",
            "target.pdb",
            "target.original.pdb",
            "af2_target_runpod_job.json",
        ):
            _remove(rel)
        return removed

    if start_from == "bioemu":
        for rel in (
            "bioemu",
            "backbones",
            "backbones.json",
            "chain_strategy.json",
            "query_pdb_alignment.json",
            "query_pdb_check.json",
            "ligand_mask.json",
            "surface_mask.json",
            "mask_consensus.json",
            "wt",
            "diffdock",
            "tiers",
        ):
            _remove(rel)
        return removed

    _remove("wt")
    removed.extend(
        _clear_tier_outputs_from_stage(
            root,
            start_from=start_from,
            selected_tier_keys=selected_tier_keys,
        )
    )
    return removed


def _format_set(values: set[str], *, limit: int = 12) -> str:
    items = sorted(values)
    if len(items) <= limit:
        return "{" + ", ".join(repr(x) for x in items) + "}"
    head = items[:limit]
    return (
        "{" + ", ".join(repr(x) for x in head) + f", ... (+{len(items) - limit})" + "}"
    )


def _load_jobs_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in jobs.items():
        if not isinstance(v, str) or not v.strip():
            continue
        out[str(k)] = str(v).strip()
    return out


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _tier_key(tier: float) -> str:
    return f"{int(round(float(tier) * 100.0))}"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_json(obj: object) -> object:
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def _stable_payload_hash(payload: Any) -> str:
    try:
        text = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
    except Exception:
        text = json.dumps(
            _safe_json(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _normalize_request_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_request_value(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, list):
        return [_normalize_request_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_request_value(item) for item in value]
    return value


def _default_request_field_value(field_info: Any) -> Any:
    if field_info.default is not MISSING:
        return copy.deepcopy(field_info.default)
    if field_info.default_factory is not MISSING:  # type: ignore[comparison-overlap]
        return field_info.default_factory()
    return None


def _normalize_request_payload(
    payload: dict[str, Any] | PipelineRequest,
) -> dict[str, Any]:
    raw = (
        asdict(payload) if isinstance(payload, PipelineRequest) else dict(payload or {})
    )
    normalized: dict[str, Any] = {}
    for field_info in fields(PipelineRequest):
        key = field_info.name
        value = raw.get(key, _default_request_field_value(field_info))
        if key in {"start_from", "stop_after"}:
            value = _normalize_pipeline_stage(value)
        elif key == "af2_provider":
            value = _normalize_af2_provider(value)
        normalized[key] = _normalize_request_value(value)
    return normalized


def _changed_request_fields(
    saved_payload: dict[str, Any], current_payload: dict[str, Any]
) -> set[str]:
    changed: set[str] = set()
    for field_info in fields(PipelineRequest):
        key = field_info.name
        if key in _PARTIAL_RERUN_IGNORED_FIELDS:
            continue
        if saved_payload.get(key) != current_payload.get(key):
            changed.add(key)
    return changed


def _minimum_safe_partial_rerun_stage(
    saved_payload: dict[str, Any], current_payload: dict[str, Any]
) -> tuple[str | None, list[str]]:
    changed = _changed_request_fields(saved_payload, current_payload)
    if not changed:
        return None, []

    for stage_name, stage_keys in (
        ("design", _PARTIAL_RERUN_DESIGN_FIELDS),
        ("soluprot", _PARTIAL_RERUN_SOLUPROT_FIELDS),
        ("af2", _PARTIAL_RERUN_AF2_FIELDS),
        ("novelty", _PARTIAL_RERUN_NOVELTY_FIELDS),
    ):
        matched = sorted(changed & stage_keys)
        if matched:
            return stage_name, matched

    return "design", sorted(changed)


def _selected_tier_key(value: object) -> str:
    tier = float(value)
    if abs(tier) > 1.0:
        tier = tier / 100.0
    return _tier_key(tier)


def _resolve_active_tiers(request: PipelineRequest) -> tuple[list[float], set[str]]:
    configured_tiers = [float(tier) for tier in (request.conservation_tiers or [])]
    if not configured_tiers:
        configured_tiers = [0.3, 0.5, 0.7]

    configured_by_key: dict[str, float] = {}
    configured_order: list[str] = []
    for tier in configured_tiers:
        key = _tier_key(tier)
        if key in configured_by_key:
            continue
        configured_by_key[key] = float(tier)
        configured_order.append(key)

    raw_selected = getattr(request, "selected_tiers", None)
    if not raw_selected:
        return [configured_by_key[key] for key in configured_order], set(
            configured_order
        )

    selected_keys: set[str] = set()
    for value in raw_selected:
        selected_keys.add(_selected_tier_key(value))

    missing_keys = sorted(key for key in selected_keys if key not in configured_by_key)
    if missing_keys:
        raise PipelineInputRequired(
            stage="init",
            message=(
                "selected_tiers must be a subset of conservation_tiers; "
                f"configured={configured_order}, selected_missing={missing_keys}"
            ),
        )

    active_tiers = [
        configured_by_key[key] for key in configured_order if key in selected_keys
    ]
    return active_tiers, selected_keys


def _runpod_meta_matches(meta: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if key in meta and meta.get(key) != value:
            return False
    return True


class PipelineInputRequired(ValueError):
    def __init__(self, *, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class PipelineCancelled(RuntimeError):
    def __init__(self, *, stage: str, message: str | None = None) -> None:
        super().__init__(message or "run cancellation requested")
        self.stage = stage


class BackboneContractError(RuntimeError):
    pass


def _safe_id(value: str) -> str:
    safe = _SAFE_ID_RE.sub("_", value).strip("._-")
    return safe[:128] or "id"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _workspace_root(output_root: str) -> Path:
    return Path(str(output_root or "")).expanduser().resolve() / "_workspace"


def _round_record_path(output_root: str, project_id: str, round_id: str) -> Path:
    return (
        _workspace_root(output_root)
        / "projects"
        / _safe_id(project_id)
        / "rounds"
        / f"{_safe_id(round_id)}.json"
    )


def _attach_run_to_round_record(
    output_root: str, request: PipelineRequest, run_id: str
) -> None:
    project_id = str(getattr(request, "project_id", "") or "").strip()
    round_id = str(getattr(request, "round_id", "") or "").strip()
    if round_id and not project_id:
        raise PipelineInputRequired(
            stage="init",
            message="round_id requires project_id.",
        )
    if not project_id or not round_id:
        return
    round_path = _round_record_path(output_root, project_id, round_id)
    if not round_path.exists():
        raise PipelineInputRequired(
            stage="init",
            message=f"round_id={round_id!r} was not found under project_id={project_id!r}.",
        )
    try:
        raw = json.loads(round_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PipelineInputRequired(
            stage="init",
            message=f"Failed to read round metadata for project_id={project_id!r}, round_id={round_id!r}: {exc}",
        ) from exc
    if not isinstance(raw, dict):
        raise PipelineInputRequired(
            stage="init",
            message=f"Round metadata for project_id={project_id!r}, round_id={round_id!r} is invalid.",
        )
    linked_run_ids: list[str] = []
    for item in raw.get("linked_run_ids") or []:
        text = str(item or "").strip()
        if text and text not in linked_run_ids:
            linked_run_ids.append(text)
    if run_id not in linked_run_ids:
        linked_run_ids.append(run_id)
    raw["linked_run_ids"] = linked_run_ids
    raw["updated_at"] = _now_iso()
    write_json(round_path, raw)


def _should_retry_cached_wt_af2(payload: dict[str, Any] | None) -> bool:
    return (
        isinstance(payload, dict)
        and bool(payload.get("skipped"))
        and af2_payload_has_missing_pdb_failure(payload)
    )


def _should_retry_cached_tier_af2(payload: dict[str, Any] | None) -> bool:
    return isinstance(payload, dict) and af2_payload_has_missing_pdb_failure(payload)


def _relax_payload_has_recovered_failure(payload: dict[str, Any] | None) -> bool:
    return isinstance(payload, dict) and bool(payload.get("recovered"))


def _canonicalize_rfd3_design_id(value: object | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    safe = _safe_id(raw)
    low = safe.lower()
    if low.startswith("rfd3"):
        return safe
    if low.startswith("inputs_"):
        tail = safe[len("inputs_") :].lstrip("._-")
        return f"rfd3_{tail}" if tail else "rfd3"
    if low.startswith("inputs-"):
        tail = safe[len("inputs-") :].lstrip("._-")
        return f"rfd3_{tail}" if tail else "rfd3"
    if low in {"selected", "cached", "recovered", "dry_run"}:
        return f"rfd3_{low}"
    return f"rfd3_{safe}"


def _canonicalize_rfd3_output_name(value: object | None) -> str:
    raw = str(value or "").strip()
    if not raw or "/" in raw or "\\" in raw:
        return raw
    for suffix in (".cif.gz", ".json", ".pdb", ".cif"):
        if raw.lower().endswith(suffix):
            stem = raw[: -len(suffix)]
            return f"{_canonicalize_rfd3_design_id(stem)}{raw[-len(suffix) :]}"
    return _canonicalize_rfd3_design_id(raw)


def _canonicalize_rfd3_design_record(record: dict[str, Any]) -> dict[str, Any]:
    item = dict(record)
    raw_id = str(item.get("id") or "").strip()
    canonical_id = _canonicalize_rfd3_design_id(raw_id)
    if canonical_id:
        item["id"] = canonical_id
        if raw_id and raw_id != canonical_id:
            item.setdefault("upstream_id", raw_id)
    for key in ("cif_gz_name", "json_name", "pdb_name"):
        raw_name = str(item.get(key) or "").strip()
        if not raw_name:
            continue
        canonical_name = _canonicalize_rfd3_output_name(raw_name)
        if canonical_name and canonical_name != raw_name:
            item.setdefault(f"upstream_{key}", raw_name)
            item[key] = canonical_name
    return item


def _canonicalize_rfd3_design_list(items: object) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(_canonicalize_rfd3_design_record(item))
    return out


def _normalize_rfd3_sampling_strategy(value: object | None) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": "auto",
        "auto": "auto",
        "default": "auto",
        "batch": "batch",
        "ensemble": "batch",
        "independent": "independent_jobs",
        "independent_job": "independent_jobs",
        "independent_jobs": "independent_jobs",
        "single": "independent_jobs",
        "single_job": "independent_jobs",
        "single_shot": "independent_jobs",
    }
    return aliases.get(raw, "auto")


def _rfd3_duplicate_backbone_message(
    *, requested_count: int, unique_count: int, duplicate_count: int
) -> str | None:
    requested = max(0, int(requested_count or 0))
    if requested <= 1:
        return None
    unique = max(0, int(unique_count or 0))
    if unique >= requested:
        return None
    duplicates = max(0, int(duplicate_count or 0))
    return (
        f"RFD3 duplicate backbone collapse left only {unique} unique backbone(s) for requested {requested}. "
        f"Exact CA duplicate count={duplicates}."
    )


def _rfd3_target_gate_message(
    *,
    requested_count: int,
    accepted_count: int,
    rejected_count: int,
    cutoff: float | None,
) -> str | None:
    requested = max(0, int(requested_count or 0))
    accepted = max(0, int(accepted_count or 0))
    if requested <= 0 or accepted >= requested:
        return None
    if not isinstance(cutoff, (int, float)):
        return None
    rejected = max(0, int(rejected_count or 0))
    if rejected <= 0:
        return None
    return (
        f"RFD3 target RMSD gate accepted only {accepted} backbone(s) for requested {requested}. "
        f"Rejected {rejected} backbone(s) above cutoff {float(cutoff):.3f}A."
    )


def _recommended_bioemu_num_samples(
    requested_return_count: int, filter_samples: bool
) -> int:
    requested = max(1, int(requested_return_count or 1))
    return requested * 2 if filter_samples else requested


def _bioemu_attempt_num_samples(
    requested_return_count: int,
    *,
    configured_num_samples: int,
    configured_return_count: int,
) -> int:
    requested = max(1, int(requested_return_count or 1))
    configured_return = max(1, int(configured_return_count or 1))
    configured_samples = max(requested, int(configured_num_samples or requested))
    scale = max(1.0, configured_samples / configured_return)
    return max(requested, int(math.ceil(requested * scale)))


def _bioemu_target_gate_message(
    *,
    requested_count: int,
    accepted_count: int,
    rejected_count: int,
    cutoff: float | None,
) -> str | None:
    requested = max(0, int(requested_count or 0))
    accepted = max(0, int(accepted_count or 0))
    if requested <= 0 or accepted >= requested:
        return None
    if not isinstance(cutoff, (int, float)):
        return None
    rejected = max(0, int(rejected_count or 0))
    if rejected <= 0:
        return None
    return (
        f"BioEmu target RMSD gate accepted only {accepted} backbone(s) for requested {requested}. "
        f"Rejected {rejected} backbone(s) above cutoff {float(cutoff):.3f}A."
    )


def _rfd3_uniquify_design_records(
    records: list[dict[str, Any]] | None,
    *,
    label: str,
    existing_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    used = {
        str(item or "").strip()
        for item in (existing_ids or set())
        if str(item or "").strip()
    }
    out: list[dict[str, Any]] = []
    suffix_counter = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        item = dict(record)
        base_id = str(item.get("id") or "").strip() or _canonicalize_rfd3_design_id(
            f"{label}_{index}"
        )
        unique_id = base_id
        while unique_id in used:
            suffix_counter += 1
            unique_id = _canonicalize_rfd3_design_id(
                f"{base_id}_{label}_{suffix_counter}"
            )
        if unique_id != base_id:
            item.setdefault("upstream_id", base_id)
            item["id"] = unique_id
        item.setdefault("debug_attempt", label)
        used.add(unique_id)
        out.append(item)
    return out


def _bioemu_uniquify_sample_records(
    records: list[dict[str, Any]] | None,
    *,
    label: str,
    existing_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    used = {
        str(item or "").strip()
        for item in (existing_ids or set())
        if str(item or "").strip()
    }
    out: list[dict[str, Any]] = []
    suffix_counter = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        item = dict(record)
        base_id = str(item.get("id") or "").strip() or f"bioemu_{label}_{index:03d}"
        unique_id = base_id
        while unique_id in used:
            suffix_counter += 1
            unique_id = f"{base_id}_{label}_{suffix_counter}"
        if unique_id != base_id:
            item.setdefault("upstream_id", base_id)
            item["id"] = unique_id
        item.setdefault("debug_attempt", label)
        used.add(unique_id)
        out.append(item)
    return out


def _rfd3_design_records_to_backbones(
    records: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    backbones: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_id = str(record.get("id") or "").strip()
        pdb_text = str(record.get("pdb") or record.get("pdb_text") or "")
        if not raw_id or not pdb_text.strip():
            continue
        backbones.append(
            {
                "id": raw_id,
                "pdb_text": pdb_text,
                "score": record.get("score"),
                "source": "rfd3",
            }
        )
    return backbones


def _write_named_pdb_records(
    directory: Path,
    records: list[dict[str, Any]] | None,
    *,
    pdb_keys: tuple[str, ...] = ("pdb_text", "pdb"),
) -> None:
    _remove_path_if_exists(directory)
    if not isinstance(records, list) or not records:
        return
    out_dir = _ensure_dir(directory)
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("id") or f"record_{index}").strip()
        pdb_text = ""
        for key in pdb_keys:
            value = str(record.get(key) or "")
            if value.strip():
                pdb_text = value
                break
        if not pdb_text.strip():
            continue
        _write_text(out_dir / f"{_safe_id(record_id)}.pdb", pdb_text)


def _backbone_materialized_count(backbones: list[dict[str, Any]] | None) -> int:
    if not isinstance(backbones, list):
        return 0
    ids = {
        str(item.get("id") or "").strip()
        for item in backbones
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    return len(ids)


def _backbone_origin_stage(source: object | None) -> str:
    raw = str(source or "").strip().lower()
    if raw == "rfd3":
        return "rfd3"
    if raw in {"bioemu", "biomu"}:
        return "bioemu"
    if raw == "target":
        return "target"
    return raw or "unknown"


def _backbone_origin_artifact(
    source: object | None, backbone_id: object | None, selected_id: object | None = None
) -> str:
    source_key = _backbone_origin_stage(source)
    raw_id = str(backbone_id or "").strip()
    safe_id = _safe_id(raw_id) if raw_id else ""
    selected_key = str(selected_id or "").strip()
    if source_key == "rfd3":
        if raw_id and selected_key and raw_id == selected_key:
            return "rfd3/selected.pdb"
        return f"rfd3/designs/{safe_id}.pdb" if safe_id else "rfd3/selected.pdb"
    if source_key == "bioemu":
        return f"bioemu/designs/{safe_id}.pdb" if safe_id else "bioemu/output.json"
    if source_key == "target":
        return "target.pdb"
    return f"backbones/{safe_id}/target.pdb" if safe_id else "target.pdb"


def _backbone_propagation_mode(
    observed_count: int, materialized_count: int, propagated_count: int
) -> str:
    observed = max(0, int(observed_count or 0))
    materialized = max(0, int(materialized_count or 0))
    propagated = max(0, int(propagated_count or 0))
    if propagated <= 0:
        return "none"
    available = observed if observed > materialized else materialized
    if available <= 0:
        return "propagated_only"
    if propagated >= available:
        return "all_observed" if observed > materialized else "all_materialized"
    if propagated == 1 and available > 1:
        return "selected_only"
    return "partial"


def _requested_backbone_count(request: PipelineRequest, source: str) -> int:
    normalized = _backbone_origin_stage(source)
    if normalized == "rfd3" and _rfd3_active(request):
        return max(1, int(request.rfd3_max_return_designs or 1))
    if normalized == "bioemu" and _bioemu_active(request):
        num_samples = max(1, int(request.bioemu_num_samples or 1))
        max_return = max(1, int(request.bioemu_max_return_structures or 1))
        return min(num_samples, max_return)
    return 0


def _rfd3_missing_design_pdb_message(
    *, requested_count: int, observed_count: int, materialized_count: int
) -> str | None:
    requested = max(0, int(requested_count or 0))
    if requested <= 1:
        return None
    materialized = max(0, int(materialized_count or 0))
    if materialized >= requested:
        return None
    observed = max(materialized, max(0, int(observed_count or 0)))
    return (
        f"RFD3 returned only {materialized} design PDBs for requested {requested}. "
        f"Observed designs={observed}. The endpoint must include designs[*].pdb when "
        "return_designs_pdb=true and rfd3_max_return_designs>1."
    )


def _bioemu_missing_sample_pdb_message(
    *, requested_count: int, observed_count: int, materialized_count: int
) -> str | None:
    requested = max(0, int(requested_count or 0))
    if requested <= 1:
        return None
    materialized = max(0, int(materialized_count or 0))
    if materialized >= requested:
        return None
    observed = max(materialized, max(0, int(observed_count or 0)))
    return (
        f"BioEmu returned only {materialized} structure(s) for requested {requested}. "
        f"Observed structures={observed}. sample_pdbs are required when bioemu_max_return_structures>1; "
        "topology_pdb-only responses are not sufficient. If bioemu_filter_samples=true, "
        "BioEmu may legitimately emit fewer samples than requested."
    )


def _backbone_source_note(
    source: str,
    *,
    requested_count: int,
    observed_count: int,
    materialized_count: int,
    propagated_count: int,
    backbone_ids: list[str] | None = None,
) -> str | None:
    normalized = _backbone_origin_stage(source)
    ids = [
        str(item or "").strip().lower()
        for item in (backbone_ids or [])
        if str(item or "").strip()
    ]
    if (
        normalized == "rfd3"
        and observed_count > materialized_count
        and materialized_count == 1
        and propagated_count <= 1
    ):
        return "Additional RFD3 designs were metadata-only; downstream used the selected backbone PDB."
    if (
        normalized == "bioemu"
        and requested_count > materialized_count
        and materialized_count == 1
        and "bioemu_topology" in ids
    ):
        return "BioEmu returned topology_pdb only; sample_pdbs were not materialized."
    return None


def _build_backbone_source_summaries(
    request: PipelineRequest,
    *,
    backbone_entries: list[dict[str, Any]],
    observed_counts: dict[str, int] | None = None,
    selected_ids: dict[str, str | None] | None = None,
    diversity_summaries: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, object]], str]:
    observed_counts = observed_counts or {}
    selected_ids = selected_ids or {}
    diversity_summaries = diversity_summaries or {}
    counts_by_source: dict[str, dict[str, int]] = {}
    ids_by_source: dict[str, list[str]] = {}
    propagated_ids_by_source: dict[str, list[str]] = {}
    for entry in backbone_entries:
        if not isinstance(entry, dict):
            continue
        source = _backbone_origin_stage(entry.get("source"))
        bucket = counts_by_source.setdefault(
            source, {"materialized_count": 0, "propagated_count": 0}
        )
        raw_id = str(entry.get("id") or "").strip()
        if raw_id:
            backbone_ids = ids_by_source.setdefault(source, [])
            if raw_id not in backbone_ids:
                backbone_ids.append(raw_id)
        if bool(entry.get("materialized")):
            bucket["materialized_count"] = (
                int(bucket.get("materialized_count") or 0) + 1
            )
        if bool(entry.get("propagated")):
            bucket["propagated_count"] = int(bucket.get("propagated_count") or 0) + 1
            if raw_id:
                propagated_ids = propagated_ids_by_source.setdefault(source, [])
                if raw_id not in propagated_ids:
                    propagated_ids.append(raw_id)

    source_keys = [
        key
        for key in sorted(
            set(
                list(observed_counts.keys())
                + list(counts_by_source.keys())
                + list(selected_ids.keys())
            )
        )
        if _requested_backbone_count(request, key) > 0
        or max(0, int(observed_counts.get(key) or 0)) > 0
        or key in counts_by_source
        or bool(selected_ids.get(key))
    ]

    summaries: dict[str, dict[str, object]] = {}
    total_observed = 0
    total_materialized = 0
    total_propagated = 0
    for source in source_keys:
        source_counts = counts_by_source.get(source) or {}
        materialized_count = max(0, int(source_counts.get("materialized_count") or 0))
        propagated_count = max(0, int(source_counts.get("propagated_count") or 0))
        observed_count = max(
            materialized_count, max(0, int(observed_counts.get(source) or 0))
        )
        requested_count = max(
            observed_count, _requested_backbone_count(request, source)
        )
        selected_backbone_id = str(selected_ids.get(source) or "").strip() or None
        propagated_ids = propagated_ids_by_source.get(source) or []
        if not selected_backbone_id and len(propagated_ids) == 1:
            selected_backbone_id = str(propagated_ids[0] or "").strip() or None
        propagation_mode = _backbone_propagation_mode(
            observed_count, materialized_count, propagated_count
        )
        payload: dict[str, object] = {
            "requested_count": requested_count,
            "observed_count": observed_count,
            "materialized_count": materialized_count,
            "propagated_count": propagated_count,
            "propagation_mode": propagation_mode,
        }
        diversity = diversity_summaries.get(source)
        if isinstance(diversity, dict):
            unique_count = diversity.get("unique_count")
            duplicate_count = diversity.get("duplicate_count")
            if isinstance(unique_count, int):
                payload["unique_count"] = unique_count
            if isinstance(duplicate_count, int):
                payload["duplicate_count"] = duplicate_count
            if duplicate_count:
                payload["deduplicated"] = True
                payload["note"] = (
                    f"Exact CA-coordinate duplicate {source.upper()} backbones were collapsed from "
                    f"{int(diversity.get('input_count') or observed_count)} to {int(unique_count or 0)} unique structures."
                )
        note = _backbone_source_note(
            source,
            requested_count=requested_count,
            observed_count=observed_count,
            materialized_count=materialized_count,
            propagated_count=propagated_count,
            backbone_ids=ids_by_source.get(source) or [],
        )
        if note and "note" not in payload:
            payload["note"] = note
        if selected_backbone_id:
            payload["selected_backbone_id"] = selected_backbone_id
        summaries[source] = payload
        total_observed += observed_count
        total_materialized += materialized_count
        total_propagated += propagated_count
    return summaries, _backbone_propagation_mode(
        total_observed, total_materialized, total_propagated
    )


def _normalize_rfd3_mode(value: object | None) -> str | None:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return None
    aliases = {
        "legacy": "legacy_contig",
        "contig": "legacy_contig",
        "simple": "legacy_contig",
        "legacy_contig": "legacy_contig",
        "binder": "binder",
        "binder_mode": "binder",
        "enzyme": "enzyme",
        "enzyme_mode": "enzyme",
        "local_diversify": "local_diversify",
        "local_diversify_mode": "local_diversify",
        "diversify": "local_diversify",
        "advanced": "advanced",
        "advanced_inputs": "advanced",
    }
    return aliases.get(raw, raw)


def _effective_rfd3_mode(
    request: PipelineRequest,
    *,
    input_files: dict[str, str] | None = None,
) -> str | None:
    explicit = _normalize_rfd3_mode(request.rfd3_mode)
    if explicit:
        return explicit
    if (request.rfd3_inputs_text or "").strip() or request.rfd3_inputs:
        return "advanced"
    if (
        request.rfd3_hotspots is not None
        or (request.rfd3_infer_ori_strategy or "").strip()
        or request.rfd3_is_non_loopy is not None
    ):
        return "binder"
    has_input = bool((request.rfd3_input_pdb or "").strip()) or bool(
        (input_files or {}).get("input.pdb")
    )
    if has_input:
        if request.rfd3_length is not None:
            return "enzyme"
        return "local_diversify"
    if (
        request.rfd3_unindex is not None
        or request.rfd3_length is not None
        or request.rfd3_select_fixed_atoms is not None
    ):
        return "enzyme"
    if (request.rfd3_contig or "").strip():
        return "legacy_contig"
    return None


def _has_rfd3_config(request: PipelineRequest) -> bool:
    return bool(
        (request.rfd3_inputs_text or "").strip()
        or request.rfd3_inputs
        or (request.rfd3_input_pdb or "").strip()
        or request.rfd3_input_files
        or _normalize_rfd3_mode(request.rfd3_mode)
        or request.rfd3_contig
        or request.rfd3_hotspots
        or (request.rfd3_infer_ori_strategy or "").strip()
        or request.rfd3_is_non_loopy is not None
        or request.rfd3_unindex
        or request.rfd3_length
        or request.rfd3_select_fixed_atoms
        or request.rfd3_ligand
        or (request.rfd3_select_unfixed_sequence or "").strip()
        or (request.rfd3_cli_args or "").strip()
        or request.rfd3_env
        or int(request.rfd3_design_index or 0) != 0
        or request.rfd3_partial_t is not None
        or (request.rfd3_sampling_strategy or "").strip()
        or bool(request.rfd3_fail_on_duplicate_backbones)
        or bool(request.rfd3_use_ensemble)
    )


def _rfd3_active(request: PipelineRequest) -> bool:
    has_config = _has_rfd3_config(request)
    if request.rfd3_use is None:
        return has_config
    return bool(request.rfd3_use) and has_config


def _rfd3_input_files(request: PipelineRequest) -> dict[str, str]:
    files: dict[str, str] = {}
    if isinstance(request.rfd3_input_files, dict):
        for key, value in request.rfd3_input_files.items():
            if value is None:
                continue
            files[str(key)] = str(value)
    if request.rfd3_input_pdb and "input.pdb" not in files:
        files["input.pdb"] = str(request.rfd3_input_pdb)
    return files


def _normalize_rfd3_contig_str(value: str) -> str:
    raw = str(value or "")
    if ":" not in raw:
        return raw
    return re.sub(r"([A-Za-z])\s*:\s*([0-9])", r"\1\2", raw)


def _normalize_rfd3_contig_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_rfd3_contig_str(value)
    if isinstance(value, list):
        return [
            _normalize_rfd3_contig_str(item) if isinstance(item, str) else item
            for item in value
        ]
    return value


def _infer_rfd3_shifted_contig_defaults(
    value: Any,
) -> tuple[str, str, dict[str, str]] | None:
    normalized = _normalize_rfd3_contig_value(value)
    if not isinstance(normalized, str):
        return None
    match = re.fullmatch(r"\s*([A-Za-z_])\s*(-?\d+)\s*-\s*(-?\d+)\s*", normalized)
    if not match:
        return None
    chain_id = str(match.group(1))
    start = int(match.group(2))
    stop = int(match.group(3))
    if stop <= start:
        return None
    unindex = f"{chain_id}{start}"
    shifted_contig = f"{chain_id}{start + 1}-{stop}"
    return shifted_contig, unindex, {unindex: "ALL"}


def _clamp_rfd3_contig_to_input_pdb(value: Any, *, pdb_text: str) -> Any:
    from .bio.pdb import residues_by_chain

    normalized = _normalize_rfd3_contig_value(value)
    if not isinstance(normalized, str):
        return normalized
    match = re.fullmatch(r"\s*([A-Za-z_])\s*(-?\d+)\s*-\s*(-?\d+)\s*", normalized)
    if not match:
        return normalized
    chain_id = str(match.group(1))
    start = int(match.group(2))
    stop = int(match.group(3))
    res_list = residues_by_chain(pdb_text).get(chain_id) or []
    if not res_list:
        return normalized
    resseqs = [int(res.resseq) for res in res_list]
    if not resseqs:
        return normalized
    if any(curr != prev + 1 for prev, curr in zip(resseqs, resseqs[1:])):
        return normalized
    clamped_start = max(start, resseqs[0])
    clamped_stop = min(stop, resseqs[-1])
    if clamped_stop < clamped_start:
        return normalized
    return f"{chain_id}{clamped_start}-{clamped_stop}"


def _normalize_rfd3_inputs(inputs: dict[str, Any] | None) -> dict[str, Any] | None:
    if inputs is None:
        return None
    normalized: dict[str, Any] = {}
    for key, spec in inputs.items():
        if isinstance(spec, dict):
            spec_out = dict(spec)
            if "contig" in spec_out:
                spec_out["contig"] = _normalize_rfd3_contig_value(
                    spec_out.get("contig")
                )
            if "select_unfixed_sequence" in spec_out:
                spec_out["select_unfixed_sequence"] = _normalize_rfd3_contig_value(
                    spec_out.get("select_unfixed_sequence")
                )
            if "partial_T" in spec_out and "partial_t" not in spec_out:
                spec_out["partial_t"] = spec_out["partial_T"]
            spec_out.pop("partial_T", None)
            normalized[key] = spec_out
        else:
            normalized[key] = spec
    return normalized


def _rfd3_input_file_text(input_name: str, *, input_files: dict[str, str]) -> str:
    normalized_name = str(input_name or "").strip().replace("\\", "/")
    if not normalized_name:
        return ""
    normalized_files = {
        str(name or "").strip().replace("\\", "/"): str(content)
        for name, content in (input_files or {}).items()
    }
    direct = str(normalized_files.get(normalized_name) or "")
    if direct:
        return direct
    basename = Path(normalized_name).name
    if not basename:
        return ""
    matches = [
        content
        for name, content in normalized_files.items()
        if Path(name).name == basename
    ]
    if len(matches) == 1:
        return str(matches[0])
    return ""


def _rfd3_spec_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _rfd3_chain_ids_from_value(value: Any) -> list[str]:
    out: list[str] = []

    def _add(chain_id: str) -> None:
        token = str(chain_id or "").strip()
        if not token or token in out:
            return
        out.append(token)

    if value is None:
        return out
    if isinstance(value, dict):
        for key in value.keys():
            for chain_id in _rfd3_chain_ids_from_value(key):
                _add(chain_id)
        return out
    if isinstance(value, (list, tuple, set)):
        for item in value:
            for chain_id in _rfd3_chain_ids_from_value(item):
                _add(chain_id)
        return out
    text = str(value or "").strip()
    if not text:
        return out
    for match in re.finditer(r"([A-Za-z])\s*:?\s*-?\d", text):
        _add(str(match.group(1)))
    return out


def _rfd3_design_chains_from_inputs(inputs: dict[str, Any] | None) -> list[str] | None:
    if not isinstance(inputs, dict):
        return None
    out: list[str] = []

    def _append(chains: list[str]) -> None:
        for chain_id in chains:
            token = str(chain_id or "").strip()
            if not token or token in out:
                continue
            out.append(token)

    for spec in inputs.values():
        if not isinstance(spec, dict):
            continue
        for key in ("contig", "select_unfixed_sequence", "hotspots", "unindex"):
            _append(_rfd3_chain_ids_from_value(spec.get(key)))
    if out:
        return out
    for spec in inputs.values():
        if not isinstance(spec, dict):
            continue
        _append(_rfd3_chain_ids_from_value(spec.get("select_fixed_atoms")))
    return out or None


def _rfd3_requested_design_chains(
    request: PipelineRequest,
    *,
    input_files: dict[str, str],
) -> list[str] | None:
    explicit = [
        str(chain_id).strip()
        for chain_id in (request.design_chains or [])
        if str(chain_id).strip()
    ]
    if explicit:
        return explicit
    try:
        inputs_text = str(request.rfd3_inputs_text or "").strip() or None
        inputs_obj = (
            copy.deepcopy(request.rfd3_inputs)
            if isinstance(request.rfd3_inputs, dict)
            else None
        )
        if inputs_text is not None and inputs_obj is None:
            parsed = _parse_json_dict(inputs_text)
            if parsed is not None:
                inputs_obj = parsed
                inputs_text = None
        if inputs_text is None and inputs_obj is None:
            inputs_obj = _rfd3_simple_inputs(request, input_files=input_files)
        inputs_obj = copy.deepcopy(_normalize_rfd3_inputs(inputs_obj))
    except Exception:
        return None
    return _rfd3_design_chains_from_inputs(inputs_obj)


def _rfd3_simple_inputs(
    request: PipelineRequest, *, input_files: dict[str, str]
) -> dict[str, object]:
    from .bio.pdb import residues_by_chain

    mode = _effective_rfd3_mode(request, input_files=input_files)
    if mode == "advanced":
        raise ValueError("RFD3 advanced mode requires rfd3_inputs or rfd3_inputs_text")
    spec: dict[str, object] = {}
    if request.rfd3_input_pdb or "input.pdb" in input_files:
        spec["input"] = "input.pdb"
    if mode in {"legacy_contig", "binder"}:
        if request.rfd3_contig is None:
            raise ValueError(f"RFD3 {mode} mode requires rfd3_contig")
        spec["contig"] = _normalize_rfd3_contig_value(request.rfd3_contig)
        if mode == "binder":
            if request.rfd3_hotspots is not None:
                spec["hotspots"] = request.rfd3_hotspots
            if (request.rfd3_infer_ori_strategy or "").strip():
                spec["infer_ori_strategy"] = str(
                    request.rfd3_infer_ori_strategy
                ).strip()
            if request.rfd3_is_non_loopy is not None:
                spec["is_non_loopy"] = bool(request.rfd3_is_non_loopy)
    elif mode in {"enzyme", "local_diversify"}:
        explicit_mode = _normalize_rfd3_mode(request.rfd3_mode)
        auto_fill_local_defaults = not bool(explicit_mode)
        contig_val = request.rfd3_contig
        unindex_val = request.rfd3_unindex
        fixed_val = request.rfd3_select_fixed_atoms

        pdb_text = str(
            _rfd3_input_file_text("input.pdb", input_files=input_files)
            or request.rfd3_input_pdb
            or ""
        )
        if pdb_text.strip():
            # Renumber residues from 1 temporarily for inference if needed, because RFD3 fails on negative contigs
            if _has_nonpositive_resseq(pdb_text):
                pdb_text = _prepare_pdb_text_for_design_context(
                    pdb_text,
                    chains=None,
                    strip_nonpositive_resseq=False,
                    renumber_resseq_from_1=True,
                )

            if contig_val is not None:
                contig_val = _clamp_rfd3_contig_to_input_pdb(
                    contig_val, pdb_text=pdb_text
                )

            by_chain = residues_by_chain(pdb_text)
            if by_chain:
                first_chain = sorted(by_chain.keys())[0]
                res_list = by_chain[first_chain]
                if len(res_list) > 1:
                    default_unindex = f"{first_chain}{res_list[0].resseq}"
                    default_contig = (
                        f"{first_chain}{res_list[1].resseq}-{res_list[-1].resseq}"
                    )
                    if auto_fill_local_defaults:
                        if unindex_val is None:
                            unindex_val = default_unindex
                        if (
                            fixed_val is None
                            and str(unindex_val or "").strip() == default_unindex
                        ):
                            fixed_val = {default_unindex: "ALL"}
                        if (
                            contig_val is None
                            and str(unindex_val or "").strip() == default_unindex
                        ):
                            contig_val = default_contig
                    elif (
                        contig_val is None
                        and str(unindex_val or "").strip() == default_unindex
                    ):
                        contig_val = default_contig

        if (
            auto_fill_local_defaults
            and unindex_val is None
            and fixed_val is None
            and contig_val is not None
        ):
            shifted_defaults = _infer_rfd3_shifted_contig_defaults(contig_val)
            if shifted_defaults is not None:
                contig_val, unindex_val, fixed_val = shifted_defaults

        if contig_val is not None and unindex_val is not None:
            shifted_defaults = _infer_rfd3_shifted_contig_defaults(contig_val)
            if shifted_defaults is not None:
                shifted_contig, shifted_unindex, shifted_fixed = shifted_defaults
                if str(unindex_val or "").strip() == shifted_unindex:
                    contig_val = shifted_contig
                    if auto_fill_local_defaults and fixed_val is None:
                        fixed_val = shifted_fixed

        if mode == "enzyme" and unindex_val is None:
            raise ValueError("RFD3 enzyme mode requires rfd3_unindex")

        if contig_val is not None:
            spec["contig"] = _normalize_rfd3_contig_value(contig_val)
        if unindex_val is not None:
            spec["unindex"] = unindex_val
        if fixed_val is not None:
            spec["select_fixed_atoms"] = fixed_val

        if mode == "enzyme" and request.rfd3_length is not None:
            spec["length"] = request.rfd3_length
    if request.rfd3_ligand is not None:
        spec["ligand"] = request.rfd3_ligand
    if request.rfd3_select_unfixed_sequence is not None:
        spec["select_unfixed_sequence"] = _normalize_rfd3_contig_value(
            request.rfd3_select_unfixed_sequence
        )
    if (
        mode in {"legacy_contig", "binder", "enzyme", "local_diversify"}
        and "input" not in spec
    ):
        raise ValueError(
            f"RFD3 {mode} mode requires rfd3_input_pdb or input_files['input.pdb']"
        )
    if not spec:
        raise ValueError(
            "RFD3 simple inputs require an input backbone or explicit design fields"
        )
    spec_name = str(request.rfd3_spec_name or "spec-1").strip() or "spec-1"
    return {spec_name: spec}


def _parse_json_dict(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def _inject_rfd3_partial_t(
    inputs: dict[str, Any] | None, partial_t: float | int | None
) -> dict[str, Any] | None:
    if inputs is None:
        return None
    if partial_t is None or float(partial_t) <= 0:
        return inputs
    for spec in inputs.values():
        if not isinstance(spec, dict):
            continue
        if "partial_T" in spec and "partial_t" not in spec:
            spec["partial_t"] = spec.pop("partial_T")
        if "partial_t" in spec:
            continue
        spec["partial_t"] = float(partial_t)
    return inputs


def _effective_rfd3_partial_t(
    request: PipelineRequest, *, mode: str | None
) -> float | None:
    if request.rfd3_partial_t is not None:
        return float(request.rfd3_partial_t)
    if mode == "local_diversify":
        return 5.0
    return None


def _backbone_ca_signature(pdb_text: str) -> str:
    coords: list[str] = []
    for chain_id, residues in sorted(
        residues_by_chain(pdb_text, only_atom_records=True).items()
    ):
        for residue in residues:
            for atom in residue.atoms:
                if atom.atom_name.strip().upper() != "CA":
                    continue
                coords.append(
                    f"{chain_id}:{residue.index}:{atom.x:.3f}:{atom.y:.3f}:{atom.z:.3f}"
                )
                break
    return _sha256_text("\n".join(coords))


def _deduplicate_backbones_by_exact_ca(
    backbones: list[dict[str, Any]] | None,
    *,
    source: str,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    if not isinstance(backbones, list):
        return backbones, None
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for entry in backbones:
        if not isinstance(entry, dict):
            continue
        pdb_text = str(entry.get("pdb_text") or "")
        if not pdb_text.strip():
            continue
        signature = _backbone_ca_signature(pdb_text)
        if signature not in groups:
            groups[signature] = []
            order.append(signature)
        groups[signature].append(entry)
    if not groups:
        return backbones, None
    unique = [dict(groups[signature][0]) for signature in order]
    duplicate_groups = [
        {
            "signature": signature,
            "representative_id": str(groups[signature][0].get("id") or ""),
            "member_ids": [str(item.get("id") or "") for item in groups[signature]],
        }
        for signature in order
        if len(groups[signature]) > 1
    ]
    summary = {
        "source": source,
        "method": "exact_ca_coordinates",
        "input_count": len([item for item in backbones if isinstance(item, dict)]),
        "unique_count": len(unique),
        "duplicate_count": max(
            0, len([item for item in backbones if isinstance(item, dict)]) - len(unique)
        ),
        "duplicate_groups": duplicate_groups,
        "dropped_ids": [
            member_id
            for group in duplicate_groups
            for member_id in group.get("member_ids", [])[1:]
            if str(member_id or "").strip()
        ],
    }
    return unique, summary


def _filter_backbones_by_target_rmsd(
    backbones: list[dict[str, Any]] | None,
    *,
    reference_pdb_text: str,
    chains: list[str] | None,
    cutoff: float | None,
    source: str,
    strip_nonpositive_resseq: bool = False,
    renumber_resseq_from_1: bool = False,
    use_dssp_non_loop: bool = True,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    if not isinstance(backbones, list):
        return backbones, None
    items = [item for item in backbones if isinstance(item, dict)]
    if not items:
        return [], None

    chain_list = [
        str(chain_id).strip() for chain_id in (chains or []) if str(chain_id).strip()
    ] or None
    include_positions = None
    mask_applied = False
    mask_mode = "all_ca"
    mask_residue_count = 0
    if use_dssp_non_loop and reference_pdb_text.strip():
        dssp_positions = dssp_non_loop_positions_by_chain(
            reference_pdb_text,
            chains=chain_list,
        )
        mask_residue_count = sum(len(v) for v in dssp_positions.values())
        if mask_residue_count >= 2:
            include_positions = dssp_positions
            mask_applied = True
            mask_mode = "dssp_non_loop_reference"
    if cutoff is None or not reference_pdb_text.strip():
        return items, {
            "source": source,
            "method": "target_ca_rmsd",
            "applied": False,
            "mask_applied": mask_applied,
            "mask_mode": mask_mode,
            "mask_residue_count": mask_residue_count,
            "cutoff": float(cutoff) if isinstance(cutoff, (int, float)) else None,
            "design_chains": chain_list,
            "input_count": len(items),
            "accepted_count": len(items),
            "rejected_count": 0,
            "accepted_ids": [
                str(item.get("id") or "")
                for item in items
                if str(item.get("id") or "").strip()
            ],
            "rejected_ids": [],
            "missing_rmsd_ids": [],
            "rmsd_by_id": {},
        }

    accepted: list[dict[str, Any]] = []
    rejected_ids: list[str] = []
    missing_rmsd_ids: list[str] = []
    rmsd_by_id: dict[str, float] = {}

    for item in items:
        item_id = str(item.get("id") or "").strip()
        pdb_text = str(item.get("pdb_text") or "")
        bb_strip_nonpositive, bb_renumber, _ = _resolve_backbone_preprocess_options(
            pdb_text=pdb_text,
            source=source,
            strip_nonpositive_resseq=strip_nonpositive_resseq,
            renumber_resseq_from_1=renumber_resseq_from_1,
        )
        prepared_pdb_text = _preprocess_pdb_text(
            pdb_text,
            chains=chain_list,
            strip_nonpositive_resseq=bb_strip_nonpositive,
            renumber_resseq_from_1=bb_renumber,
        )
        rmsd = ca_rmsd(
            reference_pdb_text,
            prepared_pdb_text,
            chains=chain_list,
            include_positions=include_positions,
        )
        if not isinstance(rmsd, (int, float)):
            entry = dict(item)
            entry["target_rmsd"] = None
            if item_id:
                missing_rmsd_ids.append(item_id)
                rejected_ids.append(item_id)
            continue
        rmsd_value = float(rmsd)
        if item_id:
            rmsd_by_id[item_id] = rmsd_value
        entry = dict(item)
        entry["target_rmsd"] = rmsd_value
        if rmsd_value <= float(cutoff):
            accepted.append(entry)
        elif item_id:
            rejected_ids.append(item_id)

    rejected_count = max(0, len(items) - len(accepted))

    summary = {
        "source": source,
        "method": "target_ca_rmsd_dssp_non_loop" if mask_applied else "target_ca_rmsd",
        "applied": True,
        "mask_applied": mask_applied,
        "mask_mode": mask_mode,
        "mask_residue_count": mask_residue_count,
        "cutoff": float(cutoff),
        "design_chains": chain_list,
        "input_count": len(items),
        "accepted_count": len(accepted),
        "rejected_count": rejected_count,
        "accepted_ids": [
            str(item.get("id") or "")
            for item in accepted
            if str(item.get("id") or "").strip()
        ],
        "rejected_ids": rejected_ids,
        "missing_rmsd_ids": missing_rmsd_ids,
        "rmsd_by_id": rmsd_by_id,
    }
    return accepted, summary


def _rfd3_cli_has_arg(cli_args: str | None, key: str) -> bool:
    if not cli_args:
        return False
    pattern = rf"(?:^|\\s)--?{re.escape(key)}(?:=|\\s)"
    return re.search(pattern, str(cli_args)) is not None


def _inject_rfd3_cli_defaults(cli_args: str | None, *, max_designs: int) -> str | None:
    args = str(cli_args or "").strip()
    additions: list[str] = []
    if max_designs > 0 and not _rfd3_cli_has_arg(args, "diffusion_batch_size"):
        additions.append(f"diffusion_batch_size={max_designs}")
    if not _rfd3_cli_has_arg(args, "n_batches"):
        additions.append("n_batches=1")
    if not additions:
        return cli_args
    if args:
        return f"{args} {' '.join(additions)}".strip()
    return " ".join(additions)


def _diffdock_requested(request: PipelineRequest) -> bool:
    return bool(
        (str(request.diffdock_ligand_smiles or "").strip())
        or (str(request.diffdock_ligand_sdf or "").strip())
    )


def _bioemu_active(request: PipelineRequest) -> bool:
    return bool(request.bioemu_use)


def _is_monomer_preset(preset: str) -> bool:
    return str(preset or "").strip().lower().startswith("monomer")


def _is_multimer_preset(preset: str) -> bool:
    return str(preset or "").strip().lower().startswith("multimer")


def _resolve_af2_model_preset(requested: str, *, chain_count: int) -> str:
    preset = str(requested or "").strip()
    if not preset or preset.lower() == "auto":
        return "multimer" if int(chain_count) > 1 else "monomer"
    if _is_monomer_preset(preset):
        return preset
    if _is_multimer_preset(preset):
        return preset
    return preset


def _resolve_pipeline_chain_strategy(
    *,
    pdb_text: str,
    request_design_chains: list[str] | None,
    target_fasta_text: str,
    target_record: FastaRecord | None,
    af2_model_preset_requested: str,
) -> tuple[
    list[str], list[str] | None, list[str] | None, list[str] | None, str | None, str
]:
    pdb_chains = list(residues_by_chain(pdb_text, only_atom_records=True).keys())
    requested_chains = (
        list(request_design_chains) if request_design_chains else (pdb_chains or None)
    )
    auto_design_chains: list[str] | None = None
    auto_chain_note: str | None = None
    if request_design_chains is None and not str(target_fasta_text or "").strip():
        query_seq = (
            _clean_protein_sequence(target_record.sequence) if target_record else ""
        )
        if query_seq and pdb_chains:
            seq_by_chain = sequence_by_chain(pdb_text, chains=pdb_chains)
            best_chain = None
            best_score: tuple[float, int, int] | None = None
            for chain_id, chain_seq in seq_by_chain.items():
                clean_seq = _clean_protein_sequence(chain_seq)
                if not clean_seq:
                    continue
                aln = global_alignment_mapping(query_seq, clean_seq)
                score = (
                    float(aln.query_identity),
                    int(aln.matches),
                    int(aln.target_len),
                )
                if best_score is None or score > best_score:
                    best_score = score
                    best_chain = chain_id
            if best_chain:
                requested_chains = [best_chain]
                auto_design_chains = [best_chain]
                auto_chain_note = (
                    f"auto_design_chains={best_chain} (target_fasta empty)"
                )

    af2_model_preset = _resolve_af2_model_preset(
        af2_model_preset_requested,
        chain_count=len(pdb_chains or []),
    )
    chain_notes: list[str] = []
    if requested_chains and _is_monomer_preset(af2_model_preset):
        if len(requested_chains) > 1:
            chain_notes.append(
                f"monomer preset: using first chain only ({requested_chains[0]})"
            )
        design_chains = [requested_chains[0]]
    else:
        design_chains = requested_chains
    if auto_chain_note:
        chain_notes.insert(0, auto_chain_note)
    chain_note = " | ".join(chain_notes) if chain_notes else None
    return (
        pdb_chains,
        requested_chains,
        auto_design_chains,
        design_chains,
        chain_note,
        af2_model_preset,
    )


def _normalize_af2_provider(value: object | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"af2", "alphafold", "alphafold2"}:
        return _AF2_PROVIDER_AF2
    if raw in {"colabfold", "cf"}:
        return _AF2_PROVIDER_COLABFOLD
    return _AF2_PROVIDER_COLABFOLD


def _af2_provider_display_name(provider: str) -> str:
    return "ColabFold" if provider == _AF2_PROVIDER_COLABFOLD else "AlphaFold2"


def _af2_provider_config_hint(provider: str) -> str:
    if provider == _AF2_PROVIDER_COLABFOLD:
        return "set COLABFOLD_ENDPOINT_ID"
    return "set ALPHAFOLD2_ENDPOINT_ID (RunPod) or AF2_URL"


def _split_multichain_sequence(seq: str) -> list[str]:
    seq = str(seq or "").strip()
    if not seq:
        return []
    parts = [p.strip() for p in seq.split("/") if p.strip()]
    return parts if len(parts) > 1 else [seq]


def _clean_protein_sequence(seq: str) -> str:
    return "".join(ch for ch in str(seq or "").upper() if ch.isalpha())


def _sequence_length(seq: str) -> int:
    return len(_clean_protein_sequence(seq))


def _extract_predicted_pdb_text(
    seq_id: str,
    *,
    af2_result: dict[str, object] | None,
    af2_dir: Path,
) -> str | None:
    rec = af2_result.get(seq_id) if isinstance(af2_result, dict) else None
    if isinstance(rec, dict):
        for key in ("ranked_0_pdb", "pdb", "pdb_text"):
            value = rec.get(key)
            if isinstance(value, str) and value.strip():
                return value
    pdb_path = af2_dir / _safe_id(seq_id) / "ranked_0.pdb"
    if pdb_path.exists():
        return pdb_path.read_text(encoding="utf-8")
    return None


def _af2_candidate_parent_backbone(
    seq_id: str,
    *,
    candidate_records_by_id: dict[str, SequenceRecord],
    backbone_pdb_by_id: dict[str, str],
    fallback_pdb_text: str,
) -> tuple[str | None, str]:
    candidate = candidate_records_by_id.get(seq_id)
    meta = (
        candidate.meta
        if isinstance(candidate, SequenceRecord) and isinstance(candidate.meta, dict)
        else {}
    )
    backbone_id = str(meta.get("backbone_id") or "").strip() or None
    if backbone_id:
        pdb_text = str(backbone_pdb_by_id.get(backbone_id) or "")
        if pdb_text.strip():
            return backbone_id, pdb_text
    return backbone_id, str(fallback_pdb_text or "")


def _cached_rmsd_metric(
    metrics_payload: dict[str, object] | None,
    *,
    key: str,
    expected_reference_hash: str,
    reference_hash_key: str,
    expected_reference_mode: str | None = None,
    reference_mode_key: str = "rmsd_reference_mode",
    expected_backbone_id: str | None = None,
    backbone_id_key: str = "rmsd_reference_backbone_id",
) -> float | None:
    if not isinstance(metrics_payload, dict) or not expected_reference_hash:
        return None
    raw = metrics_payload.get(key)
    if not isinstance(raw, (int, float)):
        return None
    cached_hash = str(metrics_payload.get(reference_hash_key) or "").strip()
    if cached_hash != expected_reference_hash:
        return None
    if expected_reference_mode is not None:
        cached_mode = str(metrics_payload.get(reference_mode_key) or "").strip()
        if cached_mode != expected_reference_mode:
            return None
    if expected_backbone_id is not None:
        cached_backbone_id = (
            str(metrics_payload.get(backbone_id_key) or "").strip() or None
        )
        if cached_backbone_id != expected_backbone_id:
            return None
    return float(raw)


def _score_per_residue(total_score: float | None, sequence: str) -> float | None:
    if total_score is None:
        return None
    length = _sequence_length(sequence)
    if length <= 0:
        return None
    return float(total_score) / float(length)


def _sequence_difference_stats(
    reference_seq: str, query_seq: str
) -> dict[str, float | int] | None:
    reference = _clean_protein_sequence(reference_seq)
    query = _clean_protein_sequence(query_seq)
    if not reference or not query:
        return None
    compare_len = max(len(reference), len(query))
    if compare_len <= 0:
        return None
    span = min(len(reference), len(query))
    matches = 0
    for i in range(span):
        if reference[i] == query[i]:
            matches += 1
    diff_count = max(0, compare_len - matches)
    identity = float(matches) / float(compare_len)
    diff_ratio = float(diff_count) / float(compare_len)
    return {
        "wt_length": len(reference),
        "design_length": len(query),
        "compare_len": compare_len,
        "match_count": matches,
        "diff_count": diff_count,
        "identity": identity,
        "identity_pct": identity * 100.0,
        "diff_ratio": diff_ratio,
        "diff_pct": diff_ratio * 100.0,
    }


def _map_reference_ligand_mask_to_query(
    *,
    query_seq: str,
    reference_pdb_text: str,
    design_chains: list[str] | None,
    ligand_mask_distance: float,
    ligand_resnames: list[str] | None,
    ligand_atom_chains: list[str] | None,
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    query_clean = _clean_protein_sequence(query_seq)
    reference_text = str(reference_pdb_text or "")
    if not query_clean or not reference_text.strip():
        return {}, {}

    reference_mask = ligand_proximity_mask(
        reference_text,
        chains=design_chains,
        distance_angstrom=ligand_mask_distance,
        ligand_resnames=ligand_resnames,
        ligand_atom_chains=ligand_atom_chains,
    )
    if not reference_mask:
        return {}, {}

    seq_by_chain = sequence_by_chain(reference_text, chains=design_chains)
    query_positions_by_chain: dict[str, list[int]] = {}
    for chain_id, raw_positions in reference_mask.items():
        chain_seq = _clean_protein_sequence(seq_by_chain.get(chain_id, ""))
        if not chain_seq:
            continue
        aln = global_alignment_mapping(query_clean, chain_seq)
        ligand_positions = {
            int(pos) for pos in (raw_positions or []) if isinstance(pos, (int, float))
        }
        if not ligand_positions:
            continue
        mapped_query_positions: list[int] = []
        for query_pos, ref_pos in enumerate(aln.mapping_query_to_target, start=1):
            if ref_pos is None:
                continue
            if int(ref_pos) in ligand_positions:
                mapped_query_positions.append(int(query_pos))
        if mapped_query_positions:
            query_positions_by_chain[chain_id] = sorted(set(mapped_query_positions))

    return reference_mask, query_positions_by_chain


def _validate_af2_chain_sequences(
    seq: str,
    *,
    model_preset: str,
    chain_ids: list[str] | None,
) -> list[str]:
    raw = re.sub(r"\s+", "", str(seq or ""))
    if not raw:
        raise ValueError("AF2 input validation failed: empty sequence")

    parts = raw.split("/") if "/" in raw else [raw]
    if any(p == "" for p in parts):
        raise ValueError(
            "AF2 input validation failed: invalid chain delimiter '/': empty chain detected. "
            "Fix: use 'SEQ_A/SEQ_B' (no leading/trailing '//')."
        )

    invalid_chars: set[str] = set()
    invalid_examples: list[str] = []
    chains: list[str] = []
    for chain_idx, part in enumerate(parts, start=1):
        out_chars: list[str] = []
        for pos, ch in enumerate(part, start=1):
            if not ch.isalpha():
                invalid_chars.add(ch)
                if len(invalid_examples) < 6:
                    invalid_examples.append(f"chain{chain_idx}:pos{pos}={ch!r}")
                continue
            up = ch.upper()
            if up not in _AF2_ALLOWED_AA:
                invalid_chars.add(up)
                if len(invalid_examples) < 6:
                    invalid_examples.append(f"chain{chain_idx}:pos{pos}={ch!r}")
                continue
            out_chars.append(up)
        chains.append("".join(out_chars))

    if invalid_chars:
        allowed = "".join(sorted(_AF2_ALLOWED_AA))
        ex = ", ".join(invalid_examples) if invalid_examples else "n/a"
        raise ValueError(
            "AF2 input validation failed: sequence contains non-standard characters. "
            f"invalid={_format_set(invalid_chars)} examples=[{ex}]. "
            f"Allowed amino acids: {allowed}. "
            "Fix: replace ambiguous/modified residues with 'X' (or a canonical AA), and remove non-letter symbols. "
            "If this is a multimer, keep chains separated as 'SEQ_A/SEQ_B' and use af2_model_preset='multimer'."
        )

    preset = str(model_preset or "").strip().lower() or "monomer"
    if (
        preset.startswith("monomer")
        and len(chains) > 1
        and not _env_true("PIPELINE_AF2_MONOMER_FIRST_CHAIN")
    ):
        used_ids = (chain_ids or [])[: min(2, len(chain_ids or []))]
        raise ValueError(
            "AF2 input validation failed: monomer preset cannot accept multi-chain sequence separated by '/'. "
            f"found_chains={len(chains)} chain_ids={used_ids or None}. "
            "Fix: (1) run as multimer: set af2_model_preset='multimer' and design_chains=['A','B',...], "
            "or (2) run as monomer on a single chain: set design_chains=['A'] so ProteinMPNN/ligand mask/fixed positions "
            "are computed for one chain consistently. "
            "If you really want to evaluate only the first chain in monomer mode, set PIPELINE_AF2_MONOMER_FIRST_CHAIN=1."
        )

    if (
        preset.startswith("multimer")
        and chain_ids is not None
        and len(chain_ids) > 1
        and len(chains) != len(chain_ids)
    ):
        raise ValueError(
            "AF2 input validation failed: multimer preset expects the number of chains to match design_chains. "
            f"design_chains={chain_ids} found_chains={len(chains)}. "
            "Fix: ensure ProteinMPNN outputs chains in 'A/B/...' order matching design_chains, "
            "or set af2_model_preset='monomer' and design_chains=['A']."
        )

    if preset.startswith("monomer") and len(chains) > 1:
        chains = [chains[0]]

    return chains


def _prepare_af2_sequence(
    seq: str, *, model_preset: str, chain_ids: list[str] | None
) -> str:
    preset = str(model_preset or "").strip() or "monomer"
    chains = _validate_af2_chain_sequences(
        seq, model_preset=preset, chain_ids=chain_ids
    )
    if not chains:
        raise ValueError("AF2 input validation failed: empty sequence after validation")

    if _is_monomer_preset(preset):
        return chains[0]

    if not _is_multimer_preset(preset):
        return chains[0]

    out = chains[0]
    for idx, chain_seq in enumerate(chains[1:], start=1):
        label = None
        if chain_ids and idx < len(chain_ids):
            label = str(chain_ids[idx]).strip() or None
        label = label or f"chain_{idx + 1}"
        out += f"\n>{label}\n{chain_seq}"
    return out


def _first_chain_sequence(seq: str) -> str:
    seq = str(seq or "").strip()
    if "/" in seq:
        return seq.split("/", 1)[0]
    return seq


def _monomerize_records(
    records: list[SequenceRecord], model_preset: str
) -> list[SequenceRecord]:
    if not records or not _is_monomer_preset(model_preset):
        return records
    out: list[SequenceRecord] = []
    for rec in records:
        out.append(
            SequenceRecord(
                id=rec.id,
                header=rec.header,
                sequence=_first_chain_sequence(rec.sequence),
                meta=rec.meta,
            )
        )
    return out


def _dummy_backbone_pdb(sequence: str, *, chain_id: str = "A") -> str:
    aa3 = {
        "A": "ALA",
        "C": "CYS",
        "D": "ASP",
        "E": "GLU",
        "F": "PHE",
        "G": "GLY",
        "H": "HIS",
        "I": "ILE",
        "K": "LYS",
        "L": "LEU",
        "M": "MET",
        "N": "ASN",
        "P": "PRO",
        "Q": "GLN",
        "R": "ARG",
        "S": "SER",
        "T": "THR",
        "V": "VAL",
        "W": "TRP",
        "Y": "TYR",
    }
    lines: list[str] = []
    serial = 1
    for i, aa in enumerate(sequence, start=1):
        resname = aa3.get((aa or "A").upper(), "ALA")
        base = (i - 1) * 3.8
        atoms = [
            ("N", base + 0.0, 0.0, 0.0, "N"),
            ("CA", base + 1.45, 0.0, 0.0, "C"),
            ("C", base + 2.90, 0.0, 0.0, "C"),
            ("O", base + 3.30, 0.50, 0.0, "O"),
        ]
        for atom_name, x, y, z, element in atoms:
            lines.append(
                f"ATOM  {serial:5d} {atom_name:>4s} {resname:>3s} {chain_id}{i:4d}    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           {element:>2s}"
            )
            serial += 1
    lines.append("END")
    return "\n".join(lines) + "\n"


def _target_record_from_pdb(
    pdb_text: str, *, design_chains: list[str] | None
) -> FastaRecord:
    extracted = sequence_by_chain(pdb_text, chains=design_chains)
    if not extracted:
        raise ValueError(
            "Unable to extract protein sequence from target_pdb ATOM records"
        )
    if design_chains:
        chain_id = design_chains[0]
        seq = extracted.get(chain_id)
        if not seq:
            chain_id, seq = next(iter(extracted.items()))
    else:
        chain_id, seq = next(iter(extracted.items()))
    return FastaRecord(header=f"pdb_chain_{chain_id}", sequence=seq)


def _resolve_backbone_design_chains(
    *,
    pdb_text: str,
    preferred_chains: list[str] | None,
    query_seq: str = "",
) -> tuple[list[str], str | None]:
    residues = residues_by_chain(pdb_text, only_atom_records=True)
    available = list(residues.keys())
    preferred = [str(c).strip() for c in (preferred_chains or []) if str(c).strip()]
    if not available:
        return preferred, None
    if not preferred:
        return available, None

    matched = [c for c in preferred if c in available]
    if matched:
        return matched, None

    query_clean = _clean_protein_sequence(query_seq)
    if len(preferred) == 1 and query_clean:
        seq_by_chain = sequence_by_chain(pdb_text, chains=available)
        best_chain = None
        best_score: tuple[float, int, int] | None = None
        for chain_id, chain_seq in seq_by_chain.items():
            clean_seq = _clean_protein_sequence(chain_seq)
            if not clean_seq:
                continue
            aln = global_alignment_mapping(query_clean, clean_seq)
            score = (float(aln.query_identity), int(aln.matches), int(aln.target_len))
            if best_score is None or score > best_score:
                best_score = score
                best_chain = chain_id
        if best_chain:
            return [best_chain], (
                f"requested_chains={preferred} missing; "
                f"auto_selected_chain={best_chain} by query alignment"
            )

    if len(preferred) == 1:
        fallback = available[0]
        return [
            fallback
        ], f"requested_chains={preferred} missing; fallback_chain={fallback}"

    limit = min(len(preferred), len(available))
    fallback = available[:limit] if limit > 0 else available
    return fallback, f"requested_chains={preferred} missing; fallback_chains={fallback}"


def _fallback_chain_positions(
    values_by_chain: dict[str, list[int]],
    chain_id: str,
    *,
    include_wildcard: bool = False,
) -> list[int]:
    def _coerce(values: object) -> list[int]:
        if not isinstance(values, list):
            return []
        out: list[int] = []
        for item in values:
            try:
                out.append(int(item))
            except Exception:
                continue
        return out

    direct = values_by_chain.get(chain_id)
    direct_vals = _coerce(direct)
    if direct_vals:
        return direct_vals
    if include_wildcard:
        wildcard_vals = _coerce(values_by_chain.get("*"))
        if wildcard_vals:
            return wildcard_vals
    explicit = [_coerce(vals) for key, vals in values_by_chain.items() if key != "*"]
    explicit = [vals for vals in explicit if vals]
    if len(explicit) == 1:
        return explicit[0]
    return []


def _normalize_policy(value: str) -> str:
    policy = str(value or "").strip().lower() or "error"
    if policy not in {"error", "warn", "ignore"}:
        raise ValueError("query_pdb_policy must be one of: error | warn | ignore")
    return policy


def _validate_proteinmpnn_fixed_positions(
    *,
    pdb_text: str,
    design_chains: list[str] | None,
    fixed_positions_by_chain: dict[str, list[int]],
    native: SequenceRecord | None,
    samples: list[SequenceRecord],
) -> dict[str, Any]:
    def _clean_sequence(seq: str) -> str:
        return "".join(ch for ch in seq if ch.isalpha()).upper()

    fixed_total = sum(len(v) for v in fixed_positions_by_chain.values())
    if fixed_total <= 0:
        return {
            "ok": True,
            "fixed_positions_total": 0,
            "samples_checked": len(samples),
            "errors": [],
        }

    residues = residues_by_chain(pdb_text, only_atom_records=True)
    chain_order = list(design_chains) if design_chains else list(residues.keys())
    missing_chains = [c for c in chain_order if c not in residues]
    chain_lengths: dict[str, int] = {
        c: len(residues[c]) for c in chain_order if c in residues
    }
    total_len = sum(chain_lengths.get(c, 0) for c in chain_order)

    errors: list[str] = []
    if missing_chains:
        errors.append(f"Chains missing in PDB ATOM records: {missing_chains}")
    if native is None or not native.sequence:
        errors.append("ProteinMPNN did not return a native sequence")
    else:
        native_raw = str(native.sequence or "")
        native_seq = _clean_sequence(native_raw)
        if total_len > 0 and len(native_seq) != total_len:
            errors.append(
                f"Native sequence length mismatch: native={len(native_seq)} vs pdb_sum={total_len}"
            )

    if native is None:
        native_raw = ""
        native_seq = ""
    else:
        native_raw = str(native.sequence or "")
        native_seq = _clean_sequence(native_raw)
    for s in samples:
        sample_seq = _clean_sequence(str(s.sequence or ""))
        if sample_seq and native_seq and len(sample_seq) != len(native_seq):
            errors.append(
                f"Sample length mismatch: id={s.id} sample={len(sample_seq)} native={len(native_seq)}"
            )

    max_mismatches_per_chain = 25
    sample_summaries: list[dict[str, Any]] = []
    ok = not errors
    for s in samples:
        sample_seq = _clean_sequence(str(s.sequence or ""))
        mismatch_count = 0
        mismatches_by_chain: dict[str, list[dict[str, Any]]] = {}
        out_of_range: dict[str, list[int]] = {}

        offset = 0
        for chain_id in chain_order:
            chain_len = chain_lengths.get(chain_id, 0)
            native_chain = native_seq[offset : offset + chain_len]
            sample_chain = sample_seq[offset : offset + chain_len]
            offset += chain_len

            fixed = fixed_positions_by_chain.get(chain_id) or []
            if not fixed or chain_len <= 0:
                continue

            chain_mismatches: list[dict[str, Any]] = []
            chain_out_of_range: list[int] = []
            for pos in fixed:
                idx = int(pos) - 1
                if idx < 0 or idx >= chain_len:
                    chain_out_of_range.append(int(pos))
                    continue
                expected = native_chain[idx]
                actual = sample_chain[idx] if idx < len(sample_chain) else ""
                if expected != actual:
                    mismatch_count += 1
                    if len(chain_mismatches) < max_mismatches_per_chain:
                        chain_mismatches.append(
                            {"pos": int(pos), "expected": expected, "actual": actual},
                        )
            if chain_mismatches:
                mismatches_by_chain[chain_id] = chain_mismatches
            if chain_out_of_range:
                out_of_range[chain_id] = sorted(set(chain_out_of_range))

        if mismatch_count > 0 or out_of_range:
            ok = False

        sample_summaries.append(
            {
                "id": s.id,
                "mismatch_count": mismatch_count,
                "mismatches_by_chain": mismatches_by_chain,
                "out_of_range_positions_by_chain": out_of_range,
            }
        )

    return {
        "ok": ok,
        "errors": errors,
        "fixed_positions_total": fixed_total,
        "chain_order": chain_order,
        "chain_lengths": chain_lengths,
        "native_original_length": len(native_raw),
        "native_clean_length": len(native_seq),
        "samples_checked": len(samples),
        "samples": sample_summaries,
    }


def _normalize_fixed_positions_by_chain(value: Any) -> dict[str, list[int]] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, list[int]] = {}
    for k, v in value.items():
        if not isinstance(v, list):
            return None
        positions: list[int] = []
        for item in v:
            try:
                pos = int(item)
            except Exception:
                return None
            positions.append(pos)
        out[str(k)] = sorted(set(positions))
    return out


def _has_nonpositive_resseq(pdb_text: str) -> bool:
    for raw in pdb_text.splitlines():
        if not raw:
            continue
        rec = raw[:6].strip().upper()
        if rec not in {"ATOM", "HETATM"}:
            continue
        try:
            resseq = int(raw[22:26].strip())
        except Exception:
            continue
        if resseq <= 0:
            return True
    return False


def _has_negative_resseq(pdb_text: str) -> bool:
    for raw in pdb_text.splitlines():
        if not raw:
            continue
        rec = raw[:6].strip().upper()
        if rec not in {"ATOM", "HETATM"}:
            continue
        try:
            resseq = int(raw[22:26].strip())
        except Exception:
            continue
        if resseq < 0:
            return True
    return False


def _has_zero_resseq(pdb_text: str) -> bool:
    for raw in pdb_text.splitlines():
        if not raw:
            continue
        rec = raw[:6].strip().upper()
        if rec not in {"ATOM", "HETATM"}:
            continue
        try:
            resseq = int(raw[22:26].strip())
        except Exception:
            continue
        if resseq == 0:
            return True
    return False


def _resolve_backbone_preprocess_options(
    *,
    pdb_text: str,
    source: object | None,
    strip_nonpositive_resseq: bool,
    renumber_resseq_from_1: bool,
) -> tuple[bool, bool, str | None]:
    use_strip_nonpositive = bool(strip_nonpositive_resseq)
    use_renumber = bool(renumber_resseq_from_1)
    source_key = str(source or "").strip().lower()
    detail = None

    # BioEmu topology PDBs can start at residue 0. Stripping non-positive residue
    # indices would drop the N-terminal residue and shift every downstream position.
    if (
        source_key.startswith("bioemu")
        and _has_zero_resseq(pdb_text)
        and not _has_negative_resseq(pdb_text)
    ):
        use_strip_nonpositive = False
        use_renumber = True
        detail = "bioemu_zero_resseq_renumbered_from_1"

    return use_strip_nonpositive, use_renumber, detail


def _preprocess_pdb_text(
    pdb_text: str,
    *,
    chains: list[str] | None,
    strip_nonpositive_resseq: bool,
    renumber_resseq_from_1: bool,
) -> str:
    if not pdb_text.strip():
        return pdb_text
    if not (strip_nonpositive_resseq or renumber_resseq_from_1):
        return pdb_text
    processed, _ = preprocess_pdb(
        pdb_text,
        chains=chains,
        strip_nonpositive_resseq=strip_nonpositive_resseq,
        renumber_resseq_from_1=renumber_resseq_from_1,
    )
    return processed


def _strip_pdb_to_chains(
    pdb_text: str,
    *,
    chains: list[str] | None,
) -> str:
    selected = [
        str(chain_id).strip() for chain_id in (chains or []) if str(chain_id).strip()
    ]
    if not pdb_text.strip() or not selected:
        return pdb_text

    chain_set = set(selected)
    out_lines: list[str] = []
    for raw in pdb_text.splitlines():
        rec = raw[:6].strip().upper()
        if rec in {"ATOM", "HETATM", "TER"}:
            chain_id = raw[21:22].strip() or "_"
            if chain_id not in chain_set:
                continue
        out_lines.append(raw)
    return "\n".join(out_lines) + ("\n" if pdb_text.endswith("\n") else "")


def _prepare_pdb_text_for_design_context(
    pdb_text: str,
    *,
    chains: list[str] | None,
    strip_nonpositive_resseq: bool,
    renumber_resseq_from_1: bool,
) -> str:
    prepared = _strip_pdb_to_chains(pdb_text, chains=chains)
    return _preprocess_pdb_text(
        prepared,
        chains=chains,
        strip_nonpositive_resseq=strip_nonpositive_resseq,
        renumber_resseq_from_1=renumber_resseq_from_1,
    )


def _proteinmpnn_input_pdb_text(
    pdb_text: str,
    *,
    design_chains: list[str] | None,
    af2_model_preset: str,
) -> str:
    if not _is_monomer_preset(af2_model_preset):
        return pdb_text

    selected = [
        str(chain_id).strip()
        for chain_id in (design_chains or [])
        if str(chain_id).strip()
    ]
    if not selected:
        return pdb_text

    return _strip_pdb_to_chains(pdb_text, chains=[selected[0]])


def _wt_compare_reference_pdb_text(
    target_pdb_input_text: str,
    *,
    fallback_pdb_text: str,
    design_chains: list[str] | None,
    strip_nonpositive_resseq: bool,
    renumber_resseq_from_1: bool,
) -> str:
    if target_pdb_input_text.strip():
        return _preprocess_pdb_text(
            target_pdb_input_text,
            chains=design_chains,
            strip_nonpositive_resseq=strip_nonpositive_resseq,
            renumber_resseq_from_1=renumber_resseq_from_1,
        )
    return fallback_pdb_text


def _sync_processed_source_pdb_artifacts(
    *,
    run_root: Path,
    backbone_id: str,
    backbone_safe_id: str,
    source: object | None,
    processed_pdb_text: str,
    rfd3_selected_id: str | None = None,
) -> None:
    source_key = str(source or "").strip().lower()
    if not processed_pdb_text.strip():
        return

    if source_key.startswith("bioemu"):
        bioemu_dir = run_root / "bioemu"
        designs_dir = _ensure_dir(bioemu_dir / "designs")
        _write_text(designs_dir / f"{backbone_safe_id}.pdb", processed_pdb_text)

        output_path = bioemu_dir / "output.json"
        if output_path.exists():
            try:
                output_payload = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception:
                output_payload = None
            changed = False
            if isinstance(output_payload, dict):
                sample_pdbs = output_payload.get("sample_pdbs")
                if isinstance(sample_pdbs, list):
                    for sample in sample_pdbs:
                        if not isinstance(sample, dict):
                            continue
                        sample_id = str(sample.get("id") or "").strip()
                        if sample_id != backbone_id:
                            continue
                        if (
                            "pdb" in sample
                            and str(sample.get("pdb") or "") != processed_pdb_text
                        ):
                            sample["pdb"] = processed_pdb_text
                            changed = True
                        elif (
                            "pdb_text" in sample
                            and str(sample.get("pdb_text") or "") != processed_pdb_text
                        ):
                            sample["pdb_text"] = processed_pdb_text
                            changed = True
                if (
                    backbone_id == "bioemu_topology"
                    and str(output_payload.get("topology_pdb") or "")
                    != processed_pdb_text
                ):
                    output_payload["topology_pdb"] = processed_pdb_text
                    changed = True
            if changed:
                write_json(output_path, _safe_json(output_payload))
        return

    if source_key.startswith("rfd3"):
        rfd3_dir = run_root / "rfd3"
        designs_dir = _ensure_dir(rfd3_dir / "designs")
        _write_text(designs_dir / f"{backbone_safe_id}.pdb", processed_pdb_text)
        if backbone_id == str(rfd3_selected_id or "").strip():
            _write_text(rfd3_dir / "selected.pdb", processed_pdb_text)


@dataclass(frozen=True)
class PipelineRunner:
    output_root: str
    mmseqs: MMseqsClient | None = None
    proteinmpnn: ProteinMPNNClient | None = None
    soluprot: SoluProtClient | None = None
    colabfold: Any | None = None
    af2: Any | None = None
    rfd3: Any | None = None
    bioemu: Any | None = None
    diffdock: Any | None = None
    rosetta_relax: Any | None = None

    def run(
        self, request: PipelineRequest, *, run_id: str | None = None
    ) -> PipelineResult:
        run_id = run_id or new_run_id("pipeline")
        if getattr(request, "evolution_mode", False):
            return run_evolution(self, request, run_id)
        # A fresh run attempt for the same run_id should clear stale cancellation intent.
        clear_cancel_requested(self.output_root, run_id)
        paths = init_run(self.output_root, run_id)
        set_status(paths, stage="init", state="running")

        current_request_payload = _normalize_request_payload(request)
        errors: list[str] = []
        af2_provider = _normalize_af2_provider(getattr(request, "af2_provider", None))
        af2_client = (
            self.colabfold if af2_provider == _AF2_PROVIDER_COLABFOLD else self.af2
        )
        if (
            af2_client is None
            and af2_provider == _AF2_PROVIDER_COLABFOLD
            and self.af2 is not None
        ):
            # Backward-compatible fallback for older deployments that only configured AF2.
            af2_provider = _AF2_PROVIDER_AF2
            af2_client = self.af2
        af2_provider_label = _af2_provider_display_name(af2_provider)
        af2_provider_hint = _af2_provider_config_hint(af2_provider)
        af2_endpoint_id = (
            str(getattr(af2_client, "endpoint_id", "") or "").strip()
            if af2_client is not None
            else ""
        )
        relax_enabled = bool(getattr(request, "relax_enabled", False))
        rosetta_relax_client = self.rosetta_relax if relax_enabled else None

        msa_a3m_path = None
        msa_filtered_a3m_path = None
        msa_tsv_path = None
        conservation_path = None
        ligand_mask_path = None
        surface_mask_path = None
        tier_results: list[TierResult] = []

        def _is_cancel_error(exc: Exception) -> bool:
            msg = str(exc).strip().lower()
            return bool(msg) and any(
                token in msg for token in ("cancelled", "canceled", "cancel requested")
            )

        def _ensure_not_cancelled(stage: str) -> None:
            if is_cancel_requested(self.output_root, run_id):
                raise PipelineCancelled(
                    stage=stage, message=f"run cancellation requested (stage={stage})"
                )

        def _emit_panel(
            stage: str,
            *,
            detail: str | None = None,
            error: str | None = None,
            recovery: dict[str, object] | None = None,
        ) -> None:
            if not request.agent_panel_enabled:
                return
            emit_agent_panel_event(
                output_root=self.output_root,
                run_id=run_id,
                stage=stage,
                detail=detail,
                error=error,
                recovery=recovery,
            )

        def _recover_stage(
            stage: str,
            fn: Callable[[], Any],
            *,
            fallback: Callable[[Exception], Any] | None = None,
            recovery_actions: list[str] | None = None,
        ) -> tuple[Any, bool, str | None, dict[str, object] | None]:
            _ensure_not_cancelled(stage)
            try:
                return fn(), False, None, None
            except PipelineInputRequired:
                raise
            except PipelineCancelled:
                raise
            except BackboneContractError:
                raise
            except Exception as exc:
                if is_cancel_requested(self.output_root, run_id) or _is_cancel_error(
                    exc
                ):
                    raise PipelineCancelled(
                        stage=stage, message=f"run cancelled while {stage}: {exc}"
                    ) from exc
                msg = f"{stage} failed: {exc}"
                errors.append(msg)
                if not request.auto_recover or fallback is None:
                    _emit_panel(stage, error=msg, recovery={"attempted": False})
                    raise
                recovery_payload: dict[str, object] = {
                    "attempted": True,
                    "error": msg,
                    "actions": recovery_actions or [],
                }
                try:
                    result = fallback(exc)
                except Exception as fb_exc:
                    fb_msg = f"{stage} recovery failed: {fb_exc}"
                    errors.append(fb_msg)
                    recovery_payload["failed"] = True
                    recovery_payload["fallback_error"] = fb_msg
                    _emit_panel(stage, error=msg, recovery=recovery_payload)
                    raise
                return result, True, msg, recovery_payload

        try:
            _ensure_not_cancelled(stage="init")
            normalized_stop_after = str(request.stop_after or "").strip().lower()
            raw_start_from = (
                str(getattr(request, "start_from", "") or "").strip().lower()
            )
            normalized_start_from = _normalize_pipeline_stage(raw_start_from)
            if raw_start_from and normalized_start_from is None:
                raise PipelineInputRequired(
                    stage="init",
                    message=(
                        "start_from must be one of: "
                        + ", ".join(_PIPELINE_STAGE_ORDER[:-1] + ["wt_diff"])
                    ),
                )

            normalized_stop_stage = _normalize_pipeline_stage(normalized_stop_after)
            normalized_stop_after = normalized_stop_stage or normalized_stop_after
            if (
                normalized_start_from is not None
                and normalized_stop_stage is not None
                and _stage_index(normalized_start_from)
                > _stage_index(normalized_stop_stage)
            ):
                raise PipelineInputRequired(
                    stage="init",
                    message=(
                        f"start_from={normalized_start_from!r} must be earlier than or equal to "
                        f"stop_after={normalized_stop_stage!r}."
                    ),
                )

            novelty_enabled = bool(
                getattr(request, "novelty_enabled", False)
                or normalized_stop_after == "novelty"
            )
            if normalized_stop_after == "rfd3" and not _rfd3_active(request):
                raise PipelineInputRequired(
                    stage="rfd3",
                    message=(
                        "stop_after='rfd3' requires rfd3_use=true and RFD3 inputs "
                        "(for example rfd3_input_pdb or rfd3_inputs_text)."
                    ),
                )
            if normalized_stop_after == "bioemu" and not _bioemu_active(request):
                raise PipelineInputRequired(
                    stage="bioemu",
                    message="stop_after='bioemu' requires bioemu_use=true.",
                )
            if normalized_start_from == "rfd3" and not _rfd3_active(request):
                raise PipelineInputRequired(
                    stage="rfd3",
                    message=(
                        "start_from='rfd3' requires rfd3_use=true and RFD3 inputs "
                        "(for example rfd3_input_pdb or rfd3_inputs_text)."
                    ),
                )
            if normalized_start_from == "bioemu" and not _bioemu_active(request):
                raise PipelineInputRequired(
                    stage="bioemu",
                    message="start_from='bioemu' requires bioemu_use=true.",
                )

            active_tiers, active_tier_keys = _resolve_active_tiers(request)

            if normalized_start_from not in {None, "msa"}:
                if paths.request_json.exists():
                    try:
                        saved_request_payload = _normalize_request_payload(
                            json.loads(paths.request_json.read_text(encoding="utf-8"))
                        )
                    except Exception as exc:
                        raise PipelineInputRequired(
                            stage="init",
                            message=(
                                f"Cannot safely continue run {run_id!r}: failed to read saved request.json ({exc}). "
                                "Use start_from='msa' or a new run_id."
                            ),
                        ) from exc
                    minimum_stage, changed_fields = _minimum_safe_partial_rerun_stage(
                        saved_request_payload,
                        current_request_payload,
                    )
                    if minimum_stage is not None and _stage_index(
                        normalized_start_from
                    ) > _stage_index(minimum_stage):
                        changed_list = ", ".join(changed_fields[:8])
                        if len(changed_fields) > 8:
                            changed_list = (
                                f"{changed_list}, ... (+{len(changed_fields) - 8})"
                            )
                        raise PipelineInputRequired(
                            stage="init",
                            message=(
                                f"Unsafe partial rerun for run {run_id!r}: changed request fields ({changed_list}) "
                                f"require start_from={minimum_stage!r} or earlier. Use a new run_id if you want to keep "
                                "the previous outputs."
                            ),
                        )

            write_json(paths.request_json, current_request_payload)
            _attach_run_to_round_record(self.output_root, request, run_id)

            if normalized_start_from is not None:
                cleared = _clear_stage_outputs_from(
                    paths.root,
                    start_from=normalized_start_from,
                    selected_tier_keys=(
                        active_tier_keys
                        if getattr(request, "selected_tiers", None)
                        else None
                    ),
                )
                detail = f"start_from={normalized_start_from}"
                if getattr(request, "selected_tiers", None):
                    detail = (
                        f"{detail}; selected_tiers={','.join(sorted(active_tier_keys))}"
                    )
                if cleared:
                    detail = f"{detail}; cleared={len(cleared)}"
                set_status(paths, stage="init", state="running", detail=detail)

            msa_dir = _ensure_dir(paths.root / "msa")
            tiers_dir = _ensure_dir(paths.root / "tiers")

            target_pdb_input_text = str(request.target_pdb or "")
            target_pdb_text = target_pdb_input_text
            had_target_pdb_input = bool(target_pdb_text.strip())
            rfd3_files = _rfd3_input_files(request) if _rfd3_active(request) else {}
            rfd3_input_pdb_text = str(request.rfd3_input_pdb or "")
            rfd3_reference_pdb_text = str(
                rfd3_files.get("input.pdb") or rfd3_input_pdb_text
            )
            rfd3_preferred_design_chains = (
                _rfd3_requested_design_chains(request, input_files=rfd3_files)
                if _rfd3_active(request)
                else None
            )
            effective_strip_nonpositive = bool(request.pdb_strip_nonpositive_resseq)
            effective_renumber = bool(request.pdb_renumber_resseq_from_1)
            auto_strip_nonpositive = False

            if (
                _rfd3_active(request)
                and not effective_strip_nonpositive
                and not effective_renumber
            ):
                candidates: list[str] = []
                if rfd3_input_pdb_text.strip():
                    candidates.append(rfd3_input_pdb_text)
                if rfd3_files:
                    for content in rfd3_files.values():
                        if content is None:
                            continue
                        candidates.append(str(content))
                if any(_has_nonpositive_resseq(text) for text in candidates):
                    effective_strip_nonpositive = False
                    effective_renumber = True
                    auto_strip_nonpositive = True

            if rfd3_files and (
                effective_strip_nonpositive
                or effective_renumber
                or bool(rfd3_preferred_design_chains)
            ):
                processed_files: dict[str, str] = {}
                for name, content in rfd3_files.items():
                    text = str(content or "")
                    processed_files[name] = _prepare_pdb_text_for_design_context(
                        text,
                        chains=rfd3_preferred_design_chains,
                        strip_nonpositive_resseq=effective_strip_nonpositive,
                        renumber_resseq_from_1=effective_renumber,
                    )
                rfd3_files = processed_files
                if "input.pdb" in rfd3_files:
                    rfd3_input_pdb_text = str(rfd3_files.get("input.pdb") or "")
            elif rfd3_input_pdb_text.strip() and (
                effective_strip_nonpositive
                or effective_renumber
                or bool(rfd3_preferred_design_chains)
            ):
                rfd3_input_pdb_text = _prepare_pdb_text_for_design_context(
                    rfd3_input_pdb_text,
                    chains=rfd3_preferred_design_chains,
                    strip_nonpositive_resseq=effective_strip_nonpositive,
                    renumber_resseq_from_1=effective_renumber,
                )
            rfd3_reference_pdb_text = str(
                rfd3_files.get("input.pdb") or rfd3_input_pdb_text
            )
            rfd3_backbones: list[dict[str, Any]] | None = None
            rfd3_selected_id: str | None = None
            rfd3_observed_count = 0
            rfd3_diversity_summary: dict[str, Any] | None = None
            rfd3_debug_summary: dict[str, Any] | None = None
            bioemu_backbones: list[dict[str, Any]] | None = None
            bioemu_observed_count = 0
            target_record: FastaRecord | None = None
            msa_defer = False

            if str(request.target_fasta or "").strip():
                target_record = parse_fasta(request.target_fasta)[0]
            else:
                msa_source_pdb_text = ""
                if target_pdb_text.strip():
                    msa_source_pdb_text = target_pdb_text
                elif rfd3_input_pdb_text.strip():
                    msa_source_pdb_text = rfd3_input_pdb_text
                elif rfd3_files and "input.pdb" in rfd3_files:
                    msa_source_pdb_text = str(rfd3_files.get("input.pdb") or "")
                if msa_source_pdb_text.strip() and (
                    effective_strip_nonpositive
                    or effective_renumber
                    or bool(rfd3_preferred_design_chains)
                ):
                    msa_source_pdb_text = _prepare_pdb_text_for_design_context(
                        msa_source_pdb_text,
                        chains=(request.design_chains or rfd3_preferred_design_chains),
                        strip_nonpositive_resseq=effective_strip_nonpositive,
                        renumber_resseq_from_1=effective_renumber,
                    )
                if msa_source_pdb_text.strip():
                    target_record = _target_record_from_pdb(
                        msa_source_pdb_text,
                        design_chains=(
                            request.design_chains or rfd3_preferred_design_chains
                        ),
                    )
                elif _rfd3_active(request):
                    msa_defer = True
                else:
                    raise ValueError("One of target_fasta or target_pdb is required")

            if normalized_start_from is not None and _stage_index("msa") < _stage_index(
                normalized_start_from
            ):
                if not (paths.root / "msa" / "result.tsv").exists():
                    msa_defer = True

            def _run_msa(target_record: FastaRecord) -> str:
                nonlocal msa_tsv_path, msa_a3m_path, msa_filtered_a3m_path

                target_query_fasta = to_fasta([target_record])
                msa_request_hash = _stable_payload_hash(
                    {
                        "target_query_fasta": target_query_fasta,
                        "target_db": request.mmseqs_target_db,
                        "max_seqs": request.mmseqs_max_seqs,
                        "threads": request.mmseqs_threads,
                        "use_gpu": request.mmseqs_use_gpu,
                    }
                )
                _write_text(paths.root / "target.fasta", target_query_fasta)

                set_status(paths, stage="mmseqs_msa", state="running")
                msa_tsv_text, a3m_text = self._get_msa(
                    target_query_fasta,
                    msa_dir,
                    request,
                    on_job_id=lambda job_id: (
                        write_json(
                            msa_dir / "runpod_job.json",
                            {
                                "job_id": job_id,
                                "request_hash": msa_request_hash,
                                "target_db": request.mmseqs_target_db,
                                "max_seqs": request.mmseqs_max_seqs,
                                "threads": request.mmseqs_threads,
                                "use_gpu": request.mmseqs_use_gpu,
                            },
                        ),
                        set_status(
                            paths,
                            stage="mmseqs_msa",
                            state="running",
                            detail=f"runpod_job_id={job_id}",
                        ),
                    ),
                )
                msa_tsv_path = str(msa_dir / "result.tsv")
                msa_a3m_path = str(msa_dir / "result.a3m")

                filtered_a3m_text = a3m_text
                quality = msa_quality(a3m_text)
                if (
                    float(request.msa_min_coverage) > 0.0
                    or float(request.msa_min_identity) > 0.0
                ):
                    filtered_a3m_text, filter_report = filter_a3m(
                        a3m_text,
                        min_coverage=request.msa_min_coverage,
                        min_identity=request.msa_min_identity,
                    )
                    msa_filtered_a3m_path = str(msa_dir / "result.filtered.a3m")
                    _write_text(Path(msa_filtered_a3m_path), filtered_a3m_text)
                    quality["filter"] = filter_report
                    quality["after_filter"] = msa_quality(filtered_a3m_text)
                write_json(msa_dir / "quality.json", quality)
                msa_warns: list[str] = []
                if isinstance(quality.get("warnings"), list):
                    msa_warns.extend(str(w) for w in quality["warnings"])
                after = quality.get("after_filter")
                if isinstance(after, dict) and isinstance(after.get("warnings"), list):
                    msa_warns.extend(f"after_filter:{w}" for w in after["warnings"])
                set_status(
                    paths,
                    stage="mmseqs_msa",
                    state="completed",
                    detail=("; ".join(msa_warns)[:500] if msa_warns else None),
                )
                return filtered_a3m_text

            def _run_conservation(filtered_a3m_text: str):
                nonlocal conservation_path
                set_status(paths, stage="conservation", state="running")
                conservation_weights: list[float] | None = None
                weighting = (
                    str(getattr(request, "conservation_weighting", "none") or "none")
                    .strip()
                    .lower()
                )
                conservation_request_hash = _stable_payload_hash(
                    {
                        "filtered_a3m_sha256": _sha256_text(filtered_a3m_text),
                        "tiers": request.conservation_tiers,
                        "mode": request.conservation_mode,
                        "weighting": weighting,
                        "cluster_method": request.conservation_cluster_method,
                        "cluster_min_seq_id": request.conservation_cluster_min_seq_id,
                        "cluster_coverage": request.conservation_cluster_coverage,
                        "cluster_cov_mode": request.conservation_cluster_cov_mode,
                        "cluster_kmer_per_seq": request.conservation_cluster_kmer_per_seq,
                    }
                )
                if weighting not in {"none", "mmseqs_cluster"}:
                    raise ValueError(
                        "conservation_weighting must be one of: none, mmseqs_cluster"
                    )
                if weighting == "mmseqs_cluster":
                    if request.dry_run:
                        write_json(
                            msa_dir / "sequence_weights.json",
                            {
                                "method": "mmseqs_cluster",
                                "skipped": True,
                                "reason": "dry_run",
                            },
                        )
                    else:
                        if self.mmseqs is None:
                            raise RuntimeError(
                                "MMseqs client is required for conservation_weighting='mmseqs_cluster'"
                            )
                        raw_records = parse_fasta(filtered_a3m_text)
                        hit_ids: list[str] = []
                        fasta_parts: list[str] = []
                        for idx, rec in enumerate(raw_records[1:], start=1):
                            hit_id = f"h{idx:06d}"
                            hit_ids.append(hit_id)
                            ungapped = "".join(
                                ch
                                for ch in strip_insertions(rec.sequence)
                                if ch.isalpha()
                            ).upper()
                            if not ungapped:
                                continue
                            fasta_parts.append(f">{hit_id}\n{ungapped}\n")
                        sequences_fasta = "".join(fasta_parts)
                        if not sequences_fasta.strip() or not hit_ids:
                            conservation_weights = [1.0 for _ in hit_ids]
                            write_json(
                                msa_dir / "sequence_weights.json",
                                {
                                    "method": "mmseqs_cluster",
                                    "skipped": True,
                                    "reason": "no_sequences",
                                    "hit_count": len(hit_ids),
                                    "id_scheme": "h{index:06d} (A3M hit order)",
                                    "weights": list(conservation_weights),
                                },
                            )
                            sequences_fasta = ""
                        if not sequences_fasta.strip():
                            cluster_out = {}
                        else:
                            cluster_out = self.mmseqs.cluster(
                                sequences_fasta=sequences_fasta,
                                threads=int(request.mmseqs_threads),
                                cluster_method=str(
                                    request.conservation_cluster_method or "linclust"
                                ),
                                min_seq_id=float(
                                    request.conservation_cluster_min_seq_id
                                ),
                                coverage=request.conservation_cluster_coverage,
                                cov_mode=request.conservation_cluster_cov_mode,
                                kmer_per_seq=request.conservation_cluster_kmer_per_seq,
                            )
                        if sequences_fasta.strip():
                            cluster_tsv = str(cluster_out.get("cluster_tsv") or "")
                            _write_text(msa_dir / "cluster.tsv", cluster_tsv)
                            weights_by_id = weights_from_mmseqs_cluster_tsv(cluster_tsv)
                            conservation_weights = [
                                float(weights_by_id.get(hit_id, 1.0))
                                for hit_id in hit_ids
                            ]
                            write_json(
                                msa_dir / "sequence_weights.json",
                                {
                                    "method": "mmseqs_cluster",
                                    "cluster_method": str(
                                        request.conservation_cluster_method
                                        or "linclust"
                                    ),
                                    "min_seq_id": float(
                                        request.conservation_cluster_min_seq_id
                                    ),
                                    "coverage": request.conservation_cluster_coverage,
                                    "cov_mode": request.conservation_cluster_cov_mode,
                                    "kmer_per_seq": request.conservation_cluster_kmer_per_seq,
                                    "hit_count": len(hit_ids),
                                    "id_scheme": "h{index:06d} (A3M hit order)",
                                    "weights": list(conservation_weights),
                                    "weight_stats": {
                                        "min": min(conservation_weights)
                                        if conservation_weights
                                        else None,
                                        "max": max(conservation_weights)
                                        if conservation_weights
                                        else None,
                                        "mean": (
                                            sum(conservation_weights)
                                            / len(conservation_weights)
                                        )
                                        if conservation_weights
                                        else None,
                                    },
                                },
                            )
                conservation = compute_conservation(
                    filtered_a3m_text,
                    tiers=request.conservation_tiers,
                    mode=request.conservation_mode,
                    weights=conservation_weights,
                )
                conservation_payload = {
                    "query_length": conservation.query_length,
                    "scores": conservation.scores,
                    "fixed_positions_by_tier": conservation.fixed_positions_by_tier,
                    "mode": request.conservation_mode,
                    "tiers": request.conservation_tiers,
                    "weighting": weighting,
                    "request_hash": conservation_request_hash,
                    "filtered_a3m_sha256": _sha256_text(filtered_a3m_text),
                }
                conservation_path = str(paths.root / "conservation.json")
                write_json(Path(conservation_path), conservation_payload)
                set_status(paths, stage="conservation", state="completed")
                return conservation

            def _fallback_msa(target_record: FastaRecord, *, reason: str) -> str:
                nonlocal msa_tsv_path, msa_a3m_path, msa_filtered_a3m_path
                target_query_fasta = to_fasta([target_record])
                msa_request_hash = _stable_payload_hash(
                    {
                        "target_query_fasta": target_query_fasta,
                        "target_db": request.mmseqs_target_db,
                        "max_seqs": request.mmseqs_max_seqs,
                        "threads": request.mmseqs_threads,
                        "use_gpu": request.mmseqs_use_gpu,
                    }
                )
                _write_text(paths.root / "target.fasta", target_query_fasta)

                query = target_record.sequence
                a3m = to_fasta(
                    [
                        FastaRecord(header="query", sequence=query),
                        FastaRecord(header="fallback_hit1", sequence=query),
                    ]
                )
                tsv = ""
                _write_text(msa_dir / "result.tsv", tsv)
                _write_text(msa_dir / "result.a3m", a3m)
                write_json(
                    msa_dir / "request_meta.json",
                    {
                        "request_hash": msa_request_hash,
                        "query_sha256": _sha256_text(target_query_fasta),
                        "query_length": len(query),
                        "cached": False,
                        "recovered": True,
                    },
                )
                msa_tsv_path = str(msa_dir / "result.tsv")
                msa_a3m_path = str(msa_dir / "result.a3m")

                filtered_a3m_text = a3m
                quality = msa_quality(a3m)
                quality["recovery"] = {"reason": reason, "fallback": True}
                if (
                    float(request.msa_min_coverage) > 0.0
                    or float(request.msa_min_identity) > 0.0
                ):
                    filtered_a3m_text, filter_report = filter_a3m(
                        a3m,
                        min_coverage=request.msa_min_coverage,
                        min_identity=request.msa_min_identity,
                    )
                    msa_filtered_a3m_path = str(msa_dir / "result.filtered.a3m")
                    _write_text(Path(msa_filtered_a3m_path), filtered_a3m_text)
                    quality["filter"] = filter_report
                    quality["after_filter"] = msa_quality(filtered_a3m_text)
                write_json(msa_dir / "quality.json", quality)
                set_status(
                    paths, stage="mmseqs_msa", state="completed", detail="recovered"
                )
                return filtered_a3m_text

            def _fallback_conservation(filtered_a3m_text: str, *, reason: str):
                nonlocal conservation_path
                fallback_a3m = filtered_a3m_text.strip()
                if not fallback_a3m and target_record is not None:
                    fallback_a3m = to_fasta([target_record])
                conservation_request_hash = _stable_payload_hash(
                    {
                        "filtered_a3m_sha256": _sha256_text(fallback_a3m),
                        "tiers": request.conservation_tiers,
                        "mode": request.conservation_mode,
                        "weighting": "none",
                    }
                )
                conservation = compute_conservation(
                    fallback_a3m,
                    tiers=request.conservation_tiers,
                    mode=request.conservation_mode,
                    weights=None,
                )
                conservation_payload = {
                    "query_length": conservation.query_length,
                    "scores": conservation.scores,
                    "fixed_positions_by_tier": conservation.fixed_positions_by_tier,
                    "mode": request.conservation_mode,
                    "tiers": request.conservation_tiers,
                    "weighting": "none",
                    "request_hash": conservation_request_hash,
                    "filtered_a3m_sha256": _sha256_text(fallback_a3m),
                    "recovery": {"reason": reason, "fallback": True},
                }
                conservation_path = str(paths.root / "conservation.json")
                write_json(Path(conservation_path), conservation_payload)
                set_status(
                    paths, stage="conservation", state="completed", detail="recovered"
                )
                return conservation

            has_fixed_positions_extra = False
            if isinstance(request.fixed_positions_extra, dict):
                for positions in request.fixed_positions_extra.values():
                    if isinstance(positions, list) and positions:
                        has_fixed_positions_extra = True
                        break
            stops_before_design = (
                normalized_stop_after == "msa"
                or (normalized_stop_after == "rfd3" and _rfd3_active(request))
                or (normalized_stop_after == "bioemu" and _bioemu_active(request))
            )

            if (
                (not had_target_pdb_input)
                and (not request.dry_run)
                and (not stops_before_design)
                and (not has_fixed_positions_extra)
                and (not (request.ligand_atom_chains or []))
                and (not _rfd3_active(request))
            ):
                raise PipelineInputRequired(
                    stage="needs_fixed_positions_extra",
                    message=(
                        "Sequence-only input (target_pdb is empty): please provide active-site residues via "
                        "fixed_positions_extra (1-based query/FASTA numbering). Example: "
                        "fixed_positions_extra={'A':[10,25,42]} (monomer) or fixed_positions_extra={'*':[...]} "
                        "(apply to all chains). "
                        "Alternative: provide a target_pdb that contains ligand/substrate coordinates and configure "
                        "ligand masking (ligand_resnames or ligand_atom_chains)."
                    ),
                )

            conservation = None
            if not msa_defer:
                if target_record is None:
                    raise ValueError("target_record is required for MSA")
                filtered_a3m_text, msa_recovered, msa_error, msa_recovery = (
                    _recover_stage(
                        "mmseqs_msa",
                        lambda: _run_msa(target_record),
                        fallback=lambda exc: _fallback_msa(
                            target_record, reason=str(exc)
                        ),
                        recovery_actions=["Used fallback MSA (query-only)"],
                    )
                )
                _emit_panel(
                    "mmseqs_msa",
                    detail=("recovered" if msa_recovered else None),
                    error=msa_error,
                    recovery=msa_recovery,
                )
                if request.stop_after == "msa":
                    result = PipelineResult(
                        run_id=run_id,
                        output_dir=str(paths.root),
                        msa_a3m_path=msa_a3m_path,
                        msa_filtered_a3m_path=msa_filtered_a3m_path,
                        msa_tsv_path=msa_tsv_path,
                        conservation_path=None,
                        ligand_mask_path=None,
                        surface_mask_path=None,
                        tiers=[],
                        errors=errors,
                    )
                    write_json(paths.summary_json, asdict(result))
                    set_status(paths, stage="done", state="completed")
                    return result
                conservation, cons_recovered, cons_error, cons_recovery = (
                    _recover_stage(
                        "conservation",
                        lambda: _run_conservation(filtered_a3m_text),
                        fallback=lambda exc: _fallback_conservation(
                            filtered_a3m_text, reason=str(exc)
                        ),
                        recovery_actions=["Used fallback conservation (no weighting)"],
                    )
                )
                _emit_panel(
                    "conservation",
                    detail=("recovered" if cons_recovered else None),
                    error=cons_error,
                    recovery=cons_recovery,
                )

            if _rfd3_active(request):

                def _run_rfd3() -> None:
                    nonlocal \
                        target_pdb_text, \
                        rfd3_backbones, \
                        rfd3_selected_id, \
                        rfd3_input_pdb_text, \
                        rfd3_observed_count, \
                        rfd3_diversity_summary, \
                        rfd3_debug_summary
                    rfd3_dir = _ensure_dir(paths.root / "rfd3")
                    rfd3_detail = (
                        "auto_strip_nonpositive_resseq"
                        if auto_strip_nonpositive
                        else None
                    )
                    set_status(paths, stage="rfd3", state="running", detail=rfd3_detail)

                    inputs_text = str(request.rfd3_inputs_text or "").strip() or None
                    inputs_obj = (
                        request.rfd3_inputs
                        if isinstance(request.rfd3_inputs, dict)
                        else None
                    )
                    rfd3_mode = _effective_rfd3_mode(request, input_files=rfd3_files)
                    if inputs_text is None and inputs_obj is None:
                        inputs_obj = _rfd3_simple_inputs(
                            request, input_files=rfd3_files
                        )
                    if inputs_text is not None and inputs_obj is None:
                        parsed = _parse_json_dict(inputs_text)
                        if parsed is not None:
                            inputs_obj = parsed
                            inputs_text = None
                    inputs_obj = _normalize_rfd3_inputs(inputs_obj)
                    inputs_obj = _inject_rfd3_partial_t(
                        inputs_obj,
                        _effective_rfd3_partial_t(request, mode=rfd3_mode),
                    )
                    rfd3_runtime_design_chains = (
                        _rfd3_design_chains_from_inputs(inputs_obj)
                        or rfd3_preferred_design_chains
                        or request.design_chains
                    )

                    if inputs_text is None and inputs_obj is None:
                        raise ValueError(
                            "RFD3 inputs are required (inputs_text/inputs/input_pdb)"
                        )

                    inputs_payload = inputs_obj
                    if inputs_payload is None and inputs_text:
                        parsed_payload = _parse_json_dict(inputs_text)
                        inputs_payload = (
                            parsed_payload
                            if parsed_payload is not None
                            else {"raw_text": inputs_text}
                        )
                    if inputs_payload is not None:
                        write_json(rfd3_dir / "inputs.json", inputs_payload)
                    if rfd3_files:
                        files_dir = _ensure_dir(rfd3_dir / "input_files")
                        for raw_name, content in rfd3_files.items():
                            name = str(raw_name).replace("\\", "/")
                            rel = Path(name)
                            if rel.is_absolute() or ".." in rel.parts:
                                rel = Path(rel.name)
                            dest = files_dir / rel
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_text(str(content), encoding="utf-8")

                    selected_pdb_path = rfd3_dir / "selected.pdb"
                    selected_json_path = rfd3_dir / "selected.json"
                    selected_cif_path = rfd3_dir / "selected.cif.gz"
                    designs_json_path = rfd3_dir / "designs.json"
                    raw_designs_json_path = rfd3_dir / "raw_designs.json"
                    debug_summary_path = rfd3_dir / "debug_summary.json"
                    target_gate_summary_path = rfd3_dir / "target_gate_summary.json"
                    cache_meta_path = rfd3_dir / "cache_meta.json"
                    runpod_job_path = rfd3_dir / "runpod_job.json"
                    raw_designs_dir = rfd3_dir / "raw_designs"
                    designs_dir = rfd3_dir / "designs"
                    max_designs = max(1, int(request.rfd3_max_return_designs or 1))
                    use_ensemble = bool(request.rfd3_use_ensemble) or max_designs > 1
                    requested_final_count = max_designs if use_ensemble else 1
                    sampling_strategy = _normalize_rfd3_sampling_strategy(
                        request.rfd3_sampling_strategy
                    )
                    fail_on_duplicate_backbones = bool(
                        request.rfd3_fail_on_duplicate_backbones
                    )
                    rfd3_target_rmsd_cutoff = (
                        float(request.rfd3_target_rmsd_cutoff)
                        if request.rfd3_target_rmsd_cutoff is not None
                        else None
                    )
                    if (
                        isinstance(rfd3_target_rmsd_cutoff, float)
                        and rfd3_target_rmsd_cutoff <= 0.0
                    ):
                        rfd3_target_rmsd_cutoff = None
                    rfd3_max_attempted_designs = max(
                        requested_final_count,
                        int(
                            request.rfd3_max_attempted_designs
                            or (requested_final_count * 3)
                        ),
                    )
                    target_gate_source_pdb_text = (
                        target_pdb_input_text
                        if target_pdb_input_text.strip()
                        else (
                            rfd3_reference_pdb_text
                            if rfd3_reference_pdb_text.strip()
                            else target_pdb_text
                        )
                    )
                    (
                        _rfd3_gate_pdb_chains,
                        _rfd3_gate_requested_chains,
                        _rfd3_gate_auto_design_chains,
                        rfd3_target_gate_design_chains,
                        _rfd3_gate_chain_note,
                        _rfd3_gate_model_preset,
                    ) = _resolve_pipeline_chain_strategy(
                        pdb_text=target_gate_source_pdb_text,
                        request_design_chains=rfd3_runtime_design_chains,
                        target_fasta_text=str(request.target_fasta or ""),
                        target_record=target_record,
                        af2_model_preset_requested=request.af2_model_preset,
                    )
                    rfd3_target_gate_reference_pdb_text = _preprocess_pdb_text(
                        target_gate_source_pdb_text,
                        chains=rfd3_target_gate_design_chains,
                        strip_nonpositive_resseq=effective_strip_nonpositive,
                        renumber_resseq_from_1=effective_renumber,
                    )
                    rfd3_target_gate_reference_hash = (
                        _sha256_text(rfd3_target_gate_reference_pdb_text)
                        if rfd3_target_gate_reference_pdb_text.strip()
                        else None
                    )
                    write_json(
                        rfd3_dir / "mode.json",
                        {
                            "mode": rfd3_mode,
                            "requested_partial_t": request.rfd3_partial_t,
                            "effective_partial_t": _effective_rfd3_partial_t(
                                request, mode=rfd3_mode
                            ),
                            "sampling_strategy": _normalize_rfd3_sampling_strategy(
                                request.rfd3_sampling_strategy
                            ),
                            "fail_on_duplicate_backbones": bool(
                                request.rfd3_fail_on_duplicate_backbones
                            ),
                            "target_rmsd_cutoff": rfd3_target_rmsd_cutoff,
                            "backbone_filter_use_dssp": bool(
                                request.backbone_filter_use_dssp
                            ),
                            "max_attempted_designs": rfd3_max_attempted_designs,
                            "requested_final_count": requested_final_count,
                            "target_gate_design_chains": rfd3_target_gate_design_chains,
                            "target_gate_reference_sha256": rfd3_target_gate_reference_hash,
                        },
                    )

                    def _persist_rfd3_design_sets(
                        raw_designs: list[dict[str, Any]] | None,
                        final_backbones: list[dict[str, Any]] | None,
                    ) -> None:
                        write_json(designs_json_path, raw_designs or [])
                        write_json(raw_designs_json_path, raw_designs or [])
                        _write_named_pdb_records(
                            raw_designs_dir, raw_designs, pdb_keys=("pdb", "pdb_text")
                        )
                        _write_named_pdb_records(
                            designs_dir, final_backbones, pdb_keys=("pdb_text", "pdb")
                        )

                    if request.dry_run:
                        if rfd3_input_pdb_text.strip():
                            target_pdb_text = rfd3_input_pdb_text
                        elif rfd3_files and "input.pdb" in rfd3_files:
                            target_pdb_text = str(rfd3_files.get("input.pdb") or "")
                        else:
                            target_pdb_text = _dummy_backbone_pdb(
                                "A" * 60, chain_id="A"
                            )
                        rfd3_selected_id = _canonicalize_rfd3_design_id(
                            "design_0" if use_ensemble else "dry_run"
                        )
                        _write_text(rfd3_dir / "selected.pdb", target_pdb_text)
                        write_json(
                            rfd3_dir / "selected.json",
                            {"id": rfd3_selected_id, "source": "dummy"},
                        )
                        dry_run_designs = [
                            {
                                "id": _canonicalize_rfd3_design_id(f"design_{i}")
                                if use_ensemble
                                else rfd3_selected_id,
                                "pdb": target_pdb_text,
                                "score": None,
                                "source": "dummy",
                            }
                            for i in range(max_designs if use_ensemble else 1)
                        ]
                        rfd3_observed_count = len(dry_run_designs)
                        _persist_rfd3_design_sets(
                            dry_run_designs,
                            _rfd3_design_records_to_backbones(dry_run_designs),
                        )
                        if use_ensemble:
                            rfd3_backbones = _rfd3_design_records_to_backbones(
                                dry_run_designs
                            )
                            rfd3_backbones, rfd3_diversity_summary = (
                                _deduplicate_backbones_by_exact_ca(
                                    rfd3_backbones,
                                    source="rfd3",
                                )
                            )
                            if rfd3_diversity_summary is not None:
                                write_json(
                                    rfd3_dir / "diversity_summary.json",
                                    rfd3_diversity_summary,
                                )
                            duplicate_message = _rfd3_duplicate_backbone_message(
                                requested_count=max_designs,
                                unique_count=int(
                                    rfd3_diversity_summary.get("unique_count") or 0
                                )
                                if rfd3_diversity_summary
                                else 0,
                                duplicate_count=int(
                                    rfd3_diversity_summary.get("duplicate_count") or 0
                                )
                                if rfd3_diversity_summary
                                else 0,
                            )
                            rfd3_debug_summary = {
                                "sampling_strategy_requested": sampling_strategy,
                                "sampling_strategy_effective": sampling_strategy,
                                "independent_retry_performed": False,
                                "independent_retry_attempt_count": 0,
                                "requested_count": max_designs,
                                "raw_count": len(dry_run_designs),
                                "final_unique_count": int(
                                    rfd3_diversity_summary.get("unique_count") or 0
                                ),
                                "duplicate_count": int(
                                    rfd3_diversity_summary.get("duplicate_count") or 0
                                ),
                                "duplicate_contract_error": duplicate_message,
                                "dry_run": True,
                            }
                            write_json(debug_summary_path, rfd3_debug_summary)
                            _persist_rfd3_design_sets(dry_run_designs, rfd3_backbones)
                        set_status(
                            paths, stage="rfd3", state="completed", detail="dry_run"
                        )
                    else:
                        if self.rfd3 is None:
                            raise RuntimeError(
                                "RFD3 endpoint is not configured (set RFD3_ENDPOINT_ID)"
                            )
                        cli_args = _inject_rfd3_cli_defaults(
                            request.rfd3_cli_args, max_designs=max_designs
                        )
                        select_index = int(request.rfd3_design_index or 0)
                        rfd3_request_hash = _stable_payload_hash(
                            {
                                "inputs": inputs_obj,
                                "inputs_text": inputs_text,
                                "input_files": rfd3_files or None,
                                "cli_args": cli_args or None,
                                "env": request.rfd3_env
                                if isinstance(request.rfd3_env, dict)
                                else None,
                                "select_index": select_index,
                                "max_return_designs": max_designs,
                                "return_designs_pdb": use_ensemble,
                                "min_return_design_pdbs": max_designs
                                if use_ensemble
                                else 0,
                                "sampling_strategy": sampling_strategy,
                                "requested_final_count": requested_final_count,
                                "target_rmsd_cutoff": rfd3_target_rmsd_cutoff,
                                "target_gate_design_chains": rfd3_target_gate_design_chains,
                                "target_gate_reference_sha256": rfd3_target_gate_reference_hash,
                                "max_attempted_designs": rfd3_max_attempted_designs,
                            }
                        )
                        raw_designs: list[dict[str, Any]] = []
                        raw_design_ids: set[str] = set()
                        selected_score: Any = None
                        attempts: list[dict[str, Any]] = []
                        rfd3_target_gate_summary: dict[str, Any] | None = None

                        def _build_rfd3_debug_summary(
                            *,
                            raw_designs: list[dict[str, Any]],
                            diversity_summary: dict[str, Any] | None,
                            target_gate_summary: dict[str, Any] | None,
                            attempts: list[dict[str, Any]],
                            independent_retry_performed: bool,
                            independent_retry_attempt_count: int,
                            cache_hit: bool,
                        ) -> dict[str, Any]:
                            unique_count = (
                                int(diversity_summary.get("unique_count") or 0)
                                if isinstance(diversity_summary, dict)
                                else len(raw_designs)
                            )
                            duplicate_count = (
                                int(diversity_summary.get("duplicate_count") or 0)
                                if isinstance(diversity_summary, dict)
                                else 0
                            )
                            accepted_count = (
                                int(target_gate_summary.get("accepted_count") or 0)
                                if isinstance(target_gate_summary, dict)
                                else unique_count
                            )
                            rejected_count = (
                                int(target_gate_summary.get("rejected_count") or 0)
                                if isinstance(target_gate_summary, dict)
                                else 0
                            )
                            return {
                                "sampling_strategy_requested": sampling_strategy,
                                "sampling_strategy_effective": sampling_strategy,
                                "independent_retry_performed": independent_retry_performed,
                                "independent_retry_attempt_count": independent_retry_attempt_count,
                                "requested_count": requested_final_count,
                                "max_attempted_designs": rfd3_max_attempted_designs,
                                "raw_count": len(raw_designs),
                                "unique_before_target_gate_count": unique_count,
                                "final_unique_count": accepted_count,
                                "duplicate_count": duplicate_count,
                                "duplicate_contract_error": _rfd3_duplicate_backbone_message(
                                    requested_count=requested_final_count,
                                    unique_count=unique_count,
                                    duplicate_count=duplicate_count,
                                ),
                                "target_rmsd_cutoff": rfd3_target_rmsd_cutoff,
                                "target_rmsd_gate_applied": bool(
                                    isinstance(target_gate_summary, dict)
                                    and target_gate_summary.get("applied")
                                ),
                                "off_target_reject_count": rejected_count,
                                "target_rmsd_contract_error": _rfd3_target_gate_message(
                                    requested_count=requested_final_count,
                                    accepted_count=accepted_count,
                                    rejected_count=rejected_count,
                                    cutoff=rfd3_target_rmsd_cutoff,
                                ),
                                "cache_hit": cache_hit,
                                "attempts": attempts,
                            }

                        def _load_cached_rfd3_outputs() -> bool:
                            nonlocal \
                                target_pdb_text, \
                                rfd3_backbones, \
                                rfd3_selected_id, \
                                rfd3_observed_count, \
                                rfd3_diversity_summary, \
                                rfd3_debug_summary, \
                                raw_designs, \
                                raw_design_ids, \
                                selected_score, \
                                attempts, \
                                rfd3_target_gate_summary
                            if request.force or not selected_pdb_path.exists():
                                return False
                            try:
                                cached_pdb_text = selected_pdb_path.read_text(
                                    encoding="utf-8"
                                )
                            except Exception:
                                return False
                            if not cached_pdb_text.strip():
                                return False

                            selected_meta: dict[str, Any] = {}
                            if selected_json_path.exists():
                                try:
                                    selected_raw = json.loads(
                                        selected_json_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    selected_raw = None
                                if isinstance(selected_raw, dict):
                                    selected_meta = _canonicalize_rfd3_design_record(
                                        selected_raw
                                    )
                                    if selected_meta != selected_raw:
                                        write_json(selected_json_path, selected_meta)
                            selected_source = (
                                str(selected_meta.get("source") or "").strip().lower()
                            )
                            if selected_source in {"fallback", "dummy"}:
                                return False

                            cached_hash = ""
                            if cache_meta_path.exists():
                                try:
                                    cache_meta = json.loads(
                                        cache_meta_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    cache_meta = None
                                if isinstance(cache_meta, dict):
                                    cached_hash = str(
                                        cache_meta.get("request_hash") or ""
                                    ).strip()
                            if not cached_hash and runpod_job_path.exists():
                                try:
                                    job_meta = json.loads(
                                        runpod_job_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    job_meta = None
                                if isinstance(job_meta, dict):
                                    cached_hash = str(
                                        job_meta.get("request_hash") or ""
                                    ).strip()
                            if cached_hash and cached_hash != rfd3_request_hash:
                                return False

                            target_pdb_text = cached_pdb_text
                            rfd3_selected_id = _canonicalize_rfd3_design_id(
                                selected_meta.get("id") or "cached"
                            )
                            selected_score = selected_meta.get("score")

                            cached_designs_path = (
                                raw_designs_json_path
                                if raw_designs_json_path.exists()
                                else designs_json_path
                            )
                            cached_designs: list[dict[str, Any]] = []
                            if cached_designs_path.exists():
                                try:
                                    cached_designs_raw = json.loads(
                                        cached_designs_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    cached_designs_raw = None
                                if isinstance(cached_designs_raw, list):
                                    cached_designs = _canonicalize_rfd3_design_list(
                                        cached_designs_raw
                                    )
                            if not cached_designs:
                                cached_designs = [
                                    {
                                        "id": rfd3_selected_id,
                                        "pdb": target_pdb_text,
                                        "score": selected_meta.get("score"),
                                        "source": "rfd3",
                                    }
                                ]

                            existing_debug: dict[str, Any] = {}
                            if debug_summary_path.exists():
                                try:
                                    debug_raw = json.loads(
                                        debug_summary_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    debug_raw = None
                                if isinstance(debug_raw, dict):
                                    existing_debug = dict(debug_raw)

                            raw_designs = list(cached_designs)
                            raw_design_ids = {
                                str(item.get("id") or "").strip()
                                for item in raw_designs
                                if isinstance(item, dict)
                                and str(item.get("id") or "").strip()
                            }
                            attempts = (
                                list(existing_debug.get("attempts"))
                                if isinstance(existing_debug.get("attempts"), list)
                                else []
                            )
                            try:
                                refresh_state = _refresh_rfd3_final_backbones()
                            except BackboneContractError:
                                return False
                            independent_retry_performed = bool(
                                existing_debug.get("independent_retry_performed")
                            )
                            independent_retry_attempt_count = int(
                                existing_debug.get("independent_retry_attempt_count")
                                or 0
                            )
                            rfd3_debug_summary = _build_rfd3_debug_summary(
                                raw_designs=raw_designs,
                                diversity_summary=rfd3_diversity_summary,
                                target_gate_summary=rfd3_target_gate_summary,
                                attempts=attempts,
                                independent_retry_performed=independent_retry_performed,
                                independent_retry_attempt_count=independent_retry_attempt_count,
                                cache_hit=True,
                            )
                            write_json(debug_summary_path, rfd3_debug_summary)
                            _persist_rfd3_design_sets(raw_designs, rfd3_backbones)
                            duplicate_message = str(
                                rfd3_debug_summary.get("duplicate_contract_error") or ""
                            ).strip()
                            target_gate_message = str(
                                rfd3_debug_summary.get("target_rmsd_contract_error")
                                or ""
                            ).strip()
                            accepted_count = int(
                                refresh_state.get("accepted_count") or 0
                            )
                            if accepted_count < requested_final_count:
                                if len(raw_designs) < rfd3_max_attempted_designs:
                                    return False
                                raise BackboneContractError(
                                    target_gate_message
                                    or duplicate_message
                                    or "RFD3 target RMSD gate failed"
                                )
                            if (
                                sampling_strategy == "auto"
                                and duplicate_message
                                and not independent_retry_performed
                            ):
                                return False
                            if fail_on_duplicate_backbones and duplicate_message:
                                raise BackboneContractError(duplicate_message)
                            set_status(
                                paths, stage="rfd3", state="completed", detail="cached"
                            )
                            return True

                        resume_job_id: str | None = None
                        if (
                            runpod_job_path.exists()
                            and not request.force
                            and sampling_strategy != "independent_jobs"
                        ):
                            try:
                                meta = json.loads(
                                    runpod_job_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                meta = {}
                            job_id = (
                                str(meta.get("job_id") or "").strip()
                                if isinstance(meta, dict)
                                else ""
                            )
                            if job_id and isinstance(meta, dict):
                                same_request = _runpod_meta_matches(
                                    meta,
                                    {
                                        "request_hash": rfd3_request_hash,
                                        "select_index": select_index,
                                        "max_return_designs": max_designs,
                                        "return_designs_pdb": use_ensemble,
                                        "min_return_design_pdbs": max_designs
                                        if use_ensemble
                                        else 0,
                                        "cli_args": cli_args,
                                    },
                                )
                                if same_request:
                                    resume_job_id = job_id

                        runpod_jobs_dir = _ensure_dir(rfd3_dir / "runpod_jobs")

                        def _call_rfd3_design(
                            *,
                            requested_designs: int,
                            attempt_label: str,
                            resume_job: str | None = None,
                            primary_attempt: bool = False,
                        ) -> dict[str, Any]:
                            attempt_cli_args = _inject_rfd3_cli_defaults(
                                request.rfd3_cli_args, max_designs=requested_designs
                            )
                            attempt_job_path = (
                                runpod_job_path
                                if primary_attempt
                                else runpod_jobs_dir / f"{attempt_label}.json"
                            )
                            job_id_holder: dict[str, str | None] = {"job_id": None}

                            def _on_rfd3_job_id(job_id: str) -> None:
                                job_id_holder["job_id"] = job_id
                                payload = {
                                    "job_id": job_id,
                                    "request_hash": rfd3_request_hash,
                                    "select_index": select_index,
                                    "max_return_designs": requested_designs,
                                    "return_designs_pdb": True,
                                    "min_return_design_pdbs": requested_designs
                                    if requested_designs > 1
                                    else 0,
                                    "cli_args": attempt_cli_args,
                                    "attempt_label": attempt_label,
                                }
                                write_json(attempt_job_path, payload)
                                set_status(
                                    paths,
                                    stage="rfd3",
                                    state="running",
                                    detail=f"runpod_job_id={job_id}",
                                )

                            try:
                                return self.rfd3.design(
                                    inputs=inputs_obj,
                                    inputs_text=inputs_text,
                                    input_files=rfd3_files or None,
                                    cli_args=attempt_cli_args,
                                    env=request.rfd3_env,
                                    select_index=select_index,
                                    max_return_designs=requested_designs,
                                    return_designs_pdb=True,
                                    min_return_design_pdbs=(
                                        requested_designs
                                        if requested_designs > 1
                                        else 0
                                    ),
                                    resume_job_id=resume_job,
                                    on_job_id=_on_rfd3_job_id,
                                )
                            except TypeError as exc:
                                if "resume_job_id" not in str(exc):
                                    raise
                                return self.rfd3.design(
                                    inputs=inputs_obj,
                                    inputs_text=inputs_text,
                                    input_files=rfd3_files or None,
                                    cli_args=attempt_cli_args,
                                    env=request.rfd3_env,
                                    select_index=select_index,
                                    max_return_designs=requested_designs,
                                    return_designs_pdb=True,
                                    min_return_design_pdbs=(
                                        requested_designs
                                        if requested_designs > 1
                                        else 0
                                    ),
                                    on_job_id=_on_rfd3_job_id,
                                )

                        def _ingest_rfd3_output(
                            rfd3_out: dict[str, Any],
                            *,
                            attempt_label: str,
                            requested_designs: int,
                            primary_attempt: bool,
                            job_id: str | None = None,
                        ) -> None:
                            nonlocal target_pdb_text, rfd3_selected_id, selected_score
                            selected = rfd3_out.get("selected")
                            if not isinstance(selected, dict):
                                raise RuntimeError(
                                    f"RFD3 output missing selected design: {rfd3_out}"
                                )
                            selected = _canonicalize_rfd3_design_record(selected)
                            selected_id = str(
                                selected.get("id")
                                or _canonicalize_rfd3_design_id("selected")
                            )
                            selected_pdb_text = str(selected.get("pdb") or "")
                            if not selected_pdb_text.strip():
                                raise RuntimeError(
                                    "RFD3 selected design did not include PDB text"
                                )

                            canonical_designs = _canonicalize_rfd3_design_list(
                                rfd3_out.get("designs")
                            )
                            if not canonical_designs:
                                canonical_designs = [
                                    {
                                        "id": selected_id,
                                        "pdb": selected_pdb_text,
                                        "score": selected.get("score"),
                                        "source": "rfd3",
                                    }
                                ]
                            elif use_ensemble and not any(
                                str(item.get("id") or "") == selected_id
                                for item in canonical_designs
                            ):
                                canonical_designs.insert(
                                    0,
                                    {
                                        "id": selected_id,
                                        "pdb": selected_pdb_text,
                                        "score": selected.get("score"),
                                        "source": "rfd3",
                                    },
                                )

                            canonical_designs = _rfd3_uniquify_design_records(
                                canonical_designs,
                                label=attempt_label,
                                existing_ids=raw_design_ids,
                            )
                            raw_designs.extend(canonical_designs)
                            raw_design_ids.update(
                                str(item.get("id") or "").strip()
                                for item in canonical_designs
                                if isinstance(item, dict)
                                and str(item.get("id") or "").strip()
                            )

                            materialized_ids = {
                                str(item.get("id") or "").strip()
                                for item in _rfd3_design_records_to_backbones(
                                    canonical_designs
                                )
                                if isinstance(item, dict)
                                and str(item.get("id") or "").strip()
                            }
                            if requested_designs > 1 and selected_pdb_text.strip():
                                materialized_ids.add(selected_id)
                            materialized_count = len(materialized_ids)
                            missing_design_pdbs = _rfd3_missing_design_pdb_message(
                                requested_count=requested_designs,
                                observed_count=len(canonical_designs),
                                materialized_count=materialized_count,
                            )
                            if missing_design_pdbs:
                                raise BackboneContractError(missing_design_pdbs)

                            attempts.append(
                                {
                                    "label": attempt_label,
                                    "requested_designs": requested_designs,
                                    "returned_designs": len(canonical_designs),
                                    "materialized_count": materialized_count,
                                    "job_id": job_id,
                                }
                            )

                            if primary_attempt:
                                _write_selected_design_record(selected)

                        def _write_selected_design_record(
                            record: dict[str, Any] | None,
                        ) -> None:
                            nonlocal target_pdb_text, rfd3_selected_id, selected_score
                            if not isinstance(record, dict):
                                return
                            selected_record = _canonicalize_rfd3_design_record(record)
                            selected_id = str(
                                selected_record.get("id")
                                or _canonicalize_rfd3_design_id("selected")
                            ).strip()
                            selected_pdb_text = str(
                                selected_record.get("pdb")
                                or selected_record.get("pdb_text")
                                or ""
                            )
                            if not selected_id or not selected_pdb_text.strip():
                                return
                            rfd3_selected_id = selected_id
                            selected_score = selected_record.get("score")
                            target_pdb_text = selected_pdb_text
                            _write_text(selected_pdb_path, target_pdb_text)
                            selected_meta = {
                                key: value
                                for key, value in selected_record.items()
                                if key not in {"pdb", "pdb_text", "cif_gz_base64"}
                            }
                            selected_meta.setdefault("source", "rfd3")
                            selected_meta["request_hash"] = rfd3_request_hash
                            write_json(selected_json_path, selected_meta)
                            cif_b64 = selected_record.get("cif_gz_base64")
                            if isinstance(cif_b64, str) and cif_b64.strip():
                                try:
                                    cif_bytes = base64.b64decode(cif_b64)
                                    selected_cif_path.write_bytes(cif_bytes)
                                except Exception:
                                    _remove_path_if_exists(selected_cif_path)
                            else:
                                _remove_path_if_exists(selected_cif_path)

                        def _selected_design_record_from_raw() -> dict[str, Any] | None:
                            selected_key = str(rfd3_selected_id or "").strip()
                            for record in raw_designs:
                                if not isinstance(record, dict):
                                    continue
                                if str(record.get("id") or "").strip() == selected_key:
                                    return dict(record)
                            if selected_key and target_pdb_text.strip():
                                return {
                                    "id": selected_key,
                                    "pdb": target_pdb_text,
                                    "score": selected_score,
                                    "source": "rfd3",
                                }
                            return None

                        def _refresh_rfd3_final_backbones() -> dict[str, Any]:
                            nonlocal \
                                target_pdb_text, \
                                rfd3_backbones, \
                                rfd3_diversity_summary, \
                                rfd3_observed_count, \
                                rfd3_selected_id, \
                                selected_score, \
                                rfd3_target_gate_summary
                            rfd3_observed_count = len(raw_designs) if raw_designs else 1
                            ensemble = _rfd3_design_records_to_backbones(raw_designs)
                            selected_record = _selected_design_record_from_raw()
                            if selected_record is not None and not any(
                                str(item.get("id") or "") == str(rfd3_selected_id or "")
                                for item in ensemble
                            ):
                                ensemble.insert(
                                    0,
                                    {
                                        "id": rfd3_selected_id
                                        or _canonicalize_rfd3_design_id("selected"),
                                        "pdb_text": target_pdb_text,
                                        "score": selected_score,
                                        "source": "rfd3",
                                    },
                                )
                            materialized_count = _backbone_materialized_count(ensemble)
                            missing_design_pdbs = _rfd3_missing_design_pdb_message(
                                requested_count=requested_final_count,
                                observed_count=rfd3_observed_count,
                                materialized_count=materialized_count,
                            )
                            if missing_design_pdbs:
                                raise BackboneContractError(missing_design_pdbs)
                            deduplicated_backbones, rfd3_diversity_summary = (
                                _deduplicate_backbones_by_exact_ca(
                                    ensemble,
                                    source="rfd3",
                                )
                            )
                            if rfd3_diversity_summary is not None:
                                write_json(
                                    rfd3_dir / "diversity_summary.json",
                                    rfd3_diversity_summary,
                                )
                            accepted_backbones, rfd3_target_gate_summary = (
                                _filter_backbones_by_target_rmsd(
                                    deduplicated_backbones,
                                    reference_pdb_text=rfd3_target_gate_reference_pdb_text,
                                    chains=rfd3_target_gate_design_chains,
                                    cutoff=rfd3_target_rmsd_cutoff,
                                    source="rfd3",
                                    strip_nonpositive_resseq=effective_strip_nonpositive,
                                    renumber_resseq_from_1=effective_renumber,
                                    use_dssp_non_loop=bool(
                                        request.backbone_filter_use_dssp
                                    ),
                                )
                            )
                            if rfd3_target_gate_summary is not None:
                                write_json(
                                    target_gate_summary_path, rfd3_target_gate_summary
                                )
                            accepted_backbones = accepted_backbones or []
                            promoted_record: dict[str, Any] | None = None
                            if accepted_backbones:
                                promoted_backbone = next(
                                    (
                                        item
                                        for item in accepted_backbones
                                        if str(item.get("id") or "").strip()
                                        == str(rfd3_selected_id or "").strip()
                                    ),
                                    accepted_backbones[0],
                                )
                                promoted_id = str(
                                    promoted_backbone.get("id") or ""
                                ).strip()
                                for record in raw_designs:
                                    if not isinstance(record, dict):
                                        continue
                                    if (
                                        str(record.get("id") or "").strip()
                                        == promoted_id
                                    ):
                                        promoted_record = dict(record)
                                        break
                                if promoted_record is None:
                                    promoted_record = {
                                        "id": promoted_id,
                                        "pdb": str(
                                            promoted_backbone.get("pdb_text") or ""
                                        ),
                                        "score": promoted_backbone.get("score"),
                                        "source": "rfd3",
                                    }
                                _write_selected_design_record(promoted_record)
                            if use_ensemble:
                                rfd3_backbones = accepted_backbones
                            else:
                                rfd3_backbones = None
                            accepted_count = len(accepted_backbones)
                            unique_count = (
                                int(rfd3_diversity_summary.get("unique_count") or 0)
                                if isinstance(rfd3_diversity_summary, dict)
                                else accepted_count
                            )
                            rejected_count = (
                                int(rfd3_target_gate_summary.get("rejected_count") or 0)
                                if isinstance(rfd3_target_gate_summary, dict)
                                else 0
                            )
                            return {
                                "accepted_count": accepted_count,
                                "unique_count": unique_count,
                                "duplicate_count": (
                                    int(
                                        rfd3_diversity_summary.get("duplicate_count")
                                        or 0
                                    )
                                    if isinstance(rfd3_diversity_summary, dict)
                                    else 0
                                ),
                                "off_target_reject_count": rejected_count,
                            }

                        def _read_attempt_job_id(
                            attempt_label: str, *, primary_attempt: bool
                        ) -> str | None:
                            meta_path = (
                                runpod_job_path
                                if primary_attempt
                                else runpod_jobs_dir / f"{attempt_label}.json"
                            )
                            try:
                                attempt_job_meta = json.loads(
                                    meta_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                attempt_job_meta = {}
                            if not isinstance(attempt_job_meta, dict):
                                return None
                            job_id = str(attempt_job_meta.get("job_id") or "").strip()
                            return job_id or None

                        if _load_cached_rfd3_outputs():
                            return

                        if (
                            sampling_strategy == "independent_jobs"
                            and use_ensemble
                            and max_designs > 1
                        ):
                            for index in range(max_designs):
                                attempt_label = f"independent_{index + 1}"
                                out = _call_rfd3_design(
                                    requested_designs=1,
                                    attempt_label=attempt_label,
                                    primary_attempt=(index == 0),
                                )
                                _ingest_rfd3_output(
                                    out,
                                    attempt_label=attempt_label,
                                    requested_designs=1,
                                    primary_attempt=(index == 0),
                                    job_id=_read_attempt_job_id(
                                        attempt_label,
                                        primary_attempt=(index == 0),
                                    ),
                                )
                            independent_retry_performed = True
                            independent_retry_attempt_count = max_designs
                        else:
                            batch_requested_designs = max_designs if use_ensemble else 1
                            out = _call_rfd3_design(
                                requested_designs=batch_requested_designs,
                                attempt_label="batch",
                                resume_job=resume_job_id,
                                primary_attempt=True,
                            )
                            _ingest_rfd3_output(
                                out,
                                attempt_label="batch",
                                requested_designs=batch_requested_designs,
                                primary_attempt=True,
                                job_id=_read_attempt_job_id(
                                    "batch", primary_attempt=True
                                ),
                            )
                            independent_retry_performed = False
                            independent_retry_attempt_count = 0

                        refresh_state = _refresh_rfd3_final_backbones()
                        retry_index = 0
                        while (
                            int(refresh_state.get("accepted_count") or 0)
                            < requested_final_count
                        ):
                            remaining_budget = max(
                                0, rfd3_max_attempted_designs - len(raw_designs)
                            )
                            if remaining_budget <= 0:
                                break
                            accepted_deficit = max(
                                0,
                                requested_final_count
                                - int(refresh_state.get("accepted_count") or 0),
                            )
                            unique_deficit = max(
                                0,
                                requested_final_count
                                - int(refresh_state.get("unique_count") or 0),
                            )
                            if sampling_strategy == "independent_jobs":
                                requested_retry_designs = 1
                            elif sampling_strategy == "auto" and unique_deficit > 0:
                                requested_retry_designs = 1
                            else:
                                requested_retry_designs = min(
                                    accepted_deficit, remaining_budget
                                )
                            requested_retry_designs = max(
                                1, min(requested_retry_designs, remaining_budget)
                            )
                            retry_index += 1
                            attempt_label = f"retry_{retry_index}"
                            out = _call_rfd3_design(
                                requested_designs=requested_retry_designs,
                                attempt_label=attempt_label,
                                primary_attempt=False,
                            )
                            _ingest_rfd3_output(
                                out,
                                attempt_label=attempt_label,
                                requested_designs=requested_retry_designs,
                                primary_attempt=False,
                                job_id=_read_attempt_job_id(
                                    attempt_label, primary_attempt=False
                                ),
                            )
                            independent_retry_performed = True
                            independent_retry_attempt_count += 1
                            refresh_state = _refresh_rfd3_final_backbones()

                        _persist_rfd3_design_sets(raw_designs, rfd3_backbones)
                        rfd3_debug_summary = _build_rfd3_debug_summary(
                            raw_designs=raw_designs,
                            diversity_summary=rfd3_diversity_summary,
                            target_gate_summary=rfd3_target_gate_summary,
                            attempts=attempts,
                            independent_retry_performed=independent_retry_performed,
                            independent_retry_attempt_count=independent_retry_attempt_count,
                            cache_hit=False,
                        )
                        write_json(debug_summary_path, rfd3_debug_summary)
                        write_json(
                            cache_meta_path,
                            {
                                "request_hash": rfd3_request_hash,
                                "select_index": select_index,
                                "max_return_designs": max_designs,
                                "return_designs_pdb": use_ensemble,
                                "cli_args": cli_args,
                                "sampling_strategy": sampling_strategy,
                                "independent_retry_performed": independent_retry_performed,
                                "requested_final_count": requested_final_count,
                                "target_rmsd_cutoff": rfd3_target_rmsd_cutoff,
                                "target_gate_design_chains": rfd3_target_gate_design_chains,
                                "target_gate_reference_sha256": rfd3_target_gate_reference_hash,
                                "max_attempted_designs": rfd3_max_attempted_designs,
                                "source": "rfd3",
                            },
                        )
                        duplicate_message = str(
                            rfd3_debug_summary.get("duplicate_contract_error") or ""
                        ).strip()
                        target_gate_message = str(
                            rfd3_debug_summary.get("target_rmsd_contract_error") or ""
                        ).strip()
                        accepted_count = int(refresh_state.get("accepted_count") or 0)
                        if accepted_count < requested_final_count:
                            if accepted_count <= 0:
                                message = (
                                    target_gate_message
                                    or duplicate_message
                                    or "RFD3 target RMSD gate failed"
                                )
                                raise RuntimeError(
                                    f"RFD3 produced no acceptable backbones. {message}"
                                )
                            raise BackboneContractError(
                                target_gate_message
                                or duplicate_message
                                or "RFD3 target RMSD gate failed"
                            )
                        if fail_on_duplicate_backbones and duplicate_message:
                            raise BackboneContractError(duplicate_message)
                        set_status(paths, stage="rfd3", state="completed")

                def _fallback_rfd3(exc: Exception) -> None:
                    nonlocal \
                        target_pdb_text, \
                        rfd3_backbones, \
                        rfd3_selected_id, \
                        rfd3_input_pdb_text, \
                        rfd3_observed_count, \
                        rfd3_diversity_summary, \
                        rfd3_debug_summary
                    rfd3_dir = _ensure_dir(paths.root / "rfd3")
                    write_json(
                        rfd3_dir / "recovery.json",
                        {
                            "error": str(exc),
                            "recovered_at": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.gmtime()
                            ),
                        },
                    )
                    rfd3_backbones = None
                    rfd3_selected_id = _canonicalize_rfd3_design_id("recovered")
                    fallback_pdb_text = ""
                    if rfd3_input_pdb_text.strip():
                        fallback_pdb_text = rfd3_input_pdb_text
                    elif rfd3_files and "input.pdb" in rfd3_files:
                        fallback_pdb_text = str(rfd3_files.get("input.pdb") or "")
                    elif target_pdb_input_text.strip():
                        fallback_pdb_text = target_pdb_input_text
                    elif target_pdb_text.strip():
                        fallback_pdb_text = target_pdb_text
                    elif target_record is not None:
                        fallback_pdb_text = _dummy_backbone_pdb(
                            target_record.sequence, chain_id="A"
                        )
                    else:
                        fallback_pdb_text = _dummy_backbone_pdb("A" * 60, chain_id="A")
                    target_pdb_text = fallback_pdb_text
                    if target_pdb_text.strip():
                        _write_text(rfd3_dir / "selected.pdb", target_pdb_text)
                        write_json(
                            rfd3_dir / "selected.json",
                            {"id": rfd3_selected_id, "source": "fallback"},
                        )
                    set_status(
                        paths, stage="rfd3", state="completed", detail="recovered"
                    )

                _, rfd3_recovered, rfd3_error, rfd3_recovery = _recover_stage(
                    "rfd3",
                    _run_rfd3,
                    fallback=_fallback_rfd3,
                    recovery_actions=["Used fallback backbone (no RFD3)"],
                )
                _emit_panel(
                    "rfd3",
                    detail=("recovered" if rfd3_recovered else None),
                    error=rfd3_error,
                    recovery=rfd3_recovery,
                )

                if request.stop_after == "rfd3":
                    result = PipelineResult(
                        run_id=run_id,
                        output_dir=str(paths.root),
                        msa_a3m_path=msa_a3m_path,
                        msa_filtered_a3m_path=msa_filtered_a3m_path,
                        msa_tsv_path=msa_tsv_path,
                        conservation_path=conservation_path,
                        ligand_mask_path=None,
                        surface_mask_path=None,
                        tiers=[],
                        errors=errors,
                    )
                    write_json(paths.summary_json, asdict(result))
                    set_status(paths, stage="done", state="completed")
                    return result

            if _bioemu_active(request):
                bioemu_dir = _ensure_dir(paths.root / "bioemu")
                set_status(paths, stage="bioemu", state="running")

                bioemu_sequence = _clean_protein_sequence(
                    str(request.bioemu_sequence or "")
                )
                if not bioemu_sequence:
                    if target_record is not None:
                        bioemu_sequence = _clean_protein_sequence(
                            target_record.sequence
                        )
                    elif target_pdb_text.strip():
                        extracted = sequence_by_chain(
                            target_pdb_text, chains=request.design_chains
                        )
                        if extracted:
                            chain_order = (
                                sorted(request.design_chains)
                                if request.design_chains
                                else sorted(extracted.keys())
                            )
                            merged = "".join(
                                extracted.get(chain_id, "") for chain_id in chain_order
                            )
                            bioemu_sequence = _clean_protein_sequence(merged)
                if not bioemu_sequence:
                    raise ValueError(
                        "BioEmu requires a protein sequence. Provide bioemu_sequence, target_fasta, or a target_pdb with ATOM records."
                    )

                bioemu_num_samples = int(max(1, request.bioemu_num_samples))
                bioemu_batch_size_100 = (
                    int(request.bioemu_batch_size_100)
                    if request.bioemu_batch_size_100 is not None
                    else None
                )
                bioemu_model_name = str(request.bioemu_model_name or "bioemu-v1.1")
                bioemu_filter_samples = bool(request.bioemu_filter_samples)
                bioemu_base_seed = (
                    int(request.bioemu_base_seed)
                    if request.bioemu_base_seed is not None
                    else None
                )
                bioemu_steering_config_text = (
                    str(request.bioemu_steering_config_text or "").strip() or None
                )
                bioemu_max_return_structures = int(
                    max(1, request.bioemu_max_return_structures)
                )
                bioemu_target_rmsd_cutoff = (
                    float(request.bioemu_target_rmsd_cutoff)
                    if request.bioemu_target_rmsd_cutoff is not None
                    else None
                )
                if (
                    isinstance(bioemu_target_rmsd_cutoff, float)
                    and bioemu_target_rmsd_cutoff <= 0.0
                ):
                    bioemu_target_rmsd_cutoff = None
                bioemu_max_attempted_structures = max(
                    bioemu_max_return_structures,
                    int(
                        request.bioemu_max_attempted_structures
                        or (bioemu_max_return_structures * 3)
                    ),
                )
                bioemu_env = (
                    dict(request.bioemu_env)
                    if isinstance(request.bioemu_env, dict)
                    else None
                )

                write_json(
                    bioemu_dir / "request.json",
                    {
                        "sequence": bioemu_sequence,
                        "num_samples": bioemu_num_samples,
                        "batch_size_100": bioemu_batch_size_100,
                        "model_name": bioemu_model_name,
                        "filter_samples": bioemu_filter_samples,
                        "base_seed": bioemu_base_seed,
                        "steering_config_text": bioemu_steering_config_text,
                        "max_return_structures": bioemu_max_return_structures,
                        "target_rmsd_cutoff": bioemu_target_rmsd_cutoff,
                        "backbone_filter_use_dssp": bool(
                            request.backbone_filter_use_dssp
                        ),
                        "max_attempted_structures": bioemu_max_attempted_structures,
                        "env": bioemu_env,
                    },
                )

                if request.dry_run:
                    sample_count = min(bioemu_num_samples, bioemu_max_return_structures)
                    bioemu_observed_count = sample_count
                    base_pdb = (
                        target_pdb_text
                        if target_pdb_text.strip()
                        else _dummy_backbone_pdb(bioemu_sequence, chain_id="A")
                    )
                    bioemu_backbones = [
                        {
                            "id": f"bioemu_{i:03d}",
                            "pdb_text": base_pdb,
                            "source": "bioemu",
                            "frame_index": i,
                        }
                        for i in range(sample_count)
                    ]
                    designs_dir = _ensure_dir(bioemu_dir / "designs")
                    sample_entries: list[dict[str, object]] = []
                    for entry in bioemu_backbones:
                        bb_id = _safe_id(str(entry.get("id") or "bioemu"))
                        _write_text(
                            designs_dir / f"{bb_id}.pdb",
                            str(entry.get("pdb_text") or ""),
                        )
                        sample_entries.append(
                            {
                                "id": str(entry.get("id") or ""),
                                "frame_index": entry.get("frame_index"),
                                "source": "dry_run",
                            }
                        )
                    write_json(
                        bioemu_dir / "sample_pdbs.json", {"samples": sample_entries}
                    )
                    set_status(
                        paths,
                        stage="bioemu",
                        state="completed",
                        detail=f"dry_run structures={len(bioemu_backbones)}",
                    )
                else:
                    if self.bioemu is None:
                        raise RuntimeError(
                            "BioEmu endpoint is not configured (set BIOEMU_ENDPOINT_ID)"
                        )

                    runpod_job_path = bioemu_dir / "runpod_job.json"
                    output_path = bioemu_dir / "output.json"
                    sample_pdbs_path = bioemu_dir / "sample_pdbs.json"
                    raw_samples_path = bioemu_dir / "raw_samples.json"
                    debug_summary_path = bioemu_dir / "debug_summary.json"
                    target_gate_summary_path = bioemu_dir / "target_gate_summary.json"
                    cache_meta_path = bioemu_dir / "cache_meta.json"
                    raw_samples_dir = bioemu_dir / "raw_samples"
                    runpod_jobs_dir = _ensure_dir(bioemu_dir / "runpod_jobs")
                    designs_dir = bioemu_dir / "designs"
                    bioemu_target_gate_source_pdb_text = (
                        target_pdb_input_text
                        if target_pdb_input_text.strip()
                        else (
                            rfd3_reference_pdb_text
                            if rfd3_reference_pdb_text.strip()
                            else target_pdb_text
                        )
                    )
                    (
                        _bioemu_gate_pdb_chains,
                        _bioemu_gate_requested_chains,
                        _bioemu_gate_auto_design_chains,
                        bioemu_target_gate_design_chains,
                        _bioemu_gate_chain_note,
                        _bioemu_gate_model_preset,
                    ) = _resolve_pipeline_chain_strategy(
                        pdb_text=bioemu_target_gate_source_pdb_text,
                        request_design_chains=request.design_chains,
                        target_fasta_text=str(request.target_fasta or ""),
                        target_record=target_record,
                        af2_model_preset_requested=request.af2_model_preset,
                    )
                    bioemu_target_gate_reference_pdb_text = _preprocess_pdb_text(
                        bioemu_target_gate_source_pdb_text,
                        chains=bioemu_target_gate_design_chains,
                        strip_nonpositive_resseq=effective_strip_nonpositive,
                        renumber_resseq_from_1=effective_renumber,
                    )
                    bioemu_target_gate_reference_hash = (
                        _sha256_text(bioemu_target_gate_reference_pdb_text)
                        if bioemu_target_gate_reference_pdb_text.strip()
                        else None
                    )
                    bioemu_request_hash = _stable_payload_hash(
                        {
                            "sequence": bioemu_sequence,
                            "num_samples": bioemu_num_samples,
                            "batch_size_100": bioemu_batch_size_100,
                            "model_name": bioemu_model_name,
                            "filter_samples": bioemu_filter_samples,
                            "base_seed": bioemu_base_seed,
                            "steering_config_text": bioemu_steering_config_text,
                            "max_return_sample_pdbs": bioemu_max_return_structures,
                            "min_return_sample_pdbs": bioemu_max_return_structures
                            if bioemu_max_return_structures > 1
                            else 0,
                            "env": bioemu_env,
                            "return_pdb": True,
                            "return_sample_pdbs": True,
                            "target_rmsd_cutoff": bioemu_target_rmsd_cutoff,
                            "target_gate_design_chains": bioemu_target_gate_design_chains,
                            "target_gate_reference_sha256": bioemu_target_gate_reference_hash,
                            "max_attempted_structures": bioemu_max_attempted_structures,
                        }
                    )
                    raw_samples: list[dict[str, Any]] = []
                    raw_sample_ids: set[str] = set()
                    attempts: list[dict[str, Any]] = []
                    bioemu_target_gate_summary: dict[str, Any] | None = None

                    def _parse_bioemu_samples_from_payload(
                        payload: dict[str, Any],
                        *,
                        attempt_label: str,
                    ) -> list[dict[str, Any]]:
                        parsed_samples: list[dict[str, Any]] = []
                        payload_samples = payload.get("sample_pdbs")
                        if isinstance(payload_samples, list):
                            for i, sample in enumerate(payload_samples):
                                if not isinstance(sample, dict):
                                    continue
                                sample_id = str(sample.get("id") or f"bioemu_{i:03d}")
                                pdb_text = str(
                                    sample.get("pdb") or sample.get("pdb_text") or ""
                                )
                                if not pdb_text.strip():
                                    continue
                                parsed_samples.append(
                                    {
                                        "id": sample_id,
                                        "pdb_text": pdb_text,
                                        "source": "bioemu",
                                        "frame_index": sample.get("frame_index"),
                                    }
                                )
                        if not parsed_samples:
                            topology_pdb = str(payload.get("topology_pdb") or "")
                            if topology_pdb.strip():
                                parsed_samples.append(
                                    {
                                        "id": "bioemu_topology",
                                        "pdb_text": topology_pdb,
                                        "source": "bioemu",
                                        "frame_index": None,
                                    }
                                )
                        if not parsed_samples:
                            raise RuntimeError(
                                "BioEmu output missing sample_pdbs/topology_pdb"
                            )
                        return _bioemu_uniquify_sample_records(
                            parsed_samples,
                            label=attempt_label,
                            existing_ids=raw_sample_ids,
                        )

                    def _persist_bioemu_sample_sets(
                        raw_sample_records: list[dict[str, Any]] | None,
                        final_backbones: list[dict[str, Any]] | None,
                    ) -> None:
                        write_json(raw_samples_path, raw_sample_records or [])
                        _write_named_pdb_records(
                            raw_samples_dir,
                            raw_sample_records,
                            pdb_keys=("pdb_text", "pdb"),
                        )
                        write_json(
                            sample_pdbs_path,
                            {
                                "samples": [
                                    {
                                        "id": str(item.get("id") or ""),
                                        "frame_index": item.get("frame_index"),
                                        "target_rmsd": item.get("target_rmsd"),
                                    }
                                    for item in (final_backbones or [])
                                    if isinstance(item, dict)
                                ]
                            },
                        )
                        _write_named_pdb_records(
                            designs_dir, final_backbones, pdb_keys=("pdb_text", "pdb")
                        )

                    def _build_bioemu_debug_summary(
                        *,
                        raw_sample_records: list[dict[str, Any]],
                        target_gate_summary: dict[str, Any] | None,
                        attempts: list[dict[str, Any]],
                        retry_performed: bool,
                        retry_attempt_count: int,
                        cache_hit: bool,
                    ) -> dict[str, Any]:
                        accepted_count = (
                            int(target_gate_summary.get("accepted_count") or 0)
                            if isinstance(target_gate_summary, dict)
                            else len(raw_sample_records)
                        )
                        rejected_count = (
                            int(target_gate_summary.get("rejected_count") or 0)
                            if isinstance(target_gate_summary, dict)
                            else 0
                        )
                        return {
                            "requested_count": bioemu_max_return_structures,
                            "max_attempted_structures": bioemu_max_attempted_structures,
                            "raw_count": len(raw_sample_records),
                            "final_accepted_count": accepted_count,
                            "off_target_reject_count": rejected_count,
                            "target_rmsd_cutoff": bioemu_target_rmsd_cutoff,
                            "target_rmsd_gate_applied": bool(
                                isinstance(target_gate_summary, dict)
                                and target_gate_summary.get("applied")
                            ),
                            "target_rmsd_contract_error": _bioemu_target_gate_message(
                                requested_count=bioemu_max_return_structures,
                                accepted_count=accepted_count,
                                rejected_count=rejected_count,
                                cutoff=bioemu_target_rmsd_cutoff,
                            ),
                            "retry_performed": retry_performed,
                            "retry_attempt_count": retry_attempt_count,
                            "cache_hit": cache_hit,
                            "attempts": attempts,
                        }

                    def _refresh_bioemu_final_backbones() -> dict[str, Any]:
                        nonlocal \
                            bioemu_backbones, \
                            bioemu_observed_count, \
                            bioemu_target_gate_summary
                        bioemu_observed_count = len(raw_samples)
                        accepted_backbones, bioemu_target_gate_summary = (
                            _filter_backbones_by_target_rmsd(
                                raw_samples,
                                reference_pdb_text=bioemu_target_gate_reference_pdb_text,
                                chains=bioemu_target_gate_design_chains,
                                cutoff=bioemu_target_rmsd_cutoff,
                                source="bioemu",
                                strip_nonpositive_resseq=effective_strip_nonpositive,
                                renumber_resseq_from_1=effective_renumber,
                                use_dssp_non_loop=bool(
                                    request.backbone_filter_use_dssp
                                ),
                            )
                        )
                        if bioemu_target_gate_summary is not None:
                            write_json(
                                target_gate_summary_path, bioemu_target_gate_summary
                            )
                        bioemu_backbones = list(accepted_backbones or [])
                        return {
                            "accepted_count": len(bioemu_backbones),
                            "off_target_reject_count": (
                                int(
                                    bioemu_target_gate_summary.get("rejected_count")
                                    or 0
                                )
                                if isinstance(bioemu_target_gate_summary, dict)
                                else 0
                            ),
                        }

                    def _read_bioemu_attempt_job_id(
                        attempt_label: str, *, primary_attempt: bool
                    ) -> str | None:
                        meta_path = (
                            runpod_job_path
                            if primary_attempt
                            else runpod_jobs_dir / f"{attempt_label}.json"
                        )
                        try:
                            meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        except Exception:
                            meta = {}
                        if not isinstance(meta, dict):
                            return None
                        job_id = str(meta.get("job_id") or "").strip()
                        return job_id or None

                    def _load_cached_bioemu_outputs() -> bool:
                        nonlocal \
                            bioemu_backbones, \
                            bioemu_observed_count, \
                            raw_samples, \
                            raw_sample_ids, \
                            attempts, \
                            bioemu_target_gate_summary
                        if request.force:
                            return False
                        if (
                            not sample_pdbs_path.exists()
                            and not raw_samples_path.exists()
                            and not output_path.exists()
                        ):
                            return False

                        cached_hash = ""
                        if cache_meta_path.exists():
                            try:
                                cache_meta = json.loads(
                                    cache_meta_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                cache_meta = None
                            if isinstance(cache_meta, dict):
                                cached_hash = str(
                                    cache_meta.get("request_hash") or ""
                                ).strip()
                        if not cached_hash and runpod_job_path.exists():
                            try:
                                meta = json.loads(
                                    runpod_job_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                meta = None
                            if isinstance(meta, dict):
                                cached_hash = str(
                                    meta.get("request_hash") or ""
                                ).strip()
                        if cached_hash and cached_hash != bioemu_request_hash:
                            return False

                        cached_samples: list[dict[str, Any]] = []
                        if raw_samples_path.exists():
                            try:
                                raw_cached = json.loads(
                                    raw_samples_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                raw_cached = None
                            if isinstance(raw_cached, list):
                                for i, sample in enumerate(raw_cached):
                                    if not isinstance(sample, dict):
                                        continue
                                    sample_id = str(
                                        sample.get("id") or f"bioemu_cached_{i:03d}"
                                    )
                                    pdb_text = str(
                                        sample.get("pdb_text")
                                        or sample.get("pdb")
                                        or ""
                                    )
                                    if not pdb_text.strip():
                                        continue
                                    cached_samples.append(
                                        {
                                            "id": sample_id,
                                            "pdb_text": pdb_text,
                                            "source": "bioemu",
                                            "frame_index": sample.get("frame_index"),
                                            "target_rmsd": sample.get("target_rmsd"),
                                            "debug_attempt": sample.get(
                                                "debug_attempt"
                                            ),
                                            "upstream_id": sample.get("upstream_id"),
                                        }
                                    )

                        if not cached_samples and sample_pdbs_path.exists():
                            try:
                                sample_meta = json.loads(
                                    sample_pdbs_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                sample_meta = None
                            entries = (
                                sample_meta.get("samples")
                                if isinstance(sample_meta, dict)
                                else None
                            )
                            if isinstance(entries, list):
                                for i, entry in enumerate(entries):
                                    if not isinstance(entry, dict):
                                        continue
                                    sample_id = str(
                                        entry.get("id") or f"bioemu_{i:03d}"
                                    )
                                    pdb_path = (
                                        designs_dir / f"{_safe_id(sample_id)}.pdb"
                                    )
                                    if not pdb_path.exists():
                                        continue
                                    try:
                                        pdb_text = pdb_path.read_text(encoding="utf-8")
                                    except Exception:
                                        continue
                                    if not pdb_text.strip():
                                        continue
                                    cached_samples.append(
                                        {
                                            "id": sample_id,
                                            "pdb_text": pdb_text,
                                            "source": "bioemu",
                                            "frame_index": entry.get("frame_index"),
                                            "target_rmsd": entry.get("target_rmsd"),
                                        }
                                    )

                        if not cached_samples and output_path.exists():
                            try:
                                output_payload = json.loads(
                                    output_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                output_payload = None
                            if isinstance(output_payload, dict):
                                try:
                                    cached_samples = _parse_bioemu_samples_from_payload(
                                        output_payload,
                                        attempt_label="cached",
                                    )
                                except RuntimeError:
                                    cached_samples = []

                        if not cached_samples:
                            return False

                        raw_samples = list(cached_samples)
                        raw_sample_ids = {
                            str(item.get("id") or "").strip()
                            for item in raw_samples
                            if isinstance(item, dict)
                            and str(item.get("id") or "").strip()
                        }
                        existing_debug: dict[str, Any] = {}
                        if debug_summary_path.exists():
                            try:
                                debug_raw = json.loads(
                                    debug_summary_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                debug_raw = None
                            if isinstance(debug_raw, dict):
                                existing_debug = dict(debug_raw)
                        attempts = (
                            list(existing_debug.get("attempts"))
                            if isinstance(existing_debug.get("attempts"), list)
                            else []
                        )
                        refresh_state = _refresh_bioemu_final_backbones()
                        retry_performed = bool(existing_debug.get("retry_performed"))
                        retry_attempt_count = int(
                            existing_debug.get("retry_attempt_count") or 0
                        )
                        debug_summary = _build_bioemu_debug_summary(
                            raw_sample_records=raw_samples,
                            target_gate_summary=bioemu_target_gate_summary,
                            attempts=attempts,
                            retry_performed=retry_performed,
                            retry_attempt_count=retry_attempt_count,
                            cache_hit=True,
                        )
                        write_json(debug_summary_path, debug_summary)
                        _persist_bioemu_sample_sets(raw_samples, bioemu_backbones)
                        accepted_count = int(refresh_state.get("accepted_count") or 0)
                        if accepted_count < bioemu_max_return_structures:
                            if len(raw_samples) < bioemu_max_attempted_structures:
                                return False
                            target_gate_message = str(
                                debug_summary.get("target_rmsd_contract_error") or ""
                            ).strip()
                            raise BackboneContractError(
                                target_gate_message or "BioEmu target RMSD gate failed"
                            )
                        set_status(
                            paths,
                            stage="bioemu",
                            state="completed",
                            detail=f"cached structures={len(bioemu_backbones or [])}",
                        )
                        return True

                    if _load_cached_bioemu_outputs():
                        pass
                    else:
                        resume_job_id: str | None = None
                        if runpod_job_path.exists() and not request.force:
                            try:
                                meta = json.loads(
                                    runpod_job_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                meta = {}
                            job_id = (
                                str(meta.get("job_id") or "").strip()
                                if isinstance(meta, dict)
                                else ""
                            )
                            if job_id and isinstance(meta, dict):
                                same_request = _runpod_meta_matches(
                                    meta,
                                    {
                                        "request_hash": bioemu_request_hash,
                                        "num_samples": bioemu_num_samples,
                                        "batch_size_100": bioemu_batch_size_100,
                                        "model_name": bioemu_model_name,
                                        "filter_samples": bioemu_filter_samples,
                                        "base_seed": bioemu_base_seed,
                                        "steering_config_text": bioemu_steering_config_text,
                                        "max_return_structures": bioemu_max_return_structures,
                                        "min_return_sample_pdbs": bioemu_max_return_structures
                                        if bioemu_max_return_structures > 1
                                        else 0,
                                        "target_rmsd_cutoff": bioemu_target_rmsd_cutoff,
                                        "max_attempted_structures": bioemu_max_attempted_structures,
                                    },
                                )
                                if same_request:
                                    resume_job_id = job_id

                        def _call_bioemu_sample(
                            *,
                            requested_return_count: int,
                            attempt_label: str,
                            resume_job: str | None = None,
                            primary_attempt: bool = False,
                        ) -> tuple[dict[str, Any], int, int | None]:
                            attempt_num_samples = _bioemu_attempt_num_samples(
                                requested_return_count,
                                configured_num_samples=bioemu_num_samples,
                                configured_return_count=bioemu_max_return_structures,
                            )
                            attempt_base_seed = (
                                bioemu_base_seed + len(attempts)
                                if bioemu_base_seed is not None
                                else None
                            )

                            def _on_bioemu_job_id(job_id: str) -> None:
                                meta_path = (
                                    runpod_job_path
                                    if primary_attempt
                                    else runpod_jobs_dir / f"{attempt_label}.json"
                                )
                                write_json(
                                    meta_path,
                                    {
                                        "job_id": job_id,
                                        "request_hash": bioemu_request_hash,
                                        "attempt_label": attempt_label,
                                        "num_samples": attempt_num_samples,
                                        "batch_size_100": bioemu_batch_size_100,
                                        "model_name": bioemu_model_name,
                                        "filter_samples": bioemu_filter_samples,
                                        "base_seed": attempt_base_seed,
                                        "steering_config_text": bioemu_steering_config_text,
                                        "max_return_structures": requested_return_count,
                                        "min_return_sample_pdbs": requested_return_count
                                        if requested_return_count > 1
                                        else 0,
                                        "target_rmsd_cutoff": bioemu_target_rmsd_cutoff,
                                        "max_attempted_structures": bioemu_max_attempted_structures,
                                    },
                                )
                                set_status(
                                    paths,
                                    stage="bioemu",
                                    state="running",
                                    detail=f"runpod_job_id={job_id}",
                                )

                            try:
                                bioemu_out = self.bioemu.sample(
                                    sequence=bioemu_sequence,
                                    num_samples=attempt_num_samples,
                                    batch_size_100=bioemu_batch_size_100,
                                    model_name=bioemu_model_name,
                                    filter_samples=bioemu_filter_samples,
                                    base_seed=attempt_base_seed,
                                    steering_config_text=bioemu_steering_config_text,
                                    env=bioemu_env,
                                    return_pdb=True,
                                    return_sample_pdbs=True,
                                    max_return_sample_pdbs=requested_return_count,
                                    min_return_sample_pdbs=(
                                        requested_return_count
                                        if requested_return_count > 1
                                        else 0
                                    ),
                                    resume_job_id=resume_job,
                                    on_job_id=_on_bioemu_job_id,
                                )
                            except TypeError as exc:
                                if "resume_job_id" not in str(exc):
                                    raise
                                bioemu_out = self.bioemu.sample(
                                    sequence=bioemu_sequence,
                                    num_samples=attempt_num_samples,
                                    batch_size_100=bioemu_batch_size_100,
                                    model_name=bioemu_model_name,
                                    filter_samples=bioemu_filter_samples,
                                    base_seed=attempt_base_seed,
                                    steering_config_text=bioemu_steering_config_text,
                                    env=bioemu_env,
                                    return_pdb=True,
                                    return_sample_pdbs=True,
                                    max_return_sample_pdbs=requested_return_count,
                                    min_return_sample_pdbs=(
                                        requested_return_count
                                        if requested_return_count > 1
                                        else 0
                                    ),
                                    on_job_id=_on_bioemu_job_id,
                                )
                            return bioemu_out, attempt_num_samples, attempt_base_seed

                        def _ingest_bioemu_output(
                            bioemu_out: dict[str, Any],
                            *,
                            attempt_label: str,
                            requested_return_count: int,
                            requested_num_samples: int,
                            attempt_base_seed: int | None,
                            primary_attempt: bool,
                            job_id: str | None = None,
                        ) -> None:
                            output_target = (
                                output_path
                                if primary_attempt
                                else runpod_jobs_dir / f"{attempt_label}_output.json"
                            )
                            write_json(output_target, _safe_json(bioemu_out))
                            parsed_samples = _parse_bioemu_samples_from_payload(
                                bioemu_out,
                                attempt_label=attempt_label,
                            )
                            missing_sample_pdbs = _bioemu_missing_sample_pdb_message(
                                requested_count=requested_return_count,
                                observed_count=len(parsed_samples),
                                materialized_count=len(parsed_samples),
                            )
                            if missing_sample_pdbs:
                                raise BackboneContractError(missing_sample_pdbs)
                            raw_samples.extend(parsed_samples)
                            raw_sample_ids.update(
                                str(item.get("id") or "").strip()
                                for item in parsed_samples
                                if isinstance(item, dict)
                                and str(item.get("id") or "").strip()
                            )
                            attempts.append(
                                {
                                    "label": attempt_label,
                                    "requested_structures": requested_return_count,
                                    "requested_num_samples": requested_num_samples,
                                    "returned_structures": len(parsed_samples),
                                    "base_seed": attempt_base_seed,
                                    "job_id": job_id,
                                }
                            )

                        out, requested_num_samples, attempt_base_seed = (
                            _call_bioemu_sample(
                                requested_return_count=bioemu_max_return_structures,
                                attempt_label="batch",
                                resume_job=resume_job_id,
                                primary_attempt=True,
                            )
                        )
                        _ingest_bioemu_output(
                            out,
                            attempt_label="batch",
                            requested_return_count=bioemu_max_return_structures,
                            requested_num_samples=requested_num_samples,
                            attempt_base_seed=attempt_base_seed,
                            primary_attempt=True,
                            job_id=_read_bioemu_attempt_job_id(
                                "batch", primary_attempt=True
                            ),
                        )

                        refresh_state = _refresh_bioemu_final_backbones()
                        retry_performed = False
                        retry_attempt_count = 0
                        retry_index = 0
                        while (
                            int(refresh_state.get("accepted_count") or 0)
                            < bioemu_max_return_structures
                        ):
                            remaining_budget = max(
                                0, bioemu_max_attempted_structures - len(raw_samples)
                            )
                            if remaining_budget <= 0:
                                break
                            accepted_deficit = max(
                                0,
                                bioemu_max_return_structures
                                - int(refresh_state.get("accepted_count") or 0),
                            )
                            requested_retry_structures = max(
                                1, min(accepted_deficit, remaining_budget)
                            )
                            retry_index += 1
                            attempt_label = f"retry_{retry_index}"
                            out, requested_num_samples, attempt_base_seed = (
                                _call_bioemu_sample(
                                    requested_return_count=requested_retry_structures,
                                    attempt_label=attempt_label,
                                    primary_attempt=False,
                                )
                            )
                            _ingest_bioemu_output(
                                out,
                                attempt_label=attempt_label,
                                requested_return_count=requested_retry_structures,
                                requested_num_samples=requested_num_samples,
                                attempt_base_seed=attempt_base_seed,
                                primary_attempt=False,
                                job_id=_read_bioemu_attempt_job_id(
                                    attempt_label, primary_attempt=False
                                ),
                            )
                            retry_performed = True
                            retry_attempt_count += 1
                            refresh_state = _refresh_bioemu_final_backbones()

                        _persist_bioemu_sample_sets(raw_samples, bioemu_backbones)
                        debug_summary = _build_bioemu_debug_summary(
                            raw_sample_records=raw_samples,
                            target_gate_summary=bioemu_target_gate_summary,
                            attempts=attempts,
                            retry_performed=retry_performed,
                            retry_attempt_count=retry_attempt_count,
                            cache_hit=False,
                        )
                        write_json(debug_summary_path, debug_summary)
                        write_json(
                            cache_meta_path,
                            {
                                "request_hash": bioemu_request_hash,
                                "num_samples": bioemu_num_samples,
                                "batch_size_100": bioemu_batch_size_100,
                                "model_name": bioemu_model_name,
                                "filter_samples": bioemu_filter_samples,
                                "base_seed": bioemu_base_seed,
                                "steering_config_text": bioemu_steering_config_text,
                                "max_return_structures": bioemu_max_return_structures,
                                "target_rmsd_cutoff": bioemu_target_rmsd_cutoff,
                                "target_gate_design_chains": bioemu_target_gate_design_chains,
                                "target_gate_reference_sha256": bioemu_target_gate_reference_hash,
                                "max_attempted_structures": bioemu_max_attempted_structures,
                                "source": "bioemu",
                            },
                        )
                        if (
                            int(refresh_state.get("accepted_count") or 0)
                            < bioemu_max_return_structures
                        ):
                            target_gate_message = str(
                                debug_summary.get("target_rmsd_contract_error") or ""
                            ).strip()
                            raise BackboneContractError(
                                target_gate_message or "BioEmu target RMSD gate failed"
                            )
                        set_status(
                            paths,
                            stage="bioemu",
                            state="completed",
                            detail=f"structures={len(bioemu_backbones or [])}",
                        )

                if request.stop_after == "bioemu":
                    result = PipelineResult(
                        run_id=run_id,
                        output_dir=str(paths.root),
                        msa_a3m_path=msa_a3m_path,
                        msa_filtered_a3m_path=msa_filtered_a3m_path,
                        msa_tsv_path=msa_tsv_path,
                        conservation_path=conservation_path,
                        ligand_mask_path=None,
                        surface_mask_path=None,
                        tiers=[],
                        errors=[],
                    )
                    write_json(paths.summary_json, asdict(result))
                    set_status(paths, stage="done", state="completed")
                    return result

            if request.dry_run and not target_pdb_text.strip():
                if target_record is None:
                    raise ValueError("target_record is required for dry_run")
                target_pdb_text = _dummy_backbone_pdb(
                    target_record.sequence, chain_id="A"
                )

            if not target_pdb_text.strip():

                def _run_af2_target() -> None:
                    nonlocal target_pdb_text
                    set_status(paths, stage="af2_target", state="running")
                    target_pdb_path = paths.root / "target.pdb"
                    if target_pdb_path.exists() and not request.force:
                        target_pdb_text = target_pdb_path.read_text(encoding="utf-8")
                        set_status(
                            paths,
                            stage="af2_target",
                            state="completed",
                            detail="cached",
                        )
                        return

                    if af2_client is None:
                        raise RuntimeError(
                            f"target_pdb is missing; provide target_pdb or configure {af2_provider_label} ({af2_provider_hint})"
                        )
                    if target_record is None:
                        raise ValueError(
                            f"target_fasta is required to predict target_pdb via {af2_provider_label}"
                        )

                    jobs_path = paths.root / "af2_target_runpod_job.json"

                    def _on_target_job_id(seq_id: str, job_id: str) -> None:
                        payload: dict[str, object] = {
                            "seq_id": seq_id,
                            "job_id": job_id,
                            "provider": af2_provider,
                        }
                        if af2_endpoint_id:
                            payload["endpoint_id"] = af2_endpoint_id
                        write_json(jobs_path, payload)
                        set_status(
                            paths,
                            stage="af2_target",
                            state="running",
                            detail=f"runpod_job_id={job_id}",
                        )

                    target_seq = target_record.sequence
                    target_seqrec = SequenceRecord(
                        id="target",
                        sequence=target_seq,
                        header=target_record.header,
                        meta={},
                    )
                    target_af2_preset = _resolve_af2_model_preset(
                        request.af2_model_preset,
                        chain_count=len(_split_multichain_sequence(target_seq)),
                    )
                    target_af2_input = SequenceRecord(
                        id="target",
                        header=target_seqrec.header,
                        sequence=_prepare_af2_sequence(
                            target_seqrec.sequence,
                            model_preset=target_af2_preset,
                            chain_ids=None,
                        ),
                        meta=target_seqrec.meta,
                    )
                    try:
                        af2_out = af2_client.predict(
                            [target_af2_input],
                            model_preset=target_af2_preset,
                            db_preset=request.af2_db_preset,
                            max_template_date=request.af2_max_template_date,
                            extra_flags=request.af2_extra_flags,
                            on_job_id=_on_target_job_id,
                        )
                    except TypeError:
                        af2_out = af2_client.predict(
                            [target_af2_input],
                            model_preset=target_af2_preset,
                            db_preset=request.af2_db_preset,
                            max_template_date=request.af2_max_template_date,
                            extra_flags=request.af2_extra_flags,
                        )

                    rec = af2_out.get("target") if isinstance(af2_out, dict) else None
                    if not isinstance(rec, dict):
                        raise RuntimeError(
                            f"{af2_provider_label} did not return a record for target: {type(rec).__name__}"
                        )
                    ranked0 = (
                        rec.get("ranked_0_pdb") or rec.get("pdb") or rec.get("pdb_text")
                    )
                    if not isinstance(ranked0, str) or not ranked0.strip():
                        raise RuntimeError(
                            f"{af2_provider_label} did not return ranked_0_pdb for target sequence"
                        )

                    target_pdb_text = ranked0
                    _write_text(target_pdb_path, target_pdb_text)
                    if isinstance(rec.get("ranking_debug"), dict):
                        write_json(
                            paths.root / "af2_target_ranking_debug.json",
                            rec["ranking_debug"],
                        )
                    write_json(
                        paths.root / "af2_target_metrics.json",
                        {
                            "best_plddt": rec.get("best_plddt"),
                            "best_model": rec.get("best_model"),
                            "provider": af2_provider,
                        },
                    )
                    set_status(paths, stage="af2_target", state="completed")

                def _fallback_af2_target(exc: Exception) -> None:
                    nonlocal target_pdb_text
                    if target_record is not None:
                        target_pdb_text = _dummy_backbone_pdb(
                            target_record.sequence, chain_id="A"
                        )
                    else:
                        target_pdb_text = _dummy_backbone_pdb("A" * 60, chain_id="A")
                    _write_text(paths.root / "target.pdb", target_pdb_text)
                    write_json(
                        paths.root / "af2_target_recovery.json",
                        {
                            "error": str(exc),
                            "recovered_at": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.gmtime()
                            ),
                        },
                    )
                    set_status(
                        paths, stage="af2_target", state="completed", detail="recovered"
                    )

                _, af2t_recovered, af2t_error, af2t_recovery = _recover_stage(
                    "af2_target",
                    _run_af2_target,
                    fallback=_fallback_af2_target,
                    recovery_actions=["Used dummy backbone for target structure"],
                )
                _emit_panel(
                    "af2_target",
                    detail=("recovered" if af2t_recovered else None),
                    error=af2t_error,
                    recovery=af2t_recovery,
                )

            if msa_defer:
                if target_record is None:
                    target_record = _target_record_from_pdb(
                        target_pdb_text, design_chains=request.design_chains
                    )
                filtered_a3m_text, msa_recovered, msa_error, msa_recovery = (
                    _recover_stage(
                        "mmseqs_msa",
                        lambda: _run_msa(target_record),
                        fallback=lambda exc: _fallback_msa(
                            target_record, reason=str(exc)
                        ),
                        recovery_actions=["Used fallback MSA (query-only)"],
                    )
                )
                _emit_panel(
                    "mmseqs_msa",
                    detail=("recovered" if msa_recovered else None),
                    error=msa_error,
                    recovery=msa_recovery,
                )
                if request.stop_after == "msa":
                    result = PipelineResult(
                        run_id=run_id,
                        output_dir=str(paths.root),
                        msa_a3m_path=msa_a3m_path,
                        msa_filtered_a3m_path=msa_filtered_a3m_path,
                        msa_tsv_path=msa_tsv_path,
                        conservation_path=None,
                        ligand_mask_path=None,
                        surface_mask_path=None,
                        tiers=[],
                        errors=errors,
                    )
                    write_json(paths.summary_json, asdict(result))
                    set_status(paths, stage="done", state="completed")
                    return result
                conservation, cons_recovered, cons_error, cons_recovery = (
                    _recover_stage(
                        "conservation",
                        lambda: _run_conservation(filtered_a3m_text),
                        fallback=lambda exc: _fallback_conservation(
                            filtered_a3m_text, reason=str(exc)
                        ),
                        recovery_actions=["Used fallback conservation (no weighting)"],
                    )
                )
                _emit_panel(
                    "conservation",
                    detail=("recovered" if cons_recovered else None),
                    error=cons_error,
                    recovery=cons_recovery,
                )

            if conservation is None:
                raise ValueError("conservation is required before ligand masking")

            set_status(paths, stage="ligand_mask", state="running")

            backbones: list[dict[str, Any]] = []
            if rfd3_backbones:
                backbones.extend(
                    {
                        **dict(item),
                        "source": str(item.get("source") or "rfd3"),
                    }
                    for item in rfd3_backbones
                    if isinstance(item, dict)
                )
            elif target_pdb_text.strip():
                backbones.append(
                    {
                        "id": (rfd3_selected_id or "target"),
                        "pdb_text": target_pdb_text,
                        "source": ("rfd3" if rfd3_selected_id else "target"),
                    }
                )

            if bioemu_backbones:
                backbones.extend(
                    {
                        **dict(item),
                        "source": str(item.get("source") or "bioemu"),
                    }
                    for item in bioemu_backbones
                    if isinstance(item, dict)
                )

            if rfd3_selected_id:
                for idx, b in enumerate(backbones):
                    if str(b.get("id") or "") == str(rfd3_selected_id):
                        if idx != 0:
                            backbones.insert(0, backbones.pop(idx))
                        break

            if backbones and (effective_strip_nonpositive or effective_renumber):

                def _run_preprocess() -> None:
                    set_status(paths, stage="pdb_preprocess", state="running")
                    backbones_dir = _ensure_dir(paths.root / "backbones")
                    preprocess_notes: list[str] = []
                    for idx, b in enumerate(backbones):
                        original = str(b.get("pdb_text") or "")
                        if not original.strip():
                            continue
                        bb_strip_nonpositive, bb_renumber, bb_detail = (
                            _resolve_backbone_preprocess_options(
                                pdb_text=original,
                                source=b.get("source"),
                                strip_nonpositive_resseq=effective_strip_nonpositive,
                                renumber_resseq_from_1=effective_renumber,
                            )
                        )
                        processed, numbering = preprocess_pdb(
                            original,
                            chains=request.design_chains,
                            strip_nonpositive_resseq=bb_strip_nonpositive,
                            renumber_resseq_from_1=bb_renumber,
                        )
                        b["pdb_text"] = processed
                        bb_id = (
                            _safe_id(str(b.get("id") or f"backbone_{idx}"))
                            or f"backbone_{idx}"
                        )
                        _sync_processed_source_pdb_artifacts(
                            run_root=paths.root,
                            backbone_id=str(b.get("id") or ""),
                            backbone_safe_id=bb_id,
                            source=b.get("source"),
                            processed_pdb_text=processed,
                            rfd3_selected_id=rfd3_selected_id,
                        )
                        bb_dir = _ensure_dir(backbones_dir / bb_id)
                        _write_text(bb_dir / "target.original.pdb", original)
                        numbering_payload = {
                            "chains": request.design_chains,
                            "strip_nonpositive_resseq": bb_strip_nonpositive,
                            "renumber_resseq_from_1": bb_renumber,
                            "mapping": numbering,
                            "source": str(b.get("source") or "unknown"),
                        }
                        if bb_detail:
                            numbering_payload["detail"] = bb_detail
                            preprocess_notes.append(f"{bb_id}:{bb_detail}")
                        write_json(
                            bb_dir / "pdb_numbering.json",
                            numbering_payload,
                        )
                        if idx == 0:
                            _write_text(paths.root / "target.original.pdb", original)
                            write_json(
                                paths.root / "pdb_numbering.json",
                                numbering_payload,
                            )
                    set_status(
                        paths,
                        stage="pdb_preprocess",
                        state="completed",
                        detail=(
                            "; ".join(preprocess_notes)[:500]
                            if preprocess_notes
                            else None
                        ),
                    )

                def _fallback_preprocess(exc: Exception) -> None:
                    write_json(
                        paths.root / "pdb_preprocess_recovery.json",
                        {
                            "error": str(exc),
                            "recovered_at": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.gmtime()
                            ),
                        },
                    )
                    set_status(
                        paths,
                        stage="pdb_preprocess",
                        state="completed",
                        detail="recovered",
                    )

                _, prep_recovered, prep_error, prep_recovery = _recover_stage(
                    "pdb_preprocess",
                    _run_preprocess,
                    fallback=_fallback_preprocess,
                    recovery_actions=["Skipped PDB preprocessing"],
                )
                _emit_panel(
                    "pdb_preprocess",
                    detail=("recovered" if prep_recovered else None),
                    error=prep_error,
                    recovery=prep_recovery,
                )

            if backbones:
                target_pdb_text = str(backbones[0].get("pdb_text") or "")
            if target_pdb_text.strip():
                _write_text(paths.root / "target.pdb", target_pdb_text)

            backbones_dir = _ensure_dir(paths.root / "backbones")
            backbone_contexts: list[dict[str, Any]] = []
            backbone_entries: list[dict[str, Any]] = []
            source_rank_by_key: dict[str, int] = {}
            for idx, b in enumerate(backbones):
                raw_id = str(b.get("id") or f"backbone_{idx}")
                dir_id = _safe_id(raw_id) or f"backbone_{idx}"
                bb_dir = _ensure_dir(backbones_dir / dir_id)
                pdb_text = str(b.get("pdb_text") or "")
                if pdb_text.strip():
                    _write_text(bb_dir / "target.pdb", pdb_text)
                source_key = _backbone_origin_stage(b.get("source"))
                source_rank_by_key[source_key] = (
                    int(source_rank_by_key.get(source_key) or 0) + 1
                )
                source_rank = int(source_rank_by_key[source_key] or 0)
                frame_index = b.get("frame_index")
                selected = bool(
                    source_key == "rfd3"
                    and rfd3_selected_id
                    and raw_id == rfd3_selected_id
                )
                materialized = bool(pdb_text.strip())
                ctx = {
                    "id": raw_id,
                    "dir": bb_dir,
                    "pdb_text": pdb_text,
                    "score": b.get("score"),
                    "source": str(b.get("source") or "unknown"),
                    "rank": source_rank,
                    "frame_index": frame_index,
                    "selected": selected,
                    "materialized": materialized,
                }
                backbone_contexts.append(ctx)
                backbone_entries.append(
                    {
                        "id": raw_id,
                        "dir": str(bb_dir),
                        "pdb_path": str(bb_dir / "target.pdb"),
                        "score": b.get("score"),
                        "source": str(b.get("source") or "unknown"),
                        "primary": idx == 0,
                        "selected": selected,
                        "propagated": True,
                        "materialized": materialized,
                        "rank": source_rank,
                        "frame_index": frame_index,
                        "origin_stage": source_key,
                        "origin_artifact": _backbone_origin_artifact(
                            source_key, raw_id, rfd3_selected_id
                        ),
                    }
                )
            backbone_pdb_by_id = {
                str(ctx.get("id") or ""): str(ctx.get("pdb_text") or "")
                for ctx in backbone_contexts
                if str(ctx.get("id") or "").strip()
            }
            source_summaries, propagation_mode = _build_backbone_source_summaries(
                request,
                backbone_entries=backbone_entries,
                observed_counts={
                    "rfd3": rfd3_observed_count,
                    "bioemu": bioemu_observed_count,
                },
                selected_ids={"rfd3": rfd3_selected_id},
                diversity_summaries=(
                    {"rfd3": rfd3_diversity_summary} if rfd3_diversity_summary else None
                ),
            )
            write_json(
                paths.root / "backbones.json",
                {
                    "propagation_mode": propagation_mode,
                    "sources": source_summaries,
                    "backbones": backbone_entries,
                },
            )

            (
                pdb_chains,
                requested_chains,
                auto_design_chains,
                design_chains,
                chain_note,
                af2_model_preset,
            ) = _resolve_pipeline_chain_strategy(
                pdb_text=target_pdb_text,
                request_design_chains=request.design_chains,
                target_fasta_text=str(request.target_fasta or ""),
                target_record=target_record,
                af2_model_preset_requested=request.af2_model_preset,
            )

            write_json(
                paths.root / "chain_strategy.json",
                {
                    "af2_model_preset": af2_model_preset,
                    "pdb_chains": pdb_chains,
                    "requested_design_chains": request.design_chains,
                    "auto_selected_design_chains": auto_design_chains,
                    "design_chains_used": design_chains,
                    "note": chain_note,
                },
            )
            set_status(
                paths,
                stage="chain_strategy",
                state="completed",
                detail=(chain_note[:500] if chain_note else None),
            )
            wt_compare_reference_pdb_text = _wt_compare_reference_pdb_text(
                target_pdb_input_text,
                fallback_pdb_text=target_pdb_text,
                design_chains=None,
                strip_nonpositive_resseq=effective_strip_nonpositive,
                renumber_resseq_from_1=effective_renumber,
            )

            set_status(paths, stage="query_pdb_check", state="running")
            query_seq = _clean_protein_sequence(target_record.sequence)
            policy = _normalize_policy(request.query_pdb_policy)
            min_identity = float(request.query_pdb_min_identity)
            both_provided = bool(str(request.target_fasta or "").strip()) and bool(
                str(request.target_pdb or "").strip()
            )
            original_ligand_mask_by_chain: dict[str, list[int]] = {}
            original_ligand_mask_query_by_chain: dict[str, list[int]] = {}
            original_ligand_mask_source: str | None = None

            query_warnings: list[str] = []
            query_pdb_error: str | None = None
            for ctx in backbone_contexts:
                ctx_design_chains, ctx_chain_note = _resolve_backbone_design_chains(
                    pdb_text=ctx["pdb_text"],
                    preferred_chains=design_chains,
                    query_seq=query_seq,
                )
                ctx_available_chains = list(
                    residues_by_chain(ctx["pdb_text"], only_atom_records=True).keys()
                )
                ctx["available_chains"] = ctx_available_chains
                ctx["design_chains"] = list(ctx_design_chains)

                pdb_seq_by_chain = sequence_by_chain(
                    ctx["pdb_text"], chains=(ctx_design_chains or None)
                )
                query_to_pdb_map_by_chain: dict[str, list[int | None]] = {}
                query_pdb_report: dict[str, object] = {
                    "policy": policy,
                    "min_query_identity": min_identity,
                    "query_len": len(query_seq),
                    "backbone_id": ctx["id"],
                    "requested_design_chains": design_chains,
                    "available_chains": ctx_available_chains,
                    "design_chains_used": ctx_design_chains,
                    "design_chain_note": ctx_chain_note,
                    "chains": {},
                }
                problems: list[str] = []
                warnings: list[str] = []

                for chain_id in ctx_design_chains or sorted(pdb_seq_by_chain.keys()):
                    chain_seq_raw = pdb_seq_by_chain.get(chain_id, "")
                    chain_seq = _clean_protein_sequence(chain_seq_raw)
                    if not chain_seq:
                        problems.append(
                            f"chain {chain_id}: empty sequence extracted from target_pdb"
                        )
                        continue

                    aln = global_alignment_mapping(query_seq, chain_seq)
                    query_to_pdb_map_by_chain[chain_id] = aln.mapping_query_to_target

                    ok = aln.query_identity >= min_identity
                    exact_match = (
                        aln.query_len == aln.target_len
                        and aln.matches == aln.query_len
                        and aln.gaps_in_query == 0
                        and aln.gaps_in_target == 0
                    )
                    query_pdb_report["chains"][chain_id] = {
                        "query_len": aln.query_len,
                        "pdb_len": aln.target_len,
                        "aligned_pairs": aln.aligned_pairs,
                        "matches": aln.matches,
                        "mismatches": aln.mismatches,
                        "gaps_in_query": aln.gaps_in_query,
                        "gaps_in_pdb": aln.gaps_in_target,
                        "pairwise_identity": aln.pairwise_identity,
                        "query_identity": aln.query_identity,
                        "coverage_query": aln.coverage_query,
                        "coverage_pdb": aln.coverage_target,
                        "ok": ok,
                        "exact_match": exact_match,
                    }

                    if not ok:
                        problems.append(
                            f"chain {chain_id}: query_identity={aln.query_identity:.3f} < {min_identity:.3f} "
                            f"(query_len={aln.query_len} pdb_len={aln.target_len})"
                        )
                    elif both_provided and not exact_match:
                        warnings.append(
                            f"chain {chain_id}: FASTA vs PDB not exact match "
                            f"(mismatches={aln.mismatches} gaps_query={aln.gaps_in_query} gaps_pdb={aln.gaps_in_target} "
                            f"query_len={aln.query_len} pdb_len={aln.target_len})"
                        )

                if warnings:
                    query_pdb_report["warnings"] = warnings
                write_json(ctx["dir"] / "query_pdb_alignment.json", query_pdb_report)
                if ctx is backbone_contexts[0]:
                    write_json(
                        paths.root / "query_pdb_alignment.json", query_pdb_report
                    )

                if problems and policy == "error":
                    msg = (
                        "target_fasta/target_pdb mismatch (query_pdb_check failed): "
                        + f"backbone={ctx['id']} "
                        + "; ".join(problems)
                        + ". Fix: make sure target_fasta matches the selected PDB chain(s) "
                        "(design_chains), or omit target_fasta to derive the query from target_pdb, "
                        "or relax with query_pdb_policy='warn'/'ignore' and/or query_pdb_min_identity. "
                        "See query_pdb_alignment.json for details."
                    )
                    if request.auto_recover:
                        query_pdb_error = msg
                        errors.append(msg)
                        query_warnings.append(f"{ctx['id']}:" + "; ".join(problems))
                    else:
                        raise ValueError(msg)

                if problems and policy == "warn":
                    query_warnings.append(f"{ctx['id']}:" + "; ".join(problems))
                if warnings and policy != "ignore":
                    query_warnings.append(f"{ctx['id']}:" + "; ".join(warnings))
                if ctx_chain_note:
                    query_warnings.append(f"{ctx['id']}:{ctx_chain_note}")

                ctx["mapping"] = query_to_pdb_map_by_chain

            query_pdb_detail = (
                " | ".join(query_warnings)[:500] if query_warnings else None
            )
            if query_pdb_error:
                query_pdb_detail = (
                    f"recovered: {query_pdb_detail}"
                    if query_pdb_detail
                    else "recovered"
                )
            set_status(
                paths,
                stage="query_pdb_check",
                state="completed",
                detail=query_pdb_detail,
            )
            if query_pdb_error:
                _emit_panel(
                    "query_pdb_check",
                    detail="recovered",
                    error=query_pdb_error,
                    recovery={
                        "attempted": True,
                        "actions": ["Continued despite query/PDB mismatch"],
                    },
                )
            else:
                _emit_panel("query_pdb_check")

            if bool(request.ligand_mask_use_original_target):
                reference_pdb_text = ""
                if target_pdb_input_text.strip():
                    reference_pdb_text = target_pdb_input_text
                    original_ligand_mask_source = "target_pdb"
                elif rfd3_reference_pdb_text.strip():
                    reference_pdb_text = rfd3_reference_pdb_text
                    original_ligand_mask_source = "rfd3_input_pdb"
                if reference_pdb_text.strip():
                    (
                        original_ligand_mask_by_chain,
                        original_ligand_mask_query_by_chain,
                    ) = _map_reference_ligand_mask_to_query(
                        query_seq=query_seq,
                        reference_pdb_text=reference_pdb_text,
                        design_chains=design_chains,
                        ligand_mask_distance=request.ligand_mask_distance,
                        ligand_resnames=request.ligand_resnames,
                        ligand_atom_chains=request.ligand_atom_chains,
                    )

            write_json(
                paths.root / "ligand_mask_original_target.json",
                {
                    "enabled": bool(request.ligand_mask_use_original_target),
                    "source": original_ligand_mask_source,
                    "ligand_mask_by_chain": original_ligand_mask_by_chain,
                    "query_positions_by_chain": original_ligand_mask_query_by_chain,
                    "query_positions_total": sum(
                        len(v) for v in original_ligand_mask_query_by_chain.values()
                    ),
                },
            )

            def _compute_wt_baseline() -> None:
                if not request.wt_compare:
                    return
                wt_root = _ensure_dir(paths.root / "wt")
                metrics_path = wt_root / "metrics.json"
                set_status(paths, stage="wt_baseline", state="running")

                def _load_json_file(path: Path) -> dict[str, object] | None:
                    if not path.exists():
                        return None
                    try:
                        raw = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        return None
                    return raw if isinstance(raw, dict) else None

                cached_metrics = (
                    _load_json_file(metrics_path)
                    if metrics_path.exists() and not request.force
                    else None
                )
                cached_af2 = (
                    cached_metrics.get("af2")
                    if isinstance(cached_metrics, dict)
                    and isinstance(cached_metrics.get("af2"), dict)
                    else None
                )
                cached_relax = (
                    cached_metrics.get("relax")
                    if isinstance(cached_metrics, dict)
                    and isinstance(cached_metrics.get("relax"), dict)
                    else None
                )

                seq_source = (
                    "target_pdb"
                    if wt_compare_reference_pdb_text.strip()
                    else "target_fasta"
                )
                wt_seq = ""
                if wt_compare_reference_pdb_text.strip():
                    try:
                        seqs = sequence_by_chain(wt_compare_reference_pdb_text)
                        if seqs:
                            wt_seq = "/".join(seqs.values())
                    except Exception:
                        pass
                if not wt_seq and target_record:
                    wt_seq = target_record.sequence
                    seq_source = "target_fasta"

                wt_af2_model_preset = af2_model_preset
                cached_af2_ok = (
                    cached_af2 is not None
                    and not _should_retry_cached_wt_af2(cached_af2)
                    and (cached_af2.get("model_preset") in {None, wt_af2_model_preset})
                    and (cached_af2.get("db_preset") in {None, request.af2_db_preset})
                    and (
                        cached_af2.get("max_template_date")
                        in {None, request.af2_max_template_date}
                    )
                    and (cached_af2.get("provider") in {None, af2_provider})
                )
                cached_relax_ok = (not relax_enabled) or (
                    cached_relax is not None
                    and not _relax_payload_has_recovered_failure(cached_relax)
                    and cached_relax.get("nstruct")
                    in {None, max(1, int(getattr(request, "relax_nstruct", 1) or 1))}
                    and str(cached_relax.get("extra_flags") or "").strip()
                    == str(getattr(request, "relax_extra_flags", "") or "").strip()
                )
                if cached_metrics is not None and cached_af2_ok and cached_relax_ok:
                    set_status(
                        paths, stage="wt_baseline", state="completed", detail="cached"
                    )
                    return
                if _should_retry_cached_wt_af2(cached_af2):
                    _unlink_if_exists(wt_root / "af2" / "runpod_job.json")

                payload: dict[str, object] = {
                    "enabled": True,
                    "sequence_source": seq_source,
                    "sequence_length": len(_clean_protein_sequence(wt_seq))
                    if wt_seq
                    else 0,
                }

                sol_path = wt_root / "soluprot.json"
                sol_payload = (
                    _load_json_file(sol_path)
                    if sol_path.exists() and not request.force
                    else None
                )
                sol_cached = sol_payload is not None
                set_status(
                    paths,
                    stage="wt_soluprot",
                    state="running",
                    detail=("cached" if sol_cached else None),
                )
                if sol_payload is None:
                    try:
                        if not wt_seq:
                            sol_payload = {
                                "skipped": True,
                                "reason": "WT sequence unavailable",
                            }
                        elif self.soluprot is None:
                            sol_payload = {
                                "skipped": True,
                                "reason": "SOLUPROT_URL not set",
                            }
                        else:
                            chain_seqs = _split_multichain_sequence(wt_seq)
                            child_records: list[SequenceRecord] = []
                            child_to_parent: dict[str, tuple[str, str]] = {}
                            if len(chain_seqs) <= 1:
                                cid = "wt"
                                child_to_parent[cid] = ("wt", "")
                                child_records.append(
                                    SequenceRecord(
                                        id=cid,
                                        header="wt",
                                        sequence=_clean_protein_sequence(chain_seqs[0]),
                                        meta={},
                                    )
                                )
                            else:
                                for idx, chain_seq in enumerate(chain_seqs):
                                    label = (
                                        str(design_chains[idx]).strip()
                                        if (
                                            design_chains is not None
                                            and idx < len(design_chains)
                                        )
                                        else f"chain_{idx + 1}"
                                    )
                                    cid = f"wt:{label}"
                                    child_to_parent[cid] = ("wt", label)
                                    child_records.append(
                                        SequenceRecord(
                                            id=cid,
                                            header=f"wt|{label}",
                                            sequence=_clean_protein_sequence(chain_seq),
                                            meta={},
                                        )
                                    )
                            scores_by_child = self.soluprot.score(child_records)
                            chain_scores: dict[str, dict[str, float]] = {}
                            for child_id, score in scores_by_child.items():
                                parent_id, label = child_to_parent.get(
                                    child_id, ("wt", "")
                                )
                                chain_scores.setdefault(parent_id, {})[
                                    label or "chain_1"
                                ] = float(score)
                            per_chain = chain_scores.get("wt") or {}
                            score = min(per_chain.values()) if per_chain else 0.0
                            sol_payload = {
                                "score": float(score),
                                "scores_by_chain": per_chain,
                                "cutoff": float(request.soluprot_cutoff),
                                "passed": float(score)
                                >= float(request.soluprot_cutoff),
                            }
                    except Exception as exc:
                        sol_payload = {"skipped": True, "error": str(exc)}
                    write_json(sol_path, sol_payload)
                payload["soluprot"] = sol_payload or {"skipped": True}
                sol_detail = (
                    "cached"
                    if sol_cached
                    else (
                        "skipped" if bool((sol_payload or {}).get("skipped")) else None
                    )
                )
                set_status(
                    paths, stage="wt_soluprot", state="completed", detail=sol_detail
                )

                af2_root = _ensure_dir(wt_root / "af2")
                af2_metrics_path = af2_root / "metrics.json"
                af2_job_path = af2_root / "runpod_job.json"
                af2_payload = (
                    _load_json_file(af2_metrics_path)
                    if af2_metrics_path.exists() and not request.force
                    else None
                )
                if _should_retry_cached_wt_af2(af2_payload):
                    af2_payload = None
                    _unlink_if_exists(af2_job_path)
                af2_cached = af2_payload is not None
                set_status(
                    paths,
                    stage="wt_af2",
                    state="running",
                    detail=("cached" if af2_cached else None),
                )
                if af2_payload is None:
                    try:
                        if not wt_seq:
                            af2_payload = {
                                "skipped": True,
                                "reason": "WT sequence unavailable",
                            }
                        elif af2_client is None:
                            af2_payload = {
                                "skipped": True,
                                "reason": f"{af2_provider_label} not configured",
                            }
                        else:
                            seq_in = _prepare_af2_sequence(
                                wt_seq,
                                model_preset=wt_af2_model_preset,
                                chain_ids=design_chains,
                            )
                            seqrec = SequenceRecord(
                                id="wt",
                                header=(
                                    target_record.header if target_record else "wt"
                                ),
                                sequence=seq_in,
                                meta={},
                            )
                            resume_job_ids: dict[str, str] | None = None
                            if af2_job_path.exists():
                                try:
                                    job_payload = json.loads(
                                        af2_job_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    job_payload = None
                                if isinstance(job_payload, dict):
                                    existing_job_id = str(
                                        job_payload.get("job_id") or ""
                                    ).strip()
                                    existing_seq_id = (
                                        str(job_payload.get("seq_id") or "wt").strip()
                                        or "wt"
                                    )
                                    if existing_job_id:
                                        resume_job_ids = {
                                            existing_seq_id: existing_job_id
                                        }

                            def _on_wt_job_id(seq_id: str, job_id: str) -> None:
                                payload: dict[str, object] = {
                                    "seq_id": seq_id,
                                    "job_id": job_id,
                                    "provider": af2_provider,
                                }
                                if af2_endpoint_id:
                                    payload["endpoint_id"] = af2_endpoint_id
                                write_json(af2_job_path, payload)
                                set_status(
                                    paths,
                                    stage="wt_af2",
                                    state="running",
                                    detail=f"runpod_job_id={job_id} seq_id={seq_id}",
                                )

                            try:
                                af2_out = af2_client.predict(
                                    [seqrec],
                                    model_preset=wt_af2_model_preset,
                                    db_preset=request.af2_db_preset,
                                    max_template_date=request.af2_max_template_date,
                                    extra_flags=request.af2_extra_flags,
                                    resume_job_ids=resume_job_ids,
                                    on_job_id=_on_wt_job_id,
                                )
                            except TypeError:
                                af2_out = af2_client.predict(
                                    [seqrec],
                                    model_preset=wt_af2_model_preset,
                                    db_preset=request.af2_db_preset,
                                    max_template_date=request.af2_max_template_date,
                                    extra_flags=request.af2_extra_flags,
                                )

                            rec = (
                                af2_out.get("wt") if isinstance(af2_out, dict) else None
                            )
                            if not isinstance(rec, dict):
                                raise RuntimeError(
                                    f"{af2_provider_label} did not return WT metrics"
                                )
                            ranked0 = (
                                rec.get("ranked_0_pdb")
                                or rec.get("pdb")
                                or rec.get("pdb_text")
                            )
                            if isinstance(ranked0, str) and ranked0.strip():
                                _write_text(af2_root / "ranked_0.pdb", ranked0)
                            if isinstance(rec.get("ranking_debug"), dict):
                                write_json(
                                    af2_root / "ranking_debug.json",
                                    rec["ranking_debug"],
                                )
                            best_plddt = rec.get("best_plddt")
                            rmsd_val = None
                            if (
                                isinstance(ranked0, str)
                                and ranked0.strip()
                                and wt_compare_reference_pdb_text.strip()
                            ):
                                try:
                                    rmsd_val = ca_rmsd(
                                        wt_compare_reference_pdb_text,
                                        ranked0,
                                        chains=design_chains,
                                    )
                                except Exception:
                                    rmsd_val = None
                            af2_payload = {
                                "best_plddt": best_plddt,
                                "rmsd_ca": rmsd_val,
                                "model_preset": wt_af2_model_preset,
                                "db_preset": request.af2_db_preset,
                                "max_template_date": request.af2_max_template_date,
                                "provider": af2_provider,
                            }
                    except Exception as exc:
                        af2_payload = {"skipped": True, "error": str(exc)}
                    write_json(af2_metrics_path, af2_payload)
                payload["af2"] = af2_payload or {"skipped": True}
                af2_detail = (
                    "cached"
                    if af2_cached
                    else (
                        "skipped" if bool((af2_payload or {}).get("skipped")) else None
                    )
                )
                set_status(paths, stage="wt_af2", state="completed", detail=af2_detail)

                if relax_enabled:
                    relax_root = _ensure_dir(wt_root / "relax")
                    relax_metrics_path = relax_root / "metrics.json"
                    relax_payload = (
                        _load_json_file(relax_metrics_path)
                        if relax_metrics_path.exists() and not request.force
                        else None
                    )
                    relax_cached = (
                        relax_payload is not None
                        and not _relax_payload_has_recovered_failure(relax_payload)
                        and relax_payload.get("nstruct")
                        in {
                            None,
                            max(1, int(getattr(request, "relax_nstruct", 1) or 1)),
                        }
                        and str(relax_payload.get("extra_flags") or "").strip()
                        == str(getattr(request, "relax_extra_flags", "") or "").strip()
                    )
                    set_status(
                        paths,
                        stage="wt_relax",
                        state="running",
                        detail=("cached" if relax_cached else None),
                    )
                    if not relax_cached:
                        try:
                            wt_ranked_pdb_path = wt_root / "af2" / "ranked_0.pdb"
                            wt_ranked_pdb = (
                                wt_ranked_pdb_path.read_text(encoding="utf-8")
                                if wt_ranked_pdb_path.exists()
                                else ""
                            )
                            if not wt_seq:
                                relax_payload = {
                                    "skipped": True,
                                    "reason": "WT sequence unavailable",
                                }
                            elif not wt_ranked_pdb.strip():
                                relax_payload = {
                                    "skipped": True,
                                    "reason": "WT AF2 structure unavailable",
                                }
                            elif rosetta_relax_client is None:
                                relax_payload = {
                                    "skipped": True,
                                    "reason": "Rosetta relax is not configured",
                                }
                            else:
                                relax_result = rosetta_relax_client.relax(
                                    wt_ranked_pdb,
                                    nstruct=max(
                                        1,
                                        int(getattr(request, "relax_nstruct", 1) or 1),
                                    ),
                                    extra_flags=getattr(
                                        request, "relax_extra_flags", None
                                    ),
                                )
                                _write_text(
                                    relax_root / "relaxed_best.pdb",
                                    str(relax_result.get("best_pdb_text") or ""),
                                )
                                total_score = (
                                    float(relax_result.get("total_score"))
                                    if isinstance(
                                        relax_result.get("total_score"), (int, float)
                                    )
                                    else None
                                )
                                delta_total_score = (
                                    float(relax_result.get("delta_total_score"))
                                    if isinstance(
                                        relax_result.get("delta_total_score"),
                                        (int, float),
                                    )
                                    else None
                                )
                                relax_payload = {
                                    "score_per_residue": _score_per_residue(
                                        total_score, wt_seq
                                    ),
                                    "total_score": total_score,
                                    "delta_total_score": delta_total_score,
                                    "input_total_score": (
                                        float(relax_result.get("input_total_score"))
                                        if isinstance(
                                            relax_result.get("input_total_score"),
                                            (int, float),
                                        )
                                        else None
                                    ),
                                    "description": str(
                                        relax_result.get("description") or ""
                                    ).strip()
                                    or None,
                                    "nstruct": max(
                                        1,
                                        int(getattr(request, "relax_nstruct", 1) or 1),
                                    ),
                                    "extra_flags": str(
                                        getattr(request, "relax_extra_flags", "") or ""
                                    ).strip()
                                    or None,
                                    "mode": str(relax_result.get("mode") or "").strip()
                                    or None,
                                    "sequence_length": _sequence_length(wt_seq),
                                }
                        except Exception as exc:
                            relax_payload = {"skipped": True, "error": str(exc)}
                        write_json(relax_metrics_path, relax_payload)
                    payload["relax"] = relax_payload or {"skipped": True}
                    relax_detail = (
                        "cached"
                        if relax_cached
                        else (
                            "skipped"
                            if bool((relax_payload or {}).get("skipped"))
                            else None
                        )
                    )
                    set_status(
                        paths, stage="wt_relax", state="completed", detail=relax_detail
                    )

                write_json(metrics_path, payload)
                set_status(paths, stage="wt_baseline", state="completed")

            _compute_wt_baseline()

            for ctx in backbone_contexts:
                ctx["ligand_mask_pdb_text"] = ctx["pdb_text"]

            if _diffdock_requested(request):

                def _run_diffdock() -> None:
                    diffdock_root = _ensure_dir(paths.root / "diffdock")
                    for idx, ctx in enumerate(backbone_contexts):
                        ctx_design_chains = (
                            ctx.get("design_chains")
                            if isinstance(ctx.get("design_chains"), list)
                            else design_chains
                        )
                        has_ligand = ligand_atoms_present(
                            ctx["pdb_text"],
                            chains=ctx_design_chains,
                            ligand_resnames=request.ligand_resnames,
                            ligand_atom_chains=request.ligand_atom_chains,
                        )
                        if has_ligand:
                            continue
                        if request.dry_run:
                            continue
                        if self.diffdock is None:
                            raise RuntimeError(
                                "DiffDock endpoint is not configured (set DIFFDOCK_ENDPOINT_ID)"
                            )

                        raw_id = str(ctx.get("id") or f"backbone_{idx}")
                        dir_id = _safe_id(raw_id) or f"backbone_{idx}"
                        diffdock_dir = _ensure_dir(diffdock_root / dir_id)
                        set_status(
                            paths,
                            stage="diffdock",
                            state="running",
                            detail=f"backbone={raw_id}",
                        )

                        ligand_smiles, ligand_sdf = normalize_diffdock_ligand_inputs(
                            request.diffdock_ligand_smiles,
                            request.diffdock_ligand_sdf,
                        )

                        _write_text(diffdock_dir / "protein.pdb", ctx["pdb_text"])
                        if ligand_sdf:
                            _write_text(diffdock_dir / "ligand.sdf", ligand_sdf)
                        elif ligand_smiles:
                            _write_text(
                                diffdock_dir / "ligand.smiles",
                                ligand_smiles,
                            )

                        def _on_diffdock_job(job_id: str) -> None:
                            write_json(
                                diffdock_dir / "runpod_job.json", {"job_id": job_id}
                            )
                            set_status(
                                paths,
                                stage="diffdock",
                                state="running",
                                detail=f"runpod_job_id={job_id}",
                            )

                        diffdock_out = self.diffdock.dock(
                            protein_pdb=ctx["pdb_text"],
                            ligand_smiles=ligand_smiles,
                            ligand_sdf=ligand_sdf,
                            complex_name=dir_id or "complex",
                            config=request.diffdock_config,
                            extra_args=request.diffdock_extra_args,
                            cuda_visible_devices=request.diffdock_cuda_visible_devices,
                            on_job_id=_on_diffdock_job,
                        )
                        output_payload = diffdock_out.get("output") or {}
                        write_json(
                            diffdock_dir / "output.json", _safe_json(output_payload)
                        )
                        zip_bytes = diffdock_out.get("zip_bytes")
                        if isinstance(zip_bytes, (bytes, bytearray)):
                            (diffdock_dir / "out_dir.zip").write_bytes(bytes(zip_bytes))
                        sdf_text = str(diffdock_out.get("sdf_text") or "")
                        if not sdf_text.strip():
                            raise RuntimeError("DiffDock output missing rank1.sdf text")
                        _write_text(diffdock_dir / "rank1.sdf", sdf_text)

                        ligand_pdb = sdf_to_pdb(sdf_text)
                        _write_text(diffdock_dir / "ligand.pdb", ligand_pdb)
                        complex_pdb = append_ligand_pdb(ctx["pdb_text"], ligand_pdb)
                        _write_text(diffdock_dir / "complex.pdb", complex_pdb)
                        if idx == 0:
                            _write_text(diffdock_root / "complex.pdb", complex_pdb)
                            _write_text(diffdock_root / "ligand.pdb", ligand_pdb)
                            _write_text(diffdock_root / "rank1.sdf", sdf_text)
                        ctx["ligand_mask_pdb_text"] = complex_pdb
                        set_status(
                            paths,
                            stage="diffdock",
                            state="completed",
                            detail=f"backbone={raw_id}",
                        )

                def _fallback_diffdock(exc: Exception) -> None:
                    write_json(
                        paths.root / "diffdock_recovery.json",
                        {
                            "error": str(exc),
                            "recovered_at": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.gmtime()
                            ),
                        },
                    )
                    set_status(
                        paths, stage="diffdock", state="completed", detail="recovered"
                    )

                _, diff_recovered, diff_error, diff_recovery = _recover_stage(
                    "diffdock",
                    _run_diffdock,
                    fallback=_fallback_diffdock,
                    recovery_actions=["Skipped DiffDock and kept original complex"],
                )
                _emit_panel(
                    "diffdock",
                    detail=("recovered" if diff_recovered else None),
                    error=diff_error,
                    recovery=diff_recovery,
                )

            def _run_ligand_mask() -> None:
                nonlocal ligand_mask_path
                for ctx in backbone_contexts:
                    ctx_design_chains = (
                        ctx.get("design_chains")
                        if isinstance(ctx.get("design_chains"), list)
                        else None
                    )
                    ligand_mask = ligand_proximity_mask(
                        ctx.get("ligand_mask_pdb_text") or ctx["pdb_text"],
                        chains=ctx_design_chains,
                        distance_angstrom=request.ligand_mask_distance,
                        ligand_resnames=request.ligand_resnames,
                        ligand_atom_chains=request.ligand_atom_chains,
                    )
                    ctx["ligand_mask"] = ligand_mask
                    write_json(ctx["dir"] / "ligand_mask.json", ligand_mask)
                    if ctx is backbone_contexts[0]:
                        ligand_mask_path = str(paths.root / "ligand_mask.json")
                        write_json(Path(ligand_mask_path), ligand_mask)
                set_status(paths, stage="ligand_mask", state="completed")

            def _fallback_ligand_mask(exc: Exception) -> None:
                nonlocal ligand_mask_path
                empty_mask: dict[str, list[int]] = {}
                for ctx in backbone_contexts:
                    ctx["ligand_mask"] = empty_mask
                    write_json(ctx["dir"] / "ligand_mask.json", empty_mask)
                    if ctx is backbone_contexts[0]:
                        ligand_mask_path = str(paths.root / "ligand_mask.json")
                        write_json(Path(ligand_mask_path), empty_mask)
                write_json(
                    paths.root / "ligand_mask_recovery.json",
                    {
                        "error": str(exc),
                        "recovered_at": time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.gmtime()
                        ),
                    },
                )
                set_status(
                    paths, stage="ligand_mask", state="completed", detail="recovered"
                )

            _, lm_recovered, lm_error, lm_recovery = _recover_stage(
                "ligand_mask",
                _run_ligand_mask,
                fallback=_fallback_ligand_mask,
                recovery_actions=["Used empty ligand mask"],
            )
            _emit_panel(
                "ligand_mask",
                detail=("recovered" if lm_recovered else None),
                error=lm_error,
                recovery=lm_recovery,
            )

            if request.surface_only:
                set_status(paths, stage="surface_mask", state="running")

                def _run_surface_mask() -> None:
                    nonlocal surface_mask_path
                    for ctx in backbone_contexts:
                        ctx_design_chains = (
                            ctx.get("design_chains")
                            if isinstance(ctx.get("design_chains"), list)
                            else None
                        )
                        surface_mask, surface_sasa = surface_positions_by_chain(
                            ctx["pdb_text"],
                            chains=ctx_design_chains,
                            min_rel=request.surface_min_rel,
                            min_abs=request.surface_min_abs,
                        )
                        ctx["surface_mask"] = surface_mask
                        write_json(ctx["dir"] / "surface_mask.json", surface_mask)
                        write_json(ctx["dir"] / "surface_sasa.json", surface_sasa)
                        if ctx is backbone_contexts[0]:
                            surface_mask_path = str(paths.root / "surface_mask.json")
                            write_json(Path(surface_mask_path), surface_mask)
                            write_json(paths.root / "surface_sasa.json", surface_sasa)
                    set_status(paths, stage="surface_mask", state="completed")

                def _fallback_surface_mask(exc: Exception) -> None:
                    nonlocal surface_mask_path
                    empty_mask: dict[str, list[int]] = {}
                    for ctx in backbone_contexts:
                        ctx["surface_mask"] = None
                        write_json(ctx["dir"] / "surface_mask.json", empty_mask)
                        if ctx is backbone_contexts[0]:
                            surface_mask_path = str(paths.root / "surface_mask.json")
                            write_json(Path(surface_mask_path), empty_mask)
                    write_json(
                        paths.root / "surface_mask_recovery.json",
                        {
                            "error": str(exc),
                            "recovered_at": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.gmtime()
                            ),
                        },
                    )
                    set_status(
                        paths,
                        stage="surface_mask",
                        state="completed",
                        detail="recovered",
                    )

                _, sm_recovered, sm_error, sm_recovery = _recover_stage(
                    "surface_mask",
                    _run_surface_mask,
                    fallback=_fallback_surface_mask,
                    recovery_actions=["Used empty surface mask"],
                )
                _emit_panel(
                    "surface_mask",
                    detail=("recovered" if sm_recovered else None),
                    error=sm_error,
                    recovery=sm_recovery,
                )
            else:
                for ctx in backbone_contexts:
                    ctx["surface_mask"] = {}

            def _run_mask_consensus() -> None:
                set_status(paths, stage="mask_consensus", state="running")
                primary_ctx = backbone_contexts[0] if backbone_contexts else None
                mapping_by_chain = (
                    primary_ctx.get("mapping") if primary_ctx else {}
                ) or {}
                ligand_mask_by_chain = (
                    primary_ctx.get("ligand_mask") if primary_ctx else {}
                ) or {}
                primary_design_chains = (
                    list(primary_ctx.get("design_chains"))
                    if primary_ctx
                    and isinstance(primary_ctx.get("design_chains"), list)
                    else None
                )

                msa_quality_path = paths.root / "msa" / "quality.json"
                msa_quality: dict[str, object] | None = None
                if msa_quality_path.exists():
                    try:
                        msa_quality = json.loads(
                            msa_quality_path.read_text(encoding="utf-8")
                        )
                    except Exception:
                        msa_quality = None
                coverage_p50 = None
                usable_hits = None
                if isinstance(msa_quality, dict):
                    usable_hits = msa_quality.get("usable_hits")
                    coverage = msa_quality.get("coverage")
                    if isinstance(coverage, dict):
                        coverage_p50 = coverage.get("p50")
                msa_depth_low = False
                if isinstance(usable_hits, (int, float)) and float(usable_hits) < 100:
                    msa_depth_low = True
                if isinstance(coverage_p50, (int, float)) and float(coverage_p50) < 0.5:
                    msa_depth_low = True

                query_report_path = paths.root / "query_pdb_alignment.json"
                query_report: dict[str, object] | None = None
                if query_report_path.exists():
                    try:
                        query_report = json.loads(
                            query_report_path.read_text(encoding="utf-8")
                        )
                    except Exception:
                        query_report = None
                query_identity_min = None
                if isinstance(query_report, dict):
                    chains = query_report.get("chains")
                    if isinstance(chains, dict) and chains:
                        vals = []
                        for chain_payload in chains.values():
                            if isinstance(chain_payload, dict):
                                qi = chain_payload.get("query_identity")
                                if isinstance(qi, (int, float)):
                                    vals.append(float(qi))
                        if vals:
                            query_identity_min = min(vals)
                query_identity_low = (
                    isinstance(query_identity_min, (int, float))
                    and query_identity_min < 0.9
                )

                scores = list(conservation.scores or [])
                query_len = int(conservation.query_length or len(scores) or 0)

                def _top_positions(frac: float) -> list[int]:
                    if not scores or query_len <= 0:
                        return []
                    k = max(1, int(round(query_len * float(frac))))
                    ranked = sorted(
                        range(query_len), key=lambda i: scores[i], reverse=True
                    )[:k]
                    return sorted([i + 1 for i in ranked])

                def _positions_by_score(min_score: float) -> list[int]:
                    if not scores:
                        return []
                    out: list[int] = []
                    for idx, score in enumerate(scores, start=1):
                        try:
                            if float(score) >= float(min_score):
                                out.append(int(idx))
                        except Exception:
                            continue
                    return out

                chains = (
                    primary_design_chains
                    or list(ligand_mask_by_chain.keys())
                    or list(original_ligand_mask_query_by_chain.keys())
                    or list(mapping_by_chain.keys())
                    or ["A"]
                )

                def _map_positions(positions: list[int], chain_id: str) -> list[int]:
                    mapping = mapping_by_chain.get(chain_id)
                    if not mapping:
                        return sorted(set(int(p) for p in positions))
                    mapped: list[int] = []
                    for pos in positions:
                        if 1 <= int(pos) <= len(mapping):
                            mapped_pos = mapping[int(pos) - 1]
                            if mapped_pos is not None:
                                mapped.append(int(mapped_pos))
                    return sorted(set(mapped))

                effective_ligand_mask_by_chain: dict[str, list[int]] = {}
                for chain_id in chains:
                    chain_positions = set(
                        int(p)
                        for p in (
                            _fallback_chain_positions(ligand_mask_by_chain, chain_id)
                            or []
                        )
                        if isinstance(p, (int, float))
                    )
                    if bool(request.ligand_mask_use_original_target):
                        query_positions = _fallback_chain_positions(
                            original_ligand_mask_query_by_chain,
                            chain_id,
                        )
                        mapped_positions = _map_positions(query_positions, chain_id)
                        chain_positions.update(int(p) for p in mapped_positions)
                    effective_ligand_mask_by_chain[chain_id] = sorted(chain_positions)

                experts: list[dict[str, object]] = []
                tier_payloads_query: dict[str, dict[str, list[int]]] = {}
                tier_payloads_chain: dict[str, dict[str, dict[str, list[int]]]] = {}

                ligand_mask_query_positions: set[int] = set()
                for chain_id, mapping in mapping_by_chain.items():
                    if not mapping:
                        continue
                    chain_mask = set(
                        int(p)
                        for p in (
                            effective_ligand_mask_by_chain.get(chain_id, []) or []
                        )
                        if isinstance(p, (int, float))
                    )
                    if not chain_mask:
                        continue
                    for qpos, pdb_pos in enumerate(mapping, start=1):
                        if pdb_pos is None:
                            continue
                        if int(pdb_pos) in chain_mask:
                            ligand_mask_query_positions.add(int(qpos))

                for tier in active_tiers:
                    tier_key = _tier_key(tier)
                    base_fixed = (
                        conservation.fixed_positions_by_tier.get(tier, []) or []
                    )

                    bio_extra = _top_positions(0.1) if msa_depth_low else []
                    bio_positions = sorted(set(base_fixed) | set(bio_extra))

                    struct_positions = sorted(ligand_mask_query_positions)
                    if not struct_positions:
                        struct_positions = _top_positions(0.05)

                    eng_positions = _positions_by_score(0.8)

                    syn_frac = 0.15 if msa_depth_low else 0.05
                    syn_positions = _top_positions(syn_frac)

                    exp_frac = 0.15 if query_identity_low else 0.05
                    exp_positions = _top_positions(exp_frac)

                    tier_payloads_query[tier_key] = {
                        "bioinformatics": bio_positions,
                        "structural": struct_positions,
                        "protein_engineering": eng_positions,
                        "synthetic_biology": syn_positions,
                        "experimental": exp_positions,
                    }

                    tier_payloads_chain[tier_key] = {
                        "bioinformatics": {
                            chain: _map_positions(bio_positions, chain)
                            for chain in chains
                        },
                        "structural": {
                            chain: _map_positions(struct_positions, chain)
                            for chain in chains
                        },
                        "protein_engineering": {
                            chain: _map_positions(eng_positions, chain)
                            for chain in chains
                        },
                        "synthetic_biology": {
                            chain: _map_positions(syn_positions, chain)
                            for chain in chains
                        },
                        "experimental": {
                            chain: _map_positions(exp_positions, chain)
                            for chain in chains
                        },
                    }

                experts = [
                    {
                        "name": "bioinformatics",
                        "focus": "Conservation-driven masks, adjusted by MSA depth.",
                        "notes": "Added top 10% conserved positions when MSA depth is low."
                        if msa_depth_low
                        else "Used tier conservation positions.",
                    },
                    {
                        "name": "structural",
                        "focus": "Ligand proximity masking to protect binding site geometry.",
                        "notes": "Used ligand proximity mask; fallback to top 5% conservation if no ligand residues.",
                    },
                    {
                        "name": "protein_engineering",
                        "focus": "High-conservation positions (>=0.8) to preserve stability motifs.",
                        "notes": "Thresholded conservation scores at 0.8.",
                    },
                    {
                        "name": "synthetic_biology",
                        "focus": "Conservative masking when MSA depth/coverage is low.",
                        "notes": f"Top {int((0.15 if msa_depth_low else 0.05) * 100)}% conserved positions.",
                    },
                    {
                        "name": "experimental",
                        "focus": "Additional masking if query-PDB identity is low.",
                        "notes": f"Top {int((0.15 if query_identity_low else 0.05) * 100)}% conserved positions.",
                    },
                ]

                consensus_threshold = 3
                consensus_query_by_tier: dict[str, list[int]] = {}
                consensus_by_tier: dict[str, dict[str, list[int]]] = {}
                votes_by_tier: dict[str, dict[str, dict[str, int]]] = {}

                for tier_key, expert_votes in tier_payloads_query.items():
                    counts: dict[str, int] = {}
                    for _expert_name, positions in expert_votes.items():
                        for pos in positions or []:
                            key = str(pos)
                            counts[key] = counts.get(key, 0) + 1
                    for pos in ligand_mask_query_positions:
                        key = str(pos)
                        counts[key] = max(counts.get(key, 0), consensus_threshold)
                    consensus_positions = [
                        int(p)
                        for p, c in counts.items()
                        if int(c) >= consensus_threshold
                    ]
                    consensus_query_by_tier[tier_key] = sorted(set(consensus_positions))

                for tier_key, query_positions in consensus_query_by_tier.items():
                    consensus_by_tier[tier_key] = {
                        chain: _map_positions(query_positions, chain)
                        for chain in chains
                    }
                    votes_by_tier[tier_key] = {}
                    for chain in chains:
                        chain_counts: dict[str, int] = {}
                        for _expert_name, per_chain in tier_payloads_chain.get(
                            tier_key, {}
                        ).items():
                            chain_positions = (
                                per_chain.get(chain)
                                if isinstance(per_chain, dict)
                                else []
                            )
                            for pos in chain_positions or []:
                                key = str(pos)
                                chain_counts[key] = chain_counts.get(key, 0) + 1
                        for pos in effective_ligand_mask_by_chain.get(chain, []) or []:
                            key = str(pos)
                            chain_counts[key] = max(
                                chain_counts.get(key, 0), consensus_threshold
                            )
                        votes_by_tier[tier_key][chain] = chain_counts

                consensus_payload = {
                    "threshold": consensus_threshold,
                    "fixed_positions_query_by_tier": consensus_query_by_tier,
                    "fixed_positions_by_tier": consensus_by_tier,
                    "votes": votes_by_tier,
                }

                notes = [
                    "Consensus uses majority vote across experts (>=3).",
                    "Ligand proximity mask positions are always retained.",
                ]
                if bool(request.ligand_mask_use_original_target):
                    notes.append(
                        "Original target ligand mask was projected onto the active backbone when available."
                    )
                if request.mask_consensus_apply:
                    notes.append(
                        "Consensus output will be applied to ProteinMPNN in this run."
                    )
                else:
                    notes.append(
                        "Consensus output is advisory and not applied to ProteinMPNN in this run."
                    )

                output_payload = {
                    "run_id": run_id,
                    "experts": experts,
                    "inputs": {
                        "msa_quality_path": str(msa_quality_path)
                        if msa_quality_path.exists()
                        else None,
                        "conservation_path": conservation_path,
                        "ligand_mask_path": ligand_mask_path,
                        "ligand_mask_original_target_path": str(
                            paths.root / "ligand_mask_original_target.json"
                        ),
                        "query_pdb_alignment_path": str(query_report_path)
                        if query_report_path.exists()
                        else None,
                    },
                    "signals": {
                        "msa_depth_low": msa_depth_low,
                        "query_identity_min": query_identity_min,
                    },
                    "expert_votes_query": tier_payloads_query,
                    "expert_votes": tier_payloads_chain,
                    "consensus": consensus_payload,
                    "notes": notes,
                }

                write_json(paths.root / "mask_consensus.json", output_payload)
                for tier_key, positions in consensus_by_tier.items():
                    tier_dir = _ensure_dir(tiers_dir / tier_key)
                    write_json(tier_dir / "fixed_positions_consensus.json", positions)

                set_status(paths, stage="mask_consensus", state="completed")

            def _fallback_mask_consensus(exc: Exception) -> None:
                write_json(
                    paths.root / "mask_consensus.json",
                    {
                        "run_id": run_id,
                        "error": str(exc),
                        "notes": [
                            "Mask consensus failed; no recommendations produced."
                        ],
                    },
                )
                set_status(
                    paths, stage="mask_consensus", state="completed", detail="recovered"
                )

            _, mc_recovered, mc_error, mc_recovery = _recover_stage(
                "mask_consensus",
                _run_mask_consensus,
                fallback=_fallback_mask_consensus,
                recovery_actions=["Skipped mask consensus"],
            )
            _emit_panel(
                "mask_consensus",
                detail=("recovered" if mc_recovered else None),
                error=mc_error,
                recovery=mc_recovery,
            )

            consensus_query_by_tier: dict[str, list[int]] = {}
            if request.mask_consensus_apply:
                mc_path = paths.root / "mask_consensus.json"
                if mc_path.exists():
                    try:
                        mc_payload = json.loads(mc_path.read_text(encoding="utf-8"))
                    except Exception:
                        mc_payload = None
                    if isinstance(mc_payload, dict):
                        consensus = mc_payload.get("consensus")
                        if isinstance(consensus, dict):
                            fixed_query = consensus.get("fixed_positions_query_by_tier")
                            if isinstance(fixed_query, dict):
                                for tier_key, positions in fixed_query.items():
                                    if not isinstance(positions, list):
                                        continue
                                    cleaned: list[int] = []
                                    for pos in positions:
                                        try:
                                            cleaned.append(int(pos))
                                        except Exception:
                                            continue
                                    consensus_query_by_tier[str(tier_key)] = sorted(
                                        set(cleaned)
                                    )

            multi_backbone = len(backbone_contexts) > 1

            def _tag_samples(
                samples: list[SequenceRecord],
                backbone_id: str,
                *,
                backbone_source: str,
            ) -> list[SequenceRecord]:
                tagged: list[SequenceRecord] = []
                for s in samples:
                    raw_id = str(s.id)
                    new_id = f"{backbone_id}:{raw_id}"
                    header = s.header or raw_id
                    new_header = (
                        f"{header}|backbone={backbone_id}|source={backbone_source}"
                    )
                    meta = dict(s.meta) if isinstance(s.meta, dict) else {}
                    meta.setdefault("backbone_id", backbone_id)
                    meta.setdefault("source_id", raw_id)
                    meta.setdefault("backbone_source", backbone_source)
                    tagged.append(
                        SequenceRecord(
                            id=new_id,
                            header=new_header,
                            sequence=s.sequence,
                            meta=meta,
                        )
                    )
                return tagged

            def _fallback_proteinmpnn(
                *,
                tier_dir: Path,
                pdb_text: str,
                design_chains_local: list[str] | None,
                fixed_positions_by_chain: dict[str, list[int]],
                reason: str,
            ) -> tuple[SequenceRecord | None, list[SequenceRecord]]:
                seq = ""
                if target_record is not None and target_record.sequence:
                    seq = target_record.sequence
                if not seq:
                    seqs = sequence_by_chain(pdb_text, chains=design_chains_local)
                    if design_chains_local:
                        seq = seqs.get(design_chains_local[0], "")
                    if not seq and seqs:
                        seq = next(iter(seqs.values()))
                if not seq:
                    seq = "A" * 60
                native = SequenceRecord(id="native", sequence=seq, header="native")
                samples = [
                    SequenceRecord(
                        id=f"fallback_{i + 1:03d}",
                        sequence=seq,
                        header=f"fallback_{i + 1:03d}",
                    )
                    for i in range(max(1, int(request.num_seq_per_tier)))
                ]
                write_json(
                    tier_dir / "proteinmpnn.json",
                    {
                        "native": {
                            "id": native.id,
                            "sequence": native.sequence,
                            "header": native.header,
                        },
                        "samples": [
                            {"id": s.id, "sequence": s.sequence, "header": s.header}
                            for s in samples
                        ],
                        "fixed_positions": fixed_positions_by_chain,
                        "request": {
                            "recovered": True,
                            "reason": reason,
                            "num_seq_per_target": int(request.num_seq_per_tier),
                        },
                    },
                )
                _write_text(
                    tier_dir / "designs.fasta",
                    to_fasta(
                        [
                            FastaRecord(header=s.header or s.id, sequence=s.sequence)
                            for s in samples
                        ]
                    ),
                )
                write_json(
                    tier_dir / "fixed_positions_check.json",
                    {"ok": False, "skipped": True, "reason": "recovered"},
                )
                return native, samples

            for tier in active_tiers:
                tier_str = _tier_key(tier)
                _ensure_not_cancelled(stage=f"proteinmpnn_{tier_str}")
                tier_dir = _ensure_dir(tiers_dir / tier_str)

                tier_fixed = conservation.fixed_positions_by_tier.get(tier, []) or []
                if request.mask_consensus_apply and consensus_query_by_tier:
                    tier_fixed = consensus_query_by_tier.get(tier_str, tier_fixed)
                tier_samples: list[SequenceRecord] = []
                backbone_meta: list[dict[str, Any]] = []
                primary_fixed: dict[str, list[int]] | None = None
                primary_native: SequenceRecord | None = None
                mutation_report_path = None
                mutations_by_position_tsv = None
                mutations_by_position_svg = None
                mutations_by_sequence_tsv = None

                set_status(paths, stage=f"proteinmpnn_{tier_str}", state="running")
                mpnn_any_recovered = False
                mpnn_error: str | None = None
                mpnn_recovery: dict[str, object] | None = None

                for idx, ctx in enumerate(backbone_contexts):
                    _ensure_not_cancelled(stage=f"proteinmpnn_{tier_str}")
                    bb_tier_dir = (
                        tier_dir
                        if not multi_backbone
                        else _ensure_dir(ctx["dir"] / "tiers" / tier_str)
                    )
                    mapping_by_chain = ctx.get("mapping") or {}
                    ligand_mask = ctx.get("ligand_mask") or {}
                    surface_mask = ctx.get("surface_mask")
                    residues_by_chain_map = residues_by_chain(
                        ctx["pdb_text"], only_atom_records=True
                    )
                    ctx_design_chains = (
                        list(ctx.get("design_chains"))
                        if isinstance(ctx.get("design_chains"), list)
                        else []
                    )
                    if not ctx_design_chains:
                        ctx_design_chains = (
                            list(residues_by_chain_map.keys())
                            or list(ligand_mask.keys())
                            or ["A"]
                        )
                    proteinmpnn_pdb_text = _proteinmpnn_input_pdb_text(
                        ctx["pdb_text"],
                        design_chains=ctx_design_chains,
                        af2_model_preset=af2_model_preset,
                    )
                    fixed_positions_by_chain: dict[str, list[int]] = {}
                    extra_fixed = request.fixed_positions_extra or {}
                    for chain_id in ctx_design_chains:
                        mapped: list[int] = []
                        mapping = mapping_by_chain.get(chain_id)
                        if mapping:
                            for pos in tier_fixed:
                                if 1 <= int(pos) <= len(mapping):
                                    mapped_pos = mapping[int(pos) - 1]
                                    if mapped_pos is not None:
                                        mapped.append(int(mapped_pos))
                        else:
                            mapped = [int(pos) for pos in tier_fixed]

                        chain_fixed = set(mapped)
                        if isinstance(extra_fixed, dict):
                            raw_extra: list[object] = []
                            per_chain = extra_fixed.get(chain_id)
                            if isinstance(per_chain, list):
                                raw_extra.extend(per_chain)
                            elif len(ctx_design_chains) == 1:
                                raw_extra.extend(
                                    _fallback_chain_positions(extra_fixed, chain_id)
                                )
                            all_chains = extra_fixed.get("*")
                            if isinstance(all_chains, list):
                                raw_extra.extend(all_chains)
                            if raw_extra:
                                extra_mapped: list[int] = []
                                if mapping:
                                    for pos in raw_extra:
                                        if 1 <= int(pos) <= len(mapping):
                                            mapped_pos = mapping[int(pos) - 1]
                                            if mapped_pos is not None:
                                                extra_mapped.append(int(mapped_pos))
                                else:
                                    extra_mapped = [int(pos) for pos in raw_extra]
                                chain_fixed.update(extra_mapped)
                        chain_fixed.update(
                            _fallback_chain_positions(ligand_mask, chain_id)
                        )
                        if bool(request.ligand_mask_use_original_target):
                            projected: list[int] = []
                            reference_query_positions = _fallback_chain_positions(
                                original_ligand_mask_query_by_chain,
                                chain_id,
                            )
                            if reference_query_positions and mapping:
                                for pos in reference_query_positions:
                                    if 1 <= int(pos) <= len(mapping):
                                        mapped_pos = mapping[int(pos) - 1]
                                        if mapped_pos is not None:
                                            projected.append(int(mapped_pos))
                            elif not mapping:
                                projected.extend(
                                    _fallback_chain_positions(
                                        original_ligand_mask_by_chain, chain_id
                                    )
                                )
                            chain_fixed.update(projected)

                        if request.surface_only and isinstance(surface_mask, dict):
                            surface_positions = set(
                                int(p)
                                for p in (surface_mask.get(chain_id, []) or [])
                                if isinstance(p, (int, float))
                            )
                            all_positions = {
                                res.index
                                for res in residues_by_chain_map.get(chain_id, [])
                            }
                            if all_positions:
                                non_surface = sorted(all_positions - surface_positions)
                                chain_fixed.update(non_surface)
                        fixed_positions_by_chain[chain_id] = sorted(chain_fixed)

                    write_json(
                        bb_tier_dir / "fixed_positions.json", fixed_positions_by_chain
                    )
                    if multi_backbone and idx == 0:
                        write_json(
                            tier_dir / "fixed_positions.json", fixed_positions_by_chain
                        )

                    (native, samples), mpnn_recovered, mpnn_err, mpnn_rec = (
                        _recover_stage(
                            f"proteinmpnn_{tier_str}",
                            lambda dir_=bb_tier_dir,
                            pdb_text_=proteinmpnn_pdb_text,
                            fixed_=fixed_positions_by_chain,
                            chains_=ctx_design_chains: self._run_proteinmpnn(
                                dir_,
                                request,
                                pdb_text=pdb_text_,
                                tier_str=tier_str,
                                design_chains=chains_,
                                fixed_positions_by_chain=fixed_,
                                on_job_id=lambda job_id,
                                stage=f"proteinmpnn_{tier_str}",
                                dir_=dir_,
                                bb_id=ctx["id"]: (
                                    write_json(
                                        dir_ / "runpod_job.json", {"job_id": job_id}
                                    ),
                                    set_status(
                                        paths,
                                        stage=stage,
                                        state="running",
                                        detail=f"runpod_job_id={job_id} backbone={bb_id}",
                                    ),
                                ),
                            ),
                            fallback=lambda exc,
                            dir_=bb_tier_dir,
                            pdb_text_=proteinmpnn_pdb_text,
                            fixed_=fixed_positions_by_chain,
                            chains_=ctx_design_chains: _fallback_proteinmpnn(
                                tier_dir=dir_,
                                pdb_text=pdb_text_,
                                design_chains_local=chains_,
                                fixed_positions_by_chain=fixed_,
                                reason=str(exc),
                            ),
                            recovery_actions=[
                                "Used fallback sequences for ProteinMPNN"
                            ],
                        )
                    )
                    if mpnn_recovered:
                        mpnn_any_recovered = True
                    if mpnn_err and mpnn_error is None:
                        mpnn_error = mpnn_err
                    if mpnn_rec and mpnn_recovery is None:
                        mpnn_recovery = mpnn_rec

                    if not multi_backbone:
                        mutation_paths = write_mutation_reports(
                            tier_dir,
                            native=native,
                            samples=samples,
                            fixed_positions_by_chain=fixed_positions_by_chain,
                            design_chains=ctx_design_chains,
                        )
                        mutation_report_path = mutation_paths.get(
                            "mutation_report_path"
                        )
                        mutations_by_position_tsv = mutation_paths.get(
                            "mutations_by_position_tsv"
                        )
                        mutations_by_position_svg = mutation_paths.get(
                            "mutations_by_position_svg"
                        )
                        mutations_by_sequence_tsv = mutation_paths.get(
                            "mutations_by_sequence_tsv"
                        )
                    else:
                        mutation_paths = write_mutation_reports(
                            bb_tier_dir,
                            native=native,
                            samples=samples,
                            fixed_positions_by_chain=fixed_positions_by_chain,
                            design_chains=ctx_design_chains,
                        )
                        backbone_meta.append(
                            {
                                "id": ctx["id"],
                                "source": str(ctx.get("source") or "unknown"),
                                "dir": str(bb_tier_dir),
                                "proteinmpnn_json": str(
                                    bb_tier_dir / "proteinmpnn.json"
                                ),
                                "fixed_positions_json": str(
                                    bb_tier_dir / "fixed_positions.json"
                                ),
                                "mutation_report_path": mutation_paths.get(
                                    "mutation_report_path"
                                ),
                                "sequence_count": len(samples),
                                "propagated": True,
                                "materialized": bool(ctx.get("materialized")),
                                "selected": bool(ctx.get("selected")),
                                "rank": ctx.get("rank"),
                                "frame_index": ctx.get("frame_index"),
                                "origin_stage": _backbone_origin_stage(
                                    ctx.get("source")
                                ),
                                "origin_artifact": _backbone_origin_artifact(
                                    ctx.get("source"),
                                    ctx.get("id"),
                                    rfd3_selected_id,
                                ),
                            }
                        )

                    tier_samples.extend(
                        _tag_samples(
                            samples,
                            ctx["id"],
                            backbone_source=str(ctx.get("source") or "unknown"),
                        )
                    )

                    if idx == 0:
                        primary_fixed = fixed_positions_by_chain
                        primary_native = native

                set_status(paths, stage=f"proteinmpnn_{tier_str}", state="completed")
                _emit_panel(
                    f"proteinmpnn_{tier_str}",
                    detail=("recovered" if mpnn_any_recovered else None),
                    error=mpnn_error,
                    recovery=mpnn_recovery,
                )

                samples = tier_samples
                fixed_positions_by_chain = primary_fixed or {}
                native = primary_native if not multi_backbone else None

                pi_scores: dict[str, float] | None = None
                pi_passed = samples
                if request.pi_min is not None or request.pi_max is not None:
                    pi_passed, pi_scores = filter_records_by_pi(
                        samples,
                        pi_min=request.pi_min,
                        pi_max=request.pi_max,
                    )
                    write_json(
                        tier_dir / "pi_scores.json",
                        {
                            "scores": pi_scores,
                            "pi_min": request.pi_min,
                            "pi_max": request.pi_max,
                            "passed_ids": [s.id for s in pi_passed],
                        },
                    )
                    if samples:
                        _write_text(
                            tier_dir / "designs_pi_filtered.fasta",
                            to_fasta(
                                [
                                    FastaRecord(
                                        header=s.header or s.id, sequence=s.sequence
                                    )
                                    for s in pi_passed
                                ]
                            ),
                        )

                if multi_backbone:
                    if samples:
                        _write_text(
                            tier_dir / "designs.fasta",
                            to_fasta(
                                [
                                    FastaRecord(
                                        header=s.header or s.id, sequence=s.sequence
                                    )
                                    for s in samples
                                ]
                            ),
                        )
                    if backbone_meta:
                        write_json(
                            tier_dir / "proteinmpnn_backbones.json",
                            {"backbones": backbone_meta},
                        )

                if request.stop_after == "design":
                    tier_results.append(
                        TierResult(
                            tier=tier,
                            fixed_positions=fixed_positions_by_chain,
                            proteinmpnn_native=native,
                            proteinmpnn_samples=samples,
                            mutation_report_path=mutation_report_path,
                            mutations_by_position_tsv=mutations_by_position_tsv,
                            mutations_by_position_svg=mutations_by_position_svg,
                            mutations_by_sequence_tsv=mutations_by_sequence_tsv,
                        )
                    )
                    continue

                set_status(paths, stage=f"soluprot_{tier_str}", state="running")
                soluprot_inputs = pi_passed
                passed = soluprot_inputs
                soluprot_scores: dict[str, float] | None = None
                passed_ids: list[str] | None = None
                soluprot_path = tier_dir / "soluprot.json"
                sol_recovered = False
                sol_error: str | None = None
                sol_recovery: dict[str, object] | None = None
                try:
                    if not soluprot_inputs:
                        passed = []
                        passed_ids = []
                        write_json(
                            soluprot_path,
                            {
                                "skipped": True,
                                "reason": "pi filter removed all sequences",
                                "cutoff": request.soluprot_cutoff,
                                "passed_ids": passed_ids,
                            },
                        )
                    elif (
                        soluprot_inputs and soluprot_path.exists() and not request.force
                    ):
                        try:
                            payload = json.loads(
                                soluprot_path.read_text(encoding="utf-8")
                            )
                        except Exception:
                            payload = None
                        if isinstance(payload, dict):
                            cached_scores = payload.get("scores")
                            if isinstance(cached_scores, dict):
                                soluprot_scores = {
                                    str(k): float(v)
                                    for k, v in cached_scores.items()
                                    if isinstance(v, (int, float))
                                }
                                passed = [
                                    s
                                    for s in soluprot_inputs
                                    if float(soluprot_scores.get(s.id, 0.0))
                                    >= float(request.soluprot_cutoff)
                                ]
                                passed_ids = [s.id for s in passed]
                                write_json(
                                    soluprot_path,
                                    {
                                        "scores": soluprot_scores,
                                        "cutoff": request.soluprot_cutoff,
                                        "passed_ids": passed_ids,
                                        "cached": True,
                                    },
                                )
                            elif payload.get("skipped") is True:
                                passed = soluprot_inputs
                                passed_ids = [s.id for s in passed]
                    elif soluprot_inputs:
                        if request.dry_run:
                            scores = {
                                s.id: (0.6 if (i % 2 == 0) else 0.4)
                                for i, s in enumerate(soluprot_inputs)
                            }
                            soluprot_scores = scores
                            passed = [
                                s
                                for s in soluprot_inputs
                                if float(scores.get(s.id, 0.0))
                                >= float(request.soluprot_cutoff)
                            ]
                            passed_ids = [s.id for s in passed]
                            write_json(
                                soluprot_path,
                                {
                                    "scores": scores,
                                    "cutoff": request.soluprot_cutoff,
                                    "passed_ids": passed_ids,
                                },
                            )
                        else:
                            if self.soluprot is None:
                                passed = soluprot_inputs
                                passed_ids = [s.id for s in passed]
                                write_json(
                                    soluprot_path,
                                    {
                                        "skipped": True,
                                        "reason": "SOLUPROT_URL not set",
                                        "cutoff": request.soluprot_cutoff,
                                        "passed_ids": passed_ids,
                                    },
                                )
                            else:
                                chain_scores: dict[str, dict[str, float]] = {}
                                child_records: list[SequenceRecord] = []
                                child_to_parent: dict[str, tuple[str, str]] = {}

                                for s in soluprot_inputs:
                                    chain_seqs = _split_multichain_sequence(s.sequence)
                                    if len(chain_seqs) <= 1:
                                        cid = str(s.id)
                                        child_to_parent[cid] = (str(s.id), "")
                                        child_records.append(
                                            SequenceRecord(
                                                id=cid,
                                                header=s.header,
                                                sequence=_clean_protein_sequence(
                                                    chain_seqs[0]
                                                ),
                                                meta={},
                                            )
                                        )
                                        continue

                                    for idx, chain_seq in enumerate(chain_seqs):
                                        label = (
                                            str(design_chains[idx]).strip()
                                            if (
                                                design_chains is not None
                                                and idx < len(design_chains)
                                            )
                                            else f"chain_{idx + 1}"
                                        )
                                        cid = f"{s.id}:{label}"
                                        child_to_parent[cid] = (str(s.id), label)
                                        child_records.append(
                                            SequenceRecord(
                                                id=cid,
                                                header=f"{s.header or s.id}|{label}",
                                                sequence=_clean_protein_sequence(
                                                    chain_seq
                                                ),
                                                meta={},
                                            )
                                        )

                                scores_by_child = self.soluprot.score(child_records)
                                for child_id, score in scores_by_child.items():
                                    parent_id, label = child_to_parent.get(
                                        child_id, (str(child_id), "")
                                    )
                                    chain_scores.setdefault(parent_id, {})[
                                        label or "chain_1"
                                    ] = float(score)

                                scores: dict[str, float] = {}
                                for s in soluprot_inputs:
                                    parent_id = str(s.id)
                                    per_chain = chain_scores.get(parent_id) or {}
                                    scores[parent_id] = (
                                        min(per_chain.values()) if per_chain else 0.0
                                    )

                                soluprot_scores = scores
                                passed = [
                                    s
                                    for s in soluprot_inputs
                                    if float(scores.get(s.id, 0.0))
                                    >= float(request.soluprot_cutoff)
                                ]
                                passed_ids = [s.id for s in passed]
                                write_json(
                                    soluprot_path,
                                    {
                                        "scores": scores,
                                        "scores_by_chain": chain_scores,
                                        "cutoff": request.soluprot_cutoff,
                                        "passed_ids": passed_ids,
                                    },
                                )
                except Exception as exc:
                    sol_error = f"soluprot_{tier_str} failed: {exc}"
                    errors.append(sol_error)
                    if not request.auto_recover:
                        raise
                    sol_recovered = True
                    sol_recovery = {
                        "attempted": True,
                        "error": sol_error,
                        "actions": ["Skipped SoluProt filter"],
                    }
                    soluprot_scores = {s.id: 1.0 for s in soluprot_inputs}
                    passed = soluprot_inputs
                    passed_ids = [s.id for s in passed]
                    write_json(
                        soluprot_path,
                        {
                            "scores": soluprot_scores,
                            "cutoff": request.soluprot_cutoff,
                            "passed_ids": passed_ids,
                            "recovered": True,
                            "error": sol_error,
                        },
                    )

                passed = _monomerize_records(passed, af2_model_preset)
                if samples:
                    _write_text(
                        tier_dir / "designs_filtered.fasta",
                        to_fasta(
                            [
                                FastaRecord(
                                    header=s.header or s.id, sequence=s.sequence
                                )
                                for s in passed
                            ]
                        ),
                    )
                set_status(
                    paths,
                    stage=f"soluprot_{tier_str}",
                    state="completed",
                    detail=("recovered" if sol_recovered else None),
                )
                _emit_panel(
                    f"soluprot_{tier_str}",
                    detail=("recovered" if sol_recovered else None),
                    error=sol_error,
                    recovery=sol_recovery,
                )

                if request.stop_after == "soluprot":
                    tier_results.append(
                        TierResult(
                            tier=tier,
                            fixed_positions=fixed_positions_by_chain,
                            proteinmpnn_native=native,
                            proteinmpnn_samples=samples,
                            mutation_report_path=mutation_report_path,
                            mutations_by_position_tsv=mutations_by_position_tsv,
                            mutations_by_position_svg=mutations_by_position_svg,
                            mutations_by_sequence_tsv=mutations_by_sequence_tsv,
                            soluprot_scores=soluprot_scores,
                            passed_ids=passed_ids,
                        )
                    )
                    continue

                af2_result = None
                af2_selected_ids: list[str] | None = None
                relax_selected_ids: list[str] | None = None
                af2_candidates = passed
                af2_budget_applied = False
                if request.af2_sequence_ids:
                    wanted = [
                        str(x).strip()
                        for x in request.af2_sequence_ids
                        if str(x).strip()
                    ]
                    if wanted:
                        wanted_set = set(wanted)
                        passed_id_set = {s.id for s in passed}
                        missing = [
                            seq_id for seq_id in wanted if seq_id not in passed_id_set
                        ]
                        if missing:
                            raise ValueError(
                                f"af2_sequence_ids not found in SoluProt-passed designs for tier={tier_str}: {missing}"
                            )
                        af2_candidates = [s for s in passed if s.id in wanted_set]
                af2_candidates_before_budget = len(af2_candidates)
                if not request.af2_sequence_ids:
                    max_candidates = max(
                        0, int(getattr(request, "af2_max_candidates_per_tier", 0) or 0)
                    )
                    if max_candidates > 0 and len(af2_candidates) > max_candidates:
                        order_by_id = {s.id: i for i, s in enumerate(af2_candidates)}

                        def _soluprot_score_for_candidate(rec: SequenceRecord) -> float:
                            if isinstance(soluprot_scores, dict):
                                raw = soluprot_scores.get(rec.id)
                                if isinstance(raw, (int, float)):
                                    return float(raw)
                            return float("-inf")

                        af2_candidates = sorted(
                            af2_candidates,
                            key=lambda rec: (
                                -_soluprot_score_for_candidate(rec),
                                order_by_id.get(rec.id, 10**9),
                            ),
                        )[:max_candidates]
                        af2_budget_applied = True
                af2_dir = tier_dir / "af2"
                if af2_candidates:
                    _ensure_not_cancelled(stage=f"af2_{tier_str}")
                    set_status(paths, stage=f"af2_{tier_str}", state="running")
                    af2_dir = _ensure_dir(af2_dir)
                    af2_scores_path = tier_dir / "af2_scores.json"
                    af2_selected_path = tier_dir / "af2_selected.fasta"
                    jobs_path = af2_dir / "runpod_jobs.json"
                    af2_recovered = False
                    af2_error: str | None = None
                    af2_recovery: dict[str, object] | None = None
                    try:
                        cached_scores: dict[str, float] = {}
                        cached_ok = False
                        if af2_scores_path.exists() and not request.force:
                            try:
                                cached = json.loads(
                                    af2_scores_path.read_text(encoding="utf-8")
                                )
                            except Exception:
                                cached = None
                            if _should_retry_cached_tier_af2(cached):
                                cached = None
                                _unlink_if_exists(jobs_path)
                            cached_scores_raw = (
                                cached.get("scores")
                                if isinstance(cached, dict)
                                else None
                            )
                            cached_model_preset = (
                                cached.get("model_preset")
                                if isinstance(cached, dict)
                                else None
                            )
                            cached_db_preset = (
                                cached.get("db_preset")
                                if isinstance(cached, dict)
                                else None
                            )
                            cached_max_template_date = (
                                cached.get("max_template_date")
                                if isinstance(cached, dict)
                                else None
                            )
                            cached_provider = (
                                cached.get("provider")
                                if isinstance(cached, dict)
                                else None
                            )
                            if (
                                isinstance(cached_scores_raw, dict)
                                and (cached_model_preset in {None, af2_model_preset})
                                and (cached_db_preset in {None, request.af2_db_preset})
                                and (
                                    cached_max_template_date
                                    in {None, request.af2_max_template_date}
                                )
                                and (cached_provider in {None, af2_provider})
                            ):
                                cached_scores = {
                                    str(k): float(v)
                                    for k, v in cached_scores_raw.items()
                                    if isinstance(v, (int, float))
                                }
                                cached_ok = True

                        candidate_ids = [s.id for s in af2_candidates]
                        candidate_records_by_id = {
                            str(record.id): record
                            for record in af2_candidates
                            if str(record.id).strip()
                        }
                        wt_compare_reference_hash = (
                            _sha256_text(wt_compare_reference_pdb_text)
                            if wt_compare_reference_pdb_text.strip()
                            else ""
                        )
                        to_predict = (
                            list(af2_candidates)
                            if request.force or not cached_ok
                            else [
                                s for s in af2_candidates if s.id not in cached_scores
                            ]
                        )
                        af2_result: dict[str, object] = {}
                        partial_prediction_errors: dict[str, str] = {}

                        if to_predict:
                            if request.dry_run:
                                af2_result = {
                                    s.id: {
                                        "best_plddt": (90.0 if (i % 2 == 0) else 80.0),
                                        "best_model": None,
                                        "ranking_debug": {},
                                        "ranked_0_pdb": None,
                                    }
                                    for i, s in enumerate(to_predict)
                                }
                            else:
                                if af2_client is None:
                                    raise RuntimeError(
                                        f"{af2_provider_label} is required for this pipeline; {af2_provider_hint}"
                                    )

                                af2_inputs = [
                                    SequenceRecord(
                                        id=s.id,
                                        header=s.header,
                                        sequence=_prepare_af2_sequence(
                                            s.sequence,
                                            model_preset=af2_model_preset,
                                            chain_ids=design_chains,
                                        ),
                                        meta=s.meta,
                                    )
                                    for s in to_predict
                                ]

                                jobs: dict[str, str] = (
                                    {} if request.force else _load_jobs_map(jobs_path)
                                )

                                def _on_af2_job_id(seq_id: str, job_id: str) -> None:
                                    jobs[seq_id] = job_id
                                    payload: dict[str, object] = {
                                        "jobs": dict(jobs),
                                        "provider": af2_provider,
                                    }
                                    if af2_endpoint_id:
                                        payload["endpoint_id"] = af2_endpoint_id
                                    write_json(jobs_path, payload)
                                    set_status(
                                        paths,
                                        stage=f"af2_{tier_str}",
                                        state="running",
                                        detail=f"runpod_job_id={job_id} seq_id={seq_id}",
                                    )

                                def _predict_af2_batch(
                                    batch_inputs: list[SequenceRecord],
                                    *,
                                    resume_job_ids: dict[str, str] | None,
                                ) -> dict[str, object]:
                                    try:
                                        return af2_client.predict(
                                            batch_inputs,
                                            model_preset=af2_model_preset,
                                            db_preset=request.af2_db_preset,
                                            max_template_date=request.af2_max_template_date,
                                            extra_flags=request.af2_extra_flags,
                                            on_job_id=_on_af2_job_id,
                                            resume_job_ids=resume_job_ids,
                                        )
                                    except TypeError:
                                        try:
                                            return af2_client.predict(
                                                batch_inputs,
                                                model_preset=af2_model_preset,
                                                db_preset=request.af2_db_preset,
                                                max_template_date=request.af2_max_template_date,
                                                extra_flags=request.af2_extra_flags,
                                                on_job_id=_on_af2_job_id,
                                            )
                                        except TypeError:
                                            return af2_client.predict(
                                                batch_inputs,
                                                model_preset=af2_model_preset,
                                                db_preset=request.af2_db_preset,
                                                max_template_date=request.af2_max_template_date,
                                                extra_flags=request.af2_extra_flags,
                                            )

                                for seq_input in af2_inputs:
                                    seq_resume_job_id = str(
                                        jobs.get(seq_input.id) or ""
                                    ).strip()
                                    seq_resume = (
                                        {seq_input.id: seq_resume_job_id}
                                        if seq_resume_job_id
                                        else None
                                    )
                                    try:
                                        rec = _predict_af2_batch(
                                            [seq_input], resume_job_ids=seq_resume
                                        )
                                    except Exception as exc:
                                        if (
                                            request.auto_recover
                                            and af2_error_is_missing_pdb_outputs(
                                                str(exc)
                                            )
                                        ):
                                            partial_prediction_errors[seq_input.id] = (
                                                str(exc)
                                            )
                                            continue
                                        raise
                                    if isinstance(rec, dict):
                                        af2_result.update(rec)

                                if partial_prediction_errors and not af2_result:
                                    first_error = next(
                                        iter(partial_prediction_errors.values())
                                    )
                                    raise RuntimeError(first_error)

                            for seq in to_predict:
                                rec = (
                                    (af2_result or {}).get(seq.id, {})
                                    if isinstance(af2_result, dict)
                                    else {}
                                )
                                if not isinstance(rec, dict):
                                    continue
                                score = rec.get("best_plddt")
                                if isinstance(score, (int, float)):
                                    cached_scores[seq.id] = float(score)

                                seq_dir = _ensure_dir(af2_dir / _safe_id(seq.id))
                                if isinstance(rec.get("ranking_debug"), dict):
                                    write_json(
                                        seq_dir / "ranking_debug.json",
                                        rec["ranking_debug"],
                                    )
                                ranked0 = rec.get("ranked_0_pdb")
                                if isinstance(ranked0, str) and ranked0.strip():
                                    _write_text(seq_dir / "ranked_0.pdb", ranked0)
                                write_json(
                                    seq_dir / "metrics.json",
                                    {
                                        "best_plddt": cached_scores.get(seq.id),
                                        "best_model": rec.get("best_model"),
                                        "archive_name": rec.get("archive_name"),
                                        "provider": af2_provider,
                                    },
                                )

                        candidate_scores = {
                            seq_id: cached_scores[seq_id]
                            for seq_id in candidate_ids
                            if seq_id in cached_scores
                        }
                        rmsd_scores: dict[str, float] = {}
                        target_rmsd_scores: dict[str, float] = {}
                        rmsd_missing: list[str] = []
                        rmsd_cutoff = float(request.af2_rmsd_cutoff)
                        if rmsd_cutoff <= 0.0:
                            rmsd_cutoff = None
                        for seq_id in candidate_ids:
                            rmsd = None
                            target_rmsd = None
                            seq_dir = _ensure_dir(af2_dir / _safe_id(seq_id))
                            metrics_path = seq_dir / "metrics.json"
                            metrics_payload: dict[str, object] | None = None
                            if metrics_path.exists():
                                try:
                                    metrics_payload = json.loads(
                                        metrics_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    metrics_payload = None
                            parent_backbone_id, parent_reference_pdb_text = (
                                _af2_candidate_parent_backbone(
                                    seq_id,
                                    candidate_records_by_id=candidate_records_by_id,
                                    backbone_pdb_by_id=backbone_pdb_by_id,
                                    fallback_pdb_text=target_pdb_text,
                                )
                            )
                            parent_reference_hash = (
                                _sha256_text(parent_reference_pdb_text)
                                if parent_reference_pdb_text.strip()
                                else ""
                            )
                            if isinstance(metrics_payload, dict):
                                rmsd = _cached_rmsd_metric(
                                    metrics_payload,
                                    key="rmsd_ca",
                                    expected_reference_hash=parent_reference_hash,
                                    reference_hash_key="rmsd_reference_hash",
                                    expected_reference_mode=_AF2_RMSD_REFERENCE_MODE_PARENT_BACKBONE,
                                    expected_backbone_id=parent_backbone_id,
                                )
                                target_rmsd = _cached_rmsd_metric(
                                    metrics_payload,
                                    key="target_rmsd_ca",
                                    expected_reference_hash=wt_compare_reference_hash,
                                    reference_hash_key="target_rmsd_reference_hash",
                                )
                            if rmsd is None or target_rmsd is None:
                                pdb_text = _extract_predicted_pdb_text(
                                    seq_id,
                                    af2_result=af2_result,
                                    af2_dir=af2_dir,
                                )
                                if pdb_text:
                                    if (
                                        rmsd is None
                                        and parent_reference_pdb_text.strip()
                                    ):
                                        rmsd_val = ca_rmsd(
                                            parent_reference_pdb_text,
                                            pdb_text,
                                            chains=design_chains,
                                        )
                                        if isinstance(rmsd_val, (int, float)):
                                            rmsd = float(rmsd_val)
                                    if (
                                        target_rmsd is None
                                        and wt_compare_reference_pdb_text.strip()
                                    ):
                                        target_rmsd_val = ca_rmsd(
                                            wt_compare_reference_pdb_text,
                                            pdb_text,
                                            chains=design_chains,
                                        )
                                        if isinstance(target_rmsd_val, (int, float)):
                                            target_rmsd = float(target_rmsd_val)
                            payload = (
                                metrics_payload
                                if isinstance(metrics_payload, dict)
                                else {}
                            )
                            if "best_plddt" not in payload and seq_id in cached_scores:
                                payload["best_plddt"] = cached_scores[seq_id]
                            payload["rmsd_ca"] = rmsd
                            payload["rmsd_reference_mode"] = (
                                _AF2_RMSD_REFERENCE_MODE_PARENT_BACKBONE
                            )
                            payload["rmsd_reference_backbone_id"] = parent_backbone_id
                            payload["rmsd_reference_hash"] = (
                                parent_reference_hash or None
                            )
                            payload["target_rmsd_ca"] = target_rmsd
                            payload["target_rmsd_reference_hash"] = (
                                wt_compare_reference_hash or None
                            )
                            write_json(metrics_path, payload)
                            if target_rmsd is not None:
                                target_rmsd_scores[seq_id] = target_rmsd
                            if rmsd is None:
                                rmsd_missing.append(seq_id)
                                continue
                            rmsd_scores[seq_id] = rmsd
                        selected_pairs = [
                            (seq_id, score)
                            for seq_id, score in candidate_scores.items()
                            if score >= float(request.af2_plddt_cutoff)
                            and (
                                rmsd_cutoff is None
                                or (
                                    seq_id in rmsd_scores
                                    and rmsd_scores[seq_id] <= rmsd_cutoff
                                )
                            )
                        ]
                        selected_pairs.sort(key=lambda t: t[1], reverse=True)
                        af2_selected_ids = [
                            seq_id
                            for seq_id, _ in selected_pairs[: int(request.af2_top_k)]
                        ]

                        selected_records = [
                            s for s in af2_candidates if s.id in set(af2_selected_ids)
                        ]
                        _write_text(
                            af2_selected_path,
                            to_fasta(
                                [
                                    FastaRecord(
                                        header=s.header or s.id, sequence=s.sequence
                                    )
                                    for s in selected_records
                                ]
                            ),
                        )
                        write_json(
                            af2_scores_path,
                            {
                                "scores": cached_scores,
                                "rmsd_scores": rmsd_scores,
                                "target_rmsd_scores": target_rmsd_scores,
                                "rmsd_reference_mode": _AF2_RMSD_REFERENCE_MODE_PARENT_BACKBONE,
                                "candidate_ids": candidate_ids,
                                "candidate_count_before_budget": af2_candidates_before_budget,
                                "candidate_count_after_budget": len(candidate_ids),
                                "candidate_budget_applied": af2_budget_applied,
                                "max_candidates_per_tier": int(
                                    getattr(request, "af2_max_candidates_per_tier", 0)
                                    or 0
                                ),
                                "cutoff": request.af2_plddt_cutoff,
                                "rmsd_cutoff": request.af2_rmsd_cutoff,
                                "rmsd_missing_ids": rmsd_missing,
                                "failed_ids": sorted(partial_prediction_errors.keys()),
                                "prediction_errors": partial_prediction_errors,
                                "top_k": request.af2_top_k,
                                "selected_ids": af2_selected_ids,
                                "model_preset": af2_model_preset,
                                "db_preset": request.af2_db_preset,
                                "max_template_date": request.af2_max_template_date,
                                "provider": af2_provider,
                                "cached": (
                                    not to_predict and cached_ok and not request.force
                                ),
                            },
                        )
                        set_status(
                            paths,
                            stage=f"af2_{tier_str}",
                            state="completed",
                            detail="cached"
                            if (not to_predict and cached_ok and not request.force)
                            else None,
                        )
                    except Exception as exc:
                        if is_cancel_requested(
                            self.output_root, run_id
                        ) or _is_cancel_error(exc):
                            raise PipelineCancelled(
                                stage=f"af2_{tier_str}",
                                message=f"run cancelled while af2_{tier_str}: {exc}",
                            ) from exc
                        af2_error = f"af2_{tier_str} failed: {exc}"
                        errors.append(af2_error)
                        if not request.auto_recover:
                            raise
                        af2_recovered = True
                        af2_recovery = {
                            "attempted": True,
                            "error": af2_error,
                            "actions": [
                                f"Selected candidates without {af2_provider_label} scoring"
                            ],
                        }
                        candidate_ids = [s.id for s in af2_candidates]
                        af2_selected_ids = candidate_ids[: int(request.af2_top_k)]
                        selected_records = [
                            s for s in af2_candidates if s.id in set(af2_selected_ids)
                        ]
                        fallback_scores = {seq_id: 0.0 for seq_id in candidate_ids}
                        _write_text(
                            af2_selected_path,
                            to_fasta(
                                [
                                    FastaRecord(
                                        header=s.header or s.id, sequence=s.sequence
                                    )
                                    for s in selected_records
                                ]
                            ),
                        )
                        write_json(
                            af2_scores_path,
                            {
                                "scores": fallback_scores,
                                "rmsd_scores": {},
                                "target_rmsd_scores": {},
                                "rmsd_reference_mode": _AF2_RMSD_REFERENCE_MODE_PARENT_BACKBONE,
                                "candidate_ids": candidate_ids,
                                "candidate_count_before_budget": af2_candidates_before_budget,
                                "candidate_count_after_budget": len(candidate_ids),
                                "candidate_budget_applied": af2_budget_applied,
                                "max_candidates_per_tier": int(
                                    getattr(request, "af2_max_candidates_per_tier", 0)
                                    or 0
                                ),
                                "cutoff": request.af2_plddt_cutoff,
                                "rmsd_cutoff": request.af2_rmsd_cutoff,
                                "rmsd_missing_ids": list(candidate_ids),
                                "top_k": request.af2_top_k,
                                "selected_ids": af2_selected_ids,
                                "model_preset": af2_model_preset,
                                "db_preset": request.af2_db_preset,
                                "max_template_date": request.af2_max_template_date,
                                "provider": af2_provider,
                                "recovered": True,
                                "error": af2_error,
                            },
                        )
                        set_status(
                            paths,
                            stage=f"af2_{tier_str}",
                            state="completed",
                            detail="recovered",
                        )
                    _emit_panel(
                        f"af2_{tier_str}",
                        detail=("recovered" if af2_recovered else None),
                        error=af2_error,
                        recovery=af2_recovery,
                    )

                relax_gate_ids = {
                    str(seq_id)
                    for seq_id in (af2_selected_ids or [])
                    if str(seq_id).strip()
                }
                relax_candidates = list(af2_candidates)
                if relax_enabled:
                    relax_dir = _ensure_dir(tier_dir / "relax")
                    relax_scores_path = tier_dir / "relax_scores.json"
                    relax_selected_path = tier_dir / "relax_selected.fasta"
                    if relax_candidates:
                        _ensure_not_cancelled(stage=f"relax_{tier_str}")
                        set_status(paths, stage=f"relax_{tier_str}", state="running")
                        relax_recovered = False
                        relax_error: str | None = None
                        relax_recovery: dict[str, object] | None = None
                        try:
                            candidate_ids = [s.id for s in relax_candidates]
                            cached_score_per_residue: dict[str, float] = {}
                            cached_total_scores: dict[str, float] = {}
                            cached_delta_total_scores: dict[str, float] = {}
                            partial_relax_errors: dict[str, str] = {}
                            cached_mode: str | None = None
                            cached_ok = False
                            if relax_scores_path.exists() and not request.force:
                                try:
                                    cached = json.loads(
                                        relax_scores_path.read_text(encoding="utf-8")
                                    )
                                except Exception:
                                    cached = None
                                cached_candidate_ids = (
                                    cached.get("candidate_ids")
                                    if isinstance(cached, dict)
                                    else None
                                )
                                cached_nstruct = (
                                    cached.get("nstruct")
                                    if isinstance(cached, dict)
                                    else None
                                )
                                cached_extra_flags = (
                                    cached.get("extra_flags")
                                    if isinstance(cached, dict)
                                    else None
                                )
                                cached_mode_raw = (
                                    cached.get("mode")
                                    if isinstance(cached, dict)
                                    else None
                                )
                                raw_score_per_residue = (
                                    cached.get("score_per_residue")
                                    if isinstance(cached, dict)
                                    and isinstance(
                                        cached.get("score_per_residue"), dict
                                    )
                                    else None
                                )
                                raw_total_scores = (
                                    cached.get("total_scores")
                                    if isinstance(cached, dict)
                                    and isinstance(cached.get("total_scores"), dict)
                                    else None
                                )
                                raw_delta_total_scores = (
                                    cached.get("delta_total_scores")
                                    if isinstance(cached, dict)
                                    and isinstance(
                                        cached.get("delta_total_scores"), dict
                                    )
                                    else None
                                )
                                raw_errors = (
                                    cached.get("errors")
                                    if isinstance(cached, dict)
                                    and isinstance(cached.get("errors"), dict)
                                    else None
                                )
                                if (
                                    not _relax_payload_has_recovered_failure(cached)
                                    and isinstance(cached_candidate_ids, list)
                                    and [str(x) for x in cached_candidate_ids]
                                    == candidate_ids
                                    and cached_nstruct
                                    in {
                                        None,
                                        max(
                                            1,
                                            int(
                                                getattr(request, "relax_nstruct", 1)
                                                or 1
                                            ),
                                        ),
                                    }
                                    and str(cached_extra_flags or "").strip()
                                    == str(
                                        getattr(request, "relax_extra_flags", "") or ""
                                    ).strip()
                                ):
                                    if isinstance(raw_score_per_residue, dict):
                                        cached_score_per_residue = {
                                            str(k): float(v)
                                            for k, v in raw_score_per_residue.items()
                                            if isinstance(v, (int, float))
                                        }
                                    if isinstance(raw_total_scores, dict):
                                        cached_total_scores = {
                                            str(k): float(v)
                                            for k, v in raw_total_scores.items()
                                            if isinstance(v, (int, float))
                                        }
                                    if isinstance(raw_delta_total_scores, dict):
                                        cached_delta_total_scores = {
                                            str(k): float(v)
                                            for k, v in raw_delta_total_scores.items()
                                            if isinstance(v, (int, float))
                                        }
                                    if isinstance(raw_errors, dict):
                                        partial_relax_errors = {
                                            str(k): str(v)
                                            for k, v in raw_errors.items()
                                            if str(k).strip() and str(v).strip()
                                        }
                                    cached_mode = (
                                        str(cached_mode_raw or "").strip() or None
                                    )
                                    cached_ok = True

                            to_relax = (
                                list(relax_candidates)
                                if request.force or not cached_ok
                                else [
                                    s
                                    for s in relax_candidates
                                    if s.id not in cached_score_per_residue
                                ]
                            )
                            relax_mode = cached_mode

                            if to_relax:
                                if request.dry_run:
                                    for seq in to_relax:
                                        seq_dir = _ensure_dir(
                                            relax_dir / _safe_id(seq.id)
                                        )
                                        seq_index = candidate_ids.index(seq.id)
                                        score_per_residue = (
                                            -3.5 if (seq_index % 2 == 0) else -2.1
                                        )
                                        total_score = score_per_residue * float(
                                            max(1, _sequence_length(seq.sequence))
                                        )
                                        input_total_score = total_score + float(
                                            max(25, _sequence_length(seq.sequence))
                                        )
                                        delta_total_score = (
                                            total_score - input_total_score
                                        )
                                        cached_score_per_residue[seq.id] = float(
                                            score_per_residue
                                        )
                                        cached_total_scores[seq.id] = float(total_score)
                                        cached_delta_total_scores[seq.id] = float(
                                            delta_total_score
                                        )
                                        write_json(
                                            seq_dir / "metrics.json",
                                            {
                                                "score_per_residue": float(
                                                    score_per_residue
                                                ),
                                                "total_score": float(total_score),
                                                "delta_total_score": float(
                                                    delta_total_score
                                                ),
                                                "input_total_score": float(
                                                    input_total_score
                                                ),
                                                "nstruct": max(
                                                    1,
                                                    int(
                                                        getattr(
                                                            request, "relax_nstruct", 1
                                                        )
                                                        or 1
                                                    ),
                                                ),
                                                "extra_flags": str(
                                                    getattr(
                                                        request, "relax_extra_flags", ""
                                                    )
                                                    or ""
                                                ).strip()
                                                or None,
                                                "mode": "dry_run",
                                                "sequence_length": _sequence_length(
                                                    seq.sequence
                                                ),
                                            },
                                        )
                                    relax_mode = "dry_run"
                                else:
                                    if rosetta_relax_client is None:
                                        raise RuntimeError(
                                            "Rosetta relax is required for relax_enabled=true"
                                        )
                                    for seq in to_relax:
                                        pdb_text = _extract_predicted_pdb_text(
                                            seq.id,
                                            af2_result=af2_result,
                                            af2_dir=af2_dir,
                                        )
                                        if not pdb_text or not pdb_text.strip():
                                            partial_relax_errors[seq.id] = (
                                                "AF2 structure unavailable for Rosetta relax"
                                            )
                                            continue
                                        try:
                                            relax_result = rosetta_relax_client.relax(
                                                pdb_text,
                                                nstruct=max(
                                                    1,
                                                    int(
                                                        getattr(
                                                            request, "relax_nstruct", 1
                                                        )
                                                        or 1
                                                    ),
                                                ),
                                                extra_flags=getattr(
                                                    request, "relax_extra_flags", None
                                                ),
                                            )
                                        except Exception as exc:
                                            partial_relax_errors[seq.id] = str(exc)
                                            continue
                                        total_score = (
                                            float(relax_result.get("total_score"))
                                            if isinstance(
                                                relax_result.get("total_score"),
                                                (int, float),
                                            )
                                            else None
                                        )
                                        score_per_residue = _score_per_residue(
                                            total_score, seq.sequence
                                        )
                                        if score_per_residue is None:
                                            partial_relax_errors[seq.id] = (
                                                "Failed to compute Rosetta score per residue"
                                            )
                                            continue
                                        delta_total_score = (
                                            float(relax_result.get("delta_total_score"))
                                            if isinstance(
                                                relax_result.get("delta_total_score"),
                                                (int, float),
                                            )
                                            else None
                                        )
                                        seq_dir = _ensure_dir(
                                            relax_dir / _safe_id(seq.id)
                                        )
                                        _write_text(
                                            seq_dir / "relaxed_best.pdb",
                                            str(
                                                relax_result.get("best_pdb_text") or ""
                                            ),
                                        )
                                        write_json(
                                            seq_dir / "metrics.json",
                                            {
                                                "score_per_residue": float(
                                                    score_per_residue
                                                ),
                                                "total_score": total_score,
                                                "delta_total_score": delta_total_score,
                                                "input_total_score": (
                                                    float(
                                                        relax_result.get(
                                                            "input_total_score"
                                                        )
                                                    )
                                                    if isinstance(
                                                        relax_result.get(
                                                            "input_total_score"
                                                        ),
                                                        (int, float),
                                                    )
                                                    else None
                                                ),
                                                "description": str(
                                                    relax_result.get("description")
                                                    or ""
                                                ).strip()
                                                or None,
                                                "nstruct": max(
                                                    1,
                                                    int(
                                                        getattr(
                                                            request, "relax_nstruct", 1
                                                        )
                                                        or 1
                                                    ),
                                                ),
                                                "extra_flags": str(
                                                    getattr(
                                                        request, "relax_extra_flags", ""
                                                    )
                                                    or ""
                                                ).strip()
                                                or None,
                                                "mode": str(
                                                    relax_result.get("mode") or ""
                                                ).strip()
                                                or None,
                                                "sequence_length": _sequence_length(
                                                    seq.sequence
                                                ),
                                            },
                                        )
                                        cached_score_per_residue[seq.id] = float(
                                            score_per_residue
                                        )
                                        if total_score is not None:
                                            cached_total_scores[seq.id] = float(
                                                total_score
                                            )
                                        if delta_total_score is not None:
                                            cached_delta_total_scores[seq.id] = float(
                                                delta_total_score
                                            )
                                        relax_mode = (
                                            str(relax_result.get("mode") or "").strip()
                                            or relax_mode
                                        )

                            if partial_relax_errors and not cached_score_per_residue:
                                first_error = next(iter(partial_relax_errors.values()))
                                raise RuntimeError(first_error)

                            relax_cutoff = (
                                float(request.relax_score_per_residue_cutoff)
                                if isinstance(
                                    request.relax_score_per_residue_cutoff, (int, float)
                                )
                                else None
                            )
                            if relax_cutoff is None:
                                relax_selected_ids = [
                                    seq_id
                                    for seq_id in candidate_ids
                                    if seq_id in relax_gate_ids
                                ]
                            else:
                                selected_pairs = [
                                    (seq_id, score)
                                    for seq_id, score in cached_score_per_residue.items()
                                    if seq_id in relax_gate_ids
                                    if score <= relax_cutoff
                                ]
                                selected_pairs.sort(key=lambda item: item[1])
                                relax_selected_ids = [
                                    seq_id for seq_id, _ in selected_pairs
                                ]

                            selected_records = [
                                s
                                for s in relax_candidates
                                if s.id in set(relax_selected_ids)
                            ]
                            _write_text(
                                relax_selected_path,
                                to_fasta(
                                    [
                                        FastaRecord(
                                            header=s.header or s.id, sequence=s.sequence
                                        )
                                        for s in selected_records
                                    ]
                                ),
                            )
                            write_json(
                                relax_scores_path,
                                {
                                    "score_per_residue": cached_score_per_residue,
                                    "total_scores": cached_total_scores,
                                    "delta_total_scores": cached_delta_total_scores,
                                    "candidate_ids": candidate_ids,
                                    "selected_ids": relax_selected_ids,
                                    "cutoff": request.relax_score_per_residue_cutoff,
                                    "nstruct": max(
                                        1,
                                        int(getattr(request, "relax_nstruct", 1) or 1),
                                    ),
                                    "extra_flags": str(
                                        getattr(request, "relax_extra_flags", "") or ""
                                    ).strip()
                                    or None,
                                    "failed_ids": sorted(partial_relax_errors.keys()),
                                    "errors": partial_relax_errors,
                                    "mode": relax_mode,
                                    "cached": (
                                        not to_relax and cached_ok and not request.force
                                    ),
                                },
                            )
                            set_status(
                                paths,
                                stage=f"relax_{tier_str}",
                                state="completed",
                                detail="cached"
                                if (not to_relax and cached_ok and not request.force)
                                else None,
                            )
                        except Exception as exc:
                            if is_cancel_requested(
                                self.output_root, run_id
                            ) or _is_cancel_error(exc):
                                raise PipelineCancelled(
                                    stage=f"relax_{tier_str}",
                                    message=f"run cancelled while relax_{tier_str}: {exc}",
                                ) from exc
                            relax_error = f"relax_{tier_str} failed: {exc}"
                            errors.append(relax_error)
                            if not request.auto_recover:
                                raise
                            relax_recovered = True
                            relax_recovery = {
                                "attempted": True,
                                "error": relax_error,
                                "actions": [
                                    "Kept AF2-selected candidates without Rosetta relax filtering"
                                ],
                            }
                            relax_selected_ids = [
                                s.id for s in relax_candidates if s.id in relax_gate_ids
                            ]
                            _write_text(
                                relax_selected_path,
                                to_fasta(
                                    [
                                        FastaRecord(
                                            header=s.header or s.id, sequence=s.sequence
                                        )
                                        for s in relax_candidates
                                        if s.id in relax_gate_ids
                                    ]
                                ),
                            )
                            write_json(
                                relax_scores_path,
                                {
                                    "score_per_residue": {},
                                    "total_scores": {},
                                    "delta_total_scores": {},
                                    "candidate_ids": [s.id for s in relax_candidates],
                                    "selected_ids": relax_selected_ids,
                                    "cutoff": request.relax_score_per_residue_cutoff,
                                    "nstruct": max(
                                        1,
                                        int(getattr(request, "relax_nstruct", 1) or 1),
                                    ),
                                    "extra_flags": str(
                                        getattr(request, "relax_extra_flags", "") or ""
                                    ).strip()
                                    or None,
                                    "recovered": True,
                                    "error": relax_error,
                                },
                            )
                            set_status(
                                paths,
                                stage=f"relax_{tier_str}",
                                state="completed",
                                detail="recovered",
                            )
                        _emit_panel(
                            f"relax_{tier_str}",
                            detail=("recovered" if relax_recovered else None),
                            error=relax_error,
                            recovery=relax_recovery,
                        )
                    else:
                        relax_selected_ids = []
                        _write_text(relax_selected_path, "")
                        write_json(
                            relax_scores_path,
                            {
                                "score_per_residue": {},
                                "total_scores": {},
                                "delta_total_scores": {},
                                "candidate_ids": [],
                                "selected_ids": [],
                                "cutoff": request.relax_score_per_residue_cutoff,
                                "nstruct": max(
                                    1, int(getattr(request, "relax_nstruct", 1) or 1)
                                ),
                                "extra_flags": str(
                                    getattr(request, "relax_extra_flags", "") or ""
                                ).strip()
                                or None,
                            },
                        )

                if normalized_stop_after == "af2" or not novelty_enabled:
                    tier_results.append(
                        TierResult(
                            tier=tier,
                            fixed_positions=fixed_positions_by_chain,
                            proteinmpnn_native=native,
                            proteinmpnn_samples=samples,
                            mutation_report_path=mutation_report_path,
                            mutations_by_position_tsv=mutations_by_position_tsv,
                            mutations_by_position_svg=mutations_by_position_svg,
                            mutations_by_sequence_tsv=mutations_by_sequence_tsv,
                            soluprot_scores=soluprot_scores,
                            passed_ids=passed_ids,
                            af2=af2_result,
                            af2_selected_ids=af2_selected_ids,
                            relax_selected_ids=relax_selected_ids,
                        )
                    )
                    continue

                novelty_tsv = None
                novelty_selected_ids = (
                    relax_selected_ids if relax_enabled else af2_selected_ids
                )
                novelty_candidates = [
                    s
                    for s in passed
                    if novelty_selected_ids and s.id in set(novelty_selected_ids)
                ]
                if novelty_candidates:
                    _ensure_not_cancelled(stage=f"novelty_{tier_str}")
                    novelty_recovered = False
                    novelty_error: str | None = None
                    novelty_recovery: dict[str, object] | None = None
                    try:
                        set_status(paths, stage=f"novelty_{tier_str}", state="running")
                        novelty_tsv_path = tier_dir / "novelty.tsv"
                        novelty_meta_path = tier_dir / "novelty.json"
                        wt_sequence = _clean_protein_sequence(
                            target_record.sequence if target_record is not None else ""
                        )
                        if not wt_sequence:
                            raise RuntimeError(
                                "WT target sequence is not available for WT Diff comparison"
                            )
                        novelty_request_hash = _stable_payload_hash(
                            {
                                "mode": "wt_sequence_diff",
                                "wt_sequence": wt_sequence,
                                "candidates": [
                                    {"id": str(s.id), "sequence": str(s.sequence)}
                                    for s in novelty_candidates
                                ],
                            }
                        )
                        novelty_meta_exists = novelty_meta_path.exists()
                        if novelty_tsv_path.exists() and not request.force:
                            try:
                                cached_tsv = novelty_tsv_path.read_text(
                                    encoding="utf-8"
                                )
                            except Exception:
                                cached_tsv = None
                            if cached_tsv is not None:
                                cached_ok = True
                                if novelty_meta_exists:
                                    try:
                                        cached_meta = json.loads(
                                            novelty_meta_path.read_text(
                                                encoding="utf-8"
                                            )
                                        )
                                    except Exception:
                                        cached_meta = None
                                    if not isinstance(cached_meta, dict):
                                        cached_ok = False
                                    else:
                                        cached_hash = str(
                                            cached_meta.get("request_hash") or ""
                                        ).strip()
                                        if (
                                            cached_hash
                                            and cached_hash != novelty_request_hash
                                        ):
                                            cached_ok = False
                                if cached_ok:
                                    novelty_tsv = cached_tsv
                                    write_json(
                                        novelty_meta_path,
                                        {
                                            "request_hash": novelty_request_hash,
                                            "mode": "wt_sequence_diff",
                                            "wt_length": len(wt_sequence),
                                            "candidate_ids": [
                                                str(s.id) for s in novelty_candidates
                                            ],
                                            "cached": True,
                                            "legacy_without_meta": (
                                                not novelty_meta_exists
                                            ),
                                        },
                                    )
                                    set_status(
                                        paths,
                                        stage=f"novelty_{tier_str}",
                                        state="completed",
                                        detail="cached",
                                    )
                                else:
                                    novelty_tsv = None

                        if novelty_tsv is None:
                            tsv_lines = [
                                "\t".join(
                                    [
                                        "query_id",
                                        "wt_identity",
                                        "wt_identity_pct",
                                        "wt_diff_ratio",
                                        "wt_diff_pct",
                                        "wt_diff_count",
                                        "compare_len",
                                        "wt_length",
                                        "design_length",
                                    ]
                                )
                            ]
                            for sample in novelty_candidates:
                                stats = _sequence_difference_stats(
                                    wt_sequence, sample.sequence
                                )
                                if not isinstance(stats, dict):
                                    continue
                                tsv_lines.append(
                                    "\t".join(
                                        [
                                            str(sample.id),
                                            f"{float(stats.get('identity') or 0.0):.6f}",
                                            f"{float(stats.get('identity_pct') or 0.0):.3f}",
                                            f"{float(stats.get('diff_ratio') or 0.0):.6f}",
                                            f"{float(stats.get('diff_pct') or 0.0):.3f}",
                                            str(int(stats.get("diff_count") or 0)),
                                            str(int(stats.get("compare_len") or 0)),
                                            str(int(stats.get("wt_length") or 0)),
                                            str(int(stats.get("design_length") or 0)),
                                        ]
                                    )
                                )
                            novelty_tsv = "\n".join(tsv_lines) + "\n"
                            _write_text(novelty_tsv_path, novelty_tsv)
                            write_json(
                                novelty_meta_path,
                                {
                                    "request_hash": novelty_request_hash,
                                    "mode": "wt_sequence_diff",
                                    "wt_length": len(wt_sequence),
                                    "candidate_ids": [
                                        str(s.id) for s in novelty_candidates
                                    ],
                                    "cached": False,
                                },
                            )
                            set_status(
                                paths, stage=f"novelty_{tier_str}", state="completed"
                            )
                    except Exception as exc:
                        if is_cancel_requested(
                            self.output_root, run_id
                        ) or _is_cancel_error(exc):
                            raise PipelineCancelled(
                                stage=f"novelty_{tier_str}",
                                message=f"run cancelled while novelty_{tier_str}: {exc}",
                            ) from exc
                        novelty_error = f"novelty_{tier_str} failed: {exc}"
                        errors.append(novelty_error)
                        if not request.auto_recover:
                            raise
                        novelty_recovered = True
                        novelty_recovery = {
                            "attempted": True,
                            "error": novelty_error,
                            "actions": ["Skipped WT Diff comparison"],
                        }
                        novelty_tsv = ""
                        _write_text(tier_dir / "novelty.tsv", novelty_tsv)
                        write_json(
                            tier_dir / "novelty.json",
                            {
                                "request_hash": _stable_payload_hash(
                                    {
                                        "mode": "wt_sequence_diff",
                                        "candidate_ids": [
                                            str(s.id) for s in novelty_candidates
                                        ],
                                    }
                                ),
                                "mode": "wt_sequence_diff",
                                "recovered": True,
                                "error": novelty_error,
                            },
                        )
                        set_status(
                            paths,
                            stage=f"novelty_{tier_str}",
                            state="completed",
                            detail="recovered",
                        )
                    _emit_panel(
                        f"novelty_{tier_str}",
                        detail=("recovered" if novelty_recovered else None),
                        error=novelty_error,
                        recovery=novelty_recovery,
                    )

                tier_results.append(
                    TierResult(
                        tier=tier,
                        fixed_positions=fixed_positions_by_chain,
                        proteinmpnn_native=native,
                        proteinmpnn_samples=samples,
                        mutation_report_path=mutation_report_path,
                        mutations_by_position_tsv=mutations_by_position_tsv,
                        mutations_by_position_svg=mutations_by_position_svg,
                        mutations_by_sequence_tsv=mutations_by_sequence_tsv,
                        soluprot_scores=soluprot_scores,
                        passed_ids=passed_ids,
                        af2=af2_result,
                        af2_selected_ids=af2_selected_ids,
                        relax_selected_ids=relax_selected_ids,
                        novelty_tsv=novelty_tsv,
                    )
                )

            _ensure_not_cancelled(stage="done")
            result = PipelineResult(
                run_id=run_id,
                output_dir=str(paths.root),
                msa_a3m_path=msa_a3m_path,
                msa_filtered_a3m_path=msa_filtered_a3m_path,
                msa_tsv_path=msa_tsv_path,
                conservation_path=conservation_path,
                ligand_mask_path=ligand_mask_path,
                surface_mask_path=surface_mask_path,
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
            if request.agent_panel_enabled:
                try:
                    write_agent_panel_report(self.output_root, run_id)
                except Exception:
                    pass
            set_status(paths, stage="done", state="completed")
            return result
        except PipelineCancelled as exc:
            errors.append(str(exc))
            set_status(paths, stage=exc.stage, state="cancelled", detail=str(exc))
            result = PipelineResult(
                run_id=run_id,
                output_dir=str(paths.root),
                msa_a3m_path=msa_a3m_path,
                msa_filtered_a3m_path=msa_filtered_a3m_path,
                msa_tsv_path=msa_tsv_path,
                conservation_path=conservation_path,
                ligand_mask_path=ligand_mask_path,
                surface_mask_path=surface_mask_path,
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
            if request.agent_panel_enabled:
                try:
                    write_agent_panel_report(self.output_root, run_id)
                except Exception:
                    pass
            raise
        except PipelineInputRequired as exc:
            errors.append(str(exc))
            set_status(paths, stage=exc.stage, state="failed", detail=str(exc))
            result = PipelineResult(
                run_id=run_id,
                output_dir=str(paths.root),
                msa_a3m_path=msa_a3m_path,
                msa_filtered_a3m_path=msa_filtered_a3m_path,
                msa_tsv_path=msa_tsv_path,
                conservation_path=conservation_path,
                ligand_mask_path=ligand_mask_path,
                surface_mask_path=surface_mask_path,
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
            if request.agent_panel_enabled:
                try:
                    write_agent_panel_report(self.output_root, run_id)
                except Exception:
                    pass
            raise
        except Exception as exc:
            errors.append(str(exc))
            set_status(paths, stage="error", state="failed", detail=str(exc))
            result = PipelineResult(
                run_id=run_id,
                output_dir=str(paths.root),
                msa_a3m_path=msa_a3m_path,
                msa_filtered_a3m_path=msa_filtered_a3m_path,
                msa_tsv_path=msa_tsv_path,
                conservation_path=conservation_path,
                ligand_mask_path=ligand_mask_path,
                surface_mask_path=surface_mask_path,
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
            if request.agent_panel_enabled:
                try:
                    write_agent_panel_report(self.output_root, run_id)
                except Exception:
                    pass
            raise

    def _get_msa(
        self,
        target_query_fasta: str,
        msa_dir: Path,
        request: PipelineRequest,
        *,
        on_job_id: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        tsv_path = msa_dir / "result.tsv"
        a3m_path = msa_dir / "result.a3m"
        meta_path = msa_dir / "request_meta.json"
        runpod_job_path = msa_dir / "runpod_job.json"
        msa_request_hash = _stable_payload_hash(
            {
                "target_query_fasta": target_query_fasta,
                "target_db": request.mmseqs_target_db,
                "max_seqs": request.mmseqs_max_seqs,
                "threads": request.mmseqs_threads,
                "use_gpu": request.mmseqs_use_gpu,
            }
        )

        if tsv_path.exists() and a3m_path.exists() and not request.force:
            if meta_path.exists():
                try:
                    cached_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    cached_meta = None
                cached_hash = (
                    str(cached_meta.get("request_hash") or "").strip()
                    if isinstance(cached_meta, dict)
                    else ""
                )
                if cached_hash and cached_hash != msa_request_hash:
                    pass
                elif cached_hash:
                    return tsv_path.read_text(encoding="utf-8"), a3m_path.read_text(
                        encoding="utf-8"
                    )
            else:
                return tsv_path.read_text(encoding="utf-8"), a3m_path.read_text(
                    encoding="utf-8"
                )

        if request.dry_run:
            tsv = ""
            query = parse_fasta(target_query_fasta)[0].sequence
            a3m = to_fasta(
                [
                    FastaRecord(header="query", sequence=query),
                    FastaRecord(header="hit1", sequence=query),
                    FastaRecord(header="hit2", sequence=query[:-1] + "A"),
                ]
            )
            _write_text(tsv_path, tsv)
            _write_text(a3m_path, a3m)
            write_json(
                meta_path,
                {
                    "request_hash": msa_request_hash,
                    "query_sha256": _sha256_text(target_query_fasta),
                    "query_length": len(query),
                    "cached": False,
                    "dry_run": True,
                },
            )
            return tsv, a3m

        if self.mmseqs is None:
            raise RuntimeError("MMseqs client is not configured")

        if runpod_job_path.exists() and not request.force:
            try:
                meta = json.loads(runpod_job_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
            job_id = meta.get("job_id")
            if isinstance(job_id, str) and job_id.strip():
                same_request = True
                if isinstance(meta, dict):
                    cached_hash = str(meta.get("request_hash") or "").strip()
                    if cached_hash and cached_hash != msa_request_hash:
                        same_request = False
                    expected = {
                        "target_db": request.mmseqs_target_db,
                        "max_seqs": request.mmseqs_max_seqs,
                        "threads": request.mmseqs_threads,
                        "use_gpu": request.mmseqs_use_gpu,
                    }
                    for k, v in expected.items():
                        if k in meta and meta.get(k) != v:
                            same_request = False
                            break
                if same_request:
                    if on_job_id is not None:
                        on_job_id(job_id)
                    out = self.mmseqs.wait_job(job_id.strip())
                    tsv = str(out.get("tsv") or "")
                    a3m_b64 = out.get("a3m_gz_b64")
                    if not a3m_b64:
                        raise RuntimeError(
                            "MMseqs search did not return A3M (a3m_gz_b64 is empty)"
                        )
                    a3m = decode_a3m_gz_b64(str(a3m_b64))
                    _write_text(tsv_path, tsv)
                    _write_text(a3m_path, a3m)
                    write_json(
                        meta_path,
                        {
                            "request_hash": msa_request_hash,
                            "query_sha256": _sha256_text(target_query_fasta),
                            "query_length": len(
                                parse_fasta(target_query_fasta)[0].sequence
                            ),
                            "cached": False,
                        },
                    )
                    return tsv, a3m

        out = self.mmseqs.search(
            query_fasta=target_query_fasta,
            target_db=request.mmseqs_target_db,
            threads=request.mmseqs_threads,
            use_gpu=request.mmseqs_use_gpu,
            include_taxonomy=False,
            return_a3m=True,
            max_seqs=request.mmseqs_max_seqs,
            on_job_id=on_job_id,
        )
        tsv = str(out.get("tsv") or "")
        a3m_b64 = out.get("a3m_gz_b64")
        if not a3m_b64:
            raise RuntimeError("MMseqs search did not return A3M (a3m_gz_b64 is empty)")
        a3m = decode_a3m_gz_b64(str(a3m_b64))
        _write_text(tsv_path, tsv)
        _write_text(a3m_path, a3m)
        write_json(
            meta_path,
            {
                "request_hash": msa_request_hash,
                "query_sha256": _sha256_text(target_query_fasta),
                "query_length": len(parse_fasta(target_query_fasta)[0].sequence),
                "cached": False,
            },
        )
        return tsv, a3m

    def _run_proteinmpnn(
        self,
        tier_dir: Path,
        request: PipelineRequest,
        *,
        pdb_text: str,
        tier_str: str,
        design_chains: list[str] | None,
        fixed_positions_by_chain: dict[str, list[int]],
        on_job_id: Callable[[str], None] | None = None,
    ) -> tuple[SequenceRecord | None, list[SequenceRecord]]:
        out_json = tier_dir / "proteinmpnn.json"
        out_fasta = tier_dir / "designs.fasta"
        out_fixed_positions_check = tier_dir / "fixed_positions_check.json"
        expected_fixed_positions = {
            k: sorted(set(int(x) for x in v))
            for k, v in fixed_positions_by_chain.items()
        }
        expected_request = {
            "pdb_path_chains": sorted(design_chains) if design_chains else None,
            "use_soluble_model": True,
            "model_name": "v_48_020",
            "num_seq_per_target": int(request.num_seq_per_tier),
            "batch_size": int(request.batch_size),
            "sampling_temp": float(request.sampling_temp),
            "seed": int(request.seed),
            "backbone_noise": 0.0,
        }
        expected_input_hash = _stable_payload_hash(
            {
                "pdb_sha256": _sha256_text(pdb_text),
                "target_fasta_sha256": _sha256_text(str(request.target_fasta or "")),
                "design_chains": sorted(design_chains) if design_chains else None,
                "fixed_positions": expected_fixed_positions,
                "dry_run": bool(request.dry_run),
            }
        )
        expected_request_hash = _stable_payload_hash(
            {
                "request": expected_request,
                "input_hash": expected_input_hash,
            }
        )

        if out_json.exists() and out_fasta.exists() and not request.force:
            try:
                payload = json.loads(out_json.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            native = payload.get("native")
            samples = payload.get("samples")
            cached_fixed_positions = _normalize_fixed_positions_by_chain(
                payload.get("fixed_positions")
            )
            cached_request = payload.get("request")
            cached_request_hash = str(payload.get("request_hash") or "").strip()
            cached_input_hash = str(payload.get("input_hash") or "").strip()

            if (
                cached_fixed_positions is None
                or cached_fixed_positions != expected_fixed_positions
            ):
                pass
            elif cached_request_hash:
                if cached_request_hash != expected_request_hash:
                    pass
                else:
                    native_rec = None
                    if isinstance(native, dict) and native.get("sequence"):
                        native_rec = SequenceRecord(
                            id=str(native.get("id") or "native"),
                            sequence=str(native["sequence"]),
                            header=str(native.get("header") or "native"),
                        )
                    sample_recs: list[SequenceRecord] = []
                    if isinstance(samples, list):
                        for s in samples:
                            if not isinstance(s, dict) or not s.get("sequence"):
                                continue
                            sample_recs.append(
                                SequenceRecord(
                                    id=str(s.get("id") or s.get("header") or "sample"),
                                    sequence=str(s["sequence"]),
                                    header=str(
                                        s.get("header") or s.get("id") or "sample"
                                    ),
                                    meta={},
                                )
                            )
                    if request.dry_run:
                        write_json(
                            out_fixed_positions_check,
                            {
                                "ok": True,
                                "skipped": True,
                                "reason": "dry_run",
                                "fixed_positions_total": sum(
                                    len(v) for v in expected_fixed_positions.values()
                                ),
                            },
                        )
                    elif not _env_true("PIPELINE_SKIP_FIXED_POSITIONS_CHECK"):
                        check = _validate_proteinmpnn_fixed_positions(
                            pdb_text=pdb_text,
                            design_chains=design_chains,
                            fixed_positions_by_chain=cached_fixed_positions,
                            native=native_rec,
                            samples=sample_recs,
                        )
                        write_json(out_fixed_positions_check, check)
                        if not bool(check.get("ok")):
                            raise RuntimeError(
                                f"ProteinMPNN output violates fixed_positions (cached) for tier={tier_str}; see {out_fixed_positions_check}"
                            )
                    return native_rec, sample_recs
            elif cached_input_hash and cached_input_hash != expected_input_hash:
                pass
            elif (
                not isinstance(cached_request, dict)
                or cached_request != expected_request
            ):
                pass
            else:
                native_rec = None
                if isinstance(native, dict) and native.get("sequence"):
                    native_rec = SequenceRecord(
                        id=str(native.get("id") or "native"),
                        sequence=str(native["sequence"]),
                        header=str(native.get("header") or "native"),
                    )
                sample_recs: list[SequenceRecord] = []
                if isinstance(samples, list):
                    for s in samples:
                        if not isinstance(s, dict) or not s.get("sequence"):
                            continue
                        sample_recs.append(
                            SequenceRecord(
                                id=str(s.get("id") or s.get("header") or "sample"),
                                sequence=str(s["sequence"]),
                                header=str(s.get("header") or s.get("id") or "sample"),
                                meta={},
                            )
                        )
                if request.dry_run:
                    write_json(
                        out_fixed_positions_check,
                        {
                            "ok": True,
                            "skipped": True,
                            "reason": "dry_run",
                            "fixed_positions_total": sum(
                                len(v) for v in expected_fixed_positions.values()
                            ),
                        },
                    )
                elif not _env_true("PIPELINE_SKIP_FIXED_POSITIONS_CHECK"):
                    check = _validate_proteinmpnn_fixed_positions(
                        pdb_text=pdb_text,
                        design_chains=design_chains,
                        fixed_positions_by_chain=cached_fixed_positions,
                        native=native_rec,
                        samples=sample_recs,
                    )
                    write_json(out_fixed_positions_check, check)
                    if not bool(check.get("ok")):
                        raise RuntimeError(
                            f"ProteinMPNN output violates fixed_positions (cached) for tier={tier_str}; see {out_fixed_positions_check}"
                        )
                return native_rec, sample_recs

        if request.dry_run:
            if str(request.target_fasta or "").strip():
                query = parse_fasta(request.target_fasta)[0].sequence
            else:
                extracted = sequence_by_chain(pdb_text, chains=design_chains)
                if not extracted:
                    raise ValueError(
                        "Unable to derive dry_run query sequence from target_pdb ATOM records"
                    )
                chain_order = (
                    sorted(design_chains) if design_chains else sorted(extracted.keys())
                )
                query = "".join(extracted.get(chain_id, "") for chain_id in chain_order)
            samples = [
                SequenceRecord(
                    id=f"{tier_str}_s1", header=f"{tier_str},sample=1", sequence=query
                ),
                SequenceRecord(
                    id=f"{tier_str}_s2",
                    header=f"{tier_str},sample=2",
                    sequence=query[:-1] + "A",
                ),
            ]
            native = SequenceRecord(id="native", header="native", sequence=query)
            _write_text(
                out_fasta,
                to_fasta(
                    [
                        FastaRecord(header=s.header or s.id, sequence=s.sequence)
                        for s in [native, *samples]
                    ]
                ),
            )
            write_json(
                out_json,
                {
                    "request": {
                        **expected_request,
                    },
                    "request_hash": expected_request_hash,
                    "input_hash": expected_input_hash,
                    "native": native.__dict__,
                    "samples": [s.__dict__ for s in samples],
                    "fixed_positions": expected_fixed_positions,
                },
            )
            write_json(
                out_fixed_positions_check,
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "dry_run",
                    "fixed_positions_total": sum(
                        len(v) for v in fixed_positions_by_chain.values()
                    ),
                },
            )
            return native, samples

        if self.proteinmpnn is None:
            raise RuntimeError("ProteinMPNN client is not configured")

        native, samples, raw = self.proteinmpnn.design(
            pdb_text=pdb_text,
            pdb_name="input",
            pdb_path_chains=design_chains or None,
            fixed_positions=fixed_positions_by_chain,
            use_soluble_model=True,
            model_name="v_48_020",
            num_seq_per_target=request.num_seq_per_tier,
            batch_size=request.batch_size,
            sampling_temp=request.sampling_temp,
            seed=request.seed,
            on_job_id=on_job_id,
        )
        _write_text(
            out_fasta,
            to_fasta(
                [
                    FastaRecord(
                        header=native.header or native.id, sequence=native.sequence
                    )
                ]
                + [
                    FastaRecord(header=s.header or s.id, sequence=s.sequence)
                    for s in samples
                ]
            ),
        )
        write_json(
            out_json,
            {
                "request": {
                    **expected_request,
                },
                "request_hash": expected_request_hash,
                "input_hash": expected_input_hash,
                "native": native.__dict__,
                "samples": [s.__dict__ for s in samples],
                "fixed_positions": expected_fixed_positions,
                "raw": _safe_json(raw),
            },
        )
        if not _env_true("PIPELINE_SKIP_FIXED_POSITIONS_CHECK"):
            check = _validate_proteinmpnn_fixed_positions(
                pdb_text=pdb_text,
                design_chains=design_chains,
                fixed_positions_by_chain=fixed_positions_by_chain,
                native=native,
                samples=samples,
            )
            write_json(out_fixed_positions_check, check)
            if not bool(check.get("ok")):
                raise RuntimeError(
                    f"ProteinMPNN output violates fixed_positions for tier={tier_str}; see {out_fixed_positions_check}"
                )
        return native, samples
