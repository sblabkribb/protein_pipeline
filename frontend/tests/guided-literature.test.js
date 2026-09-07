import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.document ??= {
  createElement(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      className: "",
      textContent: "",
      href: "",
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  },
};

const { literatureRowModels, renderLiterature } = await import("../guided/literature.js");

const ITEMS = [
  { title: "Paper A", authors: "A, B", journal: "J", year: "2023",
    citations: 12, open_access: true, identifier: "10.1/a", url: "https://doi.org/10.1/a" },
  { title: "Paper B", citations: 0, open_access: false, url: "https://europepmc.org/article/MED/9" },
];

test("literatureRowModels maps rows and tolerates junk", () => {
  const models = literatureRowModels(ITEMS);
  assert.equal(models[0].citations, 12);
  assert.equal(models[0].openAccess, true);
  assert.ok(models[0].meta.includes("2023"));
  assert.equal(models[1].citations, 0);
  assert.equal(literatureRowModels([null, "x"]).length, 2);
  assert.equal(literatureRowModels()[0], undefined);
});

test("renderLiterature paints loading/empty/error/idle states", () => {
  const host = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = host(); renderLiterature(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /찾는 중/);
  const h1 = host(); renderLiterature(h1, { state: "empty" });
  assert.match(h1.children[0].textContent, /결과 없음/);
  const h2 = host(); renderLiterature(h2, { state: "error", message: "실패" });
  assert.match(h2.children[0].textContent, /실패/);
  const h3 = host(); renderLiterature(h3, { state: "idle" });
  assert.ok(h3.children[0].textContent.length > 0);
});

test("renderLiterature paints rows with chips and links", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderLiterature(host, { state: "done", items: ITEMS });
  const cards = host.children.filter((c) => c.className === "skill");
  assert.equal(cards.length, 2);
  const link = cards[0].children[0].children.find((c) => c.tagName === "A");
  assert.equal(link.href, "https://doi.org/10.1/a");
  assert.ok(cards[0].children[0].children.some((c) => c.className === "okchip"));
});

test("the literature box is a sibling of evidenceView and survives run switches", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  const panel = html.slice(html.indexOf('data-panelfor="evidence"'));
  assert.ok(panel.includes('id="evidenceView"'));
  assert.ok(panel.includes('id="literatureBox"'));
  assert.ok(panel.includes("이 검색은 실행과 무관합니다"));
  const evidence = readFileSync(new URL("../guided/evidence.js", import.meta.url), "utf8");
  assert.ok(!evidence.includes("literatureBox"), "evidence.js must not reset the literature box");
});

test("the facade wires the search form once", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes("function initLiteratureSearch"));
  assert.ok(src.includes("initLiteratureSearch();"));
  assert.ok(src.includes("literatureForm"));
  assert.ok(src.includes("literatureGen"), "re-search must discard stale results");
});
