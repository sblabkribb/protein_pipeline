#!/usr/bin/env python3
"""홀드아웃 타겟을 확정한다: 실패한 타겟을 같은 층의 예비로 순서대로 교체한다.

왜 스크립트인가
---------------
교체를 손으로 하면 어떤 규칙으로 무엇이 바뀌었는지가 남지 않는다. 규칙은 백본
생성 전에 freeze 했으므로 (holdout_targets.json 의 acceptance), 그것을 그대로
집행하는 코드가 있어야 감사가 된다.

규칙
----
1. 층마다 designs 가 목표치인 선정 타겟을 먼저 담는다.
2. 부족하면 그 층의 예비를 reserve_rank 순서로 넣는다. designs 가 부족한 예비는
   건너뛰고 다음 순위로 간다.
3. 목록을 다시 뽑지 않는다. 층이 목표 수를 못 채우면 채우지 못했다고 보고한다.
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"


def design_count(output_root: Path, domain: str) -> int:
    return len(list((output_root / f"holdout_{domain}_rfd3" / "rfd3"
                     / "designs").glob("*.pdb")))


def resolve(spec: dict, output_root: Path, *, per_stratum: int) -> dict:
    want = int(spec["backbone_plan"]["composition"]["rfd3"])
    groups: dict[str, dict] = collections.defaultdict(
        lambda: {"selected": [], "reserve": []})
    for row in spec["selected"]:
        groups[row["stratum"]]["selected"].append(row)
    for row in sorted(spec["reserve"], key=lambda r: r["reserve_rank"]):
        groups[row["stratum"]]["reserve"].append(row)

    targets, dropped, unused, short = [], [], [], []
    for stratum, group in sorted(groups.items()):
        kept = [r for r in group["selected"]
                if design_count(output_root, r["domain"]) >= want]
        failed = [r for r in group["selected"]
                  if design_count(output_root, r["domain"]) < want]
        pool = list(group["reserve"])

        for miss in failed:
            dropped.append({"domain": miss["domain"], "stratum": stratum,
                            "n_designs": design_count(output_root, miss["domain"])})
            if len(kept) >= per_stratum:
                continue
            while pool:
                cand = pool.pop(0)
                have = design_count(output_root, cand["domain"])
                if have >= want:
                    kept.append({**cand, "role": "reserve_substitute",
                                 "replaces": miss["domain"]})
                    break
                unused.append({"domain": cand["domain"], "stratum": stratum,
                               "n_designs": have, "why": "designs 부족"})

        if len(kept) < per_stratum:
            short.append({"stratum": stratum, "have": len(kept),
                          "want": per_stratum,
                          "reserve_left": [r["domain"] for r in pool]})
        unused += [{"domain": r["domain"], "stratum": stratum,
                    "why": "쓰지 않음"} for r in pool]
        targets += kept[:per_stratum]

    return {
        "rule": ("백본 생성 전에 freeze 한 교체 규칙을 그대로 집행한다 - 실패한 "
                 "선정 타겟을 같은 층의 예비로 reserve_rank 순서대로 교체하고, "
                 "목록을 다시 뽑지 않는다."),
        "per_stratum": per_stratum,
        "n_targets": len(targets),
        "by_stratum": dict(collections.Counter(r["stratum"] for r in targets)),
        "targets": targets,
        "dropped": dropped,
        "unused_reserve": unused,
        "short_strata": short,
        "resolved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", default=str(BASE / "holdout_targets.json"))
    parser.add_argument("--output-root", default="/opt/protein_pipeline/outputs")
    parser.add_argument("--per-stratum", type=int, default=4)
    parser.add_argument("--write", action="store_true",
                        help="holdout_targets.json 의 resolved 를 갱신한다")
    args = parser.parse_args(argv)

    path = Path(args.holdout)
    spec = json.loads(path.read_text(encoding="utf-8"))
    result = resolve(spec, Path(args.output_root), per_stratum=args.per_stratum)

    print(f"확정 {result['n_targets']} 타겟 · 층별 {result['by_stratum']}")
    for row in result["targets"]:
        tag = f"  <- {row['replaces']} 대체" if row.get("replaces") else ""
        print(f"  [{row['stratum']:>8}] {row['domain']:10s} {row['length']:4d} 잔기{tag}")
    if result["dropped"]:
        print("\n제외:")
        for row in result["dropped"]:
            print(f"  {row['domain']:10s} [{row['stratum']}] designs {row['n_designs']}")
    if result["short_strata"]:
        print("\n채우지 못한 층 (목록을 다시 뽑지 않는다):")
        for row in result["short_strata"]:
            print(f"  {row['stratum']}: {row['have']}/{row['want']} · "
                  f"남은 예비 {row['reserve_left'] or '없음'}")
    if result["unused_reserve"]:
        print("\n미사용 예비: " + ", ".join(
            f"{r['domain']}({r['why']})" for r in result["unused_reserve"]))

    if args.write:
        spec["resolved"] = result
        path.write_text(json.dumps(spec, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        print(f"\nwrote {path}")
    else:
        print("\n(미리보기 - 반영하려면 --write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
