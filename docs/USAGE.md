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

## 산출물 확인
- `pipeline.list_artifacts`로 파일 목록
- `pipeline.read_artifact`로 파일 내용 조회

## 스크린샷 가이드
- 스크린샷 파일은 `docs/screenshots/`에 저장하세요.
- README에는 요약과 대표 이미지 1~2개만 넣고, 상세 이미지는 이 문서에 모으는 것을 권장합니다.
