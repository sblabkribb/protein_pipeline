#!/usr/bin/env python3
"""Uniform 10 RFD3 + 10 BioEmu at PURE 2.0A gate, 3 targets (1CQW,1LVM,5XJH).
BioEmu sampled generously (45) so >=10 pass 2.0A even for flexible 1LVM.
stop_after=design; 10 seqs/structure. Enables non-truncated K=1..10 per method."""
from __future__ import annotations
import json, sys, time
from dataclasses import replace
from pathlib import Path
PR=Path("/opt/protein_pipeline")
sys.path.insert(0, str(PR/"pipeline-mcp"/"src")); sys.path.insert(0, str(PR/"scripts"/"benchmark"))
import backbone_ensemble_ablation as abl
abl.ARM_CONFIGS["u10_2p0"]={
    "label":"uniform10 @2.0A","rfd3_use":True,"rfd3_use_ensemble":True,"rfd3_max_return_designs":10,
    "bioemu_use":True,"bioemu_num_samples":45,"bioemu_max_return_structures":10,"num_seq_per_tier":10}
TARGETS=["1CQW","1LVM","5XJH"]
LOG=open("/tmp/run_uniform_2p0.log","w")
def L(m): print(m); LOG.write(m+"\n"); LOG.flush()
from dotenv import load_dotenv
from pipeline_mcp.app import build_runner
load_dotenv(str(PR/"pipeline-mcp"/".env"), override=True)
runner=build_runner(); L("runner built")
for t in TARGETS:
    pdb=json.load(open(PR/"outputs"/f"abl_be_{t}_rfd3_bioemu_s1"/"request.json"))["target_pdb"]
    run_id=f"abl_be_{t}_rfd3_bioemu_u10_2p0_s1"
    req=abl.build_request(pdb,"u10_2p0",seed=1)
    req=replace(req, stop_after="design", force=True,
                rfd3_target_rmsd_cutoff=2.0, bioemu_target_rmsd_cutoff=2.0)
    t0=time.time(); L(f"[run] {run_id} (gate=2.0A, bioemu 45 samples)")
    try:
        runner.run(req, run_id=run_id); L(f"[done] {run_id} ({time.time()-t0:.0f}s)")
    except Exception as e:
        L(f"[error] {run_id}: {type(e).__name__}: {e}")
L("ALL DONE"); LOG.close()
