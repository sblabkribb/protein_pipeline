// RAPID 목표 기반 설계 화면.
//
// 이 화면은 결정을 스스로 만들지 않는다. 서버의 pipeline.plan_from_objective 가
// 만든 계획을 그리고, 사람이 고친 값을 되돌려줄 뿐이다. 근거 문구를 프런트에서
// 지어내면 근거 추적이 깨지므로 서버가 준 것만 표시한다.

import { apiBase, callTool, errorText, storedUserName } from "./guided/api.js";
import {
  currentRoute,
  loadRegistry,
  onPurposeChange,
  renderWeights,
  renderStages,
  state,
  generatePlan,
  approve,
  sendChat,
  loadLlmModels,
} from "./guided/plan.js";
import {
  closeStage,
  loadRunStatus,
  loadArtifacts,
  probeWorkers,
  runState,
  setRunStatus,
  startPolling,
  stopPolling,
  cancelRun,
  generateReport,
  getReport,
  renderReport,
  renderRunProgress,
} from "./guided/monitor.js";
import { loadRunList, highlightRun } from "./guided/sidebar.js";
import {
  loadFunnel,
  renderFunnel,
  loadHitList,
  renderHitList,
  loadCompare,
  summarizeCompare,
} from "./guided/results.js";
import { el } from "./guided/dom.js";

// --- 세션 -----------------------------------------------------------------
//
// 이 화면만으로 쓸 수 있어야 하므로 로그인을 여기서 한다. 토큰 키는 기존 앱과
// 같은 "kbf.token" 이다 - 다른 키를 쓰면 두 화면이 서로의 세션을 모른다.

function setSignedIn(user) {
  document.getElementById("loginGate").classList.add("hidden");
  document.getElementById("workspace").classList.remove("hidden");
  document.getElementById("whoami").textContent = user || "";
}

export function setSignedOut(message) {
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

// 재선택 세대 토큰. 두 번 빠르게 누르면 await 사이에 낡은 실행의 상태가 새
// 실행 화면에 그려질 수 있다 - await 뒤에서 세대가 어긋나면 그만둔다.
let selectGen = 0;
async function selectRun(runId) {
  if (!runId) return;
  const gen = ++selectGen;
  stopPolling();
  const status = await loadRunStatus(runId, { isStale: () => gen !== selectGen });
  if (status === "stale") return;   // 낡은 응답은 그리지도, 폴링도 시작하지 않는다
  // Results 탭은 Run 상태 다음에 따로 채운다. 퍼널은 loadRunStatus 가 방금
  // 채운 아티팩트 목록을, 히트리스트는 전용 도구를 쓴다. 재선택되면 낡은 세대
  // 아무것도 그리지 않는다 - 재선택 덧그림은 이미 한 번 막았던 것이다.
  refreshResults(runId, { isStale: () => gen !== selectGen }).catch((error) => {
    if (gen !== selectGen) return;
    document.getElementById("hitList").replaceChildren(
      el("p", "note", `결과를 불러오지 못했습니다: ${errorText(error)}`));
  });
  startPolling(runId, {
    onTick: (info) => {
      if (gen !== selectGen) return;
      // 상태 재조회 없이도 Run 탭이 살아 움직인다. 아티팩트는 상태가 바뀔 때만.
      renderRunProgress(info);
      if (info.state === "done" || info.state === "failed" || info.state === "cancelled") {
        loadArtifacts(runId, { isStale: () => gen !== selectGen });
      }
    },
  });
}

async function refreshResults(runId, { isStale = () => false } = {}) {
  const rows = await loadFunnel(runId, runState.artifacts || []);
  if (isStale()) return;
  renderFunnel(document.getElementById("funnelBox"), rows);
  const hits = await loadHitList(runId);
  if (isStale()) return;
  renderHitList(document.getElementById("hitList"), hits);
}

// 비교 기준 드롭다운은 실행 목록이 바뀔 때마다 다시 채운다. 사용자가 고른 값을
// 최대한 지킨다 - 목록이 갱신돼도 선택이 풀리면 비교를 다시 고르게 된다.
function refreshCompareBaselines(runs) {
  const select = document.getElementById("compareBaseline");
  const current = select.value;
  select.replaceChildren(new Option("비교 기준 실행 선택…", ""));
  for (const run of runs || []) select.appendChild(new Option(run.run_id, run.run_id));
  select.value = current;
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
      refreshCompareBaselines(await loadRunList(selectRun));
      highlightRun(runId);
      await selectRun(runId);
      showPanel("run");
    }
  } catch (error) {
    note.textContent = `실행하지 못했습니다: ${errorText(error)}`;
  } finally {
    button.disabled = false;
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
  loadRunList((runId) => { selectRun(runId); }).then((runs) => {
    refreshCompareBaselines(runs);
  });
}

