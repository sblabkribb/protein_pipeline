# 재현성 안내

이 문서는 원고와 보충자료의 수치·표·그림이 어떤 코드와 입력에서 나왔는지, 그리고
외부에서 무엇을 어디까지 다시 실행할 수 있는지 정리한다.

## 1. 재현의 두 수준

이 저장소가 제공하는 재현은 아래 두 수준 중 **두 번째**다.

| 수준 | 내용 | 제공 여부 |
| --- | --- | --- |
| 전체 파이프라인 | MMseqs2 → ProteinMPNN → AlphaFold2/ColabFold 까지 다시 계산 | 제공하지 않음 |
| 용해성 재채점 | 격자의 서열을 SoluProt 으로 다시 채점 | 제공함 |
| 분석 재실행 | 저장된 구조예측 격자에서 선택 규칙과 통계를 다시 계산 | 제공함 |

구조예측 자체를 다시 수행하지 않으므로, 접기 단계의 확률적 변동은 이 재현으로
평가되지 않는다. 보고된 모든 정책 비교는 완성된 후보 격자 위의 오프라인 재생이며,
이 점은 원고 4.4절과 보충자료 S9절에도 적혀 있다.

## 2. 실행 방법

```bash
bash scripts/reproduce_paper_tables_figures.sh
```

스크립트는 분석을 임시 디렉터리에 다시 실행하고, `public_data/benchmark/gate0/` 의
원본 결과 파일과 **모든 수치를 상대 오차 1e-9 로 대조**한다. 불일치가 하나라도 있으면
종료 코드 1 을 돌려준다. 그림까지 다시 그리려면 환경 변수를 비우고 실행하고,
분석만 확인하려면 `REPRO_SKIP_FIGURES=1` 을 준다.

### 용해성 점수를 직접 다시 만들려면

격자의 `soluprot` 열은 SoluProt 1.0.1.0 공식 배포본으로 매긴 값이다. 이 도구는
Python 3.7 과 scikit-learn 0.20.1 을 요구하므로 분석 환경과 분리해 설치한다.

```bash
# SoluProt 과 데이터
curl -L -o soluprot.zip 'https://loschmidt.chemi.muni.cz/soluprot/?f=soluprot.zip'
curl -L -o soluprot_data.zip 'https://loschmidt.chemi.muni.cz/soluprot/?f=soluprot_data.zip'
unzip soluprot.zip && unzip soluprot_data.zip

# 전용 환경 (배포본이 요구하는 버전)
micromamba create -y -n soluprot -c conda-forge \
    python=3.7 scikit-learn=0.20.1 biopython=1.74 pandas tqdm

# USEARCH (CC0 공개 도메인 배포본, md5 fa050a3029d33b7b25036a2cc8c6da97)
curl -L -o usearch11 \
  https://raw.githubusercontent.com/rcedgar/usearch_old_binaries/main/bin/usearch11.0.667_i86linux64
chmod +x usearch11

# 채점
python3 scripts/score_soluprot.py \
    --cohort public_data/benchmark/gate0/hier_confirmatory \
    --soluprot-dir ./soluprot-1.0.1.0 \
    --soluprot-python $MAMBA_ROOT_PREFIX/envs/soluprot/bin/python \
    --usearch ./usearch11 --out /tmp/regrid.csv
```

`--out` 으로 사본을 만들어 저장소의 격자와 `soluprot` 열을 비교하면 값이 일치한다.
TMHMM 은 별도 학술 등록이 필요해 재현성을 해치므로, 저자가 함께 배포하는 TMHMM
비의존 모델 `grad_clf_v1_tc_notmhmm` 을 사용한다. SoluProt 은 학술용 무료
라이선스이며 상업적 사용은 배포처에 문의해야 한다.

재현이 결정적인 이유는 세 가지다. 난수 시드(42, 123, 7, 2024, 31337)와 부트스트랩
설정(2,000회, seed 20260921, 재표집 단위는 표적)이 코드에 고정되어 있고, 동점 처리가
식별자 사전순으로 정해져 있으며, 선택이 미리 고정된 후보 색인 위에서만 이루어진다.

## 2.1 이 패키지가 검증하는 범위

재현 스크립트가 다시 실행하고 대조하는 것은 원고와 보충자료가 인용하는 열한 개
분석이다. `public_data/benchmark/gate0/` 에는 개발 과정에서 만든 다른 결과 파일도
함께 들어 있는데, 이들은 논문이 인용하지 않으며 SoluProt 을 공식 배포본으로 교체하기
이전에 생성된 것이 섞여 있다. 논문의 수치를 확인할 때에는 위 열한 개와 그 입력만
보면 된다.

