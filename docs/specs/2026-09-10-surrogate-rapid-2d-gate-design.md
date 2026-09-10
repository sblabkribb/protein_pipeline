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

주 근거는 tracked artifact `public_data/benchmark/sr/sequence_axis_ablation.json` 이다.
(`docs/superpowers/specs/2026-09-03-rapid-transcoder-unified-design.md` 에도 같은 표가
있으나 그 경로는 `.gitignore:102` 로 무시되는 **local historical design note 이며
non-authoritative** 다. 재현 시 인용하지 않는다.)

- 프로토콜: Ridge(alpha=100), leave-one-target-out, **82 CATH 타겟 / 9,840 설계**
- 1차 지표: **타겟 내 AF2 pLDDT Spearman 평균**
- 결과: 조성(0.047) · ESM2-8M mean(0.021) · ESM+조성(0.014) · ProtoMech PLT(0.008) ·
  CLT(−0.030) — **다섯 arm 전부 CI 가 0 을 포함**

표본은 Gate 2 의 평가 대상(11 타겟 / mixed 백본 37개 = 888 폴드)보다 훨씬 크다.
다만 **estimand 가 다르므로 "Gate 2 보다 전반적으로 검정력이 높다" 고 쓰지 않는다.**
정확한 진술은 다음이다.

> The 82-target result provides a higher-powered negative reference for transferable
> pLDDT-ranking signal under the previously tested representations, but it does not
> directly test the within-backbone joint-pass estimand of Gate 2.

그래서 이 스펙은 다음을 명시한다.

> **S1(raw ESM mean)은 사실상 이미 음성으로 시험됐다.** 신규 가설이 아니라 기지 null
> 참조로 둔다. **S2(ΔESM_global)는 여기에 포함되지 않는다.**

**정정 (2026-09-10).** 초기 논의에서 "ΔESM_global 은 unit 내 상수 평행이동이므로 S1 과
동일 예측" 이라고 적었다. 그 진술은 **unit 내부에서 학습하는 모델**(Supp. Note 5 의
프로덕션 surrogate)에만 맞고, **Gate 2 의 LOTO cross-target 설정에는 맞지 않는다.**
LOTO 에서 reference 는 타겟마다 다르다:

```
x'_ti = x_ti − r_t        (타겟별 translation)
x'_i  = x_i  − c          (전역 상수 — 이것이 아니다)
```

train 타겟 A·B·C 가 서로 다른 −r_A·−r_B·−r_C 를 받으므로 Ridge 의 계수, RF 의 split
위치, KNN/GP 의 **test point ↔ 타 타겟 train point 거리**가 모두 달라진다. 보존되는
것은 고정된 test 백본 내부의 pairwise distance 뿐이다.

정확히 말하면: **선형 모델에서는** 같은 w 를 주면 test 타겟 내부 순위차가
w·(x_i − r_t) − w·(x_j − r_t) = w·(x_i − x_j) 로 reference 가 소거되므로, S2 가 S1 과
달라지는 통로는 **학습 geometry 를 통한 w 의 변화뿐**이다. RF·KNN·GP 는 학습과
test 시점 거리 양쪽에서 달라진다.

따라서 arm 지위는 다음과 같다.

| | 지위 |
|---|---|
| S1 | prior large-cohort negative reference |
| **S2** | **untested but low-expectation hypothesis** |

S2 가 묻는 것은 합리적인 가설이다 — **reference-relative ESM 이 raw absolute ESM 의
target identity 성분을 제거해서 cross-target transfer 를 개선하는가.**

Gate 2 가 반복이 아닌 근거는 아래 세 가지뿐이고, 그 이상을 novelty 로 추가하지 않는다.

1. **endpoint 가 다르다.** 선행은 연속 pLDDT 순위, 여기는 joint-pass Top-4 회수.
   joint-pass 에는 RMSD ≤ 2.0 이 들어가고, RMSD 의 서열 수준 분산은 47.8% 로 pLDDT
   31.3% 와 다르다 (`variance_decomposition_grid.json`). **이 분산 차이를 새 feature
   가 성공할 근거로 쓰지 않는다** — 분산이 크다는 것은 exploitable predictability 와
   다른 진술이다. 여기서 쓰는 결론은 하나뿐이다: joint-pass 에는 pLDDT-only 분석과
   다른 sequence-level variation 이 있으므로 **endpoint 가 동일하지 않다.**
