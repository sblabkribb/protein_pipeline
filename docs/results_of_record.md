# RAPID 결과 기준값

원고·초록·발표에 쓰는 수치는 여기서 가져온다. 각 줄에 산출물 경로가 붙어 있고,
그 파일이 유일한 출처다. 문서나 설계 스펙에서 수치를 옮겨 적지 않는다.

**왜 이 파일이 있는가.** 초록에 out-of-fold AUC 0.756 이 들어간 적이 있다. 그 값은
`docs/superpowers/specs/2026-09-03-rapid-transcoder-unified-design.md` 에 남아 있던
옛 값이었고, 실제 측정값은 0.7247 이었다. 설계 문서의 수치는 그때의 기대치이지
측정 결과가 아니다. 수치를 인용할 곳을 한 군데로 모아 그 혼동을 없앤다.

## 인용 규칙

- 이 표에 없는 수치는 원고에 넣지 않는다. 필요하면 먼저 여기에 출처와 함께 추가한다.
- 코호트를 함께 적는다. 같은 양이라도 코호트가 다르면 다른 수치다.
- "대체됨" 으로 표시된 값은 부록에서 비교 목적으로만 쓴다.

## Gate 0 · 타겟 수준 라우팅

| 값 | 수치 | 코호트 | 출처 |
|---|---|---|---|
| out-of-fold AUC (ProteinMPNN 인코더) | **0.7247** [0.7088, 0.7397] | 타겟 62 | `public_data/benchmark/gate0/gate0_target_level.json` → `arms.C_raw_mpnn_encoder` |
| 구조 기술자 기준선 | 0.6522 [0.6314, 0.6698] | 타겟 62 | 같은 파일 → `arms.B_structural_descriptors` |
| 전역 평균 기준선 | 0.4045 [0.3814, 0.4288] | 타겟 62 | 같은 파일 → `arms.A_global_mean` |
| 인코더 − 기술자 (짝지음) | +0.0725 [0.0499, 0.0957] | 타겟 62 | 같은 파일 → `paired` |

AUC 0.725 는 순위를 매기기에는 쓸 만하지만 후보를 잘라내기에는 부족하다. 그래서
Gate 0 은 하드 컷이 아니라 사전분포로 들어간다 - 잘라낸 것은 되돌릴 수 없다.

## 분산 분해 · 구조 결과

| 값 | 타겟 | 백본 | 서열 | 코호트 | 출처 |
|---|---|---|---|---|---|
| **현행** structural_pass (제곱합) | **41.7%** | **21.9%** | **36.4%** | RFD3 전용 균형, 설계 1,440 · 타겟 12 · 백본 60 | `public_data/benchmark/gate0/holdout_grid/variance_decomposition_grid.json` |
| 현행 pLDDT (혼합모형) | 52.9% | 15.8% | 31.3% | 같음 | 같은 파일 |
| 현행 RMSD (혼합모형) | 40.2% | 12.0% | 47.8% | 같음 | 같은 파일 |
| _보조(consistency)_ structural_pass | 49.5% | 14.7% | 35.8% | 온도 패널, 타겟 20 (패널 2 가 중간 yield 백본을 선별) | `public_data/benchmark/gate0/variance_decomposition_structural.json` |

**주 결과는 균형 코호트의 타겟+백본 귀속 63.6% 다.** 온도 패널의 64.2% 는 보조
consistency 결과로 내린다 - 주 결과를 대체하거나 보강하는 독립 증거가 아니라,
선별이 결론을 만들지 않았는지 보는 대조다. 두 값이 가깝다는 것은 선별을 걷어내도
귀속이 거의 그대로라는 뜻이고, 따라서 주 결과가 패널 2 의 구성 방식에서 나온 것이
아니다.

두 값을 독립 반복으로 제시하면 안 된다. 코호트가 다르고 한쪽은 선별돼 있다.

**타겟 12 개라는 한계는 유지된다.** 분산성분, 특히 타겟 수준 성분은 클러스터 12
개로 추정한 것이라 점추정을 좁게 읽으면 안 된다. 코호트를 균형으로 바꿔도 이
불확실성은 없어지지 않는다.

