# RAPID v2 — TaskProfile 기반 adaptive compute allocation 설계안

**상태: 설계. 구현 승인 전.** v1 코드는 건드리지 않는다.
이전 판본: `rapid-objective-pluggable-v2-design.md` (같은 파일, git 이력 유지).

## 세 문장 요약

> RAPID v2 는 task-specific protein-design pipeline 을 대체하지 않고, 해당
> TaskProfile 이 정의한 design space 안에서 제한된 계산 예산을 어디에 추가로
> 사용할지 결정하는 adaptive allocation core 다.

> fixed-backbone redesign 에서 여러 backbone 을 쓰는 목적은 서로 다른 design
> basin 을 탐색하는 것이므로, diversity 를 선택된 하나의 backbone 내부 sequence
> diversity 로 축소하지 않으며, v2.0 은 제공된 backbone pool 의 exploration 과
> coverage 를 보존하는 데까지만 책임진다.

> Antigen 은 독립적인 antibody-antigen design application 과 scientific
> pipeline 을 유지하면서 AntigenTaskProfile 을 통해 adaptive compute allocation
> 을 사용할 수 있고, 향후 wet 결과로 evaluator 와 allocation policy 를 검증하는
> flagship application 이 될 수 있다.

---

# A. 이전 설계에서 잘못되었거나 모호했던 가정

이 절은 무엇을 고쳤는지 남기기 위한 것이다. 이전 판본을 지우고 새로 쓰면 같은
실수가 왜 나왔는지가 사라진다.

## A1. arm 정의를 보편 상수로 못 박았다

이전 §5 는 `arm = backbone × generation_condition` 을 v2 전체의 arm 정의로
적었다. 이 정의는 fixed-backbone redesign 에서 맞고 frozen v1 에서 그대로
유지되지만, 다른 task 의 반복 단위까지 이것이라고 볼 근거가 없다. 실제로 Antigen
의 반복 단위는 다르다 (§K).

## A2. objective 를 갈아끼우면 다른 task 가 된다고 암시했다

이전 §9 의 프로파일 B/C/D 는 `primary: stability`, `primary: binding`,
`primary: user_defined` 를 같은 pipeline 위에서 objective 만 바꾼 것으로 적었다.
binder design 은 objective 가 다른 것이 아니라 **design space 가 다르다** -
입력이 복합체이고, 생성 단계가 다르고, 평가 대상이 계면이다. 프로파일 D
(`custom`, 임의 plugin evaluator) 는 "사용자가 요청하면 evaluator 를 붙인다" 를
허용하는 형태였고, 이는 §20 이 금지하는 것이다.

레지스트리는 이미 이 점을 알고 있었다. `MODEL_REGISTRY_V1.yaml` 의 `purposes`
는 purpose 마다 **허용 objective 목록과 stage 목록**을 따로 들고 있고,
`antibody_design` 에는 "이 경로는 여기서 실행되지 않는다, antigen pipeline 의
ROUTER_POLICY_V1.1 로 보내라" 는 `referral` 이 이미 적혀 있다. 설계 문서가
코드보다 뒤처져 있었다.

## A3. diversity 를 sequence 통계 하나로 다뤘다

레지스트리의 `objective_status.diversity` 는 `status: measured`,
`evaluators: []`, "서열 통계로 직접 계산한다 (위치 엔트로피, 쌍별 거리)" 다.
`Objective.unsupported()` 는 `measurable.add("diversity")` 로 diversity 를
언제나 측정 가능으로 표시한다.

이 표현대로면 diversity 는 "서열들이 서로 얼마나 다른가" 하나이고, 그렇다면
**한 backbone 에서 서열을 더 뽑아 다양하게 만드는 것**으로 충족된다고 읽힌다.
그 해석은 여러 backbone 을 만드는 이유를 지운다. §C 의 측정값이 그것을 직접
반박한다.

## A4. `sequence-diversity-oriented redesign` 을 primary objective 로 적었다

UX 예시가

```
Primary objective
○ Structural-yield maximization
○ Sequence-diversity-oriented redesign
```

였다. 구현자가 "다양성을 고르면 좋은 backbone 을 찾아 거기서 서열을 많이 뽑는다"
로 읽을 수 있다. §D 에서 optimization mode 로 바꾼다.

## A5. redundancy 항이 있었지만 정의가 없었다

이전 acquisition 식

```
A = expected_utility + β·uncertainty + η·allocation_signal − λ·cost − γ·redundancy
```

의 `redundancy` 는 v1 의 `_diversity_term` 을 가리켰다. 그 항은 **한 배치 안에서
같은 backbone 을 두 번 고르는 것에 대한 벌점**이고 (`allocation.py`
`_diversity_term`: 같은 backbone 1.0, 같은 target 0.5), batch 를 벗어나면
사라진다. 누적 coverage 상태가 아니다. 이것을 coverage 라고 부르면 안 된다.

## A6. abandon 에 coverage 하한이 없었다

`abandon_backbone → abandon_arm` 만 이름을 바꿨다. frozen v1 에는
`MIN_PROBE_SEQUENCES = 4` 라는 arm 별 최소 관측이 있어서 2/2 로 버리는 것은
막지만, **pool 수준의 coverage 하한은 없다.** 관측이 4 개만 있어도 movability 가
바닥이면 버릴 수 있고, 남은 backbone 이 몇 개인지는 보지 않는다. v1 에서는
의도된 설계지만 (v1 의 목적은 structural yield 다), coverage-preserving mode 를
말하려면 부족하다.

## A7. v2.0 이 무엇을 할 수 있는지 과장될 여지가 있었다

"objective-pluggable" 이라는 이름은 목적을 자유롭게 갈아끼울 수 있다고 읽힌다.
실제로 v2.0 이 하는 일은 **이미 주어진 arm pool 위에서의 배분**이고, 새 arm 을
만들지 못한다. 이름을 바꾼 이유다.

---

# B. RAPID Core 와 TaskProfile 의 책임 경계 (Q1)

## B1. 경계선

RAPID Core 가 답하는 질문은 하나다.

> 지금까지의 관측을 볼 때, **다음 계산 단위를 어디에 쓸 것인가.**

RAPID Core 가 답하지 않는 질문:

```
이 단백질은 antibody 인가          → TaskProfile
CDR 은 어디인가                    → TaskProfile
어떤 generator 를 써야 하는가       → TaskProfile
binding 을 무엇으로 재는가          → TaskProfile
이 결과를 이 목적에 써도 되는가      → TaskProfile + Registry
어느 arm 에 다음 계산을 쓰는가       → RAPID Core
```

## B2. Core 가 받는 것 — 모델 이름 없음

RAPID Core 의 입력은 generic 하다. §26 의 요구대로 Core 안에 AF2, AF3, ESMFold,
SoluProt, PPIformer, Rosetta, ThermoMPNN, AntiFold, ProteinMPNN 어느 이름도
나타나지 않는다.

```
ArmState
  expected_utility          objective 기준 기대값
  uncertainty               사후 분산 / 표준편차
  exploration_state         관측 수, 최소 probe 충족 여부
  coverage_contribution     이 arm 이 pool coverage 에 기여하는 정도
  redundancy                이미 확보한 것과 얼마나 겹치는가
  marginal_value_trend      최근 관측이 새 정보를 주고 있는가
  cost                      이 arm 을 한 번 더 관측하는 비용
  fidelity_channel          어느 관측 채널인가 (이름이 아니라 등급)
  permissions               이 신호를 이 결정에 써도 되는가
```

이 값들을 **누가 만들었는지**는 Core 의 관심이 아니다. `expected_utility` 가
AF2 pLDDT 에서 왔는지 PPIformer ddG 에서 왔는지 Core 는 모른다. TaskProfile 이
ScoreTransform 을 통해 채운다.

## B3. 검증 방법 (Invariant 5 의 집행)

Core 모듈에 대해 금지 식별자 목록을 두고 import·문자열 양쪽을 테스트로 막는다.
현재 `test_allocation_v1_golden.py` 가 v1 에 대해 leakage guard 를 이미 갖고
있고 (`set_backbone_true_yield` 호출 금지), 같은 형태를 Core 에 적용한다.

---

# C. 여러 backbone 을 만드는 목적, 그리고 왜 sequence diversity 가 그것을 대신할 수 없는가 (Q2, Q3)

이 절은 이 설계에서 가장 중요하다. **주장이 아니라 이 저장소와 형제
pipeline 에서 이미 측정된 값으로 쓴다.**

## C1. 목적: 서로 다른 design basin

여러 RFD3 backbone 을 만드는 이유는 성공률 추정을 위한 replicate 를 늘리는 것이
아니라, **서로 다른 구조적 context 를 주어 서로 다른 sequence basin 을 열기
위해서**다.

## C2. 측정: 한 backbone 은 서열을 아무리 뽑아도 basin 이 늘지 않는다

`public_data/benchmark/results/sequence_space_coverage_summary.json`
(효소 3 종 평균, ≤70% pairwise identity 로 묶은 고유 서열 클러스터 수):

| 표본 수 | 단일 backbone | 앙상블 |
|---|---|---|
| 10 | 1.3 | 6.7 |
| 50 | 1.5 | 16.0 |
| 500 | 2.7 | 59.0 |
| 5,000 | **4.0** | **203.7** |

**단일 backbone 은 서열 5,000 개를 뽑아도 고유 클러스터 4 개에서 포화한다.**
앙상블은 같은 축에서 203.7 까지 간다. 격차가 표본 수에 따라 5 배에서 50 배로
벌어진다.

