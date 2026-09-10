# Surrogate–RAPID 2축 게이팅 실험 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 새 AF2 0개로 Gate 1(backbone predictability)과 Gate 2(within-backbone selectability)를 측정해, B / B+C / C / STOP 중 무엇이 존재하는 연구 문제인지 판정한다.

**Architecture:** 동결 스펙 `docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md` 의 지표 정의를 `scripts/benchmark/_gate2d.py` 한 곳에 구현하고 테스트로 고정한다. feature 재료화(P1 encoder / P2 ESM / P3 MSA)는 의존성이 서로 달라 별도 스크립트로 분리한다. 두 게이트 스크립트는 측정 primitive 와 feature 를 조립만 한다.

**Tech Stack:** Python 3.12, numpy/scipy/scikit-learn(시스템 설치됨), torch+transformers(venv 필요, `requirements-benchmark.txt`), ProteinMPNN `v_48_020` soluble ckpt, MMseqs2 RunPod 엔드포인트, pytest.

---

## 이 계획이 전제하는 사실 (실행 전 확인됨)

| 사실 | 확인 방법 |
|---|---|
| 홀드아웃 백본 PDB 72/72 해석 가능 (rfd3 60 + native 12) | rfd3: `/opt/protein_pipeline/outputs/holdout_<target>_rfd3/rfd3/designs/<backbone_id>.pdb`, native: `public_data/benchmark/gate0/holdout_targets_pdb/<target>.pdb` |
| 라벨 있는 백본은 70개 | `af2_order_metric.csv` 에서 `status == ok` 이고 plddt/rmsd/soluprot 결측 아닌 행. `sequences.csv` 의 72개 중 2개는 사용가능 폴드 0 |
| 시스템 python 에 pandas/torch/transformers **없음** | `python3 -c "import pandas"` → ModuleNotFoundError |
| `rapid_sr.clustered.clustered_bootstrap` 은 **양측 95% CI 만** 낸다 | `scripts/transcoder/rapid_sr/clustered.py:30-72`. 스펙은 **단측 90% LCB** 를 요구하므로 새 함수가 필요하다 |
| dev 코호트 backbone_source 는 rfd3 80 / target 57 / bioemu 20 | 홀드아웃 격자는 rfd3 + native 뿐 — **bioemu 가 test 에 없다** |

### 선행 시도 공개 (Gate 1)

`scripts/transcoder/13_gate0_target_level.py:1-14` 의 docstring 은 백본 수준 게이트를
시도했다가 타겟 수준으로 바꾼 이유를 적고 있다: *"타겟 내부 순위 예측은 실패했다
(rfd3 rho -0.257)"*, *"타겟 내부 yield sd 가 0.044"*.

**그 sd 는 현재 라벨에서 재현되지 않는다.** 같은 dev 코호트에서 다시 재면
rfd3 `af2_structural_pass_yield` 내부 sd 평균은 **0.134**, `joint_pass_yield` 는
**0.150** 이다. 다만 *"16 타겟 중 7개는 전부 같은 값"* 은 정확히 재현된다(rfd3 상수
타겟 7개).

원인은 correspondence metric 교체다. `gate0_target_level.json` 의 `_metric_status`
가 이전 두 정의(`kabsch_all_ca_file_order`, `ca_rmsd_dssp_non_loop_resnum`)를 모두
`valid: false` 로 기록하고 2026-09-06 에 `folded_sequence_order` 를 채택했다.
따라서 **rho −0.257 은 지금 무효인 라벨 위에서 측정된 값이며 standing negative
result 로 인용하지 않는다.** 그러나 선행 시도가 있었다는 사실은 Gate 1 결과 보고에
반드시 함께 적는다 (Task 12).

---

## File Structure

| 파일 | 책임 |
|---|---|
| `scripts/benchmark/_gate2d.py` (신규) | 동결된 상수 + 측정 primitive(Δ_Top4, 타겟 등가중, 단측 LCB, 타겟 내 Spearman, informative 필터). **여기만 테스트로 고정한다** |
| `scripts/benchmark/_gate2d_cohort.py` (신규) | 라벨 로딩과 코호트 구성. 파일 포맷이 바뀌면 여기만 바뀐다 |
| `scripts/benchmark/_gate2d_features.py` (신규) | feature 조립 + MSA 결측 처리. 모델 입력이 바뀌면 여기만 바뀐다 |
| `scripts/benchmark/21_gate2d_prepare_encoder.py` (신규) | P1. ProteinMPNN encoder 384-D, 홀드아웃 72 백본 |
| `scripts/benchmark/22_gate2d_prepare_esm.py` (신규) | P2. ESM 임베딩(설계 1,728 + WT 12) |
| `scripts/benchmark/23_gate2d_prepare_msa_features.py` (신규) | P3. a3m → conservation feature |
| `scripts/benchmark/24_gate1_backbone_predictability.py` (신규) | Gate 1 |
| `scripts/benchmark/25_gate2_within_backbone_selectability.py` (신규) | Gate 2 |
| `tests/test_gate2d_metrics.py` (신규) | primitive 단위 테스트 + 실제 코호트 회귀 테스트 |
| `scripts/transcoder/rapid_sr/clustered.py` (수정) | 단측 LCB 함수 **추가**(기존 함수 불변 — 동결 수치 보호) |
| `docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md` (수정) | §10 산출물 표를 실제 파일명으로 정정 |
| `docs/results_of_record.md` (수정) | 판정 수치 등재 |

---

## Task 0: 실행 환경

**Files:**
- Create: `/tmp/gate2d-venv/` (커밋하지 않음)

- [ ] **Step 1: venv 생성과 설치**

```bash
python3 -m venv /tmp/gate2d-venv
/tmp/gate2d-venv/bin/pip install -q -r requirements-benchmark.txt
```

- [ ] **Step 2: 의존성 확인**

Run:
```bash
/tmp/gate2d-venv/bin/python -c "import numpy,scipy,sklearn,pandas,torch,transformers;print('ok')"
```
Expected: `ok`

- [ ] **Step 3: pytest 확인**

Run: `/tmp/gate2d-venv/bin/python -m pytest --version`
Expected: `pytest 8.x` 형태의 버전 출력

**주의:** 이후 모든 명령의 `python` 은 `/tmp/gate2d-venv/bin/python` 이다. 시스템
`python3` 에는 pandas/torch 가 없다.

---

## Task 1: 동결 상수

**Files:**
- Create: `scripts/benchmark/_gate2d.py`
- Test: `tests/test_gate2d_metrics.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_gate2d_metrics.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "benchmark"))

import _gate2d as G


def test_frozen_constants_match_spec():
    assert G.PLDDT_MIN == 85.0
    assert G.RMSD_MAX == 2.0
    assert G.SOLUPROT_MIN == 0.5
    assert G.TOP_K == 4
    assert G.GATE2_DELTA_MIN == 0.10
    assert G.GATE1_RHO_MIN == 0.25
    assert G.LCB_ONE_SIDED_ALPHA == 0.10
    assert G.MIN_INFORMATIVE_TARGETS == 8
    assert G.BOOTSTRAP_SEED == 20260910
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_gate2d'`

- [ ] **Step 3: 최소 구현**

```python
# scripts/benchmark/_gate2d.py
"""2축 게이팅 실험의 동결된 상수와 측정 primitive.

정의의 출처는 docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md 하나다.
이 파일의 숫자를 바꾸면 스펙을 위반한다 - 결과를 보고 바꾸지 않는다.
"""

from __future__ import annotations

#: joint-pass 문턱. THRESHOLD_PROVENANCE 에서 고정됐고 이 실험에서 다시 고르지 않는다.
PLDDT_MIN = 85.0
RMSD_MAX = 2.0
SOLUPROT_MIN = 0.5

#: Δ_Top4 의 K. m2_endpoint_dynamic_range.json 의 min_probe_per_unit 과 같은 값.
TOP_K = 4

#: GO 문턱.
GATE2_DELTA_MIN = 0.10
GATE1_RHO_MIN = 0.25

#: 단측 LCB 의 alpha. 90% LCB 이므로 0.10.
LCB_ONE_SIDED_ALPHA = 0.10

#: 이보다 적으면 판정하지 않는다. holdout_experiment_spec.json 규칙 승계.
MIN_INFORMATIVE_TARGETS = 8

#: 부트스트랩 시드. 스펙의 시뮬레이션과 같은 값을 쓴다.
BOOTSTRAP_SEED = 20260910
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/benchmark/_gate2d.py tests/test_gate2d_metrics.py
git commit -m "feat(sr): freeze the 2-axis gate constants in one module"
```

---

## Task 2: joint-pass 판정과 Δ_Top4

**Files:**
- Modify: `scripts/benchmark/_gate2d.py`
- Test: `tests/test_gate2d_metrics.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_gate2d_metrics.py` 끝에 추가:

```python
def test_is_joint_pass_boundaries():
    # 문턱은 모두 포함(>=, <=)이다.
    assert G.is_joint_pass(85.0, 2.0, 0.5) is True
    assert G.is_joint_pass(84.99, 2.0, 0.5) is False
    assert G.is_joint_pass(85.0, 2.01, 0.5) is False
    assert G.is_joint_pass(85.0, 2.0, 0.49) is False


def test_delta_top4_oracle_and_worst():
    # 24개 중 6개만 통과. q_b = 0.25.
    labels = [True] * 6 + [False] * 18
    ids = [f"g{i}" for i in range(24)]
    oracle = [1.0] * 6 + [0.0] * 18
    # Top-4 전부 통과 -> 1.0 - 0.25
    assert abs(G.delta_top4(labels, oracle, ids) - 0.75) < 1e-12
    worst = [0.0] * 6 + [1.0] * 18
    # Top-4 전부 실패 -> 0.0 - 0.25
    assert abs(G.delta_top4(labels, worst, ids) - (-0.25)) < 1e-12


def test_delta_top4_tie_break_is_sequence_id_ascending():
    # 점수가 전부 같으면 sequence_id 오름차순 앞 4개를 고른다.
    labels = [False, False, True, True, True, True]
    ids = ["g0", "g1", "g2", "g3", "g4", "g5"]
    scores = [0.5] * 6
    # 선택 = g0,g1,g2,g3 -> 통과 2/4 = 0.5, q_b = 4/6
    assert abs(G.delta_top4(labels, scores, ids) - (0.5 - 4.0 / 6.0)) < 1e-12
    # 문자열 정렬이므로 g10 은 g2 보다 앞이다. 그 규칙을 명시적으로 고정한다.
    ids2 = ["g0", "g1", "g10", "g2", "g3", "g4"]
    labels2 = [False, False, True, False, False, False]
    assert abs(G.delta_top4(labels2, [0.5] * 6, ids2) - (1.0 / 4.0 - 1.0 / 6.0)) < 1e-12
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: FAIL — `AttributeError: module '_gate2d' has no attribute 'is_joint_pass'`

- [ ] **Step 3: 구현**

`scripts/benchmark/_gate2d.py` 에 추가:

```python
from collections.abc import Sequence


def is_joint_pass(plddt: float, rmsd: float, soluprot: float) -> bool:
    """스펙의 joint-pass. 세 문턱 모두 등호를 포함한다."""
    return (plddt >= PLDDT_MIN) and (rmsd <= RMSD_MAX) and (soluprot >= SOLUPROT_MIN)


