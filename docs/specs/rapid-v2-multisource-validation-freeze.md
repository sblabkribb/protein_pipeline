# RAPID v2 — multi-source validation protocol 동결 (v2.0)

**상태: 동결.** `multisource_validation_plan.json` 의 `status` 가 `frozen` 이다.
여기 적힌 값을 결과를 보고 바꾸지 않는다 - 바꿔야 하면 버전을 올리고 이유를
남긴다.

### 동결 뒤에도 막혀 있는 것 — MSA 실행 계층

```
protocol freeze              진행 가능  ← 이 문서
calibration_v2 타겟 선정      진행 가능
full MSA 24 타겟              **시작 금지**
```

MSA pilot 에서 길이가 다른 두 타겟이 각각 44.0 분 · 41.5 분 뒤에 `endpoint ok +
빈 A3M` 으로 똑같이 끝났다. biological MSA insufficiency 보다 **transport /
response parsing 문제**라는 가설이 훨씬 강하다.

이것은 **설계 blocker 가 아니라 실행 blocker** 다. 따라서:

```
고친다        response_keys → raw response → parser expected key → 파일 write path
              순서로 실행 계층을 추적한다
고치지 않는다  usable_hits < 10 등 §8 의 scientific MSA 기준
              타겟 선정 · source · 후보 수 · tier
확인 방법      타겟을 더 늘려 확인하지 않는다
```

기계가 읽는 정본은 `public_data/benchmark/gate0/multisource_validation_plan.json`
이다. 이 문서와 그 파일의 숫자가 다르면 테스트가 실패한다.

---

## 0. 이 문서의 지위 — 무엇을 supersede 하는가

**이전 동결을 삭제하거나 고쳐 쓰지 않는다.** 각 문서는 그 자리에 그대로 남고,
아래 표의 절만 이 문서로 대체된다. 나머지 절은 계속 유효하다.

| 이전 문서 | commit | 대체되는 절 | 유지되는 절 |
|---|---|---|---|
| `rapid-v2-phase4b-calibration-freeze.md` | `77eca15` | §2 코호트 · §3 타겟선정 · §4 backbone 선정 · §5 생성설정 · §8 격자 | §7 LOTO · §9 식별판정 · §10 미식별 · §11 민감도 |
| `rapid-v2-sequence-constraint-protocol-freeze.md` | `96a30b0` | §3 교체규칙 · §5 calibration · §6 confirmatory backbone plan | §1 deployment protocol · §2 mapping · §4 tier · §7 v1 지위 · §8 ligand |
| `rapid-v2-coverage-endpoint-freeze.md` | `c45795d` | §8 budget grid | §1-7 · §9-11 전부 |
| `masked_holdout_targets.json` | `898df93` | `design` 블록만 | `selected` · `reserve` · `exclusions` · `seed` · `msa_pilot` |

`masked_holdout_targets.json` 은 **수정하지 않는다.** 타겟 선정이 그 파일의
동결 대상이고, 거기에 손을 대면 "calibration 결과를 보기 전에 잠갔다" 는 주장이
검증 불가능해진다. backbone plan 만 이 문서와 plan JSON 이 대체한다.

이 문서가 **대체하지 않는 것**: joint-pass 정의, 세 임계값, EFBC 정의,
coverage_unit 의 운영적 지위, guardrail 0.90, comparator 구성, endpoint 별
informative 규칙, 최소 클러스터 8, mapping hard-fail 목록, tier 를 allocation
arm 으로 올리지 않는다는 결정.

---

## 1. 핵심 변경 — 왜 source 를 독립 코호트로 두는가

기존 설계는 backbone 을 하나의 배분 풀로 보고 그 안에서 RAPID 이 고르게 했다.
그러면 **"배분이 작동한다" 와 "RFD3 backbone 분포에서 배분이 작동한다" 를 구분할
수 없다.** frozen v1 격자를 다시 보면 이 구분이 이미 자료 안에 있다.

```
1,728 folds = rfd3 1,440 (12 x 5 x 24) + native 288 (12 x 1 x 24)
```

source 열은 처음부터 있었지만 배분 단위로 쓰이지 않았다. 이번에 그것을 실험
설계로 올린다.

### 이 저장소가 이미 기록한 BioEmu 증거

새로 만든 이야기가 아니라 기록된 관측이다.

```
gate0_ladder.json         62 타겟 · 157 backbone · by_source {rfd3 80, target 57, bioemu 20}
holdout_targets.json      코퍼스 전체에서 BioEmu backbone 이 나온 타겟은 4 개
                          wave-3 에서 8 회 실행 중 4 회가 2.0 A 수용 기준 미달
model_routing.py          BioEmu 경로는 n=4 이므로 결론을 exploratory 로 표시
manuscript                18-target structural-context ablation:
                          BioEmu 포함 arm 은 aggregate 점수를 올린 것이 아니라
                          **candidate-pool spread 와 서열 다양성을 바꿨다**
```

