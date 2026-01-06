from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

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

            set_status(paths, stage="mmseqs_msa", state="running")
            msa_tsv_text, a3m_text = self._get_msa(target_query_fasta, msa_dir, request)
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
            pdb_chains = list(residues_by_chain(request.target_pdb, only_atom_records=True).keys())
            design_chains = request.design_chains or pdb_chains or None
            ligand_mask = ligand_proximity_mask(
                request.target_pdb,
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
                    tier_str=tier_str,
                    design_chains=design_chains,
                    fixed_positions_by_chain=fixed_positions_by_chain,
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
                if samples:
                    if request.dry_run:
                        scores = {s.id: (0.6 if (i % 2 == 0) else 0.4) for i, s in enumerate(samples)}
                    else:
                        if self.soluprot is None:
                            raise RuntimeError("SoluProt is required for this pipeline; set SOLUPROT_URL")
                        scores = self.soluprot.score(samples)
                    soluprot_scores = scores
                    passed = [
                        s for s in samples if float(scores.get(s.id, 0.0)) >= float(request.soluprot_cutoff)
                    ]
                    passed_ids = [s.id for s in passed]
                    write_json(
                        tier_dir / "soluprot.json",
                        {"scores": scores, "cutoff": request.soluprot_cutoff},
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
                        tier_dir / "af2_selected.fasta",
                        to_fasta([FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in selected_records]),
                    )
                    write_json(
                        tier_dir / "af2_scores.json",
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
        tier_str: str,
        design_chains: list[str] | None,
        fixed_positions_by_chain: dict[str, list[int]],
    ) -> tuple[SequenceRecord | None, list[SequenceRecord]]:
        out_json = tier_dir / "proteinmpnn.json"
        out_fasta = tier_dir / "designs.fasta"

        if out_json.exists() and out_fasta.exists() and not request.force:
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            native = payload.get("native")
            samples = payload.get("samples")
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
            return native_rec, sample_recs

        if request.dry_run:
            query = parse_fasta(request.target_fasta)[0].sequence
            samples = [
                SequenceRecord(id=f"{tier_str}_s1", header=f"{tier_str},sample=1", sequence=query),
                SequenceRecord(id=f"{tier_str}_s2", header=f"{tier_str},sample=2", sequence=query[:-1] + "A"),
            ]
            native = SequenceRecord(id="native", header="native", sequence=query)
            _write_text(out_fasta, to_fasta([FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in [native, *samples]]))
            write_json(out_json, {"native": native.__dict__, "samples": [s.__dict__ for s in samples], "fixed_positions": fixed_positions_by_chain})
            return native, samples

        if self.proteinmpnn is None:
            raise RuntimeError("ProteinMPNN client is not configured")

        native, samples, raw = self.proteinmpnn.design(
            pdb_text=request.target_pdb,
            pdb_name="input",
            pdb_path_chains=design_chains or None,
            fixed_positions=fixed_positions_by_chain,
            use_soluble_model=True,
            model_name="v_48_020",
            num_seq_per_target=request.num_seq_per_tier,
            batch_size=request.batch_size,
            sampling_temp=request.sampling_temp,
            seed=request.seed,
        )
        _write_text(out_fasta, to_fasta([FastaRecord(header=native.header or native.id, sequence=native.sequence)] + [FastaRecord(header=s.header or s.id, sequence=s.sequence) for s in samples]))
        write_json(
            out_json,
            {
                "native": native.__dict__,
                "samples": [s.__dict__ for s in samples],
                "fixed_positions": fixed_positions_by_chain,
                "raw": _safe_json(raw),
            },
        )
        return native, samples
