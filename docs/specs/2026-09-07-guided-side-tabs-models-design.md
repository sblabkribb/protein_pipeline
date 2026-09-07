# 좌측 탭 껍질 + 모델 탭 — 설계

- 날짜: 2026-09-07
- 상태: 승인됨 (사용자 선택: 껍질 + 모델부터 — 이후 연결·스킬·프로젝트/템플릿/에이전트는 각각 별도 단계)
- 범위: 프런트만. 백엔드 도구 `pipeline.list_models` 재사용(변경 없음). `index.html`/`app.js`/`lib/` 무변경.

## 0. 배경

guided 콘솔의 좌측 레일은 실행 목록 + 운영 링크만 있다. Ditto처럼 좌측에 기능 탭(프로젝트·템플릿·스킬·연결·모델·에이전트)을 두기로 방향이 정해졌고, 이 설계는 그 **껍질(탭 내비게이션)** 과 가장 저렴한 첫 탭 **모델**을 다룬다.

## A. 껍질 (Shell)

### A1. HTML (`guided.html`)

- `.side` 최상단에 탭 스트립:
  ```html
  <nav class="sidetabs" role="tablist" aria-label="좌측 패널">
    <button class="sidetab active" data-sidetab="runs" role="tab" aria-selected="true">실행 목록</button>
    <button class="sidetab" data-sidetab="models" role="tab" aria-selected="false">모델</button>
  </nav>
  ```
- 기존 두 `<section class="block">`(실행, 운영)을 `<div id="sideRuns">`로 감싼다. 내부는 그대로.
- 그 아래 `<div id="sideModels" class="hidden" role="tabpanel"></div>` 추가.

### A2. 동작 (`guided.js`)

- `showSideTab(name)`: `sideRuns`/`sideModels` 토글 + 버튼 active/aria-selected + `localStorage("kbf.guided.sidetab")` 저장.
- 초기화: 브라우저 전용 초기화 블록에서 `initSideTabs()` — 저장된 탭 복원(저장값이 `models`가 아니면 `runs`로 정정), 탭 버튼에 클릭 리스너 1회 연결.
- **중앙·우측 워크플로 무관**: 좌측 탭 전환은 selectRun/폴링/계획 흐름에 어떤 영향도 없다.

### A3. CSS (`guided.css`)

- `.sidetabs` 가로 스트립(간격·하단 구분선), `.sidetab`(투명 배경, active는 잉크색+밑줄) — 기존 토큰 재사용. 최소 규칙만.

## B. 모델 탭

### B1. 모듈 `frontend/guided/models.js` (council.js 패턴)

- 순수: `modelsTabModels(payload)` — `pipeline.list_models` 응답을 표시 모델로:
  ```
  { purposes: [{purpose, executable, validated, stages?}],
    objectives: [{key, state: "measured"|"unvalidated"|"none"}],
    models: [{id, endpoint_summary, portal_only}] }
  ```
  - objectives 상태 판정: `measurable_objectives` ⊂ measured, `runnable_but_unvalidated_objectives` ⊂ unvalidated. KNOWN 목적 목록은 응답의 목적 라우팅에서 수집(하드코딩하지 않음 — 레지스트리가 진실).
- 순수: 렌더는 `renderModels(host, {state: "idle"|"loading"|"done"|"error", model, message})`.
- DOM 블록 3개: (1) 설계 목적 경로 카드(목적명 + 실행가능/검증됨 칩), (2) 목표별 평가자 상태(상태 칩 3색: 측정됨 okchip / 미검증 warnchip / 평가자 없음 chip), (3) 모델 카탈로그(모델명 + 엔드포인트 요약 + 포털 전용 칩).
- API: `requestModels()` → `callTool("pipeline.list_models", {})`, `out.error` → throw.

### B2. 로딩 정책

- 탭 **첫 진입 시 1회** 로드 후 캐시(모듈 상태). 재시도는 탭을 나갔다 들어오기(또는 실패 시 "다시 시도" 버튼). 레지스트리는 정적 데이터라 세대 가드 불필요 — 다만 로딩 중 재진입 시 중복 요청만 막는다(`loading` 상태 억제).
- 실패 → warn 노트 1줄 + "다시 시도" 버튼.

### B3. 배치

- `guided.js`에서 탭 진입(`showSideTab("models")`) 시 캐시 없으면 `requestModels` 발화. `guided.css`에 `.modelstab` 블록 간격 최소 규칙.

## C. 톨러런스 요약

| 상황 | 동작 |
|---|---|
| `list_models` 실패 | warn 노트 + 다시 시도 버튼 |
| 로딩 중 재진입 | 중복 요청 억제 |
| 알 수 없는 저장 탭 값 | `runs`로 정정 |
| 응답 필드 누락 | 순수 모델 함수가 기본값으로 흡수(빈 목록/빈 문자열) |

## D. 테스트

- 프런트 `frontend/tests/guided-models.test.js`: `modelsTabModels` 매핑(상태 3분류, 필드 누락 흡수), 렌더 상태별 출력, 소스 계약(sidetabs 앵커, sideRuns 래핑, showSideTab/localStorage, 탭 진입 발화).
- 회귀: guided 전체 패밀리 + 빌드. 백엔드 변경 없음.

## E. 범위 밖 (이후 단계)

- 연결 탭: 엔드포인트 레지스트리 + `check_liveness` 실측 프로브 (Ditto `source_status` 패턴)
- 스킬 탭: 협의회 헌장 YAML화 + 사용자 작성·버전·lint
- 프로젝트/템플릿/에이전트 탭
- 모델 탭에서 비용 추정 폼(n_designs/length_aa) — 계획 카드와 중복이라 제외
