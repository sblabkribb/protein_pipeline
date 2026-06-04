import test from "node:test";
import assert from "node:assert/strict";

test("pipeline MCP tab is Korean-first and includes VS Code plus Codex guidance", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    const html = mcpGuide.renderMcpGuideMarkup({
      lang: "ko",
      endpointUrl: "https://dev-pipeline.k-biofoundrycopilot.duckdns.org/mcp",
    });
    assert.equal(html.includes("https://dev-pipeline.k-biofoundrycopilot.duckdns.org/mcp"), true);
    assert.equal(html.includes("MCP: Open User Configuration"), true);
    assert.equal(html.includes("Codex"), true);
    assert.equal(html.includes("질문 예시"), true);
    assert.equal(html.includes('id="mcpTokenCopyBtn"'), true);
    assert.equal(html.includes('id="mcpSkillDownloadBtn"'), true);
    // Skill install guidance present (where to put the downloaded skill).
    assert.equal(html.includes("~/.claude/skills/"), true);
    // The placeholder token must be fully substituted, never shown raw.
    assert.equal(html.includes("__MCP_ENDPOINT__"), false);
  });
});

test("renderMcpGuideMarkup uses the given endpoint URL everywhere (no stale prod host)", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    const html = mcpGuide.renderMcpGuideMarkup({
      lang: "en",
      endpointUrl: "https://rapid-staging.kbiofoundry.kr/mcp",
    });
    assert.equal(html.includes("https://rapid-staging.kbiofoundry.kr/mcp"), true);
    // Must not leak the old hardcoded prod redirecting host when another env is given.
    assert.equal(html.includes("pipeline.k-biofoundrycopilot.duckdns.org/mcp"), false);
  });
});

test("resolveMcpEndpointUrl derives /mcp from origin and falls back when absent", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    assert.equal(
      mcpGuide.resolveMcpEndpointUrl({ origin: "https://dev-pipeline.k-biofoundrycopilot.duckdns.org" }),
      "https://dev-pipeline.k-biofoundrycopilot.duckdns.org/mcp"
    );
    // Trailing slash on origin is normalized.
    assert.equal(
      mcpGuide.resolveMcpEndpointUrl({ origin: "https://rapid.kbiofoundry.kr/" }),
      "https://rapid.kbiofoundry.kr/mcp"
    );
    // Empty/invalid origin falls back to the canonical prod endpoint.
    assert.equal(mcpGuide.resolveMcpEndpointUrl({ origin: "" }), "https://rapid.kbiofoundry.kr/mcp");
    assert.equal(mcpGuide.resolveMcpEndpointUrl({ origin: "null" }), "https://rapid.kbiofoundry.kr/mcp");
  });
});

test("buildMcpJsonSnippetWithToken injects the real token and endpoint", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    const snippet = mcpGuide.buildMcpJsonSnippetWithToken(
      "ABC.TOKEN.123",
      "https://dev-pipeline.k-biofoundrycopilot.duckdns.org/mcp"
    );
    assert.equal(snippet.includes("ABC.TOKEN.123"), true);
    assert.equal(snippet.includes("<KBF_SSO_ACCESS_TOKEN>"), false);
    assert.equal(snippet.includes("protein-pipeline"), true);
    assert.equal(snippet.includes("https://dev-pipeline.k-biofoundrycopilot.duckdns.org/mcp"), true);
  });
});
