#!/usr/bin/env python3
"""P2. Gate 2 용 ESM 임베딩. 설계 서열과 타겟 WT reference 를 함께 만든다.

ΔESM 은 두 종류다.
  ΔESM_global : mean-pool(design) − mean-pool(WT)
  ΔESM_mut    : 변이 위치의 토큰 임베딩 차이만 평균

프로덕션 surrogate 와 같은 모델(esm2_t6_8M_UR50D, 320-D)을 기본으로 쓴다.
ESM 크기 스케일링은 이 게이트의 질문이 아니다 (Supp. Note 3 에서 이미 음성).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, EsmModel

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
NATIVE_PDB_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_targets_pdb"
OUT_DIR = PROJECT_ROOT / "data" / "benchmark"

MODEL_NAME = "facebook/esm2_t6_8M_UR50D"
EMB_DIM = 320

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}


def mutation_sites(wt: str, design: str) -> list[int]:
    """WT 와 다른 위치의 0-기반 인덱스.

    길이가 다르면 위치 대응이 성립하지 않는다. 조용히 자르면 ΔESM_mut 가
    엉뚱한 위치를 보게 되므로 예외를 낸다.
    """
    if len(wt) != len(design):
        raise ValueError(f"길이 불일치: WT {len(wt)} vs design {len(design)}")
    return [i for i, (a, b) in enumerate(zip(wt, design)) if a != b]


def wt_sequence_from_pdb(path: Path) -> str:
    """native 타겟 PDB 의 CA 잔기 순서에서 서열을 읽는다."""
    seq: list[str] = []
    seen: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        key = (line[21], line[22:27])
        if key in seen:
            continue
        seen.add(key)
        seq.append(THREE_TO_ONE.get(line[17:20].strip().upper(), "X"))
    return "".join(seq)


def embed(sequences: list[str], *, device: torch.device,
          batch_size: int = 8) -> tuple[np.ndarray, list[np.ndarray]]:
    """(mean-pooled (n, EMB_DIM), 서열별 토큰 임베딩 리스트) 를 돌려준다.

    토큰 임베딩은 ΔESM_mut 에 필요하다. 특수 토큰(BOS/EOS)을 잘라 잔기와
    1:1 로 맞춘다 - 이걸 틀리면 변이 위치가 한 칸씩 밀린다.
    """
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = EsmModel.from_pretrained(MODEL_NAME).to(device).eval()

    pooled: list[np.ndarray] = []
    per_token: list[np.ndarray] = []
    for start in range(0, len(sequences), batch_size):
        chunk = sequences[start:start + batch_size]
        batch = tokenizer(chunk, return_tensors="pt", padding=True)
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.no_grad():
            out = model(**batch)
        hidden = out.last_hidden_state
        cls_id = tokenizer.cls_token_id
        # 잔기 수 = attention 길이 − <cls> − <eos>. padding 에 무관하다.
        residue_counts = (batch["attention_mask"].sum(dim=1) - 2).tolist()
        for row, seq in enumerate(chunk):
            if int(batch["input_ids"][row, 0]) != cls_id:
                raise SystemExit(
                    "0 번 토큰이 <cls> 가 아니다. BOS 를 1칸 건너뛰는 slice 가 "
                    "잔기를 한 칸 밀어 ΔESM_mut 이 엉뚱한 위치를 본다. 중단한다."
                )
            if int(residue_counts[row]) != len(seq):
                raise SystemExit(
                    f"attention 기준 잔기 {int(residue_counts[row])} 개가 서열 "
                    f"{len(seq)} 개와 다르다. 중단한다."
                )
            tokens = hidden[row, 1:1 + len(seq)].float().cpu().numpy()
            per_token.append(tokens.astype(np.float32))
            pooled.append(tokens.mean(axis=0).astype(np.float32))
    return np.vstack(pooled), per_token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader((GRID / "sequences.csv").open(encoding="utf-8")))
    designs = [r["sequence"] for r in rows]
    targets = sorted({r["target_id"] for r in rows})
    wt = {t: wt_sequence_from_pdb(NATIVE_PDB_DIR / f"{t}.pdb") for t in targets}

    d_pooled, d_tokens = embed(designs, device=device, batch_size=args.batch_size)
    w_pooled, w_tokens = embed([wt[t] for t in targets], device=device,
                               batch_size=args.batch_size)

    np.save(OUT_DIR / "gate2d_esm_8m_designs.npy", d_pooled)
    np.save(OUT_DIR / "gate2d_esm_8m_wt.npy", w_pooled)
    np.savez_compressed(OUT_DIR / "gate2d_esm_8m_tokens.npz",
                        **{f"d{i}": t for i, t in enumerate(d_tokens)},
                        **{f"w_{t}": w_tokens[i] for i, t in enumerate(targets)})

    length_mismatch = sorted(
        {r["target_id"] for r in rows if len(r["sequence"]) != len(wt[r["target_id"]])}
    )
    (OUT_DIR / "gate2d_esm.index.json").write_text(json.dumps({
        "model": MODEL_NAME, "dim": EMB_DIM,
        "n_designs": len(designs), "targets": targets,
        "sequence_ids": [r["sequence_id"] for r in rows],
        "wt_lengths": {t: len(wt[t]) for t in targets},
        "length_mismatch_targets": length_mismatch,
        "length_mismatch_note": (
            "이 타겟들은 설계 길이가 WT 와 달라 ΔESM_mut 를 위치 대응으로 계산할 수 "
            "없다. S3/S5/S6 에서 스펙 §4 의 결측 규칙(train fold 평균 + 지시자)을 "
            "적용한다. 타겟을 코호트에서 빼지 않는다."
        ),
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"designs {d_pooled.shape}  wt {w_pooled.shape}  "
          f"length-mismatch targets {len(length_mismatch)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
