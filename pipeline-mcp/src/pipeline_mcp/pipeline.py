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
from .bio.a3m import filter_a3m
from .bio.a3m import msa_quality
from .bio.a3m import strip_insertions
from .bio.a3m import weights_from_mmseqs_cluster_tsv
from .bio.fasta import FastaRecord
from .bio.fasta import parse_fasta
from .bio.fasta import to_fasta
from .bio.alignment import global_alignment_mapping
from .bio.pdb import ligand_proximity_mask
from .bio.pdb import preprocess_pdb
from .bio.pdb import residues_by_chain
from .bio.pdb import sequence_by_chain
from .clients.mmseqs import MMseqsClient
from .clients.proteinmpnn import ProteinMPNNClient
from .clients.soluprot import SoluProtClient
from .models import PipelineRequest
from .models import PipelineResult
from .models import SequenceRecord
from .models import TierResult
from .mutation_report import write_mutation_reports
from .storage import RunPaths
from .storage import init_run
from .storage import new_run_id
from .storage import set_status
from .storage import write_json


_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_AF2_ALLOWED_AA = set("ACDEFGHIKLMNPQRSTVWYX")


def _format_set(values: set[str], *, limit: int = 12) -> str:
    items = sorted(values)
    if len(items) <= limit:
        return "{" + ", ".join(repr(x) for x in items) + "}"
    head = items[:limit]
    return "{" + ", ".join(repr(x) for x in head) + f", ... (+{len(items) - limit})" + "}"


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


