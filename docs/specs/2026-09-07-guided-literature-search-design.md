# Guided Evidence 탭 문헌 검색 (Europe PMC) — 설계

- 날짜: 2026-09-07
- 상태: 승인됨 (사용자 선택: Evidence 탭 검색 UI — 계획 자동 첨부·협의회 인용·결정 근거 부착은 범위 밖)
- 참조: Ditto `src/ditto_cs/knowledge.py:122` (`literature`) 이식. RAPID 백엔드 HTTP 관례는 stdlib `urllib.request` + timeout.
- 범위: 백엔드 신규 도구 1개 + 프런트 Evidence 탭 문헌 섹션. `index.html`/`app.js`/`lib/` 무변경.

## 0. 배경

RAPID는 외부 문헌을 페치하지 않는다 — `objective_planner`의 literature 근거는 수동 큐레이션뿐이고 LLM에는 "PubMed ID/DOI 를 지어내지 마라"는 금지 규칙만 있다(`objective_planner.py:406`). Ditto는 Europe PMC 를 서버에서 직접 검색하며(API 키 불필요), 근거 평면에서 문헌을 `published`(측정보다 약한 출처)로 라벨링한다. 이 설계는 그 검색을 guided 콘솔 Evidence 탭에 노출한다.

## A. 백엔드 — `pipeline.search_literature`

### A1. 모듈 `pipeline_mcp/literature.py` (신규)

- `search_literature(query: str, limit: int = 8) -> dict` — Europe PMC REST:
  - URL: `https://www.ebi.ac.uk/europepmc/webservices/rest/search`
  - 파라미터: `query`, `format=json`, `pageSize=clamp(limit,1,25)`, `resultType=lite`, `sort=CITED desc`
  - HTTP: `urllib.request.urlopen(request, timeout=10)` (repo 관례, `# noqa: S310` 주석 포함)
  - 파싱: `resultList.result[]` → 행:
    ```
    { title, authors(80자 절단), journal, year, citations,
      open_access(bool, isOpenAccess=="Y"),
      identifier(doi 없으면 pmid 없으면 id),
      url(doi 있으면 https://doi.org/<doi>, 없으면 https://europepmc.org/article/<source>/<id>) }
    ```
- 오류 계약: 네트워크/파싱 실패 → `{"error": "…"}` (도구 관례와 동일, 예외를 밖으로 던지지 않음). 빈 query → `{"error": "query is required"}`.
- Korean docstring: 결과는 `published` 참조용이며 계획의 측정 근거와 같은 칸에 두지 않는다는 근거 철학 명시.

### A2. 도구 등록 (`tools.py`)

- 정의(`pipeline.discuss_plan` 인근): `pipeline.search_literature`, inputSchema `{query: string(필수), limit: integer(1..25, 기본 8)}`, description에 "read-only literature search; published sources are weaker than internal measurements; results are reference only" 명시.
- dispatch 분기: query 검증(str, strip, 비면 error) → `search_literature(query, limit)` 위임.

## B. 프런트 — Evidence 탭 문헌 섹션

### B1. 모듈 `frontend/guided/literature.js` (신규, council.js 패턴)

- 순수: `literatureRowModels(items)` — 서버 행을 표시 모델로 (문자열 강제, citations 포맷, OA 여부).
- 순수: 검색 상태 머신 대신 단순 — 렌더는 `renderLiterature(host, {state: "idle"|"loading"|"done"|"empty"|"error", items, message})`.
- DOM: 행 = 제목(외부 링크, `target="_blank" rel="noopener"`) + 메타(저자·저널·연도) + 인용수 칩 + OA 칩. 전부 `el()`/`textContent`, 링크 href는 identifier에서 조립된 URL만.
- API: `requestLiterature(query)` → `callTool("pipeline.search_literature", {query, limit: 8})`, `out.error` → throw.

### B2. 배치 (`guided.html` + `guided/evidence.js` + `guided.css`)

- Evidence 탭(evidenceView) 하단에 `<h3>문헌 검색</h3>` + 검색 폼(input + 버튼) + `<div id="literatureBox">`.
- **런과 무관**: 검색 결과는 런 전환에도 유지된다 — 섹션 상단에 note 1줄("이 검색은 실행과 무관합니다"). `refreshEvidence`는 이 섹션을 건드리지 않는다.
- 검색 흐름: 버튼 → loading 노트 → `requestLiterature` → done(목록)/empty("결과 없음")/error(warn 노트 1줄). 재검색은 덮어쓴다. 빈 쿼리는 요청하지 않고 note.
- `guided.css`: `.literaturebox` 행 간격 최소 규칙만, 기존 칩/노트 재사용.

## C. 톨러런스 요약

| 상황 | 동작 |
|---|---|
| 네트워크 실패/타임아웃(10s) | 도구가 `{error}` 반환 → 프런트 warn 노트 1줄 |
| 빈 결과 | "결과 없음" 노트 |
| 빈 쿼리 | 요청하지 않고 note 1줄 |
| limit 범위 밖 | 백엔드가 1..25로 클램프 |

## D. 테스트

- 백엔드 `pipeline-mcp/tests/test_literature.py`: 행 파싱(doi/pmid/id 우선순위, OA 플래그, authors 절단), limit 클램프, 빈 query 오류, 네트워크 실패 → `{error}` 계약 (urlopen monkeypatch), 도구 정의/등록.
- 프런트 `frontend/tests/guided-literature.test.js`: `literatureRowModels` 매핑, 렌더 상태별(loading/done/empty/error) 출력, 소스 계약(guided.html 앵커, 런-무관 안내 문구, evidence.js가 문헌 섹션을 리셋하지 않음).

## E. 범위 밖 (2차 후보)

- 계획 생성 시 목적 키워드 자동 검색·첨부
- 협의회 전문가의 문헌 인용 (LLM tool-loop)
- 찾은 논문을 결정 근거로 부착 (apply_edits 확장)
- Connections/사용자 스킬 시스템
