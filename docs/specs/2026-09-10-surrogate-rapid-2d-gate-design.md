# Surrogate–RAPID 2축 게이팅 실험 설계

- 작성일: 2026-09-10
- 상태: **동결 (실행 전)**. 아래 GO 규칙과 지표 정의는 결과를 보기 전에 고정됐다.
- 범위: 새 AF2 0개. 기존 label 위에서 "연구 문제가 존재하는지"만 판정한다.
- 범위 외: 알고리즘 설계, RAPID v2 동결 검증 수정, 논문 집필.

## 0. 이 문서가 결정하는 것

surrogate 와 RAPID 를 하나의 계층적 할당 알고리즘으로 합치는 방향에서, **어느 층에
실제로 이용 가능한 신호가 있는지**를 두 축으로 판정한다. 알고리즘을 만들기 전 단계다.

```
                    sequence-level signal?
                      NO            YES
                 ┌────────────┬──────────────┐
 backbone   YES  │ B          │ B + C        │
 signal?         │ backbone   │ hierarchical │
                 │ prior only │ controller   │
                 ├────────────┼──────────────┤
            NO   │ STOP       │ C only       │
                 └────────────┴──────────────┘
```

- **B** = backbone-specific cheap prior. 현재 없다. `allocation.py:192` `set_target_prior()`
  는 Gate 0 값을 **타겟 수준** prior 로 넣고, 각 arm/backbone 은 그 타겟 사후평균을
  `pooling_strength=4.0` 만큼 다시 받는다 (`allocation.py:223-244`). 즉 백본별 사전
  정보 통로가 구조적으로 없다.
- **C** = sentinel/targeted 관측 분리와 selection-bias 보정.

## 1. 이미 측정된 것 (이 실험의 전제)

같은 홀드아웃 격자(`public_data/benchmark/gate0/holdout_grid/`, 12 타겟 · 70 백본 ·
1,728 폴드 중 사용가능 1,680, status!=ok 또는 metric 결측 48 제외)에서 2026-09-10 에
측정했다.

| 값 | 수치 | 뜻 |
|---|---|---|
| 타겟 내 백본 간 q_b 편차 (joint-pass) | 중앙값 **0.58**, 9/12 타겟 ≥ 0.25 | B 가 노리는 신호는 크다 |
| 백본 축퇴 | all-fail 14% · all-pass 33% · **mixed 53%** | 서열 선택이 의미있는 백본은 절반 |
| oracle Δ_Top4 (타겟 등가중) | **+0.326** | 서열층 상한 |
| SoluProt Δ_Top4 (타겟 등가중) | **−0.001** | 현행 cheap predictor 는 백본 내에서 무력 |
| SoluProt 백본 내 AUC (structural-pass) | **0.531** | 같은 사실의 다른 표현 |
| 백본 내 pairwise sequence identity | 중앙값 **0.678**, 서열 100% unique | T=0.1 이지만 과제가 성립한다 |
| mixed 백본 실패 원인 | 구조 단독 88% · 둘 다 9% · SoluProt 단독 3% | joint-pass 를 써도 순환성은 작다 |

**함의.** selection bias 는 surrogate 실력에 비례한다. oracle 이면 +0.326 으로 RAPID
posterior 를 확실히 오염시키지만, 현행 cheap predictor 로는 편향이 0 이고 이득도 0 이다.
따라서 **C 는 B 와 병렬인 대안이 아니라 Gate 2 통과에 조건부인 하위 확장**이다.

## 2. 선행 음성 결과 — 이 실험이 반복이 아닌 이유

`public_data/benchmark/sr/sequence_axis_ablation.json` 과
`docs/superpowers/specs/2026-09-03-rapid-transcoder-unified-design.md` 에 이미
서열축 음성 결과가 있다.

- 프로토콜: Ridge(alpha=100), leave-one-target-out, **82 CATH 타겟 / 9,840 설계**
- 1차 지표: **타겟 내 AF2 pLDDT Spearman 평균**
- 결과: 조성(0.047) · ESM2-8M mean(0.021) · ESM+조성(0.014) · ProtoMech PLT(0.008) ·
  CLT(−0.030) — **다섯 arm 전부 CI 가 0 을 포함**

이 코호트는 Gate 2 의 평가 대상(11 타겟 / mixed 백본 37개 = 888 폴드)보다
크고 검정력도 높다. 그래서 이 스펙은
다음을 명시한다.

> **S1(raw ESM mean)과 S2(ΔESM_global)는 사실상 이미 음성으로 시험됐다.** S2 는 unit
> 내에서 상수 평행이동이므로 S1 과 동일한 예측을 낸다(RF 는 임계값 분할, Ridge 는 절편,
> KNN/GP 는 유클리드 거리 — 전부 평행이동 불변). 두 arm 은 **신규 가설이 아니라 기지
> null 참조**로 둔다.

