// frontend/guided/projects.js — 프로젝트 탭. 프로젝트와 그 라운드를 읽어서 탐색한다.
// 읽기 전용 — 만들고 고치는 일은 구 app 의 몫이다. 레코드 모양은 tools.py 의
// _save_project/_save_round 를 따른다: 보관 여부는 status === "archived" 이고,
// 시각은 created_at, 라운드 실행은 linked_run_ids 배열이다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function projectCardModels(projects) {
  const rows = Array.isArray(projects) ? projects : [];
  return rows.map((item) => {
    const row = item && typeof item === "object" ? item : {};
    return {
      id: String(row.project_id || ""),
      name: String(row.name || row.project_id || ""),
      owner: String(row.owner_username || row.created_by || ""),
      description: String(row.description || ""),
      createdUtc: String(row.created_at || ""),
      archived: String(row.status || "").trim().toLowerCase() === "archived",
    };
  });
}

export function roundRowModels(rounds) {
  const rows = Array.isArray(rounds) ? rounds : [];
  return rows.map((item) => {
    const row = item && typeof item === "object" ? item : {};
    return {
      id: String(row.round_id || ""),
      createdUtc: String(row.created_at || ""),
      title: String(row.title || ""),
      note: String(row.notes || ""),
      status: String(row.status || ""),
      runIds: (Array.isArray(row.linked_run_ids) ? row.linked_run_ids : [])
        .map((runId) => String(runId || "")).filter(Boolean),
    };
  });
}

// 탭 상태는 이 모듈이 갖는다 (skills.js 의 편집 상태와 같은 취향이다). 파사드는
// 읽어 와 저장하고 다시 그릴 뿐이다. 렌더는 인자가 null 일 때 이 상태를 읽는다.
let projectsCache = [];
let expandedId = "";
let roundsCache = [];
let roundsLoading = false;

export function expandedProjectId() {
  return expandedId;
}

export function storeProjects(models) {
  projectsCache = Array.isArray(models) ? models : [];
  return projectsCache;
}

export function storeRounds(models) {
  roundsCache = Array.isArray(models) ? models : [];
  return roundsCache;
}

export function setRoundsLoading(flag) {
  roundsLoading = Boolean(flag);
}

export function toggleExpanded(projectId) {
  const id = String(projectId || "");
  expandedId = expandedId === id ? "" : id;
  return expandedId;
}

export function renderProjectsTab(host, { state = "idle", projects = null, message = "", expandedId: expanded = null, rounds = null, roundsLoading: loading = null } = {}) {
  const models = projects === null ? projectsCache : projects;
  const expandedNow = expanded === null ? expandedId : String(expanded || "");
  const roundsNow = rounds === null ? roundsCache : rounds;
  const roundsLoadingNow = loading === null ? roundsLoading : Boolean(loading);
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "프로젝트를 불러오는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "프로젝트를 불러오지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    if (typeof retry.addEventListener === "function") {
      retry.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__projectsTabLoad) window.__projectsTabLoad(true);
      });
    }
    host.appendChild(retry);
    return;
  }
  if (state === "idle") {
    host.appendChild(el("p", "note", "프로젝트 탭입니다."));
    return;
  }
  if (!models.length) {
    host.appendChild(el("p", "note", "표시할 프로젝트가 없습니다."));
    return;
  }
  for (const model of models) {
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", model.name));
    if (model.owner) head.appendChild(el("span", "chip", model.owner));
    if (model.createdUtc) head.appendChild(el("span", "chip", model.createdUtc.slice(0, 10)));
    if (model.archived) head.appendChild(el("span", "warnchip", "보관됨"));
    card.appendChild(head);
    if (model.description) card.appendChild(el("p", "note", model.description));
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "ghost";
    toggle.textContent = expandedNow === model.id ? "접기" : "라운드 보기";
    if (typeof toggle.addEventListener === "function") {
      toggle.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__projectsExpand) window.__projectsExpand(model.id);
      });
    }
    card.appendChild(toggle);
    host.appendChild(card);

    if (expandedNow !== model.id) continue;
    if (roundsLoadingNow) {
      host.appendChild(el("p", "note", "라운드를 불러오는 중…"));
      continue;
    }
    const roundRows = roundsNow;
    if (!roundRows.length) {
      host.appendChild(el("p", "note", "라운드가 없습니다."));
      continue;
    }
    for (const row of roundRows) {
      const item = el("div", "skill");
      const text = [row.id, row.createdUtc.slice(0, 10), row.title].filter(Boolean).join(" · ");
      item.appendChild(el("span", "", text || "-"));
      // 보관된 라운드는 라벨 칩으로 말한다 - 프로젝트 카드의 보관됨과 같은 근거
      // (status === "archived")이므로 프런트가 판단을 덧붙이지 않는다.
      if (String(row.status || "").trim().toLowerCase() === "archived") {
        item.appendChild(el("span", "chip", "보관됨"));
      }
      for (const runId of row.runIds) item.appendChild(el("span", "chip", runId));
      host.appendChild(item);
    }
  }
}

export async function requestProjects() {
  // include_archived 를 켠다 — 기본값은 보관된 프로젝트를 숨기므로 "보관됨"
  // 칩이 있는 카드는 영원히 볼 수 없다.
  const out = await callTool("pipeline.list_projects", { limit: 200, include_archived: true });
  if (out && out.error) throw new Error(out.error);
  return out;
}

export async function requestRounds(projectId) {
  const out = await callTool("pipeline.list_rounds", { project_id: projectId, limit: 100, include_archived: true });
  if (out && out.error) throw new Error(out.error);
  return out;
}
