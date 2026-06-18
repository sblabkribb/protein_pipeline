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


def _load_tier(run_dir: Path, tier: str):
    d = run_dir / "tiers" / tier
    sp = json.loads((d / "soluprot.json").read_text()).get("scores", {}) if (d / "soluprot.json").exists() else {}
    af = json.loads((d / "af2_scores.json").read_text()).get("scores", {}) if (d / "af2_scores.json").exists() else {}
    seqs = {}
    fa = d / "designs.fasta"
    if fa.exists():
        sid = None
        for line in fa.read_text().splitlines():
            if line.startswith(">"):
                sid = line[1:].split()[0]
            elif sid is not None:
                seqs[sid] = seqs.get(sid, "") + line.strip()
    # drop the wildtype/input row if present
    seqs = {k: v for k, v in seqs.items() if v and "input" not in k.lower()}
    return sp, af, seqs


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
    """which='selected' -> AF2-folded surrogate set; 'pool' -> full soluprot pool.
    Returns dict(diversity, soluprot_mean, plddt_mean, n_seq, n_plddt)."""
    seqlist, sols, plddts = [], [], []
    for t in TIERS:
        sp, af, seqs = _load_tier(run_dir, t)
        ids = list(af.keys()) if which == "selected" else list(sp.keys())
        for k in ids:
            seq = seqs.get(_norm(k))
            if seq:
                seqlist.append(seq)
            if k in sp:
                sols.append(sp[k])
            # pLDDT only for the surrogate-selected (AF2-folded) arm. The ensemble
            # pool's only folded designs ARE the selected set, so a "pool pLDDT"
            # would merely duplicate ens_surr; report it as N/A instead.
            if which == "selected" and k in af:
                plddts.append(af[k])
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

    # ---- figure: 3 panels ----
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    C = {"single_surr": "#2D70B8", "ens_pool": "#9CB3C9", "ens_surr": "#2F8F5B"}
    LAB = {"single_surr": "Single + surrogate", "ens_pool": "RFD3+BioEmu pool (random)",
           "ens_surr": "RFD3+BioEmu + surrogate"}
    xlabels = [ENZYME[t] for t in TARGETS] + ["MEAN"]
    x = np.arange(len(xlabels))
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.0))

    def panel(ax, key, title, arms, ylabel):
        nb = len(arms)
        w = 0.8 / nb
        for bi, arm in enumerate(arms):
            vals = [rows[t][arm][key] for t in TARGETS]
            vals.append(statistics.mean([v for v in vals if v == v]))
            ax.bar(x + (bi - (nb - 1) / 2) * w, vals, w, color=C[arm], label=LAB[arm], edgecolor="white", linewidth=0.5)
        ax.set_xticks(x); ax.set_xticklabels(xlabels, rotation=30, ha="right", fontsize=8.5)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=9)
        ax.axvline(len(TARGETS) - 0.5, color="#cccccc", ls="--", lw=0.8)

    panel(axes[0], "diversity", "Top-K sequence diversity", ARMS, "mean pairwise diversity")
    panel(axes[1], "soluprot_mean", "SoluProt (selected mean)", ARMS, "mean SoluProt")
    panel(axes[2], "plddt_mean", "pLDDT (AF2-folded mean)", ["single_surr", "ens_surr"], "mean pLDDT")
    axes[0].legend(loc="upper left", fontsize=7.5, frameon=False)
    fig.suptitle("Structural-context 3-arm comparison — 5 Solu_pipeline_benchmark monomer enzymes "
                 f"(N=5; diversity {npos}/5 up, {ratio:.1f}×, p={pdiv:.3f})",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    for ext in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"fig_solu_monomer_threeway.{ext}", dpi=200, bbox_inches="tight")
    print(f"  wrote {FIG_DIR/'fig_solu_monomer_threeway.png'}")


if __name__ == "__main__":
    main()
