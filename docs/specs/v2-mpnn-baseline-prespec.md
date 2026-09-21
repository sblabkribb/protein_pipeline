# v2 코호트에서의 ProteinMPNN 기준선 비교 — 실행 전 사전지정

> **상태: 실행 전 동결.** 이 문서가 커밋된 뒤에 분석을 돌린다. 여기 적힌 값을
> 결과를 보고 바꾸지 않는다. 바꿔야 하면 버전을 올리고 이유를 남긴다.

작성 2026-09-21. 대상 분석: `scripts/benchmark/33_v2_mpnn_baseline.py`(아직 없음).

---

## 1. 왜 하는가

현행 연구노트의 핵심 결과 — **표적별 대리모델(RF)이 같은 총예산에서 ProteinMPNN
점수 기준선과 구별되지 않는다** — 는 holdout 격자의 **11 표적 · RFD3 단독**에
근거한다. 노트 스스로 두 한계를 적고 있다.

```
n = 11 · 단일 코호트 · 단일 생성원
RF-MPNN 이 양수인 표적 3/11, LOTO 에서 두 표적 제외 시 평균의 부호가 뒤집힘
```

67 표적 CATH pilot 으로 확장하려 했으나 설계 백본이 8 개만 남아 불가능했다.
**그런데 v2 다중생성원 캠페인의 자료는 이 제약이 없다.**

```
후보 5,328 · joint-pass 라벨 5,327 · 고유 백본 357
백본 PDB 가 후보마다 기록돼 있고 5,328 건 전부 디스크에 존재
생성원 2 개 (RFD3 · BioEmu)
```

**새 folding 은 0 회다.** 필요한 것은 MPNN 채점과 ESM 임베딩뿐이다.

## 2. 동결 계획과의 관계 — 무엇을 하지 않는가

v2 는 `multisource_validation_plan.json` 으로 동결돼 있다. 이 분석은 **후보 선택
축**이며 그 계획의 종점을 건드리지 않는다. 명시적으로 하지 않는 것::

```
EFBC 를 계산하지 않는다
백본 수준 배분 정책을 비교하지 않는다
동결된 kappa 식별 판정(rfd3 NOT_IDENTIFIED / bioemu IDENTIFIED)을 바꾸지 않는다
confirmatory 평가가능성 판정(BLOCKED / NOT_EVALUABLE)을 바꾸지 않는다
**생성원을 합치지 않는다** (plan.endpoints.pooling_across_sources_forbidden)
confirmatory 주장이나 coverage 결론을 내지 않는다
```

`phase4b-calibration-freeze.md` §14 가 calibration 코호트에 대해 금지한 것은
policy 비교 · EFBC · coverage 결론 · confirmatory 주장이다. 본 분석은 그 어느
것도 아니며, `30_epsilon_band_selection.py`(선택 규칙)와
`29_orthogonal_fold_check.py`(예측기 교차확인)가 holdout 격자에 적용된 것과 같은
**별도 평가축**이다.

## 3. 코호트 구성

### 3.1 포함 기준 (사전 규칙)

```
pool >= 50            학습 30 + 평가 20 이 필요하다
0 < joint-pass 율 < 1  전원 통과 또는 전원 실패면 어떤 정책도 같은 값을 얻는다
```

실측 결과 **29 target x source** 가 남는다.

| 코호트 | 생성원 | 포함 | 제외와 사유 |
|---|---|---|---|
| calibration_v2 | BioEmu | 8 | `3ksnA00` 전원통과 |
| calibration_v2 | RFD3 | 7 | `3ksnA00` 전원통과 · `6wvfA01` 전원실패 · `1pp1X02`(12) · `4q68A01`(24) pool<50 |
| confirmatory | BioEmu | 6 | `4wexA00` 전원통과 |
| confirmatory | RFD3 | 8 | `1o22A00`·`1rdrA01`·`2w2sA00` 전원실패 |

### 3.2 코호트 합산 — 생성원 안에서만

