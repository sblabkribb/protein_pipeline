// RAPID 목표 기반 설계 화면.
//
// 이 화면은 결정을 스스로 만들지 않는다. 서버의 pipeline.plan_from_objective 가
// 만든 계획을 그리고, 사람이 고친 값을 되돌려줄 뿐이다. 근거 문구를 프런트에서
// 지어내면 근거 추적이 깨지므로 서버가 준 것만 표시한다.

import { resolveDefaultApiBase } from "./lib/auth.js";
import { unwrapToolResponse } from "./lib/tool-call.js";

const OBJECTIVES = [
  { key: "solubility", label: "용해도", value: 0.4 },
  { key: "structural_preservation", label: "구조 보존", value: 0.4 },
  { key: "diversity", label: "다양성", value: 0.2 },
  { key: "stability", label: "안정성", value: 0 },
  { key: "activity", label: "활성", value: 0 },
  { key: "aggregation", label: "응집 위험", value: 0 },
  { key: "developability", label: "개발가능성", value: 0 },
];

// 평가 단계는 서버의 모델 레지스트리에서 온다. 프런트에 박아두면 실측값이
// 바뀌었을 때 화면만 옛날 숫자를 계속 보여준다 — 실제로 그렇게 해서 62 잔기
// 프로브에서 나온 "91s / fold" 가 59-274 잔기 백본 옆에 붙어 있었다.
const registry = { models: {}, purposes: [], loaded: false };

const KIND_LABEL = {
  internal_measurement: "측정",
  literature: "문헌",
  assumption: "가정",
};

// 기존 앱과 같은 규칙을 쓴다. 빈 문자열로 두면 /tools/call 을 원점 기준으로 호출하는데,
// 배포 환경의 리버스 프록시는 /api/* 만 백엔드로 보내므로 그대로 404 가 난다.
function apiBase() {
  const saved = (localStorage.getItem("kbf.apiBase") || "").replace(/\/+$/, "");
  if (saved && !/localhost|127\.0\.0\.1/.test(saved)) return saved;
  return resolveDefaultApiBase({
    origin: window.location.origin,
    pathname: window.location.pathname,
  }).replace(/\/+$/, "");
}

function authHeaders() {
  const token = localStorage.getItem("kbf.token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function callTool(name, args) {
  const res = await fetch(`${apiBase()}/tools/call`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, arguments: args || {} }),
  });
  const payload = await res.json().catch(() => null);
  // 봉투를 벗겨서 도구 결과만 돌려준다. 봉투를 그대로 넘기면 호출자가 보는
  // 모든 필드가 undefined 가 되고, 200 응답이라 오류도 뜨지 않는다.
  return unwrapToolResponse({ ok: res.ok, status: res.status, payload });
}

function formatSeconds(value) {
  if (value == null) return "미측정";
  if (value < 90) return `${value.toFixed(1)}s`;
  if (value < 5400) return `${(value / 60).toFixed(1)}분`;
  return `${(value / 3600).toFixed(2)}시간`;
}

// 스테이지 한 줄. 점 색은 "돌아가는가", 칩은 "얼마나 드는가", 배지는 "검증됐는가".
// 세 가지가 서로 다른 사실이라서 한 칸에 합치지 않는다.
function stageRow(stage, model, costEntry) {
  const row = document.createElement("div");
  row.className = "stage";

  const dot = document.createElement("span");
  dot.className = `dot${model && model.runnable ? "" : " off"}`;
  row.appendChild(dot);

  const label = document.createElement("span");
  label.textContent = `${stage.stage} · ${model ? model.display_name : stage.model_id}`;
  row.appendChild(label);

  if (!stage.validated) {
    const badge = document.createElement("span");
    badge.className = "chip warnchip";
    badge.textContent = "미검증";
    badge.title = "이 경로에서 측정된 적이 없습니다. 돌아가는 것과 맞는 것은 다릅니다.";
    row.appendChild(badge);
  }

  const chip = document.createElement("span");
  chip.className = "chip";
  if (costEntry && costEntry.seconds != null) {
    chip.textContent = formatSeconds(costEntry.seconds);
    const parts = [`출처: ${costEntry.source || "-"}`];
    if (model && model.cost && model.cost.scope) parts.push(`범위: ${model.cost.scope}`);
    if (costEntry.client_overhead_seconds != null) {
      parts.push(`클라이언트 폴링 추가 ${costEntry.client_overhead_seconds}s/호출`);
    }
    chip.title = parts.join("\n");
  } else {
    chip.textContent = "미측정";
    chip.title = (costEntry && costEntry.reason) || "측정된 비용이 없습니다. 0초가 아닙니다.";
  }
  row.appendChild(chip);

  // Gate 0 의 AUC 처럼 스테이지가 성능 측정을 갖고 있으면 같이 보여준다.
  if (model && model.performance && model.performance.value != null) {
    const perf = document.createElement("span");
    perf.className = "chip";
    perf.textContent = `${model.performance.metric} ${model.performance.value}`;
    perf.title = `출처: ${model.performance.source || "-"}`;
    row.appendChild(perf);
  }
  return row;
}

