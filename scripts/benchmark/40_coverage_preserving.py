#!/usr/bin/env python3
"""Coverage-preserving 배분을 그 자신의 종점(EFBC)으로 평가한다.

규칙은 `docs/specs/coverage-preserving-prespec.md` 에 결과 확인 전 동결돼
있다. 여기서 그 문서에 없는 선택을 새로 하지 않는다.

앞선 분석(`35_`, `37_`)은 **수확을 목적함수로 둔** 탐욕 배분을 시험해 이득을
찾지 못했다. 정본 v2.0 정책은 수확을 목적함수로 삼지 않는다 - coverage 를
최적화하고 수확은 acceptance guardrail 로만 쓴다. 그래서 앞선 결과는 v2.0 에
대한 판정이 아니고, 이 스크립트가 정본 정책을 제 종점으로 잰다.

    주 종점    공통 최대 계산 예산 상한 B 안에서 달성한 terminal EFBC
    EFBC(f)    exp(-sum p_b log p_b),  p_b = f_b / sum f,  EFBC(0)=0
    acquisition A_b = q_b * [EFBC(f + e_b) - EFBC(f)]   one-step myopic
    STOP       max_b A_b <= 0.  local saturation 으로만 기술한다.
    가드레일   structural-yield 비율의 단측 95% 하한 >= 0.90

새 folding 을 하지 않는다. 34 표적 전수 격자를 오프라인 재생할 뿐이다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

#: 사전지정 §2-§3, §7. 바꾸지 않는다.
PLDDT_MIN, RMSD_MAX, SOLUPROT_MIN = 85.0, 2.0, 0.5
WARMUP_PER_BB, KAPPA_POOL = 4, 4.0
BUDGETS, PRIMARY_B = (42, 84, 126, 168), 126
SEEDS = [42, 123, 7, 2024, 31337]
N_BOOTSTRAP, BOOT_SEED = 2000, 20260921
GUARDRAIL_LCB = 0.90
POLICIES = ("coverage_v2", "static_equal", "greedy_fill", "static_equal_matched")


# ------------------------------------------------------------------ EFBC

def efbc(f) -> float:
    """exp(-sum p log p). 전부 0 이면 0 (사전지정 §2)."""
    tot = sum(f)
    if tot <= 0:
        return 0.0
    h = 0.0
    for v in f:
        if v > 0:
            p = v / tot
            h -= p * math.log(p)
    return math.exp(h)


# ------------------------------------------------------------------ 입력

def load(cohort_dir: Path):
    """표적 -> 백본 -> 후보(joint / structural 라벨). 격자 한 곳만 읽는다."""
    cand = {c["sequence_id"]: c
            for c in json.loads((cohort_dir / "candidates.json").read_text("utf-8"))}
    tgts: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    n_ok = 0
    for r in csv.DictReader((cohort_dir / "af2_order_metric.csv").open(encoding="utf-8")):
        #: refused / missing / technical failed 는 Bernoulli 실패로 바꾸지
        #: 않는다 (사전지정 §3.1 상태 계약). 관측 자체에서 뺀다.
        if r.get("status") != "ok":
            continue
        c = cand.get(r["sequence_id"])
        if not c:
            continue
        try:
            pl, rm, so = (float(r["plddt"]), float(r["rmsd_nonloop_order"]),
                          float(r["soluprot"]))
        except (TypeError, ValueError, KeyError):
            continue
        struct = pl >= PLDDT_MIN and rm <= RMSD_MAX
        tgts[c["target_id"]][c["backbone_key"]].append(
            {"joint": float(struct and so >= SOLUPROT_MIN),
             "struct": float(struct)})
        n_ok += 1
    out = {t: {b: v for b, v in sorted(bbs.items())} for t, bbs in sorted(tgts.items())}
    depth = [len(v) for bbs in out.values() for v in bbs.values()]
    print(f"표적 {len(out)} · 백본 {sum(len(b) for b in out.values())} · 후보 {n_ok} "
          f"· 백본당 깊이 중앙 {int(statistics.median(depth)) if depth else 0}", flush=True)
    return out


# ------------------------------------------------------------- 정책 재생

def _posterior(succ, n, tot_s, tot_n):
    """표적 수준 부분 풀링. Gate 0 사전분포는 쓰지 않는다 (사전지정 §3.2)."""
    if tot_n <= 0:                                   # 표적 사후가 아직 없다
        a0 = b0 = 1.0                                # 균등 Beta(1,1)
    else:
        p_t = tot_s / tot_n
        a0, b0 = p_t * KAPPA_POOL, (1.0 - p_t) * KAPPA_POOL
    a, b = a0 + succ, b0 + (n - succ)
    return a / (a + b) if (a + b) > 0 else 0.0


def replay(bbs: dict, B: int, seed: int, policy: str, cap_calls: int | None = None):
    """한 표적에서 한 정책을 B 회 상한 안에서 재생한다.

    모든 정책이 같은 후보 순열을 공유한다. 정책 간 차이는 **어느 백본을 언제
    부르는가** 뿐이고 같은 백본의 k 번째 호출은 어느 정책에서나 같은 후보다.
    """
    keys = list(bbs)
    rng = np.random.default_rng((seed * 1_000_003) ^ 0xC0FFEE)
    order = {b: list(rng.permutation(len(bbs[b]))) for b in keys}
    limit = B if cap_calls is None else min(B, cap_calls)

    used = {b: 0 for b in keys}                      # 이 백본에서 쓴 호출 수
    succ = {b: 0 for b in keys}                      # joint-pass 수 = f_b
    n_struct = 0
    calls = 0
    stopped = False

    def draw(b):
        nonlocal calls, n_struct
        rec = bbs[b][order[b][used[b]]]
        used[b] += 1
        calls += 1
        succ[b] += int(rec["joint"])
        n_struct += int(rec["struct"])

    def avail(b):
        return used[b] < len(bbs[b])

    if policy == "static_equal" or policy == "static_equal_matched":
        #: 최대잔여 균등 배분. 풀이 모자라면 그만큼만 준다.
        while calls < limit and any(avail(b) for b in keys):
            live = [b for b in keys if avail(b)]
            for b in live:
                if calls >= limit:
                    break
                draw(b)
        return _pack(succ, keys, calls, n_struct, stopped)

    #: warm-up: 백본당 최소 probe 4. 이 구간에서 STOP 을 허용하지 않는다.
    for _ in range(WARMUP_PER_BB):
        for b in keys:
            if calls >= limit:
                break
            if avail(b):
                draw(b)
        if calls >= limit:
            break

    while calls < limit:
        live = [b for b in keys if avail(b)]
        if not live:
            break
        tot_s, tot_n = sum(succ.values()), sum(used.values())
        f = [succ[b] for b in keys]
        cur = efbc(f)
        if policy == "greedy_fill":
            #: 수확 목적: A_b = q_b. 앞선 분석의 greedy_fill 과 같이 STOP 규칙을
            #: 두지 않는다 - STOP 은 EFBC 목적의 local saturation 개념이고
            #: 여기에 얹으면 두 비교군이 목적함수 말고도 달라진다.
            best = max(live, key=lambda b: (_posterior(succ[b], used[b], tot_s, tot_n),
                                            -keys.index(b)))
            draw(best)
            continue

        best, best_a = None, 0.0
        for b in live:
            j = keys.index(b)
            a = (_posterior(succ[b], used[b], tot_s, tot_n)
                 * (efbc(f[:j] + [f[j] + 1] + f[j + 1:]) - cur))
            if a > best_a + 1e-12:
                best, best_a = b, a
        if best is None:                             # max_b A_b <= 0
            stopped = True
            break
        draw(best)
    return _pack(succ, keys, calls, n_struct, stopped)


def _pack(succ, keys, calls, n_struct, stopped):
    f = [succ[b] for b in keys]
    return {"efbc": efbc(f), "joint": float(sum(f)), "struct": float(n_struct),
            "calls": float(calls), "stopped": float(stopped),
            "n_backbones_hit": float(sum(1 for v in f if v > 0)),
            #: `keys` 순서의 백본별 joint-pass 수. 41_ 의 구조 진단이 쓴다.
            "_f": f}


# ---------------------------------------------------------------- 집계

METRICS = ("efbc", "joint", "struct", "calls", "stopped", "n_backbones_hit")


def run(tgts: dict, label: str):
    per_target: dict = {}
    for t, bbs in tgts.items():
        if not bbs:
            continue
        d = {}
        for B in BUDGETS:
            acc = {p: collections.defaultdict(list) for p in POLICIES}
            for s in SEEDS:
                v2 = replay(bbs, B, s, "coverage_v2")
                runs = {"coverage_v2": v2,
                        "static_equal": replay(bbs, B, s, "static_equal"),
                        "greedy_fill": replay(bbs, B, s, "greedy_fill"),
                        #: 민감도: v2 가 STOP 해 덜 쓴 만큼만 균등에 준다
                        "static_equal_matched": replay(bbs, B, s, "static_equal",
                                                       cap_calls=int(v2["calls"]))}
                for p, r in runs.items():
                    for m in METRICS:
                        acc[p][m].append(r[m])
            d[str(B)] = {p: {m: statistics.mean(acc[p][m]) for m in METRICS}
                         for p in POLICIES}
        per_target[t] = {"n_backbones": len(bbs),
                         "pool": sum(len(v) for v in bbs.values()),
                         "joint_rate": statistics.mean(
                             c["joint"] for v in bbs.values() for c in v),
                         "by_budget": d}

    names = sorted(per_target)
    rng = np.random.default_rng(BOOT_SEED)
    boots = [[names[int(rng.integers(len(names)))] for _ in names]
             for _ in range(N_BOOTSTRAP)]
    out = {"label": label, "n_targets": len(names), "targets": names,
           "per_target": per_target, "by_budget": {}}

    def mean(ts, B, p, m):
        return statistics.mean(per_target[t]["by_budget"][str(B)][p][m] for t in ts)

    for B in BUDGETS:
        e = {"point": {p: {m: mean(names, B, p, m) for m in METRICS}
                       for p in POLICIES},
             "contrasts": {}, "guardrail": {}}
        for comp in ("static_equal", "greedy_fill", "static_equal_matched"):
            role = "주 비교군" if comp == "static_equal" else (
                "민감도" if comp.endswith("matched") else "보조 비교군")
            dr = sorted(mean(b, B, "coverage_v2", "efbc") - mean(b, B, comp, "efbc")
                        for b in boots)
            lo, hi = dr[int(.025 * len(dr))], dr[int(.975 * len(dr))]
            e["contrasts"][f"coverage_v2 - {comp}"] = {
                "role": role,
                "delta": mean(names, B, "coverage_v2", "efbc") - mean(names, B, comp, "efbc"),
                "ci95": [lo, hi], "excludes_zero": bool(lo > 0 or hi < 0),
                "primary": comp == "static_equal"}

        #: 가드레일 §5. 정책 목적함수(EFBC)와 채택 판정(수확)을 분리한다.
        for comp in ("static_equal", "static_equal_matched"):
            rr = []
            for b in boots:
                den = mean(b, B, comp, "struct")
                rr.append(mean(b, B, "coverage_v2", "struct") / den if den > 0 else float("nan"))
            rr = sorted(x for x in rr if not math.isnan(x))
            den = mean(names, B, comp, "struct")
            lcb = rr[int(.05 * len(rr))] if rr else float("nan")
            e["guardrail"][f"structural_yield_ratio_vs_{comp}"] = {
                "ratio": (mean(names, B, "coverage_v2", "struct") / den) if den > 0 else None,
                "lcb95_onesided": lcb, "threshold": GUARDRAIL_LCB,
                "pass": bool(lcb >= GUARDRAIL_LCB)}
        out["by_budget"][str(B)] = e
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=str(BASE / "hier_confirmatory"))
    ap.add_argument("--label", default="hier_confirmatory_34")
    ap.add_argument("--out", default=str(BASE / "coverage_preserving.json"))
    a = ap.parse_args(argv)

    res = run(load(Path(a.cohort)), a.label)
    doc = {"purpose": ("coverage-preserving 배분을 EFBC 종점으로 평가한다. "
                       "새 folding 없음."),
           "prespec": "docs/specs/coverage-preserving-prespec.md",
           "primary_endpoint": "공통 최대 계산 예산 상한 B 안에서 달성한 terminal EFBC",
           "primary_budget": PRIMARY_B, "warmup_per_backbone": WARMUP_PER_BB,
           "kappa_pool": KAPPA_POOL, "seeds": SEEDS,
           "bootstrap": {"n": N_BOOTSTRAP, "seed": BOOT_SEED, "unit": "target"},
           "result": res}

    print(f"\n=== {res['label']} · 표적 {res['n_targets']}")
    for B in BUDGETS:
        e = res["by_budget"][str(B)]
        star = " ★" if B == PRIMARY_B else ""
        print(f"\n  B={B:3d}{star}")
        for p in POLICIES:
            v = e["point"][p]
            print(f"      {p:22s} EFBC {v['efbc']:5.2f} · joint {v['joint']:6.2f} "
                  f"· struct {v['struct']:6.2f} · 호출 {v['calls']:6.1f} "
                  f"· STOP {v['stopped']:.2f}")
        for k, c in e["contrasts"].items():
            print(f"      {k:40s} {c['delta']:+6.3f} "
                  f"[{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}] "
                  f"{'0 제외' if c['excludes_zero'] else '0 포함'} ({c['role']})")
        for k, g in e["guardrail"].items():
            print(f"      {k:40s} {g['ratio']:.3f} LCB {g['lcb95_onesided']:.3f} "
                  f"{'통과' if g['pass'] else '미통과'}")
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"\n{a.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
