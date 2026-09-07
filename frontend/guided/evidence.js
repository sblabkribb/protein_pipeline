// frontend/guided/evidence.js — Evidence 탭: 잔기별 보존도와 리알리티 근거.
//
// 전용 조회 도구(get_conservation/get_liabilities)는 존재하지 않는다. 파이프라인이
// 쓴 산출물 계약을 그대로 읽는다: run 루트의 conservation.json (bio/a3m.py 의
// Conservation: scores 는 잔기별 0..1, 잔기 번호는 1-인덱스) 과
// tiers/<tier>/liabilities.json (pipeline.py: {summary, thresholds, sequences}).
// 여기서 점수를 다시 계산하지 않는다 - 요약(중앙값, 낮은 위치)만 붙인다.
import { callTool, errorText } from "./api.js";
import { el } from "./dom.js";

// 보존도 "낮음" 기본 임계값. scores 는 최다 잔기 비율(0..1)이라 0.3 미만이면
// MSA 히트의 30%도 그 잔기를 지키지 못한다는 뜻이다.
export const LOW_CONSERVATION_DEFAULT = 0.3;

// liabilities.json 의 sequences 행을 펼친 열 순서. 필드 이름은 백엔드 계약 그대로,
// ng_dg 만 게이트가 쓰는 합(deamidation_NG + isomerisation_DG)으로 묶어 놓았다.
export const LIABILITY_COLUMNS = [
  "seq_id", "passed", "net_charge", "max_hydrophobic_patch",
  "aggregation_prone_fraction", "ng_dg", "free_cysteine", "reasons",
];

const LIABILITIES_RE = /tiers\/([0-9.]+)\/liabilities\.json$/;

// 보존도 요약. 잔기 번호는 파이프라인의 fixed_positions 와 같은 1-인덱스다.
// 빈 점수는 실패가 아니라 "볼 것이 없다"이므로 median null 로 돌아온다.
export function summarizeConservation(scores, { lowThreshold = LOW_CONSERVATION_DEFAULT } = {}) {
  const list = Array.isArray(scores)
    ? scores.filter((score) => Number.isFinite(score)) : [];
  if (!list.length) return { median: null, low: [], count: 0 };
  const sorted = [...list].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
  const low = list
    .map((score, idx) => ({ i: idx + 1, score }))
    .filter((p) => p.score < lowThreshold)
    .sort((a, b) => a.score - b.score || a.i - b.i);
  return { median, low, count: low.length };
}

// sequences 행을 테이블 열에 맞게 평평하게 만든다. gate.enabled 가 거짓이면
// passed 는 null 이고, 그것을 "pass" 로 렌더링하면 검사하지 않은 것을 통과한
// 것처럼 보이므로 "-" 로 둔다.
export function buildLiabilityRows(payload) {
  const sequences = payload && Array.isArray(payload.sequences) ? payload.sequences : [];
  return sequences.map((seq) => {
    const motifs = seq.motifs || {};
    const gate = seq.gate || {};
    const reasons = Array.isArray(gate.reasons) ? gate.reasons : [];
    return {
      seq_id: seq.id,
      passed: gate.passed === true ? "pass" : gate.passed === false ? "fail" : "-",
      net_charge: seq.net_charge,
      max_hydrophobic_patch: seq.max_hydrophobic_patch,
      aggregation_prone_fraction: seq.aggregation_prone_fraction,
      ng_dg: (motifs.deamidation_NG || 0) + (motifs.isomerisation_DG || 0),
      free_cysteine: motifs.free_cysteine,
      reasons: reasons.join("; "),
    };
  });
}

// 티어 요약(summary)을 칩으로 내보낼 스칼라로 묶는다. 값이 없으면 0/거짓으로
// 기본값을 둔다 - 없는 것을 추측으로 채우지 않는다.
export function liabilitySummary(payload) {
  const summary = (payload && payload.summary) || {};
  return {
    evaluated: Number(summary.evaluated) || 0,
    failed: Number(summary.failed) || 0,
    enabled: summary.enabled === true,
    calibrated: summary.calibrated === true,
  };
}

