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

// --- 세션 -----------------------------------------------------------------
//
// 이 화면만으로 쓸 수 있어야 하므로 로그인을 여기서 한다. 토큰 키는 기존 앱과
// 같은 "kbf.token" 이다 - 다른 키를 쓰면 두 화면이 서로의 세션을 모른다.

function setSignedIn(user) {
  document.getElementById("loginGate").classList.add("hidden");
  document.getElementById("workspace").classList.remove("hidden");
  document.getElementById("whoami").textContent = user || "";
}

function setSignedOut(message) {
  document.getElementById("loginGate").classList.remove("hidden");
  document.getElementById("workspace").classList.add("hidden");
  if (message) document.getElementById("loginError").textContent = message;
}

async function signIn(username, password) {
  const res = await fetch(`${apiBase()}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const payload = await res.json().catch(() => null);
  if (!res.ok || !payload || !payload.ok) {
    throw new Error((payload && payload.error) || `로그인 실패 (HTTP ${res.status})`);
  }
  localStorage.setItem("kbf.token", payload.token || "");
  if (payload.user) localStorage.setItem("kbf.user", JSON.stringify(payload.user));
  return payload.user;
}

function signOut() {
  localStorage.removeItem("kbf.token");
  localStorage.removeItem("kbf.user");
  setSignedOut("");
}

function storedUserName() {
  try {
    const raw = JSON.parse(localStorage.getItem("kbf.user") || "null");
    return raw ? String(raw.username || raw.name || raw.id || "") : "";
  } catch {
    return "";
  }
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

// --- 모니터 / 분석 --------------------------------------------------------
//
// 기존 RAPID 화면이 쓰는 도구를 그대로 쓴다. 여기서 별도의 요약을 만들면 같은
// 사실이 두 곳에서 갈라지고, 어느 쪽이 맞는지 판단할 근거가 없어진다.

const runState = { runId: "", artifacts: [] };

//: 3D 로 그릴 수 있는 형식. 그 외에는 텍스트로 보여준다 - 뷰어에 아무 파일이나
//: 넣으면 빈 캔버스가 나오고, 사용자는 파일이 비었다고 생각한다.
const STRUCTURE_FORMATS = { pdb: "pdb", cif: "cif", mmcif: "cif", ent: "pdb", sdf: "sdf" };

// 던져진 것이 Error 가 아닐 수 있다. 메시지가 없으면 그 사실을 말한다.
function errorText(error) {
  if (!error) return "알 수 없는 오류";
  if (typeof error === "string") return error;
  return (error && error.message) || String(error) || "알 수 없는 오류";
}

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
    setRunStatus(`실행 목록을 불러오지 못했습니다: ${errorText(error)}`);
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
    // 상태와 산출물은 별개다. status.json 이 없는 실행에도 결과 파일은 있다
    // (예: test_relax_out 은 상태 파일 없이 .pdb 를 갖고 있다).
    if (out.found === false) {
      setRunStatus(`${runId}: 상태 파일이 없습니다. 산출물은 아래에서 볼 수 있습니다.`);
      await loadArtifacts(runId);
      showPanel("artifacts");
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
    setRunStatus(`상태를 불러오지 못했습니다: ${errorText(error)}`);
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
    // 서버는 디렉터리를 type "dir" 로 준다. 이름을 짐작해 제외하는 대신 파일만
    // 허용한다 - 새 type 이 생겨도 읽을 수 없는 것을 누르게 되지 않는다.
    const files = items.filter((item) => String(item.type || "file") === "file");
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
    host.textContent = `산출물을 불러오지 못했습니다: ${errorText(error)}`;
  }
}

async function openArtifact(runId, path, format, maxBytes) {
  const preview = document.getElementById("artifactPreview");
  preview.replaceChildren(el("div", "empty", "불러오는 중…"));
  const cap = maxBytes || (format ? 4000000 : 200000);
  try {
    const out = await callTool("pipeline.read_artifact", {
      run_id: runId, path, max_bytes: cap,
    });
    if (out && out.error) throw new Error(out.error);
    const text = out.text != null ? String(out.text) : "";
    preview.replaceChildren();

    const head = el("div", "previewhead");
    head.appendChild(el("span", "", path));
    if (format) {
      // 이 화면에서 가장 볼 만한 것이 340px 레일에 갇혀 있을 이유가 없다.
      const zoom = document.createElement("button");
      zoom.type = "button";
      zoom.className = "ghost";
      zoom.textContent = "크게 보기";
      zoom.addEventListener("click", () => openStage(path, text, format));
      head.appendChild(zoom);
    }
    preview.appendChild(head);

    // read_artifact 는 max_bytes 로 자른다. 잘렸다고만 말하고 끝내면 막다른 길이다. 이 화면 안에서 이어 읽게 한다.
    if (out.truncated) {
      const warn = el("div", "warn", `내용이 잘렸습니다 (${formatBytes(cap)}까지). `);
      const more = document.createElement("button");
      more.type = "button";
      more.className = "ghost";
      more.textContent = "두 배로 더 읽기";
      more.addEventListener("click", () => openArtifact(runId, path, format, cap * 2));
      warn.appendChild(more);
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
    // "undefined" 로 끝나는 오류 메시지는 아무것도 알려주지 않는다.
    preview.replaceChildren(el("div", "warn",
      `산출물을 읽지 못했습니다: ${errorText(error)}`));
  }
}

// 3D 는 WebGL 을 쓴다. 원격 데스크톱이나 GPU 차단 목록에 걸린 브라우저에서는
// 컨텍스트 생성 자체가 실패한다. 그때 파일을 못 여는 것이 아니라 그리지만
// 못 하는 것이므로, 내용은 텍스트로라도 보여준다.
// 구조를 화면 가득 띄운다. 레일 안의 작은 뷰포트로는 접힘을 읽을 수 없다.
function openStage(path, text, format) {
  const stage = document.getElementById("stage");
  const body = document.getElementById("stageBody");
  document.getElementById("stageTitle").textContent = path;
  body.replaceChildren();
  stage.classList.remove("hidden");
  render3d(text, format, body, "viewer3d viewer3d-lg");
  stage.querySelector(".stageclose").focus();
}

function closeStage() {
  document.getElementById("stage").classList.add("hidden");
  document.getElementById("stageBody").replaceChildren();
}

function render3d(text, format, host, viewerClass) {
  const fallback = (reason) => {
    host.appendChild(el("div", "warn", `${reason} 대신 원문을 표시합니다.`));
    host.appendChild(el("pre", "artifacttext", text));
  };
  if (!window.$3Dmol) {
    fallback("3D 뷰어를 불러오지 못했습니다.");
    return;
  }
  const container = el("div", viewerClass || "viewer3d");
  host.appendChild(container);
  try {
    const viewer = window.$3Dmol.createViewer(container, { backgroundColor: "#12161d" });
    viewer.addModel(text, format);
    viewer.setStyle({}, format === "sdf"
      ? { stick: { radius: 0.15 } }
      : { cartoon: { color: "spectrum" } });
    viewer.zoomTo();
    viewer.render();
  } catch (error) {
    container.remove();
    fallback(`3D 를 그릴 수 없습니다 (${errorText(error)}).`);
  }
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
    host.textContent = `확인하지 못했습니다: ${errorText(error)}`;
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
  renderCostBar(document.getElementById("costBar"), route);
  if (typeof showStep === "function" && registry.loaded) showStep(2);
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

// --- 타겟 파일 --------------------------------------------------------------
//
// FASTA 는 헤더를 빼고 서열만, PDB/mmCIF 는 CA 잔기에서 서열을 읽는다. 붙여넣기
// 만 지원하면 사용자는 매번 다른 도구로 변환해 와야 한다.

const THREE_TO_ONE = {
  ALA:"A", ARG:"R", ASN:"N", ASP:"D", CYS:"C", GLN:"Q", GLU:"E", GLY:"G",
  HIS:"H", ILE:"I", LEU:"L", LYS:"K", MET:"M", PHE:"F", PRO:"P", SER:"S",
  THR:"T", TRP:"W", TYR:"Y", VAL:"V", MSE:"M",
};

function sequenceFromFasta(text) {
  const lines = text.split(/\r?\n/);
  const records = [];
  let current = null;
  for (const line of lines) {
    if (line.startsWith(">")) {
      current = { name: line.slice(1).trim(), seq: "" };
      records.push(current);
    } else if (current) {
      current.seq += line.trim();
    }
  }
  if (!records.length) {
    // 헤더가 없으면 파일 전체를 서열로 본다.
    return { seq: text.replace(/[^A-Za-z]/g, ""), name: "", count: 1 };
  }
  return { seq: records[0].seq.replace(/[^A-Za-z]/g, ""), name: records[0].name,
           count: records.length };
}

function sequenceFromStructure(text) {
  // ATOM 의 CA 만 읽는다. HETATM 의 CA 는 알파탄소가 아니라 칼슘이거나 리간드
  // 원자일 수 있다 - 구조 지표에서 같은 함정을 이미 겪었다.
  const seen = new Set();
  let seq = "";
  let chain = "";
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith("ATOM")) continue;
    if (line.slice(12, 16).trim() !== "CA") continue;
    const ch = line[21];
    if (!chain) chain = ch;
    if (ch !== chain) break;          // 첫 사슬만 쓴다
    const key = line.slice(21, 27);
    if (seen.has(key)) continue;
    seen.add(key);
    seq += THREE_TO_ONE[line.slice(17, 20).trim().toUpperCase()] || "X";
  }
  return { seq, name: chain ? `chain ${chain}` : "", count: 1 };
}

async function loadTargetFile(file) {
  const note = document.getElementById("targetNote");
  const text = await file.text();
  const isStructure = /\.(pdb|ent|cif|mmcif)$/i.test(file.name)
    || /^(ATOM|HEADER|data_)/m.test(text);
  const parsed = isStructure ? sequenceFromStructure(text) : sequenceFromFasta(text);
  if (!parsed.seq) {
    note.textContent = `${file.name} 에서 서열을 찾지 못했습니다.`;
    return;
  }
  if (/X/.test(parsed.seq)) {
    note.textContent = `${file.name}: 표준 아미노산이 아닌 잔기를 X 로 두었습니다. 확인하세요.`;
  } else {
    note.textContent = `${file.name}${parsed.name ? ` · ${parsed.name}` : ""} · ${parsed.seq.length} aa`
      + (parsed.count > 1 ? ` · 서열 ${parsed.count}개 중 첫 번째만 사용` : "");
  }
  document.getElementById("targetFasta").value = parsed.seq;
}

function targetFasta() {
  return document.getElementById("targetFasta").value.trim();
}

async function startRun() {
  const note = document.getElementById("runNote");
  const button = document.getElementById("runBtn");
  const fasta = targetFasta();
  if (!fasta) {
    note.textContent = "타겟 서열을 입력해야 실행할 수 있습니다.";
    return;
  }
  // 실행은 되돌릴 수 없다. 무엇이 시작되는지 먼저 말하고 확인을 받는다.
  const route = currentRoute();
  const summary = route ? route.display_name_ko : "선택한 경로";
  if (!window.confirm(`${summary} 경로로 실행을 시작합니다. 계속할까요?`)) return;

  button.disabled = true;
  note.textContent = "실행을 시작하는 중…";
  try {
    const out = await callTool("pipeline.run", {
      target_fasta: fasta,
      ...(state.overrides || {}),
    });
    if (out && out.error) throw new Error(out.error);
    const runId = String(out.run_id || out.id || "");
    note.textContent = runId ? `실행 ${runId} 를 시작했습니다.` : "실행을 시작했습니다.";
    if (runId) {
      await loadRuns();
      document.getElementById("runSelect").value = runId;
      await loadRunStatus(runId);
      showPanel("runs");
    }
  } catch (error) {
    note.textContent = `실행하지 못했습니다: ${errorText(error)}`;
  } finally {
    button.disabled = false;
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

// --- 화면 비율 -------------------------------------------------------------
//
// 세 열의 폭을 드래그로 바꾸고 그 값을 기억한다. 3D 결과를 볼 때와 계획을 읽을
// 때 필요한 폭이 다른데, 고정 폭이면 둘 중 하나는 늘 좁다.

const PANE_KEY = "kbf.guided.panes";
const PANE_MIN = 200;
const PANE_DEFAULT = { left: 264, right: 340 };

function readPanes() {
  try {
    const saved = JSON.parse(localStorage.getItem(PANE_KEY) || "null");
    if (saved && Number(saved.left) > 0 && Number(saved.right) > 0) return saved;
  } catch { /* 저장값이 깨졌으면 기본값을 쓴다 */ }
  return { ...PANE_DEFAULT };
}

function applyPanes(panes) {
  document.querySelector(".layout").style.gridTemplateColumns =
    `${panes.left}px 6px minmax(0, 1fr) 6px ${panes.right}px`;
}

function initSplitters() {
  const layout = document.querySelector(".layout");
  const panes = readPanes();
  applyPanes(panes);

  const clamp = (value) => Math.max(PANE_MIN, Math.min(value, layout.clientWidth - PANE_MIN * 2));

  for (const handle of document.querySelectorAll(".splitter")) {
    const side = handle.dataset.splitter;

    const drag = (event) => {
      const rect = layout.getBoundingClientRect();
      panes[side] = clamp(side === "left" ? event.clientX - rect.left : rect.right - event.clientX);
      applyPanes(panes);
    };
    const stop = () => {
      document.removeEventListener("pointermove", drag);
      document.removeEventListener("pointerup", stop);
      document.body.classList.remove("dragging");
      localStorage.setItem(PANE_KEY, JSON.stringify(panes));
    };
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      document.body.classList.add("dragging");
      document.addEventListener("pointermove", drag);
      document.addEventListener("pointerup", stop);
    });
    // 드래그는 키보드로 못 한다. 방향키로 같은 일을 할 수 있어야 한다.
    handle.addEventListener("keydown", (event) => {
      const step = event.shiftKey ? 40 : 12;
      if (event.key === "ArrowLeft") panes[side] = clamp(panes[side] + (side === "right" ? step : -step));
      else if (event.key === "ArrowRight") panes[side] = clamp(panes[side] + (side === "right" ? -step : step));
      else if (event.key !== "Home") return;
      if (event.key === "Home") panes[side] = PANE_DEFAULT[side];
      event.preventDefault();
      applyPanes(panes);
      localStorage.setItem(PANE_KEY, JSON.stringify(panes));
    });
  }
}

function boot() {
  loadRegistry();
  loadRuns();
}

initSplitters();
renderWeights(document.getElementById("weights"));
renderStages(document.getElementById("stages"), null);
document.getElementById("purpose").addEventListener("change", onPurposeChange);
for (const id of ["nDesigns", "lengthAa"]) {
  document.getElementById(id).addEventListener("change", loadRegistry);
}

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

document.getElementById("stageClose").addEventListener("click", closeStage);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeStage();
});
document.getElementById("probeBtn").addEventListener("click", probeWorkers);
document.getElementById("runRefreshBtn").addEventListener("click", loadRuns);
document.getElementById("runSelect").addEventListener("change", (event) => {
  loadRunStatus(event.target.value);
});
document.getElementById("planBtn").addEventListener("click", generatePlan);
document.getElementById("approveBtn").addEventListener("click", approve);
document.getElementById("runBtn").addEventListener("click", startRun);
document.getElementById("chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = document.getElementById("chatInput").value.trim();
  if (question) sendChat(question);
});
document.getElementById("llmLoadBtn").addEventListener("click", loadLlmModels);
document.getElementById("llmProvider").addEventListener("change", loadLlmModels);
document.getElementById("llmModel").addEventListener("change", (event) => {
  state.llm.model = event.target.value;
  document.getElementById("llmSummary").textContent =
    `LLM: ${state.llm.provider} · ${event.target.value}`;
});
document.getElementById("targetFileBtn").addEventListener("click", () => {
  document.getElementById("targetFile").click();
});
document.getElementById("targetFile").addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  if (file) loadTargetFile(file).catch((error) => {
    document.getElementById("targetNote").textContent = `파일을 읽지 못했습니다: ${errorText(error)}`;
  });
});
document.getElementById("targetClearBtn").addEventListener("click", () => {
  document.getElementById("targetFasta").value = "";
  document.getElementById("targetFile").value = "";
  document.getElementById("targetNote").textContent = "";
});
document.getElementById("logoutBtn").addEventListener("click", signOut);
document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.getElementById("loginBtn");
  const error = document.getElementById("loginError");
  error.textContent = "";
  button.disabled = true;
  try {
    const user = await signIn(
      document.getElementById("loginUser").value.trim(),
      document.getElementById("loginPass").value,
    );
    setSignedIn((user && (user.username || user.name)) || storedUserName());
    boot();
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
  }
});

if (localStorage.getItem("kbf.token")) {
  setSignedIn(storedUserName());
  boot();
} else {
  setSignedOut("");
}

export { collectObjective, decisionNode, evidenceNode, formatSeconds, stageRow };
