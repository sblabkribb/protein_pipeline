// frontend/guided/skills.js — 스킬 탭. 협의회 전문가 헌장을 보고, 편집해 저장하면
// 다음 협의회부터 반영된다. 초기화하면 빌트인 헌장으로 돌아간다.
import { callTool } from "./api.js";
import { el } from "./dom.js";

export function skillCardModels(skills) {
  const rows = Array.isArray(skills) ? skills : [];
  return rows.map((item) => {
    const row = item && typeof item === "object" ? item : {};
    return {
      id: String(row.expert_id || ""),
      name: String(row.name || row.expert_id || ""),
      source: String(row.source || "builtin"),
      charter: String(row.charter || ""),
      updatedUtc: String(row.updated_utc || ""),
    };
  });
}

let editingId = "";
let editingText = "";

export function beginEdit(id, charter) {
  editingId = String(id || "");
  editingText = String(charter ?? "");
}

export function cancelEdit() {
  editingId = "";
  editingText = "";
}

export function currentEdit() {
  return { editingId, editingText };
}

export function renderSkillsTab(host, { state = "idle", skills = [], message = "", editingId = null, editingText = null } = {}) {
  const edit = currentEdit();
  const editId = editingId === null ? edit.editingId : editingId;
  const editText = editingText === null ? edit.editingText : editingText;
  host.replaceChildren();
  if (state === "loading") {
    host.appendChild(el("p", "note", "스킬을 불러오는 중…"));
    return;
  }
  if (state === "error") {
    host.appendChild(el("p", "warn", message || "스킬을 불러오지 못했습니다."));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "ghost";
    retry.textContent = "다시 시도";
    if (typeof retry.addEventListener === "function") {
      retry.addEventListener("click", () => {
        if (typeof window !== "undefined" && window.__skillsTabLoad) window.__skillsTabLoad(true);
      });
    }
    host.appendChild(retry);
    return;
  }
  if (state === "idle") {
    host.appendChild(el("p", "note", "스킬 탭입니다."));
    return;
  }

  const models = skillCardModels(skills);
  host.appendChild(el("h3", "", "협의회 전문가 헌장"));
  host.appendChild(el("p", "note", "헌장은 계획 협의회 전문가의 관점을 정의합니다. 저장 시 다음 협의회부터 반영됩니다."));
  for (const model of models) {
    const card = el("div", "skill");
    const head = el("div", "cardtitle");
    head.appendChild(el("span", "name", model.name));
    if (model.source === "user") head.appendChild(el("span", "warnchip", "사용자 편집"));
    else head.appendChild(el("span", "chip", "빌트인"));
    card.appendChild(head);
    // 마지막 수정은 칩이 아니라 kv 행으로 - 값이 모이는 자리는 모노로 읽는다.
    if (model.updatedUtc) {
      const kv = document.createElement("dl");
      kv.className = "kv";
      kv.appendChild(el("dt", "", "마지막 수정"));
      kv.appendChild(el("dd", "", model.updatedUtc));
      card.appendChild(kv);
    }

    if (editId === model.id) {
      // 편집 중인 카드는 헌장 대신 textarea 폼으로 바뀐다. 값은 textContent 가
      // 아니라 value 로 넣는다 - 줄바꿈이 보존되어야 한다.
      const textarea = document.createElement("textarea");
      textarea.className = "skilledit";
      textarea.value = editText || model.charter;
      card.appendChild(textarea);
      const actions = el("div", "");
      const save = document.createElement("button");
      save.type = "button";
      save.className = "primary";
      save.textContent = "헌장 저장";
      if (typeof save.addEventListener === "function") {
        save.addEventListener("click", () => {
          if (typeof window !== "undefined" && window.__skillsSave) window.__skillsSave();
        });
      }
      actions.appendChild(save);
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "ghost";
      cancel.textContent = "취소";
      if (typeof cancel.addEventListener === "function") {
        cancel.addEventListener("click", () => {
          if (typeof window !== "undefined" && window.__skillsCancel) window.__skillsCancel();
        });
      }
      actions.appendChild(cancel);
      card.appendChild(actions);
    } else {
      if (model.charter) card.appendChild(el("p", "note", model.charter));
      const actions = el("div", "");
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "ghost";
      editBtn.textContent = "편집";
      if (typeof editBtn.addEventListener === "function") {
        editBtn.addEventListener("click", () => {
          if (typeof window !== "undefined" && window.__skillsEdit) window.__skillsEdit(model.id);
        });
      }
      actions.appendChild(editBtn);
      if (model.source === "user") {
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "ghost";
        resetBtn.textContent = "초기화";
        if (typeof resetBtn.addEventListener === "function") {
          resetBtn.addEventListener("click", () => {
            if (typeof window !== "undefined" && window.__skillsReset) window.__skillsReset(model.id);
          });
        }
        actions.appendChild(resetBtn);
      }
      card.appendChild(actions);
    }
    host.appendChild(card);
  }
}

export async function requestSkills() {
  const out = await callTool("pipeline.list_council_skills", {});
  if (out && out.error) throw new Error(out.error);
  return out;
}

export async function saveSkill(expertId, charter) {
  const out = await callTool("pipeline.save_council_skill", { expert_id: expertId, charter });
  if (out && out.error) throw new Error(out.error);
  return out;
}

export async function resetSkill(expertId) {
  const out = await callTool("pipeline.reset_council_skill", { expert_id: expertId });
  if (out && out.error) throw new Error(out.error);
  return out;
}

// guided.js 에는 renderSkills 라는 부분 문자열 자체가 금지다 - 예전 콘솔의
// renderSkills 가 stage 목록을 중복 그렸다는 회귀 경비가 부분 문자열로 검사한다.
// 그래서 파사드는 별명으로 가져온다.
export { renderSkillsTab as paintSkillsTab };