function renderStages(host, route) {
  if (!host) return;
  host.innerHTML = "";
  const total = document.getElementById("costTotal");
  if (!route) {
    host.textContent = "설계 목적을 고르면 단계가 표시됩니다.";
    if (total) total.textContent = "";
    return;
  }
  const costByStage = {};
  for (const entry of (route.cost_estimate && route.cost_estimate.breakdown) || []) {
    costByStage[entry.stage] = entry;
  }
  for (const stage of route.stages || []) {
    host.appendChild(stageRow(stage, registry.models[stage.model_id], costByStage[stage.stage]));
  }
  if (total) {
    const est = route.cost_estimate;
    if (!est) {
      total.textContent = "";
    } else {
      const unknown = est.unknown_stages || [];
      total.textContent =
        `측정된 합계 ${formatSeconds(est.known_seconds)}` +
        (unknown.length ? ` · 미측정 ${unknown.length}단계 제외 (하한값)` : " · 전 단계 측정됨");
    }
  }
}

async function loadRegistry() {
  const select = document.getElementById("purpose");
  try {
    const out = await callTool("pipeline.list_models", {
      n_designs: Number(document.getElementById("nDesigns").value) || 16,
      length_aa: Number(document.getElementById("lengthAa").value) || 200,
    });
    if (out && out.error) throw new Error(out.error);
    registry.models = out.models || {};
    registry.purposes = out.purposes || [];
    registry.loaded = true;
    select.innerHTML = "";
    for (const route of registry.purposes) {
      const option = document.createElement("option");
      option.value = route.purpose;
      // 실행할 수 없는 경로도 목록에 남긴다. 숨기면 사용자는 왜 없는지 모른다.
      option.textContent = route.display_name_ko + (route.executable ? "" : " — 실행 불가");
      select.appendChild(option);
    }
    onPurposeChange();
  } catch (error) {
    select.innerHTML = "";
    document.getElementById("purposeNote").textContent =
      `모델 목록을 가져오지 못했습니다: ${error.message}`;
    renderStages(document.getElementById("stages"), null);
  }
}

function currentRoute() {
  const value = document.getElementById("purpose").value;
  return registry.purposes.find((route) => route.purpose === value) || null;
}

function onPurposeChange() {
  const route = currentRoute();
  const note = document.getElementById("purposeNote");
  renderStages(document.getElementById("stages"), route);
  if (!route) { note.textContent = ""; return; }
  const lines = [route.description || ""];
  if (!route.executable) lines.push(route.blocked_reason || "");
  else if (!route.validated) {
    lines.push(`검증되지 않은 단계: ${(route.unvalidated_stages || []).join(", ")}`);
  }
  if (route.referral) lines.push(route.referral);
  if (route.caveat) lines.push(route.caveat);
  note.textContent = lines.filter(Boolean).join(" ");
  document.getElementById("planBtn").disabled = false;
}

function renderWeights(host) {
  host.innerHTML = "";
  for (const item of OBJECTIVES) {
    const row = document.createElement("label");
    row.innerHTML =
      `${item.label} <input type="range" min="0" max="1" step="0.05" value="${item.value}" data-key="${item.key}" />` +
      `<output>${item.value.toFixed(2)}</output>`;
    const slider = row.querySelector("input");
    const out = row.querySelector("output");
    slider.addEventListener("input", () => { out.textContent = Number(slider.value).toFixed(2); });
    host.appendChild(row);
  }
}

