# Phase 4B — joint-pass posterior calibration cohort audit

**결론: 부분 자격만 있다. `κ_pool` 은 어떤 독립 코호트에서도 식별되지 않는다.**

목적은 12-target confirmatory holdout 과 완전히 분리된 기존 development
데이터에서 joint-pass 사후분포의 hyperparameter 를 추정해 동결하는 것이었다.
데이터가 많다는 이유로 쓰면 안 되므로 5 개 조건으로 감사했다.

---

## 1. frozen joint-pass 를 판정할 수 있는 코호트

joint-pass = `pLDDT >= 85 AND rmsd_nonloop_order <= 2.0 AND soluprot >= 0.5`
이므로 세 열이 모두 있고 동결된 지표 정의를 쓴 데이터만 후보다.

| 코호트 | 행 | 타겟 | backbone | 판정 |
|---|---|---|---|---|
| `temperature_sweep` (panel1_unfiltered) | 480 | 15 | 15 (전부 native) | 후보 |
| `temperature_panel2` (panel2_informative) | 832 | 10 | 26 (rfd3 16 · bioemu · native) | 후보 |
| `holdout_grid` | 1,728 | 12 | 72 | **제외 — 확증 코호트** |
| `refresh/cath_pilot_dataset.csv` (77 타겟) | — | 77 | — | **부적격** |

`refresh` 는 열이 7 개이고 **RMSD 열이 아예 없다.** paired SoluProt/pLDDT 는
있어도 joint-pass 를 판정할 수 없다. "옛 데이터가 많다" 를 근거로 쓰면 안
된다는 경고가 정확했다.

## 2. 5 개 조건 대조

| 조건 | panel1 | panel2 |
|---|---|---|
| 1. holdout 타겟과 target-level 분리 | ✅ 겹침 0 | ✅ 겹침 0 |
| 2. Phase 4 결과 이전에 존재 | ✅ | ✅ |
| 3. frozen joint-pass 판정 가능 | ✅ 480/480 | ✅ 832/832 |
| 4. corrected non-loop RMSD 재현 가능 | ✅ `gate0_structural_v1`, matches=True | ✅ 동일 |
| 5. valid/non-valid 구분 가능 | ✅ 거부 0 · 실패 0 | ✅ |

표면 조건은 둘 다 통과한다. 문제는 그 아래에 있다.

## 3. 결정적 발견 — `κ_pool` 은 식별되지 않는다

`κ_pool` 은 **한 타겟 안에서 형제 backbone 이 서로를 얼마나 알려주는가** 를
정하는 값이다. 그러므로 타겟당 backbone 이 둘 이상인 데이터에서만 추정된다.

```
panel1            타겟 15 · 타겟당 backbone 1 개 (15/15)
                  → 형제가 하나도 없다. 원리적으로 추정 불가.

panel2            타겟 10 · 타겟당 1 개 4, 2 개 1, 4 개 5
                  → 형제 구조는 있다. 그러나 **yield 로 선별됐다.**

panel2 native 만   타겟 6 · 전부 타겟당 1 개
                  → 역시 추정 불가.
```

panel2 의 선별은 그 산출물이 스스로 적고 있다.

> 이 패널은 baseline yield 가 중간인 백본만 담는다.

**선별 방향이 하필 `κ_pool` 을 편향시키는 방향이다.** 중간 yield 만 남기면
backbone 간 yield 분산이 압축되고, 압축된 분산은 "형제끼리 비슷하다" 로 읽혀
`κ_pool` 을 위로 민다. 그리고 Phase 4 보고에서 확인했듯 `κ_pool` 을 올리면
argmax 가 이미 mass 가 있는 unit 에서 빈 unit 으로 넘어간다.

즉 이 코호트로 보정하면 **정책을 바꾸는 방향으로 편향된 값**을 얻는다.

두 패널의 분포가 그 차이를 보여준다.

```
panel1 (미선별) backbone yield: 0 인 것 6 · 1 인 것 4 / 15   (양극단)
panel2 (선별)   backbone yield: 0 인 것 4 · 1 인 것 1 / 26   (가운데로 몰림)
```

