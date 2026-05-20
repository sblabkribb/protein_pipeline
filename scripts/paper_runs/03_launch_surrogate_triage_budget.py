#!/usr/bin/env python3
"""Launch manuscript AF2-budgeted surrogate-triage runs.

This script is the paper-facing compute-saving path. It runs the standard
RAPID design pipeline with RFD3, BioEmu, Relax, and experimental evolution
disabled, then enables one-round surrogate triage before AF2/ColabFold.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_SRC = PROJECT_ROOT / "pipeline-mcp" / "src"
if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

from pipeline_mcp.app import build_runner
from pipeline_mcp.cath_ops import _launch_helper


DEFAULT_TARGETS = (
    "cath_val_1a19A00,"
    "cath_val_1advA02,"
    "cath_val_1h6wA03,"
    "cath_train_1a6jA00,"
    "cath_train_1a8rG01"
)


def _load_env(explicit: str | None = None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            PROJECT_ROOT / "pipeline-mcp" / ".env",
            Path("/opt/protein_pipeline/pipeline-mcp/.env"),
        ]
    )
    for env_file in candidates:
        if env_file.exists():
            load_dotenv(str(env_file), override=False)
            return env_file
    return None


def _load_cath_batch_module():
    path = PROJECT_ROOT / "scripts" / "02_run_cath_batch.py"
    spec = importlib.util.spec_from_file_location("rapid_cath_batch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_targets(text: str) -> list[str]:
    return [item.strip() for item in str(text or "").split(",") if item.strip()]


def _parse_models(text: str) -> str | list[str]:
    items = [item.strip().lower() for item in re.split(r"[,;\n]+", str(text or "")) if item.strip()]
    if not items:
        return "rf"
    return items[0] if len(items) == 1 else items


def _split_target(target: str) -> tuple[str | None, str]:
    for subset in ("train", "val", "test"):
        prefix = f"cath_{subset}_"
        if target.startswith(prefix):
            return subset, target.removeprefix(prefix)
    return None, target.removesuffix(".pdb")


def _resolve_pdb(target: str, source_root: Path) -> Path:
    path = Path(target)
    if path.exists():
        return path
    subset, target_id = _split_target(target)
    subsets = [subset] if subset else ["val", "train", "test"]
    for item in subsets:
        if not item:
            continue
        candidate = source_root / f"cath_{item}" / f"{target_id}.pdb"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"PDB not found for target {target!r} under {source_root}")


def _safe_run_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("._")


def _build_request(*, cath_module, pdb_path: Path, target_id: str, args: argparse.Namespace):
    base = cath_module.build_cath_request(
        pdb_path.read_text(encoding="utf-8"),
        target_id=target_id,
        num_seq_per_tier=int(args.num_seq_per_tier),
        af2_max_candidates_per_tier=0,
        af2_top_k=0,
    )
    return replace(
        base,
        evolution_mode=False,
        surrogate_triage_enabled=True,
        surrogate_triage_initial_samples=int(args.initial_samples),
        surrogate_triage_top_k=int(args.top_k),
        surrogate_triage_model=_parse_models(args.surrogate_models),
        rfd3_use=False,
        bioemu_use=False,
        relax_enabled=False,
        novelty_enabled=(str(args.stop_after).lower() == "novelty"),
        wt_compare=False,
        agent_panel_enabled=False,
        soluprot_cutoff=float(args.soluprot_cutoff),
        af2_provider=str(args.af2_provider),
        af2_plddt_cutoff=float(args.af2_plddt_cutoff),
        af2_rmsd_cutoff=float(args.af2_rmsd_cutoff),
        stop_after=str(args.stop_after),
        force=bool(args.force),
        auto_recover=True,
    )


def run_now(args: argparse.Namespace) -> int:
    env_file = _load_env(args.env_file)
    os.environ["PIPELINE_OUTPUT_ROOT"] = str(Path(args.output_root).resolve())
    print(f"env_file={env_file or 'not found'}")
    print(f"output_root={os.environ['PIPELINE_OUTPUT_ROOT']}")

    source_root = Path(args.source_root).resolve()
    targets = _parse_targets(args.targets)
    cath_module = _load_cath_batch_module()
    runner = None if args.dry_run else build_runner()
    run_prefix = str(args.run_prefix or "").strip() or time.strftime(
        "paper_surrogate_%Y%m%d", time.gmtime()
    )
    launched: list[dict[str, str]] = []

    for target in targets:
        subset, target_id = _split_target(target)
        pdb_path = _resolve_pdb(target, source_root)
        run_id = _safe_run_id(f"{run_prefix}_{target}")
        run_dir = Path(args.output_root).resolve() / run_id
        if run_dir.exists() and not args.force:
            print(f"[skip] {run_id}: output exists")
            launched.append(
                {"target": target, "run_id": run_id, "status": "skipped_existing"}
            )
            continue
        request = _build_request(
            cath_module=cath_module,
            pdb_path=pdb_path,
            target_id=target_id,
            args=args,
        )
        print(
            f"[run] {run_id}: target={target} split={subset or '-'} "
            f"n_train={args.initial_samples} top_k={args.top_k} "
            f"models={args.surrogate_models}"
        )
        if args.dry_run:
            launched.append({"target": target, "run_id": run_id, "status": "dry_run"})
            continue
        if runner is None:
            raise RuntimeError("runner was not initialized")
        runner.run(request, run_id=run_id)
        launched.append({"target": target, "run_id": run_id, "status": "submitted"})

    print(json.dumps({"runs": launched}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-now", action="store_true")
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--source-root", default="/opt/protein_pipeline")
    parser.add_argument("--output-root", default=str(PROJECT_ROOT / "outputs"))
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--run-prefix", default=time.strftime("paper_surrogate_%Y%m%d", time.gmtime()))
    parser.add_argument("--initial-samples", type=int, default=30)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--num-seq-per-tier", type=int, default=40)
    parser.add_argument("--surrogate-models", default="rf")
    parser.add_argument("--soluprot-cutoff", type=float, default=0.5)
    parser.add_argument("--af2-provider", default="colabfold")
    parser.add_argument("--af2-plddt-cutoff", type=float, default=85.0)
    parser.add_argument("--af2-rmsd-cutoff", type=float, default=2.0)
    parser.add_argument("--stop-after", choices=["af2", "novelty"], default="af2")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.run_now:
        return run_now(args)

    env_file = _load_env(args.env_file)
    os.environ["PIPELINE_OUTPUT_ROOT"] = str(Path(args.output_root).resolve())
    command = [
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--run-now",
        "--targets",
        str(args.targets),
        "--source-root",
        str(args.source_root),
        "--output-root",
        str(Path(args.output_root).resolve()),
        "--run-prefix",
        str(args.run_prefix),
        "--initial-samples",
        str(args.initial_samples),
        "--top-k",
        str(args.top_k),
        "--num-seq-per-tier",
        str(args.num_seq_per_tier),
        "--surrogate-models",
        str(args.surrogate_models),
        "--soluprot-cutoff",
        str(args.soluprot_cutoff),
        "--af2-provider",
        str(args.af2_provider),
        "--af2-plddt-cutoff",
        str(args.af2_plddt_cutoff),
        "--af2-rmsd-cutoff",
        str(args.af2_rmsd_cutoff),
        "--stop-after",
        str(args.stop_after),
    ]
    for flag, enabled in (
        ("--force", args.force),
        ("--dry-run", args.dry_run),
    ):
        if enabled:
            command.append(flag)
    if args.env_file:
        command.extend(["--env-file", str(args.env_file)])

    metadata = {
        "env_file": str(env_file) if env_file else None,
        "targets": _parse_targets(args.targets),
        "source_root": str(args.source_root),
        "output_root": str(Path(args.output_root).resolve()),
        "initial_samples": int(args.initial_samples),
        "top_k": int(args.top_k),
        "num_seq_per_tier": int(args.num_seq_per_tier),
        "surrogate_models": str(args.surrogate_models),
        "soluprot_cutoff": float(args.soluprot_cutoff),
        "af2_provider": str(args.af2_provider),
        "stop_after": str(args.stop_after),
        "command": command,
    }
    if args.dry_run:
        print(json.dumps({"dry_run": True, **metadata}, ensure_ascii=False, indent=2))
        return 0

    job = _launch_helper(
        str(Path(args.output_root).resolve()),
        kind="paper_surrogate_triage_budget",
        label=f"Paper surrogate-triage budget ({len(metadata['targets'])} targets)",
        command=command,
        metadata=metadata,
        cwd=str(PROJECT_ROOT),
    )
    print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
