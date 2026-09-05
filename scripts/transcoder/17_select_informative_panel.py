#!/usr/bin/env python3
"""온도 실험용 informative backbone panel 을 고르고 동결한다.

1 차 온도 패널 15 개 중 12 개가 모든 온도에서 structural_yield 0.000 또는
1.000 이었다. 움직일 수 없는 백본의 "차이 0" 을 클러스터 부트스트랩이 합의로
세면서 판정이 뒤집혔다. 이 스크립트는 그 실패를 반복하지 않도록 **baseline
yield 가 중간인 백본만** 고르고, 고른 이유를 실행 전에 동결한다.

선정에 쓰는 정보는 게이트 0 캠페인의 baseline joint/structural pass yield 뿐이다.
온도 sweep 결과와 global_score 는 코드 수준에서 차단한다 (`--forbid-columns`).

동결이 왜 필요한가. 결과를 보고 기준을 손보면 그 순간 선정이 결과의 함수가 된다.
목록과 기준을 실행 전에 파일로 고정하고 입력 파일의 해시를 함께 남긴다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.bio.pdb import dssp_non_loop_positions_by_chain  # noqa: E402
from rapid_sr.descriptors import ca_coords  # noqa: E402
from rapid_sr.panel import (  # noqa: E402
    SELECTION_CRITERIA, build_manifest, eligible_backbones, select_panel,
    sha256_of, write_manifest, yield_band,
)


def structure_reader(pdb_dir: Path):
    """백본 PDB 에서 사슬 수와 잔기 수를 읽는다. 백본당 한 번만 읽고 캐싱한다."""
    cache: dict[str, dict] = {}

    def read(row) -> dict:
        key = row["backbone_key"]
        if key not in cache:
            text = (pdb_dir / row["pdb_file"]).read_text(encoding="utf-8", errors="replace")
            cache[key] = {
                "n_residues": len(ca_coords(text)),
                "n_chains": len({line[21] for line in text.splitlines()
                                 if line.startswith("ATOM")}),
                # 캠페인 RMSD 가 실제로 쓰는 위치 수. 이것이 적으면 structural
                # endpoint 는 판정할 대상이 없다.
                "n_non_loop": sum(
                    len(v) for v in dssp_non_loop_positions_by_chain(text).values()),
            }
        return cache[key]

    return read

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
DEFAULT_LABELS = BASE / "backbones" / "backbone_labels.csv"
DEFAULT_OUT = BASE / "temperature_panel2" / "panel_manifest.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--pdb-dir", type=Path, default=BASE / "backbones" / "pdb")
    parser.add_argument("--size", type=int, default=27, help="24-30 사이를 권장한다.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--previous-panel", type=Path,
                        default=BASE / "temperature_sweep" / "af2_stage1.csv",
                        help="겹치는 백본을 기록하기 위해서만 읽는다. 선정에는 쓰지 않는다.")
    parser.add_argument("--force", action="store_true",
                        help="이미 동결된 manifest 를 덮어쓴다.")
    args = parser.parse_args(argv)

    if args.out.exists() and not args.force:
        print(f"이미 동결된 manifest 가 있다: {args.out}\n"
              f"결과를 보고 기준을 바꾸지 않기 위해 덮어쓰지 않는다. "
              f"정말 다시 뽑으려면 --force.", file=sys.stderr)
        return 2

    rows = list(csv.DictReader(args.labels.open(encoding="utf-8")))
    structure = structure_reader(args.pdb_dir)
    pool = eligible_backbones(rows, structure_info=structure)
    print(f"전체 {len(rows)} · 적격 {len(pool)} "
          f"(baseline joint·structural 둘 다 (0,1), n>={SELECTION_CRITERIA['min_sequences_with_af2']}, "
          f"단일 사슬, <={SELECTION_CRITERIA['max_residues']} 잔기, "
          f"non-loop>={SELECTION_CRITERIA['min_non_loop_positions']})")

    picked = select_panel(rows, target_size=args.size, seed=args.seed,
                          structure_info=structure)
    if not 24 <= len(picked) <= 30:
        print(f"경고: 선정 {len(picked)} 개는 권장 범위 24-30 밖이다. "
              f"적격 후보가 부족하면 이것이 최선이다.", file=sys.stderr)

    manifest = build_manifest(picked, source_path=args.labels.relative_to(PROJECT_ROOT),
                              seed=args.seed, source_sha256=sha256_of(args.labels))

    # 겹침은 기록만 한다. 겹친다고 빼면 그 자체가 온도 실험 정보를 선정에 쓰는 것이다.
    if args.previous_panel.exists():
        previous = {r["backbone_key"] for r in csv.DictReader(args.previous_panel.open(encoding="utf-8"))}
        overlap = sorted({e["backbone_key"] for e in manifest["backbones"]} & previous)
        manifest["previous_panel_overlap"] = overlap
        manifest["previous_panel_note"] = (
            "겹침은 기록만 한다. 1 차 패널에 있었다는 이유로 제외하면 온도 실험의 "
            "정보를 선정에 쓰는 셈이 된다. 분석에서는 두 패널을 분리해 보고한다."
        )

    write_manifest(manifest, args.out)

    print(f"\n선정 {manifest['n_selected']} 개")
    print(f"  소스   {manifest['source_distribution']}")
    print(f"  밴드   {manifest['band_distribution']}  (0:(0,.25] 1:(.25,.5] 2:(.5,.75] 3:(.75,1))")
    print(f"  타겟   {len(manifest['target_distribution'])} 개 "
          f"(최대 {max(manifest['target_distribution'].values())} 개/타겟)")
    if manifest.get("previous_panel_overlap"):
        print(f"  1차 패널과 겹침 {len(manifest['previous_panel_overlap'])} 개: "
              f"{manifest['previous_panel_overlap']}")
    print(f"  AF2 예상 {manifest['expected_af2_folds']} 폴드 · "
          f"워커 1개 기준 {manifest['expected_af2_worker_seconds'] / 3600:.1f} 시간")
    print(f"  예상 정보 백본 {manifest['expected_informative_backbones']}/{manifest['n_selected']}")
    print(f"\n{'backbone':50s} {'src':>7s} {'joint':>7s} {'struct':>7s} {'aa':>5s} {'nl':>4s} {'band':>4s}")
    for entry in sorted(manifest["backbones"], key=lambda e: (e["yield_band"], e["backbone_key"])):
        print(f"{entry['backbone_key']:50s} {entry['backbone_source']:>7s} "
              f"{entry['baseline_joint_yield']:>7.3f} {entry['baseline_structural_yield']:>7.3f} "
              f"{entry['n_residues'] or 0:>5d} {entry['n_non_loop_positions'] or 0:>4d} "
              f"{entry['yield_band']:>4d}")
    print(f"\n동결: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
