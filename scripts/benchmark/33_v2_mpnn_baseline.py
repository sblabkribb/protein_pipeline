#!/usr/bin/env python3
"""v2 코호트에서 ProteinMPNN 기준선과 표적별 대리모델을 같은 예산에서 비교한다.

규칙은 `docs/specs/v2-mpnn-baseline-prespec.md` 에 실행 전 동결돼 있다. 여기서
그 문서에 없는 선택을 새로 하지 않는다.

왜 하는가
---------
현행 연구노트의 핵심 결과(RF 와 MPNN 점수가 같은 예산에서 구별되지 않는다)는
holdout 격자의 **11 표적 · RFD3 단독** 에 근거한다. v2 캠페인 자료는 후보마다
설계 백본 PDB 가 기록돼 있고 생성원이 둘이므로 그 제약이 없다.

    후보 5,328 · joint-pass 라벨 5,327 · 고유 백본 357 · 생성원 2
    포함 기준 통과 30 target x source (RFD3 15 · BioEmu 15, 코호트 합산)
    단 RFD3 의 B=100 은 후보가 예산보다 적은 단위 하나가 빠져 14 다
    **새 folding 0 회**

하지 않는 것 (동결 계획)
------------------------
- EFBC 를 계산하지 않는다. 배분 정책을 비교하지 않는다.
- kappa 식별·confirmatory 평가가능성 판정을 바꾸지 않는다.
- **생성원을 합치지 않는다** (`pooling_across_sources_forbidden`).
- 결과를 보고 포함 기준·예산 격자·해석 규칙을 바꾸지 않는다.

백본 처리에 대한 기록
---------------------
사전등록 §3.3 은 BioEmu 백본이 resseq 를 0 부터 매겨 `preprocess_pdb` 의
`strip_nonpositive_resseq` 에서 1 잔기가 빠지는 문제를 대비했다. 실제 채점 경로는
`27_gate2d_prepare_mpnn_scores.score_backbone` 이고 이것은 ProteinMPNN 의
`parse_PDB` 로 파일을 직접 읽으므로 그 전처리를 거치지 않는다. 두 생성원 모두
길이 검사를 통과함을 실행 전에 확인했다. 즉 사전등록이 대비한 문제가 실제
경로에서는 발생하지 않는다 - 규칙을 바꾼 것이 아니라 해당 사항이 없다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

V2 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "v2_multisource"
OUT_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
DATA = PROJECT_ROOT / "data" / "benchmark"
MPNN_CACHE = V2 / "mpnn_scores_v2.json"
EMB_CACHE = DATA / "v2_emb_320d.npz"

#: 동결 문턱.
PLDDT_MIN, RMSD_MAX, SOLUPROT_MIN = 85.0, 2.0, 0.5
#: 사전등록 §3.1 · §4. 바꾸지 않는다.
MIN_POOL = 50
N_TRAIN = 30
SEEDS = [42, 123, 7, 2024, 31337]
BUDGETS = [40, 60, 80, 100]
SELECTION = "kmeans"
N_BOOTSTRAP = 2000
BOOT_SEED = 20260921
MPNN_ORDERS = 4
MPNN_SEED = 20260921


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ 입력

def load_rows() -> list[dict]:
    """후보 + joint-pass 라벨 + 설계 백본 경로."""
    cand = {c["sequence_id"]: c
            for c in json.loads((V2 / "candidates.json").read_text(encoding="utf-8"))}
    rows = []
    for r in csv.DictReader((V2 / "af2_order_metric.csv").open(encoding="utf-8")):
        if r.get("status") != "ok":
            continue
        c = cand.get(r["sequence_id"])
        if not c or not os.path.exists(c.get("backbone_pdb", "")):
            continue
        try:
            pl, rm, so = (float(r["plddt"]), float(r["rmsd_nonloop_order"]),
                          float(r["soluprot"]))
        except (TypeError, ValueError, KeyError):
            continue
        rows.append({
            "sequence_id": r["sequence_id"], "sequence": c["sequence"],
            "target_id": r["target_id"], "cohort": r["cohort"],
            "source": r["backbone_source"], "backbone_pdb": c["backbone_pdb"],
            "joint_pass": float(pl >= PLDDT_MIN and rm <= RMSD_MAX
                                and so >= SOLUPROT_MIN),
        })
    return rows


def mpnn_scores(rows) -> dict[str, float]:
    """백본 조건부 per-residue mean NLL. **낮을수록 좋다.**"""
    if MPNN_CACHE.exists():
        d = json.loads(MPNN_CACHE.read_text(encoding="utf-8"))
        have = d.get("scores", {})
        if all(r["sequence_id"] in have for r in rows):
            print(f"  MPNN 캐시 사용 {len(have)}", flush=True)
            return {k: float(v) for k, v in have.items()}
    m27 = _mod("27_gate2d_prepare_mpnn_scores.py", "m27")
    by_bb = collections.defaultdict(list)
    for r in rows:
        by_bb[r["backbone_pdb"]].append((r["sequence_id"], r["sequence"]))
    print(f"  MPNN 채점 백본 {len(by_bb)} · 서열 {len(rows)}", flush=True)
    model = m27.ENC.load_model()
    out, t0 = {}, time.monotonic()
    for i, (pdb, seqs) in enumerate(sorted(by_bb.items()), 1):
        out.update(m27.score_backbone(pdb, seqs, model=model,
                                      n_orders=MPNN_ORDERS, seed=MPNN_SEED))
        if i % 25 == 0 or i == len(by_bb):
            rate = (time.monotonic() - t0) / i
            print(f"    {i}/{len(by_bb)} (~{(len(by_bb)-i)*rate/60:.1f}분 남음)",
                  flush=True)
    MPNN_CACHE.write_text(json.dumps({
        "definition": ("per-residue mean NLL of the design sequence on its own "
                       "backbone, averaged over random decoding orders. Lower is better."),
        "n_decoding_orders": MPNN_ORDERS, "seed": MPNN_SEED,
        "prespec": "docs/specs/v2-mpnn-baseline-prespec.md",
        "scores": out}, ensure_ascii=False), encoding="utf-8")
    return out


def embeddings(rows, url) -> np.ndarray:
    digest = hashlib.sha256("\n".join(r["sequence_id"] for r in rows).encode()).hexdigest()
    if EMB_CACHE.exists():
        z = np.load(EMB_CACHE, allow_pickle=False)   # 배열과 해시뿐. pickle 불필요.
        if str(z["digest"]) == digest:
            print(f"  임베딩 캐시 사용 {z['embeddings'].shape}", flush=True)
            return z["embeddings"]
    from pipeline_mcp.clients.esm_embedding import LocalHTTPESMEmbeddingClient
    if not url:
        raise SystemExit("ESM URL 이 없다 (--esm-url 또는 RAPID_GPU_HOST)")
    print(f"  임베딩 계산 {len(rows)} · {url}", flush=True)
    emb = LocalHTTPESMEmbeddingClient(base_url=url, token=None).embed(
        [r["sequence"] for r in rows])
    EMB_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMB_CACHE, embeddings=emb, digest=digest)
    return emb


# ---------------------------------------------------------------- 비교

def run_group(rows, emb, mpnn, idx_by_unit, label) -> dict:
    """unit = (cohort, source, target). 정책별 예산 일치 비교."""
    from _selection import select_train_indices
    m31 = _mod("31_fewshot_jointpass_transfer.py", "m31")
    pols = ["rf_probe", "ridge_probe", "mpnn_score", "random", "oracle"]
    per_unit = {}
    for unit, idx in sorted(idx_by_unit.items()):
        idx = np.array(idx)
        y = np.array([rows[i]["joint_pass"] for i in idx], dtype=float)
        # 사전등록 §3.1 의 포함 기준. 결과를 보고 완화하지 않는다.
        if len(idx) < MIN_POOL or y.min() == y.max():
            per_unit["|".join(unit)] = {"informative": False, "n": int(len(idx)),
                                        "rate": float(y.mean())}
            continue
        X, m = emb[idx], np.array([mpnn[rows[i]["sequence_id"]] for i in idx])
        by_b = {}
        for B in BUDGETS:
            if B > len(idx):
                continue
            got = {p: [] for p in pols}
            for seed in SEEDS:
                got["mpnn_score"].append(float(y[np.argsort(m)[:B]].sum()))
                rng = np.random.default_rng(seed)
                got["random"].append(float(y[rng.choice(len(y), size=B, replace=False)].sum()))
                got["oracle"].append(float(np.sort(y)[::-1][:B].sum()))
                tr = select_train_indices(X, N_TRAIN, seed, SELECTION)
                te = np.setdiff1d(np.arange(len(idx)), tr)
                extra = B - N_TRAIN
                if extra > len(te):
                    continue
                base = float(y[tr].sum())
                for pol, est in (("rf_probe", "RF"), ("ridge_probe", "Ridge")):
                    pred = m31.fit_rank(X, y, tr, te, seed, estimator=est)
                    top = np.argsort(pred)[::-1][:extra]
                    got[pol].append(base + float(y[te][top].sum()))
            if all(got[p] for p in pols):
                by_b[str(B)] = {p: statistics.mean(v) for p, v in got.items()}
        per_unit["|".join(unit)] = {"informative": True, "n": int(len(idx)),
                                    "rate": float(y.mean()), "by_budget": by_b}

    info = {k: v for k, v in per_unit.items() if v.get("informative")}
    names = sorted(info)
    rng = np.random.default_rng(BOOT_SEED)
    boots = [[names[int(rng.integers(len(names)))] for _ in names]
             for _ in range(N_BOOTSTRAP)] if len(names) >= 2 else []
    out = {"label": label, "n_units": len(info), "units": names,
           "excluded": {k: v for k, v in per_unit.items() if not v.get("informative")},
           "by_budget": {}, "per_unit": per_unit}
    for B in BUDGETS:
        key = str(B)
        have = [t for t in names if key in info[t]["by_budget"]]
        if len(have) < 2:
            continue

        def agg(ts, p):
            return statistics.mean(info[t]["by_budget"][key][p] for t in ts)

        e = {"n_units": len(have),
             "dropped_pool_lt_B": [t for t in names if key not in info[t]["by_budget"]],
             "point": {p: agg(have, p) for p in pols}, "paired_vs": {}}
        for a, b in (("rf_probe", "mpnn_score"), ("rf_probe", "random"),
                     ("mpnn_score", "random"), ("rf_probe", "ridge_probe")):
            dr = sorted(agg([x for x in bs if x in have], a)
                        - agg([x for x in bs if x in have], b)
                        for bs in boots if any(x in have for x in bs))
            n = len(dr)
            q = lambda p: dr[min(n - 1, max(0, int(p * n)))]
            lo, hi = q(.025), q(.975)
            e["paired_vs"][f"{a}-{b}"] = {
                "delta": agg(have, a) - agg(have, b),
                "ci95": [lo, hi], "excludes_zero": bool(lo > 0 or hi < 0),
                "ci9875_bonf4": [q(.00625), q(.99375)],
                "ci99375_bonf8": [q(.003125), q(.996875)]}
        out["by_budget"][key] = e
    return out


def main(argv=None) -> int:
    #: 격자 경로를 바꿔 끼울 수 있게 한다. 기본값은 동결된 코호트이므로
    #: 인자를 주지 않으면 동작이 달라지지 않는다.
    global V2, MPNN_CACHE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=str(V2),
                    help="격자 디렉터리. 기본값은 동결된 v2_multisource 다.")
    ap.add_argument("--esm-url", default="")
    ap.add_argument("--out", default=str(OUT_DIR / "v2_mpnn_baseline.json"))
    args = ap.parse_args(argv)
    V2 = Path(args.cohort)
    MPNN_CACHE = V2 / "mpnn_scores_v2.json"
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    url = args.esm_url or (f"http://{host}:18170" if host else "")

    rows = load_rows()
    print(f"v2 후보 {len(rows)} (라벨·백본 모두 있는 것)", flush=True)
    mp = mpnn_scores(rows)
    emb = embeddings(rows, url)
    rows = [r for r in rows if r["sequence_id"] in mp]
    print(f"  MPNN 점수 있는 후보 {len(rows)}", flush=True)

    out = {"purpose": "v2 코호트에서 MPNN 기준선과 표적별 대리모델을 같은 예산에서 비교",
           "prespec": "docs/specs/v2-mpnn-baseline-prespec.md",
           "prespec_sha256": hashlib.sha256(
               (PROJECT_ROOT / "docs" / "specs"
                / "v2-mpnn-baseline-prespec.md").read_bytes()).hexdigest(),
           "thresholds": {"plddt_min": PLDDT_MIN, "rmsd_max": RMSD_MAX,
                          "soluprot_min": SOLUPROT_MIN},
           "min_pool": MIN_POOL, "n_train": N_TRAIN, "budgets": BUDGETS,
           "seeds": SEEDS, "bootstrap": {"n": N_BOOTSTRAP, "seed": BOOT_SEED,
                                         "unit": "target x source"},
           "sources_never_pooled": True,
           "groups": {}}

    def units(pred):
        d = collections.defaultdict(list)
        for i, r in enumerate(rows):
            if pred(r):
                d[(r["cohort"], r["source"], r["target_id"])].append(i)
        return d

    for src in ("rfd3", "bioemu"):
        print(f"\n[주 분석] {src} · 코호트 합산", flush=True)
        out["groups"][f"{src}_pooled_cohorts"] = run_group(
            rows, emb, mp, units(lambda r, s=src: r["source"] == s), f"{src} (합산)")
        for coh in ("calibration_v2", "confirmatory"):
            out["groups"][f"{src}_{coh}"] = run_group(
                rows, emb, mp,
                units(lambda r, s=src, c=coh: r["source"] == s and r["cohort"] == c),
                f"{src} / {coh}")

    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text, encoding="utf-8")

    for gk in (f"{s}_pooled_cohorts" for s in ("rfd3", "bioemu")):
        g = out["groups"][gk]
        print(f"\n=== {g['label']} · informative {g['n_units']} target×source")
        print(f"  {'B':>5}{'units':>7}{'RF':>9}{'MPNN':>9}{'무작위':>9}{'oracle':>9}"
              f"   RF−MPNN [95% CI]")
        for B, e in g["by_budget"].items():
            s = e["paired_vs"]["rf_probe-mpnn_score"]
            mark = "0 제외" if s["excludes_zero"] else "0 포함"
            print(f"  {B:>5}{e['n_units']:>7}{e['point']['rf_probe']:9.2f}"
                  f"{e['point']['mpnn_score']:9.2f}{e['point']['random']:9.2f}"
                  f"{e['point']['oracle']:9.2f}   {s['delta']:+6.2f} "
                  f"[{s['ci95'][0]:+.2f},{s['ci95'][1]:+.2f}] {mark}")
    print(f"\n{args.out}")
    print("sha256", hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
