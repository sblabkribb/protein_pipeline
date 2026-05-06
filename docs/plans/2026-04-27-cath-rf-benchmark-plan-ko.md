# CATH 기반 Local Surrogate 벤치마크 계획 - RF 최적성 및 N=30 보수성 검증

**작성일**: 2026-04-27
**작성자**: Sisyphus Orchestrator
**상위 문서**: `2026-04-24-local-expert-memory-bank-strategy-ko.md`, `2026-04-15-hierarchical-meta-surrogate-bo-design.md`
**데이터 소스**: `/opt/protein_pipeline/cath_outputs/` (CATH test 15 타겟)

---

## 1. 논문에서 증명할 두 가지 주장

| 주장 | 정당화 메커니즘 |
|---|---|
| **(A)** evolution mode의 local surrogate로 **Random Forest가 합리적/최적의 선택**이다 | 8개 모델 ablation, 다중 메트릭, 통계검정 |
| **(B)** 학습 샘플 **N=30은 보수적으로 충분**하다 (plateau) | N ∈ {5,10,20,30,50,80} 학습곡선 |

**왜 중요한가**: `evolution.py`는 신규 타겟마다 30개 AF2 라벨로 즉석 RF를 학습한다. 리뷰어가 "왜 RF? 왜 30개?"를 물을 때 답할 수 있어야 함.

**Surrogate target (이중)**:
- **Target 1: pLDDT** (ColabFold) — 메인. evolution.py와 직접 매칭, 구조 적합도
- **Target 2: SoluProt** — 평행 평가. 용해도 표현 학습이 RF로 잘 되는가
- 두 target 모두 동일 모델 zoo / 프로토콜 / 메트릭으로 평가 → 결과 일관성이 RF 일반화의 증거

---

## 2. 데이터 인벤토리 (확정)

```
/opt/protein_pipeline/cath_outputs/
└── 15 × cath_test_*/  (CATH test 15 타겟, 모두 완료)
    └── tiers/{30,50,70}/
        ├── af2_scores.json     # ColabFold pLDDT
        ├── soluprot.json       # SoluProt 점수
        └── designs.fasta       # ProteinMPNN 시퀀스 40개
```

| 메트릭 | 라벨 수 | 비고 |
|---|---|---|
| pLDDT (ColabFold) | **1,766** (98.1%) | 일부 AF2 실패; 타겟별 92~120 |
| SoluProt | **1,800** (100%) | 완전 |
| Relax | **0** | 없음 → **본 벤치마크에서 제외** |

**타겟별 라벨 수** (pLDDT 기준):
- 평균 117.7, 중앙값 120, 최소 92 (1ibvC00), 최대 120
- **15 타겟 모두 N=80 ablation까지 가능** (80 train + 20 holdout이 가능한 라벨 수 ≥ 100)
- 단 **1ibvC00**은 라벨 92 → N=80 ablation 시 holdout=12로 축소

**시퀀스 = 3개 conservation tier에서 mix**: tier가 conservation 제약 강도(30/50/70%)를 다르게 부여하므로 시퀀스 다양성 ↑. 한 타겟의 120개를 단일 pool로 취급해도 evolution 시나리오와 부합 (evolution도 conservation tier 다중 사용).

---

## 3. 방법론

### 3.1 특징 추출 (Feature Extraction)
- **메인**: ESM-2 8M (`facebook/esm2_t6_8M_UR50D`), 320D mean-pooled embedding
  - 현재 `evolution.py`와 동일 → 직접 비교 가능
- **보조 ablation**: ESM-2 150M (`facebook/esm2_t30_150M_UR50D`), 640D
- 모든 시퀀스 한 번에 임베딩 → `data/cath_pilot_embeddings.npy`로 캐시

### 3.2 실험 1 — 모델 비교 (RF 최적성 증명)

**비교 대상 8종**:

| 모델 | 라이브러리 | 하이퍼파라미터 | 역할 |
|---|---|---|---|
| **RF** (baseline) | sklearn | `n_estimators=100, random_state=42` | 현재 evolution.py |
| XGBoost | xgboost | `n_estimators=100, max_depth=6, lr=0.1` | gradient boosting #1 |
| LightGBM | lightgbm | `n_estimators=100, num_leaves=31, lr=0.1` | gradient boosting #2 |
| GP-RBF | sklearn | `RBF + WhiteKernel`, normalize_y=True | kernel-based, BO 정통 |
| MLP | sklearn | `(128, 64)`, max_iter=500 | deep baseline |
| Ridge | sklearn | `alpha=1.0` | 선형 baseline |
| KNN | sklearn | `n_neighbors=5` | 비파라미터 baseline |
| Random | - | shuffle | sanity check |

**프로토콜** (per-target nested CV, **두 target 양쪽**):
```
For each surrogate_target in [pLDDT, SoluProt]:
  For each target (15):
    For each seed in [42, 123, 7, 2024, 31337]:  # 5 seeds
      1. Shuffle target's ~120 labels
      2. Split: 30 train / 90 test  (메인 설정)
      3. Train each model on (X_train, y_train[surrogate_target])
      4. Predict y_pred on test pool
      5. Record metrics
Aggregate: 2 targets × 15 × 5 seeds = 150 paired observations per model
```

