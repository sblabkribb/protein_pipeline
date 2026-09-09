# Phase 4B — joint-pass posterior calibration 동결

**상태: 폴딩 전 동결.** 이 문서가 커밋된 뒤에 데이터를 만든다. 여기 적힌 값을
결과를 보고 바꾸지 않는다 - 바꿔야 하면 버전을 올리고 이유를 남긴다.

배경: `docs/specs/rapid-v2-phase4b-calibration-audit.md`.
`κ_pool` 은 정책 선택을 뒤집는 변수인데 (2 와 4 사이에서 argmax 가 바뀐다)
기존 미선별 데이터에는 형제 backbone 이 없어 식별되지 않고, 형제가 있는
데이터는 yield 로 선별돼 있다. 그래서 새 코호트를 만든다.

---

## 1. 무엇을 정하는가

```
mu0         backbone 하나의 joint-pass 사전 평균
kappa0      그 사전분포의 세기 (타겟 간 분산)
kappa_pool  형제 backbone 이 서로를 알려주는 세기
```

**셋을 같은 population 에서 정한다.** panel1 로 `mu0`·`kappa0` 만 정하면
native → RFD3 전이 가정이 남는다. 새 코호트는 RFD3 이므로 그 약점이 없다.

panel1 은 이후 `native-backbone calibration sensitivity` 로만 쓴다.

## 2. 코호트 설계

계획은 `12 × 5 × 8 = 480` 이었다. 생성 결과 수용 게이트에서 세 타겟이 5 개를
채우지 못했고, **코호트를 수선하지 않고 확보된 것을 그대로 쓴다.**

```
9 targets × 5 backbones
1 target  × 4 backbones   (2mq6A00)
1 target  × 2 backbones   (5nazA00)
------------------------------------
11 informative targets · 51 RFD3 backbones · 8 sequences = 408 folds

2r01A02   수용 backbone 0 개
          → CALIBRATION_GENERATION_INFEASIBLE
          → hyperparameter 우도에 기여하지 않는다
          → cohort flow 에는 그대로 기록한다
```

### 왜 추가 생성도 complete-case 도 하지 않는가

```
어려운 세 타겟에만 생성을 더 준다
  → 게이트 결과를 본 뒤 그 타겟에만 기회를 주는 것이다.
    joint-pass 를 안 봤어도 코호트 구성이 관측된 생성 결과에 반응한다.

5/5 를 채운 9 타겟만 쓴다
  → generation-feasibility complete-case selection 이다.
    RFD3 생성이 쉬운 타겟 쪽으로 calibration population 이 치우친다.
```

`kappa_pool` 이 요구하는 것은 **한 타겟 안에 형제가 둘 이상 있는 것**이지 모든
타겟이 정확히 5 개를 가질 것이 아니다. 4 개와 2 개 집단도 between-backbone
변이에 정보를 준다. 버릴 이유가 없다.

### 2r01A02 를 기록하는 방식

조용히 지우지 않는다.

> 사전 선정한 calibration 타겟 12 개 중 하나는 최초 생성 실행에서 동결된 생성
> QC 를 만족하는 backbone 을 하나도 내지 못했고, 따라서 사후분포 보정에 평가
> 가능한 형제 context 를 제공하지 않았다.

**joint-pass 실패도 생물학적 실패도 아니다.** RFD3 가 15 개를 만들었고 2.0 Å
게이트가 15 개를 전부 기각했다.

### 12 × 5 를 굳이 유지하려면

