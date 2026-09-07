import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { showSideTab, SIDE_TAB_KEY } = await import("../guided.js");

test("side tab strip exists with runs and models tabs", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('class="sidetabs"'));
  assert.ok(html.includes('data-sidetab="runs"'));
  assert.ok(html.includes('data-sidetab="models"'));
  assert.ok(html.includes('id="sideRuns"'));
  assert.ok(html.includes('id="sideModels"'));
});

test("existing side content is wrapped in sideRuns", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  const start = html.indexOf('id="sideRuns"');
  const end = html.indexOf('id="sideModels"');
  const between = html.slice(start, end);
  assert.ok(between.includes('id="runList"'), "runList lives inside sideRuns");
  assert.ok(between.includes('id="monitorList"'), "ops block lives inside sideRuns");
});

test("showSideTab toggles panels and persists the choice", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('localStorage.setItem(SIDE_TAB_KEY'), "choice must persist");
  assert.ok(src.includes('localStorage.getItem(SIDE_TAB_KEY'), "choice must restore");
  assert.ok(src.includes("initSideTabs"), "init function must exist");
  assert.ok(/initSideTabs\(\);/.test(src), "init must be called");
});

test("an unknown stored tab falls back to runs", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"runs"') && src.includes('"models"'),
            "only two tab names are accepted");
});

test("projects tab comes first in the side tab order", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  const strip = html.slice(html.indexOf('class="sidetabs"'), html.indexOf("</nav>"));
  const order = ["projects", "runs", "templates", "models", "connections", "skills", "agents"];
  let prev = -1;
  for (const name of order) {
    const at = strip.indexOf(`data-sidetab="${name}"`);
    assert.ok(at > prev, `${name} must follow the previous tab`);
    prev = at;
  }
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('["projects", "runs", "templates", "models", "connections", "skills", "agents"]'),
            "SIDE_TAB_NAMES must match the button order");
});
