#!/usr/bin/env python3
"""Phase 4B calibration 코호트의 타겟을 고른다. 폴딩 전에 동결한다.

동결 문서: `docs/specs/rapid-v2-phase4b-calibration-freeze.md`

적격성과 길이만 본다. 과거 yield · SoluProt · structural-success · joint-pass ·
Gate 0 점수는 선정에 쓰지 않는다 - 그 중 하나라도 보면 이 코호트로 정한
hyperparameter 가 성능을 보고 정한 것이 된다.

confirmatory holdout 과 겹치지 않게 하는 것만으로는 부족해서, holdout 의
selected/reserve/resolved 와 온도 패널 두 개에 쓰인 타겟, 그리고 **그 타겟들의
superfamily** 까지 뺀다. 근접 중복이 남으면 독립 코호트가 아니다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUT = BASE / "calibration_targets.json"

#: 선정 seed. 이 파일과 함께 커밋되고 결과를 보고 바꾸지 않는다.
SEED = 20260909

PER_STRATUM = 4
RESERVE_PER_STRATUM = 2
BACKBONES_PER_TARGET = 5
SEQUENCES_PER_BACKBONE = 8


def _holdout_module():
    """24 의 적격성 구현을 그대로 쓴다. 다시 구현하면 규칙이 갈라진다."""
    path = Path(__file__).resolve().parent / "24_select_holdout_targets.py"
    spec = importlib.util.spec_from_file_location("sel24", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def used_targets() -> tuple[set[str], dict]:
    """이미 쓴 타겟. 어디서 왔는지도 남긴다."""
    src: dict[str, list[str]] = {}
    d = json.loads((BASE / "holdout_targets.json").read_text(encoding="utf-8"))
    src["holdout_resolved"] = sorted(x["domain"] for x in d["resolved"]["targets"])
    src["holdout_selected"] = sorted(x["domain"] for x in d.get("selected", []))
    src["holdout_reserve"] = sorted(x["domain"] for x in d.get("reserve", []))
    for name in ("temperature_sweep", "temperature_panel2"):
        path = BASE / name / "af2_order_metric.csv"
        if path.exists():
            src[name] = sorted({r["target_id"]
                                for r in csv.DictReader(path.open(encoding="utf-8"))})
    return {t for v in src.values() for t in v}, src


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    m = _holdout_module()
    sf = m.superfamilies()
    used, used_src = used_targets()
    used_sf = {sf.get(t) for t in used if sf.get(t)}
    print(f"이미 쓴 타겟 {len(used)} · 그 superfamily {len(used_sf)}")

    pool = m.eligible(used_sf, sf, used)
    by_stratum: dict[str, list[dict]] = {label: [] for label, _, _ in m.STRATA}
    for row in pool:
        s = m.stratum_of(row["length"])
        if s:
            row["stratum"] = s
            by_stratum[s].append(row)
    print(f"적격 후보 {len(pool)} · 층별 "
          f"{ {k: len(v) for k, v in by_stratum.items()} }")

    rng = random.Random(SEED)
    selected, reserve = [], []
    for label, _, _ in m.STRATA:
        candidates = sorted(by_stratum[label], key=lambda r: r["domain"])
        need = PER_STRATUM + RESERVE_PER_STRATUM
        if len(candidates) < need:
            print(f"  거부: {label} 층 후보 {len(candidates)} < {need}")
            return 2
        picked = rng.sample(candidates, need)
        for i, row in enumerate(picked):
            row = dict(row)
            row["role"] = "selected" if i < PER_STRATUM else "reserve"
            if row["role"] == "reserve":
                row["reserve_rank"] = i - PER_STRATUM
            (selected if i < PER_STRATUM else reserve).append(row)

    print(f"\n선정 {len(selected)} · 예비 {len(reserve)}")
    for row in sorted(selected, key=lambda r: (r["stratum"], r["domain"])):
        print(f"  {row['stratum']:>8}  {row['domain']:10s} {row['length']:>4} aa  "
              f"{row['superfamily']}")

    report = {
        "purpose": "Phase 4B joint-pass posterior calibration 코호트. "
                   "성능 주장에 쓰지 않는다.",
        "freeze_doc": "docs/specs/rapid-v2-phase4b-calibration-freeze.md",
        "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": SEED,
        "design": {
            "n_targets": len(selected),
            "backbones_per_target": BACKBONES_PER_TARGET,
            "sequences_per_backbone": SEQUENCES_PER_BACKBONE,
            "total_folds": len(selected) * BACKBONES_PER_TARGET * SEQUENCES_PER_BACKBONE,
            "temperature": 0.1,
        },
        "eligibility": dict(m.ELIGIBILITY),
        "strata": [{"label": a, "low": b, "high": c} for a, b, c in m.STRATA],
        "selection_inputs": ["적격성", "길이"],
        "selection_excluded_inputs": [
            "과거 yield", "SoluProt 결과", "structural-success 결과",
            "joint-pass 결과", "Gate 0 사전분포 점수",
        ],
        "exclusions": {
            "used_targets": sorted(used),
            "used_target_sources": used_src,
            "n_used_superfamilies": len(used_sf),
            "why_superfamily": "근접 중복이 남으면 독립 코호트가 아니다",
        },
        "pool": {"n_eligible": len(pool),
                 "by_stratum": {k: len(v) for k, v in by_stratum.items()}},
        "selected": selected,
        "reserve": reserve,
        "substitution_rule": "수용 게이트를 통과해 backbone 5 개를 채우지 못한 "
                             "타겟은 같은 층의 예비로 reserve_rank 순서대로 "
                             "교체한다. 결과를 보고 빼지 않는다.",
        "not_for": ["policy 비교", "EFBC 계산", "coverage 결론",
                    "confirmatory 주장"],
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
    }
    body = json.dumps(report, ensure_ascii=False, indent=2)
    report["self_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
