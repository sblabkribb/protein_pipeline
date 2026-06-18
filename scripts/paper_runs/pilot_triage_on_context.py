#!/usr/bin/env python3
"""PILOT: surrogate triage on a structural-context-expanded candidate pool.

Tests whether running the resource-aware surrogate triage on a pool generated
from RFD3 + BioEmu backbones (instead of the single original backbone) helps or
hurts Top-K selection at the SAME fixed AF2 budget. Control = the single-backbone
5-target triage benchmark.

Design: original + RFD3 (ensemble) + BioEmu backbones -> ProteinMPNN designs over
3 conservation tiers -> ~10k pool -> surrogate triage (K-means N=30 bootstrap,
Top-K=20) selects from the pooled set. Same 50-AF2-call budget as the control.
Chain is given explicitly from the corrected single-chain reference (no chain
auto-select). 1h6wA03 is BioEmu-non-evaluable -> RFD3-only.

Run ONE target at a time (arg) to validate the config before scaling to all 5.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

PR = Path("/opt/protein_pipeline-work")
sys.path.insert(0, str(PR / "pipeline-mcp" / "src"))
from dotenv import load_dotenv
load_dotenv("/opt/protein_pipeline/pipeline-mcp/.env", override=True)
os.environ["PIPELINE_OUTPUT_ROOT"] = str(PR / "outputs")
# The local ColabFold HTTP worker wedges under the 50-job triage burst (no --host-url
# -> public MSA server hangs; HTTP path has no clean cancel). Force AF2 onto the RunPod
# ColabFold endpoint (the proven 5/20 path) by clearing the HTTP URLs so _env_provider
# falls back to COLABFOLD_ENDPOINT_ID. Toggle with PILOT_AF2_RUNPOD=1 (default on).
if os.environ.get("PILOT_AF2_RUNPOD", "1") == "1":
    for _k in ("COLABFOLD_URL", "COLABFOLD_HTTP_URL", "COLABFOLD_GPU_URL"):
        os.environ.pop(_k, None)
    print("[af2] COLABFOLD_URL cleared -> AF2 routed to RunPod COLABFOLD_ENDPOINT_ID", flush=True)
from pipeline_mcp.app import build_runner
from pipeline_mcp.models import PipelineRequest

SC = Path("/opt/structural_context_18_targets/pdb_single_chain")
# target -> (single-chain pdb file, design chain, bioemu evaluable?)
TARGETS = {
    "1a8rG01": ("1a8rG01_G.pdb", "G", True),
    "1a6jA00": ("1a6jA00_A.pdb", "A", True),
    "1a19A00": ("1a19A00_A.pdb", "A", True),
    "1advA02": ("1advA02_A.pdb", "A", True),
    "1h6wA03": ("1h6wA03_A.pdb", "A", False),  # BioEmu non-evaluable -> RFD3 only
    # RFD3+BioEmu-evaluable scale-up roster (matches the 18-target ablation subset)
    "1agrE02": ("1agrE02_E.pdb", "E", True),
    "1b12B02": ("1b12B02_B.pdb", "B", True),
    "1bxmA00": ("1bxmA00_A.pdb", "A", True),
    "1eruA00": ("1eruA00_A.pdb", "A", True),
    "1jyoE00": ("1jyoE00_E.pdb", "E", True),
    "3is8V00": ("3is8V00_V.pdb", "V", True),
    "3it4B01": ("3it4B01_B.pdb", "B", True),
}
RFD3_BACKBONES = int(os.environ.get("PILOT_RFD3_BACKBONES", "30"))  # lower for targets whose RFD3 gate passes <30
BIOEMU_RETURN = int(os.environ.get("PILOT_BIOEMU_RETURN", "30"))  # gated BioEmu backbones to keep
BIOEMU_ATTEMPT = int(os.environ.get("PILOT_BIOEMU_ATTEMPT", "48"))  # sample more than needed so enough pass the 2.0A gate
NUM_SEQ_PER_TIER = 55   # ~60 backbones (RFD3 30 + BioEmu 30, no original) x 3 tiers x 55 ~ 10k
SINGLE = os.environ.get("PILOT_SINGLE", "0") == "1"   # single-backbone control arm (no RFD3/BioEmu)
NUM_SEQ_SINGLE = int(os.environ.get("PILOT_NUM_SEQ", "3333"))  # ~10k from the original backbone alone

def main() -> int:
    tid = sys.argv[1] if len(sys.argv) > 1 else "1a8rG01"
    if tid not in TARGETS:
        print(f"unknown target {tid}; choose from {list(TARGETS)}"); return 2
    fname, chain, bioemu_ok = TARGETS[tid]
    pdb_text = (SC / fname).read_text()
    runner = build_runner()
    req = PipelineRequest(
        target_fasta="",
        target_pdb=pdb_text,
        design_chains=[chain],
        conservation_tiers=[0.3, 0.5, 0.7],
        num_seq_per_tier=(NUM_SEQ_SINGLE if SINGLE else NUM_SEQ_PER_TIER),
        # structural-context expansion
        rfd3_use=(not SINGLE),
        rfd3_use_ensemble=True,
        rfd3_max_return_designs=RFD3_BACKBONES,
        rfd3_target_rmsd_cutoff=2.0,
        bioemu_use=(bool(bioemu_ok) and not SINGLE),
        bioemu_num_samples=BIOEMU_ATTEMPT if bioemu_ok else 0,
        bioemu_max_attempted_structures=BIOEMU_ATTEMPT if bioemu_ok else 0,
        bioemu_max_return_structures=BIOEMU_RETURN if bioemu_ok else 0,
        bioemu_target_rmsd_cutoff=2.0,
        # surrogate triage on the pooled set, same budget as the control
        surrogate_triage_enabled=True,
        surrogate_triage_scope="pooled_tiers",
        surrogate_triage_initial_samples=30,
        surrogate_triage_top_k=20,
        surrogate_triage_model="auto",
        surrogate_triage_comparator_models=["rf", "ridge", "lightgbm", "xgboost"],
        surrogate_triage_cv_folds=5,
        # AF2 via ColabFold full_dbs, triage owns the AF2 budget
        af2_provider="colabfold",
        af2_db_preset="full_dbs",
        af2_max_candidates_per_tier=0,
        af2_top_k=0,
        relax_enabled=False,
        pdb_strip_nonpositive_resseq=True,
        pdb_renumber_resseq_from_1=True,
        wt_compare=True,
        stop_after="af2",
        force=(os.environ.get("PILOT_FORCE", "1") == "1"),
        auto_recover=True,
    )
    run_id = (f"single_ctx_triage_{tid}" if SINGLE else f"pilot_ctx_triage_{tid}")
    print(f"[run] {run_id} (RFD3x{RFD3_BACKBONES} + BioEmu return<={BIOEMU_RETURN if bioemu_ok else 0} "
          f"(attempt {BIOEMU_ATTEMPT if bioemu_ok else 0}), num_seq_per_tier={NUM_SEQ_PER_TIER}, chain {chain})", flush=True)
    try:
        runner.run(req, run_id=run_id)
    except Exception as exc:
        print(f"[error] {run_id}: {exc}", file=sys.stderr, flush=True)
        return 1
    # report pool size + triage outcome
    rd = PR / "outputs" / run_id
    try:
        st = json.load((rd / "surrogate_triage" / "model_selection.json").open()) if (rd/"surrogate_triage"/"model_selection.json").exists() else {}
        print(f"[triage policy] {st.get('selected_model') or st}", flush=True)
    except Exception:
        pass
    # count designs that entered triage
    seqs = 0
    for tdir in (rd / "tiers").glob("*/designs_filtered.fasta") if (rd/"tiers").exists() else []:
        seqs += sum(1 for l in tdir.open() if l.startswith(">"))
    print(f"[pool] designs entering triage (approx): {seqs}", flush=True)
    print("DONE", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