이것이 Q3 의 답이다. sequence diversity 를 늘리는 행위 (= 서열을 더 뽑는 것) 는
backbone 이 정한 basin 상한을 넘지 못한다. 두 축은 대체 관계가 아니다.

## C3. 반례를 숨기지 않는다 — 온도는 부분적으로 대체할 수 있다

`docs/figures/README.md` 에 기록된, **논문에서 제외된** 그림
(`expl_temperature_diversity_recovery_tradeoff.png`) 은 다음을 보여준다.

- 단일 backbone 에서 ProteinMPNN 온도를 올리면 mean pairwise diversity 가
  0.12 → 0.30 으로 단조 증가한다.
- RFD3+BioEmu 앙상블은 T=0.1 에서 0.29–0.33 이다.
- 즉 **mean pairwise diversity 축에서는 온도가 앙상블 수준에 도달한다.**
  대가는 native recovery 감소 (0.38 → 0.33) 다.
- README 는 이 그림을 "논문 서사를 약화시켜 제외" 라고 적고 있다.

따라서 정확한 진술은 이렇다.

> **intensive 지표 (mean pairwise diversity) 에서는** 단일 backbone 도 온도를
> 올려 앙상블 수준의 값을 얻을 수 있고, native recovery 를 대가로 낸다.
> **extensive 지표 (고유 서열 클러스터 수) 에서는** 단일 backbone 이 4 개에서
> 포화하고 앙상블은 203.7 로 계속 늘어난다.

"온도로는 다양성을 못 얻는다" 는 틀렸다. 맞는 것은 **"온도로는 basin 수를 못
늘린다"** 다. 설계 문서에 이 구분을 남긴다 - 서사에 불리하다는 이유로 제외한
측정은 설계 근거에서까지 빠지면 안 된다.

## C4. 측정: 같은 backbone 의 후보들은 서로 중복이다 (Antigen)

`/opt/antigen_pipeline` 커밋 `ca84aab`:

- antifold-r7 의 생존 후보 93 개는 backbone 35 개에서 나왔고, 한 backbone 이
  8 개를 냈다.
- **같은 backbone 을 공유하는 후보는 CDR geometry 를 공유하고, r6 에서 변이
  집합이 90% 겹쳤다.**
- 93 개를 그대로 합성하면 scaffold 35 개를 시험하는데 그중 하나를 여덟 번
  시험하는 것이 된다.
- backbone 당 1 개로 상한을 걸면 35 개 construct 가 같은 35 scaffold 를 덮고,
  ddG 정렬 뒤에 상한이 걸리므로 각 backbone 이 자기 최선을 낸다.
  **보관 집합의 ddG 중앙값이 +1.00 에서 +0.12 로 개선됐다.**

즉 backbone coverage 를 강제했더니 portfolio 의 품질 지표가 나빠진 것이 아니라
**좋아졌다.** coverage 는 성능과 맞바꾸는 것이 아닐 수 있다.

## C5. 측정: surrogate 선택은 단일 backbone 에서 near-duplicate 로 붕괴한다

현재 원고 §3.3 (`docs/manuscript.md`):

- RFD3+BioEmu pool 의 surrogate 선택 Top-K: mean pairwise diversity **0.31**
- 단일 backbone surrogate 선택: **0.11** (9/9 타겟에서 더 낮음, 평균 4.2 배 차,
  paired Wilcoxon p = 0.0039)
- pool 대표 무작위 표본: 0.35 → surrogate 가 0.31 을 보존
- 선택 집합의 pLDDT (95.0 vs 96.4) 와 SoluProt (0.71 vs 0.71) 은 비슷하다

원고의 표현: 다양성은 **구조적 context 확장에서 나오고 surrogate 가 그것을
보존한 것이지 만든 것이 아니다.** 단일 backbone 에서는 surrogate 선택이 자주
near-duplicate 로 붕괴했다.

## C6. 종합

Q2 의 답: 여러 backbone 은 서로 다른 design basin 을 열기 위한
design-space diversification 장치다.

Q3 의 답: 한 backbone 안의 sequence diversity 는 그 backbone 이 정한 basin
상한 안에서만 움직인다 (C2: 5,000 서열에서 4 클러스터 포화). 같은 backbone 의
후보들은 서로 중복이고 (C4: 변이 집합 90% 중복), 선택 단계에서 near-duplicate
로 붕괴하기 쉽다 (C5: 0.11 vs 0.31). 따라서 sequence diversity 는 backbone
coverage 의 대체물이 아니라 **진단 지표**다.

---

# D. Diversity 계층 — 하나의 개념으로 합치지 않는다

## D1. 네 층

| 층 | 무엇을 재는가 | 무엇에 쓰는가 | 대체 가능? |
|---|---|---|---|
| **backbone diversity** | 서로 다른 구조적 context / design basin 의 수 | design-space diversification 의 **상위 층** | 아래 층으로 대체 불가 (C2) |
| **sequence diversity within backbone** | 같은 backbone 에서 나온 서열들의 상호 거리 | 이 backbone 이 아직 새 서열을 내고 있는지 **진단** | backbone diversity 를 대체하지 않음 |
| **cross-backbone sequence diversity** | 서로 다른 backbone 의 서열 pool 사이 거리 | backbone diversification 이 **실제로** 새 서열 공간을 여는지 확인 | — |
| **portfolio coverage** | 최종 후보군이 design space 를 얼마나 덮는가 | 최종 산출물의 성질 | 상위 개념 |

## D2. portfolio coverage 의 구성 요소

단순 `sequence_diversity` 대신 최종 상위 개념은 **design-space coverage /
portfolio coverage** 다. 최소한 다음을 구분해 담는다.

```
backbone_coverage           몇 개의 backbone 이 최종 후보군에 대표되는가
backbone_cluster_coverage   구조적으로 유사한 backbone 을 묶었을 때의 coverage
sequence_cluster_coverage   서열 클러스터 기준 coverage (C2 의 축)
cross_backbone_novelty      다른 backbone 대비 새로운 서열 클러스터 비율
redundancy                  같은 basin/클러스터의 중복 정도
```

C4 의 `per_backbone` 상한은 이 중 `backbone_coverage` 를 직접 강제한 것이고,
그 결과가 품질 개선이었다.

## D3. 금지 해석 (§16 의 명문화)

다음 두 해석은 **틀렸다.**

> ❌ "다양성을 선택하면 가장 좋은 backbone 을 골라 그 backbone 에서 서열을
> 다양하게 많이 생성한다."

C2 가 이것을 반박한다. 단일 backbone 은 서열 5,000 개에서 클러스터 4 개다.

> ❌ "backbone 은 성공률을 추정하기 위한 replicate 다."

C4/C5 가 이것을 반박한다. backbone 은 CDR geometry 와 서열 basin 을 결정한다.
replicate 라면 backbone 당 1 개 상한이 품질을 개선할 이유가 없다.

올바른 해석:

> ✅ 여러 backbone 은 서로 다른 design basin 을 탐색하기 위한 design-space
> diversification 장치이며, coverage-aware policy 는 이 여러 basin 의
> exploration 을 유지해야 한다.

---

# E. Optimization mode — objective 가 아니라 mode 다

## E1. 왜 objective 가 아닌가

"structural yield" 와 "coverage" 는 같은 축의 두 값이 아니다. 둘 다 같은
objective (structural success) 를 쓰면서 **배분 정책이 다른 것**이다. objective
로 두면 A4 의 오해가 다시 생긴다.

UX 는 다음과 같이 바꾼다.

```
Task
  Fixed-backbone protein redesign

Optimization mode
  ○ Structural-yield optimization
  ○ Design-space coverage preservation

Constraints
  □ Structural fidelity
  □ Solubility-oriented constraint

Annotations
  □ Sequence diversity      ← coverage 판단을 돕는 관측이지 상위 목표가 아니다
  □ Stability
  □ Aggregation
  □ Novelty
```

## E2. Structural-yield mode (Q4)

목적: 제한된 예산에서 structural-success 후보 수를 최대한 회수한다. frozen v1 의
과학적 질문과 같다.

**언제 유망 backbone 에 계산을 더 배분할 수 있는가 (Q4):**

전향 검증이 이 질문에 수치로 답한다. `39_prospective_allocation_validation.py`
결과에서 적응 배분의 이득은 **예산 상한 23 미만에서 0** 이고, 그 지점이
`MIN_PROBE_SEQUENCES(4) × backbone 5 개 = 20` 이라는 probe 바닥과 일치한다.

```
조건 1  모든 arm 이 최소 probe (v1: 4 관측) 를 채웠다
조건 2  남은 예산이 probe 바닥을 초과한다
조건 3  arm 간 사후 평균 차이가 사후 불확실성 대비 의미 있다
```

세 조건이 충족된 뒤에야 exploitation 비중을 올린다. 이것은 v1 이 이미 하고 있는
동작이고, v2 는 그것을 mode 로 명시할 뿐이다.

## E3. Coverage-preserving mode (Q5)

목적: 여러 backbone 이 제공하는 design basin 을 충분히 탐색하고, 특정 backbone
으로 계산이 붕괴해 전체 탐색 공간이 축소되지 않게 한다.

**계산 붕괴를 어떻게 막는가 (Q5):** 세 가지 장치를 함께 쓴다. 하나만으로는
부족하다.

### (a) coverage floor — 하한을 정책으로 둔다

```
minimum_probe_per_arm            각 arm 이 관측 없이 버려지지 않게
minimum_probe_per_arm_cluster    구조적으로 묶인 backbone 군 단위
minimum_arms_retained            동시에 살아 있어야 하는 arm 수 하한
```