function collectObjective() {
  const weights = {};
  for (const slider of document.querySelectorAll("#weights input[type=range]")) {
    const value = Number(slider.value);
    if (value > 0) weights[slider.dataset.key] = value;
  }
  return {
    purpose: document.getElementById("purpose").value || undefined,
    weights,
    constraints: { rmsd_max: Number(document.getElementById("rmsdMax").value) },
    budget: {
      af2_calls: Number(document.getElementById("af2Budget").value),
      designs: Number(document.getElementById("nDesigns").value),
      length_aa: Number(document.getElementById("lengthAa").value),
    },
  };
}

function evidenceNode(ev) {
  const node = document.createElement("div");
  node.className = "ev";
  const kind = document.createElement("span");
  kind.className = `kind kind-${ev.kind}`;
  kind.textContent = KIND_LABEL[ev.kind] || ev.kind;
  node.appendChild(kind);
  node.appendChild(document.createTextNode(ev.statement || ""));
  if (ev.source) {
    const src = document.createElement("span");
    src.className = "src";
    src.textContent = `출처: ${ev.source}`;
    node.appendChild(src);
  }
  return node;
}

function decisionNode(decision, edits) {
  const box = document.createElement("div");
  box.className = decision.editable ? "decision" : "decision locked";

  const row = document.createElement("div");
  row.className = "row";
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = decision.field;
  row.appendChild(name);

  const input = document.createElement("input");
  input.type = typeof decision.value === "number" ? "number" : "text";
  if (input.type === "number") input.step = "any";
  input.value = String(decision.value);
  input.disabled = !decision.editable;
  input.addEventListener("change", () => {
    const raw = input.value;
    const parsed = input.type === "number" ? Number(raw) : raw;
    edits[decision.field] = parsed;
    box.querySelector(".badge.edited")?.remove();
    const badge = document.createElement("span");
    badge.className = "badge edited";
    badge.textContent = "수정됨";
    row.appendChild(badge);
  });
  row.appendChild(input);

  if (!decision.editable) {
    const lock = document.createElement("span");
    lock.className = "badge lock";
    lock.textContent = "고정 — 측정 결과가 반대를 지지함";
    row.appendChild(lock);
  }
  box.appendChild(row);

  const rationale = document.createElement("p");
  rationale.className = "rationale";
  rationale.textContent = decision.rationale || "";
  box.appendChild(rationale);

  const evidence = decision.evidence || [];
  if (evidence.length) {
    const details = document.createElement("details");
    details.className = "evidence";
    const summary = document.createElement("summary");
    const kinds = evidence.map((e) => KIND_LABEL[e.kind] || e.kind);
    summary.textContent = `근거 ${evidence.length}건 (${[...new Set(kinds)].join(", ")})`;
    details.appendChild(summary);
    for (const ev of evidence) details.appendChild(evidenceNode(ev));
    box.appendChild(details);
  }
  return box;
}

function renderEvidencePanel(plan) {
  const host = document.getElementById("evidenceList");
  if (!host) return;
  host.innerHTML = "";
  host.classList.remove("empty");
  let count = 0;
  for (const decision of plan.decisions || []) {
    for (const ev of decision.evidence || []) {
      const node = evidenceNode(ev);
      const who = document.createElement("span");
      who.className = "src";
      who.textContent = `결정: ${decision.field}`;
      node.appendChild(who);
      host.appendChild(node);
      count += 1;
    }
  }
  if (!count) {
    host.classList.add("empty");
    host.textContent = "근거가 없습니다.";
  }
}

const REASON_LABEL = {
  evidence_is_assumption_only: "근거가 가정뿐",
  evidence_partially_assumption: "일부만 측정으로 뒷받침",
  objective_not_measurable: "평가 불가한 목표",
  objective_not_covered_by_purpose: "목적이 이 목표를 포함하지 않음",
};

