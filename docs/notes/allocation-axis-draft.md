# 배분 축 — 확증 캠페인 원고 초안

> **방법과 해석적 주장만 쓴 상태다.** 결과 절은 자리표시이며 폴딩이 끝난 뒤
> `42_`·`39_`·`40_`·`41_`·`45_` 의 산출물로 채운다. 여기 적힌 설계는 전부
> 결과 확인 전에 동결·커밋된 것이므로, 나중 숫자에 맞춰 고치지 않는다.

초안 2026-09-28. 병합 대상: `/opt/용해성 지향 단백질 재설계 파이프라인.docx`
(§3.3·§4.4·§5.3 이 파일럿 수준으로 이미 있다 - 그 뒤에 잇는다).

---

## 3.5 실험 4: 배분 가설의 확증 코호트

앞선 §3.3 은 v2 코호트 8 unit 과 깊이 파일럿에서 배분을 쟀다. 그 자료는
**가설을 만든 자료**다. `greedy_frozen - rf_only = +1.55 [-0.60, +4.25]` 에서
+1.55 의 대부분이 표적 하나(`1n81A00`, +10.00)에서 나왔고 그것을 빼면
+0.34 였다. 즉 가설이지 증거가 아니었다.

이 절은 그 가설을 **처음으로 미리 고정한 정책**으로 새 표적에서 시험한다.
규칙은 `docs/specs/hierarchical-confirmatory-prespec.md` (v1.6) 에 실행 전
동결했다.

### 코호트

```
생성원   RFD3 단독 (BioEmu 는 넣지 않는다)
표적     34. CATH pilot 중 v2 와 코호트 B 어디에도 쓰이지 않은 것
비중복   같은 PDB 엔트리 금지 · 쌍대 서열 동일성 30% 미만
길이     80-400 aa
백본     표적당 6 계획 · 실제 수용 184/204
서열     백본당 42 (보존도 tier 14/14/14 균형)
폴딩     7,728 전수
```

전수 격자이므로 **어떤 배분 정책도 추가 folding 없이 오프라인으로 재생**할 수
있다. 이 설계 선택이 이 절 전체의 전제다.

두 가지를 한계로 적는다. (1) 생성 실패로 백본 수용이 0 인 표적이 2 개이고,
사전지정 §9 대로 표적을 새로 고르지 않고 모자란 채로 보고한다 - 실효 32
표적이다. (2) CATH superfamily 분류가 로컬에 없어 **superfamily 수준의
비중복은 확인하지 못했다.** 비중복은 PDB 엔트리와 서열 동일성으로만 보장된다.

### 왜 게이트를 통과하지 못한 채로 돌렸는가

사전지정 §7.0 은 표본 크기를 깊이 파일럿의 효과 `D_p` 로 정하게 해 두었고,
`D_p <= 0` 이면 공식을 쓰지 않고 멈추도록 했다. 파일럿 결과는
`D(42) - D(18) = -0.119 [-0.238, +0.079]`, `D(42) = -0.010` 으로 게이트를
통과하지 못했다.

그 뒤 사람이 **구간 축소를 목적으로** 실행을 승인했다(v1.6). 근거는 파일럿
표본이 작아(주 비교 8 unit, 깊이 5 unit) 작은 양의 효과를 배제할 수 없다는
것이었다. **따라서 이 결과는 구간을 좁히는 데 쓰고, 양성이 나와도 게이트를
소급해 통과시키지 않는다.** 이 문장을 결과 절에 그대로 유지한다.

### 정책

`greedy_frozen` 을 사전지정 §5 에 전부 고정했다. 모든 arm 이 같은 seed 에서
**같은 warm-up 표본**을 받고, 차이는 남은 예산을 쓰는 방식에서만 생긴다.

