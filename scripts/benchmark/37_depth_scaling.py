#!/usr/bin/env python3
"""깊이를 18 에서 42 로 올리면 greedy 배분의 이득이 커지는가.

규칙은 `docs/specs/depth-scaling-pilot-prespec.md` (v1.1) 에 실행 전 동결돼
있다. 여기서 그 문서에 없는 선택을 새로 하지 않는다.

    주 비교   D(42) - D(18),  D(d) = G(greedy_fill, d) - G(rf_only, d)
    G         (Y_policy - Y_equal) / (Y_oracle - Y_equal)   여지 회수율
    보조      greedy_thompson (36_ 과 같은 정책) 으로 같은 대비

두 greedy 가 왜 둘인가
----------------------
`36_` 이 측정한 `greedy_frozen` 은 고정 posterior 에서 **Thompson 추출**이고,
확증 사전지정 §5 가 동결한 것은 posterior **mean 내림차순 결정적 채우기**다.
캠페인을 정당화한 +1.55 는 Thompson 쪽에서 나왔는데 확증 코호트는 결정적
쪽을 돌리게 되어 있었다. 추가 폴딩 없이 둘 다 잴 수 있으므로 둘 다 낸다.

**확증 분석이 아니다.** 가설을 만든 바로 그 8 표적을 다시 쓴다.
"""

from __future__ import annotations

import argparse
import collections
import csv
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
PILOT = BASE / "depth_pilot"
EMB_CACHE = PROJECT_ROOT / "data" / "benchmark" / "depth_pilot_emb_320d.npz"

#: 사전지정 §3-§5. 바꾸지 않는다.
PLDDT_MIN, RMSD_MAX, SOLUPROT_MIN = 85.0, 2.0, 0.5
DEPTHS = (18, 42)
SENTINEL, BUDGETS, PRIMARY_B = 4, (60, 80, 100), 80
SEEDS = [42, 123, 7, 2024, 31337]
N_BOOTSTRAP, BOOT_SEED = 2000, 20260921
DENOM_MIN = 5.0
ARMS = ("equal_random", "rf_only", "greedy_fill", "greedy_thompson", "oracle")


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


# ------------------------------------------------------------------ 입력

def load(esm_url: str, v2_cohort=None, pilot_cohort=None):
    """기존 18 개(v2) + 신규 24 개(파일럿) 를 한 표로 합친다."""
    m33 = _mod("33_v2_mpnn_baseline.py", "m33")
    global PILOT
    if v2_cohort is not None:
        m33.V2 = Path(v2_cohort)
        m33.MPNN_CACHE = m33.V2 / "mpnn_scores_v2.json"
    if pilot_cohort is not None:
        PILOT = Path(pilot_cohort)
    rows = [r for r in m33.load_rows()
            if r["cohort"] == "confirmatory" and r["source"] == "rfd3"]
    key = {c["sequence_id"]: c["backbone_key"]
           for c in json.loads((BASE / "v2_multisource" / "candidates.json")
                               .read_text("utf-8"))}
    for r in rows:
        r["backbone_key"], r["depth_ext"] = key[r["sequence_id"]], False

    cand = {c["sequence_id"]: c
            for c in json.loads((PILOT / "candidates_ext.json").read_text("utf-8"))}
    n_new = 0
    csv_path = PILOT / "af2_order_metric.csv"
    if csv_path.exists():
        for r in csv.DictReader(csv_path.open(encoding="utf-8")):
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
            rows.append({"sequence_id": r["sequence_id"], "sequence": c["sequence"],
                         "target_id": c["target_id"], "cohort": c["cohort"],
                         "source": c["backbone_source"],
                         "backbone_pdb": c["backbone_pdb"],
                         "backbone_key": c["backbone_key"], "depth_ext": True,
                         "joint_pass": float(pl >= PLDDT_MIN and rm <= RMSD_MAX
                                             and so >= SOLUPROT_MIN)})
            n_new += 1
    print(f"기존 {len(rows) - n_new} · 신규 {n_new} · 합 {len(rows)}", flush=True)

    digest = hashlib.sha256("\n".join(r["sequence_id"] for r in rows).encode()).hexdigest()
    if EMB_CACHE.exists():
        z = np.load(EMB_CACHE, allow_pickle=False)
        if str(z["digest"]) == digest:
            print(f"  임베딩 캐시 {z['embeddings'].shape}", flush=True)
            return rows, z["embeddings"]
    from pipeline_mcp.clients.esm_embedding import LocalHTTPESMEmbeddingClient
    print(f"  임베딩 계산 {len(rows)} · {esm_url}", flush=True)
    emb = LocalHTTPESMEmbeddingClient(base_url=esm_url, token=None).embed(
        [r["sequence"] for r in rows])
    EMB_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMB_CACHE, embeddings=emb, digest=digest)
    return rows, emb


