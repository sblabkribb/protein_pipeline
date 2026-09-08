// frontend/guided/literature.js — 참조 검색 (PDB·UniProt·InterPro·UniRef·Europe
// PMC). 실행과 무관한 참조 도구라 런 전환에도 결과가 유지된다. 순수 모델과 렌더를
// 나눠 node 테스트가 가능하게 한다. 소스마다 성격 라벨(구조/주석/군집/문헌)이
// 붙는다 — 어느 것도 측정 근거와 같은 칸에 두지 않는다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export const SOURCE_LABEL = {
  structural: "구조",
  curated: "주석",
  clusters: "군집",
  published: "문헌",
};

export function sourceRowModels(items) {
  const rows = Array.isArray(items) ? items : [];
  return rows.map((item) => {
    const row = item && typeof item === "object" ? item : {};
    const legacy = [row.authors, row.journal, row.year].map(String).filter(Boolean).join(" · ");
    const source = String(row.source || "").trim();
    const label = Object.prototype.hasOwnProperty.call(SOURCE_LABEL, source)
      ? SOURCE_LABEL[source] : "";
    return {
      title: String(row.title || "").trim() || "제목 없음",
      meta: String(row.detail || "").trim() || legacy,
      source,
      sourceLabel: label,
      citations: Number(row.citations || 0),
      openAccess: Boolean(row.open_access),
      url: String(row.url || ""),
    };
  });
}

export function renderReference(host, { state = "idle", items = [], message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "참조를 찾는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "참조를 찾지 못했습니다."));
    return;
  }
  if (state === "empty") {
    host.appendChild(el("p", "note", "결과 없음"));
    return;
  }
  if (state === "done") {
    for (const model of sourceRowModels(items)) {
      const card = el("div", "skill");
      const head = el("div", "cardtitle");
      if (model.sourceLabel) head.appendChild(el("span", "chip", model.sourceLabel));
      if (model.url && model.url.startsWith("https://")) {
        // identifier 에서 조립된 서버 URL 만 연다 - 임의 href 는 받지 않는다.
        const link = document.createElement("a");
        link.href = model.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.className = "lit-title";
        link.textContent = model.title;
        head.appendChild(link);
      } else {
        head.appendChild(el("span", "name", model.title));
      }
      if (model.citations) head.appendChild(el("span", "chip", `인용 ${model.citations}`));
      if (model.openAccess) head.appendChild(el("span", "okchip", "OA"));
      card.appendChild(head);
      if (model.meta) card.appendChild(el("p", "note", model.meta));
      host.appendChild(card);
    }
    return;
  }
  host.appendChild(el("p", "note", "검색어를 넣고 검색하세요."));
}

export async function requestReference(source, query) {
  const out = await callTool("pipeline.search_reference", { source, query, limit: 8 });
  if (out && out.error) throw new Error(out.error);
  return out;
}
