#!/usr/bin/env python3
"""게이트 0 baseline 사다리 (설계 6.1b, 게이트 G0a).

  A. source mean          — 백본 소스 평균만
  B. structural descriptors — CA 좌표 기반 기술자
  C. raw MPNN encoder     — 희소화 없는 인코더 풀링 (특징 파일 필요)
  D. encoder + descriptors — C + B

평가 설계상 주의: CATH 타겟은 백본이 하나뿐이라 fold 내부 상관을 잴 수 없다.
그래서 **grouped K-fold 의 out-of-fold 예측을 모아** 전체 백본에서 지표를 낸다.
라벨이 k/n 이므로 head 는 n 을 시행 수로 쓰는 binomial(로지스틱) 회귀다.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.descriptors import DESCRIPTOR_NAMES, ca_coords, descriptors  # noqa: E402

TARGET_COLUMN = "af2_structural_pass_yield"


def load_table(labels_csv: Path) -> list[dict]:
    with open(labels_csv, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_descriptor_matrix(rows: list[dict], pdb_dir: Path) -> np.ndarray:
    out = []
    for row in rows:
        coords = ca_coords((pdb_dir / row["pdb_file"]).read_text(encoding="utf-8", errors="replace"))
        d = descriptors(coords)
        out.append([d[name] for name in DESCRIPTOR_NAMES])
    return np.asarray(out, dtype=float)


def grouped_folds(groups: np.ndarray, *, n_splits: int, seed: int):
    uniq = np.array(sorted(set(groups)))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(uniq))
    for fold in range(n_splits):
        held = {uniq[int(i)] for j, i in enumerate(order) if j % n_splits == fold}
        test = np.array([g in held for g in groups])
        if test.sum() == 0 or (~test).sum() < 5:
            continue
        yield test


def fit_predict(x_train, y_train, w_train, x_test, *, kind: str):
    """binomial head. baseline A 는 소스별 평균이라 별도 처리한다."""
    from sklearn.linear_model import LogisticRegression

    if kind == "group_mean":
        # x 는 소스 one-hot. 각 테스트 행에 대해 같은 소스의 학습 평균을 준다.
        # (전역 평균을 쓰면 예측이 상수가 되어 Spearman 이 정의되지 않는다.)
        overall = float(np.average(y_train, weights=w_train))
        preds = np.full(x_test.shape[0], overall)
        for col in range(x_train.shape[1]):
            tr = x_train[:, col] > 0
            te = x_test[:, col] > 0
            if tr.sum() >= 2 and te.any():
                preds[te] = float(np.average(y_train[tr], weights=w_train[tr]))
        return preds

    mu, sd = x_train.mean(0), x_train.std(0)
    sd[sd == 0] = 1.0
    xtr, xte = (x_train - mu) / sd, (x_test - mu) / sd

    # k/n 라벨을 성공/실패 두 행으로 펼쳐 binomial 로 학습한다.
    successes = np.rint(y_train * w_train).astype(int)
    failures = np.rint(w_train).astype(int) - successes
    xs = np.vstack([xtr, xtr])
    ys = np.concatenate([np.ones(len(xtr)), np.zeros(len(xtr))])
    ws = np.concatenate([successes, failures]).astype(float)
    keep = ws > 0
    if len(set(ys[keep])) < 2:
        return np.full(x_test.shape[0], float(np.average(y_train, weights=w_train)))
    model = LogisticRegression(max_iter=2000, C=1.0)
    model.fit(xs[keep], ys[keep], sample_weight=ws[keep])
    return model.predict_proba(xte)[:, 1]


def paired_difference(per_repeat_a, per_repeat_b, *, seed=0):
    """같은 split 에서 잰 두 arm 의 차이에 대한 부트스트랩 CI.

    "각자의 CI 가 안 겹친다"는 우월성의 증거로 약하다. 같은 fold 에서 짝지어
    차이를 재야 split 변동이 상쇄된다.
    """
    a = np.asarray(per_repeat_a, dtype=float)
    b = np.asarray(per_repeat_b, dtype=float)
    n = min(a.size, b.size)
    if n < 3:
        return None
    diff = a[:n] - b[:n]
    rng = np.random.default_rng(seed)
    boot = [rng.choice(diff, diff.size, replace=True).mean() for _ in range(4000)]
    low, high = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
    return {
        "mean_difference": round(float(diff.mean()), 4),
        "ci95": [round(low, 4), round(high, 4)],
        "excludes_zero": bool(low > 0 or high < 0),
        "n_paired_repeats": int(n),
    }


def evaluate(X, y, w, groups, sources, *, kind, n_splits=5, n_repeats=10, seed=0):
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score

    preds = np.zeros((n_repeats, len(y)))
    counts = np.zeros((n_repeats, len(y)))
    for rep in range(n_repeats):
        for test in grouped_folds(groups, n_splits=n_splits, seed=seed + rep):
            p = fit_predict(X[~test], y[~test], w[~test], X[test], kind=kind)
            preds[rep, test] = p
            counts[rep, test] = 1
    valid = counts.sum(0) > 0
    mean_pred = np.divide(preds.sum(0), np.maximum(counts.sum(0), 1))

    rhos, aucs = [], []
    binary = (y >= 0.5).astype(int)
    for rep in range(n_repeats):
        m = counts[rep] > 0
        if m.sum() < 10:
            continue
        rho = spearmanr(y[m], preds[rep][m]).statistic
        if rho == rho:
            rhos.append(float(rho))
        if len(set(binary[m])) == 2:
            aucs.append(float(roc_auc_score(binary[m], preds[rep][m])))

    def ci(values):
        if not values:
            return None
        rng = np.random.default_rng(seed)
        arr = np.asarray(values)
        boot = [rng.choice(arr, arr.size, replace=True).mean() for _ in range(2000)]
        return [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)]

    return {
        "n_backbones": int(valid.sum()),
        "per_repeat_spearman": [round(v, 4) for v in rhos],
        "per_repeat_auc": [round(v, 4) for v in aucs],
        "spearman": round(float(np.mean(rhos)), 4) if rhos else None,
        "spearman_ci95": ci(rhos),
        "auc": round(float(np.mean(aucs)), 4) if aucs else None,
        "auc_ci95": ci(aucs),
        "mae": round(float(np.abs(mean_pred[valid] - y[valid]).mean()), 4),
        "n_repeats": n_repeats,
    }


def leave_one_source_out(X, y, w, sources, *, kind):
    from scipy.stats import spearmanr
    out = {}
    for src in sorted(set(sources)):
        test = sources == src
        if test.sum() < 5 or (~test).sum() < 10:
            out[src] = {"skipped": True, "n_test": int(test.sum())}
            continue
        p = fit_predict(X[~test], y[~test], w[~test], X[test], kind=kind)
        rho = spearmanr(y[test], p).statistic
        out[src] = {"n_test": int(test.sum()),
                    "spearman": None if rho != rho else round(float(rho), 4)}
    return out


def cross_source_matrix(X, y, w, groups, sources, *, kind, seed=0):
    """소스별 within / cross 전이 행렬 (게이트 G0b).

    "MPNN 인코더가 source-independent 한 백본 품질을 배웠는가"가 질문이다.
    within-source 는 타겟 group split 으로, cross-source 는 한 소스를 통째로
    학습해 다른 소스에서 평가한다.
    """
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score

    uniq = sorted(set(sources))
    out: dict[str, dict] = {}
    for train_src in uniq:
        for test_src in uniq:
            train = sources == train_src
            test = sources == test_src
            key = f"{train_src}->{test_src}"
            if train_src == test_src:
                # 같은 소스 안에서는 타겟 그룹으로 나눠야 누출이 없다.
                if train.sum() < 20:
                    out[key] = {"skipped": "n<20", "n": int(train.sum())}
                    continue
                res = evaluate(X[train], y[train], w[train], groups[train],
                               sources[train], kind=kind, n_repeats=10, seed=seed)
                out[key] = {"n_train": int(train.sum()), "n_test": int(train.sum()),
                            "spearman": res["spearman"], "auc": res["auc"],
                            "mode": "grouped_cv"}
                continue
            if train.sum() < 20 or test.sum() < 8:
                out[key] = {"skipped": "too few", "n_train": int(train.sum()),
                            "n_test": int(test.sum())}
                continue
            pred = fit_predict(X[train], y[train], w[train], X[test], kind=kind)
            truth = y[test]
            rho = spearmanr(truth, pred).statistic if len(set(truth)) > 1 else float("nan")
            binary = (truth >= 0.5).astype(int)
            auc = (float(roc_auc_score(binary, pred))
                   if len(set(binary)) == 2 else None)
            out[key] = {
                "n_train": int(train.sum()), "n_test": int(test.sum()),
                "spearman": None if rho != rho else round(float(rho), 4),
                "auc": round(auc, 4) if auc is not None else None,
                "mode": "transfer",
            }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "backbones"
    parser.add_argument("--labels", default=str(base / "backbone_labels.csv"))
    parser.add_argument("--pdb-dir", default=str(base / "pdb"))
    parser.add_argument("--encoder-features", default="")
    parser.add_argument("--n-repeats", type=int, default=10)
    parser.add_argument("--out", default=str(base.parent / "gate0_ladder.json"))
    args = parser.parse_args(argv)

    rows = load_table(Path(args.labels))
    y = np.array([float(r[TARGET_COLUMN]) for r in rows])
    w = np.array([float(r["n_sequences_with_af2"]) for r in rows])
    groups = np.array([r["target_id"] for r in rows])
    sources = np.array([r["backbone_source"] for r in rows])

    desc = build_descriptor_matrix(rows, Path(args.pdb_dir))
    source_onehot = np.stack([(sources == s).astype(float) for s in sorted(set(sources))], axis=1)

    arms = {
        "A_source_mean": (source_onehot, "group_mean"),
        "B_structural_descriptors": (desc, "binomial"),
    }
    if args.encoder_features:
        enc = np.load(args.encoder_features)
        assert enc.shape[0] == len(rows), (enc.shape, len(rows))
        alive = (enc != 0).any(0) & (enc.std(0) > 0)
        enc = enc[:, alive]
        arms["C_raw_mpnn_encoder"] = (enc, "binomial")
        arms["D_encoder_plus_descriptors"] = (np.hstack([enc, desc]), "binomial")

    report = {
        "target": TARGET_COLUMN, "n_backbones": len(rows),
        "n_targets": int(len(set(groups))),
        "by_source": {s: int((sources == s).sum()) for s in sorted(set(sources))},
        "protocol": "repeated grouped 5-fold by target_id, out-of-fold predictions, binomial head weighted by n",
        "arms": {},
    }
    # 소스가 프로토콜과 얽혀 있으므로(캠페인 rfd3 는 타겟 3개뿐) 소스 내부 평가를
    # 함께 낸다. 가장 큰 단일 소스만 남기면 소스 교란이 사라진다.
    main_source = max(set(sources), key=lambda s: (sources == s).sum())
    within = sources == main_source
    print(f"within-source 평가 기준: {main_source} (n={int(within.sum())})\n")

    for name, (X, kind) in arms.items():
        res = evaluate(X, y, w, groups, sources, kind=kind, n_repeats=args.n_repeats)
        res["loso"] = leave_one_source_out(X, y, w, sources, kind=kind)
        res["feature_dim"] = int(X.shape[1])
        if name != "A_source_mean" and within.sum() >= 20:
            res["within_source"] = evaluate(
                X[within], y[within], w[within], groups[within], sources[within],
                kind=kind, n_repeats=args.n_repeats,
            )
            res["within_source"]["source"] = main_source
        report["arms"][name] = res
        ws = res.get("within_source")
        extra = (f" | within-{main_source}: rho={ws['spearman']} auc={ws['auc']}"
                 if ws else "")
        print(f"{name:28s} dim={X.shape[1]:5d} rho={res['spearman']} CI{res['spearman_ci95']} "
              f"auc={res['auc']} CI{res['auc_ci95']} mae={res['mae']}{extra}", flush=True)

    if len(set(sources)) >= 2:
        print("\n=== cross-source 전이 (G0b) ===")
        report["cross_source"] = {}
        for name, (X, kind) in arms.items():
            if name == "A_source_mean":
                continue
            matrix = cross_source_matrix(X, y, w, groups, sources, kind=kind)
            report["cross_source"][name] = matrix
            print(f"  {name}")
            for key, res in matrix.items():
                if res.get("skipped"):
                    print(f"    {key:22s} skip ({res['skipped']})")
                else:
                    print(f"    {key:22s} rho={res['spearman']} auc={res['auc']} "
                          f"({res['mode']}, n_test={res['n_test']})")

    # 같은 split 에서 짝지은 차이. 각자 CI 비교보다 강한 근거다.
    if "C_raw_mpnn_encoder" in report["arms"]:
        report["paired_differences"] = {}
        c = report["arms"]["C_raw_mpnn_encoder"]
        print()
        for other in ("A_source_mean", "B_structural_descriptors", "D_encoder_plus_descriptors"):
            if other not in report["arms"]:
                continue
            o = report["arms"][other]
            entry = {
                "spearman": paired_difference(c["per_repeat_spearman"], o["per_repeat_spearman"]),
                "auc": paired_difference(c["per_repeat_auc"], o["per_repeat_auc"]),
            }
            report["paired_differences"][f"C_minus_{other}"] = entry
            for metric, res in entry.items():
                if res:
                    mark = "유의" if res["excludes_zero"] else "불확실"
                    print(f"  paired C - {other:26s} {metric:8s} "
                          f"diff={res['mean_difference']:+.4f} CI{res['ci95']} [{mark}]")

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
