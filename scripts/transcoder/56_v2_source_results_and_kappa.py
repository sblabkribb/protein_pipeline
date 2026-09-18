#!/usr/bin/env python3
"""v2 멀티소스 캠페인의 **source 별** 결과 정리와 kappa_pool 식별 판정.

이 스크립트가 하는 것
--------------------
A. cohort flow - target x source 마다 확보된 unit 수 u 와 그 상태를 적는다.
   `unequal_units` 공식(warm-up 4u, ceiling 18u)을 u<10 조합에 적용한다.
B. joint-pass 분포 - source 마다 **따로** 낸다. 합치지 않는다.
C. kappa_pool 식별 판정 - calibration_v2 코호트에서 source 마다 독립으로,
   `rapid-v2-phase4b-calibration-freeze.md` §6·§7·§9 의 동결 절차를 그대로.

하지 않는 것 (동결 규칙)
-----------------------
- **calibration 코호트에서 EFBC 를 계산하지 않는다.** §7: "계산하는 순간
  policy tuning 이다." §14 도 같은 금지를 적는다.
- source 를 합쳐 하나의 p-value/CI 를 만들지 않는다 (plan `pooling_across_
  sources_forbidden`).
- 한 source 의 kappa 를 다른 source 에 빌려주지 않는다 (`borrowing_across_
  sources_forbidden`).
- 식별되지 않으면 억지로 하나를 고르지 않는다. §10 대로 그 source 의
  confirmatory 는 BLOCKED 이고 그것이 결과다.
- 문턱·격자·판정 기준을 결과를 보고 바꾸지 않는다.

모형 (§6) 과 LOTO (§7)
----------------------
동결 v1 과 같은 함수 형태를 쓰려고 `pipeline_mcp.rapid_core.observation.
BetaPosterior` 를 직접 쓴다. 손으로 다시 쓰면 연산 순서가 갈라진다::

    타겟 수준      Beta(mu0*kappa0, (1-mu0)*kappa0), 그 타겟의 모든 관측으로 갱신
    backbone 사전  Beta(m_t*kappa_pool, (1-m_t)*kappa_pool), m_t = 타겟 사후 평균
    backbone 사후  + 그 backbone 자신의 관측
    예측           backbone 사후 평균

`BetaBernoulliModel.observe/posterior` 와 같은 통로다 - 어떤 관측이든 타겟
수준을 갱신하고, backbone 자신의 관측은 거기서 한 번 더 들어간다. 이 이중
반영은 v1 의 실제 동작이고 §6 이 그대로 기술한다. 여기서 "고치지" 않는다.

LOTO 는 타겟을 통째로 빼고, 그 타겟의 관측을 동결된 무작위 순서로 하나씩
넣으며 넣기 직전의 backbone 사후 평균으로 로그 확률을 더한다. 타겟마다 20 개
순서를 평균하고, **타겟별 예측 개수로 나눈 뒤** 타겟 동일 가중으로 평균한다
(§7: 불균형 코호트에서 target-equal estimand 를 보존하는 정규화).

하이퍼파라미터는 격자에서 가져와 **점수만 매긴다** - 어떤 타겟의 데이터로도
적합하지 않으므로 held-out 타겟의 관측은 채점에만 쓰인다.

LOTO 순서 seed 에 대한 명시
---------------------------
§7 은 순서의 **개수**(20)와 **seed 를 동결한다는 원칙**은 적었지만 그 숫자는
적지 않았고, §12 가 요구한 "분석 코드와 해시" 는 폴딩 전에 커밋되지 않았다.
그래서 여기서 정하고 드러내 적는다: 동결된 코호트 seed 에서 결정론적으로
파생시킨다 (`--order-seed` 로 확인 가능). 사후에 고른 값이 아니라는 것을
보이려고 코호트 seed 를 그대로 쓴다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUT_DIR = BASE / "v2_multisource"
PLAN_PATH = BASE / "multisource_validation_plan.json"

#: 동결 문턱. 바꾸지 않는다.
PLDDT_MIN = 85.0
RMSD_MAX = 2.0
SOLUPROT_MIN = 0.5

#: §7 - 타겟마다 평균할 순서 개수.
N_ORDERS = 20
#: §9(3) - 부트스트랩 반복.
N_BOOTSTRAP = 1000
#: §9(1) - 단측 90% 하한.
DELTA_LOWER_Q = 0.10
#: §9(3) - argmax 가 +-1 칸에 드는 비율의 운영 게이트.
STABILITY_MIN = 0.80
#: §11 - 민감도 격자. 선택 도구가 아니다.
SENSITIVITY_KAPPA = (1.0, 2.0, 4.0, 8.0, 16.0)


# ---------------------------------------------------------------- 입력

def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def load_runs() -> dict:
    return json.loads((OUT_DIR / "backbones.json").read_text(encoding="utf-8"))["runs"]


def load_metric() -> list[dict]:
    path = OUT_DIR / "af2_order_metric.csv"
    return list(csv.DictReader(path.open(encoding="utf-8")))


def _num(row: dict, key: str) -> float | None:
    try:
        return float(row[key])
    except (TypeError, ValueError, KeyError):
        return None


def classify(row: dict) -> dict | None:
    """joint-pass / structural-pass 를 동결 정의대로. 측정이 없으면 None."""
    if row.get("status") != "ok":
        return None
    pl, rm, so = _num(row, "plddt"), _num(row, "rmsd_nonloop_order"), _num(row, "soluprot")
    if pl is None or rm is None or so is None:
        return None
    structural = bool(pl >= PLDDT_MIN and rm <= RMSD_MAX)
    return {
        "sequence_id": row["sequence_id"],
        "backbone_key": row["backbone_key"],
        "target_id": row["target_id"],
        "source": row.get("backbone_source"),
        "cohort": row.get("cohort"),
        "structural_pass": structural,
        # joint-pass = 구조 조건 AND SoluProt >= 0.5
        "joint_pass": bool(structural and so >= SOLUPROT_MIN),
        "soluprot": so,
    }


# ------------------------------------------------- A. cohort flow

def cohort_flow(runs: dict, plan: dict) -> dict:
    """target x source 의 u 와 상태. `unequal_units` 공식을 적용한다.

    shortfall / SOURCE_GENERATION_INFEASIBLE / generation_error 를 **구분**한다.
    워커가 죽어 u=0 이 된 것을 생성 불가로 적으면 실패에서 결과를 만드는 것이다.
    """
    f = plan["generation_rules"]["unequal_units_formula"]
    warm_per, ceil_per = int(f["warmup_per_unit"]), int(f["ceiling_per_unit"])
    out: dict = {}
    for run in runs.values():
        cohort, source = run["cohort"], run["backbone_source"]
        u = int(run.get("u_accepted") or 0)
        full = int(run.get("wanted") or 10)
        entry = out.setdefault(cohort, {}).setdefault(source, {
            "n_targets": 0, "u_total": 0, "targets": {},
            "n_shortfall": 0, "n_infeasible": 0, "n_generation_error": 0,
            "n_full": 0, "warmup_total": 0, "ceiling_total": 0,
        })
        state = ("generation_error" if run.get("generation_error")
                 else "SOURCE_GENERATION_INFEASIBLE"
                 if run.get("source_generation_infeasible")
                 else "shortfall" if run.get("shortfall") else "full")
        entry["n_targets"] += 1
        entry["u_total"] += u
        entry["warmup_total"] += warm_per * u
        entry["ceiling_total"] += ceil_per * u
        entry[{"full": "n_full", "shortfall": "n_shortfall",
               "SOURCE_GENERATION_INFEASIBLE": "n_infeasible",
               "generation_error": "n_generation_error"}[state]] += 1
        entry["targets"][run["target_id"]] = {
            "u": u, "state": state, "wanted": full,
            # unequal_units: u<10 이면 40/180 이 아니라 4u/18u 다.
            "warmup_for_this_unit": warm_per * u,
            "ceiling_for_this_unit": ceil_per * u,
            "attempt_cap": run.get("attempt_cap"),
        }
    return out


# ------------------------------------- B. source 별 joint-pass 분포

def joint_pass_distribution(rows: list[dict]) -> dict:
    """cohort x source 마다 따로. **source 를 합치지 않는다.**

    후보 등가중과 타겟 등가중을 같이 낸다 - 이 둘은 실질적으로 다르고
    (리포트의 다른 결과에서 78.8% vs 68.4%), 하나만 적으면 오해를 만든다.
    """
    out: dict = {}
    by_key = collections.defaultdict(list)
    for r in rows:
        by_key[(r["cohort"], r["source"])].append(r)

    for (cohort, source), items in sorted(by_key.items()):
        by_target = collections.defaultdict(list)
        by_backbone = collections.defaultdict(list)
        for r in items:
            by_target[r["target_id"]].append(r)
            by_backbone[r["backbone_key"]].append(r)

        def rate(xs, field):
            return sum(x[field] for x in xs) / len(xs) if xs else None

        t_joint = {t: rate(v, "joint_pass") for t, v in by_target.items()}
        t_struct = {t: rate(v, "structural_pass") for t, v in by_target.items()}
        b_joint = {b: rate(v, "joint_pass") for b, v in by_backbone.items()}
        n_struct = sum(r["structural_pass"] for r in items)

        out.setdefault(cohort, {})[source] = {
            "n_candidates": len(items),
            "n_targets_with_data": len(by_target),
            "n_backbones_with_data": len(by_backbone),
            "joint_pass_n": sum(r["joint_pass"] for r in items),
            "structural_pass_n": n_struct,
            # 후보 등가중
            "joint_pass_rate_candidate_equal": rate(items, "joint_pass"),
            "structural_pass_rate_candidate_equal": rate(items, "structural_pass"),
            # 타겟 등가중 (타겟 클러스터 부트스트랩과 같은 단위)
            "joint_pass_rate_target_equal": statistics.mean(t_joint.values()),
            "structural_pass_rate_target_equal": statistics.mean(t_struct.values()),
            # SoluProt 문턱이 실제로 거르는 양. 직교성 주장의 근거가 되는 수다.
            "soluprot_filtered_from_structural": n_struct - sum(r["joint_pass"] for r in items),
            "soluprot_pass_rate_within_structural": (
                sum(r["joint_pass"] for r in items) / n_struct if n_struct else None),
            "per_target_joint_pass": dict(sorted(t_joint.items())),
            "per_backbone_joint_pass_spread": {
                "min": min(b_joint.values()), "max": max(b_joint.values()),
                "median": statistics.median(b_joint.values()),
            },
        }
    return out


# ------------------------------------------ C. kappa 식별 (§6·§7·§9)

def _orders(items: list, n_orders: int, seed: int) -> list[list[int]]:
    """동결 seed 로 만든 관측 순서 n_orders 개."""
    rng = random.Random(seed)
    idx = list(range(len(items)))
    out = []
    for _ in range(n_orders):
        perm = idx[:]
        rng.shuffle(perm)
        out.append(perm)
    return out


def target_loto_ll(obs: list[tuple[str, bool]], orders: list[list[int]],
                   mu0: float, kappa0: float, kappa_pool: float) -> float:
    """§7 의 온라인 예측 LL. **예측 개수로 나눈** 타겟별 평균 로그 우도.

    `BetaPosterior` 를 그대로 써서 v1 과 연산 순서를 맞춘다.
    """
    from pipeline_mcp.rapid_core.observation import BetaPosterior

    totals = []
    for perm in orders:
        group = BetaPosterior.from_prior(mean=mu0, strength=kappa0)
        seen: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
        ll = 0.0
        for i in perm:
            bb, ok = obs[i]
            # 넣기 직전의 backbone 사후 평균으로 예측한다.
            post = BetaPosterior.from_prior(mean=group.mean, strength=kappa_pool)
            s, n = seen[bb]
            post.update(successes=s, trials=n)
            p = post.mean
            ll += math.log(p) if ok else math.log1p(-p)
            # 관측을 반영한다. 타겟 수준과 backbone 자신 양쪽으로 (v1 통로).
            group.update(successes=int(ok), trials=1)
            seen[bb] = [s + int(ok), n + 1]
        totals.append(ll / len(perm))
    return statistics.mean(totals)


def ll_matrix(obs_by_target: dict[str, list[tuple[str, bool]]], grid: dict,
              order_seed: int, n_orders: int, progress: str = "") -> tuple[list, list, dict]:
    """(mu0, kappa0, kappa_pool) x target 의 정규화 LL 표.

    이 표가 점추정과 타겟 클러스터 부트스트랩 양쪽의 충분통계량이다. 부트스트랩
    마다 온라인 예측을 다시 돌리면 1,000 x 931 번 재계산이 되어 실행이 불가능하다.
    """
    mu0s = grid["mu0"]
    triples = [(m, k0, kp) for m in mu0s for k0 in grid["kappa0"]
               for kp in grid["kappa_pool"]]
    targets = sorted(obs_by_target)
    orders = {t: _orders(obs_by_target[t], n_orders, order_seed + i)
              for i, t in enumerate(targets)}
    mat = {}
    for n, (m, k0, kp) in enumerate(triples, 1):
        mat[(m, k0, kp)] = {
            t: target_loto_ll(obs_by_target[t], orders[t], m, k0, kp)
            for t in targets}
        if progress and (n % 100 == 0 or n == len(triples)):
            print(f"    {progress} {n}/{len(triples)} 격자점", flush=True)
    return triples, targets, mat


def profile_by_kappa(triples, targets, mat, kappa_grid,
                     weights: dict[str, float] | None = None) -> dict[float, float]:
    """kappa_pool 마다 (mu0, kappa0) 위로 profile 한 타겟 동일가중 LOTO-LL.

    §9 의 판정은 kappa_pool 축에서 이뤄지므로 나머지 둘은 profile out 한다.
    """
    best: dict[float, float] = {}
    for (m, k0, kp) in triples:
        per_t = mat[(m, k0, kp)]
        if weights is None:
            score = statistics.mean(per_t[t] for t in targets)
        else:
            tot = sum(weights.values())
            score = sum(per_t[t] * weights[t] for t in targets) / tot
        if kp not in best or score > best[kp]:
            best[kp] = score
    return {kp: best[kp] for kp in kappa_grid if kp in best}


def argmax_kappa(scores: dict[float, float], kappa_grid: list[float]) -> float:
    """동률이면 **더 작은 kappa**. §9 의 사전지정 규칙이다."""
    best_kp, best_v = None, None
    for kp in kappa_grid:                      # 격자 오름차순
        v = scores.get(kp)
        if v is None:
            continue
        if best_v is None or v > best_v:       # 엄격 부등호 -> 동률은 작은 쪽 유지
            best_kp, best_v = kp, v
    return best_kp


def identify_kappa(obs_by_target, grid, *, order_seed, n_orders, n_bootstrap,
                   label="") -> dict:
    """§9 의 세 조건. 하나라도 실패하면 NOT_IDENTIFIED 다."""
    kappa_grid = list(grid["kappa_pool"])
    targets_all = sorted(obs_by_target)
    if len(targets_all) < 2:
        return {"verdict": "NOT_IDENTIFIED",
                "why": f"informative 타겟이 {len(targets_all)} 개다. "
                       "타겟 클러스터 부트스트랩을 할 수 없다.",
                "n_informative_targets": len(targets_all)}

    triples, targets, mat = ll_matrix(obs_by_target, grid, order_seed, n_orders,
                                      progress=label)
    point = profile_by_kappa(triples, targets, mat, kappa_grid)
    kstar = argmax_kappa(point, kappa_grid)
    i_star = kappa_grid.index(kstar)

    # 부트스트랩: 타겟 클러스터를 재표집하고 kappa 마다 다시 profile 한다.
    rng = random.Random(order_seed ^ 0x5EED)
    boot_scores: list[dict[float, float]] = []
    for _ in range(n_bootstrap):
        pick = [targets[rng.randrange(len(targets))] for _ in targets]
        w = collections.Counter(pick)
        boot_scores.append(profile_by_kappa(
            triples, targets, mat, kappa_grid,
            weights={t: float(w.get(t, 0)) for t in targets}))

    # (1) 예측 분리력 - kappa* 에서 두 칸 이상 떨어진 모든 kappa 에 대해
    #     Delta 의 단측 90% 하한 > 0
    far = [kp for i, kp in enumerate(kappa_grid) if abs(i - i_star) >= 2]
    sep = {}
    for kp in far:
        deltas = sorted(b[kstar] - b[kp] for b in boot_scores if kp in b)
        lo = deltas[max(0, int(math.floor(DELTA_LOWER_Q * len(deltas))) - 1)]
        sep[kp] = {"delta_point": point[kstar] - point[kp],
                   "lower_90_one_sided": lo, "passes": bool(lo > 0)}
    c1 = bool(far) and all(v["passes"] for v in sep.values())

    # (2) 내부 최대
    c2 = kstar not in (kappa_grid[0], kappa_grid[-1])

    # (3) 부트스트랩 안정성 - argmax 가 kappa* 의 +-1 칸 안
    near = {kappa_grid[i] for i in range(max(0, i_star - 1),
                                         min(len(kappa_grid), i_star + 2))}
    within = sum(1 for b in boot_scores if argmax_kappa(b, kappa_grid) in near)
    stability = within / len(boot_scores)
    c3 = bool(stability >= STABILITY_MIN)

    identified = bool(c1 and c2 and c3)
    best_triple = max(triples, key=lambda tr: (
        statistics.mean(mat[tr][t] for t in targets)))

    return {
        "verdict": "IDENTIFIED" if identified else "NOT_IDENTIFIED",
        "kappa_star": kstar,
        "n_informative_targets": len(targets),
        "informative_targets": targets,
        "profiled_loto_ll_by_kappa": {str(k): v for k, v in point.items()},
        "criteria": {
            "1_predictive_separation": {
                "passes": c1, "rule": "kappa* 에서 2 칸 이상 떨어진 모든 kappa 의 "
                                      "Delta 단측 90% 하한 > 0",
                "compared_kappas": [str(k) for k in far], "per_kappa": {
                    str(k): v for k, v in sep.items()}},
            "2_interior_maximum": {
                "passes": c2, "rule": f"kappa* 가 격자 양 끝"
                                      f"({kappa_grid[0]}, {kappa_grid[-1]})이 아니다"},
            "3_bootstrap_stability": {
                "passes": c3, "rule": f"argmax 가 kappa* +-1 칸에 드는 비율 >= "
                                      f"{STABILITY_MIN}",
                "fraction_within_one_cell": stability,
                "n_bootstrap": n_bootstrap},
        },
        "mle_triple_if_identified": (
            {"mu0": best_triple[0], "kappa0": best_triple[1],
             "kappa_pool": best_triple[2]} if identified else None),
        "on_not_identified": None if identified else (
            "이 source 의 confirmatory RAPID 은 BLOCKED. 다른 source 의 kappa 를 "
            "빌려 쓰지 않는다. available development evidence is insufficient to "
            "identify the between-backbone pooling strength required by the "
            "coverage policy."),
        "sensitivity_grid_loto_ll": {
            str(k): point.get(k) for k in SENSITIVITY_KAPPA},
        "sensitivity_note": "§11 - robustness 보고용이다. 선택 도구가 아니다.",
    }


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--order-seed", type=int, default=None,
                    help="LOTO 순서 seed. 기본은 동결된 calibration_v2 코호트 seed.")
    ap.add_argument("--n-orders", type=int, default=N_ORDERS)
    ap.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    ap.add_argument("--skip-kappa", action="store_true",
                    help="A/B 만 낸다. 부분 데이터 점검용.")
    ap.add_argument("--allow-partial", action="store_true",
                    help="폴딩이 끝나지 않은 상태에서도 돌린다. 판정은 예비값이다.")
    ap.add_argument("--out", default=str(OUT_DIR / "v2_source_results_and_kappa.json"))
    args = ap.parse_args(argv)

    plan = load_plan()
    runs = load_runs()
    raw = load_metric()
    rows = [c for c in (classify(r) for r in raw) if c]
    order_seed = (args.order_seed if args.order_seed is not None
                  else int(plan["cohorts"]["calibration_v2"]["seed"]))

    flow = cohort_flow(runs, plan)

    # 폴딩 완료 여부. 기대 관측 수는 확보된 u 와 동결된 후보 수에서 나온다.
    expected = 0
    for cohort, per_src in flow.items():
        per_bb = int(plan["per_source_design"][
            "calibration_candidates_per_backbone" if cohort == "calibration_v2"
            else "confirmatory_candidates_per_backbone"])
        for src, e in per_src.items():
            expected += e["u_total"] * per_bb
    complete = len(rows) >= expected
    print(f"관측 {len(rows)} / 기대 {expected} "
          f"({'완료' if complete else '진행 중'})", flush=True)
    if not complete and not args.allow_partial:
        print("\n폴딩이 끝나지 않았다. 판정을 내지 않는다.\n"
              "  부분 데이터로 점검만 하려면 --allow-partial 을 쓴다.", flush=True)
        return 2

    dist = joint_pass_distribution(rows)

    out = {
        "purpose": "v2 멀티소스 캠페인의 source 별 결과와 kappa_pool 식별 판정",
        "plan_id": plan["plan_id"], "plan_version": plan["version"],
        "criteria_source": "docs/specs/rapid-v2-phase4b-calibration-freeze.md §6·§7·§9",
        "thresholds": {"plddt_min": PLDDT_MIN, "rmsd_nonloop_order_max": RMSD_MAX,
                       "soluprot_min": SOLUPROT_MIN},
        "data_complete": complete,
        "n_observations": len(rows), "n_observations_expected": expected,
        "cohort_flow": flow,
        "joint_pass_distribution": dist,
        "forbidden_here": [
            "calibration 코호트의 EFBC 계산 (§7·§14)",
            "source 를 합친 p-value/CI (plan.endpoints.pooling_across_sources_forbidden)",
            "source 간 kappa 차용 (plan.kappa_identification.borrowing_across_sources_forbidden)",
            "식별 실패 시 임계값 완화 또는 대체 kappa 채택 (§10)",
        ],
        "loto_order_seed": order_seed,
        "loto_order_seed_note": (
            "§7 은 순서 개수 20 과 seed 동결 원칙만 적었고 숫자는 적지 않았다. "
            "사후 선택이 아님을 보이려고 동결된 calibration_v2 코호트 seed 를 "
            "그대로 쓴다."),
    }

    if not args.skip_kappa:
        grid = {"mu0": [round(0.05 * i, 2) for i in range(1, 19)],
                "kappa0": [float(x) for x in plan["kappa_identification"]["kappa0_grid"]],
                "kappa_pool": [float(x) for x in plan["kappa_identification"]["grid"]]}
        # mu0 격자는 0.05..0.95 step 0.05 = 19 점이다.
        grid["mu0"] = [round(0.05 * i, 2) for i in range(1, 20)]
        out["grid"] = grid
        out["kappa_identification"] = {}
        for source in plan["sources"]["ids"]:
            cal = [r for r in rows
                   if r["cohort"] == "calibration_v2" and r["source"] == source]
            obs_by_target: dict[str, list[tuple[str, bool]]] = collections.defaultdict(list)
            for r in cal:
                obs_by_target[r["target_id"]].append(
                    (r["backbone_key"], bool(r["joint_pass"])))
            print(f"\n[{source}] calibration_v2 관측 {len(cal)} · "
                  f"informative 타겟 {len(obs_by_target)}", flush=True)
            out["kappa_identification"][source] = identify_kappa(
                dict(obs_by_target), grid, order_seed=order_seed,
                n_orders=args.n_orders, n_bootstrap=args.n_bootstrap,
                label=f"[{source}]")

    text = json.dumps(out, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text, encoding="utf-8")

    # ---- 사람이 읽는 요약
    print("\n=== A. cohort flow (unequal_units 적용)")
    for cohort in sorted(flow):
        for src in sorted(flow[cohort]):
            e = flow[cohort][src]
            print(f"  {cohort:15s} {src:7s} u={e['u_total']:3d} "
                  f"(full {e['n_full']} · shortfall {e['n_shortfall']} · "
                  f"INFEASIBLE {e['n_infeasible']} · gen_error "
                  f"{e['n_generation_error']}) warm-up {e['warmup_total']} · "
                  f"ceiling {e['ceiling_total']}")

    print("\n=== B. joint-pass (source 별, 합치지 않음)")
    print(f"  {'cohort':16s}{'src':8s}{'n':>6}{'joint(cand)':>13}"
          f"{'joint(tgt)':>12}{'struct(cand)':>14}{'SoluProt 통과':>14}")
    for cohort in sorted(dist):
        for src in sorted(dist[cohort]):
            d = dist[cohort][src]
            sp = d["soluprot_pass_rate_within_structural"]
            print(f"  {cohort:16s}{src:8s}{d['n_candidates']:6d}"
                  f"{d['joint_pass_rate_candidate_equal']:13.4f}"
                  f"{d['joint_pass_rate_target_equal']:12.4f}"
                  f"{d['structural_pass_rate_candidate_equal']:14.4f}"
                  f"{'  n/a' if sp is None else f'{sp:14.4f}'}")

    if not args.skip_kappa:
        print("\n=== C. kappa_pool 식별 (source 마다 독립)")
        for source, k in out["kappa_identification"].items():
            print(f"  [{source}] {k['verdict']}  kappa*="
                  f"{k.get('kappa_star')}  informative 타겟 "
                  f"{k['n_informative_targets']}")
            for name, c in (k.get("criteria") or {}).items():
                print(f"      {'PASS' if c['passes'] else 'FAIL'}  {name}")
            if k["verdict"] == "NOT_IDENTIFIED":
                print(f"      -> confirmatory BLOCKED (§10)")

    print(f"\n{args.out}")
    print(f"sha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