```
1  백본마다 sentinel 4 개를 백본 안에서 무작위 추출            -> 24 calls
2  warm-up 24 개로 RF 적합 (ESM-2 8M 320 d, 표준화 없음,
   RandomForestRegressor n_estimators=100, random_state=seed)
3  백본 posterior mean = (통과 + 1) / (관측 + 2)               Beta(1,1)
4  posterior mean 내림차순 정렬. 동점이면 backbone_key 사전순
5  순서대로 한 백본씩 정원까지 꽉 채운다. 정원 = min(40, 후보수) - 4
6  백본 안에서는 RF 예측 상위부터. 동점이면 sequence_id 사전순
7  예산이 소진될 때까지 5-6 반복
```

posterior 갱신 없음, 탐색 몫 없음. 갱신을 뺀 이유는 §3.3 에서 되먹임의 기여가
`+0.00 [-0.32, +0.25]` 로 측정됐기 때문이고, 탐색 몫을 뺀 이유는 그 기여가
`-0.15` 로 순손실이었기 때문이다.

비교군은 `rf_only` (백본 무시, RF 상위), `equal_random`, `backbone_only`
(배분만 greedy, 백본 안은 무작위), `mpnn_only` (백본 조건부 NLL 오름차순),
`oracle` (참 라벨 상위, 눈금으로만). `adaptive_sentinel` 은 §8 탐색 arm 으로만
내고 **판정하지 않는다.**

### 종점

```
G(policy) = (Y_policy - Y_equal_random) / (Y_oracle - Y_equal_random)
주 종점   G(greedy_frozen) - G(rf_only) 의 표적 평균,  B = 80
보조      Y(greedy_frozen) - Y(rf_only) 원시 개수 (자격 규칙 없음)
```

정규화는 검정력을 위한 변환이 아니다. 표적마다 joint-pass 기회가 크게 달라
개수 차이가 기회 크기에 끌려가므로, **그 표적에서 실제로 회수 가능한 여지 중
얼마를 가져갔나**를 비교한다.

분모가 0 에 가까우면 비율이 폭발하므로 자격 규칙을 결과 전에 정했다. 분모의
기댓값은 닫힌 형태로 나온다.

```
분모(r) = H*r + min(B-H, (N-H)*r) - B*r        N=252, B=80, H=24
자격     분모 >= 5   (자격 구간 0.032 <= r <= 0.910)
```

자격은 **실측 joint-pass 율로만** 판정하며 정책 결과를 보고 판정하지 않는다.
자격 미달 unit 은 주 종점에서 빼되 원시 개수 보조에는 남긴다.

### 통계

```
단위   표적 (생성원 하나이므로 표적 = unit)
구간   표적 클러스터 부트스트랩 2,000 회 · percentile · seed 20260921
쌍대   같은 재표집 표본 안에서 arm 차이를 계산
seed   42 · 123 · 7 · 2024 · 31337  (arm 간 공통 warm-up)
다중성 주 종점이 하나이므로 보정하지 않는다
판정   95% 구간이 0 을 제외하고 부호가 양수면 가설을 지지한다.
       그 외에는 지지하지 않는다. 동등성·비열등성으로 쓰지 않는다.
```

검정력을 미리 적어 둔다. 파일럿의 정규화 효과(평균 +0.118, 자격 unit SD
0.184)와 v2 실측 자격률 55% 를 쓰면 34 표적에서 자격 unit 약 18.7, 검정력
약 79%, 80% 검정력의 MDE 는 약 +0.12 다. **자격 unit 이 16 개 아래면 검정력이
73% 밑이며, 그 경우 음성 결과를 "효과 없음" 으로 쓰지 않는다** - 결론 문장에
관측된 자격 unit 수와 그때의 검정력을 함께 적는다.

## 3.6 선택 이득을 백본 간과 백본 내로 가른다

동결된 판정 셋이 서로 맞지 않아 보인다.

```
Gate 2     백본 내부에서 cheap predictor 가 서열을 못 가른다 (NO-GO)
실험 1·2   표적의 전체 풀에서는 RF 가 잘 고른다
실험 3     명시적 백본 배분을 얹어도 추가 이득이 없다
```

