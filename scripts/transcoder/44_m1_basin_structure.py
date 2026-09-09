#!/usr/bin/env python3
"""M1 — basin 구조 기술 통계. basin 정의를 고르지 않는다.

무엇을 하는가
-------------
홀드아웃 RFD3 백본들이 서로 얼마나 다른지 기술한다. 후보 basin 정의
(backbone / structural cluster) 가 **얼마나 안정적인지** 확인하는 것이 목적이고,
정의를 고르는 것은 사람이 이 결과를 보고 별도 freeze 문서에서 한다.

하지 않는 것
------------
정책 비교 (adaptive vs static) · FDBC 계산 · yield 나 성공률과의 상관 ·
"결과가 잘 나오는 임계값" 고르기. 이 스크립트는 라벨을 읽지 않는다.

왜 타겟 안에서만 보는가
-----------------------
basin 은 한 타겟의 design space 를 나누는 축이다. 서로 다른 타겟의 백본은
애초에 다른 단백질이라 거리를 재도 basin 질문에 답하지 못한다. 배분 정책이
고르는 것도 한 타겟 안의 arm 들이다.

임계값 격자는 데이터를 보기 전에 정했다
---------------------------------------
아래 THRESHOLDS 는 이 파일이 커밋된 시점에 고정된 값이다. 결과를 보고 격자를
넓히거나 좁히면 사후 선택이 되므로, 바꿔야 한다면 커밋을 남기고 바꾼다.
2.0 Å 이 격자에 있는 것은 RFD3 수용 게이트가 이미 쓰는 값이기 때문이고,
그 값이 basin 경계로 맞다는 뜻이 아니다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import statistics
import subprocess
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID_CSV = BASE / "holdout_grid" / "af2_order_metric.csv"
OUT_JSON = BASE / "m1_basin_structure.json"
DESIGN_ROOT = Path("/opt/protein_pipeline/outputs")

#: 데이터를 보기 전에 고정한 임계값 격자 (Å, CA RMSD).
THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)

#: 두 linkage 를 모두 낸다. 어느 것을 쓸지는 basin 동결에서 정한다 -
#: single 은 사슬처럼 이어져 하나로 뭉치기 쉽고, complete 는 보수적이다.
LINKAGES = ("complete", "single")


def ca_coords(pdb_text: str, chain: str | None = None) -> np.ndarray:
    out = []
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        if chain and line[21] != chain:
            continue
        out.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
    return np.asarray(out, dtype=float)


def kabsch_rmsd(p: np.ndarray, q: np.ndarray) -> float:
    """중심 정렬 + 최적 회전 후 RMSD. 길이가 같아야 한다."""
    p = p - p.mean(axis=0)
    q = q - q.mean(axis=0)
    v, _, wt = np.linalg.svd(p.T @ q)
    if np.linalg.det(v @ wt) < 0.0:
        v[:, -1] *= -1.0
    return float(np.sqrt(((p @ (v @ wt) - q) ** 2).sum() / len(p)))


def cluster_count(dist: dict[tuple[str, str], float], keys: list[str],
                  threshold: float, linkage: str) -> list[list[str]]:
    """임계값 아래를 같은 군으로 묶는다. 외부 의존 없이 직접 구현한다."""
    clusters = [[k] for k in keys]

    def between(a: list[str], b: list[str]) -> float:
        vals = [dist[(x, y)] if (x, y) in dist else dist[(y, x)] for x in a for y in b]
        return max(vals) if linkage == "complete" else min(vals)

    merged = True
    while merged and len(clusters) > 1:
        merged = False
        best, pair = None, None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = between(clusters[i], clusters[j])
                if d <= threshold and (best is None or d < best):
                    best, pair = d, (i, j)
        if pair is not None:
            i, j = pair
            clusters[i] = clusters[i] + clusters[j]
            clusters.pop(j)
            merged = True
    return clusters


def load_backbones() -> dict[str, dict[str, np.ndarray]]:
    """격자가 실제로 쓴 RFD3 백본만 읽는다."""
    used = collections.defaultdict(set)
    for row in csv.DictReader(GRID_CSV.open(encoding="utf-8")):
        if row["backbone_source"] != "rfd3":
            continue
        target, _, stem = row["backbone_key"].split("|")
        used[target].add(stem)
    out: dict[str, dict[str, np.ndarray]] = {}
    missing = []
    for target, stems in sorted(used.items()):
        designs = DESIGN_ROOT / f"holdout_{target}_rfd3" / "rfd3" / "designs"
        got = {}
        for stem in sorted(stems):
            path = designs / f"{stem}.pdb"
            if not path.exists():
                missing.append(str(path))
                continue
            coords = ca_coords(path.read_text(errors="replace"))
            if len(coords):
                got[stem] = coords
        if got:
            out[target] = got
    if missing:
        print(f"  주의: 백본 파일 {len(missing)} 개를 찾지 못했다 - {missing[:2]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_JSON))
    args = ap.parse_args()

    backbones = load_backbones()
    print(f"타겟 {len(backbones)} · 백본 {sum(len(v) for v in backbones.values())}")

    per_target, all_pairs, length_mismatch = {}, [], []
    for target, bbs in sorted(backbones.items()):
        keys = sorted(bbs)
        dist: dict[tuple[str, str], float] = {}
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                if len(bbs[a]) != len(bbs[b]):
                    # 조용히 자르지 않는다. 길이가 다르면 대응이 정의되지 않는다.
                    length_mismatch.append(
                        {"target": target, "a": a, "b": b,
                         "n_a": len(bbs[a]), "n_b": len(bbs[b])})
                    continue
                dist[(a, b)] = kabsch_rmsd(bbs[a], bbs[b])
        if not dist:
            continue
        vals = sorted(dist.values())
        all_pairs.extend(vals)
        entry = {
            "n_backbones": len(keys), "n_pairs": len(vals),
            "rmsd": {"min": round(vals[0], 3), "median": round(statistics.median(vals), 3),
                     "max": round(vals[-1], 3)},
            "clusters": {},
        }
        for linkage in LINKAGES:
            entry["clusters"][linkage] = {
                str(t): len(cluster_count(dist, keys, t, linkage)) for t in THRESHOLDS}
        per_target[target] = entry

    # 전체 분포
    overall = {
        "n_pairs": len(all_pairs),
        "min": round(min(all_pairs), 3), "max": round(max(all_pairs), 3),
        "median": round(statistics.median(all_pairs), 3),
        "quartiles": [round(float(np.percentile(all_pairs, q)), 3) for q in (25, 75)],
    }
    # 임계값별 총 클러스터 수와 안정성
    stability = {}
    for linkage in LINKAGES:
        counts = {t: sum(per_target[x]["clusters"][linkage][str(t)] for x in per_target)
                  for t in THRESHOLDS}
        total_bb = sum(per_target[x]["n_backbones"] for x in per_target)
        singleton = {}
        for t in THRESHOLDS:
            n_single = 0
            for target, bbs in sorted(backbones.items()):
                if target not in per_target:
                    continue
                keys = sorted(bbs)
                dist = {}
                for i, a in enumerate(keys):
                    for b in keys[i + 1:]:
                        if len(bbs[a]) == len(bbs[b]):
                            dist[(a, b)] = kabsch_rmsd(bbs[a], bbs[b])
                n_single += sum(1 for c in cluster_count(dist, keys, t, linkage) if len(c) == 1)
            singleton[str(t)] = round(n_single / total_bb, 4)
        stability[linkage] = {
            "total_clusters_by_threshold": {str(t): counts[t] for t in THRESHOLDS},
            "singleton_fraction_by_threshold": singleton,
            "collapses_to_one_at": next(
                (str(t) for t in THRESHOLDS
                 if all(per_target[x]["clusters"][linkage][str(t)] == 1 for x in per_target)),
                None),
            "all_distinct_up_to": next(
                (str(t) for t in reversed(THRESHOLDS)
                 if all(per_target[x]["clusters"][linkage][str(t)]
                        == per_target[x]["n_backbones"] for x in per_target)),
                None),
        }

    print(f"\n타겟 내 쌍별 CA RMSD (n={overall['n_pairs']}): "
          f"중앙값 {overall['median']} Å · 범위 {overall['min']}–{overall['max']} Å")
    for linkage in LINKAGES:
        st = stability[linkage]
        print(f"\n[{linkage} linkage] 임계값별 총 클러스터 수 "
              f"(백본 {sum(per_target[x]['n_backbones'] for x in per_target)} 개 기준)")
        for t in THRESHOLDS:
            c = st["total_clusters_by_threshold"][str(t)]
            s = st["singleton_fraction_by_threshold"][str(t)]
            print(f"   {t:>4} Å  클러스터 {c:>3}  싱글턴 비율 {s:.2f}")
        print(f"   전부 개별로 남는 최대 임계값: {st['all_distinct_up_to']}")
        print(f"   모든 타겟이 1 개로 합쳐지는 최소 임계값: {st['collapses_to_one_at']}")

    out = {
        "purpose": "M1 - basin 구조 기술 통계. basin 정의를 고르지 않는다.",
        "does_not_do": ["정책 비교", "FDBC 계산", "yield/성공률과의 상관",
                        "임계값 사후 선택"],
        "reads_labels": False,
        "scope": "타겟 안의 RFD3 백본끼리만. 다른 타겟의 백본은 다른 단백질이라 "
                 "basin 질문에 답하지 못한다.",
        "metric": "CA RMSD, Kabsch 중첩, 같은 길이일 때만",
        "thresholds_fixed_before_data": list(THRESHOLDS),
        "linkages": list(LINKAGES),
        "overall_within_target_rmsd": overall,
        "per_target": per_target,
        "stability": stability,
        "length_mismatch_pairs": length_mismatch,
        "how_to_read": {
            "stable": "임계값을 조금 움직여도 클러스터 수가 완만하면, 그 구간 "
                      "어디를 잡아도 같은 구조를 본다는 뜻이다.",
            "fragile": "급변하면 그 정의는 basin 축으로 쓰기에 취약하다.",
            "next_step": "이 결과를 보고 사람이 basin 정의를 고르고 별도 freeze "
                         "문서에 못 박는다. 이 스크립트는 고르지 않는다.",
        },
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
