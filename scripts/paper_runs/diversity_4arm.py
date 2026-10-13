#!/usr/bin/env python3
"""4-arm structural-context DESIGN-POOL generation for the selected-Top-K
diversity study (extends the manuscript's pool-level diversity result to the
post-triage selected set).

For one (target, arm) it generates a ~10k design pool + SoluProt labels and
STOPS (stop_after=soluprot) -- NO AF2/ColabFold (so the ColabFold HTTP worker
is never touched; design runs on RunPod as configured, MSA/SoluProt on the
local HTTP GPU server). Surrogate selection is done OFFLINE afterwards with the
SoluProt objective (auto-CV), reusing soluprot_surrogate_offline.py.

Options mirror the proven pilot run; only the arm flags, per-arm num_seq (for
~10k pool parity), RFD3/BioEmu counts, and stop_after differ.

Usage: diversity_4arm.py <target> <arm>   arm in {single,rfd3,bioemu,rfd3_bioemu}
Target -> single-chain PDB + chain auto-resolved from the reference dir.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

PR = Path("/opt/protein_pipeline-work")
sys.path.insert(0, str(PR / "pipeline-mcp" / "src"))
from dotenv import load_dotenv
load_dotenv("/opt/protein_pipeline/pipeline-mcp/.env", override=True)
os.environ["PIPELINE_OUTPUT_ROOT"] = str(PR / "outputs")
# NOTE: do NOT override COLABFOLD routing -- no AF2 is run here.
from pipeline_mcp.app import build_runner
from pipeline_mcp.models import PipelineRequest

SC = Path("/opt/structural_context_18_targets/pdb_single_chain")
RFD3_N = 20            # safe: rfd3_bioemu-evaluable targets pass the 2.0A gate at this count
BIOEMU_RETURN = 20
BIOEMU_ATTEMPT = 32
# per-arm num_seq_per_tier chosen so each arm's pool is ~10k designs (3 tiers)
NUM_SEQ = {"single": 3333, "rfd3": 165, "bioemu": 165, "rfd3_bioemu": 83}
BACKBONES = {"single": 1, "rfd3": RFD3_N, "bioemu": BIOEMU_RETURN,
             "rfd3_bioemu": RFD3_N + BIOEMU_RETURN}


def resolve(target: str):
    hits = sorted(SC.glob(f"{target}_*.pdb"))
    if not hits:
        raise SystemExit(f"no single-chain PDB for {target} in {SC}")
    f = hits[0]
    chain = f.stem[len(target) + 1:]
    return f, chain


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: diversity_4arm.py <target> <arm>", file=sys.stderr); return 2
    target, arm = sys.argv[1], sys.argv[2]
    if arm not in NUM_SEQ:
        print(f"bad arm {arm}; choose {list(NUM_SEQ)}", file=sys.stderr); return 2
    pdb_path, chain = resolve(target)
    use_rfd3 = arm in ("rfd3", "rfd3_bioemu")
    use_bioemu = arm in ("bioemu", "rfd3_bioemu")
    run_id = f"div_{target}_{arm}"
    runner = build_runner()
    req = PipelineRequest(
        target_fasta="",
        target_pdb=pdb_path.read_text(),
        design_chains=[chain],
        conservation_tiers=[0.3, 0.5, 0.7],
        num_seq_per_tier=NUM_SEQ[arm],
        rfd3_use=use_rfd3,
        rfd3_use_ensemble=use_rfd3,
        rfd3_max_return_designs=RFD3_N if use_rfd3 else 0,
        rfd3_target_rmsd_cutoff=2.0,
        bioemu_use=use_bioemu,
        bioemu_num_samples=BIOEMU_ATTEMPT if use_bioemu else 0,
        bioemu_max_attempted_structures=BIOEMU_ATTEMPT if use_bioemu else 0,
        bioemu_max_return_structures=BIOEMU_RETURN if use_bioemu else 0,
        bioemu_target_rmsd_cutoff=2.0,
        surrogate_triage_enabled=False,   # selection is done offline with SoluProt objective
        soluprot_cutoff=0.5,
        relax_enabled=False,
        pdb_strip_nonpositive_resseq=True,
        pdb_renumber_resseq_from_1=True,
        wt_compare=False,                 # avoid the WT-baseline ColabFold call; WT not needed for diversity
        stop_after="soluprot",            # no AF2 / ColabFold
        force=True,
        auto_recover=True,
    )
    print(f"[run] {run_id} arm={arm} chain={chain} backbones~{BACKBONES[arm]} "
          f"num_seq/tier={NUM_SEQ[arm]} (stop_after=soluprot, no AF2)", flush=True)
    runner.run(req, run_id=run_id)  # raises on error -> runner halts (fail-fast)
    rd = PR / "outputs" / run_id
    n = 0
    for sp in (rd / "tiers").glob("*/soluprot.json"):
        try:
            n += len(json.load(open(sp)).get("scores") or {})
        except Exception:
            pass
    print(f"[done] {run_id}: {n} designs with SoluProt", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
