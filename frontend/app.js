import {
  buildRunArguments,
  buildUserPrefix,
  createRunId,
  detectTargetKey,
  filterRunsByPrefix,
  isBinaryPath,
  isImagePath,
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
  pollBtn: document.getElementById("pollBtn"),
  autoPoll: document.getElementById("autoPoll"),
  artifactList: document.getElementById("artifactList"),
  artifactFilter: document.getElementById("artifactFilter"),
  refreshArtifacts: document.getElementById("refreshArtifacts"),
  artifactPreview: document.getElementById("artifactPreview"),
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

function resetPlan() {
  state.plan = null;
  state.answers = {};
  state.answerMeta = {};
  state.chainRanges = null;
  el.questionStack.innerHTML = "";
  el.runBtn.disabled = true;
  el.runHint.textContent = "Complete required inputs to enable execution.";
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

async function planPrompt() {
  const prompt = el.promptInput.value.trim();
  if (!prompt) {
    setMessage("Please enter a prompt to plan.", "ai");
    return;
  }
  setMessage(prompt, "user");
  setMessage("Planning inputs...", "ai");

  resetPlan();
  state.plan = null;

  try {
    const result = await apiCall("pipeline.plan_from_prompt", { prompt });
    state.plan = result;
    setMessage("Plan ready. Fill the requested inputs.", "ai");
    renderQuestions(result.questions || []);
  } catch (err) {
    setMessage(`Plan failed: ${err.message}`, "ai");
  }
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

  const choiceQuestionIds = new Set(["stop_after", "design_chains", "rfd3_contig"]);

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
    title.textContent = q.id || "input";

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = q.question || "";

    card.appendChild(title);
    card.appendChild(help);

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
    help.textContent = "Attach files for the required inputs after reviewing the plan.";

    const list = document.createElement("div");
    list.className = "attachment-list";

    fileQuestions.forEach((q) => {
      const item = document.createElement("div");
      item.className = "attachment-item" + (q.required ? " required" : "");

      const itemTitle = document.createElement("div");
      itemTitle.className = "attachment-title";
      itemTitle.textContent = q.id || "file";

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

      if (q.id === "diffdock_ligand") {
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
  const requiredIds = new Set((questions || []).filter((q) => q.required).map((q) => q.id));
  if (state.answers.diffdock_use === "use") {
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

function buildAnswerPayload() {
  const answers = { ...state.answers };
  if (answers.target_input && !answers.target_pdb && !answers.target_fasta) {
    const key = detectTargetKey(answers.target_input) || "target_pdb";
    answers[key] = answers.target_input;
  }
  delete answers.target_input;
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

async function runPipeline() {
  if (!state.plan) return;
  const prompt = el.promptInput.value.trim();
  const prefix = state.user?.run_prefix || buildUserPrefix({ name: state.user?.username || "user" });
  const runId = createRunId(prefix);
  const answers = buildAnswerPayload();
  const args = buildRunArguments({
    prompt,
    routed: state.plan.routed_request || {},
    answers,
    runId,
  });

  setMessage(`Launching run ${runId}...`, "ai");
  setCurrentRunId(runId);

  try {
    const result = await apiCall("pipeline.run", args);
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
  } catch (err) {
    setMessage(`Artifact error: ${err.message}`, "ai");
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

el.planBtn.addEventListener("click", planPrompt);

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

if (state.user && state.token) {
  loadSession();
} else {
  showLogin();
}

ensureAutoPoll();