// 설명은 LLM 이 만든 산문이고 근거가 아니다. 근거 패널과 분리해서 보여준다.
async function explainPlan(plan) {
  const box = document.getElementById("explainBox");
  const text = document.getElementById("explainText");
  const badge = document.getElementById("explainSource");
  const host = document.getElementById("questions");
  try {
    const result = await callTool("pipeline.explain_plan", { plan });
    if (result && result.error) throw new Error(result.error);
    text.textContent = result.explanation || "";
    badge.textContent = result.explanation_is_generated
      ? `LLM 생성 (${result.explanation_source})`
      : "LLM 미설정 · 계획 요약";
    host.innerHTML = "";
    for (const item of result.questions || []) {
      const node = document.createElement("div");
      node.className = "q";
      if (item.field) {
        const field = document.createElement("span");
        field.className = "qfield";
        field.textContent = item.field;
        node.appendChild(field);
      }
      node.appendChild(document.createTextNode(item.question || ""));
      const why = document.createElement("span");
      why.className = "qwhy";
      why.textContent = REASON_LABEL[item.reason] || item.reason || "";
      node.appendChild(why);
      host.appendChild(node);
    }
    box.classList.remove("hidden");
  } catch (error) {
    text.textContent = `설명을 가져오지 못했습니다: ${error.message}`;
    badge.textContent = "실패";
    host.innerHTML = "";
    box.classList.remove("hidden");
  }
}

const state = { plan: null, edits: {} };

async function generatePlan() {
  const status = document.getElementById("planStatus");
  const button = document.getElementById("planBtn");
  button.disabled = true;
  status.textContent = "계획 생성 중…";
  try {
    const plan = await callTool("pipeline.plan_from_objective", collectObjective());
    if (plan && plan.error) throw new Error(plan.error);
    state.plan = plan;
    state.edits = {};

    const warnings = document.getElementById("warnings");
    warnings.innerHTML = "";
    for (const message of plan.warnings || []) {
      const node = document.createElement("div");
      node.className = "warn";
      node.textContent = message;
      warnings.appendChild(node);
    }

    const host = document.getElementById("decisions");
    host.innerHTML = "";
    for (const decision of plan.decisions || []) {
      host.appendChild(decisionNode(decision, state.edits));
    }
    host.classList.remove("empty");
    renderEvidencePanel(plan);
    await explainPlan(plan);

    const reviewState = document.getElementById("reviewState");
    reviewState.textContent = `결정 ${(plan.decisions || []).length}건 · 수정 가능 ${(plan.editable_fields || []).length}건`;
    reviewState.classList.add("ready");
    // 실행조차 못 하는 경로를 승인 버튼 뒤에 두지 않는다.
    const approvable = plan.approvable !== false;
    document.getElementById("approveState").textContent = approvable
      ? "검토 후 승인 가능"
      : "이 경로는 여기서 실행할 수 없어 승인할 수 없습니다";
    document.getElementById("approveBtn").disabled = !approvable;
    if (plan.route) renderStages(document.getElementById("stages"), plan.route);
    status.className = "status";
    status.textContent = "";
  } catch (error) {
    status.className = "status bad";
    status.textContent = `실패: ${error.message}`;
    document.getElementById("reviewState").textContent = "계획 생성 실패";
    // 401 은 설정 문제가 아니라 로그인 문제다. 무엇을 해야 하는지 알려준다.
    if (/unauthorized|401/i.test(error.message)) {
      document.getElementById("authHint").classList.remove("hidden");
    }
  } finally {
    button.disabled = false;
  }
}

async function approve() {
  const out = document.getElementById("requestOut");
  try {
    const result = await callTool("pipeline.approve_plan", {
      plan: state.plan,
      edits: state.edits,
    });
    if (result && result.error) throw new Error(result.error);
    out.classList.remove("empty");
    out.textContent = JSON.stringify(result, null, 2);
    const approveState = document.getElementById("approveState");
    approveState.textContent = "승인됨 · 실행하지 않음";
    approveState.classList.add("ready");
  } catch (error) {
    out.classList.remove("empty");
    out.textContent = `실패: ${error.message}`;
  }
}

renderWeights(document.getElementById("weights"));
renderStages(document.getElementById("stages"), null);
document.getElementById("purpose").addEventListener("change", onPurposeChange);
for (const id of ["nDesigns", "lengthAa"]) {
  document.getElementById(id).addEventListener("change", loadRegistry);
}
loadRegistry();

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".tab")) other.classList.remove("is-active");
    tab.classList.add("is-active");
    for (const panel of document.querySelectorAll(".panel")) panel.classList.add("hidden");
    document.getElementById(`panel-${tab.dataset.panel}`).classList.remove("hidden");
  });
}
document.getElementById("planBtn").addEventListener("click", generatePlan);
document.getElementById("approveBtn").addEventListener("click", approve);

export { collectObjective, decisionNode, evidenceNode, formatSeconds, stageRow };
