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
# 효과가 명확하다고 부르기 위한 최소 구간 정밀도.
CI_WIDTH_TARGET = 0.10
# 이 비율 이상이 백본 간 변동이면 서열을 더 뽑아도 구간이 좁아지지 않는다.
BACKBONE_LIMITED_THRESHOLD = 0.5


def diagnose_uncertainty(diffs, yields_ref, yields_alt, n_per_condition: int) -> dict:
    """CI 폭의 원인이 서열 수 부족인지 백본 수 부족인지 나눈다.

    관측된 백본별 차이의 분산은 두 성분의 합이다.

        Var(관측 차이) = Var(진짜 백본 간 차이) + E[서열 표집 분산]

    yield 는 n 개 서열에서 잰 비율이므로 표집 분산은 p(1-p)/n 로 근사한다.
    백본 성분이 지배적이면 같은 백본에서 서열을 더 뽑아도 소용이 없고,
    **백본을 늘려야** 한다.
    """
    diffs = np.asarray(diffs, dtype=float)
    if diffs.size < 3 or n_per_condition <= 0:
        return {"verdict": "unknown", "n_backbones": int(diffs.size)}

    observed = float(diffs.var(ddof=1))
    sampling = float(np.mean([
        p * (1 - p) / n_per_condition + q * (1 - q) / n_per_condition
        for p, q in zip(np.asarray(yields_alt, dtype=float),
                        np.asarray(yields_ref, dtype=float))
    ]))
    backbone = max(0.0, observed - sampling)
    total = backbone + sampling
    frac_backbone = (backbone / total) if total > 0 else 0.0
    return {
        "observed_variance": round(observed, 6),
        "sequence_sampling_variance": round(sampling, 6),
        "backbone_variance": round(backbone, 6),
        "fraction_backbone": round(frac_backbone, 4),
        "verdict": (
            "backbone_limited" if frac_backbone >= BACKBONE_LIMITED_THRESHOLD
            else "sequence_limited"
        ),
        "n_backbones": int(diffs.size),
    }


def decide_next_step(entry: dict, *, ci_width_target: float = CI_WIDTH_TARGET) -> str:
    """1단계 480 이후 무엇을 할지.

    구간이 넓다고 무조건 서열을 늘리지 않는다. 백본 수가 병목이면 같은 백본에서
    서열을 더 뽑아도 구간이 좁아지지 않으므로 신규 백본으로 확장해야 한다.
    """
    ci = entry.get("ci95")
    if not ci:
        return "expand_backbones"
    width = float(ci[1]) - float(ci[0])
    if width <= ci_width_target:
        return "stop_effect_confirmed" if entry.get("excludes_zero") else "stop_no_effect"
    verdict = (entry.get("uncertainty") or {}).get("verdict")
    return "add_second_half" if verdict == "sequence_limited" else "expand_backbones"


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

    backbones, diffs, refs, alts, counts = [], [], [], [], []
    for backbone, per_temp in by.items():
        if REFERENCE_T not in per_temp or temp not in per_temp:
            continue
        ref = float(np.mean(per_temp[REFERENCE_T]))
        alt = float(np.mean(per_temp[temp]))
        backbones.append(backbone)
        diffs.append(alt - ref)
        refs.append(ref)
        alts.append(alt)
        counts.append(min(len(per_temp[REFERENCE_T]), len(per_temp[temp])))
    if len(diffs) < 3:
        return {"point": None, "ci95": None, "n_clusters": len(diffs)}
    values = np.asarray(diffs)
    out = clustered_bootstrap(backbones, lambda idx: float(values[idx].mean()))
    out["n_backbones_paired"] = len(diffs)
    out["uncertainty"] = diagnose_uncertainty(
        diffs, refs, alts, int(np.median(counts)) if counts else 0
    )
    return out


def stratify_by_source(rows: list[dict], temps: list[str]) -> dict:
    """온도 효과가 백본 소스에 따라 달라지는지 본다.

    native 에서만 재면 "온도를 올려도 안전하다"가 RFD3/BioEmu 백본에도 해당하는지
    알 수 없다. 소스가 하나뿐이면 층화 자체가 불가능하므로 그 사실을 남긴다.
    """
    sources = sorted({r.get("backbone_source", "target") for r in rows})
    if len(sources) < 2:
        return {"available": False, "sources": sources,
                "note": "소스가 하나뿐이라 층화 불가. wave 2/3 백본으로 sweep 확장 필요."}
    out: dict[str, object] = {"available": True, "sources": sources, "per_source": {}}
    for source in sources:
        subset = [r for r in rows if r.get("backbone_source", "target") == source]
        entry: dict[str, object] = {
            "n_folds": len(subset),
            "n_backbones": len({r["backbone_key"] for r in subset}),
        }
        for temp in temps:
            if temp == REFERENCE_T:
                continue
            for field, label in (("_structural", "structural_yield"), ("_joint", "joint_yield")):
                entry[f"{label}@T{temp}"] = paired_yield_difference(subset, temp, field)
        out["per_source"][source] = entry
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
            unc = res.get("uncertainty") or {}
            print(f"  T={temp}: diff={res.get('point')} CI{ci} "
                  f"clusters={res.get('n_backbones_paired')} "
                  f"frac_backbone={unc.get('fraction_backbone')} "
                  f"({unc.get('verdict')}) -> {res['next_step']}")

    report["by_source"] = stratify_by_source(rows, temps)
    if not report["by_source"].get("available"):
        print(f"\n소스 층화: {report['by_source']['note']}")
    else:
        print("\n=== 소스별 온도 효과 ===")
        for source, entry in report["by_source"]["per_source"].items():
            print(f"  {source}: backbones={entry['n_backbones']} folds={entry['n_folds']}")
            for key, value in entry.items():
                if isinstance(value, dict) and value.get("ci95"):
                    print(f"    {key}: diff={value['point']} CI{value['ci95']}")

    steps = {v["next_step"] for k, v in report["comparisons"].items()
             if k.startswith(("structural_yield", "joint_yield"))}
    # 백본 확장이 필요하다는 신호가 하나라도 있으면 그것이 우선한다. 같은 백본에서
    # 서열만 늘리는 것은 백본이 병목일 때 아무것도 해결하지 못한다.
    for candidate in ("expand_backbones", "add_second_half", "stop_effect_confirmed"):
        if candidate in steps:
            report["overall_next_step"] = candidate
            break
    else:
        report["overall_next_step"] = "stop_no_effect"
    print(f"\nprimary endpoint 종합 판정: {report['overall_next_step']}")
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
