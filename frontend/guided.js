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
  mapStatusStageToStep,
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
import {
  loadConservation,
  loadLiabilities,
  renderEvidence,
} from "./guided/evidence.js";
import {
  initStructureTab,
  onStructurePanelRevealed,
  refreshStructure,
} from "./guided/structure.js";
import { renderLiterature, requestLiterature } from "./guided/literature.js";
import { renderModels, requestModels, modelsTabModels } from "./guided/models.js";
import { el } from "./guided/dom.js";
import { shouldRestoreStoredSession } from "./lib/auth.js";

// --- 세션 -----------------------------------------------------------------
//
// 이 화면만으로 쓸 수 있어야 하므로 로그인을 여기서 한다. 토큰 키는 기존 앱과
// 같은 "kbf.token" 이다 - 다른 키를 쓰면 두 화면이 서로의 세션을 모른다.

function setSignedIn(user) {
  document.getElementById("loginGate").classList.add("hidden");
  document.getElementById("workspace").classList.remove("hidden");
  document.getElementById("whoami").textContent = user || "";
  // 세션 칩을 지금 사용자로 맞춘다. 실행 상태는 이 실행에서 마지막으로 본 값을 유지한다.
  updateTopbarChips({
    runId: runState.runId, state: lastKnown.state, stage: lastKnown.stage,
  });
}

