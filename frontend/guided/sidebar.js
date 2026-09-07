import { callTool, errorText } from "./api.js";
import { el } from "./dom.js";

// 좌측 실행 목록. list_runs 는 문자열 목록을 돌려주는 배포본과 객체를 돌려주는
// 배포본이 둘 다 있었다 - 둘 다 받는다.
export function normalizeRuns(raw) {
  const seen = new Set();
  const rows = [];
  for (const run of Array.isArray(raw) ? raw : []) {
    if (run == null) continue;
    const id = typeof run === "string" ? run : String(run.run_id || run.id || "");
    if (!id || seen.has(id)) continue;
    seen.add(id);
    rows.push({
      run_id: id,
      stage: typeof run === "object" ? String(run.stage || "") : "",
      state: typeof run === "object" ? String(run.state || "") : "",
      updated_at: typeof run === "object" ? String(run.updated_at || "") : "", // 향후 목록 정렬/표시에 쓴다 - 지금은 계약 보존용.
    });
  }
  return rows;
}

export function runItemLabel(run) {
  const parts = [run.stage, run.state].filter(Boolean);
  return parts.length ? parts.join(" · ") : "idle";
}

export async function loadRunList(onSelect) {
  const host = document.getElementById("runList");
  host.classList.remove("empty");
  host.textContent = "불러오는 중…";
  try {
    const out = await callTool("pipeline.list_runs", { limit: 30 });
    if (out && out.error) throw new Error(out.error);
    const runs = normalizeRuns(out.runs || out.items || []);
    host.replaceChildren();
    if (!runs.length) {
      host.classList.add("empty");
      host.textContent = "실행이 없습니다.";
      return [];
    }
    for (const run of runs) {
      const node = document.createElement("button");
      node.type = "button";
      node.className = "run-item";
      node.dataset.runId = run.run_id;
      node.appendChild(el("span", "rid", run.run_id));
      node.appendChild(el("span", "rmeta", runItemLabel(run)));
      node.addEventListener("click", () => {
        highlightRun(run.run_id);
        onSelect(run.run_id);
      });
      host.appendChild(node);
    }
    return runs;
  } catch (error) {
    host.classList.add("empty");
    host.textContent = `실행 목록을 불러오지 못했습니다: ${errorText(error)}`;
    return [];
  }
}

export function highlightRun(runId) {
  for (const item of document.querySelectorAll("#runList .run-item")) {
    item.classList.toggle("is-active", item.dataset.runId === runId);
    item.toggleAttribute("aria-current", item.dataset.runId === runId);
  }
}
