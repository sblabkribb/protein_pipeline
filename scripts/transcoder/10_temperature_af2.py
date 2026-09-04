#!/usr/bin/env python3
"""Temperature sweep 2단계: paired AF2 subset.

선정 규칙(중요): 백본마다 **동일한 index 8개**를 골라 네 온도 모두에 넣는다.
15 backbone x 8 index x 4 T = 480. global_score 로 고르면 온도 효과와 선택
효과가 교란되므로 점수 기반 선택을 하지 않는다.

1단계 480 을 먼저 돌리고, 구간이 넓을 때만 나머지 index 8개를 추가한다.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys
import time

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client  # noqa: E402
from pipeline_mcp.models import SequenceRecord  # noqa: E402

from rapid_sr.clustered import kabsch_rmsd  # noqa: E402
from rapid_sr.descriptors import ca_coords  # noqa: E402


def select_paired(rows: list[dict], *, n_per_condition: int, offset: int) -> list[dict]:
    """백본마다 같은 index 집합을 모든 온도에서 고른다.

    index 는 sequence_id 끝의 순번이다. 온도별로 다른 서열을 고르면 paired 설계가
    깨지므로 index 를 기준으로만 자른다.
    """
    by_cond: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_cond[(row["backbone_key"], row["temperature"])].append(row)

    wanted = set(range(offset, offset + n_per_condition))
    picked: list[dict] = []
    for (_backbone, _temp), items in by_cond.items():
        items.sort(key=lambda r: int(str(r["sequence_id"]).rsplit("|", 1)[-1]))
        for item in items:
            if int(str(item["sequence_id"]).rsplit("|", 1)[-1]) in wanted:
                picked.append(item)
    return picked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
    parser.add_argument("--sequences", default=str(base / "temperature_sweep" / "sequences.csv"))
    parser.add_argument("--pdb-dir", default=str(base / "backbones" / "pdb"))
    parser.add_argument("--labels", default=str(base / "backbones" / "backbone_labels.csv"))
    parser.add_argument("--colabfold-url", default="http://211.188.35.221:18160")
    parser.add_argument("--n-per-condition", type=int, default=8)
    parser.add_argument("--offset", type=int, default=0, help="2단계에서는 8 로 준다")
    parser.add_argument("--out", default=str(base / "temperature_sweep" / "af2_stage1.csv"))
    parser.add_argument("--limit", type=int, default=0,
                        help="스모크용. 앞에서 이만큼만 폴딩한다.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    with open(args.sequences, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    picked = select_paired(rows, n_per_condition=args.n_per_condition, offset=args.offset)

    per_temp = defaultdict(int)
    for row in picked:
        per_temp[row["temperature"]] += 1
    print(f"selected={len(picked)} per_temperature={dict(sorted(per_temp.items()))} "
          f"backbones={len({r['backbone_key'] for r in picked})}", flush=True)
    if len(set(per_temp.values())) != 1:
        raise SystemExit(f"온도별 표본이 불균형하다: {dict(per_temp)}")
    if args.dry_run:
        return 0
    if args.limit > 0:
        picked = picked[: args.limit]
        print(f"[smoke] limit={args.limit}", flush=True)

    with open(args.labels, newline="", encoding="utf-8") as handle:
        pdb_of = {r["backbone_key"]: r["pdb_file"] for r in csv.DictReader(handle)}
    backbone_ca = {
        key: ca_coords((Path(args.pdb_dir) / name).read_text(encoding="utf-8", errors="replace"))
        for key, name in pdb_of.items()
    }

    client = LocalHTTPAlphaFold2Client(args.colabfold_url, None, 7200.0)
    out_path = Path(args.out)
    done: set[str] = set()
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as handle:
            existing = list(csv.DictReader(handle))
        done = {r["sequence_id"] for r in existing}
        print(f"resume: {len(done)} already folded", flush=True)
    else:
        existing = []

    started = time.monotonic()
    for index, row in enumerate(picked, start=1):
        if row["sequence_id"] in done:
            continue
        safe = row["sequence_id"].replace("|", "_")
        record = SequenceRecord(id=safe, sequence=row["sequence"])
        entry = {
            "sequence_id": row["sequence_id"], "backbone_key": row["backbone_key"],
            "target_id": row["target_id"], "temperature": row["temperature"],
            "backbone_source": row.get("backbone_source", "target"),
            "soluprot": row.get("soluprot"), "global_score": row.get("global_score"),
        }
        try:
            result = client.predict([record])
            payload = result.get(safe) if isinstance(result, dict) else None
            payload = payload if isinstance(payload, dict) else {}
            entry["plddt"] = payload.get("best_plddt")
            pdb_text = payload.get("ranked_0_pdb") or payload.get("pdb") or ""
            reference = backbone_ca.get(row["backbone_key"])
            if pdb_text and reference is not None and reference.size:
                entry["rmsd"] = round(kabsch_rmsd(ca_coords(pdb_text), reference), 4)
            entry["status"] = "ok"
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        existing.append(entry)

        fields = ["sequence_id", "backbone_key", "target_id", "temperature",
                  "backbone_source", "soluprot", "global_score",
                  "plddt", "rmsd", "status", "error"]
        with open(out_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(existing)
        if index % 20 == 0:
            print(f"  {index}/{len(picked)} ({time.monotonic()-started:.0f}s)", flush=True)

    print(f"\nwrote {out_path} rows={len(existing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
