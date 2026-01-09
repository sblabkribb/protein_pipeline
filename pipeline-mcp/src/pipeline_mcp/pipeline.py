from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any
from collections.abc import Callable

from .bio.a3m import compute_conservation
from .bio.a3m import decode_a3m_gz_b64
from .bio.fasta import FastaRecord
from .bio.fasta import parse_fasta
from .bio.fasta import to_fasta
from .bio.pdb import ligand_proximity_mask
from .bio.pdb import residues_by_chain
from .clients.mmseqs import MMseqsClient
from .clients.proteinmpnn import ProteinMPNNClient
from .clients.soluprot import SoluProtClient
from .models import PipelineRequest
from .models import PipelineResult
from .models import SequenceRecord
from .models import TierResult
from .storage import RunPaths
from .storage import init_run
from .storage import new_run_id
from .storage import set_status
from .storage import write_json


_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


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


def _safe_id(value: str) -> str:
    safe = _SAFE_ID_RE.sub("_", value).strip("._-")
    return safe[:128] or "id"


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


def _validate_proteinmpnn_fixed_positions(
    *,
    pdb_text: str,
    design_chains: list[str] | None,
    fixed_positions_by_chain: dict[str, list[int]],
    native: SequenceRecord | None,
    samples: list[SequenceRecord],
) -> dict[str, Any]:
    fixed_total = sum(len(v) for v in fixed_positions_by_chain.values())
    if fixed_total <= 0:
        return {"ok": True, "fixed_positions_total": 0, "samples_checked": len(samples), "errors": []}

    residues = residues_by_chain(pdb_text, only_atom_records=True)
    chain_order = sorted(design_chains) if design_chains else sorted(residues.keys())
    missing_chains = [c for c in chain_order if c not in residues]
    chain_lengths: dict[str, int] = {c: len(residues[c]) for c in chain_order if c in residues}
    total_len = sum(chain_lengths.get(c, 0) for c in chain_order)

    errors: list[str] = []
    if missing_chains:
        errors.append(f"Chains missing in PDB ATOM records: {missing_chains}")
    if native is None or not native.sequence:
        errors.append("ProteinMPNN did not return a native sequence")
    elif total_len > 0 and len(native.sequence) != total_len:
        errors.append(f"Native sequence length mismatch: native={len(native.sequence)} vs pdb_sum={total_len}")

    if native is None:
        native_seq = ""
    else:
        native_seq = native.sequence
    for s in samples:
        if s.sequence and native_seq and len(s.sequence) != len(native_seq):
            errors.append(f"Sample length mismatch: id={s.id} sample={len(s.sequence)} native={len(native_seq)}")

    max_mismatches_per_chain = 25
    sample_summaries: list[dict[str, Any]] = []
    ok = not errors
    for s in samples:
        mismatch_count = 0
        mismatches_by_chain: dict[str, list[dict[str, Any]]] = {}
        out_of_range: dict[str, list[int]] = {}

        offset = 0
        for chain_id in chain_order:
            chain_len = chain_lengths.get(chain_id, 0)
            native_chain = native_seq[offset : offset + chain_len]
            sample_chain = s.sequence[offset : offset + chain_len]
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


