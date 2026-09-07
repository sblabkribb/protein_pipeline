// frontend/guided/plan.js — 목표·경로·계획 검토/승인 렌더링. DOM 을 그리고 서버 도구를 호출한다.
import { callTool, errorText } from "./api.js";
// 순환 import: facade 와 상호 참조. 함수 선언이라 hoisting 으로 안전하되,
// 모듈 최상위에서 호출하지 말 것.
import { setSignedOut, showStep } from "../guided.js";

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

// 값은 textContent 로만 넣는다. 아티팩트 경로와 실행 상태는 서버에서 오고,
// 산출물 경로에는 사용자가 정한 이름(run id, design id)이 섞인다. 그 이름을
// innerHTML 로 넣으면 안에 든 마크업이 실행된다.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

function dot(on) {
  return el("span", `dot${on ? "" : " off"}`);
}

const KIND_LABEL = {
  internal_measurement: "측정",
  literature: "문헌",
  assumption: "가정",
};

// 파이프라인 내부 키를 그대로 보여주면 읽는 사람이 번역을 해야 한다.
const STAGE_LABEL = {
  gate0_routing: "게이트 0 · 타겟 선별",
  backbone_generate: "백본 생성",
  sequence_design: "서열 설계",
  cheap_filter: "가용성 필터",
  interface_screen: "인터페이스 선별",
  structure_verify: "구조 검증",
  interface_score: "인터페이스 점수",
  numbering: "항체 넘버링",
  docking: "도킹",
};

function stageLabel(stage) {
  return STAGE_LABEL[stage] || stage;
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

  const bullet = document.createElement("span");
  bullet.className = `dot${model && model.runnable ? "" : " off"}`;
  row.appendChild(bullet);

  // 파이프라인 내부 키를 그대로 보여주면 읽는 사람이 번역을 해야 한다.
  row.appendChild(el("span", "sname", stageLabel(stage.stage)));
  row.appendChild(el("span", "smodel", model ? model.display_name : stage.model_id));

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

// 이 화면의 일은 "GPU 시간을 쓸 값어치가 있는가" 를 판단하게 하는 것이다.
// 그래서 비용이 어디로 가는지를 표로만 두지 않고 한눈에 보이게 그린다.
// 측정하지 않은 단계는 폭이 아니라 빗금으로 표시한다 - 0 으로 그리면 공짜처럼
// 보이고, 임의의 폭을 주면 없는 측정을 지어내는 것이다.
function renderCostBar(host, route) {
  host.replaceChildren();
  const est = route && route.cost_estimate;
  if (!est) return;
  const known = (est.breakdown || []).filter((b) => b.seconds != null && b.seconds > 0);
  const unknown = (est.breakdown || []).filter((b) => b.seconds == null);
  if (!known.length && !unknown.length) return;

  const total = known.reduce((sum, b) => sum + b.seconds, 0);
  const bar = el("div", "costbar");
  for (const entry of known) {
    const part = el("div", "costpart");
    part.style.flexGrow = String(entry.seconds);
    part.title = `${stageLabel(entry.stage)} · ${formatSeconds(entry.seconds)} · 출처 ${entry.source || "-"}`;
    part.appendChild(el("span", "costlabel", stageLabel(entry.stage)));
    part.appendChild(el("span", "costvalue", formatSeconds(entry.seconds)));
    bar.appendChild(part);
  }
  for (const entry of unknown) {
    const part = el("div", "costpart is-unknown");
    part.style.flexGrow = "0.6";
    part.title = `${stageLabel(entry.stage)} · 측정된 비용 없음`;
    part.appendChild(el("span", "costlabel", stageLabel(entry.stage)));
    part.appendChild(el("span", "costvalue", "미측정"));
    bar.appendChild(part);
  }
  host.appendChild(bar);

  const caption = el("p", "costnote",
    total > 0
      ? `측정된 비용 ${formatSeconds(total)}. 빗금 구간은 재지 않아 합계에 들어가지 않았습니다.`
      : "이 경로에는 측정된 비용이 없습니다.");
  host.appendChild(caption);
}

function renderStages(host, route) {
  if (!host) return;
  host.innerHTML = "";
  const total = document.getElementById("routeMeta");
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
        (unknown.length ? ` · ${unknown.length}단계 미측정이라 하한값` : " · 전 단계 측정됨");
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
    // 기본 선택은 목록의 첫 항목이 아니라 **실제로 돌릴 수 있고 검증된** 경로다.
    // 순서에 기대면 레지스트리 순서가 바뀔 때 조용히 실행 불가 경로가 잡힌다.
    const preferred = registry.purposes.find((r) => r.executable && r.validated)
      || registry.purposes.find((r) => r.executable)
      || registry.purposes[0];
    if (preferred) select.value = preferred.purpose;
    renderConnections(out.connections);
    renderTemplates();
    onPurposeChange();
  } catch (error) {
    select.innerHTML = "";
    document.getElementById("templates").textContent =
      `설계 목적을 불러오지 못했습니다: ${errorText(error)}`;
    document.getElementById("purposeNote").textContent =
      `모델 목록을 가져오지 못했습니다: ${errorText(error)}`;
    renderStages(document.getElementById("stages"), null);
  }
}

