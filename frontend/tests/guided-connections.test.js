import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.document ??= {
  createElement(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      className: "",
      textContent: "",
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  },
};

const { connectionRowModels, renderConnectionsTab } = await import("../guided/connections.js");

const LIVENESS = {
  thermomp_ddg: { endpoint: "bop:18114", declared_availability: "always_on",
                  reachable: true, ready: true, model_mismatch: false },
  af3: { endpoint: "bop:18115", declared_availability: "always_on",
         reachable: false, error: "timeout" },
  mpnn: { endpoint: "bop:18112", declared_availability: "always_on",
          reachable: true, ready: false, model_mismatch: true },
};

test("connectionRowModels sorts by id and absorbs fields", () => {
  const rows = connectionRowModels(LIVENESS);
  assert.deepEqual(rows.map((r) => r.id), ["af3", "mpnn", "thermomp_ddg"]);
  assert.equal(rows[2].reachable, true);
  assert.equal(rows[1].mismatch, true);
  assert.equal(rows[0].error, "timeout");
  assert.equal(connectionRowModels(null).length, 0);
});

test("renderConnectionsTab paints rows with state chips and sections", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderConnectionsTab(host, { state: "done", data: {
    liveness: LIVENESS,
    connections: { bop_workers: { declared: 3, reachable: 2 },
                   portal_mcp: { configured: true, integration: "wired",
                                 would_unlock: ["alphafold3"], still_blocked_note: "노트" } },
  } });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("엔드포인트 실측"));
  assert.ok(html.includes("BOP 워커 요약"));
  assert.ok(html.includes("포털 연결"));
  assert.ok(html.includes("okchip") && html.includes("badchip") && html.includes("warnchip"));
  assert.ok(html.includes("모델 불일치"));
  assert.ok(html.includes("alphafold3"));
});

test("renderConnectionsTab paints loading, error-with-retry and empty states", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderConnectionsTab(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /확인하는 중/);
  const h1 = make(); renderConnectionsTab(h1, { state: "error", message: "실패" });
  assert.match(h1.children[0].textContent, /실패/);
  assert.ok(h1.children.some((c) => c.tagName === "BUTTON"));
  const h2 = make(); renderConnectionsTab(h2, { state: "done", data: {} });
  assert.match(h2.children[0].textContent, /없습니다/);
});

test("the shell hosts the connections tab", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('data-sidetab="connections"'));
  assert.ok(html.includes('id="sideConnections"'));
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"connections"'), "SIDE_TAB_NAMES must include connections");
  assert.ok(src.includes("__connectionsTabLoad"));
  assert.ok(src.indexOf("__connectionsTabLoad = ") < src.indexOf("initSideTabs();"),
            "hook must be defined before tab restore");
});