마지막 줄이 이번 설계의 근거다. BioEmu 의 기록된 효과는 **집계 성능이 아니라
분산**이었고, EFBC 가 재는 것이 정확히 분산이다. 그래서 BioEmu 를 yield 경쟁자로
넣는 것이 아니라 **독립 coverage 코호트**로 넣는다.

기존 holdout backbone plan 이 BioEmu 를 뺀 이유도 그대로 유효하다. 그 문서의
마지막 항목이 이번에 하는 일이다:

> "source 선택 자체를 주장하려면 별도 arm 으로 나중에 붙인다."

### 섞지 않는다

```
❌ 하나의 allocation pool 에 rfd3 10 + bioemu 10 = 20 unit
❌ 공통 kappa_pool
❌ 두 source 의 posterior 를 하나로
❌ RFD3 success + BioEmu success 를 합친 p-value/CI

✅ q_b,RFD3    kappa_pool,RFD3    독립 식별 · 독립 판정
✅ q_b,BioEmu  kappa_pool,BioEmu  독립 식별 · 독립 판정
```

섞으면 source 간 기저 성공률 차이가 배분 신호로 들어온다. 그러면 RAPID 이
"어느 backbone 이 유망한가" 를 배우는 것이 아니라 "어느 생성기가 잘 되는가" 를
배우고, 그것은 배분 정책의 주장이 아니다.

---

## 2. 이전 데이터의 역할 — 보존하고, input 으로 쓰지 않는다

삭제 금지 목록은 plan JSON `preserved_not_input.items` 에 있다.

```
쓸 수 있는 역할
  historical mechanism evidence
  protocol provenance
  ablation / sensitivity
  target · superfamily 제외 근거
  manuscript background

쓸 수 없는 역할
  새 v2 calibration 의 hyperparameter 우도
  새 v2 confirmatory 의 primary endpoint
```

특히 **기존 51-backbone calibration 은 새 primary calibration 에서 빠진다.**
그 코호트를 만든 이유(형제 backbone 이 있는 미선별 데이터가 없었다)는 정당했고
결과는 보존한다. 다만 그 코호트는 11 타겟 · backbone 5/4/2 불균형 · 단일
source 였고, 이번 설계는 12 타겟 · 균형 10 · 2 source 다. 후자로 정한 뒤 전자를
근거로도 쓰면 같은 hyperparameter 를 두 번 정하는 것이 된다.

기존 코호트는 `historical single-source calibration sensitivity` 로만 보고한다.

---

## 3. Fresh calibration cohort (calibration_v2)

```
타겟            12 (층당 4) · 예비 6 (층당 2)
층              50-150 / 150-250 / 250-400
seed            20260911            ← 선정 전에 이 문서로 커밋한다
source          rfd3 · bioemu 둘 다 같은 타겟을 쓴다
backbone        source 당 10
candidate       backbone 당 12 = tier30 4 · tier50 4 · tier70 4
평가             12 x 10 x 12 = 1,440 / source · 합 2,880
```

### 제외 — 이전 코호트 전부와 그 superfamily

```
holdout resolved / selected / reserve
temperature_sweep · temperature_panel2
calibration (기존) selected / reserve
masked_holdout selected / reserve      ← 이번에 추가된다
위 전부의 superfamily
```

### 가용 풀 확인 — 구성 가능하다

선정 전에 세어 두었다 (적격성·길이·정체만 사용).

```
제외 타겟 74 · 제외 superfamily 74
남은 적격 후보 183 · 층별 50-150: 80 · 150-250: 36 · 250-400: 67
층당 필요 6  →  구성 가능
```

150-250 층이 36 으로 가장 얇다. 그래도 6 의 6 배다.

### 선정에 쓰는 것과 쓰지 않는 것

```
쓴다        적격성 (단일 사슬 · 길이 50-400) · 길이 · 정체(이미 썼는가)
쓰지 않는다  MSA 품질/심도 · RFD3 성공률 · BioEmu 성공률 · pLDDT · RMSD
            SoluProt · joint-pass · Gate 0 사전분포 점수
            legacy rapid_target_manifest.csv 의 eligible 열
```

마지막 항목은 옛 길이 기준을 써서 정상 타겟도 `eligible=False` 로 적고 있다.
적격성은 PDB 를 직접 읽어 독립 판정한다. 테스트가 이것을 지킨다.

seed 와 산출된 타겟·예비 **순서**를 생성 전에 커밋한다.

---

