#!/usr/bin/env python3
"""선택 집합이 몇 개 백본에서 나왔는가 — 사후 기술 진단.

**판정이 아니다.** 사전지정(`depth-scaling-pilot-prespec.md` §7)은 EFBC 계산을
금지한다. 여기서 재는 것은 EFBC(엔트로피 기반 coverage 종점)가 아니라 선택된
후보가 **닿은 서로 다른 백본 수**와 **한 백본에 몰린 최대 비중**이라는 단순
기술 통계이고, 동결된 주 비교를 바꾸지 않는다.

왜 재는가
---------
"서열만 보는 surrogate 는 백본 다양성을 못 볼 것" 이라는 우려가 자연스럽다.
그런데 `rf_only` 는 백본을 모르고 전역 점수로만 고르는 반면 `greedy_fill` 은
posterior 상위 백본부터 정원까지 꽉 채운다. 어느 쪽이 실제로 좁은지는
측정해야 알 수 있다.

문서 §5.3 이 "greedy 가 탐색 폭을 줄일 위험" 이라고만 적고 있어 그 위험이
실제로 일어나는지 수치로 확인한다.
"""

from __future__ import annotations

import argparse
import collections
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
OUT = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "backbone_spread.json"

DEPTH, BUDGET, SENTINEL = 42, 80, 4


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esm-url", default=_esm_url_default())
    a = ap.parse_args(argv)

    m37 = _mod("37_depth_scaling.py", "m37")
    fit = _mod("31_fewshot_jointpass_transfer.py", "m31").fit_rank
    rows, emb = m37.load(a.esm_url)
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r["target_id"]].append(i)

    acc = collections.defaultdict(list)
    for tgt, idx in sorted(by.items()):
        idx = np.array(idx)
        y = np.array([rows[i]["joint_pass"] for i in idx], dtype=float)
        if y.min() == y.max():
            continue
        X = emb[idx]
        bb = np.array([rows[i]["backbone_key"] for i in idx])
        bbs = sorted(set(bb))
        members = {b: np.flatnonzero(bb == b) for b in bbs}
        for seed in m37.SEEDS:
            rng = np.random.default_rng(seed)
            warm = []
            for b in bbs:
                warm += list(rng.choice(members[b],
                                        size=min(SENTINEL, len(members[b])),
                                        replace=False))
            warm = np.array(sorted(warm))
            A = BUDGET - len(warm)
            rest = np.setdiff1d(np.arange(len(y)), warm)
            if A < 0 or A > len(rest):
                continue
            wset = set(warm.tolist())
            avail = {b: [j for j in members[b] if j not in wset] for b in bbs}
            cap = {b: max(0, min(DEPTH, len(members[b])) - SENTINEL) for b in bbs}
            cap = {b: min(cap[b], len(avail[b])) for b in bbs}
            pred = fit(X, y, warm, rest, seed, estimator="RF")
            order = list(rest[np.argsort(-pred, kind="stable")])
            rank = {j: i for i, j in enumerate(order)}
            wa = {b: np.intersect1d(members[b], warm) for b in bbs}
            post = {b: (y[wa[b]].sum() + 1) / (len(wa[b]) + 2) for b in bbs}

            sel = {"rf_only": order[:A]}
            s, left = [], A
            for b in sorted(bbs, key=lambda x: (-post[x], x)):
                if left <= 0:
                    break
                k = min(cap[b], left)
                s += sorted(avail[b], key=lambda j: (rank[j], j))[:k]
                left -= k
            sel["greedy_fill"] = s

            for name, picks in sel.items():
                used = collections.Counter(bb[j] for j in picks)
                acc[name].append({"target": tgt, "seed": seed,
                                  "n_backbones_touched": len(used),
                                  "max_share": max(used.values()) / max(len(picks), 1),
                                  "n_backbones_available": len(bbs)})

    out = {"purpose": ("선택 집합이 닿은 백본 수와 최대 편중. **사후 기술 진단**"
                       "이며 EFBC 가 아니고 판정에 쓰지 않는다."),
           "post_hoc": True, "judgement": False, "is_efbc": False,
           "depth": DEPTH, "budget": BUDGET, "policies": {}}
    print(f"\n선택 {BUDGET - 40}개가 닿은 백본 (깊이 {DEPTH})")
    print(f"  {'정책':16s}{'서로 다른 백본':>14}{'최대 한 백본 비중':>18}")
    for name, v in acc.items():
        nb = statistics.mean(x["n_backbones_touched"] for x in v)
        ms = statistics.mean(x["max_share"] for x in v)
        out["policies"][name] = {"mean_backbones_touched": nb,
                                 "mean_max_share": ms,
                                 "n_observations": len(v), "per_run": v}
        print(f"  {name:16s}{nb:14.1f}{ms * 100:17.0f}%")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
