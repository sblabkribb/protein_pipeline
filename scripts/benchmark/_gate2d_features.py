"""Gate 2 의 feature ladder. arm 목록은 스펙 §4 에서 동결됐다.

S6 하나가 판정 arm 이다. 나머지는 ablation/descriptive 이며 GO 판정에 쓰지 않는다 -
endpoint 가 하나여도 arm 을 골라 GO 를 선언하면 model selection multiplicity 다.

**S0-S6 전부 구현돼 있다** (2026-09-11, MSA 12/12 완료). S4-S6 는
`holdout_grid/msa_features.json` 을 읽는다.

측정 primitive 는 `_gate2d.py` 에 있고 여기서 다시 만들지 않는다. 서열/코호트
로딩은 `_gate2d_cohort.py`, WT 서열 파싱과 변이 위치는 `22_gate2d_prepare_esm.py`,
**MSA 대치는 `23_gate2d_prepare_msa_features.py` 의 `train_stats`/`impute`/
`arm_verdict` 가 유일한 구현**이다. 여기서 두 번째 대치 규칙을 만들지 않는다.

S4 의 본체는 **candidate 별로 달라지는** conservation burden 이다 (스펙 §4
규칙 8). 타겟 수준 요약만 넣으면 같은 타겟의 24 설계가 동일한 행을 받고, Gate 2 는
백본 **내부** 순위 문제이므로 순위가 원리상 만들어지지 않는다.

**변이 위치는 서열 비교에서만 온다.** "차이가 0 이 아닌 곳" 을 마스크로 쓰지
않는다 - S3 이 그 방식으로 S2 의 복제가 되어 무너진 전례가 있다.
"""

from __future__ import annotations

import csv
import importlib
import json
import os
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np

#: 순서 고정. 사후에 arm 을 추가하지 않는다.
ARMS = ("S0", "S1", "S2", "S3", "S4", "S5", "S6")

#: 판정 arm. Gate 2 GO/NO-GO 는 이 arm 하나로만 낸다.
PRIMARY_ARM = "S6"

ARM_LABELS = {
    "S0": "SoluProt",
    "S1": "raw ESM mean",
    "S2": "dESM_global",
    "S3": "dESM_mutation_site",
    "S4": "MSA_conservation",
    "S5": "dESM_mut + MSA",
    "S6": "dESM_mut + MSA + existing cheap features",
}

ARM_STATUS = {
    "S0": "measured_reference",
    "S1": "known_null",
    "S2": "untested_low_expectation",
    "S3": "new_hypothesis",
    "S4": "new_hypothesis",
    "S5": "new_hypothesis",
    "S6": "primary",
}

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
DATA = PROJECT_ROOT / "data" / "benchmark"
GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"

#: arm 별 feature 블록. assemble 이 이 목록을 이어붙인다.
ARM_BLOCKS = {
    "S0": ("soluprot",),
    "S1": ("esm_mean",),
    "S2": ("esm_delta_global",),
    "S3": ("esm_delta_mut",),
    "S4": ("msa",),
    "S5": ("esm_delta_mut", "msa"),
    "S6": ("esm_delta_mut", "msa", "cheap", "mpnn_score"),
}

#: 2026-09-11 이전 실행의 S6. 격자에 per-sequence MPNN score 열이 없어 cheap 이
#: 조성 전용이었고, 그래서 S6 가 S5 와 bit-for-bit 같아졌다 (Δ_Top4 −0.0366,
#: LCB −0.0854). 그 실행은 PRIMARY DEVIATION 으로 기록됐다. **arm 이 아니다** -
#: 동결된 ladder 는 S0-S6 일곱 개이고 여기서 여덟 번째를 만들지 않는다. 같은 arm 의
#: 구현 결함판이며 planned-S6 와 나란히 보고하기 위해서만 존재한다.
REALIZED_S6_BLOCKS_2026_09_11 = ("esm_delta_mut", "msa", "cheap")

#: LOTO fold 마다 다시 만들어야 하는 블록. 대치 통계량이 train fold 에서 나오므로
#: fold 에 의존한다. 나머지 블록(ΔESM·조성·SoluProt·MSA 의 candidate 성분)은
#: fold 와 무관하다.
FOLD_DEPENDENT_BLOCKS = frozenset({"msa"})

