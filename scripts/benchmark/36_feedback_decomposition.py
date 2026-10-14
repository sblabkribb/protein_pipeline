#!/usr/bin/env python3
"""`adaptive_sentinel` 의 이득이 되먹임 때문인지 배분 방식 때문인지 가른다.

**사후 진단이다. 판정이 아니다.** `35_` 의 결과를 본 뒤에 추가했고, 동결된
주 비교(`warmup_informed - rf_only`)를 바꾸지 않는다.

왜 필요한가
-----------
`35_` 에서 `adaptive_sentinel` 이 non-oracle 중 가장 높았다(여지의 62.4%).
그런데 이 arm 은 `warmup_informed` 와 **세 가지가 동시에** 다르다.

    1. posterior 가 갱신된다                      (되먹임)
    2. 배분이 Thompson 그리디다 (비례 배분이 아니라)  (배분 방식)
    3. 호출의 25% 가 무작위 선택이다 (RF 가 아니라)   (탐색 비용)

셋을 한꺼번에 바꿔 놓고 "되먹임이 효과다" 라고 하면 식별되지 않는다. 사다리로
하나씩 올려서 각 단계의 몫을 본다.

    warmup_informed        비례 · 고정 · 전부 RF
    greedy_frozen          그리디 · 고정 · 전부 RF      <- 배분 방식의 몫
    greedy_frozen_explore  그리디 · 고정 · 탐색 25%     <- 탐색 비용
    adaptive_sentinel      그리디 · 갱신 · 탐색 25%     <- 되먹임의 몫

`adaptive_sentinel - greedy_frozen_explore` 가 되먹임의 순수 몫이다. 나머지
두 차이는 되먹임과 무관하다.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))
OUT = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "feedback_decomposition.json"


def _mod(p, n):
    s = importlib.util.spec_from_file_location(n, HERE / p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


m35 = _mod("35_hierarchical_replay.py", "m35")
LADDER = ["warmup_informed", "greedy_frozen", "greedy_frozen_explore",
          "adaptive_sentinel"]


def replay(y, X, m, bb_of, B, seed, fit_rank):
    """`35_.replay_unit` 과 같은 warm-up·ceiling 규칙. arm 만 다르다."""
    rng = np.random.default_rng(seed)
    bbs = sorted(set(bb_of))
    members = {b: np.flatnonzero(bb_of == b) for b in bbs}
    warm = []
    for b in bbs:
        warm += list(rng.choice(members[b],
                                size=min(m35.SENTINEL_PER_BACKBONE, len(members[b])),
                                replace=False))
    warm = np.array(sorted(warm))
    A = B - len(warm)
    rest = np.setdiff1d(np.arange(len(y)), warm)
    if A < 0 or A > len(rest):
        return None
    base = float(y[warm].sum())
    wset = set(warm.tolist())
    avail = {b: [j for j in members[b] if j not in wset] for b in bbs}
    cap = np.array([min(m35.CEILING_PER_BACKBONE, len(members[b]))
                    - m35.SENTINEL_PER_BACKBONE for b in bbs])
    cap = np.maximum(0, np.minimum(cap, [len(avail[b]) for b in bbs]))

    pred = fit_rank(X, y, warm, rest, seed, estimator="RF")
    rf_order = rest[np.argsort(pred)[::-1]]
    rf_rank = {j: i for i, j in enumerate(rf_order)}
    wa = {b: np.intersect1d(members[b], warm) for b in bbs}
    a0 = np.array([y[wa[b]].sum() + 1.0 for b in bbs])
    b0 = np.array([len(wa[b]) - y[wa[b]].sum() + 1.0 for b in bbs])

    got = {}
    # --- 사다리 0: 비례 배분 · 고정 · 전부 RF  (35_ 와 동일)
    n_b = m35.allocate(a0 / (a0 + b0), A, cap)
    sel = []
    for b, k in zip(bbs, n_b):
        sel += m35.pick(rf_order, avail[b], k) if k > 0 else []
    got["warmup_informed"] = base + float(y[np.array(sel, dtype=int)].sum())

    # --- 사다리 1~3: 그리디 배분. update / explore 만 켜고 끈다.
    for arm, update, explore_frac in (("greedy_frozen", False, 0.0),
                                      ("greedy_frozen_explore", False,
                                       m35.EXPLORE_FRACTION),
                                      ("adaptive_sentinel", True,
                                       m35.EXPLORE_FRACTION)):
        a_s, b_s = a0.copy(), b0.copy()
        used = np.zeros(len(bbs), dtype=int)
        pool = {b: list(avail[b]) for b in bbs}
        sel, trng = [], np.random.default_rng(seed ^ 0x5E)
        step_of_explore = int(round(1 / explore_frac)) if explore_frac else 0
        for step in range(A):
            ok = [i for i in range(len(bbs)) if used[i] < cap[i] and pool[bbs[i]]]
            if not ok:
                break
            i = ok[int(np.argmax(trng.beta(a_s[ok], b_s[ok])))]
            b = bbs[i]
            exp = bool(step_of_explore) and (step % step_of_explore == 0)
            j = int(trng.choice(pool[b])) if exp else min(pool[b],
                                                          key=lambda x: rf_rank[x])
            pool[b].remove(j)
            used[i] += 1
            sel.append(j)
            if exp and update:
                a_s[i] += y[j]
                b_s[i] += 1 - y[j]
        got[arm] = base + float(y[np.array(sel, dtype=int)].sum())
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    rows, emb, mpnn = m35.load("")
    fit_rank = _mod("31_fewshot_jointpass_transfer.py", "m31").fit_rank
    out = {"purpose": ("adaptive_sentinel 의 이득을 배분방식·탐색비용·되먹임으로 "
                       "분해한다. 35_ 결과를 본 뒤 추가한 **사후 진단**이며 "
                       "동결된 주 비교를 바꾸지 않는다."),
           "post_hoc": True, "judgement": False,
           "ladder": LADDER, "sources": {}}

    for source in ("rfd3", "bioemu"):
        by_unit = collections.defaultdict(list)
        for i, r in enumerate(rows):
            if r["cohort"] == m35.COHORT and r["source"] == source:
                by_unit[r["target_id"]].append(i)
        per_unit = {}
        for tgt, idx in sorted(by_unit.items()):
            idx = np.array(idx)
            y = np.array([rows[i]["joint_pass"] for i in idx], dtype=float)
            if y.min() == y.max():
                continue
            X = emb[idx]
            mm = np.array([mpnn[rows[i]["sequence_id"]] for i in idx])
            bb = np.array([rows[i]["backbone_key"] for i in idx])
            runs = [replay(y, X, mm, bb, m35.PRIMARY_BUDGET, s, fit_rank)
                    for s in m35.SEEDS]
            runs = [r for r in runs if r]
            if len(runs) == len(m35.SEEDS):
                per_unit[tgt] = {a: statistics.mean(r[a] for r in runs)
                                 for a in LADDER}
        names = sorted(per_unit)
        rng = np.random.default_rng(m35.BOOT_SEED)
        boots = [[names[int(rng.integers(len(names)))] for _ in names]
                 for _ in range(m35.N_BOOTSTRAP)]

        def agg(ts, a):
            return statistics.mean(per_unit[t][a] for t in ts)

        res = {"n_units": len(names), "budget": m35.PRIMARY_BUDGET,
               "point": {a: agg(names, a) for a in LADDER},
               "per_unit": {t: dict(v) for t, v in sorted(per_unit.items())},
               "steps": {}}
        for lo, hi, what in ((0, 1, "배분 방식 (비례→그리디)"),
                             (1, 2, "탐색 비용 (전부 RF→25% 무작위)"),
                             (2, 3, "**되먹임** (고정→갱신)")):
            a, b = LADDER[hi], LADDER[lo]
            dr = sorted(agg(x, a) - agg(x, b) for x in boots)
            q = lambda p: dr[min(len(dr) - 1, max(0, int(p * len(dr))))]
            res["steps"][f"{a}-{b}"] = {
                "means": what, "delta": agg(names, a) - agg(names, b),
                "ci95": [q(.025), q(.975)],
                "excludes_zero": bool(q(.025) > 0 or q(.975) < 0)}
        #: 보충자료가 인용하는 "그리디 배분 - 서열 순위화" 대비. rf_only 는 35_ 가
        #: 저장한 표적별 값을 그대로 쓴다. 두 파일 모두 커밋되므로 대조할 수 있다.
        rf_only = {}
        replay_path = (PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
                       / "hierarchical_replay.json")
        if replay_path.is_file():
            saved = json.loads(replay_path.read_text("utf-8"))
            for t, v in (saved.get("sources", {}).get(source, {})
                         .get("per_unit", {}).items()):
                got = v.get("by_budget", {}).get(str(m35.PRIMARY_BUDGET), {})
                if "rf_only" in got:
                    rf_only[t] = float(got["rf_only"])
        shared = [t for t in names if t in rf_only]
        if shared:
            def dgap(ts):
                return statistics.mean(per_unit[t]["greedy_frozen"] - rf_only[t]
                                       for t in ts)
            db = sorted(dgap([t for t in x if t in rf_only]) for x in boots
                        if any(t in rf_only for t in x))
            q = lambda p: db[min(len(db) - 1, max(0, int(p * len(db))))]
            res["greedy_frozen-rf_only"] = {
                "n_units": len(shared), "delta": dgap(shared),
                "ci95": [q(.025), q(.975)],
                "per_unit_delta": {t: per_unit[t]["greedy_frozen"] - rf_only[t]
                                   for t in shared}}
        out["sources"][source] = res

    for src, r in out["sources"].items():
        print(f"\n=== {src} confirmatory · B={r['budget']} · {r['n_units']} unit")
        for a in LADDER:
            print(f"    {a:24s} {r['point'][a]:6.2f}")
        print("    " + "-" * 62)
        for k, s in r["steps"].items():
            print(f"    {s['means']:32s} {s['delta']:+.2f} "
                  f"[{s['ci95'][0]:+.2f},{s['ci95'][1]:+.2f}] "
                  f"{'0 제외' if s['excludes_zero'] else '0 포함'}")
    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"\n{args.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
