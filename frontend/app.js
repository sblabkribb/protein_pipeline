import {
  buildRunArguments,
  buildUserPrefix,
  createRunId,
  detectTargetKey,
  filterRunsByPrefix,
  isBinaryPath,
  isImagePath,
  sanitizeName,
  stageFromPath,
} from "./lib/pipeline.js";

const defaultApiBase = (() => {
  const origin = window.location.origin;
  const path = window.location.pathname || "";
  if (origin && origin !== "null") {
    if (path.startsWith("/pipeline")) {
      return `${origin}/pipeline/api`;
    }
  }
  return "https://k-biofoundrycopilot.duckdns.org/pipeline/api";
})();

const savedApiBase = localStorage.getItem("kbf.apiBase") || "";

function normalizeApiBase(value) {
  return String(value || "").trim().replace(/\/$/, "");
}

function resolveApiBase() {
  const normalized = normalizeApiBase(savedApiBase);
  if (!normalized) return defaultApiBase;
  if (/localhost|127\\.0\\.0\\.1/.test(normalized)) return defaultApiBase;
  if (
    window.location.origin &&
    window.location.origin !== "null" &&
    window.location.pathname.startsWith("/pipeline") &&
    normalized === `${window.location.origin}/api`
  ) {
    return `${window.location.origin}/pipeline/api`;
  }
  return normalized;
}

const state = {
  apiBase: resolveApiBase(),
  user: loadUser(),
  token: localStorage.getItem("kbf.token") || "",
  plan: null,
  runMode: "pipeline",
  feedbackRating: "good",
  feedbackReasons: [],
  answers: {},
  currentRunId: null,
  pollTimer: null,
  lastStatusKey: "",
  answerMeta: {},
  chainRanges: null,
  artifacts: [],
};

if (state.apiBase && state.apiBase !== normalizeApiBase(savedApiBase)) {
  localStorage.setItem("kbf.apiBase", state.apiBase);
}

const el = {
  loginGate: document.getElementById("loginGate"),
  loginUsername: document.getElementById("loginUsername"),
  loginPassword: document.getElementById("loginPassword"),
  loginBtn: document.getElementById("loginBtn"),
  loginError: document.getElementById("loginError"),
  logoutBtn: document.getElementById("logoutBtn"),
  chatArea: document.getElementById("chatArea"),
  userBadge: document.getElementById("userBadge"),
  messages: document.getElementById("messages"),
  promptInput: document.getElementById("promptInput"),
  planBtn: document.getElementById("planBtn"),
  clearBtn: document.getElementById("clearBtn"),
  questionStack: document.getElementById("questionStack"),
  runBtn: document.getElementById("runBtn"),
  runHint: document.getElementById("runHint"),
  runIdValue: document.getElementById("runIdValue"),
  runStageValue: document.getElementById("runStageValue"),
  runStateValue: document.getElementById("runStateValue"),
  runUpdatedValue: document.getElementById("runUpdatedValue"),
  runScoreValue: document.getElementById("runScoreValue"),
  runEvidenceValue: document.getElementById("runEvidenceValue"),
  runRecommendationValue: document.getElementById("runRecommendationValue"),
  pollBtn: document.getElementById("pollBtn"),
  autoPoll: document.getElementById("autoPoll"),
  artifactList: document.getElementById("artifactList"),
  artifactFilter: document.getElementById("artifactFilter"),
  refreshArtifacts: document.getElementById("refreshArtifacts"),
  artifactPreview: document.getElementById("artifactPreview"),
  feedbackRating: document.getElementById("feedbackRating"),
  feedbackReasons: document.getElementById("feedbackReasons"),
  feedbackArtifact: document.getElementById("feedbackArtifact"),
  feedbackStage: document.getElementById("feedbackStage"),
  feedbackComment: document.getElementById("feedbackComment"),
  submitFeedback: document.getElementById("submitFeedback"),
  exportFeedbackCsv: document.getElementById("exportFeedbackCsv"),
  exportFeedbackTsv: document.getElementById("exportFeedbackTsv"),
  feedbackStatus: document.getElementById("feedbackStatus"),
  feedbackList: document.getElementById("feedbackList"),
  experimentAssay: document.getElementById("experimentAssay"),
  experimentResult: document.getElementById("experimentResult"),
  experimentSampleId: document.getElementById("experimentSampleId"),
  experimentArtifact: document.getElementById("experimentArtifact"),
  experimentMetrics: document.getElementById("experimentMetrics"),
  experimentConditions: document.getElementById("experimentConditions"),
  submitExperiment: document.getElementById("submitExperiment"),
  exportExperimentCsv: document.getElementById("exportExperimentCsv"),
  exportExperimentTsv: document.getElementById("exportExperimentTsv"),
  experimentStatus: document.getElementById("experimentStatus"),
  experimentList: document.getElementById("experimentList"),
  reportContent: document.getElementById("reportContent"),
  reportScoreValue: document.getElementById("reportScoreValue"),
  reportEvidenceValue: document.getElementById("reportEvidenceValue"),
  reportRecommendationValue: document.getElementById("reportRecommendationValue"),
  loadReport: document.getElementById("loadReport"),
  generateReport: document.getElementById("generateReport"),
  saveReport: document.getElementById("saveReport"),
  reportStatus: document.getElementById("reportStatus"),
  reportArtifactLinks: document.getElementById("reportArtifactLinks"),
  settingsBtn: document.getElementById("settingsBtn"),
  settingsPanel: document.getElementById("settingsPanel"),
  apiBaseValue: document.getElementById("apiBaseValue"),
  healthCheck: document.getElementById("healthCheck"),
  healthStatus: document.getElementById("healthStatus"),
  runList: document.getElementById("runList"),
  adminPanel: document.getElementById("adminPanel"),
  adminUsername: document.getElementById("adminUsername"),
  adminPassword: document.getElementById("adminPassword"),
  adminRole: document.getElementById("adminRole"),
  adminCreateUser: document.getElementById("adminCreateUser"),
  adminStatus: document.getElementById("adminStatus"),
  adminRunsToggle: document.getElementById("adminRunsToggle"),
  showAllRuns: document.getElementById("showAllRuns"),
};

const RUN_MODE_OPTIONS = [
  { label: "Full Pipeline", value: "pipeline" },
  { label: "RFD3 (Backbone)", value: "rfd3" },
  { label: "MSA (MMseqs2)", value: "msa" },
  { label: "ProteinMPNN", value: "design" },
  { label: "SoluProt", value: "soluprot" },
  { label: "AlphaFold2", value: "af2" },
  { label: "DiffDock", value: "diffdock" },
];

const FEEDBACK_REASONS = [
  { label: "Low pLDDT", value: "low_plddt" },
  { label: "High RMSD", value: "high_rmsd" },
  { label: "Binding Poor", value: "binding_poor" },
  { label: "Low Novelty", value: "low_novelty" },
  { label: "Unstable", value: "unstable" },
  { label: "Other", value: "other" },
];

const FEEDBACK_STAGES = [
  { label: "Auto", value: "" },
  { label: "MSA", value: "msa" },
  { label: "Design", value: "design" },
  { label: "SoluProt", value: "soluprot" },
  { label: "AlphaFold2", value: "af2" },
  { label: "Novelty", value: "novelty" },
  { label: "RFD3", value: "rfd3" },
  { label: "DiffDock", value: "diffdock" },
  { label: "Other", value: "other" },
];

