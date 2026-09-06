#!/usr/bin/env python3
"""Temperature AF2 결과를 백본 clustered bootstrap 으로 비교하고 중단 여부를 판정한다.

primary endpoint: structural_yield, joint_yield
secondary       : SoluProt, diversity

480 서열은 독립 표본이 아니다. 실제 독립 단위는 백본 15개이므로 재표집을 백본
단위로 한다. 서열 단위로 재표집하면 구간이 실제보다 좁게 나온다.
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

from rapid_sr.clustered import clustered_bootstrap  # noqa: E402
from rapid_sr.protocol import GATE0_THRESHOLDS, STRUCTURAL_METRIC_V1  # noqa: E402

REFERENCE_T = "0.1"
#: 재표집 단위. 1 차 패널은 백본 하나가 곧 타겟 하나였지만, informative 패널은
#: 한 타겟에서 최대 3 개의 백본을 뽑으므로 타겟이 클러스터다. 백본으로
#: 재표집하면 독립 클러스터를 실제보다 많이 세어 구간을 과장한다.
DEFAULT_CLUSTER_UNIT = "backbone_key"

#: 이진 통과율과 나란히 보는 연속 endpoint. 같은 480 폴드에서 pLDDT 는 68-97 로
#: 흩어져 있었는데 structural_yield 는 15 개 중 12 개가 0.000 또는 1.000 이었다.
#: 연속값에는 바닥/천장이 없으므로 포화로 정보를 잃지 않는다.
CONTINUOUS_ENDPOINTS = ("plddt", "rmsd", "_soluprot")

#: 소스별 결론을 확정적으로 부르기 위한 최소 백본 수. 확장 패널의 BioEmu 는
#: 4 개뿐이라 그 아래다.
MIN_BACKBONES_FOR_CONFIRMATORY_SOURCE = 5


def min_backbones_for_confirmatory_source() -> int:
    return MIN_BACKBONES_FOR_CONFIRMATORY_SOURCE
# 효과가 명확하다고 부르기 위한 최소 구간 정밀도.
CI_WIDTH_TARGET = 0.10
# 이 비율 이상이 백본 간 변동이면 서열을 더 뽑아도 구간이 좁아지지 않는다.
BACKBONE_LIMITED_THRESHOLD = 0.5


def diagnose_uncertainty(diffs, yields_ref, yields_alt, n_per_condition: int) -> dict:
    """CI 폭의 원인이 서열 수 부족인지 백본 수 부족인지 나눈다.

    관측된 백본별 차이의 분산은 두 성분의 합이다.

        Var(관측 차이) = Var(진짜 백본 간 차이) + E[서열 표집 분산]

    yield 는 n 개 서열에서 잰 비율이므로 표집 분산은 p(1-p)/n 로 근사한다.
    백본 성분이 지배적이면 같은 백본에서 서열을 더 뽑아도 소용이 없고,
    **백본을 늘려야** 한다.
    """
    diffs = np.asarray(diffs, dtype=float)
    if diffs.size < 3 or n_per_condition <= 0:
        return {"verdict": "unknown", "n_backbones": int(diffs.size)}

    observed = float(diffs.var(ddof=1))
    sampling = float(np.mean([
        p * (1 - p) / n_per_condition + q * (1 - q) / n_per_condition
        for p, q in zip(np.asarray(yields_alt, dtype=float),
                        np.asarray(yields_ref, dtype=float))
    ]))
    backbone = max(0.0, observed - sampling)
    total = backbone + sampling
    frac_backbone = (backbone / total) if total > 0 else 0.0
    return {
        "observed_variance": round(observed, 6),
        "sequence_sampling_variance": round(sampling, 6),
        "backbone_variance": round(backbone, 6),
        "fraction_backbone": round(frac_backbone, 4),
        "verdict": (
            "backbone_limited" if frac_backbone >= BACKBONE_LIMITED_THRESHOLD
            else "sequence_limited"
        ),
        "n_backbones": int(diffs.size),
    }


#: 판정을 내리려면 최소 이만큼의 백본이 실제로 움직여야 한다. 바닥/천장에 붙어
#: 있는 백본은 온도를 바꿔도 값이 변할 수 없으므로 "차이 0" 이 합의가 아니다.
MIN_INFORMATIVE_BACKBONES = 8


def is_saturated(values, *, low: float = 0.0, high: float = 1.0, tol: float = 1e-9) -> bool:
    """이 백본이 모든 조건에서 척도의 바닥이나 천장에 붙어 있는가.

    포화된 백본의 조건 간 차이는 항상 정확히 0 이다. 그 0 을 "온도가 영향을 주지
    않았다" 는 증거로 세면, 답을 못 하는 실험이 답을 한 것처럼 보인다. 중간값에
    붙어 있는 것(예: 늘 0.5)은 포화가 아니라 그냥 변화가 없는 것이므로 제외하지
    않는다 - 그쪽은 진짜 정보다.
    """
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return False
    return all(abs(v - low) <= tol for v in vals) or all(abs(v - high) <= tol for v in vals)


def count_informative(per_backbone: dict) -> dict:
    """전체 백본 수와, 그중 실제로 정보를 주는 수를 따로 센다."""
    total = len(per_backbone)
    saturated = sum(1 for values in per_backbone.values() if is_saturated(values))
    return {
        "n_backbones": total,
        "n_saturated": saturated,
        "n_informative": total - saturated,
        "saturated_fraction": round(saturated / total, 4) if total else None,
    }


def decide_next_step(entry: dict, *, ci_width_target: float = CI_WIDTH_TARGET) -> str:
    """1단계 480 이후 무엇을 할지.

    구간이 넓다고 무조건 서열을 늘리지 않는다. 백본 수가 병목이면 같은 백본에서
    서열을 더 뽑아도 구간이 좁아지지 않으므로 신규 백본으로 확장해야 한다.

    두 가지를 구간 폭보다 먼저 본다.

    1. **포화.** 480 폴드 결과에서 15 개 백본 중 12 개가 모든 온도에서 0.000
       이거나 1.000 이었다. 그 12 개의 차이 0 이 구간을 좁혀 stop_no_effect 가
       나왔지만, 실제로 온도에 반응할 수 있었던 백본은 3 개뿐이다.
    2. **경계에 걸친 구간.** 백본별 차이가 1/8 격자 위에 있으면 부트스트랩
       분위수도 격자 위에 놓인다. T=0.2 의 97.5 분위수는 정확히 0.0000 이었는데
       0 보다 큰 질량은 0.000 이었다. 그것은 귀무가 아니라 작은 음의 효과다.
    """
    ci = entry.get("ci95")
    if not ci:
        return "expand_backbones"

    saturation = entry.get("saturation")
    if saturation and saturation.get("n_informative") is not None:
        if int(saturation["n_informative"]) < MIN_INFORMATIVE_BACKBONES:
            return "expand_backbones"

    above = entry.get("prob_above_zero")
    below = entry.get("prob_below_zero")
    one_sided_mass_only = (
        above is not None and below is not None
        and (float(above) == 0.0 or float(below) == 0.0)
        and not entry.get("excludes_zero")
    )

    width = float(ci[1]) - float(ci[0])
    if width <= ci_width_target and not one_sided_mass_only:
        return "stop_effect_confirmed" if entry.get("excludes_zero") else "stop_no_effect"
    verdict = (entry.get("uncertainty") or {}).get("verdict")
    return "add_second_half" if verdict == "sequence_limited" else "expand_backbones"


def load(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [r for r in csv.DictReader(handle) if r.get("status") == "ok"]


def _num(row, key):
    value = row.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def annotate(rows: list[dict]) -> list[dict]:
    for row in rows:
        plddt, rmsd, solu = _num(row, "plddt"), _num(row, "rmsd"), _num(row, "soluprot")
        structural = (
            None if plddt is None or rmsd is None
            else float(plddt >= GATE0_THRESHOLDS["plddt_min"]
                       and rmsd <= GATE0_THRESHOLDS["rmsd_max"])
        )
        row["_structural"] = structural
        row["_joint"] = (
            None if structural is None or solu is None
            else float(structural > 0 and solu >= GATE0_THRESHOLDS["soluprot_min"])
        )
        row["_soluprot"] = solu
    return rows


def paired_yield_difference(rows: list[dict], temp: str, field: str, *,
                            cluster_unit: str = DEFAULT_CLUSTER_UNIT) -> dict:
    """단위별로 (temp 의 yield) - (기준 T 의 yield) 를 구하고 그 단위로 재표집.

    `cluster_unit` 은 데이터 구조가 정한다. 백본이 타겟 안에 중첩되어 있으면
    타겟이 클러스터이고, 백본으로 재표집하면 구간이 부당하게 좁아진다.
    """
    by = defaultdict(lambda: defaultdict(list))
    for row in rows:
        value = row.get(field)
        if value is not None:
            by[row[cluster_unit]][row["temperature"]].append(float(value))

    backbones, diffs, refs, alts, counts = [], [], [], [], []
    for backbone, per_temp in by.items():
        if REFERENCE_T not in per_temp or temp not in per_temp:
            continue
        ref = float(np.mean(per_temp[REFERENCE_T]))
        alt = float(np.mean(per_temp[temp]))
        backbones.append(backbone)
        diffs.append(alt - ref)
        refs.append(ref)
        alts.append(alt)
        counts.append(min(len(per_temp[REFERENCE_T]), len(per_temp[temp])))
    if len(diffs) < 3:
        # CI 는 못 내지만 무엇을 몇 개로 세려 했는지는 남긴다. 그래야 호출자가
        # "구간이 없다" 와 "클러스터가 부족했다" 를 구별한다.
        return {
            "point": round(float(np.mean(diffs)), 4) if diffs else None,
            "ci95": None, "n_clusters": len(diffs),
            "cluster_unit": cluster_unit, "n_clusters_resampled": len(diffs),
            "insufficient_clusters": True,
        }
    values = np.asarray(diffs)
    out = clustered_bootstrap(backbones, lambda idx: float(values[idx].mean()))
    out["n_backbones_paired"] = len(diffs)
    out["cluster_unit"] = cluster_unit
    out["n_clusters_resampled"] = len(diffs)
    out["uncertainty"] = diagnose_uncertainty(
        diffs, refs, alts, int(np.median(counts)) if counts else 0
    )
    # 이 대조에서 실제로 움직일 수 있었던 백본이 몇 개인가. 바닥/천장에 붙은
    # 백본의 차이 0 은 합의가 아니라 정보 부재다.
    out["saturation"] = count_informative({
        backbone: [refs[i], alts[i]] for i, backbone in enumerate(backbones)
    })
    # 분위수만으로는 "0 에 닿았다" 와 "0 을 품는다" 를 구별할 수 없다. 격자형
    # 통계량에서는 그 둘이 전혀 다른 결론이므로 꼬리 질량을 함께 보고한다.
    out.update(_tail_masses(values, backbones))
    return out


#: primary endpoint. 둘 다 져야 dominated 후보가 된다. 하나만 지는 것은 잡음과
#: 구별되지 않는다.
PRIMARY_ENDPOINTS = ("structural_yield", "joint_yield")

#: dominated 판정에 필요한 최소 정보 클러스터 수. 1 차 패널의 T=0.2 는 두
#: endpoint 모두 음이었고 0 위 질량이 0 이었지만 정보 클러스터가 3 개였다.
#: 그 정도 근거로 arm 을 없애면, 없앤 뒤에는 되돌릴 데이터가 생기지 않는다.
MIN_CLUSTERS_FOR_DOMINANCE = 8


def condition_dominance(report: dict, *, other_panel: dict | None = None,
                        min_clusters: int = MIN_CLUSTERS_FOR_DOMINANCE) -> dict:
    """어떤 생성 조건이 기준 조건에 일관되게 지는지 판단한다.

    이 함수는 **제거하지 않는다**. 제거는 사람이 내리는 별도의 결정이고, 여기서는
    그 결정에 필요한 조건이 충족됐는지만 답한다. 조건 하나를 없애면 그 조건에
    대한 데이터는 더 이상 생기지 않으므로, 되돌릴 수 없는 쪽으로 기운다.

    dominated 로 부르려면 전부 만족해야 한다.

    1. 두 primary endpoint 모두에서 기준 조건보다 점추정이 낮다.
    2. 두 endpoint 모두 부트스트랩 질량이 0 위에 없다 (또는 CI 가 0 을 제외한다).
    3. 정보를 주는 클러스터가 `min_clusters` 이상이다.
    4. 두 번째 패널을 주면 그 패널도 같은 방향이어야 한다.
    """
    def read(source, endpoint, temp):
        return (source.get("comparisons") or {}).get(f"{endpoint}@T{temp}")

    temps = sorted({
        key.split("@T", 1)[1]
        for key in (report.get("comparisons") or {})
        if "@T" in key
    })

    dominated, insufficient, disagree, evidence = [], [], [], {}
    for temp in temps:
        if temp == REFERENCE_T:
            continue
        entries = {e: read(report, e, temp) for e in PRIMARY_ENDPOINTS}
        if any(entry is None for entry in entries.values()):
            continue
        evidence[temp] = {
            endpoint: {
                "point": entry.get("point"),
                "ci95": entry.get("ci95"),
                "prob_above_zero": entry.get("prob_above_zero"),
                "n_informative": (entry.get("saturation") or {}).get("n_informative"),
            }
            for endpoint, entry in entries.items()
        }

        clusters = [
            (entry.get("saturation") or {}).get("n_informative") or 0
            for entry in entries.values()
        ]
        if min(clusters) < min_clusters:
            insufficient.append(temp)
            continue

        def loses(entry):
            point = entry.get("point")
            if point is None or point >= 0:
                return False
            above = entry.get("prob_above_zero")
            # CI 가 0 을 제외하거나, 격자 때문에 0 에 닿기만 하고 위쪽 질량이 없거나.
            return bool(entry.get("excludes_zero")) or (above is not None and above == 0.0)

        if not all(loses(entry) for entry in entries.values()):
            continue

        if other_panel is not None:
            others = {e: read(other_panel, e, temp) for e in PRIMARY_ENDPOINTS}
            evidence[temp]["other_panel"] = {
                endpoint: (entry or {}).get("point") for endpoint, entry in others.items()
            }
            if any(entry is None or (entry.get("point") or 0) >= 0 for entry in others.values()):
                disagree.append(temp)
                continue

        dominated.append(temp)

    return {
        "reference_temperature": REFERENCE_T,
        "min_clusters_for_dominance": min_clusters,
        "dominated": dominated,
        "insufficient_evidence": insufficient,
        "panels_disagree": disagree,
        "evidence": evidence,
        #: 이 함수는 후보만 낸다. 실제 제거는 정책 설정에서 명시적으로 한다.
        "pruned": [],
        "recommendation": (
            f"조건 {dominated} 는 제거 검토 대상이다. 제거는 자동으로 하지 않는다 - "
            f"없애면 그 조건의 데이터가 더 생기지 않으므로 되돌릴 수 없다."
            if dominated else
            "제거 기준을 넘은 조건이 없다."
        ),
    }


def build_report_header(*, panel: str, cluster_unit: str, selection_scope: str) -> dict:
    """리포트가 자기 적용 범위를 스스로 말하게 한다.

    informative 패널은 baseline yield 가 중간인 백본만 담는다. 거기서 나온 온도
    효과를 전체 백본 집단의 평균으로 읽으면, 선택된 부분집단의 조건부 효과를
    모집단 효과로 바꿔치기하는 것이다.
    """
    # 선정에 yield 를 썼으면 개발용 패널이다. 그 패널로 정책 성능을 주장하면
    # 정책이 잘 통할 백본을 미리 골라놓고 잘 통한다고 말하는 것이 된다.
    developed_on_yield = bool(selection_scope)
    return {
        "panel": panel,
        "panel_role": "development" if developed_on_yield else "unfiltered",
        "valid_for_policy_performance_claims": False,
        "policy_validation_requires": (
            "Unseen targets whose baseline yield is not known in advance, driven from an "
            "initial probe online. 선정에 쓰지 않은 새 타겟에서, baseline yield 를 미리 "
            "모르는 채로 초기 probe 부터 실제 온라인 방식으로 돌려야 정책 성능 주장이 "
            "성립한다."
        ),
        "bootstrap_cluster_unit": cluster_unit,
        "selection_scope": selection_scope,
        "selection_scope_unknown": not bool(selection_scope),
        "frozen_metric_id": STRUCTURAL_METRIC_V1["metric_id"],
        "interpretation": (
            "This is a conditional effect within the selected backbone subpopulation, "
            "not a population-average temperature effect. "
            "선택된 부분집단 안에서의 조건부 효과이며 전체 백본 집단의 평균 효과가 아니다."
            if selection_scope else
            "Selection scope was not recorded for this panel, so the conditional/marginal "
            "distinction cannot be made. 선정 범위가 기록되지 않아 조건부인지 주변부인지 "
            "구별할 수 없다."
        ),
    }


def _tail_masses(values: np.ndarray, clusters, *, n_boot: int = 20000, seed: int = 0) -> dict:
    """부트스트랩 분포에서 0 위/아래의 질량. 나머지는 정확히 0 인 재표집이다."""
    rng = np.random.default_rng(seed)
    n = len(values)
    means = np.array([values[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    return {
        "prob_above_zero": round(float((means > 0).mean()), 4),
        "prob_below_zero": round(float((means < 0).mean()), 4),
        "prob_exactly_zero": round(float((means == 0).mean()), 4),
        "tail_mass_note": (
            "백본별 차이가 1/n 격자 위에 있으면 부트스트랩 평균도 격자 위에 놓여, "
            "분위수 끝이 정확히 0 이 될 수 있다. 그 경우 'CI 가 0 을 포함' 은 "
            "'0 보다 큰 결과가 나올 수 있다' 를 뜻하지 않는다."
        ),
    }


def rmsd_provenance(rows) -> dict:
    """이 파일의 rmsd 컬럼이 어떤 정의로 계산되었는지 확인한다.

    1 차 패널의 원본 CSV 에는 rmsd_method 컬럼이 없다. 그 파일의 rmsd 는 전체 CA
    kabsch 값이고 동결 정의와 다르다. 표시하지 않으면 연속 endpoint 로 읽을 때
    구조 일치의 변화로 오해된다.
    """
    methods = sorted({
        str(r.get("rmsd_method") or "").strip()
        for r in rows if str(r.get("rmsd_method") or "").strip()
    })
    frozen = STRUCTURAL_METRIC_V1["rmsd"]["method"]
    if not methods:
        return {
            "method": "unknown_legacy", "methods_seen": [],
            "frozen_method": frozen, "matches_frozen_definition": False,
            "note": ("rmsd_method 컬럼이 없다. 이 파일은 동결 정의 이전에 만들어졌고 "
                     "rmsd 컬럼은 전체 CA kabsch 값이다. 동결 정의의 연속값으로 "
                     "읽으면 안 된다."),
        }
    return {
        "method": methods[0] if len(methods) == 1 else "mixed",
        "methods_seen": methods,
        "frozen_method": frozen,
        "matches_frozen_definition": methods == [frozen],
        "note": ("" if methods == [frozen] else
                 "동결 정의와 다르거나 여러 정의가 섞여 있다. rmsd 를 endpoint 로 "
                 "쓰기 전에 같은 정의로 다시 계산해야 한다."),
    }


def paired_continuous_difference(rows: list[dict], temp: str, field: str, *,
                                 cluster_unit: str = DEFAULT_CLUSTER_UNIT) -> dict:
    """연속 endpoint 의 짝지은 차이. 이진 통과율과 같은 클러스터 단위로 잰다.

    포화 계산을 하지 않는다 - 연속값에는 바닥도 천장도 없으므로 "움직일 수 없는
    관측" 이라는 개념이 적용되지 않는다. 그래서 이진 endpoint 가 0/1 에 깔려도
    이쪽은 여전히 정보를 준다.
    """
    by = defaultdict(lambda: defaultdict(list))
    for row in rows:
        value = row.get(field)
        if value is None or value == "":
            continue
        try:
            by[row[cluster_unit]][row["temperature"]].append(float(value))
        except (TypeError, ValueError):
            continue

    clusters, diffs = [], []
    for cluster, per_temp in by.items():
        if REFERENCE_T not in per_temp or temp not in per_temp:
            continue
        clusters.append(cluster)
        diffs.append(float(np.mean(per_temp[temp])) - float(np.mean(per_temp[REFERENCE_T])))

    if len(diffs) < 3:
        return {"point": round(float(np.mean(diffs)), 4) if diffs else None,
                "ci95": None, "cluster_unit": cluster_unit,
                "n_clusters_resampled": len(diffs), "insufficient_clusters": True,
                "endpoint_kind": "continuous"}

    values = np.asarray(diffs)
    out = clustered_bootstrap(clusters, lambda idx: float(values[idx].mean()))
    out["cluster_unit"] = cluster_unit
    out["n_clusters_resampled"] = len(diffs)
    out["endpoint_kind"] = "continuous"
    out.update(_tail_masses(values, clusters))
    return out


def stratify_by_source(rows: list[dict], temps: list[str]) -> dict:
    """온도 효과가 백본 소스에 따라 달라지는지 본다.

    native 에서만 재면 "온도를 올려도 안전하다"가 RFD3/BioEmu 백본에도 해당하는지
    알 수 없다. 소스가 하나뿐이면 층화 자체가 불가능하므로 그 사실을 남긴다.
    """
    sources = sorted({r.get("backbone_source", "target") for r in rows})
    if len(sources) < 2:
        return {"available": False, "sources": sources,
                "note": "소스가 하나뿐이라 층화 불가. wave 2/3 백본으로 sweep 확장 필요."}
    out: dict[str, object] = {"available": True, "sources": sources, "per_source": {}}
    for source in sources:
        subset = [r for r in rows if r.get("backbone_source", "target") == source]
        n_backbones = len({r["backbone_key"] for r in subset})
        entry: dict[str, object] = {
            "n_folds": len(subset),
            "n_backbones": n_backbones,
            # 백본이 몇 개 안 되는 소스의 결론은 탐색적이다. 확장 패널의 BioEmu 는
            # 4 개이고, 그 넷이 어느 방향으로 움직이든 확정적 결론이 될 수 없다.
            "exploratory_only": n_backbones < MIN_BACKBONES_FOR_CONFIRMATORY_SOURCE,
            "min_backbones_for_confirmatory": MIN_BACKBONES_FOR_CONFIRMATORY_SOURCE,
        }
        for temp in temps:
            if temp == REFERENCE_T:
                continue
            for field, label in (("_structural", "structural_yield"), ("_joint", "joint_yield")):
                entry[f"{label}@T{temp}"] = paired_yield_difference(subset, temp, field)
        out["per_source"][source] = entry
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "temperature_sweep"
    parser.add_argument("--af2", default=str(base / "af2_stage1.csv"))
    parser.add_argument("--out", default=str(base / "af2_analysis.json"))
    parser.add_argument("--cluster-unit", default=DEFAULT_CLUSTER_UNIT,
                        choices=["backbone_key", "target_id"],
                        help="백본이 타겟 안에 중첩되면 target_id 로 재표집해야 한다.")
    parser.add_argument("--panel", default="panel1_unfiltered",
                        help="리포트에 남길 패널 이름. 두 패널을 섞어 보고하지 않기 위해서다.")
    parser.add_argument("--compare-panel", default="",
                        help="다른 패널의 af2_analysis.json. 주면 두 패널이 같은 방향일 때만 "
                             "조건을 dominated 로 부른다.")
    parser.add_argument("--panel-manifest", default="",
                        help="동결된 선정 manifest. 있으면 적용 범위를 리포트에 옮겨 적는다.")
    args = parser.parse_args(argv)

    rows = annotate(load(Path(args.af2)))
    temps = sorted({r["temperature"] for r in rows}, key=float)
    print(f"folded={len(rows)} temperatures={temps} "
          f"backbones={len({r['backbone_key'] for r in rows})}\n")

    scope = ""
    if args.panel_manifest:
        manifest = json.loads(Path(args.panel_manifest).read_text(encoding="utf-8"))
        scope = manifest.get("interpretation_scope", "")
    report = {"n_folded": len(rows), "reference_temperature": REFERENCE_T,
              "ci_width_target": CI_WIDTH_TARGET, "per_temperature": {}, "comparisons": {}}
    report.update(build_report_header(panel=args.panel, cluster_unit=args.cluster_unit,
                                      selection_scope=scope))
    print(f"panel={args.panel} cluster_unit={args.cluster_unit}"
          + (f"\n적용 범위: {scope}" if scope else ""))

    print(f"{'T':>6s} {'n':>5s} {'structural_yield':>17s} {'joint_yield':>12s} {'SoluProt':>10s}")
    for temp in temps:
        subset = [r for r in rows if r["temperature"] == temp]
        def mean_of(field):
            vals = [r[field] for r in subset if r.get(field) is not None]
            return round(float(np.mean(vals)), 4) if vals else None
        entry = {"n": len(subset), "structural_yield": mean_of("_structural"),
                 "joint_yield": mean_of("_joint"), "soluprot": mean_of("_soluprot")}
        report["per_temperature"][temp] = entry
        print(f"{temp:>6s} {entry['n']:>5d} {str(entry['structural_yield']):>17s} "
              f"{str(entry['joint_yield']):>12s} {str(entry['soluprot']):>10s}")

    print(f"\n=== paired vs T={REFERENCE_T} (백본 clustered bootstrap) ===")
    for field, label in (("_structural", "structural_yield"), ("_joint", "joint_yield"),
                         ("_soluprot", "soluprot")):
        print(f"\n{label} (primary)" if field != "_soluprot" else f"\n{label} (secondary)")
        for temp in temps:
            if temp == REFERENCE_T:
                continue
            res = paired_yield_difference(rows, temp, field, cluster_unit=args.cluster_unit)
            res["next_step"] = decide_next_step(res)
            report["comparisons"][f"{label}@T{temp}"] = res
            ci = res.get("ci95")
            unc = res.get("uncertainty") or {}
            sat = res.get("saturation") or {}
            print(f"  T={temp}: diff={res.get('point')} CI{ci} "
                  f"clusters={res.get('n_backbones_paired')}"
                  f"(정보 {sat.get('n_informative')}/{sat.get('n_backbones')}) "
                  f"P(>0)={res.get('prob_above_zero')} P(<0)={res.get('prob_below_zero')} "
                  f"frac_backbone={unc.get('fraction_backbone')} "
                  f"({unc.get('verdict')}) -> {res['next_step']}")

    other = None
    if args.compare_panel:
        other = json.loads(Path(args.compare_panel).read_text(encoding="utf-8"))
    report["condition_dominance"] = condition_dominance(report, other_panel=other)
    dom = report["condition_dominance"]
    print(f"\n=== 조건 지배 판정 (기준 T={REFERENCE_T}) ===")
    print(f"  제거 검토 대상: {dom['dominated'] or '없음'}")
    if dom["insufficient_evidence"]:
        print(f"  근거 부족(정보 클러스터 < {dom['min_clusters_for_dominance']}): "
              f"{dom['insufficient_evidence']}")
    if dom["panels_disagree"]:
        print(f"  패널 간 불일치: {dom['panels_disagree']}")
    print(f"  {dom['recommendation']}")

    # 연속 endpoint. 이진 통과율이 0/1 에 깔려도 여기서는 정보가 남는다.
    provenance = rmsd_provenance(rows)
    report["rmsd_provenance"] = provenance
    print("\n=== 연속 endpoint (secondary) ===")
    if not provenance["matches_frozen_definition"]:
        print(f"  [주의] rmsd 컬럼: {provenance['note']}")
    report["continuous"] = {}
    for field in CONTINUOUS_ENDPOINTS:
        label = field.lstrip("_")
        if field == "rmsd" and not provenance["matches_frozen_definition"]:
            # 다른 정의로 잰 값을 동결 지표인 척 보고하지 않는다.
            report["continuous"]["rmsd_skipped"] = provenance
            print("\nrmsd: 동결 정의가 아니므로 건너뛴다")
            continue
        print(f"\n{label}")
        for temp in temps:
            if temp == REFERENCE_T:
                continue
            res = paired_continuous_difference(rows, temp, field,
                                               cluster_unit=args.cluster_unit)
            report["continuous"][f"{label}@T{temp}"] = res
            print(f"  T={temp}: diff={res.get('point')} CI{res.get('ci95')} "
                  f"clusters={res.get('n_clusters_resampled')} "
                  f"P(>0)={res.get('prob_above_zero')} P(<0)={res.get('prob_below_zero')}")

    report["by_source"] = stratify_by_source(rows, temps)
    if not report["by_source"].get("available"):
        print(f"\n소스 층화: {report['by_source']['note']}")
    else:
        print("\n=== 소스별 온도 효과 ===")
        for source, entry in report["by_source"]["per_source"].items():
            scope = " [탐색적 — 백본 부족]" if entry.get("exploratory_only") else ""
            print(f"  {source}: backbones={entry['n_backbones']} "
                  f"folds={entry['n_folds']}{scope}")
            for key, value in entry.items():
                if isinstance(value, dict) and value.get("ci95"):
                    print(f"    {key}: diff={value['point']} CI{value['ci95']}")

    steps = {v["next_step"] for k, v in report["comparisons"].items()
             if k.startswith(("structural_yield", "joint_yield"))}
    # 백본 확장이 필요하다는 신호가 하나라도 있으면 그것이 우선한다. 같은 백본에서
    # 서열만 늘리는 것은 백본이 병목일 때 아무것도 해결하지 못한다.
    for candidate in ("expand_backbones", "add_second_half", "stop_effect_confirmed"):
        if candidate in steps:
            report["overall_next_step"] = candidate
            break
    else:
        report["overall_next_step"] = "stop_no_effect"
    print(f"\nprimary endpoint 종합 판정: {report['overall_next_step']}")
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
