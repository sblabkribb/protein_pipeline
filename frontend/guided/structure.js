// frontend/guided/structure.js — Structure 탭: 구조 선택, 3D 뷰, 잔기 선택.
//
// 구조 파일은 list_artifacts 가 돌려주는 .pdb 산출물이다 (백엔드가 쓰는 형태:
// target.pdb, backbones/<bb>/designs/<id>.pdb, tiers/<k>/af2/<id>/ranked_0.pdb …).
// 내용은 pipeline.read_artifact 가 디코드한 텍스트이고, 뷰어는 기존 앱과 같은
// 3Dmol(guided.html 의 CDN script 태그)을 쓴다. 잔기 선택 로직은 기존 앱의
// lib/residue-picker.js 를 그대로 재사용한다 - 선택 맵 계산을 여기서 다시
// 만들면 같은 잔기를 두고 두 화면이 서로 다른 답을 내놓는다.
import { callTool, errorText } from "./api.js";
import { el } from "./dom.js";
import {
  buildSequenceSelectionTracks,
  selectionMapContains,
  toggleResidueSelectionMaps,
} from "../lib/residue-picker.js";

// guided.js 의 sequenceFromStructure 와 같은 표다. HETATM 은 잔기로 읽지 않는다 -
// HETATM 의 CA 는 알파탄소가 아니라 칼슘이거나 리간드 원자일 수 있다.
const THREE_TO_ONE = {
  ALA:"A", ARG:"R", ASN:"N", ASP:"D", CYS:"C", GLN:"Q", GLU:"E", GLY:"G",
  HIS:"H", ILE:"I", LEU:"L", LYS:"K", MET:"M", PHE:"F", PRO:"P", SER:"S",
  THR:"T", TRP:"W", TYR:"Y", VAL:"V", MSE:"M",
};

// 아티팩트 경로에는 사용자가 정한 이름(run id, design id)이 섞여 있다. 셀렉트
// 레일이 좁으므로 짧은 이름을 보이고, 전체 경로는 풍선글자로 남긴다.
export function pdbArtifactLabel(path) {
  const parts = String(path || "").split("/").filter(Boolean);
  if (parts.length <= 3) return parts.join("/");
  // tiers/<티어>/af2/<id>/ranked_0.pdb 는 티어를 잃지 않게 축약한다.
  const prefix = parts[0] === "tiers" ? `t${parts[1]}/` : "…/";
  return prefix + parts.slice(-3).join("/");
}

// list_artifacts 결과에서 .pdb 파일만 골라 옵션 목록으로 만든다. 디렉터리(type
// "dir")는 read_artifact 에 넘기면 실패하므로 파일만 허용한다(monitor.js 와 같은
// 관행). 같은 경로가 두 번 오면 하나만 남긴다. 얕은 경로(루트의 target.pdb,
// 백본 설계)를 깊은 티어 랭크 모델보다 먼저 보인다.
export function pdbArtifactOptions(artifacts) {
  const seen = new Set();
  const out = [];
  for (const item of Array.isArray(artifacts) ? artifacts : []) {
    if (String(item?.type || "file") !== "file") continue;
    const path = String(item?.path || item?.name || "");
    if (!/\.pdb$/i.test(path)) continue;
    if (seen.has(path)) continue;
    seen.add(path);
    out.push({ path, label: pdbArtifactLabel(path) });
  }
  out.sort((a, b) =>
    a.path.split("/").length - b.path.split("/").length || a.path.localeCompare(b.path));
  return out;
}