// 템플릿 카드. 드롭다운을 카드로 바꾼 이유는, 목적마다 무엇이 돌고 무엇이
// 검증됐는지가 선택 시점에 보여야 하기 때문이다.
function renderTemplates() {
  const host = document.getElementById("templates");
  const select = document.getElementById("purpose");
  host.innerHTML = "";
  if (!registry.purposes.length) {
    host.textContent = "설계 목적을 불러오지 못했습니다.";
    return;
  }
  for (const route of registry.purposes) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "card" + (route.purpose === select.value ? " is-active" : "");
    card.dataset.purpose = route.purpose;

    card.appendChild(el("span", "cardtitle", route.display_name_ko));

    const marks = document.createElement("span");
    marks.className = "cardmarks";
    if (!route.executable) {
      marks.appendChild(mark("실행 불가", "bad", "고르면 왜 실행할 수 없는지 아래에 나옵니다."));
    } else if (!route.validated) {
      marks.appendChild(mark("미검증", "warn",
        `검증되지 않은 단계: ${(route.unvalidated_stages || []).join(", ")}`));
    } else {
      marks.appendChild(mark("검증됨", "ok", "이 경로의 모든 단계가 측정되었습니다."));
    }
    card.appendChild(marks);

    card.addEventListener("click", () => {
      select.value = route.purpose;
      onPurposeChange();
      renderTemplates();
    });
    host.appendChild(card);
  }
}

function mark(text, kind, title) {
  const node = document.createElement("span");
  node.className = `mark mark-${kind}`;
  node.textContent = text;
  if (title) node.title = title;
  return node;
}

