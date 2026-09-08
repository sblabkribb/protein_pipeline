#!/usr/bin/env python3
"""구조 성공의 분산을 타겟·백본·서열 수준으로 나눈다.

왜 저장하는가
-------------
RAPID 가 개별 서열 랭킹에만 매달리지 않고 백본·생성조건 수준에서 먼저 계산을
배분하는 이유를 정량으로 설명한다. 부수 결과가 아니라 설계 근거다.

표현에 주의할 것
----------------
이 값은 **현재 코호트의 분산 분해**다. "구조 성공의 64%가 백본 수준에서
결정된다" 로 쓰면 안 된다. 맞는 표현은 "이 코호트의 분산 분해에서 64.2% 가
타겟 및 백본 수준 차이에 귀속되었다" 다.

포화 백본도 마찬가지다. "어떤 서열 수준 예측기도 원리적으로 쓸모없다" 가 아니라
"관측된 후보군에서는 서열 랭킹으로 구분할 수 있는 변이가 없었다" 다. 서열을 더
생성하면 달라질 가능성까지 막는 주장이 아니다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.protocol import GATE0_THRESHOLDS  # noqa: E402

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
PANELS = ("temperature_sweep", "temperature_panel2")


def load() -> list[dict]:
    rows = []
    for panel in PANELS:
        path = BASE / panel / "af2_order_metric.csv"
        for r in csv.DictReader(path.open(encoding="utf-8")):
            if r.get("status") != "ok":
                continue
            try:
                plddt, rmsd = float(r["plddt"]), float(r["rmsd_nonloop_order"])
            except (TypeError, ValueError, KeyError):
                continue
            rows.append({
                "target_id": r["target_id"], "backbone_key": r["backbone_key"],
                "panel": panel,
                "label": float(plddt >= GATE0_THRESHOLDS["plddt_min"]
                               and rmsd <= GATE0_THRESHOLDS["rmsd_max"]),
            })
    return rows


def decompose(rows) -> dict:
    y = np.array([r["label"] for r in rows])
    by_target = collections.defaultdict(list)
    by_backbone = collections.defaultdict(list)
    for i, row in enumerate(rows):
        by_target[row["target_id"]].append(i)
        by_backbone[row["backbone_key"]].append(i)

    grand = y.mean()
    total = float(((y - grand) ** 2).sum())
    ss_target = sum(len(ix) * (y[ix].mean() - grand) ** 2 for ix in by_target.values())

    ss_backbone = 0.0
    for ix in by_target.values():
        target_mean = y[ix].mean()
        subs = collections.defaultdict(list)
        for i in ix:
            subs[rows[i]["backbone_key"]].append(i)
        ss_backbone += sum(len(s) * (y[s].mean() - target_mean) ** 2 for s in subs.values())

    ss_sequence = sum(float(((y[ix] - y[ix].mean()) ** 2).sum())
                      for ix in by_backbone.values())

    saturated = [k for k, ix in by_backbone.items() if y[ix].mean() in (0.0, 1.0)]
    n_saturated_designs = sum(len(by_backbone[k]) for k in saturated)
    varying = [ix for k, ix in by_backbone.items() if k not in set(saturated)]
    rates = [float(y[ix].mean()) for ix in varying]

    return {
        "n_designs": len(rows), "n_targets": len(by_target),
        "n_backbones": len(by_backbone),
        "overall_success_rate": round(float(grand), 4),
        "components": {
            "target_level": round(ss_target / total, 4),
            "backbone_within_target": round(ss_backbone / total, 4),
            "sequence_within_backbone": round(ss_sequence / total, 4),
        },
        "attributed_to_target_and_backbone": round((ss_target + ss_backbone) / total, 4),
        "saturated_backbones": {
            "n": len(saturated), "of": len(by_backbone),
            "fraction": round(len(saturated) / len(by_backbone), 4),
            "designs": n_saturated_designs,
            "designs_fraction": round(n_saturated_designs / len(rows), 4),
            "reading": ("관측된 후보군에서 이 백본들은 서열 랭킹으로 구분할 수 있는 "
                        "변이를 보이지 않았다. 서열을 더 생성하면 달라질 가능성을 "
                        "배제하는 것은 아니다."),
        },
        "varying_backbones": {
            "n": len(varying),
            "designs": sum(len(ix) for ix in varying),
            "median_success_rate": round(float(np.median(rates)), 4) if rates else None,
            "range": [round(min(rates), 4), round(max(rates), 4)] if rates else None,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(BASE / "variance_decomposition_structural.json"))
    args = parser.parse_args(argv)

    rows = load()
    result = decompose(rows)

    print(f"구조 성공 분산 분해 · 설계 {result['n_designs']} · 타겟 "
          f"{result['n_targets']} · 백본 {result['n_backbones']}")
    for name, key in (("타겟 수준", "target_level"),
                      ("타겟 내 백본 수준", "backbone_within_target"),
                      ("백본 내 서열 수준", "sequence_within_backbone")):
        print(f"  {name:20s} {result['components'][key]:6.1%}")
    sat = result["saturated_backbones"]
    print(f"\n관측된 후보군에서 변이가 없던 백본 {sat['n']}/{sat['of']} "
          f"({sat['fraction']:.0%}) · 설계 {sat['designs']}/{result['n_designs']} "
          f"({sat['designs_fraction']:.0%})")
    var = result["varying_backbones"]
    print(f"서열 선택이 의미 있는 백본 {var['n']} · 설계 {var['designs']} · "
          f"성공률 중앙값 {var['median_success_rate']}")

    report = {
        "purpose": ("RAPID 이 서열 랭킹에만 의존하지 않고 백본·생성조건 수준에서 먼저 "
                    "계산을 배분하는 이유의 정량 근거"),
        "label": f"pLDDT >= {GATE0_THRESHOLDS['plddt_min']} AND "
                 f"rmsd_nonloop_order <= {GATE0_THRESHOLDS['rmsd_max']}",
        "how_to_state_this": {
            "correct": "이 코호트의 분산 분해에서 "
                       f"{result['attributed_to_target_and_backbone']:.1%} 가 타겟 및 "
                       "백본 수준 차이에 귀속되었다",
            "incorrect": "구조 성공의 64% 가 백본 수준에서 결정된다",
            "why": "분산 분해는 관측된 코호트의 귀속이지 인과적 결정이 아니다",
        },
        **result,
        "limits": [
            "타겟 20 개, 백본 37 개의 한 코호트다.",
            "서열은 ProteinMPNN 이 T=0.05~0.3 에서 만든 것이다. 다른 생성기나 더 넓은 "
            "온도 범위에서는 서열 수준 성분이 달라질 수 있다.",
            "이진 결과의 제곱합 분해다. 혼합모형 분산성분과 정확히 같지 않다.",
        ],
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
