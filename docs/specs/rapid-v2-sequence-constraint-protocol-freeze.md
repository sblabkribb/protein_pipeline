# RAPID v2 — sequence-constraint protocol 동결

**상태: 동결. 구현 전.** 이 문서가 커밋된 뒤에 MSA·서열 생성·폴딩을 시작한다.
여기 적힌 값을 결과를 보고 바꾸지 않는다 - 바꿔야 하면 버전을 올리고 이유를
남긴다.

## 왜 이 문서가 필요한가

audit 에서 확인된 사실:

```
PipelineRequest 기본값       conservation_tiers = [0.3, 0.5, 0.7]
                             ligand_mask_distance = 6.0
표준 실행 산출물              tiers/{30,50,70}/fixed_positions_check.json
26_holdout_grid.py           ProteinMPNNClient 를 직접 호출, fixed_positions 없음
```

**배포 경로는 3-tier masking 을 쓰는데 prospective 검증은 unmasked 였다.**
서로 같았던 것은 calibration 과 holdout 뿐이고, 둘 다 배포와 달랐다.

근거: `docs/specs/rapid-v2-phase4b-rfd3-protocol-audit.md`

---

## 1. Deployment protocol — 이것이 기준점이다

calibration 도 confirmatory 도 이 프로토콜을 따른다. 셋이 같아야 한다.

```
MSA
  MMseqs2 (기존 파이프라인 설정)
  msa_min_coverage        0.0   (기본값)

conservation
  conservation_tiers      [0.3, 0.5, 0.7]
  conservation_mode       quantile
  conservation_weighting  none
  cluster_method          linclust
  cluster_min_seq_id      0.9

fixed positions (서열 제약)
  conservation positions
    ∪ ligand 6 Å positions      (리간드가 있을 때만)
    ∪ manual fixed_positions_extra (요청에 있을 때만)
  ligand_mask_distance          6.0
  ligand_mask_use_original_target  true

ProteinMPNN
  model_name              v_48_020
  use_soluble_model       True
  sampling_temp           0.1
  seed                    0
  batch_size              1

joint-pass (변경 없음)
  pLDDT >= 85.0 AND rmsd_nonloop_order <= 2.0 AND soluprot >= 0.5
```

### 이번에 바꾸지 않는 것

```
RFD3 select_fixed_atoms   {A1: ALL} 위치 앵커 그대로
RFD3 partial_t            5.0
RFD3 mode                 local_diversify
altLoc 전처리              현재 그대로 (정리하지 않음)
```

`select_fixed_atoms` 가 과학적으로 옳은지는 여전히 미결이다. 다만 그것을 지금
바꾸면 **backbone 부터 전부 다시 만들어야** 하고, 이번 논문에서 검증할 수 있는
범위를 넘는다. RFD3 구조 보존 정책은 별도 후속 설계로 남긴다.

altLoc 도 같은 이유로 이번에 고치지 않는다. 고치면 기존 51 backbone 이 무효가
된다.

**즉 이번 변경은 서열 단계 이후에만 적용된다.** backbone 은 재사용한다.

---

## 2. Position-mapping contract

보존도 마스크는 원본 query 번호로, ProteinMPNN fixed position 은 backbone 잔기
번호로 표현된다. 그 사이에 번호가 세 번 바뀐다.

### 실측된 위험 (dry-run, `position_mapping_spike.json`)

```
원본 resseq 범위가 1 에서 시작하지 않는다
  4..187 · 513..657 · -2..310 · 492..865 · 25..249
  → 원본 resseq 를 그대로 쓰면 11 중 6 타겟에서 틀린다

전처리가 음수/0 resseq 를 버린다
  1j0tA00 앞 1 잔기 · 1y8aA02 앞 3 잔기
  → 서열 인덱스에도 오프셋이 생긴다

altLoc 이 있으면 CA 행 수 != 잔기 수
  1y8aA02 321/310 · 7o1zA01 236/225 · 5nazA00 228/226
  → CA 레코드를 세는 코드는 최대 11 위치 어긋난다
```

셋 중 하나만 틀려도 **마스크가 엉뚱한 잔기에 붙고 실행은 성공한다.**

### 매핑 규칙

```
query/FASTA 위치 (1-based, MSA query 서열 기준)
  → 원본 첫 모델 잔기      서열 정렬로. resseq 로 하지 않는다.
  → staged 잔기            연속 부분열 오프셋
  → backbone 잔기          항등 (RFD3 가 정체와 번호를 보존한다 - 검증됨)
  → fixed position         backbone resseq
```

**잔기를 센다. CA 행을 세지 않는다.** altLoc 은 첫 conformer 만 취한다.

### 매핑 산출물 — 위치마다 남긴다

```
query_pos · original_chain · original_resseq · original_icode
backbone_chain · backbone_resseq · aa
mapping_source · identity_ok
```

### hard fail — 조용히 넘어가지 않는다