이 하한을 만족하기 전에는 `abandon_arm` 을 금지한다. **structural success 만으로
arm 을 제거하지 않는다** (§17).

### (b) coverage 항을 acquisition 에 넣되 batch 항과 구분한다

A5 에서 확인했듯 v1 의 `_diversity_term` 은 batch 내 벌점이고 누적 상태가
아니다. 별도의 누적 항을 둔다.

```
batch_redundancy        (기존) 이번 배치 안에서 같은 arm 을 겹쳐 고르는 것
portfolio_redundancy    (신규) 지금까지 확보한 portfolio 와의 중복
```

### (c) 산출 단계 coverage 상한

C4 의 `per_backbone` 상한이 여기 해당한다. 배분 정책과 별개로, **최종 후보군을
낼 때** backbone 당 상한을 걸어 portfolio coverage 를 강제한다. 이것은 이미
Antigen 에서 측정된 효과가 있는 장치다.

## E4. 두 mode 의 관계

mode 는 **같은 Core 에 서로 다른 제약과 가중을 주는 것**이지 다른 알고리즘이
아니다. structural-yield mode 는 coverage floor 를 최소값으로 두고 exploitation
비중을 높이며, coverage-preserving mode 는 floor 를 높이고 portfolio_redundancy
가중을 높인다. 두 mode 가 같은 코드 경로를 쓴다는 것이 테스트 대상이다.

---

# F. v2.0 이 할 수 있는 것과 없는 것 (Q6, Q7)

## F1. 구분 (Q6)

```
coverage preservation  (v2.0)
  이미 주어진 arm pool 안에서 여러 basin 의 exploration 을 유지한다.
  pool 은 실행 시작 시점에 고정된다.

diversity expansion    (v2.x)
  현재 pool 에 없는 basin 을 열기 위해 backbone 자체를 새로 만든다.
  pool 이 실행 중 늘어난다.
```

두 개는 다른 능력이다. 전자는 배분 문제이고 후자는 생성 문제다.

## F2. v2.0 을 무엇이라 부르지 않는가 (Q7)

다음 이름을 쓰지 않는다.

```
❌ arbitrary diversity maximizer
❌ full design-space optimizer
❌ full multi-objective optimizer
```

v2.0 이 새 backbone 을 만들지 못하는 한, 도달 가능한 design space 의 상한은
입력 pool 이 정한다. pool 이 basin 3 개만 담고 있으면 v2.0 이 아무리 잘
배분해도 basin 3 개다. "design space 를 최적화한다" 는 말은 그 상한을 감춘다.

정확한 이름:

> **diversity/coverage-aware allocation over an existing design-arm pool**

## F3. 주장 문구 (Invariant 4 의 집행)

v2.0 결과를 보고할 때 쓸 수 있는 문장:

> 주어진 backbone pool 에서 coverage-preserving 배분은 균등/탐욕 배분 대비
> portfolio 의 backbone coverage 를 X% 높게 유지했다.

쓸 수 없는 문장:

> RAPID 가 backbone diversity 를 확장했다.

후자는 `generate_new_backbone` 이 실제로 구현되고 그 효과가 측정된 뒤에만
가능하다.

---

# G. `generate_new_backbone` 을 위한 interface (Q8)

v2.0 구현 범위에는 넣지 않는다. **contract 만 설계한다.**

## G1. action 집합의 확장

```
generate_more_sequences        같은 arm 에서 서열을 더
explore_existing_arm           덜 탐색된 기존 arm 을
explore_generation_condition   같은 backbone 을 다른 조건으로
generate_new_backbone          새 basin 을 여는 arm 을 만든다      ← v2.x
evaluate_at_higher_fidelity    같은 arm 을 더 비싼 채널로         ← v2.1
abandon_arm                    이 arm 을 그만둔다
```

## G2. 그 action 이 성립하려면 필요한 것

```
1. pool 확장 가능성
   TaskProfile 이 "이 task 에서 새 arm 을 만들 수 있는가" 와 그 비용을 선언한다.
   fixed-backbone redesign 은 RFD3 재호출로 가능하고, maturation arm 은
   backbone generator 가 없으므로 불가능하다.

2. 포화 신호
   "현재 pool 이 더 줄 것이 없다" 를 판정할 상태. §H 의 diminishing-return
   신호를 arm 단위가 아니라 pool 단위로 집계한 것.

3. 신규 arm 의 사전분포
   아직 관측이 없는 새 arm 을 어떻게 시작할 것인가. Gate 0 사전분포가 있으면
   그것을, 없으면 형제 arm 의 부분 풀링에서 가져온다. 이 선택은 측정이 필요하다.

4. 비용 비교 가능성
   "서열 1 개 더" 와 "backbone 1 개 더" 는 비용 단위가 다르다. 같은 축에서
   비교하려면 두 action 의 비용이 같은 단위로 측정돼 있어야 한다. 현재 RFD3
   backbone 생성 비용은 측정돼 있지 않다.

5. coverage 이득 추정
   새 backbone 이 실제로 새 basin 을 열 확률. C2 의 클러스터 곡선이 이 추정의
   출발점이 될 수 있지만, 사전에 알 수 없는 값이다.
```

**4 와 5 는 현재 데이터로 채울 수 없다.** 그래서 v2.0 은 interface 만 둔다.

---

# H. 같은 backbone 에서 서열을 더 뽑을 때의 diminishing return (Q9)

## H1. 표현 가능한 신호

```
sequence_cluster_saturation   이 arm 의 누적 고유 클러스터 수가 평평해졌는가
new_cluster_probability       다음 서열이 새 클러스터일 확률
within_arm_redundancy         이 arm 후보들의 상호 identity
marginal_candidate_yield      최근 k 개 관측에서 제약 통과 후보가 나온 비율
```

## H2. C2 가 이 신호의 형태를 알려준다

단일 backbone 클러스터 수 1.3 → 1.5 → 2.7 → 4.0 (N = 10 → 5,000). 로그에
가까운 포화 곡선이고, **N 을 500 배 늘려 클러스터가 1.5 개 늘었다.** 즉
`new_cluster_probability` 는 급격히 0 으로 간다.

## H3. 주의

이 신호는 **backbone diversity 를 대신하지 않는다.** arm 하나가 포화했다는 것은
"이 arm 에서 서열을 더 뽑는 가치가 낮다" 는 뜻이지 "이 arm 을 버려도 된다" 가
아니다. 포화한 arm 도 자기 basin 의 대표로서 portfolio coverage 에 기여한다.
C4 에서 backbone 당 1 개만 남겨도 coverage 가 유지된 것이 그 예다.

따라서 포화 신호는 `generate_more_sequences` 의 가치를 낮출 뿐,
`abandon_arm` 을 촉발하지 않는다. 두 결정을 분리한다.

---

# I. 전체 architecture

```
DesignRequest
    ├─ task_profile
    ├─ biological inputs
    ├─ optimization_mode
    ├─ objectives (primary / constraints / secondary / annotations)
    └─ compute / experimental budget
            ↓
      TaskProfile Resolver          ← 기존 registry `purposes` 의 확장
            ↓
      Task-specific Pipeline        ← RAPID 이 대체하지 않는 부분
            ├─ input validation      · design-space construction
            ├─ DesignArm construction · generators
            ├─ evaluators             · constraints
            ├─ coverage semantics     · fidelity hierarchy
            └─ allowed actions
            ↓
      EvaluationResult              ← raw measurement 보존
            ↓
      ScoreTransform (versioned)    ← objective 별 해석
            ↓
      ObservationModel              ← arm 상태 갱신
            ↓
      RAPID Core                    ← 모델 이름 없음
            ↓
      NextAction
            ↓
      Task-specific executor  ──feedback──→ RAPID Core
```

## I1. TaskProfile 은 기존 `purposes` 를 확장한다 — 평행 체계를 만들지 않는다

§21 의 "새로운 평행 ObjectiveSpec 을 만들지 않는다" 를 TaskProfile 에도 적용한다.
`MODEL_REGISTRY_V1.yaml` 의 `purposes` 는 이미 다음을 갖고 있다.

```yaml
purposes:
  monomer_solubility_redesign:
    objectives: [solubility, structural_preservation, diversity]   # 허용 objective
    stages: [...]                                                   # pipeline stage
    cost_driver: colabfold
    validation_coverage: {...}
  antibody_design:
    objectives: [binding, developability]
    stages: [...]
    referral: "...route it to the antigen pipeline's ROUTER_POLICY_V1.1..."
```

TaskProfile 은 이 구조에 다음을 **추가**하는 것이다. 새 파일이나 새 개념 이름을
만들지 않는다.

```yaml
    design_arm_schema:          # 이 task 의 반복 단위 (§J)
    available_optimization_modes:
    coverage_semantics:         # 무엇을 coverage 로 셀 것인가 (§D2)
    minimum_exploration_policy: # coverage floor (§E3a)
    allowed_actions:            # §G1 중 이 task 가 허용하는 것
    fidelity_structure:         # 기존 fidelity_ladder 를 task 별로
    scientific_permissions:     # §M
    artifact_contract:
```

`purpose` 필드는 `Objective` 에 이미 있고 `load_registry().route()` 로 검증된다.
그 검증 지점이 TaskProfile 검증 지점이 된다.

---

# J. DesignArm — generic abstraction (Q12 준비)

## J1. arm 은 task 가 정의한다

```
DesignArm
  arm_id            안정적 식별자
  task_profile      어느 task 의 arm 인가
  dimensions        {이름: 값}   ← schema 는 TaskProfile 이 정한다
  cost_hint         한 번 관측하는 비용 (없으면 None, 0 아님)
  coverage_key      이 arm 이 어느 coverage 축에 기여하는가
```

