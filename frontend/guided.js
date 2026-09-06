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
    renderConnections(out.connections);
    renderTemplates();
    onPurposeChange();
  } catch (error) {
    select.innerHTML = "";
    document.getElementById("templates").textContent =
      `설계 목적을 불러오지 못했습니다: ${error.message}`;
    document.getElementById("purposeNote").textContent =
      `모델 목록을 가져오지 못했습니다: ${error.message}`;
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
      marks.appendChild(mark("실행 불가", "bad", route.blocked_reason));
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

// --- 모니터 / 분석 --------------------------------------------------------
//
// 기존 RAPID 화면이 쓰는 도구를 그대로 쓴다. 여기서 별도의 요약을 만들면 같은
// 사실이 두 곳에서 갈라지고, 어느 쪽이 맞는지 판단할 근거가 없어진다.

const runState = { runId: "", artifacts: [] };

//: 3D 로 그릴 수 있는 형식. 그 외에는 텍스트로 보여준다 - 뷰어에 아무 파일이나
//: 넣으면 빈 캔버스가 나오고, 사용자는 파일이 비었다고 생각한다.
const STRUCTURE_FORMATS = { pdb: "pdb", cif: "cif", mmcif: "cif", ent: "pdb", sdf: "sdf" };

function formatBytes(size) {
  if (size == null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function isStructureArtifact(path) {
  const ext = String(path || "").toLowerCase().split(".").pop();
  return Object.prototype.hasOwnProperty.call(STRUCTURE_FORMATS, ext) ? STRUCTURE_FORMATS[ext] : "";
}

async function loadRuns() {
  const select = document.getElementById("runSelect");
  const button = document.getElementById("runRefreshBtn");
  button.disabled = true;
  try {
    const out = await callTool("pipeline.list_runs", { limit: 30 });
    if (out && out.error) throw new Error(out.error);
    const runs = out.runs || out.items || [];
    select.innerHTML = "";
    if (!runs.length) {
      select.replaceChildren(new Option("실행이 없습니다", ""));
      setRunStatus("실행이 없습니다.");
      return;
    }
    select.appendChild(new Option("실행을 고르세요", ""));
    for (const run of runs) {
      // list_runs 는 문자열 목록을 돌려준다. 객체로 오는 배포본도 있어 둘 다 받는다.
      const id = typeof run === "string" ? run : String(run.run_id || run.id || "");
      if (!id) continue;
      const stage = typeof run === "object" ? run.stage : "";
      select.appendChild(new Option(stage ? `${id} · ${stage}` : id, id));
    }
  } catch (error) {
    select.replaceChildren(new Option("불러오지 못했습니다", ""));
    setRunStatus(`실행 목록을 불러오지 못했습니다: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function setRunStatus(text) {
  const host = document.getElementById("runStatus");
  host.classList.add("empty");
  host.textContent = text;
}

async function loadRunStatus(runId) {
  const host = document.getElementById("runStatus");
  runState.runId = runId;
  if (!runId) {
    setRunStatus("실행을 고르면 상태가 표시됩니다.");
    return;
  }
  host.classList.add("empty");
  host.textContent = "불러오는 중…";
  try {
    const out = await callTool("pipeline.status", { run_id: runId });
    if (out && out.error) throw new Error(out.error);
    if (out.found === false) {
      setRunStatus(`${runId} 의 상태 파일이 없습니다.`);
      return;
    }
    // 실제 값은 status 안에 들어 있다. 최상위에서 읽으면 전부 "-" 가 된다.
    const info = (out && typeof out.status === "object" && out.status) || out;
    host.classList.remove("empty");
    host.replaceChildren();
    const rows = [
      ["실행", runId],
      ["단계", info.stage || "-"],
      ["상태", info.state || "-"],
      ["갱신", info.updated_at || "-"],
    ];
    for (const [label, value] of rows) {
      const row = el("div", "skill");
      row.append(el("span", "", label), el("span", "chip", value));
      host.appendChild(row);
    }
    if (info.error_summary) {
      const warn = document.createElement("div");
      warn.className = "warn";
      warn.textContent = String(info.error_summary);
      host.appendChild(warn);
    }
    await loadArtifacts(runId);
    showPanel("artifacts");
  } catch (error) {
    setRunStatus(`상태를 불러오지 못했습니다: ${error.message}`);
  }
}

async function loadArtifacts(runId) {
  const host = document.getElementById("artifactList");
  host.classList.add("empty");
  host.textContent = "불러오는 중…";
  document.getElementById("artifactPreview").innerHTML = "";
  try {
    // 서버 기본값은 max_depth 4 다. app.js 는 6 을 쓰고, 기본값에 기대면 깊은
    // 산출물이 조용히 빠진다.
    const out = await callTool("pipeline.list_artifacts", {
      run_id: runId, max_depth: 6, limit: 400,
    });
    if (out && out.error) throw new Error(out.error);
    const items = out.artifacts || out.items || [];
    runState.artifacts = items;
    host.innerHTML = "";
    if (!items.length) {
      host.classList.add("empty");
      host.textContent = "이 실행에는 산출물이 없습니다.";
      return;
    }
    host.classList.remove("empty");
    // list_artifacts 는 파일과 디렉터리를 함께 돌려준다. msa 와 tiers 는
    // 디렉터리이고, 그것을 read_artifact 에 넘기면 실패한다. 디렉터리는 읽는
    // 대상이 아니라 그 아래를 묶는 제목으로 쓴다.
    const files = items.filter((item) => String(item.type || "file") !== "directory");
    if (!files.length) {
      host.classList.add("empty");
      host.textContent = "이 실행에는 읽을 수 있는 파일이 없습니다.";
      return;
    }
    const groups = new Map();
    for (const item of files) {
      const path = String(item.path || item.name || item);
      const slash = path.lastIndexOf("/");
      const folder = slash < 0 ? "" : path.slice(0, slash);
      if (!groups.has(folder)) groups.set(folder, []);
      groups.get(folder).push({ item, path, name: slash < 0 ? path : path.slice(slash + 1) });
    }
    for (const folder of [...groups.keys()].sort()) {
      if (folder) host.appendChild(el("div", "afolder", folder));
      for (const { item, path, name } of groups.get(folder)) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "artifact";
        const format = isStructureArtifact(path);
        row.title = path;
        row.append(
          el("span", "apath", name),
          el("span", "chip", format ? "3D" : formatBytes(item.size)),
        );
        row.addEventListener("click", () => openArtifact(runId, path, format));
        host.appendChild(row);
      }
    }
  } catch (error) {
    host.classList.add("empty");
    host.textContent = `산출물을 불러오지 못했습니다: ${error.message}`;
  }
}

async function openArtifact(runId, path, format) {
  const preview = document.getElementById("artifactPreview");
  preview.innerHTML = "불러오는 중…";
  try {
    const out = await callTool("pipeline.read_artifact", {
      run_id: runId, path, max_bytes: format ? 4000000 : 200000,
    });
    if (out && out.error) throw new Error(out.error);
    const text = out.text != null ? String(out.text) : "";
    preview.innerHTML = "";

    const head = document.createElement("div");
    head.className = "previewhead";
    head.textContent = path;
    preview.appendChild(head);

    // read_artifact 는 max_bytes 로 자른다. 잘렸다고 말하지 않으면 사용자는
    // 파일이 그게 전부인 줄 안다.
    if (out.truncated) {
      const warn = document.createElement("div");
      warn.className = "warn";
      warn.textContent = "내용이 잘렸습니다. 전체는 기존 화면에서 내려받으세요.";
      preview.appendChild(warn);
    }

    if (format && text) {
      render3d(text, format, preview);
    } else {
      const pre = document.createElement("pre");
      pre.className = "artifacttext";
      pre.textContent = text || "(빈 파일)";
      preview.appendChild(pre);
    }
  } catch (error) {
    preview.textContent = `산출물을 읽지 못했습니다: ${error.message}`;
  }
}

function render3d(text, format, host) {
  if (!window.$3Dmol) {
    const note = document.createElement("div");
    note.className = "warn";
    note.textContent = "3D 뷰어를 불러오지 못했습니다.";
    host.appendChild(note);
    return;
  }
  const container = document.createElement("div");
  container.className = "viewer3d";
  host.appendChild(container);
  const viewer = window.$3Dmol.createViewer(container, { backgroundColor: "#0f141c" });
  viewer.addModel(text, format);
  if (format === "sdf") {
    viewer.setStyle({}, { stick: { radius: 0.15 } });
  } else {
    viewer.setStyle({}, { cartoon: { color: "spectrum" } });
  }
  viewer.zoomTo();
  viewer.render();
}

async function probeWorkers() {
  const host = document.getElementById("monitorList");
  const button = document.getElementById("probeBtn");
  button.disabled = true;
  host.classList.remove("empty");
  host.textContent = "확인 중…";
  try {
    const out = await callTool("pipeline.list_models", { check_liveness: true });
    if (out && out.error) throw new Error(out.error);
    host.innerHTML = "";
    const entries = Object.entries(out.liveness || {});
    for (const [id, info] of entries.sort((a, b) => a[0].localeCompare(b[0]))) {
      const row = el("div", "skill");
      row.title = info.error || `선언: ${info.declared_availability}`;
      row.append(dot(info.reachable), el("span", "", id), el("span", "chip", info.endpoint));
      host.appendChild(row);
    }
    renderConnections(out.connections);
    if (!entries.length) {
      host.classList.add("empty");
      host.textContent = "확인할 엔드포인트가 없습니다.";
    }
  } catch (error) {
    host.classList.add("empty");
    host.textContent = `확인하지 못했습니다: ${error.message}`;
  } finally {
    button.disabled = false;
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
  if (typeof showStep === "function" && registry.loaded) showStep(2);
  if (!route) { note.textContent = ""; return; }
  // 실행 가능 여부와 검증 여부는 목적 카드의 배지가 말한다. 여기서는 그 경로가
  // 무엇인지와, 배지로 담기지 않는 단서만 적는다.
  const lines = [route.description || "", route.referral || "", route.caveat || ""];
  note.textContent = lines.filter(Boolean).join(" ");
  document.getElementById("planBtn").disabled = false;
}

function renderWeights(host) {
  host.innerHTML = "";
  for (const item of OBJECTIVES) {
    const row = document.createElement("label");
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0";
    slider.max = "1";
    slider.step = "0.05";
    slider.value = String(item.value);
    slider.dataset.key = item.key;
    const out = el("output", "", item.value.toFixed(2));
    row.append(document.createTextNode(`${item.label} `), slider, out);
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

// 한 번에 한 단계만 보여준다. 네 단계를 세로로 이어붙이면 아래로 계속 읽어야
// 하고, 지금 어디에 있는지도 알기 어렵다.
function showStep(step) {
  for (const node of document.querySelectorAll(".step")) {
    node.classList.toggle("hidden", node.dataset.step !== String(step));
  }
  for (const button of document.querySelectorAll(".stepbtn")) {
    const active = button.dataset.step === String(step);
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-current", active ? "step" : "false");
  }
}

function showPanel(name) {
  for (const node of document.querySelectorAll(".panel[data-panelfor]")) {
    node.classList.toggle("hidden", node.dataset.panelfor !== name);
  }
  for (const tab of document.querySelectorAll(".tab")) {
    const active = tab.dataset.panel === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  }
}

for (const button of document.querySelectorAll(".stepbtn")) {
  button.addEventListener("click", () => showStep(button.dataset.step));
}
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => showPanel(tab.dataset.panel));
}

document.getElementById("probeBtn").addEventListener("click", probeWorkers);
document.getElementById("runRefreshBtn").addEventListener("click", loadRuns);
document.getElementById("runSelect").addEventListener("change", (event) => {
  loadRunStatus(event.target.value);
});
loadRuns();
document.getElementById("planBtn").addEventListener("click", generatePlan);
document.getElementById("approveBtn").addEventListener("click", approve);

export { collectObjective, decisionNode, evidenceNode, formatSeconds, stageRow };
