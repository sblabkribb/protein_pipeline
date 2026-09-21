#!/usr/bin/env python3
"""깊이 확장 파일럿 - 기존 RFD3 confirmatory 백본의 후보를 18 -> 42 로 늘린다.

규칙은 `docs/specs/depth-scaling-pilot-prespec.md` 에 실행 전 동결돼 있다.
여기서 그 문서에 없는 선택을 새로 하지 않는다.

왜 하는가
---------
8,640 fold 확증 코호트는 "깊이가 허용되면 greedy 효과가 커진다" 는 **검증되지
않은 가정** 위에 있다. 1,800 fold 로 그 가정만 먼저 본다.

무엇을 재사용하는가
-------------------
백본·MSA·보존도를 전부 기존 것으로 쓴다. **새 backbone 생성도 MSA 도 없다.**
필요한 것은 서열 설계와 폴딩뿐이다.

    백본      v2_multisource/backbones.json 의 backbone_paths (75 개)
    보존도    동결된 full_msa_manifest.json
    tier      기존 6/6/6 에 +8/+8/+8 -> 14/14/14

seed 를 바꾸지 않으면 ProteinMPNN 이 같은 서열을 재생하므로 `EXT_SEED` 를
따로 쓰고, 그래도 겹치는 것은 버린다. **버린 만큼 재시도로 채우지 않는다.**

동결 산출물을 덮어쓰지 않는다
-----------------------------
결과는 `depth_pilot/` 에 따로 쓴다. `v2_multisource/candidates.json` 과
`af2_order_metric.csv` 위에는 동결된 v2 판정이 서 있다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
V2 = BASE / "v2_multisource"
OUT = BASE / "depth_pilot"

#: 사전지정 §3-§4. 바꾸지 않는다.
UNITS = ["1j5uA01", "1n81A00", "1sdiA00", "1x3aA00",
         "4ai2A02", "4ifxA00", "4wexA00", "6vqfA00"]
SOURCE, COHORT = "rfd3", "confirmatory"
NEW_PER_TIER = 8                 # 기존 6 + 8 = 14, tier 3 개 -> 42
EXT_SEED = 20260922


def _m52():
    spec = importlib.util.spec_from_file_location(
        "m52", HERE / "52_v2_multisource_campaign.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def design(m52, *, mpnn_url: str, soluprot_url: str, timeout: float) -> list[dict]:
    from pipeline_mcp.clients.proteinmpnn import ProteinMPNNClient
    from pipeline_mcp.clients.soluprot import SoluProtClient
    from pipeline_mcp.models import SequenceRecord
    from rapid_sr.protocol import GATE0_MPNN_SETTINGS

    msa = {t["domain"]: t for t in
           json.loads((BASE / "full_msa_manifest.json").read_text("utf-8"))["targets"]}
    state = json.loads((V2 / "backbones.json").read_text("utf-8"))["runs"]
    old = json.loads((V2 / "candidates.json").read_text("utf-8"))
    #: 같은 백본에서 이미 있는 서열. 문자열이 같으면 새로 접을 이유가 없다.
    seen: dict[str, set[str]] = {}
    for c in old:
        seen.setdefault(c["backbone_key"], set()).add(c["sequence"])

    mpnn = ProteinMPNNClient(runpod=None, endpoint_id=None, gpu_url=mpnn_url,
                             gpu_timeout_s=timeout)
    soluprot = SoluProtClient(url=soluprot_url)

    out_path = OUT / "candidates_ext.json"
    rows = (json.loads(out_path.read_text("utf-8")) if out_path.exists() else [])
    done = {r["backbone_key"] for r in rows}

    runs = [r for r in state.values()
            if r["cohort"] == COHORT and r["backbone_source"] == SOURCE
            and r["target_id"] in UNITS and r.get("u_accepted", 0) > 0]
    n_bb = sum(len(r["backbone_paths"]) for r in runs)
    print(f"[A] 대상 run {len(runs)} · 백본 {n_bb} · 목표 신규 "
          f"{n_bb * NEW_PER_TIER * 3}", flush=True)

    for run in sorted(runs, key=lambda r: r["target_id"]):
        row = msa[run["target_id"]]
        row = {**row, "target_id": row["domain"]}
        fixed = m52.tier_fixed_positions(row)
        for bb_index, pdb_path in enumerate(run["backbone_paths"]):
            bkey = f"{run['target_id']}|{run['backbone_source']}|b{bb_index}"
            if bkey in done:
                continue
            text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
            chain = m52.backbone_chain_id(text)
            produced, dropped = [], 0
            for tier in ("30", "50", "70"):
                try:
                    _n, samples, _meta = mpnn.design(
                        pdb_text=text, pdb_name=bkey.replace("|", "_"),
                        fixed_positions={chain: fixed[tier]},
                        use_soluble_model=bool(GATE0_MPNN_SETTINGS["use_soluble_model"]),
                        model_name=str(GATE0_MPNN_SETTINGS["model_name"]),
                        num_seq_per_target=NEW_PER_TIER,
                        batch_size=int(GATE0_MPNN_SETTINGS["batch_size"]),
                        sampling_temp=float(GATE0_MPNN_SETTINGS["sampling_temp"]),
                        seed=EXT_SEED)
                except Exception as exc:
                    print(f"  [mpnn 실패] {bkey} tier {tier}: "
                          f"{type(exc).__name__}: {exc}"[:160], flush=True)
                    continue
                have = seen.setdefault(bkey, set())
                for i, s in enumerate(x for x in samples if x.sequence):
                    if s.sequence in have:       # 기존 18 개 또는 신규끼리 중복
                        dropped += 1
                        continue
                    have.add(s.sequence)
                    produced.append({
                        "sequence_id": f"{bkey}|t{tier}|x{i}",
                        "sequence": s.sequence,
                        "temperature": float(GATE0_MPNN_SETTINGS["sampling_temp"]),
                        "conservation_tier": float(tier) / 100.0,
                        "backbone_key": bkey, "backbone_pdb": pdb_path,
                        "target_id": run["target_id"],
                        "backbone_source": run["backbone_source"],
                        "cohort": run["cohort"], "depth_extension": True,
                    })
            if not produced:
                continue
            try:
                scores = soluprot.score([SequenceRecord(id=p["sequence_id"],
                                                        sequence=p["sequence"])
                                         for p in produced])
            except Exception as exc:
                print(f"  [soluprot 실패] {type(exc).__name__}: {exc}"[:140],
                      flush=True)
                scores = {}
            for p in produced:
                p["soluprot"] = scores.get(p["sequence_id"])
            rows.extend(produced)
            OUT.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(rows, ensure_ascii=False), "utf-8")
            print(f"  {bkey}: 신규 {len(produced)}/24"
                  + (f" (중복 {dropped} 버림)" if dropped else ""), flush=True)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="all", choices=["design", "fold", "all"])
    ap.add_argument("--gpu-host", default="211.188.35.221")
    #: SoluProt 은 GPU 호스트가 아니라 배포 호스트의 로컬 서비스다
    #: (.env 의 SOLUPROT_URL=http://127.0.0.1:18081/score).
    ap.add_argument("--soluprot-url",
                    default=os.environ.get("SOLUPROT_URL",
                                           "http://127.0.0.1:18081/score"))
    ap.add_argument("--fold-workers", type=int, default=4)
    ap.add_argument("--af2-timeout", type=float, default=7200.0)
    ap.add_argument("--mpnn-timeout", type=float, default=1800.0)
    a = ap.parse_args(argv)

    m52 = _m52()
    #: 폴딩 산출물이 동결된 v2 디렉터리에 떨어지지 않게 한다.
    m52.OUT_DIR = OUT
    OUT.mkdir(parents=True, exist_ok=True)

    rows = []
    if a.stage in ("design", "all"):
        rows = design(m52, mpnn_url=f"http://{a.gpu_host}:18101",
                      soluprot_url=a.soluprot_url, timeout=a.mpnn_timeout)
    if a.stage in ("fold", "all"):
        p = OUT / "candidates_ext.json"
        rows = json.loads(p.read_text("utf-8")) if p.exists() else rows
        if not rows:
            raise SystemExit("접을 후보가 없다. design 을 먼저 돌린다.")
        m52.stage_fold(rows, colabfold_url=f"http://{a.gpu_host}:18160",
                       workers=a.fold_workers, timeout_s=a.af2_timeout)
    print(f"\n산출물 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
