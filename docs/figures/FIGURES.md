# RAPID 그림 관리 매니페스트

본문/보충자료의 모든 그림에 대해 **생성 스크립트 → 입력 데이터 → 출력 파일**을 한곳에 정리한다.
글꼴·색은 `repro/figstyle.py`(공용 스타일) 한 곳에서 관리한다 — `FONT` 한 줄만 바꾸면 이 파일을 import하는 모든 그림이 함께 바뀐다.

## 본문 Figure

| 본문 | 생성 스크립트 | 입력 데이터 | 출력 PNG | 상태 |
|---|---|---|---|---|
| **Figure 1** (파이프라인 전체 흐름) | `repro/make_fig1_fullflow.py` | (도식, 데이터 없음) | `fig1_fullflow.png` | ✅ 재현 |
| **Figure 2 A–D** (고정 예산 triage) | `../../scripts/benchmark/18_make_surrogate_triage_budget_figure.py` | `public_data/benchmark/results/surrogate_triage_*.csv` | (docx image2) | ✅ |
| **Figure 2 E** (비학습 baseline vs 학습) | `repro/make_fig2E_baseline.py` | `benchmark/results/baseline_ranking_comparison.csv` | `fig2E_baseline.png` | ✅ 재현 (신규) |
| **Figure 3** (구조 맥락 비교) | `../../scripts/benchmark/backbone_ensemble_ablation.py` (plot 함수) | `benchmark/results/backbone_ensemble_ablation_summary.csv` | `figures/benchmark/fig12_*.png` | ✅ |
| **Figure 4** (3-arm 다양성) | `repro/make_fig4_threeway_matched.py` | `public_data/benchmark/results/structural_context_threeway_N9.csv` | `fig4_threeway_matched.png` | ✅ 재현 |
| **Figure 5** (앙상블→다양성 곡선) | `repro/analyze_S14.py` | `outputs/abl_be_{1CQW,5XJH}_*` | `supp_figS14_ensemble_diversity_2p0A.png` | ✅ 재현 |

## 보충 Figure

| 보충 | 생성 스크립트 | 출력 | 상태 |
|---|---|---|---|
| **S13** (서열공간 커버리지) | `repro/big_sweep.py` | `supp_figS13_sequence_space_coverage.png` | ✅ 재현 |
| **S11** (오케스트레이션 구현 상세) | `../../scripts/benchmark/08_make_architecture_figure.py` (추정) | `figures/benchmark/fig1_architecture.png` | ⚠️ 확인 필요 |
| **S1–S10, S12** | `../../scripts/benchmark/06_make_figures.py · 11_make_method_figures.py · 12_make_cath_curated_figure.py` 등 | `figures/benchmark/` | ⚠️ 개별 확인 필요 |

## docx 임베딩 매핑 (manuscript_KR_BiB_final_v3.docx)

`word/media/imageN.png` ↔ 본문 그림:
- image1 = Figure 1, image2 = Figure 2 A–D, image3 = Figure 2 E,
  image4 = Figure 3, image5 = Figure 4, image6 = Figure 5.
- 이미지 교체 시 종횡비가 다르면 `<wp:extent>`·`<a:ext>`의 cy를 `cx/새 종횡비`로 갱신해야 왜곡이 없다.

## 재생성

```bash
# 재현 가능한 그림(위 ✅) 일괄 재생성 — 글꼴은 figstyle.py 따름
/opt/protein_pipeline/venv/bin/python repro/build_all_figures.py
```

Fig2 A–D · Fig3 · 보충 S1–S12는 벤치마크 데이터/환경이 필요해 `scripts/benchmark/`에서 개별 실행한다.

## 주의 / TODO
- 글꼴 변경: `repro/figstyle.py`의 `FONT`만 수정 → `build_all_figures.py` 재실행.
- Fig2 E는 과거 생성 스크립트가 없어 ad-hoc였음 → `make_fig2E_baseline.py`로 복원 완료.
- 보충 S11/S1–S12 생성 스크립트 매핑은 확인 후 이 표를 채울 것.
