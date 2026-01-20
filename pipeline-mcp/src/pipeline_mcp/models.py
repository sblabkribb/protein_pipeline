from __future__ import annotations

from dataclasses import dataclass, field
import os


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class SequenceRecord:
    id: str
    sequence: str
    header: str | None = None
    meta: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineRequest:
    target_fasta: str
    target_pdb: str

    design_chains: list[str] | None = None

    conservation_tiers: list[float] = field(default_factory=lambda: [0.3, 0.5, 0.7])
    conservation_mode: str = "quantile"  # quantile | threshold
    conservation_weighting: str = "none"  # none | mmseqs_cluster
    conservation_cluster_method: str = "linclust"
    conservation_cluster_min_seq_id: float = 0.9
    conservation_cluster_coverage: float | None = None
    conservation_cluster_cov_mode: int | None = None
    conservation_cluster_kmer_per_seq: int | None = None

    ligand_mask_distance: float = 6.0
    ligand_resnames: list[str] | None = None
    ligand_atom_chains: list[str] | None = None

    pdb_strip_nonpositive_resseq: bool = False
    pdb_renumber_resseq_from_1: bool = False

    num_seq_per_tier: int = 16
    batch_size: int = 1
    sampling_temp: float = 0.1
    seed: int = 0

    soluprot_cutoff: float = 0.5

    af2_model_preset: str = "auto"  # auto | monomer | multimer (and variants)
    af2_db_preset: str = "full_dbs"
    af2_max_template_date: str = "2020-05-14"
    af2_extra_flags: str | None = None
    af2_plddt_cutoff: float = 85.0
    af2_top_k: int = 20
    af2_sequence_ids: list[str] | None = None

    mmseqs_target_db: str = "uniref90"
    mmseqs_max_seqs: int = 3000
    mmseqs_threads: int = 4
    mmseqs_use_gpu: bool = field(default_factory=lambda: _env_true("PIPELINE_MMSEQS_USE_GPU") or _env_true("MMSEQS_USE_GPU"))

    novelty_target_db: str = "uniref90"

    msa_min_coverage: float = 0.0
    msa_min_identity: float = 0.0

    query_pdb_min_identity: float = 0.9
    query_pdb_policy: str = "error"  # error | warn | ignore

    stop_after: str | None = None  # msa | design | soluprot | af2 | novelty
    force: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class TierResult:
    tier: float
    fixed_positions: dict[str, list[int]]
    proteinmpnn_native: SequenceRecord | None
    proteinmpnn_samples: list[SequenceRecord]
    soluprot_scores: dict[str, float] | None = None
    passed_ids: list[str] | None = None
    af2: dict[str, object] | None = None
    af2_selected_ids: list[str] | None = None
    novelty_tsv: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    output_dir: str
    msa_a3m_path: str | None
    msa_filtered_a3m_path: str | None
    msa_tsv_path: str | None
    conservation_path: str | None
    ligand_mask_path: str | None
    tiers: list[TierResult]
    errors: list[str] = field(default_factory=list)