2. **unit 이 다르다.** 선행의 "타겟 내" 는 백본을 가로질러 풀링한다. 여기는 백본 내다.
3. **새 arm 이 있다.** S3(ΔESM_mut) · S4(MSA) · S5 는 선행에서 시험되지 않았다.

**경험적 기대치를 낮게 기록한다.** formal Bayesian prior 가 아니므로 숫자로 쓰지 않는다:
*prior empirical evidence lowers our expectation that generic sequence-level
representations alone will produce a practically useful effect.* 이 게이트의 기대값은
"새 방법이 될 것" 이 아니라
"세 방향 중 무엇이 존재하는 문제인지 8시간 안에 확정" 이다.

## 3. Gate 1 — backbone predictability

**질문.** AF2 를 보기 전 cheap feature 로 어느 백본의 q_b 가 높은지 예측할 수 있는가.
(백본마다 q_b 가 다르다는 것은 §1 에서 이미 확인됐다. 그것을 다시 묻지 않는다.)

| | 내용 |
|---|---|
| train | 157 백본 / 62 타겟. `backbones/backbone_labels.csv` 의 `joint_pass_yield`, feature `backbones/mpnn_encoder.npy` (157, 384) |
| test | 70 백본 / 12 타겟. q_b 는 `holdout_grid/af2_order_metric.csv` 에서 계산 |
| feature | ProteinMPNN encoder 384-D (ckpt `v_48_020`, dev 와 동일) |
| 1차 지표 | **타겟 내 Spearman(q̂_b, q_b) 의 타겟 등가중 평균** (informative 11 타겟), target-clustered bootstrap |
| 2차 지표 | top-1 backbone regret = q_b(실제 최선) − q_b(예측 최선). RAPID 이 실제로 소비하는 양 |

**전역 AUC 를 1차 지표로 쓰지 않는다.** 분산의 79~86% 가 타겟 수준이므로
(`holdout_experiment_spec.json`), 전역 지표는 "타겟 평균 예측" 만으로 부풀려진다.

**Gate 1 informative 타겟은 11 개다.** 백본 ≥ 3 이고 q_b 가 비상수인 타겟만 센다.
`1sh6A02` 는 6 백본 전부 q_b = 1.00 이라 타겟 내 Spearman 이 정의되지 않는다.
(Gate 2 의 제외 타겟과 같으나 제외 사유는 다르다 — Gate 2 는 mixed 백본 0개, Gate 1 은
q_b 상수.)

### 개정 (2026-09-10) — native 백본은 배분 풀이 아니라 comparator 다

**Gate 1 의 1차 코호트를 RFD3 백본으로 한정한다.** native 백본은 comparator 로
분리해 별도 보고한다. 아래는 그 근거이며, **Gate 1 수치는 아직 하나도 계산되지
않았다** — 결과를 보고 바꾼 것이 아니다.

교란이 실재한다. 홀드아웃 격자는 타겟당 native 1개 + RFD3 5개이고, native 의 q_b 는
**양극단**이다:

```
native 타겟내 순위 : 1/6 이 5 타겟 · 6/6 이 3 타겟 · 5/6 과 2/6 각 1
native q_b 평균 0.604 (중앙값 0.958)  vs  RFD3 0.660 (중앙값 0.833)
```

그래서 **source 를 나타내는 1 비트가 타겟내 q_b 분산의 24.8% 를 설명한다.** MPNN
encoder 는 결정 구조와 생성 구조의 기하학적 차이를 쉽게 본다. Gate 1 이 그 1 비트로
점수를 벌면 그것은 "백본 예측 가능성" 이 아니고, **RAPID 이 배분하는 대상이 생성
백본이므로 B 를 지지하지도 않는다.**

역할을 분리한다.

