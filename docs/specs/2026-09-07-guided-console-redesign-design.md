# Guided 단일화면 콘솔 재설계 (design)

- 날짜: 2026-09-07
- 상태: 승인됨 (사용자 확정: B안 / 접근 1 / guided.html 대체 / 핵심 플로우 우선)
- 대상: `frontend/guided.html` + `frontend/guided.js` (+ `frontend/guided.css`)

## 배경과 목표

`guided.html`은 목표 → 계획(근거) → 승인 → 실행 폴링에 특화된 스테퍼다. 메인 앱
(`index.html` + `app.js`)은 10개 탭(home/fast/advanced/evolution/studio/monitor/
cath/rounds/analyze/mcp)에 전체 기능을 나눠 담고 있다. 이 재설계는 guided를
**Ditto(3-페인 단일 화면)처럼, 탭 이동 없이 설계→실행→결과가 한 화면에서 이어지는
콘솔**로 재탄생시킨다.

## 범위

**1차(이 설계)에 포함**

- 설계 목표 → 계획(근거) → 질문/승인 → 실행 → 모니터 → 결과(퍼널/히트리스트) →
  구조 뷰 → 근거 뷰, 전부 한 화면
- 좌측 실행 목록 전환 (다중 실행 모니터링)
- 3Dmol 구조 뷰어 + 잔기 피커 + 주석
- 리포트 뷰 (report.md 렌더)

**1차에서 뺌 (링크로 대체)**

- RunPod Admin, CATH 배치, rounds/projects, MCP 설정 → 상단 "운영" 링크로 기존
  페이지 이동
- Compare Studio 전체(비교 프리셋·차트·run-to-run 종합) → 2차. 1차 Results 탭은
  히트리스트 + 단순 비교(`compare_runs` 1회 호출 요약)까지만

**불변 조건**

- `index.html`/`app.js`는 한 줄도 수정하지 않는다. 탭 앱은 기존 그대로 남고, 새
  콘솔이 안정화된 뒤 은퇴 여부를 별도로 결정한다.
- 백엔드/MCP 도구 변경 없음. 화면이 결정을 만들지 않는다는 guided의 철학(서버가
  준 근거·경고만 표시)은 그대로 유지한다.

## 화면 구조 (B안 — 계획 폼 중심)

```
상단바: RAPID · 실행 상태 칩(스테이지/비용) · 사용자 · (운영 링크)
좌 22%            중앙 48%                        우 30%
실행 목록          ① 설계 목표 (슬라이더+제약)      탭 4개
 (내 실행만,        ② 계획 카드 (결정+근거+질문)      Run | Results | Structure | Evidence
  기존 스코핑 동일)  ③ 승인 → 실행
운영 링크          ④ 대화 (접이식, 계획 수정용)
```

- **좌**: `pipeline.list_runs` (기존과 동일하게 사용자 스코프만). 항목 = run_id,
  상태 요약, 진행 스테이지. 선택 시 중앙·우가 해당 실행에 동기화. 새 설계 시작
  버튼. 운영 링크는 기존 페이지로의 일반 하이퍼링크.
- **중앙**: 현재 guided의 흐름이 주인공.
  1. 설계 목표 폼 — 슬라이더 7종(solubility … developability) + 제약(budget,
     rmsd_max 등) + purpose 선택. 가중치 검증(0..1)은 서버 계약 그대로.
  2. 계획 카드 — `plan_from_objective` 결과. 결정별 근거 배지(측정/문헌/가정),
     locked 필드는 비활성 입력, warnings는 그대로 노출(숨기지 않음),
     `objective_status` 상세는 Evidence 탭으로.
  3. 질문 → 답변 → `approve_plan` → `pipeline.run`.
  4. 대화(접이식) — `discuss_plan` + proposed_edits 파싱 → 계획 카드 재렌더.
     펼치기 전에는 한 줄 입력만 보인다.
- **우 탭**
  - **Run**: 스테이지 진행( lib/pipeline.js 의 RUN_PROGRESS_PLANS 사용), 현재
    상태/ETA 칩, 아티팩트 브라우저(`list_artifacts` → 유형별 그룹 →
    `read_artifact` 미리보기 — 텍스트/이미지/JSON 요약), 리포트 뷰
    (`generate_report`/`get_report` → md 렌더), `cancel_run`.
  - **Results**: 게이트 퍼널(티어별 후보→SoluProt→AF2 통과 수 — status/artifacts
    에서 집계), 히트리스트(`get_hit_list`), 비교 요약(`compare_runs` 1회 호출
    요약 카드). 2차에서 Compare Studio로 확장.
  - **Structure**: 3Dmol 뷰어(ranked_0 등 예측 PDB), 잔기 피커(`lib/residue-picker.js`),
    고정 위치/마스크 주석 오버레이. PDB는 `read_artifact`로 가져온다.
  - **Evidence**: 계획의 근거 모음 — kind(측정/문헌/가정)별 필터, statement,
    source(파일/논문 문자열), objective_status의 detail/to_enable 전문.

## 데이터 흐름 (백엔드 변경 0)

