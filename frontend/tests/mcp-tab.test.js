import test from "node:test";
import assert from "node:assert/strict";

test("pipeline MCP tab is Korean-first and includes VS Code plus Codex guidance", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    assert.ok(mcpGuide && typeof mcpGuide.renderMcpGuideMarkup === "function");

    const html = mcpGuide.renderMcpGuideMarkup({ lang: "ko" });

    assert.equal(html.includes("https://pipeline.k-biofoundrycopilot.duckdns.org/mcp"), true);
    assert.equal(html.includes("MCP: Open User Configuration"), true);
    assert.equal(html.includes("Codex"), true);
    assert.equal(html.includes("토큰"), true);
    assert.equal(html.includes("질문 예시"), true);
    assert.equal(html.includes("원격 MCP 엔드포인트"), true);
  });
});