**메트릭** (다중):

| 메트릭 | 의미 | 평가 위치 |
|---|---|---|
| **Spearman ρ** | 순위 보존 (BO에 결정적) | held-out 90 |
| **Top-5 recall** | 예측 Top-5 ∩ 실제 Top-5 / 5 | held-out 90 |
| **Top-20 recall** | 예측 Top-20 ∩ 실제 Top-20 / 20 | held-out 90 (evolution.py와 매칭) |
| **R²** | 회귀 적합도 | held-out 90 |
| **MAE** | 절대 오차 | held-out 90 |
| ★ **BO uplift** | (예측 Top-20 평균 actual pLDDT) − (random 20개 평균) | held-out 90 |

★ **BO uplift가 메인 그림 메트릭**. evolution.py 시나리오와 1:1 매칭.

**통계검정**:
- 모델 쌍별 **paired Wilcoxon signed-rank** (n=75 paired observations)
- 다중비교 보정: Holm-Bonferroni
- 95% CI: target-level bootstrap (1,000 resamples)

### 3.3 실험 2 — N 샘플 크기 ablation (N=30 보수성 증명)

**N values**: 5, 10, 20, **30**, 50, 80
- N=100은 1ibvC00의 라벨 부족 + holdout이 너무 작아져 제외
- N=80 holdout=20 (1ibvC00은 12)

**Models**: RF + 실험 1 Top-3 (예: XGBoost, LightGBM, GP)
- 비교군이 있어야 "30이 plateau"라는 주장이 모델 의존적이지 않음을 보일 수 있음

**프로토콜**: 실험 1과 동일 (5 seeds × 15 targets)

**기대 그림 (Figure 3)**:
- X축 N (5→80), Y축 Spearman ρ 또는 BO uplift
- 4개 모델 곡선 + 95% CI band
- N=30 위치에 vertical line ("conservative choice")
- "N=30 → N=80에서 RF의 평균 ρ 증가량 < ε" 형태로 정량화

**한계 효용 정량화**: 
- Δρ(N=30→80) 와 Δρ(N=10→30) 비교
- 추가 50개 AF2 호출 비용 (~30분 × 50 = 25시간 L4) vs 성능 이득 트레이드오프

### 3.4 실험 3 — ESM 임베딩 크기 ablation (Supplementary)

- ESM-2 8M (320D) vs ESM-2 150M (640D)
- RF 단독, N=30 고정
- Supplementary 1 figure: bar plot Spearman / BO uplift
- **목표**: 640D가 320D보다 유의미하게 좋지 않음을 보여 "8M이 충분"임을 정당화 (또는 그 반대를 발견)

---

## 4. 통계 방법론 (소표본 N=15 보정)

15 타겟은 작으므로 다음을 엄격히 적용:

1. **Paired analysis**: 항상 동일한 (target, seed, split)에서 모델들을 비교 → 평가 분산 제거
2. **Bootstrap CI**: 타겟 단위로 1,000회 resample → 95% CI
3. **Multiple seeds**: 5 random seed로 평균 → split 분산 제거
4. **Effect size**: p-value 외에 Cliff's δ (paired) 보고
5. **Per-target plots**: 보조 figure로 15 타겟 각각의 결과 (RF win/loss 패턴)

---

## 5. 산출물

### 코드 (신규)
```
scripts/benchmark/
  ├── 00_prepare_data.py           # cath_outputs → master CSV (sequence, target, tier, pLDDT, SoluProt)
  ├── 01_compute_embeddings.py     # ESM-2 임베딩 생성/캐시 (8M, 150M)
  ├── 02_model_comparison.py       # 실험 1: 8 모델 비교 (per-target CV)
  ├── 03_sample_size_ablation.py   # 실험 2: N ablation
  ├── 04_esm_size_ablation.py      # 실험 3: 320D vs 640D
  ├── 05_aggregate_and_test.py     # 통계검정, bootstrap CI, paired Wilcoxon
  └── 06_make_figures.py           # 논문 그림 생성
```

### 데이터/캐시
```
data/benchmark/
  ├── cath_pilot_dataset.csv       # 1,800행 (target, tier, seq_id, sequence, pLDDT, SoluProt)
  ├── cath_pilot_emb_320d.npy      # ESM-2 8M 임베딩
  ├── cath_pilot_emb_640d.npy      # ESM-2 150M 임베딩 (실험 3용)
  └── results/
      ├── exp1_model_comparison.parquet
      ├── exp2_sample_size.parquet
      └── exp3_esm_size.parquet
```