세 타겟만 더 돌리는 것이 아니라, **12 개 전체에 대해 유한 생성 규칙을 먼저
동결하고 처음부터 다시 생성**해야 한다 (예: "타겟마다 최대 N 개의 결정적 RFD3
제안 중 QC 를 통과한 첫 5 개를 쓴다"). 현재 규모에서는 거기까지 하지 않는다.

## 3. 타겟 선정 — 적격성과 길이만

```
포함 기준
  단일 사슬 · 길이 50-400 (holdout 과 동일)
  길이 층 4 / 4 / 4  (50-150 · 150-250 · 250-400)

제외
  confirmatory holdout 12 타겟
  holdout 의 selected / reserve / resolved 전부
  panel1 · panel2 에 쓰인 타겟
  위 타겟들의 superfamily (근접 중복 방지)

선정에 쓰지 않는 것
  과거 yield · SoluProt 결과 · structural-success 결과 · joint-pass 결과
  Gate 0 사전분포 점수
  **legacy `rapid_target_manifest.csv` 의 `eligible` 열**
```

마지막 항목이 중요하다. 그 manifest 는 옛 길이 기준을 쓰고 있어서 이번 코호트의
정상 타겟도 `eligible=False` 로 적혀 있다 - 실제로 `1y8aA02(313)`,
`4poaA02(309)`, `4y07A01(333)` 셋이 그렇다. 적격성은 PDB 를 직접 읽어 이 문서의
기준(단일 사슬 · 50-400 · 층 50-150 / 150-250 / 250-400)으로 **독립 판정**한다.
테스트가 이것을 지킨다.

선정은 결정적이다. seed 와 규칙을 이 문서와 함께 커밋하고, 산출된 타겟 목록도
폴딩 전에 커밋한다.

## 4. backbone 선정 — 결과를 보고 고르지 않는다

```
❌ RFD3 생성 후 구조가 예쁜 것을 고른다
❌ yield 를 보고 고른다
✅ 동결된 생성/seed 규칙으로 만든 것을 순서대로 전부 쓴다
```

holdout 과 같은 생성 경로를 쓴다 (`25_generate_holdout_backbones.py` 의
전처리와 `stop_after/start_from="rfd3"`). 타겟당 5 개를 만들고 5 개를 전부 쓴다.

**순위는 사전 동결된 생성 순서다.** RFD3 결과를 보고 구조 품질 점수로 5 개를
고르면 그 순간 selection 이 다시 들어온다.

```
✅ 동결된 seed 의 생성 순서대로 앞에서 5 개
❌ 생성 후 구조 점수로 상위 5 개
❌ 생성 후 yield 로 5 개
```

수용 게이트(2.0 Å target-RMSD)를 통과하지 못해 5 개를 못 채우면:

```
1. 같은 타겟에서 동결된 seed 로 생성을 이어가 5 개를 채운다
2. 그래도 못 채우면 그 타겟은 calibration generation-infeasible 로 표시한다
```

**타겟을 바꾸지 않는다.** 이번 동결에는 타겟 수준 예비 교체 trigger 가 없다 -
`calibration_targets.json` 의 `reserve` 6 개는 생성 시작 전에 타겟이 아예 준비
되지 않은 경우(파일 부재 등)에만 rank 순서로 쓰고, **생성 결과를 본 뒤에는
쓰지 않는다.** 결과를 보고 타겟을 바꾸면 그 코호트는 더 이상 미선별이 아니다.

generation-infeasible 타겟이 생기면 그 수를 보고하고, 남은 타겟만으로 §9 를
판정한다.

## 5. 생성·평가 설정 — holdout 과 동일

```
temperature            0.1 (단일 조건)
ProteinMPNN            use_soluble_model · v_48_020 · seed 0 · batch 1
구조 검증               ColabFold, holdout 과 같은 preset
지표                    rmsd_nonloop_order (gate0_structural_v1)
joint-pass             pLDDT >= 85 AND rmsd_nonloop_order <= 2.0 AND soluprot >= 0.5
```

임계값은 캠페인 이전에 정해진 값이고 여기서 다시 고르지 않는다.

## 6. 모형 — v1 과 같은 함수 형태

```
타겟 수준     Beta(mu0·kappa0, (1-mu0)·kappa0), 그 타겟의 모든 관측으로 갱신
backbone 사전  Beta(m_t·kappa_pool, (1-m_t)·kappa_pool),  m_t = 타겟 사후 평균
backbone 사후  + 그 backbone 자신의 관측
다음 결과 예측  backbone 사후 평균
```

새 분포족을 발명하지 않는다. 현재 generic Core 가 표현할 수 있는 형태를
유지하고 hyperparameter 만 이 데이터에서 정한다.

## 7. 선택 기준 — 확률 예측 품질만

```
primary     target-held-out predictive log likelihood (LOTO)
secondary   Brier score · calibration error (진단용, 선택에 쓰지 않는다)
```

LOTO 절차:

```
각 타겟 t 를 통째로 뺀다
남은 타겟으로 hyperparameter 를 평가한다
t 의 관측을 동결된 무작위 순서로 하나씩 넣으면서,
  넣기 직전의 backbone 사후 평균 p 로 그 관측의 로그 확률을 더한다
  joint-pass 면 log p, 아니면 log(1-p)
순서 의존을 줄이려고 타겟마다 20 개 순서를 평균한다 (seed 동결)

**타겟마다 예측 개수로 나눈다** (타겟별 평균 로그 우도)
전체 점수 = 타겟별 정규화 LL 의 **동일 가중 평균**
```

### 왜 합이 아니라 타겟 동일 가중인가

원래 설계 `12 × 5 × 8` 은 모든 타겟이 40 관측이라 **단순 합산이 곧 타겟 동일
가중**이었다. 지금은 backbone 이 5 / 4 / 2 로 불균형하므로 그냥 더하면
5-backbone 타겟이 2-backbone 타겟보다 2.5 배 큰 영향을 준다.

정규화는 결과를 유리하게 만들려는 변경이 아니라, **균형 설계에 암묵적으로
있던 target-equal estimand 를 불균형 코호트에서도 보존하는 수정**이다.

부트스트랩도 타겟 클러스터 단위이므로 같은 가중을 쓴다.

이 절차가 정책이 실제로 쓰는 방식과 같다 - 온라인으로 하나씩 관측하며 다음을
예측한다.

**선택 기준으로 쓰지 않는 것:**

```
EFBC · coverage uplift · v2 vs static · yield uplift
```

**calibration 단계에서 EFBC 를 계산하지 않는다.** 계산하는 순간 policy
tuning 이다.

## 8. 탐색 격자

```
mu0         0.05 부터 0.95 까지 0.05 간격 (19)
kappa0      0.5, 1, 2, 4, 8, 16, 32
kappa_pool  0.5, 1, 2, 4, 8, 16, 32
```

`kappa_pool` 탐색 격자를 민감도 격자 `{1,2,4,8,16}` 보다 넓게 잡은 것은
§9 의 내부 최대 조건을 판정할 수 있게 하기 위해서다.

## 9. 식별 판정 — 세 조건 모두 충족해야 한다

**이 절은 코호트가 11 타겟으로 바뀐 뒤에도 그대로다.** 타겟이 줄면 (3) 을
넘기가 어려워지지만 임계값을 낮추지 않는다. 못 넘으면 `NOT_IDENTIFIED` 이고,
그것이 결과다.

```
(1) 예측 분리력
    kappa* = 점추정 argmax
    kappa* 에서 두 칸 이상 떨어진 모든 kappa 에 대해
      Δ(kappa) = LOTO-LL(kappa*) − LOTO-LL(kappa)
      의 타겟 클러스터 부트스트랩 단측 90% 하한 > 0

(2) 내부 최대
    kappa* ∉ {0.5, 32}

(3) 부트스트랩 안정성
    타겟 클러스터 부트스트랩 1,000 회 중, argmax 가 kappa* 의
    ±1 칸 안에 드는 비율 >= 0.80
```

### (1) 을 이렇게 쓰는 이유

`LL(최선) − LL(최악) >= 2.0` 은 방어하기 어렵다. 최악이 0.5 나 32 같은 극단에
있으면 가운데 여러 kappa 가 사실상 구분되지 않아도 통과하고, 2.0 이라는 값도
LL 을 합으로 보는지 평균으로 보는지에 따라 뜻이 달라진다.

지금 형태는 **"정확히 한 격자점을 맞혔는가" 가 아니라 "적어도 factor-2 이내
까지는 구분할 수 있는가"** 를 묻는다. 격자가 0.5·1·2·4·8·16·32 이므로
kappa*=4 라면 2·4·8 은 같은 근방으로 허용하고, 0.5·1·16·32 는 예측 점수에서
실제로 열등하다는 증거를 요구한다.

### (3) 의 0.80 은 통계적 임계값이 아니다

이론에서 나온 수가 아니라 **운영 게이트**다. "confirmatory primary policy 로
채택하려면 적어도 이 정도의 재표집 안정성을 요구한다" 는 뜻이다. 0.60 이면
부트스트랩의 40% 가 factor 4 이상 떨어진 값을 골라도 안정이라 부르게 되는데,
kappa_pool 하나 때문에 Phase 4 전체가 막혀 있고 배분 방향까지 뒤집히는
상황에서는 느슨하다.

### 동률 처리 — 작은 kappa 를 고른다

LOTO-LL 이 같으면 **더 작은 kappa** 를 고른다. 같은 예측 지지라면 형제 간
차용을 덜 하는 쪽이 보수적이고, 과도한 pooling 을 피한다. 이 규칙도 사전
지정이다.

## 10. 식별되지 않으면 — 미리 정해 둔다

세 조건 중 하나라도 실패하면 **억지로 하나를 골라 holdout 으로 넘어가지
않는다.** 그 자체가 결과다.

> available development evidence is insufficient to identify the
> between-backbone pooling strength required by the coverage policy.

그 경우:

```
Phase 4B      BLOCKED 유지
kappa_pool=4  confirmatory primary 가 아니라 제한된 continuity analysis
              (exploratory / secondary) 로만 의미를 갖는다
Phase 4       acquisition 잠금 유지
Phase 5       NO-GO 유지
```

**결과를 보고 자연스럽게 (b) 로 갈아타 primary 로 만들지 않는다.**

## 11. 민감도 격자의 용도

```
kappa_pool ∈ {1, 2, 4, 8, 16}
```

이것은 **robustness 분석**이지 선택 도구가 아니다. primary 는 §7 의 기준으로
정하고, 민감도는 그 결론이 격자 안에서 얼마나 흔들리는지 보고하는 데만 쓴다.

holdout EFBC 가 가장 좋은 kappa 를 고르는 것은 금지다.

### 2 차 민감도 — 9 complete targets only

5/5 를 채운 9 타겟만으로 같은 절차를 돌린 결과를 **secondary sensitivity** 로
함께 보고한다. primary(11 타겟)와 같은 kappa* 근방을 지지하면 좋은 robustness
증거다.

**그 결과를 보고 primary 를 바꾸지 않는다.** primary 는 11 타겟이다.

## 12. 폴딩 전에 커밋할 것

```
이 문서
타겟 선정 규칙과 seed
산출된 타겟 목록 (12 + 예비)
생성 설정 (RFD3 · ProteinMPNN · 온도 · seed)
joint-pass 정의
분석 코드와 해시
선택 기준과 격자
식별 판정 규칙 (§9)
미식별 시 처리 (§10)
```

## 13. 동결 뒤 순서

```
1. calibration 실행 (EFBC 계산 없음)
2. 식별 판정 (§9)
3. 식별되면 mu0 · kappa0 · kappa_pool 동결 + 해시 기록
4. Phase 4 acquisition 잠금 해제
5. confirmatory holdout replay **한 번**
6. Phase 5 판단은 그 뒤
```

## 14. 이 코호트로 하지 않는 것

```
policy 비교
EFBC 계산
coverage 결론
holdout 재분석
confirmatory 주장
```

calibration 전용 코호트다. 여기서 나온 수치를 성능 주장으로 쓰지 않는다.
