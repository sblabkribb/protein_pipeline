// frontend/guided/results.js — Results 탭: 티어 퍼널, 히트리스트, 실행 비교.
//
// 퍼널은 파이프라인이 쓴 산출물 계약(soluprot.json 의 scores/passed_ids,
// af2_scores.json 의 candidate_ids/selected_ids)을 그대로 읽는다. 여기서
// 점수를 다시 계산하지 않는다 - 같은 사실이 두 곳에서 갈라지기 때문이다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

// 히트리스트 행의 신원 필드는 id 가 아니라 seq_id 다 (tools.py 의 get_hit_list).
export const HIT_COLUMNS = ["seq_id", "score", "soluprot", "plddt", "rmsd", "novelty"];

const FUNNEL_COLUMNS = ["tier", "designed", "soluprot", "af2", "af2_selected"];

// 티어 한 개의 퍼널 행. soluprot.json / af2_scores.json 은 파이프라인이 쓰는
// 계약 필드(scores, passed_ids / candidate_ids, selected_ids)를 그대로 읽는다.
export function buildFunnelRow(tier, soluprot, af2) {
  const scores = (soluprot && soluprot.scores) || {};
  return {
    tier: String(tier),
    designed: Object.keys(scores).length,
    soluprot: Array.isArray(soluprot?.passed_ids) ? soluprot.passed_ids.length : 0,
    af2: Array.isArray(af2?.candidate_ids) ? af2.candidate_ids.length : 0,
    af2_selected: Array.isArray(af2?.selected_ids) ? af2.selected_ids.length : 0,
  };
}

// list_artifacts 결과에서 티어별 soluprot/af2_scores 경로를 모은다.
export function tierArtifactPaths(artifacts) {
  const tiers = new Map();
  for (const item of Array.isArray(artifacts) ? artifacts : []) {
    if (String(item?.type || "file") !== "file") continue;
    const path = String(item?.path || item?.name || "");
    const match = path.match(/tiers\/([0-9.]+)\/(soluprot|af2_scores)\.json$/);
    if (!match) continue;
    const [, tier, kind] = match;
    if (!tiers.has(tier)) tiers.set(tier, {});
    tiers.get(tier)[kind] = path;
  }
  return tiers;
}

export async function loadFunnel(runId, artifacts) {
  let tiers = tierArtifactPaths(artifacts);
  if (!tiers.size) {
    // list_artifacts 는 limit 안에서 우선순위로 자른다. 큰 실행에서는 tiers/
    // 가 먼저 잘려나가 퍼널이 조용히 비어 보인다. 비었으면 tiers 로 다시 묻는다
    // - 서버는 prefix 로 좁힌 목록을 run 루트 기준 상대경로로 돌려준다.
    try {
      const out = await callTool("pipeline.list_artifacts", { run_id: runId, prefix: "tiers", limit: 400 });
      if (out && !out.error) tiers = tierArtifactPaths(out.artifacts || []);
    } catch { /* 폴백 실패 시에도 아래 빈 상태 처리로 진행 */ }
  }
  const rows = [];
  for (const [tier, paths] of [...tiers.entries()].sort()) {
    const fetchJson = async (path) => {
      if (!path) return null;
      try {
        const out = await callTool("pipeline.read_artifact", { run_id: runId, path, max_bytes: 400000 });
        // 잘린 JSON 은 파싱에 성공해도 조용히 틀린 숫자를 준다. 못 읽은 것과
        // 0 인 것을 같은 0 으로 보여주지 않는다 - 잘렸으면 없는 것으로 둔다.
        if (!out || !out.text || out.truncated) return null;
        return JSON.parse(out.text);
      } catch {
        return null;   // 티어 하나를 못 읽어도 나머지 퍼널은 그린다.
      }
    };
    const [soluprot, af2] = await Promise.all([fetchJson(paths.soluprot), fetchJson(paths.af2_scores)]);
    rows.push(buildFunnelRow(tier, soluprot, af2));
  }
  return rows;
}

export function renderFunnel(host, rows) {
  host.replaceChildren();
  if (!rows.length) {
    host.appendChild(el("p", "note", "이 실행에는 티어 결과가 없습니다."));
    return;
  }
  const max = Math.max(...rows.map((r) => Math.max(r.designed, 1)));
  const bar = el("div", "funnel");
  for (const row of rows) {
    for (const key of FUNNEL_COLUMNS.slice(1)) {
      const col = document.createElement("i");
      col.style.height = `${Math.max(6, (row[key] / max) * 100)}%`;
      col.title = `${row.tier} ${key}: ${row[key]}`;
      bar.appendChild(col);
    }
  }
  host.appendChild(bar);
  host.appendChild(renderFunnelRowsTable(rows));
}

// 테이블은 순수 렌더다 - 테스트가 최소 document 흉내로 구조를 검증한다.
export function renderFunnelRowsTable(rows) {
  const table = document.createElement("table");
  const head = table.insertRow();
  for (const key of FUNNEL_COLUMNS) head.appendChild(el("th", "", key));
  for (const row of rows) {
    const tr = table.insertRow();
    for (const key of FUNNEL_COLUMNS) {
      tr.insertCell().textContent = String(row[key]);
    }
  }
  return table;
}

// 비교 결과의 스칼라를 중첩까지 펼쳐 카드로 만든다. summary 는 카드가 아니라
// 그 내부 지표들이 카드다. notes 는 산문이라 지표 카드에 섞지 않는다 - 모르는
// 키를 버리지는 않되, 산문만은 근거 추적을 흐리므로 가린다.
export function summarizeCompare(result) {
  const cards = [];
  const walk = (obj, prefix = "") => {
    for (const [key, value] of Object.entries(obj || {})) {
      if (key === "notes") continue;
      const label = prefix ? `${prefix}.${key}` : key;
      if (value != null && typeof value !== "object") cards.push({ label, value: String(value) });
      else if (value != null && typeof value === "object" && !Array.isArray(value)) walk(value, label);
    }
  };
  walk(result);
  return cards;
}

export function renderHitList(host, rows) {
  host.replaceChildren();
  if (!Array.isArray(rows) || !rows.length) {
    host.appendChild(el("p", "note", "히트리스트가 비어 있습니다."));
    return;
  }
  const table = document.createElement("table");
  const head = table.insertRow();
  for (const key of HIT_COLUMNS) head.appendChild(el("th", "", key));
  for (const row of rows) {
    const tr = table.insertRow();
    for (const key of HIT_COLUMNS) {
      const value = row[key];
      tr.insertCell().textContent = value == null ? "-" : String(value);
    }
  }
  host.appendChild(table);
}

export async function loadHitList(runId) {
  const out = await callTool("pipeline.get_hit_list", { run_id: runId, limit: 20 });
  if (out && out.error) throw new Error(out.error);
  return out.rows || out.hits || out.items || [];
}

export async function loadCompare(runId, baselineRunId) {
  return callTool("pipeline.compare_runs", {
    run_id: runId,
    ...(baselineRunId ? { baseline_run_id: baselineRunId } : {}),
  });
}
