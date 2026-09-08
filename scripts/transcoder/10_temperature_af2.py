#!/usr/bin/env python3
"""Temperature sweep 2단계: paired AF2 subset.

선정 규칙(중요): 백본마다 **동일한 index 8개**를 골라 네 온도 모두에 넣는다.
15 backbone x 8 index x 4 T = 480. global_score 로 고르면 온도 효과와 선택
효과가 교란되므로 점수 기반 선택을 하지 않는다.

1단계 480 을 먼저 돌리고, 구간이 넓을 때만 나머지 index 8개를 추가한다.
"""

from __future__ import annotations

import argparse
import os
import csv
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
import threading
import time

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _worker_url(port: int) -> str:
    """RAPID_GPU_HOST 가 없으면 빈 문자열. 호출자가 --url 로 주어야 한다.

    내부 호스트를 기본값으로 박아두면 공개 저장소에 나간다.
    """
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    return f"http://{host}:{port}" if host else ""
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client  # noqa: E402
from pipeline_mcp.models import SequenceRecord  # noqa: E402

from pipeline_mcp.bio.pdb import ca_rmsd, dssp_non_loop_positions_by_chain  # noqa: E402
from rapid_sr.clustered import kabsch_rmsd  # noqa: E402
from rapid_sr.protocol import AF2_SETTINGS_V1, STRUCTURAL_METRIC_V1  # noqa: E402
from rapid_sr.descriptors import ca_coords  # noqa: E402

#: 게이트 0 캠페인이 쓰는 RMSD 정의. pipeline.py 는 부모 백본을 기준으로
#: DSSP non-loop 위치에서만 CA RMSD 를 잰다. GATE0_THRESHOLDS['rmsd_max'] = 2.0
#: 은 그 정의 위에서 정해진 값이다.
#:
#: 같은 AF2 모델(1bg5A03, 254 잔기, non-loop 85 개)에서 측정한 차이:
#:     kabsch, 파일 순서, 전체 CA    22.6 A
#:     ca_rmsd, resnum, 전체 위치    37.7 A
#:     ca_rmsd, resnum, non-loop      1.32 A
#: 이것은 정렬 오류가 아니다 - 정렬 오류였다면 resnum 매칭이 값을 줄였어야 하는데
#: 오히려 늘었다. 두 지표가 서로 다른 구조 영역을 재는 것이고, 그 차이는 loop 와
#: 말단의 편차가 지배한다. 1 차 온도 패널은 첫 번째 정의에 2.0 A 임계값을
#: 적용했고, 그래서 loop 가 많은 백본은 어떤 설계도 통과하지 못했다.
RMSD_METHOD = STRUCTURAL_METRIC_V1["rmsd"]["method"]

OUTPUT_FIELDS = [
    "sequence_id", "backbone_key", "target_id", "temperature",
    "backbone_source", "soluprot", "global_score",
    "plddt", "rmsd", "rmsd_all_ca", "rmsd_all_positions",
    "rmsd_method", "rmsd_n_positions",
    # 어떤 예측 설정으로 얻은 값인지 행마다 남긴다. 두 실행을 비교할 때
    # "정의를 바꿨다" 와 "예측 조건이 달랐다" 를 구별해야 하기 때문이다.
    "af2_model_preset", "af2_db_preset", "af2_max_template_date",
    "status", "error",
]