| | 역할 |
|---|---|
| RFD3 · BioEmu | **allocatable generated backbone source.** RAPID 이 계산을 배분하는 풀 |
| native | **reference comparator.** 생성기가 아니라 기준 구조다. posterior 를 섞지 않는다 |

**검정력 손실이 거의 없다는 것이 이 결정을 가능하게 한다.** RFD3-only 로도
informative 타겟은 **11 개 그대로**이고(≥3 백본 ∧ q_b 비상수), 타겟내 q_b spread
중앙값은 0.58 → 0.54 로만 줄어든다. `min_informative_clusters = 8` 을 통과한다.

**Gate 2 의 1차 코호트는 mixed 백본 37 개를 유지한다.** Δ_Top4 는 **백본 내부**에서
계산되므로 각 백본이 자기 단위이고 source 는 교란이 아니다. RFD3-only(mixed 34,
informative 11)를 민감도로 함께 보고한다.

**native 라벨은 10/12 타겟에만 있다.** `3es1A01`·`3h7eA02` 의 native arm 은 설계
길이가 WT 와 달라(163/160, 229/220) 대응이 거부돼 사용가능 폴드가 0 이다 — 이것이
1,728 중 48 폴드가 빠지는 이유이고, §5 의 Δ_Top4 NaN sentinel 이 가리키는 그 2개다.

### 학습 쪽도 정렬한다 (2026-09-10)

test 에서 native 를 빼도 dev 157 개 전체로 학습하면 **native/reference 가 계수를
형성한다.** 질문이 "RAPID 이 배분할 **생성** 백본의 q_b 를 예측할 수 있는가" 로
좁혀졌으므로 학습도 맞춘다. 네 arm 을 동결한다.

| arm | train | test | 지위 |
|---|---|---|---|
| **primary** | RFD3-only dev (백본 80 · 타겟 16) | RFD3-only holdout | **GO 판정** |
| sensitivity 1 | RFD3 + BioEmu (백본 100 · 타겟 16) | RFD3-only holdout | 사전 등록 동반 보고 |
| descriptive / legacy | target + RFD3 + BioEmu (백본 157 · 타겟 62) | RFD3-only holdout | 기존 Gate 0 과의 연속성 |
| comparator | — | native holdout (10 타겟) | Δ_generated 부수 분석. **GO 제외** |

**BioEmu 에 대한 B 의 일반화는 주장하지 않는다** — 독립 BioEmu test 가 없다.

**누수 확인.** dev 타겟은 세 source 전부 홀드아웃 12 타겟과 **겹침 0** 이다
(rfd3 16 / bioemu 4 / target 57, 교집합 모두 공집합).

### 작은 코호트가 이 질문에는 더 맞다

primary 의 표본은 legacy 의 절반이고 feature 는 384 차원이다(n/p = 0.21). 그런데
Gate 1 의 지표는 **타겟내 순위**이고, 그 관점에서 코호트 구조는 이렇다.

```
전체(legacy)   타겟 62 중 ≥2 백본  16 (26%)
RFD3-only      타겟 16 중 ≥2 백본  16 (100%)
RFD3+BioEmu    타겟 16 중 ≥2 백본  16 (100%)
```

legacy 의 추가 46 타겟은 **백본이 1개씩**이다. 그것은 "어느 타겟이 좋은가" 를
가르치고 "한 타겟 안에서 어느 백본이 좋은가" 는 가르치지 않는다. 후자가 Gate 1 이
재는 것이다. 따라서 표본이 작아진 것과 질문에 맞아진 것이 같이 일어난다.

BioEmu 의 4 타겟은 RFD3 의 16 타겟의 **부분집합**이다. 즉 sensitivity 1 은 새 타겟이
아니라 같은 타겟에 백본 20 개를 더해 타겟내 대조를 늘린다.

**NO-GO 해석에 이 사실을 반영한다.** primary 는 백본 80 개에 384 차원이므로
primary 의 NO-GO 는 "신호 없음" 이 아니라 **"이 표본에서 미검출"** 로 읽고,
sensitivity 1 을 **사전 등록된 동반 보고**로 함께 낸다. 사후 대체 arm 이 아니다 —
primary 가 실패했을 때 sensitivity 로 GO 를 선언하지 않는다.