## 4. Confirmatory cohort — 타겟을 다시 뽑지 않는다

Step 2 에서 동결한 fresh masked holdout 을 그대로 쓴다.

```
파일        public_data/benchmark/gate0/masked_holdout_targets.json  (commit 898df93)
seed        20260910
selected    1j5uA01 1n81A00 1o22A00 1rdrA01 1sdiA00 1sohA00
            1x3aA00 2w2sA00 4ai2A02 4ifxA00 4wexA00 6vqfA00
sha256      1e40e0a1022ae09df9df6428c9d164f8342f52eef2656b103b0baa34bb2d7426
예비        2hlyA00 4yikA02 6qd5A00 1okgA03 2i4f100 2hg6A00
```

**재선정 금지.** 바뀌는 것은 backbone plan 하나다.

```
이전  12 x  5 RFD3            x 24 = 1,440
지금  12 x 10 RFD3            x 18 = 2,160   (source 독립)
      12 x 10 BioEmu          x 18 = 2,160   (source 독립)
                                   = 4,320
```

candidate 는 backbone 당 **18** = tier30 6 · tier50 6 · tier70 6 이다. 근거는 §7 에
있다 - 24 는 5-backbone 설계의 ceiling 을 맞추려고 정한 값이었고, 10-backbone
에서는 그 근거가 무효다.

---

## 5. Source 별 생성 규칙 — 유한하고 사전 동결이다

두 source 모두 수용 게이트가 있고, 그래서 **10 개를 못 채울 수 있다.** 그 경우를
결과를 보고 정하면 코호트가 관측에 반응한다. 미리 정한다.

### RFD3

```
mode                local_diversify · partial_t 5.0
select_fixed_atoms  {A1: ALL} 그대로       ← 이번에도 바꾸지 않는다
수용 게이트          target-RMSD <= 2.0 A
필요                타겟당 accepted 10
최대 시도            타겟당 40
순서                동결된 seed 의 생성 순서. 구조 점수나 yield 로 고르지 않는다.
```

기록된 수용률: 60 시도 중 51 accepted (85%). 다만 2r01A02 는 15 시도에서
0 이었다 - 평균이 아니라 타겟별로 갈린다.

### BioEmu

```
model_name                bioemu-v1.1
입력                       native **서열** (구조가 아니다)
target_rmsd_cutoff        2.0            ← 완화하지 않는다
filter_samples            true
max_return_structures     10
num_samples               50
max_attempted_structures  200
필요                       타겟당 accepted 10
순서                       동결된 base_seed 의 sample 순서. RMSD 순으로 고르지 않는다.
```

`num_samples 50` 과 `max_attempted 200` 은 파이프라인이 이미 권고하는 값이다
(`_recommended_bioemu_num_samples` = 요청 x5, `_recommended_bioemu_max_attempted_
structures` = 요청 x20, `filter_samples=True` 일 때). 새로 고른 수가 아니다.
`max_return_structures=10` 도 배포 기본값이다.

기록된 수용률: wave-3 에서 8 시도 중 4 기각 (2.0 A 미달). 50% 라면 accepted 10 에
약 20 시도가 필요하고, 200 은 그 10 배 여유다.

### 못 채웠을 때

```
그 (target, source) 를 SOURCE_GENERATION_INFEASIBLE 로 기록한다
타겟을 예비로 바꾸지 않는다
어려운 타겟에만 생성을 더 주지 않는다
확보된 것을 그대로 쓴다
```

기존 calibration 동결의 판단을 그대로 따른다 - "코호트를 수선하지 않고 확보된
것을 그대로 쓴다". 다만 이번에는 그것이 **source 별로** 일어난다. RFD3 는 10 개,
BioEmu 는 6 개인 타겟이 나올 수 있고, 그것은 두 source 를 섞지 않는 이유를 다시
확인해 준다.

### unit 수가 다를 때의 예산 — 미리 정한다

unit 수 u 가 10 보다 작으면 그 (target, source) 의

```
warm-up  = 4u    (40 이 아니다)
ceiling  = 18u   (180 이 아니다)
```

**ceiling 을 넘는 격자점에서 그 타겟은 non-evaluable 이고 그 B 의 informative
set 에서 빠진다.** 남은 타겟 수를 B 마다 보고한다. 최소 클러스터 8 을 밑도는
B 는 그 source 에서 판정하지 않는다.

이것을 미리 못 박는 이유는 예산 격자와 후보 수가 어긋난 전례가 이미 있기
때문이다 (backbone 당 12 개로는 B=80 이 존재할 수 없었다).

---

## 6. Tier 와 평가 순서 — 바뀌지 않는다

