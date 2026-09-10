"""Gate 2 의 feature ladder. arm 목록은 스펙 §4 에서 동결됐다.

S6 하나가 판정 arm 이다. 나머지는 ablation/descriptive 이며 GO 판정에 쓰지 않는다 -
endpoint 가 하나여도 arm 을 골라 GO 를 선언하면 model selection multiplicity 다.

**현재 구현 범위는 S0-S3 이다.** S4-S6 는 `msa_features.json` 을 요구하는데 그
파일이 아직 없다 (MSA 실행이 진행 중이다). 없는 데이터를 가짜로 채우지 않으므로
MSA 블록은 `NotImplementedError` 를 내는 seam 으로 남긴다 - `non_evaluable` 로
적지 않는다. `non_evaluable` 은 스펙 §4 규칙 5 의 **데이터에 대한 판정**이고,
코드가 아직 없는 것을 그렇게 적으면 나중에 진짜 규칙 5 사례와 구분되지 않는다.

측정 primitive 는 `_gate2d.py` 에 있고 여기서 다시 만들지 않는다. 서열/코호트
로딩은 `_gate2d_cohort.py`, WT 서열 파싱과 변이 위치는 `22_gate2d_prepare_esm.py`
가 유일한 구현이다.
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
    "S6": ("esm_delta_mut", "msa", "cheap"),
}

#: LOTO fold 마다 다시 만들어야 하는 블록. 대치 통계량이 train fold 에서 나오므로
#: fold 에 의존한다. 나머지 블록(ΔESM·조성·SoluProt)은 fold 와 무관하다.
FOLD_DEPENDENT_BLOCKS = frozenset({"msa"})


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
        # 조성 20 열. MPNN score 는 격자의 sequences.csv 에 없으므로 넣지 않는다 -
        # 없는 feature 를 있는 것처럼 쓰지 않는다.
        alphabet = "ACDEFGHIKLMNPQRSTVWY"
        rows = []
        for fold in folds:
            seq = SEQ_OF[fold.sequence_id]
            n = max(len(seq), 1)
            rows.append([seq.count(a) / n for a in alphabet])
        return np.array(rows, dtype=float)

    if name == "msa":
        raise NotImplementedError(
            "MSA 블록은 아직 없다. msa_features.json 이 도착하면 Task 11 의 "
            "S4-S6 구간(impute_msa_block · conservation_burden)이 여기에 붙는다. "
            "가짜 값으로 채우지 않는다."
        )

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


def assemble(arm: str, folds, train_idx: Sequence[int] | None = None
             ) -> tuple[np.ndarray | None, dict | None]:
    """arm 의 feature 행렬과 결함 기록. `(None, ...)` 이면 non-evaluable.

    `None` 은 "이 arm 을 non-evaluable 로 기록" 이라는 뜻이며 타겟을 빼는 것이
    아니다 - 스펙 §4 규칙 5.

    fold 에 의존하지 않는 블록(ΔESM·조성·SoluProt)은 한 번만 만들어 캐시하고,
    MSA 블록만 `train_idx` 로 fold 마다 다시 만든다. 현재 구현 범위(S0-S3)에는
    MSA 블록이 없으므로 `train_idx` 는 결과에 영향을 주지 않는다.
    """
    if arm not in ARM_BLOCKS:
        raise KeyError(f"동결된 ladder 에 없는 arm: {arm}")
    blocks = []
    for name in ARM_BLOCKS[arm]:
        blocks.append(_block(name, folds))
    return np.hstack(blocks), None


def build_features(arm: str, folds, train_idx: Sequence[int] | None = None
                   ) -> np.ndarray | None:
    """`assemble` 의 행렬만 돌려주는 얇은 wrapper. 두 번째 조립 규칙이 아니다."""
    matrix, _defect = assemble(arm, folds, train_idx)
    return matrix
