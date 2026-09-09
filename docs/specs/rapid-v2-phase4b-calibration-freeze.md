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

```
12 targets × 5 RFD3 backbones × 8 sequences = 480 folds
```

계층 구조를 확증 코호트와 맞춘다 - 타겟 12, 타겟당 RFD3 5 개. 서열은 8 개로
줄여 비용을 억제하되 arm 별 비율을 추정할 최소 depth 는 확보한다.

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
```

선정은 결정적이다. seed 와 규칙을 이 문서와 함께 커밋하고, 산출된 타겟 목록도
폴딩 전에 커밋한다.

## 4. backbone 선정 — 결과를 보고 고르지 않는다

```
❌ RFD3 생성 후 구조가 예쁜 것을 고른다
❌ yield 를 보고 고른다
✅ 동결된 생성/seed 규칙으로 만든 것을 순서대로 전부 쓴다
```

holdout 과 같은 생성 경로를 쓴다 (`25_generate_holdout_backbones.py` 의
전처리와 `stop_after/start_from="rfd3"`). 타겟당 5 개를 만들고 5 개를 전부
쓴다. 수용 게이트(2.0 Å target-RMSD)를 통과하지 못해 5 개를 못 채우면 그
타겟은 동결된 교체 규칙으로 예비에서 대체하고, 결과를 보고 빼지 않는다.

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
모든 타겟에 대해 합한다
```

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

```
(1) 판별력   kappa_pool 프로파일에서 LL(최선) - LL(최악) >= 2.0
             (우도비 e^2. 이보다 평평하면 데이터가 구분하지 못한다)

(2) 내부 최대 argmax kappa_pool 이 격자 경계(0.5 또는 32)가 아니다
             경계면 격자가 좁았다는 뜻이고 그 값을 채택하지 않는다

(3) 안정성   타겟 클러스터 부트스트랩 1,000 회에서, argmax 가 점추정의
             한 칸 이내에 드는 비율 >= 60%
```

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