// list_artifacts 결과에서 티어별 liabilities.json 경로를 모은다. 멀티백본 실행은
// backbones/<이름>/tiers/<티어>/ 아래에 두는데, 같은 티어 키로 묶는다 - 퍼널
// (results.js tierArtifactPaths)이 이미 선택한 타협이다.
export function liabilityArtifactPaths(artifacts) {
  const tiers = new Map();
  for (const item of Array.isArray(artifacts) ? artifacts : []) {
    if (String(item?.type || "file") !== "file") continue;
    const path = String(item?.path || item?.name || "");
    const match = path.match(LIABILITIES_RE);
    if (match) tiers.set(match[1], path);
  }
  return tiers;
}

export async function loadConservation(runId) {
  try {
    const out = await callTool("pipeline.read_artifact", {
      run_id: runId, path: "conservation.json", max_bytes: 400000,
    });
    // 잘린 JSON 은 파싱에 성공해도 조용히 틀린 숫자를 준다. 못 읽은 것과 0 인
    // 것을 같은 0 으로 보여주지 않는다 - 잘렸으면 없는 것으로 둔다.
    if (!out || !out.text || out.truncated) return null;
    return {
      runId,
      path: out.path || "conservation.json",
      payload: JSON.parse(out.text),
    };
  } catch (error) {
    // conservation.json 이 없는 실행이 정상이다 (MSA 단계를 못 돌린 실행).
    // 없는 것은 빈 상태로, 그 외 오류는 facade 의 warn 으로 올린다.
    if (/not found/i.test(errorText(error))) return null;
    throw error;
  }
}

export async function loadLiabilities(runId, artifacts) {
  let tiers = liabilityArtifactPaths(artifacts);
  if (!tiers.size) {
    // list_artifacts 는 limit 안에서 우선순위로 자른다. 큰 실행에서는 tiers/
    // 가 먼저 잘려나가므로, 비었으면 tiers 로 다시 묻는다 (results.js 와 같은 폴백).
    try {
      const out = await callTool("pipeline.list_artifacts", { run_id: runId, prefix: "tiers", limit: 400 });
      if (out && !out.error) tiers = liabilityArtifactPaths(out.artifacts || []);
    } catch { /* 폴백 실패 시 아래 빈 상태 처리로 진행 */ }
  }
  const found = [];
  for (const [tier, path] of [...tiers.entries()].sort()) {
    try {
      const out = await callTool("pipeline.read_artifact", { run_id: runId, path, max_bytes: 400000 });
      if (!out || !out.text || out.truncated) continue;
      found.push({ runId, tier, path, payload: JSON.parse(out.text) });
    } catch { /* 티어 하나를 못 읽어도 나머지 근거는 그린다 */ }
  }
  return found.length ? { tiers: found } : null;
}

// 테이블은 순수 렌더다 - 테스트가 최소 document 흉내로 구조를 검증한다.
export function renderLiabilityRowsTable(rows) {
  const table = document.createElement("table");
  const head = table.insertRow();
  for (const key of LIABILITY_COLUMNS) head.appendChild(el("th", "", key));
  for (const row of rows) {
    const tr = table.insertRow();
    for (const key of LIABILITY_COLUMNS) {
      const value = row[key];
      tr.insertCell().textContent = value == null ? "-" : String(value);
    }
  }
  return table;
}

// 버튼 누르면 그 아래에서 원문을 펼친다. 재선택되면 이 목록 자체가 통째로
// 교체되므로, await 사이에 낡은 읽기가 돌아와도 붙는 곳은 이미 떨어진 노드다 -
// 화면에 덧그려질 수 없다.
async function toggleRawArtifact(pre, runId, path) {
  if (!pre.hidden) { pre.hidden = true; return; }
  pre.hidden = false;
  if (pre.dataset.loaded) return;
  pre.textContent = "불러오는 중…";
  try {
    const out = await callTool("pipeline.read_artifact", { run_id: runId, path, max_bytes: 200000 });
    if (out && out.error) throw new Error(out.error);
    pre.dataset.loaded = "1";
    pre.textContent = (out.text || "(빈 파일)")
      + (out.truncated ? `\n… 잘렸습니다 (${out.read_bytes}/${out.size} 바이트). Run 탭 산출물에서 이어볼 수 있습니다.` : "");
  } catch (error) {
    pre.textContent = `산출물을 읽지 못했습니다: ${errorText(error)}`;
  }
}

