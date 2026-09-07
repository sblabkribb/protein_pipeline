# Guided 콘솔 반응형 수정 + 계획 전문가 협의회 — 설계

- 날짜: 2026-09-07
- 상태: 승인됨 (사용자 확인: 반응형 증상 = "절반 또는 작은 창에서 가운데가 안 보임", 협의회 = LLM 전문가 5인, 계획 생성 시 자동, 표시 + 승인형 제안)
- 범위: 프런트 `frontend/guided*` + 백엔드 신규 도구 1개. `index.html`/`app.js`/`lib/` 무변경 원칙 유지.

## 0. 배경

1. **반응형**: 3페인 그리드(`264px 6px minmax(0,1fr) 6px 340px`)의 스플리터 폭이 localStorage에 px로 저장되고 `initSplitters()`가 창 크기와 무관하게 복원한다. 넓은 모니터에서 넓힌 폭이 절반/작은 창에서 그대로 적용되면 중앙 패널이 거의 0이 된다. `window.resize` 재클램프도 없고, 1101~1280px 구간은 좌 264 + 우 340 고정이라 중앙이 눌린다. ≤1100px 세로 스택 모드는 정상 동작하므로 유지한다.
2. **계획 전문가 협의회**: 현재 계획 생성(`pipeline.plan_from_objective`, 결정론) 후 대화 수정(`pipeline.discuss_plan`, 단일 LLM)만 있다. 계획 생성 시점에 도메인 전문가 5인이 병렬로 계획을 검토하고 판정+수정 제안을 내는 "협의회"를 추가한다. 기존 구현 재사용: `chat_agent.py`(LLM 엔진), `objective_planner.py`(근거 강제 규칙), `agent_panel.py`(판정 스키마 관례), `discuss_plan`(제안 파싱·적용 계약).

## A. 반응형 레이아웃 수정 (프런트만)

### A1. 순수 클램프 함수 — `clampPanes(panes, layoutWidth)`

`frontend/guided.js`에 순수 함수로 추출(테스트 대상):

- 가용 폭 `available = layoutWidth - 12` (스플리터 2개 × 6px)
- 중앙 최소 보장 `CENTER_MIN = 360`
- 규칙: `left + right ≤ available - CENTER_MIN`. 초과하면 두 패인의 현재 폭 비율에 비례해 초과분을 배분해 축소한다(좌 60%·우 40%이면 초과분도 6:4로 차감).
- 각 패인 하한 `PANE_MIN = 200` 유지. 비례 축소 결과가 하한 아래로 내려가면 하한으로 고정하고 나머지 한쪽에서 추가 차감(양쪽 다 하한이면 그 상태 수용 — 창이 너무 좁으면 ≤1100px 스택 모드가 이미 대신함).
- `layoutWidth ≤ 1100` 이면 원 입력을 그대로 반환(스택 모드가 CSS `!important`로 덮으므로 클램프 무의미).

### A2. 적용 지점 3곳

1. **복원 시**: `initSplitters()`에서 `readPanes()` 결과를 `applyPanes(clampPanes(saved, layout.clientWidth))`로 적용. 저장된 넓은 폭이 좁은 창에서 그대로 살아있는 버그 제거.
2. **resize**: `window.addEventListener("resize", …)` — 100ms 디바운스 후 현재 panes를 재클램프·재적용. 절반 창 전환 즉시 중앙 보장.
3. **좁은 창 기본값**: 저장값이 없고 `1101 ≤ width ≤ 1280`이면 `PANE_DEFAULT_NARROW = { left: 232, right: 300 }` 사용. 저장값이 있으면(클램프 후) 그대로 존중.

### A3. CSS 변경 없음

미디어 쿼리(1100px 스택)와 스플리터 스타일은 현행 유지. 로직만 고친다.

## B. 전문가 협의회 백엔드

### B1. 모듈 — `pipeline_mcp/plan_council.py` (신규) + 도구 `pipeline.plan_council`

`tools.py`에 등록. 입력:

```
{ plan: object,            # plan_from_objective 출력 그대로
  provider?: str, model?: str, api_key?: str,   # discuss_plan과 동일한 선택적 LLM 지정
  lang?: "ko"|"en" }
```

LLM 호출 경로는 `discuss_plan`이 쓰는 것과 동일한 `chat_agent` 완료 함수를 재사용(도구 루프 불필요, 단발 완료 + JSON 파싱). provider 미지정이면 서버 기본 연결을 쓰고, 그것도 없으면 B5의 생략 응답.

### B2. 전문가 5인 — 정의와 소유 필드

| id | 이름 | 소유 필드(제안 권한) |
|---|---|---|
| `solubility` | 용해도·응집 전문가 | weights.{solubility, aggregation, developability}, soluprot 관련 constraints |
| `stability` | 안정성 전문가 | weights.stability, WT 비교 관련 설정 |
| `structure` | 구조 보존·결합 전문가 | weights.{structural_preservation, binding}, RMSD/fixed-position 관련 constraints |
| `design_space` | 설계 공간·예산 전문가 | weights.diversity, budget(설계 수·티어·비용), sampling_temp |
| `experiment` | 실험 실현성 전문가 | 모티프·리아빌리티 관련 constraints, developability |

- 각 전문가의 시스템 프롬프트(헌장)는 자기 역할·검토 관점·출력 JSON 계약을 명시. 모든 전문가에게 동일한 사용자 메시지(계획 JSON + 자기 소유 필드 목록)를 보낸다.
- 5개 호출 **병렬** 실행. 개별 타임아웃 30초.

### B3. 전문가 출력 계약 (엄격 JSON)