```
calibration   backbone 당 12 = 4 / 4 / 4     (6 주기)
confirmatory  backbone 당 18 = 6 / 6 / 6     (6 주기)
prefix 순서    30 -> 50 -> 70 반복
```

12 와 18 은 둘 다 3 의 배수이므로 주기 경계에서 정확히 균형이고, 그 사이에서도
tier 간 차이가 1 을 넘지 않는다.

`q_b` 는 이 사전 지정 혼합 위의 단일 확률이고, tier 는 생성 조건이지 배분 단위가
아니다. 두 source 모두 같은 tier 혼합을 쓴다 - **source 별로 tier 를 다르게 하면
source 차이와 tier 차이가 교락된다.**

---

## 7. Budget / warm-up

**ceiling 을 먼저 정하고 격자를 파생시켰다.** 격자를 먼저 정하고 후보 수를 맞추지
않았다 - 그것이 이전 24 가 생긴 방식이고, 이번에 무효가 된 근거다.

```
후보 수      backbone 당 18                 (§7.1 근거)
ceiling      10 x 18 = 180 / target / source
warm-up      backbone 당 유효 관측 4 → 10 x 4 = 40

격자          40 · 60 · 80 · 100 · 120 · 140 · 160 · 180
k = B/u        4 ·  6 ·  8 ·  10 ·  12 ·  14 ·  16 ·  18

primary informative   60 - 160  (6 점)
앵커                   40 · 180  (판정점에서 제외)
B < 40                구성 시점에 거부된다. diagnostic 전용.
```

### 7.1 후보 수 18 의 근거 — 셋으로 제한한다

근거는 `m2b_candidate_depth_diagnostic.json` 이고, **design planning evidence
이지 새 confirmatory 결과가 아니다.**

```
12   historical v1 에서 정보가 컸던 informative interior k≈16 을 포함하지 못한다
18   k=16 과 그 이후의 interior point 를 포함한다
24   historical planning evidence 상 추가 정보 대비 full-grid 비용이 크다
```

축은 **backbone 당 관측 수 k** 다. 균등 배분에서 `k = B/u` 이므로 unit 수가 5 든
10 든 같은 축이고, 그래서 5-backbone v1 격자의 관측을 10-backbone 설계로 옮길 수
있다.

동결 v1 격자에서 측정된 두 가지:

```
EFBC 포화       k=12 의 EFBC 가 k=24 값의 99.5%
                후보당 증가분 4→12 +0.0348 · 12→18 +0.0034 · 18→24 +0.0006
최대 차이 깊이   k=16 에서 allocation difference 가 가장 컸다
```

**k=16 을 "정책이 요구하는 깊이" 로 읽지 않는다.** historical v1 에서 가장 큰
allocation difference 가 관측된 informative interior depth 라는 뜻이고, 새
RFD3/BioEmu 코호트에서 16 이 최적이라는 것은 아직 모른다.

### 근거로 쓰지 않는 것

```
❌ abandon 도달 가능성
   v2 CoverageAction = probe_unit · advance_unit · stop · budget_exhausted ·
   execution_infeasible. **abandon 이 없다.** abandon_backbone 은 v1 profile 의
   action name 이고, 그것을 v2 후보 깊이 정당화에 쓰면 정책을 섞는 것이다.
❌ movability signal floor
   v1 profile 상수(0.2)이며 coverage mode 가 계산하는 양이 아니다.
❌ k=16 을 새 설계의 최적 깊이로 간주하는 것
```

### 7.2 격자 양 끝은 앵커다 — 둘 다 판정점에서 제외한다

**B=40 (warm-up 앵커).** 10 unit x 4 의무 probe = 40 이므로 adaptive 결정이 아직
한 번도 일어나지 않았다. static/equal 도 unit 당 4 를 준다. 차이는 후보 identity
의 확률적 변동뿐이다.

**B=180 (ceiling 앵커).** `B = u x N` 에서는 unit 당 상한이 N 이므로 어떤 배분도
모든 unit 에서 N 을 다 써야 한다. 정책은 지출을 포기할 수 있으므로 **매치하거나
손실만 가능하다.**

v1 격자가 이것을 보여준다. 두 끝점이 각각 warm-up 과 ceiling 이었고, 보고된 값이
`B=20 → −0.08` 과 `B=120 → −0.24` 였다. 후자에서 적응은 120 중 106.4 만 썼다.

```
두 앵커        보고한다. replay 정합성 확인으로 읽는다.
               adaptive-effect 판정점이 아니다.
primary 판정    60 - 160 의 6 점에서 한다.
```

이것을 미리 적어 두는 이유는, 앵커의 null 을 "효과 없음" 으로 보고하는 일을 막기
위해서다.

### 7.3 warm-up 4 — primary 로 유지하고, 한계를 명시한다

