import { formatWtIdentitySummary } from "./pipeline.js";

function isKorean(lang = "en") {
  return String(lang || "").trim().toLowerCase().startsWith("ko");
}

function formatMetric(value, digits = 1) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : "-";
}

function sortRows(rows = []) {
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => row && typeof row === "object")
    .slice()
    .sort((left, right) => Number(right?.score || 0) - Number(left?.score || 0));
}

function topRows(snapshot = {}, count = 3) {
  return sortRows(snapshot?.rows).slice(0, Math.max(1, count));
}

function rowSummary(row, lang = "en") {
  const wtText = formatWtIdentitySummary(row, lang);
  return `${row?.seq_id || "-"} · score ${formatMetric(row?.score, 1)} · pLDDT ${formatMetric(
    row?.plddt,
    1
  )} · RMSD ${formatMetric(row?.rmsd, 2)} · WT ${wtText}`;
}

function explainMetricTerm(prompt, lang = "en") {
  const q = String(prompt || "").trim().toLowerCase();
  const ko = isKorean(lang);
  if (/(wt\s*(cf|colabfold)\s*rmsd|wt.*rmsd.*의미|wt.*rmsd.*뜻|wt.*rmsd.*무슨)/i.test(q)) {
    return ko
      ? "WT CF RMSD는 WT 서열을 ColabFold로 예측한 구조와 현재 후보 구조 사이의 C-alpha RMSD입니다.\n값이 낮을수록 WT 기준 구조에 더 가깝다는 뜻입니다.\npLDDT와 WT 상동성도 함께 봐야 해석이 안정적입니다."
      : "WT CF RMSD is the C-alpha RMSD between the wild-type ColabFold structure and the current candidate structure.\nLower values mean the candidate stays closer to the WT structural reference.\nInterpret it together with pLDDT and WT sequence identity.";
  }
  if (/plddt/i.test(q)) {
    return ko
      ? "pLDDT는 예측 구조의 residue-level confidence입니다.\n보통 높을수록 구조 신뢰도가 좋다고 봅니다."
      : "pLDDT is the residue-level confidence score for the predicted structure.\nHigher values usually mean the structural prediction is more reliable.";
  }
  if (/identity|상동|homology/i.test(q)) {
    return ko
      ? "WT 상동성은 설계 서열이 WT와 얼마나 같은지를 뜻합니다.\n현재 UI에서는 WT 차이 개수/길이와 함께 상동성 %를 같이 보는 것이 맞습니다."
      : "WT identity measures how similar the design sequence is to the wild-type sequence.\nIt should be read together with the WT difference count/length, not inverted into a difference percentage.";
  }
  return ko
    ? "질문한 용어의 의미를 먼저 설명하고, 필요하면 현재 run 값에 연결해서 해석하는 방식이 적절합니다."
    : "The right approach is to define the term first, then connect it to the current run if needed.";
}

function interpretSnapshot(snapshot = {}, lang = "en") {
  const ko = isKorean(lang);
  const row = snapshot?.topRow || topRows(snapshot, 1)[0] || null;
  if (!row) {
    return ko
      ? "해석할 Hit List 후보가 아직 없습니다. 먼저 Hit List를 갱신한 뒤 score, pLDDT, RMSD, WT 상동성을 함께 보세요."
      : "There is no Hit List candidate to interpret yet. Refresh the Hit List first, then review score, pLDDT, RMSD, and WT identity together.";
  }
  return ko
    ? [
        `현재는 ${rowSummary(row, "ko")}`,
        "score는 현재 가중치 기준의 종합 점수입니다.",
        "pLDDT는 구조 confidence이고, RMSD는 기준 구조와의 거리라서 낮을수록 가깝습니다.",
        "WT 항목은 차이 개수/길이와 WT 상동성 %를 같이 읽는 것이 맞습니다.",
      ].join("\n")
    : [
        `Current top row: ${rowSummary(row, "en")}`,
        "Score is the weighted composite for the current ranking configuration.",
        "pLDDT is structural confidence, while RMSD is distance to the reference, so lower is closer.",
        "The WT field should be read as difference count/length plus WT identity percentage.",
      ].join("\n");
}