// PDB 텍스트에서 사슬별 서열(1문자)과 잔기 번호 순서를 읽는다. ATOM 레코드만
// 읽는다 - HETATM 은 리간드·물·수식 잔기일 수 있고(구조 지표에서 같은 함정을
// 이미 겪었다), 스트립으로 고르는 대상은 단백질 잔기뿐이다.
export function parsePdbChains(pdbText) {
  const residuesByChain = {};
  const residueOrderByChain = {};
  const seen = new Set();
  for (const line of String(pdbText || "").split(/\r?\n/)) {
    if (!line.startsWith("ATOM")) continue;
    const chain = line.slice(21, 22).trim().toUpperCase() || "_";
    const resi = Number.parseInt(line.slice(22, 26).trim(), 10);
    if (!Number.isFinite(resi) || resi <= 0) continue;
    const key = `${chain}:${resi}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const resn = line.slice(17, 20).trim().toUpperCase();
    (residuesByChain[chain] ??= []).push(THREE_TO_ONE[resn] || "X");
    (residueOrderByChain[chain] ??= []).push(resi);
  }
  // 서열은 문자열이어야 한다 - buildSequenceSelectionTracks 가 서열을 한 글자씩
  // 나눠 팔레트를 만든다. 배열을 그대로 넘기면 쉼표가 섞인 셀이 된다.
  const sequenceByChain = {};
  for (const [chain, chars] of Object.entries(residuesByChain)) {
    if (chars.length) sequenceByChain[chain] = chars.join("");
  }
  return { sequenceByChain, residueOrderByChain };
}

// 선택 맵을 칩 목록으로 펼친다. 사슬명 → 잔기 번호 오름차순이면 스트립과 3D 뷰
// 어느 쪽에서 골라도 같은 순서로 보인다.
export function residueSelectionChips(selectionMap) {
  const chips = [];
  for (const [chain, values] of Object.entries(selectionMap || {})) {
    for (const resi of Array.isArray(values) ? values : []) {
      chips.push({ chain, resi, key: `${chain}:${resi}` });
    }
  }
  chips.sort((a, b) => a.chain.localeCompare(b.chain) || a.resi - b.resi);
  return chips;
}

function isResidueSelected(selectionMap, chain, resi) {
  return selectionMapContains(selectionMap, { [chain]: [resi] });
}

// --- 상태와 렌더 (이 아래는 DOM 을 만진다) ---------------------------------

// 선택은 실행별로 유지되지만 실행이 바뀌면 비운다 - 낡은 실행의 잔기 번호를 새
// 실행의 구조에 덧그리면 근거가 섞인다. viewer 인스턴스는 실행이 바뀌어도
// 재사용한다. 컨테이너가 떨어졌을 때만 다시 만든다(이중 초기화 방지).
const structureState = {
  runId: "",
  path: "",
  viewer: null,
  viewerEl: null,
  selection: {},
  sequenceByChain: {},
  residueOrderByChain: {},
};

// 선택 변화는 renderGen 으로 세대를 센다. 스트립·칩·뷰어는 await 없이 다시
// 그리지만, 구조 텍스트 읽기는 await 이므로 돌아왔을 때 다른 구조가 선택돼 있으면
// 그리지 않는다 - 빠르게 옵션을 옮기면 느린 옛 응답이 늦게 도착할 수 있다.
let renderGen = 0;

export async function loadStructureText(runId, path) {
  // read_artifact 는 max_bytes 로 자른 텍스트를 돌려준다(tools.py). 구조 파일
  // 상한은 monitor.js 의 3D 미리보기와 같은 4MB 다.
  const out = await callTool("pipeline.read_artifact", {
    run_id: runId, path, max_bytes: 4000000,
  });
  if (out && out.error) throw new Error(out.error);
  return out && out.text != null ? String(out.text) : "";
}

function clearViewer(message) {
  structureState.viewer = null;
  structureState.viewerEl = null;
  const host = document.getElementById("structureViewer");
  host.replaceChildren(el("p", "note", message || "실행을 고르면 구조가 표시됩니다."));
}

function ensureViewer(host) {
  const state = structureState;
  if (state.viewer && state.viewerEl && state.viewerEl.isConnected) return state.viewer;
  state.viewer = null;
  state.viewerEl = null;
  host.replaceChildren();
  if (!window.$3Dmol) return null;
  const viewerEl = el("div", "viewer3d");
  host.appendChild(viewerEl);
  try {
    // 배경은 monitor.js 의 3D 미리보기와 같은 어두운 팔레트를 쓴다.
    state.viewer = window.$3Dmol.createViewer(viewerEl, { backgroundColor: "#12161d" });
    state.viewerEl = viewerEl;
  } catch {
    // WebGL 컨텍스트 생성 실패. 호출자가 원문 표시로 폴백한다.
    state.viewer = null;
    state.viewerEl = null;
  }
  return state.viewer;
}

// 선택된 잔기만 다시 칠한다. 기본 스타일을 함께 다시 걸어야 토글 해제가 반영된다.
function redrawSelection(viewer) {
  if (!viewer) return;
  viewer.setStyle({}, { cartoon: { colorscheme: "spectrum" } });
  for (const [chain, values] of Object.entries(structureState.selection)) {
    for (const resi of Array.isArray(values) ? values : []) {
      const selector = { resi };
      if (chain && chain !== "_") selector.chain = chain;
      viewer.setStyle(selector, {
        cartoon: { color: "#d9480f" },
        stick: { radius: 0.2, color: "#d9480f" },
      });
    }
  }
  viewer.render();
}

function renderViewer(pdbText) {
  const host = document.getElementById("structureViewer");
  const viewer = ensureViewer(host);
  if (!viewer) {
    // 3Dmol 이 없거나 WebGL 이 실패해도 파일을 못 보는 것은 아니다. 원문을 보여준다.
    host.replaceChildren(el("div", "warn", "3D 뷰어를 사용할 수 없습니다. 대신 원문을 표시합니다."));
    host.appendChild(el("pre", "artifacttext", pdbText));
    return;
  }
  try {
    viewer.clear();
    viewer.addModel(pdbText, "pdb");
    viewer.setClickable({}, true, (atom) => {
      const chain = String(atom?.chain || "").trim().toUpperCase() || "_";
      const resi = Number.parseInt(atom?.resi, 10);
      if (!Number.isFinite(resi) || resi <= 0) return;
      toggleResidue(chain, resi);
    });
    redrawSelection(viewer);
    viewer.zoomTo();
  } catch (error) {
    host.replaceChildren(el("div", "warn",
      `3D 를 그릴 수 없습니다 (${errorText(error)}). 대신 원문을 표시합니다.`));
    host.appendChild(el("pre", "artifacttext", pdbText));
  }
}

// 잔기 스트립. 사슬별로 24 칸씩 끊은 버튼 행 - 누르면 선택이 토글된다.
function renderStrip() {
  const strip = document.getElementById("residueStrip");
  strip.replaceChildren();
  const tracks = buildSequenceSelectionTracks(
    structureState.sequenceByChain,
    structureState.residueOrderByChain,
    { lineLength: 24, labelEvery: 2 },
  );
  if (!tracks.length) {
    strip.appendChild(el("p", "note", structureState.path
      ? "이 구조에서 단백질 잔기를 읽지 못했습니다."
      : "구조를 고르면 잔기 스트립이 표시됩니다."));
    return;
  }
  for (const track of tracks) {
    const residues = track.rows.reduce((count, row) => count + row.cells.length, 0);
    strip.appendChild(el("div", "afolder", `chain ${track.chain} · ${residues} aa`));
    for (const row of track.rows) {
      const rowEl = el("div", "resrow");
      for (const cell of row.cells) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.chain = track.chain;
        button.dataset.resi = String(cell.resi);
        button.title = `${track.chain}:${cell.resi} ${cell.aa} · ${cell.label}`;
        button.textContent = String(cell.aa || "X");
        if (isResidueSelected(structureState.selection, track.chain, cell.resi)) {
          button.className = "is-sel";
        }
        button.addEventListener("click", () => toggleResidue(track.chain, cell.resi));
        rowEl.appendChild(button);
      }
      strip.appendChild(rowEl);
    }
  }
}

// 선택 칩. 제거 단추(×)가 같은 toggleResidue 를 타므로 스트립·3D 뷰와 항상 같다.
function renderChips() {
  const host = document.getElementById("residueSelection");
  host.replaceChildren();
  const chips = residueSelectionChips(structureState.selection);
  if (!chips.length) {
    host.appendChild(el("p", "note", "선택한 잔기가 없습니다. 스트립이나 3D 뷰에서 잔기를 누르세요."));
    return;
  }
  for (const chip of chips) {
    const chipEl = el("span", "chip", chip.key);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost";
    remove.textContent = "×";
    remove.title = `${chip.key} 선택 해제`;
    remove.setAttribute("aria-label", `${chip.key} 선택 해제`);
    remove.addEventListener("click", () => toggleResidue(chip.chain, chip.resi));
    chipEl.appendChild(remove);
    host.appendChild(chipEl);
  }
}

function toggleResidue(chain, resi) {
  structureState.selection = toggleResidueSelectionMaps(
    structureState.selection, { [chain]: [resi] });
  renderStrip();
  renderChips();
  redrawSelection(structureState.viewer);
}

async function renderSelectedStructure(runId, { isStale = () => false } = {}) {
  const gen = ++renderGen;
  const select = document.getElementById("structureFiles");
  const path = select.value;
  if (!path) {
    clearViewer("구조 파일(.pdb)이 여기 나열됩니다.");
    return;
  }
  document.getElementById("structureViewer").replaceChildren(el("p", "note", "불러오는 중…"));
  let text = "";
  try {
    text = await loadStructureText(runId, path);
  } catch (error) {
    if (isStale() || gen !== renderGen) return;
    document.getElementById("structureViewer").replaceChildren(el("div", "warn",
      `구조를 불러오지 못했습니다: ${errorText(error)}`));
    return;
  }
  // await 뒤에는 반드시 세대를 물어본다. 다른 실행을 골랐거나 다른 구조 옵션을
  // 이미 고른 뒤라면 이 응답은 화면에 덧그리면 안 된다.
  if (isStale() || gen !== renderGen) return;
  structureState.path = path;
  const chains = parsePdbChains(text);
  structureState.sequenceByChain = chains.sequenceByChain;
  structureState.residueOrderByChain = chains.residueOrderByChain;
  if (!text) {
    clearViewer(`${path}: 빈 파일입니다.`);
    renderStrip();
    return;
  }
  renderViewer(text);
  renderStrip();
}

function fillStructureSelect(select, options) {
  select.replaceChildren();
  if (!options.length) {
    select.className = "empty";
    const placeholder = document.createElement("option");
    placeholder.disabled = true;
    placeholder.selected = true;
    placeholder.textContent = "이 실행에는 3D 구조 파일(.pdb)이 없습니다.";
    select.appendChild(placeholder);
    return;
  }
  select.className = "";
  for (const option of options) {
    const node = document.createElement("option");
    node.value = option.path;
    node.textContent = option.label;
    node.title = option.path;
    select.appendChild(node);
  }
}

let wired = false;

// facade 가 모듈 최상위 배선에서 한 번 부른다. select 변경은 renderGen 으로
// 자체 보호한다 - 이 경로에는 facade 의 세대 술어가 없다.
export function initStructureTab() {
  if (wired) return;
  wired = true;
  document.getElementById("structureFiles").addEventListener("change", () => {
    const runId = structureState.runId;
    if (!runId) return;
    renderSelectedStructure(runId).catch(() => { /* 위에서 warn 으로 그렸다 */ });
  });
}

// facade 의 selectRun 이 Results·Evidence 와 같은 자리에서 부른다. 아티팩트
// 목록은 facade 가 방금 채운 runState.artifacts 를 그대로 받는다(results.js 의
// loadFunnel 과 같은 관행).
export async function refreshStructure(runId, { isStale = () => false, artifacts = [] } = {}) {
  if (!runId) return;
  if (isStale()) return;
  const options = pdbArtifactOptions(artifacts);
  // 실행이 바뀌면 선택 잔기와 스트립을 비운다. 같은 실행을 다시 고르면 유지한다.
  if (structureState.runId !== runId) {
    structureState.runId = runId;
    structureState.selection = {};
    structureState.sequenceByChain = {};
    structureState.residueOrderByChain = {};
    structureState.path = "";
  }
  fillStructureSelect(document.getElementById("structureFiles"), options);
  renderChips();
  if (!options.length) {
    structureState.path = "";
    clearViewer("이 실행에는 3D 구조 파일(.pdb)이 없습니다.");
    renderStrip();
    return;
  }
  // 사용자가 고른 구조를 최대한 지킨다. 목록에 없어졌으면 첫 번째로 돌아간다.
  const previous = document.getElementById("structureFiles").value;
  const target = options.some((option) => option.path === previous)
    ? previous : options[0].path;
  document.getElementById("structureFiles").value = target;
  await renderSelectedStructure(runId, { isStale });
}
