# Artifact Download And Source Summary Design

**Goal**

Monitor/Analyze 탭에서 각 아티팩트 파일을 직접 다운로드할 수 있게 하고, Analyze 비교 영역의 RFD3/BioEmu 백본 생성/사용 요약이 대표 backbone id까지 화면에 일관되게 드러나도록 정리한다.

**Context**

- 현재 아티팩트 목록은 미리보기만 지원하고 개별 파일 다운로드 액션은 없다.
- Compare manifest strip은 `selected_backbone_id`를 툴팁에는 포함하지만, 칩 본문에는 노출하지 않는다.
- 백엔드 집계 값은 이미 `requested_count`, `observed_count`, `materialized_count`, `propagated_count`, `propagation_mode`, `selected_backbone_id`를 제공한다.

**Scope**

- `Monitor`/`Analyze` 아티팩트 목록의 각 파일 행에 `다운로드` 버튼 추가
- Analyze 비교 manifest 요약 칩에 대표 backbone id 노출
- 필요한 i18n 문자열과 스타일 보강
- 기존 미리보기/비교/필터 동작 유지

**Non-Goals**

- 새 백엔드 다운로드 endpoint 추가
- 전체 run zip export 흐름 변경
- backend source summary 집계 규칙 변경

## Approach

### 1. Source Summary Display

- 백엔드 집계는 그대로 사용한다.
- 프런트의 `formatBackboneUsageSummary()` 호출부에서 compare manifest chip 본문도 `includeSelected: true`로 렌더링한다.
- 결과적으로 실제 run 데이터가
  - `RFD3 requested 10 / observed 10 / saved 10 / used 10`
  - `BioEmu requested 10 / observed 10 / saved 10 / used 10`
  인 경우, 화면도 그대로 반영한다.
- 반대로 이전처럼 1개만 materialize된 run은 여전히 1개로 표시된다. 표기만 바꾸고 숫자를 추측하지 않는다.

### 2. Per-Artifact Download

- 프런트에서 기존 `pipeline.read_artifact` tool call을 재사용한다.
- 다운로드 버튼 클릭 시:
  - `run_id`, `path`, `max_bytes=size+slack`, `base64=true`로 호출
  - 반환된 base64를 Blob으로 바꿔 브라우저 다운로드 수행
- 행 본문 클릭은 기존대로 preview를 열고, 버튼 클릭은 `stopPropagation()`으로 preview와 분리한다.
- 적용 대상은 `Monitor`와 `Analyze`의 공통 `renderArtifacts()` 렌더링 경로다.

### 3. UI Details

- 아티팩트 행은 좌측에 파일 경로/태그, 우측에 `다운로드` ghost button 구조로 바꾼다.
- 버튼 텍스트는 한국어/영어 i18n 사용.
- 다운로드 진행 중에는 버튼 비활성화 또는 짧은 상태 텍스트를 사용해 중복 클릭을 막는다.
- 다운로드 실패 시 기존 메시지 채널에 오류를 표시한다.

## Data Flow

1. `pipeline.list_artifacts`로 받은 `state.artifacts`를 `renderArtifacts()`가 렌더링
2. 행별 `다운로드` 버튼 클릭
3. 프런트가 `pipeline.read_artifact(base64=true)` 호출
4. base64 → Blob 변환 후 `download` 속성으로 저장

## Risks And Mitigations

- 큰 파일 다운로드 시 JSON base64 오버헤드가 있다.
  - 현재 범위에서는 endpoint 추가 없이 구현 우선
  - 필요하면 후속으로 streaming endpoint 검토
- 클릭 이벤트 충돌 가능성
  - 버튼에서 `stopPropagation()` 처리
- 대표 id가 긴 경우 칩 가독성 저하 가능성
  - 기존 한 줄 summary 유지, full text는 title tooltip로 보강

## Testing

- 프런트 테스트:
  - compare manifest summary가 대표 backbone id를 포함하는지
  - 아티팩트 목록 렌더링에 다운로드 버튼이 생기는지
  - 다운로드 버튼 클릭이 `pipeline.read_artifact(base64=true)`를 호출하는지
  - 버튼 클릭이 preview 클릭과 분리되는지
- 수동 확인:
  - Monitor/Analyze에서 `.json`, `.pdb`, `.fasta` 하나씩 다운로드
  - Compare manifest strip에서 대표 id 표시 확인

## Rollout

- 이번 변경은 프런트 중심이다.
- 정적 자산이 서비스 중이면 브라우저 새로고침으로 반영 가능하다.
- 서비스가 번들 캐시를 강하게 쓰면 프런트 재배포 또는 서비스 재시작이 필요할 수 있다.