def is_structural_pass(plddt: float, rmsd: float) -> bool:
    """SoluProt 을 뺀 2차 endpoint. 순환성 없는 대조에 쓴다."""
    return (plddt >= PLDDT_MIN) and (rmsd <= RMSD_MAX)


def top_k_indices(scores: Sequence[float], seq_ids: Sequence[str], k: int = TOP_K) -> list[int]:
    """점수 내림차순 상위 k. 동점은 sequence_id 오름차순으로 끊는다.

    무작위 동점 처리를 쓰지 않는다 - 재현되지 않는다.
    """
    order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), str(seq_ids[i])))
    return order[:k]


def delta_top4(labels: Sequence[bool], scores: Sequence[float],
               seq_ids: Sequence[str], k: int = TOP_K) -> float:
    """(Top-k 통과율) − q_b.

    q_b 는 Top-k 를 고르는 것과 **같은 candidate universe** 위의 base rate 다.
    분모는 다르다(k vs n) - 같아야 하는 것은 후보 모집단이다.
    """
    n = len(labels)
    if n == 0 or k <= 0:
        return float("nan")
    q_b = sum(1 for v in labels if v) / n
    picked = top_k_indices(scores, seq_ids, k)
    top_rate = sum(1 for i in picked if labels[i]) / len(picked)
    return top_rate - q_b
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/benchmark/_gate2d.py tests/test_gate2d_metrics.py
git commit -m "feat(sr): Delta_Top4 with a deterministic tie-break"
```

---

## Task 3: 타겟 등가중 집계

이 태스크가 제일 중요하다. **백본 등가중과 타겟 등가중은 다른 수를 낸다** — 설계
논의에서 실제로 한 번 틀렸다(백본 등가중 −0.002 vs 타겟 등가중 −0.001, oracle
+0.313 vs +0.326). 테스트로 방향을 고정한다.

**Files:**
- Modify: `scripts/benchmark/_gate2d.py`
- Test: `tests/test_gate2d_metrics.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_target_equal_mean_differs_from_backbone_equal():
    # 타겟 A 는 백본 3개(전부 0.0), 타겟 B 는 백본 1개(0.8).
    per_backbone = [0.0, 0.0, 0.0, 0.8]
    targets = ["A", "A", "A", "B"]
    # 백본 등가중 = 0.8/4 = 0.2
    assert abs(sum(per_backbone) / 4 - 0.2) < 1e-12
    # 타겟 등가중 = (0.0 + 0.8)/2 = 0.4
    per_target = G.per_target_means(per_backbone, targets)
    assert per_target == [0.0, 0.8]
    assert abs(G.target_equal_mean(per_backbone, targets) - 0.4) < 1e-12


def test_per_target_means_sorts_targets_deterministically():
    per_target = G.per_target_means([1.0, 2.0, 3.0], ["b", "a", "b"])
    # 타겟 정렬 오름차순: a -> 2.0, b -> (1.0+3.0)/2 = 2.0
    assert per_target == [2.0, 2.0]


def test_target_equal_mean_ignores_nan_backbones():
    per_target = G.per_target_means([float("nan"), 0.4], ["A", "A"])
    assert per_target == [0.4]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'per_target_means'`

- [ ] **Step 3: 구현**

```python
from collections import defaultdict


def per_target_means(per_backbone: Sequence[float],
                     targets: Sequence[str]) -> list[float]:
    """백본별 값을 타겟 내에서 먼저 평균한다. 타겟 이름 오름차순으로 돌려준다.

    NaN 백본은 제외한다. 어떤 타겟의 백본이 전부 NaN 이면 그 타겟도 빠진다.
    """
    grouped: dict[str, list[float]] = defaultdict(list)
    for value, target in zip(per_backbone, targets):
        v = float(value)
        if v == v:  # NaN 제외
            grouped[str(target)].append(v)
    return [sum(vals) / len(vals) for _t, vals in sorted(grouped.items()) if vals]


def target_equal_mean(per_backbone: Sequence[float],
                      targets: Sequence[str]) -> float:
    """타겟 등가중 평균. 백본 수가 많은 타겟이 과대대표되지 않는다."""
    per_target = per_target_means(per_backbone, targets)
    if not per_target:
        return float("nan")
    return sum(per_target) / len(per_target)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/benchmark/_gate2d.py tests/test_gate2d_metrics.py
git commit -m "feat(sr): target-equal weighting, pinned against backbone-equal"
```

---

## Task 4: 단측 90% LCB

기존 `clustered_bootstrap` 은 양측 95% CI 만 낸다. **그 함수를 고치면 동결된 v1
수치가 움직인다.** 그래서 새 함수를 추가한다.

**Files:**
- Modify: `scripts/transcoder/rapid_sr/clustered.py`
- Test: `tests/test_gate2d_metrics.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_one_sided_lcb90_positive_and_null():
    sys.path.insert(0, str(ROOT / "scripts" / "transcoder"))
    from rapid_sr.clustered import one_sided_lcb

    # 전부 +0.5 인 표본이면 LCB 도 +0.5 여야 한다(재표집해도 값이 같다).
    out = one_sided_lcb([0.5] * 11, alpha=0.10, seed=20260910)
    assert abs(out["lcb"] - 0.5) < 1e-9
    assert out["exceeds_zero"] is True
    assert out["n"] == 11

    # 0 을 중심으로 대칭인 표본이면 LCB < 0 이어야 한다.
    sym = [-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, -0.05, 0.05]
    out2 = one_sided_lcb(sym, alpha=0.10, seed=20260910)
    assert out2["lcb"] < 0
    assert out2["exceeds_zero"] is False


def test_one_sided_lcb90_is_deterministic_for_a_seed():
    from rapid_sr.clustered import one_sided_lcb
    a = one_sided_lcb([0.1, 0.2, 0.05, 0.3, 0.0, 0.15, 0.25, 0.2, 0.1, 0.05, 0.3],
                      alpha=0.10, seed=20260910)
    b = one_sided_lcb([0.1, 0.2, 0.05, 0.3, 0.0, 0.15, 0.25, 0.2, 0.1, 0.05, 0.3],
                      alpha=0.10, seed=20260910)
    assert a["lcb"] == b["lcb"]


def test_one_sided_lcb90_withholds_below_three_units():
    from rapid_sr.clustered import one_sided_lcb
    out = one_sided_lcb([0.5, 0.5], alpha=0.10, seed=1)
    assert out["lcb"] is None
    assert out["n"] == 2
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: FAIL — `ImportError: cannot import name 'one_sided_lcb'`

- [ ] **Step 3: 구현**

`scripts/transcoder/rapid_sr/clustered.py` 끝에 **추가**한다. 기존
`clustered_bootstrap` 은 한 글자도 고치지 않는다 — 동결 수치가 그 함수를 쓴다.

```python
def one_sided_lcb(values: Sequence[float], *, alpha: float = 0.10,
                  n_boot: int = 20000, seed: int = 0) -> dict[str, object]:
    """이미 클러스터 단위로 집계된 값들의 단측 하한.

    `clustered_bootstrap` 과 나누어 두는 이유: 그쪽은 행 인덱스를 받아 양측 95%
    구간을 내고 동결된 v1 수치가 그 동작에 묶여 있다. 여기는 **클러스터당 값
    하나**를 받아 단측 하한만 낸다.

    2026-09-10 게이트 스펙에서 클러스터 = 타겟이다. 호출자가 타겟 등가중으로
    집계한 뒤 넘긴다.
    """
    clean = [float(v) for v in values if float(v) == float(v)]
    n = len(clean)
    if n < 3:
        # 점추정은 낼 수 있다. 단위가 3개 미만이면 구간을 보류한다.
        point = sum(clean) / n if n else None
        return {"point": point, "lcb": None, "exceeds_zero": None, "n": n}

    rng = np.random.default_rng(seed)
    arr = np.asarray(clean, dtype=float)
    draws = rng.integers(0, n, size=(n_boot, n))
    means = arr[draws].mean(axis=1)
    lcb = float(np.percentile(means, alpha * 100.0))
    return {
        "point": round(float(arr.mean()), 6),
        "lcb": round(lcb, 6),
        "exceeds_zero": bool(lcb > 0.0),
        "n": n,
        "n_boot": int(n_boot),
        "alpha": float(alpha),
    }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: 기존 동결 수치가 안 움직였는지 확인한다**

Run:
```bash
PYTHONPATH=pipeline-mcp/src /tmp/gate2d-venv/bin/python -m pytest pipeline-mcp/tests/test_results_of_record.py -v
```
Expected: PASS — `clustered_bootstrap` 을 건드리지 않았으므로 모든 claim 이 그대로다.

- [ ] **Step 6: 커밋**

```bash
git add scripts/transcoder/rapid_sr/clustered.py tests/test_gate2d_metrics.py
git commit -m "feat(sr): add a one-sided LCB beside the frozen two-sided bootstrap"
```

---

## Task 5: 코호트 로딩과 informative 필터

**Files:**
- Create: `scripts/benchmark/_gate2d_cohort.py`
- Test: `tests/test_gate2d_metrics.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_load_holdout_grid_shapes():
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    # 1,728 폴드 중 status ok 이고 지표 결측 아닌 것이 1,680 이다.
    assert len(grid.folds) == 1680
    assert len(grid.backbones) == 70
    assert len(grid.targets) == 12


def test_gate2_informative_targets_is_eleven():
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    assert len(mixed) == 37
    # mixed 백본이 하나도 없는 타겟은 1sh6A02 뿐이다.
    assert sorted({b.target_id for b in mixed}) == sorted(set(grid.targets) - {"1sh6A02"})
    assert len({b.target_id for b in mixed}) == 11


def test_gate1_informative_targets_is_eleven():
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    inf = C.gate1_informative_targets(grid)
    # 백본 >= 3 이고 q_b 비상수. 1sh6A02 는 q_b 가 전부 1.00 이라 Spearman 미정의.
    assert len(inf) == 11
    assert "1sh6A02" not in inf
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_gate2d_cohort'`

- [ ] **Step 3: 구현**