#: MSA 블록의 **candidate 별** 열. fold 에 의존하지 않는다 - 보존 프로파일은
#: 타겟/reference 로 한 번 계산되고 (스펙 §4 규칙 8), candidate 별로 달라지는
#: 것은 "그 candidate 의 변이가 보존 위치에 있는지" 뿐이다.
CANDIDATE_MSA_FEATURES = ("cons_burden_0.3", "cons_burden_0.5", "cons_burden_0.7",
                          "mut_fraction", "cons_burden_undefined")

#: 보존 tier. `msa_features.json` 의 키와 같아야 한다.
BURDEN_TIERS = ("0.3", "0.5", "0.7")


def loto_splits(targets: Sequence[str]) -> Iterator[tuple[list[int], list[int], str]]:
    """Leave-One-Target-Out. 같은 타겟이 train 과 test 에 동시에 들어가지 않는다.

    백본을 쪼개지 않는 것은 타겟을 쪼개지 않는 데서 따라온다 - 백본은 타겟 안에
    중첩돼 있다.
    """
    for held in sorted(set(targets)):
        train = [i for i, t in enumerate(targets) if t != held]
        test = [i for i, t in enumerate(targets) if t == held]
        yield train, test, held


def _load_sequences() -> dict[str, str]:
    with (GRID / "sequences.csv").open(encoding="utf-8") as handle:
        return {r["sequence_id"]: r["sequence"] for r in csv.DictReader(handle)}


SEQ_OF = _load_sequences()


def _esm_prep():
    """P2 모듈. `mutation_sites` 와 `wt_sequence_from_pdb` 의 유일한 구현이다.

    지연 import 다 - 모듈 상단에서 torch/transformers 를 끌어오면 이 모듈을
    쓰는 모든 테스트가 그 비용을 낸다.
    """
    return importlib.import_module("22_gate2d_prepare_esm")


def wt_by_target() -> dict[str, str]:
    """타겟 WT 서열. `assert_sequence_axis` 의 입력이자 변이 위치의 기준축이다.

    ΔESM 의 reference 는 타겟 WT 서열이다. label 이 아니라 입력이므로 LOTO 를
    위배하지 않는다 (스펙 §4).
    """
    prep = _esm_prep()
    index = json.loads((DATA / "gate2d_esm.index.json").read_text(encoding="utf-8"))
    return {t: prep.wt_sequence_from_pdb(prep.NATIVE_PDB_DIR / f"{t}.pdb")
            for t in index["targets"]}


def _load_esm() -> tuple[np.ndarray, np.ndarray, dict, dict]:
    index = json.loads((DATA / "gate2d_esm.index.json").read_text(encoding="utf-8"))
    designs = np.load(DATA / "gate2d_esm_8m_designs.npy")
    wt = np.load(DATA / "gate2d_esm_8m_wt.npy")
    row_of = {sid: i for i, sid in enumerate(index["sequence_ids"])}
    wt_of = {t: i for i, t in enumerate(index["targets"])}
    return designs, wt, row_of, wt_of


