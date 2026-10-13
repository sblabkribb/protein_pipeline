#!/usr/bin/env python3
"""few-shot benchmark 의 동일 서열 누출을 통제한 재평가.

무엇이 문제였나
---------------
`02_model_comparison.py` 는 평가 집합을 **행 인덱스**로 만든다::

    tr = select_train_indices(X_full, n_train, seed, selection)
    te = np.setdiff1d(np.arange(n_avail), tr)

같은 타겟 안에 동일한 서열이 여러 행으로 있으면, 한 사본이 `tr` 에 뽑히고 다른
사본이 `te` 에 남는다. 모델은 평가 시점에 **이미 학습에서 본 서열**(동일 임베딩)
을 다시 본다. 실측: 9,206 행 중 타겟 내 고유 서열은 7,965 개이고, 중복을 가진
(타겟, 서열) 조합이 79 개, 그런 타겟이 21 개, 최대 120 회 중복이다.

두 대리 표적의 노출 정도가 다르다. SoluProt 은 서열의 결정론적 함수라 중복
조합 79 개 전부 라벨이 **완전히 같다** - 정답을 그대로 외울 수 있는 순수
누출이다. pLDDT 는 AF2 가 실행마다 조금씩 달라 2.5% 만 동일하고 중앙 편차가
0.044 다 - 부분 누출이다.

무엇을 하는가
-------------
**학습 절차를 바꾸지 않는다.** 원래와 똑같은 시드·선택 전략으로 똑같은 학습
집합을 뽑고 똑같이 적합한 뒤, **같은 모델을 두 평가 집합에서 잰다**:

    full    원래 평가 집합 (누출 포함)
    dedup   학습 서열과 동일한 서열을 제외한 평가 집합

그래서 두 값의 차이가 곧 누출의 기여분이고, 모델을 다시 고른 효과나 시드
차이가 섞이지 않는다. 적합을 한 번만 하므로 비용도 원래 실행과 같다.

하지 않는 것
------------
- 학습 집합을 다시 뽑지 않는다 (그러면 선택 전략의 효과와 섞인다).
- 중복 행을 미리 합치지 않는다 (그러면 학습 집합 구성이 달라진다).
- 원본 산출물을 덮어쓰지 않는다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PROJECT_ROOT = Path(
    os.environ.get("PROTEIN_PIPELINE_ROOT") or HERE.parents[1]).resolve()
DATA_DIR = PROJECT_ROOT / "data" / "benchmark"
RESULTS_DIR = DATA_DIR / "results"
CSV_PATH = DATA_DIR / "cath_pilot_dataset.csv"
EMB_PATH = DATA_DIR / "cath_pilot_emb_320d.npy"

# 원본과 **같은 값**을 쓴다. 여기서 바꾸면 재평가가 아니라 다른 실험이 된다.
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "exp1", HERE / "02_model_comparison.py")
_exp1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_exp1)

SEEDS = _exp1.SEEDS
N_TRAIN_DEFAULT = _exp1.N_TRAIN_DEFAULT
SURROGATE_TARGETS = _exp1.SURROGATE_TARGETS
SELECTION_STRATEGIES = _exp1.SELECTION_STRATEGIES

from _selection import select_train_indices  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-train", type=int, default=N_TRAIN_DEFAULT)
    parser.add_argument("--emb", default=str(EMB_PATH))
    parser.add_argument("--out",
                        default=str(RESULTS_DIR / "exp1_dedup_controlled.parquet"))
    parser.add_argument("--limit-targets", type=int, default=0)
    args = parser.parse_args(argv)

    df = pd.read_csv(CSV_PATH)
    embeddings = np.load(args.emb)
    if embeddings.shape[0] != len(df):
        raise SystemExit(
            f"임베딩 {embeddings.shape} 이 CSV 행 수 {len(df)} 과 다르다")

    targets = sorted(df["target"].unique())
    if args.limit_targets:
        targets = targets[: args.limit_targets]

    rows: list[dict] = []
    started = time.time()
    n_split = 0
    print(f"타겟 {len(targets)} · 시드 {len(SEEDS)} · 선택 {SELECTION_STRATEGIES}",
          flush=True)

    for selection in SELECTION_STRATEGIES:
        for surrogate in SURROGATE_TARGETS:
            for tgt in targets:
                mask = (df["target"] == tgt) & df[surrogate].notna()
                sub = df[mask].reset_index(drop=True)
                indices = df.index[mask].to_numpy()
                X_full = embeddings[indices]
                y_full = sub[surrogate].to_numpy(dtype=np.float64)
                seqs = sub["sequence"].to_numpy()

                n_avail = len(sub)
                if n_avail < args.n_train + 5:
                    continue

                for seed in SEEDS:
                    tr = select_train_indices(X_full, args.n_train, seed, selection)
                    te_full = np.setdiff1d(np.arange(n_avail), tr,
                                           assume_unique=False)
                    # 누출 제거: 학습에 들어간 서열과 **같은 서열**을 평가에서 뺀다.
                    train_seqs = set(seqs[tr].tolist())
                    keep = np.array([s not in train_seqs for s in seqs[te_full]],
                                    dtype=bool)
                    te_dedup = te_full[keep]
                    n_leaked = int(len(te_full) - len(te_dedup))

                    for name, model in _exp1.make_models(seed).items():
                        scale = _exp1.needs_scaling(name)
                        # **한 번만 적합**하고 두 평가 집합에 같은 모델을 쓴다.
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            pred_full = _exp1.fit_predict(
                                model, X_full[tr], y_full[tr], X_full[te_full],
                                seed, scale)
                        pos = {int(i): j for j, i in enumerate(te_full)}
                        sel = np.array([pos[int(i)] for i in te_dedup], dtype=int)
                        pred_dedup = pred_full[sel] if len(sel) else pred_full[:0]

                        base = {
                            "selection": selection, "surrogate": surrogate,
                            "target": tgt, "seed": seed, "model": name,
                            "n_train": int(len(tr)),
                            "n_test_full": int(len(te_full)),
                            "n_test_dedup": int(len(te_dedup)),
                            "n_leaked_rows": n_leaked,
                            "split_had_leak": bool(n_leaked > 0),
                        }
                        mf = _exp1.evaluate(y_full[te_full], pred_full, seed)
                        for k, v in mf.items():
                            base[f"full_{k}"] = v
                        if len(te_dedup) >= 2:
                            md = _exp1.evaluate(y_full[te_dedup], pred_dedup, seed)
                            for k, v in md.items():
                                base[f"dedup_{k}"] = v
                        rows.append(base)
                    n_split += 1

                print(f"  {selection}/{surrogate}/{tgt} "
                      f"(n={n_avail}, {time.time()-started:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    leaked = out[out["split_had_leak"]]
    print(f"\n분할 {n_split} · 행 {len(out)} · 누출 있던 분할 비율 "
          f"{out['split_had_leak'].mean()*100:.1f}%")
    print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
