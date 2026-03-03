from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
from dataclasses import replace
import base64
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from .bio.fasta import parse_fasta
from .bio.sdf import append_ligand_pdb
from .bio.sdf import sdf_to_pdb
from .models import PipelineRequest
from .models import SequenceRecord
from .pipeline import PipelineRunner
from .pipeline import _prepare_af2_sequence
from .pipeline import _resolve_af2_model_preset
from .pipeline import _split_multichain_sequence
from .router import request_from_prompt
from .router import plan_from_prompt
from .storage import init_run
from .storage import list_runs
from .storage import new_run_id
from .storage import normalize_run_id
from .storage import load_status
from .storage import list_artifacts
from .storage import read_artifact
from .storage import set_status
from .storage import write_json


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _as_text(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, dict):
        for key in ("value", "text", "content", "data"):
            if key in value:
                return _as_text(value.get(key))
    if isinstance(value, list):
        if all(isinstance(v, str) for v in value):
            return "\n".join(value)
        if all(isinstance(v, (bytes, bytearray)) for v in value):
            return b"\n".join(bytes(v) for v in value).decode("utf-8", errors="replace")
    return str(value)


_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _safe_id(value: str) -> str:
    safe = _SAFE_ID_RE.sub("_", str(value or "")).strip("._-")
    return safe[:128] or "id"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_json(obj: object) -> object:
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def _as_dict(value: object | None, *, name: str) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _as_dict_str(value: object | None, *, name: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    out: dict[str, str] = {}
    for k, v in value.items():
        if v is None:
            continue
        out[str(k)] = _as_text(v)
    return out or None


def _as_str_or_list(value: object | None) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return str(value)


def _as_list_of_str(value: object | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            out.append(str(item))
        return out
    return [str(value)]


def _as_list_of_float(value: object | None) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        out: list[float] = []
        for item in value:
            if isinstance(item, (int, float)):
                out.append(float(item))
            elif isinstance(item, str) and item.strip():
                out.append(float(item.strip()))
        return out
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str) and value.strip():
        return [float(value.strip())]
    return None


def _as_fixed_positions_extra(value: object | None) -> dict[str, list[int]] | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        positions = sorted({int(str(item).strip()) for item in value if item is not None})
        positions = [pos for pos in positions if pos > 0]
        return {"*": positions} if positions else None
    if not isinstance(value, dict):
        raise ValueError("fixed_positions_extra must be an object (e.g. {'A':[1,2,3]})")

    out: dict[str, list[int]] = {}
    for raw_chain, raw_positions in value.items():
        chain = str(raw_chain)
        if raw_positions is None:
            continue
        positions_raw = raw_positions if isinstance(raw_positions, list) else [raw_positions]
        positions = sorted({int(str(item).strip()) for item in positions_raw if item is not None})
        positions = [pos for pos in positions if pos > 0]
        if positions:
            out[chain] = positions
    return out or None


def _as_bool(value: object | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _as_int(value: object | None, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(float(value.strip()))
    return default


def _as_float(value: object | None, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value.strip())
    return default


@dataclass(frozen=True)
class AutoRetryConfig:
    enabled: bool
    max_attempts: int
    backoff_s: float


def _auto_retry_config(args: dict[str, Any]) -> AutoRetryConfig:
    enabled = _as_bool(args.get("auto_retry"), _env_true("PIPELINE_AUTO_RETRY"))
    max_attempts = _as_int(args.get("auto_retry_max"), _env_int("PIPELINE_AUTO_RETRY_MAX", 2))
    backoff_s = _as_float(args.get("auto_retry_backoff_s"), _env_float("PIPELINE_AUTO_RETRY_BACKOFF_S", 10.0))
    if not enabled:
        return AutoRetryConfig(enabled=False, max_attempts=1, backoff_s=0.0)
    return AutoRetryConfig(enabled=True, max_attempts=max(1, max_attempts), backoff_s=max(0.0, backoff_s))


def _retry_request(request: PipelineRequest, error: str) -> tuple[PipelineRequest, str] | None:
    msg = error.lower()

    if "persistent db" in msg and "not found" in msg:
        if request.mmseqs_target_db.lower() != "uniref90":
            return (
                replace(request, mmseqs_target_db="uniref90", force=True),
                "fallback mmseqs_target_db=uniref90",
            )

    if "unable to extract protein sequence from target_pdb" in msg and request.design_chains:
        return (replace(request, design_chains=None, force=True), "retry without design_chains")

    if "timed out" in msg or "timeout" in msg or "timed_out" in msg:
        if request.mmseqs_max_seqs > 100:
            new_max = max(50, int(request.mmseqs_max_seqs / 2))
            return (
                replace(request, mmseqs_max_seqs=new_max, force=True),
                f"reduce mmseqs_max_seqs to {new_max}",
            )

    if "runpod job not completed" in msg or "mmseqs error" in msg or "a3m" in msg:
        return (replace(request, force=True), "retry runpod job")

    return None


def _run_with_auto_retry(
    runner: PipelineRunner,
    request: PipelineRequest,
    *,
    run_id: str | None,
    retry: AutoRetryConfig,
) -> PipelineResult:
    attempt = 1
    while True:
        try:
            return runner.run(request, run_id=run_id)
        except Exception as exc:
            if not retry.enabled or attempt >= retry.max_attempts:
                raise
            decision = _retry_request(request, str(exc))
            if decision is None:
                raise
            request, _ = decision
            if retry.backoff_s > 0:
                time.sleep(retry.backoff_s)
            attempt += 1


def pipeline_request_from_args(args: dict[str, Any]) -> PipelineRequest:
    target_fasta = _as_text(args.get("target_fasta"))
    target_pdb = _as_text(args.get("target_pdb"))
    rfd3_inputs = _as_dict(args.get("rfd3_inputs"), name="rfd3_inputs")
    rfd3_inputs_text = _as_text(args.get("rfd3_inputs_text")).strip() or None
    rfd3_contig = _as_str_or_list(args.get("rfd3_contig"))
    rfd3_input_files = _as_dict_str(args.get("rfd3_input_files"), name="rfd3_input_files")
    rfd3_input_pdb = _as_text(args.get("rfd3_input_pdb")).strip() or None
    rfd3_ligand = _as_str_or_list(args.get("rfd3_ligand"))
    rfd3_select_unfixed_sequence = _as_text(args.get("rfd3_select_unfixed_sequence")).strip() or None
    rfd3_cli_args = _as_text(args.get("rfd3_cli_args")).strip() or None
    rfd3_env = _as_dict_str(args.get("rfd3_env"), name="rfd3_env")
    rfd3_design_index = _as_int(args.get("rfd3_design_index"), 0)
    rfd3_use_ensemble = _as_bool(args.get("rfd3_use_ensemble"), False)
    rfd3_max_return_designs = _as_int(args.get("rfd3_max_return_designs"), 50)
    rfd3_partial_t = _as_int(args.get("rfd3_partial_t"), 20)

    bioemu_use = _as_bool(args.get("bioemu_use"), False)
    bioemu_sequence = _as_text(args.get("bioemu_sequence")).strip() or None
    bioemu_num_samples = _as_int(args.get("bioemu_num_samples"), 50)
    bioemu_batch_size_100 = (
        _as_int(args.get("bioemu_batch_size_100"), 50)
        if str(args.get("bioemu_batch_size_100") or "").strip()
        else None
    )
    bioemu_model_name = str(args.get("bioemu_model_name") or "bioemu-v1.1")
    bioemu_filter_samples = _as_bool(args.get("bioemu_filter_samples"), True)
    bioemu_base_seed = (
        _as_int(args.get("bioemu_base_seed"), 0)
        if str(args.get("bioemu_base_seed") or "").strip()
        else None
    )
    bioemu_max_return_structures = _as_int(args.get("bioemu_max_return_structures"), 50)
    bioemu_env = _as_dict_str(args.get("bioemu_env"), name="bioemu_env")

    diffdock_ligand_smiles = _as_text(args.get("diffdock_ligand_smiles")).strip() or None
    diffdock_ligand_sdf = _as_text(args.get("diffdock_ligand_sdf")).strip() or None
    diffdock_config = str(args.get("diffdock_config") or "default_inference_args.yaml")
    diffdock_extra_args = _as_text(args.get("diffdock_extra_args")).strip() or None
    diffdock_cuda_visible_devices = _as_text(args.get("diffdock_cuda_visible_devices")).strip() or None

    has_rfd3 = bool(rfd3_inputs_text or rfd3_inputs or rfd3_contig or rfd3_input_files)
    if not target_fasta.strip() and not target_pdb.strip() and not has_rfd3:
        raise ValueError("One of target_fasta or target_pdb or rfd3 inputs is required")

    stop_after = (str(args.get("stop_after")).strip().lower() if args.get("stop_after") else None)
    dry_run = _as_bool(args.get("dry_run"), False)

    design_chains = _as_list_of_str(args.get("design_chains"))
    fixed_positions_extra = _as_fixed_positions_extra(args.get("fixed_positions_extra"))
    conservation_tiers = _as_list_of_float(args.get("conservation_tiers"))
    ligand_resnames = _as_list_of_str(args.get("ligand_resnames"))
    ligand_atom_chains = _as_list_of_str(args.get("ligand_atom_chains"))
    af2_sequence_ids = _as_list_of_str(args.get("af2_sequence_ids"))

    return PipelineRequest(
        target_fasta=target_fasta,
        target_pdb=target_pdb,
        rfd3_inputs=rfd3_inputs,
        rfd3_inputs_text=rfd3_inputs_text,
        rfd3_input_files=rfd3_input_files,
        rfd3_input_pdb=rfd3_input_pdb,
        rfd3_spec_name=str(args.get("rfd3_spec_name") or "spec-1"),
        rfd3_contig=rfd3_contig,
        rfd3_ligand=rfd3_ligand,
        rfd3_select_unfixed_sequence=rfd3_select_unfixed_sequence,
        rfd3_cli_args=rfd3_cli_args,
        rfd3_env=rfd3_env,
        rfd3_design_index=rfd3_design_index,
        rfd3_use_ensemble=rfd3_use_ensemble,
        rfd3_max_return_designs=max(1, int(rfd3_max_return_designs)),
        rfd3_partial_t=int(rfd3_partial_t),
        bioemu_use=bioemu_use,
        bioemu_sequence=bioemu_sequence,
        bioemu_num_samples=max(1, int(bioemu_num_samples)),
        bioemu_batch_size_100=(int(bioemu_batch_size_100) if bioemu_batch_size_100 is not None else None),
        bioemu_model_name=bioemu_model_name,
        bioemu_filter_samples=bioemu_filter_samples,
        bioemu_base_seed=(int(bioemu_base_seed) if bioemu_base_seed is not None else None),
        bioemu_max_return_structures=max(1, int(bioemu_max_return_structures)),
        bioemu_env=bioemu_env,
        diffdock_ligand_smiles=diffdock_ligand_smiles,
        diffdock_ligand_sdf=diffdock_ligand_sdf,
        diffdock_config=diffdock_config,
        diffdock_extra_args=diffdock_extra_args,
        diffdock_cuda_visible_devices=diffdock_cuda_visible_devices,
        design_chains=design_chains,
        fixed_positions_extra=fixed_positions_extra,
        conservation_tiers=conservation_tiers or [0.3, 0.5, 0.7],
        conservation_mode=str(args.get("conservation_mode") or "quantile"),
        conservation_weighting=str(args.get("conservation_weighting") or "none"),
        conservation_cluster_method=str(args.get("conservation_cluster_method") or "linclust"),
        conservation_cluster_min_seq_id=_as_float(args.get("conservation_cluster_min_seq_id"), 0.9),
        conservation_cluster_coverage=(
            _as_float(args.get("conservation_cluster_coverage"), 0.0)
            if str(args.get("conservation_cluster_coverage") or "").strip()
            else None
        ),
        conservation_cluster_cov_mode=(
            _as_int(args.get("conservation_cluster_cov_mode"), 0)
            if str(args.get("conservation_cluster_cov_mode") or "").strip()
            else None
        ),
        conservation_cluster_kmer_per_seq=(
            _as_int(args.get("conservation_cluster_kmer_per_seq"), 0)
            if str(args.get("conservation_cluster_kmer_per_seq") or "").strip()
            else None
        ),
        ligand_mask_distance=_as_float(args.get("ligand_mask_distance"), 6.0),
        ligand_resnames=ligand_resnames,
        ligand_atom_chains=ligand_atom_chains,
        pdb_strip_nonpositive_resseq=_as_bool(args.get("pdb_strip_nonpositive_resseq"), False),
        pdb_renumber_resseq_from_1=_as_bool(args.get("pdb_renumber_resseq_from_1"), False),
        num_seq_per_tier=_as_int(args.get("num_seq_per_tier"), 16),
        batch_size=_as_int(args.get("batch_size"), 1),
        sampling_temp=_as_float(args.get("sampling_temp"), 0.1),
        seed=_as_int(args.get("seed"), 0),
        soluprot_cutoff=_as_float(args.get("soluprot_cutoff"), 0.5),
        af2_model_preset=str(args.get("af2_model_preset") or "auto"),
        af2_db_preset=str(args.get("af2_db_preset") or "full_dbs"),
        af2_max_template_date=str(args.get("af2_max_template_date") or "2020-05-14"),
        af2_extra_flags=(str(args.get("af2_extra_flags")) if args.get("af2_extra_flags") else None),
        af2_plddt_cutoff=_as_float(args.get("af2_plddt_cutoff"), 85.0),
        af2_rmsd_cutoff=_as_float(args.get("af2_rmsd_cutoff"), 2.0),
        af2_top_k=_as_int(args.get("af2_top_k"), 20),
        af2_sequence_ids=af2_sequence_ids,
        mmseqs_target_db=str(args.get("mmseqs_target_db") or "uniref90"),
        mmseqs_max_seqs=_as_int(args.get("mmseqs_max_seqs"), 3000),
        mmseqs_threads=_as_int(args.get("mmseqs_threads"), 4),
        mmseqs_use_gpu=_as_bool(
            args.get("mmseqs_use_gpu"),
            _env_true("PIPELINE_MMSEQS_USE_GPU") or _env_true("MMSEQS_USE_GPU"),
        ),
        novelty_target_db=str(args.get("novelty_target_db") or "uniref90"),
        msa_min_coverage=_as_float(args.get("msa_min_coverage"), 0.0),
        msa_min_identity=_as_float(args.get("msa_min_identity"), 0.0),
        query_pdb_min_identity=_as_float(args.get("query_pdb_min_identity"), 0.9),
        query_pdb_policy=str(args.get("query_pdb_policy") or "error"),
        stop_after=stop_after,
        force=_as_bool(args.get("force"), False),
        dry_run=dry_run,
    )


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "pipeline.run",
            "description": "Run the full protein design pipeline (MMseqs2→mask→ProteinMPNN→SoluProt→AF2→novelty).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target_fasta": {"type": "string"},
                    "target_pdb": {"type": "string"},
                    "rfd3_inputs": {"type": "object"},
                    "rfd3_inputs_text": {"type": "string"},
                    "rfd3_input_files": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                    "rfd3_input_pdb": {"type": "string"},
                    "rfd3_spec_name": {"type": "string"},
                    "rfd3_contig": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                    "rfd3_ligand": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                    "rfd3_select_unfixed_sequence": {"type": "string"},
                    "rfd3_cli_args": {"type": "string"},
                    "rfd3_env": {"type": "object", "additionalProperties": {"type": "string"}},
                    "rfd3_design_index": {"type": "integer"},
                    "rfd3_use_ensemble": {"type": "boolean"},
                    "rfd3_max_return_designs": {"type": "integer"},
                    "rfd3_partial_t": {"type": "integer"},
                    "bioemu_use": {"type": "boolean"},
                    "bioemu_sequence": {"type": "string"},
                    "bioemu_num_samples": {"type": "integer"},
                    "bioemu_batch_size_100": {"type": "integer"},
                    "bioemu_model_name": {"type": "string"},
                    "bioemu_filter_samples": {"type": "boolean"},
                    "bioemu_base_seed": {"type": "integer"},
                    "bioemu_max_return_structures": {"type": "integer"},
                    "bioemu_env": {"type": "object", "additionalProperties": {"type": "string"}},
                    "diffdock_ligand_smiles": {"type": "string"},
                    "diffdock_ligand_sdf": {"type": "string"},
                    "diffdock_config": {"type": "string"},
                    "diffdock_extra_args": {"type": "string"},
                    "diffdock_cuda_visible_devices": {"type": "string"},
                    "design_chains": {"type": "array", "items": {"type": "string"}},
                    "fixed_positions_extra": {
                        "type": "object",
                        "additionalProperties": {"type": "array", "items": {"type": "integer"}},
                        "description": "Extra fixed positions per chain (1-based, query/FASTA numbering). Use '*' to apply to all chains.",
                    },
                    "conservation_tiers": {"type": "array", "items": {"type": "number"}},
                    "conservation_mode": {"type": "string", "enum": ["quantile", "threshold"]},
                    "conservation_weighting": {"type": "string"},
                    "conservation_cluster_method": {"type": "string"},
                    "conservation_cluster_min_seq_id": {"type": "number"},
                    "conservation_cluster_coverage": {"type": "number"},
                    "conservation_cluster_cov_mode": {"type": "integer"},
                    "conservation_cluster_kmer_per_seq": {"type": "integer"},
                    "ligand_mask_distance": {"type": "number"},
                    "ligand_resnames": {"type": "array", "items": {"type": "string"}},
                    "ligand_atom_chains": {"type": "array", "items": {"type": "string"}},
                    "pdb_strip_nonpositive_resseq": {"type": "boolean"},
                    "pdb_renumber_resseq_from_1": {"type": "boolean"},
                    "num_seq_per_tier": {"type": "integer"},
                    "batch_size": {"type": "integer"},
                    "sampling_temp": {"type": "number"},
                    "seed": {"type": "integer"},
                    "soluprot_cutoff": {"type": "number"},
                    "af2_model_preset": {"type": "string"},
                    "af2_db_preset": {"type": "string"},
                    "af2_max_template_date": {"type": "string"},
                    "af2_extra_flags": {"type": "string"},
                    "af2_plddt_cutoff": {"type": "number"},
                    "af2_rmsd_cutoff": {"type": "number"},
                    "af2_top_k": {"type": "integer"},
                    "af2_sequence_ids": {"type": "array", "items": {"type": "string"}},
                    "mmseqs_target_db": {"type": "string"},
                    "mmseqs_max_seqs": {"type": "integer"},
                    "mmseqs_threads": {"type": "integer"},
                    "mmseqs_use_gpu": {"type": "boolean"},
                    "novelty_target_db": {"type": "string"},
                    "msa_min_coverage": {"type": "number"},
                    "msa_min_identity": {"type": "number"},
                    "query_pdb_min_identity": {"type": "number"},
                    "query_pdb_policy": {"type": "string", "enum": ["error", "warn", "ignore"]},
                    "run_id": {"type": "string"},
                    "stop_after": {
                        "type": "string",
                        "enum": ["rfd3", "bioemu", "msa", "design", "soluprot", "af2", "novelty"],
                    },
                    "force": {"type": "boolean"},
                    "dry_run": {"type": "boolean"},
                    "auto_retry": {"type": "boolean"},
                    "auto_retry_max": {"type": "integer"},
                    "auto_retry_backoff_s": {"type": "number"},
                },
                "anyOf": [
                    {"required": ["target_fasta"]},
                    {"required": ["target_pdb"]},
                    {"required": ["rfd3_inputs"]},
                    {"required": ["rfd3_inputs_text"]},
                    {"required": ["rfd3_contig"]},
                ],
            },
        },
        {
            "name": "pipeline.run_af2",
            "description": "Run AlphaFold2 on provided FASTA (no full pipeline).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fasta": {
                        "type": "string",
                        "description": "FASTA text (one or more sequences).",
                    },
                    "sequence": {
                        "type": "string",
                        "description": "Single sequence (non-FASTA).",
                    },
                    "sequence_id": {"type": "string"},
                    "af2_model_preset": {"type": "string"},
                    "af2_db_preset": {"type": "string"},
                    "af2_max_template_date": {"type": "string"},
                    "af2_extra_flags": {"type": "string"},
                    "af2_chain_ids": {"type": "array", "items": {"type": "string"}},
                    "run_id": {"type": "string"},
                    "force": {"type": "boolean"},
                    "dry_run": {"type": "boolean"},
                },
                "anyOf": [{"required": ["fasta"]}, {"required": ["sequence"]}],
            },
        },
        {
            "name": "pipeline.run_diffdock",
            "description": "Run DiffDock on a protein PDB + ligand (no full pipeline).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "protein_pdb": {"type": "string"},
                    "ligand_smiles": {"type": "string"},
                    "ligand_sdf": {"type": "string"},
                    "complex_name": {"type": "string"},
                    "diffdock_config": {"type": "string"},
                    "diffdock_extra_args": {"type": "string"},
                    "diffdock_cuda_visible_devices": {"type": "string"},
                    "run_id": {"type": "string"},
                    "force": {"type": "boolean"},
                    "dry_run": {"type": "boolean"},
                },
                "anyOf": [
                    {"required": ["protein_pdb", "ligand_smiles"]},
                    {"required": ["protein_pdb", "ligand_sdf"]},
                ],
            },
        },
        {
            "name": "pipeline.plan_from_prompt",
            "description": "Route a natural-language prompt and return missing inputs/questions without running.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "target_fasta": {"type": "string"},
                    "target_pdb": {"type": "string"},
                    "rfd3_input_pdb": {"type": "string"},
                    "rfd3_contig": {"type": "string"},
                    "diffdock_ligand_smiles": {"type": "string"},
                    "diffdock_ligand_sdf": {"type": "string"},
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "pipeline.run_from_prompt",
            "description": "Route a natural-language prompt to a pipeline request and run it.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "target_fasta": {"type": "string"},
                    "target_pdb": {"type": "string"},
                    "run_id": {"type": "string"},
                    "auto_retry": {"type": "boolean"},
                    "auto_retry_max": {"type": "integer"},
                    "auto_retry_backoff_s": {"type": "number"},
                },
                "required": ["prompt"],
                "anyOf": [{"required": ["target_fasta"]}, {"required": ["target_pdb"]}],
            },
        },
        {
            "name": "pipeline.status",
            "description": "Get run status by run_id.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "pipeline.list_runs",
            "description": "List recent run_ids.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
        {
            "name": "pipeline.list_artifacts",
            "description": "List artifact paths under a run_id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "prefix": {"type": "string"},
                    "max_depth": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["run_id"],
            },
        },
        {
            "name": "pipeline.read_artifact",
            "description": "Read an artifact file under a run_id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "path": {"type": "string"},
                    "max_bytes": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "encoding": {"type": "string"},
                    "base64": {"type": "boolean"},
                },
                "required": ["run_id", "path"],
            },
        },
    ]