```python
# scripts/benchmark/_gate2d_cohort.py
"""홀드아웃 격자 라벨 로딩과 코호트 구성.

코호트 정의는 스펙 §3·§4 다. 여기서 새로 정하는 것은 없다.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import _gate2d as G

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
GRID = GATE0 / "holdout_grid"


@dataclass(frozen=True)
class Fold:
    sequence_id: str
    backbone_key: str
    target_id: str
    plddt: float
    rmsd: float
    soluprot: float

    @property
    def joint_pass(self) -> bool:
        return G.is_joint_pass(self.plddt, self.rmsd, self.soluprot)

    @property
    def structural_pass(self) -> bool:
        return G.is_structural_pass(self.plddt, self.rmsd)


@dataclass
class Backbone:
    backbone_key: str
    target_id: str
    folds: list[Fold] = field(default_factory=list)

    @property
    def q_b(self) -> float:
        """joint-pass base rate. Top-4 와 같은 candidate universe 위에서 센다."""
        return sum(1 for f in self.folds if f.joint_pass) / len(self.folds)

    @property
    def is_mixed(self) -> bool:
        return 0.0 < self.q_b < 1.0


@dataclass
class Grid:
    folds: list[Fold]
    backbones: list[Backbone]

    @property
    def targets(self) -> list[str]:
        return sorted({b.target_id for b in self.backbones})


def _f(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_holdout_grid(path: Path | None = None) -> Grid:
    """af2_order_metric.csv 를 읽는다. status != ok 나 지표 결측 행은 버린다."""
    path = path or (GRID / "af2_order_metric.csv")
    folds: list[Fold] = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "ok":
                continue
            plddt = _f(row.get("plddt", ""))
            rmsd = _f(row.get("rmsd_nonloop_order", ""))
            solu = _f(row.get("soluprot", ""))
            if None in (plddt, rmsd, solu):
                continue
            folds.append(Fold(row["sequence_id"], row["backbone_key"],
                              row["target_id"], plddt, rmsd, solu))

    grouped: dict[tuple[str, str], Backbone] = {}
    for fold in folds:
        key = (fold.target_id, fold.backbone_key)
        if key not in grouped:
            grouped[key] = Backbone(fold.backbone_key, fold.target_id)
        grouped[key].folds.append(fold)
    backbones = [grouped[k] for k in sorted(grouped)]
    return Grid(folds=folds, backbones=backbones)


def mixed_backbones(grid: Grid) -> list[Backbone]:
    """Gate 2 코호트. q_b 가 0 도 1 도 아닌 백본."""
    return [b for b in grid.backbones if b.is_mixed]


def gate1_informative_targets(grid: Grid) -> list[str]:
    """Gate 1 informative 타겟. 백본 >= 3 이고 q_b 비상수.

    q_b 가 상수면 타겟 내 Spearman 이 정의되지 않는다. Gate 2 의 제외 사유
    (mixed 백본 0개)와 결과적으로 같은 타겟이지만 사유는 다르다.
    """
    by_target: dict[str, list[float]] = defaultdict(list)
    for b in grid.backbones:
        by_target[b.target_id].append(b.q_b)
    return sorted(t for t, qs in by_target.items()
                  if len(qs) >= 3 and len(set(qs)) > 1)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/benchmark/_gate2d_cohort.py tests/test_gate2d_metrics.py
git commit -m "feat(sr): load the holdout grid and pin both informative counts at 11"
```

---

## Task 6: 스펙 참조 수치 회귀 테스트

스펙에 이미 인쇄된 두 수를 구현이 재현하는지 본다. 이 테스트가 깨지면 **구현이
스펙과 다른 것을 재고 있다는 뜻**이다.

**Files:**
- Test: `tests/test_gate2d_metrics.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_reproduces_spec_reference_deltas():
    """스펙 §1: SoluProt −0.001, oracle +0.326 (타겟 등가중, mixed 백본 37개)."""
    import _gate2d_cohort as C
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    targets = [b.target_id for b in mixed]

    solu, oracle = [], []
    for b in mixed:
        labels = [f.joint_pass for f in b.folds]
        ids = [f.sequence_id for f in b.folds]
        solu.append(G.delta_top4(labels, [f.soluprot for f in b.folds], ids))
        oracle.append(G.delta_top4(labels, [1.0 if v else 0.0 for v in labels], ids))

    assert round(G.target_equal_mean(solu, targets), 3) == -0.001
    assert round(G.target_equal_mean(oracle, targets), 3) == 0.326


def test_soluprot_reference_fails_the_gate2_threshold():
    """현행 cheap predictor 는 GO 문턱에 한참 미달한다 - 그것이 실험의 출발점이다."""
    import _gate2d_cohort as C
    from rapid_sr.clustered import one_sided_lcb
    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    per_backbone = [
        G.delta_top4([f.joint_pass for f in b.folds],
                     [f.soluprot for f in b.folds],
                     [f.sequence_id for f in b.folds])
        for b in mixed
    ]
    per_target = G.per_target_means(per_backbone, [b.target_id for b in mixed])
    point = sum(per_target) / len(per_target)
    out = one_sided_lcb(per_target, alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    assert point < G.GATE2_DELTA_MIN
    assert out["exceeds_zero"] is False
```

- [ ] **Step 2: 실행해서 실제 값을 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: PASS (15 passed).

FAIL 이 나면 **테스트의 기대값을 고치지 말고 멈춘다.** 스펙 §1 의 수치는 동결본이다.
불일치는 구현 버그이거나 라벨 파일이 바뀐 것이므로, 어느 쪽인지 먼저 밝힌다.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_gate2d_metrics.py
git commit -m "test(sr): pin the implementation to the spec's printed reference deltas"
```

---

## Task 7: P1 — 홀드아웃 백본 encoder feature

**Files:**
- Create: `scripts/benchmark/21_gate2d_prepare_encoder.py`
- Read: `scripts/transcoder/06_export_gate0_backbones.py` (백본 PDB 경로 처리 참고)
- Output: `public_data/benchmark/gate0/holdout_grid/backbone_encoder.npy`, `backbone_encoder.index.json`

- [ ] **Step 1: 경로 해석만 먼저 검증한다 (실패하는 테스트)**

```python
def test_holdout_backbone_pdb_paths_all_resolve():
    sys.path.insert(0, str(ROOT / "scripts" / "benchmark"))
    import importlib
    prep = importlib.import_module("21_gate2d_prepare_encoder")
    resolved = prep.resolve_backbone_pdbs()
    # 72 개 백본 전부 해석돼야 한다. rfd3 60 + native 12.
    assert len(resolved) == 72
    assert sum(1 for r in resolved.values() if r["source"] == "rfd3") == 60
    assert sum(1 for r in resolved.values() if r["source"] == "target") == 12
    assert all(Path(r["pdb_path"]).exists() for r in resolved.values())
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k backbone_pdb -v`
Expected: FAIL — `ModuleNotFoundError: No module named '21_gate2d_prepare_encoder'`

- [ ] **Step 3: 경로 해석을 구현한다**

```python
#!/usr/bin/env python3
"""P1. 홀드아웃 백본의 ProteinMPNN encoder feature 를 뽑는다.

dev 코호트의 mpnn_encoder.npy (157, 384) 와 **같은 ckpt·같은 차원**이어야 한다.
그렇지 않으면 Gate 1 의 train/test 가 다른 공간에 있게 된다.

백본 PDB 는 이 작업 트리에 없다. rfd3 백본은 deploy 체크아웃에 있고 native 백본은
public_data 에 있다. **deploy 경로는 읽기만 한다** (AGENTS.md).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
NATIVE_PDB_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_targets_pdb"
DEPLOY_OUTPUTS = Path(os.environ.get("RAPID_DEPLOY_OUTPUTS", "/opt/protein_pipeline/outputs"))

#: dev 코호트와 같아야 하는 값. 다르면 Gate 1 을 실행하지 않는다.
ENCODER_DIM = 384
ENCODER_CKPT = "v_48_020"


def resolve_backbone_pdbs() -> dict[str, dict]:
    """backbone_key -> {source, target_id, backbone_id, pdb_path}.

    backbone_key 형식은 `<target>|<source>|<backbone_id>` 다.
    """
    keys: set[tuple[str, str, str]] = set()
    with (GRID / "sequences.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            keys.add((row["target_id"], row["backbone_source"], row["backbone_key"]))

    out: dict[str, dict] = {}
    for target_id, source, backbone_key in sorted(keys):
        backbone_id = backbone_key.split("|")[2]
        if source == "target":
            pdb_path = NATIVE_PDB_DIR / f"{target_id}.pdb"
        else:
            pdb_path = (DEPLOY_OUTPUTS / f"holdout_{target_id}_rfd3"
                        / "rfd3" / "designs" / f"{backbone_id}.pdb")
        out[backbone_key] = {
            "source": source,
            "target_id": target_id,
            "backbone_id": backbone_id,
            "pdb_path": str(pdb_path),
        }
    return out
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k backbone_pdb -v`
Expected: PASS

### 2026-09-10 조사 결과 — 호출부는 존재하지 않는다

Step 5 를 controller 가 미리 수행했다. 결과는 다음이다.

**`mpnn_encoder.npy` 를 만든 스크립트는 커밋된 적이 없다.** 그 파일을 추가한 커밋
`1c2eeb4` 는 산출물만 담고 있다 (`mpnn_encoder.{npy,meta.json}`, `backbones/pdb/*`
157개, `gate0_ladder.json`, `gate0_learning_curve.json`) — 코드 파일이 하나도 없다.
작업 트리와 `rapid_sr/` 전체 grep 에도 추출기가 없다.

재현에 필요한 정보는 산문으로 남아 있다. `1c2eeb4` 커밋 메시지:

> The ProteinMPNN encoder starts from a zero node state and is updated only by
> geometric edges, so it is sequence-independent and can be computed once per
> backbone. Extracted 3-layer pooled node features (384 dims) for all 77
> backbones on CPU in under a minute.

`mpnn_encoder.meta.json` 의 ckpt 는 `/home/pipeline/models/src/ProteinMPNN/soluble_model_weights/v_48_020.pt` 이고 dim 384 다. ProteinMPNN 인코더 hidden dim 이
128 이므로 384 = 3 layer × 128 의 layer-wise pooled concat 으로 읽힌다.

**그런데 이 호스트에 체크포인트가 없다.** `v_48_020.pt` 를 찾지 못했고
`/home/pipeline/models/` 경로도 없다. ProteinMPNN 소스는
`/tmp/opencode/thermomp/protein_mpnn_utils.py` 에 있지만 임시 디렉터리다.
`workers/` 에는 `esm_embedding` 하나뿐이고 ProteinMPNN worker 는 없다 — 이 리포는
ProteinMPNN 을 RunPod 서버리스로 호출하며 그 엔드포인트는 서열을 돌려주고
인코더 특징을 돌려주지 않는다.

**따라서 Step 5 의 "찾지 못하면 멈추고 보고한다" 가 발동했다.** 아래 Step 5a 가
그 결정을 대신할 수 없다 — 체크포인트 접근은 controller 가 사용자에게 물어야 한다.

- [ ] **Step 5a: 새 추출기를 쓸 경우 반드시 통과해야 하는 재현 검증**

체크포인트가 확보되어 추출기를 새로 쓰게 되면, **홀드아웃에 적용하기 전에
dev feature 를 재현하는지 먼저 증명한다.** 이것이 "다른 feature 공간" 위험을
가정에서 검증 가능한 사실로 바꾼다.

dev 백본 157개의 PDB 는 **전부 커밋되어 있다** (`git ls-files
public_data/benchmark/gate0/backbones/pdb | wc -l` → 157). 따라서:

```bash
# 새 추출기를 dev 157 백본에 돌린 뒤 기존 산출물과 수치 비교
/tmp/gate2d-venv/bin/python - <<'EOF'
import numpy as np
ref = np.load("public_data/benchmark/gate0/backbones/mpnn_encoder.npy")
new = np.load("/tmp/dev_encoder_reproduction.npy")
print("shape", ref.shape, new.shape)
print("max abs diff", float(np.abs(ref - new).max()))
print("allclose(atol=1e-4)", bool(np.allclose(ref, new, atol=1e-4)))
EOF
```

**통과 기준**: shape 이 (157, 384) 로 같고 `allclose(atol=1e-4)`. 통과하면 같은
공간이므로 홀드아웃 72 백본에 적용해도 안전하다. **실패하면 Gate 1 을 실행하지
않는다** — train 과 test 가 다른 공간에 놓인 결과는 해석할 수 없다.

행 정렬도 함께 확인한다: `backbone_labels.csv` 의 행 순서가 `mpnn_encoder.npy` 의
행 순서와 같다는 것을 Task 10 의 `load_dev` 가 이미 assert 한다.

- [ ] **Step 5: (원문 유지) dev encoder 를 만든 호출부를 먼저 찾는다**

Run:
```bash
grep -rn "mpnn_encoder\|encoder_features" --include=*.py scripts/transcoder/ | head -20
grep -rn "def .*encode\|ProteinMPNN" --include=*.py scripts/transcoder/rapid_sr/ | head -20
```

`public_data/benchmark/gate0/backbones/mpnn_encoder.npy` (157, 384) 를 만든 함수의
import 경로와 함수명을 확정한다. Step 6 의 import 줄을 그것으로 바꾼다.

**찾지 못하면 여기서 멈추고 보고한다.** 새 추출기를 만들면 dev feature 와 다른
공간이 되어 Gate 1 의 train/test 가 성립하지 않는다. 우회할 수 있는 문제가 아니다.

- [ ] **Step 6: encoder 추출과 main 을 붙인다**

`ENCODE_IMPORT` 로 표시된 줄을 Step 5 에서 확정한 실제 import 로 바꾼다 —
새 추출 로직을 발명하지 않는다.

```python
def extract(resolved: dict[str, dict], *, out_npy: Path, out_index: Path) -> None:
    """encoder feature 를 뽑아 행 정렬된 npy 와 index json 으로 쓴다."""
    import numpy as np

    # ENCODE_IMPORT — Step 5 에서 확정한 dev 추출 함수를 그대로 쓴다.
    from rapid_sr.mpnn_encoder import encode_backbone_pdb

    keys = sorted(resolved)
    rows = []
    for key in keys:
        vec = encode_backbone_pdb(resolved[key]["pdb_path"], ckpt=ENCODER_CKPT)
        if vec.shape[-1] != ENCODER_DIM:
            raise SystemExit(
                f"encoder 차원이 {vec.shape[-1]} 이다. dev 코호트는 {ENCODER_DIM} 이므로 "
                "Gate 1 의 train/test 가 다른 공간에 놓인다. 중단한다."
            )
        rows.append(np.asarray(vec, dtype=np.float32))

    np.save(out_npy, np.vstack(rows))
    out_index.write_text(json.dumps({
        "ckpt": ENCODER_CKPT,
        "dim": ENCODER_DIM,
        "n_backbones": len(keys),
        "backbone_keys": keys,
        "resolved": {k: resolved[k] for k in keys},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_npy} ({len(keys)}, {ENCODER_DIM})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-npy", default=str(GRID / "backbone_encoder.npy"))
    parser.add_argument("--out-index", default=str(GRID / "backbone_encoder.index.json"))
    parser.add_argument("--dry-run", action="store_true",
                        help="PDB 경로 해석만 하고 모델을 돌리지 않는다")
    args = parser.parse_args()

    resolved = resolve_backbone_pdbs()
    missing = [v["pdb_path"] for v in resolved.values() if not Path(v["pdb_path"]).exists()]
    if missing:
        print(f"PDB 결측 {len(missing)} 건:")
        for path in missing[:10]:
            print("  ", path)
        return 1
    print(f"백본 {len(resolved)} 개 PDB 전부 해석됨")
    if args.dry_run:
        return 0
    extract(resolved, out_npy=Path(args.out_npy), out_index=Path(args.out_index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: dry-run 으로 경로를 확인한다**

Run: `/tmp/gate2d-venv/bin/python scripts/benchmark/21_gate2d_prepare_encoder.py --dry-run`
Expected: `백본 72 개 PDB 전부 해석됨`

- [ ] **Step 8: 실제 추출**

Run: `/tmp/gate2d-venv/bin/python scripts/benchmark/21_gate2d_prepare_encoder.py`
Expected: `wrote .../backbone_encoder.npy (72, 384)`

- [ ] **Step 9: 커밋**

`.npy` 는 `.gitignore` 로 무시되므로 index json 만 올린다.

```bash
git add scripts/benchmark/21_gate2d_prepare_encoder.py tests/test_gate2d_metrics.py
git add -f public_data/benchmark/gate0/holdout_grid/backbone_encoder.index.json
git commit -m "feat(sr): extract holdout backbone encoder features in the dev feature space"
```

---

## Task 8: P2 — ESM 임베딩 (설계 + WT reference)

**Files:**
- Create: `scripts/benchmark/22_gate2d_prepare_esm.py`
- Output: `data/benchmark/gate2d_esm_8m_designs.npy`, `gate2d_esm_8m_wt.npy`, `gate2d_esm.index.json`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_mutation_sites_against_wt():
    import importlib
    prep = importlib.import_module("22_gate2d_prepare_esm")
    # 길이가 같은 경우: 다른 위치만 돌려준다.
    assert prep.mutation_sites("AAAA", "ABAA") == [1]
    assert prep.mutation_sites("AAAA", "AAAA") == []
    # 길이가 다르면 비교가 성립하지 않는다 - 조용히 자르지 않고 예외를 낸다.
    try:
        prep.mutation_sites("AAAA", "AAA")
    except ValueError:
        pass
    else:
        raise AssertionError("길이 불일치에서 ValueError 가 나와야 한다")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k mutation_sites -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
#!/usr/bin/env python3
"""P2. Gate 2 용 ESM 임베딩. 설계 서열과 타겟 WT reference 를 함께 만든다.