// 마법사 단계 버튼은 사라졌다. 남은 역할은 하나다 - 계획이 생기기 전까지
// 검토·승인 섹션을 감춰 둔다.
export function showStep() {
  document.getElementById("planSection").classList.remove("hidden");
}

export function showPanel(name) {
  for (const node of document.querySelectorAll(".panel[data-panelfor]")) {
    node.classList.toggle("hidden", node.dataset.panelfor !== name);
  }
  for (const tab of document.querySelectorAll(".tab")) {
    const active = tab.dataset.panel === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  }
}

// facade 는 모듈 최상위에서 DOM 을 만진다 (dom.js 머리글의 함정과 같다). 이
// 모듈은 monitor.js 의 순환 import 를 타고 node 테스트까지 평가되므로, 브라우저
// 밖에서는 배선을 건너뛴다. 함수 선언과 export 는 그대로 남는다.
if (typeof document !== "undefined") {
  initSplitters();
  renderWeights(document.getElementById("weights"));
  renderStages(document.getElementById("stages"), null);
  document.getElementById("purpose").addEventListener("change", onPurposeChange);
  for (const id of ["nDesigns", "lengthAa"]) {
    document.getElementById(id).addEventListener("change", loadRegistry);
  }

  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => showPanel(tab.dataset.panel));
  }

  document.getElementById("stageClose").addEventListener("click", closeStage);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeStage();
  });
  document.getElementById("probeBtn").addEventListener("click", probeWorkers);
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
  document.getElementById("cancelRunBtn").addEventListener("click", async () => {
    const runId = runState.runId;
    if (!runId) return;
    if (!window.confirm(`${runId} 실행을 취소할까요? 시작된 스테이지는 되돌릴 수 없습니다.`)) return;
    try {
      const out = await cancelRun(runId);
      if (out && out.error) throw new Error(out.error);
      await loadRunStatus(runId);
    } catch (error) {
      setRunStatus(`취소하지 못했습니다: ${errorText(error)}`);
    }
  });
  document.getElementById("reportGenBtn").addEventListener("click", async () => {
    const runId = runState.runId;
    if (!runId) return;
    const button = document.getElementById("reportGenBtn");
    button.disabled = true;
    try {
      const gen = await generateReport(runId);
      if (gen && gen.error) throw new Error(gen.error);
      const out = await getReport(runId);
      if (out && out.error) throw new Error(out.error);
      renderReport(document.getElementById("reportView"),
        out.report_ko || out.report || out.markdown || out.text || "");
    } catch (error) {
      setRunStatus(`리포트를 만들지 못했습니다: ${errorText(error)}`);
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("reportLoadBtn").addEventListener("click", async () => {
    const runId = runState.runId;
    if (!runId) return;
    try {
      const out = await getReport(runId);
      if (out && out.error) throw new Error(out.error);
      renderReport(document.getElementById("reportView"),
        out.report_ko || out.report || out.markdown || out.text || "");
    } catch (error) {
      setRunStatus(`리포트를 불러오지 못했습니다: ${errorText(error)}`);
    }
  });
  document.getElementById("compareBtn").addEventListener("click", async () => {
    const runId = runState.runId;
    if (!runId) return;
    // 클릭 시점의 세대. 기다리는 사이 다른 실행을 고르면 어느 쪽에도 그리지
    // 않는다 - 낡은 비교가 새 실행의 퍼널 위에 얹히면 근거가 섞인다.
    const gen = selectGen;
    const baseline = document.getElementById("compareBaseline").value;
    const host = document.getElementById("funnelBox");
    const btn = document.getElementById("compareBtn");
    btn.disabled = true;   // 두 번 누르면 같은 비교가 두 번 얹힌다.
    try {
      const out = await loadCompare(runId, baseline);
      if (gen !== selectGen) return;
      if (out && out.error) throw new Error(out.error);
      const cards = summarizeCompare(out);
      const box = document.createElement("div");
      box.className = "compcards";
      for (const card of cards.slice(0, 24)) {
        const row = el("div", "skill");
        row.append(el("span", "", card.label), el("span", "chip", card.value));
        box.appendChild(row);
      }
      host.prepend(el("p", "note", `비교 결과 (${cards.length}개 항목)`), box);
    } catch (error) {
      if (gen !== selectGen) return;
      host.prepend(el("p", "warn", `비교하지 못했습니다: ${errorText(error)}`));
    } finally {
      btn.disabled = false;
    }
  });
  document.getElementById("newDesignBtn").addEventListener("click", () => {
    highlightRun("");
    document.getElementById("objectiveSection").scrollIntoView({ behavior: "smooth" });
    document.getElementById("targetFasta").focus();
  });
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
}

export { collectObjective, decisionNode, evidenceNode, formatSeconds, stageRow } from "./guided/plan.js";
