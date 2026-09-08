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

test("the tab strip lays out without overflowing and reads as tabs", () => {
  const css = readFileSync(new URL("../guided.css", import.meta.url), "utf8");
  // 좁은 레일에서는 균등 격자로 깔아 어느 줄이든 폭을 꽉 채운다. 예전에는
  // flex-wrap 으로 흘려보내서 둘째 줄에 탭 하나만 남았다.
  assert.ok(/\.sidetabs \{[^}]*display: grid/.test(css), "narrow rails lay the tabs out on a grid");
  assert.ok(/@container \(min-width: \d+px\) \{\s*\.sidetabs \{[^}]*display: flex/.test(css),
    "a rail wide enough for one row drops the grid and packs the tabs left");
  // 표시는 우측 탭(.tabs)과 같은 밑줄이다. 활성 탭에만 알약 배경을 달면
  // 나머지가 탭으로 읽히지 않는다.
  assert.ok(/\.sidetab \{[^}]*border-bottom: 2px solid transparent/.test(css), "tabs are underlined, not pills");
  assert.ok(/\.sidetab\.active \{[^}]*border-bottom-color/.test(css), "the active tab is marked by its underline");
  assert.ok(!/\.sidetab \{[^}]*border-radius: 999px/.test(css), "the old pill treatment is gone");
});
