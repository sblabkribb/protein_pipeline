#!/usr/bin/env python3
"""P1. 홀드아웃 백본의 ProteinMPNN encoder feature 를 뽑는다.

dev 코호트의 mpnn_encoder.npy (157, 384) 와 **같은 ckpt·같은 차원**이어야 한다.
그렇지 않으면 Gate 1 의 train/test 가 다른 공간에 있게 된다.

백본 PDB 는 이 작업 트리에 없다. rfd3 백본은 deploy 체크아웃에 있고 native 백본은
public_data 에 있다. **deploy 경로는 읽기만 한다** (AGENTS.md).

dev 추출기는 커밋된 적이 없다 (`1c2eeb4` 는 산출물만 담고 있다). 그래서 추출은
`_mpnn_encoder.py` 의 재구현이고, 그것을 쓸 자격은 `--verify-dev` 하나다:
dev 157 백본을 다시 뽑아 커밋된 산출물과 `allclose(atol=1e-4)` 로 일치해야 한다.
2026-09-11 실행 결과는 shape (157, 384), max abs diff 9.06e-06, allclose True.
**이 검증을 통과하지 못하면 홀드아웃 추출을 하지 않는다** - train 과 test 가 다른
공간에 놓인 Gate 1 수치는 해석할 수 없다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent))

GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID = GATE0 / "holdout_grid"
BACKBONES = GATE0 / "backbones"
NATIVE_PDB_DIR = GATE0 / "holdout_targets_pdb"
DEPLOY_OUTPUTS = Path(os.environ.get("RAPID_DEPLOY_OUTPUTS", "/opt/protein_pipeline/outputs"))

#: dev 코호트와 같아야 하는 값. 다르면 Gate 1 을 실행하지 않는다.
ENCODER_DIM = 384
ENCODER_CKPT = "v_48_020"

#: dev 재현 검증의 합격선 (Task 7 Step 5a).
REPRO_ATOL = 1e-4


def resolve_backbone_pdbs() -> dict[str, dict]:
    """backbone_key -> {source, target_id, backbone_id, pdb_path}.

    backbone_key 형식은 `<target>|<source>|<backbone_id>` 다.
    """
    keys: set[tuple[str, str, str]] = set()
    with (GRID / "sequences.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            keys.add((row["target_id"], row["backbone_source"], row["backbone_key"]))

    out: dict[str, dict] = {}
    for target_id, source, backbone_key in sorted(keys):
        backbone_id = backbone_key.split("|")[2]
        if source == "target":
            pdb_path = NATIVE_PDB_DIR / f"{target_id}.pdb"
        else:
            pdb_path = (DEPLOY_OUTPUTS / f"holdout_{target_id}_rfd3"
                        / "rfd3" / "designs" / f"{backbone_id}.pdb")
        out[backbone_key] = {
            "source": source,
            "target_id": target_id,
            "backbone_id": backbone_id,
            "pdb_path": str(pdb_path),
        }
    return out


def verify_dev(*, out_npy: Path | None = None) -> bool:
    """dev 157 백본을 다시 뽑아 커밋된 mpnn_encoder.npy 와 비교한다.

    Task 7 Step 5a. 통과 기준은 shape (157, 384) 과 `allclose(atol=1e-4)` 다.
    """
    import numpy as np

    import _mpnn_encoder as ENC

    ref = np.load(BACKBONES / "mpnn_encoder.npy")
    rows = list(csv.DictReader((BACKBONES / "backbone_labels.csv").open(encoding="utf-8")))
    if ref.shape[0] != len(rows):
        print(f"행 정렬 실패: npy {ref.shape[0]} vs labels {len(rows)}")
        return False

    model = ENC.load_model()
    new = np.vstack([
        ENC.encode_backbone_pdb(BACKBONES / "pdb" / r["pdb_file"], model=model)
        for r in rows
    ])
    max_diff = float(np.abs(ref - new).max())
    ok = bool(ref.shape == new.shape == (len(rows), ENCODER_DIM)
              and np.allclose(ref, new, atol=REPRO_ATOL))
    print(f"shape {ref.shape} vs {new.shape}")
    print(f"max abs diff {max_diff:.6g}")
    print(f"allclose(atol={REPRO_ATOL}) {ok}")
    if out_npy is not None:
        np.save(out_npy, new)
    return ok


def extract(resolved: dict[str, dict], *, out_npy: Path, out_index: Path) -> None:
    """encoder feature 를 뽑아 행 정렬된 npy 와 index json 으로 쓴다."""
    import numpy as np

    import _mpnn_encoder as ENC

    model = ENC.load_model()
    keys = sorted(resolved)
    rows = []
    for key in keys:
        vec = ENC.encode_backbone_pdb(resolved[key]["pdb_path"], model=model)
        if vec.shape[-1] != ENCODER_DIM:
            raise SystemExit(
                f"encoder 차원이 {vec.shape[-1]} 이다. dev 코호트는 {ENCODER_DIM} 이므로 "
                "Gate 1 의 train/test 가 다른 공간에 놓인다. 중단한다."
            )
        rows.append(np.asarray(vec, dtype=np.float32))

    np.save(out_npy, np.vstack(rows))
    out_index.write_text(json.dumps({
        "ckpt": ENCODER_CKPT,
        "dim": ENCODER_DIM,
        "n_backbones": len(keys),
        "dev_reproduction": {
            "reference": "public_data/benchmark/gate0/backbones/mpnn_encoder.npy",
            "atol": REPRO_ATOL,
            "passed": True,
            "note": "--verify-dev 로 확인함. 통과 없이는 이 파일을 만들지 않는다.",
        },
        "backbone_keys": keys,
        "resolved": {k: resolved[k] for k in keys},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_npy} ({len(keys)}, {ENCODER_DIM})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-npy", default=str(GRID / "backbone_encoder.npy"))
    parser.add_argument("--out-index", default=str(GRID / "backbone_encoder.index.json"))
    parser.add_argument("--dry-run", action="store_true",
                        help="PDB 경로 해석만 하고 모델을 돌리지 않는다")
    parser.add_argument("--verify-dev", action="store_true",
                        help="dev 157 백본 재현 검증만 하고 끝낸다 (Task 7 Step 5a)")
    parser.add_argument("--verify-out", default="/tmp/dev_encoder_reproduction.npy")
    parser.add_argument("--skip-verify", action="store_true",
                        help="재현 검증을 건너뛴다. 검증이 이미 통과한 재실행에만 쓴다")
    args = parser.parse_args()

    if args.verify_dev:
        return 0 if verify_dev(out_npy=Path(args.verify_out)) else 1

    resolved = resolve_backbone_pdbs()
    missing = [v["pdb_path"] for v in resolved.values() if not Path(v["pdb_path"]).exists()]
    if missing:
        print(f"PDB 결측 {len(missing)} 건:")
        for path in missing[:10]:
            print("  ", path)
        return 1
    print(f"백본 {len(resolved)} 개 PDB 전부 해석됨")
    if args.dry_run:
        return 0
    if not args.skip_verify:
        print("dev 재현 검증:")
        if not verify_dev(out_npy=Path(args.verify_out)):
            print("dev feature 를 재현하지 못했다. 홀드아웃 추출을 하지 않는다 - "
                  "train 과 test 가 다른 공간에 놓인 Gate 1 수치는 해석할 수 없다.")
            return 1
    extract(resolved, out_npy=Path(args.out_npy), out_index=Path(args.out_index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
