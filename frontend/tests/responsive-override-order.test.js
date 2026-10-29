import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

/** Byte ranges covered by an @media block, with its condition. */
function mediaRanges(source) {
  const ranges = [];
  const opener = /@media([^{]*)\{/g;
  let match;
  while ((match = opener.exec(source))) {
    let i = match.index + match[0].length;
    let depth = 1;
    while (i < source.length && depth > 0) {
      if (source[i] === "{") depth += 1;
      else if (source[i] === "}") depth -= 1;
      i += 1;
    }
    ranges.push({ start: match.index, end: i, condition: match[1].trim() });
  }
  return ranges;
}

function conditionFor(ranges, position) {
  for (const range of ranges) {
    if (position >= range.start && position < range.end) return range.condition;
  }
  return null;
}

test("a responsive grid override is not overridden by a later base rule", () => {
  // A media query adds no specificity, so a base rule declared further down the
  // file wins outright. That silently defeated the monitor and studio collapse
  // rules: on a 390px screen the monitor summary card rendered 54px wide and its
  // labels wrapped one character per line.
  const ranges = mediaRanges(css);
  const declarations = new Map();

  const rule = /([^{}]+)\{([^{}]*)\}/g;
  let match;
  while ((match = rule.exec(css))) {
    const body = match[2];
    if (!body.includes("grid-template-columns")) continue;
    const position = match.index + match[1].length;
    const condition = conditionFor(ranges, position);
    for (const raw of match[1].replace(/\n/g, " ").split(",")) {
      const selector = raw.trim();
      if (!selector || selector.startsWith("@")) continue;
      if (!declarations.has(selector)) declarations.set(selector, []);
      declarations.get(selector).push({ position, condition });
    }
  }

  // A scoped rule sitting before the last base rule is only a problem when
  // nothing after that base rule re-establishes it; an earlier duplicate is
  // merely redundant.
  const defeated = [];
  for (const [selector, entries] of declarations) {
    const base = entries.filter((entry) => !entry.condition);
    const scoped = entries.filter((entry) => entry.condition);
    if (!base.length || !scoped.length) continue;
    const lastBase = Math.max(...base.map((entry) => entry.position));
    const stillApplies = scoped.some((entry) => entry.position > lastBase);
    if (stillApplies) continue;
    for (const entry of scoped) {
      defeated.push(`${selector} @media ${entry.condition}`);
    }
  }

  assert.deepEqual(
    defeated,
    [],
    `these responsive overrides are defeated by a later base rule:\n  ${defeated.join(
      "\n  "
    )}`
  );
});

test("the monitor and studio grids collapse on narrow screens", () => {
  // The specific grids from the report, pinned so a future reshuffle is caught
  // even if the general ordering check is relaxed.
  for (const selector of [
    ".monitor-summary-top",
    ".monitor-summary-bottom",
    ".studio-grid",
  ]) {
    const escaped = selector.replace(".", "\\.");
    const pattern = new RegExp(
      `${escaped}[^{}]*\\{[^{}]*grid-template-columns:\\s*1fr`
    );
    assert.match(css, pattern, `${selector} should have a 1fr collapse rule`);
  }
});
