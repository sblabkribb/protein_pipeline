// frontend/guided/council.js — 계획 전문가 협의회. 순수 모델 함수와 그리는
// 함수를 나눠 node 테스트가 가능하게 한다. 서버 도구는 pipeline.plan_council.
import { callTool } from "./api.js";
import { el } from "./dom.js";

const VERDICT_LABEL = { ok: "적합", warn: "경고", block: "차단" };
const VERDICT_CHIP = { ok: "okchip", warn: "warnchip", block: "badchip" };

export function councilCardModels(council) {
  const rows = Array.isArray(council) ? council : [];
  return rows.map((row) => {
    const item = row && typeof row === "object" ? row : {};
    return {
      id: String(item.expert_id || ""),
      name: String(item.name || item.expert_id || ""),
      status: String(item.status || "ok"),
      verdict: String(item.verdict || ""),
      label: VERDICT_LABEL[item.verdict] || "",
      chipClass: VERDICT_CHIP[item.verdict] || "",
      reasons: Array.isArray(item.reasons) ? item.reasons.map(String) : [],
      suggestionsCount: Number(item.suggestions_count || 0),
      rawExcerpt: String(item.raw_excerpt || ""),
    };
  });
}

export function renderCouncil(host, council, { pending = false, notes = [] } = {}) {
  host.replaceChildren();
  if (pending) {
    host.appendChild(el("p", "note", "전문가 5인이 계획을 검토하는 중…"));
    return;
  }
  const models = councilCardModels(council);
  if (!models.length) {
    for (const note of notes.length ? notes : ["전문가 검토가 생략되었습니다."]) {
      host.appendChild(el("p", "note", note));
    }
    return;
  }
  for (const note of notes) host.appendChild(el("p", "note", note));
  for (const model of models) {
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", model.name));
    if (model.label) {
      head.appendChild(el("span", model.chipClass, model.label));
    } else {
      head.appendChild(el("span", "chip", model.status === "error" ? "오류" : "검토 불가"));
    }
    if (model.suggestionsCount) {
      head.appendChild(el("span", "chip", `제안 ${model.suggestionsCount}건`));
    }
    card.appendChild(head);
    for (const reason of model.reasons) {
      card.appendChild(el("p", "note", `· ${reason}`));
    }
    host.appendChild(card);
    if (model.rawExcerpt) {
      // 원문은 LLM 산출물이라 그대로 믿지 않는다 - 접이식으로만 참조를 남긴다.
      // 카드 밖 호스트에 두면 접이식이 카드 겉모습을 흐트러뜨리지 않는다.
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "원문 보기";
      details.appendChild(summary);
      const pre = document.createElement("pre");
      pre.className = "artifacttext";
      pre.textContent = model.rawExcerpt;
      details.appendChild(pre);
      host.appendChild(details);
    }
  }
}

export async function requestCouncil(plan) {
  const out = await callTool("pipeline.plan_council", { plan });
  if (out && out.error) throw new Error(out.error);
  return out;
}