const EXPERIMENT_ASSAYS = [
  { label: "Binding", value: "binding" },
  { label: "Activity", value: "activity" },
  { label: "Stability", value: "stability" },
  { label: "Expression", value: "expression" },
  { label: "Other", value: "other" },
];

const EXPERIMENT_RESULTS = [
  { label: "Success", value: "success" },
  { label: "Fail", value: "fail" },
  { label: "Inconclusive", value: "inconclusive" },
];

const EXPORT_LIMIT = 2000;

function loadUser() {
  const raw = localStorage.getItem("kbf.user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (err) {
    return null;
  }
}

function saveUser(user) {
  localStorage.setItem("kbf.user", JSON.stringify(user));
}

function saveToken(token) {
  localStorage.setItem("kbf.token", token);
}

function clearSession() {
  localStorage.removeItem("kbf.user");
  localStorage.removeItem("kbf.token");
  state.user = null;
  state.token = "";
}

function setMessage(text, role = "ai") {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  el.messages.appendChild(div);
  el.messages.scrollTop = el.messages.scrollHeight;
}

function setUserBadge() {
  if (!state.user) return;
  const base = state.user.username || "user";
  const role = state.user.role === "admin" ? "admin" : "user";
  el.userBadge.textContent = `${base} · ${role}`;
}

function showLogin() {
  el.loginGate.classList.remove("hidden");
  el.chatArea.classList.add("hidden");
}

function showChat() {
  el.loginGate.classList.add("hidden");
  el.chatArea.classList.remove("hidden");
  setUserBadge();
  ensureManualPlan();
}

function updateAdminUI() {
  const isAdmin = state.user && state.user.role === "admin";
  if (isAdmin) {
    el.adminPanel.classList.remove("hidden");
    el.adminRunsToggle.classList.remove("hidden");
  } else {
    el.adminPanel.classList.add("hidden");
    el.adminRunsToggle.classList.add("hidden");
    el.showAllRuns.checked = false;
  }
}

function buildManualPlan(mode) {
  const questions = [
    {
      id: "run_mode",
      label: "Run Mode",
      question: "Choose what to run.",
      required: true,
      default: "pipeline",
    },
  ];

  if (mode === "pipeline") {
    questions.push(
      {
        id: "target_input",
        label: "Target Input",
        question: "Provide target_pdb or target_fasta (raw text).",
        required: true,
      },
      {
        id: "stop_after",
        label: "Stop After",
        question: "Where to stop? (msa/design/soluprot/af2/novelty)",
        required: false,
        default: "novelty",
      },
      {
        id: "design_chains",
        label: "Design Chains",
        question: "Which chains to design? (default: all)",
        required: false,
      },
      {
        id: "rfd3_input_pdb",
        label: "RFD3 Input PDB",
        question: "Optional: provide rfd3_input_pdb text (raw PDB).",
        required: false,
      },
      {
        id: "rfd3_contig",
        label: "RFD3 Contig",
        question: "Optional: provide rfd3_contig (format: A1-221, no colon).",
        required: false,
      },
      {
        id: "diffdock_ligand",
        label: "DiffDock Ligand",
        question: "Optional: provide diffdock_ligand_smiles or diffdock_ligand_sdf.",
        required: false,
      }
    );
  }

  if (mode === "rfd3") {
    questions.push(
      {
        id: "rfd3_input_pdb",
        label: "RFD3 Input PDB",
        question: "Provide rfd3_input_pdb text (raw PDB).",
        required: true,
      },
      {
        id: "rfd3_contig",
        label: "RFD3 Contig",
        question: "Provide rfd3_contig (format: A1-221, no colon).",
        required: true,
      }
    );
  }

  if (mode === "msa") {
    questions.push({
      id: "target_input",
      label: "Target Input",
      question: "Provide target_pdb or target_fasta (raw text).",
      required: true,
    });
  }

  if (mode === "design") {
    questions.push(
      {
        id: "target_input",
        label: "Target Input",
        question: "Provide target_pdb or target_fasta (raw text).",
        required: true,
      },
      {
        id: "design_chains",
        label: "Design Chains",
        question: "Which chains to design? (default: all)",
        required: false,
      }
    );
  }

  if (mode === "soluprot") {
    questions.push(
      {
        id: "target_input",
        label: "Target Input",
        question: "Provide target_pdb or target_fasta (raw text).",
        required: true,
      },
      {
        id: "design_chains",
        label: "Design Chains",
        question: "Which chains to design? (default: all)",
        required: false,
      }
    );
  }

  if (mode === "af2") {
    questions.push({
      id: "target_input",
      label: "Target FASTA",
      question: "Provide target FASTA or sequence for AlphaFold2.",
      required: true,
    });
  }

  if (mode === "diffdock") {
    questions.push(
      {
        id: "target_input",
        label: "Protein PDB",
        question: "Provide protein PDB text for DiffDock.",
        required: true,
      },
      {
        id: "diffdock_ligand",
        label: "Ligand Input",
        question: "Provide ligand SMILES or SDF for DiffDock.",
        required: true,
      }
    );
  }

  return { routed_request: {}, questions };
}

function updateRunLabel() {
  if (!el.runBtn) return;
  const labels = {
    pipeline: "Run Pipeline",
    rfd3: "Run RFD3",
    msa: "Run MSA",
    design: "Run ProteinMPNN",
    soluprot: "Run SoluProt",
    af2: "Run AlphaFold2",
    diffdock: "Run DiffDock",
  };
  el.runBtn.textContent = labels[state.runMode] || "Run";
}

function setRunMode(mode, { render = true } = {}) {
  const normalized = RUN_MODE_OPTIONS.find((opt) => opt.value === mode)?.value || "pipeline";
  state.runMode = normalized;
  if (normalized === "diffdock") {
    state.answers.diffdock_use = "use";
  }
  state.plan = buildManualPlan(normalized);
  updateRunLabel();
  if (render) {
    renderQuestions(state.plan.questions || []);
  }
}

function ensureManualPlan() {
  if (state.plan && Array.isArray(state.plan.questions) && state.plan.questions.length > 0) {
    updateRunLabel();
    renderQuestions(state.plan.questions);
    return;
  }
  setRunMode(state.runMode || "pipeline");
}

function resetPlan({ keepMode = true } = {}) {
  state.answers = {};
  state.answerMeta = {};
  state.chainRanges = null;
  const nextMode = keepMode ? state.runMode : "pipeline";
  setRunMode(nextMode);
}

function renderToggleButtons(container, options, currentValues, onToggle) {
  const group = document.createElement("div");
  group.className = "choice-group";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice-btn";
    const selected = Array.isArray(currentValues) && currentValues.includes(opt.value);
    if (selected) btn.classList.add("selected");
    btn.textContent = opt.label;
    btn.addEventListener("click", () => {
      onToggle(opt.value);
      renderFeedbackControls();
    });
    group.appendChild(btn);
  });
  container.innerHTML = "";
  container.appendChild(group);
}

function renderSingleButtons(container, options, currentValue, onSelect) {
  const group = document.createElement("div");
  group.className = "choice-group";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice-btn";
    if (currentValue === opt.value) btn.classList.add("selected");
    btn.textContent = opt.label;
    btn.addEventListener("click", () => {
      onSelect(opt.value);
      renderFeedbackControls();
    });
    group.appendChild(btn);
  });
  container.innerHTML = "";
  container.appendChild(group);
}