estimand 가 다르다. 가설은 **RF 의 이득이 주로 백본 간 판별에서 오고 그래서
명시적 배분이 중복**이라는 것이다. 맞으면 세 결과가 하나의 기전으로 정리된다.
규칙은 `docs/specs/selection-gain-decomposition-prespec.md` 에 동결했다.

네 arm 이 **같은 warm-up 표본과 같은 RF 적합**을 공유하고 선택만 다르다.

```
            백본 내 = RF        백본 내 = 무작위
배분 = RF   rf/rf               rf/rand      <- Between
배분 = 균등 unif/rf             unif/rand    <- 기준선
                ^-- Within

Total   = Y(rf/rf)   - Y(unif/rand)
Between = Y(rf/rand) - Y(unif/rand)
Within  = Y(unif/rf) - Y(unif/rand)
Inter   = Total - Between - Within      어느 쪽에도 귀속하지 않는다
주 종점 = Between - Within.  사전 예측: Within ~ 0
```

`rf/rf` 가 실제로 고른 백본별 개수를 `rf_rand` 의 배분으로 그대로 쓴다. 즉 두
arm 은 백본별 호출 수가 **정확히 같고** 백본 안에서의 선택만 다르다.

## 3.7 목적함수를 coverage 로 바꾼 정책의 평가

§3.3-§3.5 는 모두 **수확을 목적함수로 둔** 배분을 시험한다. 정본 v2.0 정책은
수확을 목적함수로 삼지 않는다 - coverage 를 최적화하고 수확은 acceptance
guardrail 로만 쓴다. 따라서 앞선 결과는 v2.0 에 대한 판정이 아니며, 오히려
v2.0 이 목적함수를 바꾼 이유를 뒷받침한다. 이 절은 정본 정책을 **제 종점으로**
잰다. 규칙은 `docs/specs/coverage-preserving-prespec.md` 에 동결했다.

```
coverage unit   backbone_id
주 종점         공통 최대 계산 예산 상한 B 안에서 달성한 terminal EFBC
EFBC(f)         exp(-sum p_b log p_b),  p_b = f_b / sum f,  EFBC(0) = 0
f_b             backbone b 에서 얻은 joint-pass 후보 수
```

EFBC 는 "발견한 backbone 수" 가 아니라 **feasible candidate mass 가 backbone
design context 사이에 얼마나 효과적으로 분산돼 있는지**를 잰다. 그래서 이미
한 backbone 에 mass 가 몰려 있을 때 거기 성공이 하나 더 붙으면 EFBC 가
**감소할 수 있다.** 이 비단조성은 오류가 아니라 정의의 직접적 결과다.

정책은 one-step myopic 이다.

```
q_b       다음 계산이 joint-pass 후보 하나를 낳을 posterior-predictive 확률
family    Beta-Bernoulli · warm-up 백본당 4 (이 구간에서 STOP 금지)
부분 풀링 a_prior = p_t * kappa,  b_prior = (1 - p_t) * kappa,  kappa = 4.0
A_b       q_b * [ EFBC(f + e_b) - EFBC(f) ]
STOP      max_b A_b <= 0
```

**Gate 0 사전분포를 쓰지 않는다.** 기존 Gate 0 모델은 structural-success 로
학습됐고 여기서 요구하는 joint-pass 예측기가 아니다. 이름만 바꿔 재사용하는
것을 금지했으므로 표적 수준 부분 풀링만으로 사전정보를 만든다. `kappa = 4.0`
은 엄밀한 conjugate hierarchical posterior 가 아니라 **고정 강도 shrinkage
규칙**이므로 결과를 "hierarchical Bayesian posterior" 라고 기술하지 않는다.

```
비교군    same-cap static/equal (주) · 수확 탐욕형 greedy_fill (보조)
민감도    static/equal 을 v2 의 realized calls 에 맞춘 판
예산      B = 42 · 84 · 126 · 168,  주 예산점 126
가드레일  structural-yield 비율의 단측 95% 하한 >= 0.90
```