### source 분해의 provenance

**24.8% 는 informative 타겟 11 개 기준이다.** native 라벨이 있는 9 개로 한정하면
**25.6%** 다. `3es1A01`·`3h7eA02` 는 native 폴드가 0 이라 source 그룹이 rfd3 하나뿐
이고, 그러면 group mean == grand mean 이므로 between 항 기여가 0 이 된다 —
**결측을 0 으로 대입한 것이 아니다.** 따라서 11 타겟 기준 24.8% 는 그 두 타겟이
희석시킨 보수적 값이다.

### 부수 분석 (1차 endpoint 아님)

native 가 comparator 로 분리되면 다음을 직접 물을 수 있다.

```
Δ_generated = Y(생성 백본) − Y(native 백본)
```

즉 **"복수 백본을 만드는 것이 원본 백본에서 서열만 여러 개 만드는 것보다 실제로
이득인가"**. 이 연구의 주장 중 하나가 *서열 다양성이 백본 다양성을 대체하지 못한다*
이므로, `native + 많은 서열` vs `생성 백본 + 같은 총 서열 예산` 비교가 그것을 직접
시험한다. **부수 분석으로만 보고하고 GO 판정에 넣지 않는다** — endpoint 를 하나로
유지한다.

**동결된 RAPID v2 검증에는 넣지 않는다.** 그쪽은 source 별 10-백본 설계가 이미
동결돼 있어 native 를 추가하면 budget grid 와 source 정의가 바뀐다.

### 동결된 Gate 1 GO 규칙

```
Gate 1 GO  ⟺  타겟 등가중 mean within-target Spearman(q̂_b, q_b) ≥ +0.25
              AND  타겟-클러스터 부트스트랩 one-sided 90% LCB > 0
              AND  informative 타겟 ≥ 8
```

**임계값 +0.25 의 근거는 OC 시뮬레이션이다.** 실제 백본 수와 실제 q_b 를 쓰고
예측기를 q̂_b = q_b + N(0, σ) 로 만들어 σ 를 훑었다 (600 반복, informative 11).
`ρ ≳ 0.26 부터 2 SE` 같은 rough detectability 계산을 임계값으로 전용하지 않는다 —
아래 표가 근거이고, 숫자가 비슷한 것은 우연이다.

| σ | E[mean ρ] | E[top-1 regret] | P(GO) ρ≥0 | ρ≥0.20 | **ρ≥0.25** | ρ≥0.30 |
|---|---|---|---|---|---|---|
| null (순수 노이즈) | −0.002 | 0.245 | **0.12** | 0.06 | **0.03** | 0.01 |
| 1.00 | 0.184 | 0.165 | 0.53 | 0.47 | **0.34** | 0.20 |
| 0.50 | 0.340 | 0.111 | 0.92 | 0.89 | **0.79** | 0.63 |
| 0.35 | 0.441 | 0.081 | 0.98 | 0.97 | **0.96** | 0.90 |
| 0.25 | 0.529 | 0.055 | 1.00 | 1.00 | **1.00** | 0.99 |

**`ρ > 0` 규칙은 쓸 수 없다.** 귀무에서 거짓 GO 가 0.12 로 나온다 — LCB > 0 조항만으로는
통제되지 않는다. Gate 2 와 같은 구조로, **점추정 조항이 통제를 담당한다.** +0.25 에서
거짓 GO 는 0.03 이고 참값 ρ ≈ 0.34 에서 검정력 0.79, ρ ≈ 0.44 에서 0.96 이다.

**NO-GO 해석도 같은 방식으로 조건부다.** 사전 지정된 이 시뮬레이션 모형 아래에서,
Gate 1 NO-GO 는 ρ ≈ 0.44 규모의 효과에 대한 증거이고 ρ ≈ 0.18 규모(검정력 0.34)에
대해서는 약한 증거일 뿐이다. **결과를 본 뒤 임계값과 이 문구를 바꾸지 않는다.**

