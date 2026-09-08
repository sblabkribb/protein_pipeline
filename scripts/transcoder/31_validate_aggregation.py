#!/usr/bin/env python3
"""응집 휴리스틱을 우리가 가진 라벨에 대조한다 (수렴 타당도).

무엇을 주장할 수 있고 없는가
----------------------------
응집이 측정된 코호트가 없다. 그래서 이 스크립트는 **보정이 아니다.** 임계값을
정하지 않고 `calibrated` 를 바꾸지도 않는다.

할 수 있는 것은 하나다: 응집 성향 지표가 우리가 실제로 측정한 용해도(SoluProt)
와 같은 방향으로 움직이는지 본다. 응집과 용해도는 다른 성질이지만 반대 방향의
관계가 기대된다. 관계가 아예 없거나 반대 부호면 그 지표는 단량체 설계에서
무엇을 재는지 알 수 없다는 뜻이고, 게이트 후보에서 빠진다.

관계가 보여도 그것으로 통과 기준을 정할 수는 없다. SoluProt 은 응집 측정이
아니라 또 하나의 예측기다. 두 예측기가 같은 방향이면 필요조건은 만족하지만
충분조건은 아니다.

클러스터링
----------
설계는 백본 안에, 백본은 타겟 안에 중첩되어 있다. 상관을 설계 단위로 재표집하면
구간이 부당하게 좁아진다. 타겟으로 클러스터링한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.liabilities import (  # noqa: E402
    aggregation_prone_fraction, max_hydrophobic_patch, motif_counts, net_charge,
)

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
METRICS = ("aggregation_prone_fraction", "max_hydrophobic_patch", "net_charge")


def spearman(xs, ys) -> float | None:
    if len(xs) < 3:
        return None

    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            mean_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = mean_rank
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def clustered_bootstrap(rows, metric, *, repeats, seed):
    """타겟 단위로 재표집한다. 설계 단위로 재표집하면 구간이 좁아진다."""
    by_target = {}
    for row in rows:
        by_target.setdefault(row["target_id"], []).append(row)
    targets = sorted(by_target)
    rng = random.Random(seed)
    values = []
    for _ in range(repeats):
        drawn = [by_target[rng.choice(targets)] for _ in targets]
        flat = [r for group in drawn for r in group]
        rho = spearman([r[metric] for r in flat], [r["soluprot"] for r in flat])
        if rho is not None:
            values.append(rho)
    values.sort()
    if not values:
        return None
    lo = values[int(0.025 * len(values))]
    hi = values[min(len(values) - 1, int(0.975 * len(values)))]
    return {"ci95": [round(lo, 4), round(hi, 4)],
            "p_negative": round(sum(1 for v in values if v < 0) / len(values), 4)}


def load(paths) -> list[dict]:
    rows = []
    for path in paths:
        for row in csv.DictReader(Path(path).open(encoding="utf-8")):
            sequence = (row.get("sequence") or "").replace("X", "")
            solu = row.get("soluprot")
            if not sequence or solu in (None, "", "None"):
                continue
            patch = max_hydrophobic_patch(sequence)
            if patch is None:
                continue
            rows.append({
                "target_id": row["target_id"], "backbone_key": row["backbone_key"],
                "soluprot": float(solu),
                "aggregation_prone_fraction": aggregation_prone_fraction(sequence),
                "max_hydrophobic_patch": patch,
                "net_charge": net_charge(sequence),
                **{f"motif_{k}": v for k, v in motif_counts(sequence).items()},
            })
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequences", action="append", default=[])
    parser.add_argument("--repeats", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--out", default=str(BASE / "aggregation_validation.json"))
    args = parser.parse_args(argv)

    paths = args.sequences or [BASE / "temperature_sweep" / "sequences.csv",
                               BASE / "temperature_panel2" / "sequences.csv"]
    rows = load(paths)
    targets = {r["target_id"] for r in rows}
    print(f"설계 {len(rows)} · 백본 {len({r['backbone_key'] for r in rows})} "
          f"· 타겟 {len(targets)}")

    report = {
        "purpose": "응집 휴리스틱이 측정된 용해도와 같은 방향인지 본다",
        "claim_limits": [
            "보정이 아니다. 임계값을 정하지 않고 calibrated 를 바꾸지 않는다.",
            "SoluProt 은 응집 측정이 아니라 또 하나의 예측기다. 두 예측기가 같은 "
            "방향이면 필요조건이지 충분조건이 아니다.",
            "응집이 측정된 코호트를 얻기 전까지 이 지표는 게이트가 아니다.",
        ],
        "n_designs": len(rows), "n_targets": len(targets),
        "cluster_unit": "target_id", "repeats": args.repeats, "seed": args.seed,
        "expected_sign": {"aggregation_prone_fraction": "음 (응집 성향이 높을수록 용해도 낮음)",
                          "max_hydrophobic_patch": "음",
                          "net_charge": "부호 예측 없음 - 절댓값이 클수록 용해도가 높다는 "
                                        "보고가 있으나 단량체에서는 확인된 바 없다"},
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics": {},
    }

    print(f"\n{'지표':28s} {'rho':>8} {'CI95':>20} {'P(rho<0)':>9}")
    for metric in METRICS:
        rho = spearman([r[metric] for r in rows], [r["soluprot"] for r in rows])
        boot = clustered_bootstrap(rows, metric, repeats=args.repeats, seed=args.seed)
        report["metrics"][metric] = {"spearman": round(rho, 4) if rho else None, **(boot or {})}
        ci = f"[{boot['ci95'][0]:+.3f}, {boot['ci95'][1]:+.3f}]" if boot else "-"
        pn = f"{boot['p_negative']:.3f}" if boot else "-"
        print(f"{metric:28s} {rho:+8.4f} {ci:>20} {pn:>9}")

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
