#!/usr/bin/env python3
"""Option A — extract tier 50 from legacy abl_be 5-enzyme runs and compare
Original (single arm) vs Ensemble (bioemu + rfd3_single + rfd3_bioemu combined).

Metrics per target per condition:
  - pLDDT range (max - min) from AF2 scores
  - SoluProt range (max - min) from soluprot.json
  - mean pairwise sequence diversity (1 - mean pairwise identity)

Paired Wilcoxon signed-rank across 5 targets.
"""
import json
import statistics
from pathlib import Path
from collections import defaultdict
import csv

TARGETS = ["1ATJ", "1CQW", "1LVM", "1TCA", "5XJH"]
OUTPUTS = Path("/opt/protein_pipeline/outputs")
ORIGINAL_ARMS = ["single"]
ENSEMBLE_ARMS = ["bioemu", "rfd3_single", "rfd3_bioemu"]
TIER = "50"
OUT_CSV = Path("/opt/protein_pipeline-work/data/benchmark/results/solu_monomer_optA_summary.csv")
OUT_DETAIL = Path("/opt/protein_pipeline-work/data/benchmark/results/solu_monomer_optA_per_target.csv")
OUT_DIVERSITY = Path("/opt/protein_pipeline-work/data/benchmark/results/solu_monomer_optA_diversity_pairs.csv")


def load_scores(run_dir: Path, tier: str):
    """Return dict of plddt/soluprot/sequences keyed by sample_id."""
    tier_dir = run_dir / "tiers" / tier
    out = {"plddt": {}, "soluprot": {}, "seqs": {}}
    # SoluProt
    sp = tier_dir / "soluprot.json"
    if sp.exists():
        out["soluprot"] = json.loads(sp.read_text()).get("scores", {})
    # AF2 pLDDT
    af2 = tier_dir / "af2_scores.json"
    if af2.exists():
        out["plddt"] = json.loads(af2.read_text()).get("scores", {})
    # Sequences
    fa = tier_dir / "designs.fasta"
    if fa.exists():
        sid = None
        for line in fa.read_text().splitlines():
            if line.startswith(">"):
                # header like ">sample_1 T=0.1, sample=1, score=..., seq_recovery=..."
                header = line[1:].split()[0]
                # legacy id matches scores: "target:sample_N" or just "sample_N"
                sid = "target:" + header if not header.startswith("target:") else header
            elif sid:
                out["seqs"][sid] = out["seqs"].get(sid, "") + line.strip()
    return out


def mean_pairwise_identity(seqs: list[str]) -> float:
    """Compute mean pairwise identity (fraction of matching residues)."""
    if len(seqs) < 2:
        return float("nan")
    n_pairs = 0
    total = 0.0
    for i in range(len(seqs)):
        for j in range(i + 1, len(seqs)):
            a, b = seqs[i], seqs[j]
            L = min(len(a), len(b))
            if L == 0:
                continue
            same = sum(1 for k in range(L) if a[k] == b[k])
            total += same / L
            n_pairs += 1
    return total / n_pairs if n_pairs else float("nan")


def compute_metrics(loaded: dict):
    """Given combined-arm dict {plddt, soluprot, seqs}, compute metrics."""
    plddt_vals = list(loaded["plddt"].values())
    sp_vals = list(loaded["soluprot"].values())
    seqs = list(loaded["seqs"].values())
    # Drop the "input" wildtype header if present
    seqs = [s for s in seqs if s]
    m = {}
    if plddt_vals:
        m["n_plddt"] = len(plddt_vals)
        m["plddt_max"] = max(plddt_vals)
        m["plddt_min"] = min(plddt_vals)
        m["plddt_range"] = m["plddt_max"] - m["plddt_min"]
        m["plddt_mean"] = statistics.mean(plddt_vals)
    if sp_vals:
        m["n_soluprot"] = len(sp_vals)
        m["soluprot_max"] = max(sp_vals)
        m["soluprot_min"] = min(sp_vals)
        m["soluprot_range"] = m["soluprot_max"] - m["soluprot_min"]
        m["soluprot_mean"] = statistics.mean(sp_vals)
    if seqs:
        m["n_seqs"] = len(seqs)
        mpi = mean_pairwise_identity(seqs)
        m["mean_pairwise_identity"] = mpi
        m["mean_pairwise_diversity"] = 1 - mpi if mpi == mpi else float("nan")
    return m


def merge_arms(target: str, arms: list[str]) -> dict:
    merged = {"plddt": {}, "soluprot": {}, "seqs": {}}
    for arm in arms:
        run = OUTPUTS / f"abl_be_{target}_{arm}_s1"
        if not run.exists():
            continue
        loaded = load_scores(run, TIER)
        # Namespace IDs by arm so combining arms doesn't collide
        for k, v in loaded["plddt"].items():
            merged["plddt"][f"{arm}|{k}"] = v
        for k, v in loaded["soluprot"].items():
            merged["soluprot"][f"{arm}|{k}"] = v
        for k, v in loaded["seqs"].items():
            merged["seqs"][f"{arm}|{k}"] = v
    return merged