def _delta_mut_block(folds) -> np.ndarray:
    """ΔESM_mut: **변이 위치**의 토큰 임베딩 차이 평균 + 결측 지시자 1 열.

    변이 위치는 `mutation_sites(WT, design)` 즉 **서열 비교**에서 온다. 임베딩
    차이가 0 이 아닌 위치를 쓰면 안 된다 - ESM 토큰은 문맥 의존이므로 잔기 하나가
    바뀌어도 전 위치의 임베딩이 달라지고, 그러면 전 위치의 평균 = mean-pool(design)
    − mean-pool(WT) 가 되어 **S3 이 S2(ΔESM_global)의 복제로 붕괴한다.**
    (이 코호트에서 확인: 임베딩 기준 "변이" 위치는 160/160 이다.)

    위치 대응이 불가한 설계(WT 와 길이가 다름)는 스펙 §4 결측 규칙에 따라 채운
    값 + 지시자로 들어간다. **타겟을 빼지 않는다.** 채움값은 0 벡터다: 지시자
    열이 함께 있으므로 0 채움과 평균 채움은 같은 예측기 족을 만든다
    (w·(x+1_miss·μ) + c·1_miss = w·x + 1_miss·(w·μ + c)). 다른 것은 L2 벌점의
    배분뿐이고, 이 코호트에서는 도달 자체가 불가하다 - 길이가 다른 48 설계는
    af2 correspondence 가 거부되어 사용가능 폴드 1,680 에 들어 있지 않다.
    """
    prep = _esm_prep()
    _designs, _wt, row_of, _wt_of = _load_esm()
    wt_seq = wt_by_target()

    rows: list[np.ndarray] = []
    flags: list[float] = []
    with np.load(DATA / "gate2d_esm_8m_tokens.npz") as tokens:
        for fold in folds:
            design_tokens = tokens[f"d{row_of[fold.sequence_id]}"]
            wt_tokens = tokens[f"w_{fold.target_id}"]
            try:
                sites = prep.mutation_sites(wt_seq[fold.target_id],
                                            SEQ_OF[fold.sequence_id])
            except ValueError:
                # 길이 불일치 - 위치 대응이 성립하지 않는다. 규칙 3/4.
                rows.append(np.zeros(design_tokens.shape[1], dtype=float))
                flags.append(1.0)
                continue
            if design_tokens.shape[0] != wt_tokens.shape[0]:
                rows.append(np.zeros(design_tokens.shape[1], dtype=float))
                flags.append(1.0)
                continue
            diff = design_tokens[sites] - wt_tokens[sites] if sites else None
            rows.append(diff.mean(axis=0) if diff is not None
                        else np.zeros(design_tokens.shape[1], dtype=float))
            flags.append(0.0)
    return np.hstack([np.vstack(rows).astype(float),
                      np.array(flags, dtype=float).reshape(-1, 1)])


def _msa_prep():
    """P3 모듈. `train_stats`/`impute`/`arm_verdict` 의 **유일한** 구현이다.

    대치를 여기서 다시 쓰지 않는다 - 행렬 수준 열평균과 dict 수준 타겟평균이
    따로 있으면 둘이 갈라지고, 행평균은 타겟을 144:120 으로 가중한다.
    """
    return importlib.import_module("23_gate2d_prepare_msa_features")


_MSA_FEATURES: dict | None = None


def load_msa_features() -> dict:
    """`msa_features.json`. 한 번만 읽는다.

    없으면 그대로 터진다. `non_evaluable` 로 적지 않는다 - 그 상태는 스펙 §4
    규칙 5 의 **데이터에 대한 판정**이고, 입력 파일이 없는 것은 파이프라인
    오류다. 섞으면 나중에 진짜 규칙 5 사례와 구분되지 않는다.
    """
    global _MSA_FEATURES
    if _MSA_FEATURES is None:
        path = GRID / "msa_features.json"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} 가 없다. 먼저 23_gate2d_prepare_msa_features.py 를 돌린다."
            )
        _MSA_FEATURES = json.loads(path.read_text(encoding="utf-8"))
    return _MSA_FEATURES


def conservation_burden(mut_sites: Sequence[int],
                        conserved: dict[str, Sequence[int]]) -> list[float]:
    """바뀐 위치 중 보존 위치의 비율. tier 별로 하나씩.

    "point mutation 이 보존 위치를 건드렸는가" 가 아니다 - 이 코호트의 |M_i| 는
    중앙값 약 135 로 서열의 절반이 넘으므로 격자 설계는 사실상 재설계다. 따라서
    "바뀐 위치 중 보존 위치의 비율" 이다 (스펙 §4 규칙 8 의 용어 주의).

    **두 인덱스는 모두 0-기반이다.** `mut_sites` 는 `mutation_sites` 의
    `enumerate` 기반 출력이고, `conserved` 는 `msa_features.json` 의
    `conserved_positions_0based` 다. 섞으면 마스크가 한 칸 밀리고 교집합은
    **아무 오류도 내지 않으면서** 잡음을 잰다.
    """
    m = set(int(p) for p in mut_sites)
    denom = max(len(m), 1)
    return [len(m & {int(p) for p in conserved[tier]}) / denom
            for tier in BURDEN_TIERS]