top-1 regret 은 2차 지표로 보고만 한다 (귀무 0.245 → σ=0.5 에서 0.111). GO 조건에
넣지 않는다 — endpoint 를 하나로 유지한다.

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
| **판정 arm** | **S6 하나로 동결.** 나머지 arm 은 ablation/descriptive 이며 GO 판정에 쓰지 않는다 |

타겟별 mixed 백본 수가 고르지 않다 (`2jokA01`·`3bqwA01`·`5fwaA02` 5개 … `3es1A01` 1개).
타겟 등가중이므로 `3es1A01` 의 단일 백본이 1/11 가중치를 그대로 받는다. LCB 조항이
이 한 백본으로 GO 가 뒤집히는 것을 막는다.

### Feature ladder

| arm | feature | 사전 지위 |
|---|---|---|
| S0 | SoluProt | 측정 완료. Δ_Top4 = **−0.001** |
| S1 | raw ESM mean | **기지 null** (§2, 82 타겟) |
| S2 | ΔESM_global | **미시험 · 낮은 기대치.** LOTO 에서 타겟별 translation 이므로 S1 과 동치가 아니다 (§2 정정) |
| S3 | ΔESM_mutation-site | **신규 가설** |
| S4 | MSA / conservation | **신규 가설** |
| S5 | S3 + S4 | **신규 가설** (ESM 단독 vs ESM+coevolution 반증) |
| **S6** | S5 + 기존 cheap feature (조성, MPNN score) | **full-feature arm — Gate 2 PRIMARY** |

ΔESM 의 reference 는 타겟 WT 서열이다. label 이 아니라 입력이므로 LOTO 를 위배하지 않는다.

### MSA 결측·저심도 처리 (결과 보기 전 동결)

RAPID 쪽에서 이미 저심도 MSA 가 나왔다 — `msa_pilot_corrected.json` 의 파일럿 타겟
중 `median_depth` 가 33, 23 인 것이 있다. 따라서 이 규칙을 결과 전에 박아 둔다.
**나중에 "MSA 가 얕아서 그 타겟을 뺐다" 가 되면 그 자체가 selection 문제가 된다.**

1. **MSA search 가 완료되고 query 가 유효하면 depth 와 무관하게 S4–S6 feature 계산을
   시도한다.** depth·coverage 임계값으로 타겟을 걸러내지 않는다.
2. feature 가 계산되면 그대로 쓴다. 얕은 MSA 에서 나온 값도 쓴다.
3. feature 가 **수학적으로 정의되지 않는 경우**(usable hits 0 등)에만 결측 처리한다:
   **train fold 평균으로 대치하고 `msa_undefined` 이진 지시자를 feature 에 추가**한다.
   조용히 버리지 않는다.
4. **test 타겟의 MSA feature 가 전부 정의되지 않아도 그 타겟을 유지한다** — 3번 규칙
   그대로 imputation + `msa_undefined = 1` 로 평가한다. S5·S6 는 ΔESM 등 다른 feature 를
   가지고 있으므로 더욱 그렇다. **MSA 부족 때문에 test 타겟이 코호트에서 빠지는 경로를
   두지 않는다.** 코호트는 어느 arm 에서도 11 타겟이다.
5. arm 을 non-evaluable 로 내리는 경우는 **하나뿐**이다: **training fold 자체에서 해당
   MSA feature 를 정의할 수 없어 imputation statistic 을 만들 수 없을 때.** 이때는
   그 arm 의 실행을 non-evaluable 로 기록하고 이유를 남긴다. 타겟을 빼지 않는다.
6. **MSA 품질을 보고 타겟을 교체하지 않는다.** `holdout_targets.json` 의 12 타겟은
   seed 20260907 로 동결됐고 이 실험에서 다시 고르지 않는다. MSA 품질 지표
   (`usable_hits`, coverage/depth 분위)는 **보고 대상이지 선별 기준이 아니다.**
