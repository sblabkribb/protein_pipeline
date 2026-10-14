// frontend/guided/monitor.js — 실행 상태·산출물·연결/워커 점검.
import { callTool, errorText } from "./api.js";
import { el, dot, renderConnections } from "./plan.js";
import { progressStepsForRequest } from "../lib/pipeline.js";
import { renderMarkdown } from "../lib/md.js";
// 순환 import: facade 와 상호 참조. 함수 선언이라 hoisting 으로 안전하되,
// 모듈 최상위에서 호출하지 말 것.
import { showPanel } from "../guided.js";

// --- 모니터 / 분석 --------------------------------------------------------
//
// 기존 RAPID 화면이 쓰는 도구를 그대로 쓴다. 여기서 별도의 요약을 만들면 같은
// 사실이 두 곳에서 갈라지고, 어느 쪽이 맞는지 판단할 근거가 없어진다.

const runState = { runId: "", artifacts: [], status: null };

// 지금 선택된 실행의 마지막 상태 ({ stage, state }). loadRunStatus 와 폴링 tick 이
// 성공 응답마다 갱신하고, 실행을 바꾸면 null 로 지운다 - 낡은 실행의 상태가 새
// 실행의 것처럼 보이지 않게 한다. 에이전트 탭 같은 다른 모듈은 이 읽기 함수로만 본다.
export function currentRunStatus() {
  return runState.status;
}

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

function setRunStatus(text) {
  const host = document.getElementById("runStatus");
  host.classList.add("empty");
  host.textContent = text;
}

// isStale 은 facade 가 건네는 세대 검사다. 두 번 빠르게 누르면 느린 옛 응답이
// 늦게 도착해 새 실행 화면을 덧그릴 수 있다 - await 마다 물어보고, 낡았으면
// 아무것도 그리지 않고 "stale" 로 돌아온다.
export async function loadRunStatus(runId, { isStale = () => false } = {}) {
  const host = document.getElementById("runStatus");
  runState.runId = runId;
  runState.status = null;   // 새 실행을 읽는 동안 지난 실행의 상태를 비운다
  if (!runId) {
    setRunStatus("실행을 고르면 상태가 표시됩니다.");
    return;
  }
  host.classList.add("empty");
  host.textContent = "불러오는 중…";
  try {
    const out = await callTool("pipeline.status", { run_id: runId });
    if (isStale()) return "stale";
    if (out && out.error) throw new Error(out.error);
    // 상태와 산출물은 별개다. status.json 이 없는 실행에도 결과 파일은 있다
    // (예: test_relax_out 은 상태 파일 없이 .pdb 를 갖고 있다).
    if (out.found === false) {
      setRunStatus(`${runId}: 상태 파일이 없습니다. 산출물은 아래에서 볼 수 있습니다.`);
      await loadArtifacts(runId, { isStale });
      if (isStale()) return "stale";
      showPanel("run");
      return;
    }
    // 실제 값은 status 안에 들어 있다. 최상위에서 읽으면 전부 "-" 가 된다.
    const info = (out && typeof out.status === "object" && out.status) || out;
    runState.status = { stage: String(info.stage || ""), state: String(info.state || "") };
    host.classList.remove("empty");
    host.replaceChildren();
    // 상태 칩은 상단바 칩과 같은 근거 체계를 쓴다 - 완료는 측정, 실패는 차단,
    // 나머지는 무색. 여기서 새 해석을 덧붙이지 않는다.
    const stateChipClass = { done: "okchip", failed: "badchip", stalled: "warnchip" }[
      String(info.state || "").trim().toLowerCase()
    ] || "";
    const rows = [
      ["실행", runId, ""],
      ["단계", info.stage || "-", ""],
      ["상태", info.state || "-", stateChipClass],
      ["갱신", info.updated_at || "-", ""],
    ];
    for (const [label, value, cls] of rows) {
      const row = el("div", "skill");
      row.append(el("span", "", label), el("span", cls ? `chip ${cls}` : "chip", value));
      host.appendChild(row);
    }
    if (info.error_summary) {
      const warn = document.createElement("div");
      warn.className = "warn";
      warn.textContent = String(info.error_summary);
      host.appendChild(warn);
    }
    renderRunProgress(info);
    const actions = document.getElementById("runActions");
    if (actions) actions.classList.remove("hidden");
    await loadArtifacts(runId, { isStale });
    if (isStale()) return "stale";
    showPanel("run");
  } catch (error) {
    if (isStale()) return "stale";
    setRunStatus(`상태를 불러오지 못했습니다: ${errorText(error)}`);
  }
}

async function loadArtifacts(runId, { isStale = () => false } = {}) {
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
    if (isStale()) return;
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
          row.addEventListener("click", () => openArtifact(runId, path, format, null, { isStale }));
        host.appendChild(row);
      }
    }
  } catch (error) {
    if (isStale()) return;
    host.classList.add("empty");
    host.textContent = `산출물을 불러오지 못했습니다: ${errorText(error)}`;
  }
}