export function setSignedOut(message) {
  document.getElementById("loginGate").classList.remove("hidden");
  document.getElementById("workspace").classList.add("hidden");
  if (message) document.getElementById("loginError").textContent = message;
  // 만료·로그아웃도 칩에 그대로 비친다. 실행 상태 칩은 지우지 않는다 - 폴링이
  // 멈춰도 끝난 실행의 완료·실패는 여전히 사실이다.
  updateTopbarChips({
    runId: runState.runId, state: lastKnown.state, stage: lastKnown.stage,
  });
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

// --- 상단바 칩 -------------------------------------------------------------
//
// 상단바에는 지금 보고 있는 실행과 세션이 늘 보인다. 문구와 색은 서버가 준
// state 에서만 온다 - 프런트가 상태를 새로 해석하면 Run 탭과 말이 갈라진다.

// 파이프라인 상태 → 칩 문구 + 상태 클래스. stalled 는 서버 상태가 아니라 폴링이
// 3회 연속 실패해 멈춘 프런트 쪽 상태다. 모르는 상태는 받은 값 그대로 보인다.
const RUN_CHIP_STATES = {
  running: { label: "실행 중", cls: "" },
  done: { label: "완료", cls: "okchip" },
  failed: { label: "실패", cls: "badchip" },
  cancelled: { label: "취소됨", cls: "" },
  stalled: { label: "폴링 중단", cls: "warnchip" },
};

// 폴링 tick 과 취소가 마지막으로 본 상태·단계. 로그인·아웃이 칩을 다시 그릴 때
// 실행 상태를 지우지 않기 위해 따로 둔다 - 실행이 끝난 뒤 세션이 바뀌어도
// 완료·실패 칩은 그대로 보여야 한다.
let lastKnown = { state: "", stage: "" };

export function chipLabel(state) {
  const key = String(state || "").trim().toLowerCase();
  return RUN_CHIP_STATES[key] || { label: key || "-", cls: "" };
}

// 칩 내용을 DOM 없이 계산한다. 단계 칩은 monitor.js 의 스테이지 사상을 재사용하고,
// 세션 칩은 lib/auth.js 의 세션 복원 판정을 따른다. 비용 칩은 일부러 없다 - 비용은
// 출처(측정 범위)가 붙는 값이라 계획 카드의 cost bar 에서만 보여준다 (스펙의
// provenance 규칙).
export function topbarChipModels({ runId, state, stage, user, signedIn } = {}) {
  const chip = chipLabel(state);
  const name = String(user || "").trim();
  const models = [{ text: String(runId || "").trim() || "-", cls: "", title: "현재 실행" }];
  if (String(stage || "").trim()) {
    models.push({ text: String(mapStatusStageToStep(stage)), cls: "", title: "단계" });
  }
  models.push({ text: chip.label, cls: chip.cls, title: "실행 상태" });
  models.push({
    text: signedIn ? (name ? `세션 · ${name}` : "세션 있음") : "로그아웃됨",
    cls: "",
    title: "세션",
  });
  return models;
}

// 같은 내용의 칩이면 DOM 을 다시 만지지 않는다. tick 마다 replaceChildren 하면
// aria-live 영역이 같은 말을 반복해 알리고 세션 칩도 함께 떨린다.
let lastPaint = "";
function paintTopbarChips(models) {
  const host = document.getElementById("topbarChips");
  if (!host) return;
  const signature = JSON.stringify(models);
  if (signature === lastPaint) return;
  lastPaint = signature;
  host.replaceChildren();
  for (const { text, cls, title } of models) {
    const node = document.createElement("span");
    node.className = cls ? `chip ${cls}` : "chip";
    node.textContent = text;
    node.title = title;
    host.appendChild(node);
  }
}

// 칩 갱신은 이 함수 하나로만 한다. 낡은 응답 검사는 호출자의 세대 가드(selectRun
// 의 onTick)가 이미 하므로 여기서 다시 하지 않는다 - 이중 가드는 어긋났을 때
// 원인을 두 곳으로 흩는다.
function updateTopbarChips({ runId, state, stage } = {}) {
  paintTopbarChips(topbarChipModels({
    runId,
    state,
    stage,
    user: storedUserName(),
    signedIn: shouldRestoreStoredSession({ token: localStorage.getItem("kbf.token") }),
  }));
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
// 실행을 바꾸면 리포트도 함께 비운다. A 실행의 리포트가 B 실행 화면에 남아
// 있으면 B 의 결과처럼 읽힌다. 다시 만들거나 불러오면 채워진다.
function clearReportView() {
  document.getElementById("reportView").replaceChildren(
    el("p", "note", "리포트를 만들거나 불러올 수 있습니다."));
}

let selectGen = 0;
async function selectRun(runId) {
  if (!runId) return;
  const gen = ++selectGen;
  stopPolling();
  // 칩은 await 앞에서 먼저 비친다 - 느린 상태 조회를 기다리는 동안에도 어떤
  // 실행을 보고 있는지는 틀리면 안 된다. 상태는 아직 모르므로 비운다. 지난
  // 실행의 마지막 상태도 여기서 함께 지운다 - 새 실행에 옛 상태를 붙이지 않는다.
  lastKnown = { state: "", stage: "" };
  updateTopbarChips({ runId });
  clearReportView();
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
  // Evidence 탭도 Results 와 같은 자리에서 따로 채운다. 보존도·리알리티는 산출물
  // 읽기라 느릴 수 있으므로, await 뒤에서 같은 isStale 술어로 낡은 세대를 막는다.
  refreshEvidence(runId, { isStale: () => gen !== selectGen }).catch((error) => {
    if (gen !== selectGen) return;
    document.getElementById("evidenceView").replaceChildren(
      el("p", "warn", `근거를 불러오지 못했습니다: ${errorText(error)}`));
  });
  // Structure 탭도 같은 자리에서 채운다. PDB 는 산출물 읽기라 느릴 수 있으므로
  // structure 쪽 await 마다 같은 isStale 술어로 낡은 세대를 막는다.
  refreshStructure(runId, {
    isStale: () => gen !== selectGen,
    artifacts: runState.artifacts || [],
  }).catch((error) => {
    if (gen !== selectGen) return;
    document.getElementById("structureViewer").replaceChildren(
      el("p", "warn", `구조를 불러오지 못했습니다: ${errorText(error)}`));
  });
  startPolling(runId, {
    onTick: (info) => {
      if (gen !== selectGen) return;
      // 상태 재조회 없이도 Run 탭이 살아 움직인다. 아티팩트는 상태가 바뀔 때만.
      renderRunProgress(info);
      // 칩도 같은 tick 의 정보로 갱신한다. 폴링이 멈췄으면 서버 상태 대신 멈췄다는
      // 사실을 칩으로 말한다 - 마지막 상태를 살아 있는 것처럼 보이면 안 된다.
      lastKnown.state = info.poll_stalled ? "stalled" : info.state;
      if (info.stage) lastKnown.stage = info.stage;
      updateTopbarChips({ runId, state: lastKnown.state, stage: lastKnown.stage });
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

// 근거는 두 산출물(보존도, 리알리티)에서 오며 서로 독립적이다. 병렬로 읽고 한
// 번만 검사한다 - 둘 중 하나만 낡았을 수는 없다 (같은 세대 토큰을 쓴다).
// 없는 산출물은 loader 가 null 로 돌려주고 renderEvidence 가 빈 상태를 그린다.
async function refreshEvidence(runId, { isStale = () => false } = {}) {
  const [conservation, liabilities] = await Promise.all([
    loadConservation(runId),
    loadLiabilities(runId, runState.artifacts || []),
  ]);
  if (isStale()) return;
  renderEvidence(document.getElementById("evidenceView"), { conservation, liabilities });
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
const PANE_DEFAULT_NARROW = { left: 232, right: 300 };
const SPLITTER_TOTAL_PX = 12;
const CENTER_MIN_PX = 360;

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

// 저장된 폭은 화면이 바뀌면 무의미해진다. 중앙 패널은 항상 CENTER_MIN_PX 를
// 보장한다 - 넓은 모니터에서 넓힌 레일이 노트북 절반 창에서 중앙을 짜부뜨린
// 적이 있다. 초과분은 두 레일의 현재 폭 비율로 나눠 차감한다.
export function clampPanes(panes, layoutWidth) {
  const width = Number(layoutWidth) || 0;
  const left = Math.max(PANE_MIN, Number(panes?.left) || PANE_MIN);
  const right = Math.max(PANE_MIN, Number(panes?.right) || PANE_MIN);
  if (width <= 1100) return { left, right };   // 스택 모드가 CSS 로 덮는다
  const budget = width - SPLITTER_TOTAL_PX - CENTER_MIN_PX;
  const total = left + right;
  if (total <= budget) return { left, right };
  const excess = total - budget;
  const share = total > 0 ? left / total : 0.5;
  let newLeft = left - excess * share;
  let newRight = right - excess * (1 - share);
  // 하한에 닿은 쪽은 고정하고 남은 초과분을 다른 쪽에서 더 뺀다.
  if (newRight < PANE_MIN) {
    newLeft = Math.max(PANE_MIN, budget - PANE_MIN);
    newRight = PANE_MIN;
  } else if (newLeft < PANE_MIN) {
    newLeft = PANE_MIN;
    newRight = Math.max(PANE_MIN, budget - PANE_MIN);
  }
  const newLeftRounded = Math.round(newLeft);
  const newRightRounded = Math.max(PANE_MIN, Math.round(budget - newLeftRounded));
  return { left: newLeftRounded, right: newRightRounded };
}

export function choosePaneDefault(width, saved) {
  if (saved && Number(saved.left) > 0 && Number(saved.right) > 0) return saved;
  if (width > 1100 && width <= 1280) return { ...PANE_DEFAULT_NARROW };
  return { ...PANE_DEFAULT };
}

function initSplitters() {
  const layout = document.querySelector(".layout");
  let userPanes = clampPanes(choosePaneDefault(layout.clientWidth, readPanes()), layout.clientWidth);
  let panes = { ...userPanes };
  applyPanes(panes);

  const clamp = (value) => Math.max(PANE_MIN, Math.min(value, layout.clientWidth - PANE_MIN * 2));

  for (const handle of document.querySelectorAll(".splitter")) {
    const side = handle.dataset.splitter;

    const drag = (event) => {
      const rect = layout.getBoundingClientRect();
      userPanes[side] = clamp(side === "left" ? event.clientX - rect.left : rect.right - event.clientX);
      panes = clampPanes(userPanes, layout.clientWidth);
      applyPanes(panes);
    };
    const stop = () => {
      document.removeEventListener("pointermove", drag);
      document.removeEventListener("pointerup", stop);
      document.body.classList.remove("dragging");
      userPanes = clampPanes(userPanes, layout.clientWidth);
      localStorage.setItem(PANE_KEY, JSON.stringify(userPanes));
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
      if (event.key === "ArrowLeft") userPanes[side] = clamp(userPanes[side] + (side === "right" ? step : -step));
      else if (event.key === "ArrowRight") userPanes[side] = clamp(userPanes[side] + (side === "right" ? -step : step));
      else if (event.key !== "Home") return;
      if (event.key === "Home") userPanes[side] = PANE_DEFAULT[side];
      event.preventDefault();
      // 키 입력 하나가 곧 커밋이다(예전에도 즉시 저장했다). 저장 불변식 -
      // userPanes 가 창에 맞는 상태로만 저장된다 - 를 지키기 위해 여기서도 접는다.
      userPanes = clampPanes(userPanes, layout.clientWidth);
      panes = { ...userPanes };
      applyPanes(panes);
      localStorage.setItem(PANE_KEY, JSON.stringify(userPanes));
    });
  }

  // 작업 복사본(panes)은 항상 사용자 선호(userPanes)에서 파생한다. 리사이즈가
  // userPanes 를 되감지 않으므로 창을 다시 넓히면 사용자가 정한 폭으로 돌아간다.
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      panes = clampPanes(userPanes, layout.clientWidth);
      applyPanes(panes);
    }, 100);
  });
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
  // Structure 탭은 숨은 동안 0×0 로 측정된 캔버스를 갖고 있다. 3Dmol 은 드러난
  // 뒤 크기를 다시 재지만 렌더는 뷰어가 lost 일 때만 다시 하므로, 첫 방문이 빈
  // 박스가 되지 않게 드러난 지금 다시 그린다.
  if (name === "structure") onStructurePanelRevealed();
}

// --- 좌측 탭 ---------------------------------------------------------------
//
// 좌측 탭은 기능 패널을 갈아끼운다. 중앙·우측 워크플로와는 무관하다 -
// 실행 선택·폴링·계획 흐름을 건드리지 않는다.

export const SIDE_TAB_KEY = "kbf.guided.sidetab";
const SIDE_TAB_NAMES = ["runs", "models"];
let sideTabWired = false;

export function showSideTab(name) {
  const wanted = SIDE_TAB_NAMES.includes(name) ? name : "runs";
  for (const tab of document.querySelectorAll(".sidetab")) {
    const on = tab.dataset.sidetab === wanted;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", String(on));
  }
  document.getElementById("sideRuns").classList.toggle("hidden", wanted !== "runs");
  document.getElementById("sideModels").classList.toggle("hidden", wanted !== "models");
  localStorage.setItem(SIDE_TAB_KEY, wanted);
  if (wanted === "models" && typeof window.__modelsTabLoad === "function") {
    window.__modelsTabLoad();
  }
}

function initSideTabs() {
  if (sideTabWired) return;
  sideTabWired = true;
  for (const tab of document.querySelectorAll(".sidetab")) {
    tab.addEventListener("click", () => showSideTab(tab.dataset.sidetab));
  }
  let saved = null;
  try { saved = localStorage.getItem(SIDE_TAB_KEY); } catch { /* 저장값이 깨졌으면 기본값 */ }
  showSideTab(saved || "runs");
}

// facade 는 모듈 최상위에서 DOM 을 만진다 (dom.js 머리글의 함정과 같다). 이
// 모듈은 monitor.js 의 순환 import 를 타고 node 테스트까지 평가되므로, 브라우저
// 밖에서는 배선을 건너뛴다. 함수 선언과 export 는 그대로 남는다.
if (typeof document !== "undefined") {
  initSplitters();
  initStructureTab();

  // 문헌 검색은 실행과 무관하다 - 런 전환 리셋 대상이 아니므로 Evidence 패널의
  // evidenceView 형제로 두고 여기서 한 번만 연결한다.
  let literatureGen = 0;
  async function runLiteratureSearch() {
    const host = document.getElementById("literatureBox");
    const query = document.getElementById("literatureInput").value.trim();
    const gen = ++literatureGen;
    if (!query) {
      renderLiterature(host, { state: "idle" });
      return;
    }
    renderLiterature(host, { state: "loading" });
    try {
      const out = await requestLiterature(query);
      if (gen !== literatureGen) return;   // 재검색됨 - 늦게 도착한 결과는 버린다
      const items = Array.isArray(out.items) ? out.items : [];
      renderLiterature(host, items.length ? { state: "done", items } : { state: "empty" });
    } catch (error) {
      if (gen !== literatureGen) return;
      renderLiterature(host, { state: "error", message: `문헌을 찾지 못했습니다: ${errorText(error)}` });
    }
  }

  function initLiteratureSearch() {
    const form = document.getElementById("literatureForm");
    if (!form || form.dataset.wired) return;
    form.dataset.wired = "1";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      runLiteratureSearch();
    });
  }
  initLiteratureSearch();
  initSideTabs();

  // 모델 탭은 정적 레지스트리라 첫 진입에 한 번만 읽는다. showSideTab 이 탭이
  // 열릴 때 부르는 훅이다. force 는 실패 화면의 "다시 시도" 가 쓴다.
  window.__modelsTabLoad = (force = false) => {
    const host = document.getElementById("sideModels");
    if (host.dataset.loaded && !force) return;   // 첫 진입 1회 로드
    if (host.dataset.loading) return;            // 중복 요청 억제
    host.dataset.loading = "1";
    renderModels(host, { state: "loading" });
    requestModels().then((payload) => {
      host.dataset.loaded = "1";
      delete host.dataset.loading;
      renderModels(host, { state: "done", model: modelsTabModels(payload) });
    }).catch((error) => {
      delete host.dataset.loading;
      renderModels(host, { state: "error", message: `레지스트리를 불러오지 못했습니다: ${errorText(error)}` });
    });
  };

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
      // 취소가 받아들여졌다. 다음 tick 이 서버 상태를 확인해 주기 전에도 칩은
      // 곧바로 취소됨을 비춘다 - 서버가 달리 말하면 tick 이 되돌린다.
      lastKnown.state = "cancelled";
      updateTopbarChips({ runId, state: "cancelled" });
    } catch (error) {
      setRunStatus(`취소하지 못했습니다: ${errorText(error)}`);
    }
  });
  document.getElementById("reportGenBtn").addEventListener("click", async () => {
    const runId = runState.runId;
    if (!runId) return;
    // 클릭 시점의 세대. compareBtn 과 같은 규칙이다 - 기다리는 사이 다른 실행을
    // 고르면 어느 쪽에도 그리지 않는다.
    const gen = selectGen;
    const button = document.getElementById("reportGenBtn");
    button.disabled = true;
    try {
      const genOut = await generateReport(runId);
      if (gen !== selectGen) return;
      if (genOut && genOut.error) throw new Error(genOut.error);
      const out = await getReport(runId);
      if (gen !== selectGen) return;
      if (out && out.error) throw new Error(out.error);
      renderReport(document.getElementById("reportView"),
        out.report_ko || out.report || out.markdown || out.text || "");
    } catch (error) {
      if (gen !== selectGen) return;
      setRunStatus(`리포트를 만들지 못했습니다: ${errorText(error)}`);
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("reportLoadBtn").addEventListener("click", async () => {
    const runId = runState.runId;
    if (!runId) return;
    const gen = selectGen;
    try {
      const out = await getReport(runId);
      if (gen !== selectGen) return;
      if (out && out.error) throw new Error(out.error);
      renderReport(document.getElementById("reportView"),
        out.report_ko || out.report || out.markdown || out.text || "");
    } catch (error) {
      if (gen !== selectGen) return;
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
