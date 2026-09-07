// frontend/guided/models.js — 모델 탭. 레지스트리(목적 경로·목표 평가 상태·모델
// 카탈로그)를 pipeline.list_models 로 읽어 보여준다. 정적 데이터라 탭 첫 진입
// 1회 로드 후 캐시한다. 목적 목록을 프런트에 박지 않는다 - 레지스트리가 진실이다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

// 목표 어휘는 플랫폼이 아는 것(da 뒤 objective_planner.KNOWN_OBJECTIVES)과 같다.
// 목적 목록과 달리 목표는 화면이 세 상태를 판정하려면 후보가 필요하다 - 레지스트리가
// 말하지 않은 목표는 평가자 없음(none)으로 보인다.
const KNOWN_OBJECTIVES = [
  "solubility", "structural_preservation", "stability", "activity",
  "aggregation", "developability", "diversity", "binding",
];

export function modelsTabModels(payload) {
  const data = payload && typeof payload === "object" ? payload : {};
  const measured = new Set(data.measurable_objectives || []);
  const unvalidated = new Set(data.runnable_but_unvalidated_objectives || []);
  // 레지스트리가 목표에 대해 말한 경우에만 어휘를 채운다. 응답이 없거나 비어 있으면
  // 아무것도 지어내지 않는다 - 빈 화면은 곧 "불러온 것이 없다"의 뜻이다.
  const spoke = Array.isArray(data.measurable_objectives)
    || Array.isArray(data.runnable_but_unvalidated_objectives);
  const vocabulary = spoke ? [...KNOWN_OBJECTIVES] : [];
  const keys = [...new Set([...vocabulary, ...measured, ...unvalidated])];
  return {
    purposes: (Array.isArray(data.purposes) ? data.purposes : [])
      .filter((p) => p && typeof p === "object")
      .map((p) => ({
        purpose: String(p.purpose || ""),
        executable: Boolean(p.executable),
        validated: Boolean(p.validated),
      })),
    objectives: keys.map((key) => ({
      key: String(key),
      state: measured.has(key) ? "measured"
        : unvalidated.has(key) ? "unvalidated" : "none",
    })),
    models: Object.entries(data.models || {}).map(([id, m]) => {
      const item = m && typeof m === "object" ? m : {};
      // ModelEntry.to_dict() 는 extra 를 상위로 평탄화해 보낸다 (model_routing.py).
      // 그래서 접근 정보는 item.extra.access 가 아니라 item.access 다.
      const access = item.access || {};
      return {
        id: String(id),
        name: String(item.display_name || id),
        endpoint: String(item.endpoint || "").slice(0, 40),
        portalOnly: Boolean(access.portal_mcp) && !access.direct_client,
      };
    }),
  };
}

export function renderModels(host, { state = "idle", model = null, message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "모델 레지스트리를 불러오는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "레지스트리를 불러오지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    if (typeof retry.addEventListener === "function") {
      retry.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__modelsTabLoad) window.__modelsTabLoad(true);
      });
    }
    host.appendChild(retry);
    return;
  }
  if (state === "idle") {
    host.appendChild(el("p", "note", "모델 탭입니다."));
    return;
  }
  const data = model || { purposes: [], objectives: [], models: [] };

  host.appendChild(el("h3", "", "설계 목적 경로"));
  for (const purpose of data.purposes) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", purpose.purpose));
    if (purpose.validated) head.appendChild(el("span", "okchip", "검증됨"));
    else if (purpose.executable) head.appendChild(el("span", "warnchip", "실행 가능·미검증"));
    else head.appendChild(el("span", "badchip", "실행 불가"));
    row.appendChild(head);
    host.appendChild(row);
  }

  host.appendChild(el("h3", "", "목표별 평가자 상태"));
  for (const objective of data.objectives) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", objective.key));
    if (objective.state === "measured") head.appendChild(el("span", "okchip", "측정됨"));
    else if (objective.state === "unvalidated") head.appendChild(el("span", "warnchip", "평가자 있으나 미검증"));
    else head.appendChild(el("span", "chip", "평가자 없음"));
    row.appendChild(head);
    host.appendChild(row);
  }

  host.appendChild(el("h3", "", "모델 카탈로그"));
  for (const item of data.models) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", item.name));
    if (item.portalOnly) head.appendChild(el("span", "chip", "포털 경유"));
    row.appendChild(head);
    if (item.endpoint) row.appendChild(el("p", "note", item.endpoint));
    host.appendChild(row);
  }
}

export async function requestModels() {
  const out = await callTool("pipeline.list_models", {});
  if (out && out.error) throw new Error(out.error);
  return out;
}
