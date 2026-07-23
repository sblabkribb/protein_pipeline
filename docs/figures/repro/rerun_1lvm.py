from __future__ import annotations
import json, sys, time
from dataclasses import replace
from pathlib import Path
PR=Path("/opt/protein_pipeline")
sys.path.insert(0,str(PR/"pipeline-mcp"/"src")); sys.path.insert(0,str(PR/"scripts"/"benchmark"))
import backbone_ensemble_ablation as abl
abl.ARM_CONFIGS["u8_2p0"]={"label":"u8@2.0","rfd3_use":True,"rfd3_use_ensemble":True,"rfd3_max_return_designs":10,
    "bioemu_use":True,"bioemu_num_samples":45,"bioemu_max_return_structures":8,"num_seq_per_tier":10}
LOG=open("/tmp/rerun_1lvm.log","w")
def L(m): print(m); LOG.write(m+"\n"); LOG.flush()
from dotenv import load_dotenv
from pipeline_mcp.app import build_runner
load_dotenv(str(PR/"pipeline-mcp"/".env"),override=True); runner=build_runner(); L("runner built")
pdb=json.load(open(PR/"outputs"/"abl_be_1LVM_rfd3_bioemu_s1"/"request.json"))["target_pdb"]
run_id="abl_be_1LVM_rfd3_bioemu_u10_2p0_s1"
req=abl.build_request(pdb,"u8_2p0",seed=1)
req=replace(req,stop_after="design",force=True,rfd3_target_rmsd_cutoff=2.0,bioemu_target_rmsd_cutoff=2.0)
t0=time.time(); L(f"[run] {run_id} (BioEmu max_return=8)")
try: runner.run(req,run_id=run_id); L(f"[done] ({time.time()-t0:.0f}s)")
except Exception as e: L(f"[error] {type(e).__name__}: {e}")
L("ALL DONE"); LOG.close()
