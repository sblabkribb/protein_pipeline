#!/usr/bin/env python3
"""게이트 0 사다리용 백본 PDB 와 yield 라벨을 한곳에 모은다.

CATH run 은 backbone PDB 가 `request.json` 의 `target_pdb` 에 인라인으로 들어 있고,
캠페인 run 은 `backbones/<id>/` 아래 파일로 있다. 두 경로를 모두 처리한다.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.cath_source import load_cath_run  # noqa: E402
from rapid_sr.outputs_source import load_output_run  # noqa: E402
from rapid_sr.yields import backbone_yields  # noqa: E402


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def backbone_pdb_text(run_dir: Path, backbone_id: str) -> str | None:
    """백본 하나의 PDB 텍스트. 없으면 None."""
    if backbone_id == "target":
        # CATH run: request.json 에 인라인으로 들어 있다.
        text = str(_load_json(run_dir / "request.json").get("target_pdb") or "")
        if text.startswith("ATOM") or "\nATOM" in text:
            return text
        for name in ("target.pdb", "target.original.pdb"):
            path = run_dir / name
            if path.exists():
                return path.read_text(encoding="utf-8", errors="replace")
        return None

    for candidate in (
        run_dir / "backbones" / backbone_id / f"{backbone_id}.pdb",
        run_dir / "rfd3" / "designs" / f"{backbone_id}.pdb",
        run_dir / "backbones" / backbone_id / "backbone.pdb",
    ):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace")

    entries = _load_json(run_dir / "backbones.json").get("backbones") or []
    for entry in entries:
        if str(entry.get("id")) != backbone_id:
            continue
        raw = entry.get("pdb_path")
        if raw and Path(raw).exists():
            return Path(raw).read_text(encoding="utf-8", errors="replace")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cath-dir", default=str(PROJECT_ROOT / "cath_outputs_s3"))
    parser.add_argument("--outputs-dir", default="/opt/protein_pipeline/outputs")
    parser.add_argument("--outputs-glob", default="gate0_*")
    parser.add_argument(
        "--tier", default="50",
        help="이 tier 만 사용한다. CATH 는 3 tier, 캠페인은 1 tier 라 "
             "합산하면 yield 가 같은 척도가 아니다. 빈 값이면 전체 tier 합산.",
    )
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "backbones"))
    args = parser.parse_args(argv)

    per_run: dict[str, list] = {}
    for run in sorted(p for p in Path(args.cath_dir).iterdir() if p.is_dir()):
        per_run[str(run)] = load_cath_run(run)
    outputs = Path(args.outputs_dir)
    if outputs.exists():
        for run in sorted(outputs.glob(args.outputs_glob)):
            if run.is_dir():
                per_run[str(run)] = load_output_run(run)

    if args.tier:
        per_run = {
            k: [r for r in recs if r.tier == args.tier] for k, recs in per_run.items()
        }
    all_records = [rec for recs in per_run.values() for rec in recs]
    yields = backbone_yields(all_records)

    # backbone_key -> run_dir 매핑
    run_of: dict[str, str] = {}
    for run_path, recs in per_run.items():
        for rec in recs:
            run_of.setdefault(f"{rec.target_id}|{rec.backbone_source}|{rec.backbone_id}", run_path)

    out_dir = Path(args.out_dir)
    (out_dir / "pdb").mkdir(parents=True, exist_ok=True)
    rows, missing = [], []
    for key, info in sorted(yields.items()):
        if info["af2_structural_pass_yield"] is None:
            continue
        run_dir = Path(run_of[key])
        text = backbone_pdb_text(run_dir, str(info["backbone_id"]))
        if not text:
            missing.append(key)
            continue
        safe = key.replace("|", "__").replace("/", "_")
        (out_dir / "pdb" / f"{safe}.pdb").write_text(text, encoding="utf-8")
        rows.append({
            "backbone_key": key, "pdb_file": f"{safe}.pdb",
            "target_id": info["target_id"], "backbone_source": info["backbone_source"],
            "backbone_id": info["backbone_id"],
            "n_sequences": info["n_sequences"],
            "n_sequences_with_af2": info["n_sequences_with_af2"],
            "soluprot_pass_yield": info["soluprot_pass_yield"],
            "af2_structural_pass_yield": info["af2_structural_pass_yield"],
            "joint_pass_yield": info["joint_pass_yield"],
            "label_regime": info["label_regime"],
            "needs_topup": info["needs_topup"],
            "run_dir": str(run_dir),
            "tier": args.tier or "all",
        })

    labels = out_dir / "backbone_labels.csv"
    with open(labels, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"backbones exported: {len(rows)} | pdb missing: {len(missing)}")
    if missing:
        print("  missing sample:", missing[:5])
    import collections
    print("  by source:", dict(collections.Counter(r["backbone_source"] for r in rows)))
    print(f"  labels -> {labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
