// frontend/guided/literature.js — Europe PMC 문헌 검색. 실행과 무관한 참조
// 도구라 런 전환에도 결과가 유지된다. 순수 모델과 렌더를 나눠 node 테스트가
// 가능하게 한다. 결과는 published 출처 — 측정 근거와 섞지 않는다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function literatureRowModels(items) {
  const rows = Array.isArray(items) ? items : [];
  return rows.map((item) => {
    const row = item && typeof item === "object" ? item : {};
    const meta = [row.authors, row.journal, row.year].map(String).filter(Boolean).join(" · ");
    return {
      title: String(row.title || "").trim() || "제목 없음",
      meta,
      citations: Number(row.citations || 0),
      openAccess: Boolean(row.open_access),
      url: String(row.url || ""),
    };
  });
}

export function renderLiterature(host, { state = "idle", items = [], message = "" } = {}) {
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "문헌을 찾는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "문헌을 찾지 못했습니다."));
    return;
  }
  if (state === "empty") {
    host.appendChild(el("p", "note", "결과 없음"));
    return;
  }
  if (state === "done") {
    for (const model of literatureRowModels(items)) {
      const card = el("div", "skill");
      const head = el("div", "cardtitle");
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

export async function requestLiterature(query) {
  const out = await callTool("pipeline.search_literature", { query, limit: 8 });
  if (out && out.error) throw new Error(out.error);
  return out;
}
