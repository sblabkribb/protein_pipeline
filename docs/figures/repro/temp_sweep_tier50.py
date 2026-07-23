#!/usr/bin/env python3
"""Temperature sweep at TIER-50 conservation mask, 5 enzyme targets, single backbone.
Consistent with S13/S14 (enzyme, tier-50). Computes diversity + native recovery vs T."""
import os, sys, json, time
os.chdir("/opt/protein_pipeline/pipeline-mcp")
for line in open(".env"):
    line=line.strip()
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0,"src")
from pipeline_mcp.clients.runpod import RunPodClient
from pipeline_mcp.clients.proteinmpnn import ProteinMPNNClient
cli=ProteinMPNNClient(runpod=RunPodClient(api_key=os.environ["RUNPOD_API_KEY"]),
                      endpoint_id=os.environ.get("PROTEINMPNN_ENDPOINT_ID","a763g45kfio4f9"))
OUT="/opt/protein_pipeline/outputs"
enz=["1ATJ","1CQW","1LVM","1TCA","5XJH"]; temps=[0.1,0.2,0.3,0.5,0.7]; NSEQ=48
log=open("/tmp/temp_sweep_tier50.log","w")
def L(m): print(m); log.write(m+"\n"); log.flush()
def meanpair(sl):
    n=len(sl)
    if n<2: return float("nan")
    tot=cnt=0
    for i in range(n):
        a=sl[i]
        for j in range(i+1,n):
            b=sl[j]; d=max(len(a),len(b),1); m=sum(1 for x,y in zip(a,b) if x==y); tot+=1-m/d; cnt+=1
    return tot/cnt
res={}
for t in enz:
    pdb=open(f"{OUT}/abl_be_{t}_single_s1/target.pdb").read()
    fp=json.load(open(f"{OUT}/abl_be_{t}_single_s1/tiers/50/fixed_positions.json"))
    res[t]={}
    for T in temps:
        t0=time.time()
        try:
            _,samples,_=cli.design(pdb_text=pdb, pdb_name=t, pdb_path_chains=["A"],
                                   fixed_positions=fp, use_soluble_model=True, model_name="v_48_020",
                                   num_seq_per_target=NSEQ, sampling_temp=T, seed=1)
            seqs=[getattr(s,"sequence","") or "" for s in samples if getattr(s,"sequence","")]
            recs=[float(s.meta["seq_recovery"]) for s in samples if s.meta.get("seq_recovery") is not None]
            div=meanpair(seqs); rec=sum(recs)/len(recs) if recs else None
            res[t][T]={"diversity":div,"recovery":rec,"n":len(seqs)}
            L(f"{t} T={T}: div={div:.4f} rec={rec:.4f} n={len(seqs)} ({time.time()-t0:.0f}s)")
        except Exception as e:
            res[t][T]={"error":str(e)}; L(f"{t} T={T}: ERROR {type(e).__name__}: {e}")
        json.dump(res, open("/tmp/temp_sweep_tier50_results.json","w"))
L("ALL DONE")
log.close()
