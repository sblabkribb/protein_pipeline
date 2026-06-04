import test from "node:test";
import assert from "node:assert/strict";

test("pipeline MCP tab is Korean-first and includes VS Code plus Codex guidance", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    const html = mcpGuide.renderMcpGuideMarkup({ lang: "ko" });
    assert.equal(html.includes("https://pipeline.k-biofoundrycopilot.duckdns.org/mcp"), true);
    assert.equal(html.includes("MCP: Open User Configuration"), true);
    assert.equal(html.includes("Codex"), true);
    assert.equal(html.includes("질문 예시"), true);
    assert.equal(html.includes('id="mcpTokenCopyBtn"'), true);
    assert.equal(html.includes('id="mcpSkillDownloadBtn"'), true);
  });
});

test("buildMcpJsonSnippetWithToken injects the real token", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    const snippet = mcpGuide.buildMcpJsonSnippetWithToken("ABC.TOKEN.123");
    assert.equal(snippet.includes("ABC.TOKEN.123"), true);
    assert.equal(snippet.includes("<KBF_SSO_ACCESS_TOKEN>"), false);
    assert.equal(snippet.includes("protein-pipeline"), true);
  });
});
