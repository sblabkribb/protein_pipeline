#!/usr/bin/env python3
"""P3. a3m -> conservation feature. 결측 규칙은 스펙 §4 에 동결돼 있다.

핵심 제약 두 개.
  - conservation 프로파일은 **타겟/reference 로 한 번** 계산된다. candidate 의
    AF2 결과나 Gate 2 label 에 따라 달라지는 항이 들어가면 leakage 다.
  - MSA 가 얕거나 없다고 test 타겟을 코호트에서 빼지 않는다. depth 로 타겟을
    걸러내면 그 자체가 selection 문제가 된다.

규칙 7 이 요구하는 것: candidate 별로 달라지는 것은 "그 candidate 의 변이가 보존
위치에 있는지" 뿐이고, 보존 프로파일 자체는 candidate 와 무관하다. 따라서 P3 는
타겟 수준 요약만 내면 안 되고 **tier 별 보존 위치 집합**도 내야 한다 - 타겟 수준
상수만으로는 백본 내부 순위를 만들 수 없다. 위치 집합을 쓰는 candidate 별
feature 조립은 Task 11 이 한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

#: 타겟 수준 conservation feature 이름. candidate 와 무관한 값만 둔다.
TARGET_FEATURES = ("cons_mean", "cons_p25", "cons_p75", "usable_hits_log10",
                   "coverage_median", "depth_median_log10")

#: `per_target` 행에 함께 실리지만 **feature 가 아닌** 이름.
#: 스펙 §4 규칙 6 이 `usable_hits` 를 `per_target` 에 그대로 기록하라고 하므로
#: 행에는 들어가지만 설계행렬로는 가지 않는다. `msa_low_depth` 는 지시자 열이고
#: 대치 대상이 아니다 - 대치하면 "얼마나 얕은가" 가 train 평균으로 번진다.
PER_TARGET_METADATA = ("usable_hits", "msa_low_depth")

#: 보존 tier. 배포 기본값과 같아야 하고 여기서 고르지 않는다.
TIERS = (0.3, 0.5, 0.7)

#: 저심도 문턱 (스펙 §4 규칙 6). `50_full_msa.py` 의 feasibility 기준과
#: `bio/a3m.msa_quality` 의 경고 경계에서 **상속**된 값이며 여기서 고르지 않는다.
LOW_DEPTH_MIN_USABLE_HITS = 10

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
MANIFEST_PATH = GRID / "holdout_msa_manifest.json"
OUT_PATH = GRID / "msa_features.json"


def _a3m():
    """배포의 a3m primitive 모듈. 보존·품질 정의는 여기 하나뿐이다.

    지연 import 다. `pipeline_mcp` 는 이 venv 에 설치돼 있지 않으므로 소스
    경로를 한 번 넣는다 - 이 모듈을 import 만 하는 테스트에 그 비용을 지우지
    않는다.
    """
    src = str(PROJECT_ROOT / "pipeline-mcp" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import pipeline_mcp.bio.a3m as a3m_mod
    return a3m_mod


def _defined(features: Mapping[str, float] | None) -> dict[str, float]:
    """정의된 값만 남긴다. Step 6 은 정의되지 않은 값을 **null 로** 쓴다.

    전부 null 인 행은 truthy dict 이므로 그대로 두면 "값이 있다" 분기로 들어가
    `float(None)` 에서 죽는다. 규칙 4 는 그 타겟을 **유지**하라고 하므로, 죽는
    것은 규칙 위반이다 - null 은 "없음" 으로 정규화한다.

    NaN·inf 도 "없음" 이다. `json.dumps` 는 기본값으로 bare `NaN` 을 쓰고
    `json.loads` 는 그것을 float 로 읽으므로, 정의되지 않은 값이 null 대신 NaN
    으로 저장되는 경로가 실재한다. 그것을 값으로 받으면 train 평균이 NaN 이 되어
    **모든 fold 의 모든 타겟**이 NaN 이 되는데 행은 `msa_undefined = 0` 이라고
    말한다. 스펙 §5 는 NaN 을 fail-closed 로 규정한다 - 고장이 잡음처럼 읽히지
    않게 하려는 것이 그 이유다.

    `TARGET_FEATURES` 에 없는 이름은 조용히 버리지 않고 거절한다. 조용히 버리면
    Step 6 의 오타 하나가 `msa_undefined = 0` 인 채로 사라진다.
    """
    if not features:
        return {}
    unknown = sorted(k for k in features if k not in TARGET_FEATURES)
    if unknown:
        raise ValueError(
            f"MSA feature 이름이 아니다: {unknown}. 아는 이름은 "
            f"{list(TARGET_FEATURES)} 뿐이다 - 조용히 버리면 오타가 정상값처럼 보인다."
        )
    out: dict[str, float] = {}
    for name, value in features.items():
        if value is None:
            continue
        number = float(value)
        if not math.isfinite(number):
            continue
        out[name] = number
    return out


def train_stats(train_by_target: Mapping[str, Mapping[str, float] | None]
                ) -> dict[str, float] | None:
    """train fold 의 feature 평균. 하나도 정의되지 않으면 None.

    None 은 "이 arm 을 non-evaluable 로 기록" 이라는 뜻이다. 타겟을 빼는 것이
    아니다 - 스펙 §4 규칙 5.

    평균은 **타겟 등가중**이다. 타겟마다 fold 수가 다르므로(144 vs 120) 행
    평균을 쓰면 타겟을 144:120 으로 가중하게 된다.
    """
    usable = [d for d in (_defined(v) for v in train_by_target.values()) if d]
    if not usable:
        return None
    out: dict[str, float] = {}
    for name in TARGET_FEATURES:
        vals = [v[name] for v in usable if name in v]
        if vals:
            out[name] = sum(vals) / len(vals)
    return out


def impute(target_id: str, features: Mapping[str, float] | None, *,
           train_stats: dict[str, float] | None) -> dict[str, float | list[str]]:
    """정의된 값은 그대로, 정의되지 않은 값은 train fold 평균 + 지시자 1.

    test 타겟이 전부 undefined 여도 타겟을 유지한다.

    train fold 에 통계가 없어 **측정된 값을 버려야 하는** 이름은
    `dropped_measured` 로 보고한다. arm 판정은 `arm_verdict()` 가 한다.
    """
    # 모듈 함수 train_stats() 와 이름이 겹치므로 아래에서는 stats 를 쓴다.
    # 인자 이름은 동결된 Step 2 테스트가 `train_stats=` 로 부르므로 못 바꾼다.
    stats = train_stats
    if stats is None:
        raise ValueError(
            f"{target_id}: train fold 에 정의된 MSA feature 가 없어 imputation "
            "statistic 을 만들 수 없다. 이 arm 은 non-evaluable 이다."
        )
    have = _defined(features)
    # 대치는 train fold 평균이 **있는** 이름으로만 한다. 통계가 없는 이름을 0.0
    # 같은 상수로 채우면 모든 타겟이 같은 값을 받아, 정보가 없는데도 측정값인
    # 것처럼 하류로 흐른다.
    names = [name for name in TARGET_FEATURES if name in stats]
    # 그런데 그 좁히기가 **측정된 값**까지 버릴 수 있다. 규칙 2 는 계산된
    # feature 를 그대로 쓰라고 하고, 규칙 5 는 그 경우를 arm non-evaluable 로
    # 기록하라고 한다. 조용히 좁아진 설계행렬로 평가하면 6 개 중 5 개를 잃은
    # arm 도 정상 arm 처럼 보인다 - 그래서 버린 이름을 반드시 남긴다.
    dropped = [name for name in TARGET_FEATURES if name in have and name not in stats]
    if have:
        out: dict[str, float | list[str]] = {name: have[name] for name in names
                                             if name in have}
        # 지시자는 **대치가 실제로 일어났는가**를 뜻한다 (스펙 §4 규칙 3).
        imputed = [name for name in names if name not in out]
        for name in imputed:
            out[name] = stats[name]
        out["msa_undefined"] = 1 if imputed else 0
    else:
        out = {name: stats[name] for name in names}
        out["msa_undefined"] = 1
    if dropped:
        out["dropped_measured"] = dropped
    return out


def arm_verdict(rows: Mapping[str, Mapping[str, object]], *,
                stats: Mapping[str, float] | None) -> dict[str, object]:
    """arm 수준 판정 - 스펙 §4 규칙 5. **타겟을 빼지 않는다.**

    두 조건이 arm 을 non-evaluable 로 만들고, 둘 다 arm 전체에 대한 판정이라
    `impute()` 안이 아니라 여기에 있다.

    1. **train fold 가 동결된 feature 를 정의하지 못했다** - 규칙 5 의 문자 그대로
       의 조건이다. 이것을 보려면 `stats` 가 필요하다: 그 feature 를 test 타겟도
       아무도 측정하지 않았으면 `dropped_measured` 는 비고, 행만 봐서는 설계행렬
       이 조용히 좁아진 것을 알 수 없다.
    2. **측정된 값을 버려야 했다** - 규칙 2 위반이다 (`dropped_measured`).
    """
    if stats is None:
        return {"evaluable": False,
                "reason": ("train fold 에 정의된 MSA feature 가 하나도 없어 "
                           "imputation statistic 을 만들 수 없다. 스펙 §4 규칙 5."),
                "undefined_in_train": list(TARGET_FEATURES),
                "dropped_measured_by_target": {}}
    undefined_in_train = [n for n in TARGET_FEATURES if n not in stats]
    dropped = {tid: list(row["dropped_measured"])
               for tid, row in rows.items() if row.get("dropped_measured")}
    if not undefined_in_train and not dropped:
        return {"evaluable": True}
    reasons = []
    if undefined_in_train:
        reasons.append(f"train fold 가 정의하지 못한 feature {undefined_in_train} "
                       "- 설계행렬에서 빠진다")
    if dropped:
        names = sorted({n for v in dropped.values() for n in v})
        reasons.append(f"train fold 에 imputation statistic 이 없어 측정값을 버린 "
                       f"feature {names} · 타겟 {sorted(dropped)}")
    return {
        "evaluable": False,
        "reason": " / ".join(reasons) + ". 스펙 §4 규칙 5.",
        "undefined_in_train": undefined_in_train,
        "dropped_measured_by_target": dropped,
    }


def conserved_positions(a3m: str, *, tiers: Sequence[float] = TIERS,
                        mode: str = "quantile",
                        manifest_sha256: Mapping[str, str] | None = None
                        ) -> tuple[dict[str, list[int]], bool | None]:
    """tier 별 보존 위치 집합을 **0-기반**으로 낸다. + manifest 해시 검증 결과.

    보존 정의는 배포의 `compute_conservation` 하나만 쓴다 - 새 보존 정의를
    만들지 않는다 (스펙 §4 규칙 7, 그리고 50_full_msa.py 의 `measure` 와 같은
    함수여야 값이 갈라지지 않는다).

    **인덱스 기준이 두 개다.** 배포는 위치를 1-기반으로 돌려주고, manifest 의
    `fixed_positions_sha256` 은 그 1-기반 목록을 해싱한 값이다. 계획서의 Step 6
    스키마는 0-기반을 요구한다. 그래서 검증은 1-기반 목록으로 하고 산출물에는
    0-기반으로 쓴다 - 둘을 섞으면 보존 마스크가 조용히 한 칸 밀린다.

    `manifest_sha256` 을 주지 않으면 검증 결과는 None 이다.
    """
    compute_conservation = _a3m().compute_conservation

    cons = compute_conservation(a3m, tiers=list(tiers), mode=mode, weights=None)
    one_based = {str(t): list(v) for t, v in cons.fixed_positions_by_tier.items()}
    zero_based = {t: [p - 1 for p in v] for t, v in one_based.items()}
    if manifest_sha256 is None:
        return zero_based, None
    verified = all(
        hashlib.sha256(json.dumps(one_based[t]).encode()).hexdigest()
        == manifest_sha256.get(t)
        for t in one_based
    )
    return zero_based, verified


def dump_features(payload: Mapping[str, object]) -> str:
    """msa_features.json 직렬화. **NaN 을 쓰지 않는다.**

    `json.dumps` 는 기본값으로 bare `NaN`/`Infinity` 를 쓰고 그것은 JSON 이
    아니다. 게다가 `json.loads` 는 그것을 float 로 되읽으므로, 정의되지 않은 값이
    null 대신 NaN 으로 저장되면 그 파일을 읽은 fold 의 train 평균이 전부 NaN 이
    된다. 정의되지 않은 값은 **null** 로 쓴다 - 여기서 터지는 것이 맞다
    (스펙 §5, fail-closed).
    """
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


# ---------------------------------------------------------------------------
# Step 6 - a3m 를 읽어 12 타겟 feature 를 만든다.
# ---------------------------------------------------------------------------


def feature_view(row: Mapping[str, object] | None) -> dict[str, object] | None:
    """`per_target` 행에서 **feature 만** 뽑는다. metadata 는 뺀다.

    `PER_TARGET_METADATA` 이름만 제외하고 나머지는 그대로 넘긴다 - 모르는 이름을
    여기서 걸러내면 `_defined()` 의 오타 가드가 무력해진다. 오타는 계속
    `impute()` 안에서 터져야 한다.
    """
    if row is None:
        return None
    return {k: v for k, v in row.items() if k not in PER_TARGET_METADATA}


def is_low_depth(usable_hits: object) -> int:
    """스펙 §4 규칙 6 의 저심도 지시자. 문턱은 상속된 값이다.

    **제외가 아니라 가시화**다 - 이 값으로 타겟을 코호트에서 빼지 않는다.
    usable_hits 를 알 수 없으면 저심도라고 단정하지 않는다(0).
    """
    if usable_hits is None:
        return 0
    return 1 if int(usable_hits) < LOW_DEPTH_MIN_USABLE_HITS else 0


def _log10(value: object) -> float | None:
    """log10. 정의되지 않으면 None 이다 - 0 이나 -inf 로 채우지 않는다."""
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        return None
    return math.log10(number)


def target_features(msa_quality: Mapping[str, object],
                    conservation_scores: Sequence[float]
                    ) -> dict[str, float | None]:
    """타겟 수준 MSA feature 6 개. 정의되지 않으면 **None** 이다.

    보존 분위수는 배포의 `_percentiles` 로 낸다 - manifest 의 coverage/depth
    분위수를 만든 바로 그 함수다. 여기서 두 번째 분위수 규칙을 만들면 같은
    이름의 값이 파일마다 다른 뜻이 된다.

    대치는 하지 않는다. imputation 은 LOTO train fold 평균이어야 하므로 fold
    안에서만 할 수 있다 (Task 11 Step 8b).
    """
    percentiles = _a3m()._percentiles
    cons = percentiles([float(s) for s in conservation_scores], [25, 50, 75])
    coverage = msa_quality.get("coverage") or {}
    depth = msa_quality.get("depth") or {}
    return {
        "cons_mean": None if cons is None else float(cons["mean"]),
        "cons_p25": None if cons is None else float(cons["p25"]),
        "cons_p75": None if cons is None else float(cons["p75"]),
        "usable_hits_log10": _log10(msa_quality.get("usable_hits")),
        "coverage_median": (None if coverage.get("p50") is None
                            else float(coverage["p50"])),
        "depth_median_log10": _log10(depth.get("p50")),
    }


def build_payload(manifest: Mapping[str, object], *,
                  project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    """manifest + a3m -> msa_features.json 페이로드.

    세 가지를 fail-closed 로 검사한다. 어느 하나가 어긋나도 **오류는 나지
    않고** S4 가 조용히 잡음을 재게 되기 때문이다.
      1. a3m 파일의 sha256 이 manifest 와 같은가 (같은 검색 결과인가).
      2. tier 별 보존 위치가 manifest 의 `fixed_positions_sha256` 과 같은가.
         검증은 **1-기반**으로 되돌려서 한다 - manifest 해시가 1-기반이다.
      3. a3m query 서열이 동결 WT(`_gate2d_cohort.FROZEN_WT`)와 같은가.
         `F_tier` 는 MSA query 축, `M_i` 는 WT 축이므로 이것이 같아야 교집합이
         의미를 갖는다 (스펙 §4 규칙 8, hard precondition).
    """
    import _gate2d as gate2d
    import _gate2d_cohort as cohort

    a3m_mod = _a3m()
    per_target: dict[str, dict[str, object]] = {}
    positions: dict[str, dict[str, list[int]] | None] = {}
    verified: dict[str, bool | None] = {}
    query_sha: dict[str, str] = {}
    query_seq: dict[str, str] = {}
    depth_profile: dict[str, dict[str, object]] = {}
    undefined: list[str] = []
    low_depth: list[str] = []
    problems: list[str] = []

    for entry in manifest["targets"]:
        target = entry["domain"]
        path = project_root / entry["a3m_path"]
        raw = path.read_bytes()
        got_sha = hashlib.sha256(raw).hexdigest()
        if got_sha != entry.get("a3m_sha256"):
            problems.append(f"{target}: a3m sha256 {got_sha[:16]} != manifest "
                            f"{str(entry.get('a3m_sha256'))[:16]}")
            continue
        text = raw.decode("utf-8", errors="replace")

        quality = entry.get("msa_quality") or {}
        cons = a3m_mod.compute_conservation(text, tiers=list(TIERS),
                                            mode="quantile", weights=None)
        zero_based, hash_ok = conserved_positions(
            text, manifest_sha256=(entry.get("conservation") or {}).get(
                "fixed_positions_sha256"))
        if hash_ok is not True:
            problems.append(f"{target}: 보존 위치가 manifest 의 "
                            "fixed_positions_sha256 과 다르다")
            continue

        features = target_features(quality, cons.scores)
        row: dict[str, object] = dict(features)
        row["usable_hits"] = quality.get("usable_hits")
        row["msa_low_depth"] = is_low_depth(quality.get("usable_hits"))
        per_target[target] = row
        positions[target] = zero_based
        verified[target] = hash_ok
        if row["msa_low_depth"]:
            low_depth.append(target)
        if not _defined(feature_view(row)):
            undefined.append(target)

        seq = a3m_mod._normalize_records(text)[0].sequence
        query_seq[target] = seq
        query_sha[target] = hashlib.sha256(seq.encode()).hexdigest()
        depth_profile[target] = {
            "usable_hits": quality.get("usable_hits"),
            "median_depth": (quality.get("depth") or {}).get("p50"),
            "median_coverage": (quality.get("coverage") or {}).get("p50"),
            "query_length": quality.get("query_length"),
            "classification": entry.get("classification"),
        }

    if problems:
        raise SystemExit("MSA provenance 가 manifest 와 어긋난다. 중단한다:\n  "
                         + "\n  ".join(problems))
    # 서열 축. 여기서 죽는 것이 맞다 - 어긋난 좌표에서 계산된 S4 는 오류 없이
    # 잡음을 잰다.
    cohort.assert_sequence_axis(query_seq)

    return {
        "purpose": ("P3 - 타겟 수준 MSA conservation feature. candidate 와 "
                    "무관하다."),
        "spec": "docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md",
        "source_manifest": "public_data/benchmark/gate0/holdout_grid/holdout_msa_manifest.json",
        "feature_names": list(TARGET_FEATURES),
        "per_target_metadata_names": list(PER_TARGET_METADATA),
        "per_target": per_target,
        "conserved_positions_0based": positions,
        "conserved_positions_sha256_verified": verified,
        "query_sequence_sha256": query_sha,
        "query_sequence_axis": (
            "12/12 a3m query 서열의 sha256 이 _gate2d_cohort.FROZEN_WT 와 일치한다. "
            "F_tier(MSA query 축)와 M_i(WT 축)가 같은 서열 위에 있다는 뜻이며, "
            "다르면 이 스크립트가 fail-closed 한다 (스펙 §4 규칙 8)."
        ),
        "undefined_targets": undefined,
        "low_depth": {
            "threshold": f"usable_hits < {LOW_DEPTH_MIN_USABLE_HITS}",
            "threshold_inherited_from": (
                "50_full_msa.py 의 feasibility 기준 · bio/a3m.msa_quality 의 경고 경계. "
                "여기서 새로 고르지 않는다 (스펙 §4 규칙 6)."
            ),
            "targets": sorted(low_depth),
            "n": len(low_depth),
            "depth_profile": depth_profile,
            "note": ("저심도 타겟도 코호트에 남는다. 지시자 msa_low_depth 로 "
                     "가시화할 뿐 제외하지 않는다. 분포가 사실상 이봉이므로"
                     "(3 · 46 · 866 · 3000×9) 문턱을 46 위로 올리지 않는다 - "
                     "그것은 결과를 본 뒤의 문턱 쇼핑이다."),
        },
        "note": ("undefined 타겟도 코호트에 남는다. 대치는 LOTO fold 안에서 "
                 "한다 (23_gate2d_prepare_msa_features.train_stats/impute)."),
        "conserved_positions_note": (
            "0-기반 인덱스. manifest 의 fixed_positions_sha256 은 1-기반 목록으로 "
            "계산된 값이므로, 검증할 때만 1-기반으로 되돌려 해시를 맞춘다. "
            "candidate 와 무관한 타겟 수준 값이다."),
        "conservation_settings": manifest.get("conservation"),
        "msa_settings": manifest.get("settings"),
        "msa_run_provenance": manifest.get("run_provenance"),
        "run_provenance": gate2d.run_provenance(
            "scripts/benchmark/23_gate2d_prepare_msa_features.py",
            "scripts/benchmark/_gate2d.py",
            "scripts/benchmark/_gate2d_cohort.py",
            "pipeline-mcp/src/pipeline_mcp/bio/a3m.py",
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    payload = build_payload(manifest)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_features(payload), encoding="utf-8")
    print(f"wrote {out}  targets {len(payload['per_target'])}  "
          f"undefined {len(payload['undefined_targets'])}  "
          f"low_depth {payload['low_depth']['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
