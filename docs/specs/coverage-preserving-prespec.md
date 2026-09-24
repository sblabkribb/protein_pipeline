# Coverage-preserving 배분 평가 — 결과 확인 전 동결

> **상태: 결과 확인 전 동결.** 34 표적 격자의 폴딩이 13% 진행된 시점에 쓴다.
> 분석은 폴딩이 끝난 뒤에 돌린다. 여기 적힌 값을 결과를 보고 바꾸지 않는다.

작성 2026-09-24. 정본 설계: Notion "RAPID 적응형 계산 배분 — 측정 결과와 결정"
(2026-09-08) 의 **v2.0 Coverage-Preserving Mode** 절. 이 문서는 그 결정을 이
코호트에 적용하기 위한 실행 사양이며, 거기서 정하지 않은 것을 새로 정하지
않는다.

---

## 0. 왜 새 사전지정이 필요한가

앞선 분석(`hierarchical-replay`, `depth-scaling-pilot`)은 **수확(joint-pass
확보량)을 목적함수로 둔 탐욕 배분**을 시험했고, 서열 순위화 위에 추가 이득이
없다는 결과를 얻었다(+0.25개 [−0.58, +1.25]; 깊이 42 에서 D=−0.010). 같은
분석에서 그 정책이 선택을 백본 2.0 개에 91% 몰아넣는 것도 측정했다.

**그런데 v2.0 정책은 수확을 목적함수로 삼지 않는다.** 정본은 coverage 를
최적화하고 수확은 acceptance guardrail 로만 쓴다. 즉 앞선 결과는 v2.0 에 대한
판정이 아니다 - 오히려 v2.0 이 목적함수를 바꾼 이유를 뒷받침한다. 이 문서는
**정본 정책을 그 자신의 종점으로** 평가한다.

앞선 사전지정들이 EFBC 계산을 금지한 것은 그 분석들의 범위 제한이었다. 이
코호트는 34 개 **새 표적**의 전수 격자이고 calibration 코호트가 아니므로
그 금지가 적용되지 않는다. 다만 앞선 산출물의 판정은 그대로 둔다.

## 1. 자료

```
표적       34 (동결 목록, hier_confirmatory_targets.json)
생성원     RFD3 단독
백본       수용 184 / 계획 204. 2 표적은 수용 0 이라 사실상 32 표적
후보       백본당 42, 전수 폴딩 (7,728)
격자       전수이므로 어떤 배분 정책도 오프라인으로 재생할 수 있다
```

**표적 교체 없음.** 생성 실패 2 표적은 모자란 채로 보고한다.

## 2. Coverage unit 과 주 종점 (Notion §1–2)

`coverage_unit = backbone_id` 로 고정한다. 이 값은 **coverage accounting 을
위한 operational design-context unit** 이며, 각 backbone 이 서로 다른
biological basin 이나 structural cluster 를 뜻한다고 주장하지 않는다.

주 종점은 **EFBC** 다.

```
EFBC(f) = exp(−Σ_b p_b log p_b),   p_b = f_b / Σ_j f_j
f_b     = backbone b 에서 얻은 joint-pass 후보 수
EFBC(0,…,0) = 0
```

EFBC 는 "발견한 backbone 수" 가 아니라 **feasible candidate mass 가 backbone
design context 사이에 얼마나 효과적으로 분산되어 있는지**를 잰다. 따라서
이미 한 backbone 에 mass 가 몰려 있을 때 그 backbone 에 성공이 하나 더
붙으면 EFBC 가 **감소할 수 있다.** 이 비단조성은 오류가 아니라 정의의 직접적
결과다.

종점 명칭은 `EFBC @ B calls` 가 아니라 다음으로 쓴다 (Notion §6).

> **공통 최대 계산 예산 상한 B 안에서 달성한 terminal EFBC**

## 3. 정책 (Notion §3–5)

### 3.1 q_b 가 예측하는 사건 — joint-pass 다

```
joint-pass = pLDDT ≥ 85 AND 비루프 Cα-RMSD ≤ 2.0 Å AND SoluProt ≥ 0.5
```

`q_b` 는 "다음 계산이 **joint-pass 후보 하나를 낳을** posterior-predictive
확률" 이다. v1 의 structural-success posterior 를 이름만 바꾸어 쓰지 않는다.

상태 계약도 유지한다.

```
joint-pass                      → 과학적 성공 관측
valid non-pass                  → 과학적 실패 관측
refused / missing / technical failed → Bernoulli 실패로 변환하지 않는다
```

### 3.2 posterior family · prior · pooling

```
family     Beta-Bernoulli
warm-up    백본당 최소 probe 4. 이 구간에서 STOP 을 허용하지 않는다.
표적 사후  그 표적 아래 모든 backbone 의 관측을 합쳐 p̂_t 를 만든다
부분 풀링  α_prior = p̂_t·κ_pool,  β_prior = (1−p̂_t)·κ_pool,  κ_pool = 4.0
백본 사후  α_b = α_prior + s_b,   β_b = β_prior + n_b − s_b
q_b        = α_b / (α_b + β_b)
```

**Gate 0 사전분포는 쓰지 않는다.** 기존 Gate 0 모델은 structural-success 로
학습됐고 §3.1 이 요구하는 joint-pass 예측기가 아니다. Notion §4 가 이름만
바꿔 재사용하는 것을 금지하므로, 이 코호트에서는 표적 수준 부분 풀링만으로
사전정보를 만든다. 표적 사후가 만들어지기 전(warm-up 이전)에는 균등
Beta(1,1) 을 쓴다.

