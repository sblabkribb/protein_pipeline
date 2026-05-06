# 파이프라인 진화 전략: Target-Expert Memory Bank 및 대규모 데이터 생성 계획

**작성일**: 2026-04-24
**작성자**: Sisyphus Orchestrator
**관련 문서**: `2026-04-15-hierarchical-meta-surrogate-bo-design.md`, `2026-04-24-meta-surrogate-bias-analysis-ko.md`

---

## 1. 개요 및 배경 (Executive Summary)

현재 파이프라인의 `evolution` 모드는 AF2 오라클 비용을 줄이기 위해 도입되었으나, 매 실행마다 타겟 단백질에 대해 맨바닥에서 Random Forest(RF) 모델을 훈련하는 'Local Surrogate' 방식을 취하고 있습니다. 이는 극소수의 데이터(N=30)에 과적합되어 다양성을 상실하는 문제를 낳고 있습니다. 

본 문서는 이를 해결하기 위해 **"타겟별 전문가(Local Expert) 모델을 지속적으로 축적(Memory Bank)하고, 이를 바탕으로 점진적으로 Global Surrogate 및 GFlowNet으로 진화하는 아키텍처"**에 대한 청사진을 제시합니다. 아울러 CATH 데이터셋(1,470개 타겟)을 활용한 초기 대규모 데이터 생성(Cold-Start)을 위한 **클라우드 인프라(NCP L4 4ea) 및 추론 최적화 가이드라인**을 정의합니다.

---

## 2. 3단계 아키텍처 진화 전략 (Phased Architecture Strategy)

단일 Global 모델을 무에서 유로 창조하는 대신, 바텀업(Bottom-up) 방식으로 데이터와 지식을 축적합니다.

### Phase 1: Memory Accumulation (현재 ~ 1,500 타겟) - *구현 완료*
- **목표**: 파이프라인이 실행될 때마다 버려지던 Local RF 모델을 보존.
- **방식**: 각 타겟 단백질에 대해 학습된 Surrogate 모델을 `models/experts/expert_<target_name>_<run_id>.pkl` 형태로 메타데이터와 함께 아카이빙.
- **효과**: CATH 1,470개 타겟을 돌리는 동안, 서로 다른 단백질 구조(Fold)에 특화된 1,470개의 '분야별 전문가 모델'이 확보됨. S3 및 MLflow와 연동되어 자동 백업됨.

### Phase 2: Memory-Based Routing (1,500 ~ 10,000 타겟) - *Next Step*
- **목표**: 새로운 타겟 입력 시 AF2 초기 호출(30회) 비용 제거.
- **방식**: (k-Nearest Experts 알고리즘) 새로운 Target X가 입력되면, 구조적/서열적으로 가장 유사한 과거의 Top-K Expert 모델들을 불러옴. 이들이 만장일치로 좋다고 평가한 서열은 AF2 없이 채택하고, 의견이 엇갈리는(Variance가 큰) 낯선 서열에 대해서만 AF2 오라클을 호출하여 능동 학습(Active Learning) 수행.
- **효과**: AF2 호출 비용 최대 80% 이상 절감 및 탐색 공간 확장.

### Phase 3: GFlowNet & Global Reward Model (10,000 타겟 이상) - *장기 목표*
- **목표**: 단백질 생성 패러다임을 "생성 후 필터링"에서 "목적 기반 생성"으로 전환.
- **방식**: 축적된 수십만 개의 데이터(Sequence -> AF2/SoluProt Score)를 활용해 거대한 미분 가능 Global MLP를 훈련. 이를 Reward Model로 삼아 ProteinMPNN 기반의 **GFlowNet**을 도입하거나 **Classifier Guidance**를 적용.
- **효과**: 실패할 서열은 아예 생성하지 않음. 다양성과 적합성을 동시에 만족하는 서열군(Pareto Front) 다이렉트 샘플링 가능.

---

## 3. 대규모 데이터 생성 인프라 및 소요 시간 예측

CATH 1,470개 타겟에 대한 Phase 1 (데이터 및 Expert 모델 수집) 실행을 위한 인프라 계획입니다.