7. **MSA conservation 은 타겟/reference 로 한 번 계산된 값이다.** candidate 서열의
   AF2 결과나 Gate 2 label 에 따라 달라지는 항이 S4–S6 에 들어가면 안 된다. candidate
   별로 달라지는 것은 "그 candidate 의 변이가 보존 위치에 있는지" 뿐이며, 그 판정에
   쓰이는 보존 프로파일 자체는 candidate 와 무관하다.

   **명시 (2026-09-10).** 위 문장이 S4 의 요구사항이다. 구현이 이것을 놓치기 쉬우므로
   풀어 적는다. **S4 의 본체는 candidate 별로 달라지는 conservation burden 이어야
   한다.** 타겟 수준 요약(`cons_mean`·`coverage`·`depth`)만 넣으면 같은 타겟의 모든
   서열이 동일한 행을 받고, Gate 2 는 **백본 내부** 순위 문제이므로 S4 가 원리상
   순위를 만들 수 없다 — Ridge 예측이 전부 같아지고 Top-4 가 tie-break 으로 떨어진다.
   그러면 S4·S5·S6 는 "진화적으로 보존된 위치를 건드렸는가" 를 시험하지 못한다.

   최소 형태: 타겟의 동결 보존 마스크 `F_0.3`·`F_0.5`·`F_0.7` 과 candidate 의 변이
   위치 집합 `M_i` 로

   ```
   r_tier,i = |M_i ∩ F_tier| / max(|M_i|, 1)
   ```

   타겟 수준 품질 지표는 **보조 context** 로 남긴다. 이것은 새 가설이 아니라 위
   문장의 구현이다.

   **용어 주의.** 이 코호트의 `M_i` 는 중앙값 약 135 개(서열 길이의 50~65%)다 —
   격자 설계는 보존 마스킹 없이 생성됐으므로 point mutant 가 아니라 사실상 재설계다.
   따라서 `r_tier` 는 "point mutation 이 보존 위치를 건드렸는가" 가 아니라 **"바뀐
   위치 중 보존 위치의 비율"** 이다. 그렇게만 서술한다.

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

1. **귀무에서 거짓 GO 를 관측하지 못했다 — 확률이 0 이라는 뜻은 아니다.** 동결 문구:
   *No false GO was observed in 600 null simulations (0/600). This does not establish a
   zero false-GO probability.* rule-of-three 기준 95% 상한은 약 3/600 = **0.5%** 다.
   보고 형식은 `observed false-GO rate 0/600; approximate 95% upper bound ≈ 0.5%` 로
   고정한다. 점추정 조항이 통제를 담당하고 LCB 조항은 사실상 non-binding 한
   단일타겟 방어 장치다.
2. **NO-GO 의 해석을 미리 고정한다.** 위 검정력은 **사전 지정된 시뮬레이션 모형에
   조건부**다 — Δ_Top4 와 AUC 의 대응은 그 모형, prevalence, 백본 크기, 점수 분포에
   의존한다. 따라서 "AUC ≥ 0.70 인 예측기는 존재하지 않는다" 로 읽지 않는다. 동결
   문구는 다음이다.

   > Under the prespecified simulation model, the gate has approximately 94%
   > probability of GO for an effect corresponding to AUC ≈ 0.70. Therefore, NO-GO
   > would constitute evidence against an effect of approximately this magnitude
   > under the assumed operating conditions, rather than proving the absence of any
   > AUC ≥ 0.70 predictor.

   임계값과 참값이 같을 때(AUC ≈ 0.64) 검정력은 0.54 이므로 그 규모에 대한 NO-GO 는
   약한 증거일 뿐이다. **결과를 본 뒤 이 문구와 임계값을 바꾸지 않는다.**

### 연산 정의 (모호성 제거)

- **q_b 는 Top-4 를 고르는 것과 같은 candidate universe 위의 base rate 다.**
  *q_b is the base rate over the same eligible candidate pool from which Top-4 is
  selected.* 분모는 그 백본의 사용가능 설계 전부(격자에서 24개, status!=ok 제외 후)이고
  홀드아웃 부분집합이 아니다. Top-4 rate 의 분모는 4 이므로 **두 항의 분모가 같다고
  쓰지 않는다** — 같아야 하는 것은 후보 모집단이다.