function renderConnections(connections) {
  const host = document.getElementById("connections");
  host.innerHTML = "";
  if (!connections) return;

  const bop = connections.bop_workers || {};
  const bopRow = el("div", "skill");
  const reach = bop.reachable == null ? "미확인" : `${bop.reachable}/${bop.declared} 도달`;
  bopRow.append(dot(bop.reachable != null),
                el("span", "", `BOP 워커 ${bop.declared ?? "?"}`),
                el("span", "chip", reach));
  bopRow.title = bop.note || "";
  host.appendChild(bopRow);

  const portal = connections.portal_mcp || {};
  const portalRow = el("div", "skill");
  const state = portal.configured ? "설정됨" : `미설정 (${(portal.missing || []).join(", ")})`;
  portalRow.append(dot(portal.configured), el("span", "", "포털 MCP"), el("span", "chip", state));
  portalRow.title = [portal.still_blocked_note,
                     portal.would_unlock && portal.would_unlock.length
                       ? `열리는 모델: ${portal.would_unlock.join(", ")}` : ""]
    .filter(Boolean).join("\n");
  host.appendChild(portalRow);

  if (!portal.configured) {
    host.appendChild(el("p", "note",
      `${portal.url_env} / ${portal.token_env} 를 설정하면 ` +
      `${(portal.would_unlock || []).length}개 모델에 닿습니다.`));
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
  renderCostBar(document.getElementById("costBar"), route);
  if (!route) { note.textContent = ""; return; }
  // 실행 가능 여부와 검증 여부는 목적 카드의 배지가 말한다. 여기서는 그 경로가
  // 무엇인지와, 배지로 담기지 않는 단서만 적는다.
  // 설명·안내·주의를 한 덩어리로 쏟으면 좌측이 글 벽이 된다. 요약만 보이고
  // 전문은 펼쳐서 본다.
  note.replaceChildren();
  if (route.description) note.appendChild(el("span", "", route.description));
  const extra = [route.referral, route.caveat, route.blocked_reason].filter(Boolean).join("\n\n");
  if (extra) {
    const more = document.createElement("details");
    more.className = "evidence";
    more.appendChild(el("summary", "", route.executable ? "이 경로에 대한 주의" : "왜 실행할 수 없나"));
    more.appendChild(el("p", "rationale", extra));
    note.appendChild(more);
  }
  document.getElementById("planBtn").disabled = false;
}

function renderWeights(host) {
  host.replaceChildren();
  // 목표 일곱 개를 늘 펼쳐두면 좌측이 슬라이더 벽이 되고, 그중 넷은 대개 0 이다.
  const active = OBJECTIVES.filter((item) => item.value > 0);
  const rest = OBJECTIVES.filter((item) => item.value <= 0);
  const more = document.createElement("details");
  more.className = "evidence";
  more.appendChild(el("summary", "", `다른 목표 ${rest.length}개`));
  for (const item of active) host.appendChild(weightRow(item));
  for (const item of rest) more.appendChild(weightRow(item));
  if (rest.length) host.appendChild(more);
}

function weightRow(item) {
  {
    const row = document.createElement("label");
    row.htmlFor = `w_${item.key}`;
    const slider = document.createElement("input");
    slider.id = `w_${item.key}`;
    slider.type = "range";
    slider.min = "0";
    slider.max = "1";
    slider.step = "0.05";
    slider.value = String(item.value);
    slider.dataset.key = item.key;
    const out = el("output", "", item.value.toFixed(2));
    row.append(document.createTextNode(`${item.label} `), slider, out);
    slider.addEventListener("input", () => { out.textContent = Number(slider.value).toFixed(2); });
    return row;
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
    text.textContent = `설명을 가져오지 못했습니다: ${errorText(error)}`;
    badge.textContent = "실패";
    host.innerHTML = "";
    box.classList.remove("hidden");
  }
}

const state = { plan: null, edits: {}, overrides: null, chat: [], llm: {} };

// --- 계획 대화 --------------------------------------------------------------
//
// LLM 은 제안만 한다. 적용은 승인 단계의 apply_edits 를 지나가고 거기서 고정
// 필드가 거부된다. 대화가 그 규칙을 우회하면, 근거 없는 결정을 만들 수 없다는
// 이 저장소의 규칙이 대화 한 번으로 무너진다.

function appendChat(role, text, generated) {
  const log = document.getElementById("chatLog");
  log.classList.remove("empty");
  const node = el("div", `msg msg-${role}`);
  node.appendChild(el("span", "who", role === "user" ? "나" : "도우미"));
  node.appendChild(el("p", "", text));
  if (role === "assistant") {
    node.appendChild(el("span", "src",
      generated ? "LLM 이 생성한 설명입니다. 근거가 아닙니다." : "LLM 미설정 · 계획 요약"));
  }
  log.appendChild(node);
  log.scrollTop = log.scrollHeight;
}

function renderProposals(applicable, rejected) {
  const host = document.getElementById("proposals");
  host.replaceChildren();
  for (const [field, value] of Object.entries(applicable || {})) {
    const row = el("div", "proposal");
    row.append(el("span", "name", field), el("span", "chip", String(value)));
    const apply = document.createElement("button");
    apply.type = "button";
    apply.className = "ghost";
    apply.textContent = "이 수정 적용";
    apply.addEventListener("click", () => {
      state.edits[field] = value;
      const input = [...document.querySelectorAll("#decisions .decision")]
        .map((box) => box.querySelector(".name"))
        .find((name) => name && name.textContent === field);
      if (input) input.closest(".decision").querySelector("input").value = String(value);
      row.replaceChildren(el("span", "name", field),
                          el("span", "chip", `${value} 적용됨`));
    });
    row.appendChild(apply);
    host.appendChild(row);
  }
  for (const [field, info] of Object.entries(rejected || {})) {
    const row = el("div", "proposal is-rejected");
    row.append(el("span", "name", field),
               el("span", "chip", String(info.value)),
               el("span", "src", `거부됨 — ${info.reason}`));
    host.appendChild(row);
  }
}

async function sendChat(question) {
  if (!state.plan) {
    appendChat("assistant", "먼저 계획을 생성하세요.", false);
    return;
  }
  state.chat.push({ role: "user", content: question });
  appendChat("user", question, false);
  const input = document.getElementById("chatInput");
  const button = document.getElementById("chatSend");
  input.disabled = button.disabled = true;
  try {
    const out = await callTool("pipeline.discuss_plan", {
      plan: state.plan, messages: state.chat,
      ...(state.llm.provider ? {
        provider: state.llm.provider, model: state.llm.model, api_key: state.llm.key,
      } : {}),
    });
    if (out && out.error) throw new Error(out.error);
    state.chat.push({ role: "assistant", content: out.reply || "" });
    appendChat("assistant", out.reply || "", out.reply_is_generated);
    if (out.parse_warning) appendChat("assistant", out.parse_warning, false);
    renderProposals(out.applicable_edits, out.rejected_edits);
  } catch (error) {
    appendChat("assistant", `답변하지 못했습니다: ${errorText(error)}`, false);
  } finally {
    input.disabled = button.disabled = false;
    input.value = "";
    input.focus();
  }
}

async function loadLlmModels() {
  const provider = document.getElementById("llmProvider").value;
  const key = document.getElementById("llmKey").value.trim();
  const select = document.getElementById("llmModel");
  const summary = document.getElementById("llmSummary");
  if (!provider) {
    state.llm = {};
    summary.textContent = "LLM: 서버 연결";
    select.replaceChildren(new Option("서버에 연결된 것 사용", ""));
    return;
  }
  if (!key) {
    summary.textContent = "LLM: API 키가 필요합니다";
    return;
  }
  try {
    const out = await callTool("chat.list_models", { provider, api_key: key });
    if (out && out.error) throw new Error(out.error.message || out.error);
    select.replaceChildren();
    for (const model of out.models || []) {
      const id = typeof model === "string" ? model : String(model.id || model.name || "");
      if (id) select.appendChild(new Option(id, id));
    }
    state.llm = { provider, key, model: select.value };
    summary.textContent = `LLM: ${provider} · ${select.value || "모델 미선택"}`;
  } catch (error) {
    summary.textContent = `LLM: 모델을 불러오지 못했습니다 (${errorText(error)})`;
  }
}

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
    showStep(3);
    document.getElementById("discuss").hidden = false;
    state.chat = [];
    const log = document.getElementById("chatLog");
    log.replaceChildren();
    log.classList.add("empty");
    log.textContent = "계획에 대해 궁금한 것을 물어보세요.";
    document.getElementById("proposals").replaceChildren();
    if (plan.route) renderStages(document.getElementById("stages"), plan.route);
    status.className = "status";
    status.textContent = "";
  } catch (error) {
    status.className = "status bad";
    status.textContent = `실패: ${errorText(error)}`;
    document.getElementById("reviewState").textContent = "계획 생성 실패";
    // 401 은 설정 문제가 아니라 로그인 문제다. 무엇을 해야 하는지 알려준다.
    if (/unauthorized|401/i.test(errorText(error))) {
      document.getElementById("authHint").classList.remove("hidden");
      setSignedOut("세션이 만료되었습니다. 다시 로그인하세요.");
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
    state.overrides = result.request_overrides || {};
    document.getElementById("runBtn").disabled = false;
    const approveState = document.getElementById("approveState");
    approveState.textContent = "승인됨";
    approveState.classList.add("ready");
  } catch (error) {
    out.classList.remove("empty");
    out.textContent = `실패: ${errorText(error)}`;
  }
}

export { currentRoute, loadRegistry, onPurposeChange, renderWeights, renderStages, state, generatePlan, approve, sendChat, loadLlmModels, collectObjective, decisionNode, evidenceNode, formatSeconds, stageRow, el, dot, renderConnections };