Gate 2 가 반복이 아닌 근거는 두 가지뿐이고, 그 이상을 주장하지 않는다.

1. **endpoint 가 다르다.** 선행은 연속 pLDDT 순위, 여기는 joint-pass Top-4 회수.
   joint-pass 에는 RMSD ≤ 2.0 이 들어가고 RMSD 의 서열 수준 분산은 47.8% 로 pLDDT
   31.3% 보다 크다 (`variance_decomposition_grid.json`). mixed 백본 실패의 88% 가
   구조 단독이라는 관찰과도 방향이 같다.
2. **unit 이 다르다.** 선행의 "타겟 내" 는 백본을 가로질러 풀링한다. 여기는 백본 내다.
3. **새 arm 이 있다.** S3(ΔESM_mut) · S4(MSA) · S5 는 선행에서 시험되지 않았다.

**사전 확률은 낮다고 기록한다.** 이 게이트의 기대값은 "새 방법이 될 것" 이 아니라
"세 방향 중 무엇이 존재하는 문제인지 8시간 안에 확정" 이다.

## 3. Gate 1 — backbone predictability

**질문.** AF2 를 보기 전 cheap feature 로 어느 백본의 q_b 가 높은지 예측할 수 있는가.
(백본마다 q_b 가 다르다는 것은 §1 에서 이미 확인됐다. 그것을 다시 묻지 않는다.)

| | 내용 |
|---|---|
| train | 157 백본 / 62 타겟. `backbones/backbone_labels.csv` 의 `joint_pass_yield`, feature `backbones/mpnn_encoder.npy` (157, 384) |
| test | 70 백본 / 12 타겟. q_b 는 `holdout_grid/af2_order_metric.csv` 에서 계산 |
| feature | ProteinMPNN encoder 384-D (ckpt `v_48_020`, dev 와 동일) |
| 1차 지표 | **타겟 내 Spearman(q̂_b, q_b) 의 12 타겟 평균**, target-clustered bootstrap |
| 2차 지표 | top-1 backbone regret = q_b(실제 최선) − q_b(예측 최선). RAPID 이 실제로 소비하는 양 |

**전역 AUC 를 1차 지표로 쓰지 않는다.** 분산의 79~86% 가 타겟 수준이므로
(`holdout_experiment_spec.json`), 전역 지표는 "타겟 평균 예측" 만으로 부풀려진다.

**검정력 (사전 고정).** 12 타겟 × 약 6 백본. n=6 Spearman 의 SD 약 0.45 →
평균의 SE 약 0.13 → 참값 ρ ≳ 0.26 부터 2 SE 로 탐지된다. 이보다 작은 참 효과에
대한 음성은 "효과 없음" 이 아니라 "이 검정력에서 미검출" 로 읽는다.

**한계 (사전 기록).** dev 코호트에서 백본이 2개 이상인 타겟은 **16/62** 뿐이다
(백본/타겟 중앙값 1). 모델은 절대 q_b 로 학습하고 **평가만 타겟 내에서** 한다.
따라서 Gate 1 은 "타겟 내 순위 학습" 이 아니라 "절대 예측기의 타겟 내 순위 유용성"
을 시험한다. 이 구별을 결과 문장에서 지우지 않는다.

## 4. Gate 2 — within-backbone selectability

| | 내용 |
|---|---|
| 코호트 | mixed 백본 37개, **informative 타겟 11개**. `1sh6A02` 는 6 백본 전부 q_b=1.00 이라 mixed 백본이 0개다 |
| split | **LOTO (12 타겟)**. 백본을 train/test 로 쪼개지 않는다 |
| 1차 endpoint | joint-pass (pLDDT≥85 ∧ rmsd_nonloop_order≤2.0 ∧ soluprot≥0.5) |
| 2차 endpoint | structural-pass (pLDDT ∧ RMSD). 37/37 백본이 이 기준으로도 mixed 이므로 SoluProt 순환성 없는 대조가 된다 |
| **1차 지표** | **타겟 등가중 Δ_Top4** = 백본별 (Top-4 joint-pass rate − q_b) 를 타겟 내 평균 후 11 타겟 평균 |
| 보조 지표 | 백본 내 AUC. **descriptive only** — GO 판정에 쓰지 않는다 |

타겟별 mixed 백본 수가 고르지 않다 (`2jokA01`·`3bqwA01`·`5fwaA02` 5개 … `3es1A01` 1개).
타겟 등가중이므로 `3es1A01` 의 단일 백본이 1/11 가중치를 그대로 받는다. LCB 조항이
이 한 백본으로 GO 가 뒤집히는 것을 막는다.

### Feature ladder

