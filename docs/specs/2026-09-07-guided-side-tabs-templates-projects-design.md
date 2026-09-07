# 좌측 탭 3차: 템플릿·프로젝트 + 스킬 겹침 수정 — 설계

- 날짜: 2026-09-07
- 상태: 진행 (사용자 보고: "스킬 탭이 좁으면 글자가 겹쳐" + "나머지 탭도 진행")
- 선행: 좌측 탭 껍질 + 모델·연결·스킬·에이전트 탭 배포 완료.

## A. 스킬(및 좌측 탭 공통) 텍스트 겹침 수정 — 버그

**원인**: `.skill`은 전역으로 `display: flex; align-items: center`(guided.css:260) 행이다. models/connections/skills/agents 탭의 카드는 `div.skill` 안에 제목(`.cardtitle`)과 본문(`p.note`)을 **세로로** 쌓는 구조인데, flex 행이라 본문 `p.note`가 제목 옆에 눌린 열로 배치된다 — 좁으면 겹침/압축. (협의회 카드에서 동일 결함을 `.councilbox .skill { display: block }`(guid.css:447)으로 고친 것과 같은 계열. 문헌 탭도 `.literaturebox .skill`로 이미 고침.)

**수정**: `.modelstab .skill { display: block; padding: 8px 10px; }` — 네 탭(모델·연결·스킬·에이전트)이 전부 `.modelstab` 패널 안에 있으므로 한 규칙으로 해결. `.councilbox`/`.literaturebox` 규칙과 동일 패턴.

## B. 연결 탭 — 성공 화면에 "다시 실측" 버튼

최종 리뷰 후속 1번: 성공(done) 상태에서 스냅샷이 고정된다. 상단에 "다시 실측" ghost 버튼 추가 → `window.__connectionsTabLoad(true)` (force 재프로브). 스펙 A의 "재프로프 버튼" 이행.

## C. 템플릿 탭 (프런트만)

- 데이터: `pipeline.list_models {}`의 `purposes`(모델 탭과 동일 도구, 재사용).
- 내용: 목적 카드 목록(한글명 + 검증 칩 + 단계 요약). 카드 클릭 = **"이 목적으로 시작"** — 중앙 목표 섹션의 purpose select를 설정하고 `onPurposeChange()`를 돌린 뒤 중앙 1단계로 이동(기존 `showStep(1)`/objective 패널 활성). 중앙 1단계의 목적 카드와 데이터는 같지만 탭은 **선택·이동 허브** 역할(중복 렌더가 아니라 진입점).
- 모듈 `guided/templates.js` (기존 패턴), 탭 진입 1회 로드 캐시, 재시도 버튼.
- 목적 선택은 중앙의 기존 로직(`select.value = purpose; onPurposeChange();`)을 재사용 — guided.js에서 중앙 요소에 접근하는 헬퍼 1개(`startFromPurpose(purpose)`)를 facade에 두고 탭은 호출만.

## D. 프로젝트 탭 (프런트만)

- 데이터: `pipeline.list_projects {limit: 200}` + 드릴다운 `pipeline.list_rounds {project_id, limit: 100}` (기존 도구, 백엔드 변경 없음).
- 내용: 프로젝트 카드(이름·owner·설명 요약·아카이브 여부) → 클릭하면 해당 프로젝트의 라운드 목록(라운드 id·생성 시각·비고) 펼침. 라운드는 읽기 전용 참조(실행으로 이동하는 링크는 run_id가 기록돼 있으면 표시).
- 모듈 `guided/projects.js`. 프로젝트 목록은 탭 진입 1회 로드 + 재시도; 라운드는 프로젝트 클릭 시 로드(펼침/접음).
- 권한: 서버 세션이 보는 목록 그대로(구 app과 동일 — user 파라미터 미전달).

## E. 톨러런스/테스트

- 겹침 수정: 소스 계약 테스트 1줄(`.modelstab .skill` 규칙 존재) — guided-models.test.js에 추가.
- 연결: done 상태에 재실측 버튼 — guided-connections.test.js에 케이스 추가.
- 템플릿: `templateCardModels` 순수 + 렌더 + "이 목적으로 시작" 액션 소스 계약(`startFromPurpose`).
- 프로젝트: `projectCardModels`/`roundRowModels` 순수 + 렌더(펼침 상태) + 소스 계약(list_projects/list_rounds 호출).
- 기존 169 테스트 전부 유지.

## F. 범위 밖

- 프로젝트 생성/수정(save_project/archive) — 읽기 전용 유지 (탭의 목적은 탐색).
- 라운드→실행 심화 연동(라운드 기반 rerun 프리셋).
