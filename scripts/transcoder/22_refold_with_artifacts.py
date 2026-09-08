#!/usr/bin/env python3
"""동결된 지표로 온도 패널을 다시 접고, 이번엔 전부 저장한다.

왜 다시 접는가
--------------
구조 지표의 대응 방식이 틀려서 오프셋 백본의 RMSD 가 프레임 시프트된 값이었다
(1af7A01: 29.01 A -> 1.57 A). 고친 지표로 다시 계산하려면 모델 좌표가 있어야
하는데, 앞선 실행들이 PDB 를 저장하지 않았다.

왜 이번이 마지막이어야 하는가
-----------------------------
지표 정의 문제로 재폴딩한 것이 이번이 세 번째다. 그 고리를 끊으려면 모델
좌표를 남겨야 한다. 그래서 폴드마다 다음을 전부 기록한다.

    AF2 모델 PDB (gzip)          정의가 또 바뀌어도 다시 접지 않는다
    설계 서열                     대응을 서열에서 정하므로 필수다
    기준 구조 경로와 sha256       어떤 백본에 맞춰 쟀는지
    DSSP 마스크와 인덱스 매핑     마스크가 어느 자리였는지
    pLDDT, 모든 RMSD 변형         지표 하나가 아니라 전부
    AF2 설정, 워커가 보고한 버전   예측 조건
    code SHA                     계산한 코드
"""

from __future__ import annotations

import argparse
import os
import csv
import gzip
import hashlib
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _worker_url(port: int) -> str:
    """RAPID_GPU_HOST 가 없으면 빈 문자열. 호출자가 --url 로 주어야 한다.

    내부 호스트를 기본값으로 박아두면 공개 저장소에 나간다.
    """
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    return f"http://{host}:{port}" if host else ""
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.bio.pdb import dssp_non_loop_positions_by_chain  # noqa: E402
from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client  # noqa: E402
from pipeline_mcp.models import SequenceRecord  # noqa: E402
from rapid_sr.clustered import kabsch_rmsd  # noqa: E402
from rapid_sr.descriptors import ca_coords  # noqa: E402
from rapid_sr.protocol import AF2_SETTINGS_V1, GATE0_THRESHOLDS  # noqa: E402
from rapid_sr.structural import (  # noqa: E402
    ca_records, designed_length, model_positions, non_loop_indices,
    positional_non_loop_rmsd, sequence_indices,
)

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"

