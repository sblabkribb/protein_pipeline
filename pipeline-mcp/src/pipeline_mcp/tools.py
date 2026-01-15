from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
from dataclasses import replace
import os
import time
from typing import Any

from .models import PipelineRequest
from .pipeline import PipelineRunner
from .router import request_from_prompt
from .storage import list_runs
from .storage import new_run_id
from .storage import normalize_run_id
from .storage import load_status


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
    if not target_fasta.strip() and not target_pdb.strip():
        raise ValueError("One of target_fasta or target_pdb is required")

    stop_after = (str(args.get("stop_after")).strip().lower() if args.get("stop_after") else None)
    dry_run = _as_bool(args.get("dry_run"), False)

    design_chains = _as_list_of_str(args.get("design_chains"))
    conservation_tiers = _as_list_of_float(args.get("conservation_tiers"))
    ligand_resnames = _as_list_of_str(args.get("ligand_resnames"))
    af2_sequence_ids = _as_list_of_str(args.get("af2_sequence_ids"))

    return PipelineRequest(
        target_fasta=target_fasta,
        target_pdb=target_pdb,
        design_chains=design_chains,
        conservation_tiers=conservation_tiers or [0.3, 0.5, 0.7],
        conservation_mode=str(args.get("conservation_mode") or "quantile"),
        ligand_mask_distance=_as_float(args.get("ligand_mask_distance"), 6.0),
        ligand_resnames=ligand_resnames,
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
        af2_top_k=_as_int(args.get("af2_top_k"), 20),
        af2_sequence_ids=af2_sequence_ids,
        mmseqs_target_db=str(args.get("mmseqs_target_db") or "uniref90"),
        mmseqs_max_seqs=_as_int(args.get("mmseqs_max_seqs"), 3000),
        mmseqs_threads=_as_int(args.get("mmseqs_threads"), 4),
        mmseqs_use_gpu=_as_bool(args.get("mmseqs_use_gpu"), False),
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
                    "design_chains": {"type": "array", "items": {"type": "string"}},
                    "conservation_tiers": {"type": "array", "items": {"type": "number"}},
                    "conservation_mode": {"type": "string", "enum": ["quantile", "threshold"]},
                    "ligand_mask_distance": {"type": "number"},
                    "ligand_resnames": {"type": "array", "items": {"type": "string"}},
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
                    "stop_after": {"type": "string"},
                    "force": {"type": "boolean"},
                    "dry_run": {"type": "boolean"},
                    "auto_retry": {"type": "boolean"},
                    "auto_retry_max": {"type": "integer"},
                    "auto_retry_backoff_s": {"type": "number"},
                },
                "anyOf": [{"required": ["target_fasta"]}, {"required": ["target_pdb"]}],
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

        raise ValueError(f"Unknown tool: {name}")