```
값        4 valid observations / backbone
근거      v1 continuity (V1_MIN_PROBE = 4)
          첫 배분 결정 시점의 posterior ESS 가 더 크다
          ESS = kappa_pool + n. n=3 은 kappa_pool=4 에서 ESS 7 (−12.5%),
          kappa_pool=0.5 에서 −22.2% 다.
```

**사전 지정 한계.** 첫 prefix 4 개의 tier 구성은 `30·50·70·30` = **2/1/1** 이다.
`q_b` 는 30/50/70 균형 혼합 위의 확률로 정의돼 있으므로, 첫 adaptive decision
시점의 관측 혼합은 그 정의와 다르다.

`backbone x tier` interaction 이 있으면 이 불균형이 **backbone 간 순위에도 영향을
줄 수 있다.** 상쇄된다고 가정하지 않는다 - 그것을 보장할 근거가 없고, tier 별
결과를 보고 확인하는 것은 금지다.

부수적으로: calibration LOTO 는 20 개 무작위 순서를 평균하므로 균형 혼합
estimand 를 추정하는데, confirmatory 는 고정 순서다. warm-up 4 에서는 k=4
prefix 에서만 어긋난다. 이 불일치도 한계로 기록한다.

### 7.4 warm-up 3 — 사전 등록된 secondary sensitivity

```
방법        같은 full-grid 를 warmup=3 으로 replay 한다
tier        prefix 1/1/1 로 정확히 균형이다
추가 AF2    0 - full-grid 를 어차피 생성하므로 폴딩이 늘지 않는다
보는 것      방향 일관성만
쓰지 않는 것  primary policy 변경 · GO/NO-GO 기준 · kappa 선택 · 격자 변경
```

**primary 를 바꾸지 않는다.** primary 는 warm-up 4 다. 이 분석은 2/1/1 prefix 가
결론의 방향을 만들었는지 보는 대조이고, 결과를 보고 primary 를 갈아타지 않는다.

### 7.5 이전 격자를 그대로 쓰지 않는 이유

이전 격자는 `1-24 + 30/40/50/60/80/100/120` 이었고 5-backbone ceiling 120 에
맞춰져 있었다. 1-24 구간은 10 unit 의 의무 probe 40 을 채우지도 못하고, 120 은
새 ceiling 180 의 3 분의 2 다.

검토 중 제안했던 `24 candidates / ceiling 240 / 격자 40-240` 은 **동결되지
않았다.** 24 의 근거가 `5x24=120` 이었으므로 10-backbone 설계에서 재사용할 수
없다는 지적을 받아 §7.1 로 다시 정했다.

## 8. MSA — target 수준 산출물이다

```
MSA 실행       target 당 1 회
공유           conservation mask 를 두 source 에 **동일하게** mapping
대상           calibration_v2 12 + confirmatory 12 = 24 타겟
threshold      변경 없음 (bio/a3m.py::msa_quality)
```

source 마다 MSA 를 다시 돌리지 않는다. 같은 타겟의 보존도는 backbone 생성기와
무관하다.

### 이미 시작된 pilot 의 처리

confirmatory 3 타겟 (`1j5uA01` · `1n81A00` · `1rdrA01`) 에 대한 MSA operational
pilot 이 이 문서 작성 전에 시작됐다. 중단하지 않고 결과도 버리지 않는다. 대신
**operational-only evidence 로 격리한다.**

```
쓸 수 있다   endpoint 가 살아 있는가 · 타겟당 wall time · A3M 이 비어 있는가
            usable_hits · median coverage · median depth · full_length_fraction
            msa_quality 경고

쓸 수 없다   target 선정 변경 · source 선정 변경 · candidate 수 변경
            threshold 변경 · tier 변경
```

pilot 결과가 나쁘면 **scientific threshold 를 그대로 두고 실행 방식만** 고친다.
"MSA 가 좋은 타겟만 고르는" 것은 금지다.

Step 3b 전체 MSA 는 이 문서가 `frozen` 이 된 뒤에 시작한다.

---

## 9. Mapping — source 마다 독립으로 검증한다

hard-fail contract 는 그대로다 (`rapid-v2-sequence-constraint-protocol-freeze.md`
§2). 바뀌는 것은 **경로가 둘이라는 것**이다.

```
RFD3
  query -> original -> staged -> RFD3 backbone -> fixed positions
  번호   RFD3 가 정체와 번호를 보존한다 (검증됨) → staged -> backbone 은 항등

BioEmu
  query -> original -> staged/normalized BioEmu structure -> fixed positions
  번호   **항등이 아니다.** BioEmu 출력은 서열 1..L 로 번호가 다시 매겨진다.
```

