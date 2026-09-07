// frontend/guided/intake.js — 대화형 목표 인테이크 카드.
//
// 서버의 pipeline.intake_chat 이 규칙 먼저 확정 값을 뽑고 LLM 은 빈 칸만 채운다.
// 이 모듈은 그 결과를 그리는 일만 한다. 실행 경로는 여기서 열리지 않는다 —
// objective_ready 가 참이면 facade 가 목표 폼에 반영하고, 실행은 언제나 계획
// 생성 → 계획 카드 승인을 지난다. 순수 모델과 렌더를 나눠 node 테스트가
// 가능하게 한다(literature.js 와 같은 패턴).
import { callTool } from "./api.js";
import { el } from "./dom.js";

// 대화는 모듈 상태로 쌓인다. facade 는 push/reset 로만 만진다 — 인테이크 카드가
// 다시 그려져도 대화가 사라지면 안 된다.
let intakeMessages = [];

export function intakeMsgModels(messages) {
  return (Array.isArray(messages) ? messages : [])
    .filter((m) => m && typeof m === "object")
    .map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      text: String(m.content ?? "").trim(),
    }))
    .filter((m) => m.text);
}

export function intakeThread() {
  return intakeMessages.map((m) => ({ ...m }));
}

export function pushIntakeMessage(role, text) {
  const content = String(text ?? "").trim();
  if (content) intakeMessages.push({ role, content });
  return intakeThread();
}

export function resetIntakeMessages() {
  intakeMessages = [];
}

function msgNode(model) {
  const node = el("div", `msg msg-${model.role}`);
  node.appendChild(el("span", "who", model.role === "user" ? "나" : "도우미"));
  node.appendChild(el("p", "", model.text));
  return node;
}

export function renderIntake(host, {
  state = "idle", messages = [], reply = "", missing = [], objectiveReady = false, note = "",
} = {}) {
  host.replaceChildren();
  host.appendChild(el("h3", "", "무엇을 만들고 싶으신가요?"));
  host.appendChild(el("p", "note",
    "말로 설명하면 목표 폼을 채워 드립니다. 실행은 계획 카드 검토·승인을 거칩니다."));

  const log = el("div", "chatlog");
  const models = intakeMsgModels(messages);
  // reply 는 아직 스레드에 없을 때만 뒤에 붙인다 — facade 가 스레드에 넣은 뒤에도
  // 같은 텍스트를 인자로 넘기면 이중으로 그려진다.
  const lastAssistant = [...models].reverse().find((m) => m.role === "assistant");
  const trailing = String(reply || "").trim();
  if (trailing && (!lastAssistant || lastAssistant.text !== trailing)) {
    models.push({ role: "assistant", text: trailing });
  }
  if (!models.length) {
    log.className = "chatlog empty";
    log.appendChild(el("p", "", "예: \"용해도 좋은 효소를 40개 만들고 싶어요.\""));
  } else {
    for (const model of models) log.appendChild(msgNode(model));
  }
  host.appendChild(log);

  // 빠진 필수는 줄줄이 보인다. 서버가 계산한 목록이며 프런트가 추측하지 않는다.
  for (const item of Array.isArray(missing) ? missing : []) {
    host.appendChild(el("p", "warn", String(item)));
  }
  if (objectiveReady) {
    host.appendChild(el("p", "note", "계획 카드로 옮겼습니다 — 검토 후 계획 생성을 눌러주세요."));
  }

  if (state === "busy") {
    host.appendChild(el("p", "note", note || "목표를 정리하는 중…"));
    return;
  }
  if (state === "unavailable") {
    host.appendChild(el("p", "warn",
      note || "LLM 연결 없음 — 아래 카드에서 목적과 목표를 선택해 주세요."));
  }

  // idle/chat/ready/unavailable 모두 입력을 남긴다. LLM 이 없어도 카드는 그대로
  // 있고 입력만 막힌다 — 상태가 사라지면 이유도 같이 사라진다.
  const form = el("div", "chatform");
  const input = document.createElement("input");
  input.id = "intakeInput";
  input.placeholder = "예: 용해도 좋은 효소를 40개 만들고 싶어요";
  input.disabled = state === "unavailable";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "primary";
  button.id = "intakeSend";
  button.textContent = "보내기";
  button.disabled = state === "unavailable";
  // 테스트용 document 스텁에는 addEventListener 이 없다. 있을 때만 연결한다.
  if (typeof input.addEventListener === "function") {
    input.addEventListener("keydown", (event) => {
      if (event && event.key === "Enter" && typeof event.preventDefault === "function") {
        event.preventDefault();
        if (typeof window !== "undefined" && typeof window.__intakeSend === "function") {
          window.__intakeSend(input.value);
        }
      }
    });
  }
  if (typeof button.addEventListener === "function") {
    button.addEventListener("click", () => {
      if (typeof window !== "undefined" && typeof window.__intakeSend === "function") {
        window.__intakeSend(input.value);
      }
    });
  }
  form.appendChild(input);
  form.appendChild(button);
  host.appendChild(form);
}

export async function requestIntake(messages, attached = {}) {
  const out = await callTool("pipeline.intake_chat", {
    messages,
    attached_fasta: String(attached.fasta || ""),
    attached_pdb: String(attached.pdb || ""),
  });
  if (out && out.error) throw new Error(out.error);
  return out;
}
