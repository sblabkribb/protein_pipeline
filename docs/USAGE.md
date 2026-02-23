# Usage Guide

## 목적
- 자연어 프롬프트로 파이프라인을 실행하기 전에 필요한 입력을 질문 형태로 수집합니다.
- 결과 산출물은 MCP의 artifact API로 조회합니다.

## 자연어 → 질문 → 실행 (추천)
1) `pipeline.plan_from_prompt`
   - 자연어를 파싱하고, 누락된 입력을 `questions`로 반환합니다.
2) `pipeline.run`
   - 질문 응답을 합쳐 최종 실행합니다.

### 예시
- plan:
  - prompt: "rfd3 diffusion design, diffdock 사용"
- 질문 예시:
  - target_pdb 또는 target_fasta
  - rfd3_contig (A1-221 형식)
  - diffdock_ligand_smiles 또는 diffdock_ligand_sdf
  - stop_after

## 빠른 실행 (대화형 질문 생략)
- `pipeline.run_from_prompt`
  - target_pdb/target_fasta가 이미 준비된 경우 바로 실행합니다.

## 단일 도구 실행
- `pipeline.af2_predict`
  - FASTA/sequence 또는 target_pdb로 AlphaFold2만 실행합니다.
- `pipeline.diffdock`
  - protein_pdb + ligand(SMILES/SDF)로 DiffDock만 실행합니다.

## 피드백/실험/리포트
- `pipeline.submit_feedback` / `pipeline.list_feedback`
- `pipeline.submit_experiment` / `pipeline.list_experiments`
- `pipeline.generate_report` / `pipeline.save_report` / `pipeline.get_report`

### 리포트 점수 환경변수
- `PIPELINE_REPORT_BASE_SCORE` (기본 50)
- `PIPELINE_REPORT_FEEDBACK_WEIGHT` (기본 20)
- `PIPELINE_REPORT_EXPERIMENT_WEIGHT` (기본 30)
- `PIPELINE_REPORT_MIN_SCORE` / `PIPELINE_REPORT_MAX_SCORE` (기본 0 / 100)
- `PIPELINE_REPORT_EVIDENCE_MEDIUM_FEEDBACK` (기본 2)
- `PIPELINE_REPORT_EVIDENCE_HIGH_FEEDBACK` (기본 6)
- `PIPELINE_REPORT_EVIDENCE_MEDIUM_EXPERIMENT` (기본 1)
- `PIPELINE_REPORT_EVIDENCE_HIGH_EXPERIMENT` (기본 3)
- `PIPELINE_REPORT_PROMOTE_SCORE` (기본 75)
- `PIPELINE_REPORT_PROMISING_SCORE` (기본 60)
- `PIPELINE_REPORT_REVIEW_SCORE` (기본 40)
- `PIPELINE_REPORT_PROMOTE_REQUIRE_EVIDENCE` (기본 true)
- 커스텀 스코어러:
  - `PIPELINE_REPORT_SCORER` = 모듈 경로 또는 `/abs/path/to/scorer.py`
  - `PIPELINE_REPORT_SCORER_FN` = 함수명 (기본 `score_report`)

예시 (`/opt/protein_pipeline/custom_scorer.py`):
```python
def score_report(feedback_counts, experiment_counts, config):
    score = 70
    return {
        "score": score,
        "evidence": "medium",
        "recommendation": "promising",
        "scoring_config": config,
    }
```

## 산출물 확인
- `pipeline.list_artifacts`로 파일 목록
- `pipeline.read_artifact`로 파일 내용 조회

## 스크린샷 가이드
- 스크린샷 파일은 `docs/screenshots/`에 저장하세요.
- README에는 요약과 대표 이미지 1~2개만 넣고, 상세 이미지는 이 문서에 모으는 것을 권장합니다.