function usageReply(snapshot = {}, lang = "en") {
  const ko = isKorean(lang);
  const tab = String(snapshot?.tab || "").trim().toLowerCase();
  if (tab === "setup" || tab === "studio") {
    return ko
      ? "Setup/Studio에서는 input을 정리하고 residue picker로 고정 위치를 지정한 뒤 run을 시작합니다.\n서열과 3D 선택은 같은 selection으로 동기화되는 흐름이 적절합니다."
      : "In Setup/Studio, prepare the input, lock residues with the residue picker, and then launch the run.\nSequence and 3D selections should stay synchronized as one selection state.";
  }
  if (tab === "monitor") {
    return ko
      ? "Monitor에서는 stage 상태와 산출물을 확인하고, 중단된 run은 resume로 이어갑니다."
      : "In Monitor, inspect stage state and artifacts, then resume interrupted runs when needed.";
  }
  return ko
    ? "Analyze에서는 1) Hit List로 후보를 좁히고 2) Compare Studio 기본 sequence diff를 보고 3) 필요할 때 구조 차이와 residue-linked view를 함께 확인합니다."
    : "In Analyze, 1) narrow candidates in the Hit List, 2) start from the default sequence diff in Compare Studio, and 3) inspect structure deltas plus the residue-linked view when needed.";
}

function summaryReply(snapshot = {}, lang = "en") {
  const ko = isKorean(lang);
  const rows = sortRows(snapshot?.rows);
  if (!snapshot?.runId) {
    return ko
      ? "현재 선택된 run이 없습니다. run을 선택하면 상태, 상위 후보, 비교 준비 상태를 바로 요약할 수 있습니다."
      : "No run is selected. Once a run is selected, status, top candidates, and compare readiness can be summarized immediately.";
  }
  const row = rows[0] || null;
  const head = ko ? `Run ${snapshot.runId}` : `Run ${snapshot.runId}`;
  if (!row) return `${head}\n${ko ? "아직 정리할 후보가 없습니다." : "There is no ranked candidate yet."}`;
  return `${head}\n${ko ? "상위 후보" : "Top candidate"}: ${rowSummary(row, lang)}`;
}

function compareReply(snapshot = {}, lang = "en") {
  const ko = isKorean(lang);
  const compare = snapshot?.compare && typeof snapshot.compare === "object" ? snapshot.compare : {};
  if (!compare?.leftPath && !compare?.rightPath) {
    return ko
      ? "Compare Studio에서 아직 좌/우 구조를 선택하지 않았습니다. 먼저 기준 구조와 후보 구조를 고르세요."
      : "No left/right structures are selected in Compare Studio yet. Pick a reference structure and a candidate first.";
  }
  if (!compare?.ready) {
    return ko
      ? "지금은 한쪽만 선택된 상태입니다. 좌/우 구조를 모두 고르면 sequence diff부터 보는 것이 좋습니다."
      : "Only one side is selected right now. Once both sides are chosen, start with the sequence diff.";
  }
  return ko
    ? "좌측은 기준 구조, 우측은 현재 선택된 후보 구조입니다. 먼저 sequence diff를 보고, 그 다음 structure diff와 residue-linked view로 좁히는 흐름이 좋습니다."
    : "The left side is the reference structure and the right side is the selected candidate. Start with the sequence diff, then narrow the review with structure diff and the residue-linked view.";
}

function nextReply(snapshot = {}, lang = "en") {
  const ko = isKorean(lang);
  const rows = topRows(snapshot, 3);
  if (!snapshot?.runId) {
    return ko
      ? "다음 단계는 run을 선택하거나 새 run을 시작하는 것입니다."
      : "The next step is to select an existing run or start a new one.";
  }
  if (!rows.length) {
    return ko
      ? "다음 단계는 Hit List를 갱신하고 Compare Studio에서 기준/후보를 선택하는 것입니다."
      : "Next, refresh the Hit List and choose a reference/candidate pair in Compare Studio.";
  }
  return ko
    ? `다음 단계는 상위 ${rows.length}개 후보를 Compare Studio에서 순서대로 검토하는 것입니다.`
    : `Next, review the top ${rows.length} candidates in Compare Studio one by one.`;
}

