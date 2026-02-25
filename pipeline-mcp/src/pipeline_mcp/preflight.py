from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .bio.fasta import parse_fasta
from .bio.pdb import ligand_atoms_present
from .bio.pdb import residues_by_chain
from .bio.pdb import sequence_by_chain
from .models import PipelineRequest
from .pipeline import PipelineRunner
from .pipeline import _clean_protein_sequence
from .pipeline import _diffdock_requested
from .pipeline import _resolve_af2_model_preset
from .pipeline import _rfd3_active
from .pipeline import _split_multichain_sequence
from .pipeline import _validate_af2_chain_sequences


_STAGE_ORDER = ["msa", "rfd3", "design", "soluprot", "af2", "novelty"]


def _needs_stage(stop_after: str | None, stage: str) -> bool:
    if stop_after is None:
        return True
    stop = str(stop_after or "").strip().lower()
    if stop not in _STAGE_ORDER:
        return True
    if stage not in _STAGE_ORDER:
        return True
    return _STAGE_ORDER.index(stage) <= _STAGE_ORDER.index(stop)


def _has_fixed_positions_extra(request: PipelineRequest) -> bool:
    if not isinstance(request.fixed_positions_extra, dict):
        return False
    for positions in request.fixed_positions_extra.values():
        if isinstance(positions, list) and positions:
            return True
    return False


def preflight_request(request: PipelineRequest, runner: PipelineRunner) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    required_inputs: list[dict[str, object]] = []
    detected: dict[str, object] = {}

    stop_after = str(request.stop_after or "").strip().lower() or None
    if stop_after is not None and stop_after not in _STAGE_ORDER:
        warnings.append(f"Unknown stop_after={stop_after!r}; defaulting to full pipeline.")
        stop_after = None

    target_fasta = str(request.target_fasta or "").strip()
    target_pdb = str(request.target_pdb or "").strip()
    has_target = bool(target_fasta or target_pdb)
    rfd3_active = _rfd3_active(request)
    diffdock_requested = _diffdock_requested(request)

    if not has_target and not rfd3_active:
        errors.append("One of target_fasta or target_pdb (or rfd3 inputs) is required.")
        required_inputs.append(
            {
                "id": "target_input",
                "message": "Provide target_fasta or target_pdb (raw text).",
                "required": True,
            }
        )

    query_seq = ""
    if target_fasta:
        try:
            records = parse_fasta(target_fasta)
            if not records:
                errors.append("target_fasta parse failed: no FASTA records found.")
            else:
                query_seq = str(records[0].sequence or "").strip()
                if not query_seq:
                    errors.append("target_fasta parse failed: empty sequence.")
        except Exception as exc:
            errors.append(f"target_fasta parse failed: {exc}")

    pdb_chains: list[str] | None = None
    if target_pdb:
        try:
            residues = residues_by_chain(target_pdb, only_atom_records=True)
            if not residues:
                errors.append("target_pdb parse failed: no ATOM records found.")
            else:
                pdb_chains = sorted(residues.keys())
                detected["pdb_chains"] = pdb_chains
                if request.design_chains:
                    missing = [c for c in request.design_chains if c not in residues]
                    if missing:
                        errors.append(f"design_chains not found in target_pdb: {missing}")
        except Exception as exc:
            errors.append(f"target_pdb parse failed: {exc}")

    if target_pdb and (request.ligand_resnames or request.ligand_atom_chains):
        try:
            has_ligand = ligand_atoms_present(
                target_pdb,
                chains=request.design_chains,
                ligand_resnames=request.ligand_resnames,
                ligand_atom_chains=request.ligand_atom_chains,
            )
            if not has_ligand:
                warnings.append(
                    "ligand_resnames/ligand_atom_chains provided but no matching ligand atoms found in target_pdb."
                )
        except Exception as exc:
            warnings.append(f"ligand mask check failed: {exc}")

    if (
        (not target_pdb)
        and (not request.dry_run)
        and (stop_after != "msa")
        and (not _has_fixed_positions_extra(request))
        and (not (request.ligand_atom_chains or []))
        and (not rfd3_active)
    ):
        required_inputs.append(
            {
                "id": "fixed_positions_extra",
                "message": (
                    "Sequence-only input requires fixed_positions_extra (1-based query/FASTA numbering) or "
                    "a target_pdb with ligand masking (ligand_resnames/ligand_atom_chains)."
                ),
                "required": True,
            }
        )

    if request.conservation_tiers is not None and len(request.conservation_tiers) == 0:
        errors.append("conservation_tiers cannot be empty.")

    # Endpoint/service availability checks (honor auto_recover).
    def _warn_or_error(msg: str) -> None:
        if request.auto_recover:
            warnings.append(msg)
        else:
            errors.append(msg)

    if _needs_stage(stop_after, "msa") and runner.mmseqs is None:
        _warn_or_error("MMseqs client not configured; MSA will fall back to query-only if auto_recover is enabled.")

    if _needs_stage(stop_after, "design") and runner.proteinmpnn is None:
        _warn_or_error("ProteinMPNN client not configured; design will fall back to dummy sequences if auto_recover is enabled.")

    if _needs_stage(stop_after, "soluprot") and runner.soluprot is None:
        warnings.append("SoluProt service not configured; solubility filtering will be skipped.")

    if _needs_stage(stop_after, "af2") and runner.af2 is None:
        _warn_or_error("AlphaFold2 not configured; AF2 scoring will be skipped if auto_recover is enabled.")

    if rfd3_active and runner.rfd3 is None:
        _warn_or_error("RFD3 requested but endpoint is not configured (set RFD3_ENDPOINT_ID).")

    if diffdock_requested and runner.diffdock is None:
        _warn_or_error("DiffDock requested but endpoint is not configured (set DIFFDOCK_ENDPOINT_ID).")

    # AF2 input validation (only if AF2 stage is needed and sequence is available).
    if _needs_stage(stop_after, "af2"):
        seq_for_af2 = ""
        if query_seq:
            seq_for_af2 = query_seq
        elif target_pdb:
            try:
                seqs = sequence_by_chain(target_pdb, chains=request.design_chains)
                if seqs:
                    order = request.design_chains or sorted(seqs.keys())
                    parts = [_clean_protein_sequence(seqs.get(c, "")) for c in order if seqs.get(c)]
                    seq_for_af2 = "/".join(p for p in parts if p)
            except Exception as exc:
                warnings.append(f"AF2 precheck skipped: failed to extract sequence from target_pdb ({exc})")

        if seq_for_af2:
            chain_count = len(_split_multichain_sequence(seq_for_af2))
            resolved_preset = _resolve_af2_model_preset(request.af2_model_preset, chain_count=chain_count)
            detected["af2_model_preset_resolved"] = resolved_preset
            try:
                _validate_af2_chain_sequences(
                    seq_for_af2,
                    model_preset=resolved_preset,
                    chain_ids=request.design_chains,
                )
            except Exception as exc:
                errors.append(str(exc))

    ok = not errors and not required_inputs
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "required_inputs": required_inputs,
        "detected": detected,
        "normalized_request": asdict(request),
    }