### 3.1 하드웨어 권장 사항 (NCP 클라우드)
- **추천 인스턴스**: **L4 (24GB) x 4ea**
- **비교군 (A100 8ea) 대비 우위 사유**:
  - **비용 효율성**: L4가 A100 대비 절대 속도는 2~3배 느리지만, 시간당 비용이 3~5배 저렴하므로 달러당 처리량(Throughput per dollar)이 압도적으로 높음.
  - **VRAM 낭비 방지**: 1000 aa 이하 단일 사슬 단백질의 AF2 추론은 12~16GB VRAM으로 충분. A100의 40GB/80GB는 오버스펙임.

### 3.2 소요 시간 산출 (Wall-clock Estimate) - AF2 단독 추론 기준
- **가정**: 
  - 평균 단백질 길이: 150~300 aa (CATH 도메인 평균)
  - 파라미터: `--num-models 1`, `--num-recycle 3` (Surrogate 훈련용 데이터 수집 목적이므로 5개 모델 전부 앙상블 할 필요 없음)
  - 1 Sequence 당 평균 L4 처리 시간: **약 30초**

- **시나리오 A: 타겟당 30개 시퀀스 (기본 세팅, 권장)**
  - 총 시퀀스 수: 1,470 x 30 = 44,100 개
  - L4 4장 병렬 처리 시: 약 92시간 + 15% 오버헤드 $\approx$ **4 ~ 5 일 소요**
  - *결론: 가장 현실적이고 빠른 Phase 1 달성 방법.*

- **시나리오 B: 타겟당 100개 시퀀스 (심층 탐색)**
  - 총 시퀀스 수: 1,470 x 100 = 147,000 개
  - L4 4장 병렬 처리 시: 약 306시간 + 15% 오버헤드 $\approx$ **13 ~ 16 일 소요**
  - *결론: 시나리오 A를 먼저 수행한 뒤, 성능이 부족한 특정 타겟 그룹만 선별하여 추가 수행하는 것을 권장.*

### 3.3 Full Evolution Pipeline 종합 처리량 (MPNN + SoluProt + AF2 + Relax)
단순 AF2 추론이 아닌, `evolution_mode` 전체 파이프라인을 돌렸을 때의 실제 타겟 처리량입니다.

#### 타겟 1개당 소요 시간 분석 (End-to-End, Oracle 정밀 분석 기준)
| 단계 | 수행 위치 | 시간 | Critical Path |
|---|---|---|---|
| 1. ProteinMPNN (1,000개 서열 생성) | RunPod | 3~5분 + Cold start 10~30초 | O |
| 2. SoluProt (1,000개 용해도 평가) | RunPod | 5분 | O |
| 3. ESM-2 임베딩 + K-Means | L4/CPU | 2분 | O |
| 4a. AF2 - 훈련용 30개 | L4 | 30 × ~35초 ≈ **18분** | O |
| 4b. Local RF 학습 | CPU | 30초 | O |
| 4c. AF2 - Top-K 20개 | L4 | 20 × ~35초 ≈ **12분** | O |
| 5. Rosetta Relax (50개 PDB) | RunPod (10+ 동시 워커) | 5~10분 | O |
| **합계** | - | **약 45~55분 / 타겟** | - |

> **주의**: AF2 소요 시간이 30초가 아닌 **35초**로 상향된 이유는 JIT 재컴파일 오버헤드 때문입니다. 150~300aa 편차에서 타겟당 5~10회 재컴파일이 발생하여 평균 추론 시간이 증가합니다. Length Bucketing 적용 시 30초로 복귀 가능.

#### 일일 처리량 시나리오
| 운영 방식 | 일일 처리량 | CATH 1,470개 완료 |
|---|---|---|
| **① 기본 병렬 (4 타겟 동시 실행, 파이프라이닝 X)** | **100~120개/일** | 약 12~15일 |
| **② 공격적 파이프라이닝 (L4는 AF2 전용 워커)** | **135~150개/일** | 약 10~11일 |
| **③ 이론적 최대 (L4 4장의 AF2 Throughput 상한선)** | 192개/일 | 약 8일 |

#### 공격적 파이프라이닝 전략 상세
각 L4를 **영구 AF2 워커**로 전환하고, MPNN/SoluProt/Relax는 RunPod에서 다른 타겟과 오버랩(Overlap) 실행:
- 타겟 A가 AF2를 도는 동안 타겟 B의 MPNN 생성이 진행
- 타겟 B의 AF2 시작 시점에 타겟 C의 SoluProt 실행
- 병목은 이제 L4 AF2 Throughput 하나로 수렴 (타겟당 30분)
- 달성 가능: 이론의 70% 수준인 약 135~150개/일

---

