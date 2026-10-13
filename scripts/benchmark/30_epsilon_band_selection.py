#!/usr/bin/env python3
"""ε-band 선택 규칙의 offline replay. **새 AF2 호출 0 회.**

무엇을 바꾸자는 것인가
----------------------
현행 surrogate 는 `joint-pass` 를 예측한다. 그런데 holdout 격자에서
structural-pass 1,107 건 중 **99.0% 가 SoluProt >= 0.5 를 자동으로 통과**하므로
joint-pass 는 사실상 structural-pass 와 같고, SoluProt 문턱은 거의 아무것도
거르지 않는다. 동시에 0.5 위로 폭이 남아 있다 (중앙 0.719, 최대 0.921).
문턱이 버리는 정보가 거기 있다.

그리고 **SoluProt 은 예측 대상이 아니다.** 서열의 결정론적 함수이고 파이프라인이
이미 전 후보에 계산한다. 비싸고 아직 모르는 것은 `P(structural pass)` 뿐이다.

그래서 선택 규칙을 이렇게 바꾼다::

    1. P̂(structural pass) 로 구조적으로 유망한 후보를 고른다
    2. best P̂ - ε 안에 드는 후보들 안에서만
       ΔSoluProt = SoluProt(candidate) - SoluProt(WT) 내림차순 정렬

정확한 동률 tie-break 는 연속 점수에서 거의 발동하지 않으므로 쓰지 않는다.
ε-band 는 "구조 성공률을 희생하지 않는 범위에서 더 높은 predicted solubility 를
선호했다" 는 진술을 가능하게 해 Goodhart 위험을 줄인다.

측정
----
백본 하나 안에서 Top-K 를 고르고 두 가지를 같이 본다::

    structural-pass recovery   유지되는가 (희생 없음을 보이는 축)
    선택된 후보의 ΔSoluProt    올라가는가 (이득을 보이는 축)

하지 않는 것
------------
- 동결된 v1/v2 판정을 바꾸지 않는다. 새 선택 규칙의 별도 평가축이다.
- "용해도를 개선했다" 고 주장하지 않는다. SoluProt 은 예측 proxy 다.
- P̂ 가 좋다고 가정하지 않는다 - Gate 2 가 이미 서열 수준 선택을 NO-GO 로
  판정했으므로, P̂ 만 쓰는 정책이 무작위와 비슷해도 놀랄 일이 아니다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import statistics
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "benchmark"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID = GATE0 / "holdout_grid"

PLDDT_MIN, RMSD_MAX = 85.0, 2.0
SEED = 20260915


def load_rows() -> list[dict]:
    wt = json.loads((GRID / "wt_soluprot.json").read_text(encoding="utf-8"))
    out = []
    for r in csv.DictReader((GRID / "af2_order_metric.csv").open(encoding="utf-8")):
        if r.get("status") != "ok" or r.get("backbone_source") != "rfd3":
            continue
        try:
            pl, rm, so = (float(r["plddt"]), float(r["rmsd_nonloop_order"]),
                          float(r["soluprot"]))
        except (TypeError, ValueError, KeyError):
            continue
        t = r["target_id"]
        if t not in wt:
            continue
        out.append({
            "sequence_id": r["sequence_id"], "backbone_key": r["backbone_key"],
            "target_id": t,
            "structural_pass": int(pl >= PLDDT_MIN and rm <= RMSD_MAX),
            "soluprot": so, "delta_soluprot": so - wt[t],
        })
    return out


def fit_loto_pstruct(rows: list[dict]) -> dict[str, float]:
    """LOTO 로 P̂(structural pass). Gate 2 와 같은 싼 특징을 쓴다.

    이 값이 약할 것은 미리 안다 - Gate 2 가 같은 축에서 NO-GO 였다. 그래도
    실제 시스템이 쓸 수 있는 예측을 그대로 넣어야 정책 비교가 정직해진다.
    oracle 을 P̂ 로 쓰면 규칙이 아니라 정답을 평가하게 된다.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    mp = json.loads((GRID / "mpnn_scores.json").read_text(encoding="utf-8"))
    mp = mp.get("scores", mp) if isinstance(mp, dict) else mp
    msa = json.loads((GRID / "msa_features.json").read_text(encoding="utf-8"))
    cons = msa.get("targets", msa) if isinstance(msa, dict) else {}

    def feat(r):
        s = mp.get(r["sequence_id"])
        if isinstance(s, dict):
            s = s.get("score") or s.get("global_score")
        c = cons.get(r["target_id"]) or {}
        q = (c.get("quality_medians") or {}) if isinstance(c, dict) else {}
        return [float(s) if s is not None else 0.0,
                float(q.get("median_coverage") or 0.0),
                float(q.get("median_depth") or 0.0),
                float(len(r["sequence_id"]))]

    X = np.array([feat(r) for r in rows], dtype=float)
    y = np.array([r["structural_pass"] for r in rows], dtype=int)
    tg = np.array([r["target_id"] for r in rows])
    pred = {}
    for t in sorted(set(tg)):
        tr, te = tg != t, tg == t
        if len(set(y[tr])) < 2:
            for r, _ in zip([r for r, m in zip(rows, te) if m], range(10**9)):
                pred[r["sequence_id"]] = float(y[tr].mean())
            continue
        sc = StandardScaler().fit(X[tr])
        m = LogisticRegression(max_iter=5000).fit(sc.transform(X[tr]), y[tr])
        p = m.predict_proba(sc.transform(X[te]))[:, 1]
        for r, v in zip([r for r, mm in zip(rows, te) if mm], p):
            pred[r["sequence_id"]] = float(v)
    return pred


