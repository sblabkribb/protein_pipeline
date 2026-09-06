// /tools/call 응답 봉투를 벗긴다.
//
// 서버는 도구 결과를 `{"ok": true, "result": {...}}` 로 감싸서 돌려준다.
// guided.js 는 그 봉투를 그대로 호출자에게 넘겼고, 그래서 `out.purposes` 와
// `plan.decisions` 가 전부 undefined 가 되었다. HTTP 는 200 이고 payload 에
// 오류도 없으므로 화면에는 빈 드롭다운과 빈 계획 검토만 남고 아무 메시지도
// 뜨지 않았다 - 실패가 아니라 성공처럼 보이는 실패였다.
//
// DOM 이 필요 없는 순수 함수로 떼어낸 이유가 그것이다. 원래 guided.js 의
// 테스트는 소스 문자열만 검사해서 이 경로를 한 번도 실행해보지 않았다.

export function unwrapToolResponse({ ok, status, payload }) {
  if (!ok) {
    const message =
      payload && typeof payload.error === "string" ? payload.error : `HTTP ${status}`;
    throw Object.assign(new Error(message), { status });
  }
  if (!payload || typeof payload !== "object") {
    throw Object.assign(new Error(`서버가 객체가 아닌 응답을 보냈습니다 (HTTP ${status})`), {
      status,
    });
  }
  // 서버는 도구 오류를 200 + ok:false 로도 돌려준다. 성공으로 읽으면 빈 화면이
  // 되고 사용자는 이유를 알 수 없다.
  if (payload.ok === false) {
    throw Object.assign(new Error(payload.error || `HTTP ${status}`), { status });
  }
  // 결과 안의 `error` 는 전송 실패가 아니라 도구가 돌려준 메시지다(예: 알 수 없는
  // 설계 목적). 여기서 던지지 않고 호출자가 판단하게 둔다.
  return payload.result === undefined ? {} : payload.result;
}
