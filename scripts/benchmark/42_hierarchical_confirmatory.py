#!/usr/bin/env python3
"""백본 배분이 서열 순위화 위에 수확을 더하는가 - 34 표적 확증 코호트.

규칙은 `docs/specs/hierarchical-confirmatory-prespec.md` (v1.6) 에 실행 전
동결돼 있다. 여기서 그 문서에 없는 선택을 새로 하지 않는다.

    주 비교   G(greedy_frozen) - G(rf_only)  의 표적 평균, B=80
    G         (Y_policy - Y_equal_random) / (Y_oracle - Y_equal_random)
    자격      분모(r) = H*r + min(B-H, (N-H)*r) - B*r >= 5
              실측 joint-pass 율로만 판정한다. 정책 결과를 보고 판정하지 않는다.
    보조      Y(greedy_frozen) - Y(rf_only) 의 표적 평균 (자격 규칙 없음)

`35_`/`36_` 은 이 가설을 **만든** 자료다. 여기 34 표적은 그 가설을 처음으로
미리 고정한 정책으로 시험한다. 사전지정 §0 대로 깊이 게이트는 통과하지 못했고
(파일럿 D_p = -0.010) 사람이 구간 축소를 목적으로 실행을 승인했다. 그래서
**이 결과는 구간을 좁히는 데 쓰고, 양성이 나와도 게이트를 소급해 통과시키지
않는다.**

EFBC 를 계산하지 않는다. coverage 결론을 내지 않는다 (사전지정 §9).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import math
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

#: 사전지정 §4-§7. 바꾸지 않는다.
WARMUP_PER_BB, QUOTA_CAP = 4, 40
BUDGETS, PRIMARY_B = (60, 80, 100), 80
DENOM_MIN = 5.0
SEEDS = [42, 123, 7, 2024, 31337]
N_BOOTSTRAP, BOOT_SEED = 2000, 20260921
ARMS = ("greedy_frozen", "rf_only", "equal_random", "backbone_only",
        "mpnn_only", "oracle", "adaptive_sentinel")
#: 판정하는 arm 은 둘뿐이다. 나머지는 눈금과 탐색이다 (§5, §8).
EXPLORATORY = ("adaptive_sentinel",)


def _esm_url_default() -> str:
    """ESM_EMBEDDING_URL 이 없으면 빈 문자열. 호출자가 --esm-url 로 준다.

    내부 호스트를 기본값으로 박아두면 공개 저장소에 그대로 나간다. 임베딩
    캐시가 있으면 이 값은 쓰이지 않는다.
    """
    return os.environ.get("ESM_EMBEDDING_URL", "").strip()


def _mod(p, n):
    s = importlib.util.spec_from_file_location(n, HERE / p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


# -------------------------------------------------------------- 정책 재생

def replay(y, X, bb_of, sid, mp, B, seed, fit_rank, m35):
    """한 표적 · 한 예산 · 한 seed. 모든 arm 이 같은 warm-up 표본을 받는다."""
    rng = np.random.default_rng(seed)
    bbs = sorted(set(bb_of))
    members = {b: np.flatnonzero(bb_of == b) for b in bbs}

    warm = []
    for b in bbs:                                   # §5-1 백본 안에서 무작위
        m = members[b]
        warm += list(rng.choice(m, size=min(WARMUP_PER_BB, len(m)), replace=False))
    warm = np.array(sorted(int(i) for i in warm), dtype=int)
    H = len(warm)
    rest = np.setdiff1d(np.arange(len(y)), warm)
    A = int(min(B - H, len(rest)))                  # 배분 가능 호출 수
    if A <= 0:
        return None
    base = float(y[warm].sum())

    #: §5-2 warm-up 으로만 RF 를 적합한다. 표준화 없음, n_estimators=100.
    pred = fit_rank(X, y, warm, rest, seed, estimator="RF")
    #: §5-6 RF 내림차순, 동점이면 sequence_id 사전순
    rf_order = np.array([rest[i] for i in sorted(
        range(len(rest)), key=lambda i: (-float(pred[i]), sid[rest[i]]))])
    avail = {b: [int(j) for j in rest if bb_of[j] == b] for b in bbs}
    quota = {b: max(0, min(QUOTA_CAP, len(members[b])) - WARMUP_PER_BB) for b in bbs}

    #: §5-3 백본 posterior mean = (통과 + 1) / (관측 + 2)
    post = {}
    for b in bbs:
        w = np.intersect1d(members[b], warm)
        post[b] = (float(y[w].sum()) + 1.0) / (len(w) + 2.0)
    #: §5-4 내림차순, 동점이면 backbone_key 사전순
    order_bb = sorted(bbs, key=lambda b: (-post[b], b))

    #: §5-5,7 순서대로 정원까지 꽉 채운다. 한 바퀴로 안 차면 정원 밖으로 잇는다.
    alloc = {b: 0 for b in bbs}
    left = A
    for cap in (quota, {b: len(avail[b]) for b in bbs}):
        for b in order_bb:
            if left <= 0:
                break
            take = min(cap[b] - alloc[b], len(avail[b]) - alloc[b], left)
            if take > 0:
                alloc[b] += take
                left -= take
        if left <= 0:
            break

    nb = len(bbs)
    eq = m35.allocate(np.ones(nb), A, np.array([len(avail[b]) for b in bbs]))
    eq_alloc = {b: int(eq[i]) for i, b in enumerate(bbs)}
    r2 = np.random.default_rng(seed ^ 0xA11C)

    def by_alloc(a, use_rf):
        out = []
        for b in bbs:
            k = int(a.get(b, 0))
            if k <= 0:
                continue
            out += (m35.pick(rf_order, avail[b], k) if use_rf
                    else [int(x) for x in r2.choice(avail[b], size=k, replace=False)])
        return out

    got = {"greedy_frozen": by_alloc(alloc, True),
           "backbone_only": by_alloc(alloc, False),
           "equal_random": by_alloc(eq_alloc, False),
           "rf_only": list(rf_order[:A]),
           "oracle": sorted(rest, key=lambda j: (-y[j], sid[j]))[:A]}
    if mp is not None:
        got["mpnn_only"] = sorted(rest, key=lambda j: (mp[j], sid[j]))[:A]

    #: §8 탐색 arm. 35_/36_ 과 같은 규칙 - Thompson, 탐색 25%,
    #: posterior 는 탐색(sentinel) 관측으로만 갱신한다. 판정하지 않는다.
    a_s = np.array([float(y[np.intersect1d(members[b], warm)].sum()) + 1.0 for b in bbs])
    b_s = np.array([len(np.intersect1d(members[b], warm))
                    - float(y[np.intersect1d(members[b], warm)].sum()) + 1.0 for b in bbs])
    rf_rank = {int(j): i for i, j in enumerate(rf_order)}
    pool = {b: list(avail[b]) for b in bbs}
    used = np.zeros(nb, dtype=int)
    sel, trng = [], np.random.default_rng(seed ^ 0x5E)
    step_of_explore = int(round(1 / m35.EXPLORE_FRACTION))
    for step in range(A):
        ok = [i for i in range(nb) if used[i] < quota[bbs[i]] and pool[bbs[i]]]
        if not ok:
            ok = [i for i in range(nb) if pool[bbs[i]]]
        if not ok:
            break
        i = ok[int(np.argmax(trng.beta(a_s[ok], b_s[ok])))]
        b = bbs[i]
        exp = (step % step_of_explore) == 0
        j = int(trng.choice(pool[b])) if exp else min(pool[b], key=lambda x: rf_rank[x])
        pool[b].remove(j)
        used[i] += 1
        sel.append(j)
        if exp:
            a_s[i] += y[j]
            b_s[i] += 1 - y[j]
    got["adaptive_sentinel"] = sel

    out = {a: base + float(y[np.array(v, dtype=int)].sum()) if v else base
           for a, v in got.items()}
    out["_meta"] = {"H": H, "A": A,
                    "max_share": max(alloc.values()) / A if A else 0.0,
                    "n_backbones_used": sum(1 for v in alloc.values() if v > 0)}
    return out


# ---------------------------------------------------------------- 집계

def eligible_denominator(N: int, H: int, B: int, r: float) -> float:
    """§6.2 닫힌 형태. 실측 joint-pass 율만 쓴다."""
    return H * r + min(B - H, (N - H) * r) - B * r


def run(rows, emb, mpnn, label):
    m35 = _mod("35_hierarchical_replay.py", "m35")
    fit_rank = _mod("31_fewshot_jointpass_transfer.py", "m31").fit_rank

    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r["target_id"]].append(i)

    per_target = {}
    for tgt, idx in sorted(by.items()):
        idx = np.array(idx)
        y = np.array([rows[i]["joint_pass"] for i in idx], dtype=float)
        X, sid = emb[idx], [rows[i]["sequence_id"] for i in idx]
        bb = np.array([rows[i]["backbone_key"] for i in idx])
        mp = (np.array([mpnn[rows[i]["sequence_id"]] for i in idx])
              if mpnn and all(rows[i]["sequence_id"] in mpnn for i in idx) else None)
        N, nb, r = len(idx), len(set(bb)), float(y.mean())
        d = {}
        for B in BUDGETS:
            runs = [replay(y, X, bb, sid, mp, B, s, fit_rank, m35) for s in SEEDS]
            runs = [x for x in runs if x]
            if len(runs) != len(SEEDS):
                continue
            Y = {a: statistics.mean(x[a] for x in runs)
                 for a in ARMS if a in runs[0]}
            H = runs[0]["_meta"]["H"]
            denom_obs = Y["oracle"] - Y["equal_random"]
            d[str(B)] = {
                "Y": Y, "H": H, "A": runs[0]["_meta"]["A"],
                "denom_expected": eligible_denominator(N, H, B, r),
                "denom_observed": denom_obs,
                "eligible": bool(eligible_denominator(N, H, B, r) >= DENOM_MIN),
                "G": {a: ((Y[a] - Y["equal_random"]) / denom_obs)
                      if abs(denom_obs) > 1e-9 else None for a in Y},
                "max_share": statistics.mean(x["_meta"]["max_share"] for x in runs)}
        per_target[tgt] = {"n": N, "n_backbones": nb, "joint_rate": r,
                           "has_mpnn": mp is not None, "by_budget": d}

    names = sorted(per_target)
    out = {"label": label, "n_targets": len(names), "targets": names,
           "per_target": per_target, "by_budget": {}}

    for B in BUDGETS:
        key = str(B)
        allt = [t for t in names if key in per_target[t]["by_budget"]]
        elig = [t for t in allt if per_target[t]["by_budget"][key]["eligible"]]
        if not allt:
            continue
        rng = np.random.default_rng(BOOT_SEED)
        bt_e = [[elig[int(rng.integers(len(elig)))] for _ in elig]
                for _ in range(N_BOOTSTRAP)] if elig else []
        bt_a = [[allt[int(rng.integers(len(allt)))] for _ in allt]
                for _ in range(N_BOOTSTRAP)]

        def gm(ts, a):
            v = [per_target[t]["by_budget"][key]["G"][a] for t in ts
                 if per_target[t]["by_budget"][key]["G"].get(a) is not None]
            return statistics.mean(v) if v else float("nan")

        def ym(ts, a):
            v = [per_target[t]["by_budget"][key]["Y"][a] for t in ts
                 if a in per_target[t]["by_budget"][key]["Y"]]
            return statistics.mean(v) if v else float("nan")

        def ci(draws):
            dr = sorted(x for x in draws if not math.isnan(x))
            if not dr:
                return None
            lo, hi = dr[int(.025 * len(dr))], dr[int(.975 * len(dr))]
            return [lo, hi]

        have = [a for a in ARMS if a in per_target[allt[0]]["by_budget"][key]["Y"]]
        e = {"n_targets_all": len(allt), "n_targets_eligible": len(elig),
             "G_point": {a: gm(elig, a) for a in have} if elig else {},
             "Y_point": {a: ym(allt, a) for a in have},
             "max_share": statistics.mean(
                 per_target[t]["by_budget"][key]["max_share"] for t in allt),
             "primary": None, "secondary": None, "other": {}}

        if elig:
            d = gm(elig, "greedy_frozen") - gm(elig, "rf_only")
            c = ci(gm(b, "greedy_frozen") - gm(b, "rf_only") for b in bt_e)
            e["primary"] = {"name": "G(greedy_frozen) - G(rf_only)", "delta": d,
                            "ci95": c, "n": len(elig),
                            "excludes_zero": bool(c and (c[0] > 0 or c[1] < 0))}
        d = ym(allt, "greedy_frozen") - ym(allt, "rf_only")
        c = ci(ym(b, "greedy_frozen") - ym(b, "rf_only") for b in bt_a)
        e["secondary"] = {"name": "Y(greedy_frozen) - Y(rf_only) 원시 개수",
                          "delta": d, "ci95": c, "n": len(allt),
                          "excludes_zero": bool(c and (c[0] > 0 or c[1] < 0))}
        for a in have:
            if a in ("greedy_frozen", "rf_only", "equal_random", "oracle") or not elig:
                continue
            d2 = gm(elig, a) - gm(elig, "rf_only")
            c2 = ci(gm(b, a) - gm(b, "rf_only") for b in bt_e)
            e["other"][f"G({a}) - G(rf_only)"] = {
                "delta": d2, "ci95": c2,
                "role": "탐색 (판정하지 않는다)" if a in EXPLORATORY else "보조",
                "excludes_zero": bool(c2 and (c2[0] > 0 or c2[1] < 0))}
        out["by_budget"][key] = e
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=str(BASE / "hier_confirmatory"))
    ap.add_argument("--label", default="hier_confirmatory_34")
    ap.add_argument("--esm-url", default=_esm_url_default())
    ap.add_argument("--mpnn-cache", default=str(BASE / "hier_confirmatory"
                                                / "mpnn_scores.json"))
    ap.add_argument("--out", default=str(BASE / "hierarchical_confirmatory.json"))
    a = ap.parse_args(argv)

    rows, emb = _mod("39_selection_gain_decomposition.py", "m39").load(
        Path(a.cohort), a.esm_url)
    mpnn = None
    mc = Path(a.mpnn_cache)
    if mc.exists():
        cached = json.loads(mc.read_text(encoding="utf-8")).get("scores", {})
        #: 일부 표적만 점수가 있으면 arm 의 표본이 다른 arm 과 달라진다.
        #: 전수가 아니면 아예 내지 않는다.
        missing = sum(1 for r in rows if r["sequence_id"] not in cached)
        if missing:
            print(f"  MPNN 점수 {len(cached)} · 누락 {missing} - "
                  "전수가 아니라 mpnn_only arm 을 내지 않는다", flush=True)
        else:
            mpnn = {k: float(v) for k, v in cached.items()}
            print(f"  MPNN 점수 {len(mpnn)} (전수)", flush=True)
    else:
        print("  MPNN 점수 없음 - mpnn_only arm 을 내지 않는다", flush=True)

    res = run(rows, emb, mpnn, a.label)
    doc = {"purpose": "백본 배분이 서열 순위화 위에 수확을 더하는가. 새 folding 없음.",
           "prespec": "docs/specs/hierarchical-confirmatory-prespec.md",
           "prespec_sha256": hashlib.sha256(
               (PROJECT_ROOT / "docs" / "specs"
                / "hierarchical-confirmatory-prespec.md").read_bytes()).hexdigest(),
           "primary_endpoint": "G(greedy_frozen) - G(rf_only)",
           "primary_budget": PRIMARY_B, "denom_min": DENOM_MIN, "seeds": SEEDS,
           "note_gate": ("깊이 게이트 미통과(파일럿 D_p=-0.010) 뒤 사람이 구간 "
                         "축소를 목적으로 승인한 실행이다. 양성이 나와도 게이트를 "
                         "소급해 통과시키지 않는다."),
           "bootstrap": {"n": N_BOOTSTRAP, "seed": BOOT_SEED, "unit": "target"},
           "result": res}

    print(f"\n=== {res['label']} · 표적 {res['n_targets']}")
    for B in BUDGETS:
        e = res["by_budget"].get(str(B))
        if not e:
            continue
        star = " ★" if B == PRIMARY_B else ""
        print(f"\n  B={B:3d}  전체 {e['n_targets_all']} · 자격 "
              f"{e['n_targets_eligible']} · 최대 집중 {e['max_share']:.1%}{star}")
        for arm, v in e["Y_point"].items():
            g = e["G_point"].get(arm)
            print(f"      {arm:20s} Y {v:7.2f}"
                  + (f" · G {g:+.3f}" if g is not None else ""))
        for nm in ("primary", "secondary"):
            s = e[nm]
            if not s:
                continue
            c = s["ci95"] or [float("nan")] * 2
            print(f"      {nm:9s} {s['name']:34s} {s['delta']:+7.3f} "
                  f"[{c[0]:+.3f},{c[1]:+.3f}] "
                  f"{'0 제외' if s['excludes_zero'] else '0 포함'} (n={s['n']})")
        for k, s in e["other"].items():
            c = s["ci95"] or [float("nan")] * 2
            print(f"      {'':9s} {k:34s} {s['delta']:+7.3f} "
                  f"[{c[0]:+.3f},{c[1]:+.3f}] "
                  f"{'0 제외' if s['excludes_zero'] else '0 포함'} ({s['role']})")
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"\n{a.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
