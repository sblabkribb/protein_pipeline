#!/usr/bin/env python3
"""3-arm structural-context comparison on the 5 Solu_pipeline_benchmark MONOMER
enzymes, mirroring the manuscript's N=9 CATH structural-context result
(single+surrogate / RFD3+BioEmu pool / RFD3+BioEmu+surrogate).

Data is taken verbatim from the already-completed `abl_be_<PDB>_<arm>_s1` runs
(no new design / AF2). Each arm's surrogate-selected, AF2-folded set is the
`af2_scores.json` subset (af2 keys are a subset of soluprot keys); sequences come
from `designs.fasta`. The ensemble *pool* arm uses the full RFD3+BioEmu soluprot
pool (random/pool-representative reference).

Metrics per arm (aggregated over conservation tiers 30/50/70):
  - mean pairwise sequence diversity = 1 - mean pairwise identity
  - mean SoluProt
  - mean pLDDT  (only defined for the two AF2-folded *selected* arms; the
    pool/random arm is NOT fully folded, so its pLDDT is left blank -- same
    honest caveat as the N=9 result)

Outputs (new dedicated folder):
  public_data/benchmark/results/solu_monomer_threeway/monomer_threeway_per_target.csv
  public_data/benchmark/results/solu_monomer_threeway/monomer_threeway_means.csv
  figures/benchmark/fig_solu_monomer_threeway.{png,pdf}
"""
from __future__ import annotations
import csv, json, statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PR = Path("/opt/protein_pipeline-work")
OUTPUTS = Path("/opt/protein_pipeline/outputs")
TARGETS = ["1ATJ", "1CQW", "1LVM", "1TCA", "5XJH"]
ENZYME = {"1ATJ": "HRP-C", "1CQW": "DhaA", "1LVM": "TEV", "1TCA": "CALB", "5XJH": "IsPETase"}
TIERS = ["30", "50", "70"]
SINGLE_ARM = "single"
ENS_ARM = "rfd3_bioemu"

OUT_DIR = PR / "public_data" / "benchmark" / "results" / "solu_monomer_threeway"
FIG_DIR = PR / "figures" / "benchmark"


def _norm(k: str) -> str:
    """Normalize a score key to its design fasta header (strip a leading 'target:')."""
    return k[len("target:"):] if k.startswith("target:") else k


def _read_fasta(p: Path):
    out, sid = {}, None
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith(">"):
                sid = line[1:].split()[0]
                out[sid] = ""
            elif sid is not None:
                out[sid] += line.strip()
    return {k: v for k, v in out.items() if v and "input" not in k.lower()}


def _load_tier(run_dir: Path, tier: str):
    d = run_dir / "tiers" / tier
    sp = json.loads((d / "soluprot.json").read_text()).get("scores", {}) if (d / "soluprot.json").exists() else {}
    af = json.loads((d / "af2_scores.json").read_text()).get("scores", {}) if (d / "af2_scores.json").exists() else {}
    designs = _read_fasta(d / "designs.fasta")        # all pool designs: id -> seq
    sel = _read_fasta(d / "af2_selected.fasta")       # surrogate-selected Top-K: id -> seq
    return sp, af, designs, sel


def _mkey(cid: str, dct: dict):
    """Match a canonical id to a score dict that may key on 'target:<id>' or '<id>'."""
    if cid in dct:
        return cid
    if ("target:" + cid) in dct:
        return "target:" + cid
    return None


def _mean_pairwise_diversity(seqs):
    seqs = [s for s in seqs if s]
    if len(seqs) < 2:
        return float("nan")
    tot, n = 0.0, 0
    for i in range(len(seqs)):
        for j in range(i + 1, len(seqs)):
            a, b = seqs[i], seqs[j]
            L = min(len(a), len(b))
            if not L:
                continue
            same = sum(1 for k in range(L) if a[k] == b[k])
            tot += same / L
            n += 1
    return (1 - tot / n) if n else float("nan")