`dimensions` 를 열어 두는 것이 핵심이다. Core 는 arm 을 불투명 식별자와
coverage_key 로만 다룬다.

## J2. fixed_backbone_redesign 의 arm — v1 과 동일

```
dimensions = {backbone, generation_condition}
coverage_key = backbone (또는 backbone_cluster)
```

frozen v1 의 정의 그대로다. `rapid_structural_v1` 프로파일은 이 schema 로
재현된다.

## J3. fidelity 는 arm 이 아니다 (§29 유지)

이전 판본 §10.4 를 그대로 유지한다. 같은 arm 을 여러 fidelity 채널이 관측한다.

```
arm → observations_by_fidelity → CrossFidelityLink → allocator
```

evaluator 이름을 arm identity 에 넣지 않는다. 넣으면 arm 수가 fidelity 배로
늘고, 같은 backbone 의 두 관측이 서로 정보를 주지 않는 별개 arm 이 된다.

## J4. calibration 없는 fidelity 혼합 금지 (§30 유지)

`CrossFidelityLink` (= `PromotionModel`) 가 paired data 로 검증된 경우에만
low-fidelity 관측이 high-fidelity 결정에 영향을 준다. 그 전에는 annotation
전용이다. 현재 ESMFold 는 registry 에서 `wired_unvalidated · 비용 미측정 ·
호출하는 곳 없음` 이다.

---

# K. Objective 는 TaskProfile 안에서만 유효하다 (Q11)

## K1. 왜 evaluator 하나를 붙이는 것으로 끝나지 않는가

```
TaskProfile: fixed_backbone_redesign
Objective:   binding_affinity
```

이 조합에서 PPIformer 를 자동 연결하지 않는 이유는 세 가지다. **평가자가 없어서
가 아니다** - PPIformer 는 붙어 있고 워커도 살아 있다.

```
1. 입력이 없다
   fixed_backbone_redesign 의 design space 에는 파트너 사슬이 없다. 결합
   ddG 는 복합체에서 정의되는 값이고, 단량체 재설계 요청에는 그 복합체가
   존재하지 않는다.

2. 생성 단계가 다르다
   binder/antibody 경로는 registry 에서 이미 stage 구성이 다르다 -
   interface_screen 과 interface_score 두 stage 가 추가된다. objective 만
   바꾼다고 그 stage 가 생기지 않는다.

3. Gate 0 사전분포가 그 목적에 대해 측정된 적이 없다
   registry 의 protein_binder_design.caveat 가 이것을 적어 두었다:
   "Gate 0's AUC was measured on MONOMER structural yield. Whether the same
   encoder representation routes binder targets is untested."
```

## K2. 실패 방식

조용히 무시하거나 근사하지 않고 실패한다.

```
binding_affinity is not supported by fixed_backbone_redesign.
  reason: this task's design space has no partner chain.
  required: a binder/antibody-compatible TaskProfile.
  see: purposes.protein_binder_design, purposes.antibody_design
```

이 동작은 이미 부분적으로 존재한다. `Objective.unsupported()` 와
`wired_but_unvalidated()` 가 registry 를 읽어 목록을 만들고, 가중치를 받아놓고
조용히 무시하지 않는다. v2 는 이것을 **task 별로** 만든다 - 현재는 전역
`measurable_objectives()` 라서 "이 task 에서 의미가 있는가" 를 묻지 않는다.

## K3. 실패는 크게 낸다 (이전 판본 §6 유지)

다음은 대체하지 않고 실패한다.

```
이 task 에서 의미가 없는 objective          ← v2 에서 추가된 항목
objective 에 맞는 evaluator 가 없음
required input 이 없음
evaluator 가 해당 role 로 허가되지 않음
score direction 을 알 수 없음
reference-relative score 가 정의되지 않음
model service unavailable
```

유사한 evaluator 로 자동 대체하지 않는다.

```
Requested objective: catalytic activity
No evaluator permitted for catalytic activity allocation.
  ppiformer_ddg   binding_affinity 에만 허가됨
  rosetta_relax   annotation 으로만 허가됨
활성은 타겟마다 다른 assay 로 정의되므로 assay 라벨 없이는 평가자를 붙일 수 없다.
```

첫 줄이 v2 에서 추가됐다. 이전 판본은 "evaluator 가 있는가" 만 물었고, "이
task 에서 그 목적이 성립하는가" 는 묻지 않았다 (A2).

## K4. Objective 구조는 확장한다

```
DesignRequest
  task_profile          (기존 purpose 확장)
  optimization_mode     (신규)
  primary               objective 이름
  constraints[]         hard
  secondary[]           soft
  annotations[]         기록만
  budget
```

TaskProfile 이 검증하는 것:

```
이 objective 가 이 task 에서 의미가 있는가      purposes[task].objectives
필수 입력이 있는가                              required_inputs
평가자가 존재하는가                             models
그 역할로 과학적으로 허용되는가                  scientific_permissions
```

기존 `weights`/`constraints` 이분법은 유지한다 (soft vs hard). `annotations` 는
weights 에 들어가면 안 되는 것들을 담는 자리다 - 현재 diversity 가 weights 에
들어갈 수 있는 것이 A3 의 원인 중 하나다.

---

# L. Evaluator, EvaluationResult, ScoreTransform

## L1. Evaluator 는 raw measurement 를 낸다

pLDDT, RMSD, ΔΔG, ipSAE, REU, SoluProt score 를 그대로 돌려준다. evaluator 안에서
0–1 success probability 로 바꾸지 않는다. 그 변환은 objective 에 따라 다르고,
evaluator 는 objective 를 모른다.

## L2. `EvaluationResult` contract

```
evaluator          누가 쟀는가
objective          무엇을 위해 쟀는가
raw_value          단위가 붙은 원값
unit
direction          higher_is_better / lower_is_better
validity           계산이 성립했는가 (거부도 값이다)
uncertainty        있으면
reference          무엇에 대한 값인가 (예: 이 backbone 자신의 PDB)
fidelity           채널 등급
provenance         모델 버전, 설정, 코드 sha
artifact           산출물 경로/해시
failure_reason     실패했으면 왜
```

`validity` 와 `failure_reason` 이 first-class 인 이유는 이번 캠페인에서 세 번
같은 실패를 겪었기 때문이다 - 동결 지표가 대응을 거부한 48 행, ThermoMPNN 의
예외 타입만 남고 메시지가 사라진 8 건, DiffDock 이 pose 를 안 냈는데 22/22 ok
로 기록된 것. **"값이 없다" 와 "실패했다" 와 "거부했다" 는 서로 다른 상태다.**

## L3. `ScoreTransform` (이전 §10.1 유지)

```
Evaluator → raw EvaluationResult → versioned ScoreTransform → objective 해석
```

registry 가 관리하는 것:

```
TaskProfile × evaluator × objective × allowed_role × ScoreTransform
```

`TaskProfile` 이 키에 추가된 것이 이전 판본과의 차이다. 같은 evaluator 가 같은
objective 를 재더라도 task 가 다르면 해석과 허용 역할이 다를 수 있다.

모든 점수를 억지로 0–1 로 만들지 않는다.

---

# M. 운영 상태와 과학적 허가는 분리한다 (이전 §1 유지, 확장)

| 축 | 질문 | 값 |
|---|---|---|
| operational | 지금 실행할 수 있는가 | installed · service_alive · wired |
| scientific | 이 목적에 써도 되는가 | computed · annotation · ranking · gate · allocation · wet_validated |

두 축은 독립이다. PPIformer 는 `service_alive: true` 이면서
`allocation: false` 다. 실재하는 조합이고 한 값으로 합치면 표현할 수 없다.

`computed` 를 별도 값으로 두는 이유: "숫자가 나온다" 는 "그 숫자를 쓸 수 있다"
가 아니다. 이번 캠페인에서 aggregation 항목에 `status: measured` 를 적었다가
"수를 계산한다" 와 "objective 가 측정됐다" 를 혼동한 것이 테스트에 걸렸다.

`wet_validated` 는 현재 어떤 evaluator 에도 붙어 있지 않다.

---

# N. ObservationModel (이전 §2 유지)

```
AllocationObservationModel          interface
  ├ BetaBernoulliState              v1 이 쓰는 것. 이진 결과.
  ├ ContinuousState                 연속 endpoint. 파라미터 미확정.
  └ MultiObjectiveState             future
```

v1 대응:

```
expected_utility  = posterior mean
uncertainty       = posterior SD
allocation_signal = movability = 4p(1−p)
```

`movability` 를 information gain 이라고 부르지 않는다. n 에 무관하고 (2/4 와
200/400 이 같은 값), 그 사실이 golden test 로 고정돼 있다
(`test_movability_does_not_decay_with_more_observations`).

## N1. 연속 결과의 pooling 은 확정하지 않는다 (이전 §10.2 유지)

Beta 의 `pooling_strength=4.0` 을 연속 objective 에 복사하지 않는다. 계층
구조 (target → arm) 만 contract 로 두고, 통계 모형과 hyperparameter 는
objective/evaluator 별 데이터가 확보된 뒤 추정하고 freeze 한다.

---

# O. RAPID Core 와 acquisition

## O1. expected marginal utility 는 상위 abstraction 으로만 둔다 (§45)

고려 가능한 요소:

```
expected objective value
constraint satisfaction probability
uncertainty
exploration value
backbone / design-basin coverage
sequence-cluster novelty
redundancy (batch / portfolio 구분)
diminishing returns
compute cost
```

