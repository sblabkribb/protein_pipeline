#!/usr/bin/env python3
"""v2 confirmatory 종점의 **평가가능성** 판정. EFBC 를 계산하기 전에 결정된다.

왜 replay 보다 먼저인가
-----------------------
동결 계획서가 예산 격자의 각 점마다 판정 가능 여부를 미리 정해 뒀다::

    B 는 target x source 단위다 (anchors.warmup = "10 unit x 4 의무 probe = 40")
    u < 10 이면 그 조합의 warm-up 은 4u, ceiling 은 18u 다
    ceiling 을 넘는 격자점에서 그 타겟은 non-evaluable 로 기록하고
      그 B 의 informative set 에서 빠진다
    **최소 클러스터 8 을 밑도는 B 는 그 source 에서 판정하지 않는다**
    anchors (40, 180) 는 replay 정합성 확인용이고 판정점이 아니다
    B < 40 은 warm-up/prefix diagnostic 으로만 보고한다

그래서 informative set 의 크기가 8 에 못 미치면 **EFBC 를 계산해도 그 수를
종점으로 쓸 수 없다.** 계산해서 보고하면 동결 규칙이 금지한 판정을 사실상
하게 되므로, 여기서는 계산하지 않고 평가가능성만 기록한다.

이 스크립트가 하지 않는 것
--------------------------
- 최소 클러스터 8 을 낮추지 않는다. 결과를 보고 임계값을 바꾸는 것이다.
- 판정 불가인 source 에 대해 EFBC 수치를 만들지 않는다.
- source 를 합치지 않는다 (`pooling_across_sources_forbidden`).
- kappa 가 식별되지 않은 source 의 confirmatory 를 진행하지 않는다 (§10).
- u=0 인 타겟을 예비 타겟으로 교체하지 않는다 (`on_shortfall`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUT_DIR = BASE / "v2_multisource"

#: 동결 값. 여기서 바꾸지 않는다.
MIN_CLUSTERS = 8


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT_DIR / "confirmatory_evaluability.json"))
    args = ap.parse_args(argv)

    plan = json.loads((BASE / "multisource_validation_plan.json").read_text(encoding="utf-8"))
    runs = json.loads((OUT_DIR / "backbones.json").read_text(encoding="utf-8"))["runs"]
    kfreeze = json.loads((OUT_DIR / "kappa_identification_freeze.json").read_text(encoding="utf-8"))

    f = plan["generation_rules"]["unequal_units_formula"]
    warm_per, ceil_per = int(f["warmup_per_unit"]), int(f["ceiling_per_unit"])
    grid = [int(b) for b in plan["budget_grid"]["primary"]]
    informative_pts = {int(b) for b in plan["budget_grid"]["primary_informative"]}
    anchors = {int(plan["budget_grid"]["anchors"]["warmup"]),
               int(plan["budget_grid"]["anchors"]["ceiling"])}

    out = {
        "artifact": "rapid_v2_confirmatory_evaluability",
        "purpose": "confirmatory 종점의 평가가능성. EFBC 계산 전에 동결 규칙으로 결정된다.",
        "plan_id": plan["plan_id"], "plan_version": plan["version"],
        "rules_applied": {
            "budget_unit": "target x source (anchors.warmup=40 = 10 unit x 4 probe)",
            "unequal_units": plan["generation_rules"]["unequal_units"],
            "min_clusters": MIN_CLUSTERS,
            "anchors_excluded_from_primary_judgement": True,
            "warmup_per_unit": warm_per, "ceiling_per_unit": ceil_per,
        },
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "kappa_freeze_sha256": hashlib.sha256(
            (OUT_DIR / "kappa_identification_freeze.json").read_bytes()).hexdigest(),
        "per_source": {},
        "efbc_not_computed_where_unjudgeable": (
            "판정 불가인 B 에 대해 EFBC 를 계산하지 않았다. 계산해 보고하면 "
            "동결 규칙이 금지한 판정을 사실상 하게 된다."),
    }

    for source in plan["sources"]["ids"]:
        per_target = {}
        for r in runs.values():
            if r["cohort"] != "confirmatory" or r["backbone_source"] != source:
                continue
            u = int(r.get("u_accepted") or 0)
            state = ("generation_error" if r.get("generation_error")
                     else "SOURCE_GENERATION_INFEASIBLE"
                     if r.get("source_generation_infeasible")
                     else "shortfall" if r.get("shortfall") else "full")
            per_target[r["target_id"]] = {
                "u": u, "state": state,
                "warmup": warm_per * u, "ceiling": ceil_per * u,
                "evaluable_at_all": bool(u > 0),
            }
        evaluable = {t: v for t, v in per_target.items() if v["u"] > 0}

        by_budget = {}
        for b in grid:
            n = sum(1 for v in evaluable.values() if v["ceiling"] >= b)
            if b in anchors:
                verdict = "EXCLUDED_ANCHOR"
            elif n < MIN_CLUSTERS:
                verdict = "NOT_JUDGED_MIN_CLUSTERS"
            else:
                verdict = "JUDGEABLE"
            by_budget[str(b)] = {
                "informative_targets": n, "verdict": verdict,
                "is_primary_informative": b in informative_pts,
                "dropped_by_ceiling": sorted(
                    t for t, v in evaluable.items() if v["ceiling"] < b),
            }

        kappa = kfreeze["per_source"][source]
        judgeable = [b for b, v in by_budget.items()
                     if v["verdict"] == "JUDGEABLE" and v["is_primary_informative"]]
        if kappa["verdict"] != "IDENTIFIED":
            status = "BLOCKED_KAPPA_NOT_IDENTIFIED"
            why = ("§10 — kappa 가 식별되지 않았으므로 confirmatory RAPID 을 "
                   "진행하지 않는다. 다른 source 의 kappa 를 빌리지 않는다.")
        elif not judgeable:
            status = "NOT_EVALUABLE_INSUFFICIENT_CLUSTERS"
            why = (f"kappa 는 식별됐으나 primary informative 격자점 전부에서 "
                   f"informative set 이 최소 클러스터 {MIN_CLUSTERS} 에 미달한다. "
                   f"동결 규칙상 어떤 B 도 판정하지 않는다.")
        else:
            status = "EVALUABLE"
            why = f"판정 가능한 primary informative 격자점: {sorted(judgeable, key=int)}"

        out["per_source"][source] = {
            "kappa_verdict": kappa["verdict"],
            "frozen_hyperparameters": kappa.get("frozen_hyperparameters"),
            "n_targets": len(per_target),
            "n_targets_with_units": len(evaluable),
            "u_total": sum(v["u"] for v in per_target.values()),
            "per_target": dict(sorted(per_target.items())),
            "by_budget": by_budget,
            "judgeable_primary_informative_budgets": sorted(judgeable, key=int),
            "confirmatory_status": status,
            "why": why,
        }

    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text, encoding="utf-8")

    for source, e in out["per_source"].items():
        print(f"=== confirmatory / {source}")
        print(f"  kappa {e['kappa_verdict']} · 타겟 {e['n_targets']} · "
              f"u>0 타겟 {e['n_targets_with_units']} · Σu {e['u_total']}")
        print(f"  {'B':>6}  {'informative':>12}  판정")
        for b, v in e["by_budget"].items():
            print(f"  {b:>6}  {v['informative_targets']:12d}  {v['verdict']}")
        print(f"  => {e['confirmatory_status']}")
        print(f"     {e['why']}\n")
    print(args.out)
    print("sha256", hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
