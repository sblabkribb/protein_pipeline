import test from "node:test";
import assert from "node:assert/strict";

import { unwrapToolResponse } from "../lib/tool-call.js";

// 서버는 도구 결과를 {"ok": true, "result": {...}} 로 감싸서 돌려준다.
// guided.js 는 그 봉투를 벗기지 않고 그대로 썼고, 그래서 out.purposes 와
// plan.decisions 가 전부 undefined 가 되었다. 200 응답에 오류도 없으므로
// 화면에는 "빈 드롭다운" 과 "빈 계획 검토" 만 남고 아무 메시지도 뜨지 않았다.

test("a successful envelope is unwrapped to the tool result", () => {
  const out = unwrapToolResponse({
    ok: true, status: 200, payload: { ok: true, result: { purposes: [1, 2] } },
  });
  assert.deepEqual(out, { purposes: [1, 2] });
});

test("the envelope itself is never returned to the caller", () => {
  const out = unwrapToolResponse({
    ok: true, status: 200, payload: { ok: true, result: { decisions: ["a"] } },
  });
  assert.equal(out.ok, undefined, "봉투가 새어나가면 호출자는 result 를 못 본다");
  assert.deepEqual(out.decisions, ["a"]);
});

test("an empty result is returned as an object rather than undefined", () => {
  assert.deepEqual(unwrapToolResponse({ ok: true, status: 200, payload: { ok: true } }), {});
});

test("a transport failure reports the server's message", () => {
  assert.throws(
    () => unwrapToolResponse({ ok: false, status: 401, payload: { ok: false, error: "unauthorized" } }),
    /unauthorized/,
  );
});

test("a transport failure without a message reports the status", () => {
  assert.throws(
    () => unwrapToolResponse({ ok: false, status: 502, payload: null }),
    /502/,
  );
});

test("ok:false with HTTP 200 is still a failure", () => {
  // 서버는 도구 오류를 200 + ok:false 로도 돌려준다. 성공으로 읽으면
  // 빈 화면이 되고 사용자는 이유를 알 수 없다.
  assert.throws(
    () => unwrapToolResponse({ ok: true, status: 200, payload: { ok: false, error: "boom" } }),
    /boom/,
  );
});

test("a non-object payload is a failure, not an empty result", () => {
  assert.throws(() => unwrapToolResponse({ ok: true, status: 200, payload: "nope" }));
  assert.throws(() => unwrapToolResponse({ ok: true, status: 200, payload: null }));
});

test("a tool-level error inside the result is left for the caller to see", () => {
  // pipeline.list_models 는 알 수 없는 purpose 에 {"error": ...} 를 돌려준다.
  // 그것은 전송 실패가 아니므로 여기서 던지지 않고 호출자가 판단한다.
  const out = unwrapToolResponse({
    ok: true, status: 200, payload: { ok: true, result: { error: "unknown purpose" } },
  });
  assert.equal(out.error, "unknown purpose");
});

test("an auth failure is identifiable by the caller", () => {
  try {
    unwrapToolResponse({ ok: false, status: 401, payload: { ok: false, error: "unauthorized" } });
    assert.fail("should have thrown");
  } catch (error) {
    assert.equal(error.status, 401, "401 을 구분할 수 있어야 로그인 안내를 띄운다");
  }
});