**근거 없이 하나의 weighted sum 을 확정하지 않는다.** 특히 기존 식에
`+ γ·sequence_diversity_bonus` 하나를 더하고 diversity-aware 라고 부르지
않는다 - 그것이 정확히 A4/D3 의 오해를 코드로 옮기는 형태다.

## O2. v1 환원 (Invariant 6 준비, Q16 의 일부)

v2 식이 v1 식으로 환원되는 것을 테스트로 고정한다. 이진 objective 에서
`q = p̂` 이므로 `4q(1−q) = movability` 이고, coverage 항의 가중을 0 으로 두면
v1 acquisition 과 같아야 한다.

```
v1  A = p̂ + β·U − λ·C − γ·D_batch + η·(movability × 조건 불확실성)
v2  A = expected_utility + β·uncertainty + η·allocation_signal
        − λ·cost − γ·batch_redundancy − δ·portfolio_redundancy
    (δ = 0, 이진 objective, 단일 fidelity → v1 과 동일)
```

## O3. RAPID v2 의 목적 서술 (§44)

쓰지 않는다:

> ❌ RAPID 은 가장 성공률 높은 backbone 을 찾아 그 backbone 에 집중한다.

쓴다:

> ✅ RAPID 은 각 DesignArm 의 예상 성과뿐 아니라 탐색 상태, design-space
> coverage, 중복, 불확실성, 계산비용을 함께 고려해 다음 계산을 배분한다.

---

# P. AF2 structural success 와 biological success (Q10)

v1 의 structural success 는 한정된 operational endpoint 다.

```
pLDDT ≥ 85  AND  reference-backbone non-loop RMSD ≤ 2.0 Å
→ "이 서열이 의도한 backbone 을 형성할 것으로 예측되는가"
```

이것은 다음과 **같지 않다**: function, binding affinity, enzyme activity,
stability, expression, actual solubility, wet-lab success.

세 임계값은 캠페인 이전에 정해졌고 (`THRESHOLD_PROVENANCE`) 셋 다
`convention_without_internal_calibration` 이다. 관례로 쓴 값이지 내부 보정
결과가 아니다.

v2 에서 AF2/AF3 같은 evaluator 는 TaskProfile 과 objective 에 따라 다음 중
하나의 역할을 갖는다: primary objective evaluator · hard constraint ·
feasibility evaluator · secondary evaluator · annotation.

**어떤 evaluator 도 universal success oracle 이 아니다.**

---

# AG. AntigenTaskProfile — 실제 구현을 먼저 기록한다

> 이 절의 소제목은 `AG1..AG9` 다. 과제 지시의 질문 번호 `Q1..Q16` 과
> 섞이지 않게 다른 접두사를 쓴다.

이 절은 `/opt/antigen_pipeline` 의 실제 코드와 문서를 조사해서 쓴 것이다.
상상한 pipeline 이 아니다. 문서와 구현이 다르면 구현을 적었다.

## AG1. 무엇을 그대로 유지하는가

```
antigen.kbiofoundry.kr 서비스        유지
Antigen UI                          변경 없음
Antigen backend / scientific pipeline 변경 없음
ROUTER_POLICY_V1.1                   변경 없음 (frozen, evidence_id P53)
IMGT / CDR / framework 마스크 로직    Antigen 에 남는다
```

하지 않는 것: Antigen 삭제, RAPID 로의 병합, fixed-backbone pipeline 으로의
변환, Antigen-specific biology 를 Core 로 이동 (Invariant 5).

RAPID 은 Antigen 의 **결정 지점 하나** - 비싼 계산을 어디에 쓸 것인가 - 만
가져간다.

## AG2. Antigen 의 두 arm 은 routing arm 이지 allocation arm 이 아니다

`docs/routing/ANTIBODY_DESIGN_ARMS.md` 와
`pipeline_mcp/antibody_arm.py::resolve_arm` 이 정의하는 두 arm:

| | `maturation` | `interface_redesign` |
|---|---|---|
| 목적 | 존재하는 항체 주변 저변이 최적화 | 같은 에피토프 주변 넓은 탐색 |
| backbone generator | 없음 (`rfd3_use=false`) | RFD3 partial diffusion (`partial_t` 5.0) |
| backbone-designable | — | CDR / local loop + 승인된 contact framework |
| sequence expert | `proteinmpnn` (`v_48_020` soluble) | `antifold` |
| sequence-designable | IMGT CDR only | CDR + 승인된 contact framework |
| 변이 상한 | `antibody_max_mutations` (기본 6) | 없음 |

**중요**: 이 arm 은 요청당 한 번 `resolve_arm` 이 규칙으로 정하는
**design-policy 선택**이다. 배분 정책이 반복적으로 고르는 단위가 아니다.
그러므로 이것을 그대로 RAPID 의 DesignArm 이라고 부르면 틀린다 (§34 의 경고가
정확했다).

두 designable 집합이 **따로** 결정된다는 점도 기록한다 - 어느 잔기를 다시
접을 수 있는가와 어느 잔기를 다시 쓸 수 있는가는 다른 질문이다.

## AG3. Antigen 의 실제 계산 배분 지점 (Q12 의 답)

실행 구조를 따라가면 배분이 일어나는 곳은 다음이다.

```
RFD3 partial diffusion
   → backbone N 개                    (antifold-r6..r8 타겟에서 200 개)
       ↓  각 backbone 마다 AntiFold 설계
   → candidate 다수                   (r8: 1,894 후보)
       ↓  PPIformer ddG 스크리닝       (antibody_affinity_max_ddg, top_k)
   → 적격 pool
       ↓  surrogate triage (선택)      (antibody_surrogate_triage_enabled)
   → shortlist
       ↓  AF3 co-fold                 ← 비싼 자원. 예산 = antibody_affinity_top_k
   → interface metrics (ipSAE 등) + preservation gate
       ↓  export_sequences(per_backbone)
   → wet 후보
```

따라서:

```
비싼 자원        AF3 co-fold 호출 (cost_driver: alphafold3)
배분 단위 후보   RFD3 backbone  ← coverage 축이 여기다
관측 단위        candidate (backbone 하나에 여러 개)
```

**AntigenTaskProfile 의 DesignArm 은 RFD3 backbone 으로 두는 것이 현재
구현과 맞는다.** 근거:

- `export_sequences(per_backbone)` 가 이미 backbone 을 coverage 축으로 쓴다.
- 같은 backbone 의 후보는 CDR geometry 를 공유하고 변이 집합이 90% 겹친다
  (C4). 즉 backbone 안에서는 후보들이 서로 교환 가능에 가깝다.
- backbone 은 200 개 규모이고 co-fold 예산은 그보다 작다 (schema 기본값
  `antibody_affinity_top_k = 20`, antifold-r6 실행은 400 을 썼다). 후보가 예산을
  넘으므로 배분이 실제 문제다.

`generation_condition` 축은 Antigen 에서 arm 차원이 **아니다** - AntiFold 는
seed 를 그대로 받고, 커밋 `e064f1c` 가 확인했듯 같은 backbone·같은 mask 에서
200/200 이 byte-identical 서열을 냈다. 조건을 바꾸지 않으면 새로 줄 것이 없다.
이것은 fixed_backbone_redesign 과 다른 점이고, arm schema 를 task 가 정해야
하는 이유의 실례다 (A1).

**미확정**: backbone 을 구조 유사도로 묶은 cluster 를 coverage 축으로 쓸지,
개별 backbone 을 쓸지는 측정이 필요하다. 200 개 중 몇 개가 실제로 서로 다른
basin 인지 재본 적이 없다.

## AG4. Antigen evaluator 의 현재 과학적 허가 (Q13)

**측정된 사실부터.** `pipeline_mcp/models.py` 의
`selection_independent_annotations` 주석:

> ddG, ipSAE 와 preservation 지표는 모두 계산·기록되지만 아무도 탈락시키지
> 않는다. 각 신호의 전향적 예측력을 wet 결과에 대해 재기 위한 것이다 —
> **이 pipeline 자신의 데이터에서 ddG 순위는 어떤 후보가 구조 검증을
> 통과하는지 예측하지 못했다.**

이것은 부정 결과이고, 그래서 `antibody_affinity_annotate_only` 라는 별도
스위치가 존재한다 (ddG 만 annotate-only 로 돌리고 나머지 게이트는 유지).

현재 허가:

| evaluator | computed | annotation | ranking | gate | allocation | wet_validated |
|---|---|---|---|---|---|---|
| PPIformer ddG | ✅ | ✅ | ⚠️ 운영상 사용 중 (`antibody_affinity_max_ddg`), 예측력 부정 결과 있음 | ⚠️ 현재 hard gate 지만 근거 약함 | ❌ | ❌ |
| AF3 co-fold 구조 | ✅ | ✅ | ✅ | ✅ (preservation gate) | ❌ | ❌ |
| ipSAE | ✅ | ✅ | ✅ | ✅ (`binder_score_cutoff`) | ❌ | ❌ |
| ipTM / pDockQ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| contact retention | ✅ | ✅ | ✅ | ✅ (`antibody_contact_retention_cutoff`) | ❌ | ❌ |
| framework / CDR RMSD | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |

RAPID 쪽 registry 도 같은 말을 한다: `binding.status = evaluator_unvalidated`,
"RAPID 가 어떤 결합 라벨에도 맞춰본 적이 없어서 검증되지 않았다."

**결론: 현재 allocation reward 로 쓸 수 있는 Antigen evaluator 는 없다.**
사용자가 UI 에서 골랐다는 이유로 allocation 으로 승격하지 않는다 (Invariant 6).

