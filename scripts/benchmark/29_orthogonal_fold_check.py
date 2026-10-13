#!/usr/bin/env python3
"""joint-pass 후보를 **독립 접힘 예측기**로 다시 접어 self-consistency 를 교차 확인한다.

왜 필요한가
-----------
`joint-pass` 의 구조 조건(pLDDT >= 85 AND 비루프 Cα-RMSD <= 2.0 Å)은 "ProteinMPNN
이 만든 서열을 AF2 가 원래 백본으로 되접는가" 를 본다. 그런데 ProteinMPNN 은
AF2 가 선호하는 서열을 만들도록 학습된 도구이므로 두 모델이 편향을 공유한다.
즉 이 기준은 **설계 파이프라인의 내부 일관성**을 재는 것이지 구조가 실제로
맞다는 증거가 아니다.

ESMFold 는 MSA 를 쓰지 않고 단백질 언어모델만으로 접으므로 AF2 와 학습·입력이
다르다. 같은 후보가 ESMFold 에서도 같은 백본으로 되접히면 self-consistency 가
AF2 특이적이지 않다는 근거가 되고, 되접히지 않으면 현행 기준이 AF2-MPNN
순환을 재고 있었다는 뜻이다. **어느 쪽이든 해석에 필요한 정보다.**

하지 않는 것
------------
- 동결된 joint-pass 정의를 바꾸지 않는다. 판정은 AF2 기준 그대로다.
- 이 결과로 후보를 다시 고르지 않는다. 사후 기술 통계다.
- ESMFold 가 AF2 보다 옳다고 주장하지 않는다. **불일치의 존재**만 본다.

RMSD 는 동결된 지표 경로(`22_refold_with_artifacts.fold_one`)와 같은 함수를 쓴다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
OUT_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "orthogonal_fold"

#: 동결 문턱. 판정을 바꾸지 않으므로 여기서도 같은 값을 쓴다.
PLDDT_MIN = 85.0
RMSD_MAX = 2.0
SOLUPROT_MIN = 0.5


def _worker_url(port: int) -> str:
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    return f"http://{host}:{port}" if host else ""


def _refold_module():
    path = PROJECT_ROOT / "scripts" / "transcoder" / "22_refold_with_artifacts.py"
    spec = importlib.util.spec_from_file_location("refold_artifacts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def joint_pass_rows() -> list[dict]:
    """AF2 기준으로 joint-pass 한 후보. 여기서 기준을 바꾸지 않는다."""
    metric = {r["sequence_id"]: r for r in
              csv.DictReader((GRID / "af2_order_metric.csv").open(encoding="utf-8"))
              if r.get("status") == "ok"}
    seqs = {r["sequence_id"]: r["sequence"] for r in
            csv.DictReader((GRID / "sequences.csv").open(encoding="utf-8"))}

    def num(r, k):
        try:
            return float(r[k])
        except (TypeError, ValueError):
            return None

    out = []
    for sid, r in metric.items():
        p, d, s = num(r, "plddt"), num(r, "rmsd_nonloop_order"), num(r, "soluprot")
        if p is None or d is None or s is None:
            continue
        if p >= PLDDT_MIN and d <= RMSD_MAX and s >= SOLUPROT_MIN and sid in seqs:
            out.append({**r, "sequence": seqs[sid]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="파일럿용. 0 이면 전부.")
    ap.add_argument("--sources", default="rfd3",
                    help="쉼표 구분. 기본은 배분 주장이 걸린 rfd3 코호트.")
    ap.add_argument("--workers", type=int, default=2,
                    help="낮게 잡는다 - 진행 중인 ColabFold 와 GPU 를 나눠 쓴다.")
    ap.add_argument("--esmfold-url", default="")
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("--out", default=str(OUT_DIR / "esmfold_cross_check.csv"))
    args = ap.parse_args(argv)

    from pipeline_mcp.bio.pdb import dssp_non_loop_positions_by_chain
    from pipeline_mcp.clients.esmfold import LocalHTTPESMFoldClient
    from pipeline_mcp.models import SequenceRecord

    refold = _refold_module()
    url = args.esmfold_url or _worker_url(18162)
    if not url:
        raise SystemExit("ESMFold URL 이 없다 (RAPID_GPU_HOST 또는 --esmfold-url)")

    rows = joint_pass_rows()
    want = {s.strip() for s in args.sources.split(",") if s.strip()}
    rows = [r for r in rows if r.get("backbone_source") in want]
    if args.limit:
        rows = rows[: args.limit]
    print(f"AF2 joint-pass 후보 {len(rows)} (source={sorted(want)}) · "
          f"ESMFold {url} · workers {args.workers}", flush=True)

    # 기준 백본과 비루프 마스크. 동결 경로와 같은 함수를 쓴다.
    gen = json.loads((PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
                      / "holdout_generation.json").read_text(encoding="utf-8"))
    hold = json.loads((PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
                       / "holdout_targets.json").read_text(encoding="utf-8"))
    # 26_holdout_grid.collect_backbones 는 (backbones, incomplete) 를 돌려준다.
    # 기준 백본 목록을 여기서 다시 구현하지 않는다 - 격자를 만든 것과 같은
    # 함수를 써야 backbone_key 와 PDB 경로가 어긋나지 않는다.
    import importlib.util as iu
    spec = iu.spec_from_file_location(
        "grid", PROJECT_ROOT / "scripts" / "transcoder" / "26_holdout_grid.py")
    m = iu.module_from_spec(spec)
    spec.loader.exec_module(m)
    bbs, _incomplete = m.collect_backbones(
        hold, gen, Path("/opt/protein_pipeline/outputs"))
    pdb_by_key = {b["backbone_key"]: b["pdb_path"] for b in bbs}

    refs = {}
    missing = set()
    for r in rows:
        k = r["backbone_key"]
        if k in refs or k in missing:
            continue
        p = pdb_by_key.get(k)
        if not p:
            missing.add(k); continue
        t = Path(p).read_text(encoding="utf-8", errors="replace")
        refs[k] = (t, dssp_non_loop_positions_by_chain(t),
                   hashlib.sha256(t.encode()).hexdigest())
    if missing:
        print(f"  기준 백본 없음 {len(missing)} 개 - 해당 후보는 건너뛴다", flush=True)
    rows = [r for r in rows if r["backbone_key"] in refs]

    out_csv = Path(args.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if out_csv.exists():
        for r in csv.DictReader(out_csv.open(encoding="utf-8")):
            if r.get("status") == "ok":
                done[r["sequence_id"]] = r
    pending = [r for r in rows if r["sequence_id"] not in done]
    print(f"  전체 {len(rows)} · 완료 {len(done)} · 남은 {len(pending)}", flush=True)

    client = LocalHTTPESMFoldClient(base_url=url, token=None,
                                    timeout_s=args.timeout)

    results = list(done.values())
    lock = threading.Lock()
    started = time.monotonic()
    n = 0
    fields = ["sequence_id", "backbone_key", "target_id", "backbone_source",
              "af2_plddt", "af2_rmsd_nonloop_order", "soluprot",
              "esmfold_plddt", "esmfold_rmsd_nonloop_order",
              "esmfold_rmsd_pass", "esmfold_structural_pass",
              "reference_sha256", "status", "error"]

    def flush():
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(results)

    def work(row):
        nonlocal n
        sid = row["sequence_id"]
        reference, mask, ref_sha = refs[row["backbone_key"]]
        entry = {"sequence_id": sid, "backbone_key": row["backbone_key"],
                 "target_id": row["target_id"],
                 "backbone_source": row.get("backbone_source"),
                 "af2_plddt": row.get("plddt"),
                 "af2_rmsd_nonloop_order": row.get("rmsd_nonloop_order"),
                 "soluprot": row.get("soluprot"),
                 "reference_sha256": ref_sha}
        try:
            safe = sid.replace("|", "_").replace("/", "_")
            res = client.predict([SequenceRecord(id=safe, sequence=row["sequence"])])
            payload = (res or {}).get(safe) if isinstance(res, dict) else None
            payload = payload if isinstance(payload, dict) else {}
            model = payload.get("pdb") or payload.get("ranked_0_pdb") or ""
            entry["esmfold_plddt"] = payload.get("best_plddt")
            if not model:
                entry["status"] = "failed"; entry["error"] = "ESMFold 가 모델을 안 줌"
            else:
                rmsd = refold.positional_non_loop_rmsd(
                    reference, model, mask, sequence=row["sequence"])
                entry["esmfold_rmsd_nonloop_order"] = rmsd
                pl = entry.get("esmfold_plddt")
                # **기하만** 보는 판정. pLDDT 문턱 85 는 MSA 를 쓴 AF2 에
                # 맞춰 정해진 값이라 단일서열 ESMFold 에 그대로 옮길 수 없다
                # (파일럿에서 ESMFold pLDDT 는 56-81 로 전부 85 미만이었다).
                # RMSD 는 같은 기준 백본에 대한 기하 측정이므로 비교 가능하다.
                entry["esmfold_rmsd_pass"] = bool(
                    rmsd is not None and float(rmsd) <= RMSD_MAX)
                # 참고용. 문턱 이식 문제가 있으므로 1 차 판단에 쓰지 않는다.
                entry["esmfold_structural_pass"] = bool(
                    pl is not None and rmsd is not None
                    and float(pl) >= PLDDT_MIN and float(rmsd) <= RMSD_MAX)
                entry["status"] = "ok"
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        with lock:
            results.append(entry); n += 1
            if n % 10 == 0 or n == len(pending):
                rate = (time.monotonic() - started) / n
                print(f"  [X] {n}/{len(pending)} ({rate:.1f} s/건, "
                      f"~{(len(pending)-n)*rate/60:.0f}분 남음)", flush=True)
                flush()

    if pending:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(work, pending))
    flush()
    ok = [r for r in results if r.get("status") == "ok"]
    agree = [r for r in ok if str(r.get("esmfold_rmsd_pass")) == "True"]
    print(f"\nESMFold 완료 {len(ok)}/{len(results)}")
    if ok:
        print(f"  AF2 joint-pass 중 ESMFold 에서도 RMSD<=2.0 Å: {len(agree)} "
              f"({len(agree)/len(ok)*100:.1f}%)")
        print("  (pLDDT 문턱은 AF2+MSA 기준이라 ESMFold 에 이식하지 않는다)")
    print(f"  {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