표현: "이 코호트의 분산 분해에서 63.6% 가 타겟 및 백본 수준 차이에 귀속되었다."
쓰지 않는다: "구조 성공의 64% 가 백본 수준에서 결정된다." 분산 분해는 관측된
코호트의 귀속이지 인과적 결정이 아니다.

길이로 설명되지 않는다: length_stratum 을 고정효과로 넣어도 타겟 분산이 pLDDT
52.9%, RMSD 40.2% 로 남는다. 짧은 도메인이 더 잘 접히는 것은 맞다 (50-150 층이
150-250 대비 pLDDT +3.51, RMSD −1.58 Å).

## 전향 배분 검증 · 미지 타겟

정책 성능 주장은 이 코호트에서만 한다. 격자는 12 개 홀드아웃 타겟 (인코더 학습에
쓰이지 않음) 에서 정책 동결 후에 생성됐다.

| 예산 상한 | 적응 | 적응이 실제로 쓴 호출 | 최적 정적 (사후 k) | oracle | 차이 [95% CI] |
|---|---|---|---|---|---|
| 20 | 12.57 | 20.0 | 12.65 | 17.19 | -0.08 [-0.17, +0.01] |
| 24 | 15.72 | 23.9 | 15.24 | 20.64 | **+0.48** [+0.23, +0.75] |
| 40 | 28.82 | 39.5 | 25.36 | 32.81 | **+3.46** [+2.10, +4.92] |
| 60 | 44.06 | 57.4 | 37.85 | 46.69 | **+6.21** [+3.68, +9.14] |
| 80 | 56.77 | 73.6 | 50.33 | 58.63 | **+6.44** [+3.48, +9.42] |
| 100 | 67.55 | 90.0 | 62.95 | 68.51 | **+4.60** [+2.23, +7.26] |
| 120 | 75.31 | 106.4 | 75.55 | 75.55 | -0.24 [-0.58, +0.00] |

출처: `public_data/benchmark/gate0/holdout_grid/prospective_allocation_validation_joint.json`
(주 endpoint = joint-pass, 동결 spec `holdout_experiment_spec.json` 기준).

격자는 1,728/1,728 로 완성했다 (실패 51 건 재시도). RFD3 코호트가 1,440/1,440
으로 완전 균형이다. 1,400 개였을 때와 비교해 열 개 예산 지점의 CI 0 제외 판정이
전부 그대로였고 차이의 점추정은 0.05 이내로만 움직였다.

위 표가 **1 차 endpoint** 다. 동결 spec 그대로이고 사후에 바꾸지 않았다. 상한
120 의 −0.24 도 그대로 보고한다.

### 2 차: 실제로 쓴 계산량

예산은 상한이지 지출이 아니다. 적응 정책은 movability 가 바닥인 백본을 버리고
남은 예산을 쓰지 않는다 (평균 0.76 개 포기). 정적 배분은 상한을 늘 다 쓴다.
그래서 같은 상한 비교는 같은 계산량 비교가 아니다. 1 차 지표를 바꾸는 대신
따로 잰다.

| 상한 | 적응이 쓴 호출 | 균등이 쓴 호출 | 같은 실현 계산량에서 Δ설계 | 같은 성공 수까지 Δ호출 |
|---|---|---|---|---|
| 20 | 20.0 | 20.0 | -0.04 [-0.11, +0.03] | **+0.86** [+0.19, +1.98] |
| 24 | 23.9 | 24.0 | **+0.62** [+0.31, +0.94] | **-2.21** [-4.36, -0.56] |
| 40 | 39.5 | 40.0 | **+3.62** [+2.29, +4.99] | **-15.11** [-29.07, -4.30] |
| 60 | 57.4 | 60.0 | **+6.49** [+4.05, +9.35] | **-18.36** [-30.21, -8.37] |
| 80 | 73.6 | 80.0 | **+6.83** [+4.19, +9.43] | **-17.96** [-28.13, -9.09] |
| 100 | 90.0 | 100.0 | **+5.30** [+3.23, +7.80] | **-15.11** [-25.82, -6.44] |
| 120 | 106.4 | 120.0 | +0.71 [+0.00, +1.75] | -8.30 [-21.25, +0.42] |

출처: `public_data/benchmark/gate0/holdout_grid/realized_compute_analysis.json`.
Δ호출이 음수면 적응이 더 적은 호출로 같은 수를 채웠다는 뜻이다.