def rmsd_against_reference(model_pdb_text, non_loop_positions, *, reference_text,
                           reference_ca=None) -> dict:
    """세 가지 RMSD 를 전부 기록한다.

    `rmsd` 만 임계값 판정에 쓰고 나머지는 출처 기록이다. 정의가 바뀌면 다시
    폴딩해야 하는 상황을 만들지 않기 위해서다 - 1 차 패널은 PDB 를 저장하지
    않아서 정의를 고치는 데 480 폴드를 다시 돌려야 했다.

    non-loop 위치가 하나도 없으면 캠페인과 같은 값을 낼 수 없으므로 `rmsd` 를
    비워 둔다. 다른 정의로 대신 채우면 임계값이 조용히 다른 것을 뜻하게 된다.
    """
    out = {
        "rmsd": None, "rmsd_all_ca": None, "rmsd_all_positions": None,
        "rmsd_method": RMSD_METHOD,
        "rmsd_n_positions": sum(len(v) for v in (non_loop_positions or {}).values()),
    }
    if not model_pdb_text or not reference_text:
        return out
    if non_loop_positions:
        value = ca_rmsd(reference_text, model_pdb_text, include_positions=non_loop_positions)
        if isinstance(value, (int, float)):
            out["rmsd"] = round(float(value), 4)
    value = ca_rmsd(reference_text, model_pdb_text)
    if isinstance(value, (int, float)):
        out["rmsd_all_positions"] = round(float(value), 4)
    if reference_ca is not None and getattr(reference_ca, "size", 0):
        out["rmsd_all_ca"] = round(kabsch_rmsd(ca_coords(model_pdb_text), reference_ca), 4)
    return out


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
    parser.add_argument("--colabfold-url", default=_worker_url(18160))
    parser.add_argument("--n-per-condition", type=int, default=8)
    parser.add_argument("--offset", type=int, default=0, help="2단계에서는 8 로 준다")
    parser.add_argument("--out", default=str(base / "temperature_sweep" / "af2_stage1.csv"))
    parser.add_argument("--workers", type=int, default=4,
                        help="ColabFold 워커 수에 맞춘다. 직렬이면 워커 하나만 쓴다.")
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
    backbone_text = {
        key: (Path(args.pdb_dir) / name).read_text(encoding="utf-8", errors="replace")
        for key, name in pdb_of.items()
    }
    backbone_ca = {key: ca_coords(text) for key, text in backbone_text.items()}
    # DSSP 는 백본마다 한 번만 돈다. 폴드마다 다시 돌리면 896 번 헛돈다.
    backbone_non_loop = {
        key: dssp_non_loop_positions_by_chain(text) for key, text in backbone_text.items()
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

    pending = [r for r in picked if r["sequence_id"] not in done]
    print(f"pending={len(pending)} workers={args.workers}", flush=True)

    def fold(row: dict) -> dict:
        safe = row["sequence_id"].replace("|", "_")
        entry = {
            "sequence_id": row["sequence_id"], "backbone_key": row["backbone_key"],
            "target_id": row["target_id"], "temperature": row["temperature"],
            "backbone_source": row.get("backbone_source", "target"),
            "soluprot": row.get("soluprot"), "global_score": row.get("global_score"),
            "af2_model_preset": AF2_SETTINGS_V1["model_preset"],
            "af2_db_preset": AF2_SETTINGS_V1["db_preset"],
            "af2_max_template_date": AF2_SETTINGS_V1["max_template_date"],
        }
        try:
            # 클라이언트 기본값에 기대지 않고 명시적으로 넘긴다. 기본값이 바뀌면
            # 두 실행이 조용히 갈리고, RMSD 정의 수정과 run-to-run 차이가 섞인다.
            result = client.predict(
                [SequenceRecord(id=safe, sequence=row["sequence"])],
                model_preset=str(AF2_SETTINGS_V1["model_preset"]),
                db_preset=str(AF2_SETTINGS_V1["db_preset"]),
                max_template_date=str(AF2_SETTINGS_V1["max_template_date"]),
                extra_flags=AF2_SETTINGS_V1["extra_flags"],
            )
            payload = result.get(safe) if isinstance(result, dict) else None
            payload = payload if isinstance(payload, dict) else {}
            entry["plddt"] = payload.get("best_plddt")
            pdb_text = payload.get("ranked_0_pdb") or payload.get("pdb") or ""
            key = row["backbone_key"]
            entry.update(rmsd_against_reference(
                pdb_text, backbone_non_loop.get(key),
                reference_text=backbone_text.get(key, ""),
                reference_ca=backbone_ca.get(key),
            ))
            entry["status"] = "ok"
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return entry

    fields = OUTPUT_FIELDS

    def flush() -> None:
        with open(out_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(existing)

    # ColabFold 워커가 4개이므로 직렬로 돌리면 하나만 쓴다. 클라이언트 안에
    # 동시성 게이트가 있어 워커 수를 넘겨도 큐에서 조절된다.
    started = time.monotonic()
    lock = threading.Lock()
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fold, row): row for row in pending}
        for future in as_completed(futures):
            entry = future.result()
            with lock:
                existing.append(entry)
                completed += 1
                flush()
                if completed % 20 == 0 or completed == len(pending):
                    rate = (time.monotonic() - started) / completed
                    left = (len(pending) - completed) * rate / 60
                    print(f"  {completed}/{len(pending)} "
                          f"({time.monotonic()-started:.0f}s, ~{left:.0f}min left)", flush=True)

    print(f"\nwrote {out_path} rows={len(existing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
