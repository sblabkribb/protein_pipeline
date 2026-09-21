# 계층형 배분 retrospective replay — 실행 전 사전지정

> **상태: 실행 전 동결.** 이 문서가 커밋된 뒤에 분석을 돌린다. 여기 적힌 값을
> 결과를 보고 바꾸지 않는다. 바꿔야 하면 버전을 올리고 이유를 남긴다.

작성 2026-09-21. 대상 분석: `scripts/benchmark/35_hierarchical_replay.py`(아직 없음).

**v1.1 개정 (2026-09-21, 실행 전).** §6.1 이 제외했던 순차 갱신판을
`adaptive_sentinel` 이라는 이름의 **탐색 arm 으로 추가**한다. 주 비교는 바꾸지
않는다. 개정 이유: 배분을 warm-up 에 고정하면 "되먹임이 조금이라도 이득을
주는가" 를 아예 물을 수 없는데, 이 질문은 ceiling 안에서도 답할 수 있고 같은
실행에서 공짜로 얻어진다. 개정 시점에 분석은 아직 실행되지 않았다.

---

## 1. 무엇을 묻는가

연구노트는 **서열 축**만 다룬다 — 한 표적의 후보 풀에서 어느 서열을 접을지.
RAPID 에는 **백본 축**이 하나 더 있다: 어느 백본에 folding 호출을 더 줄지.
이 분석이 묻는 것은 하나다.

> 동일한 neutral warm-up 이후, **백본 수준 배분**과 **백본 내부 서열 순위화**를
> 결합하면 서열 순위화만 쓰는 것보다 남은 folding 예산을 더 효율적으로 쓰는가?

**이것은 확증 분석이 아니다.** 우리는 이미 v2 결과를 보았다. 그러므로 이름은
**pre-specified retrospective replay / exploratory algorithmic validation** 이고,
동결된 confirmatory 종점이나 기존 판정을 대체하지 않는다.

## 2. 왜 지금 자료로 되는가, 그리고 어디까지만 되는가

저장 격자는 후보 5,328 · 고유 백본 357 이고 후보마다 백본이 기록돼 있다.
**새 folding 은 0 회다.** 그러나 격자는 "완전"하지 않다. 실측:

```
calibration_v2   백본당 후보 12 개  (rfd3 93 백본 · bioemu 90 백본)
confirmatory     백본당 후보 18 개  (rfd3 105 백본 · bioemu 69 백본)
```

백본당 18 은 동결 계획의 `ceiling_per_unit = 18` 과 정확히 같다. 격자가 그
계획에 맞춰 생성됐기 때문이다. 따라서 **백본 하나에 18 회를 넘겨 집중하는
정책은 재생할 자료가 아예 없다.** 이 분석이 측정할 수 있는 것은 ceiling 안의
약~중간 집중뿐이며, 그 사실을 결과 해석에 명시한다.

집중 여지는 예산이 **클수록 좁아진다** (10 백본 unit 기준):

```
B=60   adaptive 20   한 백본 최대 +14   최소 2 백본에 분산   집중배율 7.0x
B=80   adaptive 40   한 백본 최대 +14   최소 3 백본에 분산   집중배율 3.5x
B=100  adaptive 60   한 백본 최대 +14   최소 5 백본에 분산   집중배율 2.3x
```

## 3. 코호트 — confirmatory 만 쓴다

`rapid-v2-phase4b-calibration-freeze.md` §14 는 calibration 코호트에 대해
**policy 비교 · EFBC 계산 · coverage 결론 · confirmatory 주장**을 금지한다.
§7: "calibration 단계에서 EFBC 를 계산하지 않는다. 계산하는 순간 policy
tuning 이다." 이 분석은 정의상 policy 비교이므로 **calibration 코호트를 쓰지
않는다.**

| 역할 | source | unit | 비고 |
|---|---|---|---|
| Primary | RFD3 confirmatory | 8 | 판정 대상 |
| Descriptive | BioEmu confirmatory | 6 | 최소 클러스터 8 미달 — 방향만 기술 |

RFD3 confirmatory 8 unit 의 실측 구조:

