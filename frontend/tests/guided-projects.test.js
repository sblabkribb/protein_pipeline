import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.document ??= {
  createElement(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      className: "",
      textContent: "",
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  },
};

const { projectCardModels, roundRowModels, renderProjectsTab } = await import("../guided/projects.js");

// 실제 레코드 모양(_save_project/_save_round, tools.py)에 맞춘 fixture 다.
// 보관 여부는 불리언이 아니라 status === "archived" 이고, 시각 필드는
// created_at (created_utc 아님), 라운드 실행은 linked_run_ids 배열이다.
const PROJECTS = [
  { project_id: "p1", name: "프로젝트 하나", owner_username: "kim", description: "설명", status: "active", created_at: "2026-09-01" },
  { project_id: "p2", name: "보관된 것", status: "archived" },
];
const ROUNDS = [
  { round_id: "r1", created_at: "2026-09-02", title: "1차", notes: "메모", linked_run_ids: ["run_x"] },
  { round_id: "r2" },
  { round_id: "r3", created_at: "2026-09-03", title: "보관 라운드", status: "archived" },
];

test("projectCardModels absorbs records", () => {
  const models = projectCardModels(PROJECTS);
  assert.equal(models[0].id, "p1");
  assert.equal(models[0].name, "프로젝트 하나");
  assert.equal(models[0].owner, "kim");
  assert.equal(models[0].createdUtc, "2026-09-01");
  assert.equal(models[0].archived, false);
  assert.equal(models[1].archived, true);
  assert.equal(projectCardModels(null).length, 0);
  assert.equal(projectCardModels([null])[0].name, "");
});

test("roundRowModels absorbs rounds", () => {
  const rows = roundRowModels(ROUNDS);
  assert.equal(rows[0].id, "r1");
  assert.equal(rows[0].createdUtc, "2026-09-02");
  assert.equal(rows[0].title, "1차");
  assert.deepEqual(rows[0].runIds, ["run_x"]);
  assert.deepEqual(rows[1].runIds, []);
  assert.equal(rows[2].status, "archived", "round status must be captured for the chip");
  assert.equal(roundRowModels(null).length, 0);
});

test("an archived round renders the 보관됨 chip, an active round does not", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  // 보관되지 않은 프로젝트만 쓴다 - 카드의 보관됨 칩과 라운드 칩을 구별하기 위해.
  const active = projectCardModels([PROJECTS[0]]);
  const host = make();
  renderProjectsTab(host, { state: "done", projects: active, expandedId: "p1",
                            rounds: roundRowModels([{ round_id: "r9", status: "archived" }]) });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("r9"), "the round row is rendered");
  assert.ok(html.includes("보관됨"), "archived round carries the 보관됨 chip");

  const plain = make();
  renderProjectsTab(plain, { state: "done", projects: active, expandedId: "p1",
                             rounds: roundRowModels([{ round_id: "r9" }]) });
  assert.ok(!JSON.stringify(plain.children).includes("보관됨"),
            "active rounds must not carry the chip");
});

test("renderProjectsTab paints projects and the expanded project's rounds", () => {
  const host = { children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } };
  renderProjectsTab(host, { state: "done", projects: projectCardModels(PROJECTS),
                            expandedId: "p1", rounds: roundRowModels(ROUNDS) });
  const html = JSON.stringify(host.children);
  assert.ok(html.includes("프로젝트 하나"));
  assert.ok(html.includes("보관된 것"));
  assert.ok(html.includes("r1"));
  assert.ok(html.includes("run_x"));
  assert.ok(html.includes("라운드 보기") || html.includes("접기"));
});

test("renderProjectsTab paints loading, error, empty states", () => {
  const make = () => ({ children: [], replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); } });
  const h0 = make(); renderProjectsTab(h0, { state: "loading" });
  assert.match(h0.children[0].textContent, /불러오는 중/);
  const h1 = make(); renderProjectsTab(h1, { state: "error", message: "실패" });
  assert.match(h1.children[0].textContent, /실패/);
  assert.ok(h1.children.some((c) => c.tagName === "BUTTON"));
  const h2 = make(); renderProjectsTab(h2, { state: "done", projects: [] });
  assert.match(h2.children[0].textContent, /프로젝트가 없/);
});

test("the shell hosts the projects tab with drill-down wiring", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  assert.ok(html.includes('data-sidetab="projects"'));
  assert.ok(html.includes('id="sideProjects"'));
  const src = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  assert.ok(src.includes('"projects"'));
  assert.ok(src.includes("__projectsTabLoad"));
  assert.ok(src.includes("__projectsExpand"), "cards must trigger the facade expand action");
  assert.ok(src.indexOf("__projectsTabLoad = ") < src.indexOf("initSideTabs();"));
  const mod = readFileSync(new URL("../guided/projects.js", import.meta.url), "utf8");
  assert.ok(mod.includes("pipeline.list_projects"));
  assert.ok(mod.includes("pipeline.list_rounds"));
});
