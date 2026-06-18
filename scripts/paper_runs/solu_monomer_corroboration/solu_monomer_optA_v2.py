#!/usr/bin/env python3
"""Solu_monomer corroboration v2 — Original now 20 designs (legacy single +
Option B single s2) vs Ensemble (bioemu + rfd3_single + rfd3_bioemu).

Compares candidate-pool spread + sequence diversity, paired Wilcoxon across
5 enzyme targets. Reads af2_scores.json (pLDDT), soluprot.json, designs.fasta.
"""
import json, os, statistics, csv
from itertools import product

TARGETS = ["1ATJ", "1CQW", "1LVM", "1TCA", "5XJH"]
OUT = "/opt/protein_pipeline-work/data/benchmark/results"

# (run_dir, tier) sources per condition
def original_sources(t):
    return [
        (f"/opt/protein_pipeline/outputs/abl_be_{t}_single_s1", "50"),
        (f"/opt/protein_pipeline/outputs/solu_monomer_optB_{t}_single_s2", "50"),
    ]

def ensemble_sources(t):
    return [
        (f"/opt/protein_pipeline/outputs/abl_be_{t}_bioemu_s1", "50"),
        (f"/opt/protein_pipeline/outputs/abl_be_{t}_rfd3_single_s1", "50"),
        (f"/opt/protein_pipeline/outputs/abl_be_{t}_rfd3_bioemu_s1", "50"),
    ]

def load_run(run, tier):
    base = f"{run}/tiers/{tier}"
    plddt, solu, seqs = {}, {}, {}
    p = f"{base}/af2_scores.json"
    if os.path.exists(p):
        plddt = json.load(open(p)).get("scores", {})
    p = f"{base}/soluprot.json"
    if os.path.exists(p):
        solu = json.load(open(p)).get("scores", {})
    p = f"{base}/designs.fasta"
    if os.path.exists(p):
        sid = None
        for line in open(p):
            if line.startswith(">"):
                sid = line[1:].split()[0]
            elif sid:
                seqs[sid] = seqs.get(sid, "") + line.strip()
    return plddt, solu, seqs

def merge(sources):
    P, S, Q = {}, {}, {}
    for run, tier in sources:
        plddt, solu, seqs = load_run(run, tier)
        tag = os.path.basename(run)
        for k, v in plddt.items(): P[f"{tag}|{k}"] = v
        for k, v in solu.items():  S[f"{tag}|{k}"] = v
        for k, v in seqs.items():  Q[f"{tag}|{k}"] = v
    return P, S, Q

def mean_pairwise_diversity(seqs):
    seqs = [s for s in seqs if s]
    if len(seqs) < 2: return float("nan")
    tot, n = 0.0, 0
    for i in range(len(seqs)):
        for j in range(i+1, len(seqs)):
            a, b = seqs[i], seqs[j]
            L = min(len(a), len(b))
            if not L: continue
            tot += sum(1 for k in range(L) if a[k]==b[k]) / L
            n += 1
    return 1 - tot/n if n else float("nan")

def metrics(P, S, Q):
    pv, sv = list(P.values()), list(S.values())
    seqs = list(Q.values())
    m = {}
    if pv:
        m["n_plddt"] = len(pv); m["plddt_range"] = max(pv)-min(pv); m["plddt_mean"] = statistics.mean(pv)
    if sv:
        m["n_solu"] = len(sv); m["soluprot_range"] = max(sv)-min(sv); m["soluprot_mean"] = statistics.mean(sv)
    if seqs:
        m["n_seq"] = len([s for s in seqs if s]); m["diversity"] = mean_pairwise_diversity(seqs)
    return m

def wilcoxon(pairs):
    diffs = [b-a for a,b in pairs if b-a != 0]
    n = len(diffs)
    if n == 0: return (0,0,1.0)
    order = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = {idx: r+1 for r, idx in enumerate(order)}
    wpos = sum(ranks[i] for i in range(n) if diffs[i]>0)
    wstat = min(wpos, sum(ranks.values())-wpos)
    extreme = sum(1 for s in product([-1,1], repeat=n)
                  if min(sum(i+1 for i,x in enumerate(s) if x>0),
                         sum(i+1 for i,x in enumerate(s) if x<0)) <= wstat)
    return (wpos, n, extreme/2**n)

per = {}
for t in TARGETS:
    o = metrics(*merge(original_sources(t)))
    e = metrics(*merge(ensemble_sources(t)))
    per[t] = {"original": o, "ensemble": e}
    print(f"\n--- {t} ---")
    print(f"  Original (n_seq={o.get('n_seq','-')}, af2={o.get('n_plddt','-')}): "
          f"pLDDT_range={o.get('plddt_range',float('nan')):.3f} "
          f"SoluProt_range={o.get('soluprot_range',float('nan')):.3f} "
          f"diversity={o.get('diversity',float('nan')):.3f}")
    print(f"  Ensemble (n_seq={e.get('n_seq','-')}, af2={e.get('n_plddt','-')}): "
          f"pLDDT_range={e.get('plddt_range',float('nan')):.3f} "
          f"SoluProt_range={e.get('soluprot_range',float('nan')):.3f} "
          f"diversity={e.get('diversity',float('nan')):.3f}")

print("\n=== Paired Wilcoxon (Ensemble - Original), 5 targets ===")
summary = {}
for m in ["plddt_range", "soluprot_range", "diversity"]:
    pairs = [(per[t]["original"][m], per[t]["ensemble"][m]) for t in TARGETS
             if per[t]["original"].get(m)==per[t]["original"].get(m) and per[t]["ensemble"].get(m)==per[t]["ensemble"].get(m)]
    diffs = [b-a for a,b in pairs]
    npos = sum(1 for d in diffs if d>0)
    wpos, n, p = wilcoxon(pairs)
    summary[m] = (len(pairs), npos, statistics.median(diffs), p)
    print(f"  {m}: n={len(pairs)} positive={npos}/{len(pairs)} median_diff={statistics.median(diffs):+.4f} p={p:.4f}")

os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/solu_monomer_optA_v2_per_target.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["target","condition","n_seq","n_af2","plddt_range","plddt_mean","soluprot_range","soluprot_mean","diversity"])
    for t in TARGETS:
        for c in ["original","ensemble"]:
            m=per[t][c]; w.writerow([t,c,m.get("n_seq",""),m.get("n_plddt",""),
                m.get("plddt_range",""),m.get("plddt_mean",""),m.get("soluprot_range",""),m.get("soluprot_mean",""),m.get("diversity","")])
with open(f"{OUT}/solu_monomer_optA_v2_summary.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["metric","n_pairs","n_positive","median_diff","p_value"])
    for m,(n,npos,md,p) in summary.items(): w.writerow([m,n,npos,f"{md:.4f}",f"{p:.4f}"])
print(f"\nWrote: {OUT}/solu_monomer_optA_v2_per_target.csv")
print(f"Wrote: {OUT}/solu_monomer_optA_v2_summary.csv")