def _agg(run_dir: Path, which: str):
    """which='selected' -> surrogate-selected Top-K (af2_selected.fasta).
    which='pool' -> the structural-context pool WITHOUT surrogate selection:
      diversity and SoluProt are measured over the full candidate pool (every
      SoluProt-scored design, the cleanest "pool" estimate), while pLDDT is
      measured over the pool-representative K-means bootstrap -- the folded
      designs that are NOT in the Top-K -- since only that subset carries real
      AF2 labels. This gives the pool arm a genuine pLDDT distinct from the
      selected set, matching the N=9 CATH analysis.
    Returns dict(diversity, soluprot_mean, plddt_mean, n_seq, n_plddt)."""
    seqlist, sols, plddts = [], [], []
    for t in TIERS:
        sp, af, designs, sel = _load_tier(run_dir, t)
        sel_canon = {_norm(h) for h in sel}
        if which == "selected":
            for h, seq in sel.items():
                cid = _norm(h)
                if seq:
                    seqlist.append(seq)
                ks = _mkey(cid, sp)
                if ks:
                    sols.append(sp[ks])
                ka = _mkey(cid, af)
                if ka:
                    plddts.append(af[ka])
        else:  # pool: full pool for diversity/SoluProt, bootstrap (folded non-Top-K) for pLDDT
            for k in sp:
                cid = _norm(k)
                sols.append(sp[k])
                seq = designs.get(cid) or designs.get(k)
                if seq:
                    seqlist.append(seq)
            for k, pl in af.items():           # bootstrap = folded but not Top-K
                if _norm(k) not in sel_canon:
                    plddts.append(pl)
    return {
        "diversity": _mean_pairwise_diversity(seqlist),
        "soluprot_mean": statistics.mean(sols) if sols else float("nan"),
        "plddt_mean": statistics.mean(plddts) if plddts else float("nan"),
        "n_seq": len(seqlist),
        "n_plddt": len(plddts),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    ARMS = ["single_surr", "ens_pool", "ens_surr"]
    rows = {}  # target -> arm -> metrics
    for tgt in TARGETS:
        rows[tgt] = {
            "single_surr": _agg(OUTPUTS / f"abl_be_{tgt}_{SINGLE_ARM}_s1", "selected"),
            "ens_pool":    _agg(OUTPUTS / f"abl_be_{tgt}_{ENS_ARM}_s1", "pool"),
            "ens_surr":    _agg(OUTPUTS / f"abl_be_{tgt}_{ENS_ARM}_s1", "selected"),
        }

    # ---- per-target CSV ----
    p1 = OUT_DIR / "monomer_threeway_per_target.csv"
    with p1.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["target", "enzyme", "arm", "diversity", "soluprot_mean", "plddt_mean", "n_seq", "n_plddt"])
        for tgt in TARGETS:
            for arm in ARMS:
                m = rows[tgt][arm]
                w.writerow([tgt, ENZYME[tgt], arm,
                            f"{m['diversity']:.4f}", f"{m['soluprot_mean']:.4f}",
                            ("" if m["plddt_mean"] != m["plddt_mean"] else f"{m['plddt_mean']:.2f}"),
                            m["n_seq"], m["n_plddt"]])

    # ---- means CSV ----
    def _safemean(vals):
        vals = [v for v in vals if v == v]  # drop NaN
        return statistics.mean(vals) if vals else float("nan")
    means = {arm: {k: _safemean([rows[t][arm][k] for t in TARGETS])
                   for k in ("diversity", "soluprot_mean", "plddt_mean")}
             for arm in ARMS}
    p2 = OUT_DIR / "monomer_threeway_means.csv"
    with p2.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "diversity", "soluprot_mean", "plddt_mean"])
        for arm in ARMS:
            pl = means[arm]["plddt_mean"]
            w.writerow([arm, f"{means[arm]['diversity']:.4f}",
                        f"{means[arm]['soluprot_mean']:.4f}",
                        "" if pl != pl else f"{pl:.2f}"])  # blank for N/A pool pLDDT

    # ---- paired Wilcoxon (ens_surr vs single_surr), diversity ----
    def wilcoxon_exact(pairs):
        from itertools import product
        diffs = [b - a for a, b in pairs if (b - a) != 0]
        n = len(diffs)
        if not n:
            return 1.0, 0
        ad = sorted([(abs(d), 1 if d > 0 else -1) for d in diffs])
        wpos = sum(i + 1 for i, (_, s) in enumerate(ad) if s > 0)
        wneg = sum(i + 1 for i, (_, s) in enumerate(ad) if s < 0)
        wst = min(wpos, wneg)
        ext = sum(1 for sg in product([-1, 1], repeat=n)
                  if min(sum(i + 1 for i, s in enumerate(sg) if s > 0),
                         sum(i + 1 for i, s in enumerate(sg) if s < 0)) <= wst)
        return ext / 2 ** n, n
    dpairs = [(rows[t]["single_surr"]["diversity"], rows[t]["ens_surr"]["diversity"]) for t in TARGETS]
    pdiv, ndiv = wilcoxon_exact(dpairs)
    npos = sum(1 for a, b in dpairs if b > a)
    ratio = statistics.mean([b / a for a, b in dpairs if a > 0])

    print("=== 5-monomer 3-arm means ===")
    for arm in ARMS:
        pl = means[arm]["plddt_mean"]
        print(f"  {arm:11s}: div={means[arm]['diversity']:.3f}  SoluProt={means[arm]['soluprot_mean']:.3f}  "
              f"pLDDT={'n/a' if pl != pl else f'{pl:.1f}'}")
    print(f"  diversity ens_surr vs single_surr: {npos}/{len(TARGETS)} up, "
          f"mean {ratio:.2f}x, paired Wilcoxon p={pdiv:.4f}")
    print(f"  wrote {p1}\n  wrote {p2}")
    # The distribution figure (box-and-whisker) is generated separately by
    # scripts/paper_runs/make_threeway_distribution_figures.py from these CSVs.


if __name__ == "__main__":
    main()
