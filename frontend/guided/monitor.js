// frontend/guided/monitor.js — 실행 상태·산출물·연결/워커 점검.
import { callTool } from "./api.js";
import { el, dot, renderConnections } from "./plan.js";
import { showPanel } from "../guided.js";

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

export { errorText, formatBytes, isStructureArtifact, loadRunStatus, loadArtifacts, openArtifact, openStage, closeStage, render3d, probeWorkers, runState, setRunStatus };