## 2.2 다중 백본 다양성 비교의 출처

원고 3.3절과 그림 3은 `public_data/benchmark/results/structural_context_threeway_N9.csv`
에서 그린다. 이 표는 9개 CATH 표적에서 세 조건(단일 백본·대리모델, 앙상블·무작위,
앙상블·대리모델)의 선택 20개를 요약한 값이다.

생성 조건은 다음과 같다. 앙상블 크기는 표적당 50~60개(평균 58.3)다. 일곱 표적은 RFD3 30개와 BioEmu 30개를
받았고, 1advA02 는 RFD3 상한이 20개, 3it4B01 은 BioEmu 상한이 25개여서 각각 50개와
55개다. 세 경우 모두 상한만큼 생성되어 중도 손실은 없다. 조건별 후보 풀은 설계상 약 10,000개를
목표로 했으나 실현값은 5,397~9,999개다. 대리모델은 초기 30개의 구조예측 결과로 학습해
pLDDT 를 예측하며, Random Forest·능형회귀·LightGBM·XGBoost 를 교차검증 스피어만
상관으로 표적마다 자동 선택한다. **용해성은 이 선택에 쓰이지 않는다** — 표의 SoluProt
열은 선택 결과를 사후에 기술한 값이고, 무작위 조건은 공식 배포본으로 다시 채점하지
않아 비워 두었다.

선택을 만든 실행 디렉터리 자체는 용량 때문에 이 패키지에 넣지 않았다. 표의 값이 그
선택에서 나온다는 것은 저장된 선택 목록으로 다양성과 pLDDT 를 다시 계산해 확인했다.

## 3. 환경

의존성은 `requirements-repro.txt` 에 고정해 두었다.

```bash
python3 -m venv .venv-repro
.venv-repro/bin/pip install -r requirements-repro.txt
PYTHON=.venv-repro/bin/python3 bash scripts/reproduce_paper_tables_figures.sh
```

보고된 실행 환경은 Python 3.12.3, scikit-learn 1.8.0, NumPy 2.4.4 이다.
검증은 두 환경에서 했다. 보고된 환경에서는 열한 개 결과 파일이 **바이트 단위로**
원본과 같았다. scikit-learn 1.9.0 · NumPy 2.5.3 으로 올린 환경에서는 구조 분산 진단
한 건만 부동소수점 최하위 자리에서 달라 1e-9 허용 오차 안에서 일치했고 나머지는
바이트 단위로 같았다. 따라서 이 범위의 버전 차이는 결론을 바꾸지 않는다.

| 분석 | 비교한 수치 |
| --- | ---: |
| 실험 2 기준선 | 2,212 |
| 초기 배분 평가 | 740 |
| 깊이 확장 | 366 |
| 선택 이득 분해 | 572 |
| EFBC 분산도 | 3,335 |
| 구조 분산 진단 | 2,804 |
| 후속 평가 주 분석 | 1,885 |
| 종료 규칙 진단 | 1,753 |
| 파일럿 전이 시험 | 1,927 |
| 후보 집중도 진단 | 328 |
| 배분 요소 분해 | 113 |
| **합계** | **16,035** |

불일치는 0건이었다.

ESM-2 임베딩은 `data/benchmark/*_emb_320d.npz` 캐시에서 읽는다. 캐시가 있으면
네트워크 접근이 필요 없다. 캐시가 없을 때만 `ESM_EMBEDDING_URL` 환경 변수로 임베딩
서버를 지정한다. 저장소에는 내부 호스트 주소를 기본값으로 두지 않는다.

## 4. 입력 데이터

| 경로 | 내용 | 크기 |
| --- | --- | --- |
| `public_data/benchmark/gate0/hier_confirmatory/af2_order_metric.csv` | 후속 평가 구조예측 격자(7,728행: ok 7,722 · failed 6) | 약 5 MB |
| `public_data/benchmark/gate0/hier_confirmatory/candidates.json` | 후보 서열과 백본·표적 식별자 | 약 3 MB |
| `public_data/benchmark/gate0/hier_confirmatory/mpnn_scores.json` | 백본 조건부 ProteinMPNN 점수 | 약 1 MB |
| `data/benchmark/hier_confirmatory_emb_320d.npz` | ESM-2 8M 평균 풀링 320차원 임베딩 캐시 | 약 9 MB |
| `public_data/benchmark/gate0/hier_confirmatory/af2_models/` | 예측 구조 파일 7,722개 | 약 222 MB |

