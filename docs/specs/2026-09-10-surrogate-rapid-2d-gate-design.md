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

그래서 **타겟내 q_b 분산 분해에서 between-source 성분이 24.8% 였다.** ("source 가
24.8% 를 설명한다" 로 쓰지 않는다 — 관측된 귀속이지 인과가 아니다.) MPNN
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

### OC 표의 authoritative geometry (2026-09-10 동결)

**Gate 1 primary 의 OC 는 RFD3-only test geometry 에서 계산한 것이 정본이다.**
"기존 인쇄값과 어느 geometry 가 잘 맞는지" 로 정본을 고르지 않는다 — 낡은 숫자가
프로토콜을 결정하게 하는 것이고 순서가 거꾸로다.

| 산출물 키 | 지위 |
|---|---|
| `OC_primary_rfd3_only` | **정본.** Gate 1 의 GO/NO-GO 해석이 인용한다 |
| `OC_legacy_all_sources` | **historical reference 전용.** 이 문서의 이전 §3 수치가 어디서 나왔는지(native 포함 70 백본 기하) 재현할 뿐, 어떤 판정에도 쓰지 않는다 |

`rho_min = 0.25` 에서 false-GO 나 검정력이 이전 표와 달라도 **이전 숫자에 맞추지
않는다.** Gate 1 예측을 아직 하나도 계산하지 않았으므로 지금은 outcome-blind
프로토콜 정정이 가능한 시점이다. 문턱이 여전히 적절하면 **0.25 를 유지하고 운영특성
표와 NO-GO 문구만 새 geometry 로 재동결**한다. false-GO 가 명백히 깨지는 경우에만
문턱을 재검토한다.

**Gate 2 도 같다.** 이 문서에 인쇄된 교정표·작동특성표는 controller 의 임시 실행
(power 루프 안 부트스트랩 800 회)에서 나왔다. 프로덕션 `one_sided_lcb` 가 자기
기본 반복수로 재생성한 값이 **정본**이며, 3째 자리 차이는 조정할 불일치가 아니라
임시 값이 대체되는 것이다.

**재현성 계약은 여섯 개를 한 세트로 묶는다.** production `delta_top4` + production
`one_sided_lcb` + 고정 시드 + 커밋된 생성기 + 커밋된 산출물 + 회귀 테스트.
생성기가 primitive 를 재구현하면 부트스트랩이 바뀌어도 표가 깨지지 않으므로 계약이
성립하지 않는다.

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

**between-source 성분 24.8% 는 informative 타겟 11 개 기준이다.** native 라벨이 있는 9 개로 한정하면
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

**Gate 1 의 ρ 는 2026-09-11 에 +0.0935 → +0.0379 로 정정됐다 (판정 불변).**
최초 기록값은 데이터가 아니라 **solver 가 멈춘 자리**였다. sklearn 기본 `tol=1e-4`
에서 타겟 `5pc8A00` 의 두 백본이 예측확률 4.4e-4 차이였고 feature 가 float32 라
상대 1e-7 교란이 순서를 뒤집었다 — 그래서 sklearn 1.9.0 환경은 +0.0935, 1.8.0
환경은 +0.0743 을 냈다. `tol` 을 6 decade(1e-5~1e-10) 조이면 두 환경이 **+0.0379**
로 일치하고, 같은 목적함수를 독립 Newton solve 로 `|grad|_inf ≈ 7e-14` 까지 풀면
+0.037927 이 bit-identical 하게 나온다. 즉 +0.0379 는 **정확한 최적해**다.
**원인은 판본이 아니라 입력 dtype 이다** (2026-09-11 재리뷰에서 정정). 한때 여기
"sklearn 1.9.0 이 손실을 `sum(sample_weight)=1380` 으로 정규화해 같은 `tol` 이 같은
기준이 아니게 됐다" 고 적혀 있었으나 그것은 틀렸다 — 두 판본 다 그렇게 나눈다
(`_logistic.py` 의 `l2_reg_strength = 1/(C·sw_sum)`). 실제로 다른 것은 1.9.0 이
float32 입력을 그대로 푸는 반면 1.8.0 은 float64 로 올린다는 점이고, 따라서 커밋된
적합은 float32 에서 돌았다. 이것은 한 판본 안에서 확인된다 — 같은 환경에서 입력만
float64 로 올리면 `tol=1e-4` 의 ρ 가 +0.0935 에서 +0.0743 으로 바뀐다. 산출물의
`numerics.solver_tol_stability` 는 이제 tol × dtype 격자(14 행)를 매 실행마다 다시
재며, 수렴한 12 행은 두 dtype 에서 같은 값이다. 채택: `tol=1e-8`, `max_iter=20000`, 해석된 패키지
버전과 함께 산출물 `numerics` 에 기록. 절단된 fit(`n_iter >= max_iter`)은
fail-closed 다. **문턱·arm·코호트·endpoint·시드는 바꾸지 않았다** — solver 허용오차
하나이며, 스윕 전체에서 가장 큰 후보값도 +0.0935 로 문턱 0.25 에서 멀다.

**정본 = `OC_primary_rfd3_only`** (백본 60 · 타겟당 5 · informative 11).

| σ | E[mean ρ] | E[top-1 regret] | **P(GO) ρ≥0.25** | (참고) ρ≥0.30 |
|---|---|---|---|---|
| null (순수 노이즈) | +0.0055 | 0.2274 | **0.0500** | 0.0300 |
| 1.00 | +0.1764 | 0.1634 | **0.3133** | — |
| 0.50 | +0.3337 | 0.1149 | **0.7383** | 0.605 |
| 0.35 | +0.4391 | 0.0881 | **0.9383** | 0.877 |
| 0.25 | +0.5471 | 0.0595 | **0.9967** | — |

historical reference (`OC_legacy_all_sources`, 백본 70, native 포함)는 최초 동결본에
인쇄된 표를 재현한다 — E[ρ] 최대차 0.0082, E[regret] 0.0029, P(GO) 0.0417. 독립
교차확인: 귀무 E[regret] 을 `max − mean q_b` 로 해석적으로 계산하면 all-sources
**0.2466** (인쇄값 0.245) 대 RFD3-only **0.2303** 이다 — 인쇄된 표가 70-백본 기하임이
확정된다.

**`ρ > 0` 규칙은 쓸 수 없다.** 귀무 거짓 GO 가 **0.1383** (정본 기하) · 0.11
(legacy) 로 나온다 — 최초 인쇄값 0.12 는 임시 실행값이었고
`gate2d_operating_characteristics.json` 의 재생성값으로 대체한다. 어느 쪽이든 — LCB > 0 조항만으로는
통제되지 않는다. Gate 2 와 같은 구조로 **점추정 조항이 통제를 담당한다.**

### 문턱 결정: ρ ≥ 0.25 를 유지한다 (재동결 2026-09-10)

정본 기하에서 ρ≥0.25 의 거짓 GO 는 **30/600 = 0.050** (Clopper-Pearson 단측 95% 상한
0.067) 이며, 최초 인쇄값 0.03 이 아니다. 원인은 조정이 아니라 **구조**다 — 타겟당
백본이 5~6 개에서 **5 개로 고정**되어 타겟내 ρ 가 더 시끄럽다.

이 문서는 사전에 *"false-GO 가 명백히 깨지는 경우에만 문턱을 재검토한다"* 고 적었다.
**0.050 은 관행적 5% 수준이며 명백히 깨진 것이 아니다.** 따라서 규칙대로 문턱을
유지하고 **표와 NO-GO 문구만 정본 기하로 재동결한다.**

**ρ ≥ 0.30 을 채택하지 않은 이유를 기록한다.** 그 문턱은 거짓 GO 를 0.030 으로
낮추지만 검정력을 ρ≈0.33 에서 0.738 → 0.605, ρ≈0.44 에서 0.938 → 0.877 로 깎는다.
그리고 **0.25 가 3% 가 아니라 5% 를 준다는 것을 본 뒤에 0.30 으로 올리는 것은 정확히
이 동결 규율이 막으려는 문턱 쇼핑이다.** 사전 규칙이 "유지" 를 지시하므로 유지한다.

**NO-GO 해석도 같은 방식으로 조건부다 (정본 기하로 재동결).** 사전 지정된 이
시뮬레이션 모형 아래에서 Gate 1 의 GO 확률은 ρ ≈ 0.33 에서 **0.74**, ρ ≈ 0.44 에서
**0.94** 다. 따라서 NO-GO 는 **대략 그 규모의 효과에 대한 증거**이고, ρ ≈ 0.18
규모(검정력 0.31)에 대해서는 약한 증거일 뿐이다. **결과를 본 뒤 임계값과 이 문구를
바꾸지 않는다.**

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
6. **얕은 MSA 는 "계산 가능하지만 정보가 없는" 제 3 의 경우다 (2026-09-10 추가).**
   규칙 1–5 는 두 경우만 다룬다 — feature 가 계산되거나, 수학적으로 정의되지 않거나.
   peer 세션이 v2 코호트에서 실제 사례를 찾았다: `2jvfA00` 은 uniref90 에서
   **usable_hits = 1** 이다(truncation·부분쓰기·strip·multi-model 전부 배제 확인).

   **usable_hits 가 1 이면 보존 프로파일이 사실상 query 자신이다.** 그러면 tier
   30/50/70 이 거의 임의의 근거로 위치를 고정하고, `F_tier` 가 임의가 되므로 그
   타겟의 `r_tier` 는 **계산은 되지만 잡음을 잰다.** 규칙 3 의 "수학적으로 정의되지
   않음" 에 걸리지 않으므로 지금 규칙 아래에서는 **진짜 측정처럼 조용히 들어간다.**

   처리는 **제외가 아니라 가시화**다 — depth 로 타겟을 걸러내면 규칙 5 가 막으려는
   selection 문제가 그대로 돌아온다.

   - `msa_features.json` 의 `per_target` 에 **`usable_hits` 를 그대로 기록**한다.
   - **`msa_low_depth` 이진 지시자**를 `msa_undefined` 와 나란히 feature 에 넣는다.
     문턱은 `usable_hits < 10` — 이 값은 `50_full_msa.py` docstring 이 이미 동결한
     feasibility 기준이며 **여기서 새로 고르지 않는다.**
   - Gate 2 결과에 **저심도 타겟 목록과 그 수**를 보고한다. 1 차 판정은 informative
     11 타겟 전체로 내고, **저심도 타겟을 뺀 민감도를 함께** 낸다.
   - 어느 경우에도 **타겟을 코호트에서 빼지 않는다.**

   지시자를 넣는 이유는 모델이 그 타겟의 보존 feature 를 스스로 할인할 수 있게
   하려는 것이다. 조용히 포함하는 것과 조용히 제외하는 것 사이의 제 3 의 선택이다.

   **이 게이트에서 마스크는 측정 전용이며 적용되지 않는다.** 격자 설계는
   `fixed_positions` 없이 생성됐다 — `holdout_grid/manifest.json` 의 `condition` 과
   `protocol_fingerprint.mpnn_settings` 에 마스크 항이 없고, `holdout_generation.json`
   의 `why_skip_msa` 가 *"RFD3 는 타겟 구조에 조건을 걸고 MSA 를 읽지 않는다 …
   백본만 만드는 데 MSA 는 낭비다"* 라고 적고 있다. 즉 백본 생성 시 MSA 자체가
   없었으므로 보존 프로파일도 없었다. `|M_i|` 중앙값 약 135 가 그 결과다.

   따라서 얕은 MSA 의 피해가 이 게이트에서는 **feature 하나가 잡음이 되는 것**에
   그친다. 지시자로 할인 가능하게 하는 처리가 그 수준에 맞다.

   **하류에서는 같지 않다.** B 나 C 가 진행되면 보존 마스크는 프로덕션에서
   ProteinMPNN `fixed_positions` 로 **적용**된다 — 그러면 정보 없는 마스크가
   잔기의 30/50/70% 를 근거 없이 고정한다. 측정이 아니라 설계 제약이 되므로 한
   단계 더 무겁다. peer 세션의 v2 코호트가 이미 그 경우다. **B/C 설계 시 지시자로
   할인하는 것으로는 부족하고, 저심도 타겟에서 마스크 적용 자체를 게이트하는 규칙이
   필요하다.** 이 게이트의 규칙을 그대로 옮기지 않는다.

   **이 규칙은 결과 전에 등록됐다.** 이 글을 쓰는 시점에 격자 12 타겟 중 완료된 것은
   `3es1A01` 하나이고 `usable = 3000` 으로 건강하다. 나머지 11 개의 depth 는 아직
   모른다.

   **다만 사전 등록이 이 규칙을 정당화하는 근거는 아니다.** 실제 근거는 두 개다 —
   문턱이 `bio/a3m.py` 의 기존 경계에서 **상속**된 것이지 새로 고른 값이 아니고,
   depth 는 **어떤 설계도 존재하기 전에 측정되는 homolog record 의 속성**이라
   동결이 막는 selection 위험(코호트 구성을 **성능**에서 고르는 것)에 해당하지
   않는다. 따라서 이 규칙은 영향받는 타겟을 알고 등록해도 정당하다.

   ### scope 를 모른다는 것의 대가를 사전에 등록한다

   peer 세션이 정확히 지적했다: 사전 등록은 blind 하지만 **scope 가 없다.** 저심도
   타겟이 몇 개일지 모르는 상태에서 할인 규칙을 등록하는 것이므로, 11 개 중 여러
   개가 10 미만으로 돌아오면 등록 당시 몰랐던 규모에 규칙을 적용하게 된다. 반대로
   scope 를 아는 쪽은 blind 하지 않다. **둘 다 가질 수는 없다.**

   그래서 **scope 에 대한 반응**을 지금 등록한다. informative 타겟은 11 이고
   `min_informative_clusters = 8` 이므로 산술은 확정적이다.

   | 저심도 타겟 수 | 민감도 코호트 | 처리 |
   |---|---|---|
   | 0 | 11 | 민감도 불필요. 저심도 없음을 보고한다 |
   | 1–3 | 10–8 | 민감도 계산 가능. 1 차 판정과 나란히 보고 |
   | **4 이상** | **7 이하** | **민감도가 floor 미달로 non-evaluable.** 1 차 판정을 내되 **"교차 확인이 불가능했다" 를 명시**한다. 조용히 확인 없는 판정으로 두지 않는다 |
   | 6 이상 (과반) | 5 이하 | 위에 더해 **S4·S5·S6 의 보존 성분이 대부분 공허한 프로파일에서 나왔음**을 arm 지위에 기록한다. Δ_Top4 가 통과해도 그것을 "보존이 예측한다" 로 서술하지 않는다 |

   **어느 구간에서도 타겟을 빼지 않고 문턱을 바꾸지 않는다.** 바뀌는 것은 결과에
   붙는 서술뿐이다.

   ### 실측 결과 (2026-09-11, MSA 12/12 완료)

   등록된 규칙이 **1–3 구간**에 떨어졌다. 저심도 타겟은 **1 개**다.

   | 타겟 | 길이 | usable_hits | median_cov | 분류 |
   |---|---|---|---|---|
   | **1tm9A00** | 137 | **3** | 0.993 | **MSA_INSUFFICIENT_DEPTH** |
   | 2jokA01 | 184 | 46 | 0.614 | OK |
   | 3bqwA01 | 347 | 866 | 0.853 | OK |
   | 나머지 9 개 | 115–339 | 3000 (상한) | 0.762–0.983 | OK |

   따라서 **민감도 코호트는 10 타겟이고 floor 8 을 넘으므로 계산 가능**하다. 1 차
   판정과 나란히 보고한다. 4 이상 구간의 "교차 확인 불가" 조항은 발동하지 않는다.

   **`2jokA01` 을 borderline 으로 함께 보고한다.** usable 46, median_depth 24 는
   문턱 10 을 넘으므로 규칙상 저심도가 아니지만, 나머지 아홉 개가 상한 3000 에
   붙어 있는 것과 비교하면 얇다. 분포가 사실상 이봉이다 (3 · 46 · 866 · 3000×9).
   **문턱을 46 위로 올리지 않는다** — 그것은 결과를 본 뒤의 문턱 쇼핑이다.
   대신 depth 분포 전체를 산출물에 남겨 독자가 직접 볼 수 있게 한다.

   **등록이 지식에 앞섰다는 감사 기록:** 규칙 커밋 `eed024b` 와 scope 반응 커밋
   `a90d214` 는 모두 MSA 재시작 **전** 이고, 그 시점에 완료된 타겟은 `3es1A01`
   하나(usable 3000)였다. `1tm9A00` 이 저심도라는 것은 11 번째로 완료됐다.

7. **MSA 품질을 보고 타겟을 교체하지 않는다.** `holdout_targets.json` 의 12 타겟은
   seed 20260907 로 동결됐고 이 실험에서 다시 고르지 않는다. MSA 품질 지표
   (`usable_hits`, coverage/depth 분위)는 **보고 대상이지 선별 기준이 아니다.**
8. **MSA conservation 은 타겟/reference 로 한 번 계산된 값이다.** candidate 서열의
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

   **서열 축은 hard precondition 이다 (2026-09-10).** `F_tier` 는 MSA query 에서,
   `M_i` 는 WT reference 에서 나오고 **서로 다른 파일·다른 파서**를 거친다. 두
   서열이 다르면 교집합이 어긋난 좌표에서 계산되고 **아무 오류도 나지 않는다.**
   12/12 전체 문자열 일치를 확인했고, 그 확인을 계약으로 승격한다 — P3 와 Task 11
   은 WT 서열 sha256 이 동결값(`_gate2d_cohort.FROZEN_WT`)과 다르면 **fail-closed**
   한다. **길이만 검사하지 않는다** — 같은 길이의 다른 서열이 통과하면 검사가
   무의미하다. 동결 해시는 손으로 적으며 production 코드에서 재유도하지 않는다:
   재유도하면 검사와 대상이 같은 버그를 공유한다.

   **peer 세션의 `query_sequence()` staging 수정은 이 코호트에서 measured no-op
   이었다.** 수정 전후 코드를 12 타겟에 전체 문자열로 비교해 차이 0 을 확인했다
   (격자 타겟 중 비양수 resseq 가 0 개). 진행 중이던 A3M 은 수정된 코드와 일관되며
   재실행하지 않았다. "코드가 바뀌었으나 이 실험의 입력에는 효과가 없었다" 를
   기록으로 남긴다.

   **용어 주의.** 이 코호트의 `M_i` 는 중앙값 약 135 개(서열 길이의 50~65%)다 —
   격자 설계는 보존 마스킹 없이 생성됐으므로 point mutant 가 아니라 사실상 재설계다.
   따라서 `r_tier` 는 "point mutation 이 보존 위치를 건드렸는가" 가 아니라 **"바뀐
   위치 중 보존 위치의 비율"** 이다. 그렇게만 서술한다.

   **MSA query 서술도 보수적으로 쓴다.** peer 세션이 calibration 코호트 3 타겟에서
   제거한 N-말단 접두사는 `HM` · `GSH` · `G` 이고 His-tag 잔재·GST 절단 흔적·linker
   와 **일치하는** 형태다. 그러나 construct annotation 을 확인한 것이 아니라 서열
   접두사만 본 것이므로 단정하지 않는다.

   쓴다: *"N-terminal residues consistent with common cloning/tag remnants were
   excluded from the evolutionary-query sequence."* 그리고 *"host/construct-derived
   residues are not part of the native evolutionary sequence of the target domain."*

   쓰지 않는다: "이들은 cloning artifact 다", "진화 신호가 없다". 전자는 construct
   metadata 확인이 필요하고 후자는 절대명제다.

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

| mean AUC | 0.4996 | 0.5668 | **0.6392** | 0.6674 | 0.7030 | 0.7613 | 1.0000 |
|---|---|---|---|---|---|---|---|
| Δ_Top4 | +0.0008 | +0.0528 | **+0.1037** | +0.1252 | +0.1483 | +0.1899 | +0.3255 |

위 값은 **프로덕션 primitive 로 재생성한 정본**이다 (`26_gate2d_operating_characteristics.py`
→ `gate2d_operating_characteristics.json`). 최초 동결본에 인쇄된 값은 controller 의
임시 실행(power 루프 안 부트스트랩 800 회)에서 나온 것이고 최대 차이는 AUC 0.0024,
Δ_Top4 0.0052 였다. **Δ_Top4 +0.10 ↔ AUC ≈ 0.64 라는 대응은 그대로다.**

### GO 규칙 작동 특성 (n=11, 600 반복)

| 참 효과 Δ_Top4 | 대응 AUC | P(점추정 ≥ .10) | P(LCB > 0) | **P(GO)** |
|---|---|---|---|---|
| +0.0003 (신호 없음) | 0.50 | 0.0017 | 0.1283 | **0.0017** |
| +0.0532 | 0.57 | 0.0783 | 0.6917 | **0.0783** |
| +0.1026 | 0.64 | 0.5483 | 0.9617 | **0.5483** |
| +0.1218 | 0.665 | 0.7517 | 0.9867 | **0.7517** |
| +0.1469 | 0.70 | 0.9283 | 1.0000 | **0.9283** |

**P(GO) = P(점추정 ≥ .10) 이 다섯 행 전부에서 정확히 같다** — LCB 조항이 non-binding
하다는 것이 예측이 아니라 측정으로 확인됐다.

교정 표와 이 표는 별개의 시뮬레이션 실행이다(400 vs 600 반복). 같은 delta 에서
Δ_Top4 가 ±0.002 다르게 나오는 것은 그 때문이고, 어느 쪽도 실제 feature 를 쓰지 않는다.

두 가지를 사전 등록한다.

1. **귀무 거짓 GO 는 600 회 중 1 회다 (재동결 2026-09-10).** 프로덕션 primitive 로
   재생성하니 `0/600` 이 아니라 **`1/600 = 0.0017`** 이었다. P(GO) 표시값은 0.00 으로
   같지만 문장이 틀렸으므로 고친다. 동결 문구:
   *1 false GO was observed in 600 null simulations (1/600 = 0.002); one-sided 95%
   Clopper-Pearson upper bound 0.008.*

   **rule-of-three 를 쓰지 않는다** — 그 근사는 관측수가 0 일 때만 유효하다.
   0 이 아닌 관측 옆에 "≈0.5%" 를 적으면 자기모순이다. Clopper-Pearson 단측 95% 는
   관측수 0 에서 3/n 과 일치하므로 두 경우를 한 형식으로 보고할 수 있다. 점추정 조항이 통제를 담당하고 LCB 조항은 사실상 non-binding 한
   단일타겟 방어 장치다.
2. **NO-GO 의 해석을 미리 고정한다.** 위 검정력은 **사전 지정된 시뮬레이션 모형에
   조건부**다 — Δ_Top4 와 AUC 의 대응은 그 모형, prevalence, 백본 크기, 점수 분포에
   의존한다. 따라서 "AUC ≥ 0.70 인 예측기는 존재하지 않는다" 로 읽지 않는다. 동결
   문구는 다음이다.

   > Under the prespecified simulation model, the gate has approximately 93%
   > probability of GO for an effect corresponding to AUC ≈ 0.70. Therefore, NO-GO
   > would constitute evidence against an effect of approximately this magnitude
   > under the assumed operating conditions, rather than proving the absence of any
   > AUC ≥ 0.70 predictor.

   임계값과 참값이 같을 때(AUC ≈ 0.64) 검정력은 0.55 이므로 그 규모에 대한 NO-GO 는
   약한 증거일 뿐이다. **결과를 본 뒤 이 문구와 임계값을 바꾸지 않는다.**
   (0.93 · 0.55 는 프로덕션 primitive 재생성값이다. 최초 동결본의 0.94 · 0.54 는
   임시 실행값이었다.)

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

### 확정 (2026-09-11) — 두 게이트 모두 NO-GO

```
Gate 1  NO-GO [FINAL]   ρ +0.0379 · LCB90 -0.1559 · n_info 11   (문턱 0.25)
Gate 2  NO-GO [FINAL]   Δ_Top4 -0.0313 · LCB90 -0.0803 · n_info 11  (문턱 +0.10)
최종    STOP            이 연구축을 접는다. negative result 로 보고하고
                        RAPID 자체에 집중한다.
```

**PRIMARY DEVIATION 이 해소됐다.** planned S6 = `S5 + 조성 + per-sequence MPNN score`
(355 열)를 실행했다. realized S6(354 열, score 없음)와 **판정이 일치**하고 점추정은
+0.0053 움직였다 (−0.0366 → −0.0313). S0–S5 는 bit-for-bit 불변이다. 따라서 이 문서가
사전에 정한 확정 조건 — *"full S6 도 NO-GO 면 그때 `Gate 2 = NO-GO [FINAL]`,
`C = closed`"* — 이 충족됐다.

**Gate 1 arm 별 (판정은 primary 하나로만).**

| arm | train | ρ | LCB90 | top-1 regret (informative 11) |
|---|---|---|---|---|
| **primary** RFD3→RFD3 | 80 bb / 16 tgt | **+0.0379** | **−0.1559** | 0.1780 |
| sensitivity 1 (+BioEmu) | 100 / 16 | +0.0577 | −0.1524 | 0.1818 |
| descriptive / legacy (전체) | 157 / 62 | −0.0604 | −0.2561 | 0.2841 |
| comparator (native) | — | **non-evaluable** | — | — |

legacy arm 이 음수인 것은 §3 이 사전에 경고한 것과 일치한다 — native 백본이 계수를
형성한다. comparator 는 native 가 타겟당 1 백본이라 타겟 내 Spearman 이 정의되지
않아 non-evaluable 이며, **0 으로 기록하지 않는다.**

부수 분석 `Δ_generated` = **+0.0825** (LCB −0.0475, 10 타겟, native 라벨 있는 것만).
**GO 판정에서 제외**되며, 생성 백본이 native 보다 낫다는 주장의 근거로 쓰기에는
LCB 가 0 을 포함한다.

### Post-review terminology clarification (2026-09-11)

The native/RFD3 source separation was **prediction-blind but label-structure-informed**,
not strictly outcome-blind. Source-level `q_b` distributions and between-source variance
were inspected before Gate 1 predictions were evaluated. All prespecified arms are
reported. This refinement does not change the scientific verdict: both the RFD3-only
primary arm (`ρ = 0.0379`) and the descriptive legacy all-source arm (`ρ = −0.0604`)
remain below the frozen GO threshold (`ρ ≥ 0.25`). No threshold, endpoint, cohort, or
arm was selected after observing Gate 1 predictive performance.

이 문서 앞부분에서 이 결정을 `outcome-blind` 로 서술한 곳이 있다면 위 문단이
우선한다. `outcome-blind` 를 `prediction-blind` 로 단순 치환하지 않고 조항을 추가하는
이유는, 무엇을 보고 결정했는지(source 별 라벨 구조)와 무엇을 보지 않았는지(Gate 1
예측 성능)를 둘 다 남겨야 하기 때문이다.

### SoluProt 의 지위 (2026-09-11)

**SoluProt 은 measured solubility 가 아니라 computational proxy 다.** 현재 RAPID 에서
SoluProt 은 **optimization objective 가 아니라 proxy constraint / annotation** 이다.
`docs/manuscript.md:149` 가 이미 *"pLDDT and SoluProt scores do not establish soluble
expression … without experimental validation"* 라고 적고 있으며, 이 문서는 그와
충돌하지 않는다.

**게이트의 작동 강도는 코호트 의존적이다.** `SoluProt ≥ 0.5` 통과율은 홀드아웃
격자(마스킹 없는 재설계)에서 **97.5%**, 보존 마스킹된 CATH 파일럿에서 **87.5%** 다.
따라서 "거의 비어 있는 게이트" 라는 서술을 **파이프라인 전체로 일반화하지 않는다.**

`improved solubility` · `optimized solubility` 같은 실험적 개선 주장은 하지 않는다.
원고의 `solubility-oriented` 표현은 유지하되 Methods/Discussion 에서 SoluProt 의
지위를 objective 가 아닌 proxy constraint 로 일관되게 기술한다.

### NO-GO 의 강도 — 사전 등록된 대로만 읽는다

**Gate 1.** 사전 지정된 시뮬레이션 모형 아래에서 GO 확률은 ρ ≈ 0.33 에서 0.74,
ρ ≈ 0.44 에서 0.94 다. 따라서 대략 그 규모에 대한 증거이고, ρ ≈ 0.18 규모
(검정력 0.31)에는 약한 증거다. primary 는 백본 80 개에 384 차원(n/p = 0.21)이므로
**"신호 없음" 이 아니라 "이 표본에서 미검출"** 로 읽는다 (§3 사전 등록).

**Gate 2.** *Under the prespecified simulation model, the gate has approximately 93%
probability of GO for an effect corresponding to AUC ≈ 0.70. Therefore, NO-GO would
constitute evidence against an effect of approximately this magnitude under the
assumed operating conditions, rather than proving the absence of any AUC ≥ 0.70
predictor.* 문턱 자체(AUC ≈ 0.64)에서는 검정력 0.55 로 약한 증거다.

### encoder 레시피에 붙는 단서

Gate 1 의 feature 는 **복구된 레시피**이지 문서화된 것이 아니다. dev 157 백본을
`max abs diff 9.06e-06`, `allclose(atol=1e-4) True` 로 재현했고 exact-match variant
는 시도한 것들 중 유일하게 결정됐다. 결정적 요소는 **`residue_idx` 가 상수**라는
것이다 — 상대 위치 인코딩이 꺼져 있어 feature 가 순수하게 기하학적이며, 이는
`1c2eeb4` 의 *"sequence-independent"* 주장과 일치한다. 실제 `residue_idx` 를 주면
블록별 평균·표준편차는 여전히 맞아 보이면서 재현은 실패한다 — 이 게이트가 막으려던
조용한 train/test 공간 분리가 바로 그 모습이다.

**원본 스크립트가 없으므로 그것이 의도였는지는 확인할 수 없다.** dev 추출기가
위치 인코딩을 실수로 껐다면 Gate 1 이 그 선택을 상속한다. 그러나 train 과 test 가
같은 공간에 있어야 하므로 상속이 옳은 처리다.

### 쓸 수 있는 문장과 쓸 수 없는 문장

**쓸 수 있다.** *"사전 등록된 두 게이트에서 모두 실용적으로 유용한 신호를 찾지
못했다 — AF2 를 보기 전 백본 수준 예측(ρ +0.09)에서도, 백본 내부 서열 선택
(Δ_Top4 −0.03)에서도."* *"새 AF2 0 개로 이 판정에 도달했다."*

**쓸 수 없다.** *"백본/서열 수준 신호가 존재하지 않는다"*, *"ProteinMPNN encoder 는
백본 품질을 예측할 수 없다"*. 둘 다 사전 등록한 검정력이 지지하지 않는 절대명제다.

### 판정표 (변경 없음)

**realized-S6 의 NO-GO 를 공식 Gate 2 판정으로 닫지 않는다.** 판정 arm 을 S6 하나로
동결한 것은 사후 arm 선택을 막기 위해서였는데, 그 S6 를 사전 등록과 **다른 feature
집합**으로 실행했다면 그 동결의 효력이 그대로 유지된다고 말할 수 없다. 여기서
NO-GO 를 확정하면 "primary feature set 을 사전 등록과 다르게 실행했는데 왜
confirmatory NO-GO 인가" 라는 물음에 답할 수 없다.

**해소 경로가 있고 새 AF2 가 필요 없다.** 같은 1,680 폴드에 per-sequence
ProteinMPNN score 만 붙여 S6 를 재실행하면 된다. 그 score 를 만들려면
`v_48_020.pt` 체크포인트가 필요하고, **Task 7 의 Gate 1 encoder 재현에 필요한 것과
같은 체크포인트**다. 따라서 체크포인트가 확보되면 **Gate 1 encoder 재현과 Gate 2
MPNN score 복원을 함께** 수행한다.

full S6 도 NO-GO 면 그때 `Gate 2 = NO-GO [FINAL]`, `C = closed` 로 확정한다.

**지금 쓸 수 있는 문장과 쓸 수 없는 문장.** 쓸 수 있다 — *"현재 시험한 서열
표현들(SoluProt · raw ESM · ΔESM_global · ΔESM_mut · MSA conservation · 그 결합)에서
실용적으로 유용한 백본 내부 선택 신호를 찾지 못했다."* S0·S2·S3·S4 가 거의 0 이고
S5·realized-S6 가 음수이며 저심도 민감도도 같은 방향이므로 이 진술은 지지된다.
쓸 수 없다 — *"Gate 2 가 NO-GO 로 판정됐다"*, *"C 는 닫혔다"*.

### 판정표

| Gate 1 | Gate 2 | 결정 |
|---|---|---|
| GO | NO | **B 만.** backbone-specific surrogate prior + calibrated prior strength. C 는 하지 않는다 |
| GO | GO | **B + C.** hierarchical controller. sentinel/targeted 분리를 검증할 이유가 생긴다 |
| NO | GO | **C 단독.** B 를 억지로 합치지 않는다 |
| NO | NO | **◀ 해당.** 이 연구축을 접는다. negative result 로 보고하고 RAPID 자체에 집중한다 |

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
| `scripts/benchmark/21_gate2d_prepare_encoder.py` | P1 · 백본 encoder + dev 재현 검증 |
| `scripts/benchmark/22_gate2d_prepare_esm.py` | P2 · ESM 임베딩 |
| `scripts/benchmark/23_gate2d_prepare_msa_features.py` | P3 · MSA conservation |
| `scripts/benchmark/24_gate1_backbone_predictability.py` | Gate 1 |
| `scripts/benchmark/25_gate2_within_backbone_selectability.py` | Gate 2 (S0–S6) |
| `scripts/benchmark/26_gate2d_operating_characteristics.py` | OC 표 생성기 (재현성 계약) |
| `scripts/benchmark/27_gate2d_prepare_mpnn_scores.py` | S6 의 per-sequence MPNN score |
| `scripts/benchmark/_mpnn_encoder.py` | 복구된 encoder 추출기 |
| `public_data/benchmark/gate0/gate1_backbone_predictability.json` | Gate 1 결과 |
| `public_data/benchmark/gate0/gate2_within_backbone_selectability.json` | Gate 2 결과 |
| `public_data/benchmark/gate0/gate2d_operating_characteristics.json` | OC 표 (재현성 계약) |
| `docs/results_of_record.md` | 판정 수치. 인용은 이 파일 경유 |

**번호 정정 (2026-09-11).** 최초 동결본은 게이트 스크립트를 `21_`/`22_` 로 적었으나
그 번호는 P1/P2 준비 스크립트가 쓰게 되어 게이트는 `24_`/`25_` 다. 그리고
`gate2d_spec.json` 은 **만들지 않았다** — 동결 상수는 `_gate2d.py` 에 있고
`test_frozen_constants_match_spec` 이 이 문서와 대조하므로 기계가독 사본을 하나 더
두면 정본이 둘이 된다. 그 이중화가 이 프로젝트에서 이미 한 번 사고를 냈다.
