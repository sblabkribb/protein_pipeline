const MCP_DEFAULT_ENDPOINT_URL = "https://rapid.kbiofoundry.kr/mcp";
const MCP_ENDPOINT_TOKEN = "__MCP_ENDPOINT__";
const MCP_SERVER_NAME = "protein-pipeline";

export function resolveMcpEndpointUrl({
  origin = typeof window !== "undefined" ? window.location.origin : "",
} = {}) {
  const normalized = String(origin || "").trim().replace(/\/$/, "");
  if (normalized && normalized !== "null") {
    return `${normalized}/mcp`;
  }
  return MCP_DEFAULT_ENDPOINT_URL;
}
const TOKEN_PLACEHOLDER = "<KBF_SSO_ACCESS_TOKEN>";
const TOKEN_PLACEHOLDER_HTML = "&lt;KBF_SSO_ACCESS_TOKEN&gt;";

const GUIDE_COPY = {
  en: {
    title: "Connect your AI to the pipeline",
    description: "Three steps: give your AI client the connection, the skill, and one prompt — then it does the rest, from MCP connection to analysis.",
    flow: {
      step1Title: "1) Connection",
      step1Desc: "Sign in, then copy a ready-to-paste mcp.json with your token and paste it into your AI client (VS Code / Codex / Claude).",
      step2Title: "2) Skill",
      step2Desc: "Download the protein-pipeline-stepper skill (it includes the connection + execution rules) and place it in your agent's skills directory.",
      step3Title: "3) Tell your AI",
      step3Desc: "Copy this master prompt, replace «your analysis task», and send it. The AI connects via MCP and runs the analysis following the skill.",
      masterPrompt:
        "Use the protein-pipeline-stepper skill. The protein-pipeline MCP server is already configured in my client — connect to it, then do this analysis:\n\n«describe your analysis task, e.g. run standalone ColabFold on this FASTA: ...»\n\nFollow the skill: reuse one stable run_id, check pipeline.status before running, poll long-running jobs instead of re-running, pass file contents (not paths), and if a result looks wrong or fails, diagnose and ask me before re-running.",
      masterPromptButton: "Copy master prompt",
      advancedSummary: "Advanced setup (endpoint URL, manual mcp.json, VS Code / Codex steps, verify, prompt examples)",
    },
    endpoint: {
      title: "1) Remote MCP endpoint",
      description: "Public HTTP MCP endpoint for the pipeline service.",
      items: [
        `<strong>URL</strong>: <code>${MCP_ENDPOINT_TOKEN}</code>`,
        `<strong>Header</strong>: <code>Authorization: Bearer ${TOKEN_PLACEHOLDER_HTML}</code>`,
        "Non-admin users only see allowed tools, and run-scoped tools only work for their own <code>run_id</code> values.",
      ],
    },
    config: {
      title: "2) VS Code mcp.json",
      description:
        "Open <strong>MCP: Open User Configuration</strong> and paste this into <code>mcp.json</code>.",
    },
    token: {
      title: "3) How to get the token",
      description: "Choose the token source that matches your auth mode.",
      copyButton: "Copy mcp.json with my token",
      downloadButton: "Download skill",
      autoNote:
        "One click fills your bearer token into the mcp.json above and copies it. The token is a short-lived sign-in token — if MCP calls start failing, click again to refresh it.",
      installNote:
        "To use the downloaded skill: unzip it and put the <code>protein-pipeline-stepper/</code> folder in your agent's skills directory (Claude Code: <code>~/.claude/skills/</code>), then reload/restart the client so it discovers the skill.",
      items: [
        "<strong>Local auth mode</strong>: open browser devtools, go to <code>Local Storage</code>, and copy <code>kbf.token</code>.",
        `<strong>OIDC / KBF SSO mode</strong>: sign in to a KBF SSO-backed service, open the notebook service MCP page, then open browser devtools and inspect <code>Local Storage</code> &gt; <code>auth-storage</code>. Copy the <code>access_token</code> value and reuse it as <code>${TOKEN_PLACEHOLDER_HTML}</code> in <code>mcp.json</code>.`,
      ],
      note: "If you are signed in with SSO and <code>kbf.token</code> is empty in this app, that is expected. The pipeline UI currently uses the server-side session cookie for the browser session, while VS Code MCP still requires a bearer token in <code>mcp.json</code>.",
    },
    codex: {
      title: "4) Use it from Codex",
      description: "Codex can use the same endpoint and Authorization header as VS Code.",
      steps: [
        `Add an MCP server named <code>${MCP_SERVER_NAME}</code> in your Codex client.`,
        `Set the server URL to <code>${MCP_ENDPOINT_TOKEN}</code>.`,
        `Store <code>Authorization: Bearer ${TOKEN_PLACEHOLDER_HTML}</code> with the server configuration.`,
        "Explicitly mention MCP in your prompt so the tool call is unambiguous.",
      ],
    },
    verify: {
      title: "5) Verify it works",
      description: "After saving the configuration:",
      steps: [
        `Run <strong>MCP: List Servers</strong> and confirm <code>${MCP_SERVER_NAME}</code> is available.`,
        "Ask VS Code Copilot or Codex to call MCP for a run status or a pipeline launch.",
        "Check that returned <code>run_id</code> values use your user-scoped prefix.",
      ],
    },
    prompts: {
      title: "6) Prompt examples",
      description: "Start with direct MCP wording so the tool is clearly invoked.",
      examples: [
        "Use MCP to list my recent protein pipeline runs.",
        "Use MCP to check the status of run_id abc_20260316_123456_deadbeef.",
        "Use MCP to build a pipeline.run example for the current signed-in user.",
        "Use MCP to run AlphaFold2 standalone (pipeline.af2_predict) on this FASTA sequence.",
        "Use MCP to run a single design stage only: pipeline.run with stop_after=design.",
        "Codex, use MCP to list my recent protein pipeline runs.",
      ],
    },
  },
  ko: {
    title: "AI를 파이프라인에 연결",
    description: "세 단계면 됩니다 — AI 클라이언트에 연결·스킬·프롬프트 하나만 주면, MCP 연결부터 분석까지 AI가 알아서 합니다.",
    flow: {
      step1Title: "1) 연결",
      step1Desc: "로그인한 뒤 토큰이 채워진 mcp.json을 복사해 AI 클라이언트(VS Code / Codex / Claude)에 붙여넣으세요.",
      step2Title: "2) 스킬",
      step2Desc: "protein-pipeline-stepper 스킬을 다운로드(연결+실행 규칙 포함)해서 에이전트의 skills 디렉터리에 넣으세요.",
      step3Title: "3) AI에게 명령",
      step3Desc: "이 마스터 프롬프트를 복사하고 《분석 작업》 부분만 바꿔 보내세요. AI가 MCP로 연결해 스킬에 따라 분석을 수행합니다.",
      masterPrompt:
        "protein-pipeline-stepper 스킬을 사용해. protein-pipeline MCP 서버는 내 클라이언트에 이미 설정돼 있어 — 거기에 연결한 뒤 다음 분석을 해줘:\n\n《분석 작업을 설명, 예: 이 FASTA로 ColabFold 단독 실행: ...》\n\n스킬 규칙을 지켜: run_id 하나를 재사용하고, 실행 전 pipeline.status로 확인하고, 오래 걸리는 작업은 재실행 말고 폴링하고, 파일은 경로 대신 내용을 전달하고, 결과가 이상하거나 실패하면 진단한 뒤 재실행 전에 나에게 확인해.",
      masterPromptButton: "마스터 프롬프트 복사",
      advancedSummary: "고급 설정 (엔드포인트 URL · 수동 mcp.json · VS Code / Codex 단계 · 검증 · 프롬프트 예시)",
    },
    endpoint: {
      title: "1) 원격 MCP 엔드포인트",
      description: "파이프라인 서비스용 공용 HTTP MCP endpoint입니다.",
      items: [
        `<strong>URL</strong>: <code>${MCP_ENDPOINT_TOKEN}</code>`,
        `<strong>헤더</strong>: <code>Authorization: Bearer ${TOKEN_PLACEHOLDER_HTML}</code>`,
        "일반 사용자는 허용된 도구만 볼 수 있고, run 범위 도구는 자신의 <code>run_id</code>에 대해서만 동작합니다.",
      ],
    },
    config: {
      title: "2) VS Code 설정",
      description: "<strong>MCP: Open User Configuration</strong>을 열고 아래 내용을 <code>mcp.json</code>에 붙여 넣으세요.",
    },
    token: {
      title: "3) 토큰 가져오기",
      description: "현재 인증 방식에 맞는 토큰 원본을 선택하세요.",
      copyButton: "내 토큰으로 mcp.json 복사",
      downloadButton: "skill 다운로드",
      autoNote:
        "버튼 한 번이면 위 mcp.json에 bearer 토큰을 채워 클립보드에 복사합니다. 이 토큰은 수명이 짧은 로그인 토큰이라, MCP 호출이 실패하기 시작하면 다시 눌러 갱신하세요.",
      installNote:
        "다운로드한 skill 사용법: 압축을 풀어 <code>protein-pipeline-stepper/</code> 폴더를 에이전트의 skills 디렉터리(Claude Code: <code>~/.claude/skills/</code>)에 넣고, 클라이언트를 새로고침/재시작하면 인식됩니다.",
      items: [
        "<strong>로컬 인증 모드</strong>: 브라우저 개발자 도구를 열고 <code>Local Storage</code>에서 <code>kbf.token</code> 값을 복사하세요.",
        `<strong>OIDC / KBF SSO 모드</strong>: KBF SSO가 적용된 서비스에 로그인한 뒤 notebook service MCP 페이지를 열고, 브라우저 개발자 도구에서 <code>Local Storage</code> &gt; <code>auth-storage</code>를 확인하세요. 그 안의 <code>access_token</code> 값을 복사해 VS Code 또는 Codex 설정의 <code>${TOKEN_PLACEHOLDER_HTML}</code> 자리에 넣으면 됩니다.`,
      ],
      note: "SSO로 로그인한 상태에서 이 앱의 <code>kbf.token</code>이 비어 있어도 정상입니다. 현재 pipeline UI는 브라우저 세션에서 서버측 세션 쿠키를 사용하고, VS Code와 Codex의 MCP 연결은 별도 bearer token을 저장해야 합니다.",
    },
    codex: {
      title: "4) Codex에서 사용",
      description: "Codex도 VS Code와 같은 endpoint와 Authorization 헤더를 사용하면 됩니다.",
      steps: [
        `<code>${MCP_SERVER_NAME}</code> 라는 이름으로 MCP 서버를 추가합니다.`,
        `URL은 <code>${MCP_ENDPOINT_TOKEN}</code> 를 사용합니다.`,
        `<code>Authorization: Bearer ${TOKEN_PLACEHOLDER_HTML}</code> 헤더를 함께 저장합니다.`,
        "질문할 때는 MCP 사용을 직접 적어 도구 호출이 분명하게 보이게 합니다.",
      ],
    },
    verify: {
      title: "5) 연결 확인",
      description: "설정을 저장한 뒤 아래를 확인하세요.",
      steps: [
        `먼저 <strong>MCP: List Servers</strong>를 실행해 <code>${MCP_SERVER_NAME}</code>가 보이는지 확인합니다.`,
        "VS Code나 Codex에 MCP로 run 상태 조회나 pipeline 실행을 요청합니다.",
        "반환된 <code>run_id</code>가 현재 사용자 prefix를 사용하는지 확인합니다.",
      ],
    },
    prompts: {
      title: "6) 질문 예시",
      description: "도구 호출이 분명하게 보이도록 MCP를 직접 언급하는 문장으로 시작하세요.",
      examples: [
        "MCP를 이용해서 내 protein pipeline 최근 run 목록을 보여줘.",
        "MCP를 이용해서 run_id abc_20260316_123456_deadbeef 상태를 확인해줘.",
        "MCP를 이용해서 현재 사용자 기준으로 실행 가능한 pipeline.run 예시를 만들어줘.",
        "MCP를 이용해서 이 FASTA로 AlphaFold2 단독 실행(pipeline.af2_predict)을 해줘.",
        "MCP를 이용해서 design 단계만 단독 실행해줘: pipeline.run에 stop_after=design.",
        "Codex에서 MCP를 사용해서 내 최근 pipeline run들을 보여줘.",
      ],
    },
  },
};

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderList(items = []) {
  return `<div class="mcp-guide-list">${items.map((item) => `<div>${item}</div>`).join("")}</div>`;
}

