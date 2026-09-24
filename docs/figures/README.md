# 구조맥락 앙상블 다양성 분석 — 그림 모음 (2026-07)

RFD3+BioEmu 구조맥락 앙상블 + surrogate 관련 추가 분석 그림. 모두 **CATH가 아니라
용해도 공학 효소 표적(Solu benchmark)** 실측 ProteinMPNN 서열(T=0.1) 기반:
S13 = 효소 3종(1ATJ·1TCA·1LVM, 단일 vs 4-backbone 앙상블, maskless 커버리지 상한),
S14 = 효소 2종(1CQW·5XJH; 기본 앙상블 20구조가 2.0Å 온전히 통과하는 표적) — RAPID fast-모드
기본 앙상블(RFD3 10+BioEmu 10) 다양성 vs 단일 backbone, 순수 2.0Å, 50% tier. expl = 효소 5종.

## 논문 채택 그림

### `supp_figS13_sequence_space_coverage.png`  ← Supplementary Figure S13 (채택)
표본 수(10·50·500·5000)에 따른 **고유 서열 클러스터 수(≤70% pairwise identity)**,
3 표적 평균. 단일 backbone은 하나의 서열공간 basin에 **포화(5,000개에서 ~4)**,
앙상블은 여러 basin을 채워 **계속 증가(~204)**. 격차 5배(10개)→50배(5,000개).
**메시지**: 앙상블 다양성은 "서열을 더 뽑아서"가 아니라 표본 수와 무관한
**구조적 커버리지**(온도로 대체 불가). → supplementary_KR_BiB_v2.docx Note 15 하위,
본문 §3.4에서 참조.
**주의**: S13은 **maskless(전체 재설계)** 기준 커버리지 상한 분석(효소 3종). 지지 그림 3점
(temperature·meanpairwise·clusters)과 S14는 파이프라인 기본 **50% 보존도 tier**로,
분석 범위가 다르나 결론(앙상블이 커버리지·다양성 확장)은 동일.

### `supp_figS14_ensemble_diversity_2p0A.png`  ← Supplementary Figure S14 (채택, 파이프라인-충실, 4곡선)
**RAPID fast 모드 기본값 그대로**: 표적당 RFD3 10 + BioEmu 10 = 20 앙상블 구조, ProteinMPNN
서열(생성 값쌈 → 대리모델이 유망 후보만 골라 비싼 AF2 검증). **순수 2.0Å 게이트(완화 없음)**,
50% tier, 고정 10-서열 예산(다양성 지표는 표본 수 무관 intensive). **기본 앙상블(20구조)이 2.0Å를
온전히 통과하는 효소 2종(1CQW·5XJH)** — 나머지 3종은 게이트 통과 부족으로 제외(1ATJ·1TCA RFD3 2개,
유연한 1LVM BioEmu 8개). 데이터: abl_be_{1CQW,5XJH}_rfd3_bioemu_u10_2p0_s1.
- 빨강 RFD3+BioEmu: 0.12→**0.31**(K=20=기본값) / 보라 RFD3만: →0.29(K=10) / 초록 BioEmu만: →0.28(K=10)
  — 셋 다 단조 증가·**RFD3만·BioEmu만 K=10으로 통일**, 결합 최고. 세로 점선(K=20)=fast-모드 기본 앙상블.
- 파랑 점선 단일 backbone: **~0.11 평평**(구조 1개라 같은 예산에서도 안 늘어남).
- x축 정수 눈금(구조 개수).
**메시지**: 후보 다양성은 서열 수가 아니라 **구조 앙상블**에서 옴 — 프로덕션 2.0Å 조건에서 성립,
surrogate triage 서사와 직결(다양한 앙상블 → 대리모델이 고를 풍부한 후보 풀). "왜 10/2개씩?"
→ **fast-모드 기본값**. 데이터: `S14_ensemble_diversity_results.json`.
→ supplementary_KR_BiB_v2.docx Note 15, Figure S14.
**참고(폐기)**: 이전 2.5Å 이중게이트 버전(dropped)은 게이트 완화 필요 → 리뷰어 우려로 순수 2.0Å로 대체.
불균형(과거 BioEmu 3:RFD3 1 착각)은 실제 fast-모드가 10+10이라 무의미; 기존 Figure 3/4·Note 13/15는 유지.

## 참고/탐색 그림 (논문 미채택)

### `expl_temperature_diversity_recovery_tradeoff.png`  ← 온도 각도 (제외, 효소 5종·tier-50)
단일 backbone에서 ProteinMPNN 온도 vs 다양성(빨강)·native recovery(파랑), **효소 5종
(1ATJ·1CQW·1LVM·1TCA·5XJH) 평균, 50% 보존도 tier 마스크**. 온도↑ → 다양성 **단조 증가**
(0.12→0.30) + recovery **감소**(0.38→0.33). 녹색 점선/띠 = RFD3+BioEmu 앙상블 다양성
(~0.29–0.33 @ T=0.1). **결론**: "온도를 올려도 다양성 한계가 있다"는 가설은 **성립하지 않음**
— 온도는 recovery를 대가로 다양성을 사는 trade-off이고, 앙상블은 T=0.1(고품질)에서 그 수준의
다양성을 얻음. 논문 서사를 약화시켜 **제외**. 데이터: `temperature_diversity_recovery_sweep.json`.

### `expl_meanpairwise_diversity_vs_N_flat.png`  ← 지표 선택 근거 (효소 4-arm, n=5, tier-50)
평균 pairwise 다양성 vs 표본 수. arm별로 수준은 다르지만(단일~0.13 < RFD3~0.14 <
BioEmu~0.26 < RFD3+BioEmu~0.28; **50% 보존도 tier**) 각 arm은 N에 대해 **평평**(intensive
지표). → "서열 수↑ → 다양성↑"는 이 지표로 안 보임(그래서 S13/S14는 누적 클러스터·구조 수 축 사용).
**효소 4-arm(1ATJ·1CQW·1LVM·1TCA·5XJH) tier-50 재생성 + 영어 라벨**(이전 CATH·한글 tofu 수정).

### `expl_clusters_vs_N_thr0.90_all-distinct.png`  ← 임계값 선택 근거 (효소 4-arm, n=5, tier-50)
90% identity 임계 클러스터 vs N. 이 임계에선 클러스터 수 ≈ N(거의 전부 distinct)라 무의미.
→ fold 수준 임계(60–70%)가 필요함을 보여줌(S13은 70% 사용). **효소 4-arm tier-50 재생성.**

## 원시 데이터 (재현용)
- `public_data/benchmark/results/sequence_space_coverage_sequences.json` — 원시 30k 서열
- `public_data/benchmark/results/sequence_space_coverage_summary.json`, `S13_clusters_vs_N_thr0.7.json`
- `temperature_diversity_recovery_sweep.json` — 온도 sweep 원시 수치
