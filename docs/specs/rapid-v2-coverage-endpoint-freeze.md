# Coverage-preserving mode — endpoint 동결

> **§8 만 SUPERSEDED — v2.0 multi-source 설계로 대체됨.**
> 대체 문서: [`rapid-v2-multisource-validation-freeze.md`](rapid-v2-multisource-validation-freeze.md) §7
> (이 문서의 commit `c45795d` 기준)
>
> budget grid 가 10-backbone candidate ceiling (240 / target / source) 에 맞춰
> `40 · 60 · 80 · 100 · 120 · 160 · 200 · 240` 으로 다시 동결됐다.
> **§1-7 과 §9-11 은 전부 유지된다** - coverage_unit · EFBC 정의 · feasibility ·
> guardrail 0.90 · comparator · 판정 규칙 · endpoint 별 informative 규칙.
> 단 coverage_unit 의 M1 근거는 RFD3 backbone 에서만 나왔으므로, BioEmu 적용은
> 대체 문서 §12 의 M1-BioEmu 구조 진단을 거친다.


**상태: 승인됨.** 이 문서가 coverage mode 평가의 사전등록이다. 여기 적힌 값을
결과를 보고 바꾸지 않는다 - 바꿔야 하면 버전을 올리고 이유를 남긴다.

v1 의 `holdout_experiment_spec.json` 과 같은 역할이다. 결과를 보고 판정 기준을
고르는 일이 없도록, 평가를 시작하기 전에 여기 못 박는다.

관련 문서: 설계 §SS · 구현 계획 M1/M2 ·
`m1_basin_structure.json` · `m2_endpoint_dynamic_range.json`

---

## 1. coverage_unit

```
coverage_unit = backbone_id
```

**운영 정의다.** 각 backbone 이 서로 다른 생물학적·구조적 basin 에 대응한다고
주장하지 않는다. coverage 를 세기 위한 design-context 단위다.

근거 (M1, 홀드아웃 RFD3 60 개 · 타겟 내 120 쌍):

```
비자명 AND 안정인 임계값이 사실상 없다
  complete linkage  1.0 Å 하나 → 60 백본에서 59 클러스터 (병합 1 회)
  single linkage    1.0 Å 과 3.0 Å → 후자는 13 개로 바닥(12)에 붙음
1.5–2.5 Å 에서 전체 백본의 58% 가 소속을 바꾼다
2.0 Å 에서 linkage 선택만으로 42 vs 36
```

M1 이 말하는 것: "1 backbone = 1 basin" 이 아니라 **"이 데이터에서는 backbone
보다 더 적절한 안정적 중간 coverage unit 을 정의할 근거가 없다"**.

이 profile 에만 적용된다. 다른 TaskProfile 은 자기 unit 을 정한다.

## 2. Primary endpoint

```
Effective Feasible Backbone Coverage @ Fixed Budget       (EFBC@B)

  예산 상한 B 안에서 얻은 joint-pass 후보를 backbone 별로 세고,
  pᵢ = (backbone i 의 통과 후보 수) / (전체 통과 후보 수)
  H  = −Σ pᵢ ln pᵢ
  EFBC = exp(H)          통과 후보가 하나도 없으면 0
```

### 왜 binary 가 아닌가 (M2)

```
의무 probe 직후 이미 61.1% 의 재생에서 5 개 unit 이 전부 feasible
타겟 5/12 가 90% 이상 5/5
전체 격자 천장에서 10/12 가 5/5, 나머지 2 개는 1/5
```

binary count 는 정책이 아니라 코호트를 재게 된다. effective 는 같은 자료에서
1.00–5.00 의 범위를 유지하고, 집중을 실제로 구분한다 - 3bqwA01 은 binary 5/5
지만 통과 수가 `[24, 23, 23, 23, 1]` 이라 effective 4.18 이다.

무작위 portfolio 에서도 범위가 남는다: 크기 5 에서 평균 2.87/5 backbone,
크기 10 에서 4.27/5.

## 3. Feasibility 기준

```
joint-pass = pLDDT >= 85 AND rmsd_nonloop_order <= 2.0 AND soluprot >= 0.5
```

v1 과 같은 정의다. 세 임계값은 캠페인 이전에 정해졌고 여기서 다시 고르지 않는다
(`THRESHOLD_PROVENANCE`, 셋 다 `convention_without_internal_calibration`).

## 4. Guardrail

```
structural-yield ratio = (coverage mode 총 joint-pass 수)
                       / (comparator 총 joint-pass 수)

guardrail: yield ratio >= 0.90
```

**운영상 사전등록 기준이며 biological truth 가 아니다.** 5% 는 일부 yield 를
내주려는 mode 에 지나치게 빡빡하고, 20% 는 구조 성공 후보를 너무 많이 잃어도
통과시킨다는 판단에서 골랐다.

## 5. Comparator — 실험 전 고정

```
primary comparator    같은 예산의 static / equal allocation
secondary comparator  frozen structural-yield RAPID (rapid_structural_v1)
```

둘을 합치지 않는다. `vs static` 은 "기존 균등 배분보다 coverage 를 늘렸는가",
`vs v1` 은 "그 대가로 yield 를 얼마나 잃었는가" 에 답한다.

## 6. 판정 규칙

