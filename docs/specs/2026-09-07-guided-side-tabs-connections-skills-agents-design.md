# 좌측 탭 2차: 연결·스킬·에이전트 — 설계

- 날짜: 2026-09-07
- 상태: 진행 (사용자 승인: "나머지도 진행"). 템플릿·프로젝트 탭은 별도 과제로 유지(아래 E).
- 선행: 좌측 탭 껍질 + 모델 탭(85ea521 계열) 이미 배포. 이 설계는 같은 껍질에 탭 3개를 추가한다.
- 참조: Ditto `evidence.py source_status`(실측 프로브)·`skills.py`(builtin+사용자 작성) 패턴.

## A. 연결 탭 (프런트만)

- 데이터: `pipeline.list_models {check_liveness: true}` (기존 도구, 백엔드 변경 없음).
- 블록:
  1. **엔드포인트 실측** — `liveness` 맵 테이블: 모델 id / 엔드포인트 / 도달 점(dot) / ready / `model_mismatch` 경고. "연결됨"을 상수로 주장하지 않고 매번 실측 — 버튼 클릭마다 재프로브(6초 타임아웃, 서버측).
  2. **BOP 워커 요약** — declared / reachable 개수.
  3. **포털 연결** — `connections.portal_mcp`: configured·integration·would_unlock·still_blocked_note.
- 기존 운영 블록의 미니 프로브(probeBtn)는 그대로 유지 — 탭은 풀 뷰.
- 모듈 `guided/connections.js` (models.js 패턴). 로딩: 탭 진입 시 자동 1회, 재프로브 버튼.

## B. 스킬 탭 (백엔드 + 프런트)

### B1. 백엔드 — 협의회 전문가 헌장의 사용자 치환

- **저장소**: `<PIPELINE_OUTPUT_ROOT>/_council_skills/<expert_id>.json` — `{"charter": str, "updated_utc": str}`. output root 아래라 커밋 대상 아님.
- **신규 도구 3개** (`tools.py` + `plan_council.py` 확장):
  - `pipeline.list_council_skills` `{}` → `{skills: [{expert_id, name, source: "builtin"|"user", charter, updated_utc?}]}` — builtin 헌장은 코드 상수에서, user 파일이 있으면 그것으로 대체해 보여준다.
  - `pipeline.save_council_skill` `{expert_id, charter}` — expert_id는 `EXPERTS` 5종만, charter는 strip 후 1~8000자. 위반은 `{"error": ...}`.
  - `pipeline.reset_council_skill` `{expert_id}` — 사용자 파일 삭제(없어도 ok).
- **협의회 반영**: `_ask_expert`는 호출 시점에 사용자 파일을 읽어 있으면 그 헌장으로, 없으면 builtin. 파일 파싱 실패 시 builtin으로 조용히 폴백(주석 명시).
- **보안**: charter는 LLM system 프롬프트로만 쓰인다 — 길이 상한 외 실행·포맷 권한 없음.

### B2. 프런트

- 모듈 `guided/skills.js`: 스킬 카드 5장(전문가명 + 출처 칩 builtin/사용자 + 헌장 본문). 각 카드에 "편집"(textarea로 전환 + 저장/취소)과 "초기화"(사용자 파일 삭제) 액션.
- 저장/초기화 후 목록 재로드. 탭 진입 1회 로드 + 액션 후 갱신.
- 스킬 탭 헤더에 note: "헌장은 계획 협의회 전문가의 관점을 정의합니다. 저장 시 다음 협의회부터 반영됩니다."

## C. 에이전트 탭 (프런트만)

- 데이터: `pipeline.list_agent_events {run_id, limit}` (기존 도구).
- 현재 선택된 실행(`runState.runId`)의 agent panel 이벤트를 표시: 스테이지별 판정(합의/해석/에러). 실행을 선택하면 갱신 — `selectRun`에서 에이전트 탭이 활성 상태일 때만 재조회(불필요한 호출 방지: 탭 진입/런 전환 시 로드).
- 실행 미선택 시 note. 모듈 `guided/agents.js`.

## D. 톨러런스/테스트

- 백엔드 `test_council_skills.py`: list(builtin+user 병합, 파일 깨짐 무시), save(검증·상한), reset, 협의회 폴백(깨진 파일 → builtin), 도구 등록. `plan_council.py`의 헌장 선택은 fake gemini로 검증.
- 프런트: `guided-connections.test.js`, `guided-skills.test.js`, `guided-agents.test.js` — 순수 렌더 + 소스 계약(탭 앵커, 재프로브, 저장 액션, 런 연동).
- 스킬 파일은 JSON 저장이라 YAML 의존 없음.

## E. 범위 밖

- **템플릿 탭**: 목적 카드가 이미 중앙 1단계에 있음 — 중복이라 제외(추후 워크플로 템플릿 체계화 때 재검토).
- **프로젝트 탭**: project_id 그룹핑에 백엔드 목록 지원 확장 필요 — 별도 설계.
- LLM(Gemini) 설정 상태 표시 — `list_models` 응답에 없어 이번엔 제외.