```
1j5uA01 1n81A00 1sdiA00 1x3aA00 4ifxA00 4wexA00 6vqfA00   백본 10 · pool 180
4ai2A02                                                    백본  5 · pool  90
```

**생성원을 합치지 않는다** (`pooling_across_sources_forbidden`). BioEmu 6 unit 은
동결 계획의 `min_clusters = 8` 을 밑돌므로 판정하지 않고 방향만 적는다 — 이는
BioEmu confirmatory 가 NOT_EVALUABLE 이었던 바로 그 이유이며, 같은 자료로는
해소되지 않는다.

## 4. 예산 격자 — 주 분석은 B=80 이다

`4ai2A02` 는 pool 이 90 이라 **B=100 에서 빠진다** → 7 unit. 동결 계획은
"최소 클러스터 8 을 밑도는 B 는 그 source 에서 판정하지 않는다" 이므로
**B=100 은 판정 불가**다.

```
B=80    주 분석      8 unit   adaptive 40   집중배율 3.5x
B=60    민감도       8 unit   adaptive 20   집중배율 7.0x
B=100   기술만       7 unit   min_clusters 미달 → 판정하지 않는다
B=40    제외         warm-up 과 같아 모든 정책이 동일 배분이 된다
```

B=80 을 고른 이유는 **8 unit 을 유지하는 최대 예산**이기 때문이지 효과가 클
것 같아서가 아니다. B=100 이 adaptive call 은 많지만 ceiling 때문에 정책
공간은 오히려 좁다(위 §2).

## 5. warm-up — 모든 arm 이 똑같이 쓴다

```
백본당 sentinel 4 개, 백본 안에서 무작위 추출
10 백본 unit → warm-up 40 calls
 5 백본 unit (4ai2A02) → warm-up 20 calls   (동결 규칙 unequal_units: 4u)
```

warm-up 은 **arm 간 동일**하다. 같은 seed 에서 네 arm 이 **같은 warm-up 표본**을
받는다. 따라서 arm 간 차이는 오직 "남은 B−warm-up 을 어떻게 쓰는가"에서만
생긴다. warm-up 에서 나온 joint-pass 도 수확에 센다.

## 6. arm 정의

`H` 가 warm-up 수, `A = B − H` 가 배분 가능한 호출 수다.

```
equal_random        A 를 백본에 균등 배분, 백본 안에서 무작위
mpnn_only           A 를 MPNN score 오름차순으로 (백본 무시)
rf_only             warm-up 으로 RF 적합, unit 전체 pool 에서 상위 A 개
backbone_only       백본 posterior 로 A 를 배분, 백본 안에서는 무작위
hierarchical        백본 posterior 로 A 를 배분, 백본 안에서는 RF 순위
```

**주 비교는 `hierarchical − rf_only` 하나다.** 나머지는 보조다.

`mpnn_only` 는 두 가지로 보고한다. (a) 위처럼 같은 warm-up 을 치른 판
(이 분석의 질문에 맞는 비교), (b) warm-up 없이 B 개를 전부 고르는 판
(`33_` 과 같은 회계). **둘을 섞어 쓰지 않는다.**

### 6.1 백본 posterior 와 선택 편향

이것이 이 설계에서 가장 틀리기 쉬운 부분이다.

RF 가 고른 관측은 **위로 편향**돼 있다. 그것을 백본 성공률 posterior 에
넣으면 되먹임이 생긴다 — RF 가 좋아하는 백본이 높은 성공률로 보이고, 그래서
더 배분받고, 다시 RF 가 고른 높은 결과가 들어온다. 그러면 측정되는 것은
배분 정책의 가치가 아니라 되먹임의 크기다.

그래서 **동결 규칙: posterior 는 warm-up sentinel 로만 갱신한다.**
targeted 관측은 수확에만 세고 posterior 에 넣지 않는다.

그 결과 **warm-up 이후 posterior 가 변하지 않으므로 배분은 고정된다.**
따라서 이 arm 을 "adaptive" 라 부르지 않고 **warm-up-informed allocation**
이라 부른다. 순차적 적응의 검증이 아니다.

```
posterior     Beta(1,1) + warm-up sentinel 의 joint-pass 성공/실패
배분 규칙     A 를 posterior 평균에 비례 배분, 백본당 ceiling 18 (누적)
              반올림 잔여는 posterior 평균 내림차순으로 배정
```