- **Top-4 동점 처리**: 점수 동점이면 `sequence_id` 오름차순으로 끊는다(문자열
  비교이므로 `g10` 이 `g2` 보다 앞이다). 무작위 동점 처리를 쓰지 않는다 —
  재현되지 않는다.
- **점수의 NaN 은 예외로 처리한다 (fail-closed).** surrogate 가 어떤 후보에
  점수를 못 매기면 그것은 feature 파이프라인의 버그이고, 조용히 뒤로 미루면
  안 된다. NaN 을 마지막으로 정렬하면 최악의 경우(전 후보 NaN) Top-4 가
  `sequence_id` 앞 4개가 되어 **Δ_Top4 가 고장 대신 잡음처럼 보인다.** 그래서
  점수 배열에 NaN 이 있으면 `ValueError` 를 낸다.

  **왜 이것이 값을 바꾸지 않는가.** 현재 코호트에서 도달 불가다 — 격자 1,728 행
  전부 `soluprot` 이 비어 있지 않고, S3–S6 의 MSA 결측은 §4 규칙 3 의 대치로
  처리되어 NaN 이 모델에 들어가지 않는다. 이것은 지금의 결함 수정이 아니라
  나중에 조용히 틀리는 경로를 막는 규칙이다.

  **`Δ_Top4` 자체가 돌려주는 NaN 은 다른 뜻이며 유지한다.** 사용가능 설계가 0 인
  백본은 NaN 이고(격자에 2개 있다), 타겟 등가중 집계가 그 백본을 제외한다.
  즉 NaN 은 **점수에서는 금지, 백본 수준 결과에서는 "이 백본은 셀 수 없다"** 는
  sentinel 이다. 두 용법을 섞지 않는다.
- **Gate 1 의 타겟 내 Spearman**: 백본이 3개 미만인 타겟은 상관이 불안정하므로
  제외하고 그 수를 보고한다. 홀드아웃 12 타겟은 전부 5~6개이므로 현재 제외는 0 이다.
- **Δ_Top4 의 K**: K=4 로 고정한다. `m2_endpoint_dynamic_range.json` 의
  `min_probe_per_unit = 4` 와 같은 값이며, 이 실험에서 다시 고르지 않는다.
- **부트스트랩·시뮬레이션 시드**: **20260910** 으로 고정한다. 이 문서의 OC 표
  (§3 Gate 1 교정표, §5 Gate 2 교정표·작동특성표)가 전부 이 시드로 생성됐다.
  단측 LCB 도 같은 시드를 쓴다. `n_boot` 은 LCB 20,000, OC 시뮬레이션 400~600
  반복이다.

  **2026-09-10 추가.** 최초 동결본이 이 시드를 적지 않았다 — 문턱과 해석은 모두
  적었는데 그것을 만든 RNG 를 빼놓았다. 값을 바꾸는 수정이 아니라 **이미 보고된
  표를 재현 가능하게 만드는 기입**이다. 어떤 문턱도 달라지지 않았다. (§4 규칙 6 의
  타겟 동결 시드 20260907 과는 다른 값이며, 그쪽은 홀드아웃 타겟 선정용이다.)

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

**S0–S3 를 먼저 돌리고 MSA 12건을 병행한다. 단 그 1차 결과는 interim/descriptive
only 이며, 공식 Gate 2 판정은 S6 없이는 내리지 않는다.** 판정 arm 이 S6 로 동결됐기
때문이다 (§4). arm 목록(S0–S6)과 GO 규칙은 이 문서에서 전부 동결됐으므로 사후 arm
추가가 아니다.

**결과적으로 MSA 12건은 critical path 다.** 처음 "S0–S3 먼저" 를 고른 이유는 판정을
8시간 앞당기는 것이었으나, S6 를 판정 arm 으로 동결한 지금 그 이유는 사라졌다.
S0–S3 를 먼저 돌리는 남은 값어치는 **파이프라인·feature 코드를 MSA 도착 전에
검증해 두는 것**뿐이다. 그 목적으로만 실행하고, 어떤 GO/NO-GO 문장도 내지 않는다.

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
