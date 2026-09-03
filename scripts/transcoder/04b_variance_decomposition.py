#!/usr/bin/env python3
"""타겟/백본/설계 nested 분산 성분과 백본 ICC 를 보고한다 (설계 3.4).

게이트 0 의 전제("백본 선택이 결과를 좌우한다")를 SD 비교가 아니라
분산 성분으로 검증한다.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.variance import nested_variance_components  # noqa: E402

DEFAULT_CSV = (
    PROJECT_ROOT / "public_data" / "benchmark" / "results"
    / "backbone_ensemble_ablation_sequences.csv"
)
DEFAULT_OUT = (
    PROJECT_ROOT / "public_data" / "benchmark" / "results" / "gate0_variance_components.json"
)

# 설계 3.5: 이 CSV 의 pLDDT 는 SoluProt 상위 10개에만 AF2 를 돌려 얻은 절단 표본이다.
CENSORED_METRICS = {"plddt"}


def load_rows(csv_path: Path, metric: str) -> list[dict]:
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get(metric) or "").strip()
            if raw in ("", "None", "nan", "NaN"):
                continue
            rows.append({
                "target": row["target"],
                # 백본 식별자는 타겟과 소스까지 묶어야 서로 다른 타겟의 동명 백본이
                # 하나로 합쳐지지 않는다.
                "backbone": f"{row['target']}|{row['backbone_source']}|{row['backbone_id']}",
                "value": float(raw),
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--metrics", default="soluprot,plddt")
    parser.add_argument("--n-boot", type=int, default=500)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    report: dict[str, object] = {"source_csv": str(csv_path), "metrics": {}}
    for metric in [m.strip() for m in args.metrics.split(",") if m.strip()]:
        rows = load_rows(csv_path, metric)
        result = nested_variance_components(rows, n_boot=args.n_boot, seed=0)
        result["metric"] = metric
        result["label_regime"] = (
            "af2_after_soluprot_filter" if metric in CENSORED_METRICS else "complete"
        )
        result["is_censored"] = metric in CENSORED_METRICS
        report["metrics"][metric] = result

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    for metric, result in report["metrics"].items():
        ci = result.get("icc_backbone_ci95")
        ci_text = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "n/a"
        print(
            f"{metric:9s} n_rows={result['n_rows']:5d} "
            f"n_backbones={result['n_backbones']:4d} n_targets={result['n_targets']:3d} "
            f"| ICC_backbone={result['icc_backbone']:.3f} CI95={ci_text} "
            f"| censored={result['is_censored']}"
        )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