function fillSelect(select, options, { includeEmpty = false } = {}) {
  if (!select) return;
  select.innerHTML = "";
  if (includeEmpty) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "None";
    select.appendChild(opt);
  }
  options.forEach((item) => {
    const opt = document.createElement("option");
    opt.value = item.value;
    opt.textContent = item.label;
    select.appendChild(opt);
  });
}

function renderFeedbackControls() {
  if (!el.feedbackRating || !el.feedbackReasons) return;
  renderSingleButtons(
    el.feedbackRating,
    [
      { label: "Good", value: "good" },
      { label: "Bad", value: "bad" },
    ],
    state.feedbackRating,
    (value) => {
      state.feedbackRating = value;
    }
  );

  renderToggleButtons(el.feedbackReasons, FEEDBACK_REASONS, state.feedbackReasons, (value) => {
    const next = new Set(state.feedbackReasons);
    if (next.has(value)) {
      next.delete(value);
    } else {
      next.add(value);
    }
    state.feedbackReasons = Array.from(next);
  });
}

function refreshArtifactSelects() {
  const options = [
    { label: "None", value: "" },
    ...state.artifacts.map((item) => ({ label: item.path, value: item.path })),
  ];
  if (el.feedbackArtifact) {
    fillSelect(el.feedbackArtifact, options);
  }
  if (el.experimentArtifact) {
    fillSelect(el.experimentArtifact, options);
  }
}

function initFeedbackUI() {
  renderFeedbackControls();
  fillSelect(el.feedbackStage, FEEDBACK_STAGES, { includeEmpty: false });
  fillSelect(el.experimentAssay, EXPERIMENT_ASSAYS, { includeEmpty: false });
  fillSelect(el.experimentResult, EXPERIMENT_RESULTS, { includeEmpty: false });
  refreshArtifactSelects();

  if (el.feedbackArtifact && el.feedbackStage) {
    el.feedbackArtifact.addEventListener("change", () => {
      const value = el.feedbackArtifact.value;
      if (value) {
        const stage = stageFromPath(value);
        if (stage && el.feedbackStage.value === "") {
          el.feedbackStage.value = stage;
        }
      }
    });
  }
}

function updateRunInfo(status) {
  if (!status) return;
  el.runStageValue.textContent = status.stage || "-";
  el.runStateValue.textContent = status.state || "-";
  el.runUpdatedValue.textContent = status.updated_at || "-";
}

function setCurrentRunId(runId) {
  state.currentRunId = runId;
  state.lastStatusKey = "";
  el.runIdValue.textContent = runId || "-";
  refreshFeedback();
  refreshExperiments();
  loadReport();
}