상한 120 을 두 지표로 같이 읽어야 한다. 1 차는 −0.24 개이고, 같은 실행에서
적응은 106.4 회만 썼다. 정적에게도 106 회만 주면 +0.71 [+0.00, +1.75] 로 부호가
바뀐다. CI 가 0 에 닿으므로 정직한 진술은 "포화 지점에서 둘은 구별되지 않는데
한쪽이 13.6 회를 덜 쓴다" 다. 어느 한쪽 값으로 다른 쪽을 지우면 안 된다.

파레토 프론티어에서 균등 배분은 상한 12–20 구간을 차지하고 (probe 바닥 구간),
적응은 상한 24 부터 120 까지 전 구간을 차지한다. 지배된 12 점 중 9 점이 균등이다.

곡선의 모양이 결과다. 예산 22 이하에서는 이득이 없다 - 백본 5 개에 각 4 개씩
의무 probe 를 돌리면 예산이 다 소진돼 배분할 것이 남지 않는다. 예산 120 에서는
모든 정책이 모든 관측을 보므로 반드시 수렴해야 하고, 실제로 수렴한다. 이 수렴은
발견이 아니라 재생이 제대로 구현됐다는 점검이다.

이득이 있는 구간에서 균등 배분과 oracle 사이 간격의 약 70% 를 회수한다.

민감도: native 포함 +3.52 / +6.62 (예산 40 / 60), 구조-only 라벨 +3.50 / +6.06.

검증 범위: Gate 1B 의 **백본 배분** 축만. 격자는 단일 조건 (T=0.1) 이라 조건-탐색
축은 여기서 검증되지 않는다.

## 생성 조건 · 온도

| 값 | 수치 | 출처 |
|---|---|---|
| T=0.1 structural yield | 0.4952 | `public_data/benchmark/gate0/temperature_panel2/af2_analysis_order_complete.json` |
| T=0.05 대비 | −0.0906, CI 0 제외 | 같은 파일 |
| T=0.2 대비 | −0.1094, CI 0 제외 | 같은 파일 |
| T=0.3 대비 | −0.1313, CI 0 제외 | 같은 파일 |

결측은 판정을 바꾸지 않았다. 워커 끊김으로 13 건이 빠져 있었고 그중 6 건이
하필 가장 큰 효과를 보인 T=0.3 이라 무작위 결측이라는 근거만으로 넘기지 않고
채워서 다시 냈다. 832/832 로 완성한 뒤 아홉 개 비교의 CI 0 제외 판정이 전부
그대로였고 점추정은 0.002 이내로만 움직였다 (819 → 832).

패널 2 는 **개발 패널**이다 (`valid_for_policy_performance_claims: false`). 중간
yield 백본만 담고 있으므로 여기서 나온 온도 효과는 전체 백본 집단의 평균 효과가
아니라 중간-yield 영역에서의 조건부 효과다. 정책 성능 수치는 홀드아웃 격자에서만
인용한다.

## Gate 1 · 백본 예측 가능성 (2026-09-11)

동결 스펙 `docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md` §3. 질문:
**AF2 를 보기 전 cheap feature 로 어느 백본의 q_b 가 높은지 예측할 수 있는가.**
feature = ProteinMPNN encoder 384-D (`v_48_020` soluble). **새 AF2 0 개.**
판정 arm 은 primary 하나다 — RFD3-only dev(백본 80·타겟 16)로 학습해 RFD3-only
홀드아웃(백본 60·타겟 12, informative 11)에서 평가한다.

| 값 | 정본 | 출처 (`gate1_backbone_predictability.json`) |
|---|---|---|
| primary 타겟 등가중 mean within-target Spearman | **+0.0379** | `arms.primary.point` |
| primary 단측 90% LCB | **−0.1559** | `arms.primary.one_sided_90_lcb` |
| primary informative 타겟 | **11** | `arms.primary.informative_targets` |
| primary top-1 백본 regret (2 차, **informative 11**) | **0.1780** | `arms.primary.top1_backbone_regret_mean_informative_cohort` |
| 〃 (ranked 12, 참고) | 0.1632 | 같은 파일 → `.top1_backbone_regret_mean_all_ranked_targets` |
| 동결 문턱 | ρ ≥ +0.25 ∧ LCB > 0 ∧ n ≥ 8 | `frozen_go_rule` |
| **판정** | **NO-GO [FINAL]** (문턱 세 개 중 두 개 미달) | `verdict` |