앞의 네 파일만 있으면 통계 분석은 모두 재실행된다. 다른 분석에 필요한 임베딩 캐시
(`v2_`, `depth_pilot_`, `holdout_grid_`)까지 더해도 저장소에 들어가는 입력은 약
28 MB 다. 구조 파일은 보충자료 S5.2 의 구조 분산 진단에만 쓰이므로 별도 보관소로
배포한다. 묶음은 다음으로 만든다.

```bash
bash scripts/make_zenodo_package.sh
```

모든 입력·결과·사전지정 문서의 SHA-256 은 `public_data/benchmark/gate0/repro_manifest.json`
에 있고, 다음으로 다시 만든다.

```bash
python3 scripts/make_repro_manifest.py --out public_data/benchmark/gate0/repro_manifest.json
```

격자의 `soluprot` 열은 SoluProt 1.0.1.0 공식 배포본의 출력이다. 초기 분석에서는
조성 기반 대리 점수를 쓴 적이 있으나, 그 격자는 배포본에 포함하지 않는다.
위의 재채점 절차를 따르면 공개된 격자와 같은 값을 다시 만들 수 있다.

격자의 `status` 열이 `ok` 가 아닌 행은 모든 분석에서 후보 집합에서 제외된다. 즉 실행에
실패한 6건은 통과 실패로 세지 않고, 재시도하지 않으며, 예산에도 포함하지 않는다.

## 5. 분석과 결과 파일의 대응

| 분석 | 스크립트 | 결과 파일 | 문서 위치 |
| --- | --- | --- | --- |
| 실험 2 기준선 | `scripts/benchmark/33_v2_mpnn_baseline.py` | `v2_mpnn_baseline.json` | 원고 3.2절, 보충 표 S1 |
| 초기 배분 평가 | `scripts/benchmark/35_hierarchical_replay.py` | `hierarchical_replay.json` | 보충 S2.1, 표 S2 |
| 깊이 확장 | `scripts/benchmark/37_depth_scaling.py` | `depth_scaling.json` | 보충 S2.3, 표 S3 |
| 선택 이득 분해 | `scripts/benchmark/39_selection_gain_decomposition.py` | `selection_gain_decomposition.json` | 원고 3.5절, 보충 표 S5 |
| EFBC 분산도 | `scripts/benchmark/40_coverage_preserving.py` | `coverage_preserving.json` | 원고 3.6절, 보충 표 S6·S7 |
| 구조 분산 진단 | `scripts/benchmark/41_structural_dispersion.py` | `structural_dispersion.json` | 보충 S5.2 |
| 후속 평가 주 분석 | `scripts/benchmark/42_hierarchical_confirmatory.py` | `hierarchical_confirmatory.json` | 원고 3.4절·표 3, 보충 S3, 표 S4·S11 |
| 종료 규칙 진단 | `scripts/benchmark/45_stop_rule_diagnosis.py` | `stop_rule_diagnosis.json` | 보충 S6, 표 S8 |

그림은 `scripts/paper_runs/61_manuscript_figures_en.py`(본문)와
`scripts/paper_runs/62_confirmatory_figures_en.py`(확증 분석)가 만들며 출력은
`figures/submission/` 에 쌓인다.

## 6. 사전지정 문서

결과를 보기 전에 고정한 계획 문서와 그 해시는 다음과 같다.

| 분석 | 문서 | sha256 |
| --- | --- | --- |
| 후속 평가 | `docs/specs/hierarchical-confirmatory-prespec.md` | `b63edd1f93d10db05e0cea1f8481d61cffdd3a7cd168cf787b20db22cb73d569` |
| 초기 배분 평가 | `docs/specs/hierarchical-replay-prespec.md` (v1.1) | `22b63f2878d61cf2a68def4611af2c54ec0d519f14bab0cc68efa2a567b2bcd2` |
| EFBC 분산도 | `docs/specs/coverage-preserving-prespec.md` | 결과 파일의 `prespec` 항목 참조 |

각 결과 JSON 은 자신이 따른 사전지정 문서 경로와 해시를 함께 저장한다.

## 7. 공개 전 확인

`docs/release_checklist.md` 를 따른다. 특히 아래 두 가지를 반드시 확인한다.

1. 분석 스크립트와 데이터 파일에 내부 호스트 주소가 남아 있지 않은지 확인한다.
   구조예측 격자의 `error` 열과 일부 백본 메타데이터에는 실패 당시의 내부 주소가
   문자열로 기록되어 있을 수 있다. 공개용 사본에서는 이 값을 가린 뒤 배포한다.
2. 재현에 필요한 입력 파일이 실제로 저장소나 보관소에 포함되는지 확인한다. 저장소
   기본 설정은 `public_data/` 를 산출물로 보고 무시하므로, 필요한 파일은 명시적으로
   허용 목록에 넣거나 별도 보관소로 배포해야 한다.
