#!/usr/bin/env python3
"""균형 격자 코호트에서 구조 결과의 분산을 타겟·백본·서열 수준으로 나눈다.

이것은 holdout_experiment_spec.json 의 variance_decomposition_plan 을 그대로
집행한다. 계획은 격자가 끝나기 전(2026-09-08)에 동결됐다 - 결과를 보고 분해
방식을 고르면 그 분해는 확증이 아니다.

주 코호트는 RFD3 전용 1,440 (12 타겟 x 5 백본 x 24 서열) 이다. 전체 1,728 을
쓰면 타겟당 native 1 + RFD3 5 이라서 백본 분산 안에 native/RFD3 source 차이가
섞인다. RFD3 만 쓰면 target -> backbone -> sequence 가 완전 균형이고 source 가
상수다. native 포함은 민감도로만 본다.

두 가지 분해를 함께 낸다
------------------------
제곱합(SS) 분해는 관측된 코호트의 귀속이고, 혼합모형(GLMM) 분산성분은 모형
가정 아래의 추정이다. 두 값은 같은 양이 아니므로 하나로 합치지 않는다.
특히 이진 결과의 GLMM 은 잠재 로짓 척도이고 잔차 분산이 자유 모수가 아니라
pi^2/3 로 고정된 값을 쓴다 - 그 백분율을 SS 백분율과 직접 비교하면 안 된다.
연속 endpoint (pLDDT, RMSD) 는 잔차가 실제로 추정되므로 그쪽이 더 직접적이다.

표현에 주의할 것
----------------
"구조 성공의 X% 가 백본 수준에서 결정된다" 로 쓰면 안 된다. 맞는 표현은
"이 코호트의 분산 분해에서 X% 가 타겟 및 백본 수준 차이에 귀속되었다" 다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID_CSV = BASE / "holdout_grid" / "af2_order_metric.csv"
TARGETS_JSON = BASE / "holdout_targets.json"

PLDDT_MIN, RMSD_MAX, SOLUPROT_MIN = 85.0, 2.0, 0.5
#: 로지스틱 잠재변수의 분산. 이진 GLMM 의 잔차는 자유 모수가 아니다.
LOGISTIC_RESIDUAL_VAR = math.pi ** 2 / 3.0


def strata() -> dict[str, str]:
    d = json.loads(TARGETS_JSON.read_text(encoding="utf-8"))
    return {t["domain"]: t["stratum"] for t in d["resolved"]["targets"]}


def load(*, include_native: bool) -> tuple[list[dict], dict]:
    by_target = strata()
    rows, dropped = [], collections.Counter()
    for r in csv.DictReader(GRID_CSV.open(encoding="utf-8")):
        if r["status"] != "ok":
            dropped["fold 실패"] += 1
            continue
        if not include_native and r["backbone_source"] != "rfd3":
            dropped["native 제외"] += 1
            continue
        plddt, rmsd = r["plddt"].strip(), r["rmsd_nonloop_order"].strip()
        if not plddt or not rmsd:
            dropped[f"지표 거부 ({r['backbone_source']})"] += 1
            continue
        solu = r["soluprot"].strip()
        rows.append({
            "target_id": r["target_id"],
            "backbone_key": r["backbone_key"],
            "length_stratum": by_target.get(r["target_id"], "unknown"),
            "plddt": float(plddt),
            "rmsd_nonloop_order": float(rmsd),
            "structural_pass": float(float(plddt) >= PLDDT_MIN and float(rmsd) <= RMSD_MAX),
            "joint_pass": float(float(plddt) >= PLDDT_MIN and float(rmsd) <= RMSD_MAX
                                and bool(solu) and float(solu) >= SOLUPROT_MIN),
        })
    return rows, dict(dropped)


def sum_of_squares(rows, field: str) -> dict:
    """35_variance_decomposition_structural.py 와 같은 제곱합 분해. 대조용이다."""
    y = [r[field] for r in rows]
    n = len(y)
    grand = sum(y) / n
    total = sum((v - grand) ** 2 for v in y)
    if total <= 0:
        return {"note": "총 분산 0 - 분해할 것이 없다"}
    by_t, by_b = collections.defaultdict(list), collections.defaultdict(list)
    for i, r in enumerate(rows):
        by_t[r["target_id"]].append(i)
        by_b[r["backbone_key"]].append(i)
    mean = lambda ix: sum(y[i] for i in ix) / len(ix)  # noqa: E731
    ss_t = sum(len(ix) * (mean(ix) - grand) ** 2 for ix in by_t.values())
    ss_b = 0.0
    for ix in by_t.values():
        tm = mean(ix)
        subs = collections.defaultdict(list)
        for i in ix:
            subs[rows[i]["backbone_key"]].append(i)
        ss_b += sum(len(s) * (mean(s) - tm) ** 2 for s in subs.values())
    ss_e = sum(sum((y[i] - mean(ix)) ** 2 for i in ix) for ix in by_b.values())
    return {"target_level": round(ss_t / total, 4),
            "backbone_within_target": round(ss_b / total, 4),
            "sequence_within_backbone": round(ss_e / total, 4),
            "attributed_to_target_and_backbone": round((ss_t + ss_b) / total, 4),
            "n": n, "mean": round(grand, 4)}


def glmm_continuous(rows, field: str) -> dict:
    """plddt / rmsd ~ length_stratum + (1|target) + (1|target:backbone).

    연속 endpoint 를 쓰는 이유: 이진 pass 만 보면 pLDDT 96 과 86 이 같아진다.
    온도 분석에서 실제로 연속값이 이진보다 판정력이 높았다.
    """
    import pandas as pd
    import statsmodels.formula.api as smf

    df = pd.DataFrame(rows)
    md = smf.mixedlm(f"{field} ~ C(length_stratum)", df, groups="target_id",
                     re_formula="1", vc_formula={"backbone": "0 + C(backbone_key)"})
    res = md.fit(reml=True)
    v_t = float(res.cov_re.iloc[0, 0])
    v_b = float(res.vcomp[0]) if len(res.vcomp) else 0.0
    v_e = float(res.scale)
    tot = v_t + v_b + v_e
    return {
        "formula": f"{field} ~ C(length_stratum) + (1|target) + (1|target:backbone)",
        "variance": {"target": round(v_t, 6), "backbone_within_target": round(v_b, 6),
                     "residual_sequence": round(v_e, 6)},
        "percent": {"target": round(v_t / tot, 4),
                    "backbone_within_target": round(v_b / tot, 4),
                    "residual_sequence": round(v_e / tot, 4)},
        "attributed_to_target_and_backbone": round((v_t + v_b) / tot, 4),
        "length_stratum_fixed_effects": {
            k: round(float(v), 4) for k, v in res.fe_params.items()},
        "converged": bool(res.converged),
        "n": int(df.shape[0]),
    }


def glmm_binary(rows, field: str) -> dict:
    """이진 pass 의 잠재 로짓 척도 분산성분.

    잔차는 추정되지 않는다 - 로지스틱 잠재변수의 분산 pi^2/3 을 쓴다. 따라서
    여기 백분율은 SS 백분율과 같은 양이 아니다. 그 사실을 결과에 적어 둔다.
    """
    import pandas as pd
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    df = pd.DataFrame(rows)
    md = BinomialBayesMixedGLM.from_formula(
        f"{field} ~ C(length_stratum)",
        {"target": "0 + C(target_id)", "backbone": "0 + C(backbone_key)"}, df)
    res = md.fit_vb()
    # vcp_mean 은 log-sd 다. 분산으로 되돌린다.
    names = list(res.model.vcp_names)
    sd = {n: math.exp(float(res.vcp_mean[i])) for i, n in enumerate(names)}
    v_t, v_b = sd.get("target", 0.0) ** 2, sd.get("backbone", 0.0) ** 2
    tot = v_t + v_b + LOGISTIC_RESIDUAL_VAR
    return {
        "formula": f"{field} ~ C(length_stratum) + (1|target) + (1|target:backbone)",
        "scale": "latent logit",
        "variance": {"target": round(v_t, 4), "backbone_within_target": round(v_b, 4),
                     "residual_assumed_pi2_over_3": round(LOGISTIC_RESIDUAL_VAR, 4)},
        "percent": {"target": round(v_t / tot, 4),
                    "backbone_within_target": round(v_b / tot, 4),
                    "residual_sequence": round(LOGISTIC_RESIDUAL_VAR / tot, 4)},
        "attributed_to_target_and_backbone": round((v_t + v_b) / tot, 4),
        "caveat": "잔차를 pi^2/3 로 고정한 잠재 척도 분해다. 제곱합 분해의 "
                  "백분율과 같은 양이 아니므로 직접 비교하지 않는다.",
        "fit": "variational Bayes (fit_vb)",
        "n": int(df.shape[0]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "holdout_grid" / "variance_decomposition_grid.json"))
    args = ap.parse_args()

    report = {
        "purpose": "동결된 variance_decomposition_plan 집행 (균형 격자 코호트)",
        "frozen_spec": "public_data/benchmark/gate0/holdout_experiment_spec.json",
        "cohort_description": "yield-unselected, QC-eligible balanced cohort",
        "why_not_unselected": "yield 를 보고 고르지는 않았다 - 이 타겟들은 게이트 0 을 "
                              "통과한 적이 없어 볼 yield 가 존재하지 않았다. 다만 RFD3 "
                              "백본은 2.0 A 수용 게이트와 구조 적격성을 통과해야 했다.",
        "cohorts": {},
    }
    for name, include_native in (("rfd3_only_primary", False),
                                 ("native_inclusive_sensitivity", True)):
        rows, dropped = load(include_native=include_native)
        n_t = len({r["target_id"] for r in rows})
        n_b = len({r["backbone_key"] for r in rows})
        print(f"\n=== {name} · 설계 {len(rows)} · 타겟 {n_t} · 백본 {n_b} · 제외 {dropped}")
        entry = {"n_designs": len(rows), "n_targets": n_t, "n_backbones": n_b,
                 "dropped": dropped, "sum_of_squares": {}, "mixed_model": {}}
        for field in ("structural_pass", "joint_pass", "plddt", "rmsd_nonloop_order"):
            entry["sum_of_squares"][field] = sum_of_squares(rows, field)
        for field in ("plddt", "rmsd_nonloop_order"):
            try:
                entry["mixed_model"][field] = glmm_continuous(rows, field)
            except Exception as exc:  # 수렴 실패를 성공처럼 적지 않는다
                entry["mixed_model"][field] = {"error": f"{type(exc).__name__}: {exc}"}
        for field in ("structural_pass", "joint_pass"):
            try:
                entry["mixed_model"][field] = glmm_binary(rows, field)
            except Exception as exc:
                entry["mixed_model"][field] = {"error": f"{type(exc).__name__}: {exc}"}
        report["cohorts"][name] = entry

        print(f"  {'endpoint':22s} {'방법':10s} {'타겟':>8} {'백본':>8} {'서열':>8}")
        for field in ("structural_pass", "joint_pass", "plddt", "rmsd_nonloop_order"):
            ss = entry["sum_of_squares"][field]
            if "target_level" in ss:
                print(f"  {field:22s} {'제곱합':10s} {ss['target_level']:>8.1%} "
                      f"{ss['backbone_within_target']:>8.1%} "
                      f"{ss['sequence_within_backbone']:>8.1%}")
            mm = entry["mixed_model"].get(field, {})
            if "percent" in mm:
                p = mm["percent"]
                tag = "혼합(잠재)" if mm.get("scale") else "혼합모형"
                print(f"  {'':22s} {tag:10s} {p['target']:>8.1%} "
                      f"{p['backbone_within_target']:>8.1%} {p['residual_sequence']:>8.1%}")
            elif "error" in mm:
                print(f"  {'':22s} {'혼합모형':10s} 실패: {mm['error'][:60]}")

    primary = report["cohorts"]["rfd3_only_primary"]
    ss = primary["sum_of_squares"]["structural_pass"]
    report["how_to_state_this"] = {
        "correct": f"이 균형 코호트의 제곱합 분해에서 "
                   f"{ss['attributed_to_target_and_backbone']:.1%} 가 타겟 및 백본 수준 "
                   f"차이에 귀속되었다",
        "incorrect": f"구조 성공의 {ss['attributed_to_target_and_backbone']:.0%} 가 "
                     f"백본 수준에서 결정된다",
        "why": "분산 분해는 관측된 코호트의 귀속이지 인과적 결정이 아니다",
    }
    report["supersedes"] = ("초록의 49.5 / 14.7 / 35.8 은 온도 패널 코호트(20 타겟)에서 "
                            "나온 값이고, 패널 2 가 중간 yield 백본을 선별해 구성됐다. "
                            "이 균형 코호트 값으로 교체하고, 기존 값은 부록에 선별된 "
                            "코호트와의 비교로 남긴다.")
    report["limits"] = [
        "타겟 12 개다. 타겟 수준 분산성분의 정밀도가 그만큼만 된다.",
        "생성 조건은 T=0.1 하나다. 조건 수준 변이는 이 분해에 없다.",
        "RFD3 백본은 2.0 A 수용 게이트를 통과한 것들이다 - 기각된 백본의 변이는 "
        "관측되지 않는다.",
        "이진 endpoint 의 혼합모형은 잠재 로짓 척도이고 잔차가 pi^2/3 로 고정이다. "
        "제곱합 백분율과 같은 양이 아니다.",
    ]
    report["code_sha"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                        capture_output=True, text=True).stdout.strip()
    report["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