FIELDS = [
    "sequence_id", "backbone_key", "target_id", "temperature", "backbone_source",
    "soluprot", "plddt",
    # 동결된 primary 지표와 그 옆에 두는 변형들.
    "rmsd_nonloop_order", "rmsd_all_ca_order",
    "correspondence", "n_non_loop", "designed_length", "x_placeholders",
    "reference_sha256", "model_path",
    "af2_model_preset", "af2_db_preset", "af2_max_template_date",
    "status", "error",
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fold_one(client, row, refs, model_dir) -> dict:
    key = row["backbone_key"]
    reference, mask, ref_sha = refs[key]
    entry = {
        "sequence_id": row["sequence_id"], "backbone_key": key,
        "target_id": row["target_id"], "temperature": row["temperature"],
        "backbone_source": row.get("backbone_source", "target"),
        "soluprot": row.get("soluprot"),
        "reference_sha256": ref_sha,
        "designed_length": len(row["sequence"]),
        "x_placeholders": row["sequence"].count("X"),
        "af2_model_preset": AF2_SETTINGS_V1["model_preset"],
        "af2_db_preset": AF2_SETTINGS_V1["db_preset"],
        "af2_max_template_date": AF2_SETTINGS_V1["max_template_date"],
    }
    safe = row["sequence_id"].replace("|", "_").replace("/", "_")
    try:
        result = client.predict(
            [SequenceRecord(id=safe, sequence=row["sequence"])],
            model_preset=str(AF2_SETTINGS_V1["model_preset"]),
            db_preset=str(AF2_SETTINGS_V1["db_preset"]),
            max_template_date=str(AF2_SETTINGS_V1["max_template_date"]),
        )
        payload = (result or {}).get(safe) if isinstance(result, dict) else None
        payload = payload if isinstance(payload, dict) else {}
        entry["plddt"] = payload.get("best_plddt")
        model = payload.get("ranked_0_pdb") or payload.get("pdb") or ""
        if not model:
            entry["status"] = "failed"
            entry["error"] = "AF2 가 모델을 돌려주지 않았다"
            return entry

        # 좌표를 먼저 저장한다. 지표 계산이 실패해도 다시 접을 필요는 없어야 한다.
        path = model_dir / f"{safe}.pdb.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(model)
        entry["model_path"] = str(path.relative_to(PROJECT_ROOT))

        keep = non_loop_indices(reference, mask)
        entry["n_non_loop"] = len(keep)
        try:
            positions = model_positions(reference, model, sequence=row["sequence"])
            entry["correspondence"] = (
                "file_order" if positions == list(range(len(positions))) else "numbering_span")
            entry["rmsd_nonloop_order"] = positional_non_loop_rmsd(
                reference, model, mask, sequence=row["sequence"])
            entry["rmsd_all_ca_order"] = round(
                float(kabsch_rmsd(ca_coords(model)[positions], ca_coords(reference))), 4)
        except ValueError as exc:
            # 대응을 세울 수 없으면 값을 비워 둔다. 좌표는 이미 저장했으므로
            # 나중에 다시 접지 않고도 조사할 수 있다.
            entry["correspondence"] = f"refused: {exc}"
        entry["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        entry["status"] = "failed"
        entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return entry


def run_panel(name, sequences_csv, out_csv, model_dir, *, n_per_condition, offset,
              client, labels, pdb_dir, workers) -> dict:
    rows = list(csv.DictReader(sequences_csv.open(encoding="utf-8")))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "temp_af2", PROJECT_ROOT / "scripts" / "transcoder" / "10_temperature_af2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    picked = module.select_paired(rows, n_per_condition=n_per_condition, offset=offset)

    # ok 만 완료로 친다. status 를 무시하면 실패 행이 "완료" 로 남아 재시도되지
    # 않고, 그 폴드는 영영 비어 있게 된다.
    done, retrying = {}, 0
    if out_csv.exists():
        for r in csv.DictReader(out_csv.open(encoding="utf-8")):
            if r.get("status") == "ok":
                done[r["sequence_id"]] = r
            else:
                retrying += 1
    pending = [r for r in picked if r["sequence_id"] not in done]
    print(f"[{name}] 전체 {len(picked)} · 완료 {len(done)} · 남은 {len(pending)}"
          + (f" (이전 실패 {retrying} 건 재시도 포함)" if retrying else ""), flush=True)

    refs = {}
    for key in {r["backbone_key"] for r in picked}:
        text = (pdb_dir / labels[key]["pdb_file"]).read_text(encoding="utf-8", errors="replace")
        refs[key] = (text, dssp_non_loop_positions_by_chain(text), sha256_text(text))

    model_dir.mkdir(parents=True, exist_ok=True)
    results = list(done.values())
    lock = threading.Lock()
    started = time.monotonic()
    completed = 0

    def flush():
        with out_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

    def work(row):
        nonlocal completed
        entry = fold_one(client, row, refs, model_dir)
        with lock:
            results.append(entry)
            completed += 1
            if completed % 20 == 0 or completed == len(pending):
                rate = (time.monotonic() - started) / completed
                left = (len(pending) - completed) * rate / 60
                print(f"  [{name}] {completed}/{len(pending)} (~{left:.0f}분 남음)", flush=True)
                flush()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, pending))
    flush()
    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"[{name}] 완료 · ok {ok}/{len(results)} · {out_csv}", flush=True)
    return {"panel": name, "n": len(results), "ok": ok, "csv": str(out_csv.relative_to(PROJECT_ROOT))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--colabfold-url", default=_worker_url(18160))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", default="", help="panel1 또는 panel2 만 돌린다")
    args = parser.parse_args(argv)

    labels = {r["backbone_key"]: r for r in
              csv.DictReader((BASE / "backbones" / "backbone_labels.csv").open(encoding="utf-8"))}
    pdb_dir = BASE / "backbones" / "pdb"
    client = LocalHTTPAlphaFold2Client(args.colabfold_url, None, 7200.0)

    manifest = {
        "purpose": "동결된 sequence-order 지표로 온도 패널 재계산",
        "metric": {
            "primary": "rmsd_nonloop_order",
            "correspondence": "folded-sequence order (X placeholders resolved per fold)",
            "mask": "reference DSSP non-loop, applied by sequence index",
            "superposition": "kabsch_ca",
            "cutoff_angstrom": GATE0_THRESHOLDS["rmsd_max"],
            "cutoff_provenance": (
                "pipeline 기본값 af2_rmsd_cutoff=2.0 (2026-01-28), 게이트 0 와 온도 패널보다 "
                "앞선다. 잘못된 resnum 매칭 결과에서 정한 값이 아니다. 다만 내부 보정 근거가 "
                "있는 값도 아닌 관례값이며, 이 패널에서 새로 최적화하지 않는다."
            ),
        },
        "af2_settings": {k: v for k, v in AF2_SETTINGS_V1.items() if k != "not_controlled_here"},
        "af2_not_controlled": AF2_SETTINGS_V1["not_controlled_here"],
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "panels": [],
    }

    panels = [
        ("panel1", BASE / "temperature_sweep" / "sequences.csv",
         BASE / "temperature_sweep" / "af2_order_metric.csv",
         BASE / "temperature_sweep" / "models", 8, 0),
        ("panel2", BASE / "temperature_panel2" / "sequences.csv",
         BASE / "temperature_panel2" / "af2_order_metric.csv",
         BASE / "temperature_panel2" / "models", 8, 0),
    ]
    for name, seqs, out_csv, model_dir, n, offset in panels:
        if args.only and args.only != name:
            continue
        manifest["panels"].append(run_panel(
            name, seqs, out_csv, model_dir, n_per_condition=n, offset=offset,
            client=client, labels=labels, pdb_dir=pdb_dir, workers=args.workers))

    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (BASE / "refold_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {BASE / 'refold_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
