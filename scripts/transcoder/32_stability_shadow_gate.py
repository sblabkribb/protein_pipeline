#!/usr/bin/env python3
"""안정성을 게이트로 올리면 무엇을 버리게 되는지 먼저 재 본다 (그림자 게이트).

왜 바로 올리지 않는가
---------------------
게이트는 자기확증적이다. 안정성으로 설계를 버리기 시작하면 버려진 설계가 실제로
나빴는지 알 방법이 영영 없어진다. 온도 조건 제거를 자동으로 하지 않는 것과 같은
이유다 - 없애면 그 데이터가 더 생기지 않는다.

그래서 먼저 그림자로 돌린다. 실제로 버리지 않고, 버렸다면 무엇을 잃었을지만
센다. 이미 측정한 endpoint (AF2 pLDDT, RMSD) 로 그 대가를 잰다.

무엇을 재는가
-------------
1. 같은 백본 안에서 Rosetta score_per_residue 가 pLDDT/RMSD 와 같은 순위를
   주는가. 두 지표가 무관하면 안정성 게이트는 구조 품질과 상관없이 설계를
   버린다는 뜻이다.
2. 안정성 게이트를 걸면 구조 게이트를 통과한 설계 중 몇 개를 잃는가.
   이득 없는 손실이면 게이트로 올릴 근거가 없다.

Rosetta 절대 점수는 백본 간 비교가 불가능하다 (comparability: same_backbone_only).
그래서 모든 비교를 백본 안에서만 하고, 게이트도 백본 내 분위수로 정의한다.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUTPUTS = Path("/opt/protein_pipeline/outputs")
PLDDT_MIN = 85.0


def spearman(xs, ys):
    if len(xs) < 3:
        return None

    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            mid = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = mid
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def collect() -> list[dict]:
    """run/tier 하나가 한 백본이다. 그 안에서만 비교한다."""
    groups = []
    for relax_path in sorted(OUTPUTS.glob("*/tiers/*/relax_scores.json")):
        tier_dir = relax_path.parent
        af2_path = tier_dir / "af2_scores.json"
        if not af2_path.exists():
            continue
        try:
            relax = json.loads(relax_path.read_text()).get("score_per_residue") or {}
            af2 = json.loads(af2_path.read_text())
        except Exception:
            continue
        plddt = af2.get("scores") or {}
        rmsd = af2.get("rmsd_scores") or {}
        shared = sorted(set(relax) & set(plddt))
        if len(shared) < 5:
            continue
        groups.append({
            "run": tier_dir.parts[-3], "tier": tier_dir.name,
            "designs": [{"id": k, "relax": float(relax[k]),
                         "plddt": float(plddt[k]),
                         "rmsd": float(rmsd[k]) if k in rmsd else None}
                        for k in shared],
        })
    return groups


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quantile", type=float, default=0.5,
                        help="백본 안에서 상위 이 비율만 통과시키는 그림자 게이트")
    parser.add_argument("--out", default=str(BASE / "stability_shadow_gate.json"))
    args = parser.parse_args(argv)

    groups = collect()
    n_designs = sum(len(g["designs"]) for g in groups)
    print(f"백본(run/tier) {len(groups)} · 설계 {n_designs}")
    if not groups:
        print("relax 와 af2 를 함께 가진 백본이 없다")
        return 1

    rho_plddt, rho_rmsd = [], []
    kept = lost = passed_structure = 0
    lost_examples = []
    # 전체 손실률은 분위수가 정하므로(중앙값 컷이면 50%) 그 자체로는 정보가 없다.
    # 게이트가 '좋은 설계' 를 버리는지가 결정적이므로 백본 내 pLDDT 상위
    # 10%/25% 가 얼마나 걸리는지 따로 센다.
    top_lost = {10: 0, 25: 0}
    top_total = {10: 0, 25: 0}
    for group in groups:
        ds = group["designs"]
        r = spearman([d["relax"] for d in ds], [d["plddt"] for d in ds])
        if r is not None:
            rho_plddt.append(r)
        with_rmsd = [d for d in ds if d["rmsd"] is not None]
        if len(with_rmsd) >= 3:
            r2 = spearman([d["relax"] for d in with_rmsd],
                          [d["rmsd"] for d in with_rmsd])
            if r2 is not None:
                rho_rmsd.append(r2)

        # 그림자 게이트: 백본 안에서 relax 점수가 낮은(=안정한) 상위 분위수만 통과
        ordered = sorted(ds, key=lambda d: d["relax"])
        cut = max(1, int(round(len(ordered) * args.quantile)))
        allowed = {d["id"] for d in ordered[:cut]}

        if len(ds) >= 8:
            by_plddt = sorted(ds, key=lambda d: -d["plddt"])
            for pct, divisor in ((10, 10), (25, 4)):
                top = {d["id"] for d in by_plddt[: max(1, len(by_plddt) // divisor)]}
                top_total[pct] += len(top)
                top_lost[pct] += sum(1 for i in top if i not in allowed)
        for d in ds:
            if d["plddt"] < PLDDT_MIN:
                continue
            passed_structure += 1
            if d["id"] in allowed:
                kept += 1
            else:
                lost += 1
                if len(lost_examples) < 8:
                    lost_examples.append(
                        {"run": group["run"], "id": d["id"],
                         "plddt": round(d["plddt"], 2), "relax": round(d["relax"], 4)})

    report = {
        "purpose": "안정성을 게이트로 올렸을 때의 대가를 실제로 버리기 전에 잰다",
        "why_not_promote_directly": (
            "게이트는 자기확증적이다. 안정성으로 버리기 시작하면 버려진 설계가 "
            "실제로 나빴는지 확인할 데이터가 더 생기지 않는다."
        ),
        "comparability": "Rosetta 절대 점수는 백본 간 비교 불가. 모든 비교와 게이트를 백본 안에서만 한다.",
        "n_backbones": len(groups), "n_designs": n_designs,
        "shadow_gate_quantile": args.quantile,
        "structure_gate": f"plddt >= {PLDDT_MIN}",
        "rank_agreement": {
            "relax_vs_plddt": {
                "n_backbones": len(rho_plddt),
                "median_rho": round(statistics.median(rho_plddt), 4) if rho_plddt else None,
                "mean_rho": round(statistics.mean(rho_plddt), 4) if rho_plddt else None,
                "frac_negative": round(sum(1 for r in rho_plddt if r < 0) / len(rho_plddt), 3) if rho_plddt else None,
            },
            "relax_vs_rmsd": {
                "n_backbones": len(rho_rmsd),
                "median_rho": round(statistics.median(rho_rmsd), 4) if rho_rmsd else None,
                "frac_negative": round(sum(1 for r in rho_rmsd if r < 0) / len(rho_rmsd), 3) if rho_rmsd else None,
            },
        },
        "cost": {
            "passed_structure_gate": passed_structure,
            "kept_by_stability_gate": kept,
            "lost_to_stability_gate": lost,
            "loss_fraction": round(lost / passed_structure, 4) if passed_structure else None,
            "loss_fraction_note": ("분위수가 정하는 값이라 그 자체로는 정보가 없다. "
                                   "아래 top_plddt_lost 가 결정적이다."),
            "top_plddt_lost": {
                f"top{pct}pct": {
                    "n": top_total[pct],
                    "lost": top_lost[pct],
                    "fraction": (round(top_lost[pct] / top_total[pct], 4)
                                 if top_total[pct] else None),
                    "random_gate_would_lose": round(1.0 - args.quantile, 4),
                }
                for pct in (10, 25)
            },
            "examples_lost": lost_examples,
        },
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    ra = report["rank_agreement"]
    print(f"\n순위 일치 (백본 안, 백본마다 rho 하나)")
    print(f"  relax vs pLDDT : 중앙값 rho {ra['relax_vs_plddt']['median_rho']} "
          f"· 음수 비율 {ra['relax_vs_plddt']['frac_negative']} "
          f"· n={ra['relax_vs_plddt']['n_backbones']}")
    print(f"  relax vs RMSD  : 중앙값 rho {ra['relax_vs_rmsd']['median_rho']} "
          f"· 음수 비율 {ra['relax_vs_rmsd']['frac_negative']} "
          f"· n={ra['relax_vs_rmsd']['n_backbones']}")
    c = report["cost"]
    print(f"\n그림자 게이트 대가 (상위 {args.quantile:.0%} 통과)")
    print(f"  구조 게이트 통과 {c['passed_structure_gate']} → "
          f"유지 {c['kept_by_stability_gate']} · 잃음 {c['lost_to_stability_gate']} "
          f"({c['loss_fraction']:.1%})")
    for pct in (10, 25):
        t = c["top_plddt_lost"][f"top{pct}pct"]
        if t["fraction"] is not None:
            print(f"  pLDDT 상위 {pct}% 중 버려짐 {t['fraction']:.1%} "
                  f"(무작위 게이트라면 {t['random_gate_would_lose']:.0%}) · n={t['n']}")

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