export function renderEvidence(host, { conservation, liabilities } = {}) {
  host.classList.remove("empty");
  host.replaceChildren();

  // (a) 잔기별 보존도
  host.appendChild(el("div", "afolder", "보존도 (MSA 합의)"));
  const payload = conservation && conservation.payload;
  const scores = payload && Array.isArray(payload.scores) ? payload.scores : [];
  if (!scores.length) {
    host.appendChild(el("p", "note", "이 실행에는 보존도 산출물(conservation.json)이 없습니다."));
  } else {
    const summary = summarizeConservation(scores);
    const queryLength = Number(payload.query_length) || scores.length;
    const meta = el("div", "evmeta");
    meta.append(
      el("span", "chip", `길이 ${queryLength}`),
      el("span", "chip", `중앙값 ${summary.median == null ? "-" : summary.median.toFixed(2)}`),
      el("span", "chip", `낮은 위치 ${summary.count}개 (< ${LOW_CONSERVATION_DEFAULT})`),
    );
    host.appendChild(meta);
    // 막대 높이가 보존도다. 낮은 위치는 absent 색으로 표시한다.
    const strip = document.createElement("div");
    strip.className = "conservstrip";
    scores.forEach((score, idx) => {
      const clamped = Math.max(0, Math.min(1, Number(score) || 0));
      const bar = document.createElement("i");
      bar.style.height = `${Math.max(4, clamped * 100)}%`;
      if (clamped < LOW_CONSERVATION_DEFAULT) bar.className = "low";
      bar.title = `#${idx + 1}: ${clamped.toFixed(2)}`;
      strip.appendChild(bar);
    });
    host.appendChild(strip);
    if (summary.low.length) {
      const shown = summary.low.slice(0, 8);
      host.appendChild(el("p", "note",
        `가장 낮은 보존도 위치 ${summary.low.length}개 중 처음 ${shown.length}개`));
      const chips = el("div", "evlows");
      for (const p of shown) chips.appendChild(el("span", "chip", `#${p.i} ${p.score.toFixed(2)}`));
      host.appendChild(chips);
    }
  }

  // (b) 리알리티 테이블
  host.appendChild(el("div", "afolder", "리알리티 (게이트)"));
  const tierList = liabilities && Array.isArray(liabilities.tiers) ? liabilities.tiers : [];
  if (!tierList.length) {
    host.appendChild(el("p", "note", "이 실행에는 리알리티 산출물(tiers/*/liabilities.json)이 없습니다."));
  } else {
    for (const entry of tierList) {
      host.appendChild(el("div", "afolder", `tiers/${entry.tier}`));
      const summary = liabilitySummary(entry.payload);
      host.appendChild(el("p", "note",
        `평가 ${summary.evaluated} · 탈락 ${summary.failed}${summary.enabled ? "" : " · 게이트 비활성"}`));
      host.appendChild(renderLiabilityRowsTable(buildLiabilityRows(entry.payload)));
    }
  }

  // (c) 원문 산출물 - 근거의 출처를 직접 열 수 있게 남겨둔다.
  host.appendChild(el("div", "afolder", "원문 산출물"));
  const paths = [];
  if (conservation) paths.push(conservation);
  for (const entry of tierList) paths.push(entry);
  if (!paths.length) {
    host.appendChild(el("p", "note", "열 수 있는 근거 산출물이 없습니다."));
  } else {
    const list = document.createElement("div");
    list.className = "evidencelinks";
    for (const item of paths) {
      const link = document.createElement("button");
      link.type = "button";
      link.className = "artifact";
      link.title = item.path;
      link.textContent = item.path;
      const pre = document.createElement("pre");
      pre.className = "artifacttext";
      pre.hidden = true;
      link.addEventListener("click", () => toggleRawArtifact(pre, item.runId, item.path));
      list.appendChild(link);
      list.appendChild(pre);
    }
    host.appendChild(list);
  }
}