function ensureAutoPoll() {
  if (!el.autoPoll.checked) {
    stopPolling();
    return;
  }
  if (state.pollTimer) return;
  state.pollTimer = window.setInterval(() => {
    if (state.currentRunId) {
      pollStatus(state.currentRunId);
    }
  }, 5000);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

async function apiCall(name, args) {
  const res = await fetch(`${state.apiBase}/tools/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, arguments: args || {} }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const payload = await res.json();
  if (!payload.ok) {
    throw new Error(payload.error || "API error");
  }
  return payload.result;
}

async function authLogin() {
  const username = el.loginUsername.value.trim();
  const password = el.loginPassword.value.trim();
  el.loginError.textContent = "";
  if (!username || !password) {
    el.loginError.textContent = "Username and password required.";
    return;
  }
  try {
    const res = await fetch(`${state.apiBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const payload = await res.json();
    if (!payload.ok) {
      throw new Error(payload.error || "Login failed");
    }
    state.token = payload.token;
    state.user = payload.user;
    saveToken(payload.token);
    saveUser(payload.user);
    showChat();
    updateAdminUI();
    refreshRuns();
  } catch (err) {
    el.loginError.textContent = err.message;
  }
}

async function loadSession() {
  if (!state.token) {
    showLogin();
    return;
  }
  try {
    const res = await fetch(`${state.apiBase}/auth/me`, {
      headers: { ...authHeaders() },
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const payload = await res.json();
    if (!payload.ok) {
      throw new Error(payload.error || "Session invalid");
    }
    state.user = payload.user;
    saveUser(payload.user);
    showChat();
    updateAdminUI();
    refreshRuns();
  } catch (err) {
    clearSession();
    showLogin();
  }
}

function resetInputs() {
  resetPlan({ keepMode: true });
  setMessage("Inputs reset. Reconfirm selections and attachments.", "ai");
}

function parsePdbChainRanges(pdbText) {
  const ranges = {};
  const lines = String(pdbText || "").split(/\r?\n/);
  for (const line of lines) {
    if (!(line.startsWith("ATOM") || line.startsWith("HETATM"))) continue;
    const chainId = (line[21] || "").trim() || "_";
    const resSeq = parseInt(line.slice(22, 26).trim(), 10);
    if (!Number.isFinite(resSeq)) continue;
    const entry = ranges[chainId] || { min: resSeq, max: resSeq };
    entry.min = Math.min(entry.min, resSeq);
    entry.max = Math.max(entry.max, resSeq);
    ranges[chainId] = entry;
  }
  return Object.keys(ranges).length ? ranges : null;
}

function updateChainRangesFromText(text) {
  const ranges = parsePdbChainRanges(text);
  if (ranges) {
    state.chainRanges = ranges;
  }
}

function isAnswerMissing(value) {
  if (Array.isArray(value)) return value.length === 0;
  if (value === null || value === undefined) return true;
  return String(value).trim() === "";
}

function renderChoiceButtons(container, options, currentValue, onSelect, { multi = false } = {}) {
  const group = document.createElement("div");
  group.className = "choice-group";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice-btn";
    const isSelected = multi
      ? Array.isArray(currentValue) && currentValue.includes(opt.value)
      : currentValue === opt.value;
    if (isSelected) btn.classList.add("selected");
    btn.textContent = opt.label;
    btn.addEventListener("click", () => {
      onSelect(opt.value);
      renderQuestions(state.plan?.questions || []);
    });
    group.appendChild(btn);
  });
  container.appendChild(group);
}

function renderQuestions(questions) {
  el.questionStack.innerHTML = "";
  if (!questions.length) {
    el.runBtn.disabled = false;
    el.runHint.textContent = "No missing inputs. You can run now.";
    return;
  }

  const fileQuestionIds = new Set([
    "target_input",
    "target_pdb",
    "target_fasta",
    "rfd3_input_pdb",
    "diffdock_ligand",
  ]);

  const choiceQuestionIds = new Set(["run_mode", "stop_after", "design_chains", "rfd3_contig"]);

  const isFileQuestion = (q) => q && fileQuestionIds.has(q.id);
  const isChoiceQuestion = (q) => q && choiceQuestionIds.has(q.id);
  const fileQuestions = [];
  const choiceQuestions = [];

  questions.forEach((q) => {
    if (isFileQuestion(q)) {
      fileQuestions.push(q);
    } else if (isChoiceQuestion(q)) {
      choiceQuestions.push(q);
    }
  });

  choiceQuestions.forEach((q) => {
    const card = document.createElement("div");
    card.className = "question-card" + (q.required ? " required" : "");

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = q.label || q.id || "input";

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = q.question || "";

    card.appendChild(title);
    card.appendChild(help);

    if (q.id === "run_mode") {
      const current = state.runMode || q.default || "pipeline";
      renderChoiceButtons(card, RUN_MODE_OPTIONS, current, (value) => {
        setRunMode(value, { render: false });
        updateRunEligibility(questions);
      });
    }

    if (q.id === "stop_after") {
      const routedDefault = state.plan?.routed_request?.stop_after;
      const current = state.answers.stop_after || routedDefault || q.default || "design";
      state.answers.stop_after = current;
      renderChoiceButtons(
        card,
        [
          { label: "MSA", value: "msa" },
          { label: "Design", value: "design" },
          { label: "SoluProt", value: "soluprot" },
          { label: "AlphaFold2", value: "af2" },
          { label: "Full (Novelty)", value: "novelty" },
        ],
        current,
        (value) => {
          state.answers.stop_after = value;
          updateRunEligibility(questions);
        }
      );
    }

    if (q.id === "design_chains") {
      const chains = state.chainRanges ? Object.keys(state.chainRanges) : [];
      const current = Array.isArray(state.answers.design_chains) ? state.answers.design_chains : [];
      const group = document.createElement("div");
      group.className = "choice-group";

      const allBtn = document.createElement("button");
      allBtn.type = "button";
      allBtn.className = "choice-btn" + (current.length === 0 ? " selected" : "");
      allBtn.textContent = "All chains";
      allBtn.addEventListener("click", () => {
        state.answers.design_chains = [];
        updateRunEligibility(questions);
        renderQuestions(state.plan?.questions || []);
      });
      group.appendChild(allBtn);

      chains.forEach((chain) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "choice-btn" + (current.includes(chain) ? " selected" : "");
        btn.textContent = chain;
        btn.addEventListener("click", () => {
          const next = new Set(current);
          if (next.has(chain)) {
            next.delete(chain);
          } else {
            next.add(chain);
          }
          state.answers.design_chains = Array.from(next);
          updateRunEligibility(questions);
          renderQuestions(state.plan?.questions || []);
        });
        group.appendChild(btn);
      });

      card.appendChild(group);

      if (!chains.length) {
        const note = document.createElement("div");
        note.className = "choice-note";
        note.textContent = "Upload a target PDB to enable chain selection.";
        card.appendChild(note);
      }
    }

    if (q.id === "rfd3_contig") {
      const routedDefault = state.plan?.routed_request?.rfd3_contig;
      if (!state.answers.rfd3_contig && routedDefault) {
        state.answers.rfd3_contig = routedDefault;
      }
      const ranges = state.chainRanges || {};
      const contigs = Object.entries(ranges).map(([chain, range]) => ({
        label: `${chain}${range.min}-${range.max}`,
        value: `${chain}${range.min}-${range.max}`,
      }));
      if (contigs.length) {
        const current = state.answers.rfd3_contig || contigs[0].value;
        state.answers.rfd3_contig = current;
        renderChoiceButtons(card, contigs, current, (value) => {
          state.answers.rfd3_contig = value;
          updateRunEligibility(questions);
        });
      } else {
        const note = document.createElement("div");
        note.className = "choice-note";
        note.textContent = "Upload a PDB to suggest rfd3_contig options.";
        card.appendChild(note);
      }
    }

    el.questionStack.appendChild(card);
  });

  if (fileQuestions.length) {
    const card = document.createElement("div");
    card.className = "question-card attachments";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = "Attachments";

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = "Attach files for the required inputs.";

    const list = document.createElement("div");
    list.className = "attachment-list";

    fileQuestions.forEach((q) => {
      const item = document.createElement("div");
      item.className = "attachment-item" + (q.required ? " required" : "");

      const itemTitle = document.createElement("div");
      itemTitle.className = "attachment-title";
      itemTitle.textContent = q.label || q.id || "file";

      const itemHelp = document.createElement("div");
      itemHelp.className = "attachment-help";
      itemHelp.textContent = q.question || "";

      const controls = document.createElement("div");
      controls.className = "input-row two";

      const fileInput = document.createElement("input");
      fileInput.type = "file";

      const meta = document.createElement("div");
      meta.className = "attachment-meta";
      const existingName = (state.answerMeta[q.id] || {}).fileName;
      if (state.answers[q.id] && existingName) {
        meta.textContent = `Attached: ${existingName}`;
      } else {
        meta.textContent = "No file selected.";
      }

      if (q.id === "diffdock_ligand" && state.runMode === "pipeline") {
        const toggleWrap = document.createElement("div");
        toggleWrap.className = "choice-group";

        const useBtn = document.createElement("button");
        useBtn.type = "button";
        useBtn.className = "choice-btn";
        useBtn.textContent = "Use DiffDock";

        const skipBtn = document.createElement("button");
        skipBtn.type = "button";
        skipBtn.className = "choice-btn selected";
        skipBtn.textContent = "Skip";

        const setMode = (mode) => {
          state.answers.diffdock_use = mode;
          if (mode === "use") {
            useBtn.classList.add("selected");
            skipBtn.classList.remove("selected");
            fileInput.disabled = false;
          } else {
            useBtn.classList.remove("selected");
            skipBtn.classList.add("selected");
            fileInput.value = "";
            fileInput.disabled = true;
            state.answers.diffdock_ligand = "";
            meta.textContent = "No file selected.";
          }
          updateRunEligibility(questions);
        };

        useBtn.addEventListener("click", () => setMode("use"));
        skipBtn.addEventListener("click", () => setMode("skip"));
        toggleWrap.appendChild(useBtn);
        toggleWrap.appendChild(skipBtn);
        item.appendChild(toggleWrap);
        setMode(state.answers.diffdock_use || "skip");
      } else if (q.id === "diffdock_ligand" && state.runMode === "diffdock") {
        state.answers.diffdock_use = "use";
      }

      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "ghost";
      clearBtn.textContent = "Clear";

      fileInput.addEventListener("change", async (event) => {
        const file = event.target.files?.[0];
        if (!file) {
          state.answers[q.id] = "";
          state.answerMeta[q.id] = {};
          meta.textContent = "No file selected.";
          updateRunEligibility(questions);
          return;
        }
        try {
          const text = await file.text();
          state.answers[q.id] = text;
          state.answerMeta[q.id] = { fileName: file.name };
          const kb = Math.max(1, Math.round(file.size / 1024));
          meta.textContent = `Attached: ${file.name} (${kb} KB)`;
          if (q.id === "target_input") {
            const key = detectTargetKey(text);
            if (key === "target_pdb") {
              updateChainRangesFromText(text);
            } else {
              state.chainRanges = null;
            }
            renderQuestions(state.plan?.questions || []);
          }
          if (q.id === "rfd3_input_pdb") {
            updateChainRangesFromText(text);
            renderQuestions(state.plan?.questions || []);
          }
        } catch (err) {
          state.answers[q.id] = "";
          state.answerMeta[q.id] = {};
          meta.textContent = `Failed to read file: ${err.message}`;
        }
        updateRunEligibility(questions);
      });

      clearBtn.addEventListener("click", () => {
        fileInput.value = "";
        state.answers[q.id] = "";
        state.answerMeta[q.id] = {};
        meta.textContent = "No file selected.";
        if (q.id === "target_input" || q.id === "rfd3_input_pdb") {
          state.chainRanges = null;
        }
        updateRunEligibility(questions);
      });

      controls.appendChild(fileInput);
      controls.appendChild(clearBtn);

      item.appendChild(itemTitle);
      item.appendChild(itemHelp);
      item.appendChild(controls);
      item.appendChild(meta);
      list.appendChild(item);
    });

    card.appendChild(title);
    card.appendChild(help);
    card.appendChild(list);
    el.questionStack.appendChild(card);
  }

  updateRunEligibility(questions);
}

function updateRunEligibility(questions) {
  const requiredIds = new Set(
    (questions || [])
      .filter((q) => q.required && q.id !== "run_mode")
      .map((q) => q.id)
  );

  if (state.runMode === "pipeline") {
    const hasRfd3Input = !isAnswerMissing(state.answers.rfd3_input_pdb);
    if (hasRfd3Input) {
      requiredIds.delete("target_input");
      requiredIds.add("rfd3_contig");
    }
    if (state.answers.diffdock_use === "use") {
      requiredIds.add("diffdock_ligand");
    } else {
      requiredIds.delete("diffdock_ligand");
    }
  }

  if (state.runMode === "rfd3") {
    requiredIds.delete("target_input");
    requiredIds.add("rfd3_input_pdb");
    requiredIds.add("rfd3_contig");
  }

  if (state.runMode === "msa") {
    requiredIds.add("target_input");
  }

  if (state.runMode === "design") {
    requiredIds.add("target_input");
  }

  if (state.runMode === "soluprot") {
    requiredIds.add("target_input");
  }

  if (state.runMode === "af2") {
    requiredIds.add("target_input");
  }

  if (state.runMode === "diffdock") {
    requiredIds.add("target_input");
    requiredIds.add("diffdock_ligand");
  }

  const missing = Array.from(requiredIds).filter((id) => isAnswerMissing(state.answers[id]));
  if (missing.length === 0) {
    el.runBtn.disabled = false;
    el.runHint.textContent = "All required inputs captured.";
  } else {
    el.runBtn.disabled = true;
    el.runHint.textContent = "Missing required inputs.";
  }
}

function buildAnswerPayload(mode = state.runMode) {
  const answers = { ...state.answers };
  if (answers.target_input && !answers.target_pdb && !answers.target_fasta) {
    if (mode === "diffdock") {
      answers.target_pdb = answers.target_input;
    } else {
      const key = detectTargetKey(answers.target_input) || "target_pdb";
      answers[key] = answers.target_input;
    }
  }
  delete answers.target_input;
  if (answers.run_mode) {
    delete answers.run_mode;
  }
  if (Array.isArray(answers.design_chains) && answers.design_chains.length === 0) {
    delete answers.design_chains;
  }
  if (answers.diffdock_use) {
    delete answers.diffdock_use;
  }
  if (answers.diffdock_ligand) {
    const name = (state.answerMeta.diffdock_ligand || {}).fileName || "";
    if (name.toLowerCase().endsWith(".sdf")) {
      answers.diffdock_ligand_sdf = answers.diffdock_ligand;
    } else {
      answers.diffdock_ligand_smiles = answers.diffdock_ligand;
    }
    delete answers.diffdock_ligand;
  }
  return answers;
}

function filterAnswersForMode(mode, answers) {
  const allow = {
    pipeline: [
      "target_fasta",
      "target_pdb",
      "rfd3_input_pdb",
      "rfd3_contig",
      "diffdock_ligand_smiles",
      "diffdock_ligand_sdf",
      "design_chains",
      "stop_after",
    ],
    rfd3: ["rfd3_input_pdb", "rfd3_contig"],
    msa: ["target_fasta", "target_pdb"],
    design: ["target_fasta", "target_pdb", "design_chains"],
    soluprot: ["target_fasta", "target_pdb", "design_chains"],
    af2: ["target_fasta", "target_pdb"],
    diffdock: ["target_pdb", "diffdock_ligand_smiles", "diffdock_ligand_sdf"],
  }[mode || "pipeline"] || [];

  const filtered = {};
  allow.forEach((key) => {
    if (answers[key] !== undefined) {
      filtered[key] = answers[key];
    }
  });
  return filtered;
}

async function runPipeline() {
  if (!state.plan) return;
  const prompt = el.promptInput.value.trim();
  const prefix = state.user?.run_prefix || buildUserPrefix({ name: state.user?.username || "user" });
  const runId = createRunId(prefix);
  const mode = state.runMode || "pipeline";
  const rawAnswers = buildAnswerPayload(mode);
  const answers = filterAnswersForMode(mode, rawAnswers);
  let args = {};
  let toolName = "pipeline.run";

  if (mode === "pipeline") {
    args = buildRunArguments({
      prompt,
      routed: state.plan.routed_request || {},
      answers,
      runId,
    });
  } else if (mode === "rfd3") {
    args = buildRunArguments({
      prompt,
      routed: { stop_after: "rfd3" },
      answers,
      runId,
    });
  } else if (mode === "msa") {
    args = buildRunArguments({
      prompt,
      routed: { stop_after: "msa" },
      answers,
      runId,
    });
  } else if (mode === "design") {
    args = buildRunArguments({
      prompt,
      routed: { stop_after: "design" },
      answers,
      runId,
    });
  } else if (mode === "soluprot") {
    args = buildRunArguments({
      prompt,
      routed: { stop_after: "soluprot" },
      answers,
      runId,
    });
  } else if (mode === "af2") {
    toolName = "pipeline.af2_predict";
    args = {
      run_id: runId,
      target_fasta: answers.target_fasta || "",
      target_pdb: answers.target_pdb || "",
    };
  } else if (mode === "diffdock") {
    toolName = "pipeline.diffdock";
    args = {
      run_id: runId,
      protein_pdb: answers.target_pdb || "",
      diffdock_ligand_smiles: answers.diffdock_ligand_smiles || "",
      diffdock_ligand_sdf: answers.diffdock_ligand_sdf || "",
    };
  }

  const modeLabels = {
    pipeline: "pipeline",
    rfd3: "RFD3",
    msa: "MSA",
    design: "ProteinMPNN",
    soluprot: "SoluProt",
    af2: "AlphaFold2",
    diffdock: "DiffDock",
  };
  const modeLabel = modeLabels[mode] || mode;
  setMessage(`Launching ${modeLabel} run ${runId}...`, "ai");
  setCurrentRunId(runId);

  try {
    const result = await apiCall(toolName, args);
    setMessage(`Run started: ${result.run_id}`, "ai");
    setCurrentRunId(result.run_id);
    ensureAutoPoll();
    await pollStatus(result.run_id);
    await refreshRuns();
  } catch (err) {
    setMessage(`Run failed: ${err.message}`, "ai");
  }
}

async function pollStatus(runId) {
  try {
    const result = await apiCall("pipeline.status", { run_id: runId });
    if (!result.found) {
      updateRunInfo({ stage: "-", state: "not found", updated_at: "-" });
      return;
    }
    updateRunInfo(result.status);
    const stage = result.status?.stage || "-";
    const stateText = result.status?.state || "-";
    const key = `${stage}|${stateText}`;
    if (key !== state.lastStatusKey) {
      state.lastStatusKey = key;
      setMessage(`Status: ${stage} / ${stateText}`, "ai");
    }
  } catch (err) {
    setMessage(`Status error: ${err.message}`, "ai");
  }
}

function renderArtifacts(list) {
  const filter = el.artifactFilter.value.trim().toLowerCase();
  el.artifactList.innerHTML = "";
  const filtered = list.filter((item) => {
    if (!filter) return true;
    return String(item.path).toLowerCase().includes(filter);
  });
  if (!filtered.length) {
    el.artifactList.innerHTML = "<div class=\"placeholder\">No artifacts.</div>";
    return;
  }
  filtered.forEach((item) => {
    const div = document.createElement("div");
    div.className = "artifact-item";
    const stage = stageFromPath(item.path);
    div.innerHTML = `
      <span>${item.path}</span>
      <span class=\"stage-tag\">${stage}</span>
    `;
    div.addEventListener("click", () => previewArtifact(item));
    el.artifactList.appendChild(div);
  });
}

async function previewArtifact(item) {
  if (!state.currentRunId) return;
  if (item.type !== "file") return;
  const path = item.path;

  if (/\.pdb$/i.test(path) || /\.sdf$/i.test(path)) {
    try {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: state.currentRunId,
        path,
        max_bytes: 500000,
      });
      const format = /\.sdf$/i.test(path) ? "sdf" : "pdb";
      render3dModel(result.text || "", format);
    } catch (err) {
      el.artifactPreview.innerHTML = `<div class=\"placeholder\">Preview failed: ${err.message}</div>`;
    }
    return;
  }

  if (isImagePath(path)) {
    try {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: state.currentRunId,
        path,
        base64: true,
        max_bytes: 2000000,
      });
      const ext = path.split(".").pop() || "png";
      const img = new Image();
      img.src = `data:image/${ext};base64,${result.base64}`;
      img.className = "preview-image";
      el.artifactPreview.innerHTML = "";
      el.artifactPreview.appendChild(img);
    } catch (err) {
      el.artifactPreview.innerHTML = `<div class=\"placeholder\">Preview failed: ${err.message}</div>`;
    }
    return;
  }

  if (isBinaryPath(path)) {
    el.artifactPreview.innerHTML = `<div class=\"placeholder\">Binary file: ${path}</div>`;
    return;
  }

  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: state.currentRunId,
      path,
      max_bytes: 200000,
    });
    const text = result.text || "";
    el.artifactPreview.innerHTML = `<pre>${escapeHtml(text)}</pre>`;
  } catch (err) {
    el.artifactPreview.innerHTML = `<div class=\"placeholder\">Preview failed: ${err.message}</div>`;
  }
}