def _msa_candidate_block(folds) -> np.ndarray:
    """MSA 블록의 candidate 성분. fold 와 무관하므로 캐시된다.

    열: `CANDIDATE_MSA_FEATURES`.

    변이 위치는 `22_gate2d_prepare_esm.mutation_sites(WT, design)` 하나만 쓴다 -
    **서열 비교**다. 위치 대응이 불가하거나(길이 불일치) 보존 프로파일이 없는
    행은 채운 값 + `cons_burden_undefined = 1` 로 들어간다. **타겟을 빼지
    않는다** (스펙 §4 규칙 3-4).
    """
    prep = _esm_prep()
    conserved_by_target = load_msa_features()["conserved_positions_0based"]
    wt_seq = wt_by_target()

    rows: list[list[float]] = []
    for fold in folds:
        conserved = conserved_by_target.get(fold.target_id)
        reference = wt_seq[fold.target_id]
        if not conserved:
            rows.append([0.0, 0.0, 0.0, 0.0, 1.0])
            continue
        try:
            sites = prep.mutation_sites(reference, SEQ_OF[fold.sequence_id])
        except ValueError:
            # 길이 불일치 - 위치 대응이 성립하지 않는다. 규칙 3/4.
            rows.append([0.0, 0.0, 0.0, 0.0, 1.0])
            continue
        rows.append([*conservation_burden(sites, conserved),
                     len(sites) / max(len(reference), 1), 0.0])
    return np.array(rows, dtype=float)


def _msa_train_stats(per_target: dict, row_targets: Sequence[str],
                     train_idx: Sequence[int]) -> dict[str, float] | None:
    """train **타겟** 등가중 대치 통계량. 행 평균이 아니다.

    MSA feature 는 타겟 수준 상수이고 타겟마다 행 수가 120/144 로 다르므로 행
    평균은 타겟을 불균등 가중한다 - 백본 등가중 vs 타겟 등가중과 같은 오류다.
    """
    prep = _msa_prep()
    train_targets = sorted({row_targets[i] for i in train_idx})
    return prep.train_stats({t: prep.feature_view(per_target.get(t))
                             for t in train_targets})


def _active_target_names(stats: dict[str, float] | None,
                         feature_names: Sequence[str]) -> list[str]:
    """설계행렬에 실제로 들어가는 타겟 수준 열 이름."""
    if stats is None:
        return []
    return [n for n in feature_names if n in stats] + ["msa_undefined",
                                                       "msa_low_depth"]


def impute_msa_block(per_target: dict, row_targets: Sequence[str],
                     train_idx: Sequence[int], feature_names: Sequence[str]
                     ) -> tuple[np.ndarray | None, dict | None]:
    """fold 별 MSA 타겟 블록. train **타겟** 등가중으로 대치한다.

    `(행렬, 결함)` 을 돌려준다 - `assemble` 과 같은 계약이다. 행렬이 None 이면
    arm 이 non-evaluable 이고, **타겟을 빼는 것이 아니다** (스펙 §4 규칙 5).

    대치 통계량과 arm 판정은 P3 의 `train_stats`/`impute`/`arm_verdict` 하나만
    쓴다. 여기서 두 번째 구현을 만들지 않는다.

    마지막 두 열은 지시자다.
      - `msa_undefined` : 대치가 실제로 일어났는가 (규칙 3).
      - `msa_low_depth` : `usable_hits < 10` (규칙 6). **대치하지 않는다** -
        depth 는 설계가 존재하기 전에 측정되는 homolog record 의 속성이고,
        train 평균으로 번지면 "얼마나 얕은가" 가 다른 타겟으로 새어 나간다.
    """
    prep = _msa_prep()
    stats = _msa_train_stats(per_target, row_targets, train_idx)
    if stats is None:
        return None, None   # arm non-evaluable - 규칙 5. 타겟을 빼지 않는다.

    rows_by_target = {t: prep.impute(t, prep.feature_view(per_target.get(t)),
                                     train_stats=stats)
                      for t in sorted(set(row_targets))}

    # 규칙 5 는 per-feature 조건에 **arm 수준** 결과를 붙인다. 그 판정은
    # arm_verdict() 하나에만 있다 - 여기서 다시 구현하지 않는다.
    verdict = prep.arm_verdict(rows_by_target, stats=stats)
    if not verdict["evaluable"]:
        return None, verdict

    names = _active_target_names(stats, feature_names)
    low_depth = {t: prep.is_low_depth((per_target.get(t) or {}).get("usable_hits"))
                 for t in rows_by_target}
    values = {t: [float(rows_by_target[t][n]) for n in names[:-1]]
                 + [float(low_depth[t])]
              for t in rows_by_target}
    return np.array([values[t] for t in row_targets], dtype=float), None