| arm | feature | 사전 지위 |
|---|---|---|
| S0 | SoluProt | 측정 완료. Δ_Top4 = **−0.001** |
| S1 | raw ESM mean | **기지 null** (§2, 82 타겟) |
| S2 | ΔESM_global | **기지 null.** unit 내 상수 평행이동 → S1 과 동일 예측. 그 null 을 명시적으로 기록하는 arm |
| S3 | ΔESM_mutation-site | **신규 가설** |
| S4 | MSA / conservation | **신규 가설** |
| S5 | S3 + S4 | **신규 가설** (ESM 단독 vs ESM+coevolution 반증) |
| S6 | S5 + 기존 cheap feature (조성, MPNN score) | 상한 참조 |

ΔESM 의 reference 는 타겟 WT 서열이다. label 이 아니라 입력이므로 LOTO 를 위배하지 않는다.

## 5. 동결된 GO 규칙

```
Gate 2 GO  ⟺  점추정 Δ_Top4 ≥ +0.10
              AND  타겟-클러스터 부트스트랩 one-sided 90% LCB > 0
              AND  informative 타겟 ≥ 8
```

AUC 조항은 두지 않는다. 이 코호트에서 Δ_Top4 +0.10 은 이미 AUC ≈ 0.640 을 요구하므로
`AUC ≥ 0.60` 조항은 절대 binding 되지 않는다. 그리고 **Δ_Top4 는 C 가 보정해야 할
selection bias 와 정확히 같은 추정량**이다 (q̂_b = Top-4 pass rate, 편향 = q̂_b − q_b).
숫자 하나가 "surrogate 가 쓸모 있는가" 와 "bias 문제가 존재하는가" 를 동시에 답하므로
endpoint 를 하나로 두고 multiplicity 보정을 피한다.

### AUC ↔ Δ_Top4 교정 (outcome-blind, 라벨 분포만 사용)

label-shift 노이즈 모형, 400 반복, 타겟 등가중. **실제 feature 를 쓰지 않는다.**

| mean AUC | 0.502 | 0.568 | **0.640** | 0.665 | 0.701 | 0.760 | oracle |
|---|---|---|---|---|---|---|---|
| Δ_Top4 | −0.001 | +0.053 | **+0.101** | +0.120 | +0.146 | +0.187 | +0.326 |

### GO 규칙 작동 특성 (n=11, 600 반복)

| 참 효과 Δ_Top4 | 대응 AUC | P(점추정 ≥ .10) | P(LCB > 0) | **P(GO)** |
|---|---|---|---|---|
| +0.001 (신호 없음) | 0.50 | 0.00 | 0.12 | **0.00** |
| +0.053 | 0.57 | 0.09 | 0.65 | **0.09** |
| +0.103 | 0.64 | 0.54 | 0.96 | **0.54** |
| +0.122 | 0.665 | 0.77 | 0.99 | **0.77** |
| +0.148 | 0.70 | 0.94 | 0.99 | **0.94** |

교정 표와 이 표는 별개의 시뮬레이션 실행이다(400 vs 600 반복). 같은 delta 에서
Δ_Top4 가 ±0.002 다르게 나오는 것은 그 때문이고, 어느 쪽도 실제 feature 를 쓰지 않는다.

두 가지를 사전 등록한다.

1. **거짓 GO 위험은 0 이다.** 신호가 없을 때 GO 확률 0.00. 점추정 조항이 통제를
   담당하고 LCB 조항은 사실상 non-binding 한 단일타겟 방어 장치다.
2. **NO-GO 의 해석을 미리 고정한다.** 임계값과 참값이 같을 때(AUC 0.64) 검정력이
   0.54 이므로, NO-GO 는 "효과가 없다" 가 아니라 **"AUC ≈ 0.70 이상의 효과는 없다"**
   로만 읽는다. **결과를 본 뒤 이 문장과 임계값을 바꾸지 않는다.**

### 연산 정의 (모호성 제거)

- **q_b 의 분모는 그 백본의 사용가능 설계 전부**(격자에서 24개, status!=ok 제외 후)다.
  홀드아웃 부분집합이 아니다. Δ_Top4 의 두 항이 같은 분모를 보게 하기 위함이다.
- **Top-4 동점 처리**: 점수 동점이면 `sequence_id` 오름차순으로 끊는다. 무작위
  동점 처리를 쓰지 않는다 — 재현되지 않는다.
- **Gate 1 의 타겟 내 Spearman**: 백본이 3개 미만인 타겟은 상관이 불안정하므로
  제외하고 그 수를 보고한다. 홀드아웃 12 타겟은 전부 5~6개이므로 현재 제외는 0 이다.