`κ_pool = 4.0` 은 정본 값이며 이 코호트에서 조정하지 않는다. Notion 의
경고대로 이것은 엄밀한 conjugate hierarchical posterior 가 아니라 **고정 강도
shrinkage / 부분 풀링 규칙**이므로, 결과를 "hierarchical Bayesian posterior"
라고 기술하지 않는다.

### 3.3 acquisition — one-step expected marginal EFBC gain

```
A_b = q_b · [ EFBC(f + e_b) − EFBC(f) ]
```

별도의 uncertainty bonus 를 붙이지 않는다. next-outcome 의 불확실성은 `q_b`
에 반영되지만 value of information 이나 non-myopic information gain 을
계산하지 않는다. **명시적으로 one-step myopic 정책이다.**

모든 action 의 계산비용이 같으므로(폴드 1 회) cost adjustment 를 적용하지
않는다.

### 3.4 STOP

```
if max_b A_b > 0:  allocate argmax_b A_b
else:              STOP
```

`max_b A_b ≤ 0` 은 **현재 one-step EFBC 목적에서 양의 기대 coverage gain 을
갖는 action 이 없다는 local saturation** 만 뜻한다. 전역 최적 도달, 추가 계산의
과학적 무가치, 정보 소진, long-horizon 최적 도달을 뜻하지 않는다.

## 4. 비교군 (Notion §6)

```
주 비교군   same-cap static/equal allocation
보조 비교군 수확 탐욕형 배분 (앞선 분석의 greedy_fill)
보조 보고   realized calls (v2 가 STOP 하면 상한보다 적게 쓴다)
민감도      static/equal 을 v2 의 realized calls 에 맞춘 판
```

`greedy_fill` 을 보조 비교군으로 두는 이유는, 수확 목적과 coverage 목적이
같은 자료에서 어떻게 갈리는지 보여야 §0 의 논리가 닫히기 때문이다.

## 5. Acceptance guardrail (Notion §7)

정책 목적함수와 채택 판정을 분리한다.

```
정책 목적함수   EFBC
채택 가드레일   structural-yield 비열등성
                ratio 의 단측 95% 하한 ≥ 0.90
```

가드레일을 못 넘으면 **뒤에서 수확 정책으로 fallback 하여 결과를 구제하지
않는다.** 그 조건에서 coverage mode 가 acceptance criterion 을 충족하지
못했다고 판정한다.

## 6. 구조 진단 (Notion §8)

**EFBC 가 높다고 structural diversity 가 높다고 주장하지 않는다.** 구조적
다양성은 threshold-free 연속 진단으로 따로 본다.

```
1. context-level structural dispersion   feasible 후보가 있는 백본을 하나씩
                                          써서 pairwise CA-RMSD
2. feasible-mass-weighted dispersion      백본별 feasible mass 로 가중
3. 거리 분포와 분위수를 함께 보고
4. structural clustering 은 탐색적 민감도로만 (M1 에서 threshold/linkage
   불안정이 확인됐다)
```

해석은 결과에 따라 갈라 적는다.

```
EFBC↑ · dispersion↑   backbone-context coverage 증가가 greater structural
                      dispersion 과 동반되었다고 보고
EFBC↑ · dispersion→   operational coverage 증가는 확인되었으나 measurable
                      structural diversification 으로 이어지지 않았다고 보고
```

## 7. 통계

```
단위    표적 (생성원 하나이므로 표적 = 클러스터)
구간    표적 클러스터 부트스트랩 2,000 회 · percentile · seed 20260921
쌍대    같은 재표집 표본 안에서 정책 간 차이를 계산
seed    42 · 123 · 7 · 2024 · 31337
예산    B = 42·84·126·168 (백본 6 개 기준 7·14·21·28 calls/backbone)
주 판정 B 는 중간값 126 을 주 예산점으로 하고 나머지는 민감도로 본다
다중성  주 비교는 EFBC 하나이므로 보정하지 않는다. 보조 비교는 보정 없이
        내되 역할을 명시한다.
```

## 8. 사전에 정해 두는 해석 규칙

```
구간이 0 을 포함하면   "구별되지 않았다". 동등성이 아니다.
EFBC 의 비단조성       정의의 결과이지 오류가 아니다. 그대로 보고한다.
STOP                   local saturation 으로만 기술한다.
배수 표현              쓰지 않는다.
```

## 9. 하지 않는 것 (Notion §9)

- `backbone_id = biological basin` 이라고 주장하지 않는다.
- EFBC 를 structural diversity metric 이라고 부르지 않는다.
- structural clustering 을 allocation unit 으로 쓰지 않는다.
- 임의의 uncertainty 계수를 추가하지 않는다.
- information gain · value of information · non-myopic optimality 를
  주장하지 않는다.
- local saturation 후 수확 정책으로 fallback 하지 않는다.
- 미구현 `generate_new_backbone` 을 기능으로 주장하지 않는다.
- 새 folding 을 하지 않는다. 34 표적 격자를 오프라인 재생할 뿐이다.
- 앞선 분석(`hierarchical-replay`, `depth-scaling-pilot`)의 동결 판정을
  이 결과로 덮어쓰지 않는다. 목적함수가 다른 별개 평가다.

## 10. 결과별 처리

```
EFBC 우위 + 가드레일 통과   coverage-preserving 모드가 이 코호트에서
                            작동했다고 보고한다.
EFBC 우위 + 가드레일 실패   그 조건에서 acceptance criterion 미충족으로
                            판정한다. fallback 하지 않는다.
EFBC 구별 안 됨             구별되지 않았다고 보고한다. 수확 결과와 함께
                            "두 목적함수 모두에서 배분 이득이 확인되지
                            않았다" 로 쓴다.
```

**어느 쪽이 나와도 보고한다.**