## 4. 현실적인 운영 병목 (Bottlenecks in Practice)

Oracle 정밀 분석에 따른 병목 우선순위 (실제 영향도 순):

1. **AF2가 가장 큰 병목**: 전체 타겟 시간의 60% 차지 (50분 중 30분). 이 시간을 줄이지 않는 한 다른 최적화 효과 제한적.
2. **JIT 재컴파일**: 150~300aa 편차로 타겟당 5~10회 재컴파일 → AF2 시간 15~20% 낭비. **Length Bucketing 필수**.
3. **2라운드 AF2 동기화 벽(Sync Barrier)**: Stage 4a(30개) → RF 학습 → Stage 4c(20개) 순차 진행으로 대기 시간 발생. 개선: 30개 완료 전에 스트리밍 방식으로 RF를 점진 학습시켜 Top-K를 조기 예측.
4. **RunPod Cold Start**: MPNN/SoluProt/Relax 엔드포인트 호출마다 15~60초 지연 → 타겟당 1~2분 오버헤드. **Warm Pool(min_workers >= 1) 설정 필수**.
5. **Rosetta Relax 동시성**: 50개 구조 × 45초 = 37.5 CPU-min. 10개 이상 동시 워커 확보해야 5분 내 완료 가능. RunPod 동시성 캡 확인 필요.
6. **SoluProt 고정 5분**: 다중 타겟 배치 처리로 숨기지 않으면 단축 불가.

---

## 4.5 MSA 사용 결정 (Single-Sequence vs MMseqs2 MSA)

### 결론: Phase 1에서는 **Single-Sequence 모드**를 강력히 권장

### 근거
1. **MPNN 설계 서열의 본질**: ProteinMPNN이 생성한 서열은 자연계에 없는 신규 서열이므로 진화적 호모로그가 거의 없음. MSA 탐색을 해도 shallow MSA만 나와 효용 제한적.
2. **학계 표준**: ProteinMPNN 관련 논문(Dauparas 2022 외 다수)이 self-consistency 평가 시 single_sequence 모드를 기본으로 사용.
3. **공개 MMseqs2 API의 rate limit**: ColabFold 공개 서버는 IP당 분당 1~5회로 제한되어 44,000+개 요청은 불가능. 로컬 MMseqs2 미러 구축이 필수(~2TB 디스크).

### 처리량 비교

| 설정 | 타겟당 시간 | 일일 처리량 | 16~17일 누적 | CATH 1,470 커버율 |
|---|---|---|---|---|
| **Single-Sequence (권장)** | ~50분 | 100~120개 | 1,600~2,040개 | **✅ 완료 후 여유** |
| **MSA (로컬 MMseqs2)** | ~80~90분 | 65~80개 | 1,040~1,360개 | ⚠️ 71~92% (일부 누락) |
| **MSA (공개 API)** | 불가능 | - | - | ❌ Rate limit으로 불가 |

### 🎯 Hybrid 2-Stage 전략 (권장)

**Stage 1 (13~15일)**: 전체 CATH 1,470개를 Single-Sequence 모드로 처리
- Expert 모델 1,470개 + pLDDT 데이터 44,100개 확보
- Memory Bank 1차 버전 완성

**Stage 2 (추가 4~7일, 선택)**: Stage 1에서 평균 pLDDT < 70인 타겟만 MSA로 재평가
- 일반적으로 전체의 10~15% (≈ 150~200개 타겟)
- 이 타겟만 MSA 재평가 시 추가 4~7일 소요
- 재평가 결과로 해당 Expert 모델만 업데이트

### 구현된 MSA 옵션 (`submit_batches.py`)
```bash
# Stage 1: 기본 (Single-Sequence)
python3 submit_batches.py input.fasta

# Stage 2: Hybrid rescore - 이전 결과 기반으로 pLDDT 낮은 타겟만 MSA로 재제출
python3 submit_batches.py input.fasta \
  --hybrid-rescore-from /opt/protein_pipeline/phase1_dataset.csv \
  --rescore-threshold 70 \
  --msa-mode mmseqs2_uniref_env \
  --msa-host-url https://my-local-mmseqs2.internal:8888
```

---

## 5. 생산성 극대화를 위한 JAX/ColabFold 최적화 필수 수칙

L4 인스턴스에서 대규모 배치 추론을 수행할 때 다음 사항을 반드시 지켜야 GPU 가동률을 100%로 유지할 수 있습니다.