BioEmu 쪽 근거는 코드에 이미 있다. `pipeline.py` 는 BioEmu topology PDB 가
resseq 0 에서 시작할 수 있어서, 음수 resseq 가 없을 때 **strip 을 끄고
renumber_from_1 을 켠다** (`bioemu_zero_resseq_renumbered_from_1`). 즉 BioEmu
경로에서 원본 resseq 를 그대로 쓰면 전 위치가 밀린다.

### BioEmu provenance 검증 — 위치마다 남긴다

RFD3 와 같은 항목에 source 를 더한다.

```
source · query_pos · original_chain · original_resseq · original_icode
backbone_chain · backbone_resseq · aa · mapping_source · identity_ok
numbering_convention        rfd3: identity · bioemu: renumbered_from_1
```

### BioEmu 에 추가되는 hard fail

BioEmu 는 서열을 바꾸지 않는 conformational sampler 이므로 **서열 동일성이
정확히 성립해야 한다.** 성립하지 않으면 잘못된 구조를 받은 것이다.

```
BioEmu 구조 서열 != 입력 서열                        → 실패
BioEmu 잔기 수 != 입력 길이                          → 실패
사슬이 둘 이상                                       → 실패
번호가 1..L 연속이 아님                              → 실패
renumber 가 적용됐는데 detail 이 기록되지 않음        → 실패
```

**조용한 마스크 축소 금지는 두 source 에 똑같이 적용된다.** 대응되지 않는 query
위치가 하나라도 있으면 실패시킨다.

---

## 10. Calibration 과 kappa — source 별 독립

```
격자          kappa_pool ∈ {0.5, 1, 2, 4, 8, 16, 32}   (두 source 동일)
             mu0 0.05..0.95 step 0.05 · kappa0 동일 7 격자
절차          LOTO predictive log likelihood, 타겟 동일 가중
             → 기존 §7 그대로
식별 판정      기존 §9 세 조건 그대로, **source 마다 독립 적용**
동률          작은 kappa
```

```
kappa_RFD3    identified / not identified
kappa_BioEmu  identified / not identified
```

**한 source 가 실패했다고 다른 source 의 kappa 를 빌려 쓰지 않는다.** source 별
미식별이면 그 source 의 confirmatory RAPID 은 BLOCKED 이고, 다른 source 는
자기 판정대로 진행한다.

네 가지 결과가 모두 가능하고 각각 보고 가능한 결론이다.

```
둘 다 식별       두 source 에서 confirmatory 진행
RFD3 만          RFD3 confirmatory 진행 · BioEmu BLOCKED
BioEmu 만        BioEmu confirmatory 진행 · RFD3 BLOCKED
둘 다 미식별      Phase 4B BLOCKED 유지 · Phase 5 NO-GO 유지
```

이번 설계가 식별에 유리한 이유: source 당 12 타겟 x 10 형제 backbone 이므로
한 타겟 안의 형제가 10 개다. 기존 코호트는 5/4/2 였다. `kappa_pool` 이
요구하는 것이 정확히 형제 구조이므로, 표본이 아니라 **설계**가 개선된다.

**calibration 단계에서 EFBC 를 계산하지 않는다.** 두 source 모두.

---

## 11. Confirmatory endpoints — source 마다 한 번씩

각 source 에서 독립적으로:

```
primary      EFBC@B
guardrail    yield ratio (RAPID / comparator) · 단측 95% 하한 >= 0.90
comparator   같은 예산의 static/equal (primary)
             frozen structural-yield RAPID (필요할 때 secondary)
bootstrap    target-clustered
채택          EFBC 개선 CI 가 0 제외 AND yield 하한 >= 0.90
informative  endpoint 별 집합 (coverage / yield 따로) · 최소 클러스터 8
판정점        B = 60 · 80 · 100 · 120 · 140 · 160  (§7.2)
             B=40 · 180 은 앵커이므로 판정에 쓰지 않는다
```

**합치지 않는다.**

```
❌ RFD3 success + BioEmu success → 하나의 p-value / CI
❌ 두 source 를 합친 EFBC
✅ source 별 판정 2 개
```

### cross-source secondary — 두 source 가 끝난 뒤

```
cross-generator consistency   방향이 같은가
effect-size comparison        크기가 얼마나 다른가
source heterogeneity          타겟별로 어느 source 가 이득을 보는가
```

**EFBC 는 unit 수에 스케일이 걸린다** (상한 = unit 수). 두 source 의 unit 수가
다른 타겟이 생길 수 있으므로, cross-source 비교는 raw EFBC 로 하지 않는다.
사전 지정:

```
보고한다   ΔEFBC (source 내부 비교 - 여기서는 comparator 도 같은 unit 수다)
보고한다   EFBC / u  (정규화, cross-source 비교용)
하지 않는다 서로 다른 u 의 raw EFBC 를 같은 축에서 비교
```

secondary 는 **secondary 다.** 여기서 나온 방향으로 primary 를 바꾸지 않는다.

---

## 12. coverage_unit 의 source 별 지위 — BioEmu 에는 아직 근거가 없다

`coverage_unit = backbone_id` 는 M1 에서 나왔고, **M1 은 RFD3 backbone 60 개로만
돌렸다.** BioEmu 에 같은 결론을 그대로 옮길 근거가 없다.

이유가 있다. BioEmu backbone 은 native 서열의 conformational ensemble 표본이고,
2.0 A 수용 게이트를 통과한 것만 남는다. 즉 **설계상 서로 가깝다.** RFD3
local_diversify 표본과 같은 분산 구조라고 가정할 수 없다.

그래서 BioEmu confirmatory 전에 **M1-BioEmu 구조 진단**을 요구한다.

```
입력      calibration_v2 의 BioEmu backbone (120 개 목표)
계산      타겟 내 쌍별 RMSD · linkage x 임계값 안정성 (M1 과 같은 절차)
쓰는 것    구조뿐. joint-pass · SoluProt · pLDDT · yield 는 쓰지 않는다
결론      backbone 보다 나은 안정적 unit 이 있는가 / 없는가
```

이것은 outcome 을 보지 않으므로 selection 을 만들지 않는다. 구조 진단이다.

결과에 따라:

```
안정적 중간 unit 이 없다   → BioEmu 도 coverage_unit = backbone_id (RFD3 와 동일)
있다                    → 그 unit 을 BioEmu profile 에 동결하고 이유를 남긴다
전부 한 클러스터로 붕괴    → BioEmu 에서 EFBC 는 coverage 를 재지 못한다.
                          그 사실을 보고하고 BioEmu primary 를 재검토한다.
```

세 번째가 실제로 가능하다는 것이 이 절의 요점이다. 미리 적어 두지 않으면
나중에 EFBC 가 낮게 나왔을 때 그것을 "정책이 나쁘다" 로 읽게 된다.

---

## 13. 총 계산량 — 검산

```
per source, per target
  calibration    10 backbone x 12 candidate =   120
  confirmatory   10 backbone x 18 candidate =   180   (= ceiling)
  warm-up        10 backbone x  4 valid     =    40

calibration    12 x 10 x 12       = 1,440 / source
                                  x 2 source = 2,880
confirmatory   12 x 10 x 18       = 2,160 / source
                                  x 2 source = 4,320
                                  ------------------
합계                                           7,200

MSA            24 타겟 x 1 회 = 24
backbone 생성   (12 + 12) 타겟 x 10 x 2 source = 480
```

AF2 비용 (측정 적합 `elapsed_s = 2.890344 x length^0.748`, 4 점이므로 자릿수
비교용):

```
confirmatory   두 source 합 약 177.8 GPU-시간
calibration    두 source 합 약 118.6 GPU-시간 (근사 - 타겟 미선정)
```

technical failure 는 `B_eval` 과 biological posterior update 에 포함하지 않는다
(기존 contract 유지). 즉 7,200 은 **evaluable candidate outcome** 수이고 시도
횟수가 아니다.

## 14. 검토가 필요한 결정 — 승인 전까지 동결 아님

plan JSON `review_required` 와 같다.

```
1. BioEmu 유한 생성 규칙 (num_samples 50 / max_attempted 200 / accepted 10)
2. RFD3 max_attempts_per_target 40
3. B=40 warm-up anchor 와 B=180 ceiling anchor 를 primary 판정에서 제외하는 것
4. unit 수가 10 미만일 때의 non-evaluable 규칙
5. BioEmu 에 coverage_unit 을 적용하기 전 M1-BioEmu 구조 진단 요구
6. confirmatory 18/backbone (6/6/6) · warm-up 4 · 격자 40-180 · 총 7,200
```

1·2 는 "유한 생성 규칙을 먼저 동결하고 처음부터 생성한다" 는 기존 판단을
이번에 실제로 이행하는 것이다. 3·4 는 예산 격자와 후보 수가 어긋난 전례를
반복하지 않기 위한 것이다. 5 는 RFD3 근거를 BioEmu 에 전이하지 않기 위한 것이다.
6 은 검토에서 24 의 근거(`5x24=120`)가 10-backbone 설계에서 무효라는 지적을 받아
다시 정한 것이다.

---

## 15. 실행 순서

