#!/usr/bin/env python3
"""rapid_structural_v1 의 결과를 불변 기록으로 고정한다.

무엇을 고정하는가
-----------------
전향 홀드아웃 격자(1,728/1,728)와 RFD3 균형 코호트(1,440/1,440), 그리고 그
위에서 돌린 동결 분석들의 산출물이다. 각 파일의 SHA256, 행 수, 코호트 구성,
임계값 설정, 코드 커밋을 함께 적는다.

왜 해시인가
-----------
"이 표는 이 데이터에서 나왔다" 를 나중에 확인할 수 있어야 한다. 파일 경로만
적어두면 그 파일이 그 뒤에 바뀌었는지 알 수 없다. 재실행하면 해시가 다시
계산되고 --verify 는 기록된 값과 대조만 한다.

무엇을 고정하지 않는가
----------------------
v2 작업은 여기 포함되지 않는다. 이 기록은 v1 을 그대로 인용할 수 있게 하려는
것이고, v2 는 이 값을 바꾸지 않은 채로 진행돼야 한다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
FREEZE = BASE / "RAPID_STRUCTURAL_V1_FREEZE.json"

PROFILE = "rapid_structural_v1"

#: 고정 대상. (역할, 저장소 상대 경로)
ARTIFACTS = [
    ("grid_folds", "public_data/benchmark/gate0/holdout_grid/af2_order_metric.csv"),
    ("grid_sequences", "public_data/benchmark/gate0/holdout_grid/sequences.csv"),
    ("grid_manifest", "public_data/benchmark/gate0/holdout_grid/manifest.json"),
    ("holdout_targets", "public_data/benchmark/gate0/holdout_targets.json"),
    ("frozen_experiment_spec", "public_data/benchmark/gate0/holdout_experiment_spec.json"),
    ("primary_allocation_joint",
     "public_data/benchmark/gate0/holdout_grid/prospective_allocation_validation_joint.json"),
    ("secondary_allocation_structural",
     "public_data/benchmark/gate0/holdout_grid/prospective_allocation_validation_structural.json"),
    ("sensitivity_allocation_native",
     "public_data/benchmark/gate0/holdout_grid/prospective_allocation_validation_native_sens.json"),
    ("secondary_realized_compute",
     "public_data/benchmark/gate0/holdout_grid/realized_compute_analysis.json"),
    ("variance_decomposition_primary",
     "public_data/benchmark/gate0/holdout_grid/variance_decomposition_grid.json"),
    ("variance_decomposition_supplementary",
     "public_data/benchmark/gate0/variance_decomposition_structural.json"),
    ("gate0_target_level", "public_data/benchmark/gate0/gate0_target_level.json"),
    ("temperature_panel2",
     "public_data/benchmark/gate0/temperature_panel2/af2_analysis_order_complete.json"),
    ("aggregation_no_go",
     "public_data/benchmark/gate0/incremental_information_test.json"),
    ("stability_annotation",
     "public_data/benchmark/gate0/stability_annotation_comparison.json"),
    ("ligand_wiring_check",
     "public_data/benchmark/gate0/ligand_pocket/self_docking.json"),
]

#: 결과를 만든 코드. 바뀌면 결과를 다시 내야 한다.
CODE = [
    "scripts/transcoder/26_holdout_grid.py",
    "scripts/transcoder/39_prospective_allocation_validation.py",
    "scripts/transcoder/40_variance_decomposition_grid.py",
    "scripts/transcoder/41_realized_compute_analysis.py",
    "scripts/transcoder/rapid_sr/protocol.py",
    "pipeline-mcp/src/pipeline_mcp/allocation.py",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(rel: str) -> dict:
    path = PROJECT_ROOT / rel
    if not path.exists():
        return {"path": rel, "present": False}
    entry = {"path": rel, "present": True, "sha256": sha256(path),
             "bytes": path.stat().st_size}
    if path.suffix == ".csv":
        with path.open(encoding="utf-8") as fh:
            entry["rows"] = sum(1 for _ in fh) - 1
    return entry


def cohort_summary() -> dict:
    """격자의 구성. 표에 인용되는 n 이 어디서 왔는지 기록으로 남긴다."""
    path = BASE / "holdout_grid" / "af2_order_metric.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    ok = [r for r in rows if r["status"] == "ok"]
    rfd3 = [r for r in ok if r["backbone_source"] == "rfd3"]
    rfd3_usable = [r for r in rfd3 if r["rmsd_nonloop_order"].strip()]
    native = [r for r in ok if r["backbone_source"] != "rfd3"]
    refused = [r for r in ok if not r["rmsd_nonloop_order"].strip()]
    return {
        "total_folds": len(rows),
        "ok": len(ok),
        "failed": len(rows) - len(ok),
        "n_targets": len({r["target_id"] for r in rows}),
        "n_backbones": len({r["backbone_key"] for r in rows}),
        "rfd3_balanced_cohort": {
            "n": len(rfd3_usable), "of": len(rfd3),
            "n_backbones": len({r["backbone_key"] for r in rfd3_usable}),
            "role": "primary - target/backbone/sequence 완전 균형, source 상수",
        },
        "native_backbones": {
            "n": len(native),
            "role": "sensitivity only - 타겟당 1 개뿐이라 백본 수준 비교가 불균형해진다",
        },
        "metric_refusals": {
            "n": len(refused),
            "by_source": dict(collections.Counter(r["backbone_source"] for r in refused)),
            "why": "동결된 대응 규칙이 서열 길이와 기준 잔기 수가 다른 행의 RMSD 계산을 "
                   "거부했다. 전부 native 백본이고 RFD3 주 코호트에는 없다.",
        },
    }


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT,
                          capture_output=True, text=True).stdout.strip()


def build() -> dict:
    grid_manifest = json.loads(
        (BASE / "holdout_grid" / "manifest.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
    from rapid_sr.protocol import GATE0_THRESHOLDS, THRESHOLD_PROVENANCE

    return {
        "profile": PROFILE,
        "status": "frozen",
        "what_this_is": "전향 홀드아웃 위에서 확정한 v1 결과의 불변 기록. 원고가 "
                        "인용하는 수치는 여기 적힌 해시의 파일에서 나온 것이다.",
        "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": {
            "commit": git("rev-parse", "HEAD"),
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "describe": git("describe", "--tags", "--always", "--dirty"),
            "dirty_paths": [ln for ln in git("status", "--porcelain").splitlines()][:40],
        },
        "config": {
            "thresholds": dict(GATE0_THRESHOLDS),
            "threshold_provenance": THRESHOLD_PROVENANCE,
            "metric": grid_manifest.get("metric"),
            "metric_reference": grid_manifest.get("reference"),
            "protocol_fingerprint": grid_manifest.get("protocol_fingerprint"),
            "generation_condition": grid_manifest.get("condition"),
            "grid_depth": grid_manifest.get("grid_depth"),
        },
        "cohort": cohort_summary(),
        "artifacts": {role: digest(rel) for role, rel in ARTIFACTS},
        "code": {Path(rel).name: digest(rel) for rel in CODE},
        "endpoint_roles": {
            "primary": "예산 상한 안에서 찾은 joint-pass 설계 수 "
                       "(prospective_allocation_validation_joint.json). 동결 spec 그대로이며 "
                       "사후 변경하지 않았다.",
            "secondary_structural_label": "SoluProt 을 뺀 structural-pass 라벨의 같은 분석.",
            "secondary_realized_compute": "실제로 쓴 호출 수 기준 분석 "
                                          "(realized_compute_analysis.json). 1 차를 대체하지 "
                                          "않고 병기한다.",
            "sensitivity_native": "native 백본 포함.",
        },
        "claims_not_supported": {
            "ligand_self_docking": "배선 점검이다. DiffDock 은 PDBBind 로 학습했고 이 "
                                   "복합체들이 그 안에 있을 것이므로 성능 검증이 아니다.",
            "stability_annotation": "annotation 과 tie-break 로만 쓴다. pooled 상관을 "
                                    "랭킹 근거로 쓰지 않는다 - 백본 내에서 부호가 뒤집힌다.",
            "condition_exploration": "격자는 단일 조건(T=0.1)이다. Gate 1B 의 조건 탐색 "
                                     "축은 이 코호트에서 검증되지 않았다.",
            "panel2_policy_performance": "패널 2 는 개발 패널이다. 정책 성능 수치를 "
                                         "거기서 인용하지 않는다.",
        },
        "limits": [
            "타겟 12 개다. 분산성분과 클러스터 부트스트랩의 정밀도가 그만큼만 된다.",
            "RFD3 백본은 2.0 A 수용 게이트를 통과한 것들이다 - 기각된 백본의 변이는 "
            "관측되지 않았다.",
            "정책 비교는 완전 관측된 격자의 비복원 재생이다. 온라인 실행이 아니다.",
        ],
    }


def verify(recorded: dict) -> int:
    bad = []
    for group in ("artifacts", "code"):
        for role, entry in recorded.get(group, {}).items():
            if not entry.get("present"):
                continue
            now = digest(entry["path"])
            if now.get("sha256") != entry.get("sha256"):
                bad.append((group, role, entry["path"]))
    for group, role, path in bad:
        print(f"  변경됨: {group}/{role} · {path}")
    if bad:
        print(f"\n{len(bad)} 개가 기록된 해시와 다르다. 결과를 다시 내거나 "
              f"기록을 갱신해야 한다.")
        return 1
    n = sum(1 for g in ("artifacts", "code") for e in recorded[g].values()
            if e.get("present"))
    print(f"  {n} 개 파일 해시 일치 · 커밋 {recorded['git']['commit'][:12]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="기록된 해시와 대조만 한다 (기록을 덮어쓰지 않는다)")
    args = ap.parse_args()

    if args.verify:
        if not FREEZE.exists():
            print(f"동결 기록이 없다: {FREEZE}")
            return 1
        return verify(json.loads(FREEZE.read_text(encoding="utf-8")))

    report = build()
    FREEZE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    c = report["cohort"]
    print(f"프로파일 {report['profile']} · 커밋 {report['git']['commit'][:12]}")
    print(f"  격자 {c['ok']}/{c['total_folds']} ok · 타겟 {c['n_targets']} · 백본 {c['n_backbones']}")
    print(f"  RFD3 균형 코호트 {c['rfd3_balanced_cohort']['n']}/{c['rfd3_balanced_cohort']['of']} "
          f"· 백본 {c['rfd3_balanced_cohort']['n_backbones']}")
    print(f"  지표 거부 {c['metric_refusals']['n']} ({c['metric_refusals']['by_source']})")
    missing = [r for r, e in report["artifacts"].items() if not e.get("present")]
    print(f"  산출물 {len(report['artifacts']) - len(missing)}/{len(report['artifacts'])} 해시 기록"
          + (f" · 없음 {missing}" if missing else ""))
    if report["git"]["dirty_paths"]:
        print(f"  주의: 작업트리에 커밋되지 않은 변경 {len(report['git']['dirty_paths'])} 건")
    print(f"\nwrote {FREEZE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
