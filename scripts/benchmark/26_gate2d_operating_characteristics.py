#!/usr/bin/env python3
"""동결된 GO 규칙의 작동특성표를 만든다 - 스펙 §3·§5 의 재현성 계약.

스펙에는 outcome-blind 표 세 개가 인쇄돼 있다(Gate 1 OC, Gate 2 AUC↔Δ_Top4 교정,
Gate 2 GO 작동특성). 그 표를 만든 스크립트가 리포에 없었다 - controller 가 임시로
실행했다. 그래서 **배포된 LCB 가 동결된 `0/600` false-GO 수치를 만든 LCB 와 같은지
확인하는 것이 아무것도 없었다.**

이 스크립트의 목적은 두 번째 구현이 아니라 계약이다. 따라서:

  - LCB 는 `rapid_sr.clustered.one_sided_lcb` 를 그대로 호출한다. 국소 백분위를
    만들지 않는다. 부트스트랩이 나중에 바뀌면 이 표가 깨져서 즉시 드러나야 한다.
  - Δ_Top4·타겟 등가중·타겟내 Spearman·top-1 regret 은 `_gate2d` 의 primitive 를
    그대로 호출한다. 국소 Top-4 를 만들지 않는다.
  - 코호트 기하는 `_gate2d_cohort.load_holdout_grid()` 에서 읽는다. 타겟별 백본
    수와 실제 q_b 를 쓰고 합성 기하를 만들지 않는다.
  - **outcome-blind.** 라벨 분포만 쓴다. 실제 feature 는 어느 표에도 들어가지
    않는다 (Gate 2 는 label-shift 노이즈, Gate 1 은 q̂_b = q_b + N(0, σ)).

Gate 1 은 두 기하를 계산해 이름으로 구분한다 - 섞이면 어느 쪽이 판정 근거인지
알 수 없게 된다.

  - `OC_primary_rfd3_only` — **authoritative.** §3 개정이 native 를 배분 풀에서
    comparator 로 옮겼으므로 Gate 1 이 실제로 평가될 기하는 이쪽이다. GO/NO-GO
    해석이 인용하는 표다.
  - `OC_legacy_all_sources` — **historical reference only.** 스펙 §3 에 인쇄된
    현재 수치가 나온 70 백본(native 포함) 기하를 재현하기 위해서만 존재하며
    어떤 판정에도 쓰지 않는다.

인쇄값과의 대조는 `tests/test_gate2d_metrics.py` 가 한다. **이 스크립트는 스펙
파일을 고치지 않는다.** 재생성값이 인쇄값과 다르면 그 차이를 보고할 뿐이다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _gate2d as G  # noqa: E402
import _gate2d_cohort as C  # noqa: E402

_TRANSCODER = C.PROJECT_ROOT / "scripts" / "transcoder"
if str(_TRANSCODER) not in sys.path:
    sys.path.insert(0, str(_TRANSCODER))

from rapid_sr.clustered import one_sided_lcb  # noqa: E402

#: 스펙 §5: 교정표 400 반복, 작동특성표 600 반복. 여기서 다시 고르지 않는다.
CALIBRATION_REPS = 400
OC_REPS = 600

#: label-shift 노이즈 모형의 delta 격자. AUC = Phi(delta / sqrt(2)) 이므로
#: 이 여섯 개가 스펙 §5 교정표의 여섯 AUC 열(0.50 ~ 0.76)에 대응한다.
GATE2_DELTAS = (0.0, 0.25, 0.50, 0.60, 0.75, 1.00)

#: 작동특성표는 그 중 다섯 개를 쓴다 (스펙 §5 표의 다섯 행).
GATE2_OC_DELTAS = (0.0, 0.25, 0.50, 0.60, 0.75)

#: q̂_b = q_b + N(0, sigma). None 은 귀무 - 예측이 q_b 와 독립인 순수 노이즈다.
GATE1_SIGMAS = (None, 1.00, 0.50, 0.35, 0.25)

#: 스펙 §3 이 인쇄한 네 개의 점추정 조항. 동결된 규칙은 0.25 다.
GATE1_RHO_THRESHOLDS = (0.0, 0.20, 0.25, 0.30)

#: 호출한 프로덕션 primitive. 산출물에 적어 계약을 명시한다.
PRIMITIVES = {
    "lcb": "rapid_sr.clustered.one_sided_lcb",
    "delta_top4": "_gate2d.delta_top4",
    "per_target_means": "_gate2d.per_target_means",
    "target_equal_mean": "_gate2d.target_equal_mean",
    "within_target_spearman": "_gate2d.within_target_spearman",
    "top1_regret": "_gate2d.top1_regret",
    "cohort": "_gate2d_cohort.load_holdout_grid",
    "auc": "sklearn.metrics.roc_auc_score",
}

#: rng 스트림 구분자. **표마다 독립 스트림**이다 - 교정표와 작동특성표는
#: 스펙 §5 가 말하는 그대로 별개의 시뮬레이션 실행이어야 한다(400 vs 600 반복).
#: 같은 스트림을 공유하면 400 반복이 600 반복의 앞부분이 되어 "별개 실행" 이
#: 아니게 되고, 같은 delta 에서 ±0.002 차이가 나는 이유 설명도 어긋난다.
_STREAM_GATE2_CALIBRATION = 21
_STREAM_GATE2_OC = 22
_STREAM_GATE1_PRIMARY = 11
_STREAM_GATE1_LEGACY = 12


def _rng(*key: int) -> np.random.Generator:
    """시드 하나에서 파생된 독립 스트림. 반복 번호까지 키에 넣어 재현한다."""
    return np.random.default_rng([G.BOOTSTRAP_SEED, *key])


def _mc_mean(values: Sequence[float]) -> float:
    """Monte Carlo 반복 평균. **지표 집계가 아니다** - 타겟 등가중은
    `G.target_equal_mean` 이 하고 이 함수는 그 결과를 반복에 대해 평균한다."""
    return float(sum(values) / len(values))


def _lcb(per_target: Sequence[float], *, n_boot: int) -> dict[str, object]:
    """프로덕션 단측 LCB. 게이트가 부르는 것과 같은 인자로 부른다.

    시드도 게이트와 같은 `BOOTSTRAP_SEED` 다 (스펙 §5: "단측 LCB 도 같은 시드를
    쓴다"). 반복마다 시드를 흔들면 여기서 재는 P(LCB > 0) 이 실제 게이트가 낼
    판정과 다른 것을 재게 된다.
    """
    return one_sided_lcb(list(per_target), alpha=G.LCB_ONE_SIDED_ALPHA,
                         n_boot=n_boot, seed=G.BOOTSTRAP_SEED)


# --------------------------------------------------------------------------
# Gate 2 — label-shift 노이즈 모형
# --------------------------------------------------------------------------

def simulate_gate2_rep(backbones: Sequence[C.Backbone], *, delta: float, rep: int,
                       stream: int = _STREAM_GATE2_OC
                       ) -> tuple[list[float], list[float], list[str]]:
    """한 반복의 백본별 (Δ_Top4, 백본내 AUC) 와 타겟 이름.

    노이즈 모형: `score = N(delta if label else 0, 1)`. 라벨 분포만 쓰고 실제
    feature 는 쓰지 않는다 - 그것이 이 표가 outcome-blind 인 이유다.
    """
    rng = _rng(stream, int(round(delta * 1000)), rep)
    deltas, aucs, targets = [], [], []
    for backbone in backbones:
        labels = [f.joint_pass for f in backbone.folds]
        seq_ids = [f.sequence_id for f in backbone.folds]
        scores = rng.normal([delta if v else 0.0 for v in labels], 1.0).tolist()
        deltas.append(G.delta_top4(labels, scores, seq_ids))
        aucs.append(float(roc_auc_score(labels, scores)))
        targets.append(backbone.target_id)
    return deltas, aucs, targets


def oracle_gate2(backbones: Sequence[C.Backbone]) -> dict[str, float]:
    """교정표의 oracle 열. 결정적이므로 반복이 필요 없다.

    점수가 라벨 그대로이면 동점이 되고 `sequence_id` 오름차순 tie-break 이
    적용된다 - 그것이 스펙 §1 의 +0.326 을 만드는 계산이다.
    """
    deltas, aucs, targets = [], [], []
    for backbone in backbones:
        labels = [f.joint_pass for f in backbone.folds]
        scores = [1.0 if v else 0.0 for v in labels]
        deltas.append(G.delta_top4(labels, scores, [f.sequence_id for f in backbone.folds]))
        aucs.append(float(roc_auc_score(labels, scores)))
        targets.append(backbone.target_id)
    return {"mean_auc": round(G.target_equal_mean(aucs, targets), 4),
            "mean_delta_top4": round(G.target_equal_mean(deltas, targets), 4)}


def gate2_calibration(backbones: Sequence[C.Backbone], *, reps: int) -> dict[str, object]:
    """AUC ↔ Δ_Top4 교정표 (스펙 §5)."""
    rows = []
    for delta in GATE2_DELTAS:
        d_means, auc_means = [], []
        for rep in range(reps):
            deltas, aucs, targets = simulate_gate2_rep(
                backbones, delta=delta, rep=rep, stream=_STREAM_GATE2_CALIBRATION)
            d_means.append(G.target_equal_mean(deltas, targets))
            auc_means.append(G.target_equal_mean(aucs, targets))
        rows.append({"delta": delta,
                     "mean_auc": round(_mc_mean(auc_means), 4),
                     "mean_delta_top4": round(_mc_mean(d_means), 4)})
    rows.append({"delta": "oracle", **oracle_gate2(backbones)})
    return {
        "model": "score = N(delta if label else 0, 1); 라벨 분포만 사용",
        "weighting": "백본내 값 -> 타겟 등가중(G.target_equal_mean) -> 반복 평균",
        "reps": reps,
        "rows": rows,
    }


def gate2_operating_characteristics(backbones: Sequence[C.Backbone], *,
                                    reps: int, n_boot: int,
                                    auc_by_delta: dict[float, float]) -> dict[str, object]:
    """GO 규칙 작동특성표 (스펙 §5). 세 조항을 그대로 평가한다."""
    rows = []
    for delta in GATE2_OC_DELTAS:
        points, point_pass, lcb_pass, go_pass = [], 0, 0, 0
        for rep in range(reps):
            deltas, _aucs, targets = simulate_gate2_rep(backbones, delta=delta, rep=rep)
            per_target = G.per_target_means(deltas, targets)
            point = G.target_equal_mean(deltas, targets)
            out = _lcb(per_target, n_boot=n_boot)
            hits_point = point >= G.GATE2_DELTA_MIN
            hits_lcb = bool(out["exceeds_zero"])
            hits_n = int(out["n"]) >= G.MIN_INFORMATIVE_TARGETS
            points.append(point)
            point_pass += int(hits_point)
            lcb_pass += int(hits_lcb)
            go_pass += int(hits_point and hits_lcb and hits_n)
        rows.append({
            "delta": delta,
            "corresponding_mean_auc": auc_by_delta[delta],
            "true_mean_delta_top4": round(_mc_mean(points), 4),
            "p_point_ge_0.10": round(point_pass / reps, 4),
            "p_lcb_gt_0": round(lcb_pass / reps, 4),
            "p_go": round(go_pass / reps, 4),
            "go_count": go_pass,
        })
    null_row = rows[0]
    return {
        "rule": "점추정 Δ_Top4 >= +0.10 AND 단측 90% LCB > 0 AND informative >= 8",
        "reps": reps,
        "rows": rows,
        "false_go": _false_go(null_row["go_count"], reps),
    }


def _false_go(count: int, reps: int) -> dict[str, object]:
    """귀무에서 관측된 거짓 GO 와 그 단측 95% 상한.

    **rule-of-three 는 0 을 관측했을 때만 유효하다.** 0 이 아닌 관측에 3/n 을
    붙이면 "30/600 인데 상한 0.5%" 같은 자기모순이 산출물에 박힌다. 그래서
    상한은 Clopper-Pearson 단측 95% 로 내고(count = 0 이면 rule-of-three 와
    같은 값이 나온다), 문장 형식만 스펙 §5 가 고정한 그대로 쓴다.

    0 을 관측했다고 확률이 0 인 것은 아니다 - 그 문구도 스펙이 동결했다.
    """
    from scipy.stats import beta

    upper = 1.0 if count >= reps else float(beta.ppf(0.95, count + 1, reps - count))
    if count == 0:
        sentence = (f"observed false-GO rate 0/{reps}; "
                    f"approximate 95% upper bound ≈ {100.0 * upper:.1f}%")
    else:
        sentence = (f"observed false-GO rate {count}/{reps} = {count / reps:.3f}; "
                    f"one-sided 95% upper bound {upper:.3f}")
    return {
        "count": count,
        "reps": reps,
        "rate": round(count / reps, 5),
        "upper_95_one_sided": round(upper, 5),
        "upper_95_method": ("Clopper-Pearson 단측 95%. count = 0 이면 "
                            "rule-of-three(3/n) 와 같은 값이다"),
        "frozen_sentence": sentence,
    }


# --------------------------------------------------------------------------
# Gate 1 — q̂_b = q_b + N(0, sigma)
# --------------------------------------------------------------------------

def gate1_units(grid: C.Grid) -> tuple[list[str], list[float]]:
    """informative 타겟의 (타겟, 실제 q_b). 실제 백본 수와 실제 q_b 를 쓴다."""
    informative = set(C.gate1_informative_targets(grid))
    units = [(b.target_id, b.q_b) for b in grid.backbones if b.target_id in informative]
    return [t for t, _q in units], [q for _t, q in units]


def simulate_gate1_rep(targets: Sequence[str], q_b: Sequence[float], *,
                       sigma: float | None, rep: int,
                       stream: int = _STREAM_GATE1_PRIMARY
                       ) -> tuple[dict[str, float], dict[str, float]]:
    """한 반복의 타겟별 (Spearman, top-1 regret).

    `sigma is None` 은 귀무다 - q̂_b 를 q_b 와 **독립**인 N(0,1) 로 뽑는다.
    """
    rng = _rng(stream, 0 if sigma is None else int(round(sigma * 1000)), rep)
    truth = np.asarray(q_b, dtype=float)
    noise = rng.normal(0.0, 1.0, size=truth.size)
    predicted = noise if sigma is None else truth + sigma * noise
    return (G.within_target_spearman(predicted.tolist(), truth.tolist(), targets),
            G.top1_regret(predicted.tolist(), truth.tolist(), targets))


def gate1_operating_characteristics(grid: C.Grid, *, reps: int, n_boot: int,
                                    status: str, note: str, stream: int
                                    ) -> dict[str, object]:
    """Gate 1 OC 표 (스펙 §3). 네 개의 점추정 조항을 함께 낸다."""
    targets, q_b = gate1_units(grid)
    rows = []
    for sigma in GATE1_SIGMAS:
        rhos, regrets, lcb_pass = [], [], 0
        go_pass = {t: 0 for t in GATE1_RHO_THRESHOLDS}
        for rep in range(reps):
            rho_by_target, regret_by_target = simulate_gate1_rep(
                targets, q_b, sigma=sigma, rep=rep, stream=stream)
            per_target = list(rho_by_target.values())
            point = G.target_equal_mean(per_target, list(rho_by_target))
            out = _lcb(per_target, n_boot=n_boot)
            hits_lcb = bool(out["exceeds_zero"])
            hits_n = len(per_target) >= G.MIN_INFORMATIVE_TARGETS
            rhos.append(point)
            regrets.append(G.target_equal_mean(list(regret_by_target.values()),
                                               list(regret_by_target)))
            lcb_pass += int(hits_lcb)
            for threshold in GATE1_RHO_THRESHOLDS:
                go_pass[threshold] += int(point >= threshold and hits_lcb and hits_n)
        rows.append({
            "sigma": "null" if sigma is None else sigma,
            "mean_rho": round(_mc_mean(rhos), 4),
            "mean_top1_regret": round(_mc_mean(regrets), 4),
            "p_lcb_gt_0": round(lcb_pass / reps, 4),
            "p_go": {f"rho>={t:.2f}": round(go_pass[t] / reps, 4)
                     for t in GATE1_RHO_THRESHOLDS},
            "go_count": {f"rho>={t:.2f}": go_pass[t] for t in GATE1_RHO_THRESHOLDS},
            "n_informative_targets": len(set(targets)),
        })
    null_row = rows[0]
    frozen = f"rho>={G.GATE1_RHO_MIN:.2f}"
    return {
        "status": status,
        "note": note,
        "rule": ("타겟 등가중 mean within-target Spearman >= 문턱 "
                 "AND 단측 90% LCB > 0 AND informative >= 8"),
        "model": "q̂_b = q_b + N(0, sigma); null 은 q_b 와 독립인 N(0,1)",
        "reps": reps,
        "n_backbones_in_informative_targets": len(targets),
        "n_informative_targets": len(set(targets)),
        "rows": rows,
        "false_go_at_frozen_threshold": _false_go(null_row["go_count"][frozen], reps),
    }


# --------------------------------------------------------------------------
# 재현성 계약 - 표가 아니라 "이 숫자를 만든 코드" 를 고정한다
# --------------------------------------------------------------------------

def contracts(mixed: Sequence[C.Backbone], grid: C.Grid, *, n_boot: int) -> dict[str, object]:
    """단일 반복 fixture. 테스트가 여기 적힌 값을 재계산해 대조한다.

    표 전체를 다시 돌리면 테스트가 분 단위가 된다. 대신 한 반복의 타겟별 벡터와
    그 벡터의 LCB 를 적어 둔다 - `delta_top4`·`within_target_spearman`·
    `one_sided_lcb` 중 하나라도 동작이 바뀌면 이 두 값이 깨진다.
    """
    deltas, _aucs, targets = simulate_gate2_rep(mixed, delta=0.50, rep=0)
    g2_vector = G.per_target_means(deltas, targets)

    t_names, q_b = gate1_units(grid)
    rho_by_target, _regret = simulate_gate1_rep(t_names, q_b, sigma=0.50, rep=0)
    g1_vector = list(rho_by_target.values())

    return {
        "purpose": "표를 만든 primitive 가 바뀌면 여기서 먼저 깨진다",
        "gate2_delta_top4": {
            "generator": "simulate_gate2_rep(mixed, delta=0.5, rep=0) -> per_target_means",
            "per_target": g2_vector,
            "lcb": _lcb(g2_vector, n_boot=n_boot),
        },
        "gate1_spearman": {
            "generator": ("simulate_gate1_rep(OC_primary_rfd3_only, sigma=0.5, rep=0)"
                          " -> within_target_spearman"),
            "cohort": "OC_primary_rfd3_only",
            "targets": list(rho_by_target),
            "per_target": g1_vector,
            "lcb": _lcb(g1_vector, n_boot=n_boot),
        },
    }


def _code_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.PROJECT_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def build(*, calibration_reps: int = CALIBRATION_REPS, oc_reps: int = OC_REPS,
          n_boot: int = 20000) -> dict[str, object]:
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    rfd3 = C.restrict_to_sources(grid, ("rfd3",))

    calibration = gate2_calibration(mixed, reps=calibration_reps)
    auc_by_delta = {r["delta"]: r["mean_auc"] for r in calibration["rows"]
                    if r["delta"] != "oracle"}
    gate2_oc = gate2_operating_characteristics(
        mixed, reps=oc_reps, n_boot=n_boot, auc_by_delta=auc_by_delta)

    primary = gate1_operating_characteristics(
        rfd3, reps=oc_reps, n_boot=n_boot, stream=_STREAM_GATE1_PRIMARY,
        status="authoritative",
        note=("§3 개정된 primary 기하 - RFD3-only test(native 제외). Gate 1 의 "
              "GO/NO-GO 해석이 인용하는 표다."))
    legacy = gate1_operating_characteristics(
        grid, reps=oc_reps, n_boot=n_boot, stream=_STREAM_GATE1_LEGACY,
        status="historical reference only",
        note=("native 포함 70 백본 기하. 스펙 §3 에 인쇄된 현재 수치가 나온 곳을 "
              "재현하기 위해서만 존재하며 어떤 판정에도 쓰지 않는다."))

    return {
        "purpose": "동결된 GO 규칙(§3·§5)의 작동특성 - 재현성 계약",
        "frozen_spec": "docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md",
        "outcome_blind": ("라벨 분포와 실제 q_b 만 사용한다. 실제 feature 는 "
                          "어느 표에도 들어가지 않는다."),
        "seed": G.BOOTSTRAP_SEED,
        "lcb": {"primitive": PRIMITIVES["lcb"], "alpha": G.LCB_ONE_SIDED_ALPHA,
                "n_boot": n_boot, "seed": G.BOOTSTRAP_SEED,
                "note": "게이트가 부르는 것과 같은 인자·같은 시드로 부른다"},
        "primitives": PRIMITIVES,
        "go_rules": {
            "gate2_delta_min": G.GATE2_DELTA_MIN,
            "gate1_rho_min": G.GATE1_RHO_MIN,
            "min_informative_targets": G.MIN_INFORMATIVE_TARGETS,
            "top_k": G.TOP_K,
        },
        "cohorts": {
            "gate2_mixed_all_sources": {
                "n_backbones": len(mixed),
                "n_targets": len({b.target_id for b in mixed}),
                "n_folds": sum(len(b.folds) for b in mixed),
            },
            "OC_primary_rfd3_only": {
                "n_backbones": len(rfd3.backbones),
                "n_informative_targets": len(C.gate1_informative_targets(rfd3)),
                "n_folds": len(rfd3.folds),
            },
            "OC_legacy_all_sources": {
                "n_backbones": len(grid.backbones),
                "n_informative_targets": len(C.gate1_informative_targets(grid)),
                "n_folds": len(grid.folds),
            },
        },
        "gate2_auc_calibration": calibration,
        "gate2_go_operating_characteristics": gate2_oc,
        "gate1_operating_characteristics": {
            "OC_primary_rfd3_only": primary,
            "OC_legacy_all_sources": legacy,
        },
        "contracts": contracts(mixed, grid=rfd3, n_boot=n_boot),
        "code_sha": _code_sha(),
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def dump(payload: dict[str, object]) -> str:
    """NaN·Infinity 를 쓰지 않고 거절한다 - 스펙 §5 의 fail-closed 와 같은 이유다."""
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(C.GATE0 / "gate2d_operating_characteristics.json"))
    parser.add_argument("--calibration-reps", type=int, default=CALIBRATION_REPS,
                        help="스펙 §5 는 400 이다. 연습 실행 외에는 바꾸지 않는다")
    parser.add_argument("--oc-reps", type=int, default=OC_REPS,
                        help="스펙 §5 는 600 이다. 연습 실행 외에는 바꾸지 않는다")
    parser.add_argument("--n-boot", type=int, default=20000,
                        help="one_sided_lcb 기본값과 같아야 한다")
    args = parser.parse_args(argv)

    report = build(calibration_reps=args.calibration_reps, oc_reps=args.oc_reps,
                   n_boot=args.n_boot)
    Path(args.out).write_text(dump(report) + "\n", encoding="utf-8")

    print("Gate 2 AUC <-> Δ_Top4 교정 (반복 "
          f"{report['gate2_auc_calibration']['reps']})")
    for row in report["gate2_auc_calibration"]["rows"]:
        print(f"  delta={str(row['delta']):>6}  AUC={row['mean_auc']:.3f}  "
              f"Δ_Top4={row['mean_delta_top4']:+.3f}")
    print(f"\nGate 2 GO 작동특성 (반복 {report['gate2_go_operating_characteristics']['reps']})")
    for row in report["gate2_go_operating_characteristics"]["rows"]:
        print(f"  Δ_Top4={row['true_mean_delta_top4']:+.3f}  "
              f"AUC={row['corresponding_mean_auc']:.3f}"
              f"  P(점추정)={row['p_point_ge_0.10']:.2f}  P(LCB>0)={row['p_lcb_gt_0']:.2f}"
              f"  P(GO)={row['p_go']:.2f}")
    print("  " + report["gate2_go_operating_characteristics"]["false_go"]["frozen_sentence"])
    for name, table in report["gate1_operating_characteristics"].items():
        print(f"\nGate 1 OC — {name} [{table['status']}] "
              f"백본 {table['n_backbones_in_informative_targets']} · "
              f"informative {table['n_informative_targets']}")
        for row in table["rows"]:
            print(f"  sigma={str(row['sigma']):>4}  E[rho]={row['mean_rho']:+.3f}  "
                  f"E[regret]={row['mean_top1_regret']:.3f}  "
                  + "  ".join(f"P(GO {k})={v:.2f}" for k, v in row["p_go"].items()))
        print("  " + table["false_go_at_frozen_threshold"]["frozen_sentence"])
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