`selection_independent_annotations` 같은 상태는 first-class permission 으로
표현한다 - "계산하고 기록하지만 아무도 탈락시키지 않는다" 는 `computed +
annotation` 이고 `gate` 가 아니다.

## AG5. 그러면 v2.0 에서 Antigen 은 무엇으로 배분하는가

allocation reward 로 쓸 evaluator 가 없다는 것이 배분을 못 한다는 뜻은 아니다.
**coverage-preserving mode 는 성과 추정 없이도 정의된다.**

```
가능      backbone coverage 를 유지하도록 AF3 예산을 배분한다
          (C4 의 per_backbone 상한이 이미 이 방향이고 효과가 측정됐다)
가능      최소 exploration 을 강제한다
불가      "이 backbone 이 결합을 더 잘 만든다" 를 근거로 exploitation
```

즉 AntigenTaskProfile 의 v2.0 진입점은 **structural-yield mode 가 아니라
coverage-preserving mode** 다. 이것이 Antigen 을 첫 flagship 으로 삼을 때
정직하게 말할 수 있는 범위다.

## AG6. 이미 측정된 exploration 하한 (§14 의 숫자 근거)

`antibody_surrogate_triage_initial_samples` 주석이 측정값을 담고 있다.

> 예산의 몫으로 크기를 정한다. probe 의 co-fold 도 `antibody_affinity_top_k`
> 에서 나가므로 여기 쓴 후보는 surrogate 가 고르지 못한다 — 그러나 probe 가
> 너무 작으면 아무것도 배우지 못한다. **antifold-r6 의 실제 co-fold 400 회에
> 대해 (그 실행 자신의 라벨로 예산 제한 선택을 20 seed 재생) 수율은 예산의
> 대략 25–35% 에서 정점이고, r6 자신의 35/400 = 9% 는 그보다 한참 아래였으며,
> 65% 는 surrogate 를 안 쓰는 것과 같았다.**

(여기서 400 은 `antibody_affinity_top_k` 의 schema 기본값 20 이 아니라 r6 실행이
실제로 쓴 예산이다. 비율 25–35% 는 그 400 에 대해 측정됐다.)

**이것은 v1 의 `MIN_PROBE_SEQUENCES = 4` 와 같은 종류의 값이 다른 pipeline 에서
독립적으로 측정된 것이다.** v1 의 전향 검증에서 적응 배분의 이득이 예산 상한
23 부터 나타났고 probe 바닥이 20 (= 4 × 5) 이었던 것과 방향이 같다: **예산의
상당 부분을 exploration 에 먼저 쓰지 않으면 배분이 이득을 내지 못한다.**

두 값을 같은 수치라고 주장하지 않는다. 단위도 pipeline 도 다르다. 다만
`minimum_exploration_policy` 를 임의로 정하지 말고 task 별로 측정해서 넣어야
한다는 근거가 두 곳에 있다.

## AG7. 서비스 동작 보존 (Q15)

```
Antigen 은 RAPID 없이도 지금처럼 동작한다.   ← 기본 경로. 회귀 없음.
RAPID adapter 는 opt-in 이다.
adapter 가 없거나 실패하면 기존 배분으로 되돌아간다 (fail-open).
```

adapter 경계:

```
Antigen  →  ArmState 목록 + 비용 + coverage_key  →  RAPID Core
RAPID    →  NextAction (어느 arm 에 co-fold 를 쓸 것인가)  →  Antigen executor
```

Antigen 은 IMGT, CDR, mask, RFD3 설정, AntiFold 호출을 계속 자기가 한다.
RAPID 은 그중 어느 것도 모른다.

## AG8. Wet 결과 연결 (Q14)

Antigen 은 실제 wet validation 이 예정돼 있다. 준비할 것은 **저장과 연결
interface 뿐**이고, closed loop 는 v2.0 범위가 아니다 (§39).

```
WetOutcome
  candidate_id       계산 후보와 잇는 키
  arm_id             어느 backbone 에서 나왔는가
  assay              무엇을 쟀는가
  raw_value / unit
  outcome_class      binding / expression / developability ...
  measured_utc
  provenance
```

계산 관측과 wet 결과를 **하나의 `success` 로 합치지 않는다** (§37).

향후 이 데이터로 답할 질문:

```
PPIformer ddG        ↔ wet binding
AF3 interface 지표    ↔ wet binding
ipSAE                ↔ wet binding
구조 보존 지표         ↔ 실험 성공
```

그 결과로 각 evaluator 를 annotation / ranking / gate / allocation 중 어디까지
올릴지 **다시 결정한다** (§38). 현재 ddG 의 부정 결과 (AG4) 가 그 재평가가
필요한 이유의 실례다.

## AG9. 향후 검증 질문 (§36)

> 같은 computational budget 과 experimental budget 에서 adaptive RAPID
> allocation 이 static allocation 보다 실제 wet hit 를 더 효율적으로
> 회수하는가?

**wet 결과가 나오기 전에는 주장하지 않는다.** Antigen 을 현재 RAPID 논문의
검증 결과에 포함하지 않는다 (§48).

---

# R. FixedBackboneRedesign 과 Antigen 의 관계

```
                      RAPID Core
                     /          \
   FixedBackboneRedesign      AntigenTaskProfile
            │                        │
   multiple RFD3 backbones     RFD3 partial diffusion (~200)
   ProteinMPNN                 AntiFold / ProteinMPNN (arm 별)
   SoluProt constraint         PPIformer ddG screen
   AF2/ColabFold 검증           AF3 co-fold + interface metrics
   backbone coverage           backbone coverage
   arm = backbone × condition  arm = backbone
   mode: yield / coverage      mode: coverage (현재)
                               wet export
```

공통은 adaptive compute-allocation mechanism 하나다. scientific workflow 는
공유하지 않는다.

---

# S. frozen v1 을 하나의 정확한 프로파일로 보존한다 (Q16)

## S1. 표현

```
TaskProfile:   fixed_backbone_redesign
PolicyProfile: rapid_structural_v1
```

이 조합은 frozen v1 과 **동일한 결과를 재현해야 한다.**

## S2. 어떻게 검증하는가

이미 있는 것:

```
pipeline-mcp/tests/test_allocation_v1_golden.py   31 개. 상수, 사후 산술,
    부분 풀링, 4-way 경계, acquisition 순위, leakage guard, 6-step 행동/상태
    시퀀스를 값으로 고정.
public_data/benchmark/gate0/RAPID_STRUCTURAL_V1_FREEZE.json   26 개 파일 SHA256
pipeline-mcp/tests/test_v1_freeze.py   해시 일치 + 커밋 상태 + 코호트 형태
tag rapid_structural_v1
```

v2 작업 중 추가할 것:

```
1. golden test 는 v2 작업 내내 통과해야 한다. 통과하는 동안만 리팩터링한다.
2. 환원 테스트: v2 Core 를 rapid_structural_v1 프로파일로 돌리면 v1 과
   같은 행동 시퀀스와 같은 사후값이 나와야 한다 (§O2).
3. 해시 테스트: v2 작업이 v1 산출물을 건드리면 test_v1_freeze 가 깨진다.
4. `scripts/transcoder/rapid_sr/allocation.py` 와
   `pipeline-mcp/src/pipeline_mcp/allocation.py` 는 v2 작업 중 수정하지
   않는다. 논문 분석이 전자를 쓰고 golden test 가 둘을 묶는다.
```

## S3. 소급 적용 금지

v2 의 coverage 개념을 v1 frozen result 에 소급 적용하지 않는다. v1 은
structural-yield mode 만 검증했고, coverage 지표를 v1 결과에 덧붙여 계산해서
"v1 도 coverage 를 유지했다" 고 적지 않는다. 그것은 사후 분석이지 검증이 아니다.

v1 결과와 v2 결과를 같은 표에 섞지 않는다. 프로파일 이름이 결과마다 붙는다.

---

# SS. Coverage-preserving mode 의 endpoint — 확정

§X8 이 열어 두었던 질문에 대한 결정이다. 이 절이 확정되면 coverage mode 도
v1 처럼 사전등록 가능한 검증 대상이 된다.

## SS1. Primary endpoint family

```
Feasible Coverage @ Fixed Budget       (FC@B)
```

`coverage_unit` 이 무엇인지는 TaskProfile 이 정한다. fixed_backbone_redesign
에서는 `backbone_id` 로 동결했다 (SS3).

### 용어 — "basin" 과 "coverage unit" 을 구분한다

M1 이 잰 것은 **backbone 이 하나의 진짜 basin 이다** 가 아니라,
**이 코호트에서는 여러 backbone 을 더 큰 단위로 묶을 안정적이고 비자명한
structural scale 을 찾지 못했다** 는 것이다. 이 둘은 다르다.

```
여러 backbone 을 만드는 목적            서로 다른 design basin 탐색
                                        (§C2 의 측정이 지지한다)

coverage 를 세는 단위                   coverage_unit = backbone_id
                                        (운영 정의. basin 과 같다고 주장하지 않는다)
```

따라서 문서와 보고에서 쓰는 표현:

```
✅ backbone-level design-space coverage
✅ design-context coverage
✅ feasible backbone coverage
⚠️ design-basin coverage    ← 동기를 말할 때만. 지표 이름으로는 쓰지 않는다.
```

정의:

```
coverage_unit   arm pool 의 분할 단위. TaskProfile 이 정한다.

feasible     그 basin 에서 나온 후보 중 적어도 하나가 feasibility 기준을
covered      통과했다. 기준은 task 의 primary feasibility endpoint 를 쓴다
             (fixed_backbone_redesign: joint-pass).

FDBC@B       예산 상한 B 안에서 feasible-covered 인 basin 의 수 (또는 비율).
```

