#!/usr/bin/env python3
"""EFBC 가 오르면 구조 다양성도 오르는가 - threshold-free 연속 진단.

규칙은 `docs/specs/coverage-preserving-prespec.md` §6 에 결과 확인 전 동결돼
있다. 여기서 그 문서에 없는 선택을 새로 하지 않는다.

**EFBC 가 높다고 structural diversity 가 높다고 주장하지 않는다.** EFBC 는
feasible mass 가 backbone design context 사이에 얼마나 퍼져 있는지를 재는
operational 지표일 뿐이다. 구조적 다양성은 여기서 따로 본다.

    1. context-level dispersion   feasible 후보가 있는 백본을 하나씩 써서
                                  pairwise CA-RMSD (Kabsch 중첩)
    2. mass-weighted dispersion   백본별 feasible mass 로 가중
    3. 거리 분포와 분위수를 함께 보고한다
    4. clustering 은 탐색적 민감도로만 (M1 에서 threshold/linkage 불안정)

해석 규칙도 §6 에 미리 적혀 있다.

    EFBC 상승 · dispersion 상승   coverage 증가가 greater structural
                                  dispersion 과 동반되었다고 보고
    EFBC 상승 · dispersion 불변   operational coverage 증가는 확인되었으나
                                  measurable structural diversification 으로
                                  이어지지 않았다고 보고
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
PROJECT_ROOT = HERE.parents[1]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

QUANTILES = (0.05, 0.25, 0.50, 0.75, 0.95)
#: 탐색적 민감도로만 쓴다. 배분 단위로 쓰지 않는다 (사전지정 §9).
EXPLORATORY_THRESHOLDS = (1.5, 2.0, 3.0)


def _m40():
    s = importlib.util.spec_from_file_location(
        "m40", HERE / "40_coverage_preserving.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


# ------------------------------------------------------------- 좌표 · RMSD

def ca_coords(pdb: Path) -> np.ndarray:
    xs = []
    with pdb.open(encoding="utf-8", errors="replace") as fh:
        for l in fh:
            if l.startswith("ATOM") and l[12:16].strip() == "CA":
                xs.append((float(l[30:38]), float(l[38:46]), float(l[46:54])))
    return np.asarray(xs, dtype=float)


def kabsch_rmsd(P: np.ndarray, Q: np.ndarray) -> float:
    """최적 강체 중첩 후 CA-RMSD. 길이가 다르면 NaN 을 돌려준다."""
    if P.shape != Q.shape or len(P) == 0:
        return float("nan")
    P = P - P.mean(0)
    Q = Q - Q.mean(0)
    V, _, Wt = np.linalg.svd(P.T @ Q)
    if np.linalg.det(V @ Wt) < 0:          # 거울상 배제
        V[:, -1] *= -1
    return float(np.sqrt(((P @ (V @ Wt) - Q) ** 2).sum() / len(P)))


def pairwise(bb_pdb: dict) -> tuple[list, np.ndarray]:
    keys = sorted(bb_pdb)
    xyz = {k: ca_coords(Path(bb_pdb[k])) for k in keys}
    n = len(keys)
    D = np.full((n, n), np.nan)
    for i in range(n):
        D[i, i] = 0.0
        for j in range(i + 1, n):
            D[i, j] = D[j, i] = kabsch_rmsd(xyz[keys[i]], xyz[keys[j]])
    return keys, D


# ------------------------------------------------------------- 분산 요약

def dispersion(keys, D, weights: dict) -> dict | None:
    """가중 · 비가중 pairwise dispersion. 백본이 2 개 미만이면 정의하지 않는다."""
    live = [i for i, k in enumerate(keys) if weights.get(k, 0) > 0]
    if len(live) < 2:
        return None
    d, ww = [], []
    for a in range(len(live)):
        for b in range(a + 1, len(live)):
            i, j = live[a], live[b]
            if math.isnan(D[i, j]):
                continue
            d.append(D[i, j])
            ww.append(weights[keys[i]] * weights[keys[j]])
    if not d:
        return None
    d, ww = np.asarray(d), np.asarray(ww, dtype=float)
    return {"n_contexts": len(live), "n_pairs": len(d),
            "mean_unweighted": float(d.mean()),
            "mean_mass_weighted": float((d * ww).sum() / ww.sum()) if ww.sum() > 0
            else float(d.mean()),
            "quantiles": {str(q): float(np.quantile(d, q)) for q in QUANTILES},
            "distances": [round(float(x), 4) for x in d]}


def exploratory_clusters(keys, D, weights) -> dict:
    """단일 연결 threshold 클러스터 수. 탐색적 민감도로만 읽는다."""
    live = [i for i, k in enumerate(keys) if weights.get(k, 0) > 0]
    out = {}
    for th in EXPLORATORY_THRESHOLDS:
        parent = {i: i for i in live}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a in range(len(live)):
            for b in range(a + 1, len(live)):
                i, j = live[a], live[b]
                if not math.isnan(D[i, j]) and D[i, j] <= th:
                    parent[find(i)] = find(j)
        out[f"{th}A"] = len({find(i) for i in live}) if live else 0
    return out


# ------------------------------------------------------------------ 본체

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=str(BASE / "hier_confirmatory"))
    ap.add_argument("--label", default="hier_confirmatory_34")
    ap.add_argument("--out", default=str(BASE / "structural_dispersion.json"))
    a = ap.parse_args(argv)

    m40 = _m40()
    cohort = Path(a.cohort)
    tgts = m40.load(cohort)

    bb_pdb = {}
    for c in json.loads((cohort / "candidates.json").read_text(encoding="utf-8")):
        bb_pdb.setdefault(c["backbone_key"], c["backbone_pdb"])

    geom, per_target = {}, {}
    for t, bbs in tgts.items():
        keys, D = pairwise({k: bb_pdb[k] for k in bbs if k in bb_pdb})
        geom[t] = (keys, D)
        #: 격자 전체가 보는 feasible mass - 정책과 무관한 기준선
        mass = {k: sum(c["joint"] for c in bbs[k]) for k in keys}
        per_target[t] = {
            "n_backbones": len(keys),
            "grid_feasible_contexts": sum(1 for k in keys if mass[k] > 0),
            "all_contexts": dispersion(keys, D, {k: 1.0 for k in keys}),
            "grid_feasible": dispersion(keys, D, mass),
            "exploratory_clusters": exploratory_clusters(keys, D, mass),
            "by_budget": {}}

    #: 정책별로 실제 확보한 feasible mass 에 대해 같은 진단을 돌린다.
    for B in m40.BUDGETS:
        for t, bbs in tgts.items():
            keys, D = geom[t]
            acc = collections.defaultdict(list)
            for s in m40.SEEDS:
                for p in ("coverage_v2", "static_equal", "greedy_fill"):
                    r = m40.replay(bbs, B, s, p)
                    w = dict(zip(list(bbs), r["_f"])) if "_f" in r else None
                    if w is None:
                        continue
                    d = dispersion(keys, D, w)
                    if d:
                        acc[p].append((d["mean_unweighted"], d["mean_mass_weighted"],
                                       d["n_contexts"]))
            per_target[t]["by_budget"][str(B)] = {
                p: {"mean_unweighted": statistics.mean(x[0] for x in v),
                    "mean_mass_weighted": statistics.mean(x[1] for x in v),
                    "n_contexts": statistics.mean(x[2] for x in v),
                    "n_seeds_defined": len(v)}
                for p, v in acc.items() if v}

    names = sorted(per_target)
    rng = np.random.default_rng(m40.BOOT_SEED)
    boots = [[names[int(rng.integers(len(names)))] for _ in names]
             for _ in range(m40.N_BOOTSTRAP)]
    by_budget = {}
    for B in m40.BUDGETS:
        key = str(B)

        def mean(ts, p, m):
            v = [per_target[t]["by_budget"][key][p][m] for t in ts
                 if p in per_target[t]["by_budget"][key]]
            return statistics.mean(v) if v else float("nan")

        pols = ("coverage_v2", "static_equal", "greedy_fill")
        e = {"point": {p: {m: mean(names, p, m)
                           for m in ("mean_unweighted", "mean_mass_weighted",
                                     "n_contexts")} for p in pols},
             "contrasts": {}}
        for comp in ("static_equal", "greedy_fill"):
            for m in ("mean_unweighted", "mean_mass_weighted"):
                dr = sorted(x for x in (mean(b, "coverage_v2", m) - mean(b, comp, m)
                                        for b in boots) if not math.isnan(x))
                if not dr:
                    continue
                lo, hi = dr[int(.025 * len(dr))], dr[int(.975 * len(dr))]
                e["contrasts"][f"{m} | coverage_v2 - {comp}"] = {
                    "delta": mean(names, "coverage_v2", m) - mean(names, comp, m),
                    "ci95": [lo, hi], "excludes_zero": bool(lo > 0 or hi < 0)}
        by_budget[key] = e

    pooled = [x for t in names if per_target[t]["all_contexts"]
              for x in per_target[t]["all_contexts"]["distances"]]
    doc = {"purpose": ("EFBC 상승이 구조 다양성 상승과 동반되는지 본다. "
                       "EFBC 를 structural diversity metric 이라고 부르지 않는다."),
           "prespec": "docs/specs/coverage-preserving-prespec.md §6",
           "representative": "backbone 당 설계 backbone PDB 1 개 · Kabsch CA-RMSD",
           "label": a.label, "n_targets": len(names),
           "pooled_backbone_distance": {
               "n_pairs": len(pooled),
               "mean": statistics.mean(pooled) if pooled else None,
               "quantiles": {str(q): float(np.quantile(pooled, q)) for q in QUANTILES}
               if pooled else None},
           "by_budget": by_budget, "per_target": per_target}

    q = doc["pooled_backbone_distance"]["quantiles"] or {}
    print(f"\n=== {a.label} · 표적 {len(names)}")
    print(f"  표적 내 백본 쌍 CA-RMSD  n={doc['pooled_backbone_distance']['n_pairs']} "
          f"평균 {doc['pooled_backbone_distance']['mean']:.2f} A · "
          + " ".join(f"q{int(float(k)*100)} {v:.2f}" for k, v in q.items()))
    for B in m40.BUDGETS:
        e = by_budget[str(B)]
        star = " ★" if B == m40.PRIMARY_B else ""
        print(f"\n  B={B:3d}{star}")
        for p, v in e["point"].items():
            print(f"      {p:16s} context {v['n_contexts']:4.1f} · 비가중 "
                  f"{v['mean_unweighted']:5.2f} A · 가중 {v['mean_mass_weighted']:5.2f} A")
        for k, c in e["contrasts"].items():
            print(f"      {k:44s} {c['delta']:+6.3f} "
                  f"[{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}] "
                  f"{'0 제외' if c['excludes_zero'] else '0 포함'}")
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"\n{a.out}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
