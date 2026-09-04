#!/usr/bin/env python3
"""ProteinMPNN 이 생성 시 이미 내놓는 값이 downstream 성공과 관계있는지 본다.

score / global_score / seq_recovery / T 는 생성 과정에서 공짜로 나온다. 이것들이
SoluProt·pLDDT·구조 통과와 상관이 있다면 **추가 계산 없는 게이트**가 된다.

타겟 간 분산이 지배적이므로(설계 3.4) 전체 상관과 **타겟 내부 순위**를 함께 낸다.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.cath_source import _is_degenerate_unit  # noqa: E402
from rapid_sr.protocol import GATE0_THRESHOLDS  # noqa: E402

_HEADER_RE = re.compile(r"(\w+)=([-\d.]+)")
MPNN_KEYS = ("score", "global_score", "seq_recovery", "T")
DOWNSTREAM = ("soluprot", "plddt_af2", "structural_pass", "joint_pass")


def parse_sample_metrics(sample: dict) -> dict[str, float]:
    """meta 가 있으면 쓰고, 없으면 header 문자열에서 뽑는다.

    CATH run 은 meta 에 값이 채워져 있지만 캠페인 run 은 header 에만 있다.
    """
    out: dict[str, float] = {}
    meta = sample.get("meta") or {}
    for key in MPNN_KEYS:
        value = meta.get(key)
        if isinstance(value, (int, float)):
            out[key] = float(value)
    if len(out) < len(MPNN_KEYS):
        for key, value in _HEADER_RE.findall(str(sample.get("header") or "")):
            if key in MPNN_KEYS and key not in out:
                try:
                    out[key] = float(value)
                except ValueError:
                    pass
    return out


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def collect(run_dir: Path, tiers=("30", "50", "70")) -> list[dict]:
    rows: list[dict] = []
    target = run_dir.name
    for prefix in ("cath_train_", "cath_val_", "cath_test_"):
        if target.startswith(prefix):
            target = target[len(prefix):]
            break
    else:
        target = target.rsplit("_", 1)[-1]

    for tier in tiers:
        tier_dir = run_dir / "tiers" / tier
        if not tier_dir.exists():
            continue
        mpnn = _load(tier_dir / "proteinmpnn.json")
        samples = [s for s in (mpnn.get("samples") or []) if s.get("id") is not None]
        backbone = "target"
        if not samples:
            index = _load(tier_dir / "proteinmpnn_backbones.json").get("backbones") or []
            for entry in index:
                path = Path(entry.get("proteinmpnn_json") or "")
                if not path.exists():
                    continue
                sub = _load(path).get("samples") or []
                for s in sub:
                    sid = str(s.get("id") or "")
                    if sid:
                        s = dict(s)
                        s["id"] = sid if ":" in sid else f"{entry.get('id')}:{sid}"
                        samples.append(s)
        if not samples or _is_degenerate_unit(samples):
            continue

        af2 = _load(tier_dir / "af2_scores.json")
        solu = _load(tier_dir / "soluprot.json").get("scores") or {}
        plddt = af2.get("scores") or {}
        rmsd = af2.get("rmsd_scores") or {}
        failed = set(af2.get("failed_ids") or []) | set((af2.get("prediction_errors") or {}).keys())

        for sample in samples:
            sid = str(sample["id"])
            key = sid if ":" in sid else f"{backbone}:{sid}"
            metrics = parse_sample_metrics(sample)
            if not metrics:
                continue
            pl = plddt.get(key)
            pl = None if (key in failed or not isinstance(pl, (int, float)) or pl == 0) else float(pl)
            rm = rmsd.get(key)
            rm = float(rm) if isinstance(rm, (int, float)) else None
            sp = solu.get(key)
            sp = float(sp) if isinstance(sp, (int, float)) else None
            structural = (
                None if pl is None or rm is None
                else float(pl >= GATE0_THRESHOLDS["plddt_min"] and rm <= GATE0_THRESHOLDS["rmsd_max"])
            )
            joint = (
                None if structural is None or sp is None
                else float(structural > 0 and sp >= GATE0_THRESHOLDS["soluprot_min"])
            )
            rows.append({
                "target": target, "tier": tier, "design_id": key,
                **{k: metrics.get(k) for k in MPNN_KEYS},
                "soluprot": sp, "plddt_af2": pl,
                "structural_pass": structural, "joint_pass": joint,
            })
    return rows


def within_target(rows, x_key, y_key):
    from scipy.stats import spearmanr

    by_target = defaultdict(list)
    for r in rows:
        if r.get(x_key) is not None and r.get(y_key) is not None:
            by_target[r["target"]].append((r[x_key], r[y_key]))
    rhos = []
    for pairs in by_target.values():
        if len(pairs) < 5:
            continue
        xs, ys = zip(*pairs)
        if len(set(xs)) < 2 or len(set(ys)) < 2:
            continue
        rho = spearmanr(xs, ys).statistic
        if rho == rho:
            rhos.append(float(rho))
    if not rhos:
        return None
    arr = np.asarray(rhos)
    rng = np.random.default_rng(0)
    boot = [rng.choice(arr, arr.size, replace=True).mean() for _ in range(2000)]
    return {
        "n_targets": len(rhos),
        "mean_rho": round(float(arr.mean()), 4),
        "ci95": [round(float(np.percentile(boot, 2.5)), 4),
                 round(float(np.percentile(boot, 97.5)), 4)],
        "frac_positive": round(float((arr > 0).mean()), 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cath-dir", default=str(PROJECT_ROOT / "cath_outputs_s3"))
    parser.add_argument("--outputs-dir", default="/opt/protein_pipeline/outputs")
    parser.add_argument("--outputs-glob", default="gate0_*")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "mpnn_score_analysis.json"))
    args = parser.parse_args(argv)

    rows: list[dict] = []
    for run in sorted(p for p in Path(args.cath_dir).iterdir() if p.is_dir()):
        rows.extend(collect(run))
    outputs = Path(args.outputs_dir)
    if outputs.exists():
        for run in sorted(outputs.glob(args.outputs_glob)):
            if run.is_dir():
                rows.extend(collect(run, tiers=("30", "50", "70")))

    temps = sorted({r["T"] for r in rows if r.get("T") is not None})
    report = {
        "n_designs": len(rows),
        "n_targets": len({r["target"] for r in rows}),
        "temperatures_observed": temps,
        "note": "T 에 변이가 없으면 temperature 효과는 기존 데이터로 답할 수 없다.",
        "within_target": {},
    }
    print(f"designs={len(rows)} targets={report['n_targets']} T observed={temps}\n")
    print(f"{'mpnn metric':14s} {'downstream':16s} {'targets':>8s} {'rho':>8s} {'CI95':>20s} {'pos':>6s}")
    for x in MPNN_KEYS:
        for y in DOWNSTREAM:
            res = within_target(rows, x, y)
            if res is None:
                continue
            report["within_target"][f"{x}->{y}"] = res
            print(f"{x:14s} {y:16s} {res['n_targets']:>8d} {res['mean_rho']:>8.4f} "
                  f"{str(res['ci95']):>20s} {res['frac_positive']:>6.3f}")

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
