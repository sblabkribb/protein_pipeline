#!/usr/bin/env python3
"""게이트 1/2 의 상한을 값싼 특징으로 먼저 잰다.

희소 latent 든 dense 임베딩이든, 서열에서 예측 가능한 신호가 없으면 어떤 표현을
써도 게이트는 동작하지 않는다. 조성 기반 특징으로 LOTO 평가를 돌려 상한을 본다.

핵심은 **타겟 내부 순위**다. 타겟 간 분산이 전체의 79~86%라(설계 3.4) pooled 지표는
타겟 평균만 맞춰도 높게 나온다. 그래서 타겟 평균 베이스라인을 항상 병기한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.cath_source import load_cath_run  # noqa: E402
from rapid_sr.records import DesignRecord  # noqa: E402

AA = "ACDEFGHIKLMNPQRSTVWY"


def featurize(sequence: str):
    import numpy as np

    clean = "".join(ch for ch in sequence.upper() if ch.isalpha())
    length = max(1, len(clean))
    counts = [clean.count(aa) / length for aa in AA]
    charged = sum(clean.count(c) for c in "DEKRH") / length
    hydrophobic = sum(clean.count(c) for c in "AILMFWVY") / length
    polar = sum(clean.count(c) for c in "STNQCY") / length
    return np.asarray([float(length), charged, hydrophobic, polar, *counts])


def spearman(a, b) -> float | None:
    import numpy as np
    from scipy.stats import spearmanr

    if len(a) < 3:
        return None
    if len(set(map(float, a))) < 2 or len(set(map(float, b))) < 2:
        return None
    rho = spearmanr(np.asarray(a), np.asarray(b)).statistic
    return None if rho != rho else float(rho)


def top_k_regret(y_true, y_pred, k: int = 5) -> float | None:
    """예측 상위 k 의 최대 실제값이 전체 최대값에 얼마나 못 미치는가(0 이 최선)."""
    import numpy as np

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.size <= k:
        return None
    spread = float(y_true.max() - y_true.min())
    if spread == 0:
        return None
    picked = np.argsort(-y_pred)[:k]
    return float((y_true.max() - y_true[picked].max()) / spread)


def evaluate(records: list[DesignRecord], metric: str, *, seed: int = 0) -> dict:
    """leave-one-target-out. 타겟 내부 순위 지표만 본다."""
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor

    usable = [r for r in records if getattr(r, metric) is not None and r.sequence]
    targets = sorted({r.target_id for r in usable})
    x_all = np.vstack([featurize(r.sequence) for r in usable])
    y_all = np.asarray([float(getattr(r, metric)) for r in usable])
    t_all = np.asarray([r.target_id for r in usable])

    per_target = []
    for target in targets:
        test = t_all == target
        if test.sum() < 5 or (~test).sum() < 50:
            continue
        model = RandomForestRegressor(
            n_estimators=200, random_state=seed, n_jobs=-1, min_samples_leaf=2
        )
        model.fit(x_all[~test], y_all[~test])
        pred = model.predict(x_all[test])
        truth = y_all[test]
        # 타겟 평균만 아는 예측기: 타겟 안에서는 상수라 순위 정보가 0 이다.
        per_target.append({
            "target": target,
            "n": int(test.sum()),
            "spearman": spearman(truth, pred),
            "top5_regret": top_k_regret(truth, pred, k=5),
            "true_sd": float(np.std(truth)),
        })

    rhos = [p["spearman"] for p in per_target if p["spearman"] is not None]
    regrets = [p["top5_regret"] for p in per_target if p["top5_regret"] is not None]
    rng = np.random.default_rng(seed)
    boot = []
    if rhos:
        arr = np.asarray(rhos)
        for _ in range(2000):
            boot.append(float(np.mean(rng.choice(arr, size=arr.size, replace=True))))
    return {
        "metric": metric,
        "n_designs": int(len(usable)),
        "n_targets_evaluated": len(per_target),
        "mean_within_target_spearman": round(float(np.mean(rhos)), 4) if rhos else None,
        "spearman_ci95": (
            [round(float(np.percentile(boot, 2.5)), 4),
             round(float(np.percentile(boot, 97.5)), 4)] if boot else None
        ),
        "frac_targets_positive_rho": (
            round(sum(1 for r in rhos if r > 0) / len(rhos), 3) if rhos else None
        ),
        "mean_top5_regret": round(float(np.mean(regrets)), 4) if regrets else None,
        "median_within_target_sd": (
            round(float(np.median([p["true_sd"] for p in per_target])), 4)
            if per_target else None
        ),
        "per_target": per_target,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cath-dir", default=str(PROJECT_ROOT / "cath_outputs_s3"))
    parser.add_argument("--metrics", default="soluprot,plddt_af2")
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
                    / "gate_feasibility_baseline.json"),
    )
    args = parser.parse_args(argv)

    records: list[DesignRecord] = []
    for run in sorted(p for p in Path(args.cath_dir).iterdir() if p.is_dir()):
        records.extend(load_cath_run(run))

    report = {"n_records": len(records), "results": {}}
    for metric in [m.strip() for m in args.metrics.split(",") if m.strip()]:
        result = evaluate(records, metric)
        report["results"][metric] = result
        print(
            f"{metric:11s} n={result['n_designs']:5d} targets={result['n_targets_evaluated']:3d} "
            f"| within-target rho={result['mean_within_target_spearman']} "
            f"CI{result['spearman_ci95']} "
            f"| pos_frac={result['frac_targets_positive_rho']} "
            f"| top5_regret={result['mean_top5_regret']} "
            f"| median within-target sd={result['median_within_target_sd']}"
        )

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