```
staged 가 원본의 연속 부분열이 아님 (중간 결손)
그 부분열이 원본에 두 번 이상 나타남 (모호한 대응)
backbone 서열 또는 번호가 staged 와 다름
사슬이 둘 이상
위치별 아미노산 불일치
query 위치가 backbone 에 대응되지 않음
fixed position 이 backbone 잔기 번호 범위 밖
```

**마스크를 조용히 줄이는 것을 특히 금지한다.** 대응되지 않는 query 위치가
하나라도 있으면 실패시킨다 - 줄이면 성공처럼 보이는 실패가 된다.

MSA query 서열이 원본 첫 모델 서열과 다르면 위치별 아미노산 불일치로 걸린다.

---

## 3. MSA feasibility contract

새 숫자를 만들지 않고 기존 `bio/a3m.py::msa_quality()` 의 기준을 쓴다.

```
실행 실패 또는 빈 A3M          → MSA_INFEASIBLE
usable_hits < 10               → MSA_INSUFFICIENT_DEPTH
median coverage < 0.2          → 경고. 기록하고 진행한다.
median depth < 10              → 경고. 기록하고 진행한다.
full_length_fraction < 0.05    → 경고. 기록하고 진행한다.
```

`usable_hits >= 10` 은 새로 만든 값이 아니라 코드가 이미 저심도 경고를 내는
경계다.

### 교체 규칙 — calibration 과 confirmatory 가 다르다

두 코호트의 backbone 조달 방식이 다르므로 규칙도 달라야 한다.

```
calibration  (기존 51 backbone 재사용)
  MSA_INFEASIBLE / MSA_INSUFFICIENT_DEPTH / MAPPING_INFEASIBLE
    → 그 타겟을 calibration-infeasible 로 기록
    → **예비 대체 금지**
    → 남은 타겟으로 §9 를 수행할 수 있는지 확인
    → 최소 식별 요건에 미달하면 Phase 4B BLOCKED

confirmatory (새로 생성)
  같은 사유가 **후보 생성 전에** 발생 → 동결된 순서로 예비 교체 가능
  SoluProt · AF2 · joint-pass 를 본 뒤 → 교체 금지
```

**calibration 에서 예비 대체를 금지하는 이유**는 §5 가 "기존 51 backbone 만
쓴다" 로 동결돼 있기 때문이다. 예비 타겟에는 backbone 이 없으므로 대체하려면
새로 생성해야 하고, 그러면 §5 와 충돌한다. 지금은 새 calibration backbone 을
만들지 않는다.

교체 사유와 순서를 산출물에 남긴다.

---

## 4. Tier mixture

```
calibration    backbone 당 12 개 = tier30 4 · tier50 4 · tier70 4
confirmatory   backbone 당 24 개 = tier30 8 · tier50 8 · tier70 8
```

`q_b` 는 **이 사전 지정 혼합 위의 단일 확률**이다.

```
q_b = P(다음 유효 관측이 joint-pass | backbone b, 균형 tier 혼합)
```

### 평가 순서를 동결한다 — prefix 도 균형이어야 한다

RAPID 은 backbone 의 후보를 한 번에 다 평가하지 않는다. 예산에 따라 앞에서
일부만 본다. 그러면 초반 관측이 우연히 한 tier 에 몰릴 수 있고, 그 순간 실제
관측 분포가 위 정의와 달라진다.

그래서 backbone 마다 평가 순서를 폴딩 전에 고정한다.

```
30 → 50 → 70
30 → 50 → 70
...
calibration   이 주기를 4 회  (12 개)
confirmatory  이 주기를 8 회  (24 개)
```

**모든 prefix 가 가능한 한 균형을 유지한다** - 3 의 배수 지점에서 정확히
균형이고, 그 사이에서도 tier 간 차이가 1 을 넘지 않는다.

tier 안의 후보 순서는 생성 seed 와 design index 로 사전 동결한다. 결과를 보고
재배열하지 않는다.

### tier 를 allocation arm 으로 올리지 않는다

```
❌ q_(backbone, tier)   → Phase 4 구조가 바뀐다
✅ q_b + 고정 혼합       → allocation unit = backbone 유지
```

RAPID v2 가 backbone 을 고르면 그 안에서는 **언제나 4/4/4** 로 생성한다. tier 는
생성 조건이지 배분 단위가 아니다.

부수 결과: v1 의 `explore_generation_condition` 행동은 이 설계에서도 비활성이다
(홀드아웃이 단일 온도였던 것과 같다). 회귀가 아니라 동일한 제약이다.

---

## 5. Calibration

```
코호트        기존 RFD3 backbone 51 개 (재생성하지 않는다)
              11 informative targets · 2r01A02 는 generation-infeasible
평가          51 × 12 = 612
LOTO          타겟별 예측 개수로 정규화 후 타겟 동일 가중 평균
식별 판정     §9 그대로 (수정 금지)
```

§9 는 `rapid-v2-phase4b-calibration-freeze.md` 의 세 조건이다.

```
(1) kappa* 에서 두 칸 이상 떨어진 모든 kappa 에 대해
    ΔLOTO-LL 의 타겟 클러스터 부트스트랩 단측 90% 하한 > 0
(2) kappa* ∉ {0.5, 32}
(3) 부트스트랩 argmax 가 ±1 칸 안에 드는 비율 >= 0.80
동률이면 작은 kappa
```