**"feasible" 이 이름에 들어간 것이 핵심이다.** 탐색만 하고 통과 후보가 하나도
없는 basin 은 이 지표에 기여하지 않는다. 즉 "다양하지만 전부 실패하는 후보" 는
정의상 좋은 점수를 받지 못한다.

이것이 `explored coverage` 와 다르다는 점을 명시한다.

```
explored coverage   관측이 하나라도 있는 basin 의 수     ← 진단용
feasible coverage   통과 후보가 있는 basin 의 수         ← primary
```

두 값을 같은 막대로 그리거나 같은 이름으로 부르지 않는다. 죽은 basin 을 탐색한
것은 explored 는 올리지만 feasible 은 올리지 않는다.

## SS2. Guardrail — 절대 수율이 무너지면 실패다

FDBC@B 안에 feasibility 가 들어 있지만 그것만으로는 부족하다. basin 마다
통과 후보 1 개씩만 얻고 전체 통과 수가 급감하는 배분도 FDBC 는 높게 나온다.

그래서 **총 structural success 수를 guardrail 로 둔다.**

```
primary     FDBC@B                        높을수록 좋다
guardrail   총 joint-pass 후보 수          yield mode 대비 비열등이어야 한다
```

guardrail 이 깨지면 coverage 개선을 성공으로 보고하지 않는다.

### 비열등 마진 — 확정: 10% 상대 마진

```
structural-yield ratio = (coverage mode 의 총 joint-pass 수)
                       / (comparator 의 총 joint-pass 수)

guardrail:  yield ratio >= 0.90
```

**이것은 biological truth 가 아니라 v2.0 의 운영상 사전등록 기준이다.** 어떤
생물학적 근거로 0.90 이 나온 것이 아니다. 5% 는 coverage 를 위해 일부를
내주려는 mode 에 지나치게 빡빡하고, 20% 는 구조 성공 후보를 너무 많이 잃어도
통과시킨다는 판단에서 고른 값이다. 다른 값이 필요하다고 판단되면 **실험 전에**
버전을 올려 바꾼다. 결과를 보고 바꾸지 않는다.

### 판정 규칙

```
Primary    Feasible Design-Basin Coverage @ Fixed Budget
Guardrail  structural-yield ratio >= 0.90

채택 조건
  FDBC 개선의 타겟 클러스터 bootstrap 95% CI 가 0 을 제외한다
  AND
  yield ratio 의 단측 95% 하한이 0.90 이상이다
```

primary 도 CI 기반으로 둔 것은 v1 선례와 맞추기 위해서다. v1 은 점추정이 아니라
"타겟 클러스터 bootstrap CI 가 0 을 제외" 로 판정했고, 두 mode 를 같은 코호트에서
비교하려면 판정 기준의 형태가 같아야 한다.

guardrail 은 단측이다. 물어보는 것이 "yield 가 충분히 안 떨어졌는가" 이지
"yield 가 달라졌는가" 가 아니기 때문이다.

### Comparator — 실험 전에 고정

```
primary comparator     같은 예산의 static / equal allocation
secondary comparator   frozen structural-yield RAPID (rapid_structural_v1)
```

둘을 함께 보는 이유는 두 질문이 다르기 때문이다.

```
vs static      "기존 균등 배분보다 coverage 를 늘렸는가"
vs v1 yield    "그 대가로 yield 를 얼마나 잃었는가"
```

`vs static` 을 primary 로 두는 것은 그것이 현재 운영 관행이기 때문이고,
`vs v1` 을 secondary 로 두는 것은 두 mode 가 같은 Core 의 서로 다른 설정이라
직접 비교가 해석 가능하기 때문이다. **두 comparator 를 하나로 합치지 않는다** -
합치면 어느 질문에 답한 것인지 알 수 없다.

이 구조는 임상시험의 guardrail endpoint 와 같다 - primary 가 좋아져도
guardrail 이 무너지면 그 결과를 채택하지 않는다.

**추가로 보고할 것** (판정에는 쓰지 않지만 함께 싣는다):

```
explored coverage        탐색은 했으나 통과가 없던 basin 수를 드러낸다
basin 당 통과 후보 분포   한 basin 에 몰렸는지
realized compute         §41 의 2 차 분석과 같은 축
```

## SS3. coverage_unit — fixed_backbone_redesign 은 동결됨

```
coverage_unit = backbone_id
```

**운영 정의다.** 각 backbone 이 서로 다른 생물학적·구조적 basin 에 대응한다고
주장하지 않는다. coverage 를 세기 위한 design-context 단위일 뿐이다.

근거는 M1 (`public_data/benchmark/gate0/m1_basin_structure.json`) 이다. 홀드아웃
RFD3 60 개, 타겟 내 120 쌍:

```
비자명 AND 안정인 임계값이 사실상 없다
  complete linkage   1.0 Å 하나. 60 백본 → 59 클러스터 (병합 1 회)
  single linkage     1.0 Å 과 3.0 Å. 후자는 13 개로 바닥(12)에 붙어 있다
1.5–2.5 Å 에서 전체 백본의 58% 가 소속을 바꾼다
2.0 Å 에서 linkage 만으로 42 vs 36
```

M1 이 말하는 것은 "1 backbone = 1 basin" 이 아니라 **"이 데이터에서는 backbone
보다 더 적절한 안정적 중간 coverage unit 을 정의할 근거가 없다"** 다. 이 문구를
그대로 유지한다 - 전자로 쓰면 측정하지 않은 것을 주장하게 된다.

### 다른 TaskProfile 은 자기 unit 을 갖는다

```
FixedBackboneRedesign   coverage_unit = backbone_id            (동결)
AntigenTaskProfile      coverage_unit = backbone_id
                        또는 validated structural cluster       (미정)
Future task             domain-specific unit
```

**Antigen 을 기다리지 않는다.** Antigen 의 ~200 backbone 에서 나중에 명확한
클러스터 구조가 나오더라도 그것은 AntigenTaskProfile 의 unit 문제이지 이 profile
의 문제가 아니다. 서로 다른 task 를 억지로 같은 단위로 묶는 것이 오히려 Core 의
generic 설계에 어긋난다.

```
TaskProfile → coverage_unit 정의 → RAPID Core → 그 unit 들의 coverage 로 배분
```

Core 는 unit 이 무엇인지 모른다. 그것이 §B1 의 경계다.

### 아직 동결하지 않은 것

`coverage_unit` 은 정해졌지만 **endpoint 의 형태는 M2 뒤에 정한다.**

```
동결됨      coverage_unit = backbone_id
            feasibility = joint-pass
            guardrail = yield ratio >= 0.90
            comparator = static/equal (primary), frozen v1 (secondary)
            판정 = FC CI 가 0 제외 AND yield ratio 단측 하한 >= 0.90

M2 뒤 동결   endpoint 가 binary count 인가 effective (exp H) 인가
            budget_grid
            informative unit 규칙과 최소 수
```

동결 문서: `docs/specs/rapid-v2-coverage-endpoint-freeze.md` (M2 뒤 작성).

## SS4. 이 endpoint 가 v1 과 다른 점

```
v1 primary    예산 안에서 찾은 joint-pass 후보 수        후보 단위
v2 coverage   예산 안에서 feasible-covered 된 basin 수    basin 단위
```

같은 데이터에서 둘 다 계산할 수 있고, 그래야 한다. 두 mode 를 같은 코호트에서
비교할 때 각 mode 를 자기 primary 로만 평가하면 비교가 되지 않는다.

```
             yield mode        coverage mode
FDBC@B       (보고)            primary
joint-pass   primary           guardrail
```

네 칸을 모두 채워 보고한다.

## SS5. Antigen 의 주장 경계 — 확정

AG4 가 기록한 대로 현재 Antigen 에는 allocation reward 로 쓸 수 있는 evaluator 가
없다. 따라서:

```
Antigen v2.0 이 주장하는 것
  coverage allocation 까지. FDBC@B 계열의 basin coverage 유지.

Antigen v2.0 이 주장하지 않는 것
  affinity 기반 adaptive allocation
  yield 기반 adaptive allocation
  wet hit rate 개선
```

**wet 결과가 나오기 전에는 위 세 줄을 주장하지 않는다.** Invariant 6 의 구체적
적용이고, Invariant 7 로 승격한다 (§T).

여기에는 결과가 따라온다: Antigen 의 FDBC@B 에서 feasibility 기준을 무엇으로
둘 것인가. AF3 preservation gate 와 ipSAE 는 현재 gate 로 쓰이고 있으므로
feasibility 로는 쓸 수 있다 (gate 허가는 있다). **결합 성능 지표로 쓰는 것이
금지될 뿐이다.** 즉 Antigen 의 feasible coverage 는 "이 basin 에서 구조적으로
성립하는 후보가 나왔는가" 이지 "잘 붙는 후보가 나왔는가" 가 아니다. 이 구분을
보고 문구에 그대로 유지한다.

---

# T. 설계 invariant

구현 시 테스트로 집행할 대상이다.

## Invariant 1
```
Sequence diversity must never be treated as a substitute
for backbone/design-basin coverage.
```
근거: C2 (단일 backbone 5,000 서열 → 클러스터 4.0 포화 vs 앙상블 203.7).
집행: coverage 상태에 `sequence_*` 지표만으로 채워지는 경로가 없어야 한다.
`backbone_coverage` 가 None 인 채로 coverage-preserving mode 가 실행되면 실패.

## Invariant 2
```
A high structural-success estimate alone must not imply
that unexplored backbones have zero value.
```
집행: `minimum_exploration_policy` 를 만족하기 전 `abandon_arm` 금지.
관측이 0 인 arm 의 coverage 기여를 0 으로 두지 않는다.

