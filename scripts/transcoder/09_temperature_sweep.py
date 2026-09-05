#!/usr/bin/env python3
"""ProteinMPNN sampling temperature sweep (guided generation 1단계).

**AF2 를 쓰지 않는다.** 진행 중인 백본 증량 캠페인의 ColabFold 자원을 건드리지
않기 위해, 여기서는 MPNN 생성과 값싼 평가(SoluProt, 다양성, 조성)까지만 한다.
AF2 는 증량이 끝난 뒤 온도별로 균형 잡힌 subset 에만 돌린다.

paired 설계: **같은 백본 PDB** 에 온도만 바꿔 생성한다. 파이프라인을 통하면
백본이 매번 새로 생성되어 pairing 이 깨진다.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.clients.proteinmpnn import ProteinMPNNClient  # noqa: E402
from pipeline_mcp.clients.soluprot import SoluProtClient  # noqa: E402
from pipeline_mcp.models import SequenceRecord  # noqa: E402

from rapid_sr.protocol import (  # noqa: E402
    GATE0_MPNN_SETTINGS,
    GATE0_SEQUENCES_PER_BACKBONE,
    GATE0_THRESHOLDS,
)
from rapid_sr.seqstats import (  # noqa: E402
    composition, mean_pairwise_distance, n_unique, positional_entropy,
)

TEMPERATURES = (0.05, 0.1, 0.2, 0.3)


def parse_header_metrics(record: SequenceRecord) -> dict[str, float]:
    import re
    out: dict[str, float] = {}
    meta = getattr(record, "meta", None) or {}
    for key in ("score", "global_score", "seq_recovery", "T"):
        value = meta.get(key)
        if isinstance(value, (int, float)):
            out[key] = float(value)
    header = str(getattr(record, "header", "") or "")
    for key, value in re.findall(r"(\w+)=([-\d.]+)", header):
        if key in ("score", "global_score", "seq_recovery", "T") and key not in out:
            try:
                out[key] = float(value)
            except ValueError:
                pass
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
    parser.add_argument("--labels", default=str(base / "backbones" / "backbone_labels.csv"))
    parser.add_argument("--pdb-dir", default=str(base / "backbones" / "pdb"))
    parser.add_argument("--targets-file", default="", help="이 타겟만 사용")
    parser.add_argument("--source", default="target", help="사용할 backbone_source")
    parser.add_argument("--panel-manifest", default="",
                        help="동결된 panel manifest 의 backbone_key 목록만 사용한다. "
                             "주면 --targets-file/--source 보다 우선한다.")
    parser.add_argument("--mpnn-url", default="http://211.188.35.221:18101")
    parser.add_argument("--mpnn-timeout", type=float, default=900.0,
                        help="클라이언트 기본값 60 초는 긴 백본에서 터진다. "
                             "폴링 간격은 timeout/200 이므로 900 이면 4.5 초다.")
    parser.add_argument("--soluprot-url", default="http://127.0.0.1:18081/score")
    parser.add_argument("--n-sequences", type=int, default=GATE0_SEQUENCES_PER_BACKBONE)
    parser.add_argument("--temperatures", default=",".join(str(t) for t in TEMPERATURES))
    parser.add_argument("--out-dir", default=str(base / "temperature_sweep"))
    args = parser.parse_args(argv)

    wanted = None
    if args.targets_file:
        wanted = {
            line.strip()
            for line in Path(args.targets_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    with open(args.labels, newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))

    if args.panel_manifest:
        # 동결된 목록을 그대로 따른다. 여기서 다시 거르면 동결의 의미가 없다.
        manifest = json.loads(Path(args.panel_manifest).read_text(encoding="utf-8"))
        keys = [entry["backbone_key"] for entry in manifest["backbones"]]
        by_key = {r["backbone_key"]: r for r in all_rows}
        missing = [k for k in keys if k not in by_key]
        if missing:
            raise SystemExit(f"manifest 의 백본이 labels 에 없다: {missing}")
        rows = [by_key[k] for k in keys]
        print(f"panel manifest: {args.panel_manifest} "
              f"({manifest.get('n_selected')} 개, seed={manifest.get('seed')})", flush=True)
    else:
        rows = [
            r for r in all_rows
            if r["backbone_source"] == args.source
            and (wanted is None or r["target_id"] in wanted)
        ]
    temps = [float(t) for t in args.temperatures.split(",") if t.strip()]
    print(f"backbones={len(rows)} temperatures={temps} n_seq={args.n_sequences}", flush=True)

    mpnn = ProteinMPNNClient(runpod=None, endpoint_id=None, gpu_url=args.mpnn_url,
                             gpu_timeout_s=float(args.mpnn_timeout))
    soluprot = SoluProtClient(url=args.soluprot_url)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seq_rows: list[dict] = []
    cond_rows: list[dict] = []

    started = time.monotonic()
    for index, row in enumerate(rows, start=1):
        pdb_text = (Path(args.pdb_dir) / row["pdb_file"]).read_text(encoding="utf-8", errors="replace")
        for temp in temps:
            try:
                _native, samples, _meta = mpnn.design(
                    pdb_text=pdb_text,
                    pdb_name=row["backbone_key"].replace("|", "_"),
                    use_soluble_model=bool(GATE0_MPNN_SETTINGS["use_soluble_model"]),
                    model_name=str(GATE0_MPNN_SETTINGS["model_name"]),
                    num_seq_per_target=int(args.n_sequences),
                    batch_size=int(GATE0_MPNN_SETTINGS["batch_size"]),
                    sampling_temp=float(temp),
                    seed=int(GATE0_MPNN_SETTINGS["seed"]),
                )
            except Exception as exc:
                print(f"  [fail] {row['backbone_key']} T={temp}: {type(exc).__name__}: {exc}"[:200], flush=True)
                continue

            sequences = [s.sequence for s in samples if s.sequence]
            if not sequences:
                continue
            records = [
                SequenceRecord(id=f"{row['backbone_key']}|T{temp}|{i}", sequence=s)
                for i, s in enumerate(sequences)
            ]
            try:
                scores = soluprot.score(records)
            except Exception as exc:
                print(f"  [soluprot fail] {type(exc).__name__}: {exc}"[:150], flush=True)
                scores = {}

            per_seq_metrics = [parse_header_metrics(s) for s in samples if s.sequence]
            for rec, sample_metrics in zip(records, per_seq_metrics):
                seq_rows.append({
                    "backbone_key": row["backbone_key"], "target_id": row["target_id"],
                    "backbone_source": row["backbone_source"], "temperature": temp,
                    "sequence_id": rec.id, "sequence": rec.sequence,
                    "score": sample_metrics.get("score"),
                    "global_score": sample_metrics.get("global_score"),
                    "seq_recovery": sample_metrics.get("seq_recovery"),
                    "soluprot": scores.get(rec.id),
                })

            solu_values = [v for v in (scores.get(r.id) for r in records) if v is not None]
            comp = composition(sequences)
            cond_rows.append({
                "backbone_key": row["backbone_key"], "target_id": row["target_id"],
                "backbone_source": row["backbone_source"], "temperature": temp,
                "n_sequences": len(sequences), "n_unique": n_unique(sequences),
                "positional_entropy": round(positional_entropy(sequences), 4),
                "mean_pairwise_distance": round(mean_pairwise_distance(sequences), 4),
                "mean_score": _mean(m.get("score") for m in per_seq_metrics),
                "mean_global_score": _mean(m.get("global_score") for m in per_seq_metrics),
                "mean_seq_recovery": _mean(m.get("seq_recovery") for m in per_seq_metrics),
                "mean_soluprot": _mean(solu_values),
                "soluprot_pass_yield": (
                    round(sum(1 for v in solu_values if v >= GATE0_THRESHOLDS["soluprot_min"])
                          / len(solu_values), 4) if solu_values else None
                ),
                **{k: round(v, 5) for k, v in comp.items()},
            })
        print(f"  [{index}/{len(rows)}] {row['target_id']} ({time.monotonic()-started:.0f}s)", flush=True)
        _write(out_dir, seq_rows, cond_rows)

    _write(out_dir, seq_rows, cond_rows)
    print(f"\nsequences={len(seq_rows)} conditions={len(cond_rows)} -> {out_dir}")
    return 0


def _mean(values):
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 4) if vals else None


def _write(out_dir: Path, seq_rows: list[dict], cond_rows: list[dict]) -> None:
    for name, rows in (("sequences.csv", seq_rows), ("conditions.csv", cond_rows)):
        if not rows:
            continue
        with open(out_dir / name, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
