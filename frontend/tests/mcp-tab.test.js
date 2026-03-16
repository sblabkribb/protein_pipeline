import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("index.html exposes an MCP tab and panel", () => {
  const source = readFileSync(resolve(process.cwd(), "index.html"), "utf-8");

  assert.equal(source.includes('id="tabBtnMcp"'), true);
  assert.equal(source.includes('data-tab="mcp"'), true);
  assert.equal(source.includes('id="tab-mcp"'), true);
  assert.equal(source.includes("https://pipeline.k-biofoundrycopilot.duckdns.org/mcp"), true);
  assert.equal(source.includes("mcp.json"), true);
});

test("app.js includes MCP tab i18n and tab normalization support", () => {
  const source = readFileSync(resolve(process.cwd(), "app.js"), "utf-8");

  assert.equal(source.includes('"tabs.mcp": "MCP"'), true);
  assert.equal(source.includes('const TAB_OPTIONS = ["setup", "studio", "monitor", "analyze", "mcp"]'), true);
});

test("guide content documents bearer auth and VS Code config", () => {
  const source = readFileSync(resolve(process.cwd(), "index.html"), "utf-8");

  assert.equal(source.includes("Authorization: Bearer"), true);
  assert.equal(source.includes("MCP: Open User Configuration"), true);
});