**calibration 단계에서 EFBC 를 계산하지 않는다.**

---

## 6. Confirmatory validation — 지금 함께 동결한다

**Phase 4B 결과를 본 뒤 설계하면 안 되므로 여기서 전부 잠근다.**

### 코호트

```
새 unseen masked holdout
12 targets × 5 RFD3 backbones × 24 candidates = 1,440 evaluations
tier 혼합 8 / 8 / 8 · 평가 순서 §4 대로 동결
길이 층 4 / 4 / 4  (50-150 · 150-250 · 250-400)
예비 층당 2
```

### 왜 24 인가 — budget grid 와 맞춘다

budget grid 가 120 까지 가는데 backbone 당 12 개면 타겟당 평가 가능한 후보가
`5 × 12 = 60` 뿐이라 `B = 80·100·120` 이 존재할 수 없다. 24 로 두면
`5 × 24 = 120` 이 되어 grid 전 구간이 성립하고, v1 홀드아웃의 24 seq/backbone
규모와도 같아진다.

calibration 은 12 로 둔다. 목적이 확률 모수 식별이므로 같은 사전 지정 혼합에서
후보 수만 다른 것은 모순이 아니다.

### 선정 — 적격성과 길이만

```
제외   기존 holdout (selected/reserve/resolved)
       panel1 · panel2
       calibration 12 + 예비 6
       위 전부의 superfamily
포함   단일 사슬 · 길이 50-400
```

가용 풀 확인 완료: 이미 쓴 타겟 56 · 제외 superfamily 56 · **남은 적격 후보
201** (층별 86 / 42 / 73). 층당 6 이 필요하므로 여유가 있다.

선정 seed 와 산출된 목록은 backbone 생성 **전에** 커밋한다.

### 생성

```
RFD3    §1 의 "바꾸지 않는 것" 그대로 (local_diversify · partial_t 5.0)
서열    §1 의 masked protocol · §4 의 4/4/4 혼합
```

### 판정 — 기존 동결을 그대로 쓴다

```
primary      Effective Feasible Backbone Coverage @ Fixed Budget
guardrail    structural-yield ratio >= 0.90 (단측 95% 하한)
comparator   같은 예산의 static/equal (primary) · frozen v1 (secondary)
채택         EFBC 개선 CI 가 0 제외 AND yield ratio 하한 >= 0.90
informative  endpoint 별 집합 (coverage / yield 따로)
최소 클러스터 8
budget grid  1-24 + 30/40/50/60/80/100/120
bootstrap    타겟 클러스터
```

### 기존 12-target masked 재실행

**선택 사항이다.** 이미 결과를 본 타겟이므로 진정한 prospective confirmatory 가
아니다. 하면 paired protocol-transfer / sensitivity 로만 보고한다. 우선순위는
calibration → 새 holdout 이 먼저다.

---

## 7. v1 의 지위 — 유지한다

강등하지 않는다. 무효가 된 것이 아니다.

```
RAPID v1 prospectively validated adaptive allocation under a frozen
unmasked, single-generation-condition candidate distribution.
```

원고 limitation 에 추가할 문장:

> The prospective v1 validation used an unmasked ProteinMPNN candidate
> distribution and therefore did not directly validate transfer to the default
> three-tier conservation-masked deployment pipeline.

두 실험이 다른 질문에 답한다.

```
v1          배분이 작동하는가
v2 masked   실제 배포 후보 분포에서도 작동하는가, 그리고
            backbone-context coverage 를 보존할 수 있는가
```

`rapid_structural_v1` 태그 · 해시 27/27 · golden test 는 그대로 둔다.

---

## 8. Ligand

```
구현한다      원본 타겟에서 6 Å 잔기 계산 → 매핑 → fixed positions union
테스트한다    unit / integration
```

**이 코호트에는 리간드가 없다** (CATH 도메인 12 개 전부 HETATM 0). 따라서:

```
쓸 수 있다   ligand-aware masking is supported by the pipeline
쓸 수 없다   ligand-aware allocation was prospectively validated
```

효소·리간드 설계에서의 검증은 별도 프로토콜로 남긴다.

---

## 실행 순서

```
1. 이 문서 커밋                                   ← 지금
2. 새 holdout 타겟 선정 + 커밋 (생성 전)
3. MSA (calibration 11 + 새 holdout 12)
4. 매핑 검증 (§2 hard fail)
5. Phase 4B calibration 612
6. kappa_pool 식별 판정 (§9)
   미식별이면 여기서 멈춘다
7. 새 holdout backbone 생성 + checkpoint
8. 새 holdout 1,440
9. confirmatory 결과 한 번
```

6 번에서 미식별이면 7 번 이후로 가지 않는다.

## 이 문서로 하지 않는 것

```
select_fixed_atoms 변경
altLoc 전처리 변경
기존 51 backbone 재생성
기존 holdout 결과 무효화
결과를 보고 tier/마스크/임계값 조정
```
