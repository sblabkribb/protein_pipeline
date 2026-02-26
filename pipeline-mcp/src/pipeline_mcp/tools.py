from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
from dataclasses import replace
import copy
import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from .bio.fasta import FastaRecord
from .bio.fasta import parse_fasta
from .bio.sdf import append_ligand_pdb
from .bio.sdf import sdf_to_pdb
from .models import PipelineRequest
from .models import SequenceRecord
from .pipeline import PipelineRunner
from .pipeline import _dummy_backbone_pdb
from .pipeline import _prepare_af2_sequence
from .pipeline import _resolve_af2_model_preset
from .pipeline import _safe_id
from .pipeline import _safe_json
from .pipeline import _split_multichain_sequence
from .pipeline import _target_record_from_pdb
from .pipeline import _tier_key
from .pipeline import _write_text
from .preflight import preflight_request
from .router import request_from_prompt
from .router import plan_from_prompt
from .storage import ensure_dir
from .storage import init_run
from .storage import RunPaths
from .storage import list_run_events
from .storage import list_runs
from .storage import new_run_id
from .storage import normalize_run_id
from .storage import load_status
from .storage import list_artifacts
from .storage import read_artifact
from .storage import delete_run
from .storage import append_run_event
from .storage import read_json
from .storage import resolve_run_path
from .report_scoring import compute_score
from .report_scoring import scoring_config
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


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _as_reason_list(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
        return [p for p in parts if p]
    return [str(value).strip()]


def _as_metrics(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception as exc:
            raise ValueError("metrics must be a JSON object") from exc
        if not isinstance(parsed, dict):
            raise ValueError("metrics must be a JSON object")
        return {str(k): v for k, v in parsed.items()}
    return None


def _normalize_user(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key in ("id", "username", "role", "email", "org"):
            if key in value and value[key] is not None:
                out[key] = value[key]
        if out:
            return out
    if isinstance(value, str) and value.strip():
        return {"username": value.strip()}
    return None


def _parse_fasta_or_sequence(text: str) -> list[FastaRecord]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("target_fasta is required")
    if raw.lstrip().startswith(">"):
        return parse_fasta(raw)
    seq = "".join(ch for ch in raw.split())
    if not seq:
        raise ValueError("target_fasta is empty")
    return [FastaRecord(header="sequence", sequence=seq)]


def _af2_records_from_inputs(
    *,
    target_fasta: str,
    target_pdb: str,
    model_preset: str,
) -> tuple[list[SequenceRecord], str]:
    if target_fasta.strip():
        fasta_records = _parse_fasta_or_sequence(target_fasta)
    elif target_pdb.strip():
        fasta_records = [_target_record_from_pdb(target_pdb, design_chains=None)]
    else:
        raise ValueError("One of target_fasta or target_pdb is required")

    chain_counts = [len(_split_multichain_sequence(rec.sequence)) for rec in fasta_records]
    max_chains = max(chain_counts) if chain_counts else 1
    resolved_preset = _resolve_af2_model_preset(model_preset, chain_count=max_chains)

    seq_records: list[SequenceRecord] = []
    for rec in fasta_records:
        prepared = _prepare_af2_sequence(rec.sequence, model_preset=resolved_preset, chain_ids=None)
        seq_records.append(SequenceRecord(id=rec.id, sequence=prepared, header=rec.header, meta={}))
    return seq_records, resolved_preset


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


def _run_af2_predict(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = arguments.get("run_id")
    target_fasta = _as_text(arguments.get("target_fasta"))
    target_pdb = _as_text(arguments.get("target_pdb"))
    dry_run = _as_bool(arguments.get("dry_run"), False)

    requested_preset = str(arguments.get("af2_model_preset") or "auto")
    db_preset = str(arguments.get("af2_db_preset") or "full_dbs")
    max_template_date = str(arguments.get("af2_max_template_date") or "2020-05-14")
    extra_flags = (str(arguments.get("af2_extra_flags")) if arguments.get("af2_extra_flags") else None)

    normalized_run_id = normalize_run_id(str(run_id)) if run_id is not None else new_run_id("af2")
    paths = init_run(runner.output_root, normalized_run_id)
    set_status(paths, stage="af2", state="running")

    request_payload = {
        "target_fasta": target_fasta,
        "target_pdb": target_pdb,
        "af2_model_preset": requested_preset,
        "af2_db_preset": db_preset,
        "af2_max_template_date": max_template_date,
        "af2_extra_flags": extra_flags,
        "dry_run": dry_run,
    }
    write_json(paths.request_json, _safe_json(request_payload))

    af2_dir = ensure_dir(paths.root / "af2")
    jobs: dict[str, str] = {}

    def _on_job_id(seq_id: str, job_id: str) -> None:
        jobs[seq_id] = job_id
        write_json(af2_dir / "runpod_jobs.json", {"jobs": dict(jobs)})
        set_status(paths, stage="af2", state="running", detail=f"runpod_job_id={job_id} seq_id={seq_id}")

    try:
        seq_records, resolved_preset = _af2_records_from_inputs(
            target_fasta=target_fasta,
            target_pdb=target_pdb,
            model_preset=requested_preset,
        )

        if dry_run:
            def _first_chain(seq: str) -> str:
                raw = str(seq or "").strip()
                if "\n>" in raw:
                    raw = raw.split("\n>", 1)[0]
                if "/" in raw:
                    raw = raw.split("/", 1)[0]
                cleaned = "".join(ch for ch in raw if ch.isalpha())
                return cleaned or "A"

            results = {}
            for rec in seq_records:
                seq = _first_chain(rec.sequence)
                results[rec.id] = {
                    "best_plddt": 90.0,
                    "best_model": None,
                    "ranking_debug": {},
                    "ranked_0_pdb": _dummy_backbone_pdb(seq, chain_id="A"),
                }
        else:
            if runner.af2 is None:
                raise RuntimeError("AlphaFold2 is not configured (set ALPHAFOLD2_ENDPOINT_ID or AF2_URL)")
            try:
                results = runner.af2.predict(
                    seq_records,
                    model_preset=resolved_preset,
                    db_preset=db_preset,
                    max_template_date=max_template_date,
                    extra_flags=extra_flags,
                    on_job_id=_on_job_id,
                )
            except TypeError:
                results = runner.af2.predict(
                    seq_records,
                    model_preset=resolved_preset,
                    db_preset=db_preset,
                    max_template_date=max_template_date,
                    extra_flags=extra_flags,
                )

        if not isinstance(results, dict):
            raise RuntimeError(f"AlphaFold2 output invalid: {type(results).__name__}")

        summary_results: dict[str, dict[str, Any]] = {}
        for rec in seq_records:
            payload = results.get(rec.id)
            if not isinstance(payload, dict):
                raise RuntimeError(f"AlphaFold2 output missing record for {rec.id}")

            ranked0 = payload.get("ranked_0_pdb") or payload.get("pdb") or payload.get("pdb_text")
            if not isinstance(ranked0, str) or not ranked0.strip():
                raise RuntimeError(f"AlphaFold2 output missing ranked_0.pdb for {rec.id}")

            seq_dir = ensure_dir(af2_dir / _safe_id(rec.id))
            _write_text(seq_dir / "ranked_0.pdb", ranked0)
            if isinstance(payload.get("ranking_debug"), dict):
                write_json(seq_dir / "ranking_debug.json", payload["ranking_debug"])
            write_json(
                seq_dir / "metrics.json",
                {
                    "best_plddt": payload.get("best_plddt"),
                    "best_model": payload.get("best_model"),
                    "archive_name": payload.get("archive_name"),
                },
            )
            summary_results[rec.id] = {
                "best_plddt": payload.get("best_plddt"),
                "best_model": payload.get("best_model"),
            }

        write_json(af2_dir / "results.json", _safe_json(results))
        summary = {
            "run_id": normalized_run_id,
            "output_dir": str(paths.root),
            "af2": summary_results,
            "af2_model_preset": resolved_preset,
        }
        write_json(paths.summary_json, _safe_json(summary))
        set_status(paths, stage="done", state="completed")
        return {"run_id": normalized_run_id, "output_dir": str(paths.root), "summary": summary}
    except Exception as exc:
        set_status(paths, stage="error", state="failed", detail=str(exc))
        error_summary = {
            "run_id": normalized_run_id,
            "output_dir": str(paths.root),
            "errors": [str(exc)],
        }
        write_json(paths.summary_json, _safe_json(error_summary))
        raise


def _run_diffdock(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = arguments.get("run_id")
    protein_pdb = _as_text(arguments.get("protein_pdb")) or _as_text(arguments.get("target_pdb"))
    ligand_smiles = _as_text(arguments.get("diffdock_ligand_smiles")) or _as_text(arguments.get("ligand_smiles"))
    ligand_sdf = _as_text(arguments.get("diffdock_ligand_sdf")) or _as_text(arguments.get("ligand_sdf"))
    complex_name = str(arguments.get("complex_name") or "complex")
    diffdock_config = str(arguments.get("diffdock_config") or "default_inference_args.yaml")
    diffdock_extra_args = _as_text(arguments.get("diffdock_extra_args")).strip() or None
    diffdock_cuda_visible_devices = _as_text(arguments.get("diffdock_cuda_visible_devices")).strip() or None
    dry_run = _as_bool(arguments.get("dry_run"), False)

    if not protein_pdb.strip():
        raise ValueError("protein_pdb is required")
    if not (ligand_smiles.strip() or ligand_sdf.strip()):
        raise ValueError("diffdock_ligand_smiles or diffdock_ligand_sdf is required")

    normalized_run_id = normalize_run_id(str(run_id)) if run_id is not None else new_run_id("diffdock")
    paths = init_run(runner.output_root, normalized_run_id)
    set_status(paths, stage="diffdock", state="running")

    request_payload = {
        "protein_pdb": protein_pdb,
        "diffdock_ligand_smiles": ligand_smiles or None,
        "diffdock_ligand_sdf": ligand_sdf or None,
        "complex_name": complex_name,
        "diffdock_config": diffdock_config,
        "diffdock_extra_args": diffdock_extra_args,
        "diffdock_cuda_visible_devices": diffdock_cuda_visible_devices,
        "dry_run": dry_run,
    }
    write_json(paths.request_json, _safe_json(request_payload))

    diffdock_dir = ensure_dir(paths.root / "diffdock")
    _write_text(diffdock_dir / "protein.pdb", protein_pdb)
    if ligand_sdf.strip():
        _write_text(diffdock_dir / "ligand.sdf", ligand_sdf)
    else:
        _write_text(diffdock_dir / "ligand.smiles", ligand_smiles)

    def _on_job_id(job_id: str) -> None:
        write_json(diffdock_dir / "runpod_job.json", {"job_id": job_id})
        set_status(paths, stage="diffdock", state="running", detail=f"runpod_job_id={job_id}")

    try:
        if dry_run:
            output_payload = {"dry_run": True}
            sdf_text = ligand_sdf if ligand_sdf.strip() else ""
        else:
            if runner.diffdock is None:
                raise RuntimeError("DiffDock endpoint is not configured (set DIFFDOCK_ENDPOINT_ID)")
            diffdock_out = runner.diffdock.dock(
                protein_pdb=protein_pdb,
                ligand_smiles=ligand_smiles or None,
                ligand_sdf=ligand_sdf or None,
                complex_name=complex_name,
                config=diffdock_config,
                extra_args=diffdock_extra_args,
                cuda_visible_devices=diffdock_cuda_visible_devices,
                on_job_id=_on_job_id,
            )
            output_payload = diffdock_out.get("output") or {}
            zip_bytes = diffdock_out.get("zip_bytes")
            if isinstance(zip_bytes, (bytes, bytearray)):
                (diffdock_dir / "out_dir.zip").write_bytes(bytes(zip_bytes))
            sdf_text = str(diffdock_out.get("sdf_text") or "")

        write_json(diffdock_dir / "output.json", _safe_json(output_payload))
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
        }
        write_json(paths.summary_json, _safe_json(summary))
        set_status(paths, stage="done", state="completed")
        return {"run_id": normalized_run_id, "output_dir": str(paths.root), "summary": summary}
    except Exception as exc:
        set_status(paths, stage="error", state="failed", detail=str(exc))
        error_summary = {
            "run_id": normalized_run_id,
            "output_dir": str(paths.root),
            "errors": [str(exc)],
        }
        write_json(paths.summary_json, _safe_json(error_summary))
        raise


def _delete_run_tool(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "")
    if not run_id:
        raise ValueError("run_id is required")
    force = _as_bool(arguments.get("force"), False)
    status = load_status(runner.output_root, run_id)
    if status is not None and str(status.get("state") or "").lower() == "running" and not force:
        raise ValueError("run is still running; stop it or set force=true to delete anyway")
    return delete_run(runner.output_root, run_id)


def _cancel_run_tool(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "")
    if not run_id:
        raise ValueError("run_id is required")
    root = resolve_run_path(runner.output_root, run_id)
    if not root.exists():
        return {"run_id": run_id, "found": False, "cancelled": 0, "jobs": []}

    jobs = _collect_runpod_jobs(root)
    client_map = {
        "mmseqs": runner.mmseqs,
        "proteinmpnn": runner.proteinmpnn,
        "rfd3": runner.rfd3,
        "diffdock": runner.diffdock,
        "af2": runner.af2,
    }
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, object]] = []
    errors: list[str] = []
    cancelled = 0

    for job in jobs:
        kind = str(job.get("kind") or "unknown")
        job_id = str(job.get("job_id") or "")
        if not job_id:
            continue
        key = (kind, job_id)
        if key in seen:
            continue
        seen.add(key)

        cancel_info = _client_cancel_info(client_map.get(kind))
        if cancel_info is None:
            results.append(
                {
                    "kind": kind,
                    "job_id": job_id,
                    "status": "skipped",
                    "reason": "endpoint_not_configured",
                }
            )
            continue
        runpod, endpoint_id = cancel_info
        try:
            resp = runpod.cancel(endpoint_id, job_id)
            status = None
            if isinstance(resp, dict):
                status = resp.get("status") or resp.get("state")
            results.append(
                {
                    "kind": kind,
                    "job_id": job_id,
                    "endpoint_id": endpoint_id,
                    "status": status or "cancel_requested",
                }
            )
            cancelled += 1
        except Exception as exc:
            msg = f"{kind}:{job_id}: {exc}"
            errors.append(msg)
            results.append({"kind": kind, "job_id": job_id, "error": str(exc)})

    status = load_status(runner.output_root, run_id)
    stage = str(status.get("stage") or "cancel") if isinstance(status, dict) else "cancel"
    paths = RunPaths(run_id=run_id, root=root)
    detail = f"cancelled_jobs={cancelled}" if cancelled else "cancel_requested"
    set_status(paths, stage=stage, state="cancelled", detail=detail)

    return {
        "run_id": run_id,
        "found": True,
        "cancelled": cancelled,
        "errors": errors,
        "jobs": results,
    }


def _submit_feedback(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")

    rating = str(arguments.get("rating") or "").strip().lower()
    if rating not in {"good", "bad"}:
        raise ValueError("rating must be 'good' or 'bad'")

    reasons = _as_reason_list(arguments.get("reasons"))
    comment = _as_text(arguments.get("comment")).strip() or None
    artifact_path = _as_text(arguments.get("artifact_path")).strip() or None
    stage = _as_text(arguments.get("stage")).strip().lower() or None
    metrics = _as_metrics(arguments.get("metrics"))
    user = _normalize_user(arguments.get("user"))

    entry: dict[str, object] = {
        "id": uuid.uuid4().hex,
        "run_id": run_id,
        "rating": rating,
        "reasons": reasons,
        "comment": comment,
        "artifact_path": artifact_path,
        "stage": stage,
        "metrics": metrics,
        "user": user,
        "created_at": _now_iso(),
    }
    return append_run_event(runner.output_root, run_id, filename="feedback.jsonl", payload=entry)


def _list_feedback(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    limit = _as_int(arguments.get("limit"), 50)
    items = list_run_events(runner.output_root, run_id, filename="feedback.jsonl", limit=limit)
    return {"run_id": run_id, "items": items}


def _submit_experiment(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")

    assay_type = str(arguments.get("assay_type") or "unspecified").strip()
    result = str(arguments.get("result") or "").strip().lower()
    if result not in {"success", "fail", "inconclusive"}:
        raise ValueError("result must be one of: success, fail, inconclusive")

    metrics = _as_metrics(arguments.get("metrics"))
    conditions = _as_text(arguments.get("conditions")).strip() or None
    sample_id = _as_text(arguments.get("sample_id")).strip() or None
    artifact_path = _as_text(arguments.get("artifact_path")).strip() or None
    note = _as_text(arguments.get("note")).strip() or None
    user = _normalize_user(arguments.get("user"))

    entry: dict[str, object] = {
        "id": uuid.uuid4().hex,
        "run_id": run_id,
        "assay_type": assay_type,
        "result": result,
        "metrics": metrics,
        "conditions": conditions,
        "sample_id": sample_id,
        "artifact_path": artifact_path,
        "note": note,
        "user": user,
        "created_at": _now_iso(),
    }
    return append_run_event(runner.output_root, run_id, filename="experiments.jsonl", payload=entry)


def _list_experiments(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    limit = _as_int(arguments.get("limit"), 50)
    items = list_run_events(runner.output_root, run_id, filename="experiments.jsonl", limit=limit)
    return {"run_id": run_id, "items": items}


def _list_agent_events(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    limit = _as_int(arguments.get("limit"), 50)
    items = list_run_events(runner.output_root, run_id, filename="agent_panel.jsonl", limit=limit)
    return {"run_id": run_id, "items": items}


def _load_report_text(output_root: str, run_id: str) -> str | None:
    root = resolve_run_path(output_root, run_id)
    if not root.exists():
        raise ValueError("run_id not found")
    report_path = root / "report.md"
    if not report_path.exists():
        return None
    return report_path.read_text(encoding="utf-8")


def _save_report_text(output_root: str, run_id: str, content: str) -> None:
    root = resolve_run_path(output_root, run_id)
    if not root.exists():
        raise ValueError("run_id not found")
    report_path = root / "report.md"
    report_path.write_text(content, encoding="utf-8")


def _save_report_text_ko(output_root: str, run_id: str, content: str) -> None:
    root = resolve_run_path(output_root, run_id)
    if not root.exists():
        raise ValueError("run_id not found")
    report_path = root / "report_ko.md"
    report_path.write_text(content, encoding="utf-8")


def _summarize_feedback(items: list[dict[str, object]]) -> dict[str, object]:
    counts = {"good": 0, "bad": 0}
    for item in items:
        rating = str(item.get("rating") or "").lower()
        if rating in counts:
            counts[rating] += 1
    return counts


def _summarize_experiments(items: list[dict[str, object]]) -> dict[str, object]:
    counts = {"success": 0, "fail": 0, "inconclusive": 0}
    for item in items:
        result = str(item.get("result") or "").lower()
        if result in counts:
            counts[result] += 1
    return counts


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    nums = sorted(values)
    mid = len(nums) // 2
    if len(nums) % 2 == 1:
        return float(nums[mid])
    return float(nums[mid - 1] + nums[mid]) / 2.0


def _load_json_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _collect_design_metrics(run_root: Path, summary: dict[str, object] | None) -> dict[str, object]:
    out = {
        "soluprot_scores": [],
        "soluprot_total": 0,
        "soluprot_passed": 0,
        "af2_selected_plddt": [],
        "af2_selected_rmsd": [],
        "af2_selected_total": 0,
    }
    if not summary:
        return out
    tiers = summary.get("tiers")
    if not isinstance(tiers, list):
        return out
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        tier_val = tier.get("tier")
        if tier_val is None:
            continue
        try:
            tier_key = _tier_key(float(tier_val))
        except Exception:
            continue
        tier_dir = run_root / "tiers" / tier_key

        sol = _load_json_file(tier_dir / "soluprot.json")
        if isinstance(sol, dict):
            scores = sol.get("scores")
            passed_ids = sol.get("passed_ids") if isinstance(sol.get("passed_ids"), list) else []
            if isinstance(scores, dict):
                values = [float(v) for v in scores.values() if isinstance(v, (int, float))]
                out["soluprot_scores"].extend(values)
                out["soluprot_total"] += len(values)
            out["soluprot_passed"] += len(passed_ids)

        af2 = _load_json_file(tier_dir / "af2_scores.json")
        if isinstance(af2, dict):
            scores = af2.get("scores") if isinstance(af2.get("scores"), dict) else {}
            rmsd_scores = af2.get("rmsd_scores") if isinstance(af2.get("rmsd_scores"), dict) else {}
            selected_ids = af2.get("selected_ids") if isinstance(af2.get("selected_ids"), list) else []
            if selected_ids:
                out["af2_selected_total"] += len(selected_ids)
                for seq_id in selected_ids:
                    if seq_id in scores and isinstance(scores.get(seq_id), (int, float)):
                        out["af2_selected_plddt"].append(float(scores.get(seq_id)))
                    if seq_id in rmsd_scores and isinstance(rmsd_scores.get(seq_id), (int, float)):
                        out["af2_selected_rmsd"].append(float(rmsd_scores.get(seq_id)))
    return out


def _load_wt_metrics(run_root: Path) -> dict[str, object] | None:
    return _load_json_file(run_root / "wt" / "metrics.json")


def _load_mask_consensus(run_root: Path) -> dict[str, object] | None:
    return _load_json_file(run_root / "mask_consensus.json")


def _normalize_positions(raw: object) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for pos in raw:
        try:
            out.append(int(pos))
        except Exception:
            continue
    return sorted(set(out))


def _normalize_chain_positions(raw: object) -> dict[str, list[int]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[int]] = {}
    for chain, positions in raw.items():
        cleaned = _normalize_positions(positions)
        if cleaned:
            out[str(chain)] = cleaned
    return out


def _format_positions_preview(positions: list[int], *, limit: int = 8) -> str:
    if not positions:
        return "none"
    preview = ", ".join(str(p) for p in positions[:limit])
    if len(positions) > limit:
        preview += f", ...(+{len(positions) - limit})"
    return preview


def _format_chain_counts(positions_by_chain: dict[str, list[int]]) -> str:
    if not positions_by_chain:
        return "none"
    parts = [f"{chain}={len(pos)}" for chain, pos in sorted(positions_by_chain.items())]
    return ", ".join(parts) if parts else "none"


def _sort_tier_keys(keys: list[str]) -> list[str]:
    def _key(val: str) -> tuple[int, float | str]:
        try:
            return (0, float(val))
        except Exception:
            return (1, str(val))

    return sorted({str(k) for k in keys if str(k).strip()}, key=_key)


def _extract_runpod_job_ids(payload: dict[str, object]) -> list[str]:
    job_ids: list[str] = []
    job_id = payload.get("job_id")
    if isinstance(job_id, str) and job_id.strip():
        job_ids.append(job_id.strip())
    jobs = payload.get("jobs")
    if isinstance(jobs, dict):
        for val in jobs.values():
            if isinstance(val, str) and val.strip():
                job_ids.append(val.strip())
    return job_ids


def _collect_runpod_jobs(run_root: Path) -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    af2_target = run_root / "af2_target_runpod_job.json"
    if af2_target.exists():
        payload = _load_json_file(af2_target)
        if isinstance(payload, dict):
            for job_id in _extract_runpod_job_ids(payload):
                jobs.append({"kind": "af2", "job_id": job_id, "path": str(af2_target)})

    for path in run_root.rglob("runpod_job.json"):
        rel = path.relative_to(run_root)
        parts = rel.parts
        kind = "unknown"
        if "af2" in parts:
            kind = "af2"
        elif parts and parts[0] == "msa":
            kind = "mmseqs"
        elif parts and parts[0] == "rfd3":
            kind = "rfd3"
        elif parts and parts[0] == "diffdock":
            kind = "diffdock"
        elif "tiers" in parts:
            kind = "proteinmpnn"
        payload = _load_json_file(path)
        if isinstance(payload, dict):
            for job_id in _extract_runpod_job_ids(payload):
                jobs.append({"kind": kind, "job_id": job_id, "path": str(path)})

    for path in run_root.rglob("runpod_jobs.json"):
        rel = path.relative_to(run_root)
        parts = rel.parts
        kind = "af2" if "af2" in parts else "unknown"
        payload = _load_json_file(path)
        if isinstance(payload, dict):
            for job_id in _extract_runpod_job_ids(payload):
                jobs.append({"kind": kind, "job_id": job_id, "path": str(path)})

    return jobs


def _client_cancel_info(client: object | None) -> tuple[object, str] | None:
    if client is None:
        return None
    runpod = getattr(client, "runpod", None)
    endpoint_id = getattr(client, "endpoint_id", None)
    if runpod is None or endpoint_id is None:
        return None
    if not hasattr(runpod, "cancel"):
        return None
    endpoint = str(endpoint_id).strip()
    if not endpoint:
        return None
    return runpod, endpoint


def _score_payload(
    feedback_counts: dict[str, object],
    experiment_counts: dict[str, object],
) -> dict[str, object]:
    return compute_score(feedback_counts, experiment_counts)


def _mask_consensus_report_lines(
    *,
    run_root: Path,
    request: dict[str, object] | None,
    lang: str = "en",
) -> list[str]:
    payload = _load_mask_consensus(run_root)
    enabled = bool(request.get("mask_consensus_apply")) if request else False
    if payload is None and not enabled:
        return []

    is_ko = str(lang).lower().startswith("ko")
    none_label = "없음" if is_ko else "none"
    lines: list[str] = []
    lines.append("## 마스킹 합의" if is_ko else "## Mask Consensus")
    lines.append(f"- ProteinMPNN 적용 여부: {'yes' if enabled else 'no'}" if is_ko else f"- Applied to ProteinMPNN: {'yes' if enabled else 'no'}")

    if payload is None:
        lines.append("- 마스킹 합의 데이터가 아직 없습니다." if is_ko else "- Mask consensus data not available yet.")
        lines.append("")
        return lines

    consensus = payload.get("consensus") if isinstance(payload, dict) else None
    if not isinstance(consensus, dict):
        lines.append("- 마스킹 합의 데이터가 올바르지 않습니다." if is_ko else "- Mask consensus data invalid.")
        lines.append("")
        return lines

    threshold = consensus.get("threshold")
    if threshold is not None:
        label = "합의 기준(표)" if is_ko else "Vote threshold"
        lines.append(f"- {label}: {threshold}")

    notes = payload.get("notes") if isinstance(payload.get("notes"), list) else []
    for note in notes:
        if not isinstance(note, str) or not note.strip():
            continue
        label = "참고" if is_ko else "Note"
        lines.append(f"- {label}: {note.strip()}")

    fixed_query = consensus.get("fixed_positions_query_by_tier") if isinstance(consensus.get("fixed_positions_query_by_tier"), dict) else {}
    fixed_by_tier = consensus.get("fixed_positions_by_tier") if isinstance(consensus.get("fixed_positions_by_tier"), dict) else {}

    tier_keys = _sort_tier_keys(list(fixed_query.keys()) + list(fixed_by_tier.keys()))
    if not tier_keys:
        lines.append("- 티어별 합의: 없음" if is_ko else "- Per-tier consensus: none")
        lines.append("")
        return lines

    lines.append("- 티어별 합의:" if is_ko else "- Per-tier consensus:")
    for tier_key in tier_keys:
        query_positions = _normalize_positions(fixed_query.get(tier_key))
        chain_positions = _normalize_chain_positions(fixed_by_tier.get(tier_key))
        applied_positions: dict[str, list[int]] = {}
        if enabled:
            applied_payload = _load_json_file(run_root / "tiers" / str(tier_key) / "fixed_positions.json")
            applied_positions = _normalize_chain_positions(applied_payload)

        segments: list[str] = []
        if query_positions:
            preview = _format_positions_preview(query_positions)
            if preview == "none":
                preview = none_label
            if is_ko:
                segments.append(f"query 고정={len(query_positions)} ({preview})")
            else:
                segments.append(f"query_fixed={len(query_positions)} ({preview})")
        else:
            segments.append("query 고정=0" if is_ko else "query_fixed=0")

        if chain_positions:
            chain_counts = _format_chain_counts(chain_positions)
            if chain_counts == "none":
                chain_counts = none_label
            if is_ko:
                segments.append(f"체인 합의={chain_counts}")
            else:
                segments.append(f"consensus_chain={chain_counts}")

        if enabled and applied_positions:
            applied_counts = _format_chain_counts(applied_positions)
            if applied_counts == "none":
                applied_counts = none_label
            if is_ko:
                segments.append(f"적용 고정(ProteinMPNN)={applied_counts}")
            else:
                segments.append(f"applied_fixed={applied_counts}")

        if not segments:
            segments.append("데이터 없음" if is_ko else "no data")
        lines.append(f"  - Tier {tier_key}: " + "; ".join(segments))
    lines.append("")
    return lines


def _build_report_text(
    *,
    run_id: str,
    run_root: Path,
    request: dict[str, object] | None,
    summary: dict[str, object] | None,
    status: dict[str, object] | None,
    feedback_items: list[dict[str, object]],
    experiment_items: list[dict[str, object]],
    agent_items: list[dict[str, object]],
) -> str:
    lines: list[str] = []
    lines.append(f"# Run Report: {run_id}")
    lines.append("")

    if status:
        lines.append("## Status")
        lines.append(f"- Stage: {status.get('stage') or '-'}")
        lines.append(f"- State: {status.get('state') or '-'}")
        lines.append(f"- Updated: {status.get('updated_at') or '-'}")
        lines.append("")

    if request:
        lines.append("## Inputs")
        target_pdb = bool(str(request.get("target_pdb") or "").strip())
        target_fasta = bool(str(request.get("target_fasta") or "").strip())
        lines.append(f"- target_pdb: {'yes' if target_pdb else 'no'}")
        lines.append(f"- target_fasta: {'yes' if target_fasta else 'no'}")
        if request.get("stop_after"):
            lines.append(f"- stop_after: {request.get('stop_after')}")
        if request.get("design_chains"):
            lines.append(f"- design_chains: {request.get('design_chains')}")
        if request.get("rfd3_contig"):
            lines.append(f"- rfd3_contig: {request.get('rfd3_contig')}")
        if request.get("rfd3_input_pdb"):
            lines.append("- rfd3_input_pdb: provided")
        if request.get("diffdock_ligand_smiles") or request.get("diffdock_ligand_sdf"):
            lines.append("- diffdock_ligand: provided")
        if request.get("af2_model_preset"):
            lines.append(f"- af2_model_preset: {request.get('af2_model_preset')}")
        if request.get("mmseqs_target_db"):
            lines.append(f"- mmseqs_target_db: {request.get('mmseqs_target_db')}")
        if "wt_compare" in request:
            lines.append(f"- wt_compare: {'yes' if request.get('wt_compare') else 'no'}")
        if "mask_consensus_apply" in request:
            lines.append(
                f"- mask_consensus_apply: {'yes' if request.get('mask_consensus_apply') else 'no'}"
            )
        lines.append("")

    if summary:
        errors = summary.get("errors")
        lines.append("## Summary")
        if isinstance(errors, list) and errors:
            lines.append("- Errors:")
            for err in errors[:5]:
                lines.append(f"  - {err}")
        tiers = summary.get("tiers")
        if isinstance(tiers, list) and tiers:
            lines.append(f"- Tiers: {len(tiers)}")
            for tier in tiers:
                if not isinstance(tier, dict):
                    continue
                tier_val = tier.get("tier")
                samples = tier.get("proteinmpnn_samples") or []
                passed = tier.get("passed_ids") or []
                selected = tier.get("af2_selected_ids") or []
                lines.append(
                    f"  - Tier {tier_val}: designs={len(samples)} passed={len(passed)} af2_selected={len(selected)}"
                )
        if summary.get("msa_a3m_path"):
            lines.append(f"- msa_a3m_path: {summary.get('msa_a3m_path')}")
        if summary.get("conservation_path"):
            lines.append(f"- conservation_path: {summary.get('conservation_path')}")
        if summary.get("ligand_mask_path"):
            lines.append(f"- ligand_mask_path: {summary.get('ligand_mask_path')}")
        lines.append("")

    lines.extend(_mask_consensus_report_lines(run_root=run_root, request=request, lang="en"))

    wt_metrics = _load_wt_metrics(run_root)
    design_metrics = _collect_design_metrics(run_root, summary)
    if wt_metrics or (request and request.get("wt_compare")):
        lines.append("## WT Comparison")
        enabled = bool(request.get("wt_compare")) if request else False
        lines.append(f"- Enabled: {'yes' if enabled else 'no'}")

        wt_sol = wt_metrics.get("soluprot") if isinstance(wt_metrics, dict) else None
        wt_af2 = wt_metrics.get("af2") if isinstance(wt_metrics, dict) else None

        if isinstance(wt_sol, dict) and not wt_sol.get("skipped"):
            score = wt_sol.get("score")
            cutoff = wt_sol.get("cutoff")
            passed = wt_sol.get("passed")
            if isinstance(score, (int, float)):
                score_text = f"{float(score):.3f}"
            else:
                score_text = "-"
            lines.append(
                f"- WT SoluProt: score={score_text} cutoff={cutoff} passed={'yes' if passed else 'no'}"
            )
        elif isinstance(wt_sol, dict):
            reason = wt_sol.get("reason") or wt_sol.get("error") or "skipped"
            lines.append(f"- WT SoluProt: skipped ({reason})")

        sol_scores = design_metrics.get("soluprot_scores") or []
        sol_total = int(design_metrics.get("soluprot_total") or 0)
        sol_passed = int(design_metrics.get("soluprot_passed") or 0)
        if sol_scores and sol_total:
            sol_median = _median([float(x) for x in sol_scores if isinstance(x, (int, float))])
            pass_rate = (sol_passed / sol_total) if sol_total else 0.0
            lines.append(
                f"- Designs SoluProt: median={sol_median:.3f} pass_rate={pass_rate:.1%} ({sol_passed}/{sol_total})"
            )
            if isinstance(wt_sol, dict) and isinstance(wt_sol.get("score"), (int, float)):
                delta = float(sol_median) - float(wt_sol.get("score"))
                lines.append(f"- ΔSoluProt (median - WT): {delta:+.3f}")
        elif sol_total == 0:
            lines.append("- Designs SoluProt: not available")

        if isinstance(wt_af2, dict) and not wt_af2.get("skipped"):
            wt_plddt = wt_af2.get("best_plddt")
            wt_rmsd = wt_af2.get("rmsd_ca")
            plddt_text = f"{float(wt_plddt):.1f}" if isinstance(wt_plddt, (int, float)) else "-"
            rmsd_text = f"{float(wt_rmsd):.2f}" if isinstance(wt_rmsd, (int, float)) else "-"
            lines.append(f"- WT AF2: pLDDT={plddt_text} RMSD={rmsd_text}")
        elif isinstance(wt_af2, dict):
            reason = wt_af2.get("reason") or wt_af2.get("error") or "skipped"
            lines.append(f"- WT AF2: skipped ({reason})")

        plddt_vals = design_metrics.get("af2_selected_plddt") or []
        rmsd_vals = design_metrics.get("af2_selected_rmsd") or []
        selected_total = int(design_metrics.get("af2_selected_total") or 0)
        if plddt_vals:
            plddt_median = _median([float(x) for x in plddt_vals if isinstance(x, (int, float))])
            plddt_max = max(plddt_vals) if plddt_vals else None
            lines.append(
                f"- Designs AF2 pLDDT: median={plddt_median:.1f} max={float(plddt_max):.1f} (n={selected_total})"
            )
            if isinstance(wt_af2, dict) and isinstance(wt_af2.get("best_plddt"), (int, float)):
                delta = float(plddt_median) - float(wt_af2.get("best_plddt"))
                lines.append(f"- ΔpLDDT (median - WT): {delta:+.1f}")
        else:
            lines.append("- Designs AF2 pLDDT: not available")

        if rmsd_vals:
            rmsd_median = _median([float(x) for x in rmsd_vals if isinstance(x, (int, float))])
            rmsd_min = min(rmsd_vals) if rmsd_vals else None
            lines.append(
                f"- Designs RMSD: median={rmsd_median:.2f} min={float(rmsd_min):.2f} (lower is better)"
            )
            if isinstance(wt_af2, dict) and isinstance(wt_af2.get("rmsd_ca"), (int, float)):
                delta = float(rmsd_median) - float(wt_af2.get("rmsd_ca"))
                lines.append(f"- ΔRMSD (median - WT): {delta:+.2f} (lower is better)")
        else:
            lines.append("- Designs RMSD: not available")
        lines.append("")

    if agent_items:
        lines.append("## Agent Panel")
        for item in agent_items[-10:]:
            stage = item.get("stage") or "-"
            consensus = item.get("consensus") if isinstance(item.get("consensus"), dict) else {}
            decision = consensus.get("decision") or "-"
            confidence = consensus.get("confidence")
            error = item.get("error")
            line = f"- {stage}: decision={decision}"
            if isinstance(confidence, (int, float)):
                line += f" (confidence={confidence:.2f})"
            if error:
                line += f" · error={error}"
            lines.append(line)
            actions = consensus.get("actions") if isinstance(consensus, dict) else None
            if isinstance(actions, list) and actions:
                lines.append(f"  - actions: {'; '.join(str(a) for a in actions)}")
            interpretations = consensus.get("interpretations") if isinstance(consensus, dict) else None
            if isinstance(interpretations, list) and interpretations:
                lines.append(f"  - interpretation: {'; '.join(str(a) for a in interpretations)}")
        lines.append("")

        lines.append("## Stage Interpretations")
        latest_by_stage: dict[str, dict[str, object]] = {}
        for item in agent_items:
            stage = str(item.get("stage") or "")
            if stage:
                latest_by_stage[stage] = item
        for stage, item in latest_by_stage.items():
            lines.append(f"- {stage}")
            consensus = item.get("consensus") if isinstance(item.get("consensus"), dict) else {}
            interpretations = consensus.get("interpretations") if isinstance(consensus, dict) else []
            if isinstance(interpretations, list) and interpretations:
                for text in interpretations:
                    lines.append(f"  - {text}")
                continue
            agents = item.get("agents") if isinstance(item.get("agents"), list) else []
            fallback: list[str] = []
            for agent in agents:
                if not isinstance(agent, dict):
                    continue
                interp = agent.get("interpretation") if isinstance(agent.get("interpretation"), list) else None
                if isinstance(interp, list):
                    fallback.extend([str(x) for x in interp if x])
            if fallback:
                for text in fallback:
                    lines.append(f"  - {text}")
            else:
                lines.append("  - No additional interpretation.")
        lines.append("")

    feedback_counts = _summarize_feedback(feedback_items)
    experiment_counts = _summarize_experiments(experiment_items)
    score_payload = _score_payload(feedback_counts, experiment_counts)
    score = int(score_payload.get("score") or 0)
    evidence = str(score_payload.get("evidence") or "low")
    recommendation = str(score_payload.get("recommendation") or "needs_review")
    if feedback_items:
        lines.append("## Feedback")
        lines.append(f"- Good: {feedback_counts['good']}")
        lines.append(f"- Bad: {feedback_counts['bad']}")
        for item in feedback_items[:5]:
            rating = item.get("rating") or "-"
            reasons = item.get("reasons") or []
            comment = item.get("comment") or ""
            stamp = item.get("created_at") or ""
            reason_text = ", ".join(str(r) for r in reasons) if isinstance(reasons, list) else str(reasons)
            line = f"- [{rating}] {reason_text}"
            if comment:
                line += f" — {comment}"
            if stamp:
                line += f" ({stamp})"
            lines.append(line)
        lines.append("")

    if experiment_items:
        lines.append("## Experiments")
        lines.append(f"- Success: {experiment_counts['success']}")
        lines.append(f"- Fail: {experiment_counts['fail']}")
        lines.append(f"- Inconclusive: {experiment_counts['inconclusive']}")
        for item in experiment_items[:5]:
            assay = item.get("assay_type") or "-"
            result = item.get("result") or "-"
            metrics = item.get("metrics") or {}
            metrics_text = ""
            if isinstance(metrics, dict) and metrics:
                metrics_text = ", ".join(f"{k}={v}" for k, v in metrics.items())
            stamp = item.get("created_at") or ""
            line = f"- [{result}] {assay}"
            if metrics_text:
                line += f" ({metrics_text})"
            if stamp:
                line += f" ({stamp})"
            lines.append(line)
        lines.append("")

    lines.append("## Score")
    lines.append(f"- Score: {score}/100")
    lines.append(f"- Evidence: {evidence}")
    lines.append(f"- Recommendation: {recommendation}")
    lines.append("")

    lines.append("## Next Actions")
    if recommendation == "promote":
        lines.append("- Prioritize for downstream validation or scale-up.")
    elif recommendation == "promising":
        lines.append("- Consider additional experiments or parameter refinements.")
    elif recommendation == "needs_review":
        lines.append("- Review model outputs, constraints, and consider re-running key stages.")
    else:
        lines.append("- Deprioritize or revisit target/constraints before re-running.")
    lines.append("")

    if len(lines) <= 2:
        lines.append("No report data available yet.")
    return "\n".join(lines).strip() + "\n"


def _build_report_text_ko(
    *,
    run_id: str,
    run_root: Path,
    request: dict[str, object] | None,
    summary: dict[str, object] | None,
    status: dict[str, object] | None,
    feedback_items: list[dict[str, object]],
    experiment_items: list[dict[str, object]],
    agent_items: list[dict[str, object]],
) -> str:
    lines: list[str] = []
    lines.append(f"# 실행 리포트: {run_id}")
    lines.append("")

    if status:
        lines.append("## 상태")
        lines.append(f"- 단계: {status.get('stage') or '-'}")
        lines.append(f"- 상태: {status.get('state') or '-'}")
        lines.append(f"- 업데이트: {status.get('updated_at') or '-'}")
        lines.append("")

    if request:
        lines.append("## 입력")
        target_pdb = bool(str(request.get("target_pdb") or "").strip())
        target_fasta = bool(str(request.get("target_fasta") or "").strip())
        lines.append(f"- target_pdb: {'yes' if target_pdb else 'no'}")
        lines.append(f"- target_fasta: {'yes' if target_fasta else 'no'}")
        if request.get("stop_after"):
            lines.append(f"- stop_after: {request.get('stop_after')}")
        if request.get("design_chains"):
            lines.append(f"- design_chains: {request.get('design_chains')}")
        if request.get("rfd3_contig"):
            lines.append(f"- rfd3_contig: {request.get('rfd3_contig')}")
        if request.get("rfd3_input_pdb"):
            lines.append("- rfd3_input_pdb: provided")
        if request.get("diffdock_ligand_smiles") or request.get("diffdock_ligand_sdf"):
            lines.append("- diffdock_ligand: provided")
        if request.get("af2_model_preset"):
            lines.append(f"- af2_model_preset: {request.get('af2_model_preset')}")
        if request.get("mmseqs_target_db"):
            lines.append(f"- mmseqs_target_db: {request.get('mmseqs_target_db')}")
        if "wt_compare" in request:
            lines.append(f"- wt_compare: {'yes' if request.get('wt_compare') else 'no'}")
        if "mask_consensus_apply" in request:
            lines.append(
                f"- mask_consensus_apply: {'yes' if request.get('mask_consensus_apply') else 'no'}"
            )
        lines.append("")

    if summary:
        errors = summary.get("errors")
        lines.append("## 요약")
        if isinstance(errors, list) and errors:
            lines.append("- 오류:")
            for err in errors[:5]:
                lines.append(f"  - {err}")
        tiers = summary.get("tiers")
        if isinstance(tiers, list) and tiers:
            lines.append(f"- 티어 수: {len(tiers)}")
            for tier in tiers:
                if not isinstance(tier, dict):
                    continue
                tier_val = tier.get("tier")
                samples = tier.get("proteinmpnn_samples") or []
                passed = tier.get("passed_ids") or []
                selected = tier.get("af2_selected_ids") or []
                lines.append(
                    f"  - 티어 {tier_val}: designs={len(samples)} passed={len(passed)} af2_selected={len(selected)}"
                )
        if summary.get("msa_a3m_path"):
            lines.append(f"- msa_a3m_path: {summary.get('msa_a3m_path')}")
        if summary.get("conservation_path"):
            lines.append(f"- conservation_path: {summary.get('conservation_path')}")
        if summary.get("ligand_mask_path"):
            lines.append(f"- ligand_mask_path: {summary.get('ligand_mask_path')}")
        lines.append("")

    lines.extend(_mask_consensus_report_lines(run_root=run_root, request=request, lang="ko"))

    wt_metrics = _load_wt_metrics(run_root)
    design_metrics = _collect_design_metrics(run_root, summary)
    if wt_metrics or (request and request.get("wt_compare")):
        lines.append("## WT 비교")
        enabled = bool(request.get("wt_compare")) if request else False
        lines.append(f"- 사용 여부: {'yes' if enabled else 'no'}")

        wt_sol = wt_metrics.get("soluprot") if isinstance(wt_metrics, dict) else None
        wt_af2 = wt_metrics.get("af2") if isinstance(wt_metrics, dict) else None

        if isinstance(wt_sol, dict) and not wt_sol.get("skipped"):
            score = wt_sol.get("score")
            cutoff = wt_sol.get("cutoff")
            passed = wt_sol.get("passed")
            score_text = f"{float(score):.3f}" if isinstance(score, (int, float)) else "-"
            lines.append(
                f"- WT SoluProt: score={score_text} cutoff={cutoff} passed={'yes' if passed else 'no'}"
            )
        elif isinstance(wt_sol, dict):
            reason = wt_sol.get("reason") or wt_sol.get("error") or "skipped"
            lines.append(f"- WT SoluProt: skipped ({reason})")

        sol_scores = design_metrics.get("soluprot_scores") or []
        sol_total = int(design_metrics.get("soluprot_total") or 0)
        sol_passed = int(design_metrics.get("soluprot_passed") or 0)
        if sol_scores and sol_total:
            sol_median = _median([float(x) for x in sol_scores if isinstance(x, (int, float))])
            pass_rate = (sol_passed / sol_total) if sol_total else 0.0
            lines.append(
                f"- Designs SoluProt: median={sol_median:.3f} pass_rate={pass_rate:.1%} ({sol_passed}/{sol_total})"
            )
            if isinstance(wt_sol, dict) and isinstance(wt_sol.get("score"), (int, float)):
                delta = float(sol_median) - float(wt_sol.get("score"))
                lines.append(f"- ΔSoluProt (median - WT): {delta:+.3f}")
        elif sol_total == 0:
            lines.append("- Designs SoluProt: not available")

        if isinstance(wt_af2, dict) and not wt_af2.get("skipped"):
            wt_plddt = wt_af2.get("best_plddt")
            wt_rmsd = wt_af2.get("rmsd_ca")
            plddt_text = f"{float(wt_plddt):.1f}" if isinstance(wt_plddt, (int, float)) else "-"
            rmsd_text = f"{float(wt_rmsd):.2f}" if isinstance(wt_rmsd, (int, float)) else "-"
            lines.append(f"- WT AF2: pLDDT={plddt_text} RMSD={rmsd_text}")
        elif isinstance(wt_af2, dict):
            reason = wt_af2.get("reason") or wt_af2.get("error") or "skipped"
            lines.append(f"- WT AF2: skipped ({reason})")

        plddt_vals = design_metrics.get("af2_selected_plddt") or []
        rmsd_vals = design_metrics.get("af2_selected_rmsd") or []
        selected_total = int(design_metrics.get("af2_selected_total") or 0)
        if plddt_vals:
            plddt_median = _median([float(x) for x in plddt_vals if isinstance(x, (int, float))])
            plddt_max = max(plddt_vals) if plddt_vals else None
            lines.append(
                f"- Designs AF2 pLDDT: median={plddt_median:.1f} max={float(plddt_max):.1f} (n={selected_total})"
            )
            if isinstance(wt_af2, dict) and isinstance(wt_af2.get("best_plddt"), (int, float)):
                delta = float(plddt_median) - float(wt_af2.get("best_plddt"))
                lines.append(f"- ΔpLDDT (median - WT): {delta:+.1f}")
        else:
            lines.append("- Designs AF2 pLDDT: not available")

        if rmsd_vals:
            rmsd_median = _median([float(x) for x in rmsd_vals if isinstance(x, (int, float))])
            rmsd_min = min(rmsd_vals) if rmsd_vals else None
            lines.append(
                f"- Designs RMSD: median={rmsd_median:.2f} min={float(rmsd_min):.2f} (lower is better)"
            )
            if isinstance(wt_af2, dict) and isinstance(wt_af2.get("rmsd_ca"), (int, float)):
                delta = float(rmsd_median) - float(wt_af2.get("rmsd_ca"))
                lines.append(f"- ΔRMSD (median - WT): {delta:+.2f} (lower is better)")
        else:
            lines.append("- Designs RMSD: not available")
        lines.append("")

    if agent_items:
        lines.append("## 에이전트 패널")
        for item in agent_items[-10:]:
            stage = item.get("stage") or "-"
            consensus = item.get("consensus") if isinstance(item.get("consensus"), dict) else {}
            decision = consensus.get("decision") or "-"
            confidence = consensus.get("confidence")
            error = item.get("error")
            line = f"- {stage}: 결정={decision}"
            if isinstance(confidence, (int, float)):
                line += f" (confidence={confidence:.2f})"
            if error:
                line += f" · error={error}"
            lines.append(line)
            actions = consensus.get("actions") if isinstance(consensus, dict) else None
            if isinstance(actions, list) and actions:
                lines.append(f"  - actions: {'; '.join(str(a) for a in actions)}")
            interpretations = consensus.get("interpretations") if isinstance(consensus, dict) else None
            if isinstance(interpretations, list) and interpretations:
                lines.append(f"  - interpretation: {'; '.join(str(a) for a in interpretations)}")
        lines.append("")

        lines.append("## 단계 해석")
        latest_by_stage: dict[str, dict[str, object]] = {}
        for item in agent_items:
            stage = str(item.get("stage") or "")
            if stage:
                latest_by_stage[stage] = item
        for stage, item in latest_by_stage.items():
            lines.append(f"- {stage}")
            consensus = item.get("consensus") if isinstance(item.get("consensus"), dict) else {}
            interpretations = consensus.get("interpretations") if isinstance(consensus.get("interpretations"), list) else []
            if isinstance(interpretations, list) and interpretations:
                for text in interpretations:
                    lines.append(f"  - {text}")
                continue
            agents = item.get("agents") if isinstance(item.get("agents"), list) else []
            fallback: list[str] = []
            for agent in agents:
                if not isinstance(agent, dict):
                    continue
                interp = agent.get("interpretation") if isinstance(agent.get("interpretation"), list) else None
                if isinstance(interp, list):
                    fallback.extend([str(x) for x in interp if x])
            if fallback:
                for text in fallback:
                    lines.append(f"  - {text}")
            else:
                lines.append("  - 추가 해석 없음.")
        lines.append("")

    feedback_counts = _summarize_feedback(feedback_items)
    experiment_counts = _summarize_experiments(experiment_items)
    score_payload = _score_payload(feedback_counts, experiment_counts)
    score = int(score_payload.get("score") or 0)
    evidence = str(score_payload.get("evidence") or "low")
    recommendation = str(score_payload.get("recommendation") or "needs_review")
    if feedback_items:
        lines.append("## 피드백")
        lines.append(f"- Good: {feedback_counts['good']}")
        lines.append(f"- Bad: {feedback_counts['bad']}")
        for item in feedback_items[:5]:
            rating = item.get("rating") or "-"
            reasons = item.get("reasons") or []
            comment = item.get("comment") or ""
            stamp = item.get("created_at") or ""
            reason_text = ", ".join(str(r) for r in reasons) if isinstance(reasons, list) else str(reasons)
            line = f"- [{rating}] {reason_text}"
            if comment:
                line += f" — {comment}"
            if stamp:
                line += f" ({stamp})"
            lines.append(line)
        lines.append("")

    if experiment_items:
        lines.append("## 실험")
        lines.append(f"- Success: {experiment_counts['success']}")
        lines.append(f"- Fail: {experiment_counts['fail']}")
        lines.append(f"- Inconclusive: {experiment_counts['inconclusive']}")
        for item in experiment_items[:5]:
            assay = item.get("assay_type") or "-"
            result = item.get("result") or "-"
            metrics = item.get("metrics") or {}
            metrics_text = ""
            if isinstance(metrics, dict) and metrics:
                metrics_text = ", ".join(f"{k}={v}" for k, v in metrics.items())
            stamp = item.get("created_at") or ""
            line = f"- [{result}] {assay}"
            if metrics_text:
                line += f" ({metrics_text})"
            if stamp:
                line += f" ({stamp})"
            lines.append(line)
        lines.append("")

    lines.append("## 점수")
    lines.append(f"- Score: {score}/100")
    lines.append(f"- Evidence: {evidence}")
    lines.append(f"- Recommendation: {recommendation}")
    lines.append("")

    lines.append("## 다음 권장 조치")
    if recommendation == "promote":
        lines.append("- 후속 검증 또는 스케일업을 우선 진행하세요.")
    elif recommendation == "promising":
        lines.append("- 추가 실험 또는 파라미터 조정을 고려하세요.")
    elif recommendation == "needs_review":
        lines.append("- 결과, 제약, 주요 단계 재실행 여부를 검토하세요.")
    else:
        lines.append("- 타깃/제약을 재검토한 뒤 재실행을 권장합니다.")
    lines.append("")

    if len(lines) <= 2:
        lines.append("리포트 데이터가 아직 없습니다.")
    return "\n".join(lines).strip() + "\n"

def _generate_report(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")

    root = resolve_run_path(runner.output_root, run_id)
    if not root.exists():
        raise ValueError("run_id not found")
    summary = None
    summary_path = root / "summary.json"
    if summary_path.exists():
        raw = read_json(summary_path)
        if isinstance(raw, dict):
            summary = raw
    request = None
    request_path = root / "request.json"
    if request_path.exists():
        raw = read_json(request_path)
        if isinstance(raw, dict):
            request = raw

    status = load_status(runner.output_root, run_id)
    feedback_items = list_run_events(runner.output_root, run_id, filename="feedback.jsonl", limit=50)
    experiment_items = list_run_events(runner.output_root, run_id, filename="experiments.jsonl", limit=50)
    agent_items = list_run_events(runner.output_root, run_id, filename="agent_panel.jsonl", limit=50)
    feedback_counts = _summarize_feedback(feedback_items)
    experiment_counts = _summarize_experiments(experiment_items)
    score_payload = _score_payload(feedback_counts, experiment_counts)
    score = int(score_payload.get("score") or 0)
    evidence = str(score_payload.get("evidence") or "low")
    recommendation = str(score_payload.get("recommendation") or "needs_review")
    report_text = _build_report_text(
        run_id=run_id,
        run_root=root,
        request=request,
        summary=summary,
        status=status,
        feedback_items=feedback_items,
        experiment_items=experiment_items,
        agent_items=agent_items,
    )
    report_text_ko = _build_report_text_ko(
        run_id=run_id,
        run_root=root,
        request=request,
        summary=summary,
        status=status,
        feedback_items=feedback_items,
        experiment_items=experiment_items,
        agent_items=agent_items,
    )
    _save_report_text(runner.output_root, run_id, report_text)
    _save_report_text_ko(runner.output_root, run_id, report_text_ko)
    entry: dict[str, object] = {
        "id": uuid.uuid4().hex,
        "run_id": run_id,
        "source": "generated",
        "content": report_text,
        "content_ko": report_text_ko,
        "score": score,
        "evidence": evidence,
        "recommendation": recommendation,
        "scoring_config": score_payload.get("scoring_config") or scoring_config(),
        "created_at": _now_iso(),
    }
    append_run_event(runner.output_root, run_id, filename="report_revisions.jsonl", payload=entry)
    return {
        "run_id": run_id,
        "report": report_text,
        "report_ko": report_text_ko,
        "score": score,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _save_report(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    content = _as_text(arguments.get("content")).strip()
    if not content:
        raise ValueError("content is required")

    user = _normalize_user(arguments.get("user"))
    source = str(arguments.get("source") or "user").strip()
    _save_report_text(runner.output_root, run_id, content)
    entry: dict[str, object] = {
        "id": uuid.uuid4().hex,
        "run_id": run_id,
        "source": source,
        "content": content,
        "user": user,
        "created_at": _now_iso(),
    }
    append_run_event(runner.output_root, run_id, filename="report_revisions.jsonl", payload=entry)
    return {"run_id": run_id, "report": content}


def _get_report(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = str(arguments.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    report_text = _load_report_text(runner.output_root, run_id)
    root = resolve_run_path(runner.output_root, run_id)
    report_ko = ""
    report_ko_path = root / "report_ko.md"
    if report_ko_path.exists():
        try:
            report_ko = report_ko_path.read_text(encoding="utf-8")
        except Exception:
            report_ko = ""
    revisions = list_run_events(runner.output_root, run_id, filename="report_revisions.jsonl", limit=1)
    latest = revisions[-1] if revisions else None
    out = {
        "run_id": run_id,
        "report": report_text or "",
        "report_ko": report_ko or "",
        "latest_revision": latest,
    }
    if isinstance(latest, dict):
        for key in ("score", "evidence", "recommendation"):
            if key in latest:
                out[key] = latest.get(key)
    if "score" not in out:
        feedback_items = list_run_events(runner.output_root, run_id, filename="feedback.jsonl", limit=50)
        experiment_items = list_run_events(runner.output_root, run_id, filename="experiments.jsonl", limit=50)
        feedback_counts = _summarize_feedback(feedback_items)
        experiment_counts = _summarize_experiments(experiment_items)
        score_payload = _score_payload(feedback_counts, experiment_counts)
        out["score"] = score_payload.get("score")
        out["evidence"] = score_payload.get("evidence")
        out["recommendation"] = score_payload.get("recommendation")
    return out


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
    agent_panel_enabled = _as_bool(args.get("agent_panel_enabled"), True)
    auto_recover = _as_bool(args.get("auto_recover"), True)
    wt_compare = _as_bool(args.get("wt_compare"), True)
    mask_consensus_apply = _as_bool(args.get("mask_consensus_apply"), False)

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
        pdb_strip_nonpositive_resseq=_as_bool(args.get("pdb_strip_nonpositive_resseq"), True),
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
        agent_panel_enabled=agent_panel_enabled,
        auto_recover=auto_recover,
        wt_compare=wt_compare,
        mask_consensus_apply=mask_consensus_apply,
    )


def _pipeline_run_schema() -> dict[str, Any]:
    return {
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
            "stop_after": {"type": "string"},
            "force": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
            "agent_panel_enabled": {"type": "boolean"},
            "auto_recover": {"type": "boolean"},
            "wt_compare": {"type": "boolean"},
            "mask_consensus_apply": {"type": "boolean"},
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
    }


def tool_definitions() -> list[dict[str, Any]]:
    run_schema = _pipeline_run_schema()
    return [
        {
            "name": "pipeline.run",
            "description": "Run the full protein design pipeline (MMseqs2→mask→ProteinMPNN→SoluProt→AF2→novelty).",
            "inputSchema": run_schema,
        },
        {
            "name": "pipeline.preflight",
            "description": "Validate inputs and configuration without running the pipeline.",
            "inputSchema": copy.deepcopy(run_schema),
        },
        {
            "name": "pipeline.af2_predict",
            "description": "Run AlphaFold2 on input FASTA/sequence (standalone).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target_fasta": {"type": "string"},
                    "target_pdb": {"type": "string"},
                    "af2_model_preset": {"type": "string"},
                    "af2_db_preset": {"type": "string"},
                    "af2_max_template_date": {"type": "string"},
                    "af2_extra_flags": {"type": "string"},
                    "run_id": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                },
                "anyOf": [{"required": ["target_fasta"]}, {"required": ["target_pdb"]}],
            },
        },
        {
            "name": "pipeline.diffdock",
            "description": "Run DiffDock on a protein PDB and ligand (standalone).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "protein_pdb": {"type": "string"},
                    "target_pdb": {"type": "string"},
                    "diffdock_ligand_smiles": {"type": "string"},
                    "diffdock_ligand_sdf": {"type": "string"},
                    "ligand_smiles": {"type": "string"},
                    "ligand_sdf": {"type": "string"},
                    "complex_name": {"type": "string"},
                    "diffdock_config": {"type": "string"},
                    "diffdock_extra_args": {"type": "string"},
                    "diffdock_cuda_visible_devices": {"type": "string"},
                    "run_id": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                },
                "anyOf": [{"required": ["protein_pdb"]}, {"required": ["target_pdb"]}],
            },
        },
        {
            "name": "pipeline.submit_feedback",
            "description": "Submit a feedback rating (good/bad) for a run or artifact.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "rating": {"type": "string", "enum": ["good", "bad"]},
                    "reasons": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]},
                    "comment": {"type": "string"},
                    "artifact_path": {"type": "string"},
                    "stage": {"type": "string"},
                    "metrics": {"type": "object"},
                    "user": {"type": "object"},
                },
                "required": ["run_id", "rating"],
            },
        },
        {
            "name": "pipeline.list_feedback",
            "description": "List feedback entries for a run.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "pipeline.submit_experiment",
            "description": "Submit an experimental result for a run.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "assay_type": {"type": "string"},
                    "result": {"type": "string", "enum": ["success", "fail", "inconclusive"]},
                    "metrics": {"type": "object"},
                    "conditions": {"type": "string"},
                    "sample_id": {"type": "string"},
                    "artifact_path": {"type": "string"},
                    "note": {"type": "string"},
                    "user": {"type": "object"},
                },
                "required": ["run_id", "result"],
            },
        },
        {
            "name": "pipeline.list_experiments",
            "description": "List experimental results for a run.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "pipeline.list_agent_events",
            "description": "List agent panel events for a run.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "pipeline.generate_report",
            "description": "Generate a markdown report for a run from artifacts, feedback, and experiments.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "pipeline.save_report",
            "description": "Save a report revision for a run.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "content": {"type": "string"},
                    "source": {"type": "string"},
                    "user": {"type": "object"},
                },
                "required": ["run_id", "content"],
            },
        },
        {
            "name": "pipeline.get_report",
            "description": "Get the latest report for a run.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
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
                    "agent_panel_enabled": {"type": "boolean"},
                    "auto_recover": {"type": "boolean"},
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
            "name": "pipeline.delete_run",
            "description": "Delete a run directory and all artifacts under run_id.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}, "force": {"type": "boolean"}},
                "required": ["run_id"],
            },
        },
        {
            "name": "pipeline.cancel_run",
            "description": "Cancel in-flight RunPod jobs for a run_id and mark the run as cancelled.",
            "inputSchema": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
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

        if name == "pipeline.preflight":
            req = pipeline_request_from_args(arguments)
            return preflight_request(req, self.runner)

        if name == "pipeline.af2_predict":
            return _run_af2_predict(self.runner, arguments)

        if name == "pipeline.diffdock":
            return _run_diffdock(self.runner, arguments)

        if name == "pipeline.submit_feedback":
            return _submit_feedback(self.runner, arguments)

        if name == "pipeline.list_feedback":
            return _list_feedback(self.runner, arguments)

        if name == "pipeline.submit_experiment":
            return _submit_experiment(self.runner, arguments)

        if name == "pipeline.list_experiments":
            return _list_experiments(self.runner, arguments)

        if name == "pipeline.list_agent_events":
            return _list_agent_events(self.runner, arguments)

        if name == "pipeline.generate_report":
            return _generate_report(self.runner, arguments)

        if name == "pipeline.save_report":
            return _save_report(self.runner, arguments)

        if name == "pipeline.get_report":
            return _get_report(self.runner, arguments)

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
            agent_panel_enabled = _as_bool(arguments.get("agent_panel_enabled"), req.agent_panel_enabled)
            auto_recover = _as_bool(arguments.get("auto_recover"), req.auto_recover)
            req = replace(req, agent_panel_enabled=agent_panel_enabled, auto_recover=auto_recover)
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

        if name == "pipeline.delete_run":
            return _delete_run_tool(self.runner, arguments)

        if name == "pipeline.cancel_run":
            return _cancel_run_tool(self.runner, arguments)

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
