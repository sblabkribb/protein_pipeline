#!/usr/bin/env python3
"""M2 — coverage endpoint 의 동적 범위. 정책 비교가 아니다.

왜 필요한가
-----------
`coverage_unit = backbone_id` 로 동결하면서 위험이 하나 생겼다. 타겟당 backbone
5 개에 각 4 회 의무 probe 면, binary feasible-backbone coverage 가 probe 만으로
5/5 에 도달할 수 있다. 그러면 static 도 5/5, yield mode 도 5/5, coverage mode 도
5/5 라 지표가 정책을 구별하지 못한다. **포화한 지표로 사전등록하면 실험이 답을
낼 수 없다.**

그래서 정책을 돌리기 전에 자를 먼저 잰다.

무엇을 하지 않는가
------------------
adaptive vs static 비교를 하지 않는다. 어느 정책이 나은지 어떤 진술도 하지
않는다. 서열은 무작위로 뽑는다 - 어떤 배분 규칙도 쓰지 않는다.

무엇을 읽는가
-------------
라벨(joint-pass)을 읽는다. endpoint 의 범위를 재려면 필요하다. M1 과 다른
점이고, 그래서 별도 스크립트다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import random
import statistics
import subprocess
import time
import zlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID_CSV = BASE / "holdout_grid" / "af2_order_metric.csv"
OUT_JSON = BASE / "m2_endpoint_dynamic_range.json"

PLDDT_MIN, RMSD_MAX, SOLUPROT_MIN = 85.0, 2.0, 0.5
MIN_PROBE = 4          # v1 의 arm 별 최소 probe
SEED = 20260909


def load() -> dict[str, dict[str, list[bool]]]:
    """타겟 -> backbone -> joint-pass 목록 (RFD3 전용)."""
    out: dict[str, dict[str, list[bool]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for r in csv.DictReader(GRID_CSV.open(encoding="utf-8")):
        if r["status"] != "ok" or r["backbone_source"] != "rfd3":
            continue
        plddt, rmsd, solu = r["plddt"].strip(), r["rmsd_nonloop_order"].strip(), r["soluprot"].strip()
        if not (plddt and rmsd and solu):
            continue
        ok = (float(plddt) >= PLDDT_MIN and float(rmsd) <= RMSD_MAX
              and float(solu) >= SOLUPROT_MIN)
        out[r["target_id"]][r["backbone_key"]].append(ok)
    return {t: dict(v) for t, v in out.items()}


def effective_number(counts: list[int]) -> float:
    """exp(Shannon entropy). 균등하면 항목 수, 하나에 몰리면 1 에 가깝다."""
    total = sum(counts)
    if total <= 0:
        return 0.0
    ps = [c / total for c in counts if c > 0]
    h = -sum(p * math.log(p) for p in ps)
    return math.exp(h)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=2000)
    ap.add_argument("--out", default=str(OUT_JSON))
    args = ap.parse_args()

    cohort = load()
    print(f"타겟 {len(cohort)} · backbone {sum(len(v) for v in cohort.values())}")

    # ---- 1. 의무 probe 직후 binary coverage --------------------------------
    probe_cov, probe_eff = collections.defaultdict(list), collections.defaultdict(list)
    for target, bbs in sorted(cohort.items()):
        keys = sorted(bbs)
        for rep in range(args.replicates):
            rng = random.Random(zlib.crc32(f"{SEED}|{target}|{rep}".encode()))
            per_bb = []
            for k in keys:
                draw = rng.sample(bbs[k], min(MIN_PROBE, len(bbs[k])))
                per_bb.append(sum(draw))
            probe_cov[target].append(sum(1 for c in per_bb if c > 0))
            probe_eff[target].append(effective_number(per_bb))

    n_units = {t: len(v) for t, v in cohort.items()}
    saturated_targets = []
    print(f"\n=== 1. 의무 probe ({MIN_PROBE}/backbone) 직후 binary coverage ===")
    print(f"{'타겟':11s} {'unit':>4} {'중앙값':>7} {'최빈':>5} {'5/5 비율':>9} {'effective 중앙값':>16}")
    for t in sorted(cohort):
        vals = probe_cov[t]
        full = sum(1 for v in vals if v == n_units[t]) / len(vals)
        if full >= 0.90:
            saturated_targets.append(t)
        print(f"  {t:10s} {n_units[t]:>4} {statistics.median(vals):>7.1f} "
              f"{collections.Counter(vals).most_common(1)[0][0]:>5} {full:>8.0%} "
              f"{statistics.median(probe_eff[t]):>16.2f}")
    all_vals = [v for t in probe_cov for v in probe_cov[t]]
    frac_full = sum(1 for t in probe_cov for v in probe_cov[t]
                    if v == n_units[t]) / len(all_vals)
    print(f"\n  전체: 모든 unit 이 feasible 인 비율 {frac_full:.1%} · "
          f"포화 타겟(≥90%) {len(saturated_targets)}/{len(cohort)}")

    # ---- 2. 전체 관측에서의 집중도 -----------------------------------------
    print(f"\n=== 2. 전체 격자(24/backbone)에서 통과 후보의 backbone 별 집중도 ===")
    conc = {}
    for t in sorted(cohort):
        counts = [sum(v) for v in cohort[t].values()]
        eff = effective_number(counts)
        conc[t] = {"counts": sorted(counts, reverse=True), "n_units": n_units[t],
                   "n_feasible_units": sum(1 for c in counts if c > 0),
                   "effective": round(eff, 3),
                   "effective_ratio": round(eff / n_units[t], 3)}
        print(f"  {t:10s} 통과 {sorted(counts, reverse=True)} · "
              f"binary {conc[t]['n_feasible_units']}/{n_units[t]} · "
              f"effective {eff:.2f} ({eff / n_units[t]:.0%})")

    # ---- 3. 고정 크기 portfolio 에 대표되는 backbone 수 ---------------------
    print(f"\n=== 3. 통과 후보에서 무작위로 고른 고정 크기 portfolio ===")
    portfolio = {}
    for size in (5, 10, 20):
        reps = []
        for t in sorted(cohort):
            pool = [(k, i) for k, v in cohort[t].items() for i, ok in enumerate(v) if ok]
            if len(pool) < size:
                continue
            for rep in range(args.replicates // 4):
                rng = random.Random(zlib.crc32(f"{SEED}|{t}|{size}|{rep}".encode()))
                pick = rng.sample(pool, size)
                reps.append(len({k for k, _ in pick}))
        if reps:
            portfolio[str(size)] = {"mean_backbones": round(statistics.mean(reps), 2),
                                    "median": statistics.median(reps),
                                    "max_possible": 5}
            print(f"  크기 {size:>2}: 대표 backbone 평균 {statistics.mean(reps):.2f} / 5")

    verdict = {
        "binary_saturates": frac_full >= 0.5 or len(saturated_targets) >= len(cohort) / 2,
        "fraction_all_units_feasible_after_probe": round(frac_full, 4),
        "saturated_targets": saturated_targets,
        "criterion": "의무 probe 직후 모든 unit 이 feasible 인 재생의 비율이 50% 이상, "
                     "또는 타겟의 절반 이상이 90% 이상 5/5 이면 포화로 본다",
    }
    print(f"\n=== 판정 ===")
    print(f"  binary 포화: {verdict['binary_saturates']} "
          f"(probe 직후 전부 feasible 인 비율 {frac_full:.1%})")
    print(f"  → 권고 endpoint: "
          f"{'Effective Feasible Backbone Coverage = exp(H)' if verdict['binary_saturates'] else 'Feasible Backbone Coverage (단순 count)'}")

    out = {
        "purpose": "M2 - coverage endpoint 의 동적 범위. 정책 비교가 아니다.",
        "does_not_do": ["adaptive vs static 비교", "정책 성능에 대한 진술",
                        "배분 규칙 사용 (서열은 무작위 추출)"],
        "reads_labels": True,
        "coverage_unit": "backbone_id",
        "feasibility": f"pLDDT >= {PLDDT_MIN} and rmsd <= {RMSD_MAX} and soluprot >= {SOLUPROT_MIN}",
        "min_probe_per_unit": MIN_PROBE,
        "replicates": args.replicates,
        "seed": SEED,
        "post_probe_binary_coverage": {
            t: {"n_units": n_units[t], "median": statistics.median(probe_cov[t]),
                "fraction_all_feasible": round(
                    sum(1 for v in probe_cov[t] if v == n_units[t]) / len(probe_cov[t]), 4),
                "effective_median": round(statistics.median(probe_eff[t]), 3)}
            for t in sorted(cohort)},
        "full_grid_concentration": conc,
        "random_portfolio_representation": portfolio,
        "verdict": verdict,
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