동반 arm (사전 등록, 판정에 쓰지 않는다):

| arm | train | ρ | LCB90 | regret |
|---|---|---|---|---|
| sensitivity 1 | RFD3+BioEmu (100·16) | +0.0577 | −0.1524 | 0.1818 |
| descriptive / legacy | 전체 dev (157·62) | −0.0604 | −0.2561 | 0.2841 |
| comparator (native 홀드아웃) | — | **non-evaluable** | — | — |

**해석 제한 — 이 두 줄을 수치와 떼어 인용하지 않는다.**

> **허용:** "사전 등록된 RFD3-only primary test 에서 backbone-level cheap
> predictability 가 GO 기준에 도달하지 못했다."
>
> **금지:** "ProteinMPNN encoder 는 backbone quality 를 예측하지 못한다."
> "backbone-level signal 은 존재하지 않는다."

근거: primary 는 **백본 80 개에 384 차원**(n/p = 0.21)이고, 스펙 §3 이 결과 전에
이 NO-GO 를 **"신호 없음" 이 아니라 "이 표본에서 미검출"** 로 읽도록 고정했다.
사전 지정 OC(`OC_primary_rfd3_only`)에서 GO 확률은 ρ ≈ 0.33 에서 0.74, ρ ≈ 0.44
에서 0.94 다. 관측된 top-1 regret **0.1780** 은 같은 표의 귀무값 0.2274 보다 낮다
(둘 다 informative 11 타겟 기준 — 코호트가 일치한다) —
약하지만 0 이 아닌 신호의 모습이다.

**legacy arm 이 음수인 것은 예고된 것이다.** §3 이 native 백본이 계수를 형성한다고
사전에 경고했고, 그래서 native 를 배분 풀에서 빼 comparator 로 분리했다. comparator
는 native 가 타겟당 1 백본이라 타겟 내 Spearman 이 정의되지 않아 non-evaluable 이며
**0 으로 대입하지 않는다** — 재지 못한 것과 0 은 다르다.

부수 분석 `Δ_generated` = q_b(생성) − q_b(native) = **+0.0825** (LCB −0.0475,
타겟 10) — GO 판정에서 제외된다. LCB 가 0 을 포함하므로 "생성 백본이 native 보다
낫다" 의 근거로 쓰지 않는다.

**feature 공간은 가정이 아니라 확인된 사실이다.** dev `mpnn_encoder.npy` 를 만든
스크립트는 커밋된 적이 없어(`1c2eeb4` 는 산출물만) 추출기를 재구현했다. 홀드아웃에
적용하기 **전에** dev 157 백본을 다시 뽑아 커밋된 산출물과 비교했고
`max abs diff 9.06e-06`, `allclose(atol=1e-4) True` 였다
(`21_gate2d_prepare_encoder.py --verify-dev`). 결정적 요소는 **`residue_idx` 가
상수**(상대 위치 인코딩 비활성)이며 `1c2eeb4` 의 "sequence-independent" 서술과
일치한다 — 다만 그것이 원래 의도였는지는 원본 스크립트가 없어 확인할 수 없다.
코호트 교차확인: native 평균 q_b **0.6042** (`delta_generated_side_analysis.mean_q_b_native`,
native 는 타겟당 백본 1 개이므로 백본평균 = 타겟평균) · RFD3 **0.6604**
(`arms.primary.mean_q_b`, test 코호트 60 백본) 가 스펙 §3 의 0.604 / 0.660 과
일치한다. **`delta_generated_side_analysis.mean_q_b_rfd3` 0.6867 과 혼동하지 않는다**
— 그쪽은 짝지음을 위해 native 라벨이 있는 10 타겟으로 제한한 값이고, 위 두 수와는
다른 양이다.

**선행 시도.** `13_gate0_target_level.py` 의 rfd3 타겟내 ρ −0.257 은 correspondence
metric 교체로 라벨이 무효화됐으므로 standing negative result 로 인용하지 않되,
시도가 있었다는 사실은 함께 적는다.

## Gate 2 · 백본 내부 서열 선택성 (2026-09-11)

