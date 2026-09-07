import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { clampPanes, choosePaneDefault } = await import("../guided.js");

test("wide saved panes are clamped so the center stays visible", () => {
  const out = clampPanes({ left: 600, right: 600 }, 1200);
  assert.equal(out.left + out.right, 1200 - 12 - 360);
});

test("asymmetric saved panes shrink proportionally", () => {
  const out = clampPanes({ left: 1000, right: 400 }, 1200);
  assert.equal(out.left + out.right, 828);
  assert.ok(out.left > out.right, "bigger pane keeps a bigger share");
});

test("a pane floored at the minimum pushes the shrink to the other side", () => {
  const out = clampPanes({ left: 1400, right: 200 }, 1200);
  assert.equal(out.right, 200);
  assert.equal(out.left + out.right, 828);
});

test("panes within budget pass through untouched", () => {
  const out = clampPanes({ left: 264, right: 340 }, 1440);
  assert.deepEqual(out, { left: 264, right: 340 });
});

test("at or below 1100px the stacked mode takes over and clamping is a no-op", () => {
  assert.deepEqual(clampPanes({ left: 900, right: 900 }, 1100), { left: 900, right: 900 });
});

test("saved values win; the narrow default only applies between 1101 and 1280", () => {
  assert.deepEqual(choosePaneDefault(1150, null), { left: 232, right: 300 });
  assert.deepEqual(choosePaneDefault(1440, null), { left: 264, right: 340 });
  assert.deepEqual(choosePaneDefault(1150, { left: 500, right: 500 }), { left: 500, right: 500 });
  assert.deepEqual(choosePaneDefault(1000, null), { left: 264, right: 340 });
});

test("initSplitters clamps on restore and re-clamps on resize", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  const section = src.slice(src.indexOf("function initSplitters"));
  assert.ok(section.includes("clampPanes("), "restore must go through the clamp");
  assert.ok(section.includes('addEventListener("resize"'), "resize must re-clamp");
  assert.ok(section.includes("choosePaneDefault("));
});
