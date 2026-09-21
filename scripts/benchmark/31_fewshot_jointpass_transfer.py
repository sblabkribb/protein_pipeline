#!/usr/bin/env python3
"""few-shot 국소 보정을 **동결 종점(joint-pass)** 과 **예산 일치 비교**로 다시 본다.

왜 필요한가
-----------
기존 few-shot 결과는 강했다 - 타겟 하나에서 AF2 라벨 30 개를 먼저 얻고 나머지를
순위화하면 pLDDT Top-20 recall 이 0.437 이고 무작위는 0.221 이었다(중복 통제 후,
67 타겟). 학습기 8 개 중 5 개가 0.40-0.44 에 몰려 있어 특정 모델의 우연도 아니다.

그런데 그 결과를 리포트의 주 결과로 올리기에는 두 구멍이 있다.

**① 라벨이 joint-pass 가 아니다.** 그 분석의 목표변수는 `plddt` 다. 리포트의
동결 종점은 joint-pass = pLDDT >= 85 AND 비루프 Cα-RMSD <= 2.0 Å AND
SoluProt >= 0.5 다. `cath_pilot_dataset.csv` 에는 RMSD 열이 아예 없으므로
거기서는 답할 수 없다. 그리고 이것은 형식 문제가 아니다 - pLDDT 는 AF2 의
서열별 확신도 출력 자체이므로 "AF2 가 확신할까" 를 맞히는 것과 "AF2 가 이 특정
백본 기하를 재현할까" 를 맞히는 것은 난이도가 다를 수 있다.

**② 30 건의 라벨 비용이 비교에 들어가 있지 않다.** 무작위 기준선 0.221 은
**이미 30 건을 쓴 뒤** 남은 pool 안에서의 무작위다. 그래서 1.98 배는 enrichment
factor 이고 예산 절감 배수가 아니다. 예산 절감을 주장하려면 같은 총예산에서
비교해야 한다.

이 스크립트가 하는 것
--------------------
A. **joint-pass 전이 시험** - holdout 격자(12 타겟 x 120 후보, RFD3)에서 같은
   프로토콜을 joint-pass / structural-pass / pLDDT 세 라벨로 각각 돌린다.
B. **예산 일치 비교** - 총예산 B 에서 `probe 30 -> 학습 -> 상위 (B-30) 선택` 과
   `무작위 B` 를 비교한다. **probe 자체가 찾은 통과 후보도 수익에 센다** - 실제로
   접은 것이므로 버리지 않는다. 이것이 ② 가 빠뜨린 회계다.

프로토콜은 새로 만들지 않는다. `_selection.select_train_indices` 와
`02_model_comparison.py` 의 RF 규격(100 trees) · seed 5 개를 그대로 쓴다.

이진 라벨의 지표
----------------
joint-pass 는 0/1 이라 `topk_recall` 의 `argsort` 가 동점에서 임의 순서를 준다 -
지표가 정의되지 않는다. 그래서 **선택된 상위 K 안의 통과율**을 쓴다. 이것이
의사결정에서 실제로 궁금한 값이기도 하다 - "접기로 고른 K 개 중 몇 개가
통과하는가". pLDDT 라벨에서는 원래 `topk_recall` 도 함께 낸다.

하지 않는 것
------------
- 동결된 v1/v2 판정을 바꾸지 않는다. 별도의 평가축이다.
- joint-pass 율이 0% 또는 100% 인 타겟은 informative set 에서 뺀다 - 판별이
  원리적으로 불가능하다. §3.4 가 쓴 것과 같은 규칙이다.
- 학습 절차를 라벨에 맞게 조정하지 않는다. 세 라벨에 같은 절차를 쓴다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import statistics
import sys
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
OUT_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
EMB_CACHE = PROJECT_ROOT / "data" / "benchmark" / "holdout_grid_emb_320d.npz"

#: 동결 문턱.
PLDDT_MIN, RMSD_MAX, SOLUPROT_MIN = 85.0, 2.0, 0.5
#: 원본과 같은 seed 와 probe 예산.
SEEDS = [42, 123, 7, 2024, 31337]
N_TRAIN = 30
TOP_K = 20
#: 예산 일치 비교의 총예산 격자. probe 30 을 포함한 총액이다.
BUDGET_GRID = [30, 40, 50, 60, 80, 100, 120]
N_BOOTSTRAP = 2000
BOOT_SEED = 20260918
#: 학습 집합 선택 전략. 원본과 같다.
SELECTION_STRATEGY = "kmeans"


# ------------------------------------------------------------------ 입력

def load_grid() -> list[dict]:
    seqs = {r["sequence_id"]: r["sequence"] for r in
            csv.DictReader((GRID / "sequences.csv").open(encoding="utf-8"))}
    rows = []
    for r in csv.DictReader((GRID / "af2_order_metric.csv").open(encoding="utf-8")):
        if r.get("status") != "ok" or r.get("backbone_source") != "rfd3":
            continue
        sid = r["sequence_id"]
        try:
            pl, rm, so = (float(r["plddt"]), float(r["rmsd_nonloop_order"]),
                          float(r["soluprot"]))
        except (TypeError, ValueError, KeyError):
            continue
        if sid not in seqs:
            continue
        structural = bool(pl >= PLDDT_MIN and rm <= RMSD_MAX)
        rows.append({
            "sequence_id": sid, "sequence": seqs[sid], "target_id": r["target_id"],
            "backbone_key": r["backbone_key"],
            "plddt": pl,
            "structural_pass": float(structural),
            "joint_pass": float(structural and so >= SOLUPROT_MIN),
        })
    return rows


def embeddings_for(rows: list[dict], url: str) -> np.ndarray:
    """ESM-2 8M (320d). CATH pilot 과 같은 모델이라 비교 가능하다."""
    digest = hashlib.sha256(
        "\n".join(r["sequence_id"] for r in rows).encode()).hexdigest()
    if EMB_CACHE.exists():
        # 캐시는 float 배열과 <U64 해시 문자열뿐이라 pickle 이 필요 없다.
        # allow_pickle 을 켜지 않으므로 캐시 파일이 코드를 실행할 수 없다.
        z = np.load(EMB_CACHE, allow_pickle=False)
        if str(z["digest"]) == digest:
            print(f"  임베딩 캐시 사용 {EMB_CACHE.name} {z['embeddings'].shape}",
                  flush=True)
            return z["embeddings"]
    from pipeline_mcp.clients.esm_embedding import LocalHTTPESMEmbeddingClient
    if not url:
        raise SystemExit("ESM 임베딩 URL 이 없다 (--esm-url 또는 RAPID_GPU_HOST)")
    print(f"  임베딩 계산 {len(rows)} 서열 · {url}", flush=True)
    client = LocalHTTPESMEmbeddingClient(base_url=url, token=None)
    emb = client.embed([r["sequence"] for r in rows])
    EMB_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMB_CACHE, embeddings=emb, digest=digest)
    print(f"  저장 {EMB_CACHE} {emb.shape}", flush=True)
    return emb


# ------------------------------------------- A. joint-pass 전이 시험

def fit_rank(X, y, tr, te, seed, *, estimator="RF"):
    """원본과 같은 규격. 라벨이 무엇이든 같은 절차를 쓴다.

    Ridge 는 `02_model_comparison.needs_scaling` 이 True 로 두는 모델이므로
    원본과 같게 표준화를 붙인다. RF 는 붙이지 않는다.
    """
    Xtr, Xte = X[tr], X[te]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if estimator == "Ridge":
            from sklearn.linear_model import Ridge
            from sklearn.preprocessing import StandardScaler
            sc = StandardScaler().fit(Xtr)
            Xtr, Xte = sc.transform(Xtr), sc.transform(Xte)
            model = Ridge(alpha=1.0, random_state=seed)
        elif estimator == "RF":
            from sklearn.ensemble import RandomForestRegressor
            model = RandomForestRegressor(n_estimators=100, random_state=seed,
                                          n_jobs=1)
        else:
            raise ValueError(estimator)
        model.fit(Xtr, y[tr])
        return model.predict(Xte)


def topk_recall(y_true, y_pred, k) -> float:
    if k > len(y_true):
        return float("nan")
    true_top = set(np.argsort(y_true)[::-1][:k])
    pred_top = set(np.argsort(y_pred)[::-1][:k])
    return len(true_top & pred_top) / k


def transfer_test(rows, emb, label, *, n_train=N_TRAIN, k=TOP_K) -> dict:
    from _selection import select_train_indices

    idx_by_target = collections.defaultdict(list)
    for i, r in enumerate(rows):
        idx_by_target[r["target_id"]].append(i)

    per_target = {}
    for target, idx in sorted(idx_by_target.items()):
        idx = np.array(idx)
        y = np.array([rows[i][label] for i in idx], dtype=float)
        # 판별이 원리적으로 불가능한 타겟은 뺀다 (모두 통과 / 모두 실패).
        if label in ("joint_pass", "structural_pass") and (y.min() == y.max()):
            per_target[target] = {"informative": False,
                                  "base_rate": float(y.mean()), "n": int(len(y))}
            continue
        X = emb[idx]
        sel, rnd, orc, rec = [], [], [], []
        for seed in SEEDS:
            tr = select_train_indices(X, n_train, seed, SELECTION_STRATEGY)
            te = np.setdiff1d(np.arange(len(idx)), tr)
            if len(te) < k:
                continue
            pred = fit_rank(X, y, tr, te, seed)
            top = np.argsort(pred)[::-1][:k]
            sel.append(float(y[te][top].mean()))
            rng = np.random.default_rng(seed)
            rnd.append(float(y[te][rng.choice(len(te), size=k, replace=False)].mean()))
            orc.append(float(np.sort(y[te])[::-1][:k].mean()))
            rec.append(topk_recall(y[te], pred, k))
        if not sel:
            per_target[target] = {"informative": False, "reason": "pool < K",
                                  "n": int(len(y))}
            continue
        per_target[target] = {
            "informative": True, "n": int(len(y)),
            "base_rate": float(y.mean()),
            "selected_topk": statistics.mean(sel),
            "random_topk": statistics.mean(rnd),
            "oracle_topk": statistics.mean(orc),
            "topk_recall": statistics.mean(rec),
        }

    info = {t: v for t, v in per_target.items() if v.get("informative")}
    rng = np.random.default_rng(BOOT_SEED)
    names = sorted(info)

    def boot(fn):
        pt = fn([info[t] for t in names])
        draws = sorted(fn([info[names[int(rng.integers(len(names)))]]
                           for _ in names]) for _ in range(N_BOOTSTRAP))
        lo = draws[int(0.025 * len(draws))]
        hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
        return {"point": pt, "ci95": [lo, hi]}

    mean = lambda vs, key: statistics.mean(v[key] for v in vs)
    return {
        "label": label, "n_train": n_train, "top_k": k,
        "n_targets": len(per_target), "n_informative": len(info),
        "informative_targets": names,
        "excluded_non_informative": sorted(t for t, v in per_target.items()
                                           if not v.get("informative")),
        "selected_topk": boot(lambda vs: mean(vs, "selected_topk")),
        "random_topk": boot(lambda vs: mean(vs, "random_topk")),
        "oracle_topk": boot(lambda vs: mean(vs, "oracle_topk")),
        "topk_recall": boot(lambda vs: mean(vs, "topk_recall")),
        "selected_minus_random": boot(
            lambda vs: mean(vs, "selected_topk") - mean(vs, "random_topk")),
        "per_target": per_target,
    }


# ------------------------------------------- B. 예산 일치 비교

def budget_matched(rows, emb, label, *, budgets=BUDGET_GRID,
                   n_train=N_TRAIN) -> dict:
    """총예산 B 에서 얻는 통과 후보 수. probe 의 수익도 센다.

    probe-then-triage 는 B < n_train 에서는 정의되지 않는다 (의무 probe 를
    채울 수 없다). 그 구간은 보고하지 않는다.
    """
    from _selection import select_train_indices

    idx_by_target = collections.defaultdict(list)
    for i, r in enumerate(rows):
        idx_by_target[r["target_id"]].append(i)

    per_target = {}
    for target, idx in sorted(idx_by_target.items()):
        idx = np.array(idx)
        y = np.array([rows[i][label] for i in idx], dtype=float)
        if y.min() == y.max():
            per_target[target] = {"informative": False,
                                  "base_rate": float(y.mean())}
            continue
        X = emb[idx]
        by_b = {}
        for B in budgets:
            if B < n_train:
                continue
            tri, ran, orc = [], [], []
            for seed in SEEDS:
                tr = select_train_indices(X, n_train, seed, SELECTION_STRATEGY)
                te = np.setdiff1d(np.arange(len(idx)), tr)
                extra = B - n_train
                if extra > len(te):
                    continue
                probe_yield = float(y[tr].sum())
                if extra > 0:
                    pred = fit_rank(X, y, tr, te, seed)
                    top = np.argsort(pred)[::-1][:extra]
                    tri.append(probe_yield + float(y[te][top].sum()))
                else:
                    tri.append(probe_yield)
                rng = np.random.default_rng(seed)
                ran.append(float(y[rng.choice(len(y), size=B, replace=False)].sum()))
                orc.append(float(np.sort(y)[::-1][:B].sum()))
            if tri:
                by_b[str(B)] = {"probe_then_triage": statistics.mean(tri),
                                "random_same_budget": statistics.mean(ran),
                                "oracle_same_budget": statistics.mean(orc)}
        per_target[target] = {"informative": True, "base_rate": float(y.mean()),
                              "by_budget": by_b}

    info = {t: v for t, v in per_target.items() if v.get("informative")}
    names = sorted(info)
    rng = np.random.default_rng(BOOT_SEED ^ 0xB0)
    out = {}
    for B in budgets:
        key = str(B)
        have = [t for t in names if key in info[t]["by_budget"]]
        if len(have) < 2:
            continue

        def diff(ts):
            return statistics.mean(
                info[t]["by_budget"][key]["probe_then_triage"]
                - info[t]["by_budget"][key]["random_same_budget"] for t in ts)

        draws = sorted(diff([have[int(rng.integers(len(have)))] for _ in have])
                       for _ in range(N_BOOTSTRAP))
        out[key] = {
            "n_targets": len(have),
            "probe_then_triage": statistics.mean(
                info[t]["by_budget"][key]["probe_then_triage"] for t in have),
            "random_same_budget": statistics.mean(
                info[t]["by_budget"][key]["random_same_budget"] for t in have),
            "oracle_same_budget": statistics.mean(
                info[t]["by_budget"][key]["oracle_same_budget"] for t in have),
            "difference": diff(have),
            "ci95": [draws[int(0.025 * len(draws))],
                     draws[min(len(draws) - 1, int(0.975 * len(draws)))]],
        }
    return {"label": label, "n_train": n_train, "n_informative": len(info),
            "by_budget": out, "per_target": per_target}


# ------------------------------------------- C. 실용 기준선 비교

def load_mpnn() -> dict[str, float]:
    """ProteinMPNN 점수. **라벨이 0 건 필요한 기준선**이다.

    산출물의 `definition` 이 "per-residue mean NLL ... Lower is better" 라고
    적고 있다. 따라서 선택은 오름차순이다. 내림차순으로 고르면 가장 나쁜 후보를
    뽑아 기준선이 무작위보다 낮게 나온다 - 실제로 한 번 그렇게 틀렸다.
    """
    raw = json.loads((GRID / "mpnn_scores.json").read_text(encoding="utf-8"))
    src = raw.get("scores", raw)
    return {k: float(v) for k, v in src.items()
            if isinstance(v, (int, float))}


def baselines_budget(rows, emb, label, mpnn, *, budgets=BUDGET_GRID,
                     n_train=N_TRAIN) -> dict:
    """같은 후보 풀·같은 총예산에서 실용 기준선들을 비교한다.

    질문은 "RF 가 최고인가" 가 아니라 **"추가 라벨 비용을 감수할 만한 선별
    이점이 있는가"** 다. 그래서 비대칭을 그대로 둔다::

        RF / Ridge     probe 30 건을 써야 한다 (라벨 비용 있음)
        MPNN 점수      라벨 0 건. 총예산 B 를 전부 선택에 쓸 수 있다
        무작위         라벨 0 건

    같은 B 에서 얻은 통과 후보 수로 비교하면 라벨 비용이 자동으로 회계에 들어
    간다. MPNN 기준선이 이기면 "싼 라벨 없는 점수로 충분하다" 는 뜻이고, 그것이
    이 비교의 요점이다.
    """
    from _selection import select_train_indices

    idx_by_target = collections.defaultdict(list)
    for i, r in enumerate(rows):
        idx_by_target[r["target_id"]].append(i)

    policies = ["rf_probe", "rf_probe_mpnnsel", "ridge_probe",
                "mpnn_score", "random", "oracle"]
    per_target = {}
    for target, idx in sorted(idx_by_target.items()):
        idx = np.array(idx)
        y = np.array([rows[i][label] for i in idx], dtype=float)
        if y.min() == y.max():
            per_target[target] = {"informative": False}
            continue
        X = emb[idx]
        m = np.array([mpnn.get(rows[i]["sequence_id"], np.nan) for i in idx])
        if np.isnan(m).any():
            per_target[target] = {"informative": False, "reason": "MPNN 점수 결측"}
            continue
        by_b = {}
        for B in budgets:
            got = {p: [] for p in policies}
            for seed in SEEDS:
                # 라벨 없는 정책: 총예산 B 를 전부 선택에 쓴다.
                # MPNN score 는 per-residue mean NLL 이고 **낮을수록 좋다**
                # (mpnn_scores.json 의 definition 필드). 오름차순으로 고른다.
                got["mpnn_score"].append(
                    float(y[np.argsort(m)[:B]].sum()))
                rng = np.random.default_rng(seed)
                got["random"].append(
                    float(y[rng.choice(len(y), size=B, replace=False)].sum()))
                got["oracle"].append(float(np.sort(y)[::-1][:B].sum()))
                # 라벨 쓰는 정책: probe 30 을 먼저 지출한다.
                if B < n_train:
                    continue
                # 초기 표본 선택 전략 두 가지를 나란히 본다.
                #   kmeans    원 프로토콜. 다양성 확보가 목적이다.
                #   mpnn_sel  MPNN score 상위 30. B=30 에서 k-means 가 무작위와
                #             구별되지 않았으므로 여기를 바꾸면 무엇이 달라지는지
                #             본다. 라벨이 좁은 점수대에 몰려 RF 가 나빠질 수도
                #             있으므로 **결과를 보기 전에는 개선이라고 가정하지
                #             않는다.**
                sel_sets = {"kmeans": select_train_indices(X, n_train, seed,
                                                           SELECTION_STRATEGY),
                            "mpnn_sel": np.argsort(m)[:n_train]}
                extra = B - n_train
                for pol, est, selname in (("rf_probe", "RF", "kmeans"),
                                          ("ridge_probe", "Ridge", "kmeans"),
                                          ("rf_probe_mpnnsel", "RF", "mpnn_sel")):
                    tr = sel_sets[selname]
                    te = np.setdiff1d(np.arange(len(idx)), tr)
                    if extra > len(te):
                        continue
                    base = float(y[tr].sum())
                    if extra == 0:
                        got[pol].append(base)
                        continue
                    pred = fit_rank(X, y, tr, te, seed, estimator=est)
                    top = np.argsort(pred)[::-1][:extra]
                    got[pol].append(base + float(y[te][top].sum()))
            by_b[str(B)] = {p: statistics.mean(v) for p, v in got.items() if v}
        per_target[target] = {"informative": True, "by_budget": by_b}

    info = {t: v for t, v in per_target.items() if v.get("informative")}
    names = sorted(info)
    rng = np.random.default_rng(BOOT_SEED ^ 0xBA5E)
    boots = [[names[int(rng.integers(len(names)))] for _ in names]
             for _ in range(N_BOOTSTRAP)]
    out = {}
    for B in budgets:
        key = str(B)
        have = [t for t in names if key in info[t]["by_budget"]
                and all(p in info[t]["by_budget"][key] for p in policies)]
        if len(have) < 2:
            continue

        def agg(ts, p):
            return statistics.mean(info[t]["by_budget"][key][p] for t in ts)

        entry = {"n_targets": len(have),
                 "point": {p: agg(have, p) for p in policies},
                 "paired_vs": {}}
        # 쌍대 차이. 같은 재표집 표본 안에서 계산한다.
        for a, b in (("rf_probe", "random"), ("rf_probe", "mpnn_score"),
                     ("rf_probe", "ridge_probe"), ("mpnn_score", "random"),
                     ("ridge_probe", "random"),
                     ("rf_probe_mpnnsel", "rf_probe"),
                     ("rf_probe_mpnnsel", "mpnn_score"),
                     ("rf_probe_mpnnsel", "random")):
            draws = sorted(agg(x, a) - agg(x, b) for x in boots)
            lo = draws[int(0.025 * len(draws))]
            hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
            entry["paired_vs"][f"{a}-{b}"] = {
                "delta": agg(have, a) - agg(have, b), "ci95": [lo, hi],
                "excludes_zero": bool(lo > 0 or hi < 0)}
        out[key] = entry
    return {"label": label, "policies": policies, "n_informative": len(info),
            "by_budget": out, "per_target": per_target,
            "asymmetry_note": ("MPNN 점수와 무작위는 라벨이 0 건 필요하고 RF/Ridge 는 "
                               "probe 30 건을 쓴다. 같은 총예산에서 비교하므로 그 "
                               "비용이 회계에 들어간다.")}


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esm-url", default="")
    ap.add_argument("--labels", default="joint_pass,structural_pass,plddt")
    ap.add_argument("--baselines", action="store_true",
                    help="C. 실용 기준선 비교 (RF/Ridge/MPNN 점수/무작위)")
    ap.add_argument("--out", default=str(OUT_DIR / "fewshot_jointpass_transfer.json"))
    args = ap.parse_args(argv)

    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    url = args.esm_url or (f"http://{host}:18170" if host else "")

    rows = load_grid()
    print(f"holdout 격자 RFD3 후보 {len(rows)} · 타겟 "
          f"{len({r['target_id'] for r in rows})}", flush=True)
    emb = embeddings_for(rows, url)
    if emb.shape[0] != len(rows):
        raise SystemExit(f"임베딩 {emb.shape[0]} != 후보 {len(rows)}")

    out = {
        "purpose": ("few-shot 국소 보정을 동결 종점(joint-pass)과 예산 일치 비교로 "
                    "다시 본다. 동결 v1/v2 판정을 바꾸지 않는 별도 평가축이다."),
        "protocol_source": ("scripts/benchmark/_selection.py::select_train_indices "
                            "(kmeans) + 02_model_comparison.py 의 RF 규격"),
        "embedding": "facebook/esm2_t6_8M_UR50D (320d) — CATH pilot 과 동일 모델",
        "thresholds": {"plddt_min": PLDDT_MIN, "rmsd_nonloop_order_max": RMSD_MAX,
                       "soluprot_min": SOLUPROT_MIN},
        "n_train": N_TRAIN, "top_k": TOP_K, "seeds": SEEDS,
        "bootstrap": {"n": N_BOOTSTRAP, "unit": "target", "seed": BOOT_SEED},
        "binary_metric_note": (
            "joint-pass 는 0/1 이라 Top-K recall 의 argsort 가 동점에서 임의 "
            "순서를 준다. 그래서 선택된 상위 K 안의 통과율을 쓴다."),
        "budget_note": (
            "probe 30 건은 실제 AF2 호출이므로 총예산에 포함하고, probe 가 찾은 "
            "통과 후보도 수익에 센다. 기존 few-shot 비교는 이 회계를 하지 않았다."),
        "transfer": {}, "budget_matched": {},
    }

    for label in [s.strip() for s in args.labels.split(",") if s.strip()]:
        print(f"\n[A] 전이 시험 · label={label}", flush=True)
        out["transfer"][label] = transfer_test(rows, emb, label)
        t = out["transfer"][label]
        print(f"  informative 타겟 {t['n_informative']}/{t['n_targets']} "
              f"(제외 {t['excluded_non_informative']})")
        print(f"  선택 상위{TOP_K}  {t['selected_topk']['point']:.4f} "
              f"[{t['selected_topk']['ci95'][0]:.4f}, {t['selected_topk']['ci95'][1]:.4f}]")
        print(f"  무작위 상위{TOP_K} {t['random_topk']['point']:.4f} "
              f"[{t['random_topk']['ci95'][0]:.4f}, {t['random_topk']['ci95'][1]:.4f}]")
        print(f"  oracle        {t['oracle_topk']['point']:.4f}")
        d = t["selected_minus_random"]
        print(f"  차이          {d['point']:+.4f} [{d['ci95'][0]:+.4f}, "
              f"{d['ci95'][1]:+.4f}]  {'0 제외' if d['ci95'][0] > 0 or d['ci95'][1] < 0 else '0 포함'}")
        print(f"  Top-{TOP_K} recall {t['topk_recall']['point']:.4f}")

        print(f"\n[B] 예산 일치 비교 · label={label}", flush=True)
        out["budget_matched"][label] = budget_matched(rows, emb, label)
        b = out["budget_matched"][label]["by_budget"]
        print(f"  {'B':>5} {'probe+triage':>13} {'무작위 B':>10} {'oracle':>8} "
              f"{'차이':>9}  95% CI")
        for B, v in b.items():
            mark = "0 제외" if v["ci95"][0] > 0 or v["ci95"][1] < 0 else "0 포함"
            print(f"  {B:>5} {v['probe_then_triage']:13.2f} "
                  f"{v['random_same_budget']:10.2f} {v['oracle_same_budget']:8.2f} "
                  f"{v['difference']:+9.2f}  [{v['ci95'][0]:+.2f}, "
                  f"{v['ci95'][1]:+.2f}] {mark}")

    if args.baselines:
        mpnn = load_mpnn()
        lab = "joint_pass"
        print(f"\n[C] 실용 기준선 비교 · label={lab} (MPNN 점수는 라벨 0 건)",
              flush=True)
        out["baselines"] = baselines_budget(rows, emb, lab, mpnn)
        bb = out["baselines"]["by_budget"]
        pols = out["baselines"]["policies"]
        print("  " + f"{'B':>5}" + "".join(f"{p:>13}" for p in pols))
        for B, v in bb.items():
            print("  " + f"{B:>5}" + "".join(f"{v['point'][p]:13.2f}" for p in pols))
        print("\n  쌍대 차이 (같은 재표집 표본)")
        for B in ("40", "60", "80", "100"):
            if B not in bb:
                continue
            print(f"   B={B}")
            for k, s in bb[B]["paired_vs"].items():
                mark = "0 제외" if s["excludes_zero"] else "0 포함 → 구별 안 됨"
                print(f"     {k:26s} {s['delta']:+7.2f} "
                      f"[{s['ci95'][0]:+6.2f}, {s['ci95'][1]:+6.2f}]  {mark}")

    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"\n{args.out}")
    print("sha256", hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
