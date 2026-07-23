import os, sys, time, json, glob
import numpy as np
os.chdir("/opt/protein_pipeline/pipeline-mcp")
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, "src")
from pipeline_mcp.clients.runpod import RunPodClient
from pipeline_mcp.clients.proteinmpnn import ProteinMPNNClient

rp = RunPodClient(api_key=os.environ["RUNPOD_API_KEY"])
cli = ProteinMPNNClient(runpod=rp, endpoint_id=os.environ.get("PROTEINMPNN_ENDPOINT_ID", "a763g45kfio4f9"))
OUT = "/opt/protein_pipeline/outputs"
TARGETS = ["1ATJ", "1TCA", "1LVM"]
TOTAL = 5000
TEMP = 0.1
log = open("/tmp/big_sweep.log", "w")
def L(m): print(m); log.write(m + "\n"); log.flush()

def gen(pdb_path, n, name):
    pdb = open(pdb_path).read()
    _, samples, _ = cli.design(pdb_text=pdb, pdb_name=name, num_seq_per_target=n, sampling_temp=TEMP)
    return [getattr(s, "sequence", "") or "" for s in samples if getattr(s, "sequence", "")]

seqs = {}  # seqs[target][arm] = list
for tgt in TARGETS:
    seqs[tgt] = {}
    single_pdb = f"{OUT}/abl_be_{tgt}_single_s1/target.pdb"
    ens_pdbs = sorted(glob.glob(f"{OUT}/abl_be_{tgt}_rfd3_bioemu_s1/backbones/*/target.pdb"))
    if not os.path.exists(single_pdb) or not ens_pdbs:
        L(f"{tgt}: missing backbones (single={os.path.exists(single_pdb)}, ens={len(ens_pdbs)}) - skip"); continue
    t = time.time()
    seqs[tgt]["single"] = gen(single_pdb, TOTAL, f"{tgt}_single")
    L(f"{tgt} single: {len(seqs[tgt]['single'])} seqs ({time.time()-t:.0f}s)")
    per = max(1, TOTAL // len(ens_pdbs)); pool = []
    t = time.time()
    for bb in ens_pdbs:
        pool += gen(bb, per, f"{tgt}_ens")
    seqs[tgt]["ensemble"] = pool
    L(f"{tgt} ensemble({len(ens_pdbs)} bb): {len(pool)} seqs ({time.time()-t:.0f}s)")
    json.dump(seqs, open("/tmp/big_sweep_seqs.json", "w"))  # incremental save

# ---- cumulative distinct-cluster rarefaction (>=90% identity) ----
def arr_of(sl):
    Ln = max((len(s) for s in sl), default=0)
    sl = [s for s in sl if len(s) == Ln]
    if not sl: return None
    return np.frombuffer("".join(sl).encode("latin1"), np.uint8).reshape(len(sl), Ln)

def n_clusters(arr, thr=0.9):
    if arr is None or len(arr) == 0: return 0
    reps = arr[0:1]; count = 1
    for i in range(1, arr.shape[0]):
        row = arr[i]
        if (reps == row).mean(axis=1).max() < thr:
            reps = np.vstack([reps, row]); count += 1
    return count

rng = np.random.default_rng(0)
Ns = [10, 50, 500, 5000]
res = {arm: {N: [] for N in Ns} for arm in ("single", "ensemble")}
for tgt in TARGETS:
    if tgt not in seqs or "ensemble" not in seqs[tgt]: continue
    for arm in ("single", "ensemble"):
        pool = seqs[tgt][arm]
        for N in Ns:
            if len(pool) < N:
                continue
            draws = 6 if N <= 500 else 1
            vals = []
            for _ in range(draws):
                idx = rng.choice(len(pool), size=N, replace=False)
                vals.append(n_clusters(arr_of([pool[i] for i in idx])))
            res[arm][N].append(float(np.mean(vals)))
        L(f"{tgt} {arm} clusters: " + str({N: round(float(np.mean(res[arm][N])),1) if res[arm][N] else None for N in Ns}))

summary = {arm: {N: (float(np.mean(res[arm][N])) if res[arm][N] else None) for N in Ns} for arm in res}
json.dump(summary, open("/tmp/big_sweep_results.json", "w"))
L("SUMMARY " + json.dumps(summary))
L("DONE")