def active_msa_feature_names(folds, train_idx: Sequence[int]) -> list[str]:
    """이 fold 의 MSA 설계행렬 열 이름. 결과 JSON 에 fold 마다 남긴다.

    어떤 fold 에서 어떤 MSA 열이 빠졌는지 재현할 수 없으면 narrowing 을 감사할
    수 없다.
    """
    feats = load_msa_features()
    stats = _msa_train_stats(feats["per_target"],
                             [f.target_id for f in folds], train_idx)
    return list(CANDIDATE_MSA_FEATURES) + _active_target_names(
        stats, feats["feature_names"])


def _msa_block(folds, train_idx: Sequence[int] | None
               ) -> tuple[np.ndarray | None, dict | None]:
    """MSA 블록 = candidate 성분(캐시) + fold 별 타겟 성분."""
    if train_idx is None:
        raise ValueError(
            "MSA 블록은 train fold 없이 만들 수 없다. 대치 통계량은 LOTO train "
            "fold 의 타겟 평균이어야 하므로 fold 안에서만 정의된다 (스펙 §4 규칙 3). "
            "코호트 전체를 train 으로 쓰면 그것이 누수다."
        )
    feats = load_msa_features()
    target_block, defect = impute_msa_block(
        feats["per_target"], [f.target_id for f in folds], train_idx,
        feats["feature_names"])
    if target_block is None:
        return None, defect
    return np.hstack([_block("msa_candidate", folds), target_block]), None


def load_mpnn_scores() -> dict[str, float]:
    """격자 폴드의 per-sequence ProteinMPNN score. 유일한 구현은 P4 스크립트다.

    `27_gate2d_prepare_mpnn_scores.py` 가 만든 산출물을 읽는다. 그 산출물이 없으면
    **조용히 열을 빼지 않는다** - S6 가 판정 arm 이므로 스펙보다 좁은 S6 가 소리
    없이 다시 실행되는 것이 정확히 PRIMARY DEVIATION 을 만든 경로다.
    """
    path = GRID / "mpnn_scores.json"
    if not path.exists():
        raise SystemExit(
            f"{path} 가 없다. S6 의 cheap 블록은 스펙 §4 에서 '조성, MPNN score' 로 "
            "동결됐다. 먼저 27_gate2d_prepare_mpnn_scores.py 를 돌린다 - 열을 빼고 "
            "S6 를 돌리면 판정 arm 이 스펙보다 좁아진다."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k: float(v) for k, v in payload["scores"].items()}


def _mpnn_score_block(folds) -> np.ndarray:
    """MPNN score 1 열. 잔기당 평균 NLL 이므로 낮을수록 그럴듯하다.

    결측을 대치하지 않는다 - 격자의 모든 폴드에 score 가 있어야 하고, 없으면
    어느 서열이 빠졌는지 말하고 멈춘다.
    """
    scores = load_mpnn_scores()
    missing = [f.sequence_id for f in folds if f.sequence_id not in scores]
    if missing:
        raise SystemExit(
            f"MPNN score 결측 {len(missing)} 건 (예: {missing[:3]}). 대치하지 않는다."
        )
    return np.array([[scores[f.sequence_id]] for f in folds], dtype=float)