```
채택 조건 (둘 다 만족)
  1. EFBC 개선의 타겟 클러스터 bootstrap 95% CI 가 0 을 제외한다
  2. yield ratio 의 단측 95% 하한이 0.90 이상이다
```

primary 를 CI 로 판정하는 것은 v1 선례와 맞추기 위해서다. guardrail 이 단측인
것은 묻는 것이 "yield 가 충분히 안 떨어졌는가" 이기 때문이다.

## 7. Informative 규칙 — endpoint 마다 다르다

**두 endpoint 의 informative 집합이 다르고, 제외되는 타겟이 서로 겹치지
않는다.** 이것을 하나로 뭉개면 안 된다.

```
coverage (EFBC) 기준
  정보 없음 = feasible 가능한 unit 이 1 개 이하   ← 어떤 정책도 EFBC 를 못 바꾼다
  제외: 3es1A01 [9,0,0,0,0] · 5xpdA02 [8,0,0,0,0]
  정보 있는 타겟 10/12

yield 기준 (v1 규칙 그대로)
  정보 없음 = 모든 arm yield 0 또는 모든 arm yield 1
  제외: 1sh6A02 (전부 1.0)
  정보 있는 타겟 11/12

양쪽 모두 정보 있는 타겟 9
```

```
주 분석      endpoint 별 informative 집합을 쓴다 (EFBC 10, yield 11)
일관성 확인   9 타겟 교집합으로 다시 계산해 방향이 같은지 본다
최소 클러스터 8 (v1 선례). 10 과 11 둘 다 충족한다.
```

> **Endpoint-specific informative sets define endpoint-specific estimands;
> the 9-target intersection is a sensitivity analysis for direction
> consistency and is not the primary estimand.**

두 endpoint 에서 "정보가 없는" 이유가 서로 다르기 때문이다. EFBC 에서는
feasible 가능한 backbone 이 하나뿐이면 어떤 정책도 coverage 를 바꾸지 못하고,
yield 에서는 모든 arm 이 0 또는 1 이면 어떤 정책도 yield 를 바꾸지 못한다.
9 개 교집합으로 억지로 맞추면 각 endpoint 에서 실제로 쓸 수 있는 정보를 이유
없이 버리게 된다.

### 보고 표 — 어느 집합을 썼는지 항상 적는다

| 결과 | 분석 집합 |
|---|---|
| ΔEFBC vs static | coverage-informative 10 targets |
| Yield ratio vs static | yield-informative 11 targets |
| ΔEFBC sensitivity | common 9 targets |
| Yield ratio sensitivity | common 9 targets |

**서로 다른 n 을 쓴 결과를 같은 n 인 것처럼 합쳐 말하지 않는다.** 채택 규칙은
각 조건을 자기 endpoint 집합에서 판정한다 (§6).

1sh6A02 이 coverage 에서는 정보가 있다는 점을 특히 기록한다 - 모든 backbone 이
yield 1.0 이라 yield 로는 정책을 구별하지 못하지만, 예산을 어디에 쓰든 통과가
나오므로 **집중하느냐 분산하느냐가 EFBC 를 직접 바꾼다.**

## 8. Budget grid

```
1..24 전 구간 + 30, 40, 50, 60, 80, 100, 120
```

v1 과 같은 격자를 쓴다. 두 mode 를 같은 축에서 비교하기 위해서다. 예산 20 미만
구간은 의무 probe 가 예산을 다 쓰므로 coverage 도 probe 가 정한다 - 그 구간을
빼지 않고 그대로 보고한다 (v1 에서 probe 바닥이 결과의 일부였던 것과 같다).

## 9. 부수 보고 (판정에 쓰지 않는다)

```
binary feasible coverage      포화한다는 것을 보여주기 위해 함께 싣는다
explored coverage             통과 없이 탐색만 한 unit 수
realized compute              예산 상한이 아니라 실제 쓴 호출 수
unit 별 통과 후보 분포          집중이 어디서 생겼는지
```

## 10. 네 칸 보고 (설계 §SS4)

```
              yield mode      coverage mode
EFBC@B        보고            primary
joint-pass    primary         guardrail
```

각 칸에 해당 endpoint 의 informative 집합을 쓰고, 어느 집합을 썼는지 표에
적는다.

## 11. 동결 대상 요약

| 항목 | 값 | 근거 |
|---|---|---|
| coverage_unit | `backbone_id` | M1 |
| primary endpoint | EFBC@B = exp(H) | M2 |
| feasibility | joint-pass | v1 동일 |
| guardrail | yield ratio ≥ 0.90 | 운영 기준 |
| guardrail 검정 | 단측 95% 하한 | — |
| primary 검정 | 타겟 클러스터 bootstrap 95% CI 0 제외 | v1 선례 |
| comparator | static/equal (primary), v1 (secondary) | — |
| informative (EFBC) | feasible 가능 unit ≥ 2 → 10/12 | M2 |
| informative (yield) | v1 규칙 → 11/12 | v1 |
| 최소 클러스터 | 8 | v1 선례 |
| budget grid | 1–24 + 30/40/50/60/80/100/120 | v1 동일 |

## 12. 승인 전까지 하지 않는 것

```
prospective evaluation 시작
Phase 4 의 endpoint 확정 코드
coverage mode 결과 보고
```