function updateReportArtifactLinks(text) {
  if (!el.reportArtifactLinks) return;
  const content = String(text || "");
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  if (!content.trim() || artifacts.length === 0) {
    el.reportArtifactLinks.innerHTML =
      "<div class=\"placeholder\">No artifact references yet.</div>";
    return;
  }
  const matches = [];
  const seen = new Set();
  artifacts.forEach((item) => {
    if (item.type !== "file") return;
    if (content.includes(item.path)) {
      if (!seen.has(item.path)) {
        seen.add(item.path);
        matches.push(item);
      }
    }
  });
  if (!matches.length) {
    el.reportArtifactLinks.innerHTML =
      "<div class=\"placeholder\">No artifact references yet.</div>";
    return;
  }
  matches.sort((a, b) => String(a.path).localeCompare(String(b.path)));
  el.reportArtifactLinks.innerHTML = "";
  matches.forEach((item) => {
    const link = document.createElement("button");
    link.type = "button";
    link.className = "report-link";
    link.innerHTML = `<span>${item.path}</span><span class=\"stage-tag\">${stageFromPath(
      item.path
    )}</span>`;
    link.addEventListener("click", () => previewArtifact(item));
    el.reportArtifactLinks.appendChild(link);
  });
}

function render3dModel(text, format) {
  if (!window.$3Dmol) {
    el.artifactPreview.innerHTML = "<div class=\"placeholder\">3D viewer unavailable.</div>";
    return;
  }
  const container = document.createElement("div");
  container.className = "viewer3d";
  el.artifactPreview.innerHTML = "";
  el.artifactPreview.appendChild(container);
  const viewer = window.$3Dmol.createViewer(container, { backgroundColor: "white" });
  viewer.addModel(text, format);
  if (format === "sdf") {
    viewer.setStyle({}, { stick: { radius: 0.15 } });
  } else {
    viewer.setStyle({}, { cartoon: { color: "spectrum" } });
  }
  viewer.zoomTo();
  viewer.render();
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function refreshArtifacts() {
  if (!state.currentRunId) return;
  try {
    const result = await apiCall("pipeline.list_artifacts", {
      run_id: state.currentRunId,
      max_depth: 6,
      limit: 300,
    });
    state.artifacts = result.artifacts || [];
    renderArtifacts(state.artifacts);
    refreshArtifactSelects();
    updateReportArtifactLinks(el.reportContent ? el.reportContent.value : "");
  } catch (err) {
    setMessage(`Artifact error: ${err.message}`, "ai");
  }
}

function parseMetricsInput(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch (err) {
    return { __parse_error: err.message };
  }
  return { __parse_error: "metrics must be a JSON object" };
}

function normalizeExportValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch (err) {
    return String(value);
  }
}