동결 스펙: `docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md`.
코호트: 홀드아웃 격자 mixed 백본 37 개 / informative 타겟 11 개 / 사용가능 폴드 1,680.
1 차 endpoint = joint-pass, 지표 = 타겟 등가중 Δ_Top4. **새 AF2 0 개.**

| 값 | 수치 | 출처 |
|---|---|---|
| S6 (판정 arm) Δ_Top4 | **−0.0313** | `gate2_within_backbone_selectability.json` → `arms_joint_pass.S6.delta_top4_target_equal` |
| S6 단측 90% LCB | **−0.0803** | 같은 파일 → `.one_sided_90_lcb` |
| S6 informative 타겟 | 11 | 같은 파일 → `.informative_targets` |
| 저심도 제외 민감도 (코호트 10) | Δ **−0.0386**, LCB −0.0924 | 같은 파일 → `arms_joint_pass.S6.sensitivity_excluding_low_depth` |
| RFD3-only 민감도 (mixed 34 / informative 11) | Δ **−0.0225**, LCB −0.0755 | 같은 파일 → `arms_joint_pass.S6.sensitivity_rfd3_only` |
| oracle 상한 | +0.326 | 같은 파일 → `reference_points.oracle` |
| SoluProt 기준선 | −0.001 | 같은 파일 → `reference_points.soluprot` |

전체 ladder (joint-pass, Δ_Top4 / LCB90):

| S0 | S1 | S2 | S3 | S4 | S5 | S6 |
|---|---|---|---|---|---|---|
| −0.0014 / −0.0367 | +0.0384 / +0.0107 | −0.0188 / −0.0508 | −0.0029 / −0.0316 | +0.0001 / −0.0347 | −0.0366 / −0.0854 | **−0.0313 / −0.0803** |

**RFD3-only 민감도는 스펙 §3 이 사전 등록한 것이다.** 1 차 코호트는 mixed 37 로
유지하고 이것을 나란히 보고한다. **모델을 재적합하지 않는다** — 같은 LOTO 예측을
RFD3 백본 34 개 위에서 다시 집계할 뿐이다. §3 의 "학습 쪽도 정렬한다" 는 Gate 1
조항이고, Gate 2 문장은 코호트에 대한 것이며, ladder 는 arm 7 개로 동결돼 있어
재적합은 여덟 번째 arm 이 된다. (재적합 판은 **+0.0097 / −0.023359** 이고 산출물
`arms_joint_pass.S6.sensitivity_rfd3_only.alternative_reading_model_refit` 에 기록돼 있다.
판정은
판정은 역시 NO-GO 다. 산출물에 `model_refit: false` 와 근거를 남겨 다르게 읽는
사람이 재유도 없이 반박할 수 있게 했다.)

**두 민감도 모두 1 차와 같은 방향이고 어느 문턱도 넘지 못한다.** 즉 NO-GO 는
저심도 타겟에도, native 백본 포함 여부에도 의존하지 않는다.

**S1 을 인용할 때 반드시 붙일 것.** S1(raw ESM mean)은 1 차 endpoint 에서 점추정이
양수이고 LCB > 0 인 유일한 arm 이지만, **사전 등록된 known-null** 이고(82 타겟에서
이미 음성) 문턱보다 0.06 낮다. 스펙이 S6 를 유일 판정 arm 으로 동결한 이유가 이런
사후 arm 선택을 막기 위해서다. **S1 으로 어떤 판정도 내리지 않는다.**

### PRIMARY DEVIATION 해소 (2026-09-11) — 이제 사전 등록한 S6 다

동결 스펙의 S6 는 `S5 + 기존 cheap feature(조성 + MPNN score)` 다. 2026-09-11 의
첫 실행에는 MPNN score 열이 없었다 — 격자의 `sequences.csv` 에 그 열이 없고, score
열을 가진 다른 코호트와 격자 sequence_id 의 교집합이 **0** 이었다. 그래서 realized
S6 = `S5 + 조성` 이 되어 S5 와 bit-for-bit 같았고, 공식 판정이 `UNRESOLVED`
(PRIMARY DEVIATION) 로 남았다.

