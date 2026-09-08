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
globalThis.localStorage ??= { getItem: () => null };
globalThis.window ??= { location: { origin: "http://localhost", pathname: "/" } };

const { SOURCE_LABEL, sourceRowModels, renderReference, requestReference } =
  await import("../guided/literature.js");

const ITEMS = [
  { title: "Hemoglobin", detail: "Homo sapiens · 142 aa", identifier: "P69905",
    url: "https://www.uniprot.org/uniprotkb/P69905", source: "curated" },
  { title: "PDB 4HHB", detail: "실험 구조 (PDB)", identifier: "4HHB",
    url: "https://www.rcsb.org/structure/4HHB", source: "structural" },
  { title: "UniRef100_P69905", detail: "51 members", identifier: "UniRef100_P69905",
    url: "https://www.uniprot.org/uniref/UniRef100_P69905", source: "clusters" },
  { title: "Paper A", authors: "A, B", journal: "J", year: "2023",
    citations: 12, open_access: true, identifier: "10.1/a",
    url: "https://doi.org/10.1/a", source: "published" },
];

test("SOURCE_LABEL maps provenance sources to Korean chips", () => {
  assert.equal(SOURCE_LABEL.structural, "구조");
  assert.equal(SOURCE_LABEL.curated, "주석");
  assert.equal(SOURCE_LABEL.clusters, "군집");
  assert.equal(SOURCE_LABEL.published, "문헌");
});

test("sourceRowModels maps uniform rows and tolerates junk", () => {
  const models = sourceRowModels(ITEMS);
  assert.equal(models[0].sourceLabel, "주석");
  assert.equal(models[0].meta, "Homo sapiens · 142 aa");
  assert.equal(models[1].sourceLabel, "구조");
  assert.equal(models[2].sourceLabel, "군집");
  assert.equal(models[3].sourceLabel, "문헌");
  assert.equal(models[3].citations, 12);
  assert.equal(models[3].openAccess, true);
  // legacy 문헌 행(detail 없음)은 authors/journal/year 로 meta 를 만든다.
  assert.ok(models[3].meta.includes("2023"));
  assert.equal(sourceRowModels([null, "x"]).length, 2);
  assert.equal(sourceRowModels()[0], undefined);
});

test("sourceRowModels falls back to 제목 없음 and no label for unknown source", () => {
  const [model] = sourceRowModels([{ title: "", source: "bogus" }]);
  assert.equal(model.title, "제목 없음");
  assert.equal(model.sourceLabel, "");
});

test("renderReference paints loading/empty/error/idle states", () => {
  const host = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = host(); renderReference(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /찾는 중/);
  const h1 = host(); renderReference(h1, { state: "empty" });
  assert.match(h1.children[0].textContent, /결과 없음/);
  const h2 = host(); renderReference(h2, { state: "error", message: "실패" });
  assert.match(h2.children[0].textContent, /실패/);
  const h3 = host(); renderReference(h3, { state: "idle" });
  assert.ok(h3.children[0].textContent.length > 0);
});

test("renderReference paints rows with the provenance chip and links", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderReference(host, { state: "done", items: ITEMS });
  const cards = host.children.filter((c) => c.className === "skill");
  assert.equal(cards.length, 4);
  const labels = cards.map((card) => {
    const chip = card.children[0].children.find((c) => c.className === "chip" && c.tagName === "SPAN");
    return chip && chip.textContent;
  });
  assert.deepEqual(labels, ["주석", "구조", "군집", "문헌"]);
  const link = cards[0].children[0].children.find((c) => c.tagName === "A");
  assert.equal(link.href, "https://www.uniprot.org/uniprotkb/P69905");
  assert.ok(cards[3].children[0].children.some((c) => c.className === "okchip"));
});

test("requestReference passes source and limit to pipeline.search_reference", async () => {
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, body: JSON.parse(opts.body) });
    return { ok: true, status: 200, json: async () => ({ ok: true, result: { items: [], query: "q" } }) };
  };
  const out = await requestReference("pdb", "hemoglobin");
  assert.deepEqual(out, { items: [], query: "q" });
  assert.equal(calls.length, 1);
  assert.ok(calls[0].url.endsWith("/tools/call"));
  assert.equal(calls[0].body.name, "pipeline.search_reference");
  assert.deepEqual(calls[0].body.arguments, { source: "pdb", query: "hemoglobin", limit: 8 });
});

test("requestReference throws on tool error contract", async () => {
  globalThis.fetch = async () => ({
    ok: true, status: 200,
    json: async () => ({ ok: true, result: { error: "unknown source" } }),
  });
  await assert.rejects(requestReference("bogus", "q"), /unknown source/);
});

test("the reference box is a sibling of evidenceView and survives run switches", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  const panel = html.slice(html.indexOf('data-panelfor="evidence"'));
  assert.ok(panel.includes('id="evidenceView"'));
  assert.ok(panel.includes('id="literatureBox"'));
  assert.ok(panel.includes("이 검색은 실행과 무관합니다"));
  assert.ok(panel.includes("참조 검색"), "section is renamed to 참조 검색");
  const evidence = readFileSync(new URL("../guided/evidence.js", import.meta.url), "utf8");
  assert.ok(!evidence.includes("literatureBox"), "evidence.js must not reset the literature box");
});

test("the form has a source select with five options before the input", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  const form = html.slice(html.indexOf('id="literatureForm"'));
  const select = form.slice(0, form.indexOf('id="literatureInput"'));
  assert.ok(select.includes('id="referenceSource"'), "select must come before the input");
  for (const value of ["literature", "pdb", "uniprot", "interpro", "uniref"]) {
    assert.ok(select.includes(`value="${value}"`), `option ${value} is present`);
  }
});

test("the facade wires the search form once with the source select", () => {
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes("function initReferenceSearch"));
  assert.ok(src.includes("initReferenceSearch();"));
  assert.ok(src.includes("literatureForm"));
  assert.ok(src.includes("referenceGen"), "re-search must discard stale results");
  assert.ok(src.includes('"referenceSource"'), "the search reads the source select");
  assert.ok(src.includes('requestReference(source, query)'), "the facade passes the source");
  assert.ok(src.includes('renderReference('), "the facade renders reference rows");
});