ΔESM 은 두 종류다.
  ΔESM_global : mean-pool(design) − mean-pool(WT)
  ΔESM_mut    : 변이 위치의 토큰 임베딩 차이만 평균

프로덕션 surrogate 와 같은 모델(esm2_t6_8M_UR50D, 320-D)을 기본으로 쓴다.
ESM 크기 스케일링은 이 게이트의 질문이 아니다 (Supp. Note 3 에서 이미 음성).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, EsmModel

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"
NATIVE_PDB_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_targets_pdb"
OUT_DIR = PROJECT_ROOT / "data" / "benchmark"

MODEL_NAME = "facebook/esm2_t6_8M_UR50D"
EMB_DIM = 320

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}


def mutation_sites(wt: str, design: str) -> list[int]:
    """WT 와 다른 위치의 0-기반 인덱스.

    길이가 다르면 위치 대응이 성립하지 않는다. 조용히 자르면 ΔESM_mut 가
    엉뚱한 위치를 보게 되므로 예외를 낸다.
    """
    if len(wt) != len(design):
        raise ValueError(f"길이 불일치: WT {len(wt)} vs design {len(design)}")
    return [i for i, (a, b) in enumerate(zip(wt, design)) if a != b]


def wt_sequence_from_pdb(path: Path) -> str:
    """native 타겟 PDB 의 CA 잔기 순서에서 서열을 읽는다."""
    seq: list[str] = []
    seen: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        key = (line[21], line[22:27])
        if key in seen:
            continue
        seen.add(key)
        seq.append(THREE_TO_ONE.get(line[17:20].strip().upper(), "X"))
    return "".join(seq)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k mutation_sites -v`
Expected: PASS

- [ ] **Step 5: 임베딩 계산을 붙인다**

```python
def embed(sequences: list[str], *, device: torch.device,
          batch_size: int = 8) -> tuple[np.ndarray, list[np.ndarray]]:
    """(mean-pooled (n, EMB_DIM), 서열별 토큰 임베딩 리스트) 를 돌려준다.

    토큰 임베딩은 ΔESM_mut 에 필요하다. 특수 토큰(BOS/EOS)을 잘라 잔기와
    1:1 로 맞춘다 - 이걸 틀리면 변이 위치가 한 칸씩 밀린다.
    """
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = EsmModel.from_pretrained(MODEL_NAME).to(device).eval()

    pooled: list[np.ndarray] = []
    per_token: list[np.ndarray] = []
    for start in range(0, len(sequences), batch_size):
        chunk = sequences[start:start + batch_size]
        batch = tokenizer(chunk, return_tensors="pt", padding=True)
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.no_grad():
            hidden = model(**batch).last_hidden_state
        for row, seq in enumerate(chunk):
            # BOS 를 1칸 건너뛰고 잔기 길이만 취한다.
            tokens = hidden[row, 1:1 + len(seq)].float().cpu().numpy()
            if tokens.shape[0] != len(seq):
                raise SystemExit(
                    f"토큰 {tokens.shape[0]} 개가 잔기 {len(seq)} 개와 다르다. "
                    "ΔESM_mut 위치가 밀리므로 중단한다."
                )
            per_token.append(tokens.astype(np.float32))
            pooled.append(tokens.mean(axis=0).astype(np.float32))
    return np.vstack(pooled), per_token