```
 0. 현재 실행 pause                        ← MSA pilot 은 operational-only 로 격리
 1. branch / state audit                   ← 완료
 2. 이 문서 + plan JSON 작성                ← 완료 (검토 대기)
 3. tests 업데이트 · 전체 suite 실행         ← 완료
 4. v1 hash 27/27 확인                     ← 완료 (commit c230360da9c2)
 5. freeze commit + push                   ← 승인 후
 6. calibration_v2 타겟/예비 선정 + 커밋
 7. MSA (24 타겟)
 8. mapping validation (RFD3 · BioEmu 독립)
 9. calibration backbone 생성 (RFD3 10 · BioEmu 10, 12 타겟)
 9b. M1-BioEmu 구조 진단
10. calibration candidate 생성 + 폴딩 (2,880)
11. kappa_RFD3 · kappa_BioEmu 각각 식별 판정
12. source 별 GO / STOP
13. confirmatory backbone 생성 (RFD3 10 · BioEmu 10, 12 타겟)
14. generation checkpoint
15. confirmatory 폴딩 (4,320)
16. RFD3 결과 판정 **1 회**
17. BioEmu 결과 판정 **1 회**
18. cross-source secondary
19. manuscript update
```

11 에서 두 source 모두 미식별이면 13 이후로 가지 않는다.
16·17 은 각각 한 번이다. 다시 돌리지 않는다.

---

## 16. 원고에 들어갈 문장 — 여기 대기시킨다

`docs/manuscript.md` 와 `docs/results_of_record.md` 는 **v1 freeze manifest 의
27 개 해시에 들어 있다.** 두 파일을 고치면 `42_freeze_v1_results.py --verify`
가 27/27 을 잃는다. 그래서 문장을 여기 적어 두고, 적용은 별도 결정으로 남긴다.

적용하려면 manifest 를 의도적으로 재발행해야 한다 - 이전 digest 와 새 digest 를
함께 기록하고, **표에 고정된 수치가 하나도 바뀌지 않았음을** 확인한 뒤에.
조용히 다시 해시하지 않는다.

**적용 시점은 v2 validation 이 끝난 뒤다.** 지금 27/27 을 깨면서 manifest 를
재발행할 이유가 없다. v2 결과가 나오면 그 결과와 함께 원고를 한 번에 고치고,
그때 manifest 를 재발행한다.

### Limitations 에 추가할 문단 (영문, 그대로 붙인다)

> Two further scope limits follow from the protocol rather than from the sample
> size. The prospective v1 validation used an unmasked ProteinMPNN candidate
> distribution and therefore did not directly validate transfer to the default
> three-tier conservation-masked deployment pipeline. It also drew every
> diversified backbone from a single generator: of the 1,728 completed folds,
> 1,440 come from RFD3 backbones and 288 from the native backbone, and only the
> RFD3 cohort served as an allocation unit, so the allocation result is specific
> to an RFD3 backbone distribution and does not establish that adaptive
> allocation transfers to backbones drawn from a conformational-ensemble
> sampler. A multi-source protocol, frozen before execution, addresses both: it
> runs the masked deployment protocol on a fresh unseen holdout and treats RFD3
> and BioEmu as independent backbone-source cohorts with separate posteriors,
> separate pooling hyperparameters, and one decision per source, so that no
> reported effect is pooled across generators. No outcome of that protocol is
> claimed here.

첫 문장은 이전 동결 (`sequence-constraint-protocol-freeze.md` §7) 이 원고에 넣기로
한 문장이고, 아직 들어가지 않았다. 두 번째가 이번에 추가되는 것이다.

### results_of_record 에 추가할 기록

`holdout_grid/af2_order_metric.csv` 의 `backbone_source` 열에서 직접 나온다.

| source | 폴드 | 구성 |
|---|---|---|
| `rfd3` | 1,440 | 타겟 12 x 백본 5 x 서열 24 |
| `target` (native) | 288 | 타겟 12 x 백본 1 x 서열 24 |
| 합 | 1,728 | 전부 `status=ok` |

배분 결과는 `rfd3` 코호트에서 나왔다. native 폴드는 같은 격자에 있지만 배분
단위로 쓰이지 않았다. **1 차 결과는 단일 생성기 분포에 대한 것**이고, source
자체를 주장하려면 별도 arm 이 필요하다 - 이 문서가 그것이다.

---

## 17. 이 문서로 하지 않는 것

```
masked_holdout_targets.json 수정
기존 freeze 문서 삭제 또는 내용 rewrite
rapid_structural_v1 태그 이동
select_fixed_atoms 변경
altLoc 전처리 변경
BioEmu target_rmsd_cutoff 완화
joint-pass 임계값 변경
MSA threshold 변경
결과를 보고 tier · 마스크 · 예산 격자 조정
두 source 를 합친 판정
```