1. **MSA 검색 강제 생략 (`--msa-mode single_sequence`)**
   - **사유**: ProteinMPNN이 새로 디자인한 서열은 자연계에 존재하지 않으므로 MSA 데이터가 없음.
   - **조치**: MMseqs2 서버 통신 병목을 없애기 위해 반드시 Single sequence 모드로 AF2를 구동해야 함.

2. **길이별 버킷팅 (Length Bucketing) 배치 스케줄링 [★매우 중요]**
   - **사유**: AlphaFold2(JAX)는 입력 서열의 길이(Shape)가 바뀔 때마다 XLA 커널을 재컴파일(Recompilation)함. (회당 30~60초 낭비).
   - **조치**: 파이프라인 스크립트 단에서 14만 개의 서열을 길이 순서대로 정렬(Sorting)한 뒤, 길이가 비슷한 그룹(예: 100~150, 150~200) 단위로 묶어(Bucket) GPU에 할당해야 함. 32 aa 단위 패딩(Padding) 적용 시 8개 버킷으로 축소 가능.

3. **4개 GPU 완벽 분할 격리**
   - **사유**: JAX의 멀티 GPU 자동 할당은 종종 메모리 파편화 및 병목을 유발함.
   - **조치**: 4개의 독립된 워커 프로세스를 띄우고, 각 프로세스에 `CUDA_VISIBLE_DEVICES=0`, `1`, `2`, `3`을 명시적으로 할당하여 4개의 공장을 병렬로 가동.

4. **RunPod Warm Pool 유지**
   - **사유**: Cold Start 시 MPNN/SoluProt/Relax 엔드포인트별 15~60초 지연. 타겟당 누적 1~2분.
   - **조치**: 각 엔드포인트 `min_workers >= 1` 설정으로 항상 웜 상태 유지.

5. **스트리밍 RF 학습 (Sync Barrier 제거)**
   - **사유**: Stage 4a의 30개 AF2 결과를 다 기다리지 않고도, 일부 결과만으로도 RF의 초기 경향 파악 가능.
   - **조치**: 조기 종료된 AF2 결과를 스트리밍 방식으로 RF에 온라인 학습시켜 Top-K 예측을 앞당김.

---

## 6. 실행 권장 로드맵 (Execution Roadmap)

### Step 1: 정확한 실측 기반 벤치마크 (소요: 2~4시간)
- L4 1장을 AF2 전용 워커로 고정하고 타겟 2개에 대해 실측:
  - (a) AF2 JIT 재컴파일 빈도
  - (b) RunPod Cold Start 분포
  - (c) Rosetta Serverless 실제 동시성
- 위 수치에 따라 최종 일일 처리량이 115개에 머물지, 150개까지 도달할지 결정됨.

### Step 2: Phase 1 대규모 실행 (CATH 1,470개 타겟, 약 11~14일)
- Length Bucketing + RunPod Warm Pool 적용 필수
- 실행 중 MLflow와 S3에 Expert 모델 및 AF2 결과 자동 백업
- 1,470개의 Target Expert 모델과 수십만 개의 (서열, pLDDT, SoluProt) 데이터 확보

### Step 3: Phase 2 (Memory-Based Routing) 검증
- 축적된 1,470개 Expert 모델로 k-Nearest Experts 라우팅 로직 구현
- 신규 타겟 입력 시 AF2 호출 80% 절감 여부 벤치마크

### Step 4 (장기): ESMFold 통합 고려
- 1차 스크리닝을 ESMFold로 전환 시 AF2 부하 30회 → 20회로 감소 가능
- L4 4장으로도 200개+/일 달성 가능

---

**Next Action Items**:
- [x] `evolution.py` 내 로컬 전문가(Expert) 모델 보존 및 아카이빙 로직 추가
- [ ] CATH 타겟 대상 `--num-models 1`, `--msa-mode single_sequence` 파라미터 적용 배치 스크립트 작성
- [ ] JAX Recompilation 방지를 위한 Length-sorting 배치 디스패처(Dispatcher) 구현
- [ ] L4 1장 기반 실측 벤치마크 수행 (타겟 2개, 처리량 지표 3종 측정)
- [ ] RunPod 엔드포인트(MPNN, SoluProt, Relax)에 대한 Warm Pool 설정 및 동시성 캡 확인
- [ ] 스트리밍 RF 학습 로직 프로토타입 (AF2 결과 조기 수렴 판단)