def select(cands, k, policy, pstruct, eps, rng):
    if policy == "random":
        idx = rng.permutation(len(cands))[:k]
        return [cands[i] for i in idx]
    if policy == "pstruct":
        return sorted(cands, key=lambda r: -pstruct[r["sequence_id"]])[:k]
    if policy == "delta_soluprot":
        return sorted(cands, key=lambda r: -r["delta_soluprot"])[:k]
    if policy == "product":
        return sorted(cands, key=lambda r: -(pstruct[r["sequence_id"]]
                                             * max(r["delta_soluprot"], 0.0)))[:k]
    if policy == "eps_band":
        best = max(pstruct[r["sequence_id"]] for r in cands)
        band = [r for r in cands if pstruct[r["sequence_id"]] >= best - eps]
        band.sort(key=lambda r: -r["delta_soluprot"])
        if len(band) >= k:
            return band[:k]
        rest = sorted((r for r in cands if r not in band),
                      key=lambda r: -pstruct[r["sequence_id"]])
        return band + rest[: k - len(band)]
    if policy == "oracle":
        return sorted(cands, key=lambda r: (-r["structural_pass"],
                                            -r["delta_soluprot"]))[:k]
    raise ValueError(policy)


def _paired_bootstrap(per_target: dict, policies: list[str], n_boot: int,
                      seed: int) -> dict:
    """타겟을 재표집해 정책별 점추정과 정책 간 **짝지은** 차이의 CI 를 낸다.

    왜 짝을 짓는가: 모든 정책이 **같은 12 개 타겟** 위에서 평가된다. 정책별
    CI 를 따로 내서 겹치는지 보는 것은 짝지은 차이의 검정보다 보수적이고,
    타겟 난이도라는 공통 변동을 제거하지 못한다. 재표집 단위는 타겟이다 -
    같은 타겟의 백본들은 독립이 아니다.

    왜 두 개의 기준을 쓰는가: `random` 대비는 "싼 신호로 고르는 것이 무작위
    선택보다 나은가" 이고, `delta_soluprot` 대비는 "ε-band 라는 더 복잡한
    규칙이 가장 단순한 규칙보다 나은가" 다. 후자가 ε-band 를 도입할 이유를
    직접 묻는 비교이므로 따로 적는다.

    n=12 타겟이므로 구간은 넓다. 그 폭이 결과다 - 좁혀 보이게 만들지 않는다.
    """
    import random as _random
    targets = list(per_target)
    rng = _random.Random(seed)

    def means(ts: list[str]) -> dict[str, tuple[float, float]]:
        out = {}
        for pol in policies:
            sp = [statistics.mean(x[0] for x in per_target[t][pol]) for t in ts]
            ds = [statistics.mean(x[1] for x in per_target[t][pol]) for t in ts]
            out[pol] = (statistics.mean(sp), statistics.mean(ds))
        return out

    point = means(targets)
    draws: list[dict[str, tuple[float, float]]] = []
    for _ in range(n_boot):
        pick = [targets[rng.randrange(len(targets))] for _ in targets]
        draws.append(means(pick))

    def pct(vals: list[float], q: float) -> float:
        v = sorted(vals)
        i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
        return v[i]

    out: dict = {"n_bootstrap": n_boot, "n_targets": len(targets),
                 "resample_unit": "target", "interval": "percentile 95%",
                 "per_policy": {}, "paired_vs": {}}
    for pol in policies:
        for j, metric in enumerate(("structural_pass_rate", "delta_soluprot")):
            vals = [d[pol][j] for d in draws]
            out["per_policy"].setdefault(pol, {})[metric] = {
                "point": point[pol][j],
                "ci95": [pct(vals, 0.025), pct(vals, 0.975)]}
    for ref in ("random", "delta_soluprot"):
        for pol in policies:
            if pol == ref:
                continue
            entry = {}
            for j, metric in enumerate(("structural_pass_rate", "delta_soluprot")):
                vals = [d[pol][j] - d[ref][j] for d in draws]
                lo, hi = pct(vals, 0.025), pct(vals, 0.975)
                entry[metric] = {"delta": point[pol][j] - point[ref][j],
                                 "ci95": [lo, hi],
                                 "excludes_zero": bool(lo > 0 or hi < 0)}
            out["paired_vs"].setdefault(ref, {})[pol] = entry
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--replicates", type=int, default=200)
    ap.add_argument("--n-bootstrap", type=int, default=2000,
                    help="타겟 클러스터 부트스트랩 반복수. 0 이면 CI 를 내지 않는다.")
    ap.add_argument("--out", default=str(GATE0 / "epsilon_band_selection.json"))
    args = ap.parse_args(argv)

    rows = load_rows()
    by_bb = collections.defaultdict(list)
    for r in rows:
        by_bb[r["backbone_key"]].append(r)
    by_bb = {k: v for k, v in by_bb.items() if len(v) > args.k}
    print(f"RFD3 후보 {len(rows)} · 백본 {len(by_bb)} · K={args.k} · ε={args.eps}",
          flush=True)

    pstruct = fit_loto_pstruct(rows)
    policies = ["random", "pstruct", "delta_soluprot", "product", "eps_band", "oracle"]
    rng = np.random.default_rng(SEED)

    # 타겟을 추론 단위로 둔다 - 리포트의 다른 결과와 같은 단위다.
    per_target = collections.defaultdict(lambda: collections.defaultdict(list))
    for bk, cands in by_bb.items():
        t = cands[0]["target_id"]
        for pol in policies:
            reps = args.replicates if pol == "random" else 1
            sp, ds = [], []
            for _ in range(reps):
                sel = select(cands, args.k, pol, pstruct, args.eps, rng)
                sp.append(sum(r["structural_pass"] for r in sel) / len(sel))
                ds.append(statistics.mean(r["delta_soluprot"] for r in sel))
            per_target[t][pol].append((statistics.mean(sp), statistics.mean(ds)))

    print(f"\n{'정책':>16} | {'structural-pass 율':>18} | {'평균 ΔSoluProt':>14}")
    print("-" * 58)
    summary = {}
    for pol in policies:
        sp = [statistics.mean(x[0] for x in per_target[t][pol]) for t in per_target]
        ds = [statistics.mean(x[1] for x in per_target[t][pol]) for t in per_target]
        summary[pol] = {"structural_pass_rate": statistics.mean(sp),
                        "delta_soluprot": statistics.mean(ds),
                        "n_targets": len(sp)}
        print(f"{pol:>16} | {statistics.mean(sp):18.4f} | {statistics.mean(ds):+14.4f}")

    boot = (_paired_bootstrap(per_target, policies, args.n_bootstrap, SEED)
            if args.n_bootstrap > 0 else None)
    if boot:
        print(f"\n타겟 클러스터 부트스트랩 (n_targets={boot['n_targets']}, "
              f"{boot['n_bootstrap']} 회) · 짝지은 차이 95% CI")
        for ref in ("random", "delta_soluprot"):
            print(f"  기준 = {ref}")
            for pol, e in boot["paired_vs"][ref].items():
                sp = e["structural_pass_rate"]
                print(f"    {pol:>16}  Δstructural {sp['delta']:+.4f} "
                      f"[{sp['ci95'][0]:+.4f}, {sp['ci95'][1]:+.4f}]"
                      f"{'  *' if sp['excludes_zero'] else ''}")

    out = {
        "purpose": "ε-band 선택 규칙의 offline replay. 새 AF2 호출 0 회.",
        "does_not_change": "동결된 v1/v2 판정. 새 선택 규칙의 별도 평가축이다.",
        "k": args.k, "epsilon": args.eps, "seed": SEED,
        "replicates_for_random": args.replicates,
        "unit_of_inference": "target (백본별 선택을 타겟으로 평균)",
        "n_candidates": len(rows), "n_backbones": len(by_bb),
        "policies": summary,
        "uncertainty": boot,
        "uncertainty_note": ("점추정만으로 정책 순위를 주장하지 않는다. 재표집 "
                             "단위는 타겟(n=12)이고, 그래서 구간이 넓다. "
                             "`paired_vs.delta_soluprot` 가 ε-band 도입 여부를 "
                             "직접 묻는 비교다."),
        "pstruct_note": ("LOTO 로 학습한 싼 특징 기반 예측. Gate 2 가 같은 축에서 "
                         "NO-GO 였으므로 강한 신호를 기대하지 않는다."),
        "soluprot_note": ("SoluProt 은 예측 대상이 아니라 이미 아는 cheap observable "
                          "이다. ΔSoluProt 은 WT 서열 대비 차이이며 측정된 용해도가 "
                          "아니다 - '용해도를 개선했다' 고 해석하지 않는다."),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"\n{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
