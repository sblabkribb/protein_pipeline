#!/usr/bin/env python3
"""ThermoMPNN ddG 추론 드라이버.

THERMOMP_PYTHON (torch/pytorch-lightning venv) 으로 실행된다. HTTP 워커
(thermomp_ddg_http_worker.py) 가 subprocess 로 부르는 것이 정상 경로다.

Kuhlman-Lab/ThermoMPNN (MIT) 을 THERMOMP_ROOT 에 클론해 두어야 한다.
models/thermoMPNN_default.pt 와 vanilla_model_weights/ 를 그 저장소에서 읽는다.

입력 PDB 좌표계 규약:
- 변이 표기 "A123W" = (native AA)(1-based PDB resseq)(설계 AA). 사슬은 --chain.
- 모델 position 은 0-based 이고 사슬의 최소 resseq 기준 상대 위치다
  (alt_parse_PDB_biounits 가 resn = int(resseq)-1 로 걸어가는 것과 동일).
- ddG 단위 kcal/mol, 양수 = 불안정화 (ΔG_mutant − ΔG_wildtype).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import types


def _ensure_wandb_stub() -> None:
    """train_thermompnn 는 import 시점에 wandb 른 요구한다. 추론엔 불필요하므로
    없으면 스텁으로 대체한다 - 학습 경로는 이 드라이버가 쓰지 않는다."""
    try:
        import wandb  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("wandb")
        stub.init = lambda *args, **kwargs: None
        sys.modules["wandb"] = stub


# Kyte-Doolittle 이 아니라 표준 3→1 코드. alt_parse_PDB 와 같은 대응.
_THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}

_ALPHABET = "ACDEFGHIKLMNPQRSTVWYX"


def _parse_chain(pdb_path: str, chain: str) -> dict[int, str]:
    """사슬의 resseq → 1-letter 서열. ATOM 레코드만, 파일 순서대로."""
    residues: dict[int, str] = {}
    with open(pdb_path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("ATOM"):
                continue
            if line[21:22] != chain:
                continue
            resname = line[17:20].strip().upper()
            aa = _THREE_TO_ONE.get(resname)
            if aa is None:
                continue
            try:
                resseq = int(line[22:26].strip())
            except ValueError:
                continue
            residues.setdefault(resseq, aa)
    return residues


def _fail(message: str) -> None:
    print(json.dumps({"error": message}))
    sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdb", required=True)
    parser.add_argument("--chain", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--mutations", default="")
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = os.environ.get("THERMOMP_ROOT", "").strip()
    if not root or not os.path.isdir(root):
        _fail(f"THERMOMP_ROOT not set or missing: {root!r}")
    sys.path.insert(0, root)
    _ensure_wandb_stub()

    import torch
    from omegaconf import OmegaConf
    from protein_mpnn_utils import alt_parse_PDB
    from train_thermompnn import TransferModelPL

    model_path = args.model_path or os.path.join(root, "models", "thermoMPNN_default.pt")
    if not os.path.isfile(model_path):
        _fail(f"ThermoMPNN checkpoint missing: {model_path}")

    config = OmegaConf.create(
        {
            "platform": {"thermompnn_dir": root, "accel": "gpu"},
            "training": {
                "num_workers": 0,
                "learn_rate": 0.001,
                "epochs": 100,
                "lr_schedule": True,
            },
            "model": {
                "hidden_dims": [64, 32],
                "subtract_mut": True,
                "num_final_layers": 2,
                "freeze_weights": True,
                "load_pretrained": True,
                "lightattn": True,
                "lr_schedule": True,
            },
        }
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = (
        TransferModelPL.load_from_checkpoint(model_path, cfg=config)
        .model.eval()
        .to(device)
    )

    # 사슬 선택: 지정 없으면 파일에서 발견된 첫 사슬 (custom_inference 와 같다).
    if args.chain:
        chain = args.chain
    else:
        found: dict[str, str] = {}
        with open(args.pdb, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("ATOM") and line[17:20].strip().upper() in _THREE_TO_ONE:
                    found.setdefault(line[21:22], line[21:22])
        if not found:
            _fail(f"no protein ATOM records found in {args.pdb}")
        chain = next(iter(found))
    residue_map = _parse_chain(args.pdb, chain)
    if not residue_map:
        _fail(f"chain {chain!r} has no protein ATOM records in {args.pdb}")

    pdb_dict_list = alt_parse_PDB(args.pdb, input_chain_list=[chain])
    if not pdb_dict_list or pdb_dict_list[0].get("num_of_chains", 0) < 1:
        _fail(f"alt_parse_PDB found no usable chain {chain!r} in {args.pdb}")
    pdb_entry = pdb_dict_list[0]
    seq_key = f"seq_chain_{chain}"
    parsed_seq = str(pdb_entry.get(seq_key, ""))
    if not parsed_seq:
        _fail(f"parsed sequence empty for chain {chain!r}")

    # resseq → 모델 position. alt_parse_PDB_biounits 는 min_resseq 를 0-based
    # 범위의 시작으로 쓰므로 position = resseq - min_resseq 다.
    min_resseq = min(residue_map)
    requested: list[tuple[int, str, str, int]] = []
    if args.mutations.strip():
        for raw in args.mutations.split(","):
            token = raw.strip()
            if not token:
                continue
            if len(token) < 3 or token[0] not in _ALPHABET or token[-1] not in _ALPHABET:
                _fail(f"invalid mutation token {token!r} (expected e.g. A123W)")
            try:
                resseq = int(token[1:-1])
            except ValueError:
                _fail(f"invalid residue number in mutation token {token!r}")
            if resseq not in residue_map:
                _fail(f"resseq {resseq} not found in chain {chain!r}")
            wt_aa = residue_map[resseq]
            if wt_aa != token[0]:
                _fail(
                    f"wildtype mismatch at {chain}{resseq}: PDB says {wt_aa}, "
                    f"token says {token[0]}"
                )
            requested.append((resseq, token[0], token[-1], resseq - min_resseq))
    else:
        # 전체 단일-변이 스캔 (SSM 규약: 파싱 서열 순회, '-' 자리는 건너뛴다).
        scan_resseqs: list[tuple[int, str, str, int]] = []
        for seq_pos, aa in enumerate(parsed_seq):
            if aa in ("-", "X"):
                continue
            for mut_aa in _ALPHABET[:-1]:
                if mut_aa == aa:
                    continue
                scan_resseqs.append((seq_pos + min_resseq, aa, mut_aa, seq_pos))
        if args.top_n:
            scan_resseqs = scan_resseqs[: args.top_n]
        requested = scan_resseqs

    if not requested:
        _fail("no mutations to score")

    from datasets import Mutation

    mutation_objs = [
        Mutation(position=pos, wildtype=wt, mutation=mut, ddG=None, pdb=pdb_entry["name"])
        for (_resseq, wt, mut, pos) in requested
    ]

    with torch.no_grad():
        pred, _ = model(pdb_dict_list, mutation_objs)

    predictions = []
    total = 0.0
    for (resseq, wt, mut, _pos), out in zip(requested, pred):
        if out is None:
            continue
        ddg = float(out["ddG"].cpu().item())
        total += ddg
        predictions.append(
            {
                "wildtype": wt,
                "resseq": resseq,
                "mutation": mut,
                "label": f"{wt}{resseq}{mut}" if mut else f"{wt}{resseq}",
                "ddG_kcal_mol": round(ddg, 4),
            }
        )

    payload = {
        "chain": chain,
        "model_path": model_path,
        "device": str(device),
        "n_mutations": len(predictions),
        "additive_ddg_kcal_mol": round(total, 4),
        "mutations": predictions,
        "sign_convention": "ddG > 0 destabilizing (dG_mutant - dG_wildtype)",
        "note": "단일-변이 예측의 합은 가법 근사이고 에피스테이시스를 무시한다.",
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "out": args.out}))


if __name__ == "__main__":
    main()