@dataclass(frozen=True)
class ToolDispatcher:
    runner: PipelineRunner

    def list_tools(self) -> dict[str, Any]:
        return {"tools": tool_definitions()}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "pipeline.run":
            run_id = arguments.get("run_id")
            req = pipeline_request_from_args(arguments)
            retry = _auto_retry_config(arguments)
            normalized_run_id = normalize_run_id(str(run_id)) if run_id is not None else None
            if retry.enabled and normalized_run_id is None:
                normalized_run_id = new_run_id("pipeline")
            res = _run_with_auto_retry(self.runner, req, run_id=normalized_run_id, retry=retry)
            return {"run_id": res.run_id, "output_dir": res.output_dir, "summary": asdict(res)}

        if name == "pipeline.run_af2":
            run_id = arguments.get("run_id")
            normalized_run_id = normalize_run_id(str(run_id)) if run_id is not None else new_run_id("af2")
            dry_run = _as_bool(arguments.get("dry_run"), False)
            force = _as_bool(arguments.get("force"), False)

            fasta_text = _as_text(arguments.get("fasta") or arguments.get("target_fasta")).strip()
            sequence_text = _as_text(arguments.get("sequence")).strip()
            sequence_id = str(arguments.get("sequence_id") or "seq1").strip() or "seq1"

            if fasta_text:
                parsed = parse_fasta(fasta_text)
                raw_records = [
                    SequenceRecord(id=rec.id, header=rec.header, sequence=rec.sequence) for rec in parsed
                ]
            elif sequence_text:
                raw_records = [
                    SequenceRecord(id=sequence_id, header=sequence_id, sequence=sequence_text)
                ]
            else:
                raise ValueError("fasta or sequence is required")

            chain_ids = _as_list_of_str(arguments.get("af2_chain_ids"))
            requested_preset = str(arguments.get("af2_model_preset") or "auto")
            chain_counts = [len(_split_multichain_sequence(rec.sequence)) for rec in raw_records]
            if requested_preset.strip().lower() in {"", "auto"} and len(set(chain_counts)) > 1:
                raise ValueError(
                    "Mixed chain counts in input. Set af2_model_preset explicitly or run each group separately."
                )
            chain_count = max(chain_counts) if chain_counts else 1
            resolved_preset = _resolve_af2_model_preset(requested_preset, chain_count=chain_count)

            af2_inputs: list[SequenceRecord] = []
            for rec in raw_records:
                prepared = _prepare_af2_sequence(
                    rec.sequence,
                    model_preset=resolved_preset,
                    chain_ids=chain_ids,
                )
                af2_inputs.append(
                    SequenceRecord(
                        id=rec.id,
                        header=rec.header,
                        sequence=prepared,
                        meta=dict(rec.meta) if isinstance(rec.meta, dict) else {},
                    )
                )

            paths = init_run(self.runner.output_root, normalized_run_id)
            set_status(paths, stage="af2", state="running")

            af2_dir = paths.root / "af2"
            af2_dir.mkdir(parents=True, exist_ok=True)
            result_path = af2_dir / "result.json"

            request_payload = {
                "tool": "pipeline.run_af2",
                "input": {
                    "fasta": fasta_text or None,
                    "sequence": sequence_text or None,
                    "sequence_id": sequence_id,
                    "af2_model_preset": requested_preset,
                    "af2_db_preset": str(arguments.get("af2_db_preset") or "full_dbs"),
                    "af2_max_template_date": str(arguments.get("af2_max_template_date") or "2020-05-14"),
                    "af2_extra_flags": str(arguments.get("af2_extra_flags") or "").strip() or None,
                    "af2_chain_ids": chain_ids,
                },
            }
            write_json(paths.request_json, request_payload)

            if result_path.exists() and not force:
                summary = {
                    "run_id": normalized_run_id,
                    "output_dir": str(paths.root),
                    "af2_dir": str(af2_dir),
                    "result_path": str(result_path),
                    "cached": True,
                }
                write_json(paths.summary_json, summary)
                set_status(paths, stage="af2", state="completed", detail="cached")
                return summary

            input_fasta_path = af2_dir / "input.fasta"
            if fasta_text:
                _write_text(input_fasta_path, fasta_text)
            else:
                _write_text(input_fasta_path, f">{sequence_id}\n{sequence_text}\n")

            if dry_run:
                summary = {
                    "run_id": normalized_run_id,
                    "output_dir": str(paths.root),
                    "af2_dir": str(af2_dir),
                    "result_path": None,
                    "dry_run": True,
                    "resolved_preset": resolved_preset,
                }
                write_json(paths.summary_json, summary)
                set_status(paths, stage="af2", state="completed", detail="dry_run")
                return summary

            if self.runner.af2 is None:
                raise RuntimeError(
                    "AlphaFold2 endpoint is not configured (set ALPHAFOLD2_ENDPOINT_ID or AF2_URL)"
                )

            jobs_path = af2_dir / "runpod_jobs.json"

            def _on_job_id(seq_id: str, job_id: str) -> None:
                payload: dict[str, dict[str, str]] = {"jobs": {seq_id: job_id}}
                if jobs_path.exists():
                    try:
                        existing = json.loads(jobs_path.read_text(encoding="utf-8"))
                    except Exception:
                        existing = None
                    if isinstance(existing, dict) and isinstance(existing.get("jobs"), dict):
                        merged = dict(existing["jobs"])
                        merged[seq_id] = job_id
                        payload["jobs"] = merged
                write_json(jobs_path, payload)
                set_status(paths, stage="af2", state="running", detail=f"runpod_job_id={job_id}")

            try:
                result = self.runner.af2.predict(
                    af2_inputs,
                    model_preset=resolved_preset,
                    db_preset=str(arguments.get("af2_db_preset") or "full_dbs"),
                    max_template_date=str(arguments.get("af2_max_template_date") or "2020-05-14"),
                    extra_flags=(str(arguments.get("af2_extra_flags")) if arguments.get("af2_extra_flags") else None),
                    on_job_id=_on_job_id,
                )
            except TypeError:
                result = self.runner.af2.predict(
                    af2_inputs,
                    model_preset=resolved_preset,
                    db_preset=str(arguments.get("af2_db_preset") or "full_dbs"),
                    max_template_date=str(arguments.get("af2_max_template_date") or "2020-05-14"),
                    extra_flags=(str(arguments.get("af2_extra_flags")) if arguments.get("af2_extra_flags") else None),
                )

            write_json(result_path, _safe_json(result))

            sequence_outputs: list[dict[str, object]] = []
            if isinstance(result, dict):
                for rec in af2_inputs:
                    seq_out: dict[str, object] = {"id": rec.id}
                    rec_payload = result.get(rec.id)
                    if isinstance(rec_payload, dict):
                        seq_dir = af2_dir / _safe_id(rec.id)
                        seq_dir.mkdir(parents=True, exist_ok=True)
                        ranked0 = rec_payload.get("ranked_0_pdb") or rec_payload.get("pdb") or rec_payload.get(
                            "pdb_text"
                        )
                        if isinstance(ranked0, str) and ranked0.strip():
                            ranked0_path = seq_dir / "ranked_0.pdb"
                            _write_text(ranked0_path, ranked0)
                            seq_out["ranked_0_pdb"] = str(ranked0_path)
                        ranking_debug = rec_payload.get("ranking_debug")
                        if isinstance(ranking_debug, dict):
                            ranking_path = seq_dir / "ranking_debug.json"
                            write_json(ranking_path, ranking_debug)
                            seq_out["ranking_debug"] = str(ranking_path)
                        best_plddt = rec_payload.get("best_plddt")
                        if isinstance(best_plddt, (int, float)):
                            seq_out["best_plddt"] = float(best_plddt)
                    sequence_outputs.append(seq_out)

            summary = {
                "run_id": normalized_run_id,
                "output_dir": str(paths.root),
                "af2_dir": str(af2_dir),
                "result_path": str(result_path),
                "resolved_preset": resolved_preset,
                "sequences": sequence_outputs,
            }
            write_json(paths.summary_json, summary)
            set_status(paths, stage="af2", state="completed")
            return summary

        if name == "pipeline.run_diffdock":
            run_id = arguments.get("run_id")
            normalized_run_id = normalize_run_id(str(run_id)) if run_id is not None else new_run_id("diffdock")
            dry_run = _as_bool(arguments.get("dry_run"), False)
            force = _as_bool(arguments.get("force"), False)

            protein_pdb = _as_text(arguments.get("protein_pdb") or arguments.get("target_pdb")).strip()
            ligand_smiles = _as_text(
                arguments.get("ligand_smiles") or arguments.get("diffdock_ligand_smiles")
            ).strip()
            ligand_sdf = _as_text(
                arguments.get("ligand_sdf") or arguments.get("diffdock_ligand_sdf")
            ).strip()
            complex_name = str(arguments.get("complex_name") or "complex").strip() or "complex"

            if not protein_pdb:
                raise ValueError("protein_pdb is required")
            if not (ligand_smiles or ligand_sdf):
                raise ValueError("ligand_smiles or ligand_sdf is required")

            paths = init_run(self.runner.output_root, normalized_run_id)
            set_status(paths, stage="diffdock", state="running")

            diffdock_dir = paths.root / "diffdock"
            diffdock_dir.mkdir(parents=True, exist_ok=True)
            output_path = diffdock_dir / "output.json"

            request_payload = {
                "tool": "pipeline.run_diffdock",
                "input": {
                    "complex_name": complex_name,
                    "diffdock_config": str(arguments.get("diffdock_config") or "default_inference_args.yaml"),
                    "diffdock_extra_args": str(arguments.get("diffdock_extra_args") or "").strip() or None,
                    "diffdock_cuda_visible_devices": str(arguments.get("diffdock_cuda_visible_devices") or "")
                    .strip()
                    or None,
                    "ligand_smiles": ligand_smiles or None,
                    "ligand_sdf": ligand_sdf or None,
                },
            }
            write_json(paths.request_json, request_payload)

            if output_path.exists() and not force:
                summary = {
                    "run_id": normalized_run_id,
                    "output_dir": str(paths.root),
                    "diffdock_dir": str(diffdock_dir),
                    "output_path": str(output_path),
                    "cached": True,
                }
                write_json(paths.summary_json, summary)
                set_status(paths, stage="diffdock", state="completed", detail="cached")
                return summary

            _write_text(diffdock_dir / "protein.pdb", protein_pdb)
            if ligand_sdf:
                _write_text(diffdock_dir / "ligand.sdf", ligand_sdf)
            if ligand_smiles:
                _write_text(diffdock_dir / "ligand.smiles", ligand_smiles)

            if dry_run:
                summary = {
                    "run_id": normalized_run_id,
                    "output_dir": str(paths.root),
                    "diffdock_dir": str(diffdock_dir),
                    "output_path": None,
                    "dry_run": True,
                }
                write_json(paths.summary_json, summary)
                set_status(paths, stage="diffdock", state="completed", detail="dry_run")
                return summary

            if self.runner.diffdock is None:
                raise RuntimeError("DiffDock endpoint is not configured (set DIFFDOCK_ENDPOINT_ID)")

            def _on_job_id(job_id: str) -> None:
                write_json(diffdock_dir / "runpod_job.json", {"job_id": job_id})
                set_status(paths, stage="diffdock", state="running", detail=f"runpod_job_id={job_id}")

            diffdock_out = self.runner.diffdock.dock(
                protein_pdb=protein_pdb,
                ligand_smiles=ligand_smiles or None,
                ligand_sdf=ligand_sdf or None,
                complex_name=_safe_id(complex_name),
                config=str(arguments.get("diffdock_config") or "default_inference_args.yaml"),
                extra_args=str(arguments.get("diffdock_extra_args") or "").strip() or None,
                cuda_visible_devices=str(arguments.get("diffdock_cuda_visible_devices") or "").strip() or None,
                on_job_id=_on_job_id,
            )

            output_payload = diffdock_out.get("output") or {}
            write_json(output_path, _safe_json(output_payload))
            zip_bytes = diffdock_out.get("zip_bytes")
            if isinstance(zip_bytes, (bytes, bytearray)):
                (diffdock_dir / "out_dir.zip").write_bytes(bytes(zip_bytes))

            sdf_text = str(diffdock_out.get("sdf_text") or "")
            if sdf_text.strip():
                _write_text(diffdock_dir / "rank1.sdf", sdf_text)
                ligand_pdb = sdf_to_pdb(sdf_text)
                _write_text(diffdock_dir / "ligand.pdb", ligand_pdb)
                complex_pdb = append_ligand_pdb(protein_pdb, ligand_pdb)
                _write_text(diffdock_dir / "complex.pdb", complex_pdb)

            summary = {
                "run_id": normalized_run_id,
                "output_dir": str(paths.root),
                "diffdock_dir": str(diffdock_dir),
                "output_path": str(output_path),
                "rank1_sdf": str(diffdock_dir / "rank1.sdf") if (diffdock_dir / "rank1.sdf").exists() else None,
                "complex_pdb": str(diffdock_dir / "complex.pdb") if (diffdock_dir / "complex.pdb").exists() else None,
            }
            write_json(paths.summary_json, summary)
            set_status(paths, stage="diffdock", state="completed")
            return summary

        if name == "pipeline.plan_from_prompt":
            prompt = str(arguments.get("prompt") or "")
            target_fasta = _as_text(arguments.get("target_fasta"))
            target_pdb = _as_text(arguments.get("target_pdb"))
            rfd3_input_pdb = _as_text(arguments.get("rfd3_input_pdb"))
            rfd3_contig = str(arguments.get("rfd3_contig") or "").strip() or None
            diffdock_ligand_smiles = _as_text(arguments.get("diffdock_ligand_smiles"))
            diffdock_ligand_sdf = _as_text(arguments.get("diffdock_ligand_sdf"))
            return plan_from_prompt(
                prompt=prompt,
                target_fasta=target_fasta,
                target_pdb=target_pdb,
                rfd3_input_pdb=rfd3_input_pdb,
                rfd3_contig=rfd3_contig,
                diffdock_ligand_smiles=diffdock_ligand_smiles,
                diffdock_ligand_sdf=diffdock_ligand_sdf,
            )

        if name == "pipeline.run_from_prompt":
            run_id = arguments.get("run_id")
            retry = _auto_retry_config(arguments)
            prompt = str(arguments.get("prompt") or "")
            target_fasta = _as_text(arguments.get("target_fasta"))
            target_pdb = _as_text(arguments.get("target_pdb"))
            if not target_fasta.strip() and not target_pdb.strip():
                raise ValueError("One of target_fasta or target_pdb is required")
            req = request_from_prompt(prompt=prompt, target_fasta=target_fasta, target_pdb=target_pdb)
            normalized_run_id = normalize_run_id(str(run_id)) if run_id is not None else None
            if retry.enabled and normalized_run_id is None:
                normalized_run_id = new_run_id("pipeline")
            res = _run_with_auto_retry(self.runner, req, run_id=normalized_run_id, retry=retry)
            return {"routed_request": asdict(req), "run_id": res.run_id, "output_dir": res.output_dir, "summary": asdict(res)}

        if name == "pipeline.status":
            run_id = str(arguments.get("run_id") or "")
            if not run_id:
                raise ValueError("run_id is required")
            status = load_status(self.runner.output_root, run_id)
            if status is None:
                return {"run_id": run_id, "found": False}
            return {"run_id": run_id, "found": True, "status": status}

        if name == "pipeline.list_runs":
            limit = arguments.get("limit")
            return {"runs": list_runs(self.runner.output_root, limit=int(limit) if limit is not None else 50)}

        if name == "pipeline.list_artifacts":
            run_id = str(arguments.get("run_id") or "")
            if not run_id:
                raise ValueError("run_id is required")
            prefix = arguments.get("prefix")
            max_depth = _as_int(arguments.get("max_depth"), 4)
            limit = _as_int(arguments.get("limit"), 200)
            artifacts = list_artifacts(
                self.runner.output_root,
                run_id,
                prefix=str(prefix) if prefix is not None else None,
                max_depth=max_depth,
                limit=limit,
            )
            return {"run_id": run_id, "artifacts": artifacts}

        if name == "pipeline.read_artifact":
            run_id = str(arguments.get("run_id") or "")
            path = str(arguments.get("path") or "")
            if not run_id:
                raise ValueError("run_id is required")
            if not path:
                raise ValueError("path is required")
            max_bytes = _as_int(arguments.get("max_bytes"), 2_000_000)
            offset = _as_int(arguments.get("offset"), 0)
            encoding = str(arguments.get("encoding") or "utf-8")
            as_base64 = _as_bool(arguments.get("base64"), False)
            data, meta = read_artifact(
                self.runner.output_root,
                run_id,
                path=path,
                max_bytes=max_bytes,
                offset=offset,
            )
            if as_base64:
                meta["base64"] = base64.b64encode(data).decode("ascii")
                return {"run_id": run_id, **meta}
            meta["encoding"] = encoding
            meta["text"] = data.decode(encoding, errors="replace")
            return {"run_id": run_id, **meta}

        raise ValueError(f"Unknown tool: {name}")