// isStale 은 loadArtifacts 가 전달하는 세대 검사다. 실행을 바꾼 뒤에도 그 전에
// 시작된 read_artifact 는 도착한다 - 낡은 세대면 미리 보기를 덧그리지 않고 조용히
// 끝낸다. 행 클릭은 행이 속한 실행이 화면에 있을 때만 일어나지만, await 사이에
// 화면이 바뀔 수는 있다.
async function openArtifact(runId, path, format, maxBytes, { isStale = () => false } = {}) {
  const preview = document.getElementById("artifactPreview");
  preview.replaceChildren(el("div", "empty", "불러오는 중…"));
  const cap = maxBytes || (format ? 4000000 : 200000);
  try {
    const out = await callTool("pipeline.read_artifact", {
      run_id: runId, path, max_bytes: cap,
    });
    if (isStale()) return;
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
      more.addEventListener("click", () => openArtifact(runId, path, format, cap * 2, { isStale }));
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
    if (isStale()) return;
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

// --- Run 탭: 진행·폴링·취소·리포트 -----------------------------------------

const POLL_ACTIVE_MS = 5000;
const POLL_IDLE_MS = 30000;
const POLL_MAX_FAILURES = 3;

export function nextPollDelayMs(consecutiveFailures, isActive) {
  if (consecutiveFailures >= POLL_MAX_FAILURES) return 0;
  return isActive ? POLL_ACTIVE_MS : POLL_IDLE_MS;
}

const STAGE_ALIASES = {
  init: "msa", mmseqs_msa: "msa",
  rfd3: "backbone", bioemu: "backbone", af2_target: "af2",
  proteinmpnn: "design",
  wt_baseline: "wt", wt_soluprot: "wt", wt_af2: "wt", wt_relax: "wt", wt_diff: "wt",
  ligand_mask: "masking", pdb_preprocess: "masking", query_pdb_check: "masking",
  surface_mask: "masking", mask_consensus: "masking",
  af2_pooled_tiers: "af2",
};

export function mapStatusStageToStep(stage) {
  const raw = String(stage || "").trim();
  if (!raw) return "";
  if (STAGE_ALIASES[raw]) return STAGE_ALIASES[raw];
  const stripped = raw.replace(/_[0-9]+$/, "");
  return STAGE_ALIASES[stripped] || stripped;   // proteinmpnn_50 -> proteinmpnn -> design
}

export function stageProgressPercent(stage, state, steps) {
  if (!Array.isArray(steps) || !steps.length) return 0;
  if (String(state) === "done") return 100;
  const idx = steps.indexOf(mapStatusStageToStep(stage));
  return idx < 0 ? 0 : Math.round(((idx + 1) / steps.length) * 100);
}

// 폴링 상태. 실행이 끝나거나 실패가 3회 연속되면 멈춘다 - 조용히 계속 도는
// 타이머는 사용자가 탭을 닫은 뒤에도 서버를 두드린다.
// gen 은 재선택을 세는 토큰이다. stopPolling 이 올리면 await 사이에 걸린 낡은
// tick 은 전부 무효가 된다 - 옛 실행의 상태가 새 실행 화면에 덧그려지는 것을 막는다.
const poll = { runId: "", timer: 0, failures: 0, active: false, gen: 0 };

export function stopPolling() {
  poll.gen += 1;                       // 진행 중인 tick 을 전부 무효화
  if (poll.timer) clearTimeout(poll.timer);
  poll.timer = 0;
  poll.runId = "";
}

export function startPolling(runId, { onTick } = {}) {
  stopPolling();
  const gen = poll.gen;
  poll.runId = runId;
  poll.failures = 0;
  poll.active = true;
  const tick = async () => {
    if (gen !== poll.gen) return;                       // 재선택됨 - 낡은 tick
    try {
      const out = await callTool("pipeline.status", { run_id: runId });
      if (gen !== poll.gen) return;                     // await 사이에 재선택됨
      if (out && out.error) throw new Error(out.error);
      poll.failures = 0;
      const info = (out && typeof out.status === "object" && out.status) || out;
      runState.status = { stage: String(info.stage || ""), state: String(info.state || "") };
      const done = ["done", "failed", "cancelled"].includes(String(info.state));
      poll.active = !done;
      if (onTick) onTick(info);
      if (done) { stopPolling(); return; }
    } catch {
      if (gen !== poll.gen) return;
      poll.failures += 1;
      if (poll.failures >= POLL_MAX_FAILURES) {
        poll.active = false;
        if (onTick) onTick({ poll_stalled: true });
        stopPolling();
        return;
      }
    }
    if (gen !== poll.gen) return;
    const delay = nextPollDelayMs(poll.failures, poll.active);
    if (delay > 0) poll.timer = setTimeout(tick, delay);
  };
  poll.timer = setTimeout(tick, POLL_ACTIVE_MS);
}

// 이 화면의 요청 모양은 고정되어 있다 (pipeline 전체, novelty·wt 비교 포함).
// tick 마다 다시 계산하면 같은 배열이 계속 만들어질 뿐이다.
const RUN_PROGRESS_STEPS = progressStepsForRequest({ mode: "pipeline", noveltyEnabled: true, wtCompare: true })
  .filter((step) => step !== "done");

export function renderRunProgress(info) {
  const wrap = document.getElementById("runProgress");
  const fill = document.getElementById("runProgressFill");
  const label = document.getElementById("runProgressLabel");
  if (!wrap || !fill || !label) return;
  if (!info || info.poll_stalled) {
    wrap.classList.add("hidden");
    return;
  }
  const percent = stageProgressPercent(info.stage, info.state, RUN_PROGRESS_STEPS);
  wrap.classList.remove("hidden");
  fill.style.width = `${percent}%`;
  wrap.setAttribute("aria-valuenow", String(percent));
  label.textContent = `${mapStatusStageToStep(info.stage) || info.stage || "-"} · ${info.state || "-"} · ${percent}%`
    + (info.error_summary ? ` · 오류: ${info.error_summary}` : "");
}

export async function cancelRun(runId) {
  return callTool("pipeline.cancel_run", { run_id: runId });
}

export async function generateReport(runId) {
  return callTool("pipeline.generate_report", { run_id: runId });
}

export async function getReport(runId) {
  return callTool("pipeline.get_report", { run_id: runId });
}

export function renderReport(host, markdown) {
  host.classList.remove("hidden");
  host.innerHTML = renderMarkdown(String(markdown || ""));
}

export { closeStage, loadArtifacts, probeWorkers, runState, setRunStatus };