function resumeReply(snapshot = {}, lang = "en") {
  const ko = isKorean(lang);
  if (!snapshot?.runId) {
    return ko ? "재시작하려면 run을 먼저 선택하세요." : "Select a run first before resuming it.";
  }
  return ko
    ? "`Run 재시작`은 같은 run_id의 request.json을 다시 읽고, 이미 있는 산출물은 최대한 재사용하면서 누락 단계부터 이어갑니다."
    : "`Resume Run` reloads request.json for the same run_id and continues from missing stages while reusing existing artifacts whenever possible.";
}

function recommendReply(snapshot = {}, lang = "en") {
  const ko = isKorean(lang);
  const rows = topRows(snapshot, 3);
  if (!rows.length) {
    return ko
      ? "추천할 Hit List 후보가 없습니다. 먼저 Hit List를 갱신하세요."
      : "There are no Hit List rows to recommend from yet. Refresh the Hit List first.";
  }
  const lines = [ko ? "현재 기준 추천 3종입니다." : "Recommended top 3 candidates right now."];
  rows.forEach((row, index) => {
    lines.push(`${index + 1}. ${rowSummary(row, lang)}`);
  });
  return lines.join("\n");
}

export function copilotIntentFromPrompt(prompt, intentHint = "") {
  const hinted = String(intentHint || "")
    .trim()
    .toLowerCase();
  if (["usage", "interpret", "summary", "compare", "next", "resume", "term", "recommend"].includes(hinted)) {
    return hinted;
  }
  const q = String(prompt || "").trim().toLowerCase();
  if (!q) return "general";
  if (/(wt\s*(cf|colabfold)\s*rmsd|무슨 의미|무슨뜻|뜻이|what does|what is)/i.test(q)) return "term";
  if (/(recommend|추천|top ?3|3종)/i.test(q)) return "recommend";
  if (/(resume|restart|recover|이어|재시작|다시 시작)/i.test(q)) return "resume";
  if (/(summary|summar|요약|정리)/i.test(q)) return "summary";
  if (/(compare|comparison|studio|left|right|비교|컨텍스트|context)/i.test(q)) return "compare";
  if (/(interpret|해석|지표|점수|plddt|rmsd|score|metric)/i.test(q)) return "interpret";
  if (/(next|다음|뭘|무엇|action|step)/i.test(q)) return "next";
  if (/(usage|how to|사용법|어떻게|guide|도움)/i.test(q)) return "usage";
  return "general";
}

/**
 * Fetches a reasoned reply from the backend agent.
 */
async function fetchAgentReasoning(snapshot, prompt, lang = "en") {
  const runId = snapshot?.runId || snapshot?.run_id || snapshot?.request?.run_id;
  if (!runId) return null;

  try {
    const response = await fetch("/api/rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: Date.now(),
        method: "tools/call",
        params: {
          name: "pipeline.agent_chat",
          arguments: { run_id: runId, prompt: prompt, lang: lang }
        }
      })
    });

    const data = await response.json();
    if (data.result && data.result.reply) {
      return data.result.reply;
    }
    return null;
  } catch (err) {
    console.error("Agent Reasoning Error:", err);
    return null;
  }
}

export async function buildCopilotReply({ prompt = "", intentHint = "", snapshot = {}, lang = "en" } = {}) {
  // 1. Try Backend Reasoning Agent first if we have a run context
  if (prompt && (snapshot?.runId || snapshot?.run_id)) {
    const reasonedReply = await fetchAgentReasoning(snapshot, prompt, lang);
    if (reasonedReply) {
      return reasonedReply;
    }
  }

  // 2. Fallback to existing Rule-based logic
  const intent = copilotIntentFromPrompt(prompt, intentHint);
  if (intent === "term") return explainMetricTerm(prompt, lang);
  if (intent === "recommend") return recommendReply(snapshot, lang);
  if (intent === "usage") return usageReply(snapshot, lang);
  if (intent === "interpret") return interpretSnapshot(snapshot, lang);
  if (intent === "summary") return summaryReply(snapshot, lang);
  if (intent === "compare") return compareReply(snapshot, lang);
  if (intent === "next") return nextReply(snapshot, lang);
  if (intent === "resume") return resumeReply(snapshot, lang);
  return `${summaryReply(snapshot, lang)}\n\n${nextReply(snapshot, lang)}`;
}
