#!/usr/bin/env python3
"""실제로 쓴 계산량 기준의 2 차 분석. 사전 정의된 1 차 endpoint 는 건드리지 않는다.

왜 분리했는가
-------------
동결된 spec 의 1 차 endpoint 는 "예산 상한 안에서 찾은 설계 수" 다. 그 정의를
결과를 본 뒤에 바꾸면 사전등록이 무의미해지므로 39_prospective_allocation_
validation.py 는 그대로 두고, 여기서 다른 질문을 따로 묻는다.

물어야 할 것이 하나 더 있는 이유는 예산이 상한이지 지출이 아니기 때문이다.
적응 정책은 movability 가 바닥인 백본을 버리고 남은 예산을 쓰지 않는다. 정적
배분은 상한을 늘 다 쓴다. 그래서 "같은 상한" 비교는 두 정책에게 같은 계산량을
준 비교가 아니다. 상한 120 에서 적응이 −0.24 개를 덜 찾은 것도 이 때문인데,
1 차 지표는 그 값을 그대로 보고하고 (사후 변경 금지), 여기서 같은 실행이 계산을
얼마나 덜 썼는지를 따로 잰다.

이 스크립트는 39_ 의 정책 실행 함수를 import 해서 쓴다. 정책을 다시 구현하면
두 분석이 서로 다른 정책을 재는데도 같은 이름으로 보고될 수 있다.

네 가지 산출
------------
1. successes vs budget cap          - 1 차와 같은 축 (맥락용, 재계산)
2. actual calls used                - 정책이 실제로 쓴 호출 수
3. successes at matched actual calls - 적응이 s 회 썼을 때, 정적에게도 s 회만 주면?
4. calls required for matched success - 적응이 찾은 만큼을 정적이 찾으려면 몇 회?
그리고 (계산량, 성공 수) 파레토 프론티어.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import random
import statistics
import subprocess
import sys
import time
import zlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUT_JSON = BASE / "holdout_grid" / "realized_compute_analysis.json"


def _load_v1():
    """39_ 의 정책 구현을 그대로 쓴다. 재구현하면 다른 정책을 재게 된다."""
    path = Path(__file__).resolve().parent / "39_prospective_allocation_validation.py"
    spec = importlib.util.spec_from_file_location("v1_prospective", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V1 = _load_v1()


def clustered_ci(per_target: dict[str, list[float]], *, iters: int, seed: int):
    """타겟 클러스터 부트스트랩. 39_ 와 같은 구현을 쓴다."""
    return V1.clustered_ci(per_target, iters=iters, seed=seed)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=200)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--label", choices=("joint", "structural"), default="joint")
    ap.add_argument("--include-native", action="store_true")
    ap.add_argument("--caps", default=",".join(
        [str(b) for b in range(4, 25, 4)] + ["30", "40", "50", "60", "80", "100", "120"]))
    ap.add_argument("--out", default=str(OUT_JSON))
    args = ap.parse_args()

    cohort, dropped = V1.load_cohort(include_native=args.include_native, label=args.label)
    informative = {}
    for t, bbs in cohort.items():
        ys = [statistics.mean(v) for v in bbs.values()]
        if len(bbs) >= 2 and not (all(y == 0.0 for y in ys) or all(y == 1.0 for y in ys)):
            informative[t] = bbs
    print(f"코호트 타겟 {len(cohort)} · 정보 있는 타겟 {len(informative)} · 제외 {dropped}")
    if len(informative) < V1.MIN_INFORMATIVE_CLUSTERS:
        print("판정 거부: 정보 있는 클러스터가 부족하다")
        return 2

    caps = [int(c) for c in args.caps.split(",")]
    max_k = max(len(v) for v in informative.values())
    uniform_k = max_k  # 균등 배분 = 모든 백본에 고르게
    #: 정적이 성공 수를 맞추려 할 때 허용하는 최대 호출. 코호트의 전체 관측 수다.
    ceiling = max(sum(len(v) for v in bbs.values()) for bbs in informative.values())

    per_cap: dict[str, dict] = {}
    frontier: list[dict] = []
    for cap in caps:
        acc = {
            "adaptive_found": collections.defaultdict(list),
            "adaptive_spent": collections.defaultdict(list),
            "uniform_found": collections.defaultdict(list),
            "uniform_spent": collections.defaultdict(list),
            # 3. 적응이 실제로 쓴 만큼만 정적에게 준다
            "matched_compute_delta": collections.defaultdict(list),
            "matched_compute_static_found": collections.defaultdict(list),
            # 4. 적응이 찾은 만큼을 정적이 찾는 데 드는 호출
            "matched_success_static_calls": collections.defaultdict(list),
            "matched_success_delta": collections.defaultdict(list),
        }
        unreached = reached = 0
        for t, bbs in sorted(informative.items()):
            avail = sum(len(v) for v in bbs.values())
            b = min(cap, avail)
            for rep in range(args.replicates):
                rng = random.Random(zlib.crc32(f"{args.seed}|{t}|{cap}|{rep}".encode()))
                a = V1.run_adaptive(t, bbs, b, random.Random(rng.randrange(1 << 30)))
                u = V1.run_static(t, bbs, b, uniform_k,
                                  random.Random(rng.randrange(1 << 30)))
                acc["adaptive_found"][t].append(a["found"])
                acc["adaptive_spent"][t].append(a["spent"])
                acc["uniform_found"][t].append(u["found"])
                acc["uniform_spent"][t].append(u["spent"])

                # 3. 같은 실현 계산량: 정적에게 적응이 쓴 만큼만 준다
                m = V1.run_static(t, bbs, min(a["spent"], avail), uniform_k,
                                  random.Random(rng.randrange(1 << 30)))
                acc["matched_compute_static_found"][t].append(m["found"])
                acc["matched_compute_delta"][t].append(a["found"] - m["found"])

                # 4. 같은 성공 수: 정적이 적응만큼 찾으려면 몇 회 걸리나
                full = V1.run_static(t, bbs, min(ceiling, avail), uniform_k,
                                     random.Random(rng.randrange(1 << 30)))
                need = V1.calls_to(full["trace"], a["found"]) if a["found"] > 0 else 0
                if need is None:
                    unreached += 1
                else:
                    reached += 1
                    acc["matched_success_static_calls"][t].append(need)
                    acc["matched_success_delta"][t].append(a["spent"] - need)

        row: dict = {"cap": cap}
        for key in ("adaptive_found", "adaptive_spent", "uniform_found", "uniform_spent",
                    "matched_compute_static_found", "matched_compute_delta",
                    "matched_success_static_calls", "matched_success_delta"):
            vals = [v for t in acc[key] for v in acc[key][t]]
            if not vals:
                row[key] = None
                continue
            lo, hi = clustered_ci(acc[key], iters=args.bootstrap, seed=args.seed)
            row[key] = {"mean": round(statistics.mean(vals), 3),
                        "ci95": [round(lo, 3), round(hi, 3)],
                        "excludes_zero": bool(lo > 0 or hi < 0)}
        row["matched_success_reach"] = {
            "reached": reached, "unreached": unreached,
            "rate": round(reached / (reached + unreached), 4) if reached + unreached else None,
            "note": "정적이 상한 안에 적응의 성공 수를 못 채운 재생은 제외했다. "
                    "제외된 쪽이 정적에게 불리한 경우이므로 남은 비교는 정적에 후하다."}
        per_cap[str(cap)] = row

        frontier.append({"cap": cap, "policy": "adaptive",
                         "calls": row["adaptive_spent"]["mean"],
                         "successes": row["adaptive_found"]["mean"]})
        frontier.append({"cap": cap, "policy": f"uniform_k{uniform_k}",
                         "calls": row["uniform_spent"]["mean"],
                         "successes": row["uniform_found"]["mean"]})

        mc, ms = row["matched_compute_delta"], row["matched_success_delta"]
        print(f"\n상한 {cap}: 적응 {row['adaptive_found']['mean']:.2f} 개 / "
              f"{row['adaptive_spent']['mean']:.1f} 회 · "
              f"균등 {row['uniform_found']['mean']:.2f} 개 / {row['uniform_spent']['mean']:.1f} 회")
        print(f"   같은 실현 계산량에서 적응 − 정적 = {mc['mean']:+.2f} 개 "
              f"[{mc['ci95'][0]:+.2f}, {mc['ci95'][1]:+.2f}]"
              f"{' *' if mc['excludes_zero'] else ''}")
        if ms:
            print(f"   같은 성공 수까지 적응 − 정적 = {ms['mean']:+.2f} 회 "
                  f"[{ms['ci95'][0]:+.2f}, {ms['ci95'][1]:+.2f}]"
                  f"{' *' if ms['excludes_zero'] else ''} (음수 = 적응이 덜 씀)")

    # 파레토: 계산량이 더 적으면서 성공이 더 많거나 같은 점이 있으면 지배된다.
    for point in frontier:
        point["dominated_by"] = [
            f"{o['policy']}@cap{o['cap']}" for o in frontier
            if o is not point and o["calls"] <= point["calls"]
            and o["successes"] >= point["successes"]
            and (o["calls"] < point["calls"] or o["successes"] > point["successes"])]
        point["on_frontier"] = not point["dominated_by"]
    on = [p for p in frontier if p["on_frontier"]]
    print(f"\n파레토 프론티어 {len(on)}/{len(frontier)} 점")
    for p in sorted(on, key=lambda x: x["calls"]):
        print(f"   {p['policy']:12s} 상한 {p['cap']:>3} · 호출 {p['calls']:>6.1f} · "
              f"성공 {p['successes']:>6.2f}")
    by_policy = collections.Counter(p["policy"] for p in on)
    print(f"   프론티어 구성: {dict(by_policy)}")

    out = {
        "purpose": "실제로 쓴 계산량 기준 2 차 분석. 사전 정의된 1 차 endpoint 는 "
                   "39_prospective_allocation_validation.py 에 그대로 있고 여기서 "
                   "바꾸지 않는다.",
        "relationship_to_primary": {
            "primary_endpoint": "예산 상한 안에서 찾은 설계 수 (동결 spec)",
            "primary_unchanged": True,
            "primary_artifact": "holdout_grid/prospective_allocation_validation_joint.json",
            "why_secondary_exists": "예산은 상한이고 적응 정책은 백본을 버리면 남은 "
                                    "예산을 쓰지 않는다. 같은 상한 비교는 같은 계산량 "
                                    "비교가 아니다.",
            "how_to_read_budget_120": "1 차 지표에서 상한 120 의 −0.24 개는 그대로 "
                                      "보고한다. 같은 실행에서 적응은 106.4 회만 썼다. "
                                      "두 값을 함께 읽어야 하고, 한쪽으로 다른 쪽을 "
                                      "지우면 안 된다.",
        },
        "policy_source": "39_prospective_allocation_validation.py 에서 import "
                         "(정책 재구현 없음)",
        "label": args.label,
        "cohort": "rfd3_only" if not args.include_native else "rfd3_plus_native",
        "n_targets": len(cohort), "n_informative_targets": len(informative),
        "replicates": args.replicates, "bootstrap_iters": args.bootstrap,
        "seed": args.seed,
        "uniform_k": uniform_k,
        "endpoints": {
            "successes_vs_budget_cap": "adaptive_found / uniform_found",
            "actual_calls_used": "adaptive_spent / uniform_spent",
            "successes_at_matched_actual_calls": "matched_compute_delta "
                                                 "(정적에게 적응이 쓴 만큼만 준다)",
            "calls_required_for_matched_success": "matched_success_delta "
                                                  "(음수면 적응이 덜 씀)",
        },
        "by_cap": per_cap,
        "pareto": frontier,
        "limits": [
            "타겟 12 개다. 클러스터 부트스트랩의 정밀도가 그만큼만 된다.",
            "재생이므로 백본마다 관측이 24 개뿐이다. 적응이 한 백본을 다 쓰면 실제 "
            "제품에서는 서열을 더 만들 수 있지만 여기서는 옮겨야 한다.",
            "격자는 단일 조건(T=0.1)이다. 조건 탐색 축은 여기에 없다.",
        ],
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
