#!/usr/bin/env python3
"""파일럿 결과로 확증 코호트의 표적 수를 정한다.

공식은 `docs/specs/hierarchical-confirmatory-prespec.md` §7.0 (v1.5) 에
**파일럿 결과 전에** 동결돼 있다. 여기서 새로 정하는 값은 없다.

    n_req     = max( (2.80 * SD_p / D_p)^2 , 8 )
    n_targets = clamp( ceil(n_req / 0.55), 15, 34 )

표적은 동결 목록의 **앞에서부터** 자른다. 결과를 보고 고르지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "public_data" / "benchmark" / "gate0"
PILOT = BASE / "depth_scaling.json"
TARGETS = BASE / "hier_confirmatory_targets.json"
PLAN = BASE / "hier_confirmatory_plan.json"

Z = 2.80              # z_.975 + z_.80
QUAL_RATE = 0.55      # v2 실측 분모 자격률. 바꾸지 않는다.
MIN_CLUSTERS = 8
FLOOR, CEIL = 15, 34


def main() -> int:
    if not PILOT.exists():
        raise SystemExit("파일럿 분석 결과가 없다. 37_ 를 먼저 돌린다.")
    c = json.loads(PILOT.read_text(encoding="utf-8"))["contrasts"].get("greedy_fill|B80")
    if not c or "per_unit_delta" not in c:
        raise SystemExit("greedy_fill|B80 주 비교가 없다.")
    if not (c["excludes_zero"] and c["delta"] > 0):
        raise SystemExit(f"게이트 미통과 (delta={c['delta']:+.3f} "
                         f"[{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}]). 사이징하지 않는다.")

    d = list(c["per_unit_delta"].values())
    D_p, SD_p = statistics.mean(d), statistics.stdev(d)
    n_req = max((Z * SD_p / D_p) ** 2, MIN_CLUSTERS)
    n_targets = min(max(math.ceil(n_req / QUAL_RATE), FLOOR), CEIL)

    doc = json.loads(TARGETS.read_text(encoding="utf-8"))
    kept = doc["targets"][:n_targets]           # 앞에서부터. 고르지 않는다.
    print(f"파일럿 D(42) 평균 {D_p:+.4f} · SD {SD_p:.4f} · unit {len(d)}")
    print(f"n_req {n_req:.1f} → 표적 {n_targets} (하한 {FLOOR} 상한 {CEIL})")
    print(f"fold {n_targets * 6 * 42:,} · 폴딩 약 "
          f"{n_targets * 6 * 42 * 54 / 3600 / 24:.1f}일")

    doc["targets"] = kept
    doc["n_targets"] = len(kept)
    doc["sizing"] = {"prespec": "§7.0 v1.5", "pilot_D42": D_p, "pilot_SD": SD_p,
                     "n_required": n_req, "qual_rate": QUAL_RATE,
                     "selection": "동결 목록 앞에서부터. 결과로 고르지 않는다."}
    TARGETS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    sel = [t["domain"] for t in kept]
    plan["cohorts"]["hier_confirmatory"].update(
        {"selected": sel, "n_targets": len(sel),
         "selected_sha256": hashlib.sha256(json.dumps(sel).encode()).hexdigest()})
    plan["targets_sha256"] = hashlib.sha256(TARGETS.read_bytes()).hexdigest()
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"갱신: {TARGETS.name} · {PLAN.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
