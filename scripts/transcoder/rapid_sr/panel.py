"""온도 실험용 informative backbone panel 선정.

왜 필요한가. 1차 온도 패널 15 개 중 12 개가 모든 온도에서 structural_yield
0.000 또는 1.000 이었다. 바닥과 천장에 붙은 백본은 온도가 영향을 주더라도
움직일 수 없으므로, 그 "차이 0" 은 합의가 아니라 정보 부재다. 그런데 클러스터
부트스트랩은 그것을 12 개의 합의로 세어 구간을 좁혔고, 판정이 뒤집혔다.

그래서 다음 패널은 **움직일 수 있는 백본** 으로 고른다.

선정에 쓰는 것과 쓰지 않는 것
-----------------------------
쓰는 것: 게이트 0 캠페인이 남긴 baseline joint/structural pass yield 와 그
yield 를 만든 서열 수, 백본 소스, 타겟.

쓰지 않는 것: 온도 sweep 의 어떤 결과도, global_score 도 쓰지 않는다. 선정에
평가 대상 정보를 넣으면 선정과 평가가 같은 데이터를 쓰게 된다. `forbid_columns`
로 그것을 코드에서 막는다.

무엇을 균형 잡는가
------------------
1. **yield 밴드** - 중간 대역 안에서도 한 구간에 몰리면 "온도 효과가 yield
   수준에 따라 다른가" 를 볼 수 없다.
2. **백본 소스** - native / RFD3 / BioEmu. 소스 층화는 1 차 패널에서 전부
   native 라 아예 불가능했다.
3. **타겟** - 같은 타겟에서 여러 백본을 뽑아도 클러스터 수는 늘지 않는다.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

#: joint yield 밴드. 열린 구간 (0,1) 을 네 개로 나눈다. 경계는 위쪽 포함이다.
YIELD_BANDS: tuple[tuple[float, float], ...] = (
    (0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0),
)

SELECTION_CRITERIA = {
    "baseline_only": True,
    "requires": ["joint_pass_yield", "af2_structural_pass_yield", "n_sequences_with_af2"],
    "exclude_saturated": "joint 와 structural 이 모두 (0,1) 열린 구간에 있어야 한다",
    #: 서열 4 개에서 나온 0.25 는 1/4 이다. yield 를 '중간' 이라 부르려면 그
    #: 추정이 표본 하나에 좌우되지 않을 만큼의 서열이 있어야 한다.
    "min_sequences_with_af2": 16,
    #: 17 개 타겟 중 6 개가 적격 백본을 3 개 이상 갖고 있어서, cap 2 는 상한을
    #: 23 으로 묶어 요청 범위(24-30) 아래로 떨어뜨린다. cap 3 은 28 을 낸다.
    #: 타겟 수는 어차피 17 이 상한이므로 이 완화는 클러스터를 늘리지 않고
    #: 타겟 안의 반복만 늘린다 - 그 사실을 manifest 에 적는다.
    "max_per_target": 3,
    #: 이 실험은 서열 하나를 단량체로 접는다. 다중 사슬 기준 구조에는 그 폴드를
    #: 맞춰볼 대상이 없고, RMSD 임계값도 의미를 잃는다. 구조에서만 나오는
    #: 기준이므로 온도 결과와 무관하다.
    "single_chain_only": True,
    #: AF2 비용은 대략 2.890 * L^0.748 초다. 백본당 8 서열 x 4 조건 = 32 폴드이므로
    #: 400 잔기면 백본 하나에 약 2.3 시간이다. 첫 동결에서 3428 잔기짜리가 뽑혀
    #: MPNN 호출이 타임아웃났다.
    "max_residues": 400,
    "yield_bands": [list(band) for band in YIELD_BANDS],
    "balances": ["yield_band", "backbone_source", "target_id"],
    "forbidden_inputs": ["global_score", "temperature", "af2_stage1", "sweep"],
}

SELECTION_INPUTS = (
    "joint_pass_yield", "af2_structural_pass_yield",
    "n_sequences_with_af2", "backbone_source", "target_id", "backbone_key",
)


def yield_band(value: float | None) -> int | None:
    """이 yield 가 속한 밴드 index. 포화값(0 또는 1)은 밴드가 없다."""
    if value is None:
        return None
    v = float(value)
    if not 0.0 < v < 1.0:
        return None
    for index, (low, high) in enumerate(YIELD_BANDS):
        if low < v <= high:
            return index
    return None


def saturation_risk(p: float, *, n_per_condition: int = 8, n_conditions: int = 4) -> float:
    """이 백본이 모든 조건에서 전부 실패하거나 전부 성공할 확률.

    baseline yield 가 (0,1) 안에 있어도 8 서열 패널에서는 다시 포화될 수 있다.
    p=0.05 면 32 번 뽑아 한 번도 성공하지 않을 확률이 무시할 수 없다. 밴드를
    고르게 덮으라는 요구와 정보량 사이의 거래를 숨기지 않고 숫자로 남긴다.

    독립 베르누이를 가정한다. 같은 백본의 설계는 완전히 독립이 아니므로 이
    값은 위험의 **하한** 이다.
    """
    trials = int(n_per_condition) * int(n_conditions)
    p = float(p)
    return (1.0 - p) ** trials + p ** trials


def _float_or_none(raw) -> float | None:
    if raw in (None, "", "None"):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def eligible_backbones(rows, *, criteria: dict | None = None, structure_info=None) -> list[dict]:
    """baseline 과 구조만 보고 움직일 수 있는 백본을 고른다. 입력 순서를 지킨다.

    `structure_info(row) -> {"n_chains": int, "n_residues": int}` 를 주면 사슬 수와
    크기로도 거른다. 주지 않으면 그 기준은 건너뛴다 - 없는 정보를 추측하지 않는다.
    """
    spec = criteria or SELECTION_CRITERIA
    minimum = int(spec["min_sequences_with_af2"])
    out = []
    for row in rows:
        if structure_info is not None:
            info = structure_info(row) or {}
            if spec.get("single_chain_only") and int(info.get("n_chains", 1)) != 1:
                continue
            if int(info.get("n_residues", 0)) > int(spec["max_residues"]):
                continue
        joint = _float_or_none(row.get("joint_pass_yield"))
        struct = _float_or_none(row.get("af2_structural_pass_yield"))
        n = _float_or_none(row.get("n_sequences_with_af2"))
        if joint is None or struct is None or n is None:
            continue
        if n < minimum:
            continue
        # 두 endpoint 모두 열린 구간이어야 한다. 하나만 중간이면 나머지
        # endpoint 는 여전히 못 움직인다.
        if not (0.0 < joint < 1.0 and 0.0 < struct < 1.0):
            continue
        out.append(row)
    return out


def select_panel(
    rows,
    *,
    target_size: int = 27,
    seed: int = 0,
    criteria: dict | None = None,
    forbid_columns: tuple[str, ...] = (),
    structure_info=None,
) -> list[dict]:
    """밴드 → 소스 → 타겟 순으로 라운드로빈해서 패널을 고른다.

    난수를 쓰지 않는다. `seed` 는 동점 처리에만 들어가며, 같은 입력이면 같은
    목록이 나온다 - 동결해서 실행 전에 고정할 수 있어야 하기 때문이다.
    """
    if forbid_columns:
        present = sorted({c for row in rows for c in forbid_columns if c in row})
        if present:
            raise ValueError(
                f"선정 입력에 금지된 컬럼이 있다: {present}. "
                "온도 이후 정보를 선정에 쓰면 선정과 평가가 같은 데이터를 쓴다."
            )

    spec = criteria or SELECTION_CRITERIA
    pool = eligible_backbones(rows, criteria=spec, structure_info=structure_info)
    if not pool:
        return []
    if structure_info is not None:
        for row in pool:
            row.setdefault("_structure", structure_info(row) or {})

    max_per_target = int(spec["max_per_target"])

    def sort_key(row):
        # 결정적 정렬. seed 는 동점을 흔드는 데만 쓴다.
        digest = hashlib.sha256(f"{seed}:{row['backbone_key']}".encode()).hexdigest()
        return (row["backbone_key"], digest)

    # 밴드 -> 소스 -> 후보 목록
    buckets: dict[int, dict[str, list[dict]]] = {}
    for row in sorted(pool, key=sort_key):
        band = yield_band(_float_or_none(row.get("joint_pass_yield")))
        if band is None:
            continue
        buckets.setdefault(band, {}).setdefault(row["backbone_source"], []).append(row)

    picked: list[dict] = []
    per_target: dict[str, int] = {}
    per_band: dict[int, int] = {}
    per_source: dict[str, int] = {}

    def take(row) -> None:
        picked.append(row)
        per_target[row["target_id"]] = per_target.get(row["target_id"], 0) + 1
        band = yield_band(_float_or_none(row.get("joint_pass_yield")))
        per_band[band] = per_band.get(band, 0) + 1
        per_source[row["backbone_source"]] = per_source.get(row["backbone_source"], 0) + 1
        for sources in buckets.values():
            for candidates in sources.values():
                if row in candidates:
                    candidates.remove(row)

    # 라운드로빈. 매 바퀴 가장 적게 뽑힌 밴드부터, 그 안에서 가장 적게 뽑힌
    # 소스부터, 그 안에서 가장 적게 쓰인 타겟부터 고른다. 희소한 소스가
    # 굶지 않는 이유는 소스 순서가 뽑힌 수로 정해지기 때문이다.
    while len(picked) < target_size:
        candidates_this_round = []
        for band in sorted(buckets, key=lambda b: (per_band.get(b, 0), b)):
            sources = buckets[band]
            for source in sorted(sources, key=lambda s: (per_source.get(s, 0), s)):
                available = [
                    row for row in sources[source]
                    if per_target.get(row["target_id"], 0) < max_per_target
                ]
                if available:
                    available.sort(key=lambda row: (per_target.get(row["target_id"], 0),
                                                    row["backbone_key"]))
                    candidates_this_round.append((band, source, available[0]))
                    break
            if candidates_this_round:
                break
        if not candidates_this_round:
            break
        take(candidates_this_round[0][2])

    return picked


def build_manifest(picked, *, source_path: Path, seed: int, source_sha256: str) -> dict:
    """실행 전에 동결할 선정 기록.

    목록만 남기면 나중에 "왜 이 백본인가" 에 답할 수 없다. 기준, seed, 입력
    파일의 해시, 그리고 각 백본을 뽑히게 한 yield 를 함께 남긴다.
    """
    entries = []
    for row in picked:
        joint = _float_or_none(row.get("joint_pass_yield"))
        entries.append({
            "backbone_key": row["backbone_key"],
            "target_id": row["target_id"],
            "backbone_source": row["backbone_source"],
            "pdb_file": row.get("pdb_file", ""),
            "baseline_joint_yield": joint,
            "baseline_structural_yield": _float_or_none(row.get("af2_structural_pass_yield")),
            "n_sequences_with_af2": int(float(row.get("n_sequences_with_af2") or 0)),
            "yield_band": yield_band(joint),
            "saturation_risk": round(saturation_risk(joint), 4) if joint is not None else None,
            "n_residues": int((row.get("_structure") or {}).get("n_residues", 0)) or None,
            "n_chains": int((row.get("_structure") or {}).get("n_chains", 0)) or None,
        })

    def distribution(key):
        out: dict[str, int] = {}
        for entry in entries:
            out[str(entry[key])] = out.get(str(entry[key]), 0) + 1
        return dict(sorted(out.items()))

    return {
        "schema": "rapid.temperature_panel/1",
        "frozen": True,
        "seed": seed,
        "source_file": str(source_path),
        "source_sha256": source_sha256,
        "criteria": SELECTION_CRITERIA,
        "selection_inputs": list(SELECTION_INPUTS),
        "selection_excludes": (
            "온도 sweep 결과와 global_score 는 선정에 쓰이지 않았다. 선정은 게이트 0 "
            "캠페인의 baseline yield 만 본다."
        ),
        "interpretation_scope": (
            "이 패널은 baseline yield 가 중간인 백본만 담는다. 따라서 여기서 나온 온도 "
            "효과는 전체 백본 집단의 평균 효과가 아니라, 온도가 영향을 줄 수 있는 "
            "중간-yield 영역에서의 조건부 효과다."
        ),
        "n_selected": len(entries),
        #: 백본이 타겟 안에 중첩되므로 독립 클러스터 수는 타겟 수다. 백본으로
        #: 재표집하면 1 차 패널의 포화 오류와 같은 종류로 정밀도를 과장한다.
        "n_effective_clusters": len({e["target_id"] for e in entries}),
        "bootstrap_cluster_unit": "target_id",
        "cluster_note": (
            "1 차 패널은 백본 15 개가 곧 타겟 15 개여서 backbone_key 로 재표집해도 "
            "같았다. 이 패널은 한 타겟에서 최대 3 개를 뽑으므로 target_id 로 "
            "재표집해야 한다."
        ),
        "expected_af2_folds": len(entries) * 4 * 8,
        "expected_af2_worker_seconds": round(sum(
            4 * 8 * 2.890344 * (e["n_residues"] ** 0.748)
            for e in entries if e.get("n_residues")), 0),
        "af2_cost_note": (
            "폴드당 2.890344 * L^0.748 초 (af2_length_scaling.json 적합). 워커 4 개를 "
            "쓰면 실측 실효 속도는 그보다 빠르다."
        ),
        "expected_saturated_backbones": round(
            sum(e["saturation_risk"] or 0.0 for e in entries), 2),
        "expected_informative_backbones": round(
            len(entries) - sum(e["saturation_risk"] or 0.0 for e in entries), 2),
        "saturation_risk_note": (
            "8 서열 x 4 조건에서 전부 실패하거나 전부 성공할 확률. 설계 간 독립을 "
            "가정하므로 실제 위험의 하한이다."
        ),
        "backbones": entries,
        "band_distribution": distribution("yield_band"),
        "source_distribution": distribution("backbone_source"),
        "target_distribution": distribution("target_id"),
    }


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_manifest(manifest: dict, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