@dataclass(frozen=True)
class PipelineRunner:
    output_root: str
    mmseqs: MMseqsClient | None = None
    proteinmpnn: ProteinMPNNClient | None = None
    soluprot: SoluProtClient | None = None
    af2: Any | None = None

    def run(self, request: PipelineRequest, *, run_id: str | None = None) -> PipelineResult:
        run_id = run_id or new_run_id("pipeline")
        paths = init_run(self.output_root, run_id)
        set_status(paths, stage="init", state="running")

        write_json(paths.request_json, asdict(request))
        errors: list[str] = []

        msa_a3m_path = None
        msa_tsv_path = None
        conservation_path = None
        ligand_mask_path = None
        tier_results: list[TierResult] = []

        try:
            msa_dir = _ensure_dir(paths.root / "msa")
            tiers_dir = _ensure_dir(paths.root / "tiers")

            target_records = parse_fasta(request.target_fasta)
            target_query_fasta = to_fasta([target_records[0]])
            target_pdb_text = request.target_pdb
            if request.dry_run and not target_pdb_text:
                target_pdb_text = _dummy_backbone_pdb(target_records[0].sequence, chain_id="A")

            set_status(paths, stage="mmseqs_msa", state="running")
            msa_tsv_text, a3m_text = self._get_msa(
                target_query_fasta,
                msa_dir,
                request,
                on_job_id=lambda job_id: (
                    write_json(msa_dir / "runpod_job.json", {"job_id": job_id}),
                    set_status(paths, stage="mmseqs_msa", state="running", detail=f"runpod_job_id={job_id}"),
                ),
            )
            msa_tsv_path = str(msa_dir / "result.tsv")
            msa_a3m_path = str(msa_dir / "result.a3m")

            if request.stop_after == "msa":
                set_status(paths, stage="mmseqs_msa", state="completed")
                result = PipelineResult(
                    run_id=run_id,
                    output_dir=str(paths.root),
                    msa_a3m_path=msa_a3m_path,
                    msa_tsv_path=msa_tsv_path,
                    conservation_path=None,
                    ligand_mask_path=None,
                    tiers=[],
                    errors=[],
                )
                write_json(paths.summary_json, asdict(result))
                set_status(paths, stage="done", state="completed")
                return result

            set_status(paths, stage="conservation", state="running")
            conservation = compute_conservation(
                a3m_text,
                tiers=request.conservation_tiers,
                mode=request.conservation_mode,
            )
            conservation_payload = {
                "query_length": conservation.query_length,
                "scores": conservation.scores,
                "fixed_positions_by_tier": conservation.fixed_positions_by_tier,
                "mode": request.conservation_mode,
                "tiers": request.conservation_tiers,
            }
            conservation_path = str(paths.root / "conservation.json")
            write_json(Path(conservation_path), conservation_payload)
            set_status(paths, stage="conservation", state="completed")

            set_status(paths, stage="ligand_mask", state="running")
            pdb_chains = list(residues_by_chain(target_pdb_text, only_atom_records=True).keys())
            design_chains = request.design_chains or pdb_chains or None
            ligand_mask = ligand_proximity_mask(
                target_pdb_text,
                chains=design_chains,
                distance_angstrom=request.ligand_mask_distance,
                ligand_resnames=request.ligand_resnames,
            )
            ligand_mask_path = str(paths.root / "ligand_mask.json")
            write_json(Path(ligand_mask_path), ligand_mask)
            set_status(paths, stage="ligand_mask", state="completed")

            for tier in request.conservation_tiers:
                tier_str = _tier_key(tier)
                tier_dir = _ensure_dir(tiers_dir / tier_str)

                tier_fixed = conservation.fixed_positions_by_tier.get(tier, [])
                fixed_positions_by_chain: dict[str, list[int]] = {}
                for chain_id in design_chains or list(ligand_mask.keys()) or ["A"]:
                    chain_fixed = set(tier_fixed)
                    chain_fixed.update(ligand_mask.get(chain_id, []))
                    fixed_positions_by_chain[chain_id] = sorted(chain_fixed)

                write_json(tier_dir / "fixed_positions.json", fixed_positions_by_chain)

                set_status(paths, stage=f"proteinmpnn_{tier_str}", state="running")
                native, samples = self._run_proteinmpnn(
                    tier_dir,
                    request,
                    pdb_text=target_pdb_text,
                    tier_str=tier_str,
                    design_chains=design_chains,
                    fixed_positions_by_chain=fixed_positions_by_chain,
                    on_job_id=lambda job_id, stage=f"proteinmpnn_{tier_str}", dir_=tier_dir: (
                        write_json(dir_ / "runpod_job.json", {"job_id": job_id}),
                        set_status(paths, stage=stage, state="running", detail=f"runpod_job_id={job_id}"),
                    ),
                )
                set_status(paths, stage=f"proteinmpnn_{tier_str}", state="completed")

                if request.stop_after == "design":
                    tier_results.append(
                        TierResult(
                            tier=tier,
                            fixed_positions=fixed_positions_by_chain,
                            proteinmpnn_native=native,
                            proteinmpnn_samples=samples,
                        )
                    )
                    continue

                set_status(paths, stage=f"soluprot_{tier_str}", state="running")
                passed = samples
                soluprot_scores: dict[str, float] | None = None
                passed_ids: list[str] | None = None
                soluprot_path = tier_dir / "soluprot.json"
                if samples and soluprot_path.exists() and not request.force:
                    try:
                        payload = json.loads(soluprot_path.read_text(encoding="utf-8"))
                    except Exception:
                        payload = None
                    if isinstance(payload, dict):
                        cached_scores = payload.get("scores")
                        if isinstance(cached_scores, dict):
                            soluprot_scores = {
                                str(k): float(v) for k, v in cached_scores.items() if isinstance(v, (int, float))
                            }
                            passed = [
                                s
                                for s in samples
                                if float(soluprot_scores.get(s.id, 0.0)) >= float(request.soluprot_cutoff)
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
                            passed = samples
                            passed_ids = [s.id for s in passed]
                        if passed:
                            _write_text(
                                tier_dir / "designs_filtered.fasta",
                                to_fasta([FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in passed]),
                            )
                elif samples:
                    if request.dry_run:
                        scores = {s.id: (0.6 if (i % 2 == 0) else 0.4) for i, s in enumerate(samples)}
                        soluprot_scores = scores
                        passed = [
                            s for s in samples if float(scores.get(s.id, 0.0)) >= float(request.soluprot_cutoff)
                        ]
                        passed_ids = [s.id for s in passed]
                        write_json(
                            soluprot_path,
                            {"scores": scores, "cutoff": request.soluprot_cutoff, "passed_ids": passed_ids},
                        )
                    else:
                        if self.soluprot is None:
                            passed = samples
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
                            scores = self.soluprot.score(samples)
                            soluprot_scores = scores
                            passed = [
                                s for s in samples if float(scores.get(s.id, 0.0)) >= float(request.soluprot_cutoff)
                            ]
                            passed_ids = [s.id for s in passed]
                            write_json(
                                soluprot_path,
                                {"scores": scores, "cutoff": request.soluprot_cutoff, "passed_ids": passed_ids},
                            )

                    _write_text(
                        tier_dir / "designs_filtered.fasta",
                        to_fasta([FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in passed]),
                    )
                set_status(paths, stage=f"soluprot_{tier_str}", state="completed")

                if request.stop_after == "soluprot":
                    tier_results.append(
                        TierResult(
                            tier=tier,
                            fixed_positions=fixed_positions_by_chain,
                            proteinmpnn_native=native,
                            proteinmpnn_samples=samples,
                            soluprot_scores=soluprot_scores,
                            passed_ids=passed_ids,
                        )
                    )
                    continue

                af2_result = None
                af2_selected_ids: list[str] | None = None
                if passed:
                    set_status(paths, stage=f"af2_{tier_str}", state="running")
                    af2_dir = _ensure_dir(tier_dir / "af2")
                    af2_scores_path = tier_dir / "af2_scores.json"
                    af2_selected_path = tier_dir / "af2_selected.fasta"
                    af2_used_cache = False
                    if af2_scores_path.exists() and af2_selected_path.exists() and not request.force:
                        try:
                            cached = json.loads(af2_scores_path.read_text(encoding="utf-8"))
                        except Exception:
                            cached = None
                        cached_scores = cached.get("scores") if isinstance(cached, dict) else None
                        cached_model_preset = cached.get("model_preset") if isinstance(cached, dict) else None
                        cached_db_preset = cached.get("db_preset") if isinstance(cached, dict) else None
                        cached_max_template_date = cached.get("max_template_date") if isinstance(cached, dict) else None
                        if (
                            isinstance(cached_scores, dict)
                            and (cached_model_preset in {None, request.af2_model_preset})
                            and (cached_db_preset in {None, request.af2_db_preset})
                            and (cached_max_template_date in {None, request.af2_max_template_date})
                        ):
                            af2_scores = {
                                str(k): float(v) for k, v in cached_scores.items() if isinstance(v, (int, float))
                            }
                            selected_pairs = [
                                (seq_id, score)
                                for seq_id, score in af2_scores.items()
                                if score >= float(request.af2_plddt_cutoff)
                            ]
                            selected_pairs.sort(key=lambda t: t[1], reverse=True)
                            af2_selected_ids = [seq_id for seq_id, _ in selected_pairs[: int(request.af2_top_k)]]
                            selected_records = [s for s in passed if af2_selected_ids and s.id in set(af2_selected_ids)]
                            _write_text(
                                af2_selected_path,
                                to_fasta(
                                    [FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in selected_records]
                                ),
                            )
                            write_json(
                                af2_scores_path,
                                {
                                    "scores": af2_scores,
                                    "cutoff": request.af2_plddt_cutoff,
                                    "top_k": request.af2_top_k,
                                    "selected_ids": af2_selected_ids,
                                    "model_preset": request.af2_model_preset,
                                    "db_preset": request.af2_db_preset,
                                    "max_template_date": request.af2_max_template_date,
                                    "cached": True,
                                },
                            )
                            set_status(paths, stage=f"af2_{tier_str}", state="completed", detail="cached")
                            af2_result = None
                            af2_used_cache = True
                        else:
                            # Cache exists but config differs; fall back to recompute unless force=false but cache invalid.
                            pass
                    if not af2_used_cache:
                        if request.dry_run:
                            # Deterministic fake pLDDT scores for tests.
                            af2_result = {
                                s.id: {
                                    "best_plddt": (90.0 if (i % 2 == 0) else 80.0),
                                    "best_model": None,
                                    "ranking_debug": {},
                                    "ranked_0_pdb": None,
                                }
                                for i, s in enumerate(passed)
                            }
                        else:
                            if self.af2 is None:
                                raise RuntimeError("AlphaFold2 is required for this pipeline; set ALPHAFOLD2_ENDPOINT_ID (RunPod) or AF2_URL")
                            jobs_path = af2_dir / "runpod_jobs.json"
                            jobs: dict[str, str] = {}

                            def _on_af2_job_id(seq_id: str, job_id: str) -> None:
                                jobs[seq_id] = job_id
                                write_json(jobs_path, {"jobs": dict(jobs)})
                                set_status(
                                    paths,
                                    stage=f"af2_{tier_str}",
                                    state="running",
                                    detail=f"runpod_job_id={job_id} seq_id={seq_id}",
                                )

                            try:
                                af2_result = self.af2.predict(
                                    passed,
                                    model_preset=request.af2_model_preset,
                                    db_preset=request.af2_db_preset,
                                    max_template_date=request.af2_max_template_date,
                                    extra_flags=request.af2_extra_flags,
                                    on_job_id=_on_af2_job_id,
                                )
                            except TypeError:
                                af2_result = self.af2.predict(
                                    passed,
                                    model_preset=request.af2_model_preset,
                                    db_preset=request.af2_db_preset,
                                    max_template_date=request.af2_max_template_date,
                                    extra_flags=request.af2_extra_flags,
                                )

                        af2_scores: dict[str, float] = {}
                        for seq in passed:
                            rec = (af2_result or {}).get(seq.id, {}) if isinstance(af2_result, dict) else {}
                            if not isinstance(rec, dict):
                                continue
                            score = rec.get("best_plddt")
                            if isinstance(score, (int, float)):
                                af2_scores[seq.id] = float(score)

                            seq_dir = _ensure_dir(af2_dir / _safe_id(seq.id))
                            if isinstance(rec.get("ranking_debug"), dict):
                                write_json(seq_dir / "ranking_debug.json", rec["ranking_debug"])
                            ranked0 = rec.get("ranked_0_pdb")
                            if isinstance(ranked0, str) and ranked0.strip():
                                _write_text(seq_dir / "ranked_0.pdb", ranked0)
                            write_json(
                                seq_dir / "metrics.json",
                                {
                                    "best_plddt": af2_scores.get(seq.id),
                                    "best_model": rec.get("best_model"),
                                    "archive_name": rec.get("archive_name"),
                                },
                            )

                        selected_pairs = [
                            (seq_id, score)
                            for seq_id, score in af2_scores.items()
                            if score >= float(request.af2_plddt_cutoff)
                        ]
                        selected_pairs.sort(key=lambda t: t[1], reverse=True)
                        af2_selected_ids = [seq_id for seq_id, _ in selected_pairs[: int(request.af2_top_k)]]

                        selected_records = [s for s in passed if s.id in set(af2_selected_ids)]
                        _write_text(
                            af2_selected_path,
                            to_fasta(
                                [FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in selected_records]
                            ),
                        )
                        write_json(
                            af2_scores_path,
                            {
                                "scores": af2_scores,
                                "cutoff": request.af2_plddt_cutoff,
                                "top_k": request.af2_top_k,
                                "selected_ids": af2_selected_ids,
                                "model_preset": request.af2_model_preset,
                                "db_preset": request.af2_db_preset,
                                "max_template_date": request.af2_max_template_date,
                            },
                        )
                        set_status(paths, stage=f"af2_{tier_str}", state="completed")

                if request.stop_after == "af2":
                    tier_results.append(
                        TierResult(
                            tier=tier,
                            fixed_positions=fixed_positions_by_chain,
                            proteinmpnn_native=native,
                            proteinmpnn_samples=samples,
                            soluprot_scores=soluprot_scores,
                            passed_ids=passed_ids,
                            af2=af2_result,
                            af2_selected_ids=af2_selected_ids,
                        )
                    )
                    continue

                novelty_tsv = None
                novelty_candidates = [s for s in passed if af2_selected_ids and s.id in set(af2_selected_ids)]
                if self.mmseqs is not None and novelty_candidates:
                    set_status(paths, stage=f"novelty_{tier_str}", state="running")
                    query_fasta = to_fasta(
                        [FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in novelty_candidates]
                    )
                    novelty_out = self.mmseqs.search(
                        query_fasta=query_fasta,
                        target_db=request.novelty_target_db,
                        threads=request.mmseqs_threads,
                        use_gpu=request.mmseqs_use_gpu,
                        include_taxonomy=False,
                        return_a3m=False,
                        max_seqs=min(300, request.mmseqs_max_seqs),
                    )
                    novelty_tsv = str(novelty_out.get("tsv") or "")
                    _write_text(tier_dir / "novelty.tsv", novelty_tsv)
                    set_status(paths, stage=f"novelty_{tier_str}", state="completed")

                tier_results.append(
                    TierResult(
                        tier=tier,
                        fixed_positions=fixed_positions_by_chain,
                        proteinmpnn_native=native,
                        proteinmpnn_samples=samples,
                        soluprot_scores=soluprot_scores,
                        passed_ids=passed_ids,
                        af2=af2_result,
                        af2_selected_ids=af2_selected_ids,
                        novelty_tsv=novelty_tsv,
                    )
                )

            result = PipelineResult(
                run_id=run_id,
                output_dir=str(paths.root),
                msa_a3m_path=msa_a3m_path,
                msa_tsv_path=msa_tsv_path,
                conservation_path=conservation_path,
                ligand_mask_path=ligand_mask_path,
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
            set_status(paths, stage="done", state="completed")
            return result
        except Exception as exc:
            errors.append(str(exc))
            set_status(paths, stage="error", state="failed", detail=str(exc))
            result = PipelineResult(
                run_id=run_id,
                output_dir=str(paths.root),
                msa_a3m_path=msa_a3m_path,
                msa_tsv_path=msa_tsv_path,
                conservation_path=conservation_path,
                ligand_mask_path=ligand_mask_path,
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
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

        if tsv_path.exists() and a3m_path.exists() and not request.force:
            return tsv_path.read_text(encoding="utf-8"), a3m_path.read_text(encoding="utf-8")

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
            return tsv, a3m

        if self.mmseqs is None:
            raise RuntimeError("MMseqs client is not configured")

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

        if out_json.exists() and out_fasta.exists() and not request.force:
            try:
                payload = json.loads(out_json.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            native = payload.get("native")
            samples = payload.get("samples")
            cached_fixed_positions = _normalize_fixed_positions_by_chain(payload.get("fixed_positions"))

            expected_fixed_positions = {k: sorted(set(int(x) for x in v)) for k, v in fixed_positions_by_chain.items()}
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
            cached_request = payload.get("request")

            if cached_fixed_positions is None or cached_fixed_positions != expected_fixed_positions:
                pass
            elif not isinstance(cached_request, dict) or cached_request != expected_request:
                pass
            else:
                native_rec = None
                if isinstance(native, dict) and native.get("sequence"):
                    native_rec = SequenceRecord(id=str(native.get("id") or "native"), sequence=str(native["sequence"]), header=str(native.get("header") or "native"))
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
                            "fixed_positions_total": sum(len(v) for v in expected_fixed_positions.values()),
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
            query = parse_fasta(request.target_fasta)[0].sequence
            samples = [
                SequenceRecord(id=f"{tier_str}_s1", header=f"{tier_str},sample=1", sequence=query),
                SequenceRecord(id=f"{tier_str}_s2", header=f"{tier_str},sample=2", sequence=query[:-1] + "A"),
            ]
            native = SequenceRecord(id="native", header="native", sequence=query)
            _write_text(out_fasta, to_fasta([FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in [native, *samples]]))
            write_json(
                out_json,
                {
                    "request": {
                        "pdb_path_chains": sorted(design_chains) if design_chains else None,
                        "use_soluble_model": True,
                        "model_name": "v_48_020",
                        "num_seq_per_target": int(request.num_seq_per_tier),
                        "batch_size": int(request.batch_size),
                        "sampling_temp": float(request.sampling_temp),
                        "seed": int(request.seed),
                        "backbone_noise": 0.0,
                    },
                    "native": native.__dict__,
                    "samples": [s.__dict__ for s in samples],
                    "fixed_positions": fixed_positions_by_chain,
                },
            )
            write_json(
                out_fixed_positions_check,
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "dry_run",
                    "fixed_positions_total": sum(len(v) for v in fixed_positions_by_chain.values()),
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
        _write_text(out_fasta, to_fasta([FastaRecord(header=native.header or native.id, sequence=native.sequence)] + [FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in samples]))
        write_json(
            out_json,
            {
                "request": {
                    "pdb_path_chains": sorted(design_chains) if design_chains else None,
                    "use_soluble_model": True,
                    "model_name": "v_48_020",
                    "num_seq_per_target": int(request.num_seq_per_tier),
                    "batch_size": int(request.batch_size),
                    "sampling_temp": float(request.sampling_temp),
                    "seed": int(request.seed),
                    "backbone_noise": 0.0,
                },
                "native": native.__dict__,
                "samples": [s.__dict__ for s in samples],
                "fixed_positions": fixed_positions_by_chain,
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
                raise RuntimeError(f"ProteinMPNN output violates fixed_positions for tier={tier_str}; see {out_fixed_positions_check}")
        return native, samples
