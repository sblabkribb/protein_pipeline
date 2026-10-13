#!/usr/bin/env python3
"""백본 배분과 서열 순위화를 결합하면 서열 순위화만 쓰는 것보다 나은가.

규칙은 `docs/specs/hierarchical-replay-prespec.md` (v1.1) 에 실행 전 동결돼
있다. 여기서 그 문서에 없는 선택을 새로 하지 않는다.

무엇을 재는가
-------------
연구노트는 **서열 축**만 다룬다. RAPID 에는 백본 축이 하나 더 있다. 같은
warm-up 을 치른 뒤 남은 예산을 백본에 어떻게 나누는가가 수확을 바꾸는지 본다.

    주 비교   warmup_informed - rf_only   (RFD3 confirmatory 8 unit, B=80)

왜 "adaptive" 가 아닌가
-----------------------
RF 가 고른 관측은 위로 편향돼 있다. 그것을 백본 posterior 에 넣으면 되먹임이
생겨 배분 정책의 가치가 아니라 되먹임의 크기를 재게 된다. 그래서 posterior 는
warm-up sentinel 로만 갱신하고, 그 대가로 **warm-up 이후 배분이 고정된다.**
이것은 순차 적응이 아니므로 이름을 `warmup_informed` 로 쓴다. 되먹임이 있는
판은 `adaptive_sentinel` 로 따로 두고 판정하지 않는다 (사전지정 §6.2).

왜 B=80 이 주 분석인가
----------------------
`4ai2A02` 는 백본이 5 개뿐이고 pool 이 90 이라 B=100 에서 빠진다. 그러면 7 unit
이 되어 동결 계획의 `min_clusters = 8` 을 밑돌고, "최소 클러스터 8 을 밑도는 B
는 그 source 에서 판정하지 않는다" 에 걸린다. 그리고 ceiling 18 때문에 집중
여지는 예산이 **클수록 좁아진다** (B=60 7.0x · B=80 3.5x · B=100 2.3x).

하지 않는 것 (동결 계획)
------------------------
- 새 folding 을 하지 않는다. calibration 코호트를 쓰지 않는다.
- **EFBC 를 계산하지 않는다.** coverage 결론을 내지 않는다.
- 생성원을 합치지 않는다. B=40 에서 정책을 비교하지 않는다.
- B=100 을 판정하지 않는다. BioEmu 6 unit 을 판정하지 않는다.
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

V2 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "v2_multisource"
OUT_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
PRESPEC = PROJECT_ROOT / "docs" / "specs" / "hierarchical-replay-prespec.md"

#: 사전지정 §3-§7. 바꾸지 않는다.
COHORT = "confirmatory"
PRIMARY_SOURCE = "rfd3"
PRIMARY_BUDGET = 80
BUDGETS = [60, 80, 100]
SENTINEL_PER_BACKBONE = 4
CEILING_PER_BACKBONE = 18
MIN_CLUSTERS = 8
SEEDS = [42, 123, 7, 2024, 31337]
N_BOOTSTRAP = 2000
BOOT_SEED = 20260921
EXPLORE_FRACTION = 0.25          # adaptive_sentinel 전용 (§6.2)

PRIMARY = ("warmup_informed", "rf_only")
SECONDARY = [("warmup_informed", "backbone_only"),
             ("warmup_informed", "mpnn_only_paid"),
             ("warmup_informed", "equal_random")]
ARMS = ["equal_random", "mpnn_only_paid", "rf_only", "backbone_only",
        "warmup_informed", "adaptive_sentinel", "oracle_paid",
        "mpnn_only_zerolabel"]


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ 입력

def load(esm_url: str, cohort=None):
    """`33_` 의 로더를 그대로 쓴다 - 행 순서가 같아야 임베딩 캐시가 맞는다."""
    m33 = _mod("33_v2_mpnn_baseline.py", "m33")
    if cohort is not None:
        #: 격자를 바꿔 끼울 때 `33_` 의 전역 경로도 함께 옮긴다.
        m33.V2 = Path(cohort)
        m33.MPNN_CACHE = m33.V2 / "mpnn_scores_v2.json"
        global V2
        V2 = m33.V2
    rows = m33.load_rows()
    key = {c["sequence_id"]: c["backbone_key"]
           for c in json.loads((V2 / "candidates.json").read_text(encoding="utf-8"))}
    for r in rows:
        r["backbone_key"] = key[r["sequence_id"]]
    return rows, m33.embeddings(rows, esm_url), m33.mpnn_scores(rows)


# -------------------------------------------------------------- 배분 도구

def allocate(weights: np.ndarray, total: int, capacity: np.ndarray) -> np.ndarray:
    """가중치에 비례해 `total` 을 나누되 백본별 `capacity` 를 넘지 않는다.

    최대잔여법으로 나눈 뒤 넘친 몫을 여유 있는 백본에 가중치 순으로 다시
    돌린다. capacity 합이 total 보다 작으면 줄 수 있는 만큼만 준다.
    """
    cap = capacity.astype(int).copy()
    out = np.zeros(len(weights), dtype=int)
    left = int(min(total, cap.sum()))
    w = np.where(cap > 0, np.clip(weights, 1e-12, None), 0.0)
    while left > 0 and w.sum() > 0:
        share = w / w.sum() * left
        take = np.minimum(np.floor(share).astype(int), cap - out)
        if take.sum() == 0:                       # 잔여를 가중치 순으로 하나씩
            for b in np.argsort(-w):
                if out[b] < cap[b]:
                    out[b] += 1
                    left -= 1
                    if left == 0:
                        break
        else:
            out += take
            left -= int(take.sum())
        w = np.where(out < cap, w, 0.0)
    return out


def pick(order: np.ndarray, avail: list[int], k: int) -> list[int]:
    """`order` 가 정한 우선순위대로 `avail` 에서 k 개를 고른다."""
    rank = {j: i for i, j in enumerate(order)}
    return sorted(avail, key=lambda j: rank[j])[:k]


# -------------------------------------------------------------- 정책 재생

def replay_unit(y, X, m, bb_of, B, seed, fit_rank):
    """한 unit · 한 예산 · 한 seed. 모든 arm 이 같은 warm-up 표본을 받는다."""
    rng = np.random.default_rng(seed)
    bbs = sorted(set(bb_of))
    members = {b: np.flatnonzero(bb_of == b) for b in bbs}

    # --- 공통 warm-up: 백본당 sentinel 4 개, 백본 안에서 무작위 (§5)
    warm = []
    for b in bbs:
        idx = members[b]
        warm += list(rng.choice(idx, size=min(SENTINEL_PER_BACKBONE, len(idx)),
                                replace=False))
    warm = np.array(sorted(warm))
    H, A = len(warm), B - len(warm)
    if A < 0:
        return None
    base = float(y[warm].sum())
    rest = np.setdiff1d(np.arange(len(y)), warm)
    if A > len(rest):
        return None

    # 백본별 남은 정원과 후보
    avail = {b: [j for j in members[b] if j not in set(warm)] for b in bbs}
    cap = np.array([min(CEILING_PER_BACKBONE, len(members[b])) - SENTINEL_PER_BACKBONE
                    for b in bbs])
    cap = np.maximum(0, np.minimum(cap, [len(avail[b]) for b in bbs]))

    # --- warm-up 으로 적합한 RF 와 백본 posterior (§6.1)
    pred = fit_rank(X, y, warm, rest, seed, estimator="RF")
    rf_order = rest[np.argsort(pred)[::-1]]                     # 좋은 것부터
    post = np.array([(y[np.intersect1d(members[b], warm)].sum() + 1.0)
                     / (len(np.intersect1d(members[b], warm)) + 2.0) for b in bbs])

    def harvest(sel):
        return base + float(y[np.array(sel, dtype=int)].sum()) if sel else base

    got = {}
    # 백본을 무시하는 arm
    got["rf_only"] = harvest(list(rf_order[:A]))
    got["mpnn_only_paid"] = harvest(pick(rest[np.argsort(m[rest])], list(rest), A))
    got["oracle_paid"] = harvest(list(rest[np.argsort(y[rest])[::-1]][:A]))
    #: warm-up 을 아예 치르지 않는 별도 회계 (§6). 위와 섞지 않는다.
    got["mpnn_only_zerolabel"] = float(y[np.argsort(m)[:B]].sum())

    # 백본에 배분하는 arm
    for name, w in (("equal_random", np.ones(len(bbs))),
                    ("backbone_only", post), ("warmup_informed", post)):
        n_b = allocate(w, A, cap)
        sel = []
        for b, k in zip(bbs, n_b):
            if k <= 0:
                continue
            if name == "warmup_informed":
                sel += pick(rf_order, avail[b], k)
            else:
                sel += list(rng.choice(avail[b], size=k, replace=False))
        got[name] = harvest(sel)

    # --- 탐색 arm: posterior 가 실제로 갱신된다 (§6.2, 판정하지 않는다)
    a_s = np.array([y[np.intersect1d(members[b], warm)].sum() + 1.0 for b in bbs])
    b_s = np.array([len(np.intersect1d(members[b], warm))
                    - y[np.intersect1d(members[b], warm)].sum() + 1.0 for b in bbs])
    used = np.zeros(len(bbs), dtype=int)
    pool = {b: list(avail[b]) for b in bbs}
    rf_rank = {j: i for i, j in enumerate(rf_order)}
    sel, trng = [], np.random.default_rng(seed ^ 0x5E)
    for step in range(A):
        ok = [i for i in range(len(bbs)) if used[i] < cap[i] and pool[bbs[i]]]
        if not ok:
            break
        theta = trng.beta(a_s[ok], b_s[ok])
        i = ok[int(np.argmax(theta))]
        b = bbs[i]
        explore = (step % int(round(1 / EXPLORE_FRACTION))) == 0
        if explore:
            j = int(trng.choice(pool[b]))
        else:
            j = min(pool[b], key=lambda x: rf_rank[x])
        pool[b].remove(j)
        used[i] += 1
        sel.append(j)
        if explore:                      # 무작위 관측만 posterior 에 넣는다
            a_s[i] += y[j]
            b_s[i] += 1 - y[j]
    got["adaptive_sentinel"] = harvest(sel)

    got["_meta"] = {"warmup": H, "adaptive": A, "n_backbones": len(bbs)}
    return got


# ---------------------------------------------------------------- 집계

def run_source(rows, emb, mpnn, source):
    fit_rank = _mod("31_fewshot_jointpass_transfer.py", "m31").fit_rank
    by_unit = collections.defaultdict(list)
    for i, r in enumerate(rows):
        if r["cohort"] == COHORT and r["source"] == source:
            by_unit[r["target_id"]].append(i)

    per_unit = {}
    for tgt, idx in sorted(by_unit.items()):
        idx = np.array(idx)
        y = np.array([rows[i]["joint_pass"] for i in idx], dtype=float)
        if y.min() == y.max():            # informative 규칙 (동결)
            per_unit[tgt] = {"informative": False, "n": int(len(idx))}
            continue
        X = emb[idx]
        m = np.array([mpnn[rows[i]["sequence_id"]] for i in idx])
        bb_of = np.array([rows[i]["backbone_key"] for i in idx])
        by_b = {}
        for B in BUDGETS:
            runs = [replay_unit(y, X, m, bb_of, B, s, fit_rank) for s in SEEDS]
            runs = [r for r in runs if r]
            if len(runs) != len(SEEDS):
                continue
            by_b[str(B)] = {a: statistics.mean(r[a] for r in runs) for a in ARMS}
            by_b[str(B)]["_meta"] = runs[0]["_meta"]
        per_unit[tgt] = {"informative": True, "n": int(len(idx)),
                         "rate": float(y.mean()),
                         "n_backbones": int(len(set(bb_of))),
                         "pool_fraction_at_80": round(80 / len(idx), 3),
                         "by_budget": by_b}

    good = sorted(t for t, v in per_unit.items() if v["informative"])
    out = {"source": source, "cohort": COHORT, "n_informative": len(good),
           "units": good, "per_unit": per_unit, "by_budget": {}}
    rng = np.random.default_rng(BOOT_SEED)
    for B in BUDGETS:
        have = [t for t in good if str(B) in per_unit[t]["by_budget"]]
        if not have:
            continue
        boots = [[have[int(rng.integers(len(have)))] for _ in have]
                 for _ in range(N_BOOTSTRAP)]

        def agg(ts, a):
            return statistics.mean(per_unit[t]["by_budget"][str(B)][a] for t in ts)

        e = {"n_units": len(have),
             "judgeable": len(have) >= MIN_CLUSTERS,
             "dropped_pool_lt_B": [t for t in good if t not in have],
             "point": {a: agg(have, a) for a in ARMS}, "contrasts": {}}
        for a, b in [PRIMARY] + SECONDARY + [("adaptive_sentinel", "warmup_informed")]:
            dr = sorted(agg(x, a) - agg(x, b) for x in boots)
            q = lambda p: dr[min(len(dr) - 1, max(0, int(p * len(dr))))]
            c = {"delta": agg(have, a) - agg(have, b),
                 "ci95": [q(.025), q(.975)],
                 "excludes_zero": bool(q(.025) > 0 or q(.975) < 0)}
            if (a, b) in SECONDARY:       # 보조 3 개만 Bonferroni (§7)
                c["ci9833_bonf3"] = [q(.05 / 3 / 2), q(1 - .05 / 3 / 2)]
            c["role"] = ("primary" if (a, b) == PRIMARY
                         else "secondary" if (a, b) in SECONDARY else "exploratory")
            e["contrasts"][f"{a}-{b}"] = c
        out["by_budget"][str(B)] = e
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=None,
                    help="격자 디렉터리. 주지 않으면 동결된 코호트를 쓴다.")
    ap.add_argument("--esm-url", default="")
    ap.add_argument("--out", default=str(OUT_DIR / "hierarchical_replay.json"))
    args = ap.parse_args(argv)

    rows, emb, mpnn = load(args.esm_url, args.cohort)
    print(f"후보 {len(rows)} · 백본 {len({r['backbone_key'] for r in rows})}", flush=True)

    out = {"purpose": ("백본 배분과 서열 순위화의 결합 이득을 같은 예산에서 "
                       "재생한다. 새 folding 없음. 확증 분석이 아니다."),
           "prespec": "docs/specs/hierarchical-replay-prespec.md",
           "prespec_version": "1.1",
           "prespec_sha256": hashlib.sha256(PRESPEC.read_bytes()).hexdigest(),
           "primary": {"source": PRIMARY_SOURCE, "cohort": COHORT,
                       "budget": PRIMARY_BUDGET, "contrast": "-".join(PRIMARY)},
           "naming_note": ("배분은 warm-up 이후 갱신되지 않으므로 adaptive 가 "
                           "아니라 warmup_informed 다. adaptive_sentinel 은 "
                           "탐색 arm 이며 판정하지 않는다."),
           "sentinel_per_backbone": SENTINEL_PER_BACKBONE,
           "ceiling_per_backbone": CEILING_PER_BACKBONE,
           "explore_fraction": EXPLORE_FRACTION,
           "seeds": SEEDS, "bootstrap": {"n": N_BOOTSTRAP, "seed": BOOT_SEED,
                                         "unit": "target"},
           "efbc_computed": False, "calibration_cohort_used": False,
           "sources": {}}
    for src in (PRIMARY_SOURCE, "bioemu"):
        print(f"\n[{src}] {COHORT}", flush=True)
        out["sources"][src] = run_source(rows, emb, mpnn, src)

    for src, res in out["sources"].items():
        print(f"\n=== {src} {COHORT} · informative {res['n_informative']}")
        for B in BUDGETS:
            e = res["by_budget"].get(str(B))
            if not e:
                continue
            flag = "" if e["judgeable"] else f"  ← {MIN_CLUSTERS} 미만, 판정 안 함"
            print(f"  B={B:3d} unit {e['n_units']}{flag}")
            print("      " + "  ".join(f"{a}={e['point'][a]:.2f}"
                                       for a in ("rf_only", "warmup_informed",
                                                 "backbone_only", "mpnn_only_paid")))
            for k, c in e["contrasts"].items():
                if c["role"] == "exploratory":
                    continue
                print(f"      {c['role']:9s} {k:38s} {c['delta']:+.2f} "
                      f"[{c['ci95'][0]:+.2f},{c['ci95'][1]:+.2f}] "
                      f"{'0 제외' if c['excludes_zero'] else '0 포함'}")

    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"\n{args.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