# -------------------------------------------------------------- 정책 재생

def replay(y, X, bb_of, B, seed, depth, fit_rank):
    """한 unit · 한 깊이 · 한 예산 · 한 seed. 모든 arm 이 같은 warm-up 을 쓴다."""
    rng = np.random.default_rng(seed)
    bbs = sorted(set(bb_of))
    members = {b: np.flatnonzero(bb_of == b) for b in bbs}
    warm = []
    for b in bbs:
        warm += list(rng.choice(members[b], size=min(SENTINEL, len(members[b])),
                                replace=False))
    warm = np.array(sorted(warm))
    A = B - len(warm)
    rest = np.setdiff1d(np.arange(len(y)), warm)
    if A < 0 or A > len(rest):
        return None
    base = float(y[warm].sum())
    wset = set(warm.tolist())
    avail = {b: [j for j in members[b] if j not in wset] for b in bbs}
    #: 정원은 깊이에서 sentinel 을 뺀 값. 후보가 모자라면 그만큼만.
    cap = {b: max(0, min(depth, len(members[b])) - SENTINEL) for b in bbs}
    cap = {b: min(cap[b], len(avail[b])) for b in bbs}

    pred = fit_rank(X, y, warm, rest, seed, estimator="RF")
    rf_order = list(rest[np.argsort(-pred, kind="stable")])
    rf_rank = {j: i for i, j in enumerate(rf_order)}
    wa = {b: np.intersect1d(members[b], warm) for b in bbs}
    a0 = {b: y[wa[b]].sum() + 1.0 for b in bbs}
    b0 = {b: len(wa[b]) - y[wa[b]].sum() + 1.0 for b in bbs}
    post = {b: a0[b] / (a0[b] + b0[b]) for b in bbs}

    def harvest(sel):
        return base + (float(y[np.array(sel, dtype=int)].sum()) if sel else 0.0)

    got = {"rf_only": harvest(rf_order[:A]),
           "oracle": harvest(list(rest[np.argsort(-y[rest], kind="stable")][:A]))}

    # equal_random: 균등 배분, 백본 안에서 무작위
    per = {}
    left, active = A, [b for b in bbs if cap[b] > 0]
    while left > 0 and active:
        q = max(1, left // len(active))
        for b in list(active):
            take = min(q, cap[b] - per.get(b, 0), left)
            per[b] = per.get(b, 0) + take
            left -= take
            if per[b] >= cap[b]:
                active.remove(b)
            if left == 0:
                break
    sel = []
    for b, k in per.items():
        sel += list(rng.choice(avail[b], size=k, replace=False))
    got["equal_random"] = harvest(sel)

    # greedy_fill: posterior mean 내림차순, 동점은 backbone_key 사전순,
    # 한 백본씩 정원까지 채운다 (확증 사전지정 §5)
    sel, left = [], A
    for b in sorted(bbs, key=lambda x: (-post[x], x)):
        if left <= 0:
            break
        k = min(cap[b], left)
        sel += sorted(avail[b], key=lambda j: (rf_rank[j], j))[:k]
        left -= k
    got["greedy_fill"] = harvest(sel)

    # greedy_thompson: 36_ 과 같은 정책 (고정 posterior 에서 Thompson 추출)
    used = collections.Counter()
    pool = {b: list(avail[b]) for b in bbs}
    sel, trng = [], np.random.default_rng(seed ^ 0x5E)
    aa = np.array([a0[b] for b in bbs])
    bbv = np.array([b0[b] for b in bbs])
    for _ in range(A):
        ok = [i for i, b in enumerate(bbs) if used[b] < cap[b] and pool[b]]
        if not ok:
            break
        i = ok[int(np.argmax(trng.beta(aa[ok], bbv[ok])))]
        b = bbs[i]
        j = min(pool[b], key=lambda x: rf_rank[x])
        pool[b].remove(j)
        used[b] += 1
        sel.append(j)
    got["greedy_thompson"] = harvest(sel)
    return got


# ---------------------------------------------------------------- 집계

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esm-url", default=_esm_url_default())
    ap.add_argument("--v2-cohort", default=None)
    ap.add_argument("--pilot-cohort", default=None)
    ap.add_argument("--out", default=str(BASE / "depth_scaling.json"))
    a = ap.parse_args(argv)

    rows, emb = load(a.esm_url, a.v2_cohort, a.pilot_cohort)
    fit_rank = _mod("31_fewshot_jointpass_transfer.py", "m31").fit_rank
    by_unit = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by_unit[r["target_id"]].append(i)

    per_unit, skipped = {}, {}
    for tgt, idx in sorted(by_unit.items()):
        idx = np.array(idx)
        ext = np.array([rows[i]["depth_ext"] for i in idx])
        rec = {"n_18": int((~ext).sum()), "n_42": int(len(idx)), "by_depth": {}}
        for depth in DEPTHS:
            sub = idx if depth == 42 else idx[~ext]
            y = np.array([rows[i]["joint_pass"] for i in sub], dtype=float)
            if y.min() == y.max():
                rec["by_depth"][str(depth)] = {"informative": False}
                continue
            X = emb[sub]
            bb = np.array([rows[i]["backbone_key"] for i in sub])
            d = {}
            for B in BUDGETS:
                runs = [replay(y, X, bb, B, s, depth, fit_rank) for s in SEEDS]
                runs = [r for r in runs if r]
                if len(runs) != len(SEEDS):
                    continue
                d[str(B)] = {k: statistics.mean(r[k] for r in runs) for k in ARMS}
            rec["by_depth"][str(depth)] = {"informative": True, "rate": float(y.mean()),
                                           "n_backbones": int(len(set(bb))),
                                           "by_budget": d}
        per_unit[tgt] = rec

    def G(tgt, depth, arm, B):
        e = per_unit[tgt]["by_depth"][str(depth)]
        if not e.get("informative") or str(B) not in e["by_budget"]:
            return None
        v = e["by_budget"][str(B)]
        den = v["oracle"] - v["equal_random"]
        if den < DENOM_MIN:
            return None
        return (v[arm] - v["equal_random"]) / den

    out = {"purpose": "깊이 18->42 에서 greedy 배분 이득이 커지는지 본다. 확증 아님.",
           "prespec": "docs/specs/depth-scaling-pilot-prespec.md",
           "prespec_version": "1.1", "post_hoc": False, "confirmatory": False,
           "denominator_min": DENOM_MIN, "per_unit": per_unit, "contrasts": {}}

    for greedy in ("greedy_fill", "greedy_thompson"):
        for B in BUDGETS:
            names = [t for t in sorted(per_unit)
                     if all(G(t, d, greedy, B) is not None
                            and G(t, d, "rf_only", B) is not None for d in DEPTHS)]
            if len(names) < 2:
                out["contrasts"][f"{greedy}|B{B}"] = {"n_units": len(names),
                                                      "note": "자격 unit 부족"}
                continue
            dd = {t: ((G(t, 42, greedy, B) - G(t, 42, "rf_only", B))
                      - (G(t, 18, greedy, B) - G(t, 18, "rf_only", B))) for t in names}
            rng = np.random.default_rng(BOOT_SEED)
            boots = [[names[int(rng.integers(len(names)))] for _ in names]
                     for _ in range(N_BOOTSTRAP)]
            dr = sorted(statistics.mean(dd[t] for t in bs) for bs in boots)
            q = lambda p: dr[min(len(dr) - 1, max(0, int(p * len(dr))))]
            out["contrasts"][f"{greedy}|B{B}"] = {
                "n_units": len(names), "units": names,
                "D18": statistics.mean(G(t, 18, greedy, B) - G(t, 18, "rf_only", B)
                                       for t in names),
                "D42": statistics.mean(G(t, 42, greedy, B) - G(t, 42, "rf_only", B)
                                       for t in names),
                "delta": statistics.mean(dd.values()),
                "ci95": [q(.025), q(.975)],
                "excludes_zero": bool(q(.025) > 0 or q(.975) < 0),
                "per_unit_delta": dd}

    print(f"\n=== 깊이 반응  D(42) - D(18)   [{DENOM_MIN} 이상 분모만]")
    for k, c in out["contrasts"].items():
        if "note" in c:
            print(f"  {k:26s} {c['note']} (unit {c['n_units']})")
            continue
        star = " ★" if k.endswith(f"B{PRIMARY_B}") and k.startswith("greedy_fill") else ""
        print(f"  {k:26s} unit {c['n_units']} · D18 {c['D18']:+.3f} → "
              f"D42 {c['D42']:+.3f} · 차이 {c['delta']:+.3f} "
              f"[{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}] "
              f"{'0 제외' if c['excludes_zero'] else '0 포함'}{star}")
    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"\n{a.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