function renderSteps(items = []) {
  return `<ol class="mcp-guide-steps">${items.map((item) => `<li>${item}</li>`).join("")}</ol>`;
}

function renderCodeBlock(text) {
  return `<pre class="mcp-guide-code"><code>${escapeHtml(text)}</code></pre>`;
}

function buildMcpJsonSnippet(endpointUrl = resolveMcpEndpointUrl()) {
  return JSON.stringify(
    {
      servers: {
        [MCP_SERVER_NAME]: {
          type: "http",
          url: endpointUrl,
          headers: {
            Authorization: `Bearer ${TOKEN_PLACEHOLDER}`,
          },
        },
      },
    },
    null,
    2
  );
}

export function buildMcpJsonSnippetWithToken(token, endpointUrl = resolveMcpEndpointUrl()) {
  const safe = String(token == null ? "" : token);
  return buildMcpJsonSnippet(endpointUrl).replaceAll(TOKEN_PLACEHOLDER, safe);
}

function buildPromptSnippet(examples = []) {
  return examples.join("\n\n");
}

function guideCopyFor(lang = "en") {
  return GUIDE_COPY[lang] || GUIDE_COPY.en;
}

export function renderMcpGuideMarkup({ lang = "en", endpointUrl = resolveMcpEndpointUrl() } = {}) {
  const copy = guideCopyFor(lang);
  const markup = `
    <div class="panel-header">
      <h3>${copy.title}</h3>
      <p>${copy.description}</p>
    </div>

    <div class="tab-grid monitor-grid mcp-guide-grid">
      <div class="status-card mcp-guide-card">
        <div class="panel-header small">
          <h3>${copy.flow.step1Title}</h3>
          <p>${copy.flow.step1Desc}</p>
        </div>
        <div class="mcp-guide-actions">
          <button type="button" id="mcpTokenCopyBtn" class="btn-primary">${copy.token.copyButton}</button>
        </div>
        <div class="mcp-guide-note">${copy.token.autoNote}</div>
      </div>

      <div class="status-card mcp-guide-card">
        <div class="panel-header small">
          <h3>${copy.flow.step2Title}</h3>
          <p>${copy.flow.step2Desc}</p>
        </div>
        <div class="mcp-guide-actions">
          <button type="button" id="mcpSkillDownloadBtn" class="btn-secondary">${copy.token.downloadButton}</button>
        </div>
        <div class="mcp-guide-note">${copy.token.installNote}</div>
      </div>

      <div class="status-card mcp-guide-card span-2">
        <div class="panel-header small">
          <h3>${copy.flow.step3Title}</h3>
          <p>${copy.flow.step3Desc}</p>
        </div>
        <pre class="mcp-guide-code" id="mcpMasterPromptText"><code>${escapeHtml(copy.flow.masterPrompt)}</code></pre>
        <div class="mcp-guide-actions">
          <button type="button" id="mcpMasterPromptCopyBtn" class="btn-primary">${copy.flow.masterPromptButton}</button>
          <span id="mcpGuideStatus" class="mcp-guide-status" role="status"></span>
        </div>
      </div>
    </div>

    <details class="mcp-guide-advanced">
      <summary>${copy.flow.advancedSummary}</summary>
      <div class="tab-grid monitor-grid mcp-guide-grid">
        <div class="status-card mcp-guide-card">
          <div class="panel-header small">
            <h3>${copy.endpoint.title}</h3>
            <p>${copy.endpoint.description}</p>
          </div>
          ${renderList(copy.endpoint.items)}
        </div>

        <div class="status-card mcp-guide-card">
          <div class="panel-header small">
            <h3>${copy.config.title}</h3>
            <p>${copy.config.description}</p>
          </div>
          ${renderCodeBlock(buildMcpJsonSnippet(endpointUrl))}
        </div>

        <div class="status-card mcp-guide-card span-2">
          <div class="panel-header small">
            <h3>${copy.token.title}</h3>
            <p>${copy.token.description}</p>
          </div>
          ${renderList(copy.token.items)}
          <div class="mcp-guide-note">${copy.token.note}</div>
        </div>

        <div class="status-card mcp-guide-card">
          <div class="panel-header small">
            <h3>${copy.codex.title}</h3>
            <p>${copy.codex.description}</p>
          </div>
          ${renderSteps(copy.codex.steps)}
        </div>

        <div class="status-card mcp-guide-card">
          <div class="panel-header small">
            <h3>${copy.verify.title}</h3>
            <p>${copy.verify.description}</p>
          </div>
          ${renderSteps(copy.verify.steps)}
        </div>

        <div class="status-card mcp-guide-card">
          <div class="panel-header small">
            <h3>${copy.prompts.title}</h3>
            <p>${copy.prompts.description}</p>
          </div>
          ${renderCodeBlock(buildPromptSnippet(copy.prompts.examples))}
        </div>
      </div>
    </details>
  `;
  return markup.replaceAll(MCP_ENDPOINT_TOKEN, escapeHtml(endpointUrl));
}
