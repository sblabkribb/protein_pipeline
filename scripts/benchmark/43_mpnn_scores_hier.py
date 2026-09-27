#!/usr/bin/env python3
"""확증 코호트 서열의 백본 조건부 MPNN NLL 을 미리 채점해 캐시한다.

`42_hierarchical_confirmatory.py` 의 `mpnn_only` arm 이 쓴다. 정의는 `33_`
(v2 baseline) 과 **같다** - 자기 백본 위에서의 잔기당 평균 NLL 을 무작위
디코딩 순서로 평균한 값이고 **낮을수록 그럴듯하다.**

폴딩 결과와 무관하다. 후보 서열과 백본 PDB 만 읽으므로 언제 돌려도 같은 값이
나오고, 라벨을 보지 않으므로 결과에 의존하는 선택이 끼어들 여지가 없다.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

#: `33_` 과 같은 값을 쓴다. 코호트마다 바꾸지 않는다.
MPNN_ORDERS, MPNN_SEED = 4, 20260921


def _mod(p, n):
    s = importlib.util.spec_from_file_location(n, HERE / p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=str(BASE / "hier_confirmatory"))
    ap.add_argument("--limit", type=int, default=0,
                    help="백본 n 개만 채점한다 (속도 측정용). 0 이면 전부")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)

    cohort = Path(a.cohort)
    out_path = Path(a.out) if a.out else cohort / "mpnn_scores.json"
    cand = json.loads((cohort / "candidates.json").read_text(encoding="utf-8"))

    by_bb = collections.defaultdict(list)
    pdb_of = {}
    for c in cand:
        by_bb[c["backbone_key"]].append((c["sequence_id"], c["sequence"]))
        pdb_of[c["backbone_key"]] = c["backbone_pdb"]

    have = {}
    if out_path.exists():
        have = json.loads(out_path.read_text(encoding="utf-8")).get("scores", {})
    todo = [b for b in sorted(by_bb)
            if not all(s in have for s, _ in by_bb[b])]
    if a.limit:
        todo = todo[:a.limit]
    print(f"백본 {len(by_bb)} · 서열 {len(cand)} · 채점할 백본 {len(todo)}", flush=True)
    if not todo:
        print("이미 전부 있다")
        return 0

    m27 = _mod("27_gate2d_prepare_mpnn_scores.py", "m27")
    model = m27.ENC.load_model()
    t0 = time.monotonic()
    for i, b in enumerate(todo, 1):
        have.update(m27.score_backbone(pdb_of[b], by_bb[b], model=model,
                                       n_orders=MPNN_ORDERS, seed=MPNN_SEED))
        if i % 10 == 0 or i == len(todo):
            rate = (time.monotonic() - t0) / i
            print(f"  {i}/{len(todo)} · {rate:.1f}s/백본 "
                  f"(~{(len(todo)-i)*rate/60:.1f}분 남음)", flush=True)
            out_path.write_text(json.dumps({
                "definition": ("per-residue mean NLL of the design sequence on its "
                               "own backbone, averaged over random decoding orders. "
                               "Lower is better."),
                "n_decoding_orders": MPNN_ORDERS, "seed": MPNN_SEED,
                "cohort": cohort.name, "scores": have},
                ensure_ascii=False), encoding="utf-8")
    print(f"{out_path} · 점수 {len(have)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
