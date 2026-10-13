#!/usr/bin/env python3
"""재현에 필요한 입력과 결과 파일의 SHA-256 매니페스트를 만든다.

외부에서 내려받은 파일이 우리가 쓴 것과 같은지 확인할 수 있게 한다.
출력은 JSON 과 사람이 읽는 표 두 가지다.

사용법:
    python3 scripts/make_repro_manifest.py
    python3 scripts/make_repro_manifest.py --out public_data/repro_manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: (분류, 경로, 설명)
ENTRIES = [
    ("입력", "public_data/benchmark/gate0/hier_confirmatory/af2_order_metric.csv",
     "후속 평가 구조예측 격자"),
    ("입력", "public_data/benchmark/gate0/hier_confirmatory/candidates.json",
     "후보 서열과 백본·표적 식별자"),
    ("입력", "public_data/benchmark/gate0/hier_confirmatory/mpnn_scores.json",
     "백본 조건부 ProteinMPNN 점수"),
    ("입력", "data/benchmark/hier_confirmatory_emb_320d.npz",
     "ESM-2 8M 임베딩 캐시 (후속 평가)"),
    ("입력", "data/benchmark/v2_emb_320d.npz", "ESM-2 임베딩 캐시 (실험 2)"),
    ("입력", "data/benchmark/depth_pilot_emb_320d.npz",
     "ESM-2 임베딩 캐시 (깊이 확장)"),
    ("입력", "data/benchmark/holdout_grid_emb_320d.npz",
     "ESM-2 임베딩 캐시 (홀드아웃 격자)"),
    ("입력", "public_data/benchmark/gate0/v2_multisource/af2_order_metric.csv",
     "실험 2 구조예측 격자"),
    ("입력", "public_data/benchmark/gate0/v2_multisource/candidates.json",
     "실험 2 후보 서열"),
    ("입력", "public_data/benchmark/gate0/depth_pilot/af2_order_metric.csv",
     "깊이 확장 격자"),
    ("입력", "public_data/benchmark/gate0/depth_pilot/candidates_ext.json",
     "깊이 확장 후보 서열"),
    ("결과", "public_data/benchmark/gate0/v2_mpnn_baseline.json", "실험 2 기준선"),
    ("결과", "public_data/benchmark/gate0/hierarchical_replay.json", "초기 배분 평가"),
    ("결과", "public_data/benchmark/gate0/depth_scaling.json", "깊이 확장"),
    ("결과", "public_data/benchmark/gate0/selection_gain_decomposition.json",
     "선택 이득 분해"),
    ("결과", "public_data/benchmark/gate0/coverage_preserving.json", "EFBC 분산도"),
    ("결과", "public_data/benchmark/gate0/structural_dispersion.json", "구조 분산 진단"),
    ("결과", "public_data/benchmark/gate0/hierarchical_confirmatory.json",
     "후속 평가 주 분석"),
    ("결과", "public_data/benchmark/gate0/stop_rule_diagnosis.json", "종료 규칙 진단"),
    ("사전지정", "docs/specs/hierarchical-confirmatory-prespec.md", "후속 평가 계획"),
    ("사전지정", "docs/specs/hierarchical-replay-prespec.md", "초기 배분 평가 계획"),
    ("사전지정", "docs/specs/coverage-preserving-prespec.md", "EFBC 분석 계획"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="JSON 출력 경로. 주지 않으면 표준 출력에만 쓴다.")
    a = ap.parse_args(argv)

    rows, missing = [], []
    for kind, rel, desc in ENTRIES:
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        rows.append({"kind": kind, "path": rel, "description": desc,
                     "bytes": p.stat().st_size, "sha256": sha256(p)})

    width = max(len(r["path"]) for r in rows) if rows else 0
    for r in rows:
        print(f"{r['kind']:6s} {r['path']:{width}s} {r['bytes'] / 1048576:7.2f} MB  "
              f"{r['sha256'][:16]}…")
    total = sum(r["bytes"] for r in rows)
    print(f"\n{len(rows)}개 파일 · {total / 1048576:.1f} MB")
    for m in missing:
        print(f"없음: {m}")

    if a.out:
        doc = {"note": "RAPID 재현 패키지의 입력·결과·사전지정 문서 체크섬.",
               "algorithm": "sha256", "total_bytes": total, "files": rows,
               "missing": missing}
        Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                               encoding="utf-8")
        print(f"\n{a.out}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
