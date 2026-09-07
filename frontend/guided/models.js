// frontend/guided/models.js — 모델 탭. 레지스트리(목적 경로·목표 평가 상태·모델
// 카탈로그)를 pipeline.list_models 로 읽어 보여준다. 정적 데이터라 탭 첫 진입
// 1회 로드 후 캐시한다. 목적 목록도 목표 상태도 프런트에 박지 않는다 - 레지스트리가
// 진실이고, objective_status 가 응답에 그대로 내려온다 (tools.py).
import { callTool } from "./api.js";
import { el } from "./dom.js";

// 레지스트리 objective_status 의 다섯 상태. 판정은 백엔드 레지스트리가 하고
// 여기서는 말만 바꾼다 - 프런트가 상태를 추측하면 레지스트리와 갈라진다.
const STATUS_LABEL = {
  measured: ["okchip", "측정됨"],
  evaluator_unvalidated: ["warnchip", "평가자 있음 · 미검증"],
  evaluator_not_wired: ["warnchip", "구현 있음 · 미배선"],
  needs_experimental_labels: ["chip", "실험 라벨 필요"],
  no_evaluator_available: ["chip", "평가자 없음"],
};

// objective_status 가 없는 구 페이로드용 3분류 폴백. measurable/unvalidated 집합만
// 있을 때의 옛 분류이고, 어휘 미러는 넣지 않는다 - 응답이 말한 목표만 보인다.
const FALLBACK_LABEL = {
  measured: ["okchip", "측정됨"],
  unvalidated: ["warnchip", "평가자 있으나 미검증"],
  none: ["chip", "평가자 없음"],
};

// evaluators 는 JSON 배열이 정상이지만, 낡은 직렬화에서는 파이썬 repr 문자열
// ("['a', 'b']")로 흘러들 수 있다. [ 로 시작하면 JSON 파싱을 시도하고, 실패하면
// 쉼표로 나눈다 - 손에 잡히는 것은 전부 평가자 이름으로 보인다.
function parseEvaluators(raw) {
  if (Array.isArray(raw)) return raw.map((v) => String(v).trim()).filter(Boolean);
  const text = String(raw ?? "").trim();
  if (!text) return [];
  if (text.startsWith("[")) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed.map((v) => String(v).trim()).filter(Boolean);
      }
    } catch {
      // JSON 이 아니면 아래의 쉼표 분해로 떨어진다.
    }
  }
  return text.replace(/[[\]"']/g, "").split(",").map((s) => s.trim()).filter(Boolean);
}

function objectiveRows(data) {
  const status = data.objective_status;
  if (status && typeof status === "object" && Object.keys(status).length) {
    return Object.entries(status).map(([key, raw]) => {
      const entry = raw && typeof raw === "object" ? raw : {};
      const [cls, label] = STATUS_LABEL[entry.status]
        || ["chip", String(entry.status || "평가자 없음")];
      return {
        key: String(key),
        status: String(entry.status || ""),
        state: String(entry.status || ""),
        cls,
        label,
        evaluators: parseEvaluators(entry.evaluators),
        detail: String(entry.detail || ""),
        toEnable: String(entry.to_enable || ""),
      };
    });
  }
  const measured = new Set(data.measurable_objectives || []);
  const unvalidated = new Set(data.runnable_but_unvalidated_objectives || []);
  return [...new Set([...measured, ...unvalidated])].map((key) => {
    const state = measured.has(key) ? "measured" : "unvalidated";
    const [cls, label] = FALLBACK_LABEL[state];
    return {
      key: String(key), status: state, state, cls, label,
      evaluators: [], detail: "", toEnable: "",
    };
  });
}

function purposeRows(data) {
  return (Array.isArray(data.purposes) ? data.purposes : [])
    .filter((p) => p && typeof p === "object")
    .map((p) => ({
      purpose: String(p.purpose || ""),
      executable: Boolean(p.executable),
      validated: Boolean(p.validated),
      // 왜 미검증인지는 스테이지가 말한다. 상한 8 - 경로가 길어도 카드가 좁은
      // 레일을 먹지 않게. 모양은 route dict 의 stages[]. 그대로 온다.
      stages: (Array.isArray(p.stages) ? p.stages : [])
        .filter((s) => s && typeof s === "object")
        .slice(0, 8)
        .map((s) => ({
          stage: String(s.stage || ""),
          modelId: String(s.model_id || ""),
          validated: Boolean(s.validated),
        }))
        .filter((s) => s.stage || s.modelId),
    }));
}

export function modelsTabModels(payload) {
  const data = payload && typeof payload === "object" ? payload : {};
  return {
    purposes: purposeRows(data),
    objectives: objectiveRows(data),
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
    if (purpose.stages.length) {
      // 목적이 왜 미검증인지는 스테이지가 안다. 미검증 스테이지에 warn 점.
      const line = el("div", "stagesline");
      for (const stage of purpose.stages) {
        const chip = el("span", "chip", stage.stage
          ? `${stage.stage}(${stage.modelId})` : stage.modelId);
        if (!stage.validated) chip.appendChild(el("span", "sdot warn"));
        line.appendChild(chip);
      }
      row.appendChild(line);
    }
    host.appendChild(row);
  }

  host.appendChild(el("h3", "", "목표별 평가자 상태"));
  for (const objective of data.objectives) {
    const row = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", objective.key));
    head.appendChild(el("span", objective.cls, objective.label));
    row.appendChild(head);
    for (const evaluator of objective.evaluators) {
      row.appendChild(el("span", "chip", evaluator));
    }
    if (objective.detail) row.appendChild(el("p", "note", objective.detail));
    if (objective.toEnable) {
      row.appendChild(el("p", "note", "활성화하려면: " + objective.toEnable));
    }
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
