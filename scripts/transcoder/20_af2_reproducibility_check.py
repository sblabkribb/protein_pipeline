#!/usr/bin/env python3
"""패널 1 재실행이 '재측정' 인지 '재예측' 인지 가른다.

1 차 온도 패널은 AF2 의 PDB 를 저장하지 않았다. 그래서 RMSD 정의를 고치려면 480
서열을 다시 접어야 했고, 그러면 두 가지가 동시에 바뀐다.

  (1) 지표 정의: 전체 CA kabsch -> DSSP non-loop ca_rmsd
  (2) 예측 자체: AF2 의 run-to-run 차이

같은 서열을 다시 접었으므로 pLDDT 를 직접 대조하면 둘을 나눌 수 있다. pLDDT 가
재현되면 통과율 변화는 전부 (1) 때문이고, 재현되지 않으면 둘이 섞였다는 사실을
결과에 적어야 한다.

RMSD 는 대조하지 않는다 - 정의가 바뀌었으므로 같을 이유가 없다. 대조 대상은
정의를 바꾸지 않은 pLDDT 다.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.protocol import AF2_SETTINGS_V1, GATE0_THRESHOLDS  # noqa: E402

#: 재현되었다고 부르기 위한 문턱. af2_reproducibility.json 이 같은 서열 재실행의
#: |delta pLDDT| 를 평균 0.006 / 최대 0.011 (n=3) 로 재놨고, 타겟 내부 SD 는
#: 0.556 이다. 0.5 는 그 SD 의 약 90% 로, 이보다 크면 예측 차이가 신호와 같은
#: 크기가 된다.
REPRODUCIBILITY_BAR = {
    "plddt_tolerance": 0.5,
    "max_gate_flip_fraction": 0.02,
    "rationale": (
        "허용 오차 0.5 는 타겟 내부 pLDDT SD 0.556 에서 왔다. 게이트 뒤집힘 2% 는 "
        "임계값 근처 서열이 통과율을 흔드는 정도를 제한한다."
    ),
}


def _num(row, key):
    value = row.get(key)
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usable(row) -> bool:
    return row.get("status") == "ok" and _num(row, "plddt") is not None


def _passes(row) -> bool | None:
    plddt, rmsd = _num(row, "plddt"), _num(row, "rmsd")
    if plddt is None or rmsd is None:
        return None
    return plddt >= GATE0_THRESHOLDS["plddt_min"] and rmsd <= GATE0_THRESHOLDS["rmsd_max"]


def compare_runs(old_rows, new_rows) -> dict:
    """두 실행을 서열 단위로 맞대어 pLDDT 재현성과 통과 변화의 원인을 나눈다."""
    old = {r["sequence_id"]: r for r in old_rows if _usable(r)}
    new = {r["sequence_id"]: r for r in new_rows if _usable(r)}
    shared = sorted(set(old) & set(new))

    deltas, flips, records = [], 0, []
    attribution = {"unchanged": 0, "metric_definition_only": 0,
                   "prediction_only": 0, "confounded": 0}

    for sid in shared:
        a, b = old[sid], new[sid]
        pa, pb = _num(a, "plddt"), _num(b, "plddt")
        delta = pb - pa
        deltas.append(abs(delta))
        records.append({"sequence_id": sid, "old_plddt": pa, "new_plddt": pb,
                        "abs_delta": round(abs(delta), 4)})

        cut = GATE0_THRESHOLDS["plddt_min"]
        plddt_gate_moved = (pa >= cut) != (pb >= cut)
        flips += int(plddt_gate_moved)

        # RMSD 판정이 바뀌었는가 - 정의가 달라졌으므로 이것이 (1) 의 신호다.
        ra, rb = _num(a, "rmsd"), _num(b, "rmsd")
        rmsd_gate_moved = (
            None if ra is None or rb is None
            else (ra <= GATE0_THRESHOLDS["rmsd_max"]) != (rb <= GATE0_THRESHOLDS["rmsd_max"])
        )

        # 순 통과 여부가 아니라 **각 게이트가 움직였는지** 로 나눈다. 두 게이트가
        # 반대 방향으로 뒤집히면 순 통과는 그대로지만 그것은 unchanged 가 아니라
        # 가장 확실한 confounded 다 - 그것을 unchanged 로 세면 숨어버린다.
        if rmsd_gate_moved and plddt_gate_moved:
            attribution["confounded"] += 1
        elif rmsd_gate_moved:
            attribution["metric_definition_only"] += 1
        elif plddt_gate_moved:
            attribution["prediction_only"] += 1
        elif _passes(a) != _passes(b):
            # 어느 게이트도 안 움직였는데 통과가 바뀌었다면 결측 때문이다.
            attribution["confounded"] += 1
        else:
            attribution["unchanged"] += 1

    records.sort(key=lambda r: -r["abs_delta"])
    mean_delta = statistics.fmean(deltas) if deltas else 0.0
    max_delta = max(deltas) if deltas else 0.0
    flip_fraction = flips / len(shared) if shared else 0.0
    reproduced = (
        bool(shared)
        and max_delta <= REPRODUCIBILITY_BAR["plddt_tolerance"]
        and flip_fraction <= REPRODUCIBILITY_BAR["max_gate_flip_fraction"]
    )

    return {
        "af2_settings": {k: v for k, v in AF2_SETTINGS_V1.items()
                         if k not in ("not_controlled_here",)},
        "settings_not_controlled": AF2_SETTINGS_V1["not_controlled_here"],
        "bar": REPRODUCIBILITY_BAR,
        "n_only_in_old": len(set(old) - set(new)),
        "n_only_in_new": len(set(new) - set(old)),
        "plddt": {
            "n_compared": len(shared),
            "mean_abs_delta": round(mean_delta, 4),
            "max_abs_delta": round(max_delta, 4),
            "n_gate_flips": flips,
            "gate_flip_fraction": round(flip_fraction, 4),
            "largest_deltas": records[:10],
        },
        "attribution": attribution,
        "attribution_note": (
            "통과 여부가 바뀐 서열을 원인별로 나눈다. metric_definition_only 는 RMSD "
            "판정만 뒤집힌 것, prediction_only 는 pLDDT 판정만 뒤집힌 것, confounded 는 "
            "둘 다 움직였거나 어느 쪽으로도 설명되지 않는 것이다."
        ),
        "prediction_reproduced": reproduced,
        "verdict": (
            "pLDDT 가 재현되었다. 통과율 변화는 지표 정의 변경으로 읽어도 된다."
            if reproduced else
            "pLDDT 가 재현되지 않았다. 지표 정의 변경과 AF2 run-to-run 차이가 섞여 있으므로 "
            "통과율 변화를 정의 변경만으로 설명하면 안 된다."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "temperature_sweep"
    parser.add_argument("--old", type=Path, default=base / "af2_stage1.csv")
    parser.add_argument("--new", type=Path, default=base / "af2_stage1_rmsd_fixed.csv")
    parser.add_argument("--out", type=Path, default=base / "af2_rerun_reproducibility.json")
    args = parser.parse_args(argv)

    if not args.new.exists():
        print(f"재실행 결과가 아직 없다: {args.new}", file=sys.stderr)
        return 2

    old = list(csv.DictReader(args.old.open(encoding="utf-8")))
    new = list(csv.DictReader(args.new.open(encoding="utf-8")))
    report = compare_runs(old, new)
    report["old_file"] = str(args.old.relative_to(PROJECT_ROOT))
    report["new_file"] = str(args.new.relative_to(PROJECT_ROOT))

    p = report["plddt"]
    print(f"대조 {p['n_compared']} 서열 (old 전용 {report['n_only_in_old']}, "
          f"new 전용 {report['n_only_in_new']})")
    print(f"pLDDT |delta| 평균 {p['mean_abs_delta']} 최대 {p['max_abs_delta']} "
          f"(허용 {REPRODUCIBILITY_BAR['plddt_tolerance']})")
    print(f"pLDDT 게이트 뒤집힘 {p['n_gate_flips']} ({p['gate_flip_fraction']:.3f}, "
          f"허용 {REPRODUCIBILITY_BAR['max_gate_flip_fraction']})")
    print(f"\n통과 변화 원인: {report['attribution']}")
    print(f"\n{report['verdict']}")
    if p["largest_deltas"]:
        print(f"\n최대 편차 상위:")
        for rec in p["largest_deltas"][:5]:
            print(f"  {rec['sequence_id']:48s} {rec['old_plddt']:.2f} -> "
                  f"{rec['new_plddt']:.2f}  (|d|={rec['abs_delta']:.3f})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