주 분석은 **생성원별로 두 코호트를 합쳐** 표적 수를 확보한다 (RFD3 15 ·
BioEmu 14). 합치는 이유는 표적 수뿐이고, 동결 종점을 계산하지 않으므로
calibration/confirmatory 의 역할 구분을 침해하지 않는다. **생성원은 절대 합치지
않는다.** 코호트를 분리한 결과를 민감도로 함께 보고한다.

### 3.3 백본 전처리 — BioEmu 의 resseq 0

RFD3 백본 198 개는 CA 수가 설계 서열 길이와 정확히 같다. BioEmu 백본 159 개는
`strip_nonpositive_resseq=True` 에서 1 잔기 짧아지는데, **원인은 BioEmu 가
resseq 를 0 부터 매기기 때문이고 원본 CA 수는 서열 길이와 같다**(실측: 원본 50,
resseq 0..49, 서열 50). 따라서 이 분석은 `strip_nonpositive_resseq=False` 로
읽는다. MPNN score 는 백본 조건부 likelihood 이므로 잔기 하나가 빠지면 조건이
달라진다.

## 4. 프로토콜 — 새로 만들지 않는다

`31_fewshot_jointpass_transfer.py` 의 `baselines_budget` 과 같다.

```
초기 표본       k-means 30 (_selection.select_train_indices)
RF              RandomForestRegressor(n_estimators=100), 표준화 없음
Ridge           Ridge(alpha=1.0) + StandardScaler
MPNN score      per-residue mean NLL, **낮을수록 좋다** -> 오름차순 선택, 라벨 0 개
무작위 / oracle  31_ 과 동일
표현            esm2_t6_8M_UR50D 320 차원 평균 풀링
seed            42 · 123 · 7 · 2024 · 31337
예산 격자       40 · 60 · 80 · 100 (노트와 동일). pool < B 인 표적은 그 B 에서 빠진다
종점            joint-pass = pLDDT>=85 AND 비루프 Cα-RMSD<=2.0 Å AND SoluProt>=0.5
                probe 가 찾은 통과 후보도 수익에 센다
구간            표적 클러스터 부트스트랩 2,000 회 · percentile 95% · seed 20260921
다중성          4 예산점 Bonferroni(98.75%) 와 대비 합산(99.375%) 을 함께 보고
```

## 5. 사전에 정해 두는 해석 규칙

```
구간이 0 을 포함하면   "구별되지 않았다" 로 쓴다. 동등성·비열등성이 아니다.
                       "A 가 B 보다 낫다/못하다" 로 쓰지 않는다.
생성원 간 비교         RFD3 결과와 BioEmu 결과를 하나의 통계량으로 합치지 않는다.
                       두 생성원에서 같은 방향이면 "일관" 으로, 갈리면 "생성원
                       의존" 으로 쓴다. 어느 쪽이든 보고한다.
배수 표현              쓰지 않는다. 라벨 비용이 빠진 비율이다.
```

## 6. 예상되는 결과와 그 처리

```
두 생성원 모두 무승부   현행 결론이 29 target x source 로 강화된다
두 생성원 모두 RF 우위  현행 결론을 뒤집는다. 노트를 개정한다
생성원마다 갈림         그 자체가 결과다. "생성원 의존" 으로 보고하고
                        어느 쪽도 일반 결론으로 쓰지 않는다
```

**어느 쪽이 나와도 보고한다.** 결과를 보고 포함 기준·예산 격자·해석 규칙을 바꾸지
않는다.

## 7. 하지 않는 것

- 새 folding 을 하지 않는다.
- 전원통과/전원실패 표적을 포함시키려고 문턱을 바꾸지 않는다.
- pool < 50 인 표적을 넣으려고 초기 라벨 수를 줄이지 않는다.
- 생성원을 합치지 않는다.
- holdout 격자의 기존 11 표적 결과를 이 결과로 덮어쓰지 않는다. 별도 코호트다.
