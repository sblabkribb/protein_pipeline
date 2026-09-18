#!/usr/bin/env python3
"""few-shot 을 **고유 서열 단위**로 재평가하고 모델 간 우열을 쌍대로 판정한다.

규칙은 `docs/specs/unique-sequence-reeval-prespec.md` 에 실행 전 동결돼 있다.
여기서 그 문서에 없는 선택을 새로 하지 않는다.

무엇을 바로잡는가
-----------------
`28_dedup_controlled_reeval.py` 는 학습과 겹치는 평가 행만 뺐다. 남은 것::

    학습 집합 내부 중복   라벨 예산 30 건에 같은 서열이 여러 번 들어가면
                          실효 고유 라벨이 30 보다 적다
    평가 집합 내부 중복   같은 서열이 평가에서 여러 번 가중된다

실측: 9,206 행 · 고유 조합 7,965 · 중복 행 1,241 (13.5%) · 최대 반복 120 회.

두 단위를 같은 표적 집합에서 나란히 낸다
----------------------------------------
`row`     원래 프로토콜. 행 단위. 중복이 학습·평가 양쪽에 남는다.
`unique`  (표적, 서열) 단위로 붕괴. 라벨은 반복 pLDDT 의 **중앙값**.

같은 표적 집합에서 둘을 돌리므로 차이가 **붕괴의 효과**로 귀속된다 - 코호트가
바뀐 효과와 섞이지 않는다.

모델 간 우열은 쌍대로만 말한다
------------------------------
RF 0.4370 과 Ridge 0.4066 이라는 점추정만으로는 구별을 주장할 수 없다. 같은
부트스트랩 표본 안에서 차이를 계산한다. 구간이 0 을 포함하면 "구별되지 않았다"
로 쓴다 (사전지정 §4).

하지 않는 것
------------
- 새 folding 을 하지 않는다. 기존 라벨·임베딩만 쓴다.
- 절차·선택 전략·모델 목록·seed·표적 포함 기준을 결과를 보고 바꾸지 않는다.
- `28_` 산출물을 덮어쓰지 않는다.
- 동결된 v1/v2 판정을 바꾸지 않는다.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
DATA = PROJECT_ROOT / "data" / "benchmark"
OUT_DIR = DATA / "results"

#: 사전지정 §3.4-3.9. 바꾸지 않는다.
N_TRAIN = 30
TOP_K = 20
MIN_UNIQUE = 50           # 학습 30 + 평가 최소 20
SEEDS = [42, 123, 7, 2024, 31337]
N_BOOTSTRAP = 2000
BOOT_SEED = 20260918
SELECTION = "kmeans"


def _orig():
    """`02_model_comparison.py` 의 모델 규격과 지표를 그대로 가져온다."""
    path = HERE / "02_model_comparison.py"
    spec = importlib.util.spec_from_file_location("model_comparison", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ 입력

def load_rows() -> tuple[pd.DataFrame, np.ndarray]:
    df = pd.read_csv(DATA / "cath_pilot_dataset.csv")
    X = np.load(DATA / "cath_pilot_emb_320d.npy")
    if len(df) != X.shape[0]:
        raise SystemExit(f"행 {len(df)} != 임베딩 {X.shape[0]}")
    return df, X


def collapse(df: pd.DataFrame, X: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    """(표적, 서열) 단위로 붕괴. 라벨 = 반복 pLDDT 의 중앙값 (사전지정 §3.2).

    임베딩은 파일 순서상 첫 행을 쓴다 (§3.3). 같은 서열끼리 최대 5.662e-07 만
    다르므로 평균으로 새 벡터를 만들 이유가 없다.
    """
    df = df.reset_index(drop=True)
    first = df.groupby(["target", "sequence"], sort=False).head(1).index.to_numpy()
    med = (df.groupby(["target", "sequence"], sort=False).plddt.median()
           .rename("plddt_median").reset_index())
    kept = df.loc[first, ["target", "sequence", "soluprot"]].reset_index(drop=True)
    kept["row_index"] = first
    merged = kept.merge(med, on=["target", "sequence"], how="left", validate="1:1")
    return merged, X[merged.row_index.to_numpy()]


# ---------------------------------------------------------------- 평가

def evaluate(unit: str, frame: pd.DataFrame, X: np.ndarray, label_col: str,
             targets: list[str], *, progress=True) -> dict:
    """표적 x seed x 모델 의 Top-K recall. 원본 함수를 그대로 쓴다."""
    from _selection import select_train_indices
    orig = _orig()

    per_target: dict[str, dict[str, float]] = collections.defaultdict(dict)
    acc: dict[str, dict[str, list]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    started = time.monotonic()
    for n, target in enumerate(targets, 1):
        idx = frame.index[frame.target == target].to_numpy()
        Xt = X[idx]
        y = frame.loc[idx, label_col].to_numpy(dtype=float)
        for seed in SEEDS:
            tr = select_train_indices(Xt, N_TRAIN, seed, SELECTION)
            te = np.setdiff1d(np.arange(len(idx)), tr)
            if len(te) < TOP_K:
                continue
            for name, model in orig.make_models(seed).items():
                pred = orig.fit_predict(model, Xt[tr], y[tr], Xt[te], seed,
                                        orig.needs_scaling(name))
                acc[target][name].append(orig.topk_recall(y[te], pred, TOP_K))
        if progress and (n % 10 == 0 or n == len(targets)):
            rate = (time.monotonic() - started) / n
            print(f"    [{unit}] {n}/{len(targets)} 표적 "
                  f"(~{(len(targets)-n)*rate/60:.1f}분 남음)", flush=True)

    for target, by_model in acc.items():
        for name, vals in by_model.items():
            if vals:
                per_target[target][name] = statistics.mean(vals)
    return dict(per_target)


def summarize(per_target: dict, models: list[str]) -> dict:
    """표적 동일가중 평균과 **쌍대** 차이. 같은 재표집 표본에서 차이를 낸다."""
    names = sorted(t for t, v in per_target.items()
                   if all(m in v for m in models))
    rng = np.random.default_rng(BOOT_SEED)
    boots = [[names[int(rng.integers(len(names)))] for _ in names]
             for _ in range(N_BOOTSTRAP)]

    def agg(ts, m):
        return statistics.mean(per_target[t][m] for t in ts)

    out = {"n_targets": len(names), "targets": names, "per_model": {},
           "paired_vs": {}}
    for m in models:
        draws = sorted(agg(b, m) for b in boots)
        out["per_model"][m] = {
            "point": agg(names, m),
            "ci95": [draws[int(0.025 * len(draws))],
                     draws[min(len(draws) - 1, int(0.975 * len(draws)))]],
        }
    for a in models:
        for b in models:
            if a >= b:
                continue
            draws = sorted(agg(x, a) - agg(x, b) for x in boots)
            lo = draws[int(0.025 * len(draws))]
            hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
            out["paired_vs"][f"{a}-{b}"] = {
                "delta": agg(names, a) - agg(names, b),
                "ci95": [lo, hi], "excludes_zero": bool(lo > 0 or hi < 0),
            }
    return out


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT_DIR / "exp1_unique_sequence.json"))
    args = ap.parse_args(argv)

    df, X = load_rows()
    uni, Xu = collapse(df, X)
    counts = uni.groupby("target").size()
    targets = sorted(counts[counts >= MIN_UNIQUE].index)
    print(f"행 {len(df)} · 고유 조합 {len(uni)} · 중복 행 {len(df)-len(uni)}")
    print(f"고유 >= {MIN_UNIQUE} 인 표적 {len(targets)}/{df.target.nunique()}",
          flush=True)

    models = ["RF", "Ridge", "XGBoost", "LightGBM", "KNN", "GP-RBF", "MLP", "Random"]

    print("\n[unique] (표적, 서열) 단위 · 라벨 = 반복 pLDDT 중앙값", flush=True)
    pt_u = evaluate("unique", uni, Xu, "plddt_median", targets)
    print("\n[row] 원래 행 단위 · **같은 표적 집합**", flush=True)
    row = df.reset_index(drop=True)
    pt_r = evaluate("row", row, X, "plddt", targets)

    out = {
        "purpose": ("few-shot 을 고유 서열 단위로 재평가하고 모델 간 우열을 "
                    "쌍대로 판정한다. 새 folding 없음."),
        "prespec": "docs/specs/unique-sequence-reeval-prespec.md",
        "prespec_sha256": hashlib.sha256(
            (PROJECT_ROOT / "docs" / "specs"
             / "unique-sequence-reeval-prespec.md").read_bytes()).hexdigest(),
        "protocol_source": ("_selection.py::select_train_indices(kmeans) + "
                            "02_model_comparison.py::make_models/fit_predict/topk_recall"),
        "n_train_unique_sequences": N_TRAIN, "top_k": TOP_K,
        "min_unique_per_target": MIN_UNIQUE, "seeds": SEEDS,
        "bootstrap": {"n": N_BOOTSTRAP, "unit": "target", "seed": BOOT_SEED,
                      "paired": "같은 재표집 표본에서 모델 간 차이를 계산한다"},
        "duplication_measured": {
            "n_rows": int(len(df)), "n_unique_pairs": int(len(uni)),
            "n_duplicate_rows": int(len(df) - len(uni)),
            "label_rule": "median plddt per (target, sequence)",
            "embedding_rule": "first row in file order (max deviation 5.662e-07)",
        },
        "n_targets_evaluated": len(targets),
        "units": {},
    }
    for unit, pt in (("unique", pt_u), ("row", pt_r)):
        out["units"][unit] = summarize(pt, models)
        out["units"][unit]["per_target"] = pt

    print(f"\n=== Top-{TOP_K} recall (표적 동일가중, 같은 {len(targets)} 표적)")
    print(f"  {'model':10s}{'unique':>10}{'ci95':>22}{'row':>10}{'차이':>9}")
    for m in models:
        u = out["units"]["unique"]["per_model"][m]
        r = out["units"]["row"]["per_model"][m]
        print(f"  {m:10s}{u['point']:10.4f}"
              f"  [{u['ci95'][0]:.4f},{u['ci95'][1]:.4f}]"
              f"{r['point']:10.4f}{u['point']-r['point']:+9.4f}")

    print("\n=== 쌍대 비교 (unique 단위)")
    pv = out["units"]["unique"]["paired_vs"]
    for key in ("GP-RBF-RF", "KNN-RF", "LightGBM-RF", "MLP-RF", "RF-Random",
                "RF-Ridge", "RF-XGBoost", "Random-Ridge"):
        if key in pv:
            v = pv[key]
            print(f"  {key:16s} {v['delta']:+.4f} "
                  f"[{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}]  "
                  f"{'0 제외' if v['excludes_zero'] else '0 포함 → 구별되지 않음'}")

    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"\n{args.out}")
    print("sha256", hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