def _build_block(name: str, folds) -> np.ndarray:
    """이름 하나에 해당하는 feature 블록. 행 순서는 folds 와 같다."""
    if name == "soluprot":
        return np.array([[f.soluprot] for f in folds], dtype=float)

    if name in ("esm_mean", "esm_delta_global"):
        designs, wt, row_of, wt_of = _load_esm()
        rows = np.vstack([designs[row_of[f.sequence_id]] for f in folds]).astype(float)
        if name == "esm_mean":
            return rows
        refs = np.vstack([wt[wt_of[f.target_id]] for f in folds]).astype(float)
        return rows - refs

    if name == "esm_delta_mut":
        return _delta_mut_block(folds)

    if name == "cheap":
        # 조성 20 열. MPNN score 는 `mpnn_score` 블록이고 S6 가 둘 다 받는다 -
        # 스펙 §4 의 cheap 은 "조성, MPNN score" 다.
        alphabet = "ACDEFGHIKLMNPQRSTVWY"
        rows = []
        for fold in folds:
            seq = SEQ_OF[fold.sequence_id]
            n = max(len(seq), 1)
            rows.append([seq.count(a) / n for a in alphabet])
        return np.array(rows, dtype=float)

    if name == "mpnn_score":
        return _mpnn_score_block(folds)

    if name == "msa_candidate":
        return _msa_candidate_block(folds)

    if name == "msa":
        # fold 에 의존하므로 이 경로로 오면 안 된다. assemble 이 train_idx 와 함께
        # `_msa_block` 을 부른다.
        raise KeyError("MSA 블록은 train fold 없이 만들 수 없다 - assemble 을 쓴다")

    raise KeyError(f"알 수 없는 feature 블록: {name}")


#: 블록 캐시. LOTO fold 12 개가 같은 ΔESM 블록을 12 번 만들면 445 MB npz 를
#: 12 번 다시 읽는다. 키는 블록 이름 + 행 순서(sequence_id 튜플)다 - id() 는
#: 재사용되므로 쓰지 않는다.
_BLOCK_CACHE: dict[tuple[str, tuple[str, ...]], np.ndarray] = {}


def _block(name: str, folds) -> np.ndarray:
    if name in FOLD_DEPENDENT_BLOCKS:      # 캐시하면 안 되는 블록
        return _build_block(name, folds)
    key = (name, tuple(f.sequence_id for f in folds))
    if key not in _BLOCK_CACHE:
        _BLOCK_CACHE[key] = _build_block(name, folds)
    return _BLOCK_CACHE[key]


def assemble(arm: str, folds, train_idx: Sequence[int] | None = None,
             block_names: Sequence[str] | None = None
             ) -> tuple[np.ndarray | None, dict | None]:
    """arm 의 feature 행렬과 결함 기록. `(None, ...)` 이면 non-evaluable.

    `None` 은 "이 arm 을 non-evaluable 로 기록" 이라는 뜻이며 타겟을 빼는 것이
    아니다 - 스펙 §4 규칙 5.

    fold 에 의존하지 않는 블록(ΔESM·조성·SoluProt·MSA 의 candidate 성분)은 한 번만
    만들어 캐시하고, MSA 의 **타겟 성분만** `train_idx` 로 fold 마다 다시 만든다.
    MSA 없는 arm(S0-S3)에서는 `train_idx` 가 결과에 영향을 주지 않는다.

    `block_names` 는 동결된 `ARM_BLOCKS[arm]` 대신 쓸 블록 목록이다. **arm 을
    추가하는 수단이 아니다** - `REALIZED_S6_BLOCKS_2026_09_11` 처럼 이미 실행돼
    기록된 구현 결함판을 planned 판과 나란히 재현하는 데만 쓴다. 기본값은 항상
    동결 목록이다.
    """
    if arm not in ARM_BLOCKS:
        raise KeyError(f"동결된 ladder 에 없는 arm: {arm}")
    blocks = []
    for name in (ARM_BLOCKS[arm] if block_names is None else tuple(block_names)):
        if name == "msa":
            matrix, defect = _msa_block(folds, train_idx)
            if matrix is None:
                return None, defect
            blocks.append(matrix)
            continue
        blocks.append(_block(name, folds))
    return np.hstack(blocks), None


def build_features(arm: str, folds, train_idx: Sequence[int] | None = None,
                   block_names: Sequence[str] | None = None) -> np.ndarray | None:
    """`assemble` 의 행렬만 돌려주는 얇은 wrapper. 두 번째 조립 규칙이 아니다."""
    matrix, _defect = assemble(arm, folds, train_idx, block_names)
    return matrix