### 논문 그림 (예상)
| ID | 내용 | 핵심 메시지 |
|---|---|---|
| **Fig 2a** | 8 모델 × Spearman ρ bar plot, **pLDDT + SoluProt 2-panel** | RF는 GP/XGB/LGBM과 통계적으로 유의차 없음 |
| **Fig 2b** | 8 모델 × BO uplift violin plot, **pLDDT + SoluProt 2-panel** | RF의 실용적 우위: random 대비 +X 안정적 확보 |
| **Fig 3** | N ∈ {5..80} × Spearman ρ 학습곡선 (4 모델), **pLDDT + SoluProt 2-panel** | N=30에서 plateau, 두 target 모두 일관 |
| **Fig 4 (supp)** | ESM 320D vs 640D bar plot, 2-panel | 8M ESM-2가 두 target 모두에 충분 |
| **Fig 5 (supp)** | 15 타겟 × 2 target 별 RF 승패 heatmap | RF의 일관성 |

### 논문 표
| ID | 내용 |
|---|---|
| **Tab 2** | 8 모델 × 6 메트릭 (mean ± 95% CI), Wilcoxon p-value (vs RF) |
| **Tab 3** | N ∈ {5..80} × Top-3 모델, BO uplift |
| **Tab S1** | 15 CATH 타겟 메타정보 (PDB ID, length, CATH class) |

---

## 6. 컴퓨트 & 타임라인

**Phase A**: 데이터 준비 (1일)
- 임베딩 생성: 1,800 seq × ESM-2 8M = ~10분 GPU
- 동 ESM-2 150M = ~30분 GPU
- 데이터 master CSV 빌드: 5분

**Phase B**: 벤치마크 실행 (0.5~1일, CPU only)
- 실험 1: 8 models × 15 targets × 5 seeds = 600 fits, 각 fit < 1초 (320D × 30 sample)
- 실험 2: 4 models × 6 N values × 75 fits = 1,800 fits
- 실험 3: 1 model × 2 ESM sizes × 75 fits = 150 fits
- 모두 합쳐도 < 30분 CPU

**Phase C**: 분석 및 시각화 (1일)
- 통계검정, bootstrap, figure 생성

**Phase D**: 논문 draft 통합 (1~2일)

**총 예상**: **3~4일** (생성 작업 없음, 분석만)

---

## 7. 리스크 및 대응

| 리스크 | 영향 | 완화 |
|---|---|---|
| **N=15 타겟 작음** | 통계 검정력 부족 | seed 5개 + bootstrap CI + paired analysis로 보정. 결과가 명확하면 OK, 애매하면 cath_train에서 30개 추가 실행 (~5일) |
| **Relax 데이터 없음** | 다목적 모델 평가 불가 | pLDDT 단일 목적으로 한정. SoluProt도 이미 있으므로 supplementary로 SoluProt 예측도 추가 가능 |
| **ProteinMPNN 다양성 부족** | pool이 redundant → 모든 모델 비슷한 점수 | 3개 conservation tier가 다양성 보장. 시퀀스 identity heatmap 사전 검증 |
| **AF2 일부 실패 (1ibvC00)** | 균등하지 않은 라벨 수 | 타겟별 가용 라벨에 따라 dynamic holdout (max 80 train + 12~20 holdout) |
| **결과가 "RF가 별로다"로 나오는 경우** | 논문 내러티브 변경 필요 | 정직하게 "XGBoost를 새 default로" 권장 + evolution.py 변경 PR. 과학이 우선 |

---

## 8. 실행 로드맵 (Action Items)

- [ ] **Day 1 AM**: `00_prepare_data.py` — cath_outputs scan → master CSV (예상 1,800행)
- [ ] **Day 1 PM**: `01_compute_embeddings.py` — ESM-2 8M + 150M 임베딩 생성
- [ ] **Day 2 AM**: `02_model_comparison.py` — 실험 1 8 모델 (10분 실행)
- [ ] **Day 2 PM**: `03_sample_size_ablation.py` — 실험 2 N ablation
- [ ] **Day 3 AM**: `04_esm_size_ablation.py` + `05_aggregate_and_test.py`
- [ ] **Day 3 PM**: `06_make_figures.py` — 논문 그림 5종
- [ ] **Day 4**: 논문 본문 4.x 절 통합 작성

---

## 9. 의사결정 (확정)

| 결정 | 값 |
|---|---|
| 데이터 소스 | `cath_outputs/` 15 타겟 (사용자 확정) |
| 모델 zoo | 8개 (RF + XGB + LGBM + GP + MLP + Ridge + KNN + Random) |
| ESM ablation | 포함 (320D vs 640D supplementary) |
| BO-style 평가 | 포함 (BO uplift = 메인 메트릭) |
| 평가 프로토콜 | per-target 5-seed CV (75 paired observations) |
| N values | 5, 10, 20, 30, 50, 80 |
| 통계 | paired Wilcoxon + Holm-Bonferroni + bootstrap CI |

## 10. Open Questions (논문 작성 시 결정)

- ~~Q1: SoluProt도 별도 surrogate로 보고할지?~~ → **결정**: 포함 (사용자 확정)
- Q2: 그림 Fig 2/3을 main text vs supplementary 분배
- Q3: 결과가 "RF ≈ XGBoost"로 나올 경우 default 변경 여부

---

**다음 단계**: 본 plan에 사용자 승인 → `writing-plans` 스킬로 구체적 구현 계획 작성 → 실행.