```
pipeline.list_runs ─┐
                    ├─ 좌측 목록 → 선택 → 우/중앙 동기화
pipeline.status ────┘
pipeline.plan_from_objective → 계획 카드 (+ objective_status → Evidence 탭)
pipeline.discuss_plan → proposed_edits → 계획 카드 재렌더
pipeline.approve_plan → pipeline.run(run_id) → pipeline.status 폴링
pipeline.list_artifacts/read_artifact → Run/Structure 탭
pipeline.get_hit_list / compare_runs → Results 탭
pipeline.generate_report/get_report → Run 탭 리포트 뷰
pipeline.cancel_run → 중앙/Run 탭
```

- 폴링: 실행 중 5초, 백그라운드(실행 없음/완료) 30초. 자동폴링 토글 유지.
- 401: 재로그인 게이트로 복귀(기존 패턴). 토큰 키(`kbf.token`) 공유 유지 —
  다른 화면과 세션 공유.
- `target_fasta`/`target_pdb`는 파일 내용 전송(기존 계약), PDB ID/URL 단축
  입력도 유지.

## 코드 구성 (접근 1 — guided 확장 + lib 재사용)

- `guided.js`를 섹션 모듈로 분해: `objective-form` / `plan-card` /
  `conversation` / `run-monitor` / `results` / `structure-view` /
  `evidence-view` / `runs-sidebar` / `topbar`. 규모가 커지면 `guided/`
  디렉터리 서브모듈로 분리(진행하며 판단, 기준: 한 파일 1천 줄 초과 시).
- **재사용 (수정 없이 import)**: `lib/pipeline.js`(스테이지 순서, 진행 플랜,
  아티팩트 유형 라벨, RFD3 기본값), `lib/compare.js`, `lib/residue-picker.js`,
  `lib/md.js`, `lib/auth.js`, `lib/windowing.js`. 3Dmol은 기존과 같은 CDN 스크립트.
- **새 작성**: 우측 탭 4개 뷰, 좌측 실행 목록 뷰, 상단바 칩. 렌더만 새로 —
  로직은 lib에서.
- `guided.css`를 3페인 그리드 + 탭 스타일로 확장. 기존 `styles.css`(메인 앱)와의
  시각 일관성은 변수(색/타이포)만 맞춘다.

## 에러 처리

- 실행 실패: status.json의 error + 관련 아티팩트(예: af2_scores.json의
  errors 맵)로의 직접 링크를 중앙 상단 배너와 Run 탭에 함께 표시.
- 아티팩트 읽기 실패/빈 값: 탭에 "아직 없음" 상태를 명시(빈 화면이 아님).
- 도구 호출 오류: 기존 `unwrapToolResponse` 봉투 처리 재사용 — 200이라도
  error 필드를 놓치지 않는다.
- 폴링 일시 실패: 연속 3회 실패까지 재시도, 이후 폴링 중단 + 수동 새로고침 버튼.

## 테스트

- `frontend/tests/guided.test.js` 스타일 유지 — 소스 파싱, 도구 계약(plan/approve가
  문서화된 MCP 도구를 쓰는지), locked 필드 비활성, 근거 3종 라벨, 경고 노출 등
  기존 테스트는 전부 통과해야 한다.
- 신규: 탭 전환/렌더 로직을 순수 함수로 분리해 테스트(퍼널 집계, 아티팩트 그룹핑,
  진행 퍼센트 계산), 실행 목록 정렬/선택 상태, 폴링 백오프.
- CI: 기존 `node --test` 흐름 그대로. 빌드(vite)는 guided.html이 rollupOptions
  input에 있는지 다시 확인한다 — 이미 등록돼 있다(vite.config.mjs).

## 배포/롤백

- dev push → 확인 → staging/prod (기존 브랜치 플로우). 새 콘솔은 기존 URL
  (`/guided.html`)에서 서빙되고 루트(`/`)는 계속 기존 탭 앱을 가리킨다 — 두
  진입점 모두 유지되므로 롤백은 커밋 되돌리기로 충분하다. 루트 리다이렉트 전환은
  새 콘솔이 안정화된 뒤 별도 결정으로 둔다.

## 2차 범위 (이 설계 밖)

- Compare Studio 전체(비교 프리셋, 후보 차트, run-to-run 종합), feedback/experiments,
  Workflow Studio(체크포트 리뷰 게이트), 프로젝트/라운드, CATH/RunPod Admin 통합.
- i18n(영어 토글) — 1차는 한국어 고정.

## 결정 기록

1. 위치/관계: guided.html을 대체, 기존 탭 앱은 유지 후 은퇴 별도 결정.
2. 기능 범위: 핵심 플로우 우선(설계→실행→모니터→결과+구조), 운영 도구는 링크.
3. 중앙 패널: B안(계획 폼 중심, 대화는 보조).
4. 구현: 접근 1 — guided.js 확장 + lib 재사용, app.js 무수정.
5. 1차 Results는 히트리스트+단순 비교까지, Compare Studio 전체는 2차.
6. 실행 목록 스코핑: 기존과 동일(사용자 스코프).