## 4. 무엇이 보정 가능하고 무엇이 불가능한가

hyperparameter 를 뭉뚱그리면 안 된다. 셋의 식별 가능성이 다르다.

| 값 | 무엇인가 | panel1 에서 추정 가능? |
|---|---|---|
| `mu0` | backbone 하나의 joint-pass 사전 평균 | ✅ 독립 backbone 15 개의 주변 비율 |
| `kappa0` | 그 사전분포의 세기 (backbone 간 분산) | ✅ 15 개 yield 의 분산에서 |
| **`kappa_pool`** | **형제 backbone 이 서로를 알려주는 세기** | ❌ **형제가 없다** |

`mu0` 와 `kappa0` 는 panel1 에서 보정할 수 있다. 다만 panel1 의 15 개는 전부
native backbone 이고 확증 코호트의 주 분석은 RFD3 전용이므로, **native → RFD3
전이 가정**이 남는다.

`kappa_pool` 은 어느 독립 코호트에서도 나오지 않는다.

## 5. 선택지

### (a) 작은 미선별 형제 코호트를 새로 만든다 — 권장

holdout 12 타겟과 분리된 CATH 타겟에서, yield 를 보지 않고 타겟당 RFD3
backbone 을 여러 개 만들어 접는다.

```
예: 타겟 8 × backbone 4 × 서열 8 = 256 fold
    격자 실측 속도 기준 대략 2–3 시간
선정은 적격성과 길이로만. yield 를 보지 않는다.
목적은 kappa_pool 하나이고 EFBC 는 보지 않는다.
```

이것만이 `κ_pool` 을 편향 없이 얻는 길이다. 비용은 캠페인 전체에 비해 작다.

### (b) `mu0`·`kappa0` 만 panel1 에서 보정하고 `kappa_pool` 은 사전등록 민감도

부분 보정이다. 정직하게 쓰면:

> `mu0` 와 `kappa0` 는 holdout 과 분리된 미선별 development backbone 15 개에서
> joint-pass 예측 품질 기준으로 추정해 동결했다. `kappa_pool` 은 형제 구조를
> 가진 미선별 코호트가 없어 경험적으로 보정하지 못했고, frozen v1 과의
> continuity 를 위한 사전지정 약한 풀링 규칙으로 4.0 을 사용했다.

그리고 `kappa_pool ∈ {1, 2, 4, 8, 16}` 을 사전등록 민감도로 전부 보고한다.
이미 2 와 4 사이에서 argmax 가 바뀌는 것을 알고 있으므로, 결론이 그 격자에서
안정적이지 않을 가능성을 미리 인정하는 것이다.

### (c) panel2 로 `kappa_pool` 보정 — 권장하지 않는다

선별 방향이 편향 방향과 일치한다 (§3).

## 6. 보정을 한다면 — 선택 기준

무엇으로 고르는지가 무엇을 고르는지보다 중요하다.

```
기준으로 쓴다      target-held-out joint-pass 예측 품질
                   (leave-one-target-out predictive log likelihood)

기준으로 쓰지 않는다
  EFBC 가 가장 높았던 값
  yield 가 가장 좋았던 값
  v2 가 static 을 가장 크게 이긴 값
  배분 결과가 보기 좋은 값
```

보정 단계에서 EFBC 는 계산하지 않는다. 계산하면 그 순간 policy tuning 이다.

## 7. 동결할 항목 (보정 후)

```
posterior family      Beta-Bernoulli + fixed-form partial pooling
success event         exact frozen joint-pass
calibration cohort    타겟 ID 목록 · 데이터 해시
mu0 · kappa0          값과 추정 방법
kappa_pool            값과 근거 (보정인지 사전지정인지 명시)
update rule
tie-break rule
code/data hashes
sensitivity plan      선택 도구가 아니라 robustness 분석임을 명시
```

동결 뒤에만 `q_b` 의존 acquisition 을 열고, confirmatory replay 를 **한 번**
돌린다.

## 8. 현재 상태

```
Phase 3                    PASS
Phase 4 engineering        PASS
Phase 4 scientific policy  BLOCKED — kappa_pool 미식별
Phase 5                    NO-GO
```