```

- [ ] **Step 6: main 을 붙이고 실행한다**

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader((GRID / "sequences.csv").open(encoding="utf-8")))
    designs = [r["sequence"] for r in rows]
    targets = sorted({r["target_id"] for r in rows})
    wt = {t: wt_sequence_from_pdb(NATIVE_PDB_DIR / f"{t}.pdb") for t in targets}

    d_pooled, d_tokens = embed(designs, device=device, batch_size=args.batch_size)
    w_pooled, w_tokens = embed([wt[t] for t in targets], device=device,
                               batch_size=args.batch_size)

    np.save(OUT_DIR / "gate2d_esm_8m_designs.npy", d_pooled)
    np.save(OUT_DIR / "gate2d_esm_8m_wt.npy", w_pooled)
    np.savez_compressed(OUT_DIR / "gate2d_esm_8m_tokens.npz",
                        **{f"d{i}": t for i, t in enumerate(d_tokens)},
                        **{f"w_{t}": w_tokens[i] for i, t in enumerate(targets)})

    length_mismatch = sorted(
        {r["target_id"] for r in rows if len(r["sequence"]) != len(wt[r["target_id"]])}
    )
    (OUT_DIR / "gate2d_esm.index.json").write_text(json.dumps({
        "model": MODEL_NAME, "dim": EMB_DIM,
        "n_designs": len(designs), "targets": targets,
        "sequence_ids": [r["sequence_id"] for r in rows],
        "wt_lengths": {t: len(wt[t]) for t in targets},
        "length_mismatch_targets": length_mismatch,
        "length_mismatch_note": (
            "이 타겟들은 설계 길이가 WT 와 달라 ΔESM_mut 를 위치 대응으로 계산할 수 "
            "없다. S3/S5/S6 에서 스펙 §4 의 결측 규칙(train fold 평균 + 지시자)을 "
            "적용한다. 타겟을 코호트에서 빼지 않는다."
        ),
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"designs {d_pooled.shape}  wt {w_pooled.shape}  "
          f"length-mismatch targets {len(length_mismatch)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `/tmp/gate2d-venv/bin/python scripts/benchmark/22_gate2d_prepare_esm.py`
Expected: `designs (1728, 320)  wt (12, 320)  length-mismatch targets <N>`

`<N>` 이 0 이 아니면 그 타겟 수를 기록하고 계속한다 — 결측 규칙이 이미 있다.

- [ ] **Step 7: 커밋**

```bash
git add scripts/benchmark/22_gate2d_prepare_esm.py tests/test_gate2d_metrics.py
git add -f data/benchmark/gate2d_esm.index.json
git commit -m "feat(sr): ESM embeddings with token-aligned mutation-site deltas"
```

---

## Task 9: P3 — MSA 실행과 conservation feature

**Files:**
- Create: `scripts/benchmark/23_gate2d_prepare_msa_features.py`
- Read: `scripts/transcoder/50_full_msa.py` (MSA 실행 방식 재사용)
- Output: `public_data/benchmark/gate0/holdout_grid/msa_features.json`

- [ ] **Step 1: 홀드아웃 12 타겟 MSA 를 돌린다**

`50_full_msa.py` 의 호출 방식을 그대로 쓴다. 엔드포인트가 직렬화되므로 병렬 worker
는 의미가 없다 (commit `00a6931`). 타겟당 약 2,400 s → 12 타겟 약 8 h.

**2026-09-10 조사 결과 (실행 전 확인됨).** 래퍼는 정말 얇다. 다만 두 개의 함정이
있고 둘 다 동결 산출물을 건드린다.

| 사실 | 함의 |
|---|---|
| `COHORTS` 는 `calibration_v2` + `confirmatory` 로 하드코딩 (`50_full_msa.py:56`) | 격자 12 타겟은 두 코호트 어디에도 없다. `--only` 는 `targets()` 가 만든 목록을 필터링할 뿐이라 닿지 못한다 |
| ~~`holdout_targets.json` 의 `selected` 가 정확히 격자 12 타겟~~ **틀렸다 (아래 정정)** | — |
| **격자 코호트는 `resolved.targets` 다. `selected` 가 아니다** | `targets()` 는 `d["selected"]` 를 하드코딩해 읽으므로(`:131`) 코호트별 키 경로가 필요하다 |
| **`--out` 기본값이 `full_msa_manifest.json` (`50_full_msa.py:47,209`)** | **그 파일은 동결된 v2 multisource validation 의 산출물이다. 기본값으로 돌리면 그것을 덮어쓴다** |
| `MSA_DIR` 은 `BASE/"msa"` 하드코딩, CLI 없음 (`:46,238,264`) | a3m 은 공유 디렉터리에 떨어진다. 격자 12 타겟은 기존 20 타겟과 겹치지 않으므로 충돌은 없고, resume-from-a3m 이 그대로 작동한다 |
| MMseqs 엔드포인트는 **직렬화**되고 v2 런이 이 엔드포인트를 쓰고 있었다 | v2 런이 끝난 뒤에 착수한다. 동시 실행은 동결 검증과 경합한다 |

### 정정 (2026-09-10) — `selected` 는 격자 코호트가 아니다

controller 가 처음 "`selected` 가 정확히 격자 12 타겟" 이라고 적었다. **틀렸다.**
`selected` 의 12개 중 4개가 격자에 없고, 격자의 4개가 `selected` 에 없다.

```
selected - grid : 1vprA02  2iayA00  2jo7A00  2pgsA03
grid - selected : 1sh6A02  5pc8A00  3f2pA01  5xpdA02
```

원인은 파일 안에 이미 기록돼 있다. `holdout_targets.json` 의 `resolved.rule`:

> 백본 생성 전에 freeze 한 교체 규칙을 그대로 집행한다 — 실패한 선정 타겟을 같은
> 층의 예비로 `reserve_rank` 순서대로 교체하고, 목록을 다시 뽑지 않는다.

즉 `selected` 는 **동결 시점의 선정 목록**이고, `resolved.targets` 는 **실제 집행된
목록**이다. 백본 생성에 실패한 4개가 같은 stratum 의 예비로 교체됐고 그 이력이
남아 있다: `1sh6A02←2jo7A00`, `5xpdA02←1vprA02`, `3f2pA01←2pgsA03`,
`5pc8A00←2iayA00`. 격자는 `resolved.targets` 위에 만들어졌다.

검증: `resolved.targets` 는 12개이고 격자 타겟 집합과 **정확히 일치**하며,
`targets()` 가 읽는 키(`domain`·`stratum`·`length`·`pdb`·`superfamily`)를 모두 갖는다.

**따라서 라벨이 있는 타겟에 MSA 를 돌려야 한다.** `selected` 로 돌리면 라벨 없는
4개를 받아오고 필요한 4개를 빠뜨린다 — Gate 2 의 S4–S6 가 조용히 4/12 타겟을
잃는다.

따라서 이 Step 의 요구사항은 다음 **넷**이다.

1. **`COHORTS` 의 기본값을 바꾸지 않는다.** CLI 인자(예: `--cohorts holdout_grid`)로
   **덮어쓸 수 있게만** 만든다. 인자를 주지 않은 기존 호출은 바이트 단위로 같은
   동작이어야 한다 — 동결 v2 흐름이 그 기본값에 의존한다.
2. **`--out` 을 반드시 별도 manifest 로 넘긴다**:
   `public_data/benchmark/gate0/holdout_grid/holdout_msa_manifest.json`.
   `full_msa_manifest.json` 은 읽기 전용으로 취급한다.
3. **격자 코호트는 `resolved.targets` 에서 읽는다.** `targets()` 의 `d["selected"]`
   하드코딩(`:131`)을 코호트별 키 경로로 바꾼다. **기본 코호트는 계속 `selected` 를
   읽어야 한다** — 동결 v2 흐름이 그 동작에 의존한다.
4. **MSA 실행 로직을 복제하지 않는다.** 검색 설정(`uniref90`, `max_seqs=3000`,
   `threads=4`, `use_gpu=False`)을 다시 적으면 배포와 갈라진다 — 그것이 이 스크립트
   docstring 이 존재하는 이유다.

- [ ] **Step 2: 결측 처리 테스트를 먼저 쓴다**

```python
def test_msa_feature_missing_handling():
    import importlib
    prep = importlib.import_module("23_gate2d_prepare_msa_features")

    # test 타겟이 전부 undefined 여도 타겟은 유지되고 지시자가 1 이 된다.
    train = {"A": {"cons_mean": 0.8}, "B": {"cons_mean": 0.6}}
    out = prep.impute("C", None, train_stats=prep.train_stats(train))
    assert out["msa_undefined"] == 1
    assert abs(out["cons_mean"] - 0.7) < 1e-12

    # 정의된 타겟은 그대로 쓰고 지시자가 0 이다.
    out2 = prep.impute("A", {"cons_mean": 0.8}, train_stats=prep.train_stats(train))
    assert out2["msa_undefined"] == 0
    assert out2["cons_mean"] == 0.8

    # train fold 자체에서 정의 불가면 imputation statistic 이 없다 -> arm non-evaluable.
    assert prep.train_stats({}) is None
```

- [ ] **Step 3: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k msa_feature -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: 구현**

```python
#!/usr/bin/env python3
"""P3. a3m -> conservation feature. 결측 규칙은 스펙 §4 에 동결돼 있다.

핵심 제약 두 개.
  - conservation 프로파일은 **타겟/reference 로 한 번** 계산된다. candidate 의
    AF2 결과나 Gate 2 label 에 따라 달라지는 항이 들어가면 leakage 다.
  - MSA 가 얕거나 없다고 test 타겟을 코호트에서 빼지 않는다. depth 로 타겟을
    걸러내면 그 자체가 selection 문제가 된다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

#: 타겟 수준 conservation feature 이름. candidate 와 무관한 값만 둔다.
TARGET_FEATURES = ("cons_mean", "cons_p25", "cons_p75", "usable_hits_log10",
                   "coverage_median", "depth_median_log10")


def train_stats(train_by_target: Mapping[str, Mapping[str, float] | None]
                ) -> dict[str, float] | None:
    """train fold 의 feature 평균. 하나도 정의되지 않으면 None.

    None 은 "이 arm 을 non-evaluable 로 기록" 이라는 뜻이다. 타겟을 빼는 것이
    아니다 - 스펙 §4 규칙 5.
    """
    usable = [v for v in train_by_target.values() if v]
    if not usable:
        return None
    out: dict[str, float] = {}
    for name in TARGET_FEATURES:
        vals = [float(v[name]) for v in usable if name in v]
        if vals:
            out[name] = sum(vals) / len(vals)
    return out or None


def impute(target_id: str, features: Mapping[str, float] | None, *,
           train_stats: dict[str, float] | None) -> dict[str, float]:
    """정의된 값은 그대로, 정의되지 않은 값은 train fold 평균 + 지시자 1.

    test 타겟이 전부 undefined 여도 타겟을 유지한다.
    """
    if train_stats is None:
        raise ValueError(
            f"{target_id}: train fold 에 정의된 MSA feature 가 없어 imputation "
            "statistic 을 만들 수 없다. 이 arm 은 non-evaluable 이다."
        )
    if features:
        out = {name: float(features[name]) for name in TARGET_FEATURES if name in features}
        missing = [n for n in TARGET_FEATURES if n not in out]
        for name in missing:
            out[name] = train_stats.get(name, 0.0)
        out["msa_undefined"] = 1 if missing else 0
        return out
    out = {name: train_stats.get(name, 0.0) for name in TARGET_FEATURES}
    out["msa_undefined"] = 1
    return out
```

- [ ] **Step 5: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k msa_feature -v`
Expected: PASS

- [ ] **Step 6: a3m 파싱을 붙이고 12 타겟 feature 를 만든다**

`full_msa_manifest.json` 의 `msa_quality` 구조를 그대로 읽는다 (`usable_hits`,
`coverage.p25/p50/p75`, `depth.p50`). conservation 은 `conservation.tiers` 와 같은
정의를 쓴다 — 새 보존 정의를 만들지 않는다.

출력 스키마를 고정한다 — Task 11 의 `_block("msa")` 가 이 키를 읽는다. 정의되지
않는 값은 **`null` 로 쓴다.** 여기서 대치하지 않는다: imputation 은 LOTO train fold
평균으로 해야 하므로 fold 안에서만 할 수 있다 (Task 11 Step 8b).

```json
{
  "purpose": "P3 - 타겟 수준 MSA conservation feature. candidate 와 무관하다.",
  "feature_names": ["cons_mean", "cons_p25", "cons_p75",
                    "usable_hits_log10", "coverage_median", "depth_median_log10"],
  "per_target": {
    "1sp0A00": {"cons_mean": 0.71, "cons_p25": 0.52, "cons_p75": 0.9,
                "usable_hits_log10": 3.39, "coverage_median": 0.89,
                "depth_median_log10": 3.37},
    "5xpdA02": {"cons_mean": null, "cons_p25": null, "cons_p75": null,
                "usable_hits_log10": null, "coverage_median": null,
                "depth_median_log10": null}
  },
  "undefined_targets": ["5xpdA02"],
  "note": "undefined 타겟도 코호트에 남는다. 대치는 LOTO fold 안에서 한다."
}
```

Run: `/tmp/gate2d-venv/bin/python scripts/benchmark/23_gate2d_prepare_msa_features.py`
Expected: `wrote .../msa_features.json  targets 12  undefined <N>`

- [ ] **Step 7: 커밋**

```bash
git add scripts/benchmark/23_gate2d_prepare_msa_features.py tests/test_gate2d_metrics.py
git add -f public_data/benchmark/gate0/holdout_grid/msa_features.json
git commit -m "feat(sr): MSA conservation features that keep shallow targets in the cohort"
```

---

## Task 10: Gate 1

**Files:**
- Create: `scripts/benchmark/24_gate1_backbone_predictability.py`
- Output: `public_data/benchmark/gate0/gate1_backbone_predictability.json`

- [ ] **Step 1: 지표 테스트를 먼저 쓴다**

```python
def test_within_target_spearman_skips_constant_targets():
    per_target = G.within_target_spearman(
        q_true=[1.0, 1.0, 1.0, 0.2, 0.5, 0.9],
        q_pred=[0.1, 0.7, 0.3, 0.1, 0.5, 0.9],
        targets=["X", "X", "X", "Y", "Y", "Y"],
    )
    # X 는 q_true 상수 -> 제외. Y 는 완전 일치 -> +1.0
    assert len(per_target) == 1
    assert abs(per_target[0] - 1.0) < 1e-12


def test_within_target_spearman_requires_three_backbones():
    per_target = G.within_target_spearman(
        q_true=[0.1, 0.9], q_pred=[0.1, 0.9], targets=["Z", "Z"],
    )
    assert per_target == []
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k within_target_spearman -v`
Expected: FAIL — `AttributeError: ... has no attribute 'within_target_spearman'`

- [ ] **Step 3: `_gate2d.py` 에 구현**

```python
def within_target_spearman(q_true: Sequence[float], q_pred: Sequence[float],
                           targets: Sequence[str]) -> list[float]:
    """타겟 내 Spearman. 타겟 이름 오름차순.

    백본 3개 미만이거나 q_true 가 상수인 타겟은 제외한다 - 상관이 정의되지
    않거나 불안정하다. 제외 수는 호출자가 보고한다.
    """
    from scipy.stats import spearmanr

    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for t, a, b in zip(targets, q_true, q_pred):
        grouped[str(t)].append((float(a), float(b)))

    out: list[float] = []
    for _t, pairs in sorted(grouped.items()):
        if len(pairs) < 3:
            continue
        actual = [p[0] for p in pairs]
        if len(set(actual)) <= 1:
            continue
        rho = spearmanr(actual, [p[1] for p in pairs]).statistic
        if rho == rho:
            out.append(float(rho))
    return out


def top1_regret(q_true: Sequence[float], q_pred: Sequence[float],
                targets: Sequence[str]) -> list[float]:
    """타겟별 q_b(실제 최선) − q_b(예측 최선). RAPID 이 실제로 소비하는 양."""
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for t, a, b in zip(targets, q_true, q_pred):
        grouped[str(t)].append((float(a), float(b)))
    out: list[float] = []
    for _t, pairs in sorted(grouped.items()):
        best_true = max(p[0] for p in pairs)
        chosen = max(pairs, key=lambda p: p[1])[0]
        out.append(best_true - chosen)
    return out
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k within_target_spearman -v`
Expected: PASS

- [ ] **Step 5: Gate 1 스크립트를 쓴다**

```python
#!/usr/bin/env python3
"""Gate 1. AF2 를 보기 전 cheap feature 로 백본 q_b 순위를 예측할 수 있는가.