체크포인트 `v_48_020` 이 확보되어 **같은 1,680 폴드의 per-sequence MPNN score 를
직접 계산했다** (`scripts/benchmark/27_gate2d_prepare_mpnn_scores.py`,
`holdout_grid/mpnn_scores.json`). **새 AF2 는 0 개다** — 이미 있는 라벨에 열 하나를
붙였다. 위 표의 수치는 이제 planned-S6 다.

| | Δ_Top4 | LCB90 | n_feat | 판정 |
|---|---|---|---|---|
| planned S6 (조성 + MPNN score) | **−0.0313** | −0.0803 | 355 | NO-GO |
| realized S6 (2026-09-11 이전, MPNN score 없음) | −0.0366 | −0.0854 | 354 | NO-GO |

출처: 같은 파일 → `s6_planned_vs_realized`. **두 판정이 일치한다** (`verdicts_agree:
true`, 점추정 이동 +0.0053). S0–S5 는 bit-for-bit 그대로다 — 바뀐 것은 S6 의 열
하나뿐이고 realized 판을 같은 실행에서 재현해 그것을 확인한다.

따라서 planned-S6 도 NO-GO 이고, 스펙 §8 은 `9f1a1ae` 에서 **`Gate 2 = NO-GO
[FINAL]`** 로 닫혔다.

## 최종 판정 · Surrogate × RAPID 2축 확장 (2026-09-11)

> **STOP.** Gate 1 과 Gate 2 모두 사전 등록된 GO 기준에 도달하지 못했으므로, 현재
> 시험한 feature family 에 기반한 **B(backbone-specific surrogate prior)** 및
> **C(sequence-level targeted/sentinel extension)** 개발은 진행하지 않는다.

**STOP 의 범위를 좁게 읽는다.** 이것은 **RAPID 자체를 접는다는 뜻이 아니다.**
이번 surrogate 결합 연구축을 접는 것이며, **RAPID v2 의 독립적인 전향 검증은
별개이고 영향받지 않는다.** 이 게이트는 그 검증에 어떤 변경도 넣지 않았다
(스펙 §9).

판정 근거 두 줄:

| | 정본 | 문턱 | |
|---|---|---|---|
| Gate 1 | ρ +0.0379 · LCB −0.1559 · n 11 | ρ ≥ 0.25 | NO-GO |
| Gate 2 | Δ_Top4 −0.0313 · LCB −0.0803 · n 11 | ≥ +0.10 | NO-GO |

**전 과정에서 새 AF2 는 0 개다.** 기존 1,680 폴드 라벨을 재사용했고, 새로 든 계산은
MSA 12 타겟 · ESM 임베딩 · 백본 encoder · MPNN score 뿐이다.

## 아니라고 판정한 것

| 항목 | 판정 | 출처 |
|---|---|---|
| aggregation 서열 특징을 구조 랭커로 추가 | **NO-GO** · 타겟 내 이득 없음 | `public_data/benchmark/gate0/incremental_information_test.json` |

pooled 지표에서 보이던 이득은 타겟 난이도를 더 잘 맞힌 것이고 cheap filter 가
하는 일이 아니다 (Simpson 역설). SoluProt 은 구조 랭커가 아니라 용해도 objective
제약 (Gate 1A) 으로 남는다.

## 안정성 annotation (ThermoMPNN)

native-백본 설계 300 개에 돌렸다 (300/300 성공). 안정성을 하드 게이트로 쓰지
않기로 한 판단의 근거다.

| 비교 | pooled Spearman | 백본 내 중앙값 rho | 백본 내 음수 비율 |
|---|---|---|---|
| ThermoMPNN vs Rosetta relax | −0.0593 | −0.0079 | 0.500 |
| ThermoMPNN vs pLDDT | **+0.2143** | **−0.1677** | 0.875 |

출처: `public_data/benchmark/gate0/stability_annotation_comparison.json`.

pLDDT 와의 부호가 pooled 와 백본 내에서 뒤집힌다. 이 캠페인에서 같은 함정이 세
번째다 (aggregation 증분정보, 온도 패널 분산분해). pooled 양의 상관은 백본 간
난이도 차이에서 나온 것이고, 백본 안에서 후보를 고르는 데 쓸 수 있는 신호가
아니다. Rosetta relax 와는 백본 내 부호가 50:50 으로 사실상 무관하다.

