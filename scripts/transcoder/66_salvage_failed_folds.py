#!/usr/bin/env python3
"""경로 버그로 failed 로 기록된 행을 **디스크의 모델로** 복구한다.

무슨 일이 있었나
----------------
`--out-dir` 에 상대경로를 넘겨 `model_dir` 이 상대경로가 되었고,
`22_.fold_one` 의 `path.relative_to(PROJECT_ROOT)` 가 ValueError 로 터졌다.
폴드는 성공해 좌표까지 저장됐는데 예외가 그 직후에 나서 행이 failed 로
기록됐다. 2026-09-23 에 1,020 건이 이렇게 기록됐고 모델 1,011 개가 디스크에
남아 있다.

복구가 가능한 이유는 두 가지다.

    좌표      af2_models/*.pdb.gz 에 이미 있다
    pLDDT     실패 행에도 기록돼 있다 (payload 에서 먼저 꺼냈다)

따라서 **다시 접지 않고** 지표만 계산해 행을 채운다. AF2 를 부르지 않으므로
결과가 달라질 여지가 없다 - 같은 좌표에 같은 계산을 한다.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    out = Path(a.out_dir).resolve()
    csv_path = out / "af2_order_metric.csv"
    models = out / "af2_models"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    fields = list(rows[0].keys())

    #: 22_ 를 import 하면 모듈 로드 시 AF2 클라이언트까지 끌어온다. 지표
    #: 함수는 rapid_sr 에 있으므로 거기서 직접 가져온다 - **22_.fold_one 과
    #: 완전히 같은 호출 규격**이어야 결과가 달라지지 않는다.
    from pipeline_mcp.bio.pdb import dssp_non_loop_positions_by_chain
    from rapid_sr.clustered import kabsch_rmsd
    from rapid_sr.descriptors import ca_coords
    from rapid_sr.structural import (model_positions, non_loop_indices,
                                     positional_non_loop_rmsd)
    import json
    cand = {c["sequence_id"]: c for c in
            json.loads((out / "candidates.json").read_text(encoding="utf-8"))}

    refs: dict[str, tuple] = {}
    fixed = skipped = 0
    for r in rows:
        if r.get("status") == "ok":
            continue
        sid = r["sequence_id"]
        safe = sid.replace("|", "_").replace("/", "_")
        mp = models / f"{safe}.pdb.gz"
        if not mp.exists() or not r.get("plddt"):
            skipped += 1
            continue
        c = cand.get(sid)
        if not c:
            skipped += 1
            continue
        key = r["backbone_key"]
        if key not in refs:
            text = Path(c["backbone_pdb"]).read_text(encoding="utf-8", errors="replace")
            refs[key] = (text, dssp_non_loop_positions_by_chain(text))
        reference, mask = refs[key]
        with gzip.open(mp, "rt", encoding="utf-8") as h:
            model = h.read()
        keep = non_loop_indices(reference, mask)
        r["n_non_loop"] = len(keep)
        try:
            positions = model_positions(reference, model, sequence=c["sequence"])
            r["correspondence"] = ("file_order"
                                   if positions == list(range(len(positions)))
                                   else "numbering_span")
            r["rmsd_nonloop_order"] = positional_non_loop_rmsd(
                reference, model, mask, sequence=c["sequence"])
            r["rmsd_all_ca_order"] = round(float(kabsch_rmsd(
                ca_coords(model)[positions], ca_coords(reference))), 4)
        except ValueError as exc:
            # 22_ 와 같게 — 대응을 못 세우면 값을 비우고 status 는 ok 로 둔다.
            r["correspondence"] = f"refused: {exc}"
        r["status"] = "ok"
        r["error"] = ""
        r["model_path"] = str(mp)
        fixed += 1

    print(f"복구 {fixed} · 건너뜀 {skipped} · 전체 {len(rows)}")
    if a.dry_run:
        print("  (dry-run — 쓰지 않았다)")
        return 0
    bak = csv_path.with_suffix(".csv.bak-salvage")
    if not bak.exists():
        bak.write_bytes(csv_path.read_bytes())
    with csv_path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  {csv_path}  (백업 {bak.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