train : 157 백본 / 62 타겟 (backbones/backbone_labels.csv + mpnn_encoder.npy)
test  : 70 백본 / 12 타겟 (holdout_grid, informative 11)

GO  <=>  타겟 등가중 mean within-target Spearman >= 0.25
         AND 단측 90% LCB > 0
         AND informative 타겟 >= 8

모델은 절대 q_b 로 학습하고 **평가만 타겟 내에서** 한다. dev 코호트에서 백본이
2개 이상인 타겟이 16/62 뿐이므로 타겟 내 순위를 직접 학습할 수 없다. 이 구별을
결과 문장에서 지우지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "benchmark"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

import _gate2d as G                     # noqa: E402
import _gate2d_cohort as C              # noqa: E402
from rapid_sr.clustered import one_sided_lcb  # noqa: E402

GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"


def load_dev() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """dev 백본: encoder feature, joint_pass_yield, 설계 수 가중치, backbone_source."""
    rows = list(csv.DictReader((GATE0 / "backbones" / "backbone_labels.csv")
                               .open(encoding="utf-8")))
    features = np.load(GATE0 / "backbones" / "mpnn_encoder.npy")
    if features.shape[0] != len(rows):
        raise SystemExit(
            f"encoder 행 {features.shape[0]} 과 라벨 행 {len(rows)} 이 다르다. "
            "행 정렬이 깨졌으므로 중단한다."
        )
    y = np.array([float(r["joint_pass_yield"]) for r in rows])
    w = np.array([max(float(r["n_sequences_with_af2"] or 0), 1.0) for r in rows])
    src = [r["backbone_source"] for r in rows]
    return features, y, w, src


