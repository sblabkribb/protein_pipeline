#!/usr/bin/env python3
"""M2b — confirmatory candidate pool 깊이의 동적 범위 진단. 정책 비교가 아니다.

`24 candidates/backbone` 은 두 근거로 정해졌다.
  (a) 5 backbone x 24 = 120 으로 당시 budget ceiling 을 맞춘다
  (b) v1 홀드아웃의 24 seq/backbone 규모와 같게 한다
10 backbone 설계에서 (a) 는 무효다. (b) 는 backbone 수와 무관하므로 살아 있다.

그래서 이 진단은 **backbone 당 관측 수 k** 를 축으로 쓴다. 균등 배분에서
k = B / u 이므로 unit 수가 5 든 10 든 같은 축이다. 여기서 답하는 질문은 하나다:

    k 를 12 · 18 · 24 까지 두면 EFBC 가 움직이다 멈추는 것을 볼 수 있는가.

**하지 않는 것**: adaptive vs static, 정책 uplift, kappa, 예산별 판정.
v1 profile 의 abandon/movability 논리를 후보 깊이 근거로 쓰지 않는다 - v2
CoverageAction 에는 abandon 이 없다. 여기서 나오는 k 는 historical v1 에서
관측된 깊이이고 새 코호트의 최적 깊이가 아니다.
읽는 것은 동결된 v1 격자 (`holdout_grid/af2_order_metric.csv`) 뿐이고, 배분은
균등 round-robin 하나만 쓴다. M1/M2 와 같은 설계 진단이다.
"""

from __future__ import annotations

import collections
import csv
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "public_data" / "benchmark" / "gate0"
GRID = BASE / "holdout_grid" / "af2_order_metric.csv"
OUT = BASE / "m2b_candidate_depth_diagnostic.json"

#: 동결된 joint-pass. 여기서 다시 고르지 않는다.
PLDDT, RMSD, SOLU = 85.0, 2.0, 0.5
#: 검토 대상 후보 수. warm-up 후보는 3 과 4.
DEPTHS = (12, 18, 24)
WARMUPS = (3, 4)
#: 측정된 AF2 길이 적합 (af2_length_scaling.json)
AF2_COEF, AF2_EXP = 2.890344, 0.748


def joint_pass(row: dict) -> bool | None:
    try:
        return (float(row["plddt"]) >= PLDDT
                and float(row["rmsd_nonloop_order"]) <= RMSD
                and float(row["soluprot"]) >= SOLU)
    except (TypeError, ValueError):
        return None