따라서 ThermoMPNN 은 annotation 과 tie-break 로만 남기고, 이 결과를 근거로
SPURS 를 중재자로 추가하지 않는다 - 두 예측기가 어긋난다는 사실이 세 번째
예측기를 심판으로 만들어 주지는 않는다.

읽지 말아야 할 것: additive ddG 중앙값 8.22 kcal/mol 을 안정성 추정으로 읽으면
안 된다. 설계당 변이가 중앙값 79 개인데 ThermoMPNN 은 단일 점변이로 학습됐고,
이 값은 그 예측의 단순 합이라 에피스테이시스를 무시한다. 다만 변이 수와 ddG 의
상관은 −0.0325 로, 점수가 변이 개수를 세고 있는 것은 아니다.

## 리간드 자기도킹 (배선 점검)

**성능 검증이 아니다.** DiffDock 은 PDBBind 로 학습했고 이 복합체들이 그 안에
있을 것이므로, 여기서 나온 수치를 결합 예측 성능 주장으로 쓰지 않는다. 배선이
연결돼 있고 좌표가 오가는지를 보는 점검이다.

| 타겟 | 리간드 | 결정 사본 수 | pose 원자 | 중심이동 (Å) | 포켓겹침 |
|---|---|---|---|---|---|
| 2wejA00 | FB2 | 1 | 10 | 0.06 | 1.000 |
| 1af7A01 | SAH | 1 | 26 | 0.10 | 1.000 |
| 1jrzA02 | FAD | 2 | 53 | 0.18 | 1.000 |
| 2x62B00 | CH | 2 | 21 | 0.23 | 1.000 |
| 1amiA02 | MIC | 1 | 14 | 0.23 | 1.000 |
| 1bxmA00 | ERG | 1 | 29 | 0.35 | 1.000 |
| 1t4cA02 | COA | 2 | 48 | 0.39 | 1.000 |
| 1no3A05 | 4NC | 1 | 11 | 2.01 | 1.000 |
| 1e60A03 | PGD | 4 | 47 | 2.62 | 0.872 |
| 1lshA03 | PLD | 7 | 60 | 19.47 | 0.000 |
| 1nqlA03 | NAG | 11 | 15 | 20.98 | 0.000 |
| 3bukC01 | NAG | 2 | 15 | 28.71 | 0.000 |

중앙값 0.37 Å · 2 Å 이내 7/12 ·
출처: `public_data/benchmark/gate0/ligand_pocket/self_docking.json`.

**사본별 채점으로 고쳤다.** 예전에는 리간드를 3-문자 코드로만 묶어 파일 안의
모든 사본을 한 덩어리로 만들었다. 1nqlA03 은 NAG 사본이 11 개라 "결정 리간드
중심" 이 11 개 당사슬 자리의 평균이 됐고 - 어느 결합 자리도 아니다 - 4 Å 겹침은
아무 사본에나 걸리면 인정돼 후해졌다. 그래서 중심이동 23 Å 과 포켓겹침 1.0 이 한
줄에 같이 적히는 모순이 나왔다. 지금은 (code, chain, resseq, icode) 로 사본을
가르고 두 지표를 **가장 가까운 한 사본**에 대해 매긴다. 중앙값이 16.81 Å 에서
0.37 Å 로 바뀌었는데, 옛 값은 도킹 결과가 아니라 pooling 인공물이었다.

다중 사본 표면 리간드(PLD 7 사본, NAG 11/2 사본)는 다른 자리에 붙어 19–29 Å ·
겹침 0.0 으로 **틀렸다고 그대로** 기록된다.

pose 가 나오지 않은 9 건의 이유: {'RDKit 가 우리가 넘긴 ideal SDF 를 읽지 못함': 5, '워커 로그에 이유 없음': 4}. 입력 문제이지
배선 문제가 아니다.

## 임계값

pLDDT 85 / RMSD 2.0 Å / SoluProt 0.5 는 캠페인 이전에 정해졌고 이 실험들에서
다시 고르지 않았다. 근거는 `scripts/transcoder/rapid_sr/protocol.py` 의
`THRESHOLD_PROVENANCE` 에 있다 - 셋 다 `convention_without_internal_calibration`
이다. 관례로 쓴 값이지 내부 보정 결과가 아니라는 뜻이다.
