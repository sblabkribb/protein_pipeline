#!/usr/bin/env python3
"""Temperature AF2 결과를 백본 clustered bootstrap 으로 비교하고 중단 여부를 판정한다.

primary endpoint: structural_yield, joint_yield
secondary       : SoluProt, diversity

480 서열은 독립 표본이 아니다. 실제 독립 단위는 백본 15개이므로 재표집을 백본
단위로 한다. 서열 단위로 재표집하면 구간이 실제보다 좁게 나온다.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.clustered import clustered_bootstrap  # noqa: E402
from rapid_sr.protocol import GATE0_THRESHOLDS  # noqa: E402

REFERENCE_T = "0.1"
# 효과가 명확하다고 부르기 위한 최소 구간 정밀도. yield 차이 0.05 는
# 백본당 8 서열에서 실질적으로 구분 가능한 최소 단위에 가깝다.
CI_WIDTH_TARGET = 0.10


def decide_next_step(entry: dict, *, ci_width_target: float = CI_WIDTH_TARGET) -> str:
    """1단계 480 이후 무엇을 할지.

    - 효과가 유의하고 구간이 충분히 좁다  -> 종료
    - 구간이 넓다                        -> 나머지 480 추가
    - 유의하지 않고 구간이 이미 좁다      -> 추가 AF2 중단
    """
    ci = entry.get("ci95")
    if not ci:
        return "add_second_half"
    width = float(ci[1]) - float(ci[0])
    if entry.get("excludes_zero"):
        return "stop_effect_confirmed" if width <= ci_width_target else "add_second_half"
    return "stop_no_effect" if width <= ci_width_target else "add_second_half"


def load(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [r for r in csv.DictReader(handle) if r.get("status") == "ok"]


def _num(row, key):
    value = row.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def annotate(rows: list[dict]) -> list[dict]:
    for row in rows:
        plddt, rmsd, solu = _num(row, "plddt"), _num(row, "rmsd"), _num(row, "soluprot")
        structural = (
            None if plddt is None or rmsd is None
            else float(plddt >= GATE0_THRESHOLDS["plddt_min"]
                       and rmsd <= GATE0_THRESHOLDS["rmsd_max"])
        )
        row["_structural"] = structural
        row["_joint"] = (
            None if structural is None or solu is None
            else float(structural > 0 and solu >= GATE0_THRESHOLDS["soluprot_min"])
        )
        row["_soluprot"] = solu
    return rows


def paired_yield_difference(rows: list[dict], temp: str, field: str) -> dict:
    """백본별로 (temp 의 yield) - (기준 T 의 yield) 를 구하고 백본 단위로 재표집."""
    by = defaultdict(lambda: defaultdict(list))
    for row in rows:
        value = row.get(field)
        if value is not None:
            by[row["backbone_key"]][row["temperature"]].append(float(value))

    backbones, diffs = [], []
    for backbone, per_temp in by.items():
        if REFERENCE_T not in per_temp or temp not in per_temp:
            continue
        backbones.append(backbone)
        diffs.append(float(np.mean(per_temp[temp]) - np.mean(per_temp[REFERENCE_T])))
    if len(diffs) < 3:
        return {"point": None, "ci95": None, "n_clusters": len(diffs)}
    values = np.asarray(diffs)
    out = clustered_bootstrap(backbones, lambda idx: float(values[idx].mean()))
    out["n_backbones_paired"] = len(diffs)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "temperature_sweep"
    parser.add_argument("--af2", default=str(base / "af2_stage1.csv"))
    parser.add_argument("--out", default=str(base / "af2_analysis.json"))
    args = parser.parse_args(argv)

    rows = annotate(load(Path(args.af2)))
    temps = sorted({r["temperature"] for r in rows}, key=float)
    print(f"folded={len(rows)} temperatures={temps} "
          f"backbones={len({r['backbone_key'] for r in rows})}\n")

    report = {"n_folded": len(rows), "reference_temperature": REFERENCE_T,
              "ci_width_target": CI_WIDTH_TARGET, "per_temperature": {}, "comparisons": {}}

    print(f"{'T':>6s} {'n':>5s} {'structural_yield':>17s} {'joint_yield':>12s} {'SoluProt':>10s}")
    for temp in temps:
        subset = [r for r in rows if r["temperature"] == temp]
        def mean_of(field):
            vals = [r[field] for r in subset if r.get(field) is not None]
            return round(float(np.mean(vals)), 4) if vals else None
        entry = {"n": len(subset), "structural_yield": mean_of("_structural"),
                 "joint_yield": mean_of("_joint"), "soluprot": mean_of("_soluprot")}
        report["per_temperature"][temp] = entry
        print(f"{temp:>6s} {entry['n']:>5d} {str(entry['structural_yield']):>17s} "
              f"{str(entry['joint_yield']):>12s} {str(entry['soluprot']):>10s}")

    print(f"\n=== paired vs T={REFERENCE_T} (백본 clustered bootstrap) ===")
    for field, label in (("_structural", "structural_yield"), ("_joint", "joint_yield"),
                         ("_soluprot", "soluprot")):
        print(f"\n{label} (primary)" if field != "_soluprot" else f"\n{label} (secondary)")
        for temp in temps:
            if temp == REFERENCE_T:
                continue
            res = paired_yield_difference(rows, temp, field)
            res["next_step"] = decide_next_step(res)
            report["comparisons"][f"{label}@T{temp}"] = res
            ci = res.get("ci95")
            print(f"  T={temp}: diff={res.get('point')} CI{ci} "
                  f"clusters={res.get('n_backbones_paired')} -> {res['next_step']}")

    steps = {v["next_step"] for k, v in report["comparisons"].items()
             if k.startswith(("structural_yield", "joint_yield"))}
    report["overall_next_step"] = (
        "add_second_half" if "add_second_half" in steps
        else ("stop_effect_confirmed" if "stop_effect_confirmed" in steps else "stop_no_effect")
    )
    print(f"\nprimary endpoint 종합 판정: {report['overall_next_step']}")
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
