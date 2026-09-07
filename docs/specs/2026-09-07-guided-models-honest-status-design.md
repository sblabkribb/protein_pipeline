# 모델 탭 상태 해명 + 좌측 탭 Ditto식 재질 — 설계

- 날짜: 2026-09-07
- 상태: 진행 (사용자: "실행가능미검증/평가자있으나미검증 표시가 애매하다 — Ditto처럼 멋있게, 연결·스킬·에이전트도 마찬가지")
- 불변: 근거 강도 색 체계, 레이아웃, 다른 탭의 데이터 계약.

## 1. 백엔드 — `pipeline.list_models`에 `objective_status` 노출 (소규모, 추가)

- 출력에 `"objective_status": {name: entry}` 추가(레지스트리 `registry.objective_status` 그대로). entry: `{status, evaluators, detail, to_enable?}`.
- 목적: 프런트가 3분류 추측 대신 레지스트리의 정직한 상태 텍스트를 보여주게 한다. 문서화된 후속 과제(모델 탭 목표 어휘 페이로드 기반 전환)도 이것으로 해소 — 8키 미러 제거.
- 테스트: 도구 응답에 objective_status 존재 + 레지스트리와 동기.

## 2. 모델 탭 재건 (Ditto식 상태 표시)

### 목표별 평가자 상태 — 5단계 정직 라벨
`objective_status`가 있으면 그것으로 렌더(페이로드 기반, 미러 제거):

| 레지스트리 status | 표시 | 칩 |
|---|---|---|
| measured | 측정됨 | okchip |
| evaluator_unvalidated | 평가자 있음 · 미검증 | warnchip |
| evaluator_not_wired | 구현 있음 · 미배선 | warnchip |
| needs_experimental_labels | 실험 라벨 필요 | chip |
| no_evaluator_available | 평가자 없음 | chip |

- 각 목표 카드: 이름 + 상태 칩 + evaluators 칩들 + `detail` 1줄 + `to_enable` 있으면 "활성화하려면: …" note.
- 페이로드에 objective_status가 없으면(구 버전) 기존 3분류로 폴백.

### 목적 경로 — 왜 미검증인지 보여주기
- 목적 카드에 스테이지 행 추가: 각 스테이지 `stage 명 + 모델` 칩, 미검증 스테이지는 warn 점. (route dict의 `stages[].validated` 사용 — 이미 list_models purposes에 포함돼 옴.)

## 3. 좌측 탭 공통 재질 (연결·스킬·에이전트·모델)

Ditto `.kv` 패턴 이식:
```css
.kv { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: 11.5px; }
.kv dt { color: var(--quiet); }
.kv dd { margin: 0; font-family: var(--mono); font-size: 11px; word-break: break-all; }
```
- **연결**: 카드 안 상세를 kv로(엔드포인트·선언·오류 — 값은 mono), 도달 점(dot) 헤드에.
- **스킬**: updated_utc를 kv로, 출처 칩 유지.
- **에이전트**: 상태 헤더 유지, 이벤트 카드의 detail/actions를 kv로(라벨+mono 값).
- 카드 헤드에 상태 dot(초록/회색/빨강) 통일 — `dot()` 유틸이 plan.js에 있으나 모듈 간 재사용 대신 각 모듈이 `el("span", "dot")`+CSS로 통일.

## 4. 테스트

- 백엔드: test_plan_council.py 또는 신규 — list_models 응답의 objective_status 동기화 테스트 1건.
- 프런트: guided-models.test.js 재건(5상태 매핑, detail/to_enable 표시, 폴백), connections/skills/agents에 kv 렌더 케이스 추가. 기존 186 전부 유지(일부 assertion 갱신).
