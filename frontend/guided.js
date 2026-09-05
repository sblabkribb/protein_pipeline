// RAPID 목표 기반 설계 화면.
//
// 이 화면은 결정을 스스로 만들지 않는다. 서버의 pipeline.plan_from_objective 가
// 만든 계획을 그리고, 사람이 고친 값을 되돌려줄 뿐이다. 근거 문구를 프런트에서
// 지어내면 근거 추적이 깨지므로 서버가 준 것만 표시한다.

const OBJECTIVES = [
  { key: "solubility", label: "용해도", value: 0.4 },
  { key: "structural_preservation", label: "구조 보존", value: 0.4 },
  { key: "diversity", label: "다양성", value: 0.2 },
  { key: "stability", label: "안정성", value: 0 },
  { key: "activity", label: "활성", value: 0 },
  { key: "aggregation", label: "응집 위험", value: 0 },
  { key: "developability", label: "개발가능성", value: 0 },
];

const KIND_LABEL = {
  internal_measurement: "측정",
  literature: "문헌",
  assumption: "가정",
};

function apiBase() {
  return (localStorage.getItem("kbf.apiBase") || "").replace(/\/+$/, "") || "";
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
    document.getElementById("planCard").classList.remove("hidden");
    document.getElementById("applyCard").classList.remove("hidden");
    status.textContent = `결정 ${(plan.decisions || []).length}건 · 수정 가능 ${(plan.editable_fields || []).length}건`;
  } catch (error) {
    status.textContent = `실패: ${error.message}`;
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
    out.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    out.textContent = `실패: ${error.message}`;
  }
}

renderWeights(document.getElementById("weights"));
document.getElementById("planBtn").addEventListener("click", generatePlan);
document.getElementById("approveBtn").addEventListener("click", approve);

export { collectObjective, decisionNode, evidenceNode };
