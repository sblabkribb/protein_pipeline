// RAPID 목표 기반 설계 화면.
//
// 이 화면은 결정을 스스로 만들지 않는다. 서버의 pipeline.plan_from_objective 가
// 만든 계획을 그리고, 사람이 고친 값을 되돌려줄 뿐이다. 근거 문구를 프런트에서
// 지어내면 근거 추적이 깨지므로 서버가 준 것만 표시한다.

import { resolveDefaultApiBase } from "./lib/auth.js";

const OBJECTIVES = [
  { key: "solubility", label: "용해도", value: 0.4 },
  { key: "structural_preservation", label: "구조 보존", value: 0.4 },
  { key: "diversity", label: "다양성", value: 0.2 },
  { key: "stability", label: "안정성", value: 0 },
  { key: "activity", label: "활성", value: 0 },
  { key: "aggregation", label: "응집 위험", value: 0 },
  { key: "developability", label: "개발가능성", value: 0 },
];

// 좌측에 보여줄 평가 단계와 실측 비용. 값을 지어내지 않는다 — 전부 측정된 것이다.
const STAGES = [
  { name: "Gate 0 · 타겟 선별", cost: "AUC 0.725", on: true },
  { name: "ProteinMPNN 생성", cost: "초 단위", on: true },
  { name: "Gate 1 · SoluProt", cost: "초 단위", on: true },
  { name: "Gate 2 · AF2/ColabFold", cost: "91s / fold", on: true },
  { name: "활성 평가 플러그인", cost: "미구현", on: false },
];

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
  if (!res.ok) {
    const message = payload && typeof payload.error === "string" ? payload.error : `HTTP ${res.status}`;
    throw new Error(message);
  }
  return payload;
}

function renderStages(host) {
  if (!host) return;
  host.innerHTML = "";
  for (const stage of STAGES) {
    const row = document.createElement("div");
    row.className = "stage";
    row.innerHTML =
      `<span class="dot${stage.on ? "" : " off"}"></span>` +
      `<span>${stage.name}</span><span class="chip">${stage.cost}</span>`;
    host.appendChild(row);
  }
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
    weights,
    constraints: { rmsd_max: Number(document.getElementById("rmsdMax").value) },
    budget: { af2_calls: Number(document.getElementById("af2Budget").value) },
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

    const reviewState = document.getElementById("reviewState");
    reviewState.textContent = `결정 ${(plan.decisions || []).length}건 · 수정 가능 ${(plan.editable_fields || []).length}건`;
    reviewState.classList.add("ready");
    document.getElementById("approveState").textContent = "검토 후 승인 가능";
    document.getElementById("approveBtn").disabled = false;
    status.className = "status";
    status.textContent = "";
  } catch (error) {
    status.className = "status bad";
    status.textContent = `실패: ${error.message}`;
    document.getElementById("reviewState").textContent = "계획 생성 실패";
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
renderStages(document.getElementById("stages"));

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

export { collectObjective, decisionNode, evidenceNode };