def efbc(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    h = -sum((c / total) * math.log(c / total) for c in counts if c > 0)
    return math.exp(h)


def main() -> int:
    rows = [r for r in csv.DictReader(GRID.open(encoding="utf-8"))
            if r["backbone_source"] == "rfd3"]
    by: dict[str, dict[str, list[bool]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for r in rows:
        v = joint_pass(r)
        if v is not None:
            by[r["target_id"]][r["backbone_key"]].append(v)

    depth = {t: {b: len(v) for b, v in bb.items()} for t, bb in by.items()}
    uniform = sorted({d for t in depth.values() for d in t.values()})
    print(f"타겟 {len(by)} · backbone 당 관측 수 {uniform}")
    if uniform != [24]:
        print("  경고: backbone 당 후보 수가 균일하지 않다")

    # k = backbone 당 관측 수. 균등 배분에서 k = B/u 이므로 unit 수에 불변이다.
    curves: dict[str, dict[str, float]] = {}
    informative: dict[int, int] = {}
    yield_mass: dict[str, dict[str, float]] = {}
    for target, bbs in by.items():
        units = sorted(bbs)
        row_efbc, row_yield = {}, {}
        for k in range(1, 25):
            counts = [sum(bbs[b][:k]) for b in units]
            row_efbc[str(k)] = round(efbc(counts), 4)
            row_yield[str(k)] = sum(counts)
        curves[target] = {"n_units": len(units), **row_efbc}
        total = row_yield["24"]
        yield_mass[target] = {
            k: (round(row_yield[k] / total, 4) if total else None)
            for k in ("4", "12", "18", "24")}
    for k in (3, 4, 12, 18, 24):
        informative[k] = sum(
            1 for t, bbs in by.items()
            if sum(1 for b in bbs if any(bbs[b][:k])) >= 2)

    def stat(k: int) -> dict:
        vals = [curves[t][str(k)] for t in curves]
        ratios = [curves[t][str(k)] / curves[t]["n_units"] for t in curves]
        vals_s, rat_s = sorted(vals), sorted(ratios)
        mid = len(vals) // 2
        return {"median_efbc": round(vals_s[mid], 4),
                "mean_efbc": round(sum(vals) / len(vals), 4),
                "median_ratio": round(rat_s[mid], 4),
                "mean_ratio": round(sum(ratios) / len(ratios), 4)}

    per_k = {str(k): stat(k) for k in range(1, 25)}

    # 깊이를 늘려 얻는 것: k 에서 얻은 EFBC 가 k=24 값의 몇 %인가, 그리고
    # 구간마다 후보 하나당 EFBC 증가분이 얼마나 남아 있는가.
    windows = {}
    for lo, hi in ((4, 12), (12, 18), (18, 24), (4, 24)):
        d = [(curves[t][str(hi)] - curves[t][str(lo)]) for t in curves]
        windows[f"{lo}->{hi}"] = {
            "mean_delta_efbc": round(sum(d) / len(d), 4),
            "mean_delta_per_candidate": round(sum(d) / len(d) / (hi - lo), 5),
            "targets_increasing": sum(1 for x in d if x > 1e-9),
            "targets_flat_or_down": sum(1 for x in d if x <= 1e-9),
        }
    reached = {str(k): round(
        sum(curves[t][str(k)] / curves[t]["24"] for t in curves
            if curves[t]["24"] > 0) / sum(1 for t in curves if curves[t]["24"] > 0), 4)
        for k in (4, 12, 18, 24)}

    # 비용. 측정된 길이 적합으로 confirmatory 코호트의 AF2 초를 낸다.
    holdout = json.loads((BASE / "masked_holdout_targets.json").read_text(encoding="utf-8"))
    lengths = {t["domain"]: t["length"] for t in holdout["selected"]}
    per_fold = {d: AF2_COEF * (L ** AF2_EXP) for d, L in lengths.items()}
    cost = {}
    for n in DEPTHS:
        per_source = sum(v * 10 * n for v in per_fold.values())
        cost[str(n)] = {
            "folds_per_target_per_source": 10 * n,
            "folds_per_source": 12 * 10 * n,
            "folds_both_sources": 12 * 10 * n * 2,
            "af2_seconds_per_source": round(per_source),
            "af2_hours_both_sources": round(per_source * 2 / 3600, 1),
        }

    # warm-up 이 tier 혼합과 맞는가. prefix 는 30->50->70 반복이다.
    tiers = {}
    for w in WARMUPS:
        prefix = [("30", "50", "70")[i % 3] for i in range(w)]
        c = collections.Counter(prefix)
        tiers[str(w)] = {
            "prefix": prefix,
            "tier_counts": dict(c),
            "balanced": len(set(c.values())) == 1 and len(c) == 3,
            "max_minus_min": max(c.values()) - min(c.values()),
            "warmup_slots_per_target_per_source": w * 10,
        }
    for w in WARMUPS:
        for n in DEPTHS:
            tiers[str(w)][f"adaptive_slots_at_{n}"] = 10 * n - w * 10
            tiers[str(w)][f"warmup_fraction_at_{n}"] = round(w / n, 4)

    report = {
        "purpose": "M2b - confirmatory candidate pool 깊이의 동적 범위. 정책 비교가 아니다.",
        "does_not_do": ["adaptive vs static 비교", "정책 uplift", "kappa 선택",
                        "예산별 채택 판정"],
        "reads_labels": True,
        "axis": "k = backbone 당 관측 수. 균등 배분에서 k = B/u 이므로 unit 수에 불변이다.",
        "source_cohort": "동결 v1 격자의 rfd3 코호트 (12 타겟 x 5 backbone x 24)",
        "feasibility": f"pLDDT >= {PLDDT} and rmsd <= {RMSD} and soluprot >= {SOLU}",
        "n_targets": len(by),
        "efbc_by_k": per_k,
        "per_target_curve": curves,
        "fraction_of_full_depth_efbc": reached,
        "delta_windows": windows,
        "yield_mass_fraction": yield_mass,
        "coverage_informative_targets_by_k": informative,
        "af2_cost": {"fit": f"elapsed_s = {AF2_COEF} * length^{AF2_EXP}",
                     "fit_n_points": 4,
                     "fit_caveat": "4 점 적합이다. 자릿수 비교에만 쓴다.",
                     "target_lengths": lengths, "by_depth": cost},
        "warmup_tier_alignment": tiers,
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   capture_output=True, text=True).stdout.strip(),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nk 별 EFBC (12 타겟, unit 5)")
    print(f"  {'k':>3}{'median':>9}{'mean':>8}{'mean/u':>9}")
    for k in (1, 2, 3, 4, 6, 8, 12, 16, 18, 20, 24):
        s = per_k[str(k)]
        print(f"  {k:>3}{s['median_efbc']:>9.3f}{s['mean_efbc']:>8.3f}"
              f"{s['mean_ratio']:>9.3f}")
    print(f"\nk=24 EFBC 의 몇 %에 도달하는가: "
          + " · ".join(f"k={k} {v:.1%}" for k, v in reached.items()))
    print("\n구간별 후보 하나당 EFBC 증가분")
    for w, v in windows.items():
        print(f"  {w:>8}  총 {v['mean_delta_efbc']:+.3f}  "
              f"후보당 {v['mean_delta_per_candidate']:+.5f}  "
              f"증가 타겟 {v['targets_increasing']}/12")
    print(f"\ncoverage-informative 타겟 수 (feasible unit >= 2): {informative}")
    print("\nAF2 비용 (측정 길이 적합, 4 점)")
    for n, c in cost.items():
        print(f"  {n:>2}/backbone  폴드 {c['folds_both_sources']:>5}  "
              f"AF2 {c['af2_hours_both_sources']:>7.1f} GPU-시간 (두 source)")
    print("\nwarm-up prefix 의 tier 균형")
    for w, v in tiers.items():
        print(f"  warm-up {w}  prefix {v['prefix']}  {v['tier_counts']}  "
              f"균형 {v['balanced']}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