function escapeDelimitedValue(value, sep) {
  let text = normalizeExportValue(value);
  if (text.includes("\"")) {
    text = text.replace(/\"/g, "\"\"");
  }
  if (text.includes(sep) || text.includes("\n") || text.includes("\r") || text.includes("\"")) {
    return `"${text}"`;
  }
  return text;
}

function buildDelimited(rows, headers, sep) {
  const lines = [];
  lines.push(headers.map((h) => escapeDelimitedValue(h, sep)).join(sep));
  rows.forEach((row) => {
    lines.push(headers.map((h) => escapeDelimitedValue(row[h], sep)).join(sep));
  });
  return `${lines.join("\n")}\n`;
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function buildExportFilename(prefix, ext) {
  const stamp = new Date().toISOString().slice(0, 10);
  const safeRun = sanitizeName(state.currentRunId || "run") || "run";
  const safePrefix = sanitizeName(prefix) || "export";
  return `${safePrefix}_${safeRun}_${stamp}.${ext}`;
}

async function exportFeedback(format) {
  if (!state.currentRunId) {
    if (el.feedbackStatus) el.feedbackStatus.textContent = "Select a run first.";
    return;
  }
  const sep = format === "tsv" ? "\t" : ",";
  const ext = format === "tsv" ? "tsv" : "csv";
  if (el.feedbackStatus) el.feedbackStatus.textContent = "Exporting...";
  try {
    const result = await apiCall("pipeline.list_feedback", {
      run_id: state.currentRunId,
      limit: EXPORT_LIMIT,
    });
    const items = result.items || [];
    if (!items.length) {
      if (el.feedbackStatus) el.feedbackStatus.textContent = "No feedback to export.";
      return;
    }
    const rows = items.map((item) => ({
      id: item.id || "",
      run_id: item.run_id || state.currentRunId,
      rating: item.rating || "",
      reasons: Array.isArray(item.reasons) ? item.reasons.join(",") : item.reasons || "",
      comment: item.comment || "",
      artifact_path: item.artifact_path || "",
      stage: item.stage || "",
      metrics: item.metrics || "",
      user: item.user || "",
      created_at: item.created_at || "",
    }));
    const headers = [
      "id",
      "run_id",
      "rating",
      "reasons",
      "comment",
      "artifact_path",
      "stage",
      "metrics",
      "user",
      "created_at",
    ];
    const content = buildDelimited(rows, headers, sep);
    downloadTextFile(buildExportFilename("feedback", ext), content);
    if (el.feedbackStatus) el.feedbackStatus.textContent = `Exported ${rows.length} rows.`;
  } catch (err) {
    if (el.feedbackStatus) el.feedbackStatus.textContent = `Export failed: ${err.message}`;
  }
}

async function exportExperiments(format) {
  if (!state.currentRunId) {
    if (el.experimentStatus) el.experimentStatus.textContent = "Select a run first.";
    return;
  }
  const sep = format === "tsv" ? "\t" : ",";
  const ext = format === "tsv" ? "tsv" : "csv";
  if (el.experimentStatus) el.experimentStatus.textContent = "Exporting...";
  try {
    const result = await apiCall("pipeline.list_experiments", {
      run_id: state.currentRunId,
      limit: EXPORT_LIMIT,
    });
    const items = result.items || [];
    if (!items.length) {
      if (el.experimentStatus) el.experimentStatus.textContent = "No experiments to export.";
      return;
    }
    const rows = items.map((item) => ({
      id: item.id || "",
      run_id: item.run_id || state.currentRunId,
      assay_type: item.assay_type || "",
      result: item.result || "",
      sample_id: item.sample_id || "",
      artifact_path: item.artifact_path || "",
      metrics: item.metrics || "",
      conditions: item.conditions || "",
      note: item.note || "",
      user: item.user || "",
      created_at: item.created_at || "",
    }));
    const headers = [
      "id",
      "run_id",
      "assay_type",
      "result",
      "sample_id",
      "artifact_path",
      "metrics",
      "conditions",
      "note",
      "user",
      "created_at",
    ];
    const content = buildDelimited(rows, headers, sep);
    downloadTextFile(buildExportFilename("experiments", ext), content);
    if (el.experimentStatus) el.experimentStatus.textContent = `Exported ${rows.length} rows.`;
  } catch (err) {
    if (el.experimentStatus) el.experimentStatus.textContent = `Export failed: ${err.message}`;
  }
}

async function submitFeedback() {
  if (!state.currentRunId) {
    if (el.feedbackStatus) el.feedbackStatus.textContent = "Select a run first.";
    return;
  }
  const payload = {
    run_id: state.currentRunId,
    rating: state.feedbackRating || "good",
    reasons: state.feedbackReasons || [],
    comment: el.feedbackComment ? el.feedbackComment.value.trim() : "",
    artifact_path: el.feedbackArtifact ? el.feedbackArtifact.value.trim() : "",
    stage: el.feedbackStage ? el.feedbackStage.value.trim() : "",
  };
  try {
    await apiCall("pipeline.submit_feedback", payload);
    if (el.feedbackStatus) el.feedbackStatus.textContent = "Feedback saved.";
    if (el.feedbackComment) el.feedbackComment.value = "";
    state.feedbackReasons = [];
    renderFeedbackControls();
    await refreshFeedback();
    await loadReport();
  } catch (err) {
    if (el.feedbackStatus) el.feedbackStatus.textContent = `Failed: ${err.message}`;
  }
}

async function refreshFeedback() {
  if (!state.currentRunId || !el.feedbackList) return;
  try {
    const result = await apiCall("pipeline.list_feedback", {
      run_id: state.currentRunId,
      limit: 5,
    });
    const items = result.items || [];
    if (!items.length) {
      el.feedbackList.innerHTML = "<div class=\"placeholder\">No feedback yet.</div>";
      return;
    }
    el.feedbackList.innerHTML = "";
    items.forEach((item) => {
      const div = document.createElement("div");
      div.className = "run-item";
      const rating = item.rating || "-";
      const reason = Array.isArray(item.reasons) ? item.reasons.join(", ") : "";
      const comment = item.comment ? ` · ${item.comment}` : "";
      div.innerHTML = `<span>${rating}${comment}</span><span class="stage-tag">${reason || "-"}</span>`;
      el.feedbackList.appendChild(div);
    });
  } catch (err) {
    const msg = String(err.message || "");
    if (msg.includes("run_id not found")) {
      el.feedbackList.innerHTML = "<div class=\"placeholder\">No feedback yet.</div>";
    } else {
      el.feedbackList.innerHTML = `<div class="placeholder">Load failed: ${err.message}</div>`;
    }
  }
}

async function submitExperiment() {
  if (!state.currentRunId) {
    if (el.experimentStatus) el.experimentStatus.textContent = "Select a run first.";
    return;
  }
  const metricsInput = parseMetricsInput(el.experimentMetrics ? el.experimentMetrics.value : "");
  if (metricsInput && metricsInput.__parse_error) {
    if (el.experimentStatus) el.experimentStatus.textContent = metricsInput.__parse_error;
    return;
  }
  const payload = {
    run_id: state.currentRunId,
    assay_type: el.experimentAssay ? el.experimentAssay.value : "other",
    result: el.experimentResult ? el.experimentResult.value : "inconclusive",
    sample_id: el.experimentSampleId ? el.experimentSampleId.value.trim() : "",
    artifact_path: el.experimentArtifact ? el.experimentArtifact.value.trim() : "",
    metrics: metricsInput || undefined,
    conditions: el.experimentConditions ? el.experimentConditions.value.trim() : "",
  };
  try {
    await apiCall("pipeline.submit_experiment", payload);
    if (el.experimentStatus) el.experimentStatus.textContent = "Experiment saved.";
    if (el.experimentMetrics) el.experimentMetrics.value = "";
    if (el.experimentConditions) el.experimentConditions.value = "";
    if (el.experimentSampleId) el.experimentSampleId.value = "";
    await refreshExperiments();
    await loadReport();
  } catch (err) {
    if (el.experimentStatus) el.experimentStatus.textContent = `Failed: ${err.message}`;
  }
}

async function refreshExperiments() {
  if (!state.currentRunId || !el.experimentList) return;
  try {
    const result = await apiCall("pipeline.list_experiments", {
      run_id: state.currentRunId,
      limit: 5,
    });
    const items = result.items || [];
    if (!items.length) {
      el.experimentList.innerHTML = "<div class=\"placeholder\">No experiments yet.</div>";
      return;
    }
    el.experimentList.innerHTML = "";
    items.forEach((item) => {
      const div = document.createElement("div");
      div.className = "run-item";
      const resultLabel = item.result || "-";
      const assay = item.assay_type || "-";
      div.innerHTML = `<span>${assay}</span><span class="stage-tag">${resultLabel}</span>`;
      el.experimentList.appendChild(div);
    });
  } catch (err) {
    const msg = String(err.message || "");
    if (msg.includes("run_id not found")) {
      el.experimentList.innerHTML = "<div class=\"placeholder\">No experiments yet.</div>";
    } else {
      el.experimentList.innerHTML = `<div class="placeholder">Load failed: ${err.message}</div>`;
    }
  }
}

function formatScoreValues(result) {
  const score =
    result && result.score !== undefined && result.score !== null ? result.score : "-";
  const evidence = result && result.evidence ? result.evidence : "-";
  const recommendation = result && result.recommendation ? result.recommendation : "-";
  return { score, evidence, recommendation };
}

function updateRunScore(result) {
  if (!el.runScoreValue || !el.runEvidenceValue || !el.runRecommendationValue) return;
  const { score, evidence, recommendation } = formatScoreValues(result);
  el.runScoreValue.textContent = `Score: ${score}`;
  el.runEvidenceValue.textContent = `Evidence: ${evidence}`;
  el.runRecommendationValue.textContent = `Recommendation: ${recommendation}`;
}

function updateReportScore(result) {
  if (!el.reportScoreValue || !el.reportEvidenceValue || !el.reportRecommendationValue) return;
  const { score, evidence, recommendation } = formatScoreValues(result);
  el.reportScoreValue.textContent = `Score: ${score}`;
  el.reportEvidenceValue.textContent = `Evidence: ${evidence}`;
  el.reportRecommendationValue.textContent = `Recommendation: ${recommendation}`;
  updateRunScore(result);
}

async function loadReport() {
  if (!state.currentRunId || !el.reportContent) return;
  try {
    const result = await apiCall("pipeline.get_report", { run_id: state.currentRunId });
    el.reportContent.value = result.report || "";
    updateReportScore(result);
    updateReportArtifactLinks(result.report || "");
    if (el.reportStatus) el.reportStatus.textContent = "Report loaded.";
  } catch (err) {
    const msg = String(err.message || "");
    if (msg.includes("run_id not found")) {
      if (el.reportStatus) el.reportStatus.textContent = "Report not available yet.";
      if (el.reportContent) el.reportContent.value = "";
      updateReportScore({});
      updateReportArtifactLinks("");
    } else if (el.reportStatus) {
      el.reportStatus.textContent = `Load failed: ${err.message}`;
    }
  }
}

async function generateReport() {
  if (!state.currentRunId || !el.reportContent) return;
  try {
    const result = await apiCall("pipeline.generate_report", { run_id: state.currentRunId });
    el.reportContent.value = result.report || "";
    updateReportScore(result);
    updateReportArtifactLinks(result.report || "");
    if (el.reportStatus) el.reportStatus.textContent = "Report generated.";
  } catch (err) {
    if (el.reportStatus) el.reportStatus.textContent = `Generate failed: ${err.message}`;
  }
}

async function saveReport() {
  if (!state.currentRunId || !el.reportContent) return;
  const content = el.reportContent.value.trim();
  if (!content) {
    if (el.reportStatus) el.reportStatus.textContent = "Report content is empty.";
    return;
  }
  try {
    await apiCall("pipeline.save_report", { run_id: state.currentRunId, content });
    if (el.reportStatus) el.reportStatus.textContent = "Report saved.";
    updateReportArtifactLinks(content);
  } catch (err) {
    if (el.reportStatus) el.reportStatus.textContent = `Save failed: ${err.message}`;
  }
}

async function refreshRuns() {
  if (!state.user) return;
  try {
    const result = await apiCall("pipeline.list_runs", { limit: 30 });
    let runs = result.runs || [];
    if (state.user.role !== "admin" || !el.showAllRuns.checked) {
      const prefix = state.user.run_prefix || buildUserPrefix({ name: state.user.username || "user" });
      runs = filterRunsByPrefix(runs, prefix);
    }
    renderRuns(runs);
  } catch (err) {
    // ignore errors here
  }
}

function renderRuns(runs) {
  el.runList.innerHTML = "";
  if (!runs.length) {
    el.runList.innerHTML = "<div class=\"placeholder\">No runs yet.</div>";
    return;
  }
  runs.forEach((runId) => {
    const div = document.createElement("div");
    div.className = "run-item";
    div.innerHTML = `<span>${runId}</span><span class=\"stage-tag\">load</span>`;
    div.addEventListener("click", async () => {
      setCurrentRunId(runId);
      await pollStatus(runId);
      await refreshArtifacts();
      ensureAutoPoll();
    });
    el.runList.appendChild(div);
  });
}

async function healthCheck() {
  el.healthStatus.textContent = "Checking...";
  try {
    const res = await fetch(`${state.apiBase}/healthz`);
    if (res.ok) {
      el.healthStatus.textContent = "OK";
    } else {
      el.healthStatus.textContent = `HTTP ${res.status}`;
    }
  } catch (err) {
    el.healthStatus.textContent = err.message;
  }
}

async function createUser() {
  el.adminStatus.textContent = "";
  const username = el.adminUsername.value.trim();
  const password = el.adminPassword.value.trim();
  const role = el.adminRole.value;
  if (!username || !password) {
    el.adminStatus.textContent = "Username and password required.";
    return;
  }
  try {
    const res = await fetch(`${state.apiBase}/auth/create_user`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ username, password, role }),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const payload = await res.json();
    if (!payload.ok) {
      throw new Error(payload.error || "Create user failed");
    }
    el.adminStatus.textContent = `Created ${payload.user.username}.`;
    el.adminUsername.value = "";
    el.adminPassword.value = "";
  } catch (err) {
    el.adminStatus.textContent = err.message;
  }
}

