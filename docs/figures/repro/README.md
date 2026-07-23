# 재현 스크립트 — 구조맥락 앙상블 다양성 그림 (2026-07)

각 그림을 원시 파이프라인 실행에서 재현하는 스크립트. 전부
`/opt/protein_pipeline/venv/bin/python`으로 실행. 원시 실행 데이터는
`/opt/protein_pipeline/outputs/abl_be_*` (아래 명시).

## Supplementary Figure S14 — 구조 앙상블 → 후보 다양성 (채택)
1. 데이터 생성 (RAPID fast-모드 기본 = RFD3 10 + BioEmu 10, 순수 2.0Å 게이트, stop_after=design):
   - `run_uniform_2p0.py`  → 1CQW, 5XJH (+1LVM, 이후 제외)
   - `rerun_1lvm.py`       → 1LVM (BioEmu max_return=8; 최종 그림엔 미사용)
   생성물: `outputs/abl_be_{1CQW,5XJH}_rfd3_bioemu_u10_2p0_s1/`, 단일 backbone은 `abl_be_{t}_single_s1/`
2. 분석·플롯: `analyze_S14.py`  → `../supp_figS14_ensemble_diversity_2p0A.png`, `../S14_ensemble_diversity_results.json`
   - 지표 1−mean pairwise id(intensive), 고정 10-서열 예산, 50% tier, single은 'input' native 참조 제외.
   - 표적 2종(1CQW·5XJH): 기본 앙상블 20구조가 2.0Å 온전히 통과하는 효소.

## Supplementary Figure S13 — 서열공간 커버리지 (채택)
- `big_sweep.py`  → 단일 vs 앙상블 backbone에서 최대 5,000서열(maskless, T=0.1) 생성 후
  ≤70% identity 누적 클러스터 수 계산. 표적 1ATJ·1TCA·1LVM. 원시 실행:
  `outputs/abl_be_{t}_single_s1/target.pdb`, `abl_be_{t}_rfd3_bioemu_s1/backbones/*/target.pdb`.
  → `../supp_figS13_sequence_space_coverage.png`.

## 지지/탐색 그림 (효소 5종·tier-50, 논문 미채택)
- `temp_sweep_tier50.py` → 온도 sweep(단일 backbone, tier-50 마스크, 5종) →
  `../expl_temperature_diversity_recovery_tradeoff.png`, `../temperature_diversity_recovery_sweep.json`.
- meanpairwise-flat / clusters@0.90: 5종 4-arm(single/rfd3_single/bioemu/rfd3_bioemu) tier-50
  designs.fasta에서 mean-pairwise·클러스터 vs 표본 수 계산(원시 실행 `abl_be_{5종}_{4arm}_s1`).

## 주의
- 다양성 지표(1−평균 pairwise identity)는 intensive(표본 수 무관)이므로, 파이프라인 기본 2서열/tier
  대신 계산엔 넉넉히 써도 곡선 값은 동일.
- 게이트는 전부 파이프라인 기본 2.0Å (S14/expl). S13만 커버리지 상한을 보려 maskless.