- **Δ_Top4 의 K**: K=4 로 고정한다. `m2_endpoint_dynamic_range.json` 의
  `min_probe_per_unit = 4` 와 같은 값이며, 이 실험에서 다시 고르지 않는다.

## 6. Leakage 통제

- LOTO. 같은 백본의 형제 서열이 train/test 에 동시에 있으면 안 된다.
- 같은 타겟의 백본들을 train/test 로 나누지 않는다.
- 통계 단위는 **target cluster** 다. 1,680 서열이나 37 백본으로 추론하지 않는다.
- `min_informative_clusters = 8`. `holdout_experiment_spec.json` 의 규칙을 승계한다.
- 임계값 재최적화 금지. pLDDT 85 / RMSD 2.0 / SoluProt 0.5 는 다시 고르지 않는다
  (`THRESHOLD_PROVENANCE`).
- SoluProt 순환성은 structural-pass 2차 endpoint 로 대조한다.
- Gate 1 의 test set 백본은 encoder 학습에 쓰이지 않았음을 재확인한다
  (홀드아웃 12 타겟은 정의상 인코더 학습 제외 코호트).

## 7. 사전 준비 (AF2 0개)

| | 내용 | 비용 |
|---|---|---|
| P1 | 홀드아웃 70 백본의 MPNN encoder feature 추출. 입력 PDB 는 `/opt/protein_pipeline/outputs/holdout_*_rfd3/rfd3/designs/` (267개 중 backbone_key 로 70개 선택). **deploy 체크아웃은 읽기만 하고 산출물은 이 작업 트리에 쓴다** | 분 단위 |
| P2 | 1,680 서열 + 타겟별 WT reference 의 ESM 임베딩 | 분 단위 |
| P3 | S4–S6 용 MSA. **홀드아웃 12 타겟은 MSA 0/12** 다. 진행 중인 full MSA run 은 calibration_v2 코호트(18/24)이고 홀드아웃이 아니다 | 타겟당 ~2,400 s, 엔드포인트 직렬화(00a6931) → **~8 h wall** |

### 실행 순서 (결정됨)

**S0–S3 를 먼저 돌려 Gate 2 1차 판정을 확보하고, MSA 12건을 병행한다.** 도착하면
S4–S6 arm 을 추가한다. **arm 목록(S0–S6)과 GO 규칙은 이 문서에서 전부 동결됐으므로
사후 arm 추가가 아니다.** S4–S6 결과는 같은 스펙의 2차 보고로 낸다.

## 8. 판정표

| Gate 1 | Gate 2 | 결정 |
|---|---|---|
| GO | NO | **B 만.** backbone-specific surrogate prior + calibrated prior strength. C 는 하지 않는다 |
| GO | GO | **B + C.** hierarchical controller. sentinel/targeted 분리를 검증할 이유가 생긴다 |
| NO | GO | **C 단독.** B 를 억지로 합치지 않는다 |
| NO | NO | **이 연구축을 접는다.** negative result 로 보고하고 RAPID 자체에 집중한다 |

## 9. 이 실험이 하지 않는 것

- 알고리즘 제안. 신호 존재 확인만이다.
- **동결된 RAPID v2 전향 검증에 어떤 변경도 넣지 않는다.** 그 검증이 끝나야
  `RAPID-only` 라는 깨끗한 baseline 이 생긴다.
- ESM 크기 스케일링. 8M vs 150M 은 이미 음성이다 (Supp. Note 3, pLDDT Top-5 recall
  +0.007, Holm p = 0.72). 이 게이트에서 다시 묻지 않는다.
- clustering 알고리즘 비교. K-means vs random 도 이미 음성이다 (Supp. Note 4).
- `meta_surrogate_prototype/` 의 수치 인용. `06_global_transfer_test.py:25-30` 과
  `07_strict_cross_validation.py:25-30` 이 목적함수의 절반을 hydrophobicity 의
  결정론적 함수로 시뮬레이션했다. "Zero-Shot 28.4% 향상" 과 "LORO 100% 성공" 은
  **철회 대상이며 baseline 으로도 쓰지 않는다.**

## 10. 산출물

| 경로 | 내용 |
|---|---|
| `scripts/benchmark/21_gate1_backbone_predictability.py` | Gate 1 |
| `scripts/benchmark/22_gate2_within_backbone_selectability.py` | Gate 2 (S0–S6) |
| `public_data/benchmark/gate0/gate2d_spec.json` | 이 문서의 기계가독 동결본 (임계값·지표·코호트) |
| `public_data/benchmark/gate0/gate1_backbone_predictability.json` | Gate 1 결과 |
| `public_data/benchmark/gate0/gate2_within_backbone_selectability.json` | Gate 2 결과 |
| `docs/results_of_record.md` | 판정 수치 추가 (인용은 이 파일 경유) |