el.loginBtn.addEventListener("click", authLogin);

el.logoutBtn.addEventListener("click", () => {
  clearSession();
  showLogin();
});

el.planBtn.addEventListener("click", resetInputs);

el.clearBtn.addEventListener("click", () => {
  el.promptInput.value = "";
  el.messages.innerHTML = "";
  resetPlan();
});

el.runBtn.addEventListener("click", runPipeline);

el.pollBtn.addEventListener("click", () => {
  if (state.currentRunId) {
    pollStatus(state.currentRunId);
  }
});

el.autoPoll.addEventListener("change", () => {
  ensureAutoPoll();
});

el.refreshArtifacts.addEventListener("click", refreshArtifacts);

el.artifactFilter.addEventListener("input", () => {
  renderArtifacts(state.artifacts);
});

if (el.settingsBtn && el.settingsPanel) {
  el.settingsBtn.addEventListener("click", () => {
    el.settingsPanel.classList.toggle("hidden");
    if (el.apiBaseValue) {
      el.apiBaseValue.textContent = state.apiBase;
    }
  });
}

if (el.healthCheck) {
  el.healthCheck.addEventListener("click", healthCheck);
}

if (el.settingsPanel) {
  el.settingsPanel.addEventListener("click", (event) => {
    if (event.target === el.settingsPanel) {
      el.settingsPanel.classList.add("hidden");
    }
  });
}