class PipelineInputRequired(ValueError):
    def __init__(self, *, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _safe_id(value: str) -> str:
    safe = _SAFE_ID_RE.sub("_", value).strip("._-")
    return safe[:128] or "id"


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


def _split_multichain_sequence(seq: str) -> list[str]:
    seq = str(seq or "").strip()
    if not seq:
        return []
    parts = [p.strip() for p in seq.split("/") if p.strip()]
    return parts if len(parts) > 1 else [seq]


def _clean_protein_sequence(seq: str) -> str:
    return "".join(ch for ch in str(seq or "").upper() if ch.isalpha())


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
    if preset.startswith("monomer") and len(chains) > 1 and not _env_true("PIPELINE_AF2_MONOMER_FIRST_CHAIN"):
        used_ids = (chain_ids or [])[: min(2, len(chain_ids or []))]
        raise ValueError(
            "AF2 input validation failed: monomer preset cannot accept multi-chain sequence separated by '/'. "
            f"found_chains={len(chains)} chain_ids={used_ids or None}. "
            "Fix: (1) run as multimer: set af2_model_preset='multimer' and design_chains=['A','B',...], "
            "or (2) run as monomer on a single chain: set design_chains=['A'] so ProteinMPNN/ligand mask/fixed positions "
            "are computed for one chain consistently. "
            "If you really want to evaluate only the first chain in monomer mode, set PIPELINE_AF2_MONOMER_FIRST_CHAIN=1."
        )

    if preset.startswith("multimer") and chain_ids is not None and len(chain_ids) > 1 and len(chains) != len(chain_ids):
        raise ValueError(
            "AF2 input validation failed: multimer preset expects the number of chains to match design_chains. "
            f"design_chains={chain_ids} found_chains={len(chains)}. "
            "Fix: ensure ProteinMPNN outputs chains in 'A/B/...' order matching design_chains, "
            "or set af2_model_preset='monomer' and design_chains=['A']."
        )

    if preset.startswith("monomer") and len(chains) > 1:
        chains = [chains[0]]

    return chains


def _prepare_af2_sequence(seq: str, *, model_preset: str, chain_ids: list[str] | None) -> str:
    preset = str(model_preset or "").strip() or "monomer"
    chains = _validate_af2_chain_sequences(seq, model_preset=preset, chain_ids=chain_ids)
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
        label = label or f"chain_{idx+1}"
        out += f"\n>{label}\n{chain_seq}"
    return out


def _first_chain_sequence(seq: str) -> str:
    seq = str(seq or "").strip()
    if "/" in seq:
        return seq.split("/", 1)[0]
    return seq


def _monomerize_records(records: list[SequenceRecord], model_preset: str) -> list[SequenceRecord]:
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
        return {"ok": True, "fixed_positions_total": 0, "samples_checked": len(samples), "errors": []}

    residues = residues_by_chain(pdb_text, only_atom_records=True)
    chain_order = list(design_chains) if design_chains else list(residues.keys())
    missing_chains = [c for c in chain_order if c not in residues]
    chain_lengths: dict[str, int] = {c: len(residues[c]) for c in chain_order if c in residues}
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
            errors.append(f"Native sequence length mismatch: native={len(native_seq)} vs pdb_sum={total_len}")

    if native is None:
        native_raw = ""
        native_seq = ""
    else:
        native_raw = str(native.sequence or "")
        native_seq = _clean_sequence(native_raw)
    for s in samples:
        sample_seq = _clean_sequence(str(s.sequence or ""))
        if sample_seq and native_seq and len(sample_seq) != len(native_seq):
            errors.append(f"Sample length mismatch: id={s.id} sample={len(sample_seq)} native={len(native_seq)}")

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
        msa_filtered_a3m_path = None
        msa_tsv_path = None
        conservation_path = None
        ligand_mask_path = None
        tier_results: list[TierResult] = []

        try:
            msa_dir = _ensure_dir(paths.root / "msa")
            tiers_dir = _ensure_dir(paths.root / "tiers")

            target_pdb_text = str(request.target_pdb or "")
            had_target_pdb_input = bool(target_pdb_text.strip())
            if target_pdb_text.strip() and (
                bool(request.pdb_strip_nonpositive_resseq) or bool(request.pdb_renumber_resseq_from_1)
            ):
                set_status(paths, stage="pdb_preprocess", state="running")
                original_pdb_text = target_pdb_text
                target_pdb_text, numbering = preprocess_pdb(
                    original_pdb_text,
                    chains=request.design_chains,
                    strip_nonpositive_resseq=bool(request.pdb_strip_nonpositive_resseq),
                    renumber_resseq_from_1=bool(request.pdb_renumber_resseq_from_1),
                )
                _write_text(paths.root / "target.original.pdb", original_pdb_text)
                write_json(
                    paths.root / "pdb_numbering.json",
                    {
                        "chains": request.design_chains,
                        "strip_nonpositive_resseq": bool(request.pdb_strip_nonpositive_resseq),
                        "renumber_resseq_from_1": bool(request.pdb_renumber_resseq_from_1),
                        "mapping": numbering,
                    },
                )
                set_status(paths, stage="pdb_preprocess", state="completed")

            if str(request.target_fasta or "").strip():
                target_record = parse_fasta(request.target_fasta)[0]
            else:
                if not target_pdb_text.strip():
                    raise ValueError("One of target_fasta or target_pdb is required")
                extracted = sequence_by_chain(target_pdb_text, chains=request.design_chains)
                if not extracted:
                    raise ValueError("Unable to extract protein sequence from target_pdb ATOM records")
                if request.design_chains:
                    chain_id = request.design_chains[0]
                    seq = extracted.get(chain_id)
                    if not seq:
                        chain_id, seq = next(iter(extracted.items()))
                else:
                    chain_id, seq = next(iter(extracted.items()))
                target_record = FastaRecord(header=f"pdb_chain_{chain_id}", sequence=seq)

            target_query_fasta = to_fasta([target_record])
            _write_text(paths.root / "target.fasta", target_query_fasta)

            has_fixed_positions_extra = False
            if isinstance(request.fixed_positions_extra, dict):
                for positions in request.fixed_positions_extra.values():
                    if isinstance(positions, list) and positions:
                        has_fixed_positions_extra = True
                        break

            if (
                (not had_target_pdb_input)
                and (not request.dry_run)
                and (request.stop_after != "msa")
                and (not has_fixed_positions_extra)
                and (not (request.ligand_atom_chains or []))
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

            if request.dry_run and not target_pdb_text.strip():
                target_pdb_text = _dummy_backbone_pdb(target_record.sequence, chain_id="A")
            if target_pdb_text.strip():
                _write_text(paths.root / "target.pdb", target_pdb_text)

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
                            "target_db": request.mmseqs_target_db,
                            "max_seqs": request.mmseqs_max_seqs,
                            "threads": request.mmseqs_threads,
                            "use_gpu": request.mmseqs_use_gpu,
                        },
                    ),
                    set_status(paths, stage="mmseqs_msa", state="running", detail=f"runpod_job_id={job_id}"),
                ),
            )
            msa_tsv_path = str(msa_dir / "result.tsv")
            msa_a3m_path = str(msa_dir / "result.a3m")

            filtered_a3m_text = a3m_text
            quality = msa_quality(a3m_text)
            if float(request.msa_min_coverage) > 0.0 or float(request.msa_min_identity) > 0.0:
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

            if request.stop_after == "msa":
                result = PipelineResult(
                    run_id=run_id,
                    output_dir=str(paths.root),
                    msa_a3m_path=msa_a3m_path,
                    msa_filtered_a3m_path=msa_filtered_a3m_path,
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
            conservation_weights: list[float] | None = None
            weighting = str(getattr(request, "conservation_weighting", "none") or "none").strip().lower()
            if weighting not in {"none", "mmseqs_cluster"}:
                raise ValueError("conservation_weighting must be one of: none, mmseqs_cluster")
            if weighting == "mmseqs_cluster":
                if request.dry_run:
                    write_json(
                        msa_dir / "sequence_weights.json",
                        {"method": "mmseqs_cluster", "skipped": True, "reason": "dry_run"},
                    )
                else:
                    if self.mmseqs is None:
                        raise RuntimeError("MMseqs client is required for conservation_weighting='mmseqs_cluster'")
                    raw_records = parse_fasta(filtered_a3m_text)
                    hit_ids: list[str] = []
                    fasta_parts: list[str] = []
                    for idx, rec in enumerate(raw_records[1:], start=1):
                        hit_id = f"h{idx:06d}"
                        hit_ids.append(hit_id)
                        ungapped = "".join(ch for ch in strip_insertions(rec.sequence) if ch.isalpha()).upper()
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
                            cluster_method=str(request.conservation_cluster_method or "linclust"),
                            min_seq_id=float(request.conservation_cluster_min_seq_id),
                            coverage=request.conservation_cluster_coverage,
                            cov_mode=request.conservation_cluster_cov_mode,
                            kmer_per_seq=request.conservation_cluster_kmer_per_seq,
                        )
                    if sequences_fasta.strip():
                        cluster_tsv = str(cluster_out.get("cluster_tsv") or "")
                        _write_text(msa_dir / "cluster.tsv", cluster_tsv)
                        weights_by_id = weights_from_mmseqs_cluster_tsv(cluster_tsv)
                        conservation_weights = [float(weights_by_id.get(hit_id, 1.0)) for hit_id in hit_ids]
                        write_json(
                            msa_dir / "sequence_weights.json",
                            {
                                "method": "mmseqs_cluster",
                                "cluster_method": str(request.conservation_cluster_method or "linclust"),
                                "min_seq_id": float(request.conservation_cluster_min_seq_id),
                                "coverage": request.conservation_cluster_coverage,
                                "cov_mode": request.conservation_cluster_cov_mode,
                                "kmer_per_seq": request.conservation_cluster_kmer_per_seq,
                                "hit_count": len(hit_ids),
                                "id_scheme": "h{index:06d} (A3M hit order)",
                                "weights": list(conservation_weights),
                                "weight_stats": {
                                    "min": min(conservation_weights) if conservation_weights else None,
                                    "max": max(conservation_weights) if conservation_weights else None,
                                    "mean": (sum(conservation_weights) / len(conservation_weights))
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
            }
            conservation_path = str(paths.root / "conservation.json")
            write_json(Path(conservation_path), conservation_payload)
            set_status(paths, stage="conservation", state="completed")

            if not target_pdb_text.strip():
                set_status(paths, stage="af2_target", state="running")
                target_pdb_path = paths.root / "target.pdb"
                if target_pdb_path.exists() and not request.force:
                    target_pdb_text = target_pdb_path.read_text(encoding="utf-8")
                    set_status(paths, stage="af2_target", state="completed", detail="cached")
                else:
                    if self.af2 is None:
                        raise RuntimeError(
                            "target_pdb is missing; provide target_pdb or configure AlphaFold2 (ALPHAFOLD2_ENDPOINT_ID or AF2_URL)"
                        )

                    jobs_path = paths.root / "af2_target_runpod_job.json"

                    def _on_target_job_id(seq_id: str, job_id: str) -> None:
                        write_json(jobs_path, {"seq_id": seq_id, "job_id": job_id})
                        set_status(paths, stage="af2_target", state="running", detail=f"runpod_job_id={job_id}")

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
                        af2_out = self.af2.predict(
                            [target_af2_input],
                            model_preset=target_af2_preset,
                            db_preset=request.af2_db_preset,
                            max_template_date=request.af2_max_template_date,
                            extra_flags=request.af2_extra_flags,
                            on_job_id=_on_target_job_id,
                        )
                    except TypeError:
                        af2_out = self.af2.predict(
                            [target_af2_input],
                            model_preset=target_af2_preset,
                            db_preset=request.af2_db_preset,
                            max_template_date=request.af2_max_template_date,
                            extra_flags=request.af2_extra_flags,
                        )

                    rec = af2_out.get("target") if isinstance(af2_out, dict) else None
                    if not isinstance(rec, dict):
                        raise RuntimeError(f"AlphaFold2 did not return a record for target: {type(rec).__name__}")
                    ranked0 = rec.get("ranked_0_pdb") or rec.get("pdb") or rec.get("pdb_text")
                    if not isinstance(ranked0, str) or not ranked0.strip():
                        raise RuntimeError("AlphaFold2 did not return ranked_0_pdb for target sequence")

                    target_pdb_text = ranked0
                    _write_text(target_pdb_path, target_pdb_text)
                    if isinstance(rec.get("ranking_debug"), dict):
                        write_json(paths.root / "af2_target_ranking_debug.json", rec["ranking_debug"])
                    write_json(
                        paths.root / "af2_target_metrics.json",
                        {"best_plddt": rec.get("best_plddt"), "best_model": rec.get("best_model")},
                    )
                    set_status(paths, stage="af2_target", state="completed")

            set_status(paths, stage="ligand_mask", state="running")
            pdb_chains = list(residues_by_chain(target_pdb_text, only_atom_records=True).keys())
            requested_chains = request.design_chains or pdb_chains or None
            af2_model_preset = _resolve_af2_model_preset(
                request.af2_model_preset,
                chain_count=len(requested_chains or []),
            )
            chain_note = None
            if requested_chains and _is_monomer_preset(af2_model_preset):
                if len(requested_chains) > 1:
                    chain_note = f"monomer preset: using first chain only ({requested_chains[0]})"
                design_chains = [requested_chains[0]]
            else:
                design_chains = requested_chains

            write_json(
                paths.root / "chain_strategy.json",
                {
                    "af2_model_preset": af2_model_preset,
                    "pdb_chains": pdb_chains,
                    "requested_design_chains": request.design_chains,
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

            set_status(paths, stage="query_pdb_check", state="running")
            query_seq = _clean_protein_sequence(target_record.sequence)
            pdb_seq_by_chain = sequence_by_chain(target_pdb_text, chains=design_chains)
            policy = _normalize_policy(request.query_pdb_policy)
            min_identity = float(request.query_pdb_min_identity)

            query_to_pdb_map_by_chain: dict[str, list[int | None]] = {}
            query_pdb_report: dict[str, object] = {
                "policy": policy,
                "min_query_identity": min_identity,
                "query_len": len(query_seq),
                "chains": {},
            }
            problems: list[str] = []
            warnings: list[str] = []
            both_provided = bool(str(request.target_fasta or "").strip()) and bool(str(request.target_pdb or "").strip())

            for chain_id in design_chains or sorted(pdb_seq_by_chain.keys()):
                chain_seq_raw = pdb_seq_by_chain.get(chain_id, "")
                chain_seq = _clean_protein_sequence(chain_seq_raw)
                if not chain_seq:
                    problems.append(f"chain {chain_id}: empty sequence extracted from target_pdb")
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
            write_json(paths.root / "query_pdb_alignment.json", query_pdb_report)
            if problems and policy == "error":
                raise ValueError(
                    "target_fasta/target_pdb mismatch (query_pdb_check failed): "
                    + "; ".join(problems)
                    + ". Fix: make sure target_fasta matches the selected PDB chain(s) "
                    "(design_chains), or omit target_fasta to derive the query from target_pdb, "
                    "or relax with query_pdb_policy='warn'/'ignore' and/or query_pdb_min_identity. "
                    "See query_pdb_alignment.json for details."
                )

            detail_parts: list[str] = []
            if problems and policy == "warn":
                detail_parts.append("; ".join(problems))
            if warnings and policy != "ignore":
                detail_parts.append("; ".join(warnings))

            set_status(
                paths,
                stage="query_pdb_check",
                state="completed",
                detail=(" | ".join(detail_parts)[:500] if detail_parts else None),
            )

            ligand_mask = ligand_proximity_mask(
                target_pdb_text,
                chains=design_chains,
                distance_angstrom=request.ligand_mask_distance,
                ligand_resnames=request.ligand_resnames,
                ligand_atom_chains=request.ligand_atom_chains,
            )
            ligand_mask_path = str(paths.root / "ligand_mask.json")
            write_json(Path(ligand_mask_path), ligand_mask)
            set_status(paths, stage="ligand_mask", state="completed")

            for tier in request.conservation_tiers:
                tier_str = _tier_key(tier)
                tier_dir = _ensure_dir(tiers_dir / tier_str)

                tier_fixed = conservation.fixed_positions_by_tier.get(tier, [])
                fixed_positions_by_chain: dict[str, list[int]] = {}
                extra_fixed = request.fixed_positions_extra or {}
                for chain_id in design_chains or list(ligand_mask.keys()) or ["A"]:
                    mapped: list[int] = []
                    mapping = query_to_pdb_map_by_chain.get(chain_id)
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

                mutation_paths = write_mutation_reports(
                    tier_dir,
                    native=native,
                    samples=samples,
                    fixed_positions_by_chain=fixed_positions_by_chain,
                    design_chains=design_chains,
                )
                mutation_report_path = mutation_paths.get("mutation_report_path")
                mutations_by_position_tsv = mutation_paths.get("mutations_by_position_tsv")
                mutations_by_position_svg = mutation_paths.get("mutations_by_position_svg")
                mutations_by_sequence_tsv = mutation_paths.get("mutations_by_sequence_tsv")

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
                            chain_scores: dict[str, dict[str, float]] = {}
                            child_records: list[SequenceRecord] = []
                            child_to_parent: dict[str, tuple[str, str]] = {}

                            for s in samples:
                                chain_seqs = _split_multichain_sequence(s.sequence)
                                if len(chain_seqs) <= 1:
                                    cid = str(s.id)
                                    child_to_parent[cid] = (str(s.id), "")
                                    child_records.append(
                                        SequenceRecord(
                                            id=cid,
                                            header=s.header,
                                            sequence=_clean_protein_sequence(chain_seqs[0]),
                                            meta={},
                                        )
                                    )
                                    continue

                                for idx, chain_seq in enumerate(chain_seqs):
                                    label = (
                                        str(design_chains[idx]).strip()
                                        if (design_chains is not None and idx < len(design_chains))
                                        else f"chain_{idx+1}"
                                    )
                                    cid = f"{s.id}:{label}"
                                    child_to_parent[cid] = (str(s.id), label)
                                    child_records.append(
                                        SequenceRecord(
                                            id=cid,
                                            header=f"{s.header or s.id}|{label}",
                                            sequence=_clean_protein_sequence(chain_seq),
                                            meta={},
                                        )
                                    )

                            scores_by_child = self.soluprot.score(child_records)
                            for child_id, score in scores_by_child.items():
                                parent_id, label = child_to_parent.get(child_id, (str(child_id), ""))
                                chain_scores.setdefault(parent_id, {})[label or "chain_1"] = float(score)

                            scores: dict[str, float] = {}
                            for s in samples:
                                parent_id = str(s.id)
                                per_chain = chain_scores.get(parent_id) or {}
                                scores[parent_id] = min(per_chain.values()) if per_chain else 0.0

                            soluprot_scores = scores
                            passed = [
                                s for s in samples if float(scores.get(s.id, 0.0)) >= float(request.soluprot_cutoff)
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

                passed = _monomerize_records(passed, af2_model_preset)
                if samples:
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
                af2_candidates = passed
                if request.af2_sequence_ids:
                    wanted = [str(x).strip() for x in request.af2_sequence_ids if str(x).strip()]
                    if wanted:
                        wanted_set = set(wanted)
                        passed_id_set = {s.id for s in passed}
                        missing = [seq_id for seq_id in wanted if seq_id not in passed_id_set]
                        if missing:
                            raise ValueError(f"af2_sequence_ids not found in SoluProt-passed designs for tier={tier_str}: {missing}")
                        af2_candidates = [s for s in passed if s.id in wanted_set]
                if af2_candidates:
                    set_status(paths, stage=f"af2_{tier_str}", state="running")
                    af2_dir = _ensure_dir(tier_dir / "af2")
                    af2_scores_path = tier_dir / "af2_scores.json"
                    af2_selected_path = tier_dir / "af2_selected.fasta"

                    cached_scores: dict[str, float] = {}
                    cached_ok = False
                    if af2_scores_path.exists() and not request.force:
                        try:
                            cached = json.loads(af2_scores_path.read_text(encoding="utf-8"))
                        except Exception:
                            cached = None
                        cached_scores_raw = cached.get("scores") if isinstance(cached, dict) else None
                        cached_model_preset = cached.get("model_preset") if isinstance(cached, dict) else None
                        cached_db_preset = cached.get("db_preset") if isinstance(cached, dict) else None
                        cached_max_template_date = cached.get("max_template_date") if isinstance(cached, dict) else None
                        if (
                            isinstance(cached_scores_raw, dict)
                            and (cached_model_preset in {None, af2_model_preset})
                            and (cached_db_preset in {None, request.af2_db_preset})
                            and (cached_max_template_date in {None, request.af2_max_template_date})
                        ):
                            cached_scores = {
                                str(k): float(v) for k, v in cached_scores_raw.items() if isinstance(v, (int, float))
                            }
                            cached_ok = True

                    candidate_ids = [s.id for s in af2_candidates]
                    to_predict = (
                        list(af2_candidates)
                        if request.force or not cached_ok
                        else [s for s in af2_candidates if s.id not in cached_scores]
                    )

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
                            if self.af2 is None:
                                raise RuntimeError(
                                    "AlphaFold2 is required for this pipeline; set ALPHAFOLD2_ENDPOINT_ID (RunPod) or AF2_URL"
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

                            jobs_path = af2_dir / "runpod_jobs.json"
                            jobs: dict[str, str] = {} if request.force else _load_jobs_map(jobs_path)

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
                                    af2_inputs,
                                    model_preset=af2_model_preset,
                                    db_preset=request.af2_db_preset,
                                    max_template_date=request.af2_max_template_date,
                                    extra_flags=request.af2_extra_flags,
                                    on_job_id=_on_af2_job_id,
                                    resume_job_ids=jobs,
                                )
                            except TypeError:
                                try:
                                    af2_result = self.af2.predict(
                                        af2_inputs,
                                        model_preset=af2_model_preset,
                                        db_preset=request.af2_db_preset,
                                        max_template_date=request.af2_max_template_date,
                                        extra_flags=request.af2_extra_flags,
                                        on_job_id=_on_af2_job_id,
                                    )
                                except TypeError:
                                    af2_result = self.af2.predict(
                                        af2_inputs,
                                        model_preset=af2_model_preset,
                                        db_preset=request.af2_db_preset,
                                        max_template_date=request.af2_max_template_date,
                                        extra_flags=request.af2_extra_flags,
                                    )

                        for seq in to_predict:
                            rec = (af2_result or {}).get(seq.id, {}) if isinstance(af2_result, dict) else {}
                            if not isinstance(rec, dict):
                                continue
                            score = rec.get("best_plddt")
                            if isinstance(score, (int, float)):
                                cached_scores[seq.id] = float(score)

                            seq_dir = _ensure_dir(af2_dir / _safe_id(seq.id))
                            if isinstance(rec.get("ranking_debug"), dict):
                                write_json(seq_dir / "ranking_debug.json", rec["ranking_debug"])
                            ranked0 = rec.get("ranked_0_pdb")
                            if isinstance(ranked0, str) and ranked0.strip():
                                _write_text(seq_dir / "ranked_0.pdb", ranked0)
                            write_json(
                                seq_dir / "metrics.json",
                                {
                                    "best_plddt": cached_scores.get(seq.id),
                                    "best_model": rec.get("best_model"),
                                    "archive_name": rec.get("archive_name"),
                                },
                            )

                    candidate_scores = {seq_id: cached_scores[seq_id] for seq_id in candidate_ids if seq_id in cached_scores}
                    selected_pairs = [
                        (seq_id, score)
                        for seq_id, score in candidate_scores.items()
                        if score >= float(request.af2_plddt_cutoff)
                    ]
                    selected_pairs.sort(key=lambda t: t[1], reverse=True)
                    af2_selected_ids = [seq_id for seq_id, _ in selected_pairs[: int(request.af2_top_k)]]

                    selected_records = [s for s in af2_candidates if s.id in set(af2_selected_ids)]
                    _write_text(
                        af2_selected_path,
                        to_fasta([FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in selected_records]),
                    )
                    write_json(
                        af2_scores_path,
                        {
                            "scores": cached_scores,
                            "candidate_ids": candidate_ids,
                            "cutoff": request.af2_plddt_cutoff,
                            "top_k": request.af2_top_k,
                            "selected_ids": af2_selected_ids,
                            "model_preset": af2_model_preset,
                            "db_preset": request.af2_db_preset,
                            "max_template_date": request.af2_max_template_date,
                            "cached": (not to_predict and cached_ok and not request.force),
                        },
                    )
                    set_status(
                        paths,
                        stage=f"af2_{tier_str}",
                        state="completed",
                        detail="cached" if (not to_predict and cached_ok and not request.force) else None,
                    )

                if request.stop_after == "af2":
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
                        mutation_report_path=mutation_report_path,
                        mutations_by_position_tsv=mutations_by_position_tsv,
                        mutations_by_position_svg=mutations_by_position_svg,
                        mutations_by_sequence_tsv=mutations_by_sequence_tsv,
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
                msa_filtered_a3m_path=msa_filtered_a3m_path,
                msa_tsv_path=msa_tsv_path,
                conservation_path=conservation_path,
                ligand_mask_path=ligand_mask_path,
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
            set_status(paths, stage="done", state="completed")
            return result
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
                tiers=tier_results,
                errors=errors,
            )
            write_json(paths.summary_json, asdict(result))
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
        runpod_job_path = msa_dir / "runpod_job.json"

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

        if runpod_job_path.exists() and not request.force:
            try:
                meta = json.loads(runpod_job_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
            job_id = meta.get("job_id")
            if isinstance(job_id, str) and job_id.strip():
                same_request = True
                if isinstance(meta, dict):
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
                        raise RuntimeError("MMseqs search did not return A3M (a3m_gz_b64 is empty)")
                    a3m = decode_a3m_gz_b64(str(a3m_b64))
                    _write_text(tsv_path, tsv)
                    _write_text(a3m_path, a3m)
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
            if str(request.target_fasta or "").strip():
                query = parse_fasta(request.target_fasta)[0].sequence
            else:
                extracted = sequence_by_chain(pdb_text, chains=design_chains)
                if not extracted:
                    raise ValueError("Unable to derive dry_run query sequence from target_pdb ATOM records")
                chain_order = sorted(design_chains) if design_chains else sorted(extracted.keys())
                query = "".join(extracted.get(chain_id, "") for chain_id in chain_order)
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