def wilcoxon_signed_rank(pairs):
    """Simple Wilcoxon paired test on diffs. Returns (W+, n_eff, p_two_sided_exact)."""
    diffs = [b - a for a, b in pairs if (b - a) != 0]
    n = len(diffs)
    if n == 0:
        return (0.0, 0, 1.0)
    abs_diffs = sorted([(abs(d), 1 if d > 0 else -1) for d in diffs], key=lambda x: x[0])
    # Assign ranks (no tie correction since n=5)
    ranks = {}
    for i, (mag, sgn) in enumerate(abs_diffs, 1):
        ranks[i] = (mag, sgn, i)
    w_plus = sum(r[2] for r in ranks.values() if r[1] > 0)
    w_minus = sum(r[2] for r in ranks.values() if r[1] < 0)
    w_stat = min(w_plus, w_minus)
    # Exact two-sided p-value for small n via enumeration
    from itertools import product
    total = 2 ** n
    extreme = 0
    for signs in product([-1, 1], repeat=n):
        sim_wplus = sum(i + 1 for i, s in enumerate(signs) if s > 0)
        sim_wminus = sum(i + 1 for i, s in enumerate(signs) if s < 0)
        if min(sim_wplus, sim_wminus) <= w_stat:
            extreme += 1
    p = extreme / total
    return (w_plus, n, p)


def main():
    rows = []
    per_target = {}
    seqs_for_pairs = {}
    for t in TARGETS:
        orig = compute_metrics(merge_arms(t, ORIGINAL_ARMS))
        ens = compute_metrics(merge_arms(t, ENSEMBLE_ARMS))
        per_target[t] = {"original": orig, "ensemble": ens}
        print(f"\n--- {t} ---")
        print(f"  Original (single)        — designs:{orig.get('n_seqs','-')} AF2:{orig.get('n_plddt','-')}")
        print(f"    pLDDT range={orig.get('plddt_range',float('nan')):.3f} mean={orig.get('plddt_mean',float('nan')):.2f}")
        print(f"    SoluProt range={orig.get('soluprot_range',float('nan')):.3f} mean={orig.get('soluprot_mean',float('nan')):.3f}")
        print(f"    mean_pairwise_diversity={orig.get('mean_pairwise_diversity',float('nan')):.3f}")
        print(f"  Ensemble (bioemu+rfd3+combo) — designs:{ens.get('n_seqs','-')} AF2:{ens.get('n_plddt','-')}")
        print(f"    pLDDT range={ens.get('plddt_range',float('nan')):.3f} mean={ens.get('plddt_mean',float('nan')):.2f}")
        print(f"    SoluProt range={ens.get('soluprot_range',float('nan')):.3f} mean={ens.get('soluprot_mean',float('nan')):.3f}")
        print(f"    mean_pairwise_diversity={ens.get('mean_pairwise_diversity',float('nan')):.3f}")

    # Paired stats
    print("\n=== Paired Wilcoxon signed-rank (Ensemble - Original) across 5 targets ===")
    metrics_to_test = ["plddt_range", "soluprot_range", "mean_pairwise_diversity"]
    paired_results = {}
    for m in metrics_to_test:
        pairs = []
        for t in TARGETS:
            a = per_target[t]["original"].get(m, float("nan"))
            b = per_target[t]["ensemble"].get(m, float("nan"))
            if a == a and b == b:
                pairs.append((a, b))
        if len(pairs) < 3:
            print(f"  {m}: insufficient pairs ({len(pairs)})")
            continue
        diffs = [b - a for a, b in pairs]
        n_pos = sum(1 for d in diffs if d > 0)
        w_plus, n_eff, p = wilcoxon_signed_rank(pairs)
        mean_diff = statistics.mean(diffs)
        median_diff = statistics.median(diffs)
        paired_results[m] = {
            "n_pairs": len(pairs),
            "n_positive": n_pos,
            "median_diff": median_diff,
            "mean_diff": mean_diff,
            "W_plus": w_plus,
            "p_value_exact_two_sided": p,
        }
        print(f"  {m}: n={len(pairs)}, positive_pairs={n_pos}/{len(pairs)}, "
              f"median_diff={median_diff:+.4f}, mean_diff={mean_diff:+.4f}, "
              f"W+={w_plus:.0f}, p={p:.4f}")

    # Write summary CSV
    OUT_DETAIL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_DETAIL.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["target", "condition", "n_designs", "n_af2",
                    "plddt_range", "plddt_mean", "plddt_max",
                    "soluprot_range", "soluprot_mean", "soluprot_max",
                    "mean_pairwise_diversity"])
        for t in TARGETS:
            for cond in ["original", "ensemble"]:
                m = per_target[t][cond]
                w.writerow([t, cond,
                            m.get("n_seqs",""),
                            m.get("n_plddt",""),
                            m.get("plddt_range",""), m.get("plddt_mean",""), m.get("plddt_max",""),
                            m.get("soluprot_range",""), m.get("soluprot_mean",""), m.get("soluprot_max",""),
                            m.get("mean_pairwise_diversity","")])

    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "n_pairs", "n_positive", "median_diff", "mean_diff", "W_plus", "p_value_exact_two_sided"])
        for m, res in paired_results.items():
            w.writerow([m, res["n_pairs"], res["n_positive"],
                        f"{res['median_diff']:.4f}", f"{res['mean_diff']:.4f}",
                        f"{res['W_plus']:.1f}", f"{res['p_value_exact_two_sided']:.4f}"])

    print(f"\nWrote: {OUT_DETAIL}")
    print(f"Wrote: {OUT_CSV}")


if __name__ == "__main__":
    main()
