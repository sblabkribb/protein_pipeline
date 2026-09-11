#!/usr/bin/env python3
"""격자 1,680 폴드의 per-sequence ProteinMPNN score 를 계산한다.

스펙 §4 의 S6 는 `S5 + 기존 cheap feature (조성, MPNN score)` 다. 격자의
`sequences.csv` 에는 MPNN score 열이 없고(서열은 RunPod 엔드포인트가 돌려줬고 그
엔드포인트는 score 를 돌려주지 않는다) score 를 가진 다른 코호트
(`mpnn_score_analysis.json`, 88 타겟 / 10,360 설계)와는 sequence_id 교집합이 0 이다.
그래서 2026-09-11 실행의 S6 는 조성 전용이었고 Gate 2 판정이 PRIMARY DEVIATION 으로
남았다. 이 스크립트가 빠진 열을 만든다.

**새 AF2 는 없다.** 이미 있는 라벨에 열 하나를 붙이는 것이고, score 는 설계 서열과
그 백본만 쓰는 backbone-conditioned likelihood 다.

score 정의는 `protein_mpnn_run.py --score_only` 와 같다:

    log_probs = model(X, S, mask, chain_M*chain_M_pos, residue_idx, chain_encoding_all, randn)
    score     = _scores(S, log_probs, mask*chain_M*chain_M_pos)   # 잔기당 평균 NLL

즉 `mpnn_score_analysis.py` 가 FASTA 헤더에서 뽑아 쓰는 `score` 와 같은 양이다
(낮을수록 그 백본 위에서 그럴듯한 서열). 자기회귀 디코더라 decoding order 에
의존하므로 **고정 시드로 뽑은 order 를 `--n-orders` 개 평균**한다. 시드는
`_gate2d.BOOTSTRAP_SEED` 이고 결과를 보고 고르지 않는다.

같은 백본의 24 서열은 한 배치로 넣는다 - 인코더는 서열과 무관하지만
`ProteinMPNN.forward` 를 재구현하지 않으려고 그대로 다시 돌린다.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

import _gate2d as G                     # noqa: E402
import _gate2d_cohort as C              # noqa: E402
import _mpnn_encoder as ENC             # noqa: E402

GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID = GATE0 / "holdout_grid"

#: ProteinMPNN 알파벳. protein_mpnn_run.py 와 같은 순서여야 한다.
ALPHABET = "ACDEFGHIKLMNPQRSTVWYX"

#: 평균할 random decoding order 수. 자기회귀 score 의 order 분산을 줄인다.
DEFAULT_N_ORDERS = 4


def _sequences_by_backbone() -> dict[str, list[tuple[str, str]]]:
    """backbone_key -> [(sequence_id, sequence)]. 라벨 있는 폴드만."""
    grid = C.load_holdout_grid()
    usable = {f.sequence_id for f in grid.folds}
    seq_of: dict[str, str] = {}
    key_of: dict[str, str] = {}
    with (GRID / "sequences.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            seq_of[row["sequence_id"]] = row["sequence"]
            key_of[row["sequence_id"]] = row["backbone_key"]
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for sequence_id in sorted(usable):
        out[key_of[sequence_id]].append((sequence_id, seq_of[sequence_id]))
    return dict(out)


def score_backbone(pdb_path: str, sequences: list[tuple[str, str]], *,
                   model, n_orders: int, seed: int) -> dict[str, float]:
    """백본 하나 위에서 서열들의 잔기당 평균 NLL. 낮을수록 그럴듯하다."""
    import torch

    utils = ENC.mpnn_utils()
    device = torch.device("cpu")
    pdb_dict_list = utils.parse_PDB(pdb_path, ca_only=False)
    dataset = utils.StructureDatasetPDB(pdb_dict_list, verbose=False, truncate=None,
                                        max_length=1_000_000)
    chains = [k[-1:] for k in pdb_dict_list[0] if k[:9] == "seq_chain"]
    chain_id_dict = {pdb_dict_list[0]["name"]: (chains, [])}
    batch = [copy.deepcopy(dataset[0]) for _ in sequences]
    out = utils.tied_featurize(batch, device, chain_id_dict, None, None, None, None,
                               None, ca_only=False)
    X, S, mask, chain_M, chain_encoding_all = out[0], out[1], out[2], out[4], out[5]
    chain_M_pos, residue_idx = out[10], out[12]

    length = X.shape[1]
    codes = []
    for sequence_id, sequence in sequences:
        if len(sequence) != length:
            raise SystemExit(
                f"{sequence_id}: 서열 길이 {len(sequence)} 가 백본 잔기 수 {length} 와 "
                "다르다. score 는 백본 조건부 likelihood 이므로 정렬 없이 계산하지 않는다."
            )
        codes.append([ALPHABET.index(a) if a in ALPHABET else ALPHABET.index("X")
                      for a in sequence])
    S = torch.tensor(codes, dtype=torch.long, device=device)

    mask_for_loss = mask * chain_M * chain_M_pos
    generator = torch.Generator(device="cpu").manual_seed(seed)
    totals = np.zeros(len(sequences), dtype=np.float64)
    with torch.no_grad():
        for _ in range(n_orders):
            randn = torch.randn(chain_M.shape, generator=generator)
            log_probs = model(X, S, mask, chain_M * chain_M_pos, residue_idx,
                              chain_encoding_all, randn)
            totals += utils._scores(S, log_probs, mask_for_loss).numpy().astype(np.float64)
    scores = totals / n_orders
    return {sid: float(v) for (sid, _seq), v in zip(sequences, scores)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(GRID / "mpnn_scores.json"))
    parser.add_argument("--n-orders", type=int, default=DEFAULT_N_ORDERS)
    parser.add_argument("--limit", type=int, default=0, help="백본 n 개만 (연습용)")
    args = parser.parse_args()

    index = json.loads((GRID / "backbone_encoder.index.json").read_text(encoding="utf-8"))
    resolved = index["resolved"]
    by_backbone = _sequences_by_backbone()
    keys = sorted(by_backbone)
    if args.limit:
        keys = keys[:args.limit]

    model = ENC.load_model()
    scores: dict[str, float] = {}
    started = time.time()
    for i, key in enumerate(keys):
        got = score_backbone(resolved[key]["pdb_path"], by_backbone[key], model=model,
                             n_orders=args.n_orders, seed=G.BOOTSTRAP_SEED)
        scores.update(got)
        print(f"[{i + 1}/{len(keys)}] {key} n={len(got)} "
              f"mean={np.mean(list(got.values())):.4f} {time.time() - started:.0f}s",
              flush=True)

    values = np.array([scores[k] for k in sorted(scores)])
    payload = {
        "definition": ("per-residue mean NLL of the design sequence on its own backbone, "
                       "averaged over random decoding orders. Same quantity as the "
                       "`score` field of the ProteinMPNN FASTA header. Lower is better."),
        "ckpt": "v_48_020 (soluble)",
        "mpnn_source": str(ENC.MPNN_SRC),
        "n_decoding_orders": args.n_orders,
        "seed": G.BOOTSTRAP_SEED,
        "n_sequences": len(scores),
        "n_backbones": len(keys),
        "no_new_af2": True,
        "summary": {"mean": round(float(values.mean()), 4),
                    "sd": round(float(values.std()), 4),
                    "min": round(float(values.min()), 4),
                    "max": round(float(values.max()), 4)},
        "scores": {k: round(scores[k], 6) for k in sorted(scores)},
        "provenance": G.run_provenance(
            "scripts/benchmark/27_gate2d_prepare_mpnn_scores.py",
            "scripts/benchmark/_mpnn_encoder.py",
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"wrote {args.out}  n={len(scores)}  mean={values.mean():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