def fit_predict(x_train, y_train, w_train, x_test) -> np.ndarray:
    """설계 수로 가중한 이항 로지스틱. 13_gate0_target_level.py 와 같은 형태."""
    from sklearn.linear_model import LogisticRegression

    mu, sd = x_train.mean(0), x_train.std(0)
    sd[sd == 0] = 1.0
    succ = np.rint(y_train * w_train).astype(int)
    fail = np.rint(w_train).astype(int) - succ
    xs = np.vstack([(x_train - mu) / sd] * 2)
    ys = np.r_[np.ones(len(x_train)), np.zeros(len(x_train))]
    ws = np.r_[succ, fail].astype(float)
    keep = ws > 0
    model = LogisticRegression(max_iter=2000)
    model.fit(xs[keep], ys[keep], sample_weight=ws[keep])
    return model.predict_proba((x_test - mu) / sd)[:, 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(GATE0 / "gate1_backbone_predictability.json"))
    args = parser.parse_args()

    x_dev, y_dev, w_dev, src_dev = load_dev()
    grid = C.load_holdout_grid()
    index = json.loads((GATE0 / "holdout_grid" / "backbone_encoder.index.json")
                       .read_text(encoding="utf-8"))
    x_test_all = np.load(GATE0 / "holdout_grid" / "backbone_encoder.npy")
    row_of = {k: i for i, k in enumerate(index["backbone_keys"])}

    labelled = [b for b in grid.backbones if b.backbone_key in row_of]
    x_test = x_test_all[[row_of[b.backbone_key] for b in labelled]]
    q_true = [b.q_b for b in labelled]
    targets = [b.target_id for b in labelled]

    q_pred = fit_predict(x_dev, y_dev, w_dev, x_test)

    rhos = G.within_target_spearman(q_true, q_pred, targets)
    regrets = G.top1_regret(q_true, q_pred, targets)
    lcb = one_sided_lcb(rhos, alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    point = float(np.mean(rhos)) if rhos else float("nan")
    informative = len(rhos)  # within_target_spearman 이 제외 규칙을 이미 적용했다

    go = bool(point >= G.GATE1_RHO_MIN
              and lcb.get("exceeds_zero")
              and informative >= G.MIN_INFORMATIVE_TARGETS)

    result = {
        "purpose": "Gate 1 - backbone predictability. 정책 비교가 아니다.",
        "spec": "docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md",
        "does_not_do": [
            "알고리즘 제안",
            "타겟 내 순위 직접 학습 (dev 코호트가 허용하지 않는다)",
            "동결된 RAPID v2 전향 검증 수정",
        ],
        "train": {"n_backbones": int(len(y_dev)), "sources": sorted(set(src_dev)),
                  "note": "bioemu 백본이 train 에는 있고 test 에는 없다"},
        "test": {"n_backbones": len(labelled), "n_targets": len(set(targets))},
        "primary": {
            "metric": "target-equal mean within-target Spearman(q_hat_b, q_b)",
            "point": round(point, 4),
            "one_sided_90_lcb": lcb.get("lcb"),
            "informative_targets": informative,
            "per_target_spearman": [round(r, 4) for r in rhos],
        },
        "secondary": {
            "top1_backbone_regret_mean": round(float(np.mean(regrets)), 4),
            "per_target_regret": [round(r, 4) for r in regrets],
        },
        "frozen_go_rule": {
            "rho_min": G.GATE1_RHO_MIN,
            "lcb_alpha": G.LCB_ONE_SIDED_ALPHA,
            "min_informative_targets": G.MIN_INFORMATIVE_TARGETS,
        },
        "verdict": "GO" if go else "NO-GO",
        "no_go_reading": (
            "사전 지정된 시뮬레이션 모형 아래에서, NO-GO 는 rho ~ 0.44 규모의 효과에 "
            "대한 증거이고 rho ~ 0.18 규모(검정력 0.34)에 대해서는 약한 증거일 뿐이다."
        ),
        "prior_attempt": (
            "13_gate0_target_level.py 는 백본 수준을 시도했다가 타겟 수준으로 바꿨고 "
            "rfd3 타겟 내 rho -0.257 을 기록했다. 그 측정의 라벨은 correspondence "
            "metric 교체(2026-09-06)로 무효화됐다 - 같은 코호트를 현재 라벨로 재면 "
            "내부 sd 가 0.044 가 아니라 0.150 이다. standing negative result 로 "
            "인용하지 않되, 선행 시도가 있었다는 사실은 함께 보고한다."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"Gate 1 {result['verdict']}  rho={point:.4f}  "
          f"LCB={lcb.get('lcb')}  informative={informative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 실행**

Run: `/tmp/gate2d-venv/bin/python scripts/benchmark/24_gate1_backbone_predictability.py`
Expected: `Gate 1 GO|NO-GO  rho=<값>  LCB=<값>  informative=11`

`informative` 가 11 이 아니면 멈추고 이유를 밝힌다 — 코호트 구성이 스펙과 다르다.

- [ ] **Step 7: 커밋**

```bash
git add scripts/benchmark/24_gate1_backbone_predictability.py scripts/benchmark/_gate2d.py tests/test_gate2d_metrics.py
git add -f public_data/benchmark/gate0/gate1_backbone_predictability.json
git commit -m "feat(sr): Gate 1 with its threshold frozen and its prior attempt disclosed"
```

---

## Task 11: Gate 2

**Files:**
- Create: `scripts/benchmark/_gate2d_features.py`, `scripts/benchmark/25_gate2_within_backbone_selectability.py`
- Output: `public_data/benchmark/gate0/gate2_within_backbone_selectability.json`

- [ ] **Step 1: arm 정의 테스트를 먼저 쓴다**

```python
def test_arm_ladder_is_frozen_and_s6_is_primary():
    import _gate2d_features as F
    assert list(F.ARMS) == ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
    assert F.PRIMARY_ARM == "S6"
    # S2 는 known null 이 아니다 - LOTO 에서 타겟별 translation 이므로 S1 과 다르다.
    assert F.ARM_STATUS["S1"] == "known_null"
    assert F.ARM_STATUS["S2"] == "untested_low_expectation"
    assert F.ARM_STATUS["S6"] == "primary"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k arm_ladder -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_gate2d_features'`

- [ ] **Step 3: arm 정의를 구현한다**

```python
# scripts/benchmark/_gate2d_features.py
"""Gate 2 의 feature ladder. arm 목록은 스펙 §4 에서 동결됐다.

S6 하나가 판정 arm 이다. 나머지는 ablation/descriptive 이며 GO 판정에 쓰지 않는다 -
endpoint 가 하나여도 arm 을 골라 GO 를 선언하면 model selection multiplicity 다.
"""

from __future__ import annotations

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
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k arm_ladder -v`
Expected: PASS

- [ ] **Step 5: LOTO 누수 방지 테스트를 쓴다**

```python
def test_loto_splits_never_share_a_target():
    import _gate2d_features as F
    targets = ["A", "A", "B", "B", "C"]
    for train_idx, test_idx, held in F.loto_splits(targets):
        train_targets = {targets[i] for i in train_idx}
        test_targets = {targets[i] for i in test_idx}
        assert test_targets == {held}
        assert held not in train_targets
        assert not (train_targets & test_targets)
    assert len(list(F.loto_splits(targets))) == 3
```

- [ ] **Step 6: 실패를 확인하고 구현한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k loto_splits -v`
Expected: FAIL — `AttributeError: ... has no attribute 'loto_splits'`

```python
from collections.abc import Iterator, Sequence


def loto_splits(targets: Sequence[str]) -> Iterator[tuple[list[int], list[int], str]]:
    """Leave-One-Target-Out. 같은 타겟이 train 과 test 에 동시에 들어가지 않는다.

    백본을 쪼개지 않는 것은 타겟을 쪼개지 않는 데서 따라온다 - 백본은 타겟 안에
    중첩돼 있다.
    """
    for held in sorted(set(targets)):
        train = [i for i, t in enumerate(targets) if t != held]
        test = [i for i, t in enumerate(targets) if t == held]
        yield train, test, held
```

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k loto_splits -v`
Expected: PASS

- [ ] **Step 7: `build_features` 테스트를 쓴다**

```python
def test_build_features_shapes_and_non_evaluable():
    import _gate2d_cohort as C
    import _gate2d_features as F
    grid = C.load_holdout_grid()

    # S0 은 SoluProt 한 열이다.
    x0 = F.build_features("S0", grid.folds)
    assert x0.shape == (len(grid.folds), 1)

    # S1 은 ESM mean 320 열, S2 도 320 열(값은 다르다).
    x1 = F.build_features("S1", grid.folds)
    x2 = F.build_features("S2", grid.folds)
    assert x1.shape == (len(grid.folds), 320)
    assert x2.shape == (len(grid.folds), 320)
    # 같은 shape 이지만 같은 행렬이 아니다 - ΔESM_global 은 타겟별 translation 이다.
    import numpy as np
    assert not np.allclose(x1, x2)

    # S6 는 S5 보다 열이 많다.
    assert F.build_features("S6", grid.folds).shape[1] > \
           F.build_features("S5", grid.folds).shape[1]

    # 알 수 없는 arm 은 조용히 넘어가지 않는다.
    try:
        F.build_features("S9", grid.folds)
    except KeyError:
        pass
    else:
        raise AssertionError("정의되지 않은 arm 에서 KeyError 가 나와야 한다")
```

- [ ] **Step 8: 실패를 확인하고 `build_features` 를 구현한다**

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k build_features -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_features'`

`scripts/benchmark/_gate2d_features.py` 에 추가한다.

```python
import json
import os
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
DATA = PROJECT_ROOT / "data" / "benchmark"
GRID = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "holdout_grid"

#: arm 별 feature 블록. build_features 가 이 목록을 이어붙인다.
ARM_BLOCKS = {
    "S0": ("soluprot",),
    "S1": ("esm_mean",),
    "S2": ("esm_delta_global",),
    "S3": ("esm_delta_mut",),
    "S4": ("msa",),
    "S5": ("esm_delta_mut", "msa"),
    "S6": ("esm_delta_mut", "msa", "cheap"),
}


def _load_esm() -> tuple[np.ndarray, np.ndarray, dict, dict]:
    index = json.loads((DATA / "gate2d_esm.index.json").read_text(encoding="utf-8"))
    designs = np.load(DATA / "gate2d_esm_8m_designs.npy")
    wt = np.load(DATA / "gate2d_esm_8m_wt.npy")
    row_of = {sid: i for i, sid in enumerate(index["sequence_ids"])}
    wt_of = {t: i for i, t in enumerate(index["targets"])}
    return designs, wt, row_of, wt_of


def _block(name: str, folds) -> np.ndarray:
    """이름 하나에 해당하는 feature 블록. 행 순서는 folds 와 같다."""
    if name == "soluprot":
        return np.array([[f.soluprot] for f in folds], dtype=float)

    if name in ("esm_mean", "esm_delta_global", "esm_delta_mut"):
        designs, wt, row_of, wt_of = _load_esm()
        rows = np.vstack([designs[row_of[f.sequence_id]] for f in folds])
        if name == "esm_mean":
            return rows
        refs = np.vstack([wt[wt_of[f.target_id]] for f in folds])
        if name == "esm_delta_global":
            return rows - refs
        # esm_delta_mut: 변이 위치 토큰 차이의 평균. 위치 대응이 불가한 타겟은
        # 스펙 §4 결측 규칙에 따라 0 벡터 + 지시자로 들어간다(타겟을 빼지 않는다).
        tokens = np.load(DATA / "gate2d_esm_8m_tokens.npz")
        out, flag = [], []
        for f in folds:
            key = f"d{row_of[f.sequence_id]}"
            wkey = f"w_{f.target_id}"
            dt, wtok = tokens[key], tokens[wkey]
            if dt.shape[0] != wtok.shape[0]:
                out.append(np.zeros(dt.shape[1])); flag.append(1.0); continue
            diff = dt - wtok
            sites = np.where(np.abs(diff).sum(axis=1) > 0)[0]
            out.append(diff[sites].mean(axis=0) if len(sites) else np.zeros(dt.shape[1]))
            flag.append(0.0)
        return np.hstack([np.vstack(out), np.array(flag).reshape(-1, 1)])

    if name == "msa":
        feats = json.loads((GRID / "msa_features.json").read_text(encoding="utf-8"))
        per_target, names = feats["per_target"], feats["feature_names"]
        rows, flag = [], []
        for f in folds:
            vals = per_target[f.target_id]
            # null -> NaN. 여기서 대치하지 않는다 - train fold 평균이어야 하므로
            # LOTO fold 안에서만 할 수 있다.
            row = [np.nan if vals.get(k) is None else float(vals[k]) for k in names]
            rows.append(row)
            flag.append(1.0 if any(v != v for v in row) else 0.0)
        return np.hstack([np.array(rows, dtype=float), np.array(flag).reshape(-1, 1)])

    if name == "cheap":
        # 조성 20 열. MPNN score 는 sequences.csv 에 없으므로 넣지 않는다 -
        # 없는 feature 를 있는 것처럼 쓰지 않는다.
        alphabet = "ACDEFGHIKLMNPQRSTVWY"
        rows = []
        for f in folds:
            seq = SEQ_OF[f.sequence_id]
            n = max(len(seq), 1)
            rows.append([seq.count(a) / n for a in alphabet])
        return np.array(rows, dtype=float)

    raise KeyError(f"알 수 없는 feature 블록: {name}")


def build_features(arm: str, folds) -> np.ndarray | None:
    """arm 의 feature 행렬. non-evaluable 이면 None.

    None 은 "이 arm 을 non-evaluable 로 기록" 이라는 뜻이며 타겟을 빼는 것이
    아니다 - 스펙 §4 규칙 5.
    """
    if arm not in ARM_BLOCKS:
        raise KeyError(f"동결된 ladder 에 없는 arm: {arm}")
    blocks = []
    for name in ARM_BLOCKS[arm]:
        try:
            blocks.append(_block(name, folds))
        except FileNotFoundError:
            return None
    return np.hstack(blocks)
```

`SEQ_OF` 는 `sequences.csv` 에서 만든 `sequence_id -> sequence` 사전이다. 모듈
상단에 한 번만 만든다:

```python
import csv


def _load_sequences() -> dict[str, str]:
    with (GRID / "sequences.csv").open(encoding="utf-8") as handle:
        return {r["sequence_id"]: r["sequence"] for r in csv.DictReader(handle)}


SEQ_OF = _load_sequences()
```

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -k build_features -v`
Expected: PASS

- [ ] **Step 8b: fold 단위 대치를 구현한다**

스펙 §4 규칙 3–5 를 코드로 옮긴다. **test 타겟은 어떤 경우에도 빠지지 않는다.**

```python
def impute_train_fold(x: np.ndarray, train_idx) -> np.ndarray | None:
    """NaN 을 train fold 열평균으로 채운다. 지시자 열은 이미 붙어 있다.

    train fold 에서 그 열이 전부 NaN 이면 imputation statistic 을 만들 수 없다 ->
    None(= arm non-evaluable). 타겟을 빼는 것이 아니다 - 스펙 §4 규칙 5.
    """
    out = x.copy()
    train = out[list(train_idx)]
    for col in range(out.shape[1]):
        mask = np.isnan(out[:, col])
        if not mask.any():
            continue
        train_col = train[:, col]
        usable = train_col[~np.isnan(train_col)]
        if usable.size == 0:
            return None
        out[mask, col] = float(usable.mean())
    return out
```

`evaluate_arm` 의 fold 루프를 다음으로 바꾼다:

```python
    for train_idx, test_idx, _held in F.loto_splits(targets):
        x_fold = F.impute_train_fold(x, train_idx)
        if x_fold is None:
            return {"arm": arm, "label": F.ARM_LABELS[arm],
                    "status": "non_evaluable",
                    "reason": "train fold 에서 대치 통계량을 만들 수 없다"}
        model = Ridge(alpha=100.0)
        model.fit(x_fold[train_idx], y[train_idx])
        pred[test_idx] = model.predict(x_fold[test_idx])
```

Run: `/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v`
Expected: PASS (전체)

- [ ] **Step 9: Gate 2 스크립트를 쓴다**

```python
#!/usr/bin/env python3
"""Gate 2. mixed 백본 안에서 joint-pass 후보를 골라낼 수 있는가.

코호트 : mixed 백본 37개 / informative 타겟 11개
split  : LOTO (12 타겟). 백본을 쪼개지 않는다.
1차    : 타겟 등가중 Delta_Top4, 판정 arm 은 S6 하나

GO <=> 점추정 Delta_Top4 >= +0.10 AND 단측 90% LCB > 0 AND informative >= 8

기준점(측정 완료): SoluProt -0.001, oracle +0.326.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT")
                    or Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "benchmark"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

import _gate2d as G                     # noqa: E402
import _gate2d_cohort as C              # noqa: E402
import _gate2d_features as F            # noqa: E402
from rapid_sr.clustered import one_sided_lcb  # noqa: E402

GATE0 = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"


def evaluate_arm(arm: str, grid: C.Grid, mixed: list[C.Backbone],
                 endpoint: str = "joint") -> dict:
    """한 arm 의 타겟 등가중 Delta_Top4. LOTO 로 낸 예측만 쓴다."""
    from sklearn.linear_model import Ridge

    all_folds = grid.folds
    targets = [f.target_id for f in all_folds]
    x = F.build_features(arm, all_folds)
    if x is None:
        return {"arm": arm, "label": F.ARM_LABELS[arm],
                "status": "non_evaluable",
                "reason": "train fold 에 정의된 feature 가 없어 imputation "
                          "statistic 을 만들 수 없다"}
    y = np.array([(f.joint_pass if endpoint == "joint" else f.structural_pass)
                  for f in all_folds], dtype=float)

    pred = np.zeros(len(all_folds))
    for train_idx, test_idx, _held in F.loto_splits(targets):
        x_fold = F.impute_train_fold(x, train_idx)
        if x_fold is None:
            return {"arm": arm, "label": F.ARM_LABELS[arm],
                    "status": "non_evaluable",
                    "reason": "train fold 에서 대치 통계량을 만들 수 없다"}
        model = Ridge(alpha=100.0)
        model.fit(x_fold[train_idx], y[train_idx])
        pred[test_idx] = model.predict(x_fold[test_idx])

    score_of = {f.sequence_id: float(p) for f, p in zip(all_folds, pred)}
    per_backbone, bb_targets = [], []
    for b in mixed:
        labels = [(f.joint_pass if endpoint == "joint" else f.structural_pass)
                  for f in b.folds]
        per_backbone.append(G.delta_top4(
            labels, [score_of[f.sequence_id] for f in b.folds],
            [f.sequence_id for f in b.folds]))
        bb_targets.append(b.target_id)

    per_target = G.per_target_means(per_backbone, bb_targets)
    lcb = one_sided_lcb(per_target, alpha=G.LCB_ONE_SIDED_ALPHA, seed=G.BOOTSTRAP_SEED)
    point = float(np.mean(per_target))
    return {
        "arm": arm, "label": F.ARM_LABELS[arm], "status": F.ARM_STATUS[arm],
        "endpoint": endpoint,
        "delta_top4_target_equal": round(point, 4),
        "one_sided_90_lcb": lcb.get("lcb"),
        "informative_targets": len(per_target),
        "meets_threshold": bool(point >= G.GATE2_DELTA_MIN),
        "lcb_exceeds_zero": bool(lcb.get("exceeds_zero")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default=",".join(F.ARMS))
    parser.add_argument("--out",
                        default=str(GATE0 / "gate2_within_backbone_selectability.json"))
    args = parser.parse_args()

    grid = C.load_holdout_grid()
    mixed = C.mixed_backbones(grid)
    requested = [a.strip() for a in args.arms.split(",") if a.strip()]

    arms = {a: evaluate_arm(a, grid, mixed) for a in requested}
    arms_structural = {a: evaluate_arm(a, grid, mixed, endpoint="structural")
                       for a in requested}

    primary = arms.get(F.PRIMARY_ARM)
    if primary is None or primary.get("status") == "non_evaluable":
        verdict, note = "UNDECIDED", (
            f"판정 arm {F.PRIMARY_ARM} 이 실행되지 않았다. S0-S3 만 돌린 결과는 "
            "interim/descriptive only 이며 공식 Gate 2 판정이 아니다."
        )
    else:
        go = primary["meets_threshold"] and primary["lcb_exceeds_zero"] \
             and primary["informative_targets"] >= G.MIN_INFORMATIVE_TARGETS
        verdict, note = ("GO" if go else "NO-GO"), ""

    result = {
        "purpose": "Gate 2 - within-backbone selectability. 정책 비교가 아니다.",
        "spec": "docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md",
        "cohort": {"mixed_backbones": len(mixed),
                   "informative_targets": len({b.target_id for b in mixed})},
        "primary_arm": F.PRIMARY_ARM,
        "frozen_go_rule": {
            "delta_top4_min": G.GATE2_DELTA_MIN,
            "lcb_alpha": G.LCB_ONE_SIDED_ALPHA,
            "min_informative_targets": G.MIN_INFORMATIVE_TARGETS,
            "auc_is_descriptive_only": True,
        },
        "reference_points": {"soluprot": -0.001, "oracle": 0.326},
        "arms_joint_pass": arms,
        "arms_structural_pass_secondary": arms_structural,
        "verdict": verdict,
        "verdict_note": note,
        "no_go_reading": (
            "Under the prespecified simulation model, the gate has approximately 94% "
            "probability of GO for an effect corresponding to AUC ~ 0.70. Therefore, "
            "NO-GO would constitute evidence against an effect of approximately this "
            "magnitude under the assumed operating conditions, rather than proving the "
            "absence of any AUC >= 0.70 predictor."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"Gate 2 {verdict}  primary={F.PRIMARY_ARM} "
          f"delta={primary and primary.get('delta_top4_target_equal')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 10: interim 실행 (S0–S3). 판정을 내지 않는다**

Run:
```bash
/tmp/gate2d-venv/bin/python scripts/benchmark/25_gate2_within_backbone_selectability.py \
  --arms S0,S1,S2,S3 --out /tmp/gate2_interim.json
```
Expected: `Gate 2 UNDECIDED  primary=S6 delta=None`

`UNDECIDED` 가 나오는 것이 정상이다. S6 없이 GO/NO-GO 를 내면 스펙 위반이다.

- [ ] **Step 11: S0 이 기준점을 재현하는지 확인한다**

Run: `/tmp/gate2d-venv/bin/python -c "import json;d=json.load(open('/tmp/gate2_interim.json'));print(d['arms_joint_pass']['S0'])"`

`S0` 의 `delta_top4_target_equal` 은 SoluProt 을 **LOTO Ridge 로 학습한** 값이므로
스펙의 −0.001(SoluProt 원점수 직접 랭킹)과 정확히 같지 않아도 된다. 원점수 기준선은
Task 6 의 회귀 테스트가 이미 고정하고 있다.

- [ ] **Step 12: MSA 도착 후 전체 실행**

Run:
```bash
/tmp/gate2d-venv/bin/python scripts/benchmark/25_gate2_within_backbone_selectability.py
```
Expected: `Gate 2 GO|NO-GO  primary=S6 delta=<값>`

- [ ] **Step 13: 커밋**

```bash
git add scripts/benchmark/_gate2d_features.py scripts/benchmark/25_gate2_within_backbone_selectability.py tests/test_gate2d_metrics.py
git add -f public_data/benchmark/gate0/gate2_within_backbone_selectability.json
git commit -m "feat(sr): Gate 2 deciding on S6 alone, interim arms cannot rule"
```

---

## Task 12: 판정 등재와 스펙 정정

**Files:**
- Modify: `docs/results_of_record.md`
- Modify: `docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md` (§10 파일명)
- Modify: `pipeline-mcp/tests/test_results_of_record.py`

- [ ] **Step 1: 스펙 §10 의 산출물 표를 실제 파일명으로 고친다**

스펙은 `21_gate1_*` / `22_gate2_*` 로 적혀 있으나 실제 번호는 P1–P3 스크립트가
21–23 을 쓰므로 24 / 25 다. 표를 다음으로 교체한다.

| 경로 | 내용 |
|---|---|
| `scripts/benchmark/_gate2d.py` | 동결 상수 + 측정 primitive |
| `scripts/benchmark/_gate2d_cohort.py` | 코호트 로딩 |
| `scripts/benchmark/_gate2d_features.py` | feature ladder + LOTO |
| `scripts/benchmark/21_gate2d_prepare_encoder.py` | P1 |
| `scripts/benchmark/22_gate2d_prepare_esm.py` | P2 |
| `scripts/benchmark/23_gate2d_prepare_msa_features.py` | P3 |
| `scripts/benchmark/24_gate1_backbone_predictability.py` | Gate 1 |
| `scripts/benchmark/25_gate2_within_backbone_selectability.py` | Gate 2 |
| `tests/test_gate2d_metrics.py` | primitive + 기준점 회귀 테스트 |

- [ ] **Step 2: `results_of_record.md` 에 2축 게이트 절을 추가한다**

```markdown
## 2축 게이팅 실험 · 서열/백본 신호

| 값 | 수치 | 코호트 | 출처 |
|---|---|---|---|
| Gate 1 타겟 내 Spearman | (실행 후 기입) | 홀드아웃 70 백본 / informative 11 | `public_data/benchmark/gate0/gate1_backbone_predictability.json` → `primary.point` |
| Gate 2 Δ_Top4 (S6) | (실행 후 기입) | mixed 백본 37 / informative 11 | `public_data/benchmark/gate0/gate2_within_backbone_selectability.json` → `arms_joint_pass.S6.delta_top4_target_equal` |
| Gate 2 SoluProt 기준선 | −0.001 | 같음 | 같은 파일 → `reference_points.soluprot` |
| Gate 2 oracle 상한 | +0.326 | 같음 | 같은 파일 → `reference_points.oracle` |

문턱은 결과 전에 동결됐다 (`docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md`).
NO-GO 를 "효과 없음" 으로 쓰지 않는다 - 두 산출물의 `no_go_reading` 문구를 그대로 쓴다.
```

- [ ] **Step 3: 회귀 테스트에 claim 을 추가한다**

`pipeline-mcp/tests/test_results_of_record.py` 의 `CLAIMS` 에 추가:

```python
    ("Gate 2 SoluProt 기준선", "gate2_within_backbone_selectability.json",
     "reference_points.soluprot", 3),
    ("Gate 2 oracle 상한", "gate2_within_backbone_selectability.json",
     "reference_points.oracle", 3),
```

- [ ] **Step 4: 테스트를 돌린다**

Run:
```bash
PYTHONPATH=pipeline-mcp/src /tmp/gate2d-venv/bin/python -m pytest pipeline-mcp/tests/test_results_of_record.py -v
```
Expected: PASS

- [ ] **Step 5: 전체 테스트**

Run:
```bash
/tmp/gate2d-venv/bin/python -m pytest tests/test_gate2d_metrics.py -v
PYTHONPATH=pipeline-mcp/src /tmp/gate2d-venv/bin/python -m pytest pipeline-mcp/tests/ -q
```
Expected: 둘 다 PASS

- [ ] **Step 6: 커밋**

```bash
git add docs/results_of_record.md docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md pipeline-mcp/tests/test_results_of_record.py
git commit -m "docs(sr): register the gate verdicts where numbers must be cited from"
```

---

## Task 13: 판정표 적용

**Files:**
- Modify: `docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md` (§8 결과 기입)

- [ ] **Step 1: 두 산출물을 읽어 §8 판정표에 결과를 적는다**

```bash
/tmp/gate2d-venv/bin/python - <<'EOF'
import json
g1=json.load(open('public_data/benchmark/gate0/gate1_backbone_predictability.json'))
g2=json.load(open('public_data/benchmark/gate0/gate2_within_backbone_selectability.json'))
print('Gate 1', g1['verdict'], g1['primary']['point'])
print('Gate 2', g2['verdict'], g2['arms_joint_pass'].get('S6',{}).get('delta_top4_target_equal'))
EOF
```

- [ ] **Step 2: §8 표에 해당 행을 표시하고 결정을 적는다**

네 경우 중 하나다. **표를 고치지 않고 해당 행에 표시만 한다.**
GO/GO → B+C · GO/NO → B 만 · NO/GO → C 단독 · NO/NO → 연구축 종료.

- [ ] **Step 3: 커밋**

```bash
git add docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md
git commit -m "docs(sr): record which cell of the decision table the gates landed in"
```

---

## 남은 미확정 사항 (실행 중 확인)

| 항목 | 어디서 막히는가 | 대응 |
|---|---|---|
| dev `mpnn_encoder.npy` 를 만든 호출부 | Task 7 Step 7 | 찾지 못하면 **멈추고 보고**. 새 추출기를 만들면 Gate 1 의 train/test 가 다른 공간이 된다 |
| `50_full_msa.py` 의 타겟 지정 인자 | Task 9 Step 1 | 없으면 얇은 래퍼만 추가. MSA 실행 로직은 복제하지 않는다 |
| 설계 길이 ≠ WT 길이 타겟 수 | Task 8 Step 6 | 0 이 아니면 스펙 §4 결측 규칙 적용. **타겟을 빼지 않는다** |
| train(bioemu 포함) / test(rfd3+native) 구성 불일치 | Task 10 | Gate 1 산출물 `train.note` 에 이미 기록. 결과 문장에 함께 적는다 |