### 6.2 `adaptive_sentinel` — 탐색 arm (v1.1 추가)

주 비교에 들어가지 않는다. 판정하지 않고 기술만 한다.

```
탐색 몫        A 의 25% 를 무작위 추출에 쓴다 (4 회마다 1 회, 결정적 간격)
posterior      sentinel + 탐색 관측으로만 갱신. targeted 관측은 넣지 않는다.
배분           매 호출마다 Thompson sampling: theta_b ~ Beta(a_b, b_b),
               ceiling 에 걸리지 않은 백본 중 argmax
백본 내부      탐색 호출이면 무작위, 아니면 RF 상위
```

warm-up-informed 와의 차이는 **posterior 가 실제로 갱신되는가** 하나다.
탐색 몫 25% 는 실행 전에 고른 값이고 결과를 보고 바꾸지 않는다. 이 arm 은
탐색 호출에 예산을 쓰므로 targeted 호출이 적다 - 불리할 수 있고, 그것도
결과다.

## 7. 프로토콜 — 새로 만들지 않는다

```
RF              RandomForestRegressor(n_estimators=100), 표준화 없음
표현            esm2_t6_8M_UR50D 320 차원 평균 풀링 (기존과 동일)
라벨            joint-pass = pLDDT>=85 AND 비루프 Ca-RMSD<=2.0 A AND SoluProt>=0.5
MPNN score      per-residue mean NLL, **낮을수록 좋다** -> 오름차순
seed            42 · 123 · 7 · 2024 · 31337
구간            unit 클러스터 부트스트랩 2,000 회 · percentile 95% · seed 20260921
다중성          주 비교 1 개뿐이므로 주 분석에 보정하지 않는다.
                보조 비교 3 개는 Bonferroni 98.33%(3 검정) 를 함께 적는다.
```

## 8. 사전에 정해 두는 해석 규칙

```
구간이 0 을 포함하면   "구별되지 않았다". 동등성·비열등성이 아니다.
BioEmu                 방향만 적는다. "재현되었다" 로 쓰지 않는다 (6 < 8).
집중 범위              모든 결론에 "ceiling 18 안의 약~중간 집중" 을 붙인다.
4ai2A02                B=80 에서 pool 의 89% 를 접는다. 정책이 수렴하므로
                       판별력이 낮다. unit 별 결과를 반드시 함께 낸다.
배수 표현              쓰지 않는다.
```

## 9. 예상되는 결과와 그 처리

```
hierarchical > rf_only   이 ceiling 안에서 결합 이득을 관찰했다고 쓴다.
                         "adaptive allocation 검증됨" 으로 쓰지 않는다.
구별 안 됨               그대로 보고한다. 연구노트는 그대로 둔다.
hierarchical < rf_only   그대로 보고한다. 백본 제약이 RF 의 선택을 좁혀
                         손해일 수 있다는 것도 실제 가능한 결과다.
```

**어느 쪽이 나와도 보고한다.**

## 10. 하지 않는 것

- 새 folding 을 하지 않는다.
- calibration 코호트를 쓰지 않는다.
- **EFBC 를 계산하지 않는다.** coverage 결론을 내지 않는다.
- 생성원을 합치지 않는다.
- B=40 에서 정책을 비교하지 않는다 (warm-up 과 같다).
- B=100 을 판정하지 않는다 (7 unit < 8).
- 동결된 kappa 식별·confirmatory 평가가능성 판정을 바꾸지 않는다.
- 순차 갱신 arm(`adaptive_sentinel`)의 결과로 주 판정을 바꾸지 않는다.
- 이 결과를 "independent replication" 또는 "prospective validation" 으로
  부르지 않는다. 같은 표적을 RFD3 와 BioEmu 가 12 개 공유한다.
- ceiling 을 넘는 집중 정책을 시험하지 않는다. 자료가 없다.

## 11. 이 분석으로 답할 수 없는 것

강한 집중 배분의 가치는 **백본당 18 개를 넘는 새 자료가 있어야** 판정할 수
있다. 이 분석이 양성이어도 그것은 다음 단계의 근거이지 결론이 아니다.