## Invariant 3
```
Coverage-preserving mode must not collapse to a single backbone
before its exploration/coverage requirements are satisfied.
```
집행: coverage-preserving mode 에서 살아 있는 arm 수가
`minimum_arms_retained` 아래로 내려가는 배분 계열을 테스트로 금지.

## Invariant 4
```
v2.0 may preserve/explore an existing backbone pool,
but must not claim to expand backbone diversity unless
generate_new_backbone is actually implemented.
```
집행: `generate_new_backbone` 이 미구현인 동안 arm pool 크기는 실행 중
증가하지 않는다. 보고 문구는 §F3 을 따른다.

## Invariant 5
```
Antigen-specific biology must never leak into RAPID Core.
```
집행: Core 모듈에 대한 금지 식별자 테스트 (IMGT, CDR, framework, antibody,
epitope, 그리고 §26 의 모델 이름 전부).

## Invariant 6
```
No computational Antigen evaluator may be promoted to wet truth
without prospective experimental evidence.
```
집행: `scientific_permissions` 의 `allocation` / `wet_validated` 로 올리는
변경은 evidence id 를 요구한다. Antigen 의 ROUTER_POLICY 가 이미 이 형태다
(`evidence_id: P53`, "A revision is never edited in place").

## Invariant 7
```
Coverage must be reported as feasible coverage, never as explored coverage,
and a coverage gain that breaks the structural-yield guardrail is not a result.
```
근거: SS1, SS2. 집행: FDBC 계산 경로가 feasibility 판정 없이 basin 을 세면
실패. coverage mode 보고에 guardrail 값이 없으면 실패.

---

# U. 버전 범위

```
v1      frozen structural-yield validation
        tag rapid_structural_v1 · 26 파일 해시 · golden test 31 개
        건드리지 않는다

v2.0    TaskProfile architecture
        + 기존 backbone pool 위의 adaptive allocation
        + coverage preservation (기존 pool 한정)
        + Antigen adapter contract
        구현하지 않는 것:
          generate_new_backbone · full diversity maximization
          full multi-objective optimizer · wet-feedback closed loop
          Antigen pipeline / UI 변경 · continuous Bayesian 모형 확정

v2.1    multi-fidelity
        ESMFold-AF2 paired calibration → CrossFidelityLink
        (이전 판본의 v2.1 그대로)

v2.x    generate_new_backbone
        진짜 design-space 확장

future  wet-feedback closed loop
```

## U1. v2.0 구현 범위 (승인 후)

```
TaskProfile interface              (기존 registry `purposes` 확장)
generic DesignArm
task-aware Objective validation
optimization mode
coverage state contract
EvaluationResult
ScoreTransform
scientific permission
ObservationModel interface
RAPID Core abstraction
FixedBackboneRedesign profile
AntigenTaskProfile adapter contract   ← contract 만. Antigen 코드 변경 없음.
```

---

# V. UX

## V1. task 를 먼저 고른다

```
어떤 설계 작업인가?
  ○ Fixed-backbone protein redesign
  ○ Antibody-antigen design       → Antigen 으로 라우팅 (registry referral 대로)
  ○ Future TaskProfile
```

처음부터 모든 objective 를 보여주지 않는다. objective 목록은 task 가 정한다
(registry `purposes[task].objectives`).

## V2. FixedBackboneRedesign

§E1 의 화면. `Sequence diversity` 는 **Annotations** 에 있고 Optimization mode
에 없다. coverage-preserving mode 에서 상위 정책은 backbone/design-basin
coverage 이고 sequence diversity 는 그것을 보조하는 관측이다.

## V3. Antigen

AntigenTaskProfile 이 허용하는 것만 보여준다. 현재 허가 (AG4) 기준으로:

```
Constraints          framework preservation · CDR geometry
                     antigen preservation · contact retention · developability
Evaluations          PPIformer · AF3 complex metrics · ipSAE · ipTM · pDockQ
Optimization mode    coverage preservation      ← 현재 유일하게 정직한 선택
```

사용자가 evaluator 를 선택했다는 이유로 allocation reward 로 승격하지 않는다.
UI 는 각 evaluator 의 현재 허가 수준을 함께 보여준다 - 이 패턴은 RAPID guided
UI 에 이미 있다 (`objective_status` 를 읽어 "검증됨" 라벨에 측정 분수를 붙임).

---

# W. 논문 claim 과 v2 claim 의 분리 (§47)

현재 논문이 검증한 것:

> structural-success 기반 target-adaptive hierarchical compute allocation 이
> fixed-backbone redesign 에서 제한된 계산 예산으로 static allocation 보다
> 성공 후보를 더 효율적으로 회수할 수 있다.

검증하지 **않은** 것:

```
RAPID maximizes sequence diversity
RAPID maximizes backbone diversity
RAPID improves binding
RAPID improves arbitrary biological function
RAPID experimentally improves antibody affinity
RAPID wet-feedback allocation is validated
```

v2 와 Antigen integration 은 Discussion / Future Work 또는 후속 연구로
구분한다.

---

# X. 열린 질문 — 데이터 없이 결정할 수 없는 것

설계 결정이 아니라 측정이 필요해서 남긴다. **지금 고르지 않는다.**

1. **coverage floor 의 값.** `minimum_probe_per_arm`,
   `minimum_arms_retained` 를 얼마로 둘 것인가. 근거가 두 곳에 있지만 (v1 의
   probe 바닥 20 = 4×5, Antigen 의 예산 25–35%) 둘 다 다른 pipeline 의 값이다.
   task 별로 재야 한다.

2. **basin 축 (= coverage 축).** 개별 backbone 인가 structural cluster 인가.
   **결정 절차는 SS3 에서 확정됐다** - 먼저 클러스터 구조를 판정 없이 기술
   통계로 재고, 그 결과를 보고 별도 freeze 문서에 못 박은 뒤 prospective
   evaluation 을 시작한다. 값 자체는 그 측정 전에 정하지 않는다. 홀드아웃
   RFD3 60 개와 Antigen ~200 개 모두 서로 얼마나 다른지 재본 적이 없다.

3. **coverage 항의 가중.** `δ·portfolio_redundancy` 의 δ. 임의 값을 넣고
   diversity-aware 라고 부르지 않는다 (O1).

4. **연속 objective 의 계층 모형과 hyperparameter.** Beta 의 4.0 을 복사하지
   않는다 (N1).

5. **`CrossFidelityLink` 의 형태.** ESMFold-AF2 paired 데이터가 필요하다.
   현재 ESMFold 는 `wired_unvalidated`, 비용 미측정, 호출하는 곳 없음.

6. **`generate_new_backbone` 의 비용과 coverage 이득 추정** (G2 의 4, 5).

7. **Antigen evaluator 의 허가 재평가.** wet 결과가 필요하다. 현재 ddG 순위가
   구조 검증 통과를 예측하지 못한다는 부정 결과가 있다 (Q4).

8. ~~coverage-preserving mode 의 검증 설계.~~ **확정됨 (§SS).**
   primary 는 `Feasible Design-Basin Coverage @ Fixed Budget`, guardrail 은
   총 structural success 수의 비열등이다. 남은 것은 SS3 의 basin 동결과
   SS2 의 비열등 마진 값이며, 둘 다 위 2 번과 아래 9 번으로 옮겼다.

9. ~~guardrail 비열등 마진.~~ **확정됨: yield ratio >= 0.90 (§SS2).**
   운영상 사전등록 기준이며 biological truth 가 아니다. comparator 도 함께
   고정했다 - primary 는 같은 예산의 static/equal allocation, secondary 는
   frozen v1.

---

# Y. 참고한 근거

| 주장 | 출처 |
|---|---|
| 단일 backbone 서열 클러스터 4.0 포화 vs 앙상블 203.7 | `public_data/benchmark/results/sequence_space_coverage_summary.json` |
| 온도로 mean pairwise diversity 0.12→0.30 도달 (recovery 대가) | `docs/figures/README.md` (제외된 그림) |
| 선택 집합 다양성 0.31 vs 0.11, 9/9 타겟 | `docs/manuscript.md` §3.3 |
| 같은 backbone 후보 변이 집합 90% 중복 · per_backbone 상한으로 ddG 중앙값 +1.00→+0.12 | `/opt/antigen_pipeline` commit `ca84aab` |
| 같은 backbone·mask 재설계는 200/200 byte-identical | `/opt/antigen_pipeline` commit `e064f1c` |
| surrogate probe 최적 예산 몫 25–35% | `/opt/antigen_pipeline` `models.py` `antibody_surrogate_triage_initial_samples` |
| ddG 순위가 구조 검증 통과를 예측하지 못함 | `/opt/antigen_pipeline` `models.py` `selection_independent_annotations` |
| 두 designable 집합이 따로 결정됨 · arm 정의 | `/opt/antigen_pipeline` `docs/routing/ANTIBODY_DESIGN_ARMS.md` |
| antibody 요청을 Antigen 으로 보내라는 기존 결정 | `MODEL_REGISTRY_V1.yaml` `purposes.antibody_design.referral` |
| Gate 0 AUC 는 monomer 에서만 측정됨 | `MODEL_REGISTRY_V1.yaml` `purposes.protein_binder_design.caveat` |
| 적응 배분 이득이 예산 23 부터 · probe 바닥 20 | `holdout_grid/prospective_allocation_validation_joint.json` |
| 임계값 3 개의 provenance | `scripts/transcoder/rapid_sr/protocol.py` `THRESHOLD_PROVENANCE` |
