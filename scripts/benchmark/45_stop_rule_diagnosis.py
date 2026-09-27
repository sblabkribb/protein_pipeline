#!/usr/bin/env python3
"""coverage 정책의 STOP 규칙은 정책이 목표 상태에 도달하는 순간 발동한다.

**이것은 동결된 판정이 아니다.** `coverage-preserving-prespec.md` 의 주 종점은
`40_` 이 내고 이 파일은 그 결과가 왜 그렇게 나오는지를 설명하는 진단이다.
여기서 나온 수치로 §3.4 를 고치지 않으며 주 판정을 바꾸지 않는다.

주장 1 — 해석적. 자료가 필요 없다.
-----------------------------------
백본 k 개의 feasible mass 가 균등하면 f = (n, n, ..., n) 이고

    EFBC(f) = exp(log k) = k

어느 한 곳에 1 을 더하면 p 가 균등에서 멀어지므로 엔트로피가 **엄격히**
줄고 EFBC(f + e_b) < k 다. 따라서

    EFBC(f + e_b) - EFBC(f) < 0   모든 b 에 대해
    A_b = q_b * (음수) <= 0       q_b >= 0 이므로
    => max_b A_b <= 0             => STOP

즉 one-step myopic EFBC 정책은 **자기 목적함수의 최적점에서 스스로 멈춘다.**
이 명제는 관측을 하나도 쓰지 않는다. 아래 `analytic_check` 가 k·n 격자에서
부호를 직접 확인한다.

주장 2 — 그 상태에 얼마나 자주 닿는가. 이건 자료가 답한다.
주장 3 — 멈춘 대가는 무엇인가 (탐색적 반사실).
-----------------------------------------------------------
STOP 을 끈 판을 같은 격자에서 재생한다. **가드레일이 실패한 것을 본 뒤에
돌린 것이므로 확증 주장으로 쓰지 않는다.** 보고할 때 탐색적이라고 적는다.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"


def _m40():
    s = importlib.util.spec_from_file_location(
        "m40", HERE / "40_coverage_preserving.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def analytic_check(m40) -> dict:
    """균등 f 에서 한계 EFBC 이득의 부호를 직접 센다. 관측을 쓰지 않는다."""
    worst, rows = -1e18, []
    for k in range(2, 13):
        for n in range(1, 41):
            f = [n] * k
            g = m40.efbc(f[:-1] + [n + 1]) - m40.efbc(f)
            worst = max(worst, g)
            if n in (1, 4, 40):
                rows.append({"k": k, "n": n, "efbc": m40.efbc(f), "gain": g})
    return {"claim": ("균등 f 에서는 모든 b 에 대해 EFBC(f+e_b) - EFBC(f) < 0 "
                      "이고 q_b >= 0 이므로 max_b A_b <= 0 - 즉 STOP 이다."),
            "grid": "k = 2..12, n = 1..40",
            "max_gain_over_grid": worst,
            "holds_everywhere": bool(worst < 0), "samples": rows}


def replay_nostop(m40, bbs, B, seed):
    """`40_.replay` 의 coverage_v2 에서 STOP 조건만 뺀 판.

    동결 스크립트를 건드리지 않으려고 여기 따로 둔다. 나머지 규칙 - warm-up
    4, 부분 풀링 kappa=4.0, 같은 후보 순열 - 은 모두 같다.
    """
    keys = list(bbs)
    rng = np.random.default_rng((seed * 1_000_003) ^ 0xC0FFEE)
    order = {b: list(rng.permutation(len(bbs[b]))) for b in keys}
    used = {b: 0 for b in keys}
    succ = {b: 0 for b in keys}
    n_struct = calls = 0

    def draw(b):
        nonlocal calls, n_struct
        rec = bbs[b][order[b][used[b]]]
        used[b] += 1
        calls += 1
        succ[b] += int(rec["joint"])
        n_struct += int(rec["struct"])

    for _ in range(m40.WARMUP_PER_BB):
        for b in keys:
            if calls < B and used[b] < len(bbs[b]):
                draw(b)
    while calls < B:
        live = [b for b in keys if used[b] < len(bbs[b])]
        if not live:
            break
        tot_s, tot_n = sum(succ.values()), sum(used.values())
        f = [succ[b] for b in keys]
        cur = m40.efbc(f)
        #: 부호를 보지 않고 **가장 덜 나쁜** action 을 고른다. 이것이 유일한 차이다.
        best = max(live, key=lambda b: (
            m40._posterior(succ[b], used[b], tot_s, tot_n)
            * (m40.efbc(f[:keys.index(b)] + [f[keys.index(b)] + 1]
                        + f[keys.index(b) + 1:]) - cur), -keys.index(b)))
        draw(best)
    f = [succ[b] for b in keys]
    return {"efbc": m40.efbc(f), "joint": float(sum(f)), "struct": float(n_struct),
            "calls": float(calls)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=str(BASE / "hier_confirmatory"))
    ap.add_argument("--label", default="hier_confirmatory_34")
    ap.add_argument("--out", default=str(BASE / "stop_rule_diagnosis.json"))
    a = ap.parse_args(argv)

    m40 = _m40()
    tgts = m40.load(Path(a.cohort))
    ana = analytic_check(m40)
    print(f"\n주장 1 (해석적) · {ana['grid']} · 최대 이득 "
          f"{ana['max_gain_over_grid']:+.3e} · 모든 격자점에서 성립 "
          f"{ana['holds_everywhere']}")

    per_target, shapes, n_stop, n_run = {}, [], 0, 0
    for t, bbs in tgts.items():
        acc = collections.defaultdict(list)
        for B in m40.BUDGETS:
            for s in m40.SEEDS:
                v2 = m40.replay(bbs, B, s, "coverage_v2")
                eq = m40.replay(bbs, B, s, "static_equal")
                ns = replay_nostop(m40, bbs, B, s)
                if B == m40.PRIMARY_B:
                    n_run += 1
                    n_stop += int(v2["stopped"])
                    nz = [x for x in v2["_f"] if x > 0]
                    if v2["stopped"] and len(nz) > 1:
                        shapes.append(max(nz) / min(nz))
                for tag, r in (("v2", v2), ("nostop", ns), ("equal", eq)):
                    for m in ("efbc", "joint", "struct", "calls"):
                        acc[f"{tag}_{m}|{B}"].append(r[m])
        per_target[t] = {k: statistics.mean(v) for k, v in acc.items()}

    names = sorted(per_target)
    rng = np.random.default_rng(m40.BOOT_SEED)
    boots = [[names[int(rng.integers(len(names)))] for _ in names]
             for _ in range(m40.N_BOOTSTRAP)]

    def mean(ts, k):
        return statistics.mean(per_target[t][k] for t in ts)

    reached = {"n_runs": n_run, "n_stopped": n_stop,
               "stop_rate": n_stop / n_run if n_run else None,
               "budget": m40.PRIMARY_B,
               "max_over_min_f_at_stop": {
                   "median": statistics.median(shapes) if shapes else None,
                   "share_exactly_uniform":
                       sum(1 for x in shapes if abs(x - 1.0) < 1e-9) / len(shapes)
                       if shapes else None,
                   "n": len(shapes)}}
    print(f"\n주장 2 (자료) · B={m40.PRIMARY_B} · STOP "
          f"{n_stop}/{n_run} ({reached['stop_rate']:.0%}) · STOP 시점 f 의 "
          f"최대/최소 중앙 {reached['max_over_min_f_at_stop']['median']:.2f} · "
          f"완전 균등 비율 "
          f"{reached['max_over_min_f_at_stop']['share_exactly_uniform']:.0%}")

    cf = {}
    print(f"\n주장 3 (탐색적 반사실 · 확증 주장 아님)")
    for B in m40.BUDGETS:
        def ci(fn):
            dr = sorted(fn(b) for b in boots)
            return [dr[int(.025 * len(dr))], dr[int(.975 * len(dr))]]

        e = {m: {tag: mean(names, f"{tag}_{m}|{B}")
                 for tag in ("v2", "nostop", "equal")}
             for m in ("efbc", "joint", "struct", "calls")}
        d_efbc = mean(names, f"nostop_efbc|{B}") - mean(names, f"v2_efbc|{B}")
        c_efbc = ci(lambda b: mean(b, f"nostop_efbc|{B}") - mean(b, f"v2_efbc|{B}"))
        rr = sorted(mean(b, f"nostop_struct|{B}") / mean(b, f"equal_struct|{B}")
                    for b in boots if mean(b, f"equal_struct|{B}") > 0)
        lcb = rr[int(.05 * len(rr))] if rr else float("nan")
        ratio = e["struct"]["nostop"] / e["struct"]["equal"] if e["struct"]["equal"] else float("nan")
        v2_ratio = e["struct"]["v2"] / e["struct"]["equal"] if e["struct"]["equal"] else float("nan")
        cf[str(B)] = {"point": e, "efbc_nostop_minus_v2": {"delta": d_efbc, "ci95": c_efbc},
                      "guardrail_v2": v2_ratio, "guardrail_nostop": ratio,
                      "guardrail_nostop_lcb95": lcb,
                      "threshold": m40.GUARDRAIL_LCB}
        star = " ★" if B == m40.PRIMARY_B else ""
        print(f"  B={B:3d}{star}")
        print(f"      v2 (STOP 유지)  EFBC {e['efbc']['v2']:5.2f} · struct "
              f"{e['struct']['v2']:6.2f} · 호출 {e['calls']['v2']:6.1f} "
              f"· 가드레일 {v2_ratio:.3f}")
        print(f"      v2 (STOP 제거)  EFBC {e['efbc']['nostop']:5.2f} · struct "
              f"{e['struct']['nostop']:6.2f} · 호출 {e['calls']['nostop']:6.1f} "
              f"· 가드레일 {ratio:.3f} (LCB {lcb:.3f})")
        print(f"      EFBC 차이 (제거 - 유지) {d_efbc:+.3f} "
              f"[{c_efbc[0]:+.3f},{c_efbc[1]:+.3f}]")

    doc = {"purpose": ("coverage 정책의 STOP 규칙이 정책의 목표 상태에서 발동함을 "
                       "보인다. 주 판정을 바꾸지 않는다."),
           "status": ("진단. 주장 1 은 해석적이라 자료와 무관하다. 주장 3 은 "
                      "가드레일 실패를 본 뒤 돌린 반사실이므로 탐색적이다."),
           "related_prespec": "docs/specs/coverage-preserving-prespec.md",
           "label": a.label, "n_targets": len(names),
           "analytic": ana, "reached": reached, "counterfactual": cf,
           "per_target": per_target}
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"\n{a.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
