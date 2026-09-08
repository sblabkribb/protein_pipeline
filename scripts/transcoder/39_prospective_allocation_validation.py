#!/usr/bin/env python3
"""전향 홀드아웃에서 적응 배분 정책을 정적 배분과 같은 예산으로 비교한다.

무엇을 검증하는가
-----------------
격자(12 타겟 x 6 백본 x 24 서열)는 인코더 학습에 쓰이지 않은 타겟에서
**정책을 정하기 전에** 전부 접혔다. 모든 칸이 관측돼 있으므로 어떤 배분
정책이든 새 계산 없이 그대로 재생(replay)할 수 있고, 재생은 근사가 아니라
관측값에서 비복원 추출하는 정확한 계산이다.

정책이 볼 수 있는 것은 Gate 0 사전분포와 자기가 관측한 probe 뿐이다.
백본의 참 yield 는 주입하지 않는다 (allocation.set_backbone_true_yield 는
호출 자체가 TypeError 다). 그래서 "계산을 아꼈다" 는 주장이 성립한다.

검증되지 **않는** 것
--------------------
격자는 단일 조건(T=0.1)으로 돌렸다. 따라서 이 실험은 Gate 1B 의 두 축 중
"어느 백본에 다음 계산을 쓸 것인가" 만 본다. "생성 조건을 바꿔볼 것인가" 는
여기서 검증되지 않는다 - 그것은 패널 2 (온도 스윕) 가 담당한다.
조건이 하나뿐이라 정책의 조건-탐색 항과 다양성 항은 이 실행에서 비활성이다.

기본 코호트는 RFD3 전용이다. 타겟마다 native 백본이 1 개, RFD3 가 5 개인데
native 는 타겟당 1 개뿐이라 백본 수준 비교를 불균형하게 만든다. native 포함은
민감도로만 본다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import random
import statistics
import sys
import zlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.allocation import (  # noqa: E402
    MIN_PROBE_SEQUENCES,
    Arm,
    HierarchicalAllocator,
)

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID_CSV = BASE / "holdout_grid" / "af2_order_metric.csv"
OUT_JSON = BASE / "holdout_grid" / "prospective_allocation_validation.json"

PLDDT_MIN = 85.0
RMSD_MAX = 2.0
SOLUPROT_MIN = 0.5
CONDITION = "T0.1"
#: 정보가 있는 클러스터(타겟) 최소 수. 이 아래면 판정하지 않는다.
MIN_INFORMATIVE_CLUSTERS = 8


# ---- 코호트 -----------------------------------------------------------------

def load_cohort(*, include_native: bool, label: str) -> tuple[dict, dict]:
    """타겟 -> 백본 -> 관측된 통과/실패 목록.

    라벨은 동결된 실험 spec (holdout_experiment_spec.json) 을 따른다.

      joint      primary   pLDDT>=85 & rmsd<=2.0 & soluprot>=0.5
      structural secondary pLDDT>=85 & rmsd<=2.0

    spec 을 동결한 뒤에 primary 를 바꾸면 사전등록의 의미가 없어진다. 그래서
    joint 가 기본이고, structural 은 secondary 로 함께 보고한다. (별개로,
    aggregation 증분정보 검정에서는 SoluProt 을 빼는 것이 맞았다 - 거기서
    물은 것은 "구조 성공을 예측하느냐" 였고 SoluProt 은 그 라벨의 일부가
    아니었다. 여기서 묻는 것은 "예산 안에 쓸 수 있는 설계를 몇 개 얻느냐" 이고,
    쓸 수 있는 설계는 용해도 제약도 통과해야 한다.)
    """
    rows = list(csv.DictReader(GRID_CSV.open(encoding="utf-8")))
    cohort: dict[str, dict[str, list[bool]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    dropped = collections.Counter()
    for row in rows:
        if row["status"] != "ok":
            dropped["fold 실패"] += 1
            continue
        if not include_native and row["backbone_source"] != "rfd3":
            dropped["native 제외"] += 1
            continue
        rmsd, plddt = row["rmsd_nonloop_order"].strip(), row["plddt"].strip()
        if not rmsd or not plddt:
            # 동결된 지표가 대응을 거부한 행이다. 성공/실패로 셀 수 없다.
            dropped[f"지표 거부 ({row['backbone_source']})"] += 1
            continue
        ok = float(plddt) >= PLDDT_MIN and float(rmsd) <= RMSD_MAX
        if label == "joint":
            solu = row.get("soluprot", "").strip()
            if not solu:
                dropped["soluprot 결측"] += 1
                continue
            ok = ok and float(solu) >= SOLUPROT_MIN
        cohort[row["target_id"]][row["backbone_key"]].append(ok)
    return cohort, dict(dropped)


# ---- 정책 -------------------------------------------------------------------

def _draw(pool: list[bool], taken: int) -> bool:
    """이 백본에서 아직 안 본 관측 하나. 비복원 - 같은 서열을 두 번 세지 않는다."""
    return pool[taken]


def run_adaptive(target_id, backbones, budget, rng) -> dict:
    """Gate 0 사전분포 -> 백본별 최소 probe -> movability 기반 배분.

    최소 probe 를 건너뛰지 않는 것이 정책의 일부다. next_action 은 관측 4 개
    미만에서 판정을 거부하는데, 2/2 로 백본을 버리면 되돌릴 수 없기 때문이다.
    그래서 예산의 앞부분은 반드시 probe 에 쓴다 - 이 비용을 정적 배분에
    부과하지 않으므로, 비교는 적응 정책에 불리한 쪽으로 기울어 있다.
    """
    keys = list(backbones)
    pools = {k: rng.sample(backbones[k], len(backbones[k])) for k in keys}
    taken = {k: 0 for k in keys}
    arms = [Arm(target_id=target_id, backbone_id=k, condition=CONDITION) for k in keys]
    policy = HierarchicalAllocator(arms, seed=rng.randrange(1 << 30),
                                   reference_condition=CONDITION)
    spent, found, trace = 0, 0, []

    # 1 단계: 백본마다 최소 probe. 예산이 모자라면 가능한 만큼만 돌린다.
    for key in keys:
        for _ in range(MIN_PROBE_SEQUENCES):
            if spent >= budget or taken[key] >= len(pools[key]):
                break
            ok = _draw(pools[key], taken[key]); taken[key] += 1; spent += 1
            found += int(ok); trace.append(bool(ok))
            policy.observe(f"{target_id}|{key}|{CONDITION}",
                           successes=int(ok), trials=1)

    # 2 단계: 남은 예산은 한 번에 하나씩, 관측을 반영하며 배분한다.
    abandoned: set[str] = set()
    while spent < budget:
        live = [k for k in keys if taken[k] < len(pools[k]) and k not in abandoned]
        if not live:
            # 버린 백본밖에 안 남으면 배분할 곳이 없다. 예산을 남긴다 -
            # 억지로 쓰면 정책이 하지 않을 결정을 대신 하는 것이다.
            break
        # movability 가 바닥인 백본은 정책이 버린다. 그 판정을 존중한다.
        for key in list(live):
            act = policy.next_action(target_id, key)
            if act["action"] == "abandon_backbone":
                abandoned.add(key)
        live = [k for k in live if k not in abandoned]
        if not live:
            break
        # 정책의 점수 규칙을 그대로 쓰되 아직 남은 백본으로만 제한한다.
        # 여기서 살아있는 arm 만으로 allocator 를 다시 만들면 안 된다 - 버린
        # 백본의 관측이 타겟 사후분포에서 빠져서 부분 풀링이 달라지고, 그건
        # 정책을 바꿔놓고 정책을 평가하는 것이 된다. 동점은 키로 깬다.
        pick = max((f"{target_id}|{k}|{CONDITION}" for k in live),
                   key=lambda key: (policy.score(key), key))
        key = policy.arms[pick].backbone_id
        ok = _draw(pools[key], taken[key]); taken[key] += 1; spent += 1
        found += int(ok); trace.append(bool(ok))
        policy.observe(pick, successes=int(ok), trials=1)
    return {"spent": spent, "found": found, "trace": trace,
            "n_abandoned": len(abandoned),
            "concentration": max(taken.values()) / spent if spent else 0.0}


def run_static(target_id, backbones, budget, k, rng) -> dict:
    """백본 k 개를 무작위로 골라 예산을 균등 분배한다. 되먹임 없음.

    k=전체 는 지금까지의 관행이다 - 백본마다 같은 수의 서열을 돌린다.
    k=1 은 "하나 골라서 밀어붙인다" 다.
    """
    keys = rng.sample(list(backbones), min(k, len(backbones)))
    pools = {key: rng.sample(backbones[key], len(backbones[key])) for key in keys}
    spent, found, trace = 0, 0, []
    per = [budget // len(keys)] * len(keys)
    for i in range(budget % len(keys)):
        per[i] += 1
    quota = dict(zip(keys, per))
    used = {key: 0 for key in keys}
    # 백본을 번갈아 돈다. 한 백본을 다 쓴 뒤 다음으로 넘어가면 "N 개까지 몇 번"
    # 이 첫 백본의 운에 좌우된다 - 좋은 백본을 먼저 뽑으면 빠르고 나쁜 백본을
    # 먼저 뽑으면 느리다. 균등 배분의 실제 운영 방식은 번갈아 돌리는 것이고,
    # 그쪽이 시간-기반 endpoint 에서 이기기 더 어려운 대조군이다.
    # 예산 내 성공 수(주 endpoint)는 순서와 무관하므로 이 선택에 영향받지 않는다.
    while spent < budget:
        moved = False
        for key in keys:
            if used[key] >= quota[key] or used[key] >= len(pools[key]):
                continue
            ok = pools[key][used[key]]; used[key] += 1
            found += int(ok); spent += 1; trace.append(bool(ok)); moved = True
            if spent >= budget:
                break
        if not moved:
            break
    return {"spent": spent, "found": found, "trace": trace}


def run_oracle(target_id, backbones, budget, rng) -> dict:
    """참 yield 가 가장 높은 백본만 쓴다. 도달 불가능한 상한이다."""
    order = sorted(backbones, key=lambda k: -statistics.mean(backbones[k]))
    spent, found, trace = 0, 0, []
    for key in order:
        pool = rng.sample(backbones[key], len(backbones[key]))
        for ok in pool:
            if spent >= budget:
                break
            found += int(ok); spent += 1; trace.append(bool(ok))
        if spent >= budget:
            break
    return {"spent": spent, "found": found, "trace": trace}


def calls_to(trace: list[bool], n: int) -> int | None:
    """구조 성공 n 개를 채우는 데 쓴 호출 수. 못 채우면 None - 0 이 아니다.

    못 채운 것을 큰 수로 대체하면 그 수가 결과를 만든다. 도달률을 따로 낸다.
    """
    hit = 0
    for i, ok in enumerate(trace, start=1):
        if ok:
            hit += 1
            if hit >= n:
                return i
    return None


# ---- 부트스트랩 -------------------------------------------------------------

def clustered_ci(per_target: dict[str, list[float]], *, iters: int, seed: int):
    """타겟을 복원 추출하는 부트스트랩. 서열은 타겟 안에서 독립이 아니다."""
    # 타겟별 (합, 개수) 만 있으면 재표본의 평균이 정해진다. 값을 다시
    # 이어붙일 필요가 없다 - 근사가 아니라 같은 값을 더 빠르게 얻는 것이다.
    # 이 덕분에 예산 1~24 전 구간 곡선을 돌릴 수 있다.
    stats = [(float(sum(v)), len(v)) for _, v in sorted(per_target.items()) if v]
    if not stats:
        return None, None
    rng = random.Random(seed)
    n = len(stats)
    means = []
    for _ in range(iters):
        tot = cnt = 0.0
        for _ in range(n):
            a, b = stats[rng.randrange(n)]
            tot += a; cnt += b
        if cnt:
            means.append(tot / cnt)
    means.sort()
    if not means:
        return None, None
    lo = means[int(0.025 * len(means))]
    hi = means[min(len(means) - 1, int(0.975 * len(means)))]
    return lo, hi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=200,
                    help="타겟·예산·정책마다 재생 횟수")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--include-native", action="store_true",
                    help="민감도: native 백본도 포함")
    ap.add_argument("--budgets", default=",".join(
        [str(b) for b in range(1, 25)] + ["30", "40", "50", "60", "80", "100", "120"]),
        help="동결 spec 의 secondary endpoint 는 예산 1~24 전 구간 곡선이다")
    ap.add_argument("--label", choices=("joint", "structural"), default="joint",
                    help="joint 가 동결 spec 의 primary endpoint 다")
    args = ap.parse_args()

    cohort, dropped = load_cohort(include_native=args.include_native, label=args.label)
    budgets = [int(b) for b in args.budgets.split(",")]
    print(f"코호트 타겟 {len(cohort)} · 제외 {dropped}")

    # 정보가 있는 타겟만 판정 대상이다. 백본 yield 가 전부 같으면 어디에
    # 배분하든 결과가 같아서, 배분 정책을 구별할 수 없다.
    # 동결된 규칙 (holdout_experiment_spec.analysis_fixed_in_advance):
    # "모든 arm 이 yield 0" 또는 "모든 arm 이 yield 1" 인 타겟만 정보가 없다.
    # 확산이 0 이면 무조건 제외하는 것이 아니다 - 예컨대 모든 arm 이 0.5 면
    # 확산은 0 이지만 어디에 배분하든 결과가 같지는 않다.
    informative, uninformative_reason = {}, {}
    for t, bbs in cohort.items():
        ys = [statistics.mean(v) for v in bbs.values()]
        if len(bbs) < 2:
            uninformative_reason[t] = "arm 1 개"
        elif all(y == 0.0 for y in ys):
            uninformative_reason[t] = "모든 arm yield 0"
        elif all(y == 1.0 for y in ys):
            uninformative_reason[t] = "모든 arm yield 1"
        else:
            informative[t] = bbs
    print(f"정보 있는 타겟(백본 간 yield 차이 있음) {len(informative)}/{len(cohort)}")
    for t in sorted(informative, key=lambda t: -(max(statistics.mean(v) for v in informative[t].values())
                                                 - min(statistics.mean(v) for v in informative[t].values()))):
        ys = sorted(statistics.mean(v) for v in informative[t].values())
        print(f"  {t:10s} 확산 {ys[-1]-ys[0]:.3f} · {[f'{y:.2f}' for y in ys]}")
    if len(informative) < MIN_INFORMATIVE_CLUSTERS:
        print(f"\n판정 거부: 정보 있는 클러스터 {len(informative)} < "
              f"{MIN_INFORMATIVE_CLUSTERS}. 이 코호트로는 배분 정책을 구별할 수 없다.")
        return 2

    max_k = max(len(v) for v in informative.values())
    policies = ["adaptive"] + [f"static_k{k}" for k in range(1, max_k + 1)] + ["oracle"]
    results: dict = {}
    traces: dict[str, dict[str, list[list[bool]]]] = {p: {} for p in policies}
    for budget in budgets:
        per_policy: dict[str, dict[str, list[float]]] = {p: {} for p in policies}
        extra = collections.defaultdict(list)
        keep_traces = budget == max(budgets)
        for t, bbs in sorted(informative.items()):
            avail = sum(len(v) for v in bbs.values())
            for p in policies:
                per_policy[p][t] = []
            for rep in range(args.replicates):
                # str 의 tuple 해시는 프로세스마다 달라진다 (PYTHONHASHSEED).
                # 재현 가능한 씨앗이어야 하므로 결정적 해시를 쓴다.
                rng = random.Random(zlib.crc32(
                    f"{args.seed}|{t}|{budget}|{rep}".encode()))
                b = min(budget, avail)
                a = run_adaptive(t, bbs, b, random.Random(rng.randrange(1 << 30)))
                per_policy["adaptive"][t].append(a["found"])
                if keep_traces:
                    traces["adaptive"].setdefault(t, []).append(a["trace"])
                extra["spent_adaptive"].append(a["spent"])
                extra["concentration"].append(a["concentration"])
                extra["n_abandoned"].append(a["n_abandoned"])
                for k in range(1, max_k + 1):
                    st = run_static(t, bbs, b, k, random.Random(rng.randrange(1 << 30)))
                    per_policy[f"static_k{k}"][t].append(st["found"])
                    if keep_traces:
                        traces[f"static_k{k}"].setdefault(t, []).append(st["trace"])
                o = run_oracle(t, bbs, b, random.Random(rng.randrange(1 << 30)))
                per_policy["oracle"][t].append(o["found"])
                if keep_traces:
                    traces["oracle"].setdefault(t, []).append(o["trace"])

        row = {}
        for p in policies:
            vals = [v for t in per_policy[p] for v in per_policy[p][t]]
            lo, hi = clustered_ci(per_policy[p], iters=args.bootstrap, seed=args.seed)
            row[p] = {"mean_found": round(statistics.mean(vals), 3),
                      "ci95": [round(lo, 3), round(hi, 3)]}
        # 적응 - 정적 차이도 타겟 클러스터 부트스트랩으로 낸다. 정책끼리
        # 같은 타겟·같은 복제에서 짝지어 있으므로 차이를 짝지어 계산한다.
        for k in range(1, max_k + 1):
            diff = {t: [a - s for a, s in zip(per_policy["adaptive"][t],
                                              per_policy[f"static_k{k}"][t])]
                    for t in per_policy["adaptive"]}
            lo, hi = clustered_ci(diff, iters=args.bootstrap, seed=args.seed)
            vals = [v for t in diff for v in diff[t]]
            row[f"delta_vs_static_k{k}"] = {
                "mean": round(statistics.mean(vals), 3),
                "ci95": [round(lo, 3), round(hi, 3)],
                "excludes_zero": bool(lo > 0 or hi < 0)}
        row["adaptive_spent_mean"] = round(statistics.mean(extra["spent_adaptive"]), 2)
        row["adaptive_concentration_mean"] = round(statistics.mean(extra["concentration"]), 3)
        row["adaptive_abandoned_mean"] = round(statistics.mean(extra["n_abandoned"]), 3)
        results[str(budget)] = row
        # 동결 spec: static_topk 의 k 는 사후 최적값으로 고른다. 대조군에 주는
        # 이점이므로 우리 주장에는 보수적이다. 그 k 를 주 대조군으로 기록한다.
        best_static = max((row[f"static_k{k}"]["mean_found"], k) for k in range(1, max_k + 1))
        row["posthoc_best_static_k"] = best_static[1]
        row["primary_comparison"] = row[f"delta_vs_static_k{best_static[1]}"]
        print(f"\n예산 {budget}: 적응 {row['adaptive']['mean_found']} · "
              f"최고 정적 k{best_static[1]} {best_static[0]} · "
              f"oracle {row['oracle']['mean_found']}")
        for k in range(1, max_k + 1):
            d = row[f"delta_vs_static_k{k}"]
            mark = "*" if d["excludes_zero"] else " "
            print(f"   {mark} vs static_k{k}: {d['mean']:+.3f} "
                  f"[{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]")

    # 두 번째 엔드포인트: 검증 설계 N 개를 내놓는 데 계산이 얼마나 드는가.
    # 제품에서 실제로 묻는 질문이 이쪽이다 - "예산 40 으로 몇 개?" 보다
    # "10 개 받으려면 얼마?" 가 사용자의 질문이다.
    #
    # 도달한 재생만의 평균끼리 비교하면 안 된다. 도달률이 정책마다 다르므로
    # (N=5 에서 적응 96% vs 균등 83%) 못 채운 재생이 평균에서 빠지고, 더 자주
    # 실패하는 정책이 살아남은 재생만으로 더 좋아 보인다 - 생존 편향이다.
    # 재생은 (타겟, 복제) 로 짝지어져 있으므로, 둘 다 도달한 짝에서만 차이를 낸다.
    cap = max(budgets)
    cost_to = {}
    for n_want in (5, 10, 15, 20):
        row = {}
        for pol in policies:
            reached = total = 0
            for t, reps in traces[pol].items():
                for tr in reps:
                    total += 1
                    reached += calls_to(tr, n_want) is not None
            row[pol] = {"reach_rate": round(reached / total, 4) if total else None}
        for k in range(1, max_k + 1):
            paired: dict[str, list[float]] = {}
            n_pairs = 0
            for t in traces["adaptive"]:
                vals = []
                for ta, ts in zip(traces["adaptive"][t], traces[f"static_k{k}"][t]):
                    ca, cs = calls_to(ta, n_want), calls_to(ts, n_want)
                    if ca is not None and cs is not None:
                        vals.append(ca - cs); n_pairs += 1
                if vals:
                    paired[t] = vals
            if not paired:
                row[f"delta_calls_vs_static_k{k}"] = {"n_pairs": 0}
                continue
            lo, hi = clustered_ci(paired, iters=args.bootstrap, seed=args.seed)
            allv = [v for t in paired for v in paired[t]]
            row[f"delta_calls_vs_static_k{k}"] = {
                "mean": round(statistics.mean(allv), 3),
                "ci95": [round(lo, 3), round(hi, 3)],
                "excludes_zero": bool(lo > 0 or hi < 0),
                "n_pairs": n_pairs,
                "sign": "음수면 적응이 더 적은 호출로 N 개를 채웠다"}
        cost_to[str(n_want)] = row
    print(f"\n=== 구조 성공 N 개까지의 호출 수 · 둘 다 도달한 짝만 (예산 상한 {cap}) ===")
    for n_want, row in cost_to.items():
        rates = " ".join(f"k{k}={row[f'static_k{k}']['reach_rate']:.0%}"
                         for k in range(1, max_k + 1))
        print(f"  N={n_want:2s} 도달률: 적응={row['adaptive']['reach_rate']:.0%} {rates}")
        for k in range(1, max_k + 1):
            d = row[f"delta_calls_vs_static_k{k}"]
            if not d.get("n_pairs"):
                continue
            mark = "*" if d["excludes_zero"] else " "
            print(f"     {mark} vs static_k{k}: {d['mean']:+.2f} 호출 "
                  f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}] (짝 {d['n_pairs']})")

    out = {
        "purpose": "전향 홀드아웃에서 적응 배분을 같은 예산의 정적 배분과 비교",
        "cohort": "rfd3_only" if not args.include_native else "rfd3_plus_native",
        "grid": str(GRID_CSV.relative_to(PROJECT_ROOT)),
        "endpoint_label": args.label,
        "label": (f"pLDDT >= {PLDDT_MIN} and rmsd_nonloop_order <= {RMSD_MAX}"
                  + (f" and soluprot >= {SOLUPROT_MIN}" if args.label == "joint" else "")),
        "label_role": ("동결 spec 의 primary endpoint" if args.label == "joint"
                       else "동결 spec 의 secondary endpoint (structural-pass)"),
        "frozen_spec": "public_data/benchmark/gate0/holdout_experiment_spec.json",
        "informative_rule": "모든 arm 이 yield 0 이거나 모든 arm 이 yield 1 인 타겟만 "
                            "정보가 없다 (동결 spec 의 규칙)",
        "uninformative_targets": uninformative_reason,
        "n_targets": len(cohort),
        "n_informative_targets": len(informative),
        "min_informative_clusters": MIN_INFORMATIVE_CLUSTERS,
        "dropped": dropped,
        "replicates": args.replicates,
        "bootstrap_iters": args.bootstrap,
        "seed": args.seed,
        "endpoint": "예산 안에서 찾은 구조 성공 설계 수 (많을수록 좋다)",
        "results_by_budget": results,
        "secondary_endpoint": "구조 성공 N 개를 채우는 데 든 AF2 호출 수 (적을수록 좋다)",
        "cost_to_n_successes": cost_to,
        "validates": "Gate 1B 의 백본 배분 축 (어느 백본에 다음 계산을 쓸 것인가)",
        "does_not_validate": [
            "생성 조건 탐색 축 - 격자는 단일 조건(T=0.1)이므로 조건-탐색 항과 "
            "다양성 항이 비활성이다. 그 축은 패널 2 온도 스윕이 담당한다.",
            "정책이 실시간으로 새 서열을 만드는 온라인 실행 - 이것은 전향으로 "
            "생성된 격자를 비복원 재생한 것이다. 관측 밖으로 나가지 않는다.",
        ],
        "policy_information": "Gate 0 사전분포와 자기 probe 관측만. 참 yield 주입 없음.",
        "bias_direction": [
            "적응 정책만 백본별 최소 probe 비용을 예산에서 지불한다. 정적 배분에는 "
            "그 비용이 없으므로 비교는 적응에 불리하다.",
            "정적 대조군의 k 를 사후 최적값으로 고른다 (동결 spec). 실제 사용자는 "
            "그 k 를 미리 알 수 없으므로, 이것도 대조군에 유리한 쪽이다.",
        ],
        "replay_limit": "각 백본에 관측이 24 개뿐이다. 적응 정책이 한 백본에 집중해 "
                        "24 개를 다 쓰면 실제 제품에서는 서열을 더 생성할 수 있지만 "
                        "재생에서는 다른 백본으로 옮겨야 한다. 이는 적응 정책의 "
                        "이점을 과대평가하지 않고 축소하는 방향이다.",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
