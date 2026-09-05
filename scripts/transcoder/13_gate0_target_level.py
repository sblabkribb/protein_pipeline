#!/usr/bin/env python3
"""게이트 0 을 타겟 수준으로 재정의해 평가한다.

왜 바꾸는가. 백본 수준으로 재려 했지만 데이터 구조가 그것을 허용하지 않았다.

  - native 백본은 타겟당 1개다. 그래서 "백본 고르기" 가 곧 "타겟 고르기" 였다.
  - RFD3 는 타겟당 5개지만 타겟 내부 yield sd 가 0.044 이고 16 타겟 중 7개는
    5개가 전부 같은 값이다. 고를 것이 거의 없다.
  - 타겟 내부 순위 예측은 실패했다(rfd3 rho -0.257).

따라서 게이트 0 의 질문을 **"이 타겟에 설계·AF2 예산을 투자할 것인가"** 로 정의한다.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.descriptors import DESCRIPTOR_NAMES, ca_coords, descriptors  # noqa: E402


def aggregate_to_target(rows: list[dict], features: np.ndarray) -> dict:
    """백본을 타겟 단위로 합친다.

    라벨은 그 타겟의 백본들이 만든 설계 전체의 통과 비율이다(백본 평균이 아니라
    설계 수로 가중해야 백본마다 서열 수가 다른 것이 반영된다).
    특징은 그 타겟 백본들의 평균 표현이다.
    """
    by_target: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_target[row["target_id"]].append(index)

    targets, y, w, feats, sources = [], [], [], [], []
    for target, indices in sorted(by_target.items()):
        passes = 0.0
        total = 0.0
        for i in indices:
            n = float(rows[i]["n_sequences_with_af2"] or 0)
            yv = rows[i]["af2_structural_pass_yield"]
            if not n or yv in (None, "", "None"):
                continue
            passes += float(yv) * n
            total += n
        if total <= 0:
            continue
        targets.append(target)
        y.append(passes / total)
        w.append(total)
        feats.append(features[indices].mean(axis=0))
        srcs = sorted({rows[i]["backbone_source"] for i in indices})
        sources.append("+".join(srcs))
    return {
        "targets": targets, "y": np.asarray(y), "w": np.asarray(w),
        "X": np.vstack(feats), "sources": np.asarray(sources),
    }


def evaluate_target_level(X, y, w, *, kind="binomial", n_splits=5, n_repeats=20, seed=0,
                          collect_oof=False):
    """타겟 단위 반복 K-fold. 타겟이 곧 그룹이므로 별도 group 처리가 필요 없다.

    `collect_oof=True` 면 반복별 out-of-fold 예측을 함께 돌려준다. 그 예측은 해당
    타겟의 라벨을 보지 않고 만들어진 것이므로, 예산 배분 시뮬레이션의 대리모형
    으로 그대로 쓸 수 있다 - 합성 AUC 를 가정하지 않아도 된다.
    """
    from scipy.stats import spearmanr
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    n = len(y)
    binary = (y >= 0.5).astype(int)
    rhos, aucs = [], []
    oof_repeats: list[list[float]] = []
    for rep in range(n_repeats):
        rng = np.random.default_rng(seed + rep)
        order = rng.permutation(n)
        preds = np.zeros(n)
        for fold in range(n_splits):
            test = np.zeros(n, dtype=bool)
            test[order[fold::n_splits]] = True
            if test.sum() < 2 or (~test).sum() < 10:
                continue
            if kind == "constant":
                preds[test] = float(np.average(y[~test], weights=w[~test]))
                continue
            tr = X[~test]
            mu, sd = tr.mean(0), tr.std(0)
            sd[sd == 0] = 1.0
            succ = np.rint(y[~test] * w[~test]).astype(int)
            fail = np.rint(w[~test]).astype(int) - succ
            xs = np.vstack([(tr - mu) / sd] * 2)
            ys = np.r_[np.ones(tr.shape[0]), np.zeros(tr.shape[0])]
            ws = np.r_[succ, fail].astype(float)
            keep = ws > 0
            if len(set(ys[keep])) < 2:
                preds[test] = float(np.average(y[~test], weights=w[~test]))
                continue
            model = LogisticRegression(max_iter=2000)
            model.fit(xs[keep], ys[keep], sample_weight=ws[keep])
            preds[test] = model.predict_proba((X[test] - mu) / sd)[:, 1]
        rho = spearmanr(y, preds).statistic
        if rho == rho:
            rhos.append(float(rho))
        if len(set(binary)) == 2:
            aucs.append(float(roc_auc_score(binary, preds)))
        if collect_oof:
            oof_repeats.append([float(v) for v in preds])

    def ci(values):
        if not values:
            return None
        arr = np.asarray(values)
        rng = np.random.default_rng(seed)
        boot = [rng.choice(arr, arr.size, replace=True).mean() for _ in range(3000)]
        return [round(float(np.percentile(boot, 2.5)), 4),
                round(float(np.percentile(boot, 97.5)), 4)]

    out = {
        "n_targets": int(n),
        "spearman": round(float(np.mean(rhos)), 4) if rhos else None,
        "spearman_ci95": ci(rhos), "per_repeat_spearman": rhos,
        "auc": round(float(np.mean(aucs)), 4) if aucs else None,
        "auc_ci95": ci(aucs), "per_repeat_auc": aucs,
    }
    if collect_oof and oof_repeats:
        # 반복 평균. 한 반복의 예측만 쓰면 폴드 분할 하나에 결과가 좌우된다.
        out["oof_mean"] = [round(float(v), 6) for v in np.mean(oof_repeats, axis=0)]
        out["oof_n_repeats"] = len(oof_repeats)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
    parser.add_argument("--labels", default=str(base / "backbones" / "backbone_labels.csv"))
    parser.add_argument("--pdb-dir", default=str(base / "backbones" / "pdb"))
    parser.add_argument("--encoder-features", default=str(base / "backbones" / "mpnn_encoder.npy"))
    parser.add_argument("--out", default=str(base / "gate0_target_level.json"))
    parser.add_argument("--export-oof", default="",
                        help="C 팔의 out-of-fold 타겟 예측을 이 JSON 으로 내보낸다. "
                             "예산 배분 시뮬레이션의 대리모형으로 쓴다.")
    args = parser.parse_args(argv)

    with open(args.labels, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    encoder = np.load(args.encoder_features)
    desc = np.asarray([
        [descriptors(ca_coords((Path(args.pdb_dir) / r["pdb_file"]).read_text(
            encoding="utf-8", errors="replace")))[k] for k in DESCRIPTOR_NAMES]
        for r in rows
    ])

    report = {"routing_unit": "target", "n_backbones": len(rows), "arms": {}}
    arms = {
        "A_global_mean": (np.ones((len(rows), 1)), "constant"),
        "B_structural_descriptors": (desc, "binomial"),
        "C_raw_mpnn_encoder": (encoder, "binomial"),
    }
    print(f"{'arm':30s} {'targets':>8s} {'rho':>8s} {'CI95':>19s} {'AUC':>7s} {'CI95':>19s}")
    for name, (features, kind) in arms.items():
        agg = aggregate_to_target(rows, features)
        X = agg["X"]
        alive = (X != 0).any(0) & (X.std(0) > 0)
        if alive.sum():
            X = X[:, alive]
        res = evaluate_target_level(
            X, agg["y"], agg["w"], kind=kind,
            collect_oof=bool(args.export_oof) and name == "C_raw_mpnn_encoder",
        )
        res["feature_dim"] = int(X.shape[1])
        if res.get("oof_mean"):
            oof_export = {
                "arm": name,
                "auc": res["auc"], "auc_ci95": res["auc_ci95"],
                "n_repeats": res["oof_n_repeats"],
                "note": ("각 타겟의 예측은 그 타겟이 테스트 폴드에 있을 때 만들어진 것이다. "
                         "따라서 이 점수를 대리모형으로 쓰면 해당 타겟의 라벨을 보지 않은 "
                         "예측을 쓰는 것이 된다."),
                "scores": {
                    target: score for target, score in zip(agg["targets"], res["oof_mean"])
                },
            }
        # 예측 벡터는 리포트를 크게 만들 뿐이라 별도 파일로만 내보낸다.
        res.pop("oof_mean", None)
        report["arms"][name] = res
        report.setdefault("n_targets", res["n_targets"])
        print(f"{name:30s} {res['n_targets']:>8d} {str(res['spearman']):>8s} "
              f"{str(res['spearman_ci95']):>19s} {str(res['auc']):>7s} {str(res['auc_ci95']):>19s}")

    c = report["arms"].get("C_raw_mpnn_encoder")
    if c:
        print()
        for other in ("A_global_mean", "B_structural_descriptors"):
            o = report["arms"].get(other)
            if not o:
                continue
            for metric in ("spearman", "auc"):
                a = np.asarray(c[f"per_repeat_{metric}"], dtype=float)
                b = np.asarray(o[f"per_repeat_{metric}"], dtype=float)
                k = min(a.size, b.size)
                if k < 3:
                    continue
                diff = a[:k] - b[:k]
                rng = np.random.default_rng(0)
                boot = [rng.choice(diff, diff.size, replace=True).mean() for _ in range(4000)]
                low, high = np.percentile(boot, [2.5, 97.5])
                mark = "유의" if (low > 0 or high < 0) else "불확실"
                report.setdefault("paired", {})[f"C_minus_{other}_{metric}"] = {
                    "mean_difference": round(float(diff.mean()), 4),
                    "ci95": [round(float(low), 4), round(float(high), 4)],
                    "excludes_zero": bool(low > 0 or high < 0),
                }
                print(f"  paired C - {other:26s} {metric:8s} diff={diff.mean():+.4f} "
                      f"CI[{low:+.4f}, {high:+.4f}] [{mark}]")

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    if args.export_oof:
        Path(args.export_oof).write_text(
            json.dumps(oof_export, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.export_oof} ({len(oof_export['scores'])} targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