if (el.adminCreateUser) {
  el.adminCreateUser.addEventListener("click", createUser);
}

if (el.showAllRuns) {
  el.showAllRuns.addEventListener("change", refreshRuns);
}

if (el.submitFeedback) {
  el.submitFeedback.addEventListener("click", submitFeedback);
}

if (el.exportFeedbackCsv) {
  el.exportFeedbackCsv.addEventListener("click", () => exportFeedback("csv"));
}

if (el.exportFeedbackTsv) {
  el.exportFeedbackTsv.addEventListener("click", () => exportFeedback("tsv"));
}

if (el.submitExperiment) {
  el.submitExperiment.addEventListener("click", submitExperiment);
}

if (el.exportExperimentCsv) {
  el.exportExperimentCsv.addEventListener("click", () => exportExperiments("csv"));
}

if (el.exportExperimentTsv) {
  el.exportExperimentTsv.addEventListener("click", () => exportExperiments("tsv"));
}

if (el.loadReport) {
  el.loadReport.addEventListener("click", loadReport);
}

if (el.generateReport) {
  el.generateReport.addEventListener("click", generateReport);
}

if (el.saveReport) {
  el.saveReport.addEventListener("click", saveReport);
}

if (el.reportContent) {
  el.reportContent.addEventListener("input", () => {
    updateReportArtifactLinks(el.reportContent.value);
  });
}

if (state.user && state.token) {
  loadSession();
} else {
  showLogin();
}

initFeedbackUI();
ensureAutoPoll();
