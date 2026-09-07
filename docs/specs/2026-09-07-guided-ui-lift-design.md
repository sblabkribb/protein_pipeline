# Guided UI 리프트 (A안: Pretendard + JetBrains Mono) — 설계/계획

- 날짜: 2026-09-07
- 상태: 승인됨 (사용자 선택: A안 — Ditto 프리텐다드, 뉴트럴 크리스프)
- 범위: `frontend/guided.css` + 폰트 계약 테스트 1건. 백엔드/구 app 무변경.
- 불변: 근거 강도 색 체계(--measured/--assumed/--absent)와 oklch 토큰, 레이아웃 구조, 기능.

## 방향 (A안)

Ditto의 성숙한 타이포 체계를 guided에 이식한다:

1. **글시체**
   - 본문/UI: `Pretendard Variable`(jsdelivr CDN — Ditto와 동일 소스), fallback Pretendard → system-ui
   - 데이터/숫자/경로/코드: `JetBrains Mono` (기존 tabular-nums 규칙을 모노 스택으로 강화)
   - **Spectral 세리프 제목 폐지** — 모든 제목을 Pretendard 700, 자간 -0.01em
   - 본문 자간 -0.01em, 크기 13.5px/1.6
2. **간격/밀도**
   - 카드(.skill) 패딩 통일 9px 11px, 행 간격 8px
   - 칩: 10.5px, 패딩 2px 8px — 칩 폭주 억제
   - 사이드 패딩 20px 16px, 센터 20px 26px 64px (기존보다 살짝 타이트)
   - 섹션 h3 간격 규칙화 (margin 14px 0 6px)
3. **재질**
   - 보더 1px 유지, radius 8px 통일(칩 999px 제외)
   - 보더 색은 현행 --rule 유지(색 체계 불변)
4. **폰트 로딩**: `@import url("https://cdn.jsdelivr.net/gh/orionc/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css")` + Google Fonts JetBrains Mono (Ditto와 동일 CDN 방식)

## 테스트 변경

- `guided.test.js:205` — `"Instrument Sans"` 고정을 `"Pretendard"` 로 교체(주석 갱신: 승인된 A안 리프트).
- 신규 소스 계약: `guided.css`가 `JetBrains Mono` 사용, `Spectral` 부재.

## 완료 판정

- guided 패밀리 전부 통과, 빌드 통과, 브라우저에서 A안 목업과 일치하는 인상.
