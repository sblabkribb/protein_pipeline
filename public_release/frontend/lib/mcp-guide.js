const MCP_ENDPOINT_URL = "https://pipeline.k-biofoundrycopilot.duckdns.org/mcp";
const MCP_SERVER_NAME = "protein-pipeline";
const TOKEN_PLACEHOLDER = "<KBF_SSO_ACCESS_TOKEN>";
const TOKEN_PLACEHOLDER_HTML = "&lt;KBF_SSO_ACCESS_TOKEN&gt;";

const GUIDE_COPY = {
  en: {
    title: "MCP guide",
    description: "Connect the shared protein pipeline MCP endpoint from VS Code or Codex without opening raw backend ports.",
    endpoint: {
      title: "1) Remote MCP endpoint",
      description: "Public HTTP MCP endpoint for the pipeline service.",
      items: [
        `<strong>URL</strong>: <code>${MCP_ENDPOINT_URL}</code>`,
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
        `Set the server URL to <code>${MCP_ENDPOINT_URL}</code>.`,
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
        "Codex, use MCP to list my recent protein pipeline runs.",
      ],
    },
  },
  ko: {
    title: "MCP 가이드",
    description: "원시 백엔드 포트를 직접 열지 않고 VS Code와 Codex에서 공용 protein pipeline MCP endpoint에 연결합니다.",
    endpoint: {
      title: "1) 원격 MCP 엔드포인트",
      description: "파이프라인 서비스용 공용 HTTP MCP endpoint입니다.",
      items: [
        `<strong>URL</strong>: <code>${MCP_ENDPOINT_URL}</code>`,
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
        `URL은 <code>${MCP_ENDPOINT_URL}</code> 를 사용합니다.`,
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

function buildMcpJsonSnippet() {
  return JSON.stringify(
    {
      servers: {
        [MCP_SERVER_NAME]: {
          type: "http",
          url: MCP_ENDPOINT_URL,
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

function buildPromptSnippet(examples = []) {
  return examples.join("\n\n");
}

function guideCopyFor(lang = "en") {
  return GUIDE_COPY[lang] || GUIDE_COPY.en;
}

export function renderMcpGuideMarkup({ lang = "en" } = {}) {
  const copy = guideCopyFor(lang);
  return `
    <div class="panel-header">
      <h3>${copy.title}</h3>
      <p>${copy.description}</p>
    </div>

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
        ${renderCodeBlock(buildMcpJsonSnippet())}
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
  `;
}