```
{ "verdict": "ok" | "warn" | "block",
  "reasons": ["…"],
  "suggestions": [ { "field": "<plan 필드명>", "value": …,
                     "rationale": "…",
                     "evidence": [ { "kind": "internal_measurement"|"literature"|"assumption",
                                     "statement": "…", "source": "…", "value": "…" } ] } ] }
```

### B4. 검증·병합 (`objective_planner` 규칙 재사용)

- JSON 파싱: 코드펜스 제거 등 `discuss_plan`의 기존 파싱 보조 재사용. 실패 시 그 전문가 `unavailable` + 원문 일부(접이식, 프런트에서 처리할 수 있게 `raw_excerpt` 포함).
- Evidence 검증: `Evidence` 규칙 그대로 — kind 허용값, 측정/문헌 근거에 source 필수. 위반 suggestion은 `rejected_edits`로.
- **소유권 강제**: suggestion.field가 그 전문가의 소유 필드가 아니면 `rejected_edits`에 "소유권 위반" 사유로 분류.
- 값 검증: weights는 0..1, 알 수 없는 objective → 거부. 나머지는 plan 필드별 기존 검증(`plan_from_objective`가 최종적으로 다시 검증하므로 이중 방어).
- 통과한 suggestion만 `applicable_edits`(기존 discuss_plan 계약과 동일한 형태)로 반환.

### B5. 출력 계약

```
{ council: [ { expert_id, name, verdict, reasons: [], suggestions_count: int,
               status: "ok"|"unavailable"|"error", raw_excerpt? } ],
  applicable_edits: [...], rejected_edits: [...],
  notes: ["…"] }
```

- **LLM 없음**: `{ council: [], applicable_edits: [], rejected_edits: [], notes: ["LLM 연결 없음 — 전문가 검토를 생략합니다"] }`
- 부분 실패: 실패한 전문가만 `unavailable`/`error`, 나머지는 정상 반영. 전체 실패도 예외로 계획을 막지 않는다(도구 자체는 항상 200 계약 응답).

## C. 프런트 (guided)

### C1. 트리거 — `generatePlan()` 성공 후 자동

- 계획 렌더는 즉시(현행 유지). 협의회는 별도 비동기로 발화: 판정 섹션에 "전문가 검토 중…" 표시 → 완료 시 카드 채움.
- **세대 가드**: `state.councilGen` — `generatePlan()` 시작 시 1 증가, 협의회 응답 도착 시 세대가 다르면 폐기(기존 staleness 패턴과 동일).

### C2. 판정 섹션 렌더 (plan.js + guided.html)

- `guided.html` 계획 섹션(decisions 아래)에 `<div id="councilBox">` 추가.
- 전문가 카드: 이름 + 판정 칩(적합=okchip / 경고=warnchip / 차단=badchip / 검토 불가=note) + reasons 목록. 순수 렌더 함수(`buildCouncilCards(council)`)로 분리해 노드 테스트.
- `raw_excerpt`가 있으면 접이식(`<details>`)으로 원문 표시.
- LLM 없음 note 1줄.

### C3. 제안 연동 — 기존 `renderProposals` 흐름

- `applicable_edits`를 기존 제안 목록에 합쳐 렌더(사용자가 적용/거부 — 최종 승인은 사람, 철학 유지).
- `rejected_edits`는 기존 거부 사유 표기 방식 재사용.
- 중복 필드 제안이 생기면(대화 제안 + 협의회 제안) 목록에 둘 다 표시하되 동일 필드임을 칩으로 표기.

### C4. 오류 표시

- 협의회 전체 실패/타임아웃: 판정 섹션에 warn 1줄("전문가 검토에 실패했습니다: …"), 계획은 정상.
- 판정 섹션은 절대 계획 생성 성공을 막지 않는다.

## D. 오류/톨러런스 요약

| 상황 | 동작 |
|---|---|
| LLM 미연결 | 생략 노트 1줄, 계획 정상 |
| 개별 전문가 타임아웃(30s) | 그 전문가 `unavailable`, 나머지 반영 |
| 전문가 JSON 파싱 실패 | `unavailable` + 원문 접이식 |
| 소유권/근거/값 위반 제안 | `rejected_edits`로 사유 표시 |
| 협의회 응답이 늦게 도착(재생성됨) | 세대 가드로 폐기 |
| 창 폭 변화 | resize 재클램프로 중앙 최소 360px 보장 |

## E. 테스트

- **백엔드** `pipeline-mcp/tests/test_plan_council.py`: 헌장/소유권 맵 구성, JSON 펜스 제거·파싱, Evidence 검증, 소유권 위반 분류, 값 검증(0..1, 미지 objective), 부분 실패 톨러런스, LLM 없음 생략, 도구 등록. LLM 완료 함수는 monkeypatch.
- **프런트** `frontend/tests/guided-council.test.js`: `buildCouncilCards` 순수 렌더(칩 클래스, reasons, raw_excerpt 접이식), proposal 병합, 세대 가드 소스 계약, LLM-없음 노트.
- **반응형** `frontend/tests/guided-layout.test.js`: `clampPanes` 표 형태 케이스(넓은 저장값 × 좁은 창, 하한 충돌, 1100 이하 무시), narrow 기본값 선택, resize 리스너 소스 계약.

## F. 범위 밖

- 비용 칩/예산 바 UI 변경 없음 (provenance 규칙 유지)
- `discuss_plan` 자체 변경 없음 (협의회는 별도 도구)
- Compare Studio 전체, 실행 완료 시 타 자동 갱신, CI 테스트 목록 확장 — 별도 과제로 유지 (최종 리뷰 non-blocking 목록)