가드레일을 못 넘으면 **뒤에서 수확 정책으로 fallback 하여 결과를 구제하지
않는다.** 그 조건에서 coverage mode 가 acceptance criterion 을 충족하지
못했다고 판정한다.

### 구조 진단

**EFBC 가 높다고 structural diversity 가 높다고 주장하지 않는다.** 구조적
다양성은 threshold-free 연속 진단으로 따로 본다 - feasible 후보가 있는 백본을
하나씩 대표로 써서 Kabsch 중첩 후 pairwise CA-RMSD 를 내고, 비가중과
feasible-mass 가중을 함께 보고한다. clustering 은 threshold/linkage 불안정이
확인됐으므로 탐색적 민감도로만 쓰고 배분 단위로 쓰지 않는다.

해석 규칙도 결과 전에 갈라 적어 두었다.

```
EFBC 상승 · dispersion 상승   coverage 증가가 greater structural dispersion 과
                              동반되었다고 보고
EFBC 상승 · dispersion 불변   operational coverage 증가는 확인되었으나
                              measurable structural diversification 으로
                              이어지지 않았다고 보고
```

## 4.5 결과 — 확증 코호트

*[폴딩 마감 후 `42_` 산출물로 채운다. 자격 unit 수와 그때의 검정력을 반드시
함께 적는다.]*

## 4.6 결과 — 선택 이득의 분해

*[`39_` 산출물로 채운다.]*

## 4.7 결과 — coverage 목적함수

*[`40_`·`41_` 산출물로 채운다.]*

## 5.4 STOP 규칙은 정책이 목표 상태에 도달하는 순간 발동한다

이 절의 주장 1 은 **관측을 쓰지 않는다.** 그래서 폴딩이 끝나기 전에 쓸 수 있고,
실제로 결과보다 먼저 커밋했다(`4ca28be`, `docs/notes/stop-rule-diagnosis.md`).

백본 k 개의 feasible mass 가 균등하면 `f = (n, ..., n)` 이고 `EFBC(f) = k` 다.
어느 한 곳에 1 을 더하면 분포가 균등에서 멀어져 엔트로피가 엄격히 줄므로

```
EFBC(f + e_b) - EFBC(f) < 0      모든 b 에 대해
A_b = q_b * (음수) <= 0          q_b >= 0 이므로
=> max_b A_b <= 0                => STOP
```

**one-step myopic EFBC 정책은 자기 목적함수의 최적점에서 스스로 멈춘다.**
`45_.analytic_check` 가 k = 2..12, n = 1..40 격자에서 부호를 직접 확인한다.

이것은 이 코호트의 성질이 아니라 acquisition 의 성질이다. 엔트로피류 목적에
`max A <= 0 -> STOP` 을 붙이면 어디서나 같은 일이 생긴다. 이 지적이 이 절의
기여이며, 특정 자료에 의존하지 않는다는 점이 그 가치다.

주장 2(그 상태에 얼마나 자주 닿는가)와 주장 3(멈춘 대가)은 자료가 답한다.
주장 3 은 가드레일 실패를 본 뒤 돌린 반사실이므로 **탐색적이라고 명시하고
확증 주장으로 쓰지 않으며, 이 값으로 채택 판정을 뒤집지 않는다.**

*[주장 2·3 의 수치는 `45_` 산출물로 채운다.]*

## 6.x 한계 (이 절에서 추가되는 것)

- 게이트 미통과 뒤 사람이 승인한 실행이다. 구간 축소가 목적이며 양성이 나와도
  게이트를 소급해 통과시키지 않는다.
- superfamily 수준 비중복은 확인하지 못했다.
- 백본 수용 0 인 표적 2 개를 교체하지 않았다. 실효 32 표적이다.
- 주장 3 의 반사실은 탐색적이다.
- `backbone_id` 를 biological basin 이라고 주장하지 않는다. EFBC 를 structural
  diversity metric 이라고 부르지 않는다.
