#!/usr/bin/env python3
"""계층형 배분 confirmatory 캠페인의 동결 계획 JSON 을 만든다.

`52_v2_multisource_campaign.py` 가 읽는 스키마와 같다(version 2.0). 숫자는
`docs/specs/hierarchical-confirmatory-prespec.md` (v1.3) 에서 온다 - 여기서
새로 정하는 값은 없다.

v2 계획과 다른 점만
-------------------
    생성원              RFD3 단독 (BioEmu 없음)
    표적                34 (사슬 추출된 PDB)
    백본/표적           6   (v2 는 10)
    후보/백본           42  (v2 confirmatory 는 18), tier 14/14/14
    RFD3 시도 상한      24  (v2 는 10 수용에 40 시도였으므로 같은 4 배)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "public_data" / "benchmark" / "gate0"
TARGETS = BASE / "hier_confirmatory_targets.json"
OUT = BASE / "hier_confirmatory_plan.json"

BACKBONES_PER_TARGET = 6
CANDIDATES_PER_BACKBONE = 42
TIER_COUNTS = {"30": 14, "50": 14, "70": 14}
SEED = 20260921


def main() -> int:
    doc = json.loads(TARGETS.read_text(encoding="utf-8"))
    selected = [t["domain"] for t in doc["targets"]]
    #: `52_.cohort_rows` 와 **같은 직렬화**로 digest 를 낸다 (기본 구분자).
    digest = hashlib.sha256(json.dumps(selected).encode()).hexdigest()

    plan = {
        "plan_id": "rapid_hier_confirmatory",
        "status": "frozen",
        "version": "2.0",
        "schema_note": ("52_v2_multisource_campaign.py 가 읽는 스키마와 같다. "
                        "plan_id 가 다르므로 v2 동결 계획을 덮지 않는다."),
        "prespec": "docs/specs/hierarchical-confirmatory-prespec.md",
        "prespec_version": "1.3",
        "targets_artifact": str(TARGETS.relative_to(ROOT)),
        "targets_sha256": hashlib.sha256(TARGETS.read_bytes()).hexdigest(),
        "cohorts": {
            "hier_confirmatory": {
                "n_targets": len(selected),
                "seed": SEED,
                "selected": selected,
                "selected_sha256": digest,
                "reselection_forbidden": True,
                "n_reserve": 0,
                "reserve_note": ("예비가 없다. 생성 실패는 표적 교체 없이 "
                                 "모자란 채로 보고한다 (사전지정 §9)."),
            }
        },
        "per_source_design": {
            "backbones_per_target": BACKBONES_PER_TARGET,
            "confirmatory_candidates_per_backbone": CANDIDATES_PER_BACKBONE,
            "confirmatory_tier_counts": TIER_COUNTS,
            #: 이 코호트는 calibration 을 쓰지 않는다. 스키마가 요구하므로
            #: 같은 값을 넣어 두되 실제로 참조되지 않는다.
            "calibration_candidates_per_backbone": CANDIDATES_PER_BACKBONE,
            "calibration_tier_counts": TIER_COUNTS,
            "tier_prefix_order": ["30", "50", "70"],
            "warmup_valid_observations_per_backbone": 4,
        },
        "generation_rules": {
            "rfd3": {
                "mode": "local_diversify",
                "partial_t": 5.0,
                "select_fixed_atoms": "{A1: ALL} — 변경하지 않는다",
                "accept_gate": "target-RMSD <= 2.0 A",
                "accepted_needed_per_target": BACKBONES_PER_TARGET,
                #: v2 는 10 수용에 40 시도였다. 같은 4 배를 쓴다.
                "max_attempts_per_target": BACKBONES_PER_TARGET * 4,
                "order": "동결된 seed 의 생성 순서. 구조 점수로 고르지 않는다.",
            },
            "on_shortfall": ("그 target x source 를 SOURCE_GENERATION_INFEASIBLE "
                             "로 기록한다. 타겟을 예비로 바꾸지 않는다."),
            "unequal_units_formula": {"warmup_per_unit": 4,
                                      "ceiling_per_unit": CANDIDATES_PER_BACKBONE},
        },
        "endpoints": {
            "pooling_across_sources_forbidden": True,
            "efbc_forbidden": True,
            "calibration_cohort_forbidden": True,
        },
    }
    text = json.dumps(plan, ensure_ascii=False, indent=1)
    OUT.write_text(text, encoding="utf-8")
    print(f"표적 {len(selected)} · 백본 {BACKBONES_PER_TARGET} · "
          f"후보 {CANDIDATES_PER_BACKBONE} · fold "
          f"{len(selected) * BACKBONES_PER_TARGET * CANDIDATES_PER_BACKBONE:,}")
    print(f"{OUT}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
