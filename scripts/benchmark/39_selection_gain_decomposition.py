#!/usr/bin/env python3
"""서열 선택 이득을 백본 간 성분과 백본 내 성분으로 가른다.

규칙은 `docs/specs/selection-gain-decomposition-prespec.md` 에 결과 확인 전
동결돼 있다. 여기서 그 문서에 없는 선택을 새로 하지 않는다.

왜 하는가
---------
동결된 판정 셋이 맞지 않아 보인다.

    Gate 2      백본 **내부**에서 cheap predictor 가 서열을 못 가른다 (NO-GO)
    실험 1·2    표적의 **전체 풀**에서는 RF 가 잘 고른다
    실험 3      명시적 백본 배분을 얹어도 추가 이득이 없다

estimand 가 다르다. 가설: **RF 의 이득은 주로 백본 간 판별에서 오고 그래서
명시적 배분이 중복이다.** 맞으면 세 결과가 하나의 기전으로 정리된다.

2 x 2 요인 설계
---------------
네 arm 이 **같은 warm-up 표본과 같은 RF 적합**을 공유하고 선택만 다르다.

                백본 내 = RF      백본 내 = 무작위
    배분 = RF   rf/rf              rf/rand
    배분 = 균등 unif/rf            unif/rand   (기준선)

    Total   = Y(rf/rf)   − Y(unif/rand)
    Between = Y(rf/rand) − Y(unif/rand)
    Within  = Y(unif/rf) − Y(unif/rand)
    Inter   = Total − Between − Within      어느 쪽에도 귀속하지 않는다

주 종점은 `Between − Within` 이다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

#: 사전지정 §3. 바꾸지 않는다.
PLDDT_MIN, RMSD_MAX, SOLUPROT_MIN = 85.0, 2.0, 0.5
N_TRAIN, SELECTION = 30, "kmeans"
BUDGETS, PRIMARY_B = (40, 60, 80, 100), 80
SEEDS = [42, 123, 7, 2024, 31337]
N_BOOTSTRAP, BOOT_SEED = 2000, 20260921
ARMS = ("unif_rand", "rf_rand", "unif_rf", "rf_rf")


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

def load(cohort_dir: Path, esm_url: str):
    """후보 + joint-pass 라벨 + 백본. 격자 한 곳만 읽는다."""
    cand = {c["sequence_id"]: c
            for c in json.loads((cohort_dir / "candidates.json").read_text("utf-8"))}
    rows = []
    for r in csv.DictReader((cohort_dir / "af2_order_metric.csv").open(encoding="utf-8")):
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
                     "target_id": c["target_id"], "backbone_key": c["backbone_key"],
                     "joint_pass": float(pl >= PLDDT_MIN and rm <= RMSD_MAX
                                         and so >= SOLUPROT_MIN)})
    print(f"후보 {len(rows)} · 표적 {len({r['target_id'] for r in rows})} · "
          f"백본 {len({r['backbone_key'] for r in rows})}", flush=True)

    cache = PROJECT_ROOT / "data" / "benchmark" / f"{cohort_dir.name}_emb_320d.npz"
    digest = hashlib.sha256("\n".join(r["sequence_id"] for r in rows).encode()).hexdigest()
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        if str(z["digest"]) == digest:
            print(f"  임베딩 캐시 {z['embeddings'].shape}", flush=True)
            return rows, z["embeddings"]
    from pipeline_mcp.clients.esm_embedding import LocalHTTPESMEmbeddingClient
    print(f"  임베딩 계산 {len(rows)}", flush=True)
    emb = LocalHTTPESMEmbeddingClient(base_url=esm_url, token=None).embed(
        [r["sequence"] for r in rows])
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, embeddings=emb, digest=digest)
    return rows, emb


# -------------------------------------------------------------- 선택 재생

def allocate_uniform(bbs, k, cap):
    """최대잔여 균등 배분. 후보가 모자라면 그만큼만 준다 (사전지정 §2.1)."""
    out = {b: 0 for b in bbs}
    left, active = k, [b for b in bbs if cap[b] > 0]
    while left > 0 and active:
        q = max(1, left // len(active))
        for b in list(active):
            take = min(q, cap[b] - out[b], left)
            out[b] += take
            left -= take
            if out[b] >= cap[b]:
                active.remove(b)
            if left == 0:
                break
    return out


def replay(y, X, bb_of, B, seed, fit_rank):
    from _selection import select_train_indices
    n = len(y)
    tr = select_train_indices(X, N_TRAIN, seed, SELECTION)
    te = np.setdiff1d(np.arange(n), tr)
    k = B - N_TRAIN
    if k <= 0 or k > len(te):
        return None
    base = float(y[tr].sum())
    rng = np.random.default_rng(seed ^ 0xD3C0)

    pred = fit_rank(X, y, tr, te, seed, estimator="RF")
    order = list(te[np.argsort(-pred, kind="stable")])
    rank = {j: i for i, j in enumerate(order)}

    bbs = sorted(set(bb_of[te]))
    avail = {b: [j for j in te if bb_of[j] == b] for b in bbs}
    cap = {b: len(avail[b]) for b in bbs}

    #: rf/rf 가 실제로 고른 백본별 개수가 A_rf 다 (사전지정 §2.1).
    sel_rf = order[:k]
    A_rf = collections.Counter(bb_of[j] for j in sel_rf)
    A_unif = allocate_uniform(bbs, k, cap)

    def pick(alloc, within_rf):
        out = []
        for b in bbs:
            m = min(int(alloc.get(b, 0)), cap[b])
            if m <= 0:
                continue
            if within_rf:
                out += sorted(avail[b], key=lambda j: (rank[j], j))[:m]
            else:
                out += list(rng.choice(avail[b], size=m, replace=False))
        return out

    got = {"rf_rf": sel_rf,
           "rf_rand": pick(A_rf, False),
           "unif_rf": pick(A_unif, True),
           "unif_rand": pick(A_unif, False)}
    return {a: base + float(y[np.array(v, dtype=int)].sum()) if v else base
            for a, v in got.items()}


# ---------------------------------------------------------------- 집계

def run(rows, emb, label):
    fit_rank = _mod("31_fewshot_jointpass_transfer.py", "m31").fit_rank
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r["target_id"]].append(i)

    per_target = {}
    for tgt, idx in sorted(by.items()):
        idx = np.array(idx)
        y = np.array([rows[i]["joint_pass"] for i in idx], dtype=float)
        if y.min() == y.max():          # informative 규칙 (기존과 동일)
            continue
        X = emb[idx]
        bb = np.array([rows[i]["backbone_key"] for i in idx])
        d = {}
        for B in BUDGETS:
            runs = [replay(y, X, bb, B, s, fit_rank) for s in SEEDS]
            runs = [r for r in runs if r]
            if len(runs) == len(SEEDS):
                d[str(B)] = {a: statistics.mean(r[a] for r in runs) for a in ARMS}
        if d:
            per_target[tgt] = {"n": int(len(idx)), "rate": float(y.mean()),
                               "n_backbones": int(len(set(bb))), "by_budget": d}

    names = sorted(per_target)
    out = {"label": label, "n_targets": len(names), "targets": names,
           "per_target": per_target, "by_budget": {}}

    for B in BUDGETS:
        have = [t for t in names if str(B) in per_target[t]["by_budget"]]
        if len(have) < 2:
            continue
        #: 재표집 집합은 **그 예산을 가진 표적**이어야 한다. 전체에서 뽑으면
        #: 그 예산이 없는 표적(후보 42 개짜리 1 백본 표적)이 섞여 터진다.
        #: 예산마다 다시 만들되 seed 를 고정해 재현성을 지킨다.
        rng = np.random.default_rng(BOOT_SEED)
        boots = [[have[int(rng.integers(len(have)))] for _ in have]
                 for _ in range(N_BOOTSTRAP)]

        def comp(ts, fn):
            return statistics.mean(fn(per_target[t]["by_budget"][str(B)]) for t in ts)

        parts = {
            "Total":   lambda v: v["rf_rf"] - v["unif_rand"],
            "Between": lambda v: v["rf_rand"] - v["unif_rand"],
            "Within":  lambda v: v["unif_rf"] - v["unif_rand"],
        }
        parts["Inter"] = lambda v: (v["rf_rf"] - v["unif_rand"]) \
            - (v["rf_rand"] - v["unif_rand"]) - (v["unif_rf"] - v["unif_rand"])
        parts["Between-Within"] = lambda v: v["rf_rand"] - v["unif_rf"]

        e = {"n_targets": len(have),
             "point": {a: comp(have, (lambda k: (lambda v: v[k]))(a)) for a in ARMS},
             "components": {}}
        for nm, fn in parts.items():
            dr = sorted(comp(b, fn) for b in boots)
            q = lambda p: dr[min(len(dr) - 1, max(0, int(p * len(dr))))]
            e["components"][nm] = {
                "delta": comp(have, fn), "ci95": [q(.025), q(.975)],
                "excludes_zero": bool(q(.025) > 0 or q(.975) < 0),
                "primary": nm == "Between-Within"}
        out["by_budget"][str(B)] = e
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=str(BASE / "hier_confirmatory"),
                    help="격자 디렉터리 (candidates.json + af2_order_metric.csv)")
    ap.add_argument("--label", default="hier_confirmatory_34")
    ap.add_argument("--esm-url", default=_esm_url_default())
    ap.add_argument("--out", default=str(BASE / "selection_gain_decomposition.json"))
    a = ap.parse_args(argv)

    rows, emb = load(Path(a.cohort), a.esm_url)
    res = run(rows, emb, a.label)
    doc = {"purpose": ("서열 선택 이득을 백본 간 / 백본 내 성분으로 가른다. "
                       "새 folding 없음."),
           "prespec": "docs/specs/selection-gain-decomposition-prespec.md",
           "primary_endpoint": "Between-Within", "primary_budget": PRIMARY_B,
           "seeds": SEEDS, "n_train": N_TRAIN,
           "bootstrap": {"n": N_BOOTSTRAP, "seed": BOOT_SEED, "unit": "target"},
           "result": res}

    print(f"\n=== {res['label']} · 표적 {res['n_targets']}")
    for B in BUDGETS:
        e = res["by_budget"].get(str(B))
        if not e:
            continue
        star = " ★" if B == PRIMARY_B else ""
        print(f"  B={B:3d} (표적 {e['n_targets']}){star}")
        for nm in ("Total", "Between", "Within", "Inter", "Between-Within"):
            c = e["components"][nm]
            print(f"      {nm:15s} {c['delta']:+7.2f} "
                  f"[{c['ci95'][0]:+.2f},{c['ci95'][1]:+.2f}] "
                  f"{'0 제외' if c['excludes_zero'] else '0 포함'}")
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"\n{a.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
