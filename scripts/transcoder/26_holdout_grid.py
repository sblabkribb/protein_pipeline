#!/usr/bin/env python3
"""홀드아웃 완전 격자 (2 단계): 6 arm x 24 깊이 x 12 타겟.

왜 격자인가
-----------
static top-K 는 비적응적이라 k 와 예산이 정해지면 어느 arm 에 몇 번 접을지가
사전에 결정되고, 그 폴드들은 완전 격자의 부분집합이다. 적응 정책도 모든
가능한 행동에 기록된 결과가 있으면 결정 순서가 실시간 실행과 동일하다.
따라서 격자를 한 번 채우면 예산 <=24 전부와 k 전부를 얻고, 모든 정책이
동일한 폴드 결과를 보므로 정확히 대응된 비교가 된다.

지금의 시뮬레이션과 다른 점: 시뮬레이션은 관측된 집계 yield 에서 베르누이
추출을 한다. 격자는 처음 보는 타겟의 개별 폴드 실제 결과를 쓴다.

지표
----
22_refold_with_artifacts.py 의 `fold_one` 을 그대로 불러 쓴다. 동결된
sequence-order 대응을 두 곳에 구현하지 않기 위해서다. 기준 구조는 각 백본
자신의 PDB 다 - 게이트 0 의 규약이고, 설계는 자신이 설계된 백본을 재현해야
한다.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.bio.pdb import dssp_non_loop_positions_by_chain  # noqa: E402
from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client  # noqa: E402
from pipeline_mcp.clients.proteinmpnn import ProteinMPNNClient  # noqa: E402
from pipeline_mcp.clients.soluprot import SoluProtClient  # noqa: E402
from pipeline_mcp.models import SequenceRecord  # noqa: E402
from rapid_sr.protocol import GATE0_MPNN_SETTINGS, protocol_fingerprint  # noqa: E402

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID = BASE / "holdout_grid"
#: 격자 조건. 온도는 고정 - 이 실험에서 변하는 것은 어느 백본을 접을지다.
GRID_TEMPERATURE = 0.1


def _refold_module():
    """동결된 지표 경로를 두 번 구현하지 않는다."""
    path = PROJECT_ROOT / "scripts" / "transcoder" / "22_refold_with_artifacts.py"
    spec = importlib.util.spec_from_file_location("refold_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect_backbones(holdout: dict, generation: dict, output_root: Path) -> list[dict]:
    """타겟당 native 1 개와 RFD3 5 개를 모은다.

    RFD3 산출물이 없는 타겟은 건너뛰고 목록에 남긴다 - 조용히 줄이지 않는다.
    """
    ok_runs = {r["domain"] for r in generation.get("runs", [])
               if r.get("status") == "ok"}
    backbones, incomplete = [], []
    for row in holdout["selected"]:
        domain = row["domain"]
        found = [{"backbone_key": f"{domain}|target|target", "target_id": domain,
                  "backbone_source": "target", "pdb_path": row["pdb"]}]
        if domain in ok_runs:
            run_dir = output_root / f"holdout_{domain}_rfd3"
            for index, pdb in enumerate(sorted(run_dir.rglob("*.pdb"))):
                if "rfd3" not in str(pdb).lower():
                    continue
                found.append({"backbone_key": f"{domain}|rfd3|{index}",
                              "target_id": domain, "backbone_source": "rfd3",
                              "pdb_path": str(pdb)})
        expected = 1 + int(holdout["backbone_plan"]["composition"]["rfd3"])
        if len(found) != expected:
            incomplete.append({"domain": domain, "found": len(found),
                               "expected": expected})
        backbones.extend(found)
    return backbones, incomplete


def generate_sequences(backbones: list[dict], *, n: int, mpnn_url: str,
                       soluprot_url: str, mpnn_timeout: float) -> list[dict]:
    mpnn = ProteinMPNNClient(runpod=None, endpoint_id=None, gpu_url=mpnn_url,
                             gpu_timeout_s=mpnn_timeout)
    soluprot = SoluProtClient(url=soluprot_url)
    rows: list[dict] = []
    for index, bb in enumerate(backbones, start=1):
        pdb_text = Path(bb["pdb_path"]).read_text(encoding="utf-8", errors="replace")
        try:
            _native, samples, _meta = mpnn.design(
                pdb_text=pdb_text,
                pdb_name=bb["backbone_key"].replace("|", "_"),
                use_soluble_model=bool(GATE0_MPNN_SETTINGS["use_soluble_model"]),
                model_name=str(GATE0_MPNN_SETTINGS["model_name"]),
                num_seq_per_target=n,
                batch_size=int(GATE0_MPNN_SETTINGS["batch_size"]),
                sampling_temp=GRID_TEMPERATURE,
                seed=int(GATE0_MPNN_SETTINGS["seed"]),
            )
        except Exception as exc:
            print(f"  [mpnn 실패] {bb['backbone_key']}: {type(exc).__name__}: {exc}"[:180],
                  flush=True)
            continue
        sequences = [s.sequence for s in samples if s.sequence]
        records = [SequenceRecord(id=f"{bb['backbone_key']}|g{i}", sequence=s)
                   for i, s in enumerate(sequences)]
        try:
            scores = soluprot.score(records)
        except Exception as exc:
            print(f"  [soluprot 실패] {type(exc).__name__}: {exc}"[:150], flush=True)
            scores = {}
        for rec in records:
            rows.append({
                "sequence_id": rec.id, "sequence": rec.sequence,
                "backbone_key": bb["backbone_key"], "target_id": bb["target_id"],
                "backbone_source": bb["backbone_source"],
                "temperature": GRID_TEMPERATURE,
                "soluprot": scores.get(rec.id),
            })
        print(f"  [{index}/{len(backbones)}] {bb['backbone_key']}: "
              f"서열 {len(records)}", flush=True)
    return rows


def fold_grid(rows: list[dict], backbones: list[dict], *, client, workers: int,
              out_csv: Path, model_dir: Path) -> dict:
    refold = _refold_module()
    pdb_by_key = {bb["backbone_key"]: bb["pdb_path"] for bb in backbones}
    refs = {}
    for key in {r["backbone_key"] for r in rows}:
        text = Path(pdb_by_key[key]).read_text(encoding="utf-8", errors="replace")
        refs[key] = (text, dssp_non_loop_positions_by_chain(text), sha256_text(text))

    done = {}
    if out_csv.exists():
        done = {r["sequence_id"]: r for r in csv.DictReader(out_csv.open(encoding="utf-8"))}
    pending = [r for r in rows if r["sequence_id"] not in done]
    print(f"[격자] 전체 {len(rows)} · 완료 {len(done)} · 남은 {len(pending)}", flush=True)

    model_dir.mkdir(parents=True, exist_ok=True)
    results = list(done.values())
    lock = threading.Lock()
    started = time.monotonic()
    completed = 0

    def flush():
        with out_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=refold.FIELDS,
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

    def work(row):
        nonlocal completed
        entry = refold.fold_one(client, row, refs, model_dir)
        with lock:
            results.append(entry)
            completed += 1
            if completed % 20 == 0 or completed == len(pending):
                rate = (time.monotonic() - started) / completed
                left = (len(pending) - completed) * rate / 60
                print(f"  [격자] {completed}/{len(pending)} (~{left:.0f}분 남음)",
                      flush=True)
                flush()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, pending))
    flush()
    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"[격자] 완료 · ok {ok}/{len(results)} · {out_csv}", flush=True)
    return {"n": len(results), "ok": ok, "csv": str(out_csv.relative_to(PROJECT_ROOT))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", default=str(BASE / "holdout_targets.json"))
    parser.add_argument("--generation", default=str(BASE / "holdout_generation.json"))
    parser.add_argument("--spec", default=str(BASE / "holdout_experiment_spec.json"))
    parser.add_argument("--output-root", default="/opt/protein_pipeline/outputs")
    parser.add_argument("--colabfold-url", default="http://211.188.35.221:18160")
    parser.add_argument("--mpnn-url", default="http://211.188.35.221:18101")
    parser.add_argument("--soluprot-url", default="http://127.0.0.1:18081/score")
    parser.add_argument("--mpnn-timeout", type=float, default=1800.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--skip-generation", action="store_true",
                        help="sequences.csv 가 이미 있으면 서열 생성을 건너뛴다")
    args = parser.parse_args(argv)

    holdout = json.loads(Path(args.holdout).read_text(encoding="utf-8"))
    generation = json.loads(Path(args.generation).read_text(encoding="utf-8"))
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    depth = int(spec["design"]["grid_depth"])

    GRID.mkdir(parents=True, exist_ok=True)
    backbones, incomplete = collect_backbones(holdout, generation,
                                              Path(args.output_root))
    print(f"백본 {len(backbones)} · 격자 깊이 {depth}")
    if incomplete:
        print("구성이 안 맞는 타겟 (조용히 줄이지 않는다):")
        for row in incomplete:
            print(f"  {row['domain']}: {row['found']}/{row['expected']}")

    seq_csv = GRID / "sequences.csv"
    if args.skip_generation and seq_csv.exists():
        rows = list(csv.DictReader(seq_csv.open(encoding="utf-8")))
        print(f"서열 재사용: {len(rows)}")
    else:
        print(f"\n서열 생성 (백본당 {depth}, T={GRID_TEMPERATURE})")
        rows = generate_sequences(backbones, n=depth, mpnn_url=args.mpnn_url,
                                  soluprot_url=args.soluprot_url,
                                  mpnn_timeout=args.mpnn_timeout)
        with seq_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {seq_csv} ({len(rows)} 행)")

    client = LocalHTTPAlphaFold2Client(args.colabfold_url, None, 7200.0)
    result = fold_grid(rows, backbones, client=client, workers=args.workers,
                       out_csv=GRID / "af2_order_metric.csv",
                       model_dir=GRID / "models")

    manifest = {
        "phase": "2_grid_fold",
        "grid_depth": depth,
        "condition": {"temperature": GRID_TEMPERATURE,
                      "mpnn": dict(GATE0_MPNN_SETTINGS)},
        "n_backbones": len(backbones),
        "incomplete_targets": incomplete,
        "protocol_fingerprint": protocol_fingerprint(),
        "metric": "rmsd_nonloop_order (22_refold_with_artifacts.fold_one 재사용)",
        "reference": "각 백본 자신의 PDB (게이트 0 규약)",
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "result": result,
    }
    (GRID / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {GRID / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
