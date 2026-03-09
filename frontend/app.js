import {
  artifactMetaFromPath,
  buildRunArguments,
  buildUserPrefix,
  createRunId,
  detectTargetKey,
  displayArtifactPath,
  filterRunsByPrefix,
  inferRequestRunMode,
  isBinaryPath,
  isImagePath,
  sanitizeName,
  stageFromPath,
} from "./lib/pipeline.js";
import { extractDesignChainsFromPayload, filterPdbTextByChains, selectResidueStripMetrics } from "./lib/compare.js";

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

const LANG_KEY = "kbf.lang";
const LANG_OPTIONS = ["en", "ko"];
const REPORT_LANG_KEY = "kbf.reportLang";
const REPORT_LANG_OPTIONS = ["auto", "en", "ko"];
const WORKFLOW_PLAN_STORAGE_KEY = "kbf.workflowPlans";
const DEFAULT_WORKFLOW_STAGES = ["msa", "rfd3", "bioemu", "design", "soluprot", "af2", "novelty"];

function loadLang() {
  const saved = localStorage.getItem(LANG_KEY);
  if (LANG_OPTIONS.includes(saved)) return saved;
  const browser = String(navigator.language || "").toLowerCase();
  if (browser.startsWith("ko")) return "ko";
  return "en";
}

function loadReportLang() {
  const saved = localStorage.getItem(REPORT_LANG_KEY);
  if (REPORT_LANG_OPTIONS.includes(saved)) return saved;
  return "auto";
}

function normalizeReportLang(value) {
  return REPORT_LANG_OPTIONS.includes(value) ? value : "auto";
}

function resolveReportLang(value) {
  const pref = normalizeReportLang(value || state.reportLang);
  return pref === "auto" ? state.lang : pref;
}

function updateReportLangSelect() {
  if (el.reportLangSelect) {
    el.reportLangSelect.value = normalizeReportLang(state.reportLang);
  }
}

function setReportLang(value) {
  const next = normalizeReportLang(value);
  state.reportLang = next;
  localStorage.setItem(REPORT_LANG_KEY, next);
  updateReportLangSelect();
}

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

function createSetupResiduePickerState() {
  return {
    pdbText: "",
    sourceLabel: "",
    sourceKey: "",
    selection: {},
    residueOrderByChain: {},
    notice: "",
    runningAf2: false,
  };
}

function createArtifactFilterState() {
  return {
    stage: "all",
    tier: "all",
    type: "all",
  };
}

function normalizeWorkflowStageList(value) {
  const source = Array.isArray(value) ? value : DEFAULT_WORKFLOW_STAGES;
  const out = [];
  source.forEach((item) => {
    const stage = String(item || "")
      .trim()
      .toLowerCase();
    if (!DEFAULT_WORKFLOW_STAGES.includes(stage)) return;
    if (!out.includes(stage)) out.push(stage);
  });
  if (!out.length) return ["msa", "design", "soluprot", "af2"];
  return out;
}

function workflowCheckpointCandidates(nodes) {
  const orderedNodes = normalizeWorkflowStageList(nodes);
  if (orderedNodes.length <= 1) return [];
  return orderedNodes.slice(0, -1);
}

function normalizeWorkflowCheckpointList(value, nodes, { ensureDefault = false } = {}) {
  const candidates = workflowCheckpointCandidates(nodes);
  const source = Array.isArray(value) ? value : value ? [value] : [];
  const out = [];
  source.forEach((item) => {
    const stage = String(item || "")
      .trim()
      .toLowerCase();
    if (!candidates.includes(stage)) return;
    if (!out.includes(stage)) out.push(stage);
  });
  if (!out.length && ensureDefault && candidates.length) {
    out.push(candidates[candidates.length - 1]);
  }
  return out;
}

function createWorkflowDesignerState() {
  const nodes = normalizeWorkflowStageList(DEFAULT_WORKFLOW_STAGES);
  return {
    nodes,
    checkpointEnabled: false,
    checkpointStages: [],
    graphEnabled: true,
    mmseqLoopEnabled: true,
    flowPulse: 0,
  };
}

function loadWorkflowPlansByRunId() {
  const raw = localStorage.getItem(WORKFLOW_PLAN_STORAGE_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out = {};
    Object.entries(parsed).forEach(([runId, item]) => {
      const key = String(runId || "").trim();
      if (!key) return;
      const payload = item && typeof item === "object" && !Array.isArray(item) ? item : {};
      const nodes = normalizeWorkflowStageList(payload.nodes);
      const checkpointEnabled = Boolean(payload.checkpointEnabled);
      const legacyCheckpointStage = String(payload.checkpointStage || "")
        .trim()
        .toLowerCase();
      const checkpointStages = checkpointEnabled
        ? normalizeWorkflowCheckpointList(
            [
              ...(Array.isArray(payload.checkpointStages) ? payload.checkpointStages : []),
              legacyCheckpointStage,
            ],
            nodes
          )
        : [];
      let checkpointIndex = Number(payload.checkpointIndex);
      if (!Number.isFinite(checkpointIndex)) {
        if (Object.prototype.hasOwnProperty.call(payload, "checkpointConsumed")) {
          checkpointIndex = payload.checkpointConsumed ? checkpointStages.length : 0;
        } else if (legacyCheckpointStage) {
          const legacyIndex = checkpointStages.indexOf(legacyCheckpointStage);
          checkpointIndex = legacyIndex >= 0 ? legacyIndex : 0;
        } else {
          checkpointIndex = 0;
        }
      }
      checkpointIndex = Math.max(0, Math.min(checkpointStages.length, Math.trunc(checkpointIndex)));
      out[key] = {
        nodes,
        finalStopAfter: String(payload.finalStopAfter || nodes[nodes.length - 1] || "novelty")
          .trim()
          .toLowerCase(),
        checkpointEnabled: checkpointStages.length > 0,
        checkpointStages,
        checkpointIndex,
        graphEnabled: payload.graphEnabled !== false,
        mmseqLoopEnabled: payload.mmseqLoopEnabled !== false,
      };
    });
    return out;
  } catch (_err) {
    return {};
  }
}

const state = {
  apiBase: resolveApiBase(),
  user: loadUser(),
  token: localStorage.getItem("kbf.token") || "",
  lang: loadLang(),
  reportLang: loadReportLang(),
  plan: null,
  runMode: "pipeline",
  feedbackRating: "good",
  feedbackReasons: [],
  reportReviewRating: "good",
  reportReviewReasons: [],
  answers: {},
  currentRunId: null,
  currentRunState: "",
  runSubmitting: false,
  pollTimer: null,
  pollCyclePromise: null,
  lastStatusKey: "",
  answerMeta: {},
  chainRanges: null,
  artifacts: [],
  artifactRefreshAtByRunId: {},
  artifactRefreshStatusKeyByRunId: {},
  artifactMetaByPath: {},
  artifactFiltersByView: {
    monitor: createArtifactFilterState(),
    analyze: createArtifactFilterState(),
  },
  artifactComparison: null,
  artifactComparisonRunId: "",
  monitorNeedsReport: false,
  monitorCompleteness: null,
  analyzeArtifactPath: "",
  artifactCompareLeftPath: "",
  artifactCompareRightPath: "",
  artifactCompareMode: "structure",
  compareTargetSequenceByRunId: {},
  compareInputPdbTextByRunId: {},
  compareWorkingPdbTextByRunId: {},
  compareWtPdbTextByRunId: {},
  compareWtMetricsByRunId: {},
  compareDesignChainsByKey: {},
  compareFixedCountByKey: {},
  compareAf2ScoresByKey: {},
  runCompareBaselineId: "",
  runCompareResult: null,
  hitListResult: null,
  hitListRows: [],
  hitListCutoff: 0,
  hitListLimit: 120,
  chartView: "plddt_rmsd",
  hitListWeights: {
    soluprot: 0.4,
    plddt: 0.3,
    rmsd: 0.2,
    novelty: 0,
  },
  runs: [],
  runModeById: {},
  af2ProviderByRunId: {},
  progressByRunId: {},
  progressContextByRunId: {},
  timingByRunId: {},
  feedbackCount: 0,
  experimentCount: 0,
  lastScore: null,
  lastRunStatus: null,
  reportModalText: "",
  reportModalMode: "rendered",
  reportModalFilename: "report.md",
  reportModalRenderToken: 0,
  reportModalImageCache: {},
  copilotHistory: [],
  setupResiduePicker: createSetupResiduePickerState(),
  setupStepIndex: 0,
  autoAnalyzePendingByRunId: {},
  workflowDesigner: createWorkflowDesignerState(),
  workflowPlansByRunId: loadWorkflowPlansByRunId(),
};

if (state.apiBase && state.apiBase !== normalizeApiBase(savedApiBase)) {
  localStorage.setItem("kbf.apiBase", state.apiBase);
}

function persistWorkflowPlans() {
  try {
    localStorage.setItem(WORKFLOW_PLAN_STORAGE_KEY, JSON.stringify(state.workflowPlansByRunId || {}));
  } catch (_err) {
    // Ignore localStorage quota/transient errors.
  }
}

const el = {
  loginGate: document.getElementById("loginGate"),
  appShell: document.getElementById("appShell"),
  loginUsername: document.getElementById("loginUsername"),
  loginPassword: document.getElementById("loginPassword"),
  loginBtn: document.getElementById("loginBtn"),
  loginError: document.getElementById("loginError"),
  logoutBtn: document.getElementById("logoutBtn"),
  adminBtn: document.getElementById("adminBtn"),
  helpBtn: document.getElementById("helpBtn"),
  copilotOpenBtn: document.getElementById("copilotOpenBtn"),
  copilotFabBtn: document.getElementById("copilotFabBtn"),
  chatArea: document.getElementById("chatArea"),
  userBadge: document.getElementById("userBadge"),
  messages: document.getElementById("messages"),
  monitorMessages: document.getElementById("monitorMessages"),
  promptInput: document.getElementById("promptInput"),
  checkBtn: document.getElementById("checkBtn"),
  planBtn: document.getElementById("planBtn"),
  clearBtn: document.getElementById("clearBtn"),
  questionStack: document.getElementById("questionStack"),
  questionInputStack: document.getElementById("questionInputStack"),
  questionConfigStack: document.getElementById("questionConfigStack"),
  setupStepper: document.getElementById("setupStepper"),
  setupStepMeta: document.getElementById("setupStepMeta"),
  setupStepDots: document.getElementById("setupStepDots"),
  setupStepPrev: document.getElementById("setupStepPrev"),
  setupStepNext: document.getElementById("setupStepNext"),
  setupRunSelector: document.getElementById("setupRunSelector"),
  setupContextStageValue: document.getElementById("setupContextStageValue"),
  setupContextStateValue: document.getElementById("setupContextStateValue"),
  runBtn: document.getElementById("runBtn"),
  runHint: document.getElementById("runHint"),
  runInlineStatus: document.getElementById("runInlineStatus"),
  setupRunIdValue: document.getElementById("setupRunIdValue"),
  setupRunStageValue: document.getElementById("setupRunStageValue"),
  setupRunStateValue: document.getElementById("setupRunStateValue"),
  setupRunUpdatedValue: document.getElementById("setupRunUpdatedValue"),
  setupRunEtaValue: document.getElementById("setupRunEtaValue"),
  setupPollBtn: document.getElementById("setupPollBtn"),
  setupMonitorTabBtn: document.getElementById("setupMonitorTabBtn"),
  setupErrorDetails: document.getElementById("setupErrorDetails"),
  setupErrorSummary: document.getElementById("setupErrorSummary"),
  setupErrorRaw: document.getElementById("setupErrorRaw"),
  runIdValue: document.getElementById("runIdValue"),
  runSelector: document.getElementById("runSelector"),
  runStageValue: document.getElementById("runStageValue"),
  runStateValue: document.getElementById("runStateValue"),
  runUpdatedValue: document.getElementById("runUpdatedValue"),
  analyzeRunSelector: document.getElementById("analyzeRunSelector"),
  analyzeContextStageValue: document.getElementById("analyzeContextStageValue"),
  analyzeContextStateValue: document.getElementById("analyzeContextStateValue"),
  runDetailValue: document.getElementById("runDetailValue"),
  runErrorDetails: document.getElementById("runErrorDetails"),
  runErrorSummary: document.getElementById("runErrorSummary"),
  runErrorRaw: document.getElementById("runErrorRaw"),
  runProgressLabel: document.getElementById("runProgressLabel"),
  runProgressPercent: document.getElementById("runProgressPercent"),
  runProgressFill: document.getElementById("runProgressFill"),
  runProgressStages: document.getElementById("runProgressStages"),
  runScoreValue: document.getElementById("runScoreValue"),
  runEvidenceValue: document.getElementById("runEvidenceValue"),
  runRecommendationValue: document.getElementById("runRecommendationValue"),
  monitorCompletenessBadges: document.getElementById("monitorCompletenessBadges"),
  workflowReviewPanel: document.getElementById("workflowReviewPanel"),
  pollBtn: document.getElementById("pollBtn"),
  cancelRunBtn: document.getElementById("cancelRunBtn"),
  resumeRunBtn: document.getElementById("resumeRunBtn"),
  autoPoll: document.getElementById("autoPoll"),
  refreshRunsBtn: document.getElementById("refreshRunsBtn"),
  clearMonitorMessages: document.getElementById("clearMonitorMessages"),
  clearMonitorMessagesMonitor: document.getElementById("clearMonitorMessagesMonitor"),
  artifactList: document.getElementById("artifactList"),
  artifactFilter: document.getElementById("artifactFilter"),
  artifactStageFilter: document.getElementById("artifactStageFilter"),
  artifactTierFilter: document.getElementById("artifactTierFilter"),
  artifactTypeFilter: document.getElementById("artifactTypeFilter"),
  refreshArtifacts: document.getElementById("refreshArtifacts"),
  monitorArtifactPreview: document.getElementById("monitorArtifactPreview"),
  compareStudioPreview: document.getElementById("compareStudioPreview"),
  analyzeArtifactList: document.getElementById("analyzeArtifactList"),
  analyzeArtifactFilter: document.getElementById("analyzeArtifactFilter"),
  analyzeArtifactStageFilter: document.getElementById("analyzeArtifactStageFilter"),
  analyzeArtifactTierFilter: document.getElementById("analyzeArtifactTierFilter"),
  analyzeArtifactTypeFilter: document.getElementById("analyzeArtifactTypeFilter"),
  analyzeRefreshArtifacts: document.getElementById("analyzeRefreshArtifacts"),
  analyzeArtifactPreview: document.getElementById("analyzeArtifactPreview"),
  artifactComparisonSummary: document.getElementById("artifactComparisonSummary"),
  artifactCompareMode: document.getElementById("artifactCompareMode"),
  artifactCompareLeft: document.getElementById("artifactCompareLeft"),
  artifactCompareRight: document.getElementById("artifactCompareRight"),
  artifactCompareSwap: document.getElementById("artifactCompareSwap"),
  artifactCompareRun: document.getElementById("artifactCompareRun"),
  artifactCompareClear: document.getElementById("artifactCompareClear"),
  artifactCompareRefs: document.getElementById("artifactCompareRefs"),
  artifactComparePresets: document.getElementById("artifactComparePresets"),
  artifactComparisonDetails: document.getElementById("artifactComparisonDetails"),
  artifactGenerateReport: document.getElementById("artifactGenerateReport"),
  agentPanelList: document.getElementById("agentPanelList"),
  agentPanelStatus: document.getElementById("agentPanelStatus"),
  viewRunReport: document.getElementById("viewRunReport"),
  viewAgentReport: document.getElementById("viewAgentReport"),
  reportModal: document.getElementById("reportModal"),
  reportModalTitle: document.getElementById("reportModalTitle"),
  reportModalContent: document.getElementById("reportModalContent"),
  reportModalToggle: document.getElementById("reportModalToggle"),
  reportModalDownload: document.getElementById("reportModalDownload"),
  reportModalClose: document.getElementById("reportModalClose"),
  refreshAgentPanel: document.getElementById("refreshAgentPanel"),
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
  viewReportRendered: document.getElementById("viewReportRendered"),
  exportRunPackage: document.getElementById("exportRunPackage"),
  saveReport: document.getElementById("saveReport"),
  reportStatus: document.getElementById("reportStatus"),
  reportArtifactLinks: document.getElementById("reportArtifactLinks"),
  reportReviewRating: document.getElementById("reportReviewRating"),
  reportReviewReasons: document.getElementById("reportReviewReasons"),
  reportReviewComment: document.getElementById("reportReviewComment"),
  submitReportReview: document.getElementById("submitReportReview"),
  reportReviewStatus: document.getElementById("reportReviewStatus"),
  analyzeFeedbackCount: document.getElementById("analyzeFeedbackCount"),
  analyzeExperimentCount: document.getElementById("analyzeExperimentCount"),
  analyzeRecommendationValue: document.getElementById("analyzeRecommendationValue"),
  runCompareBaseline: document.getElementById("runCompareBaseline"),
  runCompareRefresh: document.getElementById("runCompareRefresh"),
  runCompareDetails: document.getElementById("runCompareDetails"),
  runCompareSummary: document.getElementById("runCompareSummary"),
  hitListCutoff: document.getElementById("hitListCutoff"),
  hitListCutoffValue: document.getElementById("hitListCutoffValue"),
  hitListLimit: document.getElementById("hitListLimit"),
  hitWeightSoluprot: document.getElementById("hitWeightSoluprot"),
  hitWeightPlddt: document.getElementById("hitWeightPlddt"),
  hitWeightRmsd: document.getElementById("hitWeightRmsd"),
  hitWeightNovelty: document.getElementById("hitWeightNovelty"),
  hitListRefresh: document.getElementById("hitListRefresh"),
  hitListDetails: document.getElementById("hitListDetails"),
  hitListSummary: document.getElementById("hitListSummary"),
  hitListTable: document.getElementById("hitListTable"),
  analyzeChartType: document.getElementById("analyzeChartType"),
  analyzeChartCanvas: document.getElementById("analyzeChartCanvas"),
  analyzeChartCaption: document.getElementById("analyzeChartCaption"),
  reportChartType: document.getElementById("reportChartType"),
  reportChartCanvas: document.getElementById("reportChartCanvas"),
  reportChartCaption: document.getElementById("reportChartCaption"),
  settingsBtn: document.getElementById("settingsBtn"),
  settingsPanel: document.getElementById("settingsPanel"),
  settingsClose: document.getElementById("settingsClose"),
  apiBaseValue: document.getElementById("apiBaseValue"),
  reportLangSelect: document.getElementById("reportLangSelect"),
  healthCheck: document.getElementById("healthCheck"),
  healthStatus: document.getElementById("healthStatus"),
  runList: document.getElementById("runList"),
  adminPanel: document.getElementById("adminPanel"),
  adminClose: document.getElementById("adminClose"),
  helpPanel: document.getElementById("helpPanel"),
  helpClose: document.getElementById("helpClose"),
  copilotBackdrop: document.getElementById("copilotBackdrop"),
  copilotDrawer: document.getElementById("copilotDrawer"),
  copilotCloseBtn: document.getElementById("copilotCloseBtn"),
  copilotClearBtn: document.getElementById("copilotClearBtn"),
  copilotSummary: document.getElementById("copilotSummary"),
  copilotContext: document.getElementById("copilotContext"),
  copilotActions: document.getElementById("copilotActions"),
  copilotMessages: document.getElementById("copilotMessages"),
  copilotInput: document.getElementById("copilotInput"),
  copilotSendBtn: document.getElementById("copilotSendBtn"),
  copilotQuickUsage: document.getElementById("copilotQuickUsage"),
  copilotQuickInterpret: document.getElementById("copilotQuickInterpret"),
  copilotQuickSummary: document.getElementById("copilotQuickSummary"),
  copilotQuickCompare: document.getElementById("copilotQuickCompare"),
  copilotQuickNext: document.getElementById("copilotQuickNext"),
  copilotQuickResume: document.getElementById("copilotQuickResume"),
  adminUsername: document.getElementById("adminUsername"),
  adminPassword: document.getElementById("adminPassword"),
  adminRole: document.getElementById("adminRole"),
  adminCreateUser: document.getElementById("adminCreateUser"),
  adminStatus: document.getElementById("adminStatus"),
  adminRunsToggle: document.getElementById("adminRunsToggle"),
  showAllRuns: document.getElementById("showAllRuns"),
};

const I18N = {
  en: {
    "brand.subtitle": "Protein Pipeline Console",
    "action.admin": "Admin",
    "action.settings": "Settings",
    "action.logout": "Logout",
    "action.help": "Usage",
    "tabs.setup": "Setup",
    "tabs.monitor": "Monitor",
    "tabs.analyze": "Analyze",
    "copilot.open": "Copilot",
    "copilot.title": "Context Copilot",
    "copilot.desc": "Usage + interpretation helper using current run/screen data.",
    "copilot.context.title": "Current Context",
    "copilot.context.empty": "Select a run to load context.",
    "copilot.quick.title": "Quick Prompts",
    "copilot.quick.usage": "How to use this page?",
    "copilot.quick.interpret": "Interpret current metrics",
    "copilot.quick.summary": "Summarize this run",
    "copilot.quick.compare": "Explain compare state",
    "copilot.quick.next": "What should I do next?",
    "copilot.quick.resume": "How does resume work?",
    "copilot.summary.title": "Live Snapshot",
    "copilot.summary.empty": "Open a run to build the live snapshot.",
    "copilot.actions.title": "Suggested Actions",
    "copilot.actions.empty": "Select a run to unlock in-place actions.",
    "copilot.conversation.title": "Conversation",
    "copilot.clear": "Clear",
    "copilot.role.user": "You",
    "copilot.role.ai": "Copilot",
    "copilot.action.openSetup": "Open Setup",
    "copilot.action.openSetup.desc": "Fill inputs and launch a new run.",
    "copilot.action.openMonitor": "Open Monitor",
    "copilot.action.openMonitor.desc": "Check state, errors, and artifact progress.",
    "copilot.action.openAnalyze": "Open Analyze",
    "copilot.action.openAnalyze.desc": "Review hit list, charts, and compare studio.",
    "copilot.action.poll": "Poll Now",
    "copilot.action.poll.desc": "Refresh the current run status immediately.",
    "copilot.action.refreshArtifacts": "Refresh Artifacts",
    "copilot.action.refreshArtifacts.desc": "Reload file outputs and preview choices.",
    "copilot.action.refreshHitList": "Refresh Hit List",
    "copilot.action.refreshHitList.desc": "Rebuild candidate ranking for this run.",
    "copilot.action.generateReport": "Generate Report",
    "copilot.action.generateReport.desc": "Refresh comparison summary and report assets.",
    "copilot.action.resume": "Resume Run",
    "copilot.action.resume.desc": "Continue an interrupted run from saved request.",
    "copilot.action.compare3d": "Run Compare 3D",
    "copilot.action.compare3d.desc": "Render the selected left/right structures now.",
    "copilot.action.completed": "{action} completed.",
    "copilot.action.failed": "{action} failed: {error}",
    "copilot.input.placeholder": "Ask about current run or this UI",
    "copilot.send": "Send",
    "analyze.kpi.feedback": "Feedback",
    "analyze.kpi.experiment": "Experiments",
    "analyze.kpi.recommendation": "Recommendation",
    "login.title": "Enter the Lab",
    "login.desc": "Identify yourself to separate runs and keep artifacts organized.",
    "login.username": "Username",
    "login.username.placeholder": "e.g. hana.kim",
    "login.password": "Password",
    "login.password.placeholder": "••••••••",
    "login.submit": "Access Console",
    "setup.title": "Run Setup",
    "setup.desc": "Choose a workflow, attach inputs, and launch the job.",
    "setup.section.input": "Input",
    "setup.section.inputDesc": "Attach required files and add optional context notes.",
    "setup.section.execution": "Execution Settings",
    "setup.section.executionDesc": "Select run mode and configure stage options.",
    "setup.section.monitor": "Monitoring",
    "setup.section.monitorDesc": "Keep progress and errors visible while preparing a run.",
    "setup.section.log": "Activity Log",
    "setup.section.logDesc": "Preflight and run messages appear here.",
    "setup.openMonitor": "Open Monitor",
    "setup.prompt.placeholder": "Prompt or notes (key=value supported).",
    "setup.check": "Check Setup",
    "setup.reset": "Reset Inputs",
    "setup.clear": "Clear Note",
    "setup.hint": "Complete required inputs to enable execution.",
    "setup.runStatus.empty": "Run status: -",
    "setup.runStatus.line": "Run status: {id} · {stage} / {state} · {updated}",
    "setup.residuePicker.title": "Residue Picker (Optional)",
    "setup.residuePicker.help":
      "Select residues from a structure and append them to fixed_positions_extra. If target_pdb is missing, run once to create target.pdb ({af2Provider} target), then load it from the selected run.",
    "setup.residuePicker.source": "Structure source: {source}",
    "setup.residuePicker.source.none": "none",
    "setup.residuePicker.loadTargetInput": "Load target_input PDB",
    "setup.residuePicker.loadRfd3Input": "Load rfd3_input_pdb",
    "setup.residuePicker.loadRunTarget": "Load selected run target.pdb",
    "setup.residuePicker.runAf2": "Run {af2Provider} from FASTA",
    "setup.residuePicker.runAf2Running": "Running {af2Provider} to generate a target structure...",
    "setup.residuePicker.runAf2NeedsFasta": "Attach a FASTA/sequence in target_input first.",
    "setup.residuePicker.runAf2NoResult": "{af2Provider} completed but ranked_0.pdb was not found.",
    "setup.residuePicker.runAf2Loaded": "{af2Provider} structure loaded from {run}:{path}",
    "setup.residuePicker.runAf2Failed": "{af2Provider} run failed: {error}",
    "setup.residuePicker.viewerPlaceholder": "Load a structure to start residue picking.",
    "setup.residuePicker.viewerUnavailable": "3D viewer unavailable.",
    "setup.residuePicker.selection.none": "No residues selected.",
    "setup.residuePicker.selection.summary": "Selected residues: {summary}",
    "setup.residuePicker.apply": "Apply to fixed_positions_extra",
    "setup.residuePicker.clearSelection": "Clear selection",
    "setup.residuePicker.note":
      "Applied values use sequence-order indices per chain (query position space) for ProteinMPNN constraints.",
    "setup.residuePicker.applied": "Applied {count} residue positions to fixed_positions_extra.",
    "setup.residuePicker.loadFailed": "Failed to load structure: {error}",
    "setup.residuePicker.noRun": "Select a run first.",
    "setup.residuePicker.noSelection": "Select at least one residue.",
    "setup.residuePicker.noPdb": "No PDB text available from this source.",
    "preflight.title": "Setup check",
    "preflight.ok": "No blocking issues found.",
    "preflight.blocked": "Fix the issues below before running.",
    "preflight.errors": "Errors",
    "preflight.warnings": "Warnings",
    "preflight.required": "Required inputs",
    "preflight.questions": "Questions",
    "preflight.detected": "Detected",
    "preflight.routed": "Prompt routing",
    "preflight.failed": "Preflight failed: {error}",
    "preflight.unavailable": "Setup check is not available for {mode}.",
    "monitor.title": "Run Monitor",
    "monitor.desc": "Track live status, scores, and recent runs.",
    "monitor.runId": "Run ID",
    "monitor.selectRun": "Select run",
    "monitor.stage": "Stage",
    "monitor.state": "State",
    "monitor.updated": "Updated",
    "monitor.eta": "ETA",
    "monitor.detail": "Detail",
    "monitor.progress": "Progress",
    "monitor.progress.backbone": "Backbone",
    "monitor.progress.wt": "WT Baseline",
    "monitor.progress.masking": "Masking",
    "monitor.progress.done": "Done",
    "monitor.scoring": "Scoring",
    "monitor.completeness": "Data Completeness",
    "monitor.completeness.placeholder": "Select a run to show data completeness.",
    "monitor.completeness.badge.rfd3Ready": "RFD3 ready",
    "monitor.completeness.badge.rfd3Missing": "RFD3 missing",
    "monitor.completeness.badge.bioemuReady": "BioEmu ready",
    "monitor.completeness.badge.bioemuMissing": "BioEmu missing",
    "monitor.completeness.badge.bioemuOnly": "BioEmu only",
    "monitor.completeness.badge.wtOn": "WT compare on",
    "monitor.completeness.badge.wtOff": "WT compare off",
    "monitor.completeness.badge.af2None": "{af2Provider} selected none",
    "monitor.completeness.badge.af2Some": "{af2Provider} selected {count}",
    "monitor.workflow.title": "Workflow Review Gate",
    "monitor.workflow.waiting": "Running until checkpoint: {stage}",
    "monitor.workflow.ready": "Checkpoint reached at {stage}. Review graph and choose next action.",
    "monitor.workflow.completed": "Workflow completed to final stage: {stage}",
    "monitor.workflow.chart.empty": "No artifact count yet. Refresh artifacts after checkpoint.",
    "monitor.workflow.checkpoints": "Checkpoints: {stages}",
    "monitor.workflow.nextStage": "Next stage: {stage}",
    "monitor.workflow.finalStage": "Final stage: {stage}",
    "monitor.workflow.continue": "Continue to Next Stage",
    "monitor.workflow.continueStarted": "Continuing workflow from {start} to {stop} for {id}...",
    "monitor.workflow.continueFailed": "Workflow continue failed: {error}",
    "monitor.workflow.rerunLabel": "Rerun Target Stage",
    "monitor.workflow.rerunAction": "Rerun to Stage",
    "monitor.workflow.rerunConfirm":
      "Rerun a new run from MSA to {stage} based on run {id}? This creates a separate comparison run.",
    "monitor.workflow.rerunStarted": "Stage rerun started: {id} ({start} -> {stop})",
    "monitor.workflow.rerunFailed": "Stage rerun failed: {error}",
    "monitor.workflow.resultsTitle": "Checkpoint Results",
    "monitor.workflow.resultsHint": "{count} artifacts generated so far. Click an item to preview.",
    "monitor.workflow.resultsEmpty": "No result artifacts yet.",
    "monitor.workflow.resultsUnknown": "Unknown",
    "monitor.workflow.resultsDisabled": "Checkpoint result panel is disabled in setup.",
    "monitor.workflow.mmseq": "Rerun MMseqs",
    "monitor.workflow.mmseqConfirm":
      "Run MMseqs rerun from stage MSA for run {id}? A new run will be created for comparison.",
    "monitor.workflow.mmseqStarted": "MMseqs rerun started: {id}",
    "monitor.workflow.mmseqFailed": "MMseqs rerun failed: {error}",
    "monitor.workflow.openAnalyze": "Open Analyze",
    "monitor.poll": "Poll Now",
    "monitor.stop": "Stop Run",
    "monitor.resume": "Resume Run",
    "monitor.stopConfirm": "Cancel run {id}? This will request RunPod cancellation.",
    "monitor.stopSuccess": "Cancel requested for {id} (jobs: {count}).",
    "monitor.stopFailed": "Cancel failed: {error}",
    "monitor.autoPoll": "Auto Poll",
    "monitor.recentRuns": "Recent Runs",
    "monitor.refreshRuns": "Refresh",
    "monitor.showAll": "Show all runs (admin)",
    "monitor.activity": "Activity Log",
    "monitor.clearLog": "Clear",
    "agent.title": "Agent Panel",
    "agent.desc": "Stage-by-stage expert consensus and recovery notes.",
    "agent.refresh": "Refresh",
    "agent.viewReport": "View Report",
    "agent.viewAgentReport": "View Agent Report",
    "agent.report.loading": "Loading report...",
    "agent.report.missing": "No report available yet.",
    "agent.report.failed": "Failed to load report: {error}",
    "agent.feedback.good": "Good",
    "agent.feedback.bad": "Bad",
    "agent.feedback.note": "Note (optional)",
    "agent.feedback.saving": "Saving...",
    "agent.feedback.saved": "Saved.",
    "agent.feedback.failed": "Failed: {error}",
    "report.modal.download": "Download",
    "report.modal.toggleRendered": "Rendered",
    "report.modal.toggleRaw": "Raw",
    "agent.loading": "Loading agent panel...",
    "agent.empty": "No agent events yet.",
    "agent.failed": "Agent panel load failed: {error}",
    "artifacts.title": "Artifacts",
    "artifacts.desc": "Filter outputs from the run.",
    "artifacts.monitorHint.title": "Compare moved to Analyze",
    "artifacts.monitorHint.desc":
      "Use the Analyze tab for 3D structure compare and report-based comparison summary.",
    "artifacts.monitorHint.action": "Open Analyze",
    "artifacts.filter.placeholder": "Filter by name or stage",
    "artifacts.refresh": "Refresh",
    "artifacts.filter.allStages": "All stages",
    "artifacts.filter.allTiers": "All tiers",
    "artifacts.filter.allTypes": "All types",
    "artifacts.filter.stage": "Stage",
    "artifacts.filter.tier": "Tier",
    "artifacts.filter.type": "Type",
    "artifacts.compare.title": "Comparison Summary",
    "artifacts.compare.desc":
      "WT-vs-design and RFD3-vs-BioEmu metrics from generated report artifacts.",
    "artifacts.compare.placeholder": "Generate report to load comparison metrics.",
    "artifacts.compare.noData": "Comparison data is not available for this run.",
    "artifacts.compare.viewDetails": "View Details",
    "artifacts.compare.detailsTitle": "Comparison Details",
    "artifacts.compare.generateReport": "Generate Report",
    "artifacts.compare.wt": "WT vs Design",
    "artifacts.compare.funnel": "Selection Funnel",
    "artifacts.compare.funnelBackbone": "Backbones",
    "artifacts.compare.funnelSoluprot": "SoluProt pass",
    "artifacts.compare.funnelAf2": "{af2Provider} pass",
    "artifacts.compare.funnelRetain": "Backbone retention",
    "artifacts.compare.source": "RFD3 vs BioEmu",
    "artifacts.compare.metric": "Metric",
    "artifacts.compare.wtValue": "WT",
    "artifacts.compare.designMedian": "Design median",
    "artifacts.compare.delta": "Delta",
    "artifacts.compare.wtEnabled": "WT compare enabled: {enabled}",
    "artifacts.compare.sourceName": "Source",
    "artifacts.compare.backbones": "Backbones",
    "artifacts.compare.passRate": "SoluProt pass",
    "artifacts.compare.soluprotMedian": "Median SoluProt",
    "artifacts.compare.af2Selected": "{af2Provider} selected",
    "artifacts.compare.plddtMedian": "Median pLDDT",
    "artifacts.compare.rmsdMedian": "Median RMSD",
    "artifacts.preview.title": "Artifact Preview",
    "artifacts.preview.desc": "3D structures, images, or text extracts.",
    "artifacts.preview.placeholder": "Select an artifact to preview it here.",
    "artifacts.preview.compare.mode.structure": "Structure Diff",
    "artifacts.preview.compare.mode.sequence": "Sequence Diff",
    "artifacts.preview.compare.left": "Reference 3D",
    "artifacts.preview.compare.right": "Candidate 3D",
    "artifacts.preview.compare.run": "Compare 3D",
    "artifacts.preview.compare.swap": "Swap",
    "artifacts.preview.compare.clear": "Clear",
    "artifacts.preview.compare.missing": "Select both left and right 3D artifacts first.",
    "artifacts.preview.compare.failed": "3D comparison failed: {error}",
    "artifacts.preview.compare.refs.title": "Resolved Baselines",
    "artifacts.preview.compare.refs.input": "Input Structure",
    "artifacts.preview.compare.refs.working": "Working Backbone",
    "artifacts.preview.compare.refs.wt": "WT ColabFold",
    "artifacts.preview.compare.refs.missing": "Not available",
    "artifacts.preview.compare.preset.title": "Quick Compare",
    "artifacts.preview.compare.preset.inputVsWt": "Input vs WT",
    "artifacts.preview.compare.preset.inputVsWorking": "Input vs Working",
    "artifacts.preview.compare.preset.inputVsRfd3": "Input vs RFD3",
    "artifacts.preview.compare.preset.inputVsBioemu": "Input vs BioEmu",
    "artifacts.preview.compare.preset.wtVsRfd3": "WT vs RFD3",
    "artifacts.preview.compare.preset.wtVsBioemu": "WT vs BioEmu",
    "artifacts.preview.compare.preset.rfd3VsBioemu": "RFD3 vs BioEmu",
    "artifacts.preview.compare.group.references": "References",
    "artifacts.preview.compare.group.backbones": "Backbone Snapshots",
    "artifacts.preview.compare.group.af2": "{af2Provider} Candidates",
    "artifacts.preview.compare.group.source": "Source Outputs",
    "artifacts.preview.compare.group.other": "Other Structures",
    "artifacts.preview.compare.sequenceTitle": "Sequence (FASTA)",
    "artifacts.preview.compare.sequenceLeft": "Reference",
    "artifacts.preview.compare.sequenceRight": "Candidate",
    "artifacts.preview.compare.sequenceEmpty": "No sequence extracted from this structure.",
    "artifacts.preview.compare.diffLegendStructure":
      "Structure diff after CA alignment: <=1.5A gray, 1.5-3.0A yellow, >3.0A red, gaps WT blue / Design orange",
    "artifacts.preview.compare.diffLegendSequence":
      "Sequence diff on residue identity: WT-only/WT-mutated blue, Design-only/Design-mutated orange, same residue gray",
    "artifacts.preview.compare.diffNone": "No residue-level differences detected.",
    "artifacts.preview.compare.meta.title": "Compare Context",
    "artifacts.preview.compare.meta.left": "Reference",
    "artifacts.preview.compare.meta.right": "Candidate",
    "artifacts.preview.compare.meta.role": "Role",
    "artifacts.preview.compare.meta.source": "Source",
    "artifacts.preview.compare.meta.provenance": "Provenance",
    "artifacts.preview.compare.meta.tier": "Tier",
    "artifacts.preview.compare.meta.backbone": "Backbone",
    "artifacts.preview.compare.meta.chains": "Chains",
    "artifacts.preview.compare.meta.fixedCount": "Fixed Count",
    "artifacts.preview.compare.meta.wtDiff": "WT Seq Diff",
    "artifacts.preview.compare.meta.inputStructRmsd": "Input RMSD",
    "artifacts.preview.compare.meta.wtStructRmsd": "WT CF RMSD",
    "artifacts.preview.compare.meta.workingStructRmsd": "Working RMSD",
    "artifacts.preview.compare.meta.commonCa": "Common CA",
    "artifacts.preview.compare.meta.predScope": "{af2Provider} Scope",
    "artifacts.preview.compare.meta.predScopeExact": "Exact candidate",
    "artifacts.preview.compare.meta.predScopeWt": "WT reference",
    "artifacts.preview.compare.meta.predScopeTier": "Tier summary",
    "artifacts.preview.compare.meta.predScopeBackbone": "Backbone summary",
    "artifacts.preview.compare.meta.predScopePre": "Pre-{af2Provider}",
    "artifacts.preview.compare.meta.predSelected": "{af2Provider} Selected",
    "artifacts.preview.compare.meta.predPlddt": "{af2Provider} pLDDT",
    "artifacts.preview.compare.meta.predRmsd": "{af2Provider} RMSD",
    "artifacts.preview.compare.meta.path": "Path",
    "artifacts.preview.compare.role.input_reference": "Input Structure",
    "artifacts.preview.compare.role.working_backbone": "Working Backbone",
    "artifacts.preview.compare.role.wt_colabfold": "WT ColabFold",
    "artifacts.preview.compare.role.backbone_snapshot": "Backbone Snapshot",
    "artifacts.preview.compare.role.af2_candidate": "{af2Provider} Candidate",
    "artifacts.preview.compare.role.source_output": "Source Output",
    "artifacts.preview.compare.role.structure_artifact": "Structure Artifact",
    "artifacts.preview.compare.provenance.input": "Original run input snapshot",
    "artifacts.preview.compare.provenance.inputRfd3": "Original run input snapshot (RFD3-derived)",
    "artifacts.preview.compare.provenance.working": "Primary backbone copy used for downstream stages",
    "artifacts.preview.compare.provenance.wt": "WT sequence predicted by {af2Provider}",
    "artifacts.preview.compare.provenance.backbone": "{source} backbone snapshot",
    "artifacts.preview.compare.provenance.candidate": "Tier {tier} candidate predicted by {af2Provider}",
    "artifacts.preview.compare.provenance.source": "{source} source-stage output",
    "artifacts.preview.compare.provenance.other": "Structure artifact",
    "feedback.title": "Feedback",
    "feedback.desc": "Capture expert reviews and ratings.",
    "feedback.rating": "Rating",
    "feedback.reasons": "Reasons",
    "feedback.artifact": "Artifact (optional)",
    "feedback.stage": "Stage (optional)",
    "feedback.comment": "Comment",
    "feedback.comment.placeholder": "Short context or interpretation",
    "feedback.submit": "Submit Feedback",
    "feedback.exportCsv": "Export CSV",
    "feedback.exportTsv": "Export TSV",
    "feedback.recent": "Recent Feedback",
    "experiment.title": "Experiment",
    "experiment.desc": "Log wet-lab outcomes and metrics.",
    "experiment.assay": "Assay Type",
    "experiment.result": "Result",
    "experiment.sample": "Sample ID (optional)",
    "experiment.sample.placeholder": "e.g. seq_001",
    "experiment.artifact": "Artifact (optional)",
    "experiment.metrics": "Metrics (JSON, optional)",
    "experiment.metrics.placeholder": "{\"kd_nM\": 12.5, \"t50_C\": 48}",
    "experiment.conditions": "Conditions / Notes",
    "experiment.conditions.placeholder": "Buffer, temperature, assay details",
    "experiment.submit": "Submit Experiment",
    "experiment.exportCsv": "Export CSV",
    "experiment.exportTsv": "Export TSV",
    "experiment.recent": "Recent Experiments",
    "report.title": "Report",
    "report.desc": "Generate a consolidated run summary.",
    "report.label": "Report (Markdown)",
    "report.placeholder": "Generate or edit the report",
    "report.load": "Load",
    "report.generate": "Generate",
    "report.viewRendered": "Rendered View",
    "report.exportPackage": "Export Package",
    "report.save": "Save",
    "report.links": "Artifact Links",
    "report.chart.title": "Report Charts",
    "report.chart.desc": "Render one selected chart from current hit-list data.",
    "report.chart.select": "Chart Type",
    "report.chart.placeholder": "Load hit list to show report charts.",
    "report.chart.sectionTitle": "Candidate Charts (SVG Attachments)",
    "report.chart.sectionEmpty": "Chart data is not available yet.",
    "report.compare.sectionTitle": "Structure/Sequence Difference (SVG Attachments)",
    "report.compare.sectionEmpty": "Not enough PDB artifacts for automatic structure/sequence diff.",
    "report.compare.left": "Reference",
    "report.compare.right": "Candidate",
    "report.hitList.title": "Hit List",
    "report.hitList.empty": "Hit list data is not available yet.",
    "report.hitList.summary": "Rows: {shown}/{total} (cutoff >= {cutoff})",
    "report.review.title": "Report Review",
    "report.review.desc": "Rate the report and provide reasons.",
    "report.review.rating": "Rating",
    "report.review.reasons": "Reasons",
    "report.review.comment": "Comment",
    "report.review.comment.placeholder": "Optional notes",
    "report.review.submit": "Submit Review",
    "report.review.saved": "Report review saved.",
    "report.review.failed": "Review failed: {error}",
    "report.review.reason.clear": "Clear summary",
    "report.review.reason.actionable": "Actionable guidance",
    "report.review.reason.complete": "Complete coverage",
    "report.review.reason.missing_metrics": "Missing key metrics",
    "report.review.reason.inaccurate": "Inaccurate content",
    "report.review.reason.confusing": "Hard to follow",
    "report.review.reason.other": "Other",
    "settings.title": "Settings",
    "settings.baseLabel": "MCP HTTP Base URL",
    "settings.baseHint": "This value is fixed by the server configuration.",
    "settings.reportLang.label": "Report Language",
    "settings.reportLang.auto": "Follow UI",
    "settings.reportLang.en": "English",
    "settings.reportLang.ko": "Korean",
    "settings.reportLang.hint": "Applies to run reports and agent reports.",
    "settings.health": "Health Check",
    "role.admin": "Admin",
    "role.user": "User",
    "admin.title": "Admin: Create User",
    "admin.username": "New Username",
    "admin.username.placeholder": "new.user",
    "admin.password": "New Password",
    "admin.password.placeholder": "min 8 chars",
    "admin.role": "Role",
    "admin.role.user": "User",
    "admin.role.admin": "Admin",
    "admin.create": "Create User",
    "help.title": "Usage Guide",
    "help.quick.title": "Quick Start",
    "help.quick.step1": "Setup: choose mode, attach inputs, and run.",
    "help.quick.step2": "Monitor: watch status and review artifacts.",
    "help.quick.step3": "Analyze: record feedback, experiments, and reports.",
    "help.setup.title": "Setup Tips",
    "help.setup.step1": "Use Run Mode to select pipeline or specific tools.",
    "help.setup.step2": "Attach required files; missing inputs keep Run disabled.",
    "help.monitor.title": "Monitoring",
    "help.monitor.step1": "Select a recent run to load status and artifacts.",
    "help.monitor.step2": "Use Auto Poll for live updates.",
    "help.analyze.title": "Analysis",
    "help.analyze.step1": "Start with Compare Studio, Run-to-Run, and Hit List for quick triage.",
    "help.analyze.step2": "Review 3D structure diffs and WT/RFD3/BioEmu comparison summaries.",
    "help.analyze.step3": "Then log feedback/experiments and finalize reports.",
    "help.admin.title": "Admin",
    "help.admin.step1": "Admins can create users from the Admin button.",
    "common.close": "Close",
    "common.none": "None",
    "common.score": "Score",
    "common.evidence": "Evidence",
    "common.recommendation": "Recommendation",
    "runs.delete": "delete",
    "runs.deleteConfirm": "Delete run {id}? This cannot be undone.",
    "runs.deleteFailed": "Delete failed: {error}",
    "runs.deleteSuccess": "Deleted run: {id}",
    "question.runMode.label": "Run Mode",
    "question.runMode.help": "Choose what to run.",
    "question.runMode.detail": "Each mode changes required input, runtime, and output depth.",
    "question.targetInput.label": "Target Input",
    "question.targetInput.help": "Provide target_pdb or target_fasta (raw text).",
    "question.startFrom.label": "Start From",
    "question.startFrom.help": "Where to start? Reuses cached outputs before this stage when available.",
    "question.stopAfter.label": "Stop After",
    "question.stopAfter.help": "Where to stop? (msa/rfd3/bioemu/design/soluprot/af2/wt_diff)",
    "question.designChains.label": "Design Chains",
    "question.designChains.help": "Which chains to design? (default: all)",
    "question.wtCompare.label": "WT Compare",
    "question.wtCompare.help": "Compute WT baseline (SoluProt/{af2Provider}) and compare in report.",
    "question.maskConsensusApply.label": "Apply Mask Consensus",
    "question.maskConsensusApply.help": "Apply expert mask consensus to ProteinMPNN (optional).",
    "question.bioemuUse.label": "Enable BioEmu",
    "question.bioemuUse.help": "Run the BioEmu backbone sampling stage.",
    "question.bioemuNumSamples.label": "BioEmu Samples",
    "question.bioemuNumSamples.help": "Number of BioEmu samples to generate.",
    "question.bioemuMaxReturn.label": "BioEmu Return Count",
    "question.bioemuMaxReturn.help": "Maximum number of BioEmu structures to keep.",
    "question.numSeqPerTier.label": "ProteinMPNN per Tier",
    "question.numSeqPerTier.help": "Number of ProteinMPNN sequences to generate for each tier and backbone.",
    "question.af2MaxCandidatesPerTier.label": "{af2Provider} per Tier (Top N)",
    "question.af2MaxCandidatesPerTier.help":
      "Run {af2Provider} only for top N SoluProt-passed designs per tier (ranked by SoluProt score, 0 = all).",
    "question.af2PlddtCutoff.label": "{af2Provider} pLDDT Cutoff",
    "question.af2PlddtCutoff.help": "Minimum pLDDT threshold for {af2Provider} pass filtering (default: 85).",
    "question.af2RmsdCutoff.label": "{af2Provider} RMSD Cutoff",
    "question.af2RmsdCutoff.help": "Maximum RMSD threshold (angstrom) for {af2Provider} pass filtering (default: 2.0).",
    "question.noveltyEnabled.label": "WT Diff",
    "question.noveltyEnabled.help": "Run the final WT Diff comparison for AF2-selected sequences.",
    "question.af2Provider.label": "Structure Predictor",
    "question.af2Provider.help": "Choose structure prediction provider.",
    "question.rfd3MaxReturn.label": "RFD3 Return Count",
    "question.rfd3MaxReturn.help": "Maximum number of RFD3 backbone designs to keep.",
    "question.confirmRun.label": "Confirm Run",
    "question.confirmRun.help": "Review the parsed settings and confirm to enable execution.",
    "question.fixedPositionsExtra.label": "Fixed Positions (Extra)",
    "question.fixedPositionsExtra.help": "Optional hard constraints before design. Use JSON ({\"A\":[6,10],\"*\":[120]}) or shorthand (A:6,10;*:120).",
    "question.ligandMaskOriginal.label": "Preserve Original Ligand Mask",
    "question.ligandMaskOriginal.help": "Project ligand-contact residues from original target_pdb/rfd3_input_pdb onto current backbones.",
    "question.stripNonpositive.label": "Strip non-positive residues",
    "question.stripNonpositive.help": "Remove residues with resseq <= 0 before RFD3 and downstream steps.",
    "question.rfd3InputPdb.label": "RFD3 Input PDB",
    "question.rfd3InputPdb.help": "Provide rfd3_input_pdb text (raw PDB).",
    "question.rfd3Contig.label": "RFD3 Contig",
    "question.rfd3Contig.help": "Provide rfd3_contig (format: A1-221, no colon).",
    "question.diffdockLigand.label": "DiffDock Ligand",
    "question.diffdockLigand.help": "Provide diffdock_ligand_smiles or diffdock_ligand_sdf.",
    "question.targetFasta.label": "Target FASTA",
    "question.targetFasta.help": "Provide target FASTA or sequence for {af2ProviderPair}.",
    "question.proteinPdb.label": "Protein PDB",
    "question.proteinPdb.help": "Provide protein PDB text for DiffDock.",
    "question.ligandInput.label": "Ligand Input",
    "question.ligandInput.help": "Provide ligand SMILES or SDF for DiffDock.",
    "attachment.title": "Attachments",
    "attachment.help": "Attach files for the required inputs.",
    "attachment.select": "Choose file",
    "attachment.clear": "Clear",
    "attachment.none": "No file selected.",
    "attachment.attached": "Attached: {name} ({kb} KB)",
    "attachment.attachedName": "Attached: {name}",
    "attachment.failed": "Failed to read file: {error}",
    "attachment.diffdock.use": "Use DiffDock",
    "attachment.diffdock.skip": "Skip",
    "choice.allChains": "All chains",
    "choice.chainNote": "Upload a target PDB to enable chain selection.",
    "choice.chainDefaultNote": "Tip: with no target FASTA, the pipeline defaults to the primary chain. Select chains explicitly for multi-chain designs or to avoid short-chain mismatches.",
    "choice.contigNone": "None (skip RFD3)",
    "choice.contigNote": "Upload a PDB to suggest rfd3_contig options.",
    "choice.contigPositiveOnly": "Contig suggestions use protein residues (ATOM and common amino-acid HETATM) with positive numbering only.",
    "choice.stripNonpositive.on": "Strip (recommended)",
    "choice.stripNonpositive.off": "Keep as-is",
    "choice.wtCompare.on": "Enable WT compare",
    "choice.wtCompare.off": "Disable WT compare",
    "choice.maskConsensusApply.on": "Apply consensus",
    "choice.maskConsensusApply.off": "Do not apply",
    "choice.ligandMaskOriginal.on": "Preserve original mask",
    "choice.ligandMaskOriginal.off": "Use backbone-only mask",
    "choice.bioemuUse.on": "Enable BioEmu",
    "choice.bioemuUse.off": "Disable BioEmu",
    "choice.novelty.on": "Enable WT Diff",
    "choice.novelty.off": "Disable WT Diff",
    "choice.af2Provider.colabfold": "ColabFold (default)",
    "choice.af2Provider.af2": "AlphaFold2",
    "advanced.bioemuCounts.title": "BioEmu Count Options",
    "advanced.bioemuCounts.help": "These values are optional and hidden by default.",
    "advanced.bioemuCounts.show": "Show BioEmu Count Options",
    "advanced.bioemuCounts.hide": "Hide BioEmu Count Options",
    "advanced.rfd3Counts.title": "RFD3 Count Options",
    "advanced.rfd3Counts.help": "These values are optional and hidden by default.",
    "advanced.rfd3Counts.show": "Show RFD3 Count Options",
    "advanced.rfd3Counts.hide": "Hide RFD3 Count Options",
    "choice.confirmRun.yes": "Yes, run",
    "choice.confirmRun.no": "Review first",
    "setup.wizard.scope": "Scope",
    "setup.wizard.input": "Input",
    "setup.wizard.options": "Options",
    "setup.wizard.stepMeta": "Step {current}/{total}: {label}",
    "setup.wizard.prev": "Previous",
    "setup.wizard.next": "Next",
    "hint.none": "No missing inputs. You can run now.",
    "hint.ready": "All required inputs captured.",
    "hint.missing": "Missing required inputs.",
    "hint.nextStep": "Move to the final step to launch the run.",
    "hint.running": "A run is already in progress.",
    "run.reset": "Inputs reset. Reconfirm selections and attachments.",
    "setup.options.title": "Core Option Board",
    "setup.options.help": "Review key execution options in one board.",
    "setup.parameters.title": "Compact Parameter Board",
    "setup.parameters.help":
      "Tune key numeric settings in one place. BioEmu and RFD3 counts stay visible in Pipeline and Workflow modes.",
    "setup.parameters.inactive": "Inactive in current context",
    "setup.workflow.title": "Workflow Studio",
    "setup.workflow.help":
      "Build a staged execution flow. Select stages, place checkpoints, and continue after reviewing intermediate results.",
    "setup.workflow.palette": "Stage Palette",
    "setup.workflow.paletteHelp": "Choose only the stages you need. Hover a stage to see its role.",
    "setup.workflow.canvas": "Flow Canvas",
    "setup.workflow.canvasHelp": "Selected stages appear in execution order. Click a node to toggle checkpoints.",
    "setup.workflow.stageGuide": "Stage Guide",
    "setup.workflow.stageGuideHint": "Hover or focus a stage to view details.",
    "setup.workflow.stageGuideLabel": "Selected Stage",
    "setup.workflow.controls": "Run Controls",
    "setup.workflow.summaryTitle": "Plan Snapshot",
    "setup.workflow.stageDesc.msa": "Find homologous sequences and assemble the MSA baseline.",
    "setup.workflow.stageDesc.rfd3": "Generate backbone candidates from the prepared scaffold input.",
    "setup.workflow.stageDesc.bioemu": "Sample structural conformations with BioEmu for diversity.",
    "setup.workflow.stageDesc.design": "Design candidate amino-acid sequences from backbone context.",
    "setup.workflow.stageDesc.soluprot": "Score and filter candidates by solubility tendency.",
    "setup.workflow.stageDesc.af2": "Predict structures and quality metrics with {af2Provider}.",
    "setup.workflow.stageDesc.novelty": "Compare against the WT sequence and calculate WT Diff.",
    "setup.workflow.summary": "Execution Plan",
    "setup.workflow.empty": "Click a stage button to add nodes.",
    "setup.workflow.nodeHint": "Click nodes to toggle checkpoints (multi-select). Use x to remove a stage.",
    "setup.workflow.checkpoint": "Pause at checkpoint",
    "setup.workflow.showResults": "Show checkpoint results",
    "setup.workflow.showGraph": "Show graph at checkpoint",
    "setup.workflow.mmseqLoop": "Allow stage rerun from review panel",
    "setup.workflow.orderLocked":
      "Stage order is fixed by pipeline dependencies. Reordering is technically possible but not recommended for stable execution.",
    "setup.workflow.removeNode": "Remove stage",
    "setup.workflow.badge.checkpoint": "Checkpoint",
    "setup.workflow.badge.final": "Final",
    "setup.workflow.plan": "Run {start} -> {stop} (final {final})",
    "setup.workflow.planNoCheckpoint": "Run {start} -> {final}",
    "setup.workflow.checkpoints": "Checkpoints: {stages}",
    "setup.workflow.checkpoints.none": "Checkpoints: none (run continuously)",
    "runmode.pipeline": "Full Pipeline",
    "runmode.workflow": "Workflow Studio",
    "runmode.rfd3": "RFD3 (Backbone)",
    "runmode.bioemu": "BioEmu (Backbone)",
    "runmode.msa": "MSA (MMseqs2)",
    "runmode.design": "ProteinMPNN",
    "runmode.soluprot": "SoluProt",
    "runmode.af2": "{af2Provider}",
    "runmode.diffdock": "DiffDock",
    "setup.modeGuide.title": "Mode Guide",
    "setup.modeGuide.pipeline": "Run the end-to-end pipeline through the final WT Diff stage.",
    "setup.modeGuide.workflow":
      "Run by checkpointed stage blocks and decide continue/rerun actions from the monitor panel.",
    "setup.modeGuide.rfd3": "Run only RFD3 backbone generation.",
    "setup.modeGuide.bioemu": "Run only BioEmu backbone sampling.",
    "setup.modeGuide.msa": "Run only MSA/MMseqs retrieval and cache preparation.",
    "setup.modeGuide.design": "Run only sequence design (ProteinMPNN).",
    "setup.modeGuide.soluprot": "Run only solubility scoring.",
    "setup.modeGuide.af2": "Run only structure prediction with {af2Provider}.",
    "setup.modeGuide.diffdock": "Run only protein-ligand docking.",
    "stop.full": "Full (WT Diff)",
    "stage.msa": "MSA",
    "stage.rfd3": "RFD3",
    "stage.bioemu": "BioEmu",
    "stage.design": "Design",
    "stage.soluprot": "SoluProt",
    "stage.af2": "{af2Provider}",
    "run.label.pipeline": "Run Pipeline",
    "run.label.workflow": "Run Workflow",
    "run.label.rfd3": "Run RFD3",
    "run.label.bioemu": "Run BioEmu",
    "run.label.msa": "Run MSA",
    "run.label.design": "Run ProteinMPNN",
    "run.label.soluprot": "Run SoluProt",
    "run.label.af2": "Run {af2Provider}",
    "run.label.diffdock": "Run DiffDock",
    "mode.pipeline": "pipeline",
    "mode.workflow": "workflow",
    "mode.rfd3": "RFD3",
    "mode.bioemu": "BioEmu",
    "mode.msa": "MSA",
    "mode.design": "ProteinMPNN",
    "mode.soluprot": "SoluProt",
    "mode.af2": "{af2Provider}",
    "mode.diffdock": "DiffDock",
    "run.launching": "Launching {mode} run {id}...",
    "run.started": "Run started: {id}",
    "run.failed": "Run failed: {error}",
    "run.resume.loading": "Loading request.json for {id}...",
    "run.resume.running": "Run is already in progress.",
    "run.resume.noRequest": "request.json was not found for this run.",
    "run.resume.badRequest": "request.json is invalid.",
    "run.resume.starting": "Resuming run {id} from saved request...",
    "run.resume.started": "Resume requested: {id}",
    "run.resume.failed": "Resume failed: {error}",
    "run.alreadyRunning": "A run is already in progress. Stop it or wait for completion.",
    "run.confirmRequired": "Confirm the prompt plan before running.",
    "status.line": "Status: {stage} / {state}",
    "status.notFound":
      "Status unavailable for {id}. status.json may be missing while an external/resumed job is still running.",
    "status.error": "Status error: {error}",
    "artifact.none": "No artifacts.",
    "artifact.error": "Artifact error: {error}",
    "artifact.preview.binary": "Binary file: {path}",
    "artifact.preview.failed": "Preview failed: {error}",
    "artifact.preview.unavailable": "3D viewer unavailable.",
    "artifact.references.none": "No artifact references yet.",
    "runs.none": "No runs yet.",
    "runs.load": "load",
    "feedback.rating.good": "Good",
    "feedback.rating.bad": "Bad",
    "feedback.reason.low_plddt": "Low pLDDT",
    "feedback.reason.high_plddt": "High pLDDT",
    "feedback.reason.high_rmsd": "High RMSD",
    "feedback.reason.low_rmsd": "Low RMSD",
    "feedback.reason.binding_poor": "Binding Poor",
    "feedback.reason.binding_good": "Binding Good",
    "feedback.reason.low_novelty": "Low WT Diff",
    "feedback.reason.high_novelty": "High WT Diff",
    "feedback.reason.unstable": "Unstable",
    "feedback.reason.stable": "Stable",
    "feedback.reason.other": "Other",
    "feedback.stage.auto": "Auto",
    "feedback.stage.msa": "MSA",
    "feedback.stage.design": "Design",
    "feedback.stage.soluprot": "SoluProt",
    "feedback.stage.af2": "{af2Provider}",
    "feedback.stage.novelty": "WT Diff",
    "feedback.stage.rfd3": "RFD3",
    "feedback.stage.diffdock": "DiffDock",
    "feedback.stage.other": "Other",
    "experiment.assay.binding": "Binding",
    "experiment.assay.activity": "Activity",
    "experiment.assay.stability": "Stability",
    "experiment.assay.expression": "Expression",
    "experiment.assay.other": "Other",
    "experiment.result.success": "Success",
    "experiment.result.fail": "Fail",
    "experiment.result.inconclusive": "Inconclusive",
    "export.selectRun": "Select a run first.",
    "export.exporting": "Exporting...",
    "export.none.feedback": "No feedback to export.",
    "export.none.experiments": "No experiments to export.",
    "export.done": "Exported {count} rows.",
    "export.failed": "Export failed: {error}",
    "feedback.saved": "Feedback saved.",
    "feedback.failed": "Failed: {error}",
    "feedback.none": "No feedback yet.",
    "feedback.loadFailed": "Load failed: {error}",
    "experiment.saved": "Experiment saved.",
    "experiment.failed": "Failed: {error}",
    "experiment.none": "No experiments yet.",
    "experiment.loadFailed": "Load failed: {error}",
    "report.loaded": "Report loaded.",
    "report.notAvailable": "Report not available yet.",
    "report.loadFailed": "Load failed: {error}",
    "report.generated": "Report generated.",
    "report.generateFailed": "Generate failed: {error}",
    "report.saved": "Report saved.",
    "report.saveFailed": "Save failed: {error}",
    "report.empty": "Report content is empty.",
    "analyze.compareStudio.title": "Structure Compare Studio",
    "analyze.compareStudio.desc":
      "Run 3D/sequence diff and review WT/RFD3/BioEmu comparison in one place.",
    "analyze.runCompare.title": "Run-to-Run Compare",
    "analyze.runCompare.desc":
      "Compare pLDDT, RMSD, SoluProt, and pass-rate deltas against a baseline run.",
    "analyze.runCompare.baseline": "Baseline Run",
    "analyze.runCompare.refresh": "Compare",
    "analyze.runCompare.details": "View Details",
    "analyze.runCompare.placeholder": "Select a baseline run to load run-to-run deltas.",
    "analyze.runCompare.sameRun": "Baseline run must be different from current run.",
    "analyze.runCompare.failed": "Run comparison failed: {error}",
    "analyze.runCompare.detailsTitle": "Run Comparison Details",
    "analyze.hitList.title": "Hit List",
    "analyze.hitList.desc": "Weighted ranking of final candidates with cutoff filtering.",
    "analyze.hitList.cutoff": "Score Cutoff",
    "analyze.hitList.limit": "Rows",
    "analyze.hitList.weight.soluprot": "SoluProt W",
    "analyze.hitList.weight.plddt": "pLDDT W",
    "analyze.hitList.weight.rmsd": "RMSD W",
    "analyze.hitList.weight.novelty": "WT Diff W (off)",
    "analyze.hitList.identity": "WT Diff (n/len, %)",
    "analyze.hitList.identityInfo":
      "WT difference is shown as count/length and percent and does not affect ranking/filtering.",
    "analyze.hitList.refresh": "Refresh",
    "analyze.hitList.details": "View Details",
    "analyze.hitList.placeholder": "Load a run to build the hit list.",
    "analyze.hitList.failed": "Hit list load failed: {error}",
    "analyze.hitList.detailsTitle": "Hit List Details",
    "analyze.hitList.summary":
      "Showing {shown}/{filtered} candidates (total {total}), median score {score}.",
    "analyze.hitList.empty": "No candidates matched the cutoff.",
    "analyze.chart.select": "Chart",
    "analyze.chart.placeholder": "Run hit list to render candidate charts.",
    "analyze.chart.noData": "No numeric data for the selected chart in current filters.",
    "analyze.chart.option.plddtRmsd": "Scatter: pLDDT vs RMSD vs WT",
    "analyze.chart.option.scoreHist": "Histogram: Hit Score",
    "analyze.chart.option.tierPass": "Tier AF2 Pass Rate",
    "analyze.chart.axis.plddt": "pLDDT",
    "analyze.chart.axis.rmsd": "RMSD (A)",
    "analyze.chart.axis.score": "Hit Score",
    "analyze.chart.axis.passRate": "Pass Rate (%)",
    "analyze.chart.axis.count": "Count",
    "analyze.chart.axis.tier": "Tier",
    "analyze.chart.legend.selected": "{af2Provider} selected",
    "analyze.chart.legend.unselected": "Not selected",
    "analyze.chart.legend.wt": "WT",
    "analyze.chart.caption.rows": "Rows={rows} (cutoff >= {cutoff})",
    "analyze.chart.caption.scatter": "Points={points}, selected={selected}",
    "analyze.chart.caption.scatterPoints": "Points={points}",
    "analyze.chart.caption.scatterWithWt": "Points={points}, selected={selected}, WT={wt}",
    "analyze.chart.caption.hist": "Values={values}, bins={bins}",
    "analyze.chart.caption.tier": "Tiers={tiers}, rows={rows}",
    "analyze.files.title": "Artifact File Viewer",
    "analyze.files.desc": "Preview PDB/FASTA/CSV and text artifacts in Analyze.",
    "analyze.files.select": "Artifact File",
    "analyze.files.open": "Open",
    "analyze.files.placeholder": "Select an artifact file to preview it in Analyze.",
    "analyze.files.none": "No file artifacts are available for this run.",
    "residue.linked.title": "Residue-linked view",
    "residue.linked.help": "Click a residue chip or row to highlight it on both structures.",
    "residue.linked.empty": "No residue-level metric was produced for this comparison.",
    "residue.linked.selected": "Selected: chain {chain} residue {resi} ({left}->{right}) dist={dist}A",
    "residue.linked.selectedNone": "Selected: none",
    "metrics.parseError": "Failed to parse metrics: {error}",
    "metrics.objectRequired": "metrics must be a JSON object",
    "auth.required": "Username and password required.",
    "auth.loginFailed": "Login failed",
    "auth.sessionInvalid": "Session invalid",
    "auth.createFailed": "Create user failed",
    "auth.created": "Created {username}.",
    "error.api": "API error",
    "health.checking": "Checking...",
    "health.ok": "OK",
  },
  ko: {
    "brand.subtitle": "단백질 파이프라인 콘솔",
    "action.admin": "관리자",
    "action.settings": "설정",
    "action.logout": "로그아웃",
    "action.help": "사용법",
    "tabs.setup": "설정",
    "tabs.monitor": "모니터",
    "tabs.analyze": "분석",
    "copilot.open": "Copilot",
    "copilot.title": "Context Copilot",
    "copilot.desc": "현재 run/화면 데이터를 바탕으로 사용법과 해석을 도와줍니다.",
    "copilot.context.title": "현재 컨텍스트",
    "copilot.context.empty": "run을 선택하면 컨텍스트를 표시합니다.",
    "copilot.quick.title": "빠른 질문",
    "copilot.quick.usage": "이 화면 사용법",
    "copilot.quick.interpret": "현재 지표 해석",
    "copilot.quick.summary": "현재 run 요약",
    "copilot.quick.compare": "비교 상태 설명",
    "copilot.quick.next": "다음에 뭘 할까?",
    "copilot.quick.resume": "재시작은 어떻게 해?",
    "copilot.summary.title": "라이브 스냅샷",
    "copilot.summary.empty": "run을 열면 현재 상태 스냅샷을 구성합니다.",
    "copilot.actions.title": "추천 액션",
    "copilot.actions.empty": "run을 선택하면 바로 실행 가능한 액션이 표시됩니다.",
    "copilot.conversation.title": "대화",
    "copilot.clear": "지우기",
    "copilot.role.user": "사용자",
    "copilot.role.ai": "Copilot",
    "copilot.action.openSetup": "Setup 열기",
    "copilot.action.openSetup.desc": "입력을 채우고 새 run을 시작합니다.",
    "copilot.action.openMonitor": "Monitor 열기",
    "copilot.action.openMonitor.desc": "상태, 에러, 아티팩트 진행을 확인합니다.",
    "copilot.action.openAnalyze": "Analyze 열기",
    "copilot.action.openAnalyze.desc": "Hit List, 차트, 비교 스튜디오를 검토합니다.",
    "copilot.action.poll": "지금 조회",
    "copilot.action.poll.desc": "현재 run 상태를 즉시 새로고칩니다.",
    "copilot.action.refreshArtifacts": "아티팩트 새로고침",
    "copilot.action.refreshArtifacts.desc": "파일 산출물과 미리보기 선택지를 다시 불러옵니다.",
    "copilot.action.refreshHitList": "Hit List 새로고침",
    "copilot.action.refreshHitList.desc": "현재 run 후보 랭킹을 다시 계산합니다.",
    "copilot.action.generateReport": "리포트 생성",
    "copilot.action.generateReport.desc": "비교 요약과 리포트 산출물을 새로 만듭니다.",
    "copilot.action.resume": "Run 재시작",
    "copilot.action.resume.desc": "중단된 run을 저장된 request 기준으로 이어갑니다.",
    "copilot.action.compare3d": "3D 비교 실행",
    "copilot.action.compare3d.desc": "선택한 좌/우 구조를 바로 렌더링합니다.",
    "copilot.action.completed": "{action} 완료.",
    "copilot.action.failed": "{action} 실패: {error}",
    "copilot.input.placeholder": "현재 run 또는 화면 사용법을 질문하세요",
    "copilot.send": "보내기",
    "analyze.kpi.feedback": "피드백",
    "analyze.kpi.experiment": "실험",
    "analyze.kpi.recommendation": "권고",
    "login.title": "랩 입장",
    "login.desc": "실행을 구분하고 아티팩트를 정리하기 위해 계정을 확인합니다.",
    "login.username": "사용자명",
    "login.username.placeholder": "예: hana.kim",
    "login.password": "비밀번호",
    "login.password.placeholder": "••••••••",
    "login.submit": "콘솔 접속",
    "setup.title": "실행 설정",
    "setup.desc": "워크플로를 선택하고 입력을 첨부해 실행하세요.",
    "setup.section.input": "입력",
    "setup.section.inputDesc": "필수 파일을 첨부하고 선택적으로 메모를 남기세요.",
    "setup.section.execution": "실행 설정",
    "setup.section.executionDesc": "실행 모드와 단계 옵션을 설정하세요.",
    "setup.section.monitor": "모니터링",
    "setup.section.monitorDesc": "실행 준비 중에도 진행률과 오류를 바로 확인합니다.",
    "setup.section.log": "활동 로그",
    "setup.section.logDesc": "사전 점검 및 실행 메시지를 확인합니다.",
    "setup.openMonitor": "모니터 열기",
    "setup.prompt.placeholder": "프롬프트/메모 입력 (key=value 지원).",
    "setup.check": "설정 점검",
    "setup.reset": "입력 초기화",
    "setup.clear": "메모 지우기",
    "setup.hint": "필수 입력을 완료하면 실행할 수 있습니다.",
    "setup.runStatus.empty": "실행 상태: -",
    "setup.runStatus.line": "실행 상태: {id} · {stage} / {state} · {updated}",
    "setup.residuePicker.title": "잔기 선택기 (선택)",
    "setup.residuePicker.help":
      "구조에서 잔기를 선택해 fixed_positions_extra에 추가합니다. target_pdb가 없으면 먼저 1회 실행해 target.pdb({af2Provider} target)를 만든 뒤, 선택한 run에서 불러오세요.",
    "setup.residuePicker.source": "구조 소스: {source}",
    "setup.residuePicker.source.none": "없음",
    "setup.residuePicker.loadTargetInput": "target_input PDB 불러오기",
    "setup.residuePicker.loadRfd3Input": "rfd3_input_pdb 불러오기",
    "setup.residuePicker.loadRunTarget": "선택 run의 target.pdb 불러오기",
    "setup.residuePicker.runAf2": "FASTA로 {af2Provider} 실행",
    "setup.residuePicker.runAf2Running": "target 구조 생성을 위해 {af2Provider}를 실행 중입니다...",
    "setup.residuePicker.runAf2NeedsFasta": "먼저 target_input에 FASTA/서열을 첨부하세요.",
    "setup.residuePicker.runAf2NoResult": "{af2Provider}는 완료됐지만 ranked_0.pdb를 찾지 못했습니다.",
    "setup.residuePicker.runAf2Loaded": "{run}:{path} 에서 {af2Provider} 구조를 불러왔습니다.",
    "setup.residuePicker.runAf2Failed": "{af2Provider} 실행 실패: {error}",
    "setup.residuePicker.viewerPlaceholder": "잔기 선택을 시작하려면 구조를 불러오세요.",
    "setup.residuePicker.viewerUnavailable": "3D 뷰어를 사용할 수 없습니다.",
    "setup.residuePicker.selection.none": "선택된 잔기가 없습니다.",
    "setup.residuePicker.selection.summary": "선택 잔기: {summary}",
    "setup.residuePicker.apply": "fixed_positions_extra에 반영",
    "setup.residuePicker.clearSelection": "선택 초기화",
    "setup.residuePicker.note":
      "반영 값은 체인별 서열 순서 인덱스(query position) 기준으로 저장되어 ProteinMPNN 제약에 사용됩니다.",
    "setup.residuePicker.applied": "{count}개 위치를 fixed_positions_extra에 반영했습니다.",
    "setup.residuePicker.loadFailed": "구조 로드 실패: {error}",
    "setup.residuePicker.noRun": "먼저 run을 선택하세요.",
    "setup.residuePicker.noSelection": "최소 1개 잔기를 선택하세요.",
    "setup.residuePicker.noPdb": "이 소스에서 사용할 PDB 텍스트가 없습니다.",
    "preflight.title": "설정 점검",
    "preflight.ok": "실행을 막는 문제는 없습니다.",
    "preflight.blocked": "아래 문제를 해결해야 실행할 수 있습니다.",
    "preflight.errors": "오류",
    "preflight.warnings": "경고",
    "preflight.required": "추가 입력 필요",
    "preflight.questions": "질문",
    "preflight.detected": "감지된 사항",
    "preflight.routed": "프롬프트 라우팅",
    "preflight.failed": "점검 실패: {error}",
    "preflight.unavailable": "{mode} 모드에서는 설정 점검이 제공되지 않습니다.",
    "monitor.title": "실행 모니터",
    "monitor.desc": "상태, 점수, 최근 실행을 확인합니다.",
    "monitor.runId": "실행 ID",
    "monitor.selectRun": "실행 선택",
    "monitor.stage": "단계",
    "monitor.state": "상태",
    "monitor.updated": "업데이트",
    "monitor.eta": "예상 남은 시간",
    "monitor.detail": "세부",
    "monitor.progress": "진행률",
    "monitor.progress.backbone": "백본",
    "monitor.progress.wt": "WT 기준선",
    "monitor.progress.masking": "마스킹",
    "monitor.progress.done": "완료",
    "monitor.scoring": "점수",
    "monitor.completeness": "데이터 완전성",
    "monitor.completeness.placeholder": "실행을 선택하면 데이터 완전성을 표시합니다.",
    "monitor.completeness.badge.rfd3Ready": "RFD3 준비됨",
    "monitor.completeness.badge.rfd3Missing": "RFD3 없음",
    "monitor.completeness.badge.bioemuReady": "BioEmu 준비됨",
    "monitor.completeness.badge.bioemuMissing": "BioEmu 없음",
    "monitor.completeness.badge.bioemuOnly": "BioEmu 전용",
    "monitor.completeness.badge.wtOn": "WT 비교 사용",
    "monitor.completeness.badge.wtOff": "WT 비교 꺼짐",
    "monitor.completeness.badge.af2None": "{af2Provider} 선발 없음",
    "monitor.completeness.badge.af2Some": "{af2Provider} 선발 {count}",
    "monitor.workflow.title": "워크플로우 검토 게이트",
    "monitor.workflow.waiting": "체크포인트까지 실행 중: {stage}",
    "monitor.workflow.ready": "{stage} 체크포인트에 도달했습니다. 그래프를 확인하고 다음 동작을 선택하세요.",
    "monitor.workflow.completed": "워크플로우가 최종 단계까지 완료되었습니다: {stage}",
    "monitor.workflow.chart.empty": "아티팩트 카운트가 아직 없습니다. 체크포인트 이후 아티팩트를 새로고침하세요.",
    "monitor.workflow.checkpoints": "체크포인트: {stages}",
    "monitor.workflow.nextStage": "다음 단계: {stage}",
    "monitor.workflow.finalStage": "최종 단계: {stage}",
    "monitor.workflow.continue": "다음 단계로 계속",
    "monitor.workflow.continueStarted": "{id} run을 {start} -> {stop} 로 계속 실행합니다...",
    "monitor.workflow.continueFailed": "워크플로우 이어서 실행 실패: {error}",
    "monitor.workflow.rerunLabel": "재실행 대상 단계",
    "monitor.workflow.rerunAction": "해당 단계까지 재실행",
    "monitor.workflow.rerunConfirm":
      "{id} run 기준으로 MSA부터 {stage}까지 새 run을 재실행할까요? 비교용 별도 run이 생성됩니다.",
    "monitor.workflow.rerunStarted": "단계 재실행 시작: {id} ({start} -> {stop})",
    "monitor.workflow.rerunFailed": "단계 재실행 실패: {error}",
    "monitor.workflow.resultsTitle": "체크포인트 결과",
    "monitor.workflow.resultsHint": "현재까지 생성된 아티팩트 {count}개입니다. 항목을 클릭하면 미리보기가 열립니다.",
    "monitor.workflow.resultsEmpty": "아직 결과 아티팩트가 없습니다.",
    "monitor.workflow.resultsUnknown": "미분류",
    "monitor.workflow.resultsDisabled": "설정에서 체크포인트 결과 패널 표시를 꺼둔 상태입니다.",
    "monitor.workflow.mmseq": "MMseqs 재실행",
    "monitor.workflow.mmseqConfirm":
      "{id} run 기준으로 MSA 단계에서 MMseqs를 다시 실행할까요? 비교를 위해 새 run이 생성됩니다.",
    "monitor.workflow.mmseqStarted": "MMseqs 재실행 시작: {id}",
    "monitor.workflow.mmseqFailed": "MMseqs 재실행 실패: {error}",
    "monitor.workflow.openAnalyze": "분석 탭 열기",
    "monitor.poll": "지금 조회",
    "monitor.stop": "정지",
    "monitor.resume": "재시작",
    "monitor.stopConfirm": "{id} 실행을 취소할까요? RunPod 작업 취소가 요청됩니다.",
    "monitor.stopSuccess": "{id} 실행 취소 요청 완료 (jobs: {count}).",
    "monitor.stopFailed": "취소 실패: {error}",
    "monitor.autoPoll": "자동 조회",
    "monitor.recentRuns": "최근 실행",
    "monitor.refreshRuns": "새로고침",
    "monitor.showAll": "모든 실행 보기 (관리자)",
    "monitor.activity": "활동 로그",
    "monitor.clearLog": "지우기",
    "agent.title": "에이전트 패널",
    "agent.desc": "단계별 전문가 합의와 복구 기록을 확인합니다.",
    "agent.refresh": "새로고침",
    "agent.viewReport": "리포트 보기",
    "agent.viewAgentReport": "에이전트 리포트",
    "agent.report.loading": "리포트를 불러오는 중...",
    "agent.report.missing": "아직 리포트가 없습니다.",
    "agent.report.failed": "리포트 로드 실패: {error}",
    "agent.feedback.good": "좋음",
    "agent.feedback.bad": "나쁨",
    "agent.feedback.note": "메모 (선택)",
    "agent.feedback.saving": "저장 중...",
    "agent.feedback.saved": "저장됨",
    "agent.feedback.failed": "저장 실패: {error}",
    "report.modal.download": "다운로드",
    "report.modal.toggleRendered": "렌더링",
    "report.modal.toggleRaw": "원문",
    "agent.loading": "에이전트 패널 불러오는 중...",
    "agent.empty": "아직 에이전트 이벤트가 없습니다.",
    "agent.failed": "에이전트 패널 로드 실패: {error}",
    "artifacts.title": "아티팩트",
    "artifacts.desc": "실행 결과 아티팩트를 필터링합니다.",
    "artifacts.monitorHint.title": "비교 기능은 Analyze 탭으로 이동",
    "artifacts.monitorHint.desc":
      "3D 구조 비교와 리포트 기반 비교 요약은 Analyze 탭에서 확인할 수 있습니다.",
    "artifacts.monitorHint.action": "Analyze 열기",
    "artifacts.filter.placeholder": "이름 또는 단계로 필터",
    "artifacts.refresh": "새로고침",
    "artifacts.filter.allStages": "전체 단계",
    "artifacts.filter.allTiers": "전체 티어",
    "artifacts.filter.allTypes": "전체 형식",
    "artifacts.filter.stage": "단계",
    "artifacts.filter.tier": "티어",
    "artifacts.filter.type": "형식",
    "artifacts.compare.title": "비교 요약",
    "artifacts.compare.desc": "리포트에서 생성된 WT 비교와 RFD3/BioEmu 비교 지표를 보여줍니다.",
    "artifacts.compare.placeholder": "리포트를 생성하면 비교 지표를 불러올 수 있습니다.",
    "artifacts.compare.noData": "이 실행에는 비교 데이터가 없습니다.",
    "artifacts.compare.viewDetails": "상세 보기",
    "artifacts.compare.detailsTitle": "비교 상세",
    "artifacts.compare.generateReport": "리포트 생성",
    "artifacts.compare.wt": "WT 대비 Design",
    "artifacts.compare.funnel": "선발 Funnel",
    "artifacts.compare.funnelBackbone": "백본 수",
    "artifacts.compare.funnelSoluprot": "SoluProt 통과",
    "artifacts.compare.funnelAf2": "{af2Provider} 통과",
    "artifacts.compare.funnelRetain": "백본 대비 유지율",
    "artifacts.compare.source": "RFD3 대비 BioEmu",
    "artifacts.compare.metric": "지표",
    "artifacts.compare.wtValue": "WT",
    "artifacts.compare.designMedian": "Design 중앙값",
    "artifacts.compare.delta": "차이",
    "artifacts.compare.wtEnabled": "WT 비교 사용: {enabled}",
    "artifacts.compare.sourceName": "소스",
    "artifacts.compare.backbones": "백본 수",
    "artifacts.compare.passRate": "SoluProt 통과",
    "artifacts.compare.soluprotMedian": "SoluProt 중앙값",
    "artifacts.compare.af2Selected": "{af2Provider} 선발",
    "artifacts.compare.plddtMedian": "pLDDT 중앙값",
    "artifacts.compare.rmsdMedian": "RMSD 중앙값",
    "artifacts.preview.title": "아티팩트 미리보기",
    "artifacts.preview.desc": "3D 구조, 이미지, 텍스트 미리보기.",
    "artifacts.preview.placeholder": "아티팩트를 선택하면 여기서 미리보기를 볼 수 있습니다.",
    "artifacts.preview.compare.mode.structure": "구조 차이",
    "artifacts.preview.compare.mode.sequence": "서열 차이",
    "artifacts.preview.compare.left": "기준 3D",
    "artifacts.preview.compare.right": "후보 3D",
    "artifacts.preview.compare.run": "3D 비교",
    "artifacts.preview.compare.swap": "좌우 전환",
    "artifacts.preview.compare.clear": "초기화",
    "artifacts.preview.compare.missing": "좌/우 3D 아티팩트를 모두 선택하세요.",
    "artifacts.preview.compare.failed": "3D 비교 실패: {error}",
    "artifacts.preview.compare.refs.title": "기준선",
    "artifacts.preview.compare.refs.input": "입력 구조",
    "artifacts.preview.compare.refs.working": "작업 백본",
    "artifacts.preview.compare.refs.wt": "WT ColabFold",
    "artifacts.preview.compare.refs.missing": "없음",
    "artifacts.preview.compare.preset.title": "빠른 비교",
    "artifacts.preview.compare.preset.inputVsWt": "입력 vs WT",
    "artifacts.preview.compare.preset.inputVsWorking": "입력 vs 작업",
    "artifacts.preview.compare.preset.inputVsRfd3": "입력 vs RFD3",
    "artifacts.preview.compare.preset.inputVsBioemu": "입력 vs BioEmu",
    "artifacts.preview.compare.preset.wtVsRfd3": "WT vs RFD3",
    "artifacts.preview.compare.preset.wtVsBioemu": "WT vs BioEmu",
    "artifacts.preview.compare.preset.rfd3VsBioemu": "RFD3 vs BioEmu",
    "artifacts.preview.compare.group.references": "기준 구조",
    "artifacts.preview.compare.group.backbones": "백본 스냅샷",
    "artifacts.preview.compare.group.af2": "{af2Provider} 후보",
    "artifacts.preview.compare.group.source": "소스 출력",
    "artifacts.preview.compare.group.other": "기타 구조",
    "artifacts.preview.compare.sequenceTitle": "서열 (FASTA)",
    "artifacts.preview.compare.sequenceLeft": "기준",
    "artifacts.preview.compare.sequenceRight": "후보",
    "artifacts.preview.compare.sequenceEmpty": "해당 구조에서 서열을 추출하지 못했습니다.",
    "artifacts.preview.compare.diffLegendStructure":
      "CA 정렬 후 구조 차이: <=1.5A 회색, 1.5-3.0A 노랑, >3.0A 빨강, gap WT 파랑 / Design 주황",
    "artifacts.preview.compare.diffLegendSequence":
      "잔기 동일성 기준 차이: WT 쪽 불일치 파랑, Design 쪽 불일치 주황, 동일 잔기 회색",
    "artifacts.preview.compare.diffNone": "잔기 기준 차이가 감지되지 않았습니다.",
    "artifacts.preview.compare.meta.title": "비교 컨텍스트",
    "artifacts.preview.compare.meta.left": "기준",
    "artifacts.preview.compare.meta.right": "후보",
    "artifacts.preview.compare.meta.role": "역할",
    "artifacts.preview.compare.meta.source": "소스",
    "artifacts.preview.compare.meta.provenance": "계보",
    "artifacts.preview.compare.meta.tier": "티어",
    "artifacts.preview.compare.meta.backbone": "백본",
    "artifacts.preview.compare.meta.chains": "체인",
    "artifacts.preview.compare.meta.fixedCount": "고정 잔기 수",
    "artifacts.preview.compare.meta.wtDiff": "WT 서열 차이",
    "artifacts.preview.compare.meta.inputStructRmsd": "입력 구조 RMSD",
    "artifacts.preview.compare.meta.wtStructRmsd": "WT CF RMSD",
    "artifacts.preview.compare.meta.workingStructRmsd": "작업 백본 RMSD",
    "artifacts.preview.compare.meta.commonCa": "공통 CA",
    "artifacts.preview.compare.meta.predScope": "{af2Provider} 범위",
    "artifacts.preview.compare.meta.predScopeExact": "정확 후보",
    "artifacts.preview.compare.meta.predScopeWt": "WT 기준",
    "artifacts.preview.compare.meta.predScopeTier": "티어 요약",
    "artifacts.preview.compare.meta.predScopeBackbone": "백본 요약",
    "artifacts.preview.compare.meta.predScopePre": "{af2Provider} 전",
    "artifacts.preview.compare.meta.predSelected": "{af2Provider} 선발",
    "artifacts.preview.compare.meta.predPlddt": "{af2Provider} pLDDT",
    "artifacts.preview.compare.meta.predRmsd": "{af2Provider} RMSD",
    "artifacts.preview.compare.meta.path": "경로",
    "artifacts.preview.compare.role.input_reference": "입력 구조",
    "artifacts.preview.compare.role.working_backbone": "작업 백본",
    "artifacts.preview.compare.role.wt_colabfold": "WT ColabFold",
    "artifacts.preview.compare.role.backbone_snapshot": "백본 스냅샷",
    "artifacts.preview.compare.role.af2_candidate": "{af2Provider} 후보",
    "artifacts.preview.compare.role.source_output": "소스 출력",
    "artifacts.preview.compare.role.structure_artifact": "구조 아티팩트",
    "artifacts.preview.compare.provenance.input": "원래 실행 입력 구조 스냅샷",
    "artifacts.preview.compare.provenance.inputRfd3": "원래 실행 입력 구조 스냅샷 (RFD3 유래)",
    "artifacts.preview.compare.provenance.working": "downstream 단계에 사용된 primary 백본 복사본",
    "artifacts.preview.compare.provenance.wt": "WT 서열을 {af2Provider}로 예측한 구조",
    "artifacts.preview.compare.provenance.backbone": "{source} 백본 스냅샷",
    "artifacts.preview.compare.provenance.candidate": "티어 {tier} 후보 ({af2Provider})",
    "artifacts.preview.compare.provenance.source": "{source} 소스 단계 출력",
    "artifacts.preview.compare.provenance.other": "구조 아티팩트",
    "feedback.title": "피드백",
    "feedback.desc": "전문가 평가와 등급을 기록합니다.",
    "feedback.rating": "평가",
    "feedback.reasons": "사유",
    "feedback.artifact": "아티팩트 (선택)",
    "feedback.stage": "단계 (선택)",
    "feedback.comment": "코멘트",
    "feedback.comment.placeholder": "짧은 맥락 또는 해석",
    "feedback.submit": "피드백 제출",
    "feedback.exportCsv": "CSV 내보내기",
    "feedback.exportTsv": "TSV 내보내기",
    "feedback.recent": "최근 피드백",
    "experiment.title": "실험",
    "experiment.desc": "습식 실험 결과와 지표를 기록합니다.",
    "experiment.assay": "실험 유형",
    "experiment.result": "결과",
    "experiment.sample": "샘플 ID (선택)",
    "experiment.sample.placeholder": "예: seq_001",
    "experiment.artifact": "아티팩트 (선택)",
    "experiment.metrics": "지표 (JSON, 선택)",
    "experiment.metrics.placeholder": "{\"kd_nM\": 12.5, \"t50_C\": 48}",
    "experiment.conditions": "조건 / 노트",
    "experiment.conditions.placeholder": "버퍼, 온도, 실험 조건",
    "experiment.submit": "실험 등록",
    "experiment.exportCsv": "CSV 내보내기",
    "experiment.exportTsv": "TSV 내보내기",
    "experiment.recent": "최근 실험",
    "report.title": "리포트",
    "report.desc": "실행 결과를 요약한 리포트를 생성합니다.",
    "report.label": "리포트 (Markdown)",
    "report.placeholder": "리포트를 생성하거나 편집하세요",
    "report.load": "불러오기",
    "report.generate": "생성",
    "report.viewRendered": "렌더링 보기",
    "report.exportPackage": "결과 패키지",
    "report.save": "저장",
    "report.links": "아티팩트 링크",
    "report.chart.title": "리포트 차트",
    "report.chart.desc": "현재 Hit List 데이터에서 선택한 차트 1개를 렌더링합니다.",
    "report.chart.select": "차트 유형",
    "report.chart.placeholder": "Hit List를 불러오면 리포트 차트를 표시합니다.",
    "report.chart.sectionTitle": "후보 차트 (SVG 첨부)",
    "report.chart.sectionEmpty": "아직 차트 데이터를 만들 수 없습니다.",
    "report.compare.sectionTitle": "구조/서열 차이 (SVG 첨부)",
    "report.compare.sectionEmpty": "자동 구조/서열 차이를 만들 수 있는 PDB 아티팩트가 부족합니다.",
    "report.compare.left": "기준",
    "report.compare.right": "후보",
    "report.hitList.title": "Hit List",
    "report.hitList.empty": "아직 Hit List 데이터가 없습니다.",
    "report.hitList.summary": "행: {shown}/{total} (컷오프 >= {cutoff})",
    "report.review.title": "리포트 평가",
    "report.review.desc": "리포트를 평가하고 이유를 입력하세요.",
    "report.review.rating": "평가",
    "report.review.reasons": "이유",
    "report.review.comment": "코멘트",
    "report.review.comment.placeholder": "선택 사항",
    "report.review.submit": "평가 저장",
    "report.review.saved": "리포트 평가를 저장했습니다.",
    "report.review.failed": "평가 실패: {error}",
    "report.review.reason.clear": "요약이 명확함",
    "report.review.reason.actionable": "실행 가능한 가이드",
    "report.review.reason.complete": "내용이 충실함",
    "report.review.reason.missing_metrics": "핵심 지표 누락",
    "report.review.reason.inaccurate": "내용 부정확",
    "report.review.reason.confusing": "이해하기 어려움",
    "report.review.reason.other": "기타",
    "settings.title": "설정",
    "settings.baseLabel": "MCP HTTP 기본 URL",
    "settings.baseHint": "이 값은 서버 설정으로 고정됩니다.",
    "settings.reportLang.label": "리포트 언어",
    "settings.reportLang.auto": "UI 언어 따라감",
    "settings.reportLang.en": "영어",
    "settings.reportLang.ko": "한국어",
    "settings.reportLang.hint": "실행 리포트와 에이전트 리포트에 적용됩니다.",
    "settings.health": "헬스 체크",
    "role.admin": "관리자",
    "role.user": "사용자",
    "admin.title": "관리자: 사용자 생성",
    "admin.username": "새 사용자명",
    "admin.username.placeholder": "new.user",
    "admin.password": "새 비밀번호",
    "admin.password.placeholder": "최소 8자",
    "admin.role": "권한",
    "admin.role.user": "사용자",
    "admin.role.admin": "관리자",
    "admin.create": "사용자 생성",
    "help.title": "사용 가이드",
    "help.quick.title": "빠른 시작",
    "help.quick.step1": "Setup: 모드를 선택하고 입력을 첨부한 뒤 실행합니다.",
    "help.quick.step2": "Monitor: 상태를 확인하고 아티팩트를 살펴봅니다.",
    "help.quick.step3": "Analyze: 피드백, 실험, 리포트를 기록합니다.",
    "help.setup.title": "설정 팁",
    "help.setup.step1": "Run Mode에서 파이프라인 또는 특정 도구를 선택합니다.",
    "help.setup.step2": "필수 파일을 첨부하세요. 미입력 시 Run이 비활성화됩니다.",
    "help.monitor.title": "모니터링",
    "help.monitor.step1": "최근 실행을 선택하면 상태와 아티팩트가 로드됩니다.",
    "help.monitor.step2": "자동 조회를 사용하면 실시간으로 갱신됩니다.",
    "help.analyze.title": "분석",
    "help.analyze.step1": "Compare Studio, Run-to-Run, Hit List로 먼저 정량 선별을 진행합니다.",
    "help.analyze.step2": "3D 구조 차이와 WT/RFD3/BioEmu 비교 요약을 확인합니다.",
    "help.analyze.step3": "그다음 피드백/실험을 기록하고 리포트를 마무리합니다.",
    "help.admin.title": "관리자",
    "help.admin.step1": "관리자는 Admin 버튼에서 사용자를 생성할 수 있습니다.",
    "common.close": "닫기",
    "common.none": "없음",
    "common.score": "점수",
    "common.evidence": "근거",
    "common.recommendation": "추천",
    "runs.delete": "삭제",
    "runs.deleteConfirm": "실행 {id}을(를) 삭제할까요? 되돌릴 수 없습니다.",
    "runs.deleteFailed": "삭제 실패: {error}",
    "runs.deleteSuccess": "실행 삭제됨: {id}",
    "question.runMode.label": "실행 모드",
    "question.runMode.help": "실행할 항목을 선택하세요.",
    "question.runMode.detail": "모드에 따라 필요한 입력, 실행 시간, 출력 깊이가 달라집니다.",
    "question.targetInput.label": "타깃 입력",
    "question.targetInput.help": "target_pdb 또는 target_fasta 원문을 입력하세요.",
    "question.startFrom.label": "시작 단계",
    "question.startFrom.help": "어디부터 실행할까요? 가능하면 이전 단계 캐시를 재사용합니다.",
    "question.stopAfter.label": "중단 단계",
    "question.stopAfter.help": "어디까지 실행할까요? (msa/rfd3/bioemu/design/soluprot/af2/wt_diff)",
    "question.designChains.label": "디자인 체인",
    "question.designChains.help": "디자인할 체인을 선택하세요. (기본: 전체)",
    "question.wtCompare.label": "WT 비교",
    "question.wtCompare.help": "WT 기준(SoluProt/{af2Provider})을 계산해 리포트에 비교합니다.",
    "question.maskConsensusApply.label": "합의 마스킹 적용",
    "question.maskConsensusApply.help": "전문가 합의 마스킹을 ProteinMPNN에 적용합니다.",
    "question.bioemuUse.label": "BioEmu 사용",
    "question.bioemuUse.help": "BioEmu backbone 샘플링 단계를 실행합니다.",
    "question.bioemuNumSamples.label": "BioEmu 샘플 수",
    "question.bioemuNumSamples.help": "생성할 BioEmu 샘플 개수입니다.",
    "question.bioemuMaxReturn.label": "BioEmu 반환 개수",
    "question.bioemuMaxReturn.help": "보존할 BioEmu 구조 최대 개수입니다.",
    "question.numSeqPerTier.label": "티어당 ProteinMPNN 개수",
    "question.numSeqPerTier.help": "각 티어/백본마다 생성할 ProteinMPNN 서열 개수입니다.",
    "question.af2MaxCandidatesPerTier.label": "{af2Provider} 티어당 실행 개수 (상위 N개)",
    "question.af2MaxCandidatesPerTier.help":
      "티어별 SoluProt 통과 서열 중 상위 N개(점수 순)만 {af2Provider}를 실행합니다. 0이면 전체 실행.",
    "question.af2PlddtCutoff.label": "{af2Provider} pLDDT 컷오프",
    "question.af2PlddtCutoff.help": "{af2Provider} 통과 필터링에 사용할 최소 pLDDT 임계값입니다. (기본값: 85)",
    "question.af2RmsdCutoff.label": "{af2Provider} RMSD 컷오프",
    "question.af2RmsdCutoff.help": "{af2Provider} 통과 필터링에 사용할 최대 RMSD 임계값(Å)입니다. (기본값: 2.0)",
    "question.noveltyEnabled.label": "WT Diff",
    "question.noveltyEnabled.help": "AF2 선택 서열에 대해 마지막 WT Diff 비교를 실행합니다.",
    "question.af2Provider.label": "구조 예측기",
    "question.af2Provider.help": "구조 예측 provider를 선택하세요.",
    "question.rfd3MaxReturn.label": "RFD3 반환 개수",
    "question.rfd3MaxReturn.help": "보존할 RFD3 백본 디자인 최대 개수입니다.",
    "question.confirmRun.label": "실행 확인",
    "question.confirmRun.help": "해석된 설정을 확인한 뒤 실행을 승인하세요.",
    "question.fixedPositionsExtra.label": "고정 위치 추가",
    "question.fixedPositionsExtra.help": "디자인 전 반드시 보존할 위치입니다(선택). JSON({\"A\":[6,10],\"*\":[120]}) 또는 단축표기(A:6,10;*:120) 사용.",
    "question.ligandMaskOriginal.label": "원본 리간드 마스크 보존",
    "question.ligandMaskOriginal.help": "원본 target_pdb/rfd3_input_pdb의 리간드 접촉 잔기를 현재 백본에 투영해 보존합니다.",
    "question.stripNonpositive.label": "음수 잔기 제거",
    "question.stripNonpositive.help": "RFD3 및 이후 단계 전에 resseq <= 0 잔기를 제거합니다.",
    "question.rfd3InputPdb.label": "RFD3 입력 PDB",
    "question.rfd3InputPdb.help": "rfd3_input_pdb 원문을 입력하세요.",
    "question.rfd3Contig.label": "RFD3 컨티그",
    "question.rfd3Contig.help": "rfd3_contig 형식 (예: A1-221, 콜론 없이).",
    "question.diffdockLigand.label": "DiffDock 리간드",
    "question.diffdockLigand.help": "diffdock_ligand_smiles 또는 diffdock_ligand_sdf를 입력하세요.",
    "question.targetFasta.label": "타깃 FASTA",
    "question.targetFasta.help": "{af2ProviderPair}용 FASTA 또는 서열을 입력하세요.",
    "question.proteinPdb.label": "단백질 PDB",
    "question.proteinPdb.help": "DiffDock용 단백질 PDB 원문을 입력하세요.",
    "question.ligandInput.label": "리간드 입력",
    "question.ligandInput.help": "DiffDock용 리간드 SMILES 또는 SDF를 입력하세요.",
    "attachment.title": "첨부파일",
    "attachment.help": "필수 입력에 필요한 파일을 첨부하세요.",
    "attachment.select": "파일 선택",
    "attachment.clear": "삭제",
    "attachment.none": "선택된 파일 없음.",
    "attachment.attached": "첨부됨: {name} ({kb} KB)",
    "attachment.attachedName": "첨부됨: {name}",
    "attachment.failed": "파일 읽기 실패: {error}",
    "attachment.diffdock.use": "DiffDock 사용",
    "attachment.diffdock.skip": "건너뜀",
    "choice.allChains": "전체 체인",
    "choice.chainNote": "타깃 PDB를 업로드하면 체인 선택이 활성화됩니다.",
    "choice.chainDefaultNote": "팁: target FASTA가 없으면 기본적으로 주 체인만 사용합니다. 멀티체인 설계나 짧은 체인 불일치 방지를 위해 체인을 명시적으로 선택하세요.",
    "choice.contigNone": "선택 안함 (RFD3 사용 안함)",
    "choice.contigNote": "PDB를 업로드하면 rfd3_contig 옵션이 제안됩니다.",
    "choice.contigPositiveOnly": "컨티그 제안은 단백질 잔기(ATOM 및 일부 아미노산 HETATM) 중 양수 번호만 사용합니다.",
    "choice.stripNonpositive.on": "제거 (권장)",
    "choice.stripNonpositive.off": "그대로 유지",
    "choice.wtCompare.on": "WT 비교 사용",
    "choice.wtCompare.off": "WT 비교 사용 안 함",
    "choice.maskConsensusApply.on": "합의 적용",
    "choice.maskConsensusApply.off": "적용 안 함",
    "choice.ligandMaskOriginal.on": "원본 마스크 보존",
    "choice.ligandMaskOriginal.off": "현재 백본 기준만 사용",
    "choice.bioemuUse.on": "BioEmu 사용",
    "choice.bioemuUse.off": "BioEmu 사용 안 함",
    "choice.novelty.on": "WT Diff 사용",
    "choice.novelty.off": "WT Diff 사용 안 함",
    "choice.af2Provider.colabfold": "ColabFold (기본)",
    "choice.af2Provider.af2": "AlphaFold2",
    "advanced.bioemuCounts.title": "BioEmu 개수 옵션",
    "advanced.bioemuCounts.help": "선택 입력이며 기본으로 숨김입니다.",
    "advanced.bioemuCounts.show": "BioEmu 개수 옵션 보기",
    "advanced.bioemuCounts.hide": "BioEmu 개수 옵션 숨기기",
    "advanced.rfd3Counts.title": "RFD3 개수 옵션",
    "advanced.rfd3Counts.help": "선택 입력이며 기본으로 숨김입니다.",
    "advanced.rfd3Counts.show": "RFD3 개수 옵션 보기",
    "advanced.rfd3Counts.hide": "RFD3 개수 옵션 숨기기",
    "choice.confirmRun.yes": "예, 실행",
    "choice.confirmRun.no": "검토 후",
    "setup.wizard.scope": "범위 설정",
    "setup.wizard.input": "입력",
    "setup.wizard.options": "옵션",
    "setup.wizard.stepMeta": "{current}/{total} 단계: {label}",
    "setup.wizard.prev": "이전",
    "setup.wizard.next": "다음",
    "hint.none": "누락된 입력이 없습니다. 지금 실행할 수 있습니다.",
    "hint.ready": "필수 입력이 모두 완료되었습니다.",
    "hint.missing": "필수 입력이 누락되었습니다.",
    "hint.nextStep": "마지막 단계로 이동하면 실행할 수 있습니다.",
    "hint.running": "이미 실행 중인 작업이 있습니다.",
    "run.reset": "입력을 초기화했습니다. 선택과 첨부를 다시 확인하세요.",
    "setup.options.title": "핵심 옵션 보드",
    "setup.options.help": "주요 실행 옵션을 한 보드에서 한 번에 확인하고 조정합니다.",
    "setup.parameters.title": "핵심 파라미터 보드",
    "setup.parameters.help":
      "주요 숫자 파라미터를 한 카드에서 조정합니다. Pipeline/Workflow 모드에서는 BioEmu/RFD3 개수 설정을 항상 표시합니다.",
    "setup.parameters.inactive": "현재 조건에서 비활성",
    "setup.workflow.title": "Workflow Studio",
    "setup.workflow.help":
      "단계 실행 흐름을 구성합니다. 필요한 단계를 고르고 체크포인트를 지정한 뒤, 중간 결과를 확인하고 이어서 실행하세요.",
    "setup.workflow.palette": "단계 팔레트",
    "setup.workflow.paletteHelp": "필요한 단계만 선택하세요. 단계에 마우스를 올리면 역할 설명이 표시됩니다.",
    "setup.workflow.canvas": "플로우 캔버스",
    "setup.workflow.canvasHelp": "선택한 단계가 실행 순서대로 표시됩니다. 노드를 클릭해 체크포인트를 토글하세요.",
    "setup.workflow.stageGuide": "단계 가이드",
    "setup.workflow.stageGuideHint": "단계에 마우스를 올리거나 포커스하면 설명이 표시됩니다.",
    "setup.workflow.stageGuideLabel": "선택 단계",
    "setup.workflow.controls": "실행 제어",
    "setup.workflow.summaryTitle": "실행 요약",
    "setup.workflow.stageDesc.msa": "상동 서열을 탐색해 MSA 기반 데이터를 구성합니다.",
    "setup.workflow.stageDesc.rfd3": "준비된 스캐폴드 입력을 바탕으로 백본 후보를 생성합니다.",
    "setup.workflow.stageDesc.bioemu": "BioEmu로 구조 샘플을 생성해 다양성을 확보합니다.",
    "setup.workflow.stageDesc.design": "백본 문맥을 기준으로 후보 아미노산 서열을 설계합니다.",
    "setup.workflow.stageDesc.soluprot": "용해도 경향 점수로 후보를 평가하고 필터링합니다.",
    "setup.workflow.stageDesc.af2": "{af2Provider}로 구조와 품질 지표를 예측합니다.",
    "setup.workflow.stageDesc.novelty": "WT 서열과 비교해 WT Diff를 계산합니다.",
    "setup.workflow.summary": "실행 계획",
    "setup.workflow.empty": "단계 버튼을 눌러 노드를 추가하세요.",
    "setup.workflow.nodeHint": "노드를 클릭해 체크포인트를 다중 선택하고, x 버튼으로 단계를 제거할 수 있습니다.",
    "setup.workflow.checkpoint": "체크포인트에서 일시 정지",
    "setup.workflow.showResults": "체크포인트 결과 표시",
    "setup.workflow.showGraph": "체크포인트에서 그래프 표시",
    "setup.workflow.mmseqLoop": "검토 패널에서 단계 재실행 허용",
    "setup.workflow.orderLocked":
      "단계 순서는 파이프라인 의존성 때문에 고정됩니다. 기술적으로 변경은 가능하지만 안정적인 실행을 위해 권장하지 않습니다.",
    "setup.workflow.removeNode": "단계 제거",
    "setup.workflow.badge.checkpoint": "체크포인트",
    "setup.workflow.badge.final": "최종",
    "setup.workflow.plan": "{start} -> {stop} 실행 (최종 {final})",
    "setup.workflow.planNoCheckpoint": "{start} -> {final} 실행",
    "setup.workflow.checkpoints": "체크포인트: {stages}",
    "setup.workflow.checkpoints.none": "체크포인트 없음 (중단 없이 연속 실행)",
    "runmode.pipeline": "전체 파이프라인",
    "runmode.workflow": "Workflow Studio",
    "runmode.rfd3": "RFD3 (Backbone)",
    "runmode.bioemu": "BioEmu (Backbone)",
    "runmode.msa": "MSA (MMseqs2)",
    "runmode.design": "ProteinMPNN",
    "runmode.soluprot": "SoluProt",
    "runmode.af2": "{af2Provider}",
    "runmode.diffdock": "DiffDock",
    "setup.modeGuide.title": "모드 가이드",
    "setup.modeGuide.pipeline": "마지막 WT Diff 단계까지 전체 파이프라인을 한 번에 실행합니다.",
    "setup.modeGuide.workflow": "체크포인트 단위로 실행하고 모니터에서 이어서/재실행을 결정합니다.",
    "setup.modeGuide.rfd3": "RFD3 백본 생성만 실행합니다.",
    "setup.modeGuide.bioemu": "BioEmu 백본 샘플링만 실행합니다.",
    "setup.modeGuide.msa": "MSA/MMseqs 탐색과 캐시 준비만 실행합니다.",
    "setup.modeGuide.design": "서열 설계(ProteinMPNN)만 실행합니다.",
    "setup.modeGuide.soluprot": "용해도 점수 평가만 실행합니다.",
    "setup.modeGuide.af2": "{af2Provider} 구조 예측만 실행합니다.",
    "setup.modeGuide.diffdock": "단백질-리간드 도킹만 실행합니다.",
    "stop.full": "전체 (WT Diff)",
    "stage.msa": "MSA",
    "stage.rfd3": "RFD3",
    "stage.bioemu": "BioEmu",
    "stage.design": "디자인",
    "stage.soluprot": "SoluProt",
    "stage.af2": "{af2Provider}",
    "run.label.pipeline": "파이프라인 실행",
    "run.label.workflow": "워크플로우 실행",
    "run.label.rfd3": "RFD3 실행",
    "run.label.bioemu": "BioEmu 실행",
    "run.label.msa": "MSA 실행",
    "run.label.design": "ProteinMPNN 실행",
    "run.label.soluprot": "SoluProt 실행",
    "run.label.af2": "{af2Provider} 실행",
    "run.label.diffdock": "DiffDock 실행",
    "mode.pipeline": "파이프라인",
    "mode.workflow": "워크플로우",
    "mode.rfd3": "RFD3",
    "mode.bioemu": "BioEmu",
    "mode.msa": "MSA",
    "mode.design": "ProteinMPNN",
    "mode.soluprot": "SoluProt",
    "mode.af2": "{af2Provider}",
    "mode.diffdock": "DiffDock",
    "run.launching": "{mode} 실행 {id} 시작...",
    "run.started": "실행 시작: {id}",
    "run.failed": "실행 실패: {error}",
    "run.resume.loading": "{id}의 request.json을 불러오는 중...",
    "run.resume.running": "이미 실행 중입니다.",
    "run.resume.noRequest": "이 run의 request.json을 찾지 못했습니다.",
    "run.resume.badRequest": "request.json 형식이 올바르지 않습니다.",
    "run.resume.starting": "저장된 요청으로 {id} run 재시작 중...",
    "run.resume.started": "재시작 요청 완료: {id}",
    "run.resume.failed": "재시작 실패: {error}",
    "run.alreadyRunning": "이미 실행 중인 작업이 있습니다. 완료를 기다리거나 정지하세요.",
    "run.confirmRequired": "실행 전에 확인을 완료하세요.",
    "status.line": "상태: {stage} / {state}",
    "status.notFound":
      "{id} 실행 상태를 찾지 못했습니다. 외부/재개 실행이면 status.json 없이 동작 중일 수 있습니다.",
    "status.error": "상태 오류: {error}",
    "artifact.none": "아티팩트가 없습니다.",
    "artifact.error": "아티팩트 오류: {error}",
    "artifact.preview.binary": "바이너리 파일: {path}",
    "artifact.preview.failed": "미리보기 실패: {error}",
    "artifact.preview.unavailable": "3D 뷰어를 사용할 수 없습니다.",
    "artifact.references.none": "아티팩트 참조가 없습니다.",
    "runs.none": "실행 기록이 없습니다.",
    "runs.load": "불러오기",
    "feedback.rating.good": "좋음",
    "feedback.rating.bad": "나쁨",
    "feedback.reason.low_plddt": "pLDDT 낮음",
    "feedback.reason.high_plddt": "pLDDT 높음",
    "feedback.reason.high_rmsd": "RMSD 높음",
    "feedback.reason.low_rmsd": "RMSD 낮음",
    "feedback.reason.binding_poor": "결합 낮음",
    "feedback.reason.binding_good": "결합 우수",
    "feedback.reason.low_novelty": "WT 차이 낮음",
    "feedback.reason.high_novelty": "WT 차이 높음",
    "feedback.reason.unstable": "불안정",
    "feedback.reason.stable": "안정적",
    "feedback.reason.other": "기타",
    "feedback.stage.auto": "자동",
    "feedback.stage.msa": "MSA",
    "feedback.stage.design": "Design",
    "feedback.stage.soluprot": "SoluProt",
    "feedback.stage.af2": "{af2Provider}",
    "feedback.stage.novelty": "WT Diff",
    "feedback.stage.rfd3": "RFD3",
    "feedback.stage.diffdock": "DiffDock",
    "feedback.stage.other": "기타",
    "experiment.assay.binding": "결합",
    "experiment.assay.activity": "활성",
    "experiment.assay.stability": "안정성",
    "experiment.assay.expression": "발현",
    "experiment.assay.other": "기타",
    "experiment.result.success": "성공",
    "experiment.result.fail": "실패",
    "experiment.result.inconclusive": "불확실",
    "export.selectRun": "먼저 실행을 선택하세요.",
    "export.exporting": "내보내는 중...",
    "export.none.feedback": "내보낼 피드백이 없습니다.",
    "export.none.experiments": "내보낼 실험이 없습니다.",
    "export.done": "{count}행을 내보냈습니다.",
    "export.failed": "내보내기 실패: {error}",
    "feedback.saved": "피드백이 저장되었습니다.",
    "feedback.failed": "실패: {error}",
    "feedback.none": "아직 피드백이 없습니다.",
    "feedback.loadFailed": "불러오기 실패: {error}",
    "experiment.saved": "실험이 저장되었습니다.",
    "experiment.failed": "실패: {error}",
    "experiment.none": "아직 실험이 없습니다.",
    "experiment.loadFailed": "불러오기 실패: {error}",
    "report.loaded": "리포트를 불러왔습니다.",
    "report.notAvailable": "리포트를 아직 사용할 수 없습니다.",
    "report.loadFailed": "불러오기 실패: {error}",
    "report.generated": "리포트를 생성했습니다.",
    "report.generateFailed": "생성 실패: {error}",
    "report.saved": "리포트를 저장했습니다.",
    "report.saveFailed": "저장 실패: {error}",
    "report.empty": "리포트 내용이 비어 있습니다.",
    "analyze.compareStudio.title": "구조 비교 스튜디오",
    "analyze.compareStudio.desc":
      "3D/서열 비교와 WT/RFD3/BioEmu 비교 요약을 한 화면에서 확인합니다.",
    "analyze.runCompare.title": "Run-to-Run 비교",
    "analyze.runCompare.desc":
      "기준 실행 대비 pLDDT, RMSD, SoluProt, 통과율 변화를 비교합니다.",
    "analyze.runCompare.baseline": "기준 실행",
    "analyze.runCompare.refresh": "비교",
    "analyze.runCompare.details": "상세 보기",
    "analyze.runCompare.placeholder": "기준 실행을 선택하면 run 간 차이를 표시합니다.",
    "analyze.runCompare.sameRun": "기준 실행은 현재 실행과 달라야 합니다.",
    "analyze.runCompare.failed": "Run 비교 로드 실패: {error}",
    "analyze.runCompare.detailsTitle": "Run 비교 상세",
    "analyze.hitList.title": "Hit List",
    "analyze.hitList.desc": "가중합 점수 기반 최종 후보 랭킹과 컷오프 필터링.",
    "analyze.hitList.cutoff": "점수 컷오프",
    "analyze.hitList.limit": "행 수",
    "analyze.hitList.weight.soluprot": "SoluProt 가중치",
    "analyze.hitList.weight.plddt": "pLDDT 가중치",
    "analyze.hitList.weight.rmsd": "RMSD 가중치",
    "analyze.hitList.weight.novelty": "WT Diff 가중치 (비활성)",
    "analyze.hitList.identity": "WT 차이 (개수/길이, %)",
    "analyze.hitList.identityInfo": "WT 대비 차이(개수/길이, 퍼센트)로 표시되며 랭킹/필터에는 반영되지 않습니다.",
    "analyze.hitList.refresh": "새로고침",
    "analyze.hitList.details": "상세 보기",
    "analyze.hitList.placeholder": "실행을 선택하면 Hit List를 생성합니다.",
    "analyze.hitList.failed": "Hit List 로드 실패: {error}",
    "analyze.hitList.detailsTitle": "Hit List 상세",
    "analyze.hitList.summary":
      "{shown}/{filtered}개 표시 (전체 {total}), 중앙 점수 {score}",
    "analyze.hitList.empty": "컷오프 조건을 만족하는 후보가 없습니다.",
    "analyze.chart.select": "차트",
    "analyze.chart.placeholder": "Hit List를 실행하면 후보 차트를 표시합니다.",
    "analyze.chart.noData": "현재 필터에서 선택한 차트를 그릴 수 있는 수치 데이터가 없습니다.",
    "analyze.chart.option.plddtRmsd": "분산: pLDDT vs RMSD vs WT",
    "analyze.chart.option.scoreHist": "히스토그램: Hit 점수",
    "analyze.chart.option.tierPass": "티어별 AF2 통과율",
    "analyze.chart.axis.plddt": "pLDDT",
    "analyze.chart.axis.rmsd": "RMSD (A)",
    "analyze.chart.axis.score": "Hit 점수",
    "analyze.chart.axis.passRate": "통과율 (%)",
    "analyze.chart.axis.count": "개수",
    "analyze.chart.axis.tier": "티어",
    "analyze.chart.legend.selected": "{af2Provider} 선발",
    "analyze.chart.legend.unselected": "미선발",
    "analyze.chart.legend.wt": "WT",
    "analyze.chart.caption.rows": "행={rows} (컷오프 >= {cutoff})",
    "analyze.chart.caption.scatter": "포인트={points}, 선발={selected}",
    "analyze.chart.caption.scatterPoints": "포인트={points}",
    "analyze.chart.caption.scatterWithWt": "포인트={points}, 선발={selected}, WT={wt}",
    "analyze.chart.caption.hist": "값={values}, 구간={bins}",
    "analyze.chart.caption.tier": "티어={tiers}, 행={rows}",
    "analyze.files.title": "아티팩트 파일 뷰어",
    "analyze.files.desc": "Analyze에서 PDB/FASTA/CSV 및 텍스트 아티팩트를 미리보기합니다.",
    "analyze.files.select": "아티팩트 파일",
    "analyze.files.open": "열기",
    "analyze.files.placeholder": "아티팩트 파일을 선택하면 Analyze에서 미리보기합니다.",
    "analyze.files.none": "이 실행에서 미리볼 파일 아티팩트가 없습니다.",
    "residue.linked.title": "Residue 연동 뷰",
    "residue.linked.help": "잔기 칩/행을 클릭하면 양쪽 구조에서 해당 잔기를 강조합니다.",
    "residue.linked.empty": "이 비교에서 잔기 단위 지표를 계산하지 못했습니다.",
    "residue.linked.selected": "선택: chain {chain} residue {resi} ({left}->{right}) dist={dist}A",
    "residue.linked.selectedNone": "선택: 없음",
    "metrics.parseError": "지표 파싱 실패: {error}",
    "metrics.objectRequired": "metrics는 JSON 객체여야 합니다",
    "auth.required": "사용자명과 비밀번호가 필요합니다.",
    "auth.loginFailed": "로그인 실패",
    "auth.sessionInvalid": "세션이 유효하지 않습니다.",
    "auth.createFailed": "사용자 생성 실패",
    "auth.created": "{username} 생성 완료.",
    "error.api": "API 오류",
    "health.checking": "확인 중...",
    "health.ok": "정상",
  },
};

function parseAf2Provider(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase();
  if (raw === "af2" || raw === "alphafold" || raw === "alphafold2") {
    return "af2";
  }
  if (raw === "colabfold") {
    return "colabfold";
  }
  return "";
}

function normalizeAf2Provider(value) {
  return parseAf2Provider(value) || "colabfold";
}

function af2ProviderForRun(runId) {
  const key = String(runId || "").trim();
  if (!key) return "";
  const raw = state.af2ProviderByRunId ? state.af2ProviderByRunId[key] : "";
  if (!raw) return "";
  return normalizeAf2Provider(raw);
}

function activeAf2Provider(runId = state.currentRunId) {
  if (state.answers && state.answers.af2_provider !== undefined) {
    return normalizeAf2Provider(state.answers.af2_provider);
  }
  const fromRun = af2ProviderForRun(runId);
  if (fromRun) return fromRun;
  return "colabfold";
}

function currentRunAf2Provider(runId = state.currentRunId) {
  const fromRun = af2ProviderForRun(runId);
  if (fromRun) return fromRun;
  if (String(runId || "").trim()) return "";
  return activeAf2Provider(runId);
}

function af2ProviderName(provider = activeAf2Provider(), lang = state.lang) {
  const parsed = parseAf2Provider(provider);
  if (parsed === "af2") return "AlphaFold2";
  if (parsed === "colabfold") return "ColabFold";
  return "AF2";
}

function af2ProviderTargetLabel(provider = activeAf2Provider(), lang = state.lang) {
  const name = af2ProviderName(provider, lang);
  return lang === "ko" ? `${name} 타깃` : `${name} Target`;
}

function af2ProviderWtLabel(provider = activeAf2Provider(), lang = state.lang) {
  const name = af2ProviderName(provider, lang);
  return `WT ${name}`;
}

function af2ProviderPassLabel(provider = activeAf2Provider(), lang = state.lang) {
  const name = af2ProviderName(provider, lang);
  return lang === "ko" ? `${name} 통과` : `${name} pass`;
}

function af2ProviderSelectedLabel(provider = activeAf2Provider(), lang = state.lang) {
  const name = af2ProviderName(provider, lang);
  return lang === "ko" ? `${name} 선발` : `${name} selected`;
}

function af2ProviderTemplateParams(provider = activeAf2Provider()) {
  const normalized = normalizeAf2Provider(provider);
  return {
    af2Provider: af2ProviderName(normalized, state.lang),
    af2ProviderPair: normalized === "af2" ? "AlphaFold2/ColabFold" : "ColabFold/AlphaFold2",
  };
}

function setAf2ProviderForRun(runId, provider) {
  const key = String(runId || "").trim();
  if (!key) return false;
  const normalized = normalizeAf2Provider(provider);
  if (!state.af2ProviderByRunId) state.af2ProviderByRunId = {};
  if (state.af2ProviderByRunId[key] === normalized) return false;
  state.af2ProviderByRunId[key] = normalized;
  return String(state.currentRunId || "").trim() === key;
}

function refreshAf2ProviderLabels({ rerenderQuestions = false } = {}) {
  updateRunLabel();
  applyI18n();
  if (rerenderQuestions) {
    renderQuestions(state.plan?.questions || []);
    updateRunEligibility(state.plan?.questions || []);
  }
  renderAllArtifactViews(state.artifacts);
  refreshArtifactSelects();
  renderArtifactComparisonSummary(state.artifactComparison);
  renderMonitorCompleteness(state.artifactComparison, state.hitListResult?.completeness || null);
  renderRunCompareSummary(state.runCompareResult);
  renderHitList();
  updateReportArtifactLinks(el.reportContent ? el.reportContent.value : "");
}

function t(key, params = {}) {
  const table = I18N[state.lang] || I18N.en;
  const fallback = I18N.en[key] || key;
  const template = table[key] || fallback;
  const defaults = af2ProviderTemplateParams();
  const merged = { ...defaults, ...(params || {}) };
  return String(template).replace(/\{(\w+)\}/g, (_, k) => {
    if (merged[k] === undefined || merged[k] === null) return "";
    return String(merged[k]);
  });
}

function labelFor(option) {
  if (!option) return "";
  if (option.labelKey) return t(option.labelKey);
  if (option.label) return option.label;
  return option.value || "";
}

function labelFromMap(value, map) {
  if (map && Object.prototype.hasOwnProperty.call(map, value)) {
    return t(map[value]);
  }
  if (value === undefined || value === null || value === "") return t("common.none");
  return String(value);
}

const TAB_KEY = "kbf.activeTab";
const TAB_OPTIONS = ["setup", "monitor", "analyze"];
const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));
const langButtons = Array.from(document.querySelectorAll(".lang-btn"));
let tabsInitialized = false;
let langInitialized = false;
let copilotInitialized = false;

const RUN_MODE_OPTIONS = [
  { labelKey: "runmode.pipeline", value: "pipeline" },
  { labelKey: "runmode.workflow", value: "workflow" },
  { labelKey: "runmode.rfd3", value: "rfd3" },
  { labelKey: "runmode.bioemu", value: "bioemu" },
  { labelKey: "runmode.msa", value: "msa" },
  { labelKey: "runmode.design", value: "design" },
  { labelKey: "runmode.soluprot", value: "soluprot" },
  { labelKey: "runmode.af2", value: "af2" },
  { labelKey: "runmode.diffdock", value: "diffdock" },
];

const PIPELINE_STAGE_ORDER = ["msa", "rfd3", "bioemu", "design", "soluprot", "af2", "novelty"];
const SETUP_WIZARD_STEPS = [
  { id: "scope", labelKey: "setup.wizard.scope" },
  { id: "input", labelKey: "setup.wizard.input" },
  { id: "options", labelKey: "setup.wizard.options" },
];
const ENABLE_SETUP_WIZARD = false;

function normalizePipelineStage(value, fallback = "") {
  let raw = String(value || "")
    .trim()
    .toLowerCase();
  raw = raw.replace(/[\s-]+/g, "_");
  if (raw === "wt_diff" || raw === "wtdiff") raw = "novelty";
  if (PIPELINE_STAGE_ORDER.includes(raw)) return raw;
  return fallback;
}

function syncStartStopStages() {
  const start = normalizePipelineStage(state.answers.start_from, "");
  const stop = normalizePipelineStage(state.answers.stop_after, "");
  if (!start || !stop) return;
  if (PIPELINE_STAGE_ORDER.indexOf(start) > PIPELINE_STAGE_ORDER.indexOf(stop)) {
    state.answers.stop_after = start;
  }
}

function normalizeWorkflowNodesForState(value) {
  const source = Array.isArray(value) ? value : state.workflowDesigner?.nodes;
  const list = [];
  (source || []).forEach((item) => {
    const stage = normalizePipelineStage(item, "");
    if (!stage) return;
    if (!list.includes(stage)) list.push(stage);
  });
  if (!list.length) return ["msa", "design", "soluprot", "af2"];
  return list;
}

function nextPipelineStage(stage) {
  const normalized = normalizePipelineStage(stage, "");
  if (!normalized) return "";
  const idx = PIPELINE_STAGE_ORDER.indexOf(normalized);
  if (idx < 0 || idx + 1 >= PIPELINE_STAGE_ORDER.length) return "";
  return PIPELINE_STAGE_ORDER[idx + 1];
}

function buildWorkflowPlanFromDesigner() {
  const nodes = normalizeWorkflowNodesForState(state.workflowDesigner?.nodes);
  const start = nodes[0] || "msa";
  const finalStop = nodes[nodes.length - 1] || "novelty";
  const checkpointEnabled = Boolean(state.workflowDesigner?.checkpointEnabled);
  const checkpointStages = checkpointEnabled
    ? normalizeWorkflowCheckpointList(state.workflowDesigner?.checkpointStages, nodes)
    : [];
  const nextCheckpointStage = checkpointStages[0] || "";
  const stopAfter = nextCheckpointStage || finalStop;
  const noveltyEnabled = finalStop === "novelty";
  const bioemuUse = nodes.includes("bioemu");
  const continueFrom = nextCheckpointStage ? nextPipelineStage(nextCheckpointStage) : "";
  return {
    nodes,
    start,
    stopAfter,
    finalStop,
    checkpointEnabled: checkpointStages.length > 0,
    checkpointStages,
    checkpointIndex: 0,
    nextCheckpointStage,
    continueFrom,
    noveltyEnabled,
    bioemuUse,
    graphEnabled: state.workflowDesigner?.graphEnabled !== false,
    mmseqLoopEnabled: state.workflowDesigner?.mmseqLoopEnabled !== false,
  };
}

function pipelineStageSlice(start, stop) {
  const normalizedStart = normalizePipelineStage(start, "msa") || "msa";
  const normalizedStop = normalizePipelineStage(stop, normalizedStart) || normalizedStart;
  const startIdx = PIPELINE_STAGE_ORDER.indexOf(normalizedStart);
  const stopIdx = PIPELINE_STAGE_ORDER.indexOf(normalizedStop);
  if (startIdx < 0 || stopIdx < 0) return ["msa", "design", "soluprot", "af2"];
  const from = Math.min(startIdx, stopIdx);
  const to = Math.max(startIdx, stopIdx);
  return PIPELINE_STAGE_ORDER.slice(from, to + 1);
}

function workflowPlanForRunId(runId) {
  const key = String(runId || "").trim();
  if (!key) return null;
  const saved = state.workflowPlansByRunId?.[key];
  if (saved && typeof saved === "object") {
    const nodes = normalizeWorkflowNodesForState(saved.nodes);
    const finalStopAfter = normalizePipelineStage(saved.finalStopAfter, nodes[nodes.length - 1] || "novelty");
    const checkpointEnabled = Boolean(saved.checkpointEnabled);
    const legacyCheckpointStage = normalizePipelineStage(saved.checkpointStage, "");
    const checkpointStages = checkpointEnabled
      ? normalizeWorkflowCheckpointList(
          [
            ...(Array.isArray(saved.checkpointStages) ? saved.checkpointStages : []),
            legacyCheckpointStage,
          ],
          nodes
        )
      : [];
    let checkpointIndex = Number(saved.checkpointIndex);
    if (!Number.isFinite(checkpointIndex)) {
      if (Object.prototype.hasOwnProperty.call(saved, "checkpointConsumed")) {
        checkpointIndex = saved.checkpointConsumed ? checkpointStages.length : 0;
      } else if (legacyCheckpointStage) {
        const legacyIndex = checkpointStages.indexOf(legacyCheckpointStage);
        checkpointIndex = legacyIndex >= 0 ? legacyIndex : 0;
      } else {
        checkpointIndex = 0;
      }
    }
    checkpointIndex = Math.max(0, Math.min(checkpointStages.length, Math.trunc(checkpointIndex)));
    const nextCheckpointStage = checkpointStages[checkpointIndex] || "";
    return {
      nodes,
      finalStopAfter,
      checkpointEnabled: checkpointStages.length > 0,
      checkpointStages,
      checkpointIndex,
      nextCheckpointStage,
      continueFrom: nextCheckpointStage ? nextPipelineStage(nextCheckpointStage) : "",
      graphEnabled: saved.graphEnabled !== false,
      mmseqLoopEnabled: saved.mmseqLoopEnabled !== false,
      checkpointConsumed: checkpointIndex >= checkpointStages.length,
    };
  }
  if (state.runModeById?.[key] !== "workflow") return null;
  const ctx = state.progressContextByRunId?.[key];
  if (!ctx || typeof ctx !== "object") return null;
  const nodes = pipelineStageSlice(ctx.startFrom || "msa", ctx.stopAfter || "novelty");
  const finalStopAfter = normalizePipelineStage(ctx.stopAfter, nodes[nodes.length - 1] || "novelty");
  return {
    nodes,
    finalStopAfter,
    checkpointEnabled: false,
    checkpointStages: [],
    checkpointIndex: 0,
    nextCheckpointStage: "",
    continueFrom: "",
    graphEnabled: true,
    mmseqLoopEnabled: false,
    checkpointConsumed: true,
  };
}

function workflowArtifactCountsForNodes(nodes) {
  const counts = {};
  (nodes || []).forEach((stage) => {
    counts[stage] = 0;
  });
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  artifacts.forEach((item) => {
    const stage = artifactMetaForPath(item?.path || "").stage;
    if (Object.prototype.hasOwnProperty.call(counts, stage)) {
      counts[stage] += 1;
    }
  });
  return counts;
}

function workflowArtifactGroupsForReview() {
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  const files = artifacts.filter((item) => item && item.type === "file" && String(item.path || "").trim());
  const groups = new Map();
  files.forEach((item) => {
    const stage = artifactMetaForPath(item.path).stage || "misc";
    if (!groups.has(stage)) groups.set(stage, []);
    groups.get(stage).push(item);
  });
  const orderedStages = ARTIFACT_STAGE_ORDER.filter((stage) => groups.has(stage));
  const extraStages = Array.from(groups.keys())
    .filter((stage) => !orderedStages.includes(stage))
    .sort();
  const stageOrder = [...orderedStages, ...extraStages];
  return stageOrder.map((stage) => ({
    stage,
    items: (groups.get(stage) || []).sort((a, b) => String(a.path || "").localeCompare(String(b.path || ""))),
  }));
}

function workflowCountsSvg(nodes, counts) {
  const stages = Array.isArray(nodes) ? nodes : [];
  if (!stages.length) return "";
  const values = stages.map((stage) => Number(counts?.[stage] || 0));
  const maxValue = Math.max(1, ...values);
  const width = Math.max(320, stages.length * 72);
  const height = 160;
  const bottom = 128;
  const barWidth = 34;
  const gap = (width - 40) / Math.max(1, stages.length);
  const bars = stages
    .map((stage, idx) => {
      const value = Number(counts?.[stage] || 0);
      const h = Math.round((value / maxValue) * 82);
      const x = Math.round(24 + idx * gap);
      const y = bottom - h;
      const stageLabel = stage === "novelty" ? t("stop.full") : formatStageLabel(stage);
      return `
        <g class="workflow-mini-bar">
          <rect x="${x}" y="${y}" width="${barWidth}" height="${h}" rx="6" />
          <text x="${x + barWidth / 2}" y="${Math.max(16, y - 6)}" text-anchor="middle">${value}</text>
          <text x="${x + barWidth / 2}" y="${bottom + 16}" text-anchor="middle">${escapeHtml(stageLabel)}</text>
        </g>
      `;
    })
    .join("");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="workflow-stage-counts">
      <line x1="12" y1="${bottom}" x2="${width - 10}" y2="${bottom}" />
      ${bars}
    </svg>
  `;
}

function setupWizardEnabled(questions) {
  return ENABLE_SETUP_WIZARD && state.runMode === "pipeline" && Array.isArray(questions) && questions.length > 0;
}

function questionSetupStepId(questionId) {
  if (questionId === "run_mode" || questionId === "start_from" || questionId === "stop_after") {
    return "scope";
  }
  if (
    questionId === "target_input" ||
    questionId === "target_pdb" ||
    questionId === "target_fasta" ||
    questionId === "rfd3_input_pdb" ||
    questionId === "rfd3_contig" ||
    questionId === "diffdock_ligand"
  ) {
    return "input";
  }
  return "options";
}

function isSetupWizardFinalStep() {
  const lastIndex = SETUP_WIZARD_STEPS.length - 1;
  return Number(state.setupStepIndex || 0) >= lastIndex;
}

function renderSetupWizard(questions) {
  const enabled = setupWizardEnabled(questions);
  if (!el.setupStepper || !el.setupStepMeta || !el.setupStepDots || !el.setupStepPrev || !el.setupStepNext) {
    return questions;
  }
  if (!enabled) {
    state.setupStepIndex = 0;
    el.setupStepper.classList.add("hidden");
    return questions;
  }

  const maxStep = SETUP_WIZARD_STEPS.length - 1;
  const currentStep = Math.max(0, Math.min(maxStep, Number(state.setupStepIndex || 0)));
  state.setupStepIndex = currentStep;
  const activeStepId = SETUP_WIZARD_STEPS[currentStep].id;

  el.setupStepper.classList.remove("hidden");
  const label = t(SETUP_WIZARD_STEPS[currentStep].labelKey);
  el.setupStepMeta.textContent = t("setup.wizard.stepMeta", {
    current: currentStep + 1,
    total: SETUP_WIZARD_STEPS.length,
    label,
  });

  el.setupStepDots.innerHTML = SETUP_WIZARD_STEPS.map((step, index) => {
    const cls = index === currentStep ? "setup-step-dot active" : "setup-step-dot";
    return `<button type="button" class="${cls}" data-step-index="${index}">${escapeHtml(
      t(step.labelKey)
    )}</button>`;
  }).join("");
  Array.from(el.setupStepDots.querySelectorAll("[data-step-index]")).forEach((node) => {
    node.addEventListener("click", () => {
      const nextIndex = Number.parseInt(String(node.getAttribute("data-step-index") || "0"), 10);
      if (!Number.isFinite(nextIndex)) return;
      state.setupStepIndex = Math.max(0, Math.min(maxStep, nextIndex));
      renderQuestions(state.plan?.questions || []);
    });
  });

  el.setupStepPrev.textContent = t("setup.wizard.prev");
  el.setupStepNext.textContent = t("setup.wizard.next");
  el.setupStepPrev.disabled = currentStep <= 0;
  el.setupStepNext.disabled = currentStep >= maxStep;

  return (questions || []).filter((q) => questionSetupStepId(q.id) === activeStepId);
}

const QUESTION_PRESETS = {
  run_mode: {
    labelKey: "question.runMode.label",
    questionKey: "question.runMode.help",
    required: true,
  },
  target_input: {
    labelKey: "question.targetInput.label",
    questionKey: "question.targetInput.help",
    required: true,
  },
  start_from: {
    labelKey: "question.startFrom.label",
    questionKey: "question.startFrom.help",
    default: "msa",
  },
  stop_after: {
    labelKey: "question.stopAfter.label",
    questionKey: "question.stopAfter.help",
    default: "novelty",
  },
  design_chains: {
    labelKey: "question.designChains.label",
    questionKey: "question.designChains.help",
  },
  pdb_strip_nonpositive_resseq: {
    labelKey: "question.stripNonpositive.label",
    questionKey: "question.stripNonpositive.help",
  },
  wt_compare: {
    labelKey: "question.wtCompare.label",
    questionKey: "question.wtCompare.help",
  },
  mask_consensus_apply: {
    labelKey: "question.maskConsensusApply.label",
    questionKey: "question.maskConsensusApply.help",
  },
  bioemu_use: {
    labelKey: "question.bioemuUse.label",
    questionKey: "question.bioemuUse.help",
  },
  bioemu_num_samples: {
    labelKey: "question.bioemuNumSamples.label",
    questionKey: "question.bioemuNumSamples.help",
  },
  bioemu_max_return_structures: {
    labelKey: "question.bioemuMaxReturn.label",
    questionKey: "question.bioemuMaxReturn.help",
  },
  num_seq_per_tier: {
    labelKey: "question.numSeqPerTier.label",
    questionKey: "question.numSeqPerTier.help",
  },
  af2_max_candidates_per_tier: {
    labelKey: "question.af2MaxCandidatesPerTier.label",
    questionKey: "question.af2MaxCandidatesPerTier.help",
  },
  af2_plddt_cutoff: {
    labelKey: "question.af2PlddtCutoff.label",
    questionKey: "question.af2PlddtCutoff.help",
    default: 85,
  },
  af2_rmsd_cutoff: {
    labelKey: "question.af2RmsdCutoff.label",
    questionKey: "question.af2RmsdCutoff.help",
    default: 2.0,
  },
  novelty_enabled: {
    labelKey: "question.noveltyEnabled.label",
    questionKey: "question.noveltyEnabled.help",
    default: true,
  },
  af2_provider: {
    labelKey: "question.af2Provider.label",
    questionKey: "question.af2Provider.help",
    default: "colabfold",
  },
  rfd3_max_return_designs: {
    labelKey: "question.rfd3MaxReturn.label",
    questionKey: "question.rfd3MaxReturn.help",
  },
  rfd3_input_pdb: {
    labelKey: "question.rfd3InputPdb.label",
    questionKey: "question.rfd3InputPdb.help",
  },
  rfd3_contig: {
    labelKey: "question.rfd3Contig.label",
    questionKey: "question.rfd3Contig.help",
  },
  diffdock_ligand: {
    labelKey: "question.diffdockLigand.label",
    questionKey: "question.diffdockLigand.help",
  },
  target_fasta: {
    labelKey: "question.targetFasta.label",
    questionKey: "question.targetFasta.help",
  },
  target_pdb: {
    labelKey: "question.targetInput.label",
    questionKey: "question.targetInput.help",
  },
  fixed_positions_extra: {
    labelKey: "question.fixedPositionsExtra.label",
    questionKey: "question.fixedPositionsExtra.help",
    placeholder: "A:6,10;*:120 or {\"A\":[6,10],\"*\":[120]}",
    multiline: true,
  },
  ligand_mask_use_original_target: {
    labelKey: "question.ligandMaskOriginal.label",
    questionKey: "question.ligandMaskOriginal.help",
  },
  confirm_run: {
    labelKey: "question.confirmRun.label",
    questionKey: "question.confirmRun.help",
    required: true,
    default: true,
  },
};

const ANSWER_BOOL_KEYS = new Set([
  "dry_run",
  "force",
  "agent_panel_enabled",
  "auto_recover",
  "wt_compare",
  "mask_consensus_apply",
  "ligand_mask_use_original_target",
  "pdb_strip_nonpositive_resseq",
  "pdb_renumber_resseq_from_1",
  "mmseqs_use_gpu",
  "rfd3_use_ensemble",
  "bioemu_use",
  "novelty_enabled",
  "confirm_run",
]);

const ANSWER_INT_KEYS = new Set([
  "num_seq_per_tier",
  "batch_size",
  "seed",
  "af2_top_k",
  "mmseqs_max_seqs",
  "mmseqs_threads",
  "rfd3_design_index",
  "rfd3_max_return_designs",
  "rfd3_partial_t",
  "bioemu_num_samples",
  "bioemu_max_return_structures",
  "af2_max_candidates_per_tier",
  "conservation_cluster_cov_mode",
  "conservation_cluster_kmer_per_seq",
]);

const ANSWER_FLOAT_KEYS = new Set([
  "sampling_temp",
  "soluprot_cutoff",
  "af2_plddt_cutoff",
  "af2_rmsd_cutoff",
  "ligand_mask_distance",
  "msa_min_coverage",
  "msa_min_identity",
  "query_pdb_min_identity",
  "conservation_cluster_min_seq_id",
  "conservation_cluster_coverage",
]);

const ANSWER_LIST_KEYS = new Set([
  "design_chains",
  "ligand_resnames",
  "ligand_atom_chains",
  "af2_sequence_ids",
  "rfd3_ligand",
]);

const ANSWER_FLOAT_LIST_KEYS = new Set(["conservation_tiers"]);

const ANSWER_JSON_KEYS = new Set([
  "fixed_positions_extra",
  "rfd3_env",
  "rfd3_inputs",
  "rfd3_input_files",
]);

const ANSWER_TEXTAREA_KEYS = new Set(["rfd3_cli_args", "diffdock_extra_args", "af2_extra_flags"]);

const FEEDBACK_REASONS_BY_RATING = {
  good: [
    { labelKey: "feedback.reason.high_plddt", value: "high_plddt" },
    { labelKey: "feedback.reason.low_rmsd", value: "low_rmsd" },
    { labelKey: "feedback.reason.binding_good", value: "binding_good" },
    { labelKey: "feedback.reason.high_novelty", value: "high_novelty" },
    { labelKey: "feedback.reason.stable", value: "stable" },
    { labelKey: "feedback.reason.other", value: "other" },
  ],
  bad: [
    { labelKey: "feedback.reason.low_plddt", value: "low_plddt" },
    { labelKey: "feedback.reason.high_rmsd", value: "high_rmsd" },
    { labelKey: "feedback.reason.binding_poor", value: "binding_poor" },
    { labelKey: "feedback.reason.low_novelty", value: "low_novelty" },
    { labelKey: "feedback.reason.unstable", value: "unstable" },
    { labelKey: "feedback.reason.other", value: "other" },
  ],
};

const REPORT_REVIEW_REASONS_BY_RATING = {
  good: [
    { labelKey: "report.review.reason.clear", value: "report_clear" },
    { labelKey: "report.review.reason.actionable", value: "report_actionable" },
    { labelKey: "report.review.reason.complete", value: "report_complete" },
    { labelKey: "report.review.reason.other", value: "report_other" },
  ],
  bad: [
    { labelKey: "report.review.reason.missing_metrics", value: "report_missing_metrics" },
    { labelKey: "report.review.reason.inaccurate", value: "report_inaccurate" },
    { labelKey: "report.review.reason.confusing", value: "report_confusing" },
    { labelKey: "report.review.reason.other", value: "report_other" },
  ],
};

const FEEDBACK_STAGES = [
  { labelKey: "feedback.stage.auto", value: "" },
  { labelKey: "feedback.stage.msa", value: "msa" },
  { labelKey: "feedback.stage.design", value: "design" },
  { labelKey: "feedback.stage.soluprot", value: "soluprot" },
  { labelKey: "feedback.stage.af2", value: "af2" },
  { labelKey: "feedback.stage.novelty", value: "novelty" },
  { labelKey: "feedback.stage.rfd3", value: "rfd3" },
  { labelKey: "feedback.stage.diffdock", value: "diffdock" },
  { labelKey: "feedback.stage.other", value: "other" },
];

const EXPERIMENT_ASSAYS = [
  { labelKey: "experiment.assay.binding", value: "binding" },
  { labelKey: "experiment.assay.activity", value: "activity" },
  { labelKey: "experiment.assay.stability", value: "stability" },
  { labelKey: "experiment.assay.expression", value: "expression" },
  { labelKey: "experiment.assay.other", value: "other" },
];

const EXPERIMENT_RESULTS = [
  { labelKey: "experiment.result.success", value: "success" },
  { labelKey: "experiment.result.fail", value: "fail" },
  { labelKey: "experiment.result.inconclusive", value: "inconclusive" },
];

const FEEDBACK_RATING_KEYS = {
  good: "feedback.rating.good",
  bad: "feedback.rating.bad",
};

const FEEDBACK_REASON_KEYS = {
  low_plddt: "feedback.reason.low_plddt",
  high_plddt: "feedback.reason.high_plddt",
  high_rmsd: "feedback.reason.high_rmsd",
  low_rmsd: "feedback.reason.low_rmsd",
  binding_poor: "feedback.reason.binding_poor",
  binding_good: "feedback.reason.binding_good",
  low_novelty: "feedback.reason.low_novelty",
  high_novelty: "feedback.reason.high_novelty",
  unstable: "feedback.reason.unstable",
  stable: "feedback.reason.stable",
  other: "feedback.reason.other",
};

const FEEDBACK_STAGE_KEYS = {
  "": "feedback.stage.auto",
  msa: "feedback.stage.msa",
  design: "feedback.stage.design",
  soluprot: "feedback.stage.soluprot",
  af2: "feedback.stage.af2",
  novelty: "feedback.stage.novelty",
  rfd3: "feedback.stage.rfd3",
  diffdock: "feedback.stage.diffdock",
  other: "feedback.stage.other",
};

const EXPERIMENT_ASSAY_KEYS = {
  binding: "experiment.assay.binding",
  activity: "experiment.assay.activity",
  stability: "experiment.assay.stability",
  expression: "experiment.assay.expression",
  other: "experiment.assay.other",
};

const EXPERIMENT_RESULT_KEYS = {
  success: "experiment.result.success",
  fail: "experiment.result.fail",
  inconclusive: "experiment.result.inconclusive",
};

const EXPORT_LIMIT = 2000;
const ARTIFACT_STAGE_ORDER = [
  "msa",
  "conservation",
  "rfd3",
  "bioemu",
  "input_reference",
  "working_backbone",
  "wt_af2",
  "af2_target",
  "pdb_preprocess",
  "query_pdb_check",
  "diffdock",
  "ligand_mask",
  "surface_mask",
  "mask_consensus",
  "design",
  "soluprot",
  "af2",
  "novelty",
  "wt",
  "agent",
  "misc",
];

const STAGE_LABELS = {
  msa: { en: "MSA", ko: "MSA" },
  conservation: { en: "Conservation", ko: "보존도" },
  rfd3: { en: "RFD3", ko: "RFD3" },
  bioemu: { en: "BioEmu", ko: "BioEmu" },
  input_reference: { en: "Input Structure", ko: "입력 구조" },
  working_backbone: { en: "Working Backbone", ko: "작업 백본" },
  af2_target: { en: "ColabFold Target", ko: "ColabFold 타깃" },
  pdb_preprocess: { en: "PDB Preprocess", ko: "PDB 전처리" },
  query_pdb_check: { en: "Query/PDB Check", ko: "Query/PDB 검증" },
  diffdock: { en: "DiffDock", ko: "DiffDock" },
  ligand_mask: { en: "Ligand Mask", ko: "리간드 마스킹" },
  surface_mask: { en: "Surface Mask", ko: "표면 마스킹" },
  mask_consensus: { en: "Mask Consensus", ko: "마스킹 합의" },
  design: { en: "ProteinMPNN", ko: "ProteinMPNN" },
  soluprot: { en: "SoluProt", ko: "SoluProt" },
  af2: { en: "ColabFold", ko: "ColabFold" },
  novelty: { en: "WT Diff", ko: "WT Diff" },
  wt: { en: "WT Compare", ko: "WT 비교" },
  wt_baseline: { en: "WT Baseline", ko: "WT 기준선" },
  wt_soluprot: { en: "WT SoluProt", ko: "WT SoluProt" },
  wt_af2: { en: "WT ColabFold", ko: "WT ColabFold" },
  agent: { en: "Agent Panel", ko: "에이전트 패널" },
  misc: { en: "Misc", ko: "기타" },
};

const PROGRESS_PLANS = {
  pipeline: ["msa", "conservation", "backbone", "wt", "masking", "design", "soluprot", "af2", "novelty", "done"],
  workflow: ["msa", "conservation", "backbone", "wt", "masking", "design", "soluprot", "af2", "novelty", "done"],
  design: ["msa", "conservation", "backbone", "masking", "design", "done"],
  soluprot: ["msa", "conservation", "backbone", "masking", "design", "soluprot", "done"],
  rfd3: ["msa", "conservation", "rfd3", "done"],
  bioemu: ["msa", "conservation", "bioemu", "done"],
  msa: ["msa", "done"],
  af2: ["af2", "done"],
  diffdock: ["diffdock", "done"],
};

const TERMINAL_RUN_STATES = new Set(["completed", "failed", "cancelled"]);
const CHART_VIEW_OPTIONS = new Set(["plddt_rmsd", "score_hist", "tier_pass"]);

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

function appendMessage(container, text, role = "ai") {
  if (!container) return;
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  container.appendChild(div);
  while (container.childElementCount > 120) {
    container.removeChild(container.firstElementChild);
  }
  container.scrollTop = container.scrollHeight;
}

function clearMessagePanels() {
  if (el.messages) el.messages.innerHTML = "";
  if (el.monitorMessages) el.monitorMessages.innerHTML = "";
}

function setMessage(text, role = "ai") {
  appendMessage(el.messages, text, role);
  appendMessage(el.monitorMessages, text, role);
}

function copilotIsKorean() {
  return (state.lang || "en") === "ko";
}

function activeTabId() {
  const active = Array.isArray(tabPanels)
    ? tabPanels.find((panel) => panel.classList.contains("active"))
    : null;
  const tab = active?.dataset?.tab || localStorage.getItem(TAB_KEY) || "setup";
  return normalizeTab(tab);
}

function chartViewLabel() {
  const view = normalizeChartView(state.chartView);
  if (view === "score_hist") return t("analyze.chart.option.scoreHist");
  if (view === "tier_pass") return t("analyze.chart.option.tierPass");
  return t("analyze.chart.option.plddtRmsd");
}

function copilotShortArtifactLabel(path) {
  const display = displayArtifactPath(path);
  if (!display) return "";
  const parts = display.split("/").filter(Boolean);
  if (parts.length <= 2) return display;
  return parts.slice(-2).join("/");
}

function copilotCompareSnapshot() {
  const isKo = copilotIsKorean();
  const leftPath = String(state.artifactCompareLeftPath || "").trim();
  const rightPath = String(state.artifactCompareRightPath || "").trim();
  const mode = state.artifactCompareMode === "sequence" ? "sequence" : "structure";
  const leftMeta = leftPath ? artifactMetaForPath(leftPath) : null;
  const rightMeta = rightPath ? artifactMetaForPath(rightPath) : null;
  return {
    leftPath,
    rightPath,
    mode,
    modeLabel: isKo ? (mode === "sequence" ? "서열 모드" : "구조 모드") : mode === "sequence" ? "Sequence mode" : "Structure mode",
    leftMeta,
    rightMeta,
    leftLabel: leftPath ? buildArtifactCompareOptionLabel(leftPath, leftMeta) : "",
    rightLabel: rightPath ? buildArtifactCompareOptionLabel(rightPath, rightMeta) : "",
    ready: Boolean(leftPath && rightPath),
  };
}

function copilotSnapshot() {
  const runId = String(state.currentRunId || "").trim();
  const status = state.lastRunStatus && typeof state.lastRunStatus === "object" ? state.lastRunStatus : {};
  const stage = String(status?.stage || "-");
  const runState = String(status?.state || state.currentRunState || "-");
  const comparisonSummary =
    runId &&
    String(state.artifactComparisonRunId || "").trim() === runId &&
    state.artifactComparison &&
    typeof state.artifactComparison === "object"
      ? state.artifactComparison
      : null;
  const funnel =
    comparisonSummary?.funnel && typeof comparisonSummary.funnel === "object"
      ? comparisonSummary.funnel.overall || null
      : null;
  const provider = af2ProviderName(currentRunAf2Provider(runId), state.lang || "en");
  const rows = runId ? filteredHitListRows({ applyLimit: false }) : [];
  const topRow = rows.length ? rows[0] : null;
  return {
    tab: activeTabId(),
    runId,
    stage,
    runState,
    provider,
    rows,
    topRow,
    funnel,
    recommendation: state.lastScore?.recommendation || "-",
    artifactCount: runId ? (Array.isArray(state.artifacts) ? state.artifacts.length : 0) : 0,
    chartLabel: chartViewLabel(),
    compare: copilotCompareSnapshot(),
  };
}

function copilotStatusLabel(snapshot = copilotSnapshot()) {
  return `${formatStageLabel(snapshot.stage)} / ${snapshot.runState || "-"}`;
}

function copilotCompareStateText(compare = copilotCompareSnapshot()) {
  const isKo = copilotIsKorean();
  if (compare.ready) {
    return `${copilotShortArtifactLabel(compare.leftPath)} vs ${copilotShortArtifactLabel(compare.rightPath)} · ${compare.modeLabel}`;
  }
  if (compare.leftPath || compare.rightPath) {
    return isKo ? "좌/우 구조를 모두 선택해야 합니다." : "Select both left and right structures.";
  }
  return isKo ? "비교 대상 선택 전" : "Waiting for structure selection.";
}

function copilotCompareMetaText(meta) {
  if (!meta || typeof meta !== "object") return "-";
  const parts = [];
  const source = sourceLabel(compareSourceKeyFromMeta(meta));
  if (source) parts.push(source);
  if (meta?.tier) parts.push(formatCompareTierLabel(meta.tier));
  if (meta?.backboneId) parts.push(displayArtifactPath(meta.backboneId));
  return parts.length ? parts.join(" · ") : "-";
}

function copilotSummaryCards(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  const cards = [];
  const pushCard = (label, value, meta, tone = "teal") => {
    cards.push({
      label,
      value,
      meta,
      tone: ["teal", "amber", "rose"].includes(tone) ? tone : "teal",
    });
  };

  if (!snapshot.runId) {
    pushCard(isKo ? "탭" : "Tab", t(`tabs.${snapshot.tab}`), isKo ? "현재 작업 화면" : "Current workspace", "teal");
    pushCard("Run", isKo ? "선택 안됨" : "Not selected", isKo ? "Monitor 또는 Analyze에서 run을 선택하세요." : "Select a run in Monitor or Analyze.", "amber");
    pushCard(isKo ? "비교" : "Compare", snapshot.compare.ready ? `${copilotShortArtifactLabel(snapshot.compare.leftPath)} vs ${copilotShortArtifactLabel(snapshot.compare.rightPath)}` : isKo ? "선택 필요" : "Selection needed", copilotCompareStateText(snapshot.compare), "amber");
    pushCard(isKo ? "Next" : "Next", isKo ? "Setup 또는 Monitor 열기" : "Open Setup or Monitor", isKo ? "새 run을 시작하거나 기존 run 상태를 불러오세요." : "Create a new run or load an existing run.", "rose");
    return cards;
  }

  const passMeta =
    snapshot.funnel && Number(snapshot.funnel.af2_candidate_total || 0) > 0
      ? `${snapshot.provider} ${isKo ? "통과" : "pass"} ${Number(snapshot.funnel.af2_selected_total || 0)}/${Number(
          snapshot.funnel.af2_candidate_total || 0
        )}`
      : isKo
        ? "실행 진행 추적 중"
        : "Tracking execution state";
  const topValue = snapshot.topRow ? String(snapshot.topRow.seq_id || "-") : isKo ? "Hit List 대기" : "Hit List pending";
  const topMeta = snapshot.topRow
    ? `score ${formatMetricValue(snapshot.topRow.score, 1)} · pLDDT ${formatMetricValue(snapshot.topRow.plddt, 1)} · RMSD ${formatMetricValue(snapshot.topRow.rmsd, 2)} · WT ${formatWtDifference(snapshot.topRow)}`
    : `${snapshot.rows.length} ${isKo ? "행" : "rows"} · ${snapshot.chartLabel}`;
  const compareValue = snapshot.compare.ready
    ? `${copilotShortArtifactLabel(snapshot.compare.leftPath)} vs ${copilotShortArtifactLabel(snapshot.compare.rightPath)}`
    : isKo
      ? "선택 필요"
      : "Selection needed";
  const compareMeta = snapshot.compare.ready
    ? `${snapshot.compare.modeLabel} · ${copilotCompareMetaText(snapshot.compare.leftMeta)} -> ${copilotCompareMetaText(snapshot.compare.rightMeta)}`
    : copilotCompareStateText(snapshot.compare);

  pushCard(
    "Run",
    snapshot.runId,
    `${t(`tabs.${snapshot.tab}`)} · ${snapshot.provider}${snapshot.artifactCount ? ` · ${snapshot.artifactCount} ${isKo ? "산출물" : "artifacts"}` : ""}`,
    "teal"
  );
  pushCard(isKo ? "실행" : "Execution", copilotStatusLabel(snapshot), snapshot.recommendation && snapshot.recommendation !== "-" ? `${passMeta} · ${isKo ? "추천" : "Recommendation"}: ${snapshot.recommendation}` : passMeta, ["failed", "error", "cancelled"].includes(String(snapshot.runState || "").toLowerCase()) ? "rose" : String(snapshot.runState || "").toLowerCase() === "running" ? "amber" : "teal");
  pushCard(isKo ? "Top 후보" : "Top Candidate", topValue, topMeta, "teal");
  pushCard(isKo ? "비교" : "Compare", compareValue, compareMeta, snapshot.compare.ready ? "amber" : "rose");
  return cards;
}

function copilotSuggestedActionIds(snapshot = copilotSnapshot()) {
  const ids = [];
  const push = (id) => {
    if (!id || ids.includes(id)) return;
    ids.push(id);
  };
  const stateText = String(snapshot.runState || "")
    .trim()
    .toLowerCase();

  if (!snapshot.runId) {
    push("openSetup");
    push("openMonitor");
    push("openAnalyze");
    return ids.slice(0, 5);
  }

  if (stateText === "failed" || stateText === "error" || stateText === "cancelled") {
    push("openMonitor");
    push("resume");
    push("refreshArtifacts");
    push("openAnalyze");
    if (snapshot.rows.length) push("refreshHitList");
    if (snapshot.compare.ready) push("compare3d");
    return ids.slice(0, 6);
  }

  if (stateText === "running") {
    push("openMonitor");
    push("poll");
    push("refreshArtifacts");
    push("openAnalyze");
    if (snapshot.compare.ready) push("compare3d");
    return ids.slice(0, 6);
  }

  push("openAnalyze");
  push("refreshHitList");
  if (snapshot.compare.ready) push("compare3d");
  if (snapshot.rows.length) push("generateReport");
  push("refreshArtifacts");
  push("openMonitor");
  return ids.slice(0, 6);
}

function renderCopilotSummary() {
  if (!el.copilotSummary) return;
  const cards = copilotSummaryCards(copilotSnapshot());
  if (!cards.length) {
    el.copilotSummary.innerHTML = `<div class="placeholder">${t("copilot.summary.empty")}</div>`;
    return;
  }
  el.copilotSummary.innerHTML = cards
    .map(
      (card) => `
      <div class="copilot-summary-card tone-${escapeAttr(card.tone || "teal")}">
        <div class="copilot-summary-label">${escapeHtml(card.label || "")}</div>
        <div class="copilot-summary-value">${escapeHtml(card.value || "-")}</div>
        <div class="copilot-summary-meta">${escapeHtml(card.meta || "-")}</div>
      </div>
    `
    )
    .join("");
}

function renderCopilotActions() {
  if (!el.copilotActions) return;
  const actionIds = copilotSuggestedActionIds(copilotSnapshot());
  if (!actionIds.length) {
    el.copilotActions.innerHTML = `<div class="placeholder">${t("copilot.actions.empty")}</div>`;
    return;
  }
  el.copilotActions.innerHTML = "";
  actionIds.forEach((actionId) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copilot-action-btn";
    button.innerHTML = `
      <span class="copilot-action-title">${escapeHtml(t(`copilot.action.${actionId}`))}</span>
      <span class="copilot-action-desc">${escapeHtml(t(`copilot.action.${actionId}.desc`))}</span>
    `;
    button.addEventListener("click", () => {
      void handleCopilotAction(actionId);
    });
    el.copilotActions.appendChild(button);
  });
}

function copilotContextRows(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  const rows = [];
  rows.push({
    label: isKo ? "현재 탭" : "Active Tab",
    value: t(`tabs.${snapshot.tab}`),
  });
  rows.push({
    label: "Run",
    value: snapshot.runId || (isKo ? "선택되지 않음" : "Not selected"),
  });
  rows.push({
    label: isKo ? "비교" : "Compare",
    value: copilotCompareStateText(snapshot.compare),
  });
  if (!snapshot.runId) {
    return rows;
  }
  rows.push({
    label: isKo ? "상태" : "Status",
    value: copilotStatusLabel(snapshot),
  });
  rows.push({
    label: isKo ? "구조 예측기" : "Structure Predictor",
    value: snapshot.provider,
  });
  rows.push({
    label: isKo ? "아티팩트" : "Artifacts",
    value: String(snapshot.artifactCount || 0),
  });
  rows.push({
    label: "Hit List",
    value: `${snapshot.rows.length}`,
  });
  if (snapshot.topRow) {
    rows.push({
      label: isKo ? "Top 후보" : "Top Candidate",
      value: `${snapshot.topRow.seq_id || "-"} · score ${formatMetricValue(snapshot.topRow.score, 1)} · pLDDT ${formatMetricValue(
        snapshot.topRow.plddt,
        1
      )} · RMSD ${formatMetricValue(snapshot.topRow.rmsd, 2)}`,
    });
  }
  if (snapshot.funnel && Number(snapshot.funnel.af2_candidate_total || 0) > 0) {
    rows.push({
      label: isKo ? "AF2 통과" : "AF2 Pass",
      value: `${Number(snapshot.funnel.af2_selected_total || 0)}/${Number(snapshot.funnel.af2_candidate_total || 0)} (${formatPercentValue(
        snapshot.funnel.af2_pass_rate
      )})`,
    });
  }
  if (snapshot.recommendation && snapshot.recommendation !== "-") {
    rows.push({
      label: isKo ? "추천" : "Recommendation",
      value: String(snapshot.recommendation),
    });
  }
  return rows;
}

function renderCopilotContext() {
  renderCopilotSummary();
  renderCopilotActions();
  if (!el.copilotContext) return;
  const rows = copilotContextRows(copilotSnapshot());
  if (!rows.length) {
    el.copilotContext.innerHTML = `<div class="placeholder">${t("copilot.context.empty")}</div>`;
    return;
  }
  el.copilotContext.innerHTML = rows
    .map(
      (row) => `
      <div class="copilot-context-row">
        <strong>${escapeHtml(row.label || "")}</strong>
        <span>${escapeHtml(row.value || "-")}</span>
      </div>
    `
    )
    .join("");
}

function copilotIntentFromPrompt(prompt, intentHint = "") {
  const hinted = String(intentHint || "")
    .trim()
    .toLowerCase();
  if (["usage", "interpret", "summary", "compare", "next", "resume"].includes(hinted)) return hinted;
  const q = String(prompt || "").trim().toLowerCase();
  if (!q) return "general";
  if (/(resume|restart|recover|이어|재시작|다시 시작)/i.test(q)) return "resume";
  if (/(summary|summar|요약|정리)/i.test(q)) return "summary";
  if (/(compare|comparison|studio|left|right|비교|컨텍스트|context)/i.test(q)) return "compare";
  if (/(interpret|해석|지표|점수|plddt|rmsd|score|metric)/i.test(q)) return "interpret";
  if (/(next|다음|뭘|무엇|action|step)/i.test(q)) return "next";
  if (/(usage|how to|사용법|어떻게|guide|도움)/i.test(q)) return "usage";
  return "general";
}

function copilotUsageReply(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  if (snapshot.tab === "setup") {
    return isKo
      ? "Setup에서는 Scope/Input/Options를 채우면 Run 버튼이 활성화됩니다.\n구간 실행이 필요하면 시작 단계와 중단 단계를 함께 지정하세요."
      : "In Setup, fill Scope/Input/Options until Run is enabled.\nFor partial runs, set both `start_from` and `stop_after`.";
  }
  if (snapshot.tab === "monitor") {
    return isKo
      ? "Monitor에서는 run 상태, 아티팩트, 워크플로 체크포인트를 확인합니다.\n중단된 run은 `Run 재시작`, 파일 산출물은 `아티팩트 새로고침`으로 바로 이어갈 수 있습니다."
      : "In Monitor, inspect run state, artifacts, and workflow checkpoints.\nUse `Resume Run` for interrupted runs and `Refresh Artifacts` to reload outputs.";
  }
  return isKo
    ? "Analyze에서는 Hit List, 차트, Compare Studio를 함께 봐야 합니다.\n추천 액션에서 `Hit List 새로고침`, `3D 비교 실행`, `리포트 생성`을 바로 실행할 수 있습니다."
    : "In Analyze, review Hit List, charts, and Compare Studio together.\nUse Suggested Actions to refresh the Hit List, run Compare 3D, or generate the report.";
}

function copilotInterpretReply(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  if (!snapshot.runId) {
    return isKo
      ? "해석할 run이 없습니다. 먼저 Monitor나 Analyze에서 run을 선택하세요."
      : "No run is selected to interpret. Select a run in Monitor or Analyze first.";
  }
  const lines = [];
  lines.push(`Run ${snapshot.runId}: ${copilotStatusLabel(snapshot)} · ${snapshot.provider}`);
  if (snapshot.topRow) {
    lines.push(
      isKo
        ? `Top 후보 ${snapshot.topRow.seq_id || "-"}: score ${formatMetricValue(snapshot.topRow.score, 1)}, pLDDT ${formatMetricValue(
            snapshot.topRow.plddt,
            1
          )}, RMSD ${formatMetricValue(snapshot.topRow.rmsd, 2)}, WT ${formatWtDifference(snapshot.topRow)}`
        : `Top candidate ${snapshot.topRow.seq_id || "-"}: score ${formatMetricValue(snapshot.topRow.score, 1)}, pLDDT ${formatMetricValue(
            snapshot.topRow.plddt,
            1
          )}, RMSD ${formatMetricValue(snapshot.topRow.rmsd, 2)}, WT ${formatWtDifference(snapshot.topRow)}`
    );
  } else {
    lines.push(isKo ? "Hit List 데이터가 아직 없습니다." : "Hit List metrics are not available yet.");
  }
  if (snapshot.funnel && Number(snapshot.funnel.af2_candidate_total || 0) > 0) {
    lines.push(
      isKo
        ? `${snapshot.provider} 통과율: ${Number(snapshot.funnel.af2_selected_total || 0)}/${Number(
            snapshot.funnel.af2_candidate_total || 0
          )} (${formatPercentValue(snapshot.funnel.af2_pass_rate)})`
        : `${snapshot.provider} pass rate: ${Number(snapshot.funnel.af2_selected_total || 0)}/${Number(
            snapshot.funnel.af2_candidate_total || 0
          )} (${formatPercentValue(snapshot.funnel.af2_pass_rate)})`
    );
  }
  lines.push(`${isKo ? "비교 상태" : "Compare state"}: ${copilotCompareStateText(snapshot.compare)}`);
  if (snapshot.recommendation && snapshot.recommendation !== "-") {
    lines.push(isKo ? `현재 추천: ${snapshot.recommendation}` : `Current recommendation: ${snapshot.recommendation}`);
  }
  return lines.join("\n");
}

function copilotSummaryReply(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  if (!snapshot.runId) {
    return isKo
      ? "현재 선택된 run이 없습니다.\nMonitor 또는 Analyze에서 run을 선택하면 상태, Top 후보, 비교 준비 상태를 바로 요약합니다."
      : "No run is currently selected.\nSelect a run in Monitor or Analyze to summarize status, top candidates, and compare readiness.";
  }
  const lines = [];
  lines.push(`Run ${snapshot.runId}`);
  lines.push(`${isKo ? "상태" : "Status"}: ${copilotStatusLabel(snapshot)} · ${snapshot.provider}`);
  lines.push(`${isKo ? "아티팩트" : "Artifacts"}: ${snapshot.artifactCount}`);
  lines.push(`${isKo ? "비교" : "Compare"}: ${copilotCompareStateText(snapshot.compare)}`);
  if (snapshot.topRow) {
    lines.push(
      isKo
        ? `Top 후보: ${snapshot.topRow.seq_id || "-"} · score ${formatMetricValue(snapshot.topRow.score, 1)} · pLDDT ${formatMetricValue(
            snapshot.topRow.plddt,
            1
          )} · RMSD ${formatMetricValue(snapshot.topRow.rmsd, 2)}`
        : `Top candidate: ${snapshot.topRow.seq_id || "-"} · score ${formatMetricValue(snapshot.topRow.score, 1)} · pLDDT ${formatMetricValue(
            snapshot.topRow.plddt,
            1
          )} · RMSD ${formatMetricValue(snapshot.topRow.rmsd, 2)}`
    );
  } else {
    lines.push(isKo ? "Hit List는 아직 비어 있습니다." : "The Hit List is still empty.");
  }
  if (snapshot.funnel && Number(snapshot.funnel.af2_candidate_total || 0) > 0) {
    lines.push(
      `${snapshot.provider} ${isKo ? "통과" : "pass"}: ${Number(snapshot.funnel.af2_selected_total || 0)}/${Number(
        snapshot.funnel.af2_candidate_total || 0
      )} (${formatPercentValue(snapshot.funnel.af2_pass_rate)})`
    );
  }
  if (snapshot.recommendation && snapshot.recommendation !== "-") {
    lines.push(isKo ? `추천: ${snapshot.recommendation}` : `Recommendation: ${snapshot.recommendation}`);
  }
  return lines.join("\n");
}

function copilotCompareReply(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  if (!snapshot.runId) {
    return isKo
      ? "비교할 run이 없습니다. 먼저 run을 선택하세요."
      : "No run is selected for comparison. Select a run first.";
  }
  if (!snapshot.compare.leftPath && !snapshot.compare.rightPath) {
    return isKo
      ? "Compare Studio에서 좌/우 구조를 아직 선택하지 않았습니다.\nAnalyze 탭에서 reference와 candidate를 고른 뒤 `3D 비교 실행`을 누르세요."
      : "No left/right structures are selected in Compare Studio.\nPick a reference and candidate in Analyze, then run `Compare 3D`.";
  }
  if (!snapshot.compare.ready) {
    return isKo
      ? "지금은 한쪽만 선택된 상태입니다. Compare Studio에서 좌/우 구조를 모두 고르면 바로 비교할 수 있습니다."
      : "Only one side is selected right now. Choose both left and right structures in Compare Studio to compare.";
  }
  return [
    `${isKo ? "모드" : "Mode"}: ${snapshot.compare.modeLabel}`,
    `${isKo ? "기준 구조" : "Reference"}: ${copilotShortArtifactLabel(snapshot.compare.leftPath)} (${copilotCompareMetaText(
      snapshot.compare.leftMeta
    )})`,
    `${isKo ? "후보 구조" : "Candidate"}: ${copilotShortArtifactLabel(snapshot.compare.rightPath)} (${copilotCompareMetaText(
      snapshot.compare.rightMeta
    )})`,
    isKo
      ? "추천 액션의 `3D 비교 실행`으로 현재 선택 쌍을 바로 다시 렌더링할 수 있습니다."
      : "Use the `Run Compare 3D` action to render the current pair immediately.",
  ].join("\n");
}

function copilotNextReply(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  const stateText = String(snapshot.runState || "")
    .trim()
    .toLowerCase();
  if (!snapshot.runId) {
    return isKo
      ? "1) Setup에서 입력을 채워 run을 시작하세요.\n2) Monitor에서 기존 run을 선택해 상태와 산출물을 확인하세요."
      : "1) Fill inputs in Setup and launch a run.\n2) Select an existing run in Monitor to inspect state and outputs.";
  }
  if (stateText === "running") {
    return isKo
      ? "지금은 실행 중입니다. Monitor에서 `지금 조회` 또는 Auto Poll로 상태를 갱신하고, 완료 후 Analyze로 넘어가세요."
      : "The run is still in progress. Refresh status in Monitor with `Poll Now` or Auto Poll, then move to Analyze after completion.";
  }
  if (stateText === "failed" || stateText === "error" || stateText === "cancelled") {
    return isKo
      ? "중단된 run입니다. Monitor의 `Run 재시작`으로 이어서 실행을 시도하고, 필요하면 `아티팩트 새로고침`으로 산출물을 다시 읽으세요."
      : "This run is interrupted. Use `Resume Run` in Monitor, then `Refresh Artifacts` if you need to reload outputs.";
  }
  if (!snapshot.rows.length) {
    return isKo
      ? "다음 단계: Analyze에서 Hit List를 새로고침하고, Compare Studio에 reference/candidate를 선택하세요."
      : "Next: refresh the Hit List in Analyze, then choose reference/candidate structures in Compare Studio.";
  }
  if (!snapshot.compare.ready) {
    return isKo
      ? "다음 단계: Compare Studio에서 좌/우 구조를 고르고 `3D 비교 실행`을 누르세요. 그 다음 리포트를 갱신하면 됩니다."
      : "Next: choose left/right structures in Compare Studio and run `Compare 3D`. After that, refresh the report.";
  }
  return isKo
    ? `다음 단계: Compare Studio를 실행한 뒤 리포트를 갱신하세요. 후보 해석은 차트(${snapshot.chartLabel})와 Hit List를 함께 보면서 진행하면 됩니다.`
    : `Next: run Compare Studio, then refresh the report. Interpret candidates with both the chart (${snapshot.chartLabel}) and the Hit List.`;
}

function copilotResumeReply(snapshot = copilotSnapshot()) {
  const isKo = copilotIsKorean();
  if (!snapshot.runId) {
    return isKo ? "재시작하려면 먼저 run을 선택하세요." : "Select a run first to resume it.";
  }
  const stateText = String(snapshot.runState || "")
    .trim()
    .toLowerCase();
  if (stateText === "running") {
    return isKo
      ? "현재 run은 이미 실행 중입니다. 별도 재시작이 필요 없습니다."
      : "This run is already running. No resume action is needed.";
  }
  return isKo
    ? "`Run 재시작`은 이 run의 request.json을 읽어 같은 run_id로 다시 실행합니다.\n기존 산출물은 `force=false`로 최대한 재사용하고, 누락 단계부터 이어집니다."
    : "`Resume Run` reads request.json and relaunches with the same run_id.\nWith `force=false`, existing artifacts are reused and missing stages continue.";
}

function generateCopilotReply(prompt, intentHint = "") {
  const intent = copilotIntentFromPrompt(prompt, intentHint);
  const snapshot = copilotSnapshot();
  if (intent === "usage") return copilotUsageReply(snapshot);
  if (intent === "interpret") return copilotInterpretReply(snapshot);
  if (intent === "summary") return copilotSummaryReply(snapshot);
  if (intent === "compare") return copilotCompareReply(snapshot);
  if (intent === "next") return copilotNextReply(snapshot);
  if (intent === "resume") return copilotResumeReply(snapshot);
  return `${copilotSummaryReply(snapshot)}\n\n${copilotNextReply(snapshot)}`;
}

function renderCopilotMessages() {
  if (!el.copilotMessages) return;
  const history = Array.isArray(state.copilotHistory) ? state.copilotHistory : [];
  el.copilotMessages.innerHTML = "";
  history.forEach((item) => {
    const role = item?.role === "user" ? "user" : "ai";
    const wrap = document.createElement("div");
    wrap.className = `copilot-message ${role}`;
    const meta = document.createElement("div");
    meta.className = "copilot-message-meta";
    meta.textContent = role === "user" ? t("copilot.role.user") : t("copilot.role.ai");
    const bubble = document.createElement("div");
    bubble.className = "copilot-bubble";
    bubble.innerHTML = escapeHtml(item?.text || "").replace(/\n/g, "<br />");
    wrap.appendChild(meta);
    wrap.appendChild(bubble);
    el.copilotMessages.appendChild(wrap);
  });
  el.copilotMessages.scrollTop = el.copilotMessages.scrollHeight;
}

function addCopilotHistory(role, text) {
  if (!Array.isArray(state.copilotHistory)) state.copilotHistory = [];
  state.copilotHistory.push({
    role: role === "user" ? "user" : "ai",
    text: String(text || "").trim(),
    ts: Date.now(),
  });
  if (state.copilotHistory.length > 80) {
    state.copilotHistory = state.copilotHistory.slice(-80);
  }
  renderCopilotMessages();
}

function submitCopilotPrompt(rawPrompt, intentHint = "") {
  const prompt = String(rawPrompt || "").trim();
  if (!prompt) return;
  addCopilotHistory("user", prompt);
  addCopilotHistory("ai", generateCopilotReply(prompt, intentHint));
  renderCopilotContext();
}

function clearCopilotHistory() {
  state.copilotHistory = [];
  renderCopilotMessages();
  ensureCopilotWelcome();
}

function ensureCopilotWelcome() {
  if (Array.isArray(state.copilotHistory) && state.copilotHistory.length) return;
  const intro = copilotIsKorean()
    ? "현재 탭과 run 데이터를 요약하고, 바로 실행 가능한 액션을 추천합니다."
    : "I summarize the current tab/run state and recommend actions you can run immediately.";
  addCopilotHistory("ai", intro);
}

async function handleCopilotAction(actionId) {
  const label = t(`copilot.action.${actionId}`) || actionId;
  const announce = !["openSetup", "openMonitor", "openAnalyze"].includes(actionId);
  try {
    if (actionId === "openSetup") {
      setActiveTab("setup");
    } else if (actionId === "openMonitor") {
      setActiveTab("monitor");
    } else if (actionId === "openAnalyze") {
      setActiveTab("analyze");
    } else if (actionId === "poll") {
      if (!state.currentRunId) throw new Error(copilotIsKorean() ? "run이 선택되지 않았습니다." : "No run selected.");
      setActiveTab("monitor");
      await pollStatus(state.currentRunId);
    } else if (actionId === "refreshArtifacts") {
      if (!state.currentRunId) throw new Error(copilotIsKorean() ? "run이 선택되지 않았습니다." : "No run selected.");
      await refreshArtifacts();
    } else if (actionId === "refreshHitList") {
      if (!state.currentRunId) throw new Error(copilotIsKorean() ? "run이 선택되지 않았습니다." : "No run selected.");
      setActiveTab("analyze");
      await refreshHitList();
    } else if (actionId === "generateReport") {
      if (!state.currentRunId) throw new Error(copilotIsKorean() ? "run이 선택되지 않았습니다." : "No run selected.");
      setActiveTab("report");
      await generateReport();
    } else if (actionId === "resume") {
      if (!state.currentRunId) throw new Error(copilotIsKorean() ? "run이 선택되지 않았습니다." : "No run selected.");
      setActiveTab("monitor");
      await resumeCurrentRun();
    } else if (actionId === "compare3d") {
      if (!state.currentRunId) throw new Error(copilotIsKorean() ? "run이 선택되지 않았습니다." : "No run selected.");
      if (!state.artifactCompareLeftPath || !state.artifactCompareRightPath) {
        throw new Error(copilotIsKorean() ? "좌/우 구조를 모두 선택하세요." : "Select both left and right structures.");
      }
      setActiveTab("analyze");
      await compareSelected3dArtifacts();
    } else {
      return;
    }
    renderCopilotContext();
    if (announce) addCopilotHistory("ai", t("copilot.action.completed", { action: label }));
  } catch (err) {
    addCopilotHistory("ai", t("copilot.action.failed", { action: label, error: err.message || String(err) }));
  }
}

function setCopilotDrawerOpen(open) {
  if (!el.copilotDrawer) return;
  const shouldOpen = Boolean(open);
  el.copilotDrawer.classList.toggle("hidden", !shouldOpen);
  el.copilotDrawer.setAttribute("aria-hidden", shouldOpen ? "false" : "true");
  if (el.copilotBackdrop) {
    el.copilotBackdrop.classList.toggle("hidden", !shouldOpen);
    el.copilotBackdrop.setAttribute("aria-hidden", shouldOpen ? "false" : "true");
  }
  if (el.copilotFabBtn) {
    el.copilotFabBtn.classList.toggle("hidden", shouldOpen);
  }
  if (!shouldOpen) return;
  ensureCopilotWelcome();
  renderCopilotContext();
  renderCopilotMessages();
  if (el.copilotInput) el.copilotInput.focus();
}

function initCopilot() {
  renderCopilotContext();
  renderCopilotMessages();
  if (copilotInitialized) return;
  if (el.copilotOpenBtn) {
    el.copilotOpenBtn.addEventListener("click", () => setCopilotDrawerOpen(true));
  }
  if (el.copilotFabBtn) {
    el.copilotFabBtn.addEventListener("click", () => setCopilotDrawerOpen(true));
  }
  if (el.copilotCloseBtn) {
    el.copilotCloseBtn.addEventListener("click", () => setCopilotDrawerOpen(false));
  }
  if (el.copilotBackdrop) {
    el.copilotBackdrop.addEventListener("click", () => setCopilotDrawerOpen(false));
  }
  if (el.copilotClearBtn) {
    el.copilotClearBtn.addEventListener("click", () => clearCopilotHistory());
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setCopilotDrawerOpen(false);
  });
  if (el.copilotSendBtn) {
    el.copilotSendBtn.addEventListener("click", () => {
      submitCopilotPrompt(el.copilotInput?.value || "");
      if (el.copilotInput) el.copilotInput.value = "";
    });
  }
  if (el.copilotInput) {
    el.copilotInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      submitCopilotPrompt(el.copilotInput.value || "");
      el.copilotInput.value = "";
    });
  }
  if (el.copilotQuickUsage) {
    el.copilotQuickUsage.addEventListener("click", () => submitCopilotPrompt(t("copilot.quick.usage"), "usage"));
  }
  if (el.copilotQuickInterpret) {
    el.copilotQuickInterpret.addEventListener("click", () => submitCopilotPrompt(t("copilot.quick.interpret"), "interpret"));
  }
  if (el.copilotQuickSummary) {
    el.copilotQuickSummary.addEventListener("click", () => submitCopilotPrompt(t("copilot.quick.summary"), "summary"));
  }
  if (el.copilotQuickCompare) {
    el.copilotQuickCompare.addEventListener("click", () => submitCopilotPrompt(t("copilot.quick.compare"), "compare"));
  }
  if (el.copilotQuickNext) {
    el.copilotQuickNext.addEventListener("click", () => submitCopilotPrompt(t("copilot.quick.next"), "next"));
  }
  if (el.copilotQuickResume) {
    el.copilotQuickResume.addEventListener("click", () => submitCopilotPrompt(t("copilot.quick.resume"), "resume"));
  }
  setCopilotDrawerOpen(false);
  copilotInitialized = true;
}

function isRunReportFilename(filename) {
  const name = String(filename || "")
    .trim()
    .toLowerCase();
  if (!name) return false;
  return name === "report.md" || name === "report_ko.md" || /(?:^|\/)report(?:_ko)?\.md$/.test(name);
}

function renderReportModalContent() {
  return renderMarkdown(state.reportModalText || "");
}

function openReportModal(title, content, filename) {
  if (!el.reportModal) return;
  state.reportModalText = String(content || "");
  state.reportModalMode = "rendered";
  state.reportModalFilename = filename || "report.md";
  if (el.reportModalTitle) el.reportModalTitle.textContent = title || "Report";
  if (el.reportModalToggle) el.reportModalToggle.textContent = t("report.modal.toggleRendered");
  if (el.reportModalContent) {
    el.reportModalContent.innerHTML = renderReportModalContent();
    void hydrateReportModalArtifactImages();
  }
  el.reportModal.classList.remove("hidden");
}

function closeReportModal() {
  if (!el.reportModal) return;
  el.reportModal.classList.add("hidden");
}

function toggleReportModalMode() {
  if (!el.reportModalContent) return;
  if (state.reportModalMode === "rendered") {
    state.reportModalMode = "raw";
    el.reportModalContent.textContent = state.reportModalText || "";
    if (el.reportModalToggle) el.reportModalToggle.textContent = t("report.modal.toggleRaw");
  } else {
    state.reportModalMode = "rendered";
    el.reportModalContent.innerHTML = renderReportModalContent();
    void hydrateReportModalArtifactImages();
    if (el.reportModalToggle) el.reportModalToggle.textContent = t("report.modal.toggleRendered");
  }
}

function downloadReportModal() {
  const text = state.reportModalText || "";
  const name = state.reportModalFilename || "report.md";
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function isHttp400Error(err) {
  const msg = String(err?.message || "");
  return msg.includes("HTTP 400");
}

function setUserBadge() {
  if (!state.user) return;
  const base = state.user.username || "user";
  const roleKey = state.user.role === "admin" ? "role.admin" : "role.user";
  el.userBadge.textContent = `${base} · ${t(roleKey)}`;
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("option[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
}

function updateLangButtons() {
  langButtons.forEach((btn) => {
    const isActive = btn.dataset.lang === state.lang;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function setLanguage(lang) {
  const next = LANG_OPTIONS.includes(lang) ? lang : "en";
  if (state.lang === next) return;
  state.lang = next;
  localStorage.setItem(LANG_KEY, next);
  document.documentElement.lang = next;
  updateLangButtons();
  applyI18n();
  setUserBadge();
  updateRunLabel();
  renderQuestions(state.plan?.questions || []);
  updateRunEligibility(state.plan?.questions || []);
  renderFeedbackControls();
  renderReportReviewControls();
  refillSelect(el.feedbackStage, FEEDBACK_STAGES, { includeEmpty: false });
  refillSelect(el.experimentAssay, EXPERIMENT_ASSAYS, { includeEmpty: false });
  refillSelect(el.experimentResult, EXPERIMENT_RESULTS, { includeEmpty: false });
  refreshArtifactSelects();
  renderArtifactComparisonSummary(state.artifactComparison);
  renderMonitorCompleteness(state.artifactComparison, state.hitListResult?.completeness || null);
  updateMonitorReportActions();
  renderAllArtifactViews(state.artifacts);
  if (state.runs) renderRuns(state.runs);
  populateRunCompareBaselineOptions();
  renderRunCompareSummary(state.runCompareResult);
  renderHitList();
  updateReportArtifactLinks(el.reportContent ? el.reportContent.value : "");
  updateReportScore(state.lastScore || {});
  updateAnalyzeSummary();
  updateReportLangSelect();
  renderCopilotContext();
  if (state.lastRunStatus) {
    updateRunInfo(state.lastRunStatus);
  }
  if (el.reportModal && el.reportModalContent && !el.reportModal.classList.contains("hidden")) {
    if (state.reportModalMode === "rendered") {
      el.reportModalContent.innerHTML = renderReportModalContent();
      void hydrateReportModalArtifactImages();
    }
  }
}

function initLanguage() {
  if (!langInitialized) {
    langButtons.forEach((btn) => {
      btn.addEventListener("click", () => setLanguage(btn.dataset.lang));
    });
    langInitialized = true;
  }
  document.documentElement.lang = state.lang;
  updateLangButtons();
  applyI18n();
  updateReportScore(state.lastScore || {});
  updateAnalyzeSummary();
  updateReportLangSelect();
}

function normalizeTab(value) {
  if (TAB_OPTIONS.includes(value)) return value;
  return "setup";
}

function setActiveTab(value) {
  const next = normalizeTab(value);
  tabButtons.forEach((btn) => {
    const isActive = btn.dataset.tab === next;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
    btn.tabIndex = isActive ? 0 : -1;
  });
  tabPanels.forEach((panel) => {
    const isActive = panel.dataset.tab === next;
    panel.classList.toggle("active", isActive);
    panel.setAttribute("aria-hidden", isActive ? "false" : "true");
  });
  localStorage.setItem(TAB_KEY, next);
  renderCopilotContext();
  if (next === "monitor" && el.autoPoll?.checked && state.currentRunId) {
    void pollCurrentRun({ includeArtifacts: "auto" });
  }
}

function initTabs() {
  if (!tabButtons.length) return;
  if (!tabsInitialized) {
    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
    });
    tabsInitialized = true;
  }
  const stored = localStorage.getItem(TAB_KEY);
  setActiveTab(stored || "setup");
}

function showLogin() {
  el.loginGate.classList.remove("hidden");
  if (el.appShell) el.appShell.classList.add("hidden");
  if (el.chatArea) el.chatArea.classList.add("hidden");
  if (el.adminBtn) el.adminBtn.classList.add("hidden");
  if (el.settingsPanel) el.settingsPanel.classList.add("hidden");
  if (el.adminPanel) el.adminPanel.classList.add("hidden");
  if (el.helpPanel) el.helpPanel.classList.add("hidden");
}

function showChat() {
  el.loginGate.classList.add("hidden");
  if (el.appShell) el.appShell.classList.remove("hidden");
  if (el.chatArea) el.chatArea.classList.remove("hidden");
  setUserBadge();
  ensureManualPlan();
  initTabs();
}

function updateAdminUI() {
  const isAdmin = state.user && state.user.role === "admin";
  if (isAdmin) {
    if (el.adminBtn) el.adminBtn.classList.remove("hidden");
    if (el.adminRunsToggle) el.adminRunsToggle.classList.remove("hidden");
  } else {
    if (el.adminBtn) el.adminBtn.classList.add("hidden");
    if (el.adminPanel) el.adminPanel.classList.add("hidden");
    if (el.adminRunsToggle) el.adminRunsToggle.classList.add("hidden");
    if (el.showAllRuns) el.showAllRuns.checked = false;
  }
}

function buildManualPlan(mode) {
  const questions = [
    {
      id: "run_mode",
      labelKey: "question.runMode.label",
      questionKey: "question.runMode.help",
      required: true,
      default: "pipeline",
    },
  ];

  if (mode === "pipeline") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.targetInput.label",
        questionKey: "question.targetInput.help",
        required: true,
      },
      {
        id: "start_from",
        labelKey: "question.startFrom.label",
        questionKey: "question.startFrom.help",
        required: false,
        default: "msa",
      },
      {
        id: "stop_after",
        labelKey: "question.stopAfter.label",
        questionKey: "question.stopAfter.help",
        required: false,
        default: "novelty",
      },
      {
        id: "novelty_enabled",
        labelKey: "question.noveltyEnabled.label",
        questionKey: "question.noveltyEnabled.help",
        required: false,
        default: true,
      },
      {
        id: "bioemu_use",
        labelKey: "question.bioemuUse.label",
        questionKey: "question.bioemuUse.help",
        required: false,
        default: true,
      },
      {
        id: "bioemu_num_samples",
        labelKey: "question.bioemuNumSamples.label",
        questionKey: "question.bioemuNumSamples.help",
        required: false,
        default: 10,
      },
      {
        id: "bioemu_max_return_structures",
        labelKey: "question.bioemuMaxReturn.label",
        questionKey: "question.bioemuMaxReturn.help",
        required: false,
        default: 10,
      },
      {
        id: "af2_max_candidates_per_tier",
        labelKey: "question.af2MaxCandidatesPerTier.label",
        questionKey: "question.af2MaxCandidatesPerTier.help",
        required: false,
        default: 0,
      },
      {
        id: "af2_plddt_cutoff",
        labelKey: "question.af2PlddtCutoff.label",
        questionKey: "question.af2PlddtCutoff.help",
        required: false,
        default: 85.0,
      },
      {
        id: "af2_rmsd_cutoff",
        labelKey: "question.af2RmsdCutoff.label",
        questionKey: "question.af2RmsdCutoff.help",
        required: false,
        default: 2.0,
      },
      {
        id: "af2_provider",
        labelKey: "question.af2Provider.label",
        questionKey: "question.af2Provider.help",
        required: false,
        default: "colabfold",
      },
      {
        id: "num_seq_per_tier",
        labelKey: "question.numSeqPerTier.label",
        questionKey: "question.numSeqPerTier.help",
        required: false,
        default: 2,
      },
      {
        id: "design_chains",
        labelKey: "question.designChains.label",
        questionKey: "question.designChains.help",
        required: false,
      },
      {
        id: "pdb_strip_nonpositive_resseq",
        labelKey: "question.stripNonpositive.label",
        questionKey: "question.stripNonpositive.help",
        required: false,
        default: true,
      },
      {
        id: "wt_compare",
        labelKey: "question.wtCompare.label",
        questionKey: "question.wtCompare.help",
        required: false,
        default: true,
      },
      {
        id: "mask_consensus_apply",
        labelKey: "question.maskConsensusApply.label",
        questionKey: "question.maskConsensusApply.help",
        required: false,
        default: false,
      },
      {
        id: "ligand_mask_use_original_target",
        labelKey: "question.ligandMaskOriginal.label",
        questionKey: "question.ligandMaskOriginal.help",
        required: false,
        default: true,
      },
      {
        id: "fixed_positions_extra",
        labelKey: "question.fixedPositionsExtra.label",
        questionKey: "question.fixedPositionsExtra.help",
        required: false,
      },
      {
        id: "rfd3_input_pdb",
        labelKey: "question.rfd3InputPdb.label",
        questionKey: "question.rfd3InputPdb.help",
        required: false,
      },
      {
        id: "rfd3_contig",
        labelKey: "question.rfd3Contig.label",
        questionKey: "question.rfd3Contig.help",
        required: false,
      },
      {
        id: "rfd3_max_return_designs",
        labelKey: "question.rfd3MaxReturn.label",
        questionKey: "question.rfd3MaxReturn.help",
        required: false,
        default: 10,
      },
      {
        id: "diffdock_ligand",
        labelKey: "question.diffdockLigand.label",
        questionKey: "question.diffdockLigand.help",
        required: false,
      }
    );
  }

  if (mode === "workflow") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.targetInput.label",
        questionKey: "question.targetInput.help",
        required: true,
      },
      {
        id: "af2_provider",
        labelKey: "question.af2Provider.label",
        questionKey: "question.af2Provider.help",
        required: false,
        default: "colabfold",
      },
      {
        id: "num_seq_per_tier",
        labelKey: "question.numSeqPerTier.label",
        questionKey: "question.numSeqPerTier.help",
        required: false,
        default: 2,
      },
      {
        id: "af2_max_candidates_per_tier",
        labelKey: "question.af2MaxCandidatesPerTier.label",
        questionKey: "question.af2MaxCandidatesPerTier.help",
        required: false,
        default: 0,
      },
      {
        id: "af2_plddt_cutoff",
        labelKey: "question.af2PlddtCutoff.label",
        questionKey: "question.af2PlddtCutoff.help",
        required: false,
        default: 85.0,
      },
      {
        id: "af2_rmsd_cutoff",
        labelKey: "question.af2RmsdCutoff.label",
        questionKey: "question.af2RmsdCutoff.help",
        required: false,
        default: 2.0,
      },
      {
        id: "design_chains",
        labelKey: "question.designChains.label",
        questionKey: "question.designChains.help",
        required: false,
      },
      {
        id: "pdb_strip_nonpositive_resseq",
        labelKey: "question.stripNonpositive.label",
        questionKey: "question.stripNonpositive.help",
        required: false,
        default: true,
      },
      {
        id: "wt_compare",
        labelKey: "question.wtCompare.label",
        questionKey: "question.wtCompare.help",
        required: false,
        default: true,
      },
      {
        id: "mask_consensus_apply",
        labelKey: "question.maskConsensusApply.label",
        questionKey: "question.maskConsensusApply.help",
        required: false,
        default: false,
      },
      {
        id: "ligand_mask_use_original_target",
        labelKey: "question.ligandMaskOriginal.label",
        questionKey: "question.ligandMaskOriginal.help",
        required: false,
        default: true,
      },
      {
        id: "fixed_positions_extra",
        labelKey: "question.fixedPositionsExtra.label",
        questionKey: "question.fixedPositionsExtra.help",
        required: false,
      },
      {
        id: "rfd3_input_pdb",
        labelKey: "question.rfd3InputPdb.label",
        questionKey: "question.rfd3InputPdb.help",
        required: false,
      },
      {
        id: "rfd3_contig",
        labelKey: "question.rfd3Contig.label",
        questionKey: "question.rfd3Contig.help",
        required: false,
      },
      {
        id: "rfd3_max_return_designs",
        labelKey: "question.rfd3MaxReturn.label",
        questionKey: "question.rfd3MaxReturn.help",
        required: false,
        default: 10,
      },
      {
        id: "bioemu_num_samples",
        labelKey: "question.bioemuNumSamples.label",
        questionKey: "question.bioemuNumSamples.help",
        required: false,
        default: 10,
      },
      {
        id: "bioemu_max_return_structures",
        labelKey: "question.bioemuMaxReturn.label",
        questionKey: "question.bioemuMaxReturn.help",
        required: false,
        default: 10,
      }
    );
  }

  if (mode === "rfd3") {
    questions.push(
      {
        id: "rfd3_input_pdb",
        labelKey: "question.rfd3InputPdb.label",
        questionKey: "question.rfd3InputPdb.help",
        required: true,
      },
      {
        id: "rfd3_contig",
        labelKey: "question.rfd3Contig.label",
        questionKey: "question.rfd3Contig.help",
        required: true,
      },
      {
        id: "rfd3_max_return_designs",
        labelKey: "question.rfd3MaxReturn.label",
        questionKey: "question.rfd3MaxReturn.help",
        required: false,
        default: 10,
      },
      {
        id: "pdb_strip_nonpositive_resseq",
        labelKey: "question.stripNonpositive.label",
        questionKey: "question.stripNonpositive.help",
        required: false,
        default: true,
      }
    );
  }

  if (mode === "bioemu") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.targetInput.label",
        questionKey: "question.targetInput.help",
        required: true,
      },
      {
        id: "bioemu_use",
        labelKey: "question.bioemuUse.label",
        questionKey: "question.bioemuUse.help",
        required: false,
        default: true,
      },
      {
        id: "bioemu_num_samples",
        labelKey: "question.bioemuNumSamples.label",
        questionKey: "question.bioemuNumSamples.help",
        required: false,
        default: 10,
      },
      {
        id: "bioemu_max_return_structures",
        labelKey: "question.bioemuMaxReturn.label",
        questionKey: "question.bioemuMaxReturn.help",
        required: false,
        default: 10,
      }
    );
  }

  if (mode === "msa") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.targetInput.label",
        questionKey: "question.targetInput.help",
        required: true,
      },
      {
        id: "pdb_strip_nonpositive_resseq",
        labelKey: "question.stripNonpositive.label",
        questionKey: "question.stripNonpositive.help",
        required: false,
        default: true,
      }
    );
  }

  if (mode === "design") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.targetInput.label",
        questionKey: "question.targetInput.help",
        required: true,
      },
      {
        id: "design_chains",
        labelKey: "question.designChains.label",
        questionKey: "question.designChains.help",
        required: false,
      },
      {
        id: "pdb_strip_nonpositive_resseq",
        labelKey: "question.stripNonpositive.label",
        questionKey: "question.stripNonpositive.help",
        required: false,
        default: true,
      },
      {
        id: "bioemu_use",
        labelKey: "question.bioemuUse.label",
        questionKey: "question.bioemuUse.help",
        required: false,
        default: true,
      },
      {
        id: "bioemu_num_samples",
        labelKey: "question.bioemuNumSamples.label",
        questionKey: "question.bioemuNumSamples.help",
        required: false,
        default: 10,
      },
      {
        id: "bioemu_max_return_structures",
        labelKey: "question.bioemuMaxReturn.label",
        questionKey: "question.bioemuMaxReturn.help",
        required: false,
        default: 10,
      }
    );
  }

  if (mode === "soluprot") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.targetInput.label",
        questionKey: "question.targetInput.help",
        required: true,
      },
      {
        id: "design_chains",
        labelKey: "question.designChains.label",
        questionKey: "question.designChains.help",
        required: false,
      },
      {
        id: "pdb_strip_nonpositive_resseq",
        labelKey: "question.stripNonpositive.label",
        questionKey: "question.stripNonpositive.help",
        required: false,
        default: true,
      },
      {
        id: "bioemu_use",
        labelKey: "question.bioemuUse.label",
        questionKey: "question.bioemuUse.help",
        required: false,
        default: true,
      },
      {
        id: "bioemu_num_samples",
        labelKey: "question.bioemuNumSamples.label",
        questionKey: "question.bioemuNumSamples.help",
        required: false,
        default: 10,
      },
      {
        id: "bioemu_max_return_structures",
        labelKey: "question.bioemuMaxReturn.label",
        questionKey: "question.bioemuMaxReturn.help",
        required: false,
        default: 10,
      }
    );
  }

  if (mode === "af2") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.targetFasta.label",
        questionKey: "question.targetFasta.help",
        required: true,
      },
      {
        id: "af2_provider",
        labelKey: "question.af2Provider.label",
        questionKey: "question.af2Provider.help",
        required: false,
        default: "colabfold",
      }
    );
  }

  if (mode === "diffdock") {
    questions.push(
      {
        id: "target_input",
        labelKey: "question.proteinPdb.label",
        questionKey: "question.proteinPdb.help",
        required: true,
      },
      {
        id: "diffdock_ligand",
        labelKey: "question.ligandInput.label",
        questionKey: "question.ligandInput.help",
        required: true,
      }
    );
  }

  return { routed_request: {}, questions };
}

function updateRunLabel() {
  if (!el.runBtn) return;
  const labels = {
    pipeline: "run.label.pipeline",
    workflow: "run.label.workflow",
    rfd3: "run.label.rfd3",
    bioemu: "run.label.bioemu",
    msa: "run.label.msa",
    design: "run.label.design",
    soluprot: "run.label.soluprot",
    af2: "run.label.af2",
    diffdock: "run.label.diffdock",
  };
  const key = labels[state.runMode];
  el.runBtn.textContent = key ? t(key) : "Run";
}

function setRunMode(mode, { render = true } = {}) {
  const normalized = RUN_MODE_OPTIONS.find((opt) => opt.value === mode)?.value || "pipeline";
  state.runMode = normalized;
  state.setupStepIndex = 0;
  if (normalized === "workflow") {
    state.workflowDesigner = createWorkflowDesignerState();
  }
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
  resetSetupResiduePicker();
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
    btn.textContent = labelFor(opt);
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
    btn.textContent = labelFor(opt);
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
    opt.textContent = t("common.none");
    select.appendChild(opt);
  }
  options.forEach((item) => {
    const opt = document.createElement("option");
    opt.value = item.value;
    opt.textContent = labelFor(item);
    select.appendChild(opt);
  });
}

function refillSelect(select, options, { includeEmpty = false } = {}) {
  if (!select) return;
  const current = select.value;
  fillSelect(select, options, { includeEmpty });
  if (current !== undefined) {
    select.value = current;
  }
}

function renderFeedbackControls() {
  if (!el.feedbackRating || !el.feedbackReasons) return;
  renderSingleButtons(
    el.feedbackRating,
    [
      { labelKey: "feedback.rating.good", value: "good" },
      { labelKey: "feedback.rating.bad", value: "bad" },
    ],
    state.feedbackRating,
    (value) => {
      state.feedbackRating = value;
    }
  );

  const reasonsForRating =
    FEEDBACK_REASONS_BY_RATING[state.feedbackRating] || FEEDBACK_REASONS_BY_RATING.bad;
  const allowed = new Set(reasonsForRating.map((item) => item.value));
  if (Array.isArray(state.feedbackReasons)) {
    state.feedbackReasons = state.feedbackReasons.filter((reason) => allowed.has(reason));
  }

  renderToggleButtons(el.feedbackReasons, reasonsForRating, state.feedbackReasons, (value) => {
    const next = new Set(state.feedbackReasons);
    if (next.has(value)) {
      next.delete(value);
    } else {
      next.add(value);
    }
    state.feedbackReasons = Array.from(next);
  });
}

function renderReportReviewControls() {
  if (!el.reportReviewRating || !el.reportReviewReasons) return;
  renderSingleButtons(
    el.reportReviewRating,
    [
      { labelKey: "feedback.rating.good", value: "good" },
      { labelKey: "feedback.rating.bad", value: "bad" },
    ],
    state.reportReviewRating,
    (value) => {
      state.reportReviewRating = value;
    }
  );

  const reasonsForRating =
    REPORT_REVIEW_REASONS_BY_RATING[state.reportReviewRating] || REPORT_REVIEW_REASONS_BY_RATING.bad;
  const allowed = new Set(reasonsForRating.map((item) => item.value));
  if (Array.isArray(state.reportReviewReasons)) {
    state.reportReviewReasons = state.reportReviewReasons.filter((reason) => allowed.has(reason));
  }

  renderToggleButtons(el.reportReviewReasons, reasonsForRating, state.reportReviewReasons, (value) => {
    const next = new Set(state.reportReviewReasons);
    if (next.has(value)) {
      next.delete(value);
    } else {
      next.add(value);
    }
    state.reportReviewReasons = Array.from(next);
  });
}

function refreshArtifactSelects() {
  const options = [
    { labelKey: "common.none", value: "" },
    ...state.artifacts.map((item) => ({ label: displayArtifactPath(item.path), value: item.path })),
  ];
  if (el.feedbackArtifact) {
    fillSelect(el.feedbackArtifact, options);
  }
  if (el.experimentArtifact) {
    fillSelect(el.experimentArtifact, options);
  }
  renderArtifactCompareSelects();
}

function initFeedbackUI() {
  renderFeedbackControls();
  renderReportReviewControls();
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

function inferRunModeFromRequestPayload(payload) {
  return inferRequestRunMode(payload);
}

function normalizeTierKeyValue(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  const asNum = Number(raw);
  if (!Number.isFinite(asNum)) return raw;
  if (Math.abs(asNum) <= 1.0) {
    return String(Math.round(asNum * 100));
  }
  return String(Math.round(asNum));
}

function buildProgressContextFromRequestPayload(payload) {
  if (!payload || typeof payload !== "object") return null;
  const rawTiers = Array.isArray(payload.conservation_tiers) ? payload.conservation_tiers : [0.3, 0.5, 0.7];
  const tierKeys = Array.from(
    new Set(
      rawTiers
        .map((item) => normalizeTierKeyValue(item))
        .filter((item) => String(item || "").trim())
    )
  );
  const stopAfter = String(payload.stop_after || "")
    .trim()
    .toLowerCase();
  const startFrom = normalizePipelineStage(payload.start_from, "msa") || "msa";
  const noveltyEnabled = Boolean(payload.novelty_enabled) || stopAfter === "novelty";
  return {
    tierKeys,
    noveltyEnabled,
    stopAfter,
    startFrom,
  };
}

async function ensureRunModeForRunId(runId, status) {
  if (!runId) return "pipeline";
  if (state.workflowPlansByRunId && state.workflowPlansByRunId[runId]) {
    if (!state.progressContextByRunId[runId]) {
      try {
        const req = await apiCall("pipeline.read_artifact", {
          run_id: runId,
          path: "request.json",
          max_bytes: 2_500_000,
        });
        const text = typeof req?.text === "string" ? req.text : "";
        if (text.trim()) {
          const payload = JSON.parse(text);
          const progressContext = buildProgressContextFromRequestPayload(payload);
          if (progressContext) state.progressContextByRunId[runId] = progressContext;
        }
      } catch (_err) {
        // Keep workflow mode even if request.json cannot be loaded.
      }
    }
    state.runModeById[runId] = "workflow";
    return "workflow";
  }
  const mapped = state.runModeById[runId];
  const context = state.progressContextByRunId[runId];
  if (mapped && PROGRESS_PLANS[mapped] && (mapped !== "pipeline" || context)) return mapped;

  try {
    const req = await apiCall("pipeline.read_artifact", {
      run_id: runId,
      path: "request.json",
      max_bytes: 2_500_000,
    });
    const text = typeof req?.text === "string" ? req.text : "";
    if (text.trim()) {
      const payload = JSON.parse(text);
      if (payload && typeof payload === "object" && Object.prototype.hasOwnProperty.call(payload, "af2_provider")) {
        const shouldRefreshAf2Labels = setAf2ProviderForRun(runId, payload.af2_provider);
        if (shouldRefreshAf2Labels) {
          refreshAf2ProviderLabels({ rerenderQuestions: true });
        }
      }
      const progressContext = buildProgressContextFromRequestPayload(payload);
      if (progressContext) {
        state.progressContextByRunId[runId] = progressContext;
      }
      const inferred = inferRunModeFromRequestPayload(payload);
      if (inferred && PROGRESS_PLANS[inferred]) {
        state.runModeById[runId] = inferred;
        return inferred;
      }
    }
  } catch (err) {
    // Ignore mode inference failures and keep fallback below.
  }

  const rawStage = String(status?.stage || "")
    .trim()
    .toLowerCase();
  if (rawStage === "af2") {
    state.runModeById[runId] = "af2";
    return "af2";
  }
  if (rawStage === "diffdock") {
    state.runModeById[runId] = "diffdock";
    return "diffdock";
  }

  state.runModeById[runId] = "pipeline";
  return "pipeline";
}

function progressModeForStatus(status) {
  const embedded = String(status?._mode || "")
    .trim()
    .toLowerCase();
  if (embedded && PROGRESS_PLANS[embedded]) return embedded;

  const runId = state.currentRunId || "";
  const mapped = runId ? state.runModeById[runId] : "";
  if (mapped && PROGRESS_PLANS[mapped]) return mapped;

  const rawStage = String(status?.stage || "").trim().toLowerCase();
  if (rawStage === "af2") return "af2";
  if (rawStage === "diffdock") return "diffdock";
  return "pipeline";
}

function mapStageToProgressStep(stage, mode) {
  const raw = String(stage || "").trim().toLowerCase();
  if (!raw) return null;
  if (raw === "done") return "done";
  if (raw === "mmseqs_msa") return "msa";
  if (raw === "conservation") return "conservation";
  if (raw === "wt_baseline" || raw === "wt_soluprot" || raw === "wt_af2") return "wt";
  if (raw === "rfd3") return mode === "rfd3" ? "rfd3" : "backbone";
  if (raw === "bioemu") return mode === "bioemu" ? "bioemu" : "backbone";
  if (raw === "af2_target" || raw === "pdb_preprocess" || raw === "query_pdb_check") return "backbone";
  if (raw === "diffdock") return mode === "diffdock" ? "diffdock" : "masking";
  if (raw === "ligand_mask" || raw === "surface_mask" || raw === "mask_consensus") return "masking";
  if (raw === "design" || raw.startsWith("proteinmpnn_")) return "design";
  if (raw === "soluprot" || raw.startsWith("soluprot_")) return "soluprot";
  if (raw === "af2" || raw.startsWith("af2_")) return "af2";
  if (raw === "novelty" || raw.startsWith("novelty_")) return "novelty";
  return null;
}

function parseTierStage(stage) {
  const raw = String(stage || "").trim().toLowerCase();
  const match = raw.match(/^(proteinmpnn|soluprot|af2|novelty)_([0-9]+(?:\.[0-9]+)?)$/);
  if (!match) return null;
  const base = match[1];
  const tierKey = normalizeTierKeyValue(match[2]);
  if (!tierKey) return null;
  if (base === "proteinmpnn") return { step: "design", tierKey };
  return { step: base, tierKey };
}

function computePipelineTierAwareProgress(status, runState, offset, cached) {
  const runId = String(state.currentRunId || "");
  if (!runId) return null;
  const ctx = state.progressContextByRunId[runId];
  if (!ctx || !Array.isArray(ctx.tierKeys) || ctx.tierKeys.length === 0) return null;

  const preSteps = ["msa", "conservation", "backbone", "wt", "masking"];
  const tierSteps = ctx.noveltyEnabled ? ["design", "soluprot", "af2", "novelty"] : ["design", "soluprot", "af2"];
  const totalUnits = preSteps.length + ctx.tierKeys.length * tierSteps.length + 1;
  const currentStep = mapStageToProgressStep(status?.stage, "pipeline");
  const parsedTierStage = parseTierStage(status?.stage);
  if (!currentStep) return null;
  if (String(currentStep) === "done") {
    return {
      percent: 100,
      label: progressStepLabel("done"),
    };
  }

  let unitIndex = null;
  let label = progressStepLabel(currentStep);
  if (preSteps.includes(currentStep)) {
    unitIndex = preSteps.indexOf(currentStep);
  } else if (tierSteps.includes(currentStep)) {
    let tierIndex = parsedTierStage ? ctx.tierKeys.indexOf(parsedTierStage.tierKey) : -1;
    if (tierIndex < 0 && cached && Number.isFinite(cached.tierIndex)) {
      tierIndex = Math.max(0, Math.min(ctx.tierKeys.length - 1, Number(cached.tierIndex)));
    }
    if (tierIndex < 0) tierIndex = 0;
    const subIndex = Math.max(0, tierSteps.indexOf(currentStep));
    unitIndex = preSteps.length + tierIndex * tierSteps.length + subIndex;
    label = `${t("artifacts.filter.tier")} ${tierIndex + 1}/${ctx.tierKeys.length} · ${progressStepLabel(currentStep)}`;
  } else {
    return null;
  }

  let percent = ((unitIndex + offset) / Math.max(1, totalUnits)) * 100;
  if (TERMINAL_RUN_STATES.has(runState) && runState !== "completed") {
    percent = Math.max(percent, ((unitIndex + 0.75) / Math.max(1, totalUnits)) * 100);
  }
  percent = Math.max(1, Math.min(99, percent));
  return {
    percent,
    label,
    tierIndex: parsedTierStage ? ctx.tierKeys.indexOf(parsedTierStage.tierKey) : null,
  };
}

function progressStepLabel(step) {
  if (step === "backbone") return t("monitor.progress.backbone");
  if (step === "wt") return t("monitor.progress.wt");
  if (step === "masking") return t("monitor.progress.masking");
  if (step === "done") return t("monitor.progress.done");
  return formatStageLabel(step);
}

function formatStatusStage(stage) {
  const raw = String(stage || "").trim();
  if (!raw) return "-";
  const lower = raw.toLowerCase();

  const tierMatch = lower.match(/^(proteinmpnn|soluprot|af2|novelty)_([0-9]+(?:\.[0-9]+)?)$/);
  if (tierMatch) {
    const key = tierMatch[1];
    const tier = tierMatch[2];
    const tierLabel = t("artifacts.filter.tier");
    if (key === "proteinmpnn") {
      return `${formatStageLabel("design")} · ${tierLabel} ${tier}`;
    }
    if (key === "soluprot") {
      return `${formatStageLabel("soluprot")} · ${tierLabel} ${tier}`;
    }
    if (key === "af2") {
      return `${formatStageLabel("af2")} · ${tierLabel} ${tier}`;
    }
    if (key === "novelty") {
      return `${formatStageLabel("novelty")} · ${tierLabel} ${tier}`;
    }
  }

  const normalized = formatStageLabel(lower);
  if (normalized && normalized !== lower) return normalized;
  return raw;
}

function parseStatusTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) return NaN;
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const withZone = /[zZ]|[+\-]\d{2}:\d{2}$/.test(normalized) ? normalized : `${normalized}Z`;
  return Date.parse(withZone);
}

function formatEtaMs(ms) {
  if (!Number.isFinite(ms) || ms <= 0) return "0m";
  const totalSec = Math.max(1, Math.round(ms / 1000));
  if (totalSec < 60) return "<1m";
  const min = Math.floor(totalSec / 60);
  const hr = Math.floor(min / 60);
  if (hr > 0) return `${hr}h ${min % 60}m`;
  return `${min}m`;
}

function estimateRunEta(status, percentRounded) {
  const runId = String(state.currentRunId || "");
  const runState = String(status?.state || "").trim().toLowerCase();
  if (!runId) return "-";
  if (runState === "completed" || runState === "done") return "0m";
  if (runState === "failed" || runState === "cancelled" || runState === "error" || runState === "timed_out") {
    return "failed";
  }
  const updatedTs = parseStatusTimestamp(status?.updated_at);
  if (!Number.isFinite(updatedTs) || !Number.isFinite(percentRounded) || percentRounded <= 0 || percentRounded >= 100) {
    return "-";
  }
  const timing = (state.timingByRunId[runId] = state.timingByRunId[runId] || {});
  if (!Number.isFinite(timing.startedAt)) {
    timing.startedAt = updatedTs;
  }
  const elapsed = Math.max(0, updatedTs - timing.startedAt);
  if (elapsed < 5000) return "-";
  const remaining = (elapsed * (100 - percentRounded)) / Math.max(1, percentRounded);
  return formatEtaMs(remaining);
}

function setStateBadge(node, runState) {
  if (!node) return;
  node.classList.add("state-badge");
  node.dataset.state = String(runState || "").toLowerCase();
}

function updateMonitorErrorCards(status) {
  const runState = String(status?.state || "").toLowerCase();
  const detailText = String(status?.detail || "").trim();
  const shouldShow = runState === "failed" || runState === "error" || /^error[:\s]/i.test(detailText);
  const summary = detailText ? detailText.split("\n")[0].slice(0, 220) : "Error";

  const cards = [
    {
      root: el.runErrorDetails,
      summary: el.runErrorSummary,
      raw: el.runErrorRaw,
    },
    {
      root: el.setupErrorDetails,
      summary: el.setupErrorSummary,
      raw: el.setupErrorRaw,
    },
  ];

  cards.forEach((card) => {
    if (!card.root) return;
    card.root.classList.toggle("hidden", !shouldShow);
    if (shouldShow) {
      if (card.summary) card.summary.textContent = summary || "Error";
      if (card.raw) card.raw.textContent = detailText || summary;
    } else {
      if (card.raw) card.raw.textContent = "";
    }
  });
}

function renderRunProgress(status) {
  if (!el.runProgressFill || !el.runProgressPercent || !el.runProgressLabel || !el.runProgressStages) return;

  const mode = progressModeForStatus(status);
  const runId = String(state.currentRunId || "");
  let steps = PROGRESS_PLANS[mode] || PROGRESS_PLANS.pipeline;
  if (mode === "pipeline" || mode === "workflow") {
    const ctx = state.progressContextByRunId[runId];
    if (ctx && ctx.noveltyEnabled === false) {
      steps = steps.filter((step) => step !== "novelty");
    }
  }
  const runState = String(status?.state || "").trim().toLowerCase();
  const currentStep = mapStageToProgressStep(status?.stage, mode);

  const cached = runId ? state.progressByRunId[runId] : null;
  let stepIndex = currentStep ? steps.indexOf(currentStep) : -1;
  if (stepIndex < 0 && cached && cached.mode === mode && Number.isFinite(cached.index)) {
    stepIndex = cached.index;
  }
  if (stepIndex < 0) stepIndex = 0;

  let percent = 0;
  let labelOverride = "";
  let tierIndexForCache = null;
  if (currentStep === "done") {
    percent = 100;
    stepIndex = steps.length - 1;
  } else {
    const base = Math.max(0, stepIndex);
    const offset =
      runState === "running" ? 0.45 : runState === "completed" ? 1.0 : runState === "failed" ? 0.2 : 0.1;
    const tierAware =
      mode === "pipeline" || mode === "workflow"
        ? computePipelineTierAwareProgress(status, runState, offset, cached)
        : null;
    if (tierAware && Number.isFinite(tierAware.percent)) {
      percent = Number(tierAware.percent);
      labelOverride = String(tierAware.label || "");
      if (Number.isFinite(tierAware.tierIndex) && Number(tierAware.tierIndex) >= 0) {
        tierIndexForCache = Number(tierAware.tierIndex);
      }
    } else {
      percent = ((base + offset) / Math.max(1, steps.length)) * 100;
      if (TERMINAL_RUN_STATES.has(runState) && runState !== "completed") {
        percent = Math.max(percent, ((base + 0.75) / Math.max(1, steps.length)) * 100);
      }
      percent = Math.max(1, Math.min(99, percent));
    }
  }

  const rounded = Math.max(0, Math.min(100, Math.round(percent)));
  el.runProgressFill.style.width = `${rounded}%`;
  el.runProgressPercent.textContent = `${rounded}%`;
  el.runProgressLabel.textContent = labelOverride || progressStepLabel(steps[Math.min(stepIndex, steps.length - 1)]);

  el.runProgressStages.innerHTML = steps
    .map((step, index) => {
      let cls = "";
      if (index < stepIndex) cls = "done";
      else if (index === stepIndex) cls = runState === "failed" || runState === "error" ? "failed" : "current";
      return `<span class="progress-stage ${cls}">${escapeHtml(progressStepLabel(step))}</span>`;
    })
    .join("");

  if (runId) {
    const payload = { mode, index: stepIndex, percent: rounded };
    if (tierIndexForCache !== null) payload.tierIndex = tierIndexForCache;
    state.progressByRunId[runId] = payload;
  }
  return rounded;
}

function resetRunProgress() {
  if (el.runDetailValue) el.runDetailValue.textContent = "-";
  if (el.runProgressFill) el.runProgressFill.style.width = "0%";
  if (el.runProgressPercent) el.runProgressPercent.textContent = "0%";
  if (el.runProgressLabel) el.runProgressLabel.textContent = "-";
  if (el.runProgressStages) el.runProgressStages.innerHTML = "";
}

function updateRunInfo(status) {
  if (!status) return;
  const rawStage = String(status.stage || "").trim();
  const stageDisplay = formatStatusStage(rawStage);
  el.runStageValue.textContent = stageDisplay || "-";
  el.runStateValue.textContent = status.state || "-";
  el.runUpdatedValue.textContent = status.updated_at || "-";
  if (el.runDetailValue) {
    const detailText = status.detail !== undefined && status.detail !== null ? String(status.detail) : "";
    el.runDetailValue.textContent = detailText.trim() ? detailText : "-";
  }
  const runState = String(status.state || "").toLowerCase();
  setStateBadge(el.runStateValue, runState);

  state.lastRunStatus = status;
  const percent = renderRunProgress(status);
  const etaText = estimateRunEta(status, percent);

  if (el.setupContextStageValue) el.setupContextStageValue.textContent = stageDisplay || "-";
  if (el.setupContextStateValue) {
    el.setupContextStateValue.textContent = status.state || "-";
    setStateBadge(el.setupContextStateValue, runState);
  }
  if (el.analyzeContextStageValue) el.analyzeContextStageValue.textContent = stageDisplay || "-";
  if (el.analyzeContextStateValue) {
    el.analyzeContextStateValue.textContent = status.state || "-";
    setStateBadge(el.analyzeContextStateValue, runState);
  }

  if (el.setupRunIdValue) el.setupRunIdValue.textContent = state.currentRunId || "-";
  if (el.setupRunStageValue) el.setupRunStageValue.textContent = stageDisplay || "-";
  if (el.setupRunStateValue) {
    el.setupRunStateValue.textContent = status.state || "-";
    setStateBadge(el.setupRunStateValue, runState);
  }
  if (el.setupRunUpdatedValue) el.setupRunUpdatedValue.textContent = status.updated_at || "-";
  if (el.setupRunEtaValue) el.setupRunEtaValue.textContent = etaText;

  updateMonitorErrorCards(status);
  state.currentRunState = String(status.state || "").toLowerCase();
  const statusRunId = String(status.run_id || state.currentRunId || "").trim();
  const completed = state.currentRunState === "completed" || state.currentRunState === "done";
  if (statusRunId && completed && state.autoAnalyzePendingByRunId[statusRunId]) {
    const workflowPlan = workflowPlanForRunId(statusRunId);
    const workflowStop = normalizePipelineStage(state.progressContextByRunId?.[statusRunId]?.stopAfter, "");
    const checkpointTarget = normalizePipelineStage(workflowPlan?.nextCheckpointStage || "", "");
    const waitingCheckpoint =
      workflowPlan &&
      workflowPlan.checkpointEnabled &&
      checkpointTarget &&
      workflowStop === checkpointTarget &&
      normalizePipelineStage(workflowPlan.finalStopAfter, "") !== workflowStop;
    state.autoAnalyzePendingByRunId[statusRunId] = false;
    if (!waitingCheckpoint) {
      setActiveTab("analyze");
    }
  }
  if (statusRunId && (state.currentRunState === "failed" || state.currentRunState === "cancelled")) {
    state.autoAnalyzePendingByRunId[statusRunId] = false;
  }
  updateInlineStatus(status);
  updateRunEligibility(state.plan?.questions || []);
  updateMonitorActionButtons();
  renderWorkflowReviewPanel(status);
  renderCopilotContext();
}

function updateInlineStatus(status, runId = state.currentRunId) {
  if (!el.runInlineStatus) return;
  if (!runId) {
    el.runInlineStatus.textContent = t("setup.runStatus.empty");
    el.runInlineStatus.dataset.state = "";
    return;
  }
  const stage = status?.stage || "-";
  const stateText = status?.state || "-";
  const updated = status?.updated_at || "-";
  el.runInlineStatus.textContent = t("setup.runStatus.line", {
    id: runId,
    stage,
    state: stateText,
    updated,
  });
  el.runInlineStatus.dataset.state = String(stateText || "").toLowerCase();
}

function setCurrentRunId(runId) {
  state.currentRunId = runId;
  state.currentRunState = "";
  state.lastRunStatus = null;
  state.lastStatusKey = "";
  state.feedbackCount = 0;
  state.experimentCount = 0;
  state.artifacts = [];
  state.artifactMetaByPath = {};
  state.artifactComparison = null;
  state.artifactComparisonRunId = "";
  state.monitorNeedsReport = false;
  state.monitorCompleteness = null;
  state.analyzeArtifactPath = "";
  state.artifactCompareLeftPath = "";
  state.artifactCompareRightPath = "";
  state.runCompareResult = null;
  state.hitListResult = null;
  state.hitListRows = [];
  if (runId && !state.timingByRunId[runId]) state.timingByRunId[runId] = {};
  el.runIdValue.textContent = runId || "-";
  el.runStageValue.textContent = "-";
  el.runStateValue.textContent = "-";
  el.runUpdatedValue.textContent = "-";
  if (el.setupContextStageValue) el.setupContextStageValue.textContent = "-";
  if (el.setupContextStateValue) {
    el.setupContextStateValue.textContent = "-";
    setStateBadge(el.setupContextStateValue, "");
  }
  if (el.analyzeContextStageValue) el.analyzeContextStageValue.textContent = "-";
  if (el.analyzeContextStateValue) {
    el.analyzeContextStateValue.textContent = "-";
    setStateBadge(el.analyzeContextStateValue, "");
  }
  if (el.setupRunIdValue) el.setupRunIdValue.textContent = runId || "-";
  if (el.setupRunStageValue) el.setupRunStageValue.textContent = "-";
  if (el.setupRunStateValue) {
    el.setupRunStateValue.textContent = "-";
    setStateBadge(el.setupRunStateValue, "");
  }
  if (el.setupRunUpdatedValue) el.setupRunUpdatedValue.textContent = "-";
  if (el.setupRunEtaValue) el.setupRunEtaValue.textContent = "-";
  updateRunLabel();
  updateMonitorErrorCards(null);
  updateAnalyzeSummary();
  resetRunProgress();
  updateInlineStatus(null, runId);
  updateRunEligibility(state.plan?.questions || []);
  updateMonitorActionButtons();
  renderAllArtifactViews(state.artifacts);
  refreshArtifactSelects();
  renderArtifactComparisonSummary(null);
  renderMonitorCompleteness(null, null);
  renderRunCompareSummary(null);
  renderHitList();
  populateRunCompareBaselineOptions();
  updateHitCutoffLabel();
  setHitWeightInputValues();
  setFilePreviewPlaceholder("monitor");
  setFilePreviewPlaceholder("analyze", "analyze.files.placeholder");
  setComparePreviewPlaceholder("artifacts.preview.placeholder");
  updateMonitorReportActions();
  renderWorkflowReviewPanel(null);
  renderCopilotContext();
  if (state.runs) renderRuns(state.runs);
  refreshAgentPanel();
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
    void pollCurrentRun({ includeArtifacts: "auto" });
  }, 5000);
  void pollCurrentRun({ includeArtifacts: "auto" });
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function artifactRefreshStatusKeyForRun(runId = state.currentRunId) {
  const key = String(runId || "").trim();
  if (!key) return "";
  const status =
    state.lastRunStatus &&
    typeof state.lastRunStatus === "object" &&
    String(state.lastRunStatus.run_id || "").trim() === key
      ? state.lastRunStatus
      : null;
  const stage = String(status?.stage || "-").trim() || "-";
  const runState = String(status?.state || state.currentRunState || "-").trim() || "-";
  const updated = String(status?.updated_at || "-").trim() || "-";
  return `${key}|${stage}|${runState}|${updated}`;
}

function markArtifactsRefreshed(runId = state.currentRunId) {
  const key = String(runId || "").trim();
  if (!key) return;
  state.artifactRefreshAtByRunId[key] = Date.now();
  state.artifactRefreshStatusKeyByRunId[key] = artifactRefreshStatusKeyForRun(key);
}

function isTerminalRunState(stateText = currentRunStateText()) {
  const normalized = String(stateText || "")
    .trim()
    .toLowerCase();
  return ["completed", "done", "failed", "error", "cancelled", "canceled", "stopped"].includes(normalized);
}

function shouldAutoRefreshArtifacts(runId = state.currentRunId) {
  const key = String(runId || "").trim();
  if (!key) return false;
  if (activeTabId() !== "monitor") return false;
  if (!Array.isArray(state.artifacts) || state.artifacts.length === 0) return true;
  const currentStatusKey = artifactRefreshStatusKeyForRun(key);
  const previousStatusKey = String(state.artifactRefreshStatusKeyByRunId?.[key] || "");
  if (currentStatusKey && currentStatusKey !== previousStatusKey) return true;
  const lastRefreshAt = Number(state.artifactRefreshAtByRunId?.[key] || 0);
  if (!isTerminalRunState() && Date.now() - lastRefreshAt >= 15000) return true;
  return false;
}

async function pollCurrentRun({ includeArtifacts = "auto" } = {}) {
  const runId = String(state.currentRunId || "").trim();
  if (!runId) return;
  if (state.pollCyclePromise) return state.pollCyclePromise;
  state.pollCyclePromise = (async () => {
    await pollStatus(runId);
    await refreshAgentPanel();
    const shouldRefresh =
      includeArtifacts === true || (includeArtifacts === "auto" && shouldAutoRefreshArtifacts(runId));
    if (shouldRefresh) {
      await refreshArtifacts({ runId });
    }
  })()
    .catch((err) => {
      setMessage(t("status.error", { error: err.message }), "ai");
    })
    .finally(() => {
      state.pollCyclePromise = null;
    });
  return state.pollCyclePromise;
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
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = payload && typeof payload.error === "string" ? payload.error : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  if (!payload || typeof payload !== "object") {
    throw new Error(t("error.api"));
  }
  if (!payload.ok) {
    throw new Error(payload.error || t("error.api"));
  }
  return payload.result;
}

async function authLogin() {
  const username = el.loginUsername.value.trim();
  const password = el.loginPassword.value.trim();
  el.loginError.textContent = "";
  if (!username || !password) {
    el.loginError.textContent = t("auth.required");
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
      throw new Error(payload.error || t("auth.loginFailed"));
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
      throw new Error(payload.error || t("auth.sessionInvalid"));
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
  setMessage(t("run.reset"), "ai");
}

const PROTEIN_RESNAMES = new Set([
  "ALA",
  "ARG",
  "ASN",
  "ASP",
  "CYS",
  "GLN",
  "GLU",
  "GLY",
  "HIS",
  "ILE",
  "LEU",
  "LYS",
  "MET",
  "PHE",
  "PRO",
  "SER",
  "THR",
  "TRP",
  "TYR",
  "VAL",
  "ASX",
  "GLX",
  "XLE",
  "UNK",
  "MSE",
  "SEC",
  "PYL",
  "SEP",
  "TPO",
  "PTR",
  "HYP",
  "HID",
  "HIE",
  "HIP",
  "CYX",
]);

function normalizeChainId(chainId) {
  const clean = String(chainId || "").trim();
  return clean || "_";
}

function denormalizeChainId(chainId) {
  return String(chainId || "") === "_" ? "" : String(chainId || "");
}

function isProteinAtomLine(line) {
  if (line.startsWith("ATOM")) return true;
  if (!line.startsWith("HETATM")) return false;
  const resname = line.slice(17, 20).trim().toUpperCase();
  return PROTEIN_RESNAMES.has(resname);
}

function parsePdbChainRanges(pdbText) {
  const ranges = {};
  const lines = String(pdbText || "").split(/\r?\n/);
  for (const line of lines) {
    if (!isProteinAtomLine(line)) continue;
    const chainId = normalizeChainId(line[21] || "");
    const resSeq = parseInt(line.slice(22, 26).trim(), 10);
    if (!Number.isFinite(resSeq)) continue;
    const entry = ranges[chainId] || { min: resSeq, max: resSeq, minPos: null, maxPos: null };
    entry.min = Math.min(entry.min, resSeq);
    entry.max = Math.max(entry.max, resSeq);
    if (resSeq > 0) {
      entry.minPos = entry.minPos === null ? resSeq : Math.min(entry.minPos, resSeq);
      entry.maxPos = entry.maxPos === null ? resSeq : Math.max(entry.maxPos, resSeq);
    }
    ranges[chainId] = entry;
  }
  const normalized = {};
  Object.entries(ranges).forEach(([chainId, entry]) => {
    if (entry.minPos !== null && entry.maxPos !== null) {
      normalized[chainId] = { min: entry.minPos, max: entry.maxPos };
    }
  });
  return Object.keys(normalized).length ? normalized : null;
}

function parsePdbResidueOrderByChain(pdbText) {
  const orderByChain = {};
  const seenByChain = {};
  const lines = String(pdbText || "").split(/\r?\n/);
  for (const line of lines) {
    if (!isProteinAtomLine(line)) continue;
    const chainId = normalizeChainId(line[21] || "");
    const resSeq = parseInt(line.slice(22, 26).trim(), 10);
    if (!Number.isFinite(resSeq) || resSeq <= 0) continue;
    if (!seenByChain[chainId]) seenByChain[chainId] = new Set();
    const seen = seenByChain[chainId];
    if (seen.has(resSeq)) continue;
    seen.add(resSeq);
    if (!orderByChain[chainId]) orderByChain[chainId] = [];
    orderByChain[chainId].push(resSeq);
  }
  return orderByChain;
}

function normalizeResidueSelectionMap(raw) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;
  Object.entries(raw).forEach(([chain, values]) => {
    const nums = (Array.isArray(values) ? values : [values])
      .map((v) => Number.parseInt(v, 10))
      .filter((v) => Number.isFinite(v) && v > 0);
    if (nums.length) {
      out[normalizeChainId(chain)] = Array.from(new Set(nums)).sort((a, b) => a - b);
    }
  });
  return out;
}

function countSelectedResidues(selectionMap) {
  return Object.values(selectionMap || {}).reduce(
    (acc, list) => acc + (Array.isArray(list) ? list.length : 0),
    0
  );
}

function selectionSummaryText(selectionMap) {
  const parts = [];
  Object.entries(selectionMap || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .forEach(([chain, values]) => {
      if (!Array.isArray(values) || values.length === 0) return;
      const preview = values.slice(0, 8).join(",");
      const suffix = values.length > 8 ? `,+${values.length - 8}` : "";
      parts.push(`${chain}:${preview}${suffix}`);
    });
  return parts.join("; ");
}

function filterSelectionByResidueOrder(selectionMap, orderByChain) {
  const normalized = normalizeResidueSelectionMap(selectionMap);
  const filtered = {};
  Object.entries(normalized).forEach(([chain, values]) => {
    const allowed = new Set((orderByChain && orderByChain[chain]) || []);
    const kept = values.filter((v) => allowed.has(v));
    if (kept.length) filtered[chain] = kept;
  });
  return filtered;
}

function resetSetupResiduePicker() {
  state.setupResiduePicker = createSetupResiduePickerState();
}

function setSetupResiduePickerStructure(pdbText, { sourceLabel = "", sourceKey = "" } = {}) {
  const text = String(pdbText || "").trim();
  if (!text) return false;
  const residueOrderByChain = parsePdbResidueOrderByChain(text);
  if (!Object.keys(residueOrderByChain).length) return false;
  const nextSelection = filterSelectionByResidueOrder(state.setupResiduePicker.selection, residueOrderByChain);
  state.setupResiduePicker = {
    pdbText: text,
    sourceLabel,
    sourceKey,
    selection: nextSelection,
    residueOrderByChain,
    notice: "",
    runningAf2: false,
  };
  return true;
}

function normalizeFixedPositionsValue(raw) {
  if (raw === null || raw === undefined || raw === "") return {};
  let parsed = raw;
  if (typeof raw === "string") {
    const out = parseFixedPositionsExtra(raw);
    if (out.error) return {};
    parsed = out.value;
  }
  if (Array.isArray(parsed)) {
    const nums = parsed
      .map((v) => Number.parseInt(v, 10))
      .filter((v) => Number.isFinite(v) && v > 0);
    return nums.length ? { "*": Array.from(new Set(nums)).sort((a, b) => a - b) } : {};
  }
  if (!parsed || typeof parsed !== "object") return {};
  const out = {};
  Object.entries(parsed).forEach(([chain, values]) => {
    const nums = (Array.isArray(values) ? values : [values])
      .map((v) => Number.parseInt(v, 10))
      .filter((v) => Number.isFinite(v) && v > 0);
    if (nums.length) out[String(chain)] = Array.from(new Set(nums)).sort((a, b) => a - b);
  });
  return out;
}

function mergeFixedPositionsMap(baseMap, addMap) {
  const merged = normalizeFixedPositionsValue(baseMap);
  Object.entries(normalizeFixedPositionsValue(addMap)).forEach(([chain, values]) => {
    const next = new Set((merged[chain] || []).map((v) => Number.parseInt(v, 10)));
    values.forEach((v) => next.add(v));
    const sorted = Array.from(next).filter((v) => Number.isFinite(v) && v > 0).sort((a, b) => a - b);
    if (sorted.length) merged[chain] = sorted;
  });
  return merged;
}

function selectedResiduesToQueryPositions(selectionMap, residueOrderByChain) {
  const out = {};
  Object.entries(normalizeResidueSelectionMap(selectionMap)).forEach(([chain, values]) => {
    const order = Array.isArray(residueOrderByChain?.[chain]) ? residueOrderByChain[chain] : [];
    if (!order.length) return;
    const orderIndex = new Map(order.map((resi, idx) => [resi, idx + 1]));
    const mapped = values
      .map((resi) => orderIndex.get(resi))
      .filter((idx) => Number.isFinite(idx) && idx > 0);
    if (mapped.length) {
      out[chain] = Array.from(new Set(mapped)).sort((a, b) => a - b);
    }
  });
  return out;
}

function getTargetInputPdbText() {
  const explicit = String(state.answers.target_pdb || "").trim();
  if (explicit) return explicit;
  const text = String(state.answers.target_input || "").trim();
  if (!text) return "";
  return detectTargetKey(text) === "target_pdb" ? text : "";
}

function getTargetInputFastaText() {
  const explicit = String(state.answers.target_fasta || "").trim();
  if (explicit) return explicit;
  const text = String(state.answers.target_input || "").trim();
  if (!text) return "";
  return detectTargetKey(text) === "target_fasta" ? text : "";
}

function getRfd3InputPdbText() {
  return String(state.answers.rfd3_input_pdb || "").trim();
}

function refreshChainRangesFromAnswers() {
  const rfd3Text = getRfd3InputPdbText();
  if (rfd3Text) {
    updateChainRangesFromText(rfd3Text);
    return;
  }
  const targetPdbText = getTargetInputPdbText();
  if (targetPdbText) {
    updateChainRangesFromText(targetPdbText);
    return;
  }
  state.chainRanges = null;
}

function updateChainRangesFromText(text) {
  const ranges = parsePdbChainRanges(text);
  state.chainRanges = ranges;
}

function isAnswerMissing(value) {
  if (Array.isArray(value)) return value.length === 0;
  if (value === null || value === undefined) return true;
  return String(value).trim() === "";
}

function normalizeQuestion(q) {
  if (!q || !q.id) return q;
  const preset = QUESTION_PRESETS[q.id];
  if (!preset) return q;
  const merged = { ...preset, ...q };
  if (merged.required === undefined) merged.required = Boolean(preset.required);
  return merged;
}

function formatAnswerValue(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function splitAnswerList(raw) {
  return String(raw || "")
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function parseFixedPositionsExtra(raw) {
  const text = String(raw || "").trim();
  if (!text) return { value: "", error: "" };
  if (text.startsWith("{") || text.startsWith("[")) {
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed === "object") {
        return { value: parsed, error: "" };
      }
      return { value: "", error: "fixed_positions_extra must be JSON object/list." };
    } catch (err) {
      return { value: "", error: "fixed_positions_extra JSON parse failed." };
    }
  }

  if (text.includes(":")) {
    const out = {};
    const segments = text.split(/[;\n]+/).map((seg) => seg.trim()).filter(Boolean);
    segments.forEach((seg) => {
      if (!seg.includes(":")) return;
      const parts = seg.split(":");
      const chain = (parts.shift() || "").trim();
      if (!chain) return;
      const nums = splitAnswerList(parts.join(":"))
        .map((v) => Number.parseInt(v, 10))
        .filter((v) => Number.isFinite(v) && v > 0);
      if (nums.length) out[chain] = nums;
    });
    if (Object.keys(out).length) return { value: out, error: "" };
    return { value: "", error: "fixed_positions_extra chain list is empty." };
  }

  const nums = splitAnswerList(text)
    .map((v) => Number.parseInt(v, 10))
    .filter((v) => Number.isFinite(v) && v > 0);
  if (nums.length) return { value: nums, error: "" };
  return { value: "", error: "fixed_positions_extra expects numbers or JSON." };
}

function parseAnswerValue(id, raw) {
  const text = String(raw ?? "").trim();
  if (!text) return { value: "", error: "" };

  if (ANSWER_JSON_KEYS.has(id)) {
    if (id === "fixed_positions_extra") {
      return parseFixedPositionsExtra(text);
    }
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed === "object") return { value: parsed, error: "" };
      return { value: "", error: `${id} must be a JSON object.` };
    } catch (err) {
      return { value: "", error: `${id} JSON parse failed.` };
    }
  }

  if (ANSWER_BOOL_KEYS.has(id)) {
    const v = text.toLowerCase();
    if (["1", "true", "yes", "y", "on"].includes(v)) return { value: true, error: "" };
    if (["0", "false", "no", "n", "off"].includes(v)) return { value: false, error: "" };
    return { value: "", error: `${id} expects true/false.` };
  }

  if (ANSWER_INT_KEYS.has(id)) {
    const n = Number.parseInt(text, 10);
    if (Number.isFinite(n)) return { value: n, error: "" };
    return { value: "", error: `${id} expects an integer.` };
  }

  if (ANSWER_FLOAT_KEYS.has(id)) {
    const n = Number.parseFloat(text);
    if (!Number.isFinite(n)) return { value: "", error: `${id} expects a number.` };
    if (id === "af2_plddt_cutoff" && (n < 0 || n > 100)) {
      return { value: "", error: "af2_plddt_cutoff must be between 0 and 100." };
    }
    if (id === "af2_rmsd_cutoff" && n <= 0) {
      return { value: "", error: "af2_rmsd_cutoff must be greater than 0." };
    }
    return { value: n, error: "" };
  }

  if (ANSWER_FLOAT_LIST_KEYS.has(id)) {
    let items = [];
    if (text.startsWith("[")) {
      try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed)) {
          items = parsed.map((v) => Number.parseFloat(v)).filter((v) => Number.isFinite(v));
        }
      } catch (err) {
        return { value: "", error: `${id} JSON parse failed.` };
      }
    } else {
      items = splitAnswerList(text)
        .map((v) => Number.parseFloat(v))
        .filter((v) => Number.isFinite(v));
    }
    if (items.length) return { value: items, error: "" };
    return { value: "", error: `${id} expects a list of numbers.` };
  }

  if (ANSWER_LIST_KEYS.has(id)) {
    let items = [];
    if (text.startsWith("[")) {
      try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed)) {
          items = parsed.map((v) => String(v)).filter((v) => v.length > 0);
        }
      } catch (err) {
        return { value: "", error: `${id} JSON parse failed.` };
      }
    } else {
      items = splitAnswerList(text);
    }
    if (items.length) return { value: items, error: "" };
    return { value: "", error: `${id} expects a list.` };
  }

  return { value: text, error: "" };
}

function renderChoiceButtons(container, options, currentValue, onSelect, { multi = false, rerender = true } = {}) {
  const group = document.createElement("div");
  group.className = "choice-group";
  const buttons = [];
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice-btn";
    const isSelected = multi
      ? Array.isArray(currentValue) && currentValue.includes(opt.value)
      : currentValue === opt.value;
    if (isSelected) btn.classList.add("selected");
    btn.textContent = labelFor(opt);
    btn.addEventListener("click", () => {
      onSelect(opt.value);
      if (!rerender) {
        if (multi) {
          btn.classList.toggle("selected");
        } else {
          buttons.forEach((node) => node.classList.remove("selected"));
          btn.classList.add("selected");
        }
        return;
      }
      renderQuestions(state.plan?.questions || []);
    });
    group.appendChild(btn);
    buttons.push(btn);
  });
  container.appendChild(group);
}

function renderQuestions(questions) {
  const inputStack = el.questionInputStack || el.questionStack;
  const configStack = el.questionConfigStack || el.questionStack;
  if (configStack) {
    configStack.classList.toggle("workflow-layout", state.runMode === "workflow");
  }
  const stacks = new Set([el.questionStack, el.questionInputStack, el.questionConfigStack].filter(Boolean));
  stacks.forEach((node) => {
    node.innerHTML = "";
  });
  const appendInputCard = (card) => {
    if (inputStack) inputStack.appendChild(card);
  };
  const appendConfigCard = (card) => {
    if (configStack) configStack.appendChild(card);
  };

  if (!questions.length) {
    if (el.setupStepper) el.setupStepper.classList.add("hidden");
    el.runBtn.disabled = false;
    el.runHint.textContent = t("hint.none");
    return;
  }

  const normalizedQuestions = (questions || [])
    .map((q) => normalizeQuestion(q))
    .filter(Boolean);
  const visibleQuestions = renderSetupWizard(normalizedQuestions);
  if (state.runMode === "pipeline") {
    if (!normalizePipelineStage(state.answers.start_from, "")) {
      state.answers.start_from = "msa";
    }
    syncStartStopStages();
  }

  const fileQuestionIds = new Set([
    "target_input",
    "target_pdb",
    "target_fasta",
    "rfd3_input_pdb",
    "diffdock_ligand",
  ]);

  const choiceQuestionIds = new Set([
    "run_mode",
    "start_from",
    "stop_after",
    "design_chains",
    "rfd3_contig",
    "pdb_strip_nonpositive_resseq",
    "wt_compare",
    "mask_consensus_apply",
    "ligand_mask_use_original_target",
    "bioemu_use",
    "novelty_enabled",
    "af2_provider",
    "confirm_run",
  ]);

  const isFileQuestion = (q) => q && fileQuestionIds.has(q.id);
  const isChoiceQuestion = (q) => q && choiceQuestionIds.has(q.id);
  const fileQuestions = [];
  const choiceQuestions = [];
  const textQuestions = [];

  visibleQuestions.forEach((q) => {
    if (isFileQuestion(q)) {
      fileQuestions.push(q);
    } else if (isChoiceQuestion(q)) {
      choiceQuestions.push(q);
    } else {
      textQuestions.push(q);
    }
  });

  const compactChoiceQuestionIds = new Set([
    "novelty_enabled",
    "bioemu_use",
    "af2_provider",
    "design_chains",
    "pdb_strip_nonpositive_resseq",
    "wt_compare",
    "mask_consensus_apply",
    "ligand_mask_use_original_target",
  ]);

  const buildQuestionCardClass = (q, extraClasses = []) => {
    const classes = ["question-card"];
    const rawId = String(q?.id || "").trim();
    if (rawId) {
      const safeId = rawId.replace(/[^a-z0-9_-]+/gi, "-");
      if (safeId) classes.push(`question-${safeId}`);
    }
    if (q?.required) classes.push("required");
    if (Array.isArray(extraClasses)) {
      extraClasses.forEach((name) => {
        if (name) classes.push(name);
      });
    }
    return classes.join(" ");
  };

  choiceQuestions.forEach((q) => {
    if (compactChoiceQuestionIds.has(q.id)) return;
    const card = document.createElement("div");
    card.className = buildQuestionCardClass(q, q.id === "run_mode" ? ["run-mode-card"] : []);

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = q.labelKey ? t(q.labelKey) : q.label || q.id || "input";

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = q.questionKey ? t(q.questionKey) : q.question || "";

    card.appendChild(title);
    card.appendChild(help);

    if (q.id === "run_mode") {
      const current = state.runMode || q.default || "pipeline";
      renderChoiceButtons(card, RUN_MODE_OPTIONS, current, (value) => {
        setRunMode(value, { render: false });
        updateRunEligibility(normalizedQuestions);
      });
      const detail = document.createElement("div");
      detail.className = "question-summary";
      detail.textContent = t("question.runMode.detail");
      card.appendChild(detail);
      const modeGuide = document.createElement("div");
      modeGuide.className = "mode-guide";
      const modeGuideTitle = document.createElement("div");
      modeGuideTitle.className = "mode-guide-title";
      modeGuideTitle.textContent = t("setup.modeGuide.title");
      modeGuide.appendChild(modeGuideTitle);
      const selectedOpt =
        RUN_MODE_OPTIONS.find((opt) => String(opt.value || "").trim() === current) || RUN_MODE_OPTIONS[0];
      if (selectedOpt) {
        const mode = String(selectedOpt.value || "").trim();
        const item = document.createElement("div");
        item.className = "mode-guide-item selected";
        const label = document.createElement("div");
        label.className = "mode-guide-label";
        label.textContent = labelFor(selectedOpt);
        const desc = document.createElement("div");
        desc.className = "mode-guide-desc";
        desc.textContent = t(`setup.modeGuide.${mode}`);
        item.appendChild(label);
        item.appendChild(desc);
        modeGuide.appendChild(item);
      }
      card.appendChild(modeGuide);
    }

    if (q.id === "start_from") {
      const routedDefault = state.plan?.routed_request?.start_from;
      const current = normalizePipelineStage(
        state.answers.start_from || routedDefault || q.default || "msa",
        "msa"
      );
      state.answers.start_from = current;
      renderChoiceButtons(
        card,
        [
          { labelKey: "stage.msa", value: "msa" },
          { labelKey: "stage.rfd3", value: "rfd3" },
          { labelKey: "stage.bioemu", value: "bioemu" },
          { labelKey: "stage.design", value: "design" },
          { labelKey: "stage.soluprot", value: "soluprot" },
          { labelKey: "stage.af2", value: "af2" },
          { labelKey: "stop.full", value: "novelty" },
        ],
        current,
        (value) => {
          state.answers.start_from = normalizePipelineStage(value, "msa");
          syncStartStopStages();
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "stop_after") {
      const routedDefault = state.plan?.routed_request?.stop_after;
      const current = normalizePipelineStage(
        state.answers.stop_after || routedDefault || q.default || "novelty",
        "novelty"
      );
      state.answers.stop_after = current;
      renderChoiceButtons(
        card,
        [
          { labelKey: "stage.msa", value: "msa" },
          { labelKey: "stage.rfd3", value: "rfd3" },
          { labelKey: "stage.bioemu", value: "bioemu" },
          { labelKey: "stage.design", value: "design" },
          { labelKey: "stage.soluprot", value: "soluprot" },
          { labelKey: "stage.af2", value: "af2" },
          { labelKey: "stop.full", value: "novelty" },
        ],
        current,
        (value) => {
          const selectedStop = normalizePipelineStage(value, "novelty");
          state.answers.stop_after = selectedStop;
          syncStartStopStages();
          if (selectedStop === "bioemu") {
            state.answers.bioemu_use = true;
          }
          state.answers.novelty_enabled = selectedStop === "novelty";
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "af2_provider") {
      const routedDefault = state.plan?.routed_request?.af2_provider;
      const current = String(state.answers.af2_provider || routedDefault || q.default || "colabfold")
        .trim()
        .toLowerCase();
      state.answers.af2_provider = normalizeAf2Provider(current);
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.af2Provider.colabfold", value: "colabfold" },
          { labelKey: "choice.af2Provider.af2", value: "af2" },
        ],
        state.answers.af2_provider,
        (value) => {
          state.answers.af2_provider = normalizeAf2Provider(value);
          refreshAf2ProviderLabels({ rerenderQuestions: true });
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "design_chains") {
      const chains = state.chainRanges ? Object.keys(state.chainRanges) : [];
      let current = Array.isArray(state.answers.design_chains) ? state.answers.design_chains : [];
      const routedDefault = state.plan?.routed_request?.design_chains;
      if (!current.length && Array.isArray(routedDefault) && routedDefault.length) {
        current = routedDefault;
        state.answers.design_chains = current;
      }
      const group = document.createElement("div");
      group.className = "choice-group";

      const allBtn = document.createElement("button");
      allBtn.type = "button";
      allBtn.className = "choice-btn" + (current.length === 0 ? " selected" : "");
      allBtn.textContent = t("choice.allChains");
      allBtn.addEventListener("click", () => {
        state.answers.design_chains = [];
        updateRunEligibility(normalizedQuestions);
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
          updateRunEligibility(normalizedQuestions);
          renderQuestions(state.plan?.questions || []);
        });
        group.appendChild(btn);
      });

      card.appendChild(group);

      if (chains.length) {
        const note = document.createElement("div");
        note.className = "choice-note";
        note.textContent = t("choice.chainDefaultNote");
        card.appendChild(note);
      } else {
        const note = document.createElement("div");
        note.className = "choice-note";
        note.textContent = t("choice.chainNote");
        card.appendChild(note);
      }
    }

    if (q.id === "pdb_strip_nonpositive_resseq") {
      let current = state.answers.pdb_strip_nonpositive_resseq;
      if (typeof current !== "boolean") {
        const routedDefault = state.plan?.routed_request?.pdb_strip_nonpositive_resseq;
        if (typeof routedDefault === "boolean") {
          current = routedDefault;
        } else {
          current = q.default !== undefined ? Boolean(q.default) : true;
        }
        state.answers.pdb_strip_nonpositive_resseq = current;
      }
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.stripNonpositive.on", value: true },
          { labelKey: "choice.stripNonpositive.off", value: false },
        ],
        current,
        (value) => {
          state.answers.pdb_strip_nonpositive_resseq = value;
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "wt_compare") {
      let current = state.answers.wt_compare;
      if (typeof current !== "boolean") {
        const routedDefault = state.plan?.routed_request?.wt_compare;
        if (typeof routedDefault === "boolean") {
          current = routedDefault;
        } else {
          current = q.default !== undefined ? Boolean(q.default) : true;
        }
        state.answers.wt_compare = current;
      }
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.wtCompare.on", value: true },
          { labelKey: "choice.wtCompare.off", value: false },
        ],
        current,
        (value) => {
          state.answers.wt_compare = value;
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "mask_consensus_apply") {
      let current = state.answers.mask_consensus_apply;
      if (typeof current !== "boolean") {
        const routedDefault = state.plan?.routed_request?.mask_consensus_apply;
        if (typeof routedDefault === "boolean") {
          current = routedDefault;
        } else {
          current = q.default !== undefined ? Boolean(q.default) : true;
        }
        state.answers.mask_consensus_apply = current;
      }
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.maskConsensusApply.on", value: true },
          { labelKey: "choice.maskConsensusApply.off", value: false },
        ],
        current,
        (value) => {
          state.answers.mask_consensus_apply = value;
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "ligand_mask_use_original_target") {
      let current = state.answers.ligand_mask_use_original_target;
      if (typeof current !== "boolean") {
        const routedDefault = state.plan?.routed_request?.ligand_mask_use_original_target;
        if (typeof routedDefault === "boolean") {
          current = routedDefault;
        } else {
          current = q.default !== undefined ? Boolean(q.default) : true;
        }
        state.answers.ligand_mask_use_original_target = current;
      }
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.ligandMaskOriginal.on", value: true },
          { labelKey: "choice.ligandMaskOriginal.off", value: false },
        ],
        current,
        (value) => {
          state.answers.ligand_mask_use_original_target = value;
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "bioemu_use") {
      let current = state.answers.bioemu_use;
      if (typeof current !== "boolean") {
        const routedDefault = state.plan?.routed_request?.bioemu_use;
        if (typeof routedDefault === "boolean") {
          current = routedDefault;
        } else {
          current = q.default !== undefined ? Boolean(q.default) : false;
        }
        state.answers.bioemu_use = current;
      }
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.bioemuUse.on", value: true },
          { labelKey: "choice.bioemuUse.off", value: false },
        ],
        current,
        (value) => {
          state.answers.bioemu_use = value;
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "novelty_enabled") {
      let current = state.answers.novelty_enabled;
      if (typeof current !== "boolean") {
        const routedDefault = state.plan?.routed_request?.novelty_enabled;
        if (typeof routedDefault === "boolean") {
          current = routedDefault;
        } else {
          current = q.default !== undefined ? Boolean(q.default) : false;
        }
        state.answers.novelty_enabled = current;
      }
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.novelty.on", value: true },
          { labelKey: "choice.novelty.off", value: false },
        ],
        current,
        (value) => {
          state.answers.novelty_enabled = value;
          if (value) {
            state.answers.stop_after = "novelty";
          } else if (String(state.answers.stop_after || "").trim().toLowerCase() === "novelty") {
            state.answers.stop_after = "af2";
          }
          syncStartStopStages();
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "confirm_run") {
      let current = state.answers.confirm_run;
      if (typeof current !== "boolean") {
        current = q.default !== undefined ? Boolean(q.default) : true;
        state.answers.confirm_run = current;
      }
      renderChoiceButtons(
        card,
        [
          { labelKey: "choice.confirmRun.no", value: false },
          { labelKey: "choice.confirmRun.yes", value: true },
        ],
        current,
        (value) => {
          state.answers.confirm_run = value;
          updateRunEligibility(normalizedQuestions);
        }
      );
    }

    if (q.id === "rfd3_contig") {
      const rfd3Active =
        state.runMode === "rfd3" || !isAnswerMissing(state.answers.rfd3_input_pdb);
      const routedDefault = state.plan?.routed_request?.rfd3_contig;
      if (rfd3Active && !state.answers.rfd3_contig && routedDefault) {
        state.answers.rfd3_contig = routedDefault;
      }
      const ranges = state.chainRanges || {};
      const contigs = Object.entries(ranges).map(([chain, range]) => ({
        label: `${chain}${range.min}-${range.max}`,
        value: `${chain}${range.min}-${range.max}`,
      }));
      if (contigs.length) {
        let current = state.answers.rfd3_contig;
        if (!current && rfd3Active) {
          current = contigs[0].value;
          state.answers.rfd3_contig = current;
        }
        const options = [{ labelKey: "choice.contigNone", value: "" }, ...contigs];
        renderChoiceButtons(card, options, current || "", (value) => {
          state.answers.rfd3_contig = value;
          updateRunEligibility(normalizedQuestions);
        });
        const note = document.createElement("div");
        note.className = "choice-note";
        note.textContent = t("choice.contigPositiveOnly");
        card.appendChild(note);
      } else {
        const note = document.createElement("div");
        note.className = "choice-note";
        note.textContent = t("choice.contigNote");
        card.appendChild(note);
      }
    }

    appendConfigCard(card);
  });

  const appendCompactOptionBoard = () => {
    const optionQuestions = choiceQuestions.filter((q) => compactChoiceQuestionIds.has(q.id));
    if (!optionQuestions.length) return;
    const questionById = new Map(optionQuestions.map((q) => [q.id, q]));

    const ensureBooleanAnswer = (q, fallback = false) => {
      if (!q) return fallback;
      let current = state.answers[q.id];
      if (typeof current !== "boolean") {
        const routedDefault = state.plan?.routed_request?.[q.id];
        if (typeof routedDefault === "boolean") {
          current = routedDefault;
        } else if (q.default !== undefined) {
          current = Boolean(q.default);
        } else {
          current = fallback;
        }
        state.answers[q.id] = current;
      }
      return Boolean(current);
    };

    const card = document.createElement("div");
    card.className = "question-card parameter-board option-board";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = t("setup.options.title");

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = t("setup.options.help");

    const grid = document.createElement("div");
    grid.className = "parameter-board-grid option-board-grid";

    const appendOptionField = (q, buildControls) => {
      if (!q) return;
      const field = document.createElement("div");
      field.className = "parameter-field option-field" + (q.required ? " required" : "");

      const label = document.createElement("div");
      label.className = "parameter-label";
      label.textContent = q.labelKey ? t(q.labelKey) : q.label || q.id || "option";

      const desc = document.createElement("div");
      desc.className = "parameter-help";
      desc.textContent = q.questionKey ? t(q.questionKey) : q.question || "";

      field.appendChild(label);
      field.appendChild(desc);
      buildControls(field, q);
      grid.appendChild(field);
    };

    const renderBooleanField = ({
      id,
      fallback,
      onLabelKey,
      offLabelKey,
      onChange,
      rerender = false,
    }) => {
      const q = questionById.get(id);
      if (!q) return;
      const current = ensureBooleanAnswer(q, fallback);
      appendOptionField(q, (field) => {
        renderChoiceButtons(
          field,
          [
            { labelKey: onLabelKey, value: true },
            { labelKey: offLabelKey, value: false },
          ],
          current,
          (value) => {
            state.answers[id] = value;
            if (onChange) onChange(value);
            updateRunEligibility(normalizedQuestions);
          },
          { rerender }
        );
      });
    };

    renderBooleanField({
      id: "novelty_enabled",
      fallback: true,
      onLabelKey: "choice.novelty.on",
      offLabelKey: "choice.novelty.off",
      onChange: (value) => {
        if (value) {
          state.answers.stop_after = "novelty";
        } else if (String(state.answers.stop_after || "").trim().toLowerCase() === "novelty") {
          state.answers.stop_after = "af2";
        }
        syncStartStopStages();
      },
      rerender: false,
    });

    renderBooleanField({
      id: "bioemu_use",
      fallback: false,
      onLabelKey: "choice.bioemuUse.on",
      offLabelKey: "choice.bioemuUse.off",
      rerender: false,
    });

    const af2Question = questionById.get("af2_provider");
    if (af2Question) {
      const routedDefault = state.plan?.routed_request?.af2_provider;
      const current = String(state.answers.af2_provider || routedDefault || af2Question.default || "colabfold")
        .trim()
        .toLowerCase();
      state.answers.af2_provider = normalizeAf2Provider(current);
      appendOptionField(af2Question, (field) => {
        renderChoiceButtons(
          field,
          [
            { labelKey: "choice.af2Provider.colabfold", value: "colabfold" },
            { labelKey: "choice.af2Provider.af2", value: "af2" },
          ],
          state.answers.af2_provider,
          (value) => {
            state.answers.af2_provider = normalizeAf2Provider(value);
            refreshAf2ProviderLabels({ rerenderQuestions: true });
            updateRunEligibility(normalizedQuestions);
          },
          { rerender: false }
        );
      });
    }

    const designChainsQuestion = questionById.get("design_chains");
    if (designChainsQuestion) {
      appendOptionField(designChainsQuestion, (field) => {
        const chains = state.chainRanges ? Object.keys(state.chainRanges) : [];
        let current = Array.isArray(state.answers.design_chains) ? state.answers.design_chains : [];
        const routedDefault = state.plan?.routed_request?.design_chains;
        if (!current.length && Array.isArray(routedDefault) && routedDefault.length) {
          current = routedDefault;
          state.answers.design_chains = current;
        }

        const group = document.createElement("div");
        group.className = "choice-group";

        const allBtn = document.createElement("button");
        allBtn.type = "button";
        allBtn.className = "choice-btn" + (current.length === 0 ? " selected" : "");
        allBtn.textContent = t("choice.allChains");
        allBtn.addEventListener("click", () => {
          state.answers.design_chains = [];
          updateRunEligibility(normalizedQuestions);
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
            updateRunEligibility(normalizedQuestions);
            renderQuestions(state.plan?.questions || []);
          });
          group.appendChild(btn);
        });
        field.appendChild(group);

        const note = document.createElement("div");
        note.className = "choice-note";
        note.textContent = chains.length ? t("choice.chainDefaultNote") : t("choice.chainNote");
        field.appendChild(note);
      });
    }

    renderBooleanField({
      id: "pdb_strip_nonpositive_resseq",
      fallback: true,
      onLabelKey: "choice.stripNonpositive.on",
      offLabelKey: "choice.stripNonpositive.off",
      rerender: false,
    });

    renderBooleanField({
      id: "wt_compare",
      fallback: false,
      onLabelKey: "choice.wtCompare.on",
      offLabelKey: "choice.wtCompare.off",
      rerender: false,
    });

    renderBooleanField({
      id: "mask_consensus_apply",
      fallback: false,
      onLabelKey: "choice.maskConsensusApply.on",
      offLabelKey: "choice.maskConsensusApply.off",
      rerender: false,
    });

    renderBooleanField({
      id: "ligand_mask_use_original_target",
      fallback: true,
      onLabelKey: "choice.ligandMaskOriginal.on",
      offLabelKey: "choice.ligandMaskOriginal.off",
      rerender: false,
    });

    card.appendChild(title);
    card.appendChild(help);
    card.appendChild(grid);
    appendConfigCard(card);
  };

  appendCompactOptionBoard();

  const bioemuCountQuestionIds = new Set(["bioemu_num_samples", "bioemu_max_return_structures"]);
  const rfd3CountQuestionIds = new Set(["rfd3_max_return_designs"]);
  const compactParameterQuestionIds = new Set([
    "bioemu_num_samples",
    "bioemu_max_return_structures",
    "rfd3_max_return_designs",
    "num_seq_per_tier",
    "af2_max_candidates_per_tier",
    "af2_plddt_cutoff",
    "af2_rmsd_cutoff",
  ]);
  const bioemuCountRelevant =
    state.runMode === "pipeline" ||
    state.runMode === "workflow" ||
    state.runMode === "bioemu" ||
    state.answers.bioemu_use === true ||
    state.answers.stop_after === "bioemu";
  const rfd3CountRelevant =
    state.runMode === "pipeline" ||
    state.runMode === "workflow" ||
    state.runMode === "rfd3" ||
    state.answers.stop_after === "rfd3" ||
    !isAnswerMissing(state.answers.rfd3_input_pdb);

  const compactQuestions = textQuestions.filter((q) => compactParameterQuestionIds.has(q.id));

  const appendCompactParameterBoard = (questionsForBoard) => {
    if (!questionsForBoard.length) return;
    const card = document.createElement("div");
    card.className = "question-card parameter-board";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = t("setup.parameters.title");

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = t("setup.parameters.help");

    const grid = document.createElement("div");
    grid.className = "parameter-board-grid";

    questionsForBoard.forEach((q) => {
      const field = document.createElement("label");
      field.className = "parameter-field" + (q.required ? " required" : "");
      const inactive =
        (bioemuCountQuestionIds.has(q.id) && !bioemuCountRelevant) ||
        (rfd3CountQuestionIds.has(q.id) && !rfd3CountRelevant);
      if (inactive) field.classList.add("inactive");

      const fieldLabel = document.createElement("span");
      fieldLabel.className = "parameter-label";
      fieldLabel.textContent = q.labelKey ? t(q.labelKey) : q.label || q.id || "input";

      const fieldHelp = document.createElement("span");
      fieldHelp.className = "parameter-help";
      fieldHelp.textContent = q.questionKey ? t(q.questionKey) : q.question || "";

      const input = document.createElement("input");
      input.type = ANSWER_INT_KEYS.has(q.id) || ANSWER_FLOAT_KEYS.has(q.id) ? "number" : "text";
      if (ANSWER_FLOAT_KEYS.has(q.id)) input.step = "0.01";
      if (ANSWER_INT_KEYS.has(q.id)) input.step = "1";
      if (q.id === "af2_plddt_cutoff") {
        input.min = "0";
        input.max = "100";
        input.step = "0.1";
      } else if (q.id === "af2_rmsd_cutoff") {
        input.min = "0.01";
        input.step = "0.01";
      }
      if (q.placeholder) {
        input.placeholder = q.placeholder;
      }
      input.disabled = inactive;
      if (state.answers[q.id] === undefined && q.default !== undefined) {
        state.answers[q.id] = q.default;
      }
      input.value = formatAnswerValue(state.answers[q.id]);

      const errorEl = document.createElement("span");
      errorEl.className = "parameter-error";
      const existingError = (state.answerMeta[q.id] || {}).error;
      if (existingError) {
        errorEl.textContent = existingError;
      } else {
        errorEl.textContent = "";
      }

      input.addEventListener("input", () => {
        const parsed = parseAnswerValue(q.id, input.value);
        if (parsed.error) {
          state.answers[q.id] = "";
          state.answerMeta[q.id] = { ...state.answerMeta[q.id], error: parsed.error, raw: input.value };
          errorEl.textContent = parsed.error;
        } else {
          state.answers[q.id] = parsed.value;
          state.answerMeta[q.id] = { ...state.answerMeta[q.id], error: "", raw: input.value };
          errorEl.textContent = "";
        }
        updateRunEligibility(normalizedQuestions);
      });

      field.appendChild(fieldLabel);
      field.appendChild(fieldHelp);
      field.appendChild(input);
      if (inactive) {
        const inactiveHint = document.createElement("span");
        inactiveHint.className = "parameter-help inactive";
        inactiveHint.textContent = t("setup.parameters.inactive");
        field.appendChild(inactiveHint);
      }
      field.appendChild(errorEl);
      grid.appendChild(field);
    });

    card.appendChild(title);
    card.appendChild(help);
    card.appendChild(grid);
    appendConfigCard(card);
  };

  appendCompactParameterBoard(compactQuestions);

  function appendWorkflowDesignerCard() {
    if (state.runMode !== "workflow") return;
    const stageChoices = PIPELINE_STAGE_ORDER.map((stage) => ({
      stage,
      label:
        stage === "novelty"
          ? t("stop.full")
          : stage === "af2"
            ? t("stage.af2")
            : t(`stage.${stage}`),
      desc: t(`setup.workflow.stageDesc.${stage}`),
    }));
    const stageChoiceMap = new Map(stageChoices.map((item) => [item.stage, item]));
    const stageLabelFor = (stage) => stageChoiceMap.get(stage)?.label || formatStageLabel(stage);
    const stageDescFor = (stage) => stageChoiceMap.get(stage)?.desc || t("setup.workflow.stageGuideHint");
    const applyNodeSet = (nextSet) => {
      const ordered = PIPELINE_STAGE_ORDER.filter((stage) => nextSet.has(stage));
      if (!ordered.length) return;
      state.workflowDesigner.nodes = ordered;
      const normalizedCheckpoints = normalizeWorkflowCheckpointList(
        state.workflowDesigner.checkpointStages,
        ordered
      );
      state.workflowDesigner.checkpointStages = normalizedCheckpoints;
      if (!normalizedCheckpoints.length) {
        state.workflowDesigner.checkpointEnabled = false;
      }
      state.workflowDesigner.flowPulse = Number(state.workflowDesigner.flowPulse || 0) + 1;
      renderQuestions(state.plan?.questions || []);
    };

    const card = document.createElement("div");
    card.className = "question-card workflow-designer";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = t("setup.workflow.title");

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = t("setup.workflow.help");

    const layout = document.createElement("div");
    layout.className = "workflow-designer-layout";

    const mainCol = document.createElement("div");
    mainCol.className = "workflow-designer-main";

    const sideCol = document.createElement("div");
    sideCol.className = "workflow-designer-side";

    const guideBlock = document.createElement("section");
    guideBlock.className = "workflow-block";
    const guideTitle = document.createElement("div");
    guideTitle.className = "workflow-section-label";
    guideTitle.textContent = t("setup.workflow.stageGuide");
    const guideHint = document.createElement("div");
    guideHint.className = "workflow-block-help";
    guideHint.textContent = t("setup.workflow.stageGuideHint");
    const guideLabel = document.createElement("div");
    guideLabel.className = "workflow-stage-guide-label";
    const guideDesc = document.createElement("div");
    guideDesc.className = "workflow-stage-guide-desc";
    guideBlock.appendChild(guideTitle);
    guideBlock.appendChild(guideHint);
    guideBlock.appendChild(guideLabel);
    guideBlock.appendChild(guideDesc);

    const updateGuide = (stage) => {
      const item = stageChoiceMap.get(stage) || stageChoices[0] || null;
      if (!item) {
        guideLabel.textContent = t("setup.workflow.stageGuideHint");
        guideDesc.textContent = "";
        return;
      }
      guideLabel.textContent = `${t("setup.workflow.stageGuideLabel")}: ${item.label}`;
      guideDesc.textContent = stageDescFor(item.stage);
    };

    const paletteBlock = document.createElement("section");
    paletteBlock.className = "workflow-block";
    const paletteTitle = document.createElement("div");
    paletteTitle.className = "workflow-section-label";
    paletteTitle.textContent = t("setup.workflow.palette");
    const paletteHelp = document.createElement("div");
    paletteHelp.className = "workflow-block-help";
    paletteHelp.textContent = t("setup.workflow.paletteHelp");
    paletteBlock.appendChild(paletteTitle);
    paletteBlock.appendChild(paletteHelp);

    const palette = document.createElement("div");
    palette.className = "choice-group workflow-palette";
    const selected = new Set(normalizeWorkflowNodesForState(state.workflowDesigner.nodes));
    stageChoices.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "choice-btn workflow-palette-btn";
      if (selected.has(item.stage)) btn.classList.add("selected");
      btn.textContent = item.label;
      btn.title = stageDescFor(item.stage);
      btn.addEventListener("mouseenter", () => {
        updateGuide(item.stage);
      });
      btn.addEventListener("focus", () => {
        updateGuide(item.stage);
      });
      btn.addEventListener("click", () => {
        const nextSet = new Set(selected);
        if (nextSet.has(item.stage)) {
          nextSet.delete(item.stage);
        } else {
          nextSet.add(item.stage);
        }
        applyNodeSet(nextSet);
      });
      palette.appendChild(btn);
    });
    paletteBlock.appendChild(palette);

    const canvasBlock = document.createElement("section");
    canvasBlock.className = "workflow-block";
    const canvasTitle = document.createElement("div");
    canvasTitle.className = "workflow-section-label";
    canvasTitle.textContent = t("setup.workflow.canvas");
    const canvasHelp = document.createElement("div");
    canvasHelp.className = "workflow-block-help";
    canvasHelp.textContent = t("setup.workflow.canvasHelp");
    canvasBlock.appendChild(canvasTitle);
    canvasBlock.appendChild(canvasHelp);

    const canvas = document.createElement("div");
    canvas.className = "workflow-canvas";
    const nodes = normalizeWorkflowNodesForState(state.workflowDesigner.nodes);
    const checkpointStages = normalizeWorkflowCheckpointList(
      state.workflowDesigner.checkpointStages,
      nodes
    );
    if (!nodes.length) {
      canvas.innerHTML = `<div class="placeholder">${escapeHtml(t("setup.workflow.empty"))}</div>`;
    } else {
      nodes.forEach((stage, idx) => {
        const node = document.createElement("div");
        node.className = "workflow-node";
        node.tabIndex = 0;
        node.setAttribute("role", "button");
        node.style.animationDelay = `${Math.min(idx, 8) * 60}ms`;
        node.dataset.stage = stage;
        const isCheckpoint =
          Boolean(state.workflowDesigner.checkpointEnabled) && checkpointStages.includes(stage);
        const isFinal = idx === nodes.length - 1;
        if (isCheckpoint) node.classList.add("checkpoint");
        if (isFinal) node.classList.add("final-node");
        const stageLabel = stageLabelFor(stage);
        node.title = stageDescFor(stage);
        node.innerHTML = `
          <span class="workflow-node-title">${escapeHtml(stageLabel)}</span>
          <span class="workflow-node-badges">
            ${isCheckpoint ? `<span class="workflow-node-badge">${escapeHtml(t("setup.workflow.badge.checkpoint"))}</span>` : ""}
            ${isFinal ? `<span class="workflow-node-badge final">${escapeHtml(t("setup.workflow.badge.final"))}</span>` : ""}
          </span>
        `;
        const toggleCheckpoint = () => {
          const candidateStages = workflowCheckpointCandidates(nodes);
          if (!candidateStages.includes(stage)) return;
          const next = new Set(checkpointStages);
          if (next.has(stage)) {
            next.delete(stage);
          } else {
            next.add(stage);
          }
          const nextCheckpoints = normalizeWorkflowCheckpointList(Array.from(next), nodes);
          state.workflowDesigner.checkpointStages = nextCheckpoints;
          state.workflowDesigner.checkpointEnabled = nextCheckpoints.length > 0;
          renderQuestions(state.plan?.questions || []);
        };
        node.addEventListener("click", () => {
          toggleCheckpoint();
        });
        node.addEventListener("mouseenter", () => {
          updateGuide(stage);
        });
        node.addEventListener("focus", () => {
          updateGuide(stage);
        });
        node.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          toggleCheckpoint();
        });
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "workflow-node-remove";
        removeBtn.textContent = "x";
        removeBtn.title = t("setup.workflow.removeNode");
        removeBtn.addEventListener("click", (event) => {
          event.stopPropagation();
          const nextSet = new Set(nodes);
          nextSet.delete(stage);
          applyNodeSet(nextSet);
        });
        node.appendChild(removeBtn);
        canvas.appendChild(node);
        if (idx < nodes.length - 1) {
          const edge = document.createElement("span");
          edge.className = "workflow-edge";
          edge.textContent = "->";
          canvas.appendChild(edge);
        }
      });
    }
    canvasBlock.appendChild(canvas);

    const hint = document.createElement("div");
    hint.className = "workflow-block-help";
    hint.textContent = t("setup.workflow.nodeHint");
    const orderHint = document.createElement("div");
    orderHint.className = "workflow-block-help";
    orderHint.textContent = t("setup.workflow.orderLocked");
    canvasBlock.appendChild(hint);
    canvasBlock.appendChild(orderHint);

    const controlsBlock = document.createElement("section");
    controlsBlock.className = "workflow-block";
    const controlsTitle = document.createElement("div");
    controlsTitle.className = "workflow-section-label";
    controlsTitle.textContent = t("setup.workflow.controls");
    controlsBlock.appendChild(controlsTitle);
    const toggleWrap = document.createElement("div");
    toggleWrap.className = "workflow-toggle-wrap";
    const makeToggle = (labelKey, checked, onChange) => {
      const row = document.createElement("label");
      row.className = "toggle workflow-toggle";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(checked);
      input.addEventListener("change", () => {
        onChange(Boolean(input.checked));
        renderQuestions(state.plan?.questions || []);
      });
      const span = document.createElement("span");
      span.textContent = t(labelKey);
      row.appendChild(input);
      row.appendChild(span);
      return row;
    };
    toggleWrap.appendChild(
      makeToggle("setup.workflow.checkpoint", state.workflowDesigner.checkpointEnabled, (next) => {
        state.workflowDesigner.checkpointEnabled = next;
        if (!next) {
          state.workflowDesigner.checkpointStages = [];
        }
      })
    );
    toggleWrap.appendChild(
      makeToggle("setup.workflow.showResults", state.workflowDesigner.graphEnabled !== false, (next) => {
        state.workflowDesigner.graphEnabled = next;
      })
    );
    toggleWrap.appendChild(
      makeToggle("setup.workflow.mmseqLoop", state.workflowDesigner.mmseqLoopEnabled !== false, (next) => {
        state.workflowDesigner.mmseqLoopEnabled = next;
      })
    );
    controlsBlock.appendChild(toggleWrap);

    const plan = buildWorkflowPlanFromDesigner();
    const summaryBlock = document.createElement("section");
    summaryBlock.className = "workflow-block";
    const summaryTitle = document.createElement("div");
    summaryTitle.className = "workflow-section-label";
    summaryTitle.textContent = t("setup.workflow.summaryTitle");
    const summary = document.createElement("div");
    summary.className = "question-summary";
    summary.textContent = plan.checkpointEnabled
      ? t("setup.workflow.plan", {
          start: formatStageLabel(plan.start),
          stop: formatStageLabel(plan.stopAfter),
          final: formatStageLabel(plan.finalStop),
        })
      : t("setup.workflow.planNoCheckpoint", {
          start: formatStageLabel(plan.start),
          final: formatStageLabel(plan.finalStop),
        });
    const checkpointSummary = document.createElement("div");
    checkpointSummary.className = "question-summary";
    checkpointSummary.textContent = plan.checkpointStages.length
      ? t("setup.workflow.checkpoints", {
          stages: plan.checkpointStages.map((stage) => formatStageLabel(stage)).join(" -> "),
        })
      : t("setup.workflow.checkpoints.none");
    summaryBlock.appendChild(summaryTitle);
    summaryBlock.appendChild(summary);
    summaryBlock.appendChild(checkpointSummary);

    mainCol.appendChild(paletteBlock);
    mainCol.appendChild(canvasBlock);
    sideCol.appendChild(guideBlock);
    sideCol.appendChild(controlsBlock);
    sideCol.appendChild(summaryBlock);

    layout.appendChild(mainCol);
    layout.appendChild(sideCol);

    card.appendChild(title);
    card.appendChild(help);
    card.appendChild(layout);
    updateGuide(nodes[0] || stageChoices[0]?.stage || "");
    appendConfigCard(card);
  }

  appendWorkflowDesignerCard();

  function appendTextQuestionCard(q) {
    const card = document.createElement("div");
    card.className = buildQuestionCardClass(q);

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = q.labelKey ? t(q.labelKey) : q.label || q.id || "input";

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = q.questionKey ? t(q.questionKey) : q.question || "";

    const inputWrap = document.createElement("div");
    inputWrap.className = "input-row";
    const multiline = Boolean(q.multiline) || ANSWER_TEXTAREA_KEYS.has(q.id);

    const input = multiline ? document.createElement("textarea") : document.createElement("input");
    if (!multiline) {
      input.type = ANSWER_INT_KEYS.has(q.id) || ANSWER_FLOAT_KEYS.has(q.id) ? "number" : "text";
      if (ANSWER_FLOAT_KEYS.has(q.id)) input.step = "0.01";
      if (ANSWER_INT_KEYS.has(q.id)) input.step = "1";
      if (q.id === "af2_plddt_cutoff") {
        input.min = "0";
        input.max = "100";
        input.step = "0.1";
      } else if (q.id === "af2_rmsd_cutoff") {
        input.min = "0.01";
        input.step = "0.01";
      }
    }
    if (multiline) {
      input.rows = 3;
    }
    if (q.placeholder) {
      input.placeholder = q.placeholder;
    }

    if (state.answers[q.id] === undefined && q.default !== undefined) {
      state.answers[q.id] = q.default;
    }
    input.value = formatAnswerValue(state.answers[q.id]);

    const errorEl = document.createElement("div");
    errorEl.className = "question-error";
    const existingError = (state.answerMeta[q.id] || {}).error;
    if (existingError) {
      errorEl.textContent = existingError;
      errorEl.style.display = "block";
    } else {
      errorEl.style.display = "none";
    }

    input.addEventListener("input", () => {
      const parsed = parseAnswerValue(q.id, input.value);
      if (parsed.error) {
        state.answers[q.id] = "";
        state.answerMeta[q.id] = { ...state.answerMeta[q.id], error: parsed.error, raw: input.value };
        errorEl.textContent = parsed.error;
        errorEl.style.display = "block";
      } else {
        state.answers[q.id] = parsed.value;
        state.answerMeta[q.id] = { ...state.answerMeta[q.id], error: "", raw: input.value };
        errorEl.textContent = "";
        errorEl.style.display = "none";
      }
      updateRunEligibility(normalizedQuestions);
    });

    inputWrap.appendChild(input);
    card.appendChild(title);
    card.appendChild(help);
    card.appendChild(inputWrap);
    card.appendChild(errorEl);
    appendConfigCard(card);
  }

  const hiddenTextQuestionIds = new Set(compactQuestions.map((q) => q.id));
  textQuestions.forEach((q) => {
    if (hiddenTextQuestionIds.has(q.id)) return;
    appendTextQuestionCard(q);
  });

  if (fileQuestions.length) {
    const card = document.createElement("div");
    card.className = "question-card attachments";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = t("attachment.title");

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = t("attachment.help");

    const list = document.createElement("div");
    list.className = "attachment-list";

    fileQuestions.forEach((q) => {
      const item = document.createElement("div");
      item.className = "attachment-item" + (q.required ? " required" : "");

      const itemTitle = document.createElement("div");
      itemTitle.className = "attachment-title";
      itemTitle.textContent = q.labelKey ? t(q.labelKey) : q.label || q.id || "file";

      const itemHelp = document.createElement("div");
      itemHelp.className = "attachment-help";
      itemHelp.textContent = q.questionKey ? t(q.questionKey) : q.question || "";

      const controls = document.createElement("div");
      controls.className = "file-controls";

      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.className = "file-input-native";

      const selectBtn = document.createElement("button");
      selectBtn.type = "button";
      selectBtn.className = "ghost";
      selectBtn.textContent = t("attachment.select");
      selectBtn.addEventListener("click", () => fileInput.click());

      const fileName = document.createElement("div");
      fileName.className = "file-name";

      const meta = document.createElement("div");
      meta.className = "attachment-meta";
      const existingName = (state.answerMeta[q.id] || {}).fileName;
      if (state.answers[q.id] && existingName) {
        fileName.textContent = existingName;
        meta.textContent = t("attachment.attachedName", { name: existingName });
      } else {
        fileName.textContent = t("attachment.none");
        meta.textContent = t("attachment.none");
      }

      if (q.id === "diffdock_ligand" && state.runMode === "pipeline") {
        const toggleWrap = document.createElement("div");
        toggleWrap.className = "choice-group";

        const useBtn = document.createElement("button");
        useBtn.type = "button";
        useBtn.className = "choice-btn";
        useBtn.textContent = t("attachment.diffdock.use");

        const skipBtn = document.createElement("button");
        skipBtn.type = "button";
        skipBtn.className = "choice-btn selected";
        skipBtn.textContent = t("attachment.diffdock.skip");

        const setMode = (mode) => {
          state.answers.diffdock_use = mode;
          if (mode === "use") {
            useBtn.classList.add("selected");
            skipBtn.classList.remove("selected");
            fileInput.disabled = false;
            selectBtn.disabled = false;
          } else {
            useBtn.classList.remove("selected");
            skipBtn.classList.add("selected");
            fileInput.value = "";
            fileInput.disabled = true;
            selectBtn.disabled = true;
            state.answers.diffdock_ligand = "";
            fileName.textContent = t("attachment.none");
            meta.textContent = t("attachment.none");
          }
          updateRunEligibility(normalizedQuestions);
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
      clearBtn.textContent = t("attachment.clear");

      fileInput.addEventListener("change", async (event) => {
        const file = event.target.files?.[0];
        if (!file) {
          state.answers[q.id] = "";
          state.answerMeta[q.id] = {};
          if (q.id === "target_input") {
            state.answers.target_fasta = "";
            state.answers.target_pdb = "";
            state.answerMeta.target_pdb = {};
          }
          fileName.textContent = t("attachment.none");
          meta.textContent = t("attachment.none");
          let rerender = false;
          if (q.id === "target_input") {
            if (state.setupResiduePicker.sourceKey === "target_input") {
              resetSetupResiduePicker();
            }
            refreshChainRangesFromAnswers();
            rerender = true;
          }
          if (q.id === "rfd3_input_pdb") {
            if (state.setupResiduePicker.sourceKey === "rfd3_input_pdb") {
              resetSetupResiduePicker();
            }
            if (state.runMode === "pipeline" || state.runMode === "workflow") {
              state.answers.rfd3_contig = "";
            }
            refreshChainRangesFromAnswers();
            rerender = true;
          }
          if (rerender) {
            renderQuestions(state.plan?.questions || []);
          }
          updateRunEligibility(normalizedQuestions);
          return;
        }
        try {
          const text = await file.text();
          state.answers[q.id] = text;
          state.answerMeta[q.id] = { fileName: file.name };
          const kb = Math.max(1, Math.round(file.size / 1024));
          fileName.textContent = file.name;
          meta.textContent = t("attachment.attached", { name: file.name, kb });
          let rerender = false;
          if (q.id === "target_input") {
            const key = detectTargetKey(text);
            state.answers.target_fasta = "";
            state.answers.target_pdb = "";
            state.answerMeta.target_pdb = {};
            if (key === "target_pdb") {
              state.answers.target_pdb = text;
              state.answerMeta.target_pdb = { fileName: file.name };
              const loaded = setSetupResiduePickerStructure(text, {
                sourceLabel: t("setup.residuePicker.loadTargetInput"),
                sourceKey: "target_input",
              });
              if (!loaded && state.setupResiduePicker.sourceKey === "target_input") {
                resetSetupResiduePicker();
              }
            } else if (key === "target_fasta") {
              state.answers.target_fasta = text;
            } else if (state.setupResiduePicker.sourceKey === "target_input") {
              resetSetupResiduePicker();
            }
            refreshChainRangesFromAnswers();
            rerender = true;
          }
          if (q.id === "rfd3_input_pdb") {
            const loaded = setSetupResiduePickerStructure(text, {
              sourceLabel: t("setup.residuePicker.loadRfd3Input"),
              sourceKey: "rfd3_input_pdb",
            });
            if (!loaded && state.setupResiduePicker.sourceKey === "rfd3_input_pdb") {
              resetSetupResiduePicker();
            }
            refreshChainRangesFromAnswers();
            rerender = true;
          }
          if (rerender) {
            renderQuestions(state.plan?.questions || []);
          }
        } catch (err) {
          state.answers[q.id] = "";
          state.answerMeta[q.id] = {};
          if (q.id === "target_input") {
            state.answers.target_fasta = "";
            state.answers.target_pdb = "";
            state.answerMeta.target_pdb = {};
          }
          fileName.textContent = t("attachment.none");
          meta.textContent = t("attachment.failed", { error: err.message });
          let rerender = false;
          if (q.id === "target_input" && state.setupResiduePicker.sourceKey === "target_input") {
            resetSetupResiduePicker();
            rerender = true;
          }
          if (q.id === "rfd3_input_pdb" && state.setupResiduePicker.sourceKey === "rfd3_input_pdb") {
            resetSetupResiduePicker();
            if (state.runMode === "pipeline" || state.runMode === "workflow") {
              state.answers.rfd3_contig = "";
            }
            rerender = true;
          }
          if (q.id === "target_input" || q.id === "rfd3_input_pdb") {
            refreshChainRangesFromAnswers();
            rerender = true;
          }
          if (rerender) {
            renderQuestions(state.plan?.questions || []);
          }
        }
        updateRunEligibility(normalizedQuestions);
      });

      clearBtn.addEventListener("click", () => {
        fileInput.value = "";
        state.answers[q.id] = "";
        state.answerMeta[q.id] = {};
        if (q.id === "target_input") {
          state.answers.target_fasta = "";
          state.answers.target_pdb = "";
          state.answerMeta.target_pdb = {};
        }
        fileName.textContent = t("attachment.none");
        meta.textContent = t("attachment.none");
        let rerender = false;
        if (q.id === "target_input") {
          if (state.setupResiduePicker.sourceKey === "target_input") {
            resetSetupResiduePicker();
          }
          refreshChainRangesFromAnswers();
          rerender = true;
        }
        if (q.id === "rfd3_input_pdb") {
          if (state.setupResiduePicker.sourceKey === "rfd3_input_pdb") {
            resetSetupResiduePicker();
          }
          refreshChainRangesFromAnswers();
          rerender = true;
        }
        if (q.id === "rfd3_input_pdb" && (state.runMode === "pipeline" || state.runMode === "workflow")) {
          state.answers.rfd3_contig = "";
        }
        if (rerender) {
          renderQuestions(state.plan?.questions || []);
        }
        updateRunEligibility(normalizedQuestions);
      });

      controls.appendChild(selectBtn);
      controls.appendChild(fileName);
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
    appendInputCard(card);
  }

  const showResiduePicker =
    (state.runMode === "pipeline" || state.runMode === "workflow") &&
    normalizedQuestions.some((q) => q.id === "fixed_positions_extra");
  if (showResiduePicker) {
    const card = document.createElement("div");
    card.className = "question-card setup-residue-picker";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = t("setup.residuePicker.title");

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = t("setup.residuePicker.help");

    const source = document.createElement("div");
    source.className = "question-summary";
    source.textContent = t("setup.residuePicker.source", {
      source: state.setupResiduePicker.sourceLabel || t("setup.residuePicker.source.none"),
    });

    const controls = document.createElement("div");
    controls.className = "setup-residue-picker-controls";

    const loadTargetBtn = document.createElement("button");
    loadTargetBtn.type = "button";
    loadTargetBtn.className = "ghost";
    loadTargetBtn.textContent = t("setup.residuePicker.loadTargetInput");

    const loadRfd3Btn = document.createElement("button");
    loadRfd3Btn.type = "button";
    loadRfd3Btn.className = "ghost";
    loadRfd3Btn.textContent = t("setup.residuePicker.loadRfd3Input");

    const loadRunBtn = document.createElement("button");
    loadRunBtn.type = "button";
    loadRunBtn.className = "ghost";
    loadRunBtn.textContent = t("setup.residuePicker.loadRunTarget");

    const runAf2Btn = document.createElement("button");
    runAf2Btn.type = "button";
    runAf2Btn.className = "ghost";
    runAf2Btn.textContent = t("setup.residuePicker.runAf2");

    const targetPdbText = getTargetInputPdbText();
    const targetFastaText = getTargetInputFastaText();
    const rfd3PdbText = getRfd3InputPdbText();
    const pickerBusy = Boolean(state.setupResiduePicker.runningAf2);
    const selectedRunIdForPicker = String(el.setupRunSelector?.value || state.currentRunId || "").trim();
    loadTargetBtn.disabled = pickerBusy || !targetPdbText;
    loadRfd3Btn.disabled = pickerBusy || !rfd3PdbText;
    loadRunBtn.disabled = pickerBusy || !selectedRunIdForPicker;
    runAf2Btn.disabled = pickerBusy || !targetFastaText;

    const loadStructureFromText = (pdbText, sourceLabel, sourceKey) => {
      const text = String(pdbText || "").trim();
      if (!text) {
        state.setupResiduePicker.notice = t("setup.residuePicker.noPdb");
        renderQuestions(state.plan?.questions || []);
        return;
      }
      const loaded = setSetupResiduePickerStructure(text, { sourceLabel, sourceKey });
      if (!loaded) {
        state.setupResiduePicker.notice = t("setup.residuePicker.noPdb");
      } else {
        state.setupResiduePicker.notice = "";
      }
      renderQuestions(state.plan?.questions || []);
    };

    loadTargetBtn.addEventListener("click", () => {
      loadStructureFromText(targetPdbText, t("setup.residuePicker.loadTargetInput"), "target_input");
    });
    loadRfd3Btn.addEventListener("click", () => {
      loadStructureFromText(rfd3PdbText, t("setup.residuePicker.loadRfd3Input"), "rfd3_input_pdb");
    });
    loadRunBtn.addEventListener("click", async () => {
      const runId = String(el.setupRunSelector?.value || state.currentRunId || "").trim();
      if (!runId) {
        state.setupResiduePicker.notice = t("setup.residuePicker.noRun");
        renderQuestions(state.plan?.questions || []);
        return;
      }
      try {
        const result = await apiCall("pipeline.read_artifact", {
          run_id: runId,
          path: "target.pdb",
          max_bytes: 2_000_000,
        });
        const text = String(result?.text || "").trim();
        if (!text) {
          state.setupResiduePicker.notice = t("setup.residuePicker.noPdb");
          renderQuestions(state.plan?.questions || []);
          return;
        }
        const label = `${runId}:target.pdb`;
        const loaded = setSetupResiduePickerStructure(text, {
          sourceLabel: label,
          sourceKey: `run_target:${runId}`,
        });
        if (!loaded) {
          state.setupResiduePicker.notice = t("setup.residuePicker.noPdb");
        } else {
          state.setupResiduePicker.notice = "";
        }
      } catch (err) {
        state.setupResiduePicker.notice = t("setup.residuePicker.loadFailed", { error: err.message });
      }
      renderQuestions(state.plan?.questions || []);
    });

    runAf2Btn.addEventListener("click", async () => {
      const fastaText = String(getTargetInputFastaText() || "").trim();
      if (!fastaText) {
        state.setupResiduePicker.notice = t("setup.residuePicker.runAf2NeedsFasta");
        renderQuestions(state.plan?.questions || []);
        return;
      }

      const prefix = state.user?.run_prefix || buildUserPrefix({ name: state.user?.username || "user" });
      const runId = createRunId(`${prefix}_picker_af2`);
      state.setupResiduePicker.runningAf2 = true;
      state.setupResiduePicker.notice = t("setup.residuePicker.runAf2Running");
      renderQuestions(state.plan?.questions || []);

      try {
        const result = await apiCall("pipeline.af2_predict", {
          run_id: runId,
          target_fasta: fastaText,
          af2_provider: normalizeAf2Provider(state.answers.af2_provider || "colabfold"),
        });
        const outRunId = String(result?.run_id || runId);
        const candidates = [];
        const summaryAf2 = result?.summary?.af2;
        if (summaryAf2 && typeof summaryAf2 === "object") {
          Object.keys(summaryAf2).forEach((seqId) => {
            const clean = String(seqId || "").trim();
            if (!clean) return;
            candidates.push(`af2/${clean}/ranked_0.pdb`);
          });
        }
        try {
          const listed = await apiCall("pipeline.list_artifacts", {
            run_id: outRunId,
            max_depth: 5,
            limit: 300,
          });
          const listedPaths = Array.isArray(listed?.artifacts)
            ? listed.artifacts
                .map((item) => String(item?.path || ""))
                .filter((path) => /\/ranked_0\.pdb$/i.test(path))
                .sort()
            : [];
          listedPaths.forEach((path) => candidates.push(path));
        } catch {
          // best-effort candidate discovery
        }
        candidates.push("af2/target/ranked_0.pdb");
        candidates.push("af2/sequence/ranked_0.pdb");

        const tried = new Set();
        let selectedPath = "";
        let selectedPdb = "";
        for (const path of candidates) {
          const normalizedPath = String(path || "").trim();
          if (!normalizedPath || tried.has(normalizedPath)) continue;
          tried.add(normalizedPath);
          try {
            const artifact = await apiCall("pipeline.read_artifact", {
              run_id: outRunId,
              path: normalizedPath,
              max_bytes: 2_000_000,
            });
            const text = String(artifact?.text || "").trim();
            if (!text) continue;
            selectedPath = normalizedPath;
            selectedPdb = text;
            break;
          } catch {
            continue;
          }
        }

        if (!selectedPdb) {
          throw new Error(t("setup.residuePicker.runAf2NoResult"));
        }

        state.answers.target_fasta = fastaText;
        state.answers.target_pdb = selectedPdb;
        state.answerMeta.target_pdb = { fileName: `${outRunId}:${selectedPath}` };
        refreshChainRangesFromAnswers();
        const loaded = setSetupResiduePickerStructure(selectedPdb, {
          sourceLabel: `${outRunId}:${selectedPath}`,
          sourceKey: `af2_picker:${outRunId}`,
        });
        state.setupResiduePicker.notice = loaded
          ? t("setup.residuePicker.runAf2Loaded", { run: outRunId, path: selectedPath })
          : t("setup.residuePicker.noPdb");
        await refreshRuns();
      } catch (err) {
        state.setupResiduePicker.notice = t("setup.residuePicker.runAf2Failed", { error: err.message });
      } finally {
        state.setupResiduePicker.runningAf2 = false;
        renderQuestions(state.plan?.questions || []);
      }
    });

    controls.appendChild(runAf2Btn);
    controls.appendChild(loadTargetBtn);
    controls.appendChild(loadRfd3Btn);
    controls.appendChild(loadRunBtn);

    const viewerWrap = document.createElement("div");
    viewerWrap.className = "setup-residue-picker-view";

    const selectionText = document.createElement("div");
    selectionText.className = "question-summary";

    const notice = document.createElement("div");
    notice.className = "question-summary setup-residue-picker-notice";
    if (state.setupResiduePicker.notice) {
      notice.textContent = state.setupResiduePicker.notice;
    } else {
      notice.textContent = "";
    }

    const updateSelectionSummary = () => {
      const normalized = normalizeResidueSelectionMap(state.setupResiduePicker.selection);
      state.setupResiduePicker.selection = normalized;
      const summary = selectionSummaryText(normalized);
      if (summary) {
        selectionText.textContent = t("setup.residuePicker.selection.summary", { summary });
      } else {
        selectionText.textContent = t("setup.residuePicker.selection.none");
      }
    };
    updateSelectionSummary();

    if (!state.setupResiduePicker.pdbText) {
      const placeholder = document.createElement("div");
      placeholder.className = "placeholder";
      placeholder.textContent = t("setup.residuePicker.viewerPlaceholder");
      viewerWrap.appendChild(placeholder);
    } else if (!window.$3Dmol) {
      const placeholder = document.createElement("div");
      placeholder.className = "placeholder";
      placeholder.textContent = t("setup.residuePicker.viewerUnavailable");
      viewerWrap.appendChild(placeholder);
    } else {
      const viewerEl = document.createElement("div");
      viewerEl.className = "viewer3d setup-residue-picker-viewer";
      viewerWrap.appendChild(viewerEl);

      const viewer = window.$3Dmol.createViewer(viewerEl, { backgroundColor: "white" });
      viewer.addModel(state.setupResiduePicker.pdbText, "pdb");
      const residueSetByChain = {};
      Object.entries(state.setupResiduePicker.residueOrderByChain || {}).forEach(([chain, values]) => {
        residueSetByChain[chain] = new Set(values);
      });

      const redrawViewer = () => {
        viewer.setStyle({}, { cartoon: { color: "spectrum" } });
        Object.entries(normalizeResidueSelectionMap(state.setupResiduePicker.selection)).forEach(
          ([chain, values]) => {
            values.forEach((resi) => {
              const selector = { resi };
              const chainId = denormalizeChainId(chain);
              if (chainId) selector.chain = chainId;
              viewer.setStyle(selector, {
                cartoon: { color: "#d9480f" },
                stick: { radius: 0.2, color: "#d9480f" },
              });
            });
          }
        );
        viewer.render();
      };

      viewer.setClickable({}, true, (atom) => {
        const chain = normalizeChainId(atom?.chain || "");
        const resi = Number.parseInt(atom?.resi, 10);
        if (!Number.isFinite(resi) || resi <= 0) return;
        const allowed = residueSetByChain[chain];
        if (!allowed || !allowed.has(resi)) return;

        const next = normalizeResidueSelectionMap(state.setupResiduePicker.selection);
        const chainSet = new Set(next[chain] || []);
        if (chainSet.has(resi)) {
          chainSet.delete(resi);
        } else {
          chainSet.add(resi);
        }
        const sorted = Array.from(chainSet).sort((a, b) => a - b);
        if (sorted.length) {
          next[chain] = sorted;
        } else {
          delete next[chain];
        }
        state.setupResiduePicker.selection = next;
        state.setupResiduePicker.notice = "";
        notice.textContent = "";
        updateSelectionSummary();
        redrawViewer();
      });

      viewer.zoomTo();
      redrawViewer();
    }

    const actionRow = document.createElement("div");
    actionRow.className = "setup-residue-picker-controls";

    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "primary";
    applyBtn.textContent = t("setup.residuePicker.apply");
    applyBtn.addEventListener("click", () => {
      const mappedSelection = selectedResiduesToQueryPositions(
        state.setupResiduePicker.selection,
        state.setupResiduePicker.residueOrderByChain
      );
      const selectedCount = countSelectedResidues(mappedSelection);
      if (!selectedCount) {
        state.setupResiduePicker.notice = t("setup.residuePicker.noSelection");
        renderQuestions(state.plan?.questions || []);
        return;
      }
      const merged = mergeFixedPositionsMap(state.answers.fixed_positions_extra, mappedSelection);
      state.answers.fixed_positions_extra = merged;
      state.answerMeta.fixed_positions_extra = {
        ...(state.answerMeta.fixed_positions_extra || {}),
        error: "",
        raw: JSON.stringify(merged),
      };
      state.setupResiduePicker.notice = t("setup.residuePicker.applied", { count: selectedCount });
      renderQuestions(state.plan?.questions || []);
    });

    const clearSelectionBtn = document.createElement("button");
    clearSelectionBtn.type = "button";
    clearSelectionBtn.className = "ghost";
    clearSelectionBtn.textContent = t("setup.residuePicker.clearSelection");
    clearSelectionBtn.addEventListener("click", () => {
      state.setupResiduePicker.selection = {};
      state.setupResiduePicker.notice = "";
      renderQuestions(state.plan?.questions || []);
    });

    actionRow.appendChild(applyBtn);
    actionRow.appendChild(clearSelectionBtn);

    const note = document.createElement("div");
    note.className = "question-summary";
    note.textContent = t("setup.residuePicker.note");

    card.appendChild(title);
    card.appendChild(help);
    card.appendChild(source);
    card.appendChild(controls);
    card.appendChild(viewerWrap);
    card.appendChild(selectionText);
    card.appendChild(actionRow);
    card.appendChild(note);
    card.appendChild(notice);
    appendInputCard(card);
  }

  updateRunEligibility(normalizedQuestions);
}

function updateRunEligibility(questions) {
  if (state.runMode === "pipeline") {
    syncStartStopStages();
  }

  const requiredIds = new Set(
    (questions || [])
      .map((q) => normalizeQuestion(q))
      .filter((q) => q && q.required && q.id !== "run_mode")
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
    if (state.answers.stop_after === "bioemu") {
      requiredIds.add("bioemu_use");
    }
    if (state.answers.stop_after === "rfd3") {
      requiredIds.add("rfd3_input_pdb");
      requiredIds.add("rfd3_contig");
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

  if (state.runMode === "bioemu") {
    requiredIds.add("target_input");
    requiredIds.add("bioemu_use");
  }

  if (state.runMode === "workflow") {
    requiredIds.add("target_input");
    requiredIds.add("__workflow_nodes__");
  }

  const missing = Array.from(requiredIds).filter((id) => {
    if (id === "__workflow_nodes__") {
      return normalizeWorkflowNodesForState(state.workflowDesigner?.nodes).length === 0;
    }
    if (id === "confirm_run") return state.answers.confirm_run !== true;
    if (id === "bioemu_use") return state.answers.bioemu_use !== true;
    return isAnswerMissing(state.answers[id]);
  });
  const runBusy = state.runSubmitting || String(state.currentRunState || "").toLowerCase() === "running";
  const wizardBlocked = setupWizardEnabled(questions) && !isSetupWizardFinalStep();
  if (missing.length === 0 && !runBusy && !wizardBlocked) {
    el.runBtn.disabled = false;
    el.runHint.textContent = t("hint.ready");
  } else {
    el.runBtn.disabled = true;
    if (runBusy) {
      el.runHint.textContent = t("hint.running");
    } else if (wizardBlocked) {
      el.runHint.textContent = t("hint.nextStep");
    } else {
      el.runHint.textContent = t("hint.missing");
    }
  }
}

function currentRunStateText() {
  const statusState = String(state.lastRunStatus?.state || "")
    .trim()
    .toLowerCase();
  if (statusState) return statusState;
  return String(state.currentRunState || "")
    .trim()
    .toLowerCase();
}

function updateMonitorActionButtons() {
  const hasRun = Boolean(String(state.currentRunId || "").trim());
  const running = currentRunStateText() === "running";
  if (el.cancelRunBtn) {
    el.cancelRunBtn.disabled = !hasRun || !running;
  }
  if (el.resumeRunBtn) {
    el.resumeRunBtn.disabled = !hasRun || running || Boolean(state.runSubmitting);
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
  if (answers.confirm_run !== undefined) {
    delete answers.confirm_run;
  }
  if ((mode === "pipeline" || mode === "workflow") && isAnswerMissing(answers.rfd3_input_pdb)) {
    delete answers.rfd3_contig;
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
      "rfd3_max_return_designs",
      "diffdock_ligand_smiles",
      "diffdock_ligand_sdf",
      "design_chains",
      "fixed_positions_extra",
      "pdb_strip_nonpositive_resseq",
      "wt_compare",
      "mask_consensus_apply",
      "ligand_mask_use_original_target",
      "bioemu_use",
      "bioemu_num_samples",
      "bioemu_max_return_structures",
      "af2_max_candidates_per_tier",
      "af2_plddt_cutoff",
      "af2_rmsd_cutoff",
      "af2_provider",
      "novelty_enabled",
      "num_seq_per_tier",
      "start_from",
      "stop_after",
    ],
    workflow: [
      "target_fasta",
      "target_pdb",
      "rfd3_input_pdb",
      "rfd3_contig",
      "rfd3_max_return_designs",
      "design_chains",
      "fixed_positions_extra",
      "pdb_strip_nonpositive_resseq",
      "wt_compare",
      "mask_consensus_apply",
      "ligand_mask_use_original_target",
      "bioemu_num_samples",
      "bioemu_max_return_structures",
      "af2_max_candidates_per_tier",
      "af2_plddt_cutoff",
      "af2_rmsd_cutoff",
      "af2_provider",
      "num_seq_per_tier",
      "bioemu_use",
      "novelty_enabled",
      "start_from",
      "stop_after",
    ],
    bioemu: [
      "target_fasta",
      "target_pdb",
      "bioemu_use",
      "bioemu_num_samples",
      "bioemu_max_return_structures",
    ],
    rfd3: ["rfd3_input_pdb", "rfd3_contig", "rfd3_max_return_designs", "pdb_strip_nonpositive_resseq"],
    msa: ["target_fasta", "target_pdb", "pdb_strip_nonpositive_resseq"],
    design: [
      "target_fasta",
      "target_pdb",
      "design_chains",
      "pdb_strip_nonpositive_resseq",
      "bioemu_use",
      "bioemu_num_samples",
      "bioemu_max_return_structures",
    ],
    soluprot: [
      "target_fasta",
      "target_pdb",
      "design_chains",
      "pdb_strip_nonpositive_resseq",
      "bioemu_use",
      "bioemu_num_samples",
      "bioemu_max_return_structures",
    ],
    af2: ["target_fasta", "target_pdb", "af2_provider"],
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

function buildRoutedForMode(mode) {
  if (mode === "pipeline") return { stop_after: "novelty", novelty_enabled: true };
  if (mode === "rfd3") return { stop_after: "rfd3" };
  if (mode === "bioemu") return { stop_after: "bioemu", bioemu_use: true };
  if (mode === "msa") return { stop_after: "msa" };
  if (mode === "design") return { stop_after: "design", bioemu_use: true };
  if (mode === "soluprot") return { stop_after: "soluprot", bioemu_use: true };
  if (mode === "af2") return { stop_after: "af2" };
  return {};
}

function mergeRoutedWithMode(mode, routed) {
  const base = buildRoutedForMode(mode);
  const merged = { ...base, ...(routed || {}) };
  if (mode && mode !== "pipeline" && base.stop_after) {
    merged.stop_after = base.stop_after;
  }
  return merged;
}

function withWorkflowDerivedAnswers(baseAnswers) {
  const answers = { ...(baseAnswers || {}) };
  const workflow = buildWorkflowPlanFromDesigner();
  answers.start_from = workflow.start;
  answers.stop_after = workflow.stopAfter;
  answers.novelty_enabled = workflow.noveltyEnabled && workflow.stopAfter === "novelty";
  answers.bioemu_use = workflow.bioemuUse;
  return { answers, workflow };
}

function _formatList(label, items) {
  if (!items || items.length === 0) return null;
  const lines = [label + ":"];
  items.forEach((item) => {
    lines.push(`- ${item}`);
  });
  return lines.join("\n");
}

function _formatDetected(label, detected) {
  if (!detected || typeof detected !== "object") return null;
  const entries = Object.entries(detected).map(
    ([key, value]) => `${key}=${JSON.stringify(value)}`
  );
  return _formatList(label, entries);
}

function buildPromptPlan(plan, preflight, prompt) {
  const questions = [];
  const seen = new Set();
  const addQuestion = (q) => {
    const normalized = normalizeQuestion(q);
    if (!normalized || !normalized.id) return;
    if (seen.has(normalized.id)) return;
    questions.push(normalized);
    seen.add(normalized.id);
  };

  (plan?.questions || []).forEach(addQuestion);
  (preflight?.required_inputs || []).forEach((item) => {
    addQuestion({
      id: item?.id || "required_input",
      question: item?.message || "",
      required: item?.required !== false,
    });
  });

  addQuestion({ id: "confirm_run", required: true, default: true });

  return {
    routed_request: plan?.routed_request || {},
    questions,
    source: "prompt",
    allow_unfiltered_answers: true,
    prompt: prompt || "",
  };
}

async function runPreflight({ announce = true } = {}) {
  const prompt = el.promptInput.value.trim();
  const mode = state.runMode || "pipeline";
  const effectiveMode = mode === "workflow" ? "pipeline" : mode;
  const preflightModes = new Set(["pipeline", "workflow", "rfd3", "bioemu", "msa", "design", "soluprot"]);
  if (!preflightModes.has(mode)) {
    if (announce) {
      setMessage(t("preflight.unavailable", { mode: t(`mode.${mode}`) || mode }), "ai");
    }
    return { ok: false, preflight: null, plan: null };
  }
  let rawAnswers = buildAnswerPayload(mode);
  if (mode === "workflow") {
    rawAnswers = withWorkflowDerivedAnswers(rawAnswers).answers;
  }
  const answers = prompt ? rawAnswers : filterAnswersForMode(mode, rawAnswers);

  if (announce && prompt) {
    setMessage(prompt, "user");
  }

  let preflight = null;
  let plan = null;
  if (prompt) {
    try {
      plan = await apiCall("pipeline.plan_from_prompt", {
        prompt,
        target_fasta: answers.target_fasta || "",
        target_pdb: answers.target_pdb || "",
        rfd3_input_pdb: answers.rfd3_input_pdb || "",
        rfd3_contig: answers.rfd3_contig || "",
        diffdock_ligand_smiles: answers.diffdock_ligand_smiles || "",
        diffdock_ligand_sdf: answers.diffdock_ligand_sdf || "",
      });
    } catch (err) {
      if (announce) {
        setMessage(t("preflight.failed", { error: err.message }), "ai");
      }
    }
  }

  const routed = mergeRoutedWithMode(effectiveMode, plan?.routed_request || {});
  const args = buildRunArguments({
    prompt,
    routed,
    answers,
    runId: "",
  });
  delete args.run_id;

  try {
    preflight = await apiCall("pipeline.preflight", args);
  } catch (err) {
    if (announce) {
      setMessage(t("preflight.failed", { error: err.message }), "ai");
    }
    return { ok: false, preflight: null, plan: null };
  }

  if (prompt && plan) {
    const promptKey = prompt.trim();
    const samePrompt = state.plan?.source === "prompt" && state.plan?.prompt === promptKey;
    state.plan = buildPromptPlan(plan, preflight, promptKey);
    state.setupStepIndex = 0;
    if (!samePrompt) {
      state.answers.confirm_run = true;
    }
    renderQuestions(state.plan.questions || []);
  } else if (!prompt && state.plan?.source === "prompt") {
    state.plan = buildManualPlan(mode);
    renderQuestions(state.plan.questions || []);
  }

  if (announce && preflight) {
    const lines = [];
    lines.push(t("preflight.title") + ": " + (preflight.ok ? t("preflight.ok") : t("preflight.blocked")));

    const required = (preflight.required_inputs || []).map((item) => {
      if (!item || !item.message) return String(item.id || "required_input");
      const suffix = item.id ? ` (${item.id})` : "";
      return `${item.message}${suffix}`;
    });
    const requiredBlock = _formatList(t("preflight.required"), required);
    const errorBlock = _formatList(t("preflight.errors"), preflight.errors || []);
    const planWarnings = (plan?.errors || []).map((err) => `prompt: ${err}`);
    const warnBlock = _formatList(t("preflight.warnings"), [
      ...(preflight.warnings || []),
      ...planWarnings,
    ]);
    const detectBlock = _formatDetected(t("preflight.detected"), preflight.detected);

    if (requiredBlock) lines.push(requiredBlock);
    if (errorBlock) lines.push(errorBlock);
    if (warnBlock) lines.push(warnBlock);
    if (detectBlock) lines.push(detectBlock);

    if (plan) {
      const routedPairs = Object.entries(plan.routed_request || {}).map(
        ([key, value]) => `${key}=${JSON.stringify(value)}`
      );
      const routedBlock = _formatList(t("preflight.routed"), routedPairs);
      if (routedBlock) lines.push(routedBlock);

      const questions = (plan.questions || []).map((q) => {
        if (!q || !q.question) return null;
        return q.required ? `${q.question} (required)` : q.question;
      }).filter(Boolean);
      const qBlock = _formatList(t("preflight.questions"), questions);
      if (qBlock) lines.push(qBlock);
    }

    setMessage(lines.join("\n"), "ai");
  }

  return { ok: Boolean(preflight && preflight.ok), preflight, plan };
}

async function runPipeline() {
  if (state.runSubmitting || String(state.currentRunState || "").toLowerCase() === "running") {
    setMessage(t("run.alreadyRunning"), "ai");
    return;
  }
  if (!state.plan) return;
  const prompt = el.promptInput.value.trim();
  const mode = state.runMode || "pipeline";
  const effectiveMode = mode === "workflow" ? "pipeline" : mode;
  let rawAnswers = buildAnswerPayload(mode);
  let workflowPlan = null;
  if (mode === "workflow") {
    const derived = withWorkflowDerivedAnswers(rawAnswers);
    rawAnswers = derived.answers;
    workflowPlan = derived.workflow;
  }
  const answers = state.plan?.allow_unfiltered_answers ? rawAnswers : filterAnswersForMode(mode, rawAnswers);
  const prefix = state.user?.run_prefix || buildUserPrefix({ name: state.user?.username || "user" });
  const requestedStartFrom = normalizePipelineStage(answers.start_from, "");
  const canReuseRunId =
    (mode === "pipeline" || mode === "workflow") && requestedStartFrom && requestedStartFrom !== "msa";
  const selectedRunId = String(el.setupRunSelector?.value || state.currentRunId || "").trim();
  const runId = canReuseRunId && selectedRunId ? selectedRunId : createRunId(prefix);
  state.runModeById[runId] = mode;
  let args = {};
  let toolName = "pipeline.run";

  if (["pipeline", "workflow", "rfd3", "bioemu", "msa", "design", "soluprot"].includes(mode)) {
    const pre = await runPreflight({ announce: true });
    if (!pre.ok) {
      return;
    }
  }

  if (state.plan?.source === "prompt" && state.answers.confirm_run !== true) {
    setMessage(t("run.confirmRequired"), "ai");
    return;
  }

  if (["pipeline", "workflow", "rfd3", "bioemu", "msa", "design", "soluprot"].includes(mode)) {
    args = buildRunArguments({
      prompt,
      routed: mergeRoutedWithMode(effectiveMode, state.plan?.routed_request || {}),
      answers,
      runId,
    });
  } else if (mode === "af2") {
    toolName = "pipeline.af2_predict";
    args = {
      run_id: runId,
      target_fasta: answers.target_fasta || "",
      target_pdb: answers.target_pdb || "",
      af2_provider: normalizeAf2Provider(answers.af2_provider || "colabfold"),
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

  if (Object.prototype.hasOwnProperty.call(args, "af2_provider")) {
    setAf2ProviderForRun(runId, args.af2_provider);
  }
  if (toolName === "pipeline.run") {
    const progressContext = buildProgressContextFromRequestPayload(args);
    if (progressContext) state.progressContextByRunId[runId] = progressContext;
  }
  if (mode === "workflow" && workflowPlan) {
    state.workflowPlansByRunId[runId] = {
      nodes: workflowPlan.nodes,
      finalStopAfter: workflowPlan.finalStop,
      checkpointEnabled: workflowPlan.checkpointEnabled,
      checkpointStages: workflowPlan.checkpointStages,
      checkpointIndex: workflowPlan.checkpointIndex,
      graphEnabled: workflowPlan.graphEnabled,
      mmseqLoopEnabled: workflowPlan.mmseqLoopEnabled,
    };
    persistWorkflowPlans();
  }

  const modeLabel = t(`mode.${mode}`) || mode;
  setMessage(t("run.launching", { mode: modeLabel, id: runId }), "ai");
  setCurrentRunId(runId);
  state.autoAnalyzePendingByRunId[runId] = true;
  state.currentRunState = "running";
  state.runSubmitting = true;
  updateRunEligibility(state.plan?.questions || []);
  updateMonitorActionButtons();
  setActiveTab("monitor");

  try {
    const result = await apiCall(toolName, args);
    state.runModeById[result.run_id] = mode;
    state.autoAnalyzePendingByRunId[result.run_id] = true;
    if (toolName === "pipeline.run" && state.progressContextByRunId[runId] && runId !== result.run_id) {
      state.progressContextByRunId[result.run_id] = state.progressContextByRunId[runId];
    }
    if (mode === "workflow" && workflowPlan) {
      state.workflowPlansByRunId[result.run_id] = {
        nodes: workflowPlan.nodes,
        finalStopAfter: workflowPlan.finalStop,
        checkpointEnabled: workflowPlan.checkpointEnabled,
        checkpointStages: workflowPlan.checkpointStages,
        checkpointIndex: workflowPlan.checkpointIndex,
        graphEnabled: workflowPlan.graphEnabled,
        mmseqLoopEnabled: workflowPlan.mmseqLoopEnabled,
      };
      persistWorkflowPlans();
    }
    if (state.af2ProviderByRunId && state.af2ProviderByRunId[runId]) {
      setAf2ProviderForRun(result.run_id, state.af2ProviderByRunId[runId]);
    }
    setMessage(t("run.started", { id: result.run_id }), "ai");
    setCurrentRunId(result.run_id);
    await refreshRuns();
    ensureAutoPoll();
    await pollStatus(result.run_id);
  } catch (err) {
    state.currentRunState = "failed";
    state.autoAnalyzePendingByRunId[runId] = false;
    setMessage(t("run.failed", { error: err.message }), "ai");
  } finally {
    state.runSubmitting = false;
    updateRunEligibility(state.plan?.questions || []);
    updateMonitorActionButtons();
  }
}

function parseFallbackStatusFromEvents(eventsText, runId) {
  const raw = String(eventsText || "");
  if (!raw.trim()) return null;
  const lines = raw.split(/\r?\n/).filter((line) => line.trim());
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    try {
      const item = JSON.parse(lines[i]);
      if (!item || typeof item !== "object") continue;
      if (String(item.kind || "").toLowerCase() !== "status") continue;
      const stage = String(item.stage || "").trim() || "init";
      const stateText = String(item.state || "").trim() || "running";
      const updatedAt = String(item.updated_at || "").trim() || "-";
      const detailText =
        item.detail !== undefined && item.detail !== null ? String(item.detail).trim() : "events fallback";
      return {
        run_id: String(item.run_id || runId || "").trim() || String(runId || ""),
        stage,
        state: stateText,
        updated_at: updatedAt,
        detail: detailText || "events fallback",
      };
    } catch (err) {
      continue;
    }
  }
  return null;
}

function parseFallbackStatusFromRunpodJobs(jobsText, runId) {
  const raw = String(jobsText || "").trim();
  if (!raw) return null;
  let payload = null;
  try {
    payload = JSON.parse(raw);
  } catch (err) {
    return null;
  }
  if (!payload || typeof payload !== "object") return null;
  const jobs = payload.jobs;
  if (!jobs || typeof jobs !== "object") return null;
  const keys = Object.keys(jobs).filter((key) => String(key || "").trim());
  if (!keys.length) return null;
  const firstKey = keys[0];
  const inferredStage = String(firstKey).split(":")[0] || "runpod";
  return {
    run_id: String(runId || ""),
    stage: inferredStage,
    state: "running",
    updated_at: "-",
    detail: `runpod_jobs=${keys.length} (status.json missing)`,
  };
}

async function loadFallbackRunStatus(runId) {
  try {
    const events = await apiCall("pipeline.read_artifact", {
      run_id: runId,
      path: "events.jsonl",
      max_bytes: 512000,
    });
    const fallback = parseFallbackStatusFromEvents(events?.text, runId);
    if (fallback) return fallback;
  } catch (err) {
    // ignore missing events
  }
  try {
    const jobs = await apiCall("pipeline.read_artifact", {
      run_id: runId,
      path: "runpod_jobs.json",
      max_bytes: 256000,
    });
    const fallback = parseFallbackStatusFromRunpodJobs(jobs?.text, runId);
    if (fallback) return fallback;
  } catch (err) {
    // ignore missing runpod_jobs
  }
  return null;
}

async function pollStatus(runId) {
  try {
    const result = await apiCall("pipeline.status", { run_id: runId });
    if (!result.found) {
      const fallbackStatus = await loadFallbackRunStatus(runId);
      if (fallbackStatus) {
        updateRunInfo(fallbackStatus);
        const stageRaw = fallbackStatus.stage || "-";
        const stage = formatStatusStage(stageRaw);
        const stateText = fallbackStatus.state || "-";
        const key = `${stageRaw}|${stateText}`;
        if (key !== state.lastStatusKey) {
          state.lastStatusKey = key;
          setMessage(t("status.line", { stage, state: stateText }), "ai");
        }
      } else {
        updateRunInfo({ stage: "-", state: "not found", updated_at: "-" });
        const key = `not_found|${runId}`;
        if (key !== state.lastStatusKey) {
          state.lastStatusKey = key;
          setMessage(t("status.notFound", { id: runId }), "ai");
        }
      }
      return;
    }
    const mode = await ensureRunModeForRunId(runId, result.status);
    updateRunInfo({ ...(result.status || {}), _mode: mode });
    const stageRaw = result.status?.stage || "-";
    const stage = formatStatusStage(stageRaw);
    const stateText = result.status?.state || "-";
    const key = `${stageRaw}|${stateText}`;
    if (key !== state.lastStatusKey) {
      state.lastStatusKey = key;
      setMessage(t("status.line", { stage, state: stateText }), "ai");
    }
  } catch (err) {
    state.currentRunState = "";
    updateRunEligibility(state.plan?.questions || []);
    updateMonitorActionButtons();
    renderCopilotContext();
    setMessage(t("status.error", { error: err.message }), "ai");
  }
}

async function cancelCurrentRun() {
  const runId = state.currentRunId;
  if (!runId) {
    setMessage(t("export.selectRun"), "ai");
    return;
  }
  const ok = window.confirm(t("monitor.stopConfirm", { id: runId }));
  if (!ok) return;
  try {
    const result = await apiCall("pipeline.cancel_run", { run_id: runId });
    const count = Number(result.cancelled || 0);
    setMessage(t("monitor.stopSuccess", { id: runId, count }), "ai");
    await pollStatus(runId);
  } catch (err) {
    setMessage(t("monitor.stopFailed", { error: err.message }), "ai");
  }
}

async function resumeCurrentRun() {
  const runId = String(state.currentRunId || "").trim();
  if (!runId) {
    setMessage(t("export.selectRun"), "ai");
    return;
  }
  if (state.runSubmitting) {
    setMessage(t("run.alreadyRunning"), "ai");
    return;
  }

  try {
    const latest = await apiCall("pipeline.status", { run_id: runId });
    const isRunning = Boolean(
      latest?.found && String(latest?.status?.state || "").trim().toLowerCase() === "running"
    );
    if (isRunning) {
      setMessage(t("run.resume.running"), "ai");
      state.currentRunState = "running";
      updateMonitorActionButtons();
      return;
    }
  } catch (_err) {
    // Ignore transient status check failures and continue with request.json recovery.
  }

  setMessage(t("run.resume.loading", { id: runId }), "ai");
  let payload = null;
  try {
    const read = await apiCall("pipeline.read_artifact", {
      run_id: runId,
      path: "request.json",
      max_bytes: 2_000_000,
    });
    const raw = String(read?.text || "").trim();
    if (!raw) {
      setMessage(t("run.resume.noRequest"), "ai");
      return;
    }
    payload = JSON.parse(raw);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      setMessage(t("run.resume.badRequest"), "ai");
      return;
    }
  } catch (err) {
    const msg = String(err?.message || "");
    if (msg.includes("HTTP 400") || /not\s*found/i.test(msg)) {
      setMessage(t("run.resume.noRequest"), "ai");
      return;
    }
    if (/json/i.test(msg) || /unexpected token/i.test(msg)) {
      setMessage(t("run.resume.badRequest"), "ai");
      return;
    }
    setMessage(t("run.resume.failed", { error: err.message }), "ai");
    return;
  }

  const args = { ...payload, run_id: runId, force: false };
  if (!Object.prototype.hasOwnProperty.call(args, "auto_recover")) {
    args.auto_recover = true;
  }
  if (Object.prototype.hasOwnProperty.call(args, "af2_provider")) {
    const shouldRefresh = setAf2ProviderForRun(runId, args.af2_provider);
    if (shouldRefresh) refreshAf2ProviderLabels({ rerenderQuestions: true });
  }

  const inferredMode = inferRunModeFromRequestPayload(payload);
  if (inferredMode && PROGRESS_PLANS[inferredMode]) {
    state.runModeById[runId] = inferredMode;
  }
  const resumeProgressContext = buildProgressContextFromRequestPayload(args);
  if (resumeProgressContext) {
    state.progressContextByRunId[runId] = resumeProgressContext;
  }

  let resumeToolName = "pipeline.run";
  let resumeArgs = args;
  const isPipelineShapedRequest =
    Object.prototype.hasOwnProperty.call(payload, "num_seq_per_tier") ||
    Object.prototype.hasOwnProperty.call(payload, "novelty_target_db") ||
    Object.prototype.hasOwnProperty.call(payload, "rfd3_max_return_designs");
  if (inferredMode === "af2" && !isPipelineShapedRequest) {
    resumeToolName = "pipeline.af2_predict";
    resumeArgs = {
      run_id: runId,
      target_fasta: String(payload.target_fasta || ""),
      target_pdb: String(payload.target_pdb || ""),
      af2_provider: normalizeAf2Provider(payload.af2_provider || "colabfold"),
      af2_model_preset: String(payload.af2_model_preset || "auto"),
      af2_db_preset: String(payload.af2_db_preset || "full_dbs"),
      af2_max_template_date: String(payload.af2_max_template_date || "2020-05-14"),
      af2_extra_flags: payload.af2_extra_flags || undefined,
      dry_run: Boolean(payload.dry_run),
    };
  } else if (inferredMode === "diffdock") {
    resumeToolName = "pipeline.diffdock";
    resumeArgs = {
      run_id: runId,
      protein_pdb: String(payload.protein_pdb || payload.target_pdb || ""),
      diffdock_ligand_smiles: String(payload.diffdock_ligand_smiles || ""),
      diffdock_ligand_sdf: String(payload.diffdock_ligand_sdf || ""),
      diffdock_config: String(payload.diffdock_config || "default_inference_args.yaml"),
      diffdock_extra_args: payload.diffdock_extra_args || undefined,
      diffdock_cuda_visible_devices: payload.diffdock_cuda_visible_devices || undefined,
      dry_run: Boolean(payload.dry_run),
    };
  }

  setMessage(t("run.resume.starting", { id: runId }), "ai");
  state.runSubmitting = true;
  state.currentRunState = "running";
  state.autoAnalyzePendingByRunId[runId] = true;
  updateRunEligibility(state.plan?.questions || []);
  updateMonitorActionButtons();
  setActiveTab("monitor");

  try {
    const result = await apiCall(resumeToolName, resumeArgs);
    const resumedRunId = String(result?.run_id || runId).trim() || runId;
    state.autoAnalyzePendingByRunId[resumedRunId] = true;
    if (inferredMode && PROGRESS_PLANS[inferredMode]) {
      state.runModeById[resumedRunId] = inferredMode;
    }
    if (Object.prototype.hasOwnProperty.call(args, "af2_provider")) {
      setAf2ProviderForRun(resumedRunId, args.af2_provider);
    }
    setMessage(t("run.resume.started", { id: resumedRunId }), "ai");
    setCurrentRunId(resumedRunId);
    await refreshRuns();
    ensureAutoPoll();
    await pollStatus(resumedRunId);
    await refreshArtifacts();
    await refreshRunCompare();
    await refreshHitList();
  } catch (err) {
    state.currentRunState = "failed";
    state.autoAnalyzePendingByRunId[runId] = false;
    setMessage(t("run.resume.failed", { error: err.message }), "ai");
  } finally {
    state.runSubmitting = false;
    updateRunEligibility(state.plan?.questions || []);
    updateMonitorActionButtons();
  }
}

function getArtifactViewConfig(view = "monitor") {
  if (view === "analyze") {
    return {
      listEl: el.analyzeArtifactList,
      filterInputEl: el.analyzeArtifactFilter,
      stageFilterEl: el.analyzeArtifactStageFilter,
      tierFilterEl: el.analyzeArtifactTierFilter,
      typeFilterEl: el.analyzeArtifactTypeFilter,
      previewTarget: "analyze",
    };
  }
  return {
    listEl: el.artifactList,
    filterInputEl: el.artifactFilter,
    stageFilterEl: el.artifactStageFilter,
    tierFilterEl: el.artifactTierFilter,
    typeFilterEl: el.artifactTypeFilter,
    previewTarget: "monitor",
  };
}

function artifactFiltersForView(view = "monitor") {
  if (!state.artifactFiltersByView || typeof state.artifactFiltersByView !== "object") {
    state.artifactFiltersByView = {};
  }
  if (!state.artifactFiltersByView[view]) {
    state.artifactFiltersByView[view] = createArtifactFilterState();
  }
  return state.artifactFiltersByView[view];
}

function renderAllArtifactViews(items = state.artifacts) {
  renderArtifactFilters(items, "monitor");
  renderArtifacts(items, "monitor");
  renderArtifactFilters(items, "analyze");
  renderArtifacts(items, "analyze");
}

function bindArtifactFilterControls(view = "monitor") {
  const { filterInputEl, stageFilterEl, tierFilterEl, typeFilterEl } = getArtifactViewConfig(view);
  if (filterInputEl) {
    filterInputEl.addEventListener("input", () => {
      renderArtifacts(state.artifacts, view);
    });
  }
  if (stageFilterEl) {
    stageFilterEl.addEventListener("change", () => {
      artifactFiltersForView(view).stage = stageFilterEl.value || "all";
      renderArtifacts(state.artifacts, view);
    });
  }
  if (tierFilterEl) {
    tierFilterEl.addEventListener("change", () => {
      artifactFiltersForView(view).tier = tierFilterEl.value || "all";
      renderArtifacts(state.artifacts, view);
    });
  }
  if (typeFilterEl) {
    typeFilterEl.addEventListener("change", () => {
      artifactFiltersForView(view).type = typeFilterEl.value || "all";
      renderArtifacts(state.artifacts, view);
    });
  }
}

function renderArtifacts(list, view = "monitor") {
  const { listEl, filterInputEl, previewTarget } = getArtifactViewConfig(view);
  if (!listEl) return;
  const filters = artifactFiltersForView(view);
  const query = String(filterInputEl?.value || "")
    .trim()
    .toLowerCase();
  const stageFilter = filters.stage || "all";
  const tierFilter = filters.tier || "all";
  const typeFilter = filters.type || "all";

  listEl.innerHTML = "";
  const filtered = (list || []).filter((item) => {
    const path = String(item?.path || "");
    if (query && !path.toLowerCase().includes(query)) return false;
    const meta = artifactMetaForPath(path);
    const stage = meta.stage;
    if (stageFilter !== "all" && stage !== stageFilter) return false;
    const tier = meta.tier;
    if (tierFilter !== "all" && String(tier || "") !== String(tierFilter)) return false;
    const type = artifactTypeFromItem(item);
    if (typeFilter !== "all" && String(type || "") !== String(typeFilter)) return false;
    return true;
  });

  if (!filtered.length) {
    listEl.innerHTML = `<div class="placeholder">${t("artifact.none")}</div>`;
    return;
  }

  const groups = new Map();
  filtered.forEach((item) => {
    const stage = artifactMetaForPath(item.path).stage;
    if (!groups.has(stage)) groups.set(stage, []);
    groups.get(stage).push(item);
  });
  const orderedStages = ARTIFACT_STAGE_ORDER.filter((stage) => groups.has(stage));
  const extraStages = Array.from(groups.keys()).filter((s) => !orderedStages.includes(s)).sort();
  const stageList = [...orderedStages, ...extraStages];

  stageList.forEach((stage) => {
    const items = groups.get(stage) || [];
    items.sort((a, b) => String(a.path || "").localeCompare(String(b.path || "")));
    const group = document.createElement("div");
    group.className = "artifact-group";
    const header = document.createElement("div");
    header.className = "artifact-group-header";
    header.innerHTML = `
      <span class="artifact-group-title">${formatStageLabel(stage)}</span>
      <span class="artifact-group-count">${items.length}</span>
    `;
    const groupList = document.createElement("div");
    groupList.className = "artifact-group-list";
    items.forEach((item) => {
      const div = document.createElement("div");
      div.className = "artifact-item";
      const meta = artifactMetaForPath(item.path);
      const tier = meta.tier;
      const type = artifactTypeFromItem(item);
      const tierLabel = t("artifacts.filter.tier");
      const tags = [];
      tags.push(`<span class="stage-tag">${formatStageLabel(meta.stage)}</span>`);
      if (tier) {
        tags.push(`<span class="stage-tag tier-tag">${tierLabel} ${tier}</span>`);
      }
      if (type) {
        tags.push(`<span class="stage-tag type-tag">${String(type).toUpperCase()}</span>`);
      }
      const displayPath = escapeHtml(displayArtifactPath(item.path));
      div.innerHTML = `
        <span>${displayPath}</span>
        <span class="artifact-meta">${tags.join("")}</span>
      `;
      div.addEventListener("click", () => previewArtifact(item, { target: previewTarget }));
      groupList.appendChild(div);
    });
    group.appendChild(header);
    group.appendChild(groupList);
    listEl.appendChild(group);
  });
}

function resolveFilePreviewElement(target = "monitor") {
  if (target === "analyze") {
    return el.analyzeArtifactPreview || el.monitorArtifactPreview || null;
  }
  return el.monitorArtifactPreview || el.analyzeArtifactPreview || null;
}

function setFilePreviewPlaceholder(target = "monitor", key = "artifacts.preview.placeholder", params = {}) {
  const previewEl = resolveFilePreviewElement(target);
  if (!previewEl) return;
  previewEl.innerHTML = `<div class="placeholder">${t(key, params)}</div>`;
}

function syncAnalyzeArtifactSelection(path) {
  state.analyzeArtifactPath = String(path || "").trim();
}

async function previewArtifact(item, options = {}) {
  if (!state.currentRunId) return;
  if (item.type !== "file") return;
  const target = options?.target === "analyze" ? "analyze" : "monitor";
  const previewEl = resolveFilePreviewElement(target);
  if (!previewEl) return;
  const path = String(item.path || "");
  syncAnalyzeArtifactSelection(path);

  if (isStructurePath(path)) {
    try {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: state.currentRunId,
        path,
        max_bytes: 500000,
      });
      const format = /\.sdf$/i.test(path) ? "sdf" : "pdb";
      render3dModel(result.text || "", format, previewEl);
      if (!state.artifactCompareLeftPath) {
        state.artifactCompareLeftPath = path;
      } else if (!state.artifactCompareRightPath && state.artifactCompareLeftPath !== path) {
        state.artifactCompareRightPath = path;
      }
      renderArtifactCompareSelects();
    } catch (err) {
      setFilePreviewPlaceholder(target, "artifact.preview.failed", { error: err.message });
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
      previewEl.innerHTML = "";
      previewEl.appendChild(img);
    } catch (err) {
      setFilePreviewPlaceholder(target, "artifact.preview.failed", { error: err.message });
    }
    return;
  }

  if (isBinaryPath(path)) {
    setFilePreviewPlaceholder(target, "artifact.preview.binary", { path });
    return;
  }

  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: state.currentRunId,
      path,
      max_bytes: 200000,
    });
    const text = result.text || "";
    previewEl.innerHTML = `<pre>${escapeHtml(text)}</pre>`;
  } catch (err) {
    setFilePreviewPlaceholder(target, "artifact.preview.failed", { error: err.message });
  }
}

function artifactItemByPath(path) {
  const target = String(path || "").trim();
  if (!target) return null;
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  return artifacts.find((item) => String(item?.path || "") === target && item?.type === "file") || null;
}

async function previewAnalyzeSelectedArtifact() {
  const path = String(state.analyzeArtifactPath || "").trim();
  if (!path) {
    setFilePreviewPlaceholder("analyze", "analyze.files.placeholder");
    return;
  }
  const item = artifactItemByPath(path);
  if (!item) {
    setFilePreviewPlaceholder("analyze", "artifact.preview.binary", { path });
    return;
  }
  await previewArtifact(item, { target: "analyze" });
}

function updateReportArtifactLinks(text) {
  if (!el.reportArtifactLinks) return;
  const content = String(text || "");
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  if (!content.trim() || artifacts.length === 0) {
    el.reportArtifactLinks.innerHTML = `<div class="placeholder">${t(
      "artifact.references.none"
    )}</div>`;
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
    el.reportArtifactLinks.innerHTML = `<div class="placeholder">${t(
      "artifact.references.none"
    )}</div>`;
    return;
  }
  matches.sort((a, b) => String(a.path).localeCompare(String(b.path)));
  el.reportArtifactLinks.innerHTML = "";
  matches.forEach((item) => {
    const stage = artifactMetaForPath(item.path).stage;
    const link = document.createElement("button");
    link.type = "button";
    link.className = "report-link";
    link.innerHTML = `<span>${escapeHtml(displayArtifactPath(item.path))}</span><span class=\"stage-tag\">${escapeHtml(
      formatStageLabel(stage)
    )}</span>`;
    link.addEventListener("click", () => previewArtifact(item, { target: "analyze" }));
    el.reportArtifactLinks.appendChild(link);
  });
}

function render3dModel(text, format, previewEl) {
  if (!previewEl) return;
  if (!window.$3Dmol) {
    previewEl.innerHTML = `<div class="placeholder">${t(
      "artifact.preview.unavailable"
    )}</div>`;
    return;
  }
  const container = document.createElement("div");
  container.className = "viewer3d";
  previewEl.innerHTML = "";
  previewEl.appendChild(container);
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

function formatMetricValue(value, digits = 2, signed = false) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  const text = value.toFixed(digits);
  if (signed && value > 0) return `+${text}`;
  return text;
}

function formatPercentValue(value, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatWtDifference(row) {
  const diffCount = Number(row?.wt_diff_count);
  const compareLen = Number(row?.wt_compare_len);
  let diffPct = Number(row?.wt_diff_pct);
  if (!Number.isFinite(diffPct)) {
    const diffRatio = Number(row?.wt_diff_ratio);
    if (Number.isFinite(diffRatio)) diffPct = diffRatio * 100;
  }
  if (!Number.isFinite(diffPct)) {
    const novelty = Number(row?.novelty);
    if (Number.isFinite(novelty)) diffPct = novelty * 100;
  }
  if (!Number.isFinite(diffPct)) {
    const identityPct =
      Number.isFinite(Number(row?.wt_identity_pct))
        ? Number(row.wt_identity_pct)
        : Number.isFinite(Number(row?.wt_identity))
          ? Number(row.wt_identity) * 100
          : null;
    if (Number.isFinite(identityPct)) diffPct = 100 - Number(identityPct);
  }
  const pctText = Number.isFinite(diffPct) ? `${Number(diffPct).toFixed(1)}%` : null;
  if (Number.isFinite(diffCount) && Number.isFinite(compareLen) && compareLen > 0) {
    if (pctText) return `${Math.max(0, Math.round(diffCount))}/${Math.round(compareLen)} (${pctText})`;
    return `${Math.max(0, Math.round(diffCount))}/${Math.round(compareLen)}`;
  }
  return pctText || "-";
}

function localizedYesNo(value) {
  const isKo = (state.lang || "en") === "ko";
  return value ? (isKo ? "예" : "yes") : isKo ? "아니오" : "no";
}

function sourceLabel(source) {
  if (source === "wt") return "WT";
  if (source === "input") return t("artifacts.preview.compare.refs.input");
  if (source === "working") return t("artifacts.preview.compare.refs.working");
  if (source === "rfd3") return "RFD3";
  if (source === "bioemu") return "BioEmu";
  return (state.lang || "en") === "ko" ? "기타" : "Other";
}

function normalizeSourceKey(source) {
  const raw = String(source || "")
    .trim()
    .toLowerCase();
  if (raw === "rfd3") return "rfd3";
  if (raw === "bioemu" || raw === "biomu") return "bioemu";
  if (raw === "wt" || raw === "wildtype") return "wt";
  if (raw === "input" || raw === "reference") return "input";
  if (raw === "working" || raw === "backbone") return "working";
  return "other";
}

function compareArtifactRoleKey(meta) {
  const raw = String(meta?.compareRole || "")
    .trim()
    .toLowerCase();
  if (
    [
      "input_reference",
      "working_backbone",
      "wt_colabfold",
      "backbone_snapshot",
      "af2_candidate",
      "source_output",
      "backbone_input_snapshot",
    ].includes(raw)
  ) {
    return raw;
  }
  return "structure_artifact";
}

function compareSourceKeyFromMeta(meta) {
  const role = compareArtifactRoleKey(meta);
  if (role === "wt_colabfold") return "wt";
  if (role === "input_reference") return "input";
  if (role === "working_backbone") return "working";
  const stage = String(meta?.stage || "")
    .trim()
    .toLowerCase();
  if (stage === "wt" || stage === "wt_af2") return "wt";
  const backboneSource = normalizeSourceKey(meta?.backboneSource);
  if (backboneSource !== "other") return backboneSource;
  const source = normalizeSourceKey(meta?.source);
  if (source !== "other") return source;
  if (stage === "rfd3") return "rfd3";
  if (stage === "bioemu") return "bioemu";
  return "other";
}

function formatCompareTierLabel(tier) {
  const text = String(tier || "").trim();
  if (!text) return "-";
  const num = Number(text);
  const normalized =
    Number.isFinite(num) && num > 1 ? (num / 100).toFixed(2) : Number.isFinite(num) ? num.toFixed(2) : text;
  return (state.lang || "en") === "ko" ? `티어 ${normalized}` : `Tier ${normalized}`;
}

function normalizeCompareTierKey(value) {
  const text = String(value ?? "")
    .trim();
  if (!text) return "";
  const num = Number(text);
  if (!Number.isFinite(num)) return text;
  return num > 1 ? String(Math.round(num)) : String(Math.round(num * 100));
}

function compareArtifactGroupKey(meta) {
  const raw = String(meta?.compareGroup || "")
    .trim()
    .toLowerCase();
  if (["references", "backbones", "af2_candidates", "source_outputs", "internal"].includes(raw)) {
    return raw;
  }
  return "other";
}

function compareArtifactGroupLabel(groupKey, provider = "") {
  const af2Provider = af2ProviderName(provider || currentRunAf2Provider(), state.lang || "en");
  if (groupKey === "references") return t("artifacts.preview.compare.group.references");
  if (groupKey === "backbones") return t("artifacts.preview.compare.group.backbones");
  if (groupKey === "af2_candidates") return t("artifacts.preview.compare.group.af2", { af2Provider });
  if (groupKey === "source_outputs") return t("artifacts.preview.compare.group.source");
  return t("artifacts.preview.compare.group.other");
}

function compareArtifactRoleLabel(meta, provider = "") {
  const role = compareArtifactRoleKey(meta);
  const af2Provider = af2ProviderName(provider || currentRunAf2Provider(), state.lang || "en");
  if (role === "af2_candidate") return t("artifacts.preview.compare.role.af2_candidate", { af2Provider });
  const key =
    role === "backbone_input_snapshot" ? "structure_artifact" : role || "structure_artifact";
  return t(`artifacts.preview.compare.role.${key}`);
}

function shouldHideFromCompareStudio(item) {
  const path = String(item?.path || "");
  const meta = artifactMetaForPath(path);
  const normalized = String(meta?.normalizedPath || "").trim();
  if (compareArtifactGroupKey(meta) === "internal") return true;
  if (normalized === "rfd3/selected.pdb") return true;
  return false;
}

function compareSourceOrder(sourceKey) {
  if (sourceKey === "input") return 0;
  if (sourceKey === "working") return 1;
  if (sourceKey === "wt") return 2;
  if (sourceKey === "rfd3") return 3;
  if (sourceKey === "bioemu") return 4;
  return 9;
}

function compareRoleOrder(roleKey) {
  if (roleKey === "input_reference") return 0;
  if (roleKey === "working_backbone") return 1;
  if (roleKey === "wt_colabfold") return 2;
  if (roleKey === "backbone_snapshot") return 3;
  if (roleKey === "af2_candidate") return 4;
  if (roleKey === "source_output") return 5;
  return 9;
}

function compareGroupOrder(groupKey) {
  if (groupKey === "references") return 0;
  if (groupKey === "backbones") return 1;
  if (groupKey === "af2_candidates") return 2;
  if (groupKey === "source_outputs") return 3;
  return 9;
}

function compareStructureItemSort(left, right) {
  const leftPath = String(left?.path || "");
  const rightPath = String(right?.path || "");
  const leftMeta = artifactMetaForPath(leftPath);
  const rightMeta = artifactMetaForPath(rightPath);
  const groupDelta =
    compareGroupOrder(compareArtifactGroupKey(leftMeta)) - compareGroupOrder(compareArtifactGroupKey(rightMeta));
  if (groupDelta !== 0) return groupDelta;
  const roleDelta = compareRoleOrder(compareArtifactRoleKey(leftMeta)) - compareRoleOrder(compareArtifactRoleKey(rightMeta));
  if (roleDelta !== 0) return roleDelta;
  const sourceDelta =
    compareSourceOrder(compareSourceKeyFromMeta(leftMeta)) - compareSourceOrder(compareSourceKeyFromMeta(rightMeta));
  if (sourceDelta !== 0) return sourceDelta;
  const leftTier = Number(leftMeta?.tier);
  const rightTier = Number(rightMeta?.tier);
  if (Number.isFinite(leftTier) && Number.isFinite(rightTier) && leftTier !== rightTier) return leftTier - rightTier;
  return leftPath.localeCompare(rightPath);
}

function collectCompareStructureItems(items = state.artifacts) {
  return (Array.isArray(items) ? items : [])
    .filter((item) => isStructureArtifactItem(item))
    .filter((item) => !shouldHideFromCompareStudio(item))
    .sort(compareStructureItemSort);
}

function findCompareItem(structureItems, predicate) {
  return (Array.isArray(structureItems) ? structureItems : []).find((item) => predicate(item, artifactMetaForPath(item?.path)));
}

function resolveCompareReferenceItems(structureItems) {
  const items = Array.isArray(structureItems) ? structureItems : [];
  const input = findCompareItem(items, (_item, meta) => compareArtifactRoleKey(meta) === "input_reference");
  const working = findCompareItem(items, (_item, meta) => compareArtifactRoleKey(meta) === "working_backbone");
  const wt = findCompareItem(items, (_item, meta) => compareArtifactRoleKey(meta) === "wt_colabfold");
  const rfd3Backbone =
    findCompareItem(
      items,
      (_item, meta) =>
        compareArtifactRoleKey(meta) === "backbone_snapshot" && compareSourceKeyFromMeta(meta) === "rfd3"
    ) ||
    findCompareItem(
      items,
      (_item, meta) => compareArtifactRoleKey(meta) === "source_output" && compareSourceKeyFromMeta(meta) === "rfd3"
    );
  const bioemuBackbone =
    findCompareItem(
      items,
      (_item, meta) =>
        compareArtifactRoleKey(meta) === "backbone_snapshot" && compareSourceKeyFromMeta(meta) === "bioemu"
    ) ||
    findCompareItem(
      items,
      (_item, meta) => compareArtifactRoleKey(meta) === "source_output" && compareSourceKeyFromMeta(meta) === "bioemu"
    );
  return {
    input,
    working,
    wt,
    rfd3Backbone,
    bioemuBackbone,
  };
}

function buildArtifactCompareOptionLabel(path, meta = artifactMetaForPath(path)) {
  const parts = [compareArtifactRoleLabel(meta)];
  const sourceKey = compareSourceKeyFromMeta(meta);
  const roleKey = compareArtifactRoleKey(meta);
  const addSource = sourceKey !== "other" && !["input", "working", "wt"].includes(sourceKey);
  if (addSource) parts.push(sourceLabel(sourceKey));
  if (meta?.tier) parts.push(formatCompareTierLabel(meta.tier));
  if (meta?.backboneId && ["backbone_snapshot", "af2_candidate", "source_output"].includes(roleKey)) {
    parts.push(displayArtifactPath(meta.backboneId));
  }
  return `${parts.join(" · ")} · ${displayArtifactPath(path)}`;
}

function formatPassRate(sourceBucket) {
  const total = Number(sourceBucket?.soluprot_total || 0);
  const passed = Number(sourceBucket?.soluprot_passed || 0);
  if (total <= 0) return "-";
  const rate = (passed / total) * 100.0;
  return `${passed}/${total} (${rate.toFixed(1)}%)`;
}

function comparisonSummaryHasData(summary) {
  if (!summary || typeof summary !== "object") return false;
  const wt = summary?.wt_vs_design && typeof summary.wt_vs_design === "object" ? summary.wt_vs_design : {};
  const source =
    summary?.source_compare && typeof summary.source_compare === "object" ? summary.source_compare : {};
  const funnelOverall =
    summary?.funnel && typeof summary.funnel === "object" && summary.funnel.overall
      ? summary.funnel.overall
      : null;
  const wtKeys = ["soluprot", "plddt", "rmsd"];
  const hasWt = wtKeys.some((key) => {
    const metric = wt[key];
    return (
      metric &&
      typeof metric === "object" &&
      ((typeof metric.wt === "number" && Number.isFinite(metric.wt)) ||
        (typeof metric.design_median === "number" && Number.isFinite(metric.design_median))
    ));
  });
  if (hasWt) return true;
  const hasSource = ["rfd3", "bioemu", "other"].some((key) => {
    const bucket = source[key];
    if (!bucket || typeof bucket !== "object") return false;
    return (
      Number(bucket.backbone_count || 0) > 0 ||
      Number(bucket.soluprot_total || 0) > 0 ||
      Number(bucket.af2_candidate_total || 0) > 0 ||
      Number(bucket.af2_selected_total || 0) > 0
    );
  });
  if (hasSource) return true;
  if (funnelOverall && typeof funnelOverall === "object") {
    return (
      Number(funnelOverall.backbone_count || 0) > 0 ||
      Number(funnelOverall.soluprot_total || 0) > 0 ||
      Number(funnelOverall.af2_candidate_total || 0) > 0
    );
  }
  return false;
}

function parseNumberOrNull(raw) {
  if (raw === null || raw === undefined) return null;
  const text = String(raw).trim();
  if (!text || text === "-") return null;
  const matched = text.match(/[+-]?\d+(?:\.\d+)?/);
  if (!matched) return null;
  const num = Number(matched[0]);
  return Number.isFinite(num) ? num : null;
}

function parsePassStat(raw) {
  const text = String(raw || "");
  const matched = text.match(/(\d+)\s*\/\s*(\d+)/);
  if (!matched) return { passed: 0, total: 0, passRate: null };
  const passed = Number(matched[1] || 0);
  const total = Number(matched[2] || 0);
  return {
    passed,
    total,
    passRate: total > 0 ? passed / total : null,
  };
}

function medianFallbackBySource(rows = state.hitListRows) {
  const buckets = {
    rfd3: { plddt: [], rmsd: [] },
    bioemu: { plddt: [], rmsd: [] },
    other: { plddt: [], rmsd: [] },
  };
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const key = normalizeSourceKey(row?.source);
    if (!Object.prototype.hasOwnProperty.call(buckets, key)) return;
    const plddt = finiteNumber(row?.plddt);
    const rmsd = finiteNumber(row?.rmsd);
    if (plddt !== null) buckets[key].plddt.push(plddt);
    if (rmsd !== null) buckets[key].rmsd.push(rmsd);
  });
  const out = {};
  ["rfd3", "bioemu", "other"].forEach((key) => {
    out[key] = {
      plddt_median: buckets[key].plddt.length ? percentileValue(buckets[key].plddt, 0.5) : null,
      rmsd_median: buckets[key].rmsd.length ? percentileValue(buckets[key].rmsd, 0.5) : null,
    };
  });
  return out;
}

function comparisonSummaryNeedsMedianBackfill(summary) {
  if (!summary || typeof summary !== "object") return false;
  const version = Number(summary.version || 0);
  if (Number.isFinite(version) && version >= 3) return false;
  const source = summary.source_compare && typeof summary.source_compare === "object" ? summary.source_compare : {};
  const sourceRows = Object.values(source).filter((row) => row && typeof row === "object");
  if (
    sourceRows.some(
      (row) =>
        Number(row.af2_candidate_total || 0) > 0 &&
        (finiteNumber(row.plddt_median) === null || finiteNumber(row.rmsd_median) === null)
    )
  ) {
    return true;
  }
  return false;
}

function comparisonSummaryFromReportPayload(payload) {
  const summaryFromApi =
    payload?.comparison_summary && typeof payload.comparison_summary === "object" ? payload.comparison_summary : null;
  if (summaryFromApi) return summaryFromApi;
  return parseComparisonSummaryFromReportText(payload?.report || payload?.report_ko || "");
}

function parseComparisonSummaryFromReportText(reportText) {
  const text = String(reportText || "");
  if (!text.trim()) return null;
  const summary = {
    version: 1,
    generated_at: null,
    wt_compare_enabled: false,
    wt_vs_design: {
      soluprot: {},
      plddt: {},
      rmsd: {},
    },
    source_compare: {},
  };
  let hasAny = false;

  const enabledMatch = text.match(/(?:- Enabled:|- 사용 여부:)\s*(yes|no)/i);
  if (enabledMatch) {
    summary.wt_compare_enabled = String(enabledMatch[1] || "").toLowerCase() === "yes";
    hasAny = true;
  }

  const wtSolMatch = text.match(/WT SoluProt:\s*score=([+-]?\d+(?:\.\d+)?)/i);
  if (wtSolMatch) {
    summary.wt_vs_design.soluprot.wt = parseNumberOrNull(wtSolMatch[1]);
    hasAny = true;
  }
  const designSolMatch = text.match(
    /Designs SoluProt:\s*median=([+-]?\d+(?:\.\d+)?).*?\((\d+)\s*\/\s*(\d+)\)/i
  );
  if (designSolMatch) {
    const median = parseNumberOrNull(designSolMatch[1]);
    const passed = Number(designSolMatch[2] || 0);
    const total = Number(designSolMatch[3] || 0);
    summary.wt_vs_design.soluprot.design_median = median;
    summary.wt_vs_design.soluprot.design_passed = passed;
    summary.wt_vs_design.soluprot.design_total = total;
    summary.wt_vs_design.soluprot.design_pass_rate = total > 0 ? passed / total : null;
    hasAny = true;
  }
  const deltaSolMatch = text.match(/ΔSoluProt\s*\(median\s*-\s*WT\):\s*([+-]?\d+(?:\.\d+)?)/i);
  if (deltaSolMatch) {
    summary.wt_vs_design.soluprot.delta_design_minus_wt = parseNumberOrNull(deltaSolMatch[1]);
    hasAny = true;
  }

  const wtAf2Match = text.match(
    /WT (?:AF2|AlphaFold2|ColabFold):\s*pLDDT=([+-]?\d+(?:\.\d+)?|-)\s+RMSD=([+-]?\d+(?:\.\d+)?|-)/i
  );
  if (wtAf2Match) {
    summary.wt_vs_design.plddt.wt = parseNumberOrNull(wtAf2Match[1]);
    summary.wt_vs_design.rmsd.wt = parseNumberOrNull(wtAf2Match[2]);
    hasAny = true;
  }

  const designPlddtMatch = text.match(
    /Designs (?:AF2|AlphaFold2|ColabFold) pLDDT:\s*median=([+-]?\d+(?:\.\d+)?).*?\(n=(\d+)\)/i
  );
  if (designPlddtMatch) {
    summary.wt_vs_design.plddt.design_median = parseNumberOrNull(designPlddtMatch[1]);
    summary.wt_vs_design.plddt.design_total = Number(designPlddtMatch[2] || 0);
    hasAny = true;
  }
  const deltaPlddtMatch = text.match(/ΔpLDDT\s*\(median\s*-\s*WT\):\s*([+-]?\d+(?:\.\d+)?)/i);
  if (deltaPlddtMatch) {
    summary.wt_vs_design.plddt.delta_design_minus_wt = parseNumberOrNull(deltaPlddtMatch[1]);
    hasAny = true;
  }

  const designRmsdMatch = text.match(/Designs RMSD:\s*median=([+-]?\d+(?:\.\d+)?).*?\)/i);
  if (designRmsdMatch) {
    summary.wt_vs_design.rmsd.design_median = parseNumberOrNull(designRmsdMatch[1]);
    const selectedN = text.match(/Designs (?:AF2|AlphaFold2|ColabFold) pLDDT:.*?\(n=(\d+)\)/i);
    if (selectedN) {
      summary.wt_vs_design.rmsd.design_total = Number(selectedN[1] || 0);
    }
    hasAny = true;
  }
  const deltaRmsdMatch = text.match(/ΔRMSD\s*\(median\s*-\s*WT\):\s*([+-]?\d+(?:\.\d+)?)/i);
  if (deltaRmsdMatch) {
    summary.wt_vs_design.rmsd.delta_design_minus_wt = parseNumberOrNull(deltaRmsdMatch[1]);
    hasAny = true;
  }

  const rows = text.split(/\r?\n/);
  rows.forEach((line) => {
    const trimmed = String(line || "").trim();
    if (!trimmed.startsWith("|")) return;
    const parts = trimmed
      .split("|")
      .slice(1, -1)
      .map((item) => String(item || "").trim());
    if (parts.length < 7) return;
    const sourceLabelRaw = String(parts[0] || "").trim().toLowerCase();
    if (!["rfd3", "bioemu", "other", "기타"].includes(sourceLabelRaw)) return;
    const key = sourceLabelRaw === "rfd3" ? "rfd3" : sourceLabelRaw === "bioemu" ? "bioemu" : "other";
    const backboneCount = Number(parseNumberOrNull(parts[1]) || 0);
    const pass = parsePassStat(parts[2]);
    const af2Stat = parsePassStat(parts[4]);
    const af2Count = af2Stat.passed > 0 || af2Stat.total > 0 ? af2Stat.passed : Number(parseNumberOrNull(parts[4]) || 0);
    summary.source_compare[key] = {
      backbone_count: backboneCount,
      soluprot_total: pass.total,
      soluprot_passed: pass.passed,
      soluprot_pass_rate: pass.passRate,
      soluprot_median: parseNumberOrNull(parts[3]),
      af2_selected_total: af2Count,
      af2_candidate_total: af2Stat.total > 0 ? af2Stat.total : null,
      plddt_median: parseNumberOrNull(parts[5]),
      rmsd_median: parseNumberOrNull(parts[6]),
    };
    hasAny = true;
  });

  return hasAny ? summary : null;
}

function buildComparisonDetailMarkdown(summary, runId) {
  const lines = [];
  lines.push(`# ${t("artifacts.compare.detailsTitle")}: ${runId || "-"}`);
  lines.push("");

  const wt = summary?.wt_vs_design && typeof summary.wt_vs_design === "object" ? summary.wt_vs_design : {};
  const funnel =
    summary?.funnel && typeof summary.funnel === "object" ? summary.funnel : { overall: {}, by_source: {} };
  const source =
    summary?.source_compare && typeof summary.source_compare === "object" ? summary.source_compare : {};
  const tierRows = Array.isArray(summary?.tier_compare) ? summary.tier_compare : [];
  const distributions =
    summary?.distributions && typeof summary.distributions === "object" ? summary.distributions : {};
  const diversity = summary?.diversity && typeof summary.diversity === "object" ? summary.diversity : {};
  const af2Provider = currentRunAf2Provider(runId);

  lines.push("## WT vs Design");
  const wtRows = [
    { key: "soluprot", label: "SoluProt", digits: 3 },
    { key: "plddt", label: "pLDDT", digits: 1 },
    { key: "rmsd", label: "RMSD", digits: 2 },
  ];
  lines.push("| Metric | WT | Design median | Delta |");
  lines.push("|---|---:|---:|---:|");
  wtRows.forEach((row) => {
    const metric = wt[row.key] && typeof wt[row.key] === "object" ? wt[row.key] : {};
    lines.push(
      `| ${row.label} | ${formatMetricValue(metric.wt, row.digits)} | ${formatMetricValue(metric.design_median, row.digits)} | ${formatMetricValue(metric.delta_design_minus_wt, row.digits, true)} |`
    );
  });
  lines.push("");

  const overall = funnel?.overall && typeof funnel.overall === "object" ? funnel.overall : {};
  lines.push("## Funnel");
  lines.push(
    `- ${t("artifacts.compare.funnelBackbone")}: ${Number(overall.backbone_count || 0)}`
  );
  lines.push(
    `- ${t("artifacts.compare.funnelSoluprot")}: ${Number(overall.soluprot_passed || 0)}/${Number(overall.soluprot_total || 0)} (${formatPercentValue(overall.soluprot_pass_rate)})`
  );
  lines.push(
    `- ${t("artifacts.compare.funnelAf2", { af2Provider: af2ProviderName(af2Provider) })}: ${Number(overall.af2_selected_total || 0)}/${Number(overall.af2_candidate_total || 0)} (${formatPercentValue(overall.af2_pass_rate)})`
  );
  lines.push(
    `- ${t("artifacts.compare.funnelRetain")}: SoluProt=${formatPercentValue(overall.retention_backbone_to_soluprot_passed)}, ${af2ProviderName(af2Provider)}=${formatPercentValue(overall.retention_backbone_to_af2_selected)}`
  );
  lines.push("");

  lines.push("## Source Compare");
  lines.push(
    `| Source | Backbones | SoluProt pass | Median SoluProt | ${af2ProviderPassLabel(af2Provider)} | Median pLDDT | Median RMSD |`
  );
  lines.push("|---|---:|---:|---:|---:|---:|---:|");
  const metricFallback = medianFallbackBySource();
  ["rfd3", "bioemu", "other"].forEach((key) => {
    const bucket = source[key] && typeof source[key] === "object" ? source[key] : null;
    if (!bucket) return;
    const fallback = metricFallback[key] && typeof metricFallback[key] === "object" ? metricFallback[key] : {};
    const plddtMedian = finiteNumber(bucket.plddt_median) ?? finiteNumber(fallback.plddt_median);
    const rmsdMedian = finiteNumber(bucket.rmsd_median) ?? finiteNumber(fallback.rmsd_median);
    lines.push(
      `| ${sourceLabel(key)} | ${Number(bucket.backbone_count || 0)} | ${Number(bucket.soluprot_passed || 0)}/${Number(bucket.soluprot_total || 0)} (${formatPercentValue(bucket.soluprot_pass_rate)}) | ${formatMetricValue(bucket.soluprot_median, 3)} | ${Number(bucket.af2_selected_total || 0)}/${Number(bucket.af2_candidate_total || 0)} (${formatPercentValue(bucket.af2_pass_rate)}) | ${formatMetricValue(plddtMedian, 1)} | ${formatMetricValue(rmsdMedian, 2)} |`
    );
  });
  lines.push("");

  if (tierRows.length) {
    lines.push("## Tier Compare");
    lines.push(
      `| Tier | Designs | SoluProt pass | ${af2ProviderPassLabel(af2Provider)} | Median pLDDT | Median RMSD |`
    );
    lines.push("|---:|---:|---:|---:|---:|---:|");
    tierRows.forEach((row) => {
      if (!row || typeof row !== "object") return;
      lines.push(
        `| ${formatMetricValue(row.tier, 2)} | ${Number(row.design_total || 0)} | ${Number(row.soluprot_passed || 0)}/${Number(row.soluprot_total || 0)} (${formatPercentValue(row.soluprot_pass_rate)}) | ${Number(row.af2_selected_total || 0)}/${Number(row.af2_candidate_total || 0)} (${formatPercentValue(row.af2_pass_rate)}) | ${formatMetricValue(row.plddt_median, 1)} | ${formatMetricValue(row.rmsd_median, 2)} |`
      );
    });
    lines.push("");
  }

  lines.push("## Distribution");
  lines.push("| Metric | n | P10 | P25 | Median | P75 | P90 | IQR |");
  lines.push("|---|---:|---:|---:|---:|---:|---:|---:|");
  [
    ["SoluProt", distributions.soluprot],
    ["pLDDT", distributions.plddt],
    ["RMSD", distributions.rmsd],
  ].forEach(([name, stat]) => {
    const metric = stat && typeof stat === "object" ? stat : {};
    lines.push(
      `| ${name} | ${Number(metric.count || 0)} | ${formatMetricValue(metric.p10, 3)} | ${formatMetricValue(metric.p25, 3)} | ${formatMetricValue(metric.median, 3)} | ${formatMetricValue(metric.p75, 3)} | ${formatMetricValue(metric.p90, 3)} | ${formatMetricValue(metric.iqr, 3)} |`
    );
  });
  lines.push("");

  const wtIdentity = diversity?.wt_identity && typeof diversity.wt_identity === "object" ? diversity.wt_identity : {};
  const pairwise =
    diversity?.design_pairwise_identity && typeof diversity.design_pairwise_identity === "object"
      ? diversity.design_pairwise_identity
      : {};
  lines.push("## Sequence Diversity");
  lines.push(`- Unique design sequences: ${Number(diversity?.design_unique_sequences || 0)}`);
  lines.push(
    `- WT identity median: ${formatPercentValue(wtIdentity.median)} (best=${formatPercentValue(wtIdentity.best)}, worst=${formatPercentValue(wtIdentity.worst)}, n=${Number(wtIdentity.count || 0)})`
  );
  lines.push(
    `- Design pairwise identity median: ${formatPercentValue(pairwise.median)} (pairs=${Number(pairwise.evaluated_pairs || 0)}, sequences=${Number(pairwise.sequence_count || 0)}${pairwise.truncated ? ", truncated" : ""})`
  );
  lines.push("");

  return lines.join("\n");
}

function openComparisonDetailModal() {
  const summary = state.artifactComparison;
  const runId = String(state.currentRunId || "").trim();
  if (!runId || !summary || typeof summary !== "object") return;
  const markdown = buildComparisonDetailMarkdown(summary, runId);
  openReportModal(t("artifacts.compare.detailsTitle"), markdown, `comparison_${runId}.md`);
}

function renderArtifactComparisonSummary(summary) {
  if (!el.artifactComparisonSummary) return;
  if (!summary || typeof summary !== "object") {
    el.artifactComparisonSummary.innerHTML = `<div class="placeholder">${t(
      "artifacts.compare.placeholder"
    )}</div>`;
    renderCopilotContext();
    return;
  }

  const wt = summary?.wt_vs_design && typeof summary.wt_vs_design === "object" ? summary.wt_vs_design : {};
  const source =
    summary?.source_compare && typeof summary.source_compare === "object" ? summary.source_compare : {};
  const funnelOverall =
    summary?.funnel && typeof summary.funnel === "object" && summary.funnel.overall
      ? summary.funnel.overall
      : {};
  const wtEnabled = Boolean(summary?.wt_compare_enabled);
  const af2Provider = currentRunAf2Provider();

  const wtRows = [
    { key: "soluprot", label: "SoluProt", digits: 3 },
    { key: "plddt", label: "pLDDT", digits: 1 },
    { key: "rmsd", label: "RMSD", digits: 2 },
  ];
  const wtHasData = wtRows.some((row) => {
    const metric = wt[row.key] || {};
    return (
      (typeof metric?.wt === "number" && Number.isFinite(metric.wt)) ||
      (typeof metric?.design_median === "number" && Number.isFinite(metric.design_median))
    );
  });

  const sourceOrder = ["rfd3", "bioemu", "other"];
  const sourceRows = sourceOrder.filter((key) => {
    const bucket = source[key];
    if (!bucket || typeof bucket !== "object") return false;
    const backbone = Number(bucket.backbone_count || 0);
    const solTotal = Number(bucket.soluprot_total || 0);
    const af2 = Number(bucket.af2_selected_total || 0);
    return backbone > 0 || solTotal > 0 || af2 > 0;
  });
  const hasFunnel =
    Number(funnelOverall?.backbone_count || 0) > 0 ||
    Number(funnelOverall?.soluprot_total || 0) > 0 ||
    Number(funnelOverall?.af2_candidate_total || 0) > 0;

  if (!wtHasData && sourceRows.length === 0 && !hasFunnel) {
    el.artifactComparisonSummary.innerHTML = `<div class="placeholder">${t(
      "artifacts.compare.noData"
    )}</div>`;
    renderCopilotContext();
    return;
  }

  const wtTableRows = wtRows
    .map((row) => {
      const metric = wt[row.key] && typeof wt[row.key] === "object" ? wt[row.key] : {};
      const wtText = formatMetricValue(metric.wt, row.digits, false);
      const designText = formatMetricValue(metric.design_median, row.digits, false);
      const deltaText = formatMetricValue(metric.delta_design_minus_wt, row.digits, true);
      return `
        <tr>
          <th>${escapeHtml(row.label)}</th>
          <td>${escapeHtml(wtText)}</td>
          <td>${escapeHtml(designText)}</td>
          <td>${escapeHtml(deltaText)}</td>
        </tr>
      `;
    })
    .join("");

  const metricFallback = medianFallbackBySource();
  const sourceTableRows = sourceRows
    .map((key) => {
      const bucket = source[key] && typeof source[key] === "object" ? source[key] : {};
      const fallback = metricFallback[key] && typeof metricFallback[key] === "object" ? metricFallback[key] : {};
      const backbone = String(Number(bucket.backbone_count || 0));
      const passText = formatPassRate(bucket);
      const solMedian = formatMetricValue(bucket.soluprot_median, 3, false);
      const af2 = String(Number(bucket.af2_selected_total || 0));
      const plddt = formatMetricValue(
        finiteNumber(bucket.plddt_median) ?? finiteNumber(fallback.plddt_median),
        1,
        false
      );
      const rmsd = formatMetricValue(
        finiteNumber(bucket.rmsd_median) ?? finiteNumber(fallback.rmsd_median),
        2,
        false
      );
      return `
        <tr>
          <th>${escapeHtml(sourceLabel(key))}</th>
          <td>${escapeHtml(backbone)}</td>
          <td>${escapeHtml(passText)}</td>
          <td>${escapeHtml(solMedian)}</td>
          <td>${escapeHtml(af2)}</td>
          <td>${escapeHtml(plddt)}</td>
          <td>${escapeHtml(rmsd)}</td>
        </tr>
      `;
    })
    .join("");

  const wtNote = t("artifacts.compare.wtEnabled", { enabled: localizedYesNo(wtEnabled) });
  const funnelBackbones = Number(funnelOverall?.backbone_count || 0);
  const funnelSolTxt = `${Number(funnelOverall?.soluprot_passed || 0)}/${Number(
    funnelOverall?.soluprot_total || 0
  )} (${formatPercentValue(funnelOverall?.soluprot_pass_rate)})`;
  const funnelAf2Txt = `${Number(funnelOverall?.af2_selected_total || 0)}/${Number(
    funnelOverall?.af2_candidate_total || 0
  )} (${formatPercentValue(funnelOverall?.af2_pass_rate)})`;
  const funnelRetainTxt = `SoluProt ${formatPercentValue(
    funnelOverall?.retention_backbone_to_soluprot_passed
  )}, ${af2ProviderName(af2Provider)} ${formatPercentValue(funnelOverall?.retention_backbone_to_af2_selected)}`;
  el.artifactComparisonSummary.innerHTML = `
    ${
      hasFunnel
        ? `<div class="comparison-card">
      <h4>${escapeHtml(t("artifacts.compare.funnel"))}</h4>
      <div class="comparison-kpis">
        <div><span>${escapeHtml(t("artifacts.compare.funnelBackbone"))}</span><strong>${escapeHtml(String(funnelBackbones))}</strong></div>
        <div><span>${escapeHtml(t("artifacts.compare.funnelSoluprot"))}</span><strong>${escapeHtml(funnelSolTxt)}</strong></div>
        <div><span>${escapeHtml(t("artifacts.compare.funnelAf2", { af2Provider: af2ProviderName(af2Provider) }))}</span><strong>${escapeHtml(funnelAf2Txt)}</strong></div>
        <div><span>${escapeHtml(t("artifacts.compare.funnelRetain"))}</span><strong>${escapeHtml(funnelRetainTxt)}</strong></div>
      </div>
    </div>`
        : ""
    }
    ${
      wtHasData
        ? `<div class="comparison-card">
      <h4>${escapeHtml(t("artifacts.compare.wt"))}</h4>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>${escapeHtml(t("artifacts.compare.metric"))}</th>
            <th>${escapeHtml(t("artifacts.compare.wtValue"))}</th>
            <th>${escapeHtml(t("artifacts.compare.designMedian"))}</th>
            <th>${escapeHtml(t("artifacts.compare.delta"))}</th>
          </tr>
        </thead>
        <tbody>${wtTableRows}</tbody>
      </table>
      <div class="comparison-note">${escapeHtml(wtNote)}</div>
    </div>`
        : ""
    }
    ${
      sourceRows.length
        ? `<div class="comparison-card">
      <h4>${escapeHtml(t("artifacts.compare.source"))}</h4>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>${escapeHtml(t("artifacts.compare.sourceName"))}</th>
            <th>${escapeHtml(t("artifacts.compare.backbones"))}</th>
            <th>${escapeHtml(t("artifacts.compare.passRate"))}</th>
            <th>${escapeHtml(t("artifacts.compare.soluprotMedian"))}</th>
            <th>${escapeHtml(t("artifacts.compare.af2Selected", { af2Provider: af2ProviderName(af2Provider) }))}</th>
            <th>${escapeHtml(t("artifacts.compare.plddtMedian"))}</th>
            <th>${escapeHtml(t("artifacts.compare.rmsdMedian"))}</th>
          </tr>
        </thead>
        <tbody>${sourceTableRows}</tbody>
      </table>
    </div>`
        : ""
    }
  `;
  renderCopilotContext();
}

function buildCompletenessBadges(summary, fallbackCompleteness = null) {
  const source =
    summary?.source_compare && typeof summary.source_compare === "object" ? summary.source_compare : {};
  const funnel =
    summary?.funnel && typeof summary.funnel === "object" && summary.funnel.overall
      ? summary.funnel.overall
      : {};
  const fallback = fallbackCompleteness && typeof fallbackCompleteness === "object" ? fallbackCompleteness : {};

  const rfd3Backbones = Number(source?.rfd3?.backbone_count || 0);
  const bioemuBackbones = Number(source?.bioemu?.backbone_count || 0);
  const hasRfd3 = rfd3Backbones > 0 || Boolean(fallback.has_rfd3);
  const hasBioemu = bioemuBackbones > 0 || Boolean(fallback.has_bioemu);
  const wtEnabled =
    typeof summary?.wt_compare_enabled === "boolean"
      ? Boolean(summary.wt_compare_enabled)
      : Boolean(fallback.wt_compare_enabled);
  const af2Selected = Number(funnel?.af2_selected_total || fallback.af2_selected || 0);
  const af2Provider = currentRunAf2Provider();
  const af2ProviderText = af2ProviderName(af2Provider);

  const badges = [];
  badges.push({
    level: hasRfd3 ? "good" : "bad",
    text: t(hasRfd3 ? "monitor.completeness.badge.rfd3Ready" : "monitor.completeness.badge.rfd3Missing"),
  });
  badges.push({
    level: hasBioemu ? "good" : "warn",
    text: t(hasBioemu ? "monitor.completeness.badge.bioemuReady" : "monitor.completeness.badge.bioemuMissing"),
  });
  if (hasBioemu && !hasRfd3) {
    badges.push({ level: "warn", text: t("monitor.completeness.badge.bioemuOnly") });
  }
  badges.push({
    level: wtEnabled ? "good" : "warn",
    text: t(wtEnabled ? "monitor.completeness.badge.wtOn" : "monitor.completeness.badge.wtOff"),
  });
  badges.push({
    level: af2Selected > 0 ? "good" : "warn",
    text:
      af2Selected > 0
        ? t("monitor.completeness.badge.af2Some", { count: af2Selected, af2Provider: af2ProviderText })
        : t("monitor.completeness.badge.af2None", { af2Provider: af2ProviderText }),
  });
  return badges;
}

function renderMonitorCompleteness(summary = state.artifactComparison, fallback = null) {
  if (!el.monitorCompletenessBadges) return;
  if (!summary && !fallback) {
    el.monitorCompletenessBadges.innerHTML = `<span class="placeholder">${t(
      "monitor.completeness.placeholder"
    )}</span>`;
    return;
  }
  const badges = buildCompletenessBadges(summary || {}, fallback || state.hitListResult?.completeness || null);
  if (!badges.length) {
    el.monitorCompletenessBadges.innerHTML = `<span class="placeholder">${t(
      "monitor.completeness.placeholder"
    )}</span>`;
    return;
  }
  el.monitorCompletenessBadges.innerHTML = badges
    .map(
      (item) =>
        `<span class="completeness-badge ${escapeHtml(String(item.level || "warn"))}">${escapeHtml(
          String(item.text || "")
        )}</span>`
    )
    .join("");
}

async function readRunRequestPayload(runId) {
  const read = await apiCall("pipeline.read_artifact", {
    run_id: runId,
    path: "request.json",
    max_bytes: 2_000_000,
  });
  const raw = String(read?.text || "").trim();
  if (!raw) {
    throw new Error(t("run.resume.noRequest"));
  }
  const payload = JSON.parse(raw);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(t("run.resume.badRequest"));
  }
  return payload;
}

function renderWorkflowReviewPanel(status = state.lastRunStatus) {
  if (!el.workflowReviewPanel) return;
  const runId = String(state.currentRunId || "").trim();
  if (!runId) {
    el.workflowReviewPanel.classList.add("hidden");
    el.workflowReviewPanel.innerHTML = "";
    return;
  }
  const plan = workflowPlanForRunId(runId);
  if (!plan) {
    el.workflowReviewPanel.classList.add("hidden");
    el.workflowReviewPanel.innerHTML = "";
    return;
  }

  const runState = String(status?.state || state.currentRunState || "").trim().toLowerCase();
  const ctx = state.progressContextByRunId?.[runId] || {};
  const requestedStop = normalizePipelineStage(ctx.stopAfter || "", plan.finalStopAfter);
  const checkpointTarget = normalizePipelineStage(plan.nextCheckpointStage || "", "");
  const waitingForCheckpointRun =
    Boolean(checkpointTarget) &&
    normalizePipelineStage(requestedStop, "") === checkpointTarget &&
    normalizePipelineStage(plan.finalStopAfter, "") !== checkpointTarget;
  const canContinue =
    waitingForCheckpointRun &&
    (runState === "completed" || runState === "done") &&
    Boolean(plan.continueFrom);
  const finalReached =
    (runState === "completed" || runState === "done") &&
    (!waitingForCheckpointRun || normalizePipelineStage(requestedStop, "") === normalizePipelineStage(plan.finalStopAfter, ""));

  let statusLine = "";
  if (canContinue) {
    statusLine = t("monitor.workflow.ready", { stage: formatStageLabel(checkpointTarget) });
  } else if (finalReached) {
    statusLine = t("monitor.workflow.completed", { stage: formatStageLabel(plan.finalStopAfter) });
  } else if (waitingForCheckpointRun) {
    statusLine = t("monitor.workflow.waiting", { stage: formatStageLabel(checkpointTarget) });
  } else {
    statusLine = t("monitor.workflow.waiting", {
      stage: formatStageLabel(normalizePipelineStage(requestedStop || plan.finalStopAfter, "novelty")),
    });
  }

  const counts = workflowArtifactCountsForNodes(plan.nodes);
  const countValues = Object.values(counts);
  const hasCounts = countValues.some((value) => Number(value || 0) > 0);
  const chartSvg = hasCounts ? workflowCountsSvg(plan.nodes, counts) : "";
  const showCheckpointResults = plan.graphEnabled !== false;
  const checkpointLine = plan.checkpointStages.length
    ? `<div class="workflow-review-meta">${escapeHtml(
        t("monitor.workflow.checkpoints", {
          stages: plan.checkpointStages.map((stage) => formatStageLabel(stage)).join(" -> "),
        })
      )}</div>`
    : "";
  const nextStageLine = plan.continueFrom
    ? `<div class="workflow-review-meta">${escapeHtml(
        t("monitor.workflow.nextStage", { stage: formatStageLabel(plan.continueFrom) })
      )}</div>`
    : "";
  const finalStageLine = `<div class="workflow-review-meta">${escapeHtml(
    t("monitor.workflow.finalStage", { stage: formatStageLabel(plan.finalStopAfter) })
  )}</div>`;
  const rerunStageSet = new Set(["msa", ...(Array.isArray(plan.nodes) ? plan.nodes : [])]);
  const rerunStages = PIPELINE_STAGE_ORDER.filter((stage) => rerunStageSet.has(stage));
  const defaultRerunStage =
    checkpointTarget && rerunStages.includes(checkpointTarget)
      ? checkpointTarget
      : rerunStages[0] || "msa";
  const rerunControls =
    canContinue && plan.mmseqLoopEnabled
      ? `
      <label class="workflow-rerun-wrap">
        <span>${escapeHtml(t("monitor.workflow.rerunLabel"))}</span>
        <select data-workflow-rerun-stage>
          ${rerunStages
            .map(
              (stage) =>
                `<option value="${escapeAttr(stage)}"${stage === defaultRerunStage ? " selected" : ""}>${escapeHtml(
                  formatStageLabel(stage)
                )}</option>`
            )
            .join("")}
        </select>
      </label>
    `
      : "";
  const artifactGroups = workflowArtifactGroupsForReview();
  const artifactCount = artifactGroups.reduce((total, group) => total + (group?.items?.length || 0), 0);
  const resultsBody = artifactGroups.length
    ? artifactGroups
        .map((group) => {
          const stageLabel = group?.stage ? formatStageLabel(group.stage) : t("monitor.workflow.resultsUnknown");
          const items = Array.isArray(group?.items) ? group.items : [];
          const itemsHtml = items
            .map((item) => {
              const path = String(item?.path || "");
              const meta = artifactMetaForPath(path);
              const tier = meta.tier;
              const type = artifactTypeFromItem(item);
              const tierLabel = t("artifacts.filter.tier");
              const tags = [];
              if (tier) {
                tags.push(`<span class="stage-tag tier-tag">${escapeHtml(`${tierLabel} ${tier}`)}</span>`);
              }
              if (type) {
                tags.push(`<span class="stage-tag type-tag">${escapeHtml(String(type).toUpperCase())}</span>`);
              }
              const tagsHtml = tags.length ? `<span class="workflow-result-meta">${tags.join("")}</span>` : "";
              return `
                <button type="button" class="workflow-result-item" data-workflow-artifact-path="${escapeAttr(path)}">
                  <span class="workflow-result-path">${escapeHtml(path)}</span>
                  ${tagsHtml}
                </button>
              `;
            })
            .join("");
          return `
            <section class="workflow-result-group">
              <div class="workflow-result-group-head">
                <span>${escapeHtml(stageLabel || t("monitor.workflow.resultsUnknown"))}</span>
                <span>${items.length}</span>
              </div>
              <div class="workflow-result-group-list">${itemsHtml}</div>
            </section>
          `;
        })
        .join("")
    : `<div class="placeholder">${escapeHtml(t("monitor.workflow.resultsEmpty"))}</div>`;
  const resultsSection = showCheckpointResults
    ? `
      <div class="workflow-mini-chart">
        ${
          chartSvg
            ? chartSvg
            : `<div class="placeholder">${escapeHtml(t("monitor.workflow.chart.empty"))}</div>`
        }
      </div>
      <section class="workflow-results">
        <div class="workflow-results-head">
          <strong>${escapeHtml(t("monitor.workflow.resultsTitle"))}</strong>
          <span class="workflow-results-count">${artifactCount}</span>
        </div>
        <div class="workflow-results-hint">${escapeHtml(t("monitor.workflow.resultsHint", { count: artifactCount }))}</div>
        <div class="workflow-results-list">${resultsBody}</div>
      </section>
    `
    : `<div class="workflow-review-meta">${escapeHtml(t("monitor.workflow.resultsDisabled"))}</div>`;

  el.workflowReviewPanel.classList.remove("hidden");
  el.workflowReviewPanel.innerHTML = `
    <div class="workflow-review-head">
      <strong>${escapeHtml(t("monitor.workflow.title"))}</strong>
      <span class="workflow-review-state">${escapeHtml(statusLine)}</span>
    </div>
    ${checkpointLine}
    ${nextStageLine}
    ${finalStageLine}
    ${resultsSection}
    <div class="workflow-review-actions">
      ${
        canContinue
          ? `<button type="button" class="ghost" data-workflow-action="continue" data-run-id="${escapeAttr(
              runId
            )}">${escapeHtml(t("monitor.workflow.continue"))}</button>`
          : ""
      }
      ${rerunControls}
      ${
        canContinue && plan.mmseqLoopEnabled
          ? `<button type="button" class="ghost" data-workflow-action="rerun-stage" data-run-id="${escapeAttr(
              runId
            )}">${escapeHtml(t("monitor.workflow.rerunAction"))}</button>`
          : ""
      }
      <button type="button" class="ghost" data-workflow-action="analyze">${escapeHtml(
        t("monitor.workflow.openAnalyze")
      )}</button>
    </div>
  `;

  Array.from(el.workflowReviewPanel.querySelectorAll("[data-workflow-action]")).forEach((btn) => {
    const action = String(btn.getAttribute("data-workflow-action") || "").trim().toLowerCase();
    const actionRunId = String(btn.getAttribute("data-run-id") || runId).trim();
    btn.addEventListener("click", async () => {
      if (action === "continue") {
        await continueWorkflowRun(actionRunId);
        return;
      }
      if (action === "rerun-stage") {
        const select = el.workflowReviewPanel.querySelector("[data-workflow-rerun-stage]");
        const rerunStage = normalizePipelineStage(select?.value || "", "msa") || "msa";
        await rerunWorkflowStage(actionRunId, rerunStage);
        return;
      }
      if (action === "mmseq") {
        await rerunWorkflowMmseq(actionRunId);
        return;
      }
      if (action === "analyze") {
        setActiveTab("analyze");
      }
    });
  });
  Array.from(el.workflowReviewPanel.querySelectorAll("[data-workflow-artifact-path]")).forEach((btn) => {
    btn.addEventListener("click", async () => {
      const path = String(btn.getAttribute("data-workflow-artifact-path") || "").trim();
      if (!path) return;
      const artifact = (Array.isArray(state.artifacts) ? state.artifacts : []).find(
        (item) => item && item.type === "file" && String(item.path || "") === path
      );
      if (!artifact) return;
      await previewArtifact(artifact, { target: "monitor" });
    });
  });
}

async function continueWorkflowRun(runId) {
  const key = String(runId || "").trim();
  if (!key) return;
  const plan = workflowPlanForRunId(key);
  if (!plan || !plan.continueFrom) return;
  const start = normalizePipelineStage(plan.continueFrom, "");
  const nextCheckpoint = normalizePipelineStage(plan.checkpointStages?.[plan.checkpointIndex + 1], "");
  const stop = normalizePipelineStage(nextCheckpoint || plan.finalStopAfter, "");
  if (!start || !stop) return;
  if (PIPELINE_STAGE_ORDER.indexOf(start) > PIPELINE_STAGE_ORDER.indexOf(stop)) return;

  state.runSubmitting = true;
  state.currentRunState = "running";
  state.autoAnalyzePendingByRunId[key] = true;
  updateRunEligibility(state.plan?.questions || []);
  updateMonitorActionButtons();
  setMessage(
    t("monitor.workflow.continueStarted", {
      start: formatStageLabel(start),
      stop: formatStageLabel(stop),
      id: key,
    }),
    "ai"
  );
  try {
    const payload = await readRunRequestPayload(key);
    const args = {
      ...payload,
      run_id: key,
      start_from: start,
      stop_after: stop,
      novelty_enabled: stop === "novelty",
      force: false,
      auto_recover: true,
    };
    const progressContext = buildProgressContextFromRequestPayload(args);
    if (progressContext) state.progressContextByRunId[key] = progressContext;
    const result = await apiCall("pipeline.run", args);
    const resumedRunId = String(result?.run_id || key).trim() || key;
    if (state.progressContextByRunId[key] && resumedRunId !== key) {
      state.progressContextByRunId[resumedRunId] = state.progressContextByRunId[key];
    }
    state.runModeById[resumedRunId] = "workflow";
    state.autoAnalyzePendingByRunId[resumedRunId] = true;
    const nextCheckpointIndex = Math.max(
      0,
      Math.min((plan.checkpointStages || []).length, Number(plan.checkpointIndex || 0) + 1)
    );
    state.workflowPlansByRunId[resumedRunId] = {
      nodes: plan.nodes,
      finalStopAfter: plan.finalStopAfter,
      checkpointEnabled: plan.checkpointEnabled,
      checkpointStages: plan.checkpointStages,
      checkpointIndex: nextCheckpointIndex,
      graphEnabled: plan.graphEnabled,
      mmseqLoopEnabled: plan.mmseqLoopEnabled,
    };
    persistWorkflowPlans();
    setCurrentRunId(resumedRunId);
    setActiveTab("monitor");
    await refreshRuns();
    ensureAutoPoll();
    await pollStatus(resumedRunId);
    await refreshArtifacts();
  } catch (err) {
    state.currentRunState = "failed";
    state.autoAnalyzePendingByRunId[key] = false;
    setMessage(t("monitor.workflow.continueFailed", { error: err.message }), "ai");
  } finally {
    state.runSubmitting = false;
    updateRunEligibility(state.plan?.questions || []);
    updateMonitorActionButtons();
  }
}

async function rerunWorkflowStage(runId, targetStage = "msa") {
  const key = String(runId || "").trim();
  if (!key) return;
  const plan = workflowPlanForRunId(key);
  const rerunStageSet = new Set(["msa", ...(Array.isArray(plan?.nodes) ? plan.nodes : [])]);
  const availableStages = PIPELINE_STAGE_ORDER.filter((stage) => rerunStageSet.has(stage));
  const requestedStage = normalizePipelineStage(targetStage, "msa") || "msa";
  const stage = availableStages.includes(requestedStage)
    ? requestedStage
    : availableStages[0] || "msa";
  const ok = window.confirm(
    t("monitor.workflow.rerunConfirm", {
      id: key,
      stage: formatStageLabel(stage),
    })
  );
  if (!ok) return;
  const prefix = state.user?.run_prefix || buildUserPrefix({ name: state.user?.username || "user" });
  const newRunId = createRunId(prefix);

  state.runSubmitting = true;
  state.currentRunState = "running";
  updateRunEligibility(state.plan?.questions || []);
  updateMonitorActionButtons();
  try {
    const payload = await readRunRequestPayload(key);
    const args = {
      ...payload,
      run_id: newRunId,
      start_from: "msa",
      stop_after: stage,
      novelty_enabled: stage === "novelty",
      force: false,
      auto_recover: true,
    };
    const result = await apiCall("pipeline.run", args);
    const launchedRunId = String(result?.run_id || newRunId).trim() || newRunId;
    const progressContext = buildProgressContextFromRequestPayload(args);
    if (progressContext) {
      state.progressContextByRunId[launchedRunId] = progressContext;
    }
    const stageModeMap = {
      msa: "msa",
      rfd3: "rfd3",
      bioemu: "bioemu",
      design: "design",
      soluprot: "soluprot",
      af2: "af2",
      novelty: "pipeline",
    };
    state.runModeById[launchedRunId] = stageModeMap[stage] || "pipeline";
    state.autoAnalyzePendingByRunId[launchedRunId] = false;
    setMessage(
      t("monitor.workflow.rerunStarted", {
        id: launchedRunId,
        start: formatStageLabel("msa"),
        stop: formatStageLabel(stage),
      }),
      "ai"
    );
    setCurrentRunId(launchedRunId);
    setActiveTab("monitor");
    await refreshRuns();
    ensureAutoPoll();
    await pollStatus(launchedRunId);
  } catch (err) {
    state.currentRunState = "failed";
    setMessage(t("monitor.workflow.rerunFailed", { error: err.message }), "ai");
  } finally {
    state.runSubmitting = false;
    updateRunEligibility(state.plan?.questions || []);
    updateMonitorActionButtons();
  }
}

async function rerunWorkflowMmseq(runId) {
  await rerunWorkflowStage(runId, "msa");
}

function updateMonitorReportActions() {
  const hasRun = Boolean(String(state.currentRunId || "").trim());
  const shouldShowGenerate = hasRun && Boolean(state.monitorNeedsReport);
  if (el.artifactGenerateReport) {
    el.artifactGenerateReport.classList.toggle("hidden", !shouldShowGenerate);
    el.artifactGenerateReport.disabled = !hasRun;
  }
  const hasSummary = comparisonSummaryHasData(state.artifactComparison);
  if (el.artifactComparisonDetails) {
    const shouldShowDetails = hasRun && hasSummary;
    el.artifactComparisonDetails.classList.toggle("hidden", !shouldShowDetails);
    el.artifactComparisonDetails.disabled = !shouldShowDetails;
  }
}

async function refreshArtifactComparisonSummary() {
  if (!el.artifactComparisonSummary) return;
  const runId = String(state.currentRunId || "").trim();
  if (!runId) {
    state.artifactComparison = null;
    state.artifactComparisonRunId = "";
    state.monitorNeedsReport = false;
    renderArtifactComparisonSummary(null);
    renderMonitorCompleteness(null, null);
    renderCandidateCharts();
    updateMonitorReportActions();
    return;
  }
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: runId,
      path: "comparisons.json",
      max_bytes: 512000,
    });
    const text = String(result?.text || "").trim();
    const parsed = text ? JSON.parse(text) : null;
    if (String(state.currentRunId || "").trim() !== runId) return;
    let resolved = parsed && typeof parsed === "object" ? parsed : null;
    if (comparisonSummaryNeedsMedianBackfill(resolved)) {
      try {
        const reportPayload = await apiCall("pipeline.get_report", { run_id: runId });
        if (String(state.currentRunId || "").trim() !== runId) return;
        const reportSummary = comparisonSummaryFromReportPayload(reportPayload);
        if (reportSummary) resolved = reportSummary;
      } catch (_reportRefreshErr) {
        // keep comparisons.json if report fetch fails
      }
    }
    state.artifactComparison = resolved;
    state.artifactComparisonRunId = runId;
    state.monitorNeedsReport = false;
    renderArtifactComparisonSummary(state.artifactComparison);
    renderMonitorCompleteness(state.artifactComparison, null);
    renderCandidateCharts();
    updateMonitorReportActions();
  } catch (_err) {
    if (String(state.currentRunId || "").trim() !== runId) return;
    try {
      const reportPayload = await apiCall("pipeline.get_report", { run_id: runId });
      if (String(state.currentRunId || "").trim() !== runId) return;
      const resolved = comparisonSummaryFromReportPayload(reportPayload);
      if (resolved) {
        state.artifactComparison = resolved;
        state.artifactComparisonRunId = runId;
        state.monitorNeedsReport = false;
        renderArtifactComparisonSummary(resolved);
        renderMonitorCompleteness(resolved, null);
        renderCandidateCharts();
      } else {
        const hasReport = Boolean(
          String(reportPayload?.report || "").trim() || String(reportPayload?.report_ko || "").trim()
        );
        state.artifactComparison = null;
        state.artifactComparisonRunId = runId;
        state.monitorNeedsReport = !hasReport;
        if (hasReport) {
          renderArtifactComparisonSummary({
            version: 1,
            wt_compare_enabled: false,
            wt_vs_design: {},
            source_compare: {},
          });
          renderMonitorCompleteness(
            {
              version: 1,
              wt_compare_enabled: false,
              wt_vs_design: {},
              source_compare: {},
            },
            null
          );
          renderCandidateCharts();
        } else {
          renderArtifactComparisonSummary(null);
          renderMonitorCompleteness(null, null);
          renderCandidateCharts();
        }
      }
      updateMonitorReportActions();
    } catch (_reportErr) {
      if (String(state.currentRunId || "").trim() !== runId) return;
      state.artifactComparison = null;
      state.artifactComparisonRunId = runId;
      state.monitorNeedsReport = true;
      renderArtifactComparisonSummary(null);
      renderMonitorCompleteness(null, null);
      renderCandidateCharts();
      updateMonitorReportActions();
    }
  }
}

function apply3dStyle(viewer, format) {
  if (format === "sdf") {
    viewer.setStyle({}, { stick: { radius: 0.15 } });
  } else {
    viewer.setStyle({}, { cartoon: { color: "spectrum" } });
  }
}

function parsePdbResidueMap(pdbText) {
  const out = new Map();
  const lines = String(pdbText || "").split(/\r?\n/);
  lines.forEach((line) => {
    if (!/^ATOM/.test(line)) return;
    const atomName = line.slice(12, 16).trim();
    const resn = line.slice(17, 20).trim();
    const chainRaw = line.slice(21, 22).trim().toUpperCase();
    const chain = chainRaw || "";
    const chainKey = chain || "_";
    const resiRaw = line.slice(22, 26).trim();
    const resi = Number(resiRaw);
    if (!Number.isFinite(resi)) return;
    const key = `${chainKey}:${resi}`;
    const prev = out.get(key);
    if (!prev) {
      out.set(key, { chain, resi, resn, hasCA: atomName === "CA" });
      return;
    }
    if (atomName === "CA") prev.hasCA = true;
  });
  return out;
}

const PDB_AA3_TO_AA1 = {
  ALA: "A",
  ARG: "R",
  ASN: "N",
  ASP: "D",
  CYS: "C",
  GLN: "Q",
  GLU: "E",
  GLY: "G",
  HIS: "H",
  ILE: "I",
  LEU: "L",
  LYS: "K",
  MET: "M",
  PHE: "F",
  PRO: "P",
  SER: "S",
  THR: "T",
  TRP: "W",
  TYR: "Y",
  VAL: "V",
  MSE: "M",
  SEC: "U",
  PYL: "O",
  ASX: "B",
  GLX: "Z",
  XLE: "J",
  UNK: "X",
};

function parsePdbSequenceByChain(pdbText) {
  const residuesByChain = {};
  const seen = new Set();
  const lines = String(pdbText || "").split(/\r?\n/);
  lines.forEach((line) => {
    if (!/^ATOM/.test(line)) return;
    const chainRaw = line.slice(21, 22).trim().toUpperCase();
    const chain = chainRaw || "_";
    const resi = Number(line.slice(22, 26).trim());
    if (!Number.isFinite(resi)) return;
    const key = `${chain}:${resi}`;
    if (seen.has(key)) return;
    seen.add(key);
    const resn = line.slice(17, 20).trim().toUpperCase();
    const aa = PDB_AA3_TO_AA1[resn] || "X";
    if (!residuesByChain[chain]) residuesByChain[chain] = [];
    residuesByChain[chain].push(aa);
  });
  const out = {};
  Object.entries(residuesByChain).forEach(([chain, chars]) => {
    const seq = Array.isArray(chars) ? chars.join("") : "";
    if (!seq) return;
    out[chain] = seq;
  });
  return out;
}

function wrapSequenceForFasta(seq, width = 80) {
  const text = String(seq || "");
  if (!text) return "";
  const out = [];
  for (let i = 0; i < text.length; i += width) {
    out.push(text.slice(i, i + width));
  }
  return out.join("\n");
}

function buildFastaFromChainMap(sequenceByChain, labelPrefix) {
  const entries = Object.entries(sequenceByChain || {});
  if (!entries.length) return t("artifacts.preview.compare.sequenceEmpty");
  return entries
    .map(([chain, seq]) => `>${labelPrefix}|chain=${chain}\n${wrapSequenceForFasta(seq, 80)}`)
    .join("\n");
}

function formatPdbChainSummary(sequenceByChain) {
  const entries = Object.entries(sequenceByChain || {})
    .filter(([, seq]) => String(seq || "").trim())
    .sort(([left], [right]) => String(left || "").localeCompare(String(right || "")));
  if (!entries.length) return "-";
  return entries
    .map(([chain, seq]) => `${chain || "_"}(${String(seq || "").length})`)
    .join(", ");
}

function flattenSequenceByChain(sequenceByChain) {
  return Object.entries(sequenceByChain || {})
    .sort(([left], [right]) => String(left || "").localeCompare(String(right || "")))
    .map(([, seq]) => String(seq || ""))
    .join("");
}

function normalizeSequenceText(value) {
  return String(value || "")
    .replace(/[^A-Za-z]/g, "")
    .toUpperCase();
}

function parsePrimaryFastaSequence(fastaText) {
  return String(fastaText || "")
    .split(/\r?\n/)
    .map((line) => String(line || "").trim())
    .filter((line) => line && !line.startsWith(">"))
    .join("")
    .replace(/\s+/g, "")
    .toUpperCase();
}

function computeSequenceDifferenceStats(referenceSeq, candidateSeq) {
  const left = normalizeSequenceText(referenceSeq);
  const right = normalizeSequenceText(candidateSeq);
  const compareLen = Math.max(left.length, right.length);
  if (!compareLen) return null;
  let diffCount = 0;
  for (let idx = 0; idx < compareLen; idx += 1) {
    const a = left[idx] || "-";
    const b = right[idx] || "-";
    if (a !== b) diffCount += 1;
  }
  return {
    wt_diff_count: diffCount,
    wt_compare_len: compareLen,
    wt_diff_pct: (diffCount / compareLen) * 100.0,
  };
}

function pickComparableSequence(sequenceByChain, targetSequence = "") {
  const normalizedTarget = normalizeSequenceText(targetSequence);
  const chains = Object.entries(sequenceByChain || {})
    .sort(([left], [right]) => String(left || "").localeCompare(String(right || "")))
    .map(([, seq]) => normalizeSequenceText(seq))
    .filter(Boolean);
  if (!chains.length) return "";
  const candidates = Array.from(new Set([...chains, chains.join("")])).filter(Boolean);
  if (!normalizedTarget) return candidates[0] || "";
  let best = candidates[0] || "";
  let bestDiff = Number.POSITIVE_INFINITY;
  let bestLenGap = Number.POSITIVE_INFINITY;
  candidates.forEach((seq) => {
    const stats = computeSequenceDifferenceStats(normalizedTarget, seq);
    const diffCount = Number(stats?.wt_diff_count);
    const lenGap = Math.abs(seq.length - normalizedTarget.length);
    if (
      diffCount < bestDiff ||
      (diffCount === bestDiff && lenGap < bestLenGap) ||
      (diffCount === bestDiff && lenGap === bestLenGap && seq.length < best.length)
    ) {
      best = seq;
      bestDiff = diffCount;
      bestLenGap = lenGap;
    }
  });
  return best;
}

function countFixedPositions(payload) {
  if (Array.isArray(payload)) {
    return payload.filter((value) => Number.isFinite(Number(value))).length;
  }
  if (!payload || typeof payload !== "object") return null;
  let count = 0;
  Object.values(payload).forEach((values) => {
    if (!Array.isArray(values)) return;
    count += values.filter((value) => Number.isFinite(Number(value))).length;
  });
  return count;
}

function buildCompareFixedPositionPaths(meta) {
  const tier = String(meta?.tier || "").trim();
  const backboneId = String(meta?.backboneId || "").trim();
  if (!tier) return [];
  const paths = [];
  if (backboneId) {
    paths.push(`backbones/${backboneId}/tiers/${tier}/fixed_positions.json`);
  }
  paths.push(`tiers/${tier}/fixed_positions.json`);
  return Array.from(new Set(paths));
}

function compareDesignChainCacheKey(runId, path, meta = artifactMetaForPath(path)) {
  const runKey = String(runId || "").trim();
  const normalizedPath = String(meta?.normalizedPath || path || "").trim();
  return `${runKey}::${normalizedPath}`;
}

function buildCompareDesignChainPaths(path, meta = artifactMetaForPath(path)) {
  const role = compareArtifactRoleKey(meta);
  const backboneId = String(meta?.backboneId || "").trim();
  const paths = [];
  if (backboneId && ["backbone_snapshot", "source_output", "af2_candidate"].includes(role)) {
    paths.push(`backbones/${backboneId}/query_pdb_alignment.json`);
    paths.push(`backbones/${backboneId}/chain_strategy.json`);
  }
  paths.push("query_pdb_alignment.json");
  paths.push("chain_strategy.json");
  return Array.from(new Set(paths.filter(Boolean)));
}

async function readCompareDesignChains(runId, path, meta = artifactMetaForPath(path)) {
  const runKey = String(runId || "").trim();
  if (!runKey) return null;
  const cacheKey = compareDesignChainCacheKey(runKey, path, meta);
  if (Object.prototype.hasOwnProperty.call(state.compareDesignChainsByKey, cacheKey)) {
    return state.compareDesignChainsByKey[cacheKey];
  }
  const candidatePaths = buildCompareDesignChainPaths(path, meta);
  for (const candidatePath of candidatePaths) {
    try {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: runKey,
        path: candidatePath,
        max_bytes: 200000,
      });
      const parsed = JSON.parse(String(result?.text || "{}"));
      const chains = extractDesignChainsFromPayload(parsed);
      if (chains.length) {
        state.compareDesignChainsByKey[cacheKey] = chains;
        return chains;
      }
    } catch (_err) {
      // Try the next known chain-strategy location.
    }
  }
  state.compareDesignChainsByKey[cacheKey] = null;
  return null;
}

async function normalizeComparePdbTextForArtifact(runId, path, pdbText, meta = artifactMetaForPath(path)) {
  const source = String(pdbText || "");
  if (!/\.pdb$/i.test(String(path || "")) || !source.trim()) return source;
  const chains = await readCompareDesignChains(runId, path, meta);
  if (!Array.isArray(chains) || !chains.length) return source;
  const filtered = filterPdbTextByChains(source, chains);
  return filtered.trim() ? filtered : source;
}

async function readCompareTargetSequence(runId) {
  const key = String(runId || "").trim();
  if (!key) return "";
  if (Object.prototype.hasOwnProperty.call(state.compareTargetSequenceByRunId, key)) {
    return String(state.compareTargetSequenceByRunId[key] || "");
  }
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: key,
      path: "target.fasta",
      max_bytes: 200000,
    });
    const sequence = parsePrimaryFastaSequence(result?.text || "");
    if (sequence) {
      state.compareTargetSequenceByRunId[key] = sequence;
      return sequence;
    }
    const inputPdbText = await readCompareInputPdbText(key);
    const sequenceByChain = parsePdbSequenceByChain(inputPdbText || "");
    const fallback = pickComparableSequence(sequenceByChain, "") || flattenSequenceByChain(sequenceByChain);
    state.compareTargetSequenceByRunId[key] = fallback;
    return fallback;
  } catch (_err) {
    const inputPdbText = await readCompareInputPdbText(key);
    const sequenceByChain = parsePdbSequenceByChain(inputPdbText || "");
    const fallback = pickComparableSequence(sequenceByChain, "") || flattenSequenceByChain(sequenceByChain);
    state.compareTargetSequenceByRunId[key] = fallback;
    return fallback;
  }
}

async function readCompareInputPdbText(runId) {
  const key = String(runId || "").trim();
  if (!key) return "";
  if (Object.prototype.hasOwnProperty.call(state.compareInputPdbTextByRunId, key)) {
    return String(state.compareInputPdbTextByRunId[key] || "");
  }
  const candidatePaths = ["target.original.pdb", "target.pdb"];
  for (const path of candidatePaths) {
    try {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: key,
        path,
        max_bytes: 800000,
      });
      const text = String(result?.text || "");
      if (text.trim()) {
        const normalized = await normalizeComparePdbTextForArtifact(key, path, text);
        state.compareInputPdbTextByRunId[key] = normalized;
        return normalized;
      }
    } catch (_err) {
      // Try the next known input reference path.
    }
  }
  state.compareInputPdbTextByRunId[key] = "";
  return "";
}

async function readCompareWorkingPdbText(runId) {
  const key = String(runId || "").trim();
  if (!key) return "";
  if (Object.prototype.hasOwnProperty.call(state.compareWorkingPdbTextByRunId, key)) {
    return String(state.compareWorkingPdbTextByRunId[key] || "");
  }
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: key,
      path: "target.pdb",
      max_bytes: 800000,
    });
    const text = await normalizeComparePdbTextForArtifact(key, "target.pdb", String(result?.text || ""));
    state.compareWorkingPdbTextByRunId[key] = text;
    return text;
  } catch (_err) {
    state.compareWorkingPdbTextByRunId[key] = "";
    return "";
  }
}

async function readCompareWtPdbText(runId) {
  const key = String(runId || "").trim();
  if (!key) return "";
  if (Object.prototype.hasOwnProperty.call(state.compareWtPdbTextByRunId, key)) {
    return String(state.compareWtPdbTextByRunId[key] || "");
  }
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: key,
      path: "wt/af2/ranked_0.pdb",
      max_bytes: 800000,
    });
    const text = await normalizeComparePdbTextForArtifact(key, "wt/af2/ranked_0.pdb", String(result?.text || ""));
    state.compareWtPdbTextByRunId[key] = text;
    return text;
  } catch (_err) {
    state.compareWtPdbTextByRunId[key] = "";
    return "";
  }
}

async function readCompareWtMetrics(runId) {
  const key = String(runId || "").trim();
  if (!key) return null;
  if (Object.prototype.hasOwnProperty.call(state.compareWtMetricsByRunId, key)) {
    return state.compareWtMetricsByRunId[key];
  }
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: key,
      path: "wt/metrics.json",
      max_bytes: 200000,
    });
    const parsed = JSON.parse(String(result?.text || "{}"));
    state.compareWtMetricsByRunId[key] = parsed;
    return parsed;
  } catch (_err) {
    state.compareWtMetricsByRunId[key] = null;
    return null;
  }
}

async function readCompareFixedCount(runId, meta) {
  const runKey = String(runId || "").trim();
  const tier = String(meta?.tier || "").trim();
  const backboneId = String(meta?.backboneId || "").trim();
  if (!runKey || !tier) return null;
  const cacheKey = `${runKey}::${backboneId}::${tier}`;
  if (Object.prototype.hasOwnProperty.call(state.compareFixedCountByKey, cacheKey)) {
    return state.compareFixedCountByKey[cacheKey];
  }
  const paths = buildCompareFixedPositionPaths(meta);
  for (const path of paths) {
    try {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: runKey,
        path,
        max_bytes: 200000,
      });
      const parsed = JSON.parse(String(result?.text || "{}"));
      const count = countFixedPositions(parsed);
      if (Number.isFinite(count)) {
        state.compareFixedCountByKey[cacheKey] = count;
        return count;
      }
    } catch (_err) {
      // Try the next known fixed-position location.
    }
  }
  state.compareFixedCountByKey[cacheKey] = null;
  return null;
}

async function readCompareAf2Scores(runId, tier) {
  const runKey = String(runId || "").trim();
  const tierKey = String(tier || "").trim();
  if (!runKey || !tierKey) return null;
  const cacheKey = `${runKey}::${tierKey}`;
  if (Object.prototype.hasOwnProperty.call(state.compareAf2ScoresByKey, cacheKey)) {
    return state.compareAf2ScoresByKey[cacheKey];
  }
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: runKey,
      path: `tiers/${tierKey}/af2_scores.json`,
      max_bytes: 200000,
    });
    const parsed = JSON.parse(String(result?.text || "{}"));
    state.compareAf2ScoresByKey[cacheKey] = parsed;
    return parsed;
  } catch (_err) {
    state.compareAf2ScoresByKey[cacheKey] = null;
    return null;
  }
}

function compareTierKeysForRun(runId) {
  const currentRun = String(runId || "").trim();
  if (!currentRun) return [];
  const tiers = new Set();
  (Array.isArray(state.artifacts) ? state.artifacts : []).forEach((item) => {
    const path = String(item?.path || "").trim();
    if (!path) return;
    const meta = artifactMetaForPath(path);
    if (meta?.tier) tiers.add(String(meta.tier));
  });
  if (!tiers.size) {
    (Array.isArray(state.hitListRows) ? state.hitListRows : []).forEach((row) => {
      const tier = normalizeCompareTierKey(row?.tier);
      if (tier) tiers.add(tier);
    });
  }
  if (!tiers.size) {
    const tierCompare = Array.isArray(state.artifactComparison?.tier_compare) ? state.artifactComparison.tier_compare : [];
    tierCompare.forEach((row) => {
      const tier = normalizeCompareTierKey(row?.tier);
      if (tier) tiers.add(tier);
    });
  }
  return Array.from(tiers).sort((a, b) => {
    const na = Number(a);
    const nb = Number(b);
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
    return String(a).localeCompare(String(b));
  });
}

function normalizeCompareBackboneId(value) {
  return displayArtifactPath(String(value || ""))
    .trim()
    .toLowerCase();
}

function backboneIdFromCandidateId(candidateId) {
  const text = String(candidateId || "").trim();
  if (!text) return "";
  const idx = text.lastIndexOf(":");
  return idx >= 0 ? text.slice(0, idx) : text;
}

function collectAf2BackboneMetrics(af2Summary, backboneId) {
  const targetKey = normalizeCompareBackboneId(backboneId);
  if (!targetKey || !af2Summary || typeof af2Summary !== "object") {
    return { candidateCount: 0, selectedCount: 0, plddts: [], rmsds: [], provider: "" };
  }
  const candidateIds = Array.from(
    new Set([
      ...Object.keys(af2Summary?.scores || {}),
      ...Object.keys(af2Summary?.rmsd_scores || {}),
      ...(Array.isArray(af2Summary?.candidate_ids) ? af2Summary.candidate_ids : []),
      ...(Array.isArray(af2Summary?.selected_ids) ? af2Summary.selected_ids : []),
    ])
  ).filter((candidateId) => normalizeCompareBackboneId(backboneIdFromCandidateId(candidateId)) === targetKey);
  const selectedCount = (Array.isArray(af2Summary?.selected_ids) ? af2Summary.selected_ids : []).filter(
    (candidateId) => normalizeCompareBackboneId(backboneIdFromCandidateId(candidateId)) === targetKey
  ).length;
  const plddts = candidateIds
    .map((candidateId) => finiteNumber(af2Summary?.scores?.[candidateId]))
    .filter((value) => value !== null);
  const rmsds = candidateIds
    .map((candidateId) => finiteNumber(af2Summary?.rmsd_scores?.[candidateId]))
    .filter((value) => value !== null);
  return {
    candidateCount: candidateIds.length,
    selectedCount,
    plddts,
    rmsds,
    provider: String(af2Summary?.provider || "").trim(),
  };
}

function summarizeAf2BackboneMetrics(items) {
  const metrics = Array.isArray(items) ? items : [];
  const plddts = [];
  const rmsds = [];
  let candidateCount = 0;
  let selectedCount = 0;
  let provider = "";
  metrics.forEach((item) => {
    if (!item || typeof item !== "object") return;
    candidateCount += Math.max(0, Number(item.candidateCount || 0));
    selectedCount += Math.max(0, Number(item.selectedCount || 0));
    if (Array.isArray(item.plddts)) plddts.push(...item.plddts);
    if (Array.isArray(item.rmsds)) rmsds.push(...item.rmsds);
    if (!provider && item.provider) provider = String(item.provider);
  });
  if (!candidateCount && !plddts.length && !rmsds.length) return null;
  return {
    candidateCount,
    selectedCount,
    plddtMedian: plddts.length ? percentileValue(plddts, 0.5) : null,
    rmsdMedian: rmsds.length ? percentileValue(rmsds, 0.5) : null,
    provider,
  };
}

async function readCompareAf2BackboneSummary(runId, backboneId, tier = "") {
  const runKey = String(runId || "").trim();
  const tierKey = String(tier || "").trim();
  const normalizedBackbone = String(backboneId || "").trim();
  if (!runKey || !normalizedBackbone) return null;
  const tiers = tierKey ? [tierKey] : compareTierKeysForRun(runKey);
  if (!tiers.length) return null;
  const summaries = await Promise.all(tiers.map((item) => readCompareAf2Scores(runKey, item)));
  return summarizeAf2BackboneMetrics(summaries.map((item) => collectAf2BackboneMetrics(item, normalizedBackbone)));
}

function af2PredictionScopeLabel(scope, provider = "") {
  const af2Provider = af2ProviderName(provider || currentRunAf2Provider(), state.lang || "en");
  if (scope === "exact") return t("artifacts.preview.compare.meta.predScopeExact", { af2Provider });
  if (scope === "wt") return t("artifacts.preview.compare.meta.predScopeWt", { af2Provider });
  if (scope === "tier") return t("artifacts.preview.compare.meta.predScopeTier", { af2Provider });
  if (scope === "backbone") return t("artifacts.preview.compare.meta.predScopeBackbone", { af2Provider });
  return t("artifacts.preview.compare.meta.predScopePre", { af2Provider });
}

function formatCompareAf2Selection(selectedCount, candidateCount) {
  const selected = Math.max(0, Number(selectedCount || 0));
  const total = Math.max(0, Number(candidateCount || 0));
  if (!total) return "-";
  const pct = formatPercentValue(selected / total);
  return pct === "-" ? `${selected}/${total}` : `${selected}/${total} (${pct})`;
}

function af2CandidateFolderFromPath(path) {
  const normalized = artifactMetaForPath(path).normalizedPath || "";
  const match = normalized.match(/(?:^|\/)tiers\/[^/]+\/af2\/([^/]+)\/[^/]+\.pdb$/);
  return match ? String(match[1] || "") : "";
}

function canonicalAf2CandidateSlug(value) {
  return displayArtifactPath(String(value || ""))
    .trim()
    .toLowerCase()
    .replace(/:/g, "_");
}

function resolveAf2CandidateId(af2Summary, path) {
  const folder = af2CandidateFolderFromPath(path);
  if (!folder || !af2Summary || typeof af2Summary !== "object") return "";
  const folderKey = canonicalAf2CandidateSlug(folder);
  const candidates = new Set([
    ...Object.keys(af2Summary?.scores || {}),
    ...Object.keys(af2Summary?.rmsd_scores || {}),
    ...(Array.isArray(af2Summary?.selected_ids) ? af2Summary.selected_ids : []),
    ...(Array.isArray(af2Summary?.candidate_ids) ? af2Summary.candidate_ids : []),
  ]);
  for (const candidateId of candidates) {
    if (canonicalAf2CandidateSlug(candidateId) === folderKey) return String(candidateId || "");
  }
  return folder.includes("_") ? folder.replace(/_([^_]+)$/u, ":$1") : "";
}

function isCompareWtReference(meta, rawPath) {
  return compareArtifactRoleKey(meta) === "wt_colabfold";
}

function isRfd3DerivedPdbText(pdbText) {
  const head = String(pdbText || "")
    .split(/\r?\n/)
    .slice(0, 5)
    .join(" ")
    .toUpperCase();
  return /(INPUTS_SPEC|RFD3|RFDIFFUSION|RF_DIFFUSION)/.test(head);
}

function buildCompareProvenanceText(meta, { provider = "", inputPdbText = "" } = {}) {
  const role = compareArtifactRoleKey(meta);
  const af2Provider = af2ProviderName(provider || currentRunAf2Provider(), state.lang || "en");
  const source = sourceLabel(compareSourceKeyFromMeta(meta));
  if (role === "input_reference") {
    return isRfd3DerivedPdbText(inputPdbText)
      ? t("artifacts.preview.compare.provenance.inputRfd3")
      : t("artifacts.preview.compare.provenance.input");
  }
  if (role === "working_backbone") {
    return t("artifacts.preview.compare.provenance.working");
  }
  if (role === "wt_colabfold") {
    return t("artifacts.preview.compare.provenance.wt", { af2Provider });
  }
  if (role === "backbone_snapshot") {
    return t("artifacts.preview.compare.provenance.backbone", { source });
  }
  if (role === "af2_candidate") {
    return t("artifacts.preview.compare.provenance.candidate", {
      tier: String(meta?.tier || "-"),
      af2Provider,
    });
  }
  if (role === "source_output") {
    return t("artifacts.preview.compare.provenance.source", { source });
  }
  return t("artifacts.preview.compare.provenance.other");
}

async function buildComparePredictionMeta(runId, meta, rawPath, af2Summary = null) {
  const currentProvider = currentRunAf2Provider(runId);
  if (isCompareWtReference(meta, rawPath)) {
    const wtMetrics = await readCompareWtMetrics(runId);
    const wtAf2 = wtMetrics?.af2 && typeof wtMetrics.af2 === "object" ? wtMetrics.af2 : {};
    const provider = String(wtAf2?.provider || currentProvider || "").trim();
    const plddt = finiteNumber(wtAf2?.best_plddt);
    const rmsd = finiteNumber(wtAf2?.rmsd_ca);
    if (plddt !== null || rmsd !== null) {
      return {
        provider,
        scope: af2PredictionScopeLabel("wt", provider),
        selectedLabel: "WT",
        plddtLabel: plddt !== null ? formatMetricValue(plddt, 2, false) : "-",
        rmsdLabel: rmsd !== null ? `${formatMetricValue(rmsd, 2, false)}A` : "-",
        exact: true,
      };
    }
  }

  const tierKey = String(meta?.tier || "").trim();
  const backboneId = String(meta?.backboneId || "").trim();
  const tierSummary = af2Summary || (tierKey ? await readCompareAf2Scores(runId, tierKey) : null);
  const tierProvider = String(tierSummary?.provider || currentProvider || "").trim();
  const candidateId = resolveAf2CandidateId(tierSummary, rawPath);
  if (candidateId) {
    const selected =
      Array.isArray(tierSummary?.selected_ids) && tierSummary.selected_ids.includes(candidateId)
        ? localizedYesNo(true)
        : Array.isArray(tierSummary?.selected_ids)
          ? localizedYesNo(false)
          : "-";
    const exactPlddt = finiteNumber(tierSummary?.scores?.[candidateId]);
    const exactRmsd = finiteNumber(tierSummary?.rmsd_scores?.[candidateId]);
    if (selected !== "-" || exactPlddt !== null || exactRmsd !== null) {
      return {
        provider: tierProvider,
        scope: af2PredictionScopeLabel("exact", tierProvider),
        selectedLabel: selected,
        plddtLabel: exactPlddt !== null ? formatMetricValue(exactPlddt, 2, false) : "-",
        rmsdLabel: exactRmsd !== null ? `${formatMetricValue(exactRmsd, 2, false)}A` : "-",
        exact: true,
      };
    }
  }

  if (tierKey && backboneId) {
    const summary = summarizeAf2BackboneMetrics([collectAf2BackboneMetrics(tierSummary, backboneId)]);
    if (summary?.candidateCount) {
      const provider = String(summary.provider || tierProvider || currentProvider || "").trim();
      return {
        provider,
        scope: af2PredictionScopeLabel("tier", provider),
        selectedLabel: formatCompareAf2Selection(summary.selectedCount, summary.candidateCount),
        plddtLabel:
          summary.plddtMedian !== null ? formatMetricValue(summary.plddtMedian, 2, false) : "-",
        rmsdLabel:
          summary.rmsdMedian !== null ? `${formatMetricValue(summary.rmsdMedian, 2, false)}A` : "-",
        exact: false,
      };
    }
  }

  if (backboneId) {
    const summary = await readCompareAf2BackboneSummary(runId, backboneId);
    if (summary?.candidateCount) {
      const provider = String(summary.provider || tierProvider || currentProvider || "").trim();
      return {
        provider,
        scope: af2PredictionScopeLabel("backbone", provider),
        selectedLabel: formatCompareAf2Selection(summary.selectedCount, summary.candidateCount),
        plddtLabel:
          summary.plddtMedian !== null ? formatMetricValue(summary.plddtMedian, 2, false) : "-",
        rmsdLabel:
          summary.rmsdMedian !== null ? `${formatMetricValue(summary.rmsdMedian, 2, false)}A` : "-",
        exact: false,
      };
    }
  }

  const provider = String(tierProvider || currentProvider || "").trim();
  const pending = af2PredictionScopeLabel("pre", provider);
  return {
    provider,
    scope: pending,
    selectedLabel: pending,
    plddtLabel: pending,
    rmsdLabel: pending,
    exact: false,
  };
}

async function buildComparePreviewCardData(
  runId,
  path,
  text,
  { targetSequence = "", inputPdbText = "", workingPdbText = "", wtPdbText = "" } = {}
) {
  const rawPath = String(path || "");
  const meta = artifactMetaForPath(rawPath);
  const isPdb = /\.pdb$/i.test(rawPath);
  const sequenceByChain = isPdb ? parsePdbSequenceByChain(text) : {};
  const candidateSequence = isPdb ? pickComparableSequence(sequenceByChain, targetSequence) : "";
  const wtDiff = targetSequence && candidateSequence ? computeSequenceDifferenceStats(targetSequence, candidateSequence) : null;
  const [fixedCount, af2Summary] = await Promise.all([
    isPdb ? readCompareFixedCount(runId, meta) : Promise.resolve(null),
    meta?.tier ? readCompareAf2Scores(runId, meta.tier) : Promise.resolve(null),
  ]);
  const inputStructureDiff =
    isPdb && inputPdbText ? computePdbStructuralDiff(inputPdbText, String(text || "")) : null;
  const wtStructureDiff = isPdb && wtPdbText ? computePdbStructuralDiff(wtPdbText, String(text || "")) : null;
  const workingStructureDiff =
    isPdb && workingPdbText ? computePdbStructuralDiff(workingPdbText, String(text || "")) : null;
  const predictionMeta = isPdb ? await buildComparePredictionMeta(runId, meta, rawPath, af2Summary) : null;
  const af2ProviderRaw = String(predictionMeta?.provider || currentRunAf2Provider(runId) || "").trim();
  const roleLabel = compareArtifactRoleLabel(meta, af2ProviderRaw);
  return {
    descriptor: buildArtifactCompareOptionLabel(rawPath, meta),
    role: roleLabel,
    source: sourceLabel(compareSourceKeyFromMeta(meta)),
    provenance: buildCompareProvenanceText(meta, {
      provider: af2ProviderRaw,
      inputPdbText,
    }),
    tier: meta?.tier ? formatCompareTierLabel(meta.tier) : "-",
    backbone: meta?.backboneId ? displayArtifactPath(meta.backboneId) : "-",
    chains: isPdb ? formatPdbChainSummary(sequenceByChain) : "-",
    fixedCount: Number.isFinite(fixedCount) ? String(fixedCount) : "-",
    wtDiff: wtDiff ? formatWtDifference(wtDiff) : "-",
    inputStructRmsd:
      inputStructureDiff && inputStructureDiff.ok
        ? `${formatMetricValue(inputStructureDiff.rmsd, 2, false)}A`
        : "-",
    wtStructRmsd:
      wtStructureDiff && wtStructureDiff.ok ? `${formatMetricValue(wtStructureDiff.rmsd, 2, false)}A` : "-",
    workingStructRmsd:
      workingStructureDiff && workingStructureDiff.ok
        ? `${formatMetricValue(workingStructureDiff.rmsd, 2, false)}A`
        : "-",
    commonCa:
      inputStructureDiff && inputStructureDiff.ok
        ? String(Number(inputStructureDiff.commonCount || 0))
        : wtStructureDiff && wtStructureDiff.ok
          ? String(Number(wtStructureDiff.commonCount || 0))
          : workingStructureDiff && workingStructureDiff.ok
            ? String(Number(workingStructureDiff.commonCount || 0))
            : "-",
    af2Scope: String(predictionMeta?.scope || "-"),
    af2Selected: String(predictionMeta?.selectedLabel || "-"),
    af2Plddt: String(predictionMeta?.plddtLabel || "-"),
    af2Rmsd: String(predictionMeta?.rmsdLabel || "-"),
    af2ProviderLabel: af2ProviderName(af2ProviderRaw || currentRunAf2Provider(runId), state.lang || "en"),
    path: displayArtifactPath(rawPath),
  };
}

function renderCompareMetadataPanel(leftMeta, rightMeta) {
  const panel = document.createElement("div");
  panel.className = "compare-meta-panel";
  panel.innerHTML = `<div class="compare-meta-title">${escapeHtml(t("artifacts.preview.compare.meta.title"))}</div>`;
  const grid = document.createElement("div");
  grid.className = "compare-meta-grid";
  const af2Provider =
    String(leftMeta?.af2ProviderLabel || "").trim() ||
    String(rightMeta?.af2ProviderLabel || "").trim() ||
    af2ProviderName(currentRunAf2Provider(), state.lang || "en");
  const cards = [
    { title: t("artifacts.preview.compare.meta.left"), data: leftMeta },
    { title: t("artifacts.preview.compare.meta.right"), data: rightMeta },
  ];
  cards.forEach((entry) => {
    const data = entry.data || {};
    const card = document.createElement("div");
    card.className = "compare-meta-card";
    card.innerHTML = `
      <div class="compare-meta-card-title">${escapeHtml(entry.title)}</div>
      <div class="compare-meta-card-subtitle">${escapeHtml(String(data.descriptor || "-"))}</div>
      <div class="compare-meta-list">
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.role"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.role || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.source"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.source || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.provenance"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.provenance || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.tier"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.tier || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.backbone"))}</span>
          <strong class="compare-meta-value compare-meta-mono">${escapeHtml(String(data.backbone || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.chains"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.chains || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.fixedCount"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.fixedCount || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.wtDiff"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.wtDiff || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.inputStructRmsd"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.inputStructRmsd || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.wtStructRmsd"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.wtStructRmsd || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.workingStructRmsd"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.workingStructRmsd || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.commonCa"))}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.commonCa || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(
            t("artifacts.preview.compare.meta.predScope", { af2Provider })
          )}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.af2Scope || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(
            t("artifacts.preview.compare.meta.predSelected", { af2Provider })
          )}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.af2Selected || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(
            t("artifacts.preview.compare.meta.predPlddt", { af2Provider })
          )}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.af2Plddt || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(
            t("artifacts.preview.compare.meta.predRmsd", { af2Provider })
          )}</span>
          <strong class="compare-meta-value">${escapeHtml(String(data.af2Rmsd || "-"))}</strong>
        </div>
        <div class="compare-meta-item">
          <span class="compare-meta-label">${escapeHtml(t("artifacts.preview.compare.meta.path"))}</span>
          <strong class="compare-meta-value compare-meta-mono">${escapeHtml(String(data.path || "-"))}</strong>
        </div>
      </div>
    `;
    grid.appendChild(card);
  });
  panel.appendChild(grid);
  return panel;
}

function renderComparisonSequencePanel(left, right) {
  const leftMap = parsePdbSequenceByChain(left?.text || "");
  const rightMap = parsePdbSequenceByChain(right?.text || "");
  const panel = document.createElement("div");
  panel.className = "compare-seq-panel";
  panel.innerHTML = `<div class="compare-seq-title">${escapeHtml(t("artifacts.preview.compare.sequenceTitle"))}</div>`;

  const grid = document.createElement("div");
  grid.className = "compare-seq-grid";

  const leftBox = document.createElement("div");
  leftBox.className = "compare-seq-box";
  const leftLabel = document.createElement("div");
  leftLabel.className = "compare-seq-label";
  leftLabel.textContent = `${t("artifacts.preview.compare.sequenceLeft")} · ${displayArtifactPath(
    String(left?.path || "-")
  )}`;
  const leftPre = document.createElement("pre");
  leftPre.className = "compare-seq-fasta";
  leftPre.textContent = buildFastaFromChainMap(leftMap, "left");
  leftBox.appendChild(leftLabel);
  leftBox.appendChild(leftPre);

  const rightBox = document.createElement("div");
  rightBox.className = "compare-seq-box";
  const rightLabel = document.createElement("div");
  rightLabel.className = "compare-seq-label";
  rightLabel.textContent = `${t("artifacts.preview.compare.sequenceRight")} · ${displayArtifactPath(
    String(right?.path || "-")
  )}`;
  const rightPre = document.createElement("pre");
  rightPre.className = "compare-seq-fasta";
  rightPre.textContent = buildFastaFromChainMap(rightMap, "right");
  rightBox.appendChild(rightLabel);
  rightBox.appendChild(rightPre);

  grid.appendChild(leftBox);
  grid.appendChild(rightBox);
  panel.appendChild(grid);
  return panel;
}

function computePdbSequenceDiff(leftPdbText, rightPdbText) {
  const leftMap = parsePdbResidueMap(leftPdbText);
  const rightMap = parsePdbResidueMap(rightPdbText);
  const leftDiffByChain = {};
  const rightDiffByChain = {};
  const add = (bucket, chain, resi) => {
    if (!bucket[chain]) bucket[chain] = new Set();
    bucket[chain].add(Number(resi));
  };
  const allKeys = new Set([...leftMap.keys(), ...rightMap.keys()]);
  allKeys.forEach((key) => {
    const left = leftMap.get(key);
    const right = rightMap.get(key);
    if (left && right) {
      if (String(left.resn || "") !== String(right.resn || "")) {
        add(leftDiffByChain, left.chain, left.resi);
        add(rightDiffByChain, right.chain, right.resi);
      }
      return;
    }
    if (left) add(leftDiffByChain, left.chain, left.resi);
    if (right) add(rightDiffByChain, right.chain, right.resi);
  });
  const toObject = (bucket) => {
    const obj = {};
    Object.entries(bucket).forEach(([chain, values]) => {
      const residues = Array.from(values || []).filter((v) => Number.isFinite(v));
      if (!residues.length) return;
      residues.sort((a, b) => a - b);
      obj[chain] = residues;
    });
    return obj;
  };
  const leftResidues = toObject(leftDiffByChain);
  const rightResidues = toObject(rightDiffByChain);
  const totalCount = Object.values(leftResidues).reduce((acc, items) => acc + items.length, 0);
  return { leftResidues, rightResidues, totalCount };
}

function parsePdbCAResidueMap(pdbText) {
  const out = new Map();
  const lines = String(pdbText || "").split(/\r?\n/);
  lines.forEach((line) => {
    if (!/^ATOM/.test(line)) return;
    const atomName = line.slice(12, 16).trim();
    if (atomName !== "CA") return;
    const resn = line.slice(17, 20).trim();
    const chainRaw = line.slice(21, 22).trim().toUpperCase();
    const chain = chainRaw || "";
    const chainKey = chain || "_";
    const resiRaw = line.slice(22, 26).trim();
    const xRaw = line.slice(30, 38).trim();
    const yRaw = line.slice(38, 46).trim();
    const zRaw = line.slice(46, 54).trim();
    const resi = Number(resiRaw);
    const x = Number(xRaw);
    const y = Number(yRaw);
    const z = Number(zRaw);
    if (!Number.isFinite(resi) || !Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return;
    const key = `${chainKey}:${resi}`;
    out.set(key, { chain, resi, resn, coord: [x, y, z] });
  });
  return out;
}

function centroid3(points) {
  if (!Array.isArray(points) || !points.length) return [0, 0, 0];
  let sx = 0;
  let sy = 0;
  let sz = 0;
  points.forEach((p) => {
    sx += Number(p[0] || 0);
    sy += Number(p[1] || 0);
    sz += Number(p[2] || 0);
  });
  const n = points.length;
  return [sx / n, sy / n, sz / n];
}

function buildBestFitTransform(movingPoints, fixedPoints) {
  if (!Array.isArray(movingPoints) || !Array.isArray(fixedPoints)) return null;
  if (movingPoints.length !== fixedPoints.length || movingPoints.length < 3) return null;
  const cP = centroid3(movingPoints);
  const cQ = centroid3(fixedPoints);
  let Sxx = 0;
  let Sxy = 0;
  let Sxz = 0;
  let Syx = 0;
  let Syy = 0;
  let Syz = 0;
  let Szx = 0;
  let Szy = 0;
  let Szz = 0;
  for (let i = 0; i < movingPoints.length; i += 1) {
    const px = Number(movingPoints[i][0] || 0) - cP[0];
    const py = Number(movingPoints[i][1] || 0) - cP[1];
    const pz = Number(movingPoints[i][2] || 0) - cP[2];
    const qx = Number(fixedPoints[i][0] || 0) - cQ[0];
    const qy = Number(fixedPoints[i][1] || 0) - cQ[1];
    const qz = Number(fixedPoints[i][2] || 0) - cQ[2];
    Sxx += px * qx;
    Sxy += px * qy;
    Sxz += px * qz;
    Syx += py * qx;
    Syy += py * qy;
    Syz += py * qz;
    Szx += pz * qx;
    Szy += pz * qy;
    Szz += pz * qz;
  }
  const N = [
    [Sxx + Syy + Szz, Syz - Szy, Szx - Sxz, Sxy - Syx],
    [Syz - Szy, Sxx - Syy - Szz, Sxy + Syx, Szx + Sxz],
    [Szx - Sxz, Sxy + Syx, -Sxx + Syy - Szz, Syz + Szy],
    [Sxy - Syx, Szx + Sxz, Syz + Szy, -Sxx - Syy + Szz],
  ];
  let q = [1, 0, 0, 0];
  for (let iter = 0; iter < 40; iter += 1) {
    const n0 = N[0][0] * q[0] + N[0][1] * q[1] + N[0][2] * q[2] + N[0][3] * q[3];
    const n1 = N[1][0] * q[0] + N[1][1] * q[1] + N[1][2] * q[2] + N[1][3] * q[3];
    const n2 = N[2][0] * q[0] + N[2][1] * q[1] + N[2][2] * q[2] + N[2][3] * q[3];
    const n3 = N[3][0] * q[0] + N[3][1] * q[1] + N[3][2] * q[2] + N[3][3] * q[3];
    const norm = Math.hypot(n0, n1, n2, n3);
    if (!Number.isFinite(norm) || norm <= 1e-12) return null;
    q = [n0 / norm, n1 / norm, n2 / norm, n3 / norm];
  }
  const [w, x, y, z] = q;
  const r00 = 1 - 2 * (y * y + z * z);
  const r01 = 2 * (x * y - z * w);
  const r02 = 2 * (x * z + y * w);
  const r10 = 2 * (x * y + z * w);
  const r11 = 1 - 2 * (x * x + z * z);
  const r12 = 2 * (y * z - x * w);
  const r20 = 2 * (x * z - y * w);
  const r21 = 2 * (y * z + x * w);
  const r22 = 1 - 2 * (x * x + y * y);
  const t0 = cQ[0] - (r00 * cP[0] + r01 * cP[1] + r02 * cP[2]);
  const t1 = cQ[1] - (r10 * cP[0] + r11 * cP[1] + r12 * cP[2]);
  const t2 = cQ[2] - (r20 * cP[0] + r21 * cP[1] + r22 * cP[2]);
  return {
    R: [
      [r00, r01, r02],
      [r10, r11, r12],
      [r20, r21, r22],
    ],
    t: [t0, t1, t2],
  };
}

function applyTransformToCoord(coord, transform) {
  if (!transform || !Array.isArray(coord) || coord.length < 3) return null;
  const x = Number(coord[0] || 0);
  const y = Number(coord[1] || 0);
  const z = Number(coord[2] || 0);
  const R = transform.R;
  const t = transform.t;
  return [
    R[0][0] * x + R[0][1] * y + R[0][2] * z + t[0],
    R[1][0] * x + R[1][1] * y + R[1][2] * z + t[1],
    R[2][0] * x + R[2][1] * y + R[2][2] * z + t[2],
  ];
}

function formatPdbCoord(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "   0.000";
  const text = num.toFixed(3);
  return text.length >= 8 ? text.slice(-8) : text.padStart(8, " ");
}

function applyTransformToPdbText(pdbText, transform) {
  if (!transform) return String(pdbText || "");
  const lines = String(pdbText || "").split(/\r?\n/);
  return lines
    .map((line) => {
      if (!/^(ATOM  |HETATM)/.test(line)) return line;
      const x = Number(line.slice(30, 38).trim());
      const y = Number(line.slice(38, 46).trim());
      const z = Number(line.slice(46, 54).trim());
      if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return line;
      const moved = applyTransformToCoord([x, y, z], transform);
      if (!moved) return line;
      const base = line.length < 54 ? line.padEnd(54, " ") : line;
      return `${base.slice(0, 30)}${formatPdbCoord(moved[0])}${formatPdbCoord(moved[1])}${formatPdbCoord(
        moved[2]
      )}${base.slice(54)}`;
    })
    .join("\n");
}

function percentileValue(values, q) {
  if (!Array.isArray(values) || !values.length) return null;
  const nums = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!nums.length) return null;
  if (nums.length === 1) return nums[0];
  const qq = Math.min(1, Math.max(0, Number(q || 0)));
  const idx = qq * (nums.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.min(lo + 1, nums.length - 1);
  if (lo === hi) return nums[lo];
  const frac = idx - lo;
  return nums[lo] * (1 - frac) + nums[hi] * frac;
}

function computePdbStructuralDiff(leftPdbText, rightPdbText) {
  const leftMap = parsePdbCAResidueMap(leftPdbText);
  const rightMap = parsePdbCAResidueMap(rightPdbText);
  const leftKeys = Array.from(leftMap.keys());
  const rightKeys = new Set(rightMap.keys());
  const commonKeys = leftKeys.filter((key) => rightKeys.has(key));
  if (commonKeys.length < 3) {
    return { ok: false, reason: "not_enough_common_ca", commonCount: commonKeys.length };
  }
  const moving = commonKeys.map((key) => rightMap.get(key)?.coord || [0, 0, 0]);
  const fixed = commonKeys.map((key) => leftMap.get(key)?.coord || [0, 0, 0]);
  const transform = buildBestFitTransform(moving, fixed);
  if (!transform) {
    return { ok: false, reason: "alignment_failed", commonCount: commonKeys.length };
  }
  const add = (bucket, chain, resi) => {
    if (!bucket[chain]) bucket[chain] = [];
    bucket[chain].push(Number(resi));
  };
  const midResidues = {};
  const highResidues = {};
  const leftOnlyResidues = {};
  const rightOnlyResidues = {};
  const distances = [];
  const residueMetrics = [];
  let sse = 0;
  commonKeys.forEach((key) => {
    const left = leftMap.get(key);
    const right = rightMap.get(key);
    if (!left || !right) return;
    const moved = applyTransformToCoord(right.coord, transform);
    if (!moved) return;
    const dx = moved[0] - left.coord[0];
    const dy = moved[1] - left.coord[1];
    const dz = moved[2] - left.coord[2];
    const dist = Math.hypot(dx, dy, dz);
    distances.push(dist);
    sse += dist * dist;
    residueMetrics.push({
      key,
      chain: left.chain || "_",
      resi: left.resi,
      leftResn: left.resn || "",
      rightResn: right.resn || "",
      distance: dist,
    });
    if (dist > 3.0) add(highResidues, left.chain || "_", left.resi);
    else if (dist > 1.5) add(midResidues, left.chain || "_", left.resi);
  });
  leftMap.forEach((value, key) => {
    if (!rightMap.has(key)) add(leftOnlyResidues, value.chain || "_", value.resi);
  });
  rightMap.forEach((value, key) => {
    if (!leftMap.has(key)) add(rightOnlyResidues, value.chain || "_", value.resi);
  });
  return {
    ok: true,
    transform,
    commonCount: commonKeys.length,
    rmsd: distances.length ? Math.sqrt(sse / distances.length) : null,
    medianDistance: percentileValue(distances, 0.5),
    p90Distance: percentileValue(distances, 0.9),
    midResidues,
    highResidues,
    leftOnlyResidues,
    rightOnlyResidues,
    residueMetrics: residueMetrics.sort((a, b) => Number(b.distance || 0) - Number(a.distance || 0)),
  };
}

function applyDiffResidueStyle(viewer, residueByChain, color) {
  if (!viewer || !residueByChain || typeof residueByChain !== "object") return;
  Object.entries(residueByChain).forEach(([chain, residues]) => {
    if (!Array.isArray(residues) || !residues.length) return;
    const unique = Array.from(new Set(residues.map((v) => Number(v)).filter((v) => Number.isFinite(v)))).sort(
      (a, b) => a - b
    );
    unique.forEach((resi) => {
      const selector = chain === "_" || chain === "" ? { resi } : { chain, resi };
      viewer.setStyle(selector, {
        cartoon: { color },
        stick: { radius: 0.16, color },
      });
    });
  });
}

function applyPdbBaseStyle(viewer) {
  viewer.setStyle({}, { cartoon: { color: "#cfd5dc" } });
}

function applyComparisonStyles(panes, compareMode, structureDiff, seqDiff, selectedResidue = null) {
  if (!Array.isArray(panes) || panes.length < 2) return;
  panes.forEach((pane) => {
    if (pane?.format === "pdb") {
      applyPdbBaseStyle(pane.viewer);
    }
  });
  if (compareMode === "structure" && structureDiff && structureDiff.ok) {
    applyDiffResidueStyle(panes[0].viewer, structureDiff.midResidues, "#e6a700");
    applyDiffResidueStyle(panes[1].viewer, structureDiff.midResidues, "#e6a700");
    applyDiffResidueStyle(panes[0].viewer, structureDiff.highResidues, "#d62728");
    applyDiffResidueStyle(panes[1].viewer, structureDiff.highResidues, "#d62728");
    applyDiffResidueStyle(panes[0].viewer, structureDiff.leftOnlyResidues, "#1f77b4");
    applyDiffResidueStyle(panes[1].viewer, structureDiff.rightOnlyResidues, "#ff7f0e");
  } else if (seqDiff && seqDiff.totalCount > 0) {
    applyDiffResidueStyle(panes[0].viewer, seqDiff.leftResidues, "#1f77b4");
    applyDiffResidueStyle(panes[1].viewer, seqDiff.rightResidues, "#ff7f0e");
  }
  if (selectedResidue && typeof selectedResidue === "object") {
    const chain = String(selectedResidue.chain || "_");
    const resi = Number(selectedResidue.resi);
    if (Number.isFinite(resi)) {
      const selector = chain === "_" || chain === "" ? { resi } : { chain, resi };
      panes.forEach((pane) => {
        pane.viewer.setStyle(selector, { cartoon: { color: "#0b6f7b" }, stick: { radius: 0.24, color: "#0b6f7b" } });
      });
    }
  }
  panes.forEach((pane) => {
    pane.viewer.render();
  });
}

function renderResidueLinkedView(structureDiff, onSelect) {
  if (!structureDiff || !structureDiff.ok) return null;
  const metrics = Array.isArray(structureDiff.residueMetrics) ? structureDiff.residueMetrics : [];
  if (!metrics.length) return null;
  const topForTable = metrics.slice(0, 60);
  const topForStrip = selectResidueStripMetrics(metrics, {
    midThreshold: 1.5,
    maxCount: 220,
    fallbackCount: 60,
  });

  const root = document.createElement("div");
  root.className = "residue-linked";
  const title = document.createElement("div");
  title.className = "residue-linked-header";
  title.innerHTML = `<strong>${escapeHtml(t("residue.linked.title"))}</strong><span>${escapeHtml(
    t("residue.linked.help")
  )}</span>`;
  const selectedInfo = document.createElement("div");
  selectedInfo.className = "hint";
  selectedInfo.textContent = t("residue.linked.selectedNone");
  const strip = document.createElement("div");
  strip.className = "residue-strip";
  topForStrip.forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `residue-chip ${
      Number(item.distance) > 3 ? "high" : Number(item.distance) > 1.5 ? "mid" : "low"
    }`;
    chip.dataset.chain = String(item.chain || "_");
    chip.dataset.resi = String(item.resi || "");
    chip.dataset.left = String(item.leftResn || "");
    chip.dataset.right = String(item.rightResn || "");
    chip.dataset.dist = String(item.distance || "");
    chip.textContent = `${item.chain || "_"}:${item.resi}`;
    strip.appendChild(chip);
  });

  const tableWrap = document.createElement("div");
  tableWrap.className = "residue-table-wrap";
  tableWrap.innerHTML = `
    <table class="residue-table">
      <thead>
        <tr><th>Residue</th><th>WT</th><th>Design</th><th class="num">d(A)</th></tr>
      </thead>
      <tbody>
        ${topForTable
          .map(
            (item) => `<tr data-chain="${escapeHtml(String(item.chain || "_"))}" data-resi="${escapeHtml(
              String(item.resi || "")
            )}" data-left="${escapeHtml(String(item.leftResn || ""))}" data-right="${escapeHtml(
              String(item.rightResn || "")
            )}" data-dist="${escapeHtml(String(item.distance || ""))}">
            <td>${escapeHtml(`${item.chain || "_"}:${item.resi}`)}</td>
            <td>${escapeHtml(String(item.leftResn || ""))}</td>
            <td>${escapeHtml(String(item.rightResn || ""))}</td>
            <td class="num">${escapeHtml(formatMetricValue(item.distance, 2, false))}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;

  const updateSelection = (chain, resi, leftResn, rightResn, distance) => {
    const chainText = String(chain || "_");
    const resiNum = Number(resi);
    if (!Number.isFinite(resiNum)) return;
    strip.querySelectorAll(".residue-chip").forEach((node) => {
      const match = node.dataset.chain === chainText && Number(node.dataset.resi) === resiNum;
      node.classList.toggle("selected", match);
    });
    tableWrap.querySelectorAll("tbody tr").forEach((node) => {
      const match = node.dataset.chain === chainText && Number(node.dataset.resi) === resiNum;
      node.classList.toggle("selected", match);
    });
    selectedInfo.textContent = t("residue.linked.selected", {
      chain: chainText,
      resi: resiNum,
      left: leftResn || "-",
      right: rightResn || "-",
      dist: formatMetricValue(distance, 2, false),
    });
    if (typeof onSelect === "function") {
      onSelect({ chain: chainText, resi: resiNum });
    }
  };

  strip.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const chip = target ? target.closest(".residue-chip") : null;
    if (!chip) return;
    updateSelection(chip.dataset.chain, chip.dataset.resi, chip.dataset.left, chip.dataset.right, chip.dataset.dist);
  });
  strip.addEventListener("mouseover", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const chip = target ? target.closest(".residue-chip") : null;
    if (!chip) return;
    updateSelection(chip.dataset.chain, chip.dataset.resi, chip.dataset.left, chip.dataset.right, chip.dataset.dist);
  });
  tableWrap.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const row = target ? target.closest("tr[data-chain][data-resi]") : null;
    if (!row) return;
    updateSelection(row.dataset.chain, row.dataset.resi, row.dataset.left, row.dataset.right, row.dataset.dist);
  });
  tableWrap.addEventListener("mouseover", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const row = target ? target.closest("tr[data-chain][data-resi]") : null;
    if (!row) return;
    updateSelection(row.dataset.chain, row.dataset.resi, row.dataset.left, row.dataset.right, row.dataset.dist);
  });

  root.appendChild(title);
  root.appendChild(selectedInfo);
  root.appendChild(strip);
  root.appendChild(tableWrap);
  return root;
}

function getComparePreviewElement() {
  return el.compareStudioPreview || null;
}

function setComparePreviewPlaceholder(key, params = {}) {
  const previewEl = getComparePreviewElement();
  if (!previewEl) return;
  previewEl.innerHTML = `<div class="placeholder">${t(key, params)}</div>`;
}

function render3dComparison(left, right, mode = "structure", compareMeta = null) {
  const previewEl = getComparePreviewElement();
  if (!previewEl) return;
  if (!window.$3Dmol) {
    setComparePreviewPlaceholder("artifact.preview.unavailable");
    return;
  }
  previewEl.innerHTML = "";
  if (compareMeta && (compareMeta.left || compareMeta.right)) {
    previewEl.appendChild(renderCompareMetadataPanel(compareMeta.left, compareMeta.right));
  }
  const wrap = document.createElement("div");
  wrap.className = "viewer3d-compare";
  previewEl.appendChild(wrap);
  const panes = [];
  const usePdbPair = left.format === "pdb" && right.format === "pdb" && left.text && right.text;
  const compareMode = mode === "sequence" ? "sequence" : "structure";
  const structureDiff = usePdbPair && compareMode === "structure" ? computePdbStructuralDiff(left.text, right.text) : null;
  const seqDiff = usePdbPair ? computePdbSequenceDiff(left.text, right.text) : null;
  const rightTextForView =
    structureDiff && structureDiff.ok ? applyTransformToPdbText(right.text, structureDiff.transform) : right.text;
  const buildPane = (path, text, format) => {
    const pane = document.createElement("div");
    pane.className = "viewer3d-pane";
    const header = document.createElement("div");
    header.className = "viewer3d-pane-header";
    header.textContent = displayArtifactPath(path);
    const body = document.createElement("div");
    body.className = "viewer3d-pane-body";
    pane.appendChild(header);
    pane.appendChild(body);
    wrap.appendChild(pane);
    const viewer = window.$3Dmol.createViewer(body, { backgroundColor: "white" });
    viewer.addModel(text, format);
    if (format === "pdb") {
      viewer.setStyle({}, { cartoon: { color: "#cfd5dc" } });
    } else {
      apply3dStyle(viewer, format);
    }
    viewer.zoomTo();
    viewer.render();
    if (typeof viewer.resize === "function") {
      viewer.resize();
    }
    panes.push({ viewer, format, text, path });
  };
  buildPane(left.path, left.text, left.format);
  buildPane(right.path, rightTextForView, right.format);

  if (
    panes.length === 2 &&
    panes[0].format === "pdb" &&
    panes[1].format === "pdb" &&
    panes[0].text &&
    panes[1].text
  ) {
    let selectedResidue = null;
    applyComparisonStyles(panes, compareMode, structureDiff, seqDiff, selectedResidue);
    const legend = document.createElement("div");
    legend.className = "viewer3d-diff-note";
    if (compareMode === "structure" && structureDiff && structureDiff.ok) {
      const rmsdText = formatMetricValue(structureDiff.rmsd, 2, false);
      const p90Text = formatMetricValue(structureDiff.p90Distance, 2, false);
      legend.textContent = `${t("artifacts.preview.compare.diffLegendStructure")} · RMSD=${rmsdText}A, P90=${p90Text}A, n=${Number(
        structureDiff.commonCount || 0
      )}`;
    } else {
      const seqDiff = computePdbSequenceDiff(left.text, right.text);
      legend.textContent =
        seqDiff && seqDiff.totalCount > 0
          ? `${t("artifacts.preview.compare.diffLegendSequence")} (${seqDiff.totalCount})`
          : t("artifacts.preview.compare.diffNone");
    }
    previewEl.appendChild(legend);
    previewEl.appendChild(renderComparisonSequencePanel(left, right));
    if (compareMode === "structure" && structureDiff && structureDiff.ok) {
      const linked = renderResidueLinkedView(structureDiff, (selection) => {
        selectedResidue = selection;
        applyComparisonStyles(panes, compareMode, structureDiff, seqDiff, selectedResidue);
      });
      if (linked) {
        previewEl.appendChild(linked);
      } else {
        const empty = document.createElement("div");
        empty.className = "placeholder";
        empty.textContent = t("residue.linked.empty");
        previewEl.appendChild(empty);
      }
    }
  }
}

function findTierScopedCompareCandidatePath(structureItems, sourceKey, tierKey) {
  const wantedSource = normalizeSourceKey(sourceKey);
  const wantedTier = normalizeCompareTierKey(tierKey);
  if (!wantedSource || !wantedTier) return "";

  const hitRow = (Array.isArray(state.hitListRows) ? state.hitListRows : []).find((row) => {
    if (!row || normalizeSourceKey(row?.source) !== wantedSource) return false;
    if (normalizeCompareTierKey(row?.tier) !== wantedTier) return false;
    return String(row?.af2_ranked_pdb_path || "").trim().length > 0;
  });
  const hitPath = String(hitRow?.af2_ranked_pdb_path || "").trim();
  if (hitPath) return hitPath;

  const artifact = findCompareItem(structureItems, (_item, meta) => {
    if (compareArtifactRoleKey(meta) !== "af2_candidate") return false;
    if (compareSourceKeyFromMeta(meta) !== wantedSource) return false;
    return normalizeCompareTierKey(meta?.tier) === wantedTier;
  });
  return String(artifact?.path || "").trim();
}

function comparePresetVariantLabel(kind, tier = "") {
  if (kind === "base") return t("artifacts.preview.compare.meta.backbone");
  return formatCompareTierLabel(tier);
}

function buildComparePresetGroups(structureItems) {
  const refs = resolveCompareReferenceItems(structureItems);
  const tierKeys = compareTierKeysForRun(state.currentRunId);
  const groups = [];

  const addGroup = (id, labelKey, baseLeftItem, baseRightItem, tierResolver) => {
    const variants = [];
    const seen = new Set();
    const pushVariant = (variantId, variantLabel, leftPathRaw, rightPathRaw) => {
      const leftPath = String(leftPathRaw || "").trim();
      const rightPath = String(rightPathRaw || "").trim();
      if (!leftPath || !rightPath || leftPath === rightPath) return;
      const key = `${leftPath}::${rightPath}`;
      if (seen.has(key)) return;
      seen.add(key);
      variants.push({
        id: variantId,
        label: variantLabel,
        leftPath,
        rightPath,
      });
    };

    pushVariant(
      `${id}__base`,
      comparePresetVariantLabel("base"),
      baseLeftItem?.path,
      baseRightItem?.path
    );

    tierKeys.forEach((tierKey) => {
      const resolved = typeof tierResolver === "function" ? tierResolver(tierKey) : null;
      if (!resolved || typeof resolved !== "object") return;
      pushVariant(
        `${id}__tier_${tierKey}`,
        comparePresetVariantLabel("tier", tierKey),
        resolved.leftPath,
        resolved.rightPath
      );
    });

    if (!variants.length) return;
    groups.push({
      id,
      label: t(labelKey),
      variants,
    });
  };

  addGroup("wt_vs_rfd3", "artifacts.preview.compare.preset.wtVsRfd3", refs.wt, refs.rfd3Backbone, (tierKey) => ({
    leftPath: refs.wt?.path,
    rightPath: findTierScopedCompareCandidatePath(structureItems, "rfd3", tierKey),
  }));
  addGroup("wt_vs_bioemu", "artifacts.preview.compare.preset.wtVsBioemu", refs.wt, refs.bioemuBackbone, (tierKey) => ({
    leftPath: refs.wt?.path,
    rightPath: findTierScopedCompareCandidatePath(structureItems, "bioemu", tierKey),
  }));
  addGroup(
    "rfd3_vs_bioemu",
    "artifacts.preview.compare.preset.rfd3VsBioemu",
    refs.rfd3Backbone,
    refs.bioemuBackbone,
    (tierKey) => ({
      leftPath: findTierScopedCompareCandidatePath(structureItems, "rfd3", tierKey),
      rightPath: findTierScopedCompareCandidatePath(structureItems, "bioemu", tierKey),
    })
  );

  return groups;
}

function renderCompareReferenceStrip(structureItems) {
  if (!el.artifactCompareRefs) return;
  const refs = resolveCompareReferenceItems(structureItems);
  const rows = [
    { key: "input", label: t("artifacts.preview.compare.refs.input"), item: refs.input },
    { key: "working", label: t("artifacts.preview.compare.refs.working"), item: refs.working },
    { key: "wt", label: t("artifacts.preview.compare.refs.wt"), item: refs.wt },
  ];
  el.artifactCompareRefs.innerHTML = `
    <div class="compare-strip-title">${escapeHtml(t("artifacts.preview.compare.refs.title"))}</div>
    <div class="compare-reference-list">
      ${rows
        .map((row) => {
          const value = row.item ? displayArtifactPath(row.item.path) : t("artifacts.preview.compare.refs.missing");
          const missing = !row.item ? " is-missing" : "";
          return `
            <div class="compare-reference-chip${missing}">
              <span class="compare-reference-label">${escapeHtml(row.label)}</span>
              <strong class="compare-reference-value">${escapeHtml(value)}</strong>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderComparePresetStrip(structureItems) {
  if (!el.artifactComparePresets) return;
  const groups = buildComparePresetGroups(structureItems);
  if (!groups.length) {
    el.artifactComparePresets.innerHTML = "";
    return;
  }
  const currentKey = `${String(state.artifactCompareLeftPath || "").trim()}::${String(
    state.artifactCompareRightPath || ""
  ).trim()}`;

  const activeVariantByGroup = new Map();
  groups.forEach((group) => {
    const activeVariant =
      (Array.isArray(group.variants) ? group.variants : []).find(
        (variant) => `${variant.leftPath}::${variant.rightPath}` === currentKey
      ) || null;
    activeVariantByGroup.set(group.id, activeVariant);
  });

  el.artifactComparePresets.innerHTML = `
    <div class="compare-strip-title">${escapeHtml(t("artifacts.preview.compare.preset.title"))}</div>
    <div class="compare-preset-list">
      ${groups
        .map((group) => {
          const variants = Array.isArray(group.variants) ? group.variants : [];
          const activeVariant = activeVariantByGroup.get(group.id) || variants[0] || null;
          if (!activeVariant) return "";
          const active = activeVariantByGroup.get(group.id) ? " is-active" : "";
          const showSelect = variants.length > 1;
          return `
            <div class="compare-preset-group${active}" data-compare-preset-group="${escapeAttr(group.id)}">
              <button
                type="button"
                class="ghost compare-preset-btn${active}"
                data-compare-preset-group-btn="${escapeAttr(group.id)}"
              >${escapeHtml(group.label)}</button>
              ${
                showSelect
                  ? `<select class="compare-preset-select" data-compare-preset-group-select="${escapeAttr(group.id)}">
                      ${variants
                        .map(
                          (variant) =>
                            `<option value="${escapeAttr(variant.id)}"${
                              variant.id === activeVariant.id ? " selected" : ""
                            }>${escapeHtml(variant.label)}</option>`
                        )
                        .join("")}
                    </select>`
                  : ""
              }
            </div>
          `;
        })
        .join("")}
    </div>
  `;

  const variantById = new Map();
  groups.forEach((group) => {
    (Array.isArray(group.variants) ? group.variants : []).forEach((variant) => {
      variantById.set(variant.id, variant);
    });
  });

  const applyVariant = async (variantId) => {
    const variant = variantById.get(String(variantId || "").trim());
    if (!variant) return;
    state.artifactCompareLeftPath = variant.leftPath;
    state.artifactCompareRightPath = variant.rightPath;
    renderArtifactCompareSelects();
    renderCopilotContext();
    await compareSelected3dArtifacts();
  };

  Array.from(el.artifactComparePresets.querySelectorAll("[data-compare-preset-group-btn]")).forEach((btn) => {
    btn.addEventListener("click", async () => {
      const groupId = String(btn.getAttribute("data-compare-preset-group-btn") || "").trim();
      const select = el.artifactComparePresets.querySelector(`[data-compare-preset-group-select="${groupId}"]`);
      const chosenVariantId =
        select instanceof HTMLSelectElement && select.value
          ? select.value
          : activeVariantByGroup.get(groupId)?.id || "";
      await applyVariant(chosenVariantId);
    });
  });

  Array.from(el.artifactComparePresets.querySelectorAll("[data-compare-preset-group-select]")).forEach((select) => {
    select.addEventListener("change", async () => {
      const groupId = String(select.getAttribute("data-compare-preset-group-select") || "").trim();
      if (!groupId || !(select instanceof HTMLSelectElement)) return;
      if (!activeVariantByGroup.get(groupId)) return;
      await applyVariant(select.value);
    });
  });
}

function chooseDefaultComparePaths(structureItems) {
  const paths = new Set(structureItems.map((item) => String(item?.path || "")));
  if (!paths.has(state.artifactCompareLeftPath)) state.artifactCompareLeftPath = "";
  if (!paths.has(state.artifactCompareRightPath)) state.artifactCompareRightPath = "";
  const refs = resolveCompareReferenceItems(structureItems);

  if (!state.artifactCompareLeftPath) {
    state.artifactCompareLeftPath = String(
      refs.input?.path ||
        refs.wt?.path ||
        refs.working?.path ||
        refs.rfd3Backbone?.path ||
        refs.bioemuBackbone?.path ||
        structureItems[0]?.path ||
        ""
    );
  }

  if (!state.artifactCompareRightPath) {
    const candidates = structureItems.filter(
      (item) => String(item?.path || "") && String(item?.path || "") !== state.artifactCompareLeftPath
    );
    const preferredPaths = [];
    if (state.artifactCompareLeftPath === String(refs.input?.path || "").trim()) {
      preferredPaths.push(refs.bioemuBackbone?.path, refs.wt?.path, refs.rfd3Backbone?.path, refs.working?.path);
    } else {
      preferredPaths.push(refs.input?.path, refs.bioemuBackbone?.path, refs.rfd3Backbone?.path, refs.wt?.path);
    }
    const preferred = preferredPaths
      .map((path) => String(path || "").trim())
      .find((path) => path && path !== state.artifactCompareLeftPath && paths.has(path));
    if (preferred) {
      state.artifactCompareRightPath = preferred;
    } else {
      const pick = (predicate) =>
        candidates.find((item) => predicate(String(item?.path || ""), artifactMetaForPath(item?.path)));
      const designItem =
        pick(
          (path, meta) =>
            compareArtifactRoleKey(meta) === "af2_candidate" &&
            /\/ranked_\d+\.pdb$/i.test(path) &&
            !/(?:^|\/)recovered[_/]/i.test(path)
        ) ||
        pick((_path, meta) => compareArtifactRoleKey(meta) === "backbone_snapshot") ||
        pick((_path, meta) => compareArtifactRoleKey(meta) === "source_output") ||
        candidates[0];
      state.artifactCompareRightPath = String(designItem?.path || "");
    }
  }

  if (state.artifactCompareRightPath === state.artifactCompareLeftPath) {
    const fallback = structureItems.find((item) => String(item?.path || "") !== state.artifactCompareLeftPath);
    state.artifactCompareRightPath = String(fallback?.path || "");
  }
}

function renderArtifactCompareSelects() {
  if (!el.artifactCompareLeft || !el.artifactCompareRight) return;
  if (el.artifactCompareMode) {
    const mode = state.artifactCompareMode === "sequence" ? "sequence" : "structure";
    el.artifactCompareMode.value = mode;
  }
  const structureItems = collectCompareStructureItems(state.artifacts);
  if (!structureItems.length) {
    if (el.artifactCompareRefs) el.artifactCompareRefs.innerHTML = "";
    if (el.artifactComparePresets) el.artifactComparePresets.innerHTML = "";
  }

  chooseDefaultComparePaths(structureItems);
  renderCompareReferenceStrip(structureItems);
  renderComparePresetStrip(structureItems);
  const fill = (selectEl, placeholderKey) => {
    selectEl.innerHTML = "";
    const first = document.createElement("option");
    first.value = "";
    first.textContent = t(placeholderKey);
    selectEl.appendChild(first);
    const groups = new Map();
    structureItems.forEach((item) => {
      const path = String(item?.path || "");
      const meta = artifactMetaForPath(path);
      const groupKey = compareArtifactGroupKey(meta);
      if (!groups.has(groupKey)) groups.set(groupKey, []);
      groups.get(groupKey).push(item);
    });
    const orderedGroups = ["references", "backbones", "af2_candidates", "source_outputs", "other"];
    orderedGroups.forEach((groupKey) => {
      const items = groups.get(groupKey) || [];
      if (!items.length) return;
      const optgroup = document.createElement("optgroup");
      optgroup.label = compareArtifactGroupLabel(groupKey);
      items.forEach((item) => {
        const path = String(item.path || "");
        const meta = artifactMetaForPath(path);
        const opt = document.createElement("option");
        opt.value = path;
        opt.textContent = buildArtifactCompareOptionLabel(path, meta);
        optgroup.appendChild(opt);
      });
      selectEl.appendChild(optgroup);
    });
  };
  fill(el.artifactCompareLeft, "artifacts.preview.compare.left");
  fill(el.artifactCompareRight, "artifacts.preview.compare.right");

  const leftPaths = new Set(structureItems.map((item) => String(item.path || "")));
  const rightPaths = leftPaths;
  el.artifactCompareLeft.value = leftPaths.has(state.artifactCompareLeftPath)
    ? state.artifactCompareLeftPath
    : "";
  el.artifactCompareRight.value = rightPaths.has(state.artifactCompareRightPath)
    ? state.artifactCompareRightPath
    : "";
}

async function compareSelected3dArtifacts() {
  if (!state.currentRunId) return;
  const leftPath = String(state.artifactCompareLeftPath || "").trim();
  const rightPath = String(state.artifactCompareRightPath || "").trim();
  if (!leftPath || !rightPath) {
    setComparePreviewPlaceholder("artifacts.preview.compare.missing");
    return;
  }
  try {
    const targetSequencePromise = readCompareTargetSequence(state.currentRunId);
    const inputPdbPromise = readCompareInputPdbText(state.currentRunId);
    const workingPdbPromise = readCompareWorkingPdbText(state.currentRunId);
    const wtPdbPromise = readCompareWtPdbText(state.currentRunId);
    const [leftResult, rightResult, targetSequence, inputPdbText, workingPdbText, wtPdbText] = await Promise.all([
      apiCall("pipeline.read_artifact", {
        run_id: state.currentRunId,
        path: leftPath,
        max_bytes: 500000,
      }),
      apiCall("pipeline.read_artifact", {
        run_id: state.currentRunId,
        path: rightPath,
        max_bytes: 500000,
      }),
      targetSequencePromise,
      inputPdbPromise,
      workingPdbPromise,
      wtPdbPromise,
    ]);
    const [leftText, rightText] = await Promise.all([
      normalizeComparePdbTextForArtifact(state.currentRunId, leftPath, String(leftResult?.text || "")),
      normalizeComparePdbTextForArtifact(state.currentRunId, rightPath, String(rightResult?.text || "")),
    ]);
    const [leftMeta, rightMeta] = await Promise.all([
      buildComparePreviewCardData(state.currentRunId, leftPath, leftText, {
        targetSequence,
        inputPdbText,
        workingPdbText,
        wtPdbText,
      }),
      buildComparePreviewCardData(state.currentRunId, rightPath, rightText, {
        targetSequence,
        inputPdbText,
        workingPdbText,
        wtPdbText,
      }),
    ]);
    render3dComparison(
      {
        path: leftPath,
        text: leftText,
        format: /\.sdf$/i.test(leftPath) ? "sdf" : "pdb",
      },
      {
        path: rightPath,
        text: rightText,
        format: /\.sdf$/i.test(rightPath) ? "sdf" : "pdb",
      },
      state.artifactCompareMode,
      { left: leftMeta, right: rightMeta }
    );
  } catch (err) {
    setComparePreviewPlaceholder("artifacts.preview.compare.failed", {
      error: err.message,
    });
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function normalizeMarkdownTarget(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const wrapped = text.match(/^<(.+)>$/);
  return wrapped ? String(wrapped[1] || "").trim() : text;
}

function isSafeMarkdownTarget(target) {
  return !/^(?:javascript|vbscript|file):/i.test(String(target || "").trim());
}

function isExternalMarkdownTarget(target) {
  return /^(?:https?:|data:|blob:)/i.test(String(target || "").trim());
}

function normalizeArtifactMarkdownPath(target) {
  const raw = String(target || "").trim();
  if (!raw) return "";
  const stripped = raw.split("#", 1)[0].split("?", 1)[0];
  const normalized = stripped.replace(/^\.\/+/, "").replace(/^\/+/, "");
  try {
    return decodeURIComponent(normalized);
  } catch (_err) {
    return normalized;
  }
}

function imageMimeTypeFromPath(path) {
  const clean = String(path || "").split("#", 1)[0].split("?", 1)[0];
  const ext = clean.includes(".") ? clean.split(".").pop().toLowerCase() : "";
  if (ext === "svg") return "image/svg+xml";
  if (ext === "png") return "image/png";
  if (ext === "jpg" || ext === "jpeg") return "image/jpeg";
  if (ext === "gif") return "image/gif";
  if (ext === "webp") return "image/webp";
  return "application/octet-stream";
}

const TRANSPARENT_PIXEL_DATA_URI = "data:image/gif;base64,R0lGODlhAQABAAAAACwAAAAAAQABAAA=";

function utf8ToBase64(text) {
  const bytes = new TextEncoder().encode(String(text || ""));
  let binary = "";
  const chunkSize = 8192;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

function reportChartSvgForPath(path) {
  const key = String(path || "")
    .trim()
    .split("/")
    .pop()
    .toLowerCase();
  const rows = filteredHitListRows({ applyLimit: false });
  if (!rows.length) return "";
  if (key === "plddt_rmsd.svg") {
    return normalizeSvgAttachmentText(buildPlddtRmsdScatter(rows)?.svg || "");
  }
  if (key === "score_hist.svg") {
    return normalizeSvgAttachmentText(buildScoreHistogram(rows)?.svg || "");
  }
  if (key === "tier_pass.svg") {
    return normalizeSvgAttachmentText(buildTierPassRateChart(rows)?.svg || "");
  }
  return "";
}

async function reportCompareSvgForPath(path, runId) {
  const key = String(path || "")
    .trim()
    .split("/")
    .pop()
    .toLowerCase();
  const wantsStructure = key === "structure_diff.svg";
  const wantsSequence = key === "sequence_diff.svg";
  if (!wantsStructure && !wantsSequence) return "";
  const compare = selectReportComparePaths();
  const leftPath = String(compare?.leftPath || "").trim();
  const rightPath = String(compare?.rightPath || "").trim();
  if (!leftPath || !rightPath) return "";
  if (!/\.pdb$/i.test(leftPath) || !/\.pdb$/i.test(rightPath)) return "";
  try {
    const [leftResult, rightResult] = await Promise.all([
      apiCall("pipeline.read_artifact", { run_id: runId, path: leftPath, max_bytes: 800000 }),
      apiCall("pipeline.read_artifact", { run_id: runId, path: rightPath, max_bytes: 800000 }),
    ]);
    const [leftText, rightText] = await Promise.all([
      normalizeComparePdbTextForArtifact(runId, leftPath, String(leftResult?.text || "")),
      normalizeComparePdbTextForArtifact(runId, rightPath, String(rightResult?.text || "")),
    ]);
    if (!leftText.trim() || !rightText.trim()) return "";
    if (wantsStructure) {
      return normalizeSvgAttachmentText(
        buildStructureDiffSvg(computePdbStructuralDiff(leftText, rightText), leftPath, rightPath)
      );
    }
    return normalizeSvgAttachmentText(
      buildSequenceDiffSvg(computePdbSequenceDiff(leftText, rightText), leftPath, rightPath)
    );
  } catch (_err) {
    return "";
  }
}

async function resolveReportModalImageBase64(runId, artifactPath, cacheKey) {
  let base64 = String(state.reportModalImageCache[cacheKey] || "");
  if (base64) return base64;
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: runId,
      path: artifactPath,
      base64: true,
      max_bytes: 4000000,
    });
    base64 = String(result?.base64 || "");
  } catch (_err) {
    base64 = "";
  }
  if (!base64 && /^report_assets\/.+\.svg$/i.test(artifactPath)) {
    let svgText = reportChartSvgForPath(artifactPath);
    if (!svgText) {
      svgText = await reportCompareSvgForPath(artifactPath, runId);
    }
    if (svgText) {
      base64 = utf8ToBase64(svgText);
    }
  }
  if (base64) {
    state.reportModalImageCache[cacheKey] = base64;
  }
  return base64;
}

async function hydrateReportModalArtifactImages() {
  if (!el.reportModalContent) return;
  if (state.reportModalMode !== "rendered") return;
  const runId = String(state.currentRunId || "").trim();
  if (!runId) return;
  const pending = Array.from(el.reportModalContent.querySelectorAll("img[data-artifact-path]"));
  if (!pending.length) return;

  state.reportModalRenderToken += 1;
  const token = state.reportModalRenderToken;
  await Promise.all(
    pending.map(async (img) => {
      const artifactPath = normalizeArtifactMarkdownPath(img.dataset.artifactPath || "");
      if (!artifactPath) return;
      const cacheKey = `${runId}::${artifactPath}`;
      const base64 = await resolveReportModalImageBase64(runId, artifactPath, cacheKey);
      if (token !== state.reportModalRenderToken) return;
      if (!base64) {
        img.src = TRANSPARENT_PIXEL_DATA_URI;
        img.classList.add("report-image-missing");
        img.title = `missing artifact: ${artifactPath}`;
        return;
      }
      img.src = `data:${imageMimeTypeFromPath(artifactPath)};base64,${base64}`;
      img.classList.remove("report-image-missing");
      img.removeAttribute("data-artifact-path");
    })
  ).catch(() => null);
}

function renderMarkdown(text) {
  const raw = String(text || "").replace(/\r\n?/g, "\n");
  const parts = [];
  const fenceRe = /```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  while ((match = fenceRe.exec(raw))) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", content: raw.slice(lastIndex, match.index) });
    }
    parts.push({ type: "code", lang: match[1] || "", content: match[2] || "" });
    lastIndex = fenceRe.lastIndex;
  }
  if (lastIndex < raw.length) {
    parts.push({ type: "text", content: raw.slice(lastIndex) });
  }

  const html = [];
  parts.forEach((part) => {
    if (part.type === "code") {
      const code = escapeHtml(part.content);
      html.push(`<pre><code class="lang-${escapeHtml(part.lang)}">${code}</code></pre>`);
      return;
    }

    const lines = String(part.content || "").split("\n");
    let inUl = false;
    let inOl = false;
    let inPara = false;
    let inTable = false;

    const closeLists = () => {
      if (inUl) {
        html.push("</ul>");
        inUl = false;
      }
      if (inOl) {
        html.push("</ol>");
        inOl = false;
      }
    };

    const closePara = () => {
      if (inPara) {
        html.push("</p>");
        inPara = false;
      }
    };

    const closeTable = () => {
      if (inTable) {
        html.push("</tbody></table>");
        inTable = false;
      }
    };

    const formatInline = (line) => {
      let out = escapeHtml(line);
      const codeTokens = [];
      out = out.replace(/`([^`]+)`/g, (_match, code) => {
        const token = `@@CODE_${codeTokens.length}@@`;
        codeTokens.push(`<code>${code}</code>`);
        return token;
      });
      const imageTokens = [];
      out = out.replace(/!\[([^\]]*)\]\((\S+?)(?:\s+"[^"]*")?\)/g, (_match, alt, target) => {
        const normalizedTarget = normalizeMarkdownTarget(target);
        if (!normalizedTarget || !isSafeMarkdownTarget(normalizedTarget)) return _match;
        const token = `@@IMG_${imageTokens.length}@@`;
        if (isExternalMarkdownTarget(normalizedTarget)) {
          imageTokens.push(
            `<img src="${escapeAttr(normalizedTarget)}" alt="${escapeAttr(alt)}" loading="lazy" />`
          );
        } else {
          imageTokens.push(
            `<img src="${TRANSPARENT_PIXEL_DATA_URI}" data-artifact-path="${escapeAttr(
              normalizedTarget
            )}" alt="${escapeAttr(alt)}" loading="lazy" />`
          );
        }
        return token;
      });
      out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
      imageTokens.forEach((html, idx) => {
        out = out.replace(`@@IMG_${idx}@@`, html);
      });
      codeTokens.forEach((html, idx) => {
        out = out.replace(`@@CODE_${idx}@@`, html);
      });
      return out;
    };

    const isTableLine = (line) => /^\s*\|.*\|\s*$/.test(String(line || ""));
    const splitCells = (line) =>
      String(line || "")
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => String(cell).trim());
    const isSeparatorLine = (line) => {
      if (!isTableLine(line)) return false;
      const cells = splitCells(line);
      if (!cells.length) return false;
      return cells.every((cell) => /^:?-{3,}:?$/.test(cell));
    };
    const alignOf = (cell) => {
      const token = String(cell || "").trim();
      if (/^:-+:$/.test(token)) return "center";
      if (/^-+:$/.test(token)) return "right";
      return "left";
    };
    const cellHtml = (value, align) => `<td style="text-align:${align}">${formatInline(value)}</td>`;
    const headHtml = (value, align) => `<th style="text-align:${align}">${formatInline(value)}</th>`;

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      const trimmed = line.trim();
      if (!trimmed) {
        closeTable();
        closeLists();
        closePara();
        continue;
      }

      if (/^<!--[\s\S]*-->$/.test(trimmed)) {
        continue;
      }

      if (isTableLine(line) && i + 1 < lines.length && isSeparatorLine(lines[i + 1])) {
        closeLists();
        closePara();
        closeTable();

        const headerCells = splitCells(line);
        const sepCells = splitCells(lines[i + 1]);
        const aligns = headerCells.map((_value, idx) => alignOf(sepCells[idx] || "---"));
        html.push('<table class="md-table"><thead><tr>');
        headerCells.forEach((cell, idx) => {
          html.push(headHtml(cell, aligns[idx] || "left"));
        });
        html.push("</tr></thead><tbody>");
        inTable = true;
        i += 1;

        while (i + 1 < lines.length && isTableLine(lines[i + 1])) {
          const rowLine = lines[i + 1];
          if (isSeparatorLine(rowLine)) {
            i += 1;
            continue;
          }
          const rowCells = splitCells(rowLine);
          html.push("<tr>");
          for (let col = 0; col < Math.max(headerCells.length, rowCells.length); col += 1) {
            html.push(cellHtml(rowCells[col] || "", aligns[col] || "left"));
          }
          html.push("</tr>");
          i += 1;
        }
        continue;
      }

      closeTable();

      const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
      if (heading) {
        closeLists();
        closePara();
        const level = heading[1].length;
        html.push(`<h${level}>${formatInline(heading[2])}</h${level}>`);
        continue;
      }

      const olMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
      if (olMatch) {
        closePara();
        if (!inOl) {
          closeLists();
          html.push("<ol>");
          inOl = true;
        }
        html.push(`<li>${formatInline(olMatch[2])}</li>`);
        continue;
      }

      const ulMatch = trimmed.match(/^[-*]\s+(.*)$/);
      if (ulMatch) {
        closePara();
        if (!inUl) {
          closeLists();
          html.push("<ul>");
          inUl = true;
        }
        html.push(`<li>${formatInline(ulMatch[1])}</li>`);
        continue;
      }

      closeLists();
      if (!inPara) {
        html.push("<p>");
        inPara = true;
        html.push(formatInline(trimmed));
      } else {
        html.push("<br />" + formatInline(trimmed));
      }
    }

    closeTable();
    closeLists();
    closePara();
  });

  return html.join("\n");
}

async function refreshArtifacts(options = {}) {
  const runId = String(options?.runId || state.currentRunId || "").trim();
  if (!runId) return;
  try {
    const result = await apiCall("pipeline.list_artifacts", {
      run_id: runId,
      max_depth: 6,
      limit: 300,
    });
    if (runId !== String(state.currentRunId || "").trim()) return;
    state.artifacts = result.artifacts || [];
    rebuildArtifactMetaIndex(state.artifacts);
    renderAllArtifactViews(state.artifacts);
    refreshArtifactSelects();
    void refreshArtifactComparisonSummary();
    updateReportArtifactLinks(el.reportContent ? el.reportContent.value : "");
    renderWorkflowReviewPanel(state.lastRunStatus);
    if (state.analyzeArtifactPath) {
      void previewAnalyzeSelectedArtifact();
    }
    markArtifactsRefreshed(runId);
    renderCopilotContext();
  } catch (err) {
    setMessage(t("artifact.error", { error: err.message }), "ai");
  }
}

function renderAgentPanel(items) {
  if (!el.agentPanelList) return;
  const events = Array.isArray(items) ? items : [];
  if (!events.length) {
    el.agentPanelList.innerHTML = `<div class="placeholder">${t("agent.empty")}</div>`;
    return;
  }
  el.agentPanelList.innerHTML = "";
  events.forEach((item) => {
    const stage = escapeHtml(item?.stage || "-");
    const created = escapeHtml(item?.created_at || "");
    const consensus = item?.consensus || {};
    const decisionRaw = String(consensus?.decision || "unknown").toLowerCase();
    const decision = escapeHtml(decisionRaw);
    const decisionClass = `decision-${decisionRaw.replace(/[^a-z0-9_-]+/g, "") || "unknown"}`;
    const confidence =
      typeof consensus?.confidence === "number" ? consensus.confidence.toFixed(2) : "-";
    const rationale = escapeHtml(consensus?.rationale || "");
    const error = escapeHtml(item?.error || "");
    const actions = Array.isArray(consensus?.actions) ? consensus.actions : [];
    const actionText = actions.length ? escapeHtml(actions.join("; ")) : "";
    const interpretations = Array.isArray(consensus?.interpretations) ? consensus.interpretations : [];
    const interpretationText = interpretations.length ? escapeHtml(interpretations.join("; ")) : "";
    const agents = Array.isArray(item?.agents) ? item.agents : [];
    const agentBadges = agents
      .map((agent) => {
        const name = escapeHtml(agent?.name || "agent");
        const status = String(agent?.status || "info").toLowerCase();
        const statusClass = `status-${status.replace(/[^a-z0-9_-]+/g, "") || "info"}`;
        return `<span class="agent-badge ${statusClass}">${name}:${status}</span>`;
      })
      .join("");
    const agentDetails = agents
      .map((agent) => `${agent?.name || "agent"}: ${agent?.summary || ""}`)
      .filter((text) => String(text).trim())
      .map((text) => escapeHtml(text))
      .join(" · ");

    const div = document.createElement("div");
    div.className = "agent-event";
    div.innerHTML = `
      <div class="agent-meta">
        <span class="agent-stage">${stage}</span>
        <span class="agent-decision ${decisionClass}">${decision}</span>
        <span class="agent-badge">${confidence}</span>
        <span class="agent-details">${created}</span>
      </div>
      <div class="agent-badges">${agentBadges}</div>
      ${agentDetails ? `<div class="agent-details">${agentDetails}</div>` : ""}
      ${rationale ? `<div class="agent-details">rationale: ${rationale}</div>` : ""}
      ${error ? `<div class="agent-details">error: ${error}</div>` : ""}
      ${actionText ? `<div class="agent-details">actions: ${actionText}</div>` : ""}
      ${interpretationText ? `<div class="agent-details">interpretation: ${interpretationText}</div>` : ""}
      <div class="agent-actions">
        <input class="agent-note" type="text" placeholder="${escapeHtml(t("agent.feedback.note"))}" />
        <button class="ghost agent-rate" data-rating="good">${t("agent.feedback.good")}</button>
        <button class="ghost agent-rate" data-rating="bad">${t("agent.feedback.bad")}</button>
        <span class="agent-feedback-status"></span>
      </div>
    `;
    const noteInput = div.querySelector(".agent-note");
    const statusEl = div.querySelector(".agent-feedback-status");
    const buttons = div.querySelectorAll(".agent-rate");
    buttons.forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!state.currentRunId) {
          if (statusEl) statusEl.textContent = t("export.selectRun");
          return;
        }
        const rating = btn.dataset.rating || "good";
        if (statusEl) statusEl.textContent = t("agent.feedback.saving");
        try {
          await apiCall("pipeline.submit_feedback", {
            run_id: state.currentRunId,
            rating,
            reasons: ["agent_panel"],
            comment: noteInput ? noteInput.value.trim() : "",
            stage: item?.stage || "",
          });
          if (noteInput) noteInput.value = "";
          if (statusEl) statusEl.textContent = t("agent.feedback.saved");
          await refreshFeedback();
          await loadReport();
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = t("agent.feedback.failed", { error: err.message });
          }
        }
      });
    });
    el.agentPanelList.appendChild(div);
  });
}

async function refreshAgentPanel() {
  if (!el.agentPanelList) return;
  if (!state.currentRunId) {
    el.agentPanelList.innerHTML = `<div class="placeholder">${t("agent.empty")}</div>`;
    if (el.agentPanelStatus) el.agentPanelStatus.textContent = "";
    return;
  }
  if (el.agentPanelStatus) el.agentPanelStatus.textContent = t("agent.loading");
  try {
    const result = await apiCall("pipeline.list_agent_events", {
      run_id: state.currentRunId,
      limit: 50,
    });
    renderAgentPanel(result.items || []);
    if (el.agentPanelStatus) el.agentPanelStatus.textContent = "";
  } catch (err) {
    if (el.agentPanelStatus) {
      el.agentPanelStatus.textContent = t("agent.failed", { error: err.message });
    }
  }
}

async function loadRunReportModal({ lang } = {}) {
  if (!state.currentRunId) {
    setMessage(t("agent.report.missing"), "ai");
    return;
  }
  const resolvedLang = resolveReportLang(lang);
  const isKo = resolvedLang === "ko";
  const title = t("agent.viewReport");
  const filename = isKo ? "report_ko.md" : "report.md";
  openReportModal(title, t("agent.report.loading"));
  try {
    const result = await apiCall("pipeline.get_report", { run_id: state.currentRunId });
    let text = "";
    if (isKo) {
      text = result?.report_ko || "";
      if (!text.trim()) {
        text = result?.report || "";
      }
    } else {
      text = result?.report || "";
    }
    if (!text.trim()) {
      openReportModal(title, t("agent.report.missing"));
      return;
    }
    openReportModal(title, text, filename);
  } catch (err) {
    if (isHttp400Error(err)) {
      openReportModal(title, t("agent.report.missing"));
      return;
    }
    openReportModal(title, t("agent.report.failed", { error: err.message }));
  }
}

async function loadAgentReportModal() {
  if (!state.currentRunId) {
    setMessage(t("agent.report.missing"), "ai");
    return;
  }
  const isKo = resolveReportLang() === "ko";
  const filename = isKo ? "agent_panel_report_ko.md" : "agent_panel_report.md";
  openReportModal(t("agent.viewAgentReport"), t("agent.report.loading"));
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: state.currentRunId,
      path: filename,
      max_bytes: 2_000_000,
    });
    const text = result?.text || "";
    if (!text.trim()) {
      if (isKo) {
        const fallback = await apiCall("pipeline.read_artifact", {
          run_id: state.currentRunId,
          path: "agent_panel_report.md",
          max_bytes: 2_000_000,
        });
        const fallbackText = fallback?.text || "";
        if (fallbackText.trim()) {
          openReportModal(t("agent.viewAgentReport"), fallbackText, "agent_panel_report.md");
          return;
        }
      }
      openReportModal(t("agent.viewAgentReport"), t("agent.report.missing"));
      return;
    }
    openReportModal(t("agent.viewAgentReport"), text, filename);
  } catch (err) {
    if (isKo) {
      try {
        const fallback = await apiCall("pipeline.read_artifact", {
          run_id: state.currentRunId,
          path: "agent_panel_report.md",
          max_bytes: 2_000_000,
        });
        const fallbackText = fallback?.text || "";
        if (fallbackText.trim()) {
          openReportModal(t("agent.viewAgentReport"), fallbackText, "agent_panel_report.md");
          return;
        }
        if (isHttp400Error(err)) {
          openReportModal(t("agent.viewAgentReport"), t("agent.report.missing"));
          return;
        }
      } catch (fallbackErr) {
        if (isHttp400Error(err) || isHttp400Error(fallbackErr)) {
          openReportModal(t("agent.viewAgentReport"), t("agent.report.missing"));
          return;
        }
        openReportModal(
          t("agent.viewAgentReport"),
          t("agent.report.failed", { error: fallbackErr.message })
        );
        return;
      }
    }
    if (isHttp400Error(err)) {
      openReportModal(t("agent.viewAgentReport"), t("agent.report.missing"));
      return;
    }
    openReportModal(t("agent.viewAgentReport"), t("agent.report.failed", { error: err.message }));
  }
}

function formatStageLabel(stage) {
  const dynamicProvider = currentRunAf2Provider();
  if (stage === "af2") {
    return af2ProviderName(dynamicProvider, state.lang || "en");
  }
  if (stage === "af2_target") {
    return af2ProviderTargetLabel(dynamicProvider, state.lang || "en");
  }
  if (stage === "wt_af2") {
    return af2ProviderWtLabel(dynamicProvider, state.lang || "en");
  }
  const entry = STAGE_LABELS[stage];
  if (entry) {
    const lang = state.lang || "en";
    return entry[lang] || entry.en || stage;
  }
  return stage;
}

function rebuildArtifactMetaIndex(items) {
  const index = {};
  (items || []).forEach((item) => {
    const path = String(item?.path || "");
    if (!path) return;
    index[path] = artifactMetaFromPath(path);
  });
  state.artifactMetaByPath = index;
}

function artifactMetaForPath(path) {
  const key = String(path || "");
  if (!key) return artifactMetaFromPath(key);
  const cached = state.artifactMetaByPath ? state.artifactMetaByPath[key] : null;
  if (cached) return cached;
  return artifactMetaFromPath(key);
}

function tierFromPath(path) {
  return artifactMetaForPath(path).tier;
}

function isStructurePath(path) {
  return /\.(pdb|sdf)$/i.test(String(path || ""));
}

function isStructureArtifactItem(item) {
  return item?.type === "file" && isStructurePath(item?.path);
}

function artifactTypeFromItem(item) {
  if (item?.type === "dir") return "dir";
  const match = String(item?.path || "").match(/\.([^.\/]+)$/);
  if (match) return match[1].toLowerCase();
  return "file";
}

function renderArtifactFilters(items, view = "monitor") {
  const { stageFilterEl, tierFilterEl, typeFilterEl } = getArtifactViewConfig(view);
  if (!stageFilterEl || !tierFilterEl || !typeFilterEl) return;
  const filters = artifactFiltersForView(view);
  const stageSet = new Set();
  const tierSet = new Set();
  const typeSet = new Set();
  (items || []).forEach((item) => {
    const meta = artifactMetaForPath(item.path);
    const stage = meta.stage;
    if (stage) stageSet.add(stage);
    const tier = meta.tier;
    if (tier) tierSet.add(tier);
    const type = artifactTypeFromItem(item);
    if (type) typeSet.add(type);
  });

  const stageOrder = ARTIFACT_STAGE_ORDER.filter((stage) => stageSet.has(stage));
  const extraStages = Array.from(stageSet).filter((s) => !stageOrder.includes(s)).sort();
  const stages = [...stageOrder, ...extraStages];
  const tiers = Array.from(tierSet).sort((a, b) => {
    const na = Number(a);
    const nb = Number(b);
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
    return String(a).localeCompare(String(b));
  });
  const types = Array.from(typeSet).sort();

  const setOptions = (selectEl, options, allLabel, current) => {
    selectEl.innerHTML = "";
    const allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = allLabel;
    selectEl.appendChild(allOption);
    options.forEach((opt) => {
      const option = document.createElement("option");
      option.value = opt;
      option.textContent = opt;
      selectEl.appendChild(option);
    });
    if (!options.includes(current)) {
      selectEl.value = "all";
      return "all";
    }
    selectEl.value = current;
    return current;
  };

  const stageOptions = stages.map((stage) => ({ value: stage, label: formatStageLabel(stage) }));
  const setStageOptions = (selectEl, options, allLabel, current) => {
    selectEl.innerHTML = "";
    const allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = allLabel;
    selectEl.appendChild(allOption);
    options.forEach((opt) => {
      const option = document.createElement("option");
      option.value = opt.value;
      option.textContent = opt.label;
      selectEl.appendChild(option);
    });
    const values = options.map((opt) => opt.value);
    if (!values.includes(current)) {
      selectEl.value = "all";
      return "all";
    }
    selectEl.value = current;
    return current;
  };

  filters.stage = setStageOptions(
    stageFilterEl,
    stageOptions,
    t("artifacts.filter.allStages"),
    filters.stage
  );
  filters.tier = setOptions(
    tierFilterEl,
    tiers,
    t("artifacts.filter.allTiers"),
    filters.tier
  );
  filters.type = setOptions(
    typeFilterEl,
    types,
    t("artifacts.filter.allTypes"),
    filters.type
  );
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
    return { __parse_error: t("metrics.parseError", { error: err.message }) };
  }
  return { __parse_error: t("metrics.objectRequired") };
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
    if (el.feedbackStatus) el.feedbackStatus.textContent = t("export.selectRun");
    return;
  }
  const sep = format === "tsv" ? "\t" : ",";
  const ext = format === "tsv" ? "tsv" : "csv";
  if (el.feedbackStatus) el.feedbackStatus.textContent = t("export.exporting");
  try {
    const result = await apiCall("pipeline.list_feedback", {
      run_id: state.currentRunId,
      limit: EXPORT_LIMIT,
    });
    const items = result.items || [];
    if (!items.length) {
      if (el.feedbackStatus) el.feedbackStatus.textContent = t("export.none.feedback");
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
    if (el.feedbackStatus) {
      el.feedbackStatus.textContent = t("export.done", { count: rows.length });
    }
  } catch (err) {
    if (el.feedbackStatus) {
      el.feedbackStatus.textContent = t("export.failed", { error: err.message });
    }
  }
}

async function exportExperiments(format) {
  if (!state.currentRunId) {
    if (el.experimentStatus) el.experimentStatus.textContent = t("export.selectRun");
    return;
  }
  const sep = format === "tsv" ? "\t" : ",";
  const ext = format === "tsv" ? "tsv" : "csv";
  if (el.experimentStatus) el.experimentStatus.textContent = t("export.exporting");
  try {
    const result = await apiCall("pipeline.list_experiments", {
      run_id: state.currentRunId,
      limit: EXPORT_LIMIT,
    });
    const items = result.items || [];
    if (!items.length) {
      if (el.experimentStatus) el.experimentStatus.textContent = t("export.none.experiments");
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
    if (el.experimentStatus) {
      el.experimentStatus.textContent = t("export.done", { count: rows.length });
    }
  } catch (err) {
    if (el.experimentStatus) {
      el.experimentStatus.textContent = t("export.failed", { error: err.message });
    }
  }
}

async function submitFeedback() {
  if (!state.currentRunId) {
    if (el.feedbackStatus) el.feedbackStatus.textContent = t("export.selectRun");
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
    if (el.feedbackStatus) el.feedbackStatus.textContent = t("feedback.saved");
    if (el.feedbackComment) el.feedbackComment.value = "";
    state.feedbackReasons = [];
    renderFeedbackControls();
    await refreshFeedback();
    await loadReport();
  } catch (err) {
    if (el.feedbackStatus) {
      el.feedbackStatus.textContent = t("feedback.failed", { error: err.message });
    }
  }
}

async function submitReportReview() {
  if (!state.currentRunId) {
    if (el.reportReviewStatus) el.reportReviewStatus.textContent = t("export.selectRun");
    return;
  }
  const payload = {
    run_id: state.currentRunId,
    rating: state.reportReviewRating || "good",
    reasons: state.reportReviewReasons || [],
    comment: el.reportReviewComment ? el.reportReviewComment.value.trim() : "",
    stage: "report",
    artifact_path: "report.md",
  };
  try {
    await apiCall("pipeline.submit_feedback", payload);
    if (el.reportReviewStatus) el.reportReviewStatus.textContent = t("report.review.saved");
    if (el.reportReviewComment) el.reportReviewComment.value = "";
    state.reportReviewReasons = [];
    renderReportReviewControls();
    await refreshFeedback();
    await loadReport();
  } catch (err) {
    if (el.reportReviewStatus) {
      el.reportReviewStatus.textContent = t("report.review.failed", { error: err.message });
    }
  }
}

async function refreshFeedback() {
  if (!state.currentRunId || !el.feedbackList) return;
  try {
    const result = await apiCall("pipeline.list_feedback", {
      run_id: state.currentRunId,
      limit: 100,
    });
    const items = result.items || [];
    state.feedbackCount = items.length;
    updateAnalyzeSummary();
    if (!items.length) {
      el.feedbackList.innerHTML = `<div class="placeholder">${t("feedback.none")}</div>`;
      return;
    }
    el.feedbackList.innerHTML = "";
    items.slice(0, 5).forEach((item) => {
      const div = document.createElement("div");
      div.className = "run-item";
      const rating = labelFromMap(item.rating, FEEDBACK_RATING_KEYS);
      const reasons = Array.isArray(item.reasons)
        ? item.reasons
        : item.reasons
          ? [item.reasons]
          : [];
      const reason = reasons.length
        ? reasons.map((value) => labelFromMap(value, FEEDBACK_REASON_KEYS)).join(", ")
        : t("common.none");
      const comment = item.comment ? ` · ${item.comment}` : "";
      div.innerHTML = `<span>${rating}${comment}</span><span class="stage-tag">${reason}</span>`;
      el.feedbackList.appendChild(div);
    });
  } catch (err) {
    const msg = String(err.message || "");
    if (msg.includes("run_id not found")) {
      state.feedbackCount = 0;
      updateAnalyzeSummary();
      el.feedbackList.innerHTML = `<div class="placeholder">${t("feedback.none")}</div>`;
    } else {
      el.feedbackList.innerHTML = `<div class="placeholder">${t("feedback.loadFailed", {
        error: err.message,
      })}</div>`;
    }
  }
}

async function submitExperiment() {
  if (!state.currentRunId) {
    if (el.experimentStatus) el.experimentStatus.textContent = t("export.selectRun");
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
    if (el.experimentStatus) el.experimentStatus.textContent = t("experiment.saved");
    if (el.experimentMetrics) el.experimentMetrics.value = "";
    if (el.experimentConditions) el.experimentConditions.value = "";
    if (el.experimentSampleId) el.experimentSampleId.value = "";
    await refreshExperiments();
    await loadReport();
  } catch (err) {
    if (el.experimentStatus) {
      el.experimentStatus.textContent = t("experiment.failed", { error: err.message });
    }
  }
}

async function refreshExperiments() {
  if (!state.currentRunId || !el.experimentList) return;
  try {
    const result = await apiCall("pipeline.list_experiments", {
      run_id: state.currentRunId,
      limit: 100,
    });
    const items = result.items || [];
    state.experimentCount = items.length;
    updateAnalyzeSummary();
    if (!items.length) {
      el.experimentList.innerHTML = `<div class="placeholder">${t("experiment.none")}</div>`;
      return;
    }
    el.experimentList.innerHTML = "";
    items.slice(0, 5).forEach((item) => {
      const div = document.createElement("div");
      div.className = "run-item";
      const resultLabel = labelFromMap(item.result, EXPERIMENT_RESULT_KEYS);
      const assay = labelFromMap(item.assay_type, EXPERIMENT_ASSAY_KEYS);
      div.innerHTML = `<span>${assay}</span><span class="stage-tag">${resultLabel}</span>`;
      el.experimentList.appendChild(div);
    });
  } catch (err) {
    const msg = String(err.message || "");
    if (msg.includes("run_id not found")) {
      state.experimentCount = 0;
      updateAnalyzeSummary();
      el.experimentList.innerHTML = `<div class="placeholder">${t("experiment.none")}</div>`;
    } else {
      el.experimentList.innerHTML = `<div class="placeholder">${t("experiment.loadFailed", {
        error: err.message,
      })}</div>`;
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
  state.lastScore = { score, evidence, recommendation };
  el.runScoreValue.textContent = `${t("common.score")}: ${score}`;
  el.runEvidenceValue.textContent = `${t("common.evidence")}: ${evidence}`;
  el.runRecommendationValue.textContent = `${t("common.recommendation")}: ${recommendation}`;
}

function updateAnalyzeSummary() {
  if (el.analyzeFeedbackCount) {
    el.analyzeFeedbackCount.textContent = String(Math.max(0, Number(state.feedbackCount || 0)));
  }
  if (el.analyzeExperimentCount) {
    el.analyzeExperimentCount.textContent = String(Math.max(0, Number(state.experimentCount || 0)));
  }
  if (el.analyzeRecommendationValue) {
    const recommendation = state.lastScore?.recommendation || "-";
    el.analyzeRecommendationValue.textContent = String(recommendation);
  }
}

function updateReportScore(result) {
  if (!el.reportScoreValue || !el.reportEvidenceValue || !el.reportRecommendationValue) return;
  const { score, evidence, recommendation } = formatScoreValues(result);
  state.lastScore = { score, evidence, recommendation };
  el.reportScoreValue.textContent = `${t("common.score")}: ${score}`;
  el.reportEvidenceValue.textContent = `${t("common.evidence")}: ${evidence}`;
  el.reportRecommendationValue.textContent = `${t("common.recommendation")}: ${recommendation}`;
  updateRunScore(result);
  updateAnalyzeSummary();
}

function setHitWeightInputValues() {
  if (el.hitWeightSoluprot) el.hitWeightSoluprot.value = String(state.hitListWeights.soluprot ?? 0.4);
  if (el.hitWeightPlddt) el.hitWeightPlddt.value = String(state.hitListWeights.plddt ?? 0.3);
  if (el.hitWeightRmsd) el.hitWeightRmsd.value = String(state.hitListWeights.rmsd ?? 0.2);
  if (el.hitWeightNovelty) el.hitWeightNovelty.value = String(state.hitListWeights.novelty ?? 0);
}

function readHitWeightsFromInputs() {
  const parse = (inputEl, fallback) => {
    const value = Number(inputEl?.value ?? fallback);
    return Number.isFinite(value) && value >= 0 ? value : fallback;
  };
  const next = {
    soluprot: parse(el.hitWeightSoluprot, state.hitListWeights.soluprot ?? 0.4),
    plddt: parse(el.hitWeightPlddt, state.hitListWeights.plddt ?? 0.3),
    rmsd: parse(el.hitWeightRmsd, state.hitListWeights.rmsd ?? 0.2),
    novelty: parse(el.hitWeightNovelty, state.hitListWeights.novelty ?? 0),
  };
  const sum = next.soluprot + next.plddt + next.rmsd;
  if (sum <= 0) {
    return { soluprot: 0.4, plddt: 0.3, rmsd: 0.2, novelty: 0 };
  }
  return next;
}

function updateHitCutoffLabel() {
  if (el.hitListCutoffValue) {
    el.hitListCutoffValue.textContent = String(Math.max(0, Math.min(100, Number(state.hitListCutoff || 0))).toFixed(0));
  }
}

function populateRunCompareBaselineOptions() {
  if (!el.runCompareBaseline) return;
  const current = String(state.currentRunId || "").trim();
  const runIds = (state.runs || []).map((item) => String(item || "").trim()).filter(Boolean);
  const options = runIds.filter((item) => item && item !== current);
  el.runCompareBaseline.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = t("monitor.selectRun");
  el.runCompareBaseline.appendChild(placeholder);
  options.forEach((runId) => {
    const opt = document.createElement("option");
    opt.value = runId;
    opt.textContent = runId;
    el.runCompareBaseline.appendChild(opt);
  });
  if (state.runCompareBaselineId && options.includes(state.runCompareBaselineId)) {
    el.runCompareBaseline.value = state.runCompareBaselineId;
  } else {
    state.runCompareBaselineId = options[0] || "";
    el.runCompareBaseline.value = state.runCompareBaselineId;
  }
}

function renderRunCompareSummary(result) {
  if (!el.runCompareSummary) return;
  if (!result || typeof result !== "object") {
    el.runCompareSummary.innerHTML = `<div class="placeholder">${t("analyze.runCompare.placeholder")}</div>`;
    if (el.runCompareDetails) {
      el.runCompareDetails.classList.add("hidden");
      el.runCompareDetails.disabled = true;
    }
    return;
  }
  const current = result.current && typeof result.current === "object" ? result.current : {};
  const baseline = result.baseline && typeof result.baseline === "object" ? result.baseline : {};
  const delta = result.delta && typeof result.delta === "object" ? result.delta : {};
  const rows = [
    { key: "soluprot_median", label: "SoluProt", digits: 3, percent: false },
    { key: "plddt_median", label: "pLDDT", digits: 1, percent: false },
    { key: "rmsd_median", label: "RMSD", digits: 2, percent: false },
    { key: "soluprot_pass_rate", label: "SoluProt pass", digits: 1, percent: true },
    { key: "af2_pass_rate", label: af2ProviderPassLabel(currentRunAf2Provider()), digits: 1, percent: true },
  ];
  const format = (value, digits, isPercent, signed = false) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "-";
    const scaled = isPercent ? value * 100.0 : value;
    const text = scaled.toFixed(digits);
    if (signed && scaled > 0) return `+${text}${isPercent ? "%" : ""}`;
    return `${text}${isPercent ? "%" : ""}`;
  };
  const body = rows
    .map(
      (row) => `<tr>
      <th>${escapeHtml(row.label)}</th>
      <td>${escapeHtml(format(current[row.key], row.digits, row.percent, false))}</td>
      <td>${escapeHtml(format(baseline[row.key], row.digits, row.percent, false))}</td>
      <td>${escapeHtml(format(delta[row.key], row.digits, row.percent, true))}</td>
    </tr>`
    )
    .join("");
  el.runCompareSummary.innerHTML = `
    <div class="comparison-card">
      <h4>${escapeHtml(`${result.run_id || "-"} vs ${result.baseline_run_id || "-"}`)}</h4>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>${escapeHtml(t("artifacts.compare.metric"))}</th>
            <th>${escapeHtml(result.run_id || "-")}</th>
            <th>${escapeHtml(result.baseline_run_id || "-")}</th>
            <th>${escapeHtml(t("artifacts.compare.delta"))}</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
  if (el.runCompareDetails) {
    el.runCompareDetails.classList.remove("hidden");
    el.runCompareDetails.disabled = false;
  }
}

function buildRunCompareDetailsMarkdown(result) {
  const lines = [];
  lines.push(`# ${t("analyze.runCompare.detailsTitle")}`);
  lines.push("");
  lines.push(`- Run: ${result?.run_id || "-"}`);
  lines.push(`- Baseline: ${result?.baseline_run_id || "-"}`);
  lines.push("");
  lines.push("| Metric | Current | Baseline | Delta |");
  lines.push("|---|---:|---:|---:|");
  const rows = [
    ["SoluProt median", "soluprot_median", 3, false],
    ["pLDDT median", "plddt_median", 1, false],
    ["RMSD median", "rmsd_median", 2, false],
    ["SoluProt pass rate", "soluprot_pass_rate", 1, true],
    [`${af2ProviderPassLabel(currentRunAf2Provider())} rate`, "af2_pass_rate", 1, true],
    ["Backbone count", "backbone_count", 0, false],
  ];
  const format = (value, digits, percent, signed = false) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "-";
    const scaled = percent ? value * 100.0 : value;
    const text = scaled.toFixed(digits);
    if (signed && scaled > 0) return `+${text}${percent ? "%" : ""}`;
    return `${text}${percent ? "%" : ""}`;
  };
  rows.forEach(([label, key, digits, percent]) => {
    lines.push(
      `| ${label} | ${format(result?.current?.[key], digits, percent)} | ${format(result?.baseline?.[key], digits, percent)} | ${format(result?.delta?.[key], digits, percent, true)} |`
    );
  });
  lines.push("");
  const currentCompleteness = result?.completeness?.current || {};
  lines.push("## Completeness");
  lines.push(`- RFD3: ${currentCompleteness.has_rfd3 ? "yes" : "no"}`);
  lines.push(`- BioEmu: ${currentCompleteness.has_bioemu ? "yes" : "no"}`);
  lines.push(`- WT compare: ${currentCompleteness.wt_compare_enabled ? "yes" : "no"}`);
  lines.push(`- ${af2ProviderSelectedLabel(currentRunAf2Provider())}: ${Number(currentCompleteness.af2_selected || 0)}`);
  lines.push("");
  return lines.join("\n");
}

async function refreshRunCompare() {
  if (!state.currentRunId) {
    state.runCompareResult = null;
    renderRunCompareSummary(null);
    return;
  }
  const baseline = String(state.runCompareBaselineId || "").trim();
  if (!baseline || baseline === state.currentRunId) {
    state.runCompareResult = null;
    if (baseline === state.currentRunId) {
      if (el.runCompareSummary) {
        el.runCompareSummary.innerHTML = `<div class="placeholder">${t("analyze.runCompare.sameRun")}</div>`;
      }
    } else {
      renderRunCompareSummary(null);
    }
    return;
  }
  try {
    const result = await apiCall("pipeline.compare_runs", {
      run_id: state.currentRunId,
      baseline_run_id: baseline,
    });
    if (String(state.currentRunId || "").trim() !== String(result?.run_id || "").trim()) return;
    state.runCompareResult = result;
    renderRunCompareSummary(result);
  } catch (err) {
    state.runCompareResult = null;
    if (el.runCompareSummary) {
      el.runCompareSummary.innerHTML = `<div class="placeholder">${t("analyze.runCompare.failed", {
        error: err.message,
      })}</div>`;
    }
    if (el.runCompareDetails) {
      el.runCompareDetails.classList.add("hidden");
      el.runCompareDetails.disabled = true;
    }
  }
}

function normalizeChartView(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (CHART_VIEW_OPTIONS.has(raw)) return raw;
  return "plddt_rmsd";
}

function syncChartSelectors() {
  const next = normalizeChartView(state.chartView);
  state.chartView = next;
  if (el.analyzeChartType && el.analyzeChartType.value !== next) el.analyzeChartType.value = next;
  if (el.reportChartType && el.reportChartType.value !== next) el.reportChartType.value = next;
}

function setChartView(value) {
  const next = normalizeChartView(value);
  if (state.chartView === next) return;
  state.chartView = next;
  syncChartSelectors();
  renderCandidateCharts();
  if (el.reportModal && el.reportModalContent && !el.reportModal.classList.contains("hidden")) {
    if (state.reportModalMode === "rendered") {
      el.reportModalContent.innerHTML = renderReportModalContent();
      void hydrateReportModalArtifactImages();
    }
  }
}

function filteredHitListRows({ applyLimit = false } = {}) {
  const rows = Array.isArray(state.hitListRows) ? state.hitListRows : [];
  const cutoff = Math.max(0, Math.min(100, Number(state.hitListCutoff || 0)));
  const filtered = rows.filter((row) => {
    const score = Number(row?.score);
    if (Number.isFinite(score) && score >= cutoff) return true;
    return row?.score === null && cutoff <= 0;
  });
  if (!applyLimit) return filtered;
  const limit = Math.max(10, Math.min(500, Number(state.hitListLimit || 120)));
  return filtered.slice(0, limit);
}

function chartCanvasForTarget(target) {
  return target === "report" ? el.reportChartCanvas : el.analyzeChartCanvas;
}

function chartCaptionForTarget(target) {
  return target === "report" ? el.reportChartCaption : el.analyzeChartCaption;
}

function setChartPlaceholder(target, key) {
  const canvas = chartCanvasForTarget(target);
  const caption = chartCaptionForTarget(target);
  if (!canvas) return;
  canvas.innerHTML = `<div class="placeholder">${escapeHtml(t(key))}</div>`;
  if (caption) caption.textContent = "";
}

function finiteNumber(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && !value.trim()) return null;
  const num = typeof value === "number" ? value : Number(value);
  return Number.isFinite(num) ? num : null;
}

function extentWithPadding(values, { padRatio = 0.06, minPad = 1 } = {}) {
  if (!Array.isArray(values) || !values.length) return { min: 0, max: 1 };
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 1 };
  const span = Math.max(max - min, 0);
  const pad = Math.max(span * padRatio, minPad);
  if (span <= 0) return { min: min - pad, max: max + pad };
  return { min: min - pad, max: max + pad };
}

function svgSafe(text) {
  return escapeHtml(String(text || ""));
}

function chartTickText(value, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return value.toFixed(digits);
}

function wtScatterPointFromSummary(summary = state.artifactComparison) {
  const wt = summary?.wt_vs_design && typeof summary.wt_vs_design === "object" ? summary.wt_vs_design : {};
  const plddt = finiteNumber(wt?.plddt?.wt);
  const rmsd = finiteNumber(wt?.rmsd?.wt);
  if (plddt === null || rmsd === null) return null;
  return {
    x: plddt,
    y: rmsd,
    seqId: "WT",
    source: "WT",
    sourceKey: "wt",
  };
}

function buildPlddtRmsdScatter(rows) {
  const designPoints = (rows || [])
    .map((row) => ({
      x: finiteNumber(row?.plddt),
      y: finiteNumber(row?.rmsd),
      seqId: String(row?.seq_id || "-"),
      source: sourceLabel(normalizeSourceKey(row?.source)),
      sourceKey: normalizeSourceKey(row?.source),
    }))
    .filter((row) => row.x !== null && row.y !== null);
  const wtPoint = wtScatterPointFromSummary();
  const points = wtPoint ? [...designPoints, wtPoint] : designPoints;
  if (!points.length) return null;

  const width = 760;
  const height = 340;
  const left = 56;
  const right = 20;
  const top = 20;
  const bottom = 50;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const xExtent = extentWithPadding(points.map((p) => p.x), { padRatio: 0.05, minPad: 0.5 });
  const yExtent = extentWithPadding(points.map((p) => p.y), { padRatio: 0.08, minPad: 0.2 });
  const xMap = (v) => left + ((v - xExtent.min) / Math.max(xExtent.max - xExtent.min, 1e-6)) * plotW;
  const yMap = (v) => top + plotH - ((v - yExtent.min) / Math.max(yExtent.max - yExtent.min, 1e-6)) * plotH;

  const ticks = 5;
  const gridLines = [];
  for (let i = 0; i <= ticks; i += 1) {
    const rx = i / ticks;
    const x = left + plotW * rx;
    const xValue = xExtent.min + (xExtent.max - xExtent.min) * rx;
    gridLines.push(
      `<line x1="${x.toFixed(2)}" y1="${top}" x2="${x.toFixed(2)}" y2="${(top + plotH).toFixed(2)}" stroke="rgba(16,42,45,0.12)" />`
    );
    gridLines.push(
      `<text x="${x.toFixed(2)}" y="${(top + plotH + 18).toFixed(2)}" text-anchor="middle" fill="#4f6365" font-size="11">${svgSafe(chartTickText(xValue, 1))}</text>`
    );
  }
  for (let i = 0; i <= ticks; i += 1) {
    const ry = i / ticks;
    const y = top + plotH * ry;
    const yValue = yExtent.max - (yExtent.max - yExtent.min) * ry;
    gridLines.push(
      `<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotW).toFixed(2)}" y2="${y.toFixed(2)}" stroke="rgba(16,42,45,0.12)" />`
    );
    gridLines.push(
      `<text x="${(left - 8).toFixed(2)}" y="${(y + 4).toFixed(2)}" text-anchor="end" fill="#4f6365" font-size="11">${svgSafe(chartTickText(yValue, 2))}</text>`
    );
  }

  const colorBySource = {
    rfd3: "#0f6b6f",
    bioemu: "#d97757",
    wt: "#295b9d",
    other: "#7b8794",
  };
  const marks = points
    .map((p) => {
      const cx = xMap(p.x).toFixed(2);
      const cy = yMap(p.y).toFixed(2);
      const fill = colorBySource[p.sourceKey] || colorBySource.other;
      const label = `${p.seqId} | ${p.source} | pLDDT=${chartTickText(p.x, 1)} | RMSD=${chartTickText(p.y, 2)}`;
      const radius = p.sourceKey === "wt" ? 4.6 : 3.8;
      const stroke = p.sourceKey === "wt" ? "#1b3f6e" : "rgba(16,42,45,0.35)";
      const strokeWidth = p.sourceKey === "wt" ? 1.3 : 0.5;
      return `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="${fill}" fill-opacity="0.86" stroke="${stroke}" stroke-width="${strokeWidth}"><title>${svgSafe(
        label
      )}</title></circle>`;
    })
    .join("");

  const sourceCounts = points.reduce(
    (acc, point) => {
      const key = point.sourceKey || "other";
      if (!Object.prototype.hasOwnProperty.call(acc, key)) acc[key] = 0;
      acc[key] += 1;
      return acc;
    },
    { rfd3: 0, bioemu: 0, wt: 0, other: 0 }
  );
  const captionBits = [
    `${sourceLabel("rfd3")}=${sourceCounts.rfd3}`,
    `${sourceLabel("bioemu")}=${sourceCounts.bioemu}`,
    `${t("artifacts.compare.wtValue")}=${sourceCounts.wt}`,
  ];
  if (sourceCounts.other > 0) captionBits.push(`${sourceLabel("other")}=${sourceCounts.other}`);
  const caption = `${t("analyze.chart.caption.rows", {
    rows: rows.length,
    cutoff: Math.max(0, Math.min(100, Number(state.hitListCutoff || 0))).toFixed(0),
  })} · ${t("analyze.chart.caption.scatterPoints", { points: points.length })} · ${captionBits.join(", ")}`;

  const legendItems = [
    { key: "rfd3", label: sourceLabel("rfd3") },
    { key: "bioemu", label: sourceLabel("bioemu") },
    { key: "wt", label: t("artifacts.compare.wtValue") },
  ];
  if (sourceCounts.other > 0) {
    legendItems.push({ key: "other", label: sourceLabel("other") });
  }
  let legendX = left + 8;
  const legend = legendItems
    .map((item) => {
      const color = colorBySource[item.key] || colorBySource.other;
      const textX = legendX + 8;
      const marker = `<circle cx="${legendX.toFixed(2)}" cy="14" r="4" fill="${color}" stroke="rgba(16,42,45,0.35)" stroke-width="0.6" />`;
      const text = `<text x="${textX.toFixed(2)}" y="18" fill="#213c3f" font-size="11">${svgSafe(item.label)}</text>`;
      const width = Math.max(56, item.label.length * 7 + 22);
      legendX += width;
      return `${marker}${text}`;
    })
    .join("");

  return {
    caption,
    svg: `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${svgSafe(
      t("analyze.chart.option.plddtRmsd")
    )}">
      <rect x="0" y="0" width="${width}" height="${height}" fill="rgba(255,255,255,0.98)" />
      ${gridLines.join("")}
      <rect x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="none" stroke="rgba(16,42,45,0.2)" />
      ${marks}
      <text x="${(left + plotW / 2).toFixed(2)}" y="${(height - 10).toFixed(2)}" text-anchor="middle" fill="#213c3f" font-size="12">${svgSafe(
        t("analyze.chart.axis.plddt")
      )}</text>
      <text x="14" y="${(top + plotH / 2).toFixed(2)}" text-anchor="middle" fill="#213c3f" font-size="12" transform="rotate(-90 14 ${(top + plotH / 2).toFixed(2)})">${svgSafe(
        t("analyze.chart.axis.rmsd")
      )}</text>
      ${legend}
    </svg>`,
  };
}

function buildScoreHistogram(rows) {
  const values = (rows || []).map((row) => finiteNumber(row?.score)).filter((v) => v !== null);
  if (!values.length) return null;

  const width = 760;
  const height = 320;
  const left = 52;
  const right = 20;
  const top = 20;
  const bottom = 50;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1e-6);
  const binCount = Math.max(6, Math.min(16, Math.round(Math.sqrt(values.length))));
  const counts = Array.from({ length: binCount }, () => 0);
  values.forEach((value) => {
    const ratio = (value - min) / span;
    const idx = Math.min(binCount - 1, Math.max(0, Math.floor(ratio * binCount)));
    counts[idx] += 1;
  });
  const maxCount = Math.max(...counts, 1);
  const barW = plotW / binCount;

  const bars = counts
    .map((count, i) => {
      const h = (count / maxCount) * plotH;
      const x = left + i * barW + 1.5;
      const y = top + plotH - h;
      const binStart = min + (span * i) / binCount;
      const binEnd = min + (span * (i + 1)) / binCount;
      const label = `${chartTickText(binStart, 1)}-${chartTickText(binEnd, 1)}: ${count}`;
      return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(barW - 3, 1).toFixed(
        2
      )}" height="${Math.max(h, 0).toFixed(2)}" fill="#0f6b6f" fill-opacity="0.8"><title>${svgSafe(
        label
      )}</title></rect>`;
    })
    .join("");

  const yTicks = [];
  for (let i = 0; i <= 4; i += 1) {
    const ratio = i / 4;
    const y = top + plotH - plotH * ratio;
    const value = Math.round(maxCount * ratio);
    yTicks.push(
      `<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotW).toFixed(2)}" y2="${y.toFixed(
        2
      )}" stroke="rgba(16,42,45,0.12)" />`
    );
    yTicks.push(
      `<text x="${(left - 8).toFixed(2)}" y="${(y + 4).toFixed(2)}" text-anchor="end" fill="#4f6365" font-size="11">${value}</text>`
    );
  }

  const xTicks = [];
  for (let i = 0; i <= 5; i += 1) {
    const ratio = i / 5;
    const x = left + plotW * ratio;
    const value = min + span * ratio;
    xTicks.push(
      `<text x="${x.toFixed(2)}" y="${(top + plotH + 18).toFixed(2)}" text-anchor="middle" fill="#4f6365" font-size="11">${svgSafe(
        chartTickText(value, 1)
      )}</text>`
    );
  }

  const caption = `${t("analyze.chart.caption.rows", {
    rows: rows.length,
    cutoff: Math.max(0, Math.min(100, Number(state.hitListCutoff || 0))).toFixed(0),
  })} · ${t("analyze.chart.caption.hist", { values: values.length, bins: binCount })}`;

  return {
    caption,
    svg: `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${svgSafe(
      t("analyze.chart.option.scoreHist")
    )}">
      <rect x="0" y="0" width="${width}" height="${height}" fill="rgba(255,255,255,0.98)" />
      ${yTicks.join("")}
      <rect x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="none" stroke="rgba(16,42,45,0.2)" />
      ${bars}
      ${xTicks.join("")}
      <text x="${(left + plotW / 2).toFixed(2)}" y="${(height - 10).toFixed(2)}" text-anchor="middle" fill="#213c3f" font-size="12">${svgSafe(
        t("analyze.chart.axis.score")
      )}</text>
      <text x="14" y="${(top + plotH / 2).toFixed(2)}" text-anchor="middle" fill="#213c3f" font-size="12" transform="rotate(-90 14 ${(top + plotH / 2).toFixed(2)})">${svgSafe(
        t("analyze.chart.axis.count")
      )}</text>
    </svg>`,
  };
}

function buildTierPassRateChart(rows) {
  const buckets = new Map();
  (rows || []).forEach((row) => {
    const tierNum = finiteNumber(row?.tier);
    if (tierNum === null) return;
    const key = tierNum.toFixed(2);
    if (!buckets.has(key)) buckets.set(key, { tier: tierNum, total: 0, selected: 0 });
    const bucket = buckets.get(key);
    bucket.total += 1;
    if (row?.af2_selected) bucket.selected += 1;
  });
  const list = Array.from(buckets.values()).sort((a, b) => a.tier - b.tier);
  if (!list.length) return null;

  const width = 760;
  const height = 320;
  const left = 52;
  const right = 20;
  const top = 20;
  const bottom = 56;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const barW = plotW / list.length;

  const bars = list
    .map((bucket, i) => {
      const rate = bucket.total > 0 ? (bucket.selected / bucket.total) * 100 : 0;
      const h = (rate / 100) * plotH;
      const x = left + i * barW + 8;
      const y = top + plotH - h;
      const label = `${bucket.selected}/${bucket.total} (${chartTickText(rate, 1)}%)`;
      return `
        <rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(barW - 16, 8).toFixed(
          2
        )}" height="${Math.max(h, 0).toFixed(2)}" fill="#0f6b6f" fill-opacity="0.82"><title>${svgSafe(
        label
      )}</title></rect>
        <text x="${(x + Math.max(barW - 16, 8) / 2).toFixed(2)}" y="${(top + plotH + 18).toFixed(
          2
        )}" text-anchor="middle" fill="#4f6365" font-size="11">${svgSafe(chartTickText(
        bucket.tier,
        2
      ))}</text>
        <text x="${(x + Math.max(barW - 16, 8) / 2).toFixed(2)}" y="${Math.max(y - 6, top + 10).toFixed(
          2
        )}" text-anchor="middle" fill="#213c3f" font-size="10">${svgSafe(
        `${bucket.selected}/${bucket.total}`
      )}</text>
      `;
    })
    .join("");

  const yTicks = [];
  for (let i = 0; i <= 5; i += 1) {
    const value = i * 20;
    const y = top + plotH - (value / 100) * plotH;
    yTicks.push(
      `<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotW).toFixed(2)}" y2="${y.toFixed(
        2
      )}" stroke="rgba(16,42,45,0.12)" />`
    );
    yTicks.push(
      `<text x="${(left - 8).toFixed(2)}" y="${(y + 4).toFixed(2)}" text-anchor="end" fill="#4f6365" font-size="11">${value}</text>`
    );
  }

  const caption = `${t("analyze.chart.caption.rows", {
    rows: rows.length,
    cutoff: Math.max(0, Math.min(100, Number(state.hitListCutoff || 0))).toFixed(0),
  })} · ${t("analyze.chart.caption.tier", { tiers: list.length, rows: rows.length })}`;

  return {
    caption,
    svg: `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${svgSafe(
      t("analyze.chart.option.tierPass")
    )}">
      <rect x="0" y="0" width="${width}" height="${height}" fill="rgba(255,255,255,0.98)" />
      ${yTicks.join("")}
      <rect x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="none" stroke="rgba(16,42,45,0.2)" />
      ${bars}
      <text x="${(left + plotW / 2).toFixed(2)}" y="${(height - 10).toFixed(2)}" text-anchor="middle" fill="#213c3f" font-size="12">${svgSafe(
        t("analyze.chart.axis.tier")
      )}</text>
      <text x="14" y="${(top + plotH / 2).toFixed(2)}" text-anchor="middle" fill="#213c3f" font-size="12" transform="rotate(-90 14 ${(top + plotH / 2).toFixed(2)})">${svgSafe(
        t("analyze.chart.axis.passRate")
      )}</text>
    </svg>`,
  };
}

function selectedChartPayload(rows) {
  const view = normalizeChartView(state.chartView);
  if (view === "plddt_rmsd") return buildPlddtRmsdScatter(rows);
  if (view === "score_hist") return buildScoreHistogram(rows);
  if (view === "tier_pass") return buildTierPassRateChart(rows);
  return null;
}

function renderCandidateChart(target = "analyze") {
  const canvas = chartCanvasForTarget(target);
  const captionEl = chartCaptionForTarget(target);
  if (!canvas) return;
  if (!state.currentRunId) {
    setChartPlaceholder(target, target === "report" ? "report.chart.placeholder" : "analyze.chart.placeholder");
    return;
  }
  const rows = filteredHitListRows({ applyLimit: false });
  if (!rows.length) {
    setChartPlaceholder(target, "analyze.hitList.empty");
    return;
  }

  const payload = selectedChartPayload(rows);
  if (!payload) {
    setChartPlaceholder(target, "analyze.chart.noData");
    return;
  }
  canvas.innerHTML = payload.svg;
  if (captionEl) {
    captionEl.innerHTML = `<p class="chart-caption">${escapeHtml(payload.caption)}</p>`;
  }
}

function renderCandidateCharts() {
  syncChartSelectors();
  renderCandidateChart("analyze");
  renderCandidateChart("report");
  if (el.reportModal && el.reportModalContent && !el.reportModal.classList.contains("hidden")) {
    if (state.reportModalMode === "rendered" && isRunReportFilename(state.reportModalFilename)) {
      el.reportModalContent.innerHTML = renderReportModalContent();
      void hydrateReportModalArtifactImages();
    }
  }
}

function renderHitList() {
  if (!el.hitListTable) return;
  if (!state.currentRunId) {
    if (el.hitListSummary) el.hitListSummary.innerHTML = "";
    el.hitListTable.innerHTML = `<div class="placeholder">${t("analyze.hitList.placeholder")}</div>`;
    if (el.hitListDetails) {
      el.hitListDetails.classList.add("hidden");
      el.hitListDetails.disabled = true;
    }
    renderCandidateCharts();
    renderCopilotContext();
    return;
  }
  const rows = Array.isArray(state.hitListRows) ? state.hitListRows : [];
  const cutoff = Math.max(0, Math.min(100, Number(state.hitListCutoff || 0)));
  const filtered = filteredHitListRows({ applyLimit: false });
  const limit = Math.max(10, Math.min(500, Number(state.hitListLimit || 120)));
  state.hitListLimit = limit;
  const shown = filtered.slice(0, limit);
  if (el.hitListSummary) {
    el.hitListSummary.innerHTML = `<div class="score-pill">${escapeHtml(
      t("analyze.hitList.summary", {
        shown: shown.length,
        filtered: filtered.length,
        total: rows.length,
        score: formatMetricValue(state.hitListResult?.stats?.score_median, 1, false),
      })
    )}</div>`;
  }
  if (!shown.length) {
    el.hitListTable.innerHTML = `<div class="placeholder">${t("analyze.hitList.empty")}</div>`;
    if (el.hitListDetails) {
      el.hitListDetails.classList.add("hidden");
      el.hitListDetails.disabled = true;
    }
    renderCandidateCharts();
    renderCopilotContext();
    return;
  }
  const body = shown
    .map((row) => {
      const wtDiffLabel = formatWtDifference(row);
      const classNames = [
        row.af2_selected ? "hit-list-row-pass" : "",
        row.plddt == null ? "hit-list-row-missing" : "",
      ]
        .filter(Boolean)
        .join(" ");
      return `<tr class="${classNames}">
        <td class="num">${escapeHtml(String(row.rank || "-"))}</td>
        <td>${escapeHtml(String(row.seq_id || "-"))}</td>
        <td>${escapeHtml(String(row.source || "-"))}</td>
        <td class="num">${escapeHtml(formatMetricValue(row.tier, 2, false))}</td>
        <td class="num">${escapeHtml(formatMetricValue(row.score, 1, false))}</td>
        <td class="num">${escapeHtml(formatMetricValue(row.soluprot, 3, false))}</td>
        <td class="num">${escapeHtml(formatMetricValue(row.plddt, 1, false))}</td>
        <td class="num">${escapeHtml(formatMetricValue(row.rmsd, 2, false))}</td>
        <td class="num">${escapeHtml(wtDiffLabel)}</td>
        <td>${escapeHtml(localizedYesNo(Boolean(row.af2_selected)))}</td>
      </tr>`;
    })
    .join("");
  el.hitListTable.innerHTML = `
    <table class="hit-list-table">
      <thead>
        <tr>
          <th>#</th>
          <th>seq_id</th>
          <th>source</th>
          <th>tier</th>
          <th>score</th>
          <th>SoluProt</th>
          <th>pLDDT</th>
          <th>RMSD</th>
          <th>${escapeHtml(t("analyze.hitList.identity"))}</th>
          <th>${escapeHtml(af2ProviderSelectedLabel(currentRunAf2Provider()))}</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
  if (el.hitListDetails) {
    el.hitListDetails.classList.remove("hidden");
    el.hitListDetails.disabled = false;
  }
  renderCandidateCharts();
  renderCopilotContext();
}

function buildHitListDetailsMarkdown() {
  const cutoff = Math.max(0, Math.min(100, Number(state.hitListCutoff || 0)));
  const filtered = filteredHitListRows({ applyLimit: false });
  const maxRows = Math.min(filtered.length, 200);
  const lines = [];
  lines.push(`# ${t("analyze.hitList.detailsTitle")}`);
  lines.push("");
  lines.push(`- Run: ${state.currentRunId || "-"}`);
  lines.push(`- Cutoff: ${cutoff}`);
  lines.push(`- Rows: ${maxRows}/${filtered.length}`);
  lines.push("");
  lines.push(
    `| Rank | seq_id | Source | Tier | Score | SoluProt | pLDDT | RMSD | ${t("analyze.hitList.identity")} | ${af2ProviderSelectedLabel(currentRunAf2Provider())} |`
  );
  lines.push("|---:|---|---|---:|---:|---:|---:|---:|---:|---|");
  filtered.slice(0, maxRows).forEach((row) => {
    lines.push(
      `| ${row.rank || "-"} | ${row.seq_id || "-"} | ${row.source || "-"} | ${formatMetricValue(row.tier, 2)} | ${formatMetricValue(row.score, 1)} | ${formatMetricValue(row.soluprot, 3)} | ${formatMetricValue(row.plddt, 1)} | ${formatMetricValue(row.rmsd, 2)} | ${formatWtDifference(row)} | ${row.af2_selected ? "yes" : "no"} |`
    );
  });
  lines.push("");
  return lines.join("\n");
}

async function refreshHitList() {
  if (!state.currentRunId) {
    state.hitListResult = null;
    state.hitListRows = [];
    renderHitList();
    return;
  }
  state.hitListWeights = readHitWeightsFromInputs();
  setHitWeightInputValues();
  try {
    const result = await apiCall("pipeline.get_hit_list", {
      run_id: state.currentRunId,
      limit: 500,
      min_score: 0,
      weights: state.hitListWeights,
    });
    if (String(state.currentRunId || "").trim() !== String(result?.run_id || "").trim()) return;
    state.hitListResult = result;
    state.hitListRows = Array.isArray(result?.rows) ? result.rows : [];
    renderHitList();
    if (state.artifactComparison && typeof state.artifactComparison === "object") {
      renderArtifactComparisonSummary(state.artifactComparison);
    }
    if (!state.artifactComparison) {
      renderMonitorCompleteness(null, result?.completeness || null);
    }
  } catch (err) {
    state.hitListResult = null;
    state.hitListRows = [];
    if (el.hitListTable) {
      el.hitListTable.innerHTML = `<div class="placeholder">${t("analyze.hitList.failed", {
        error: err.message,
      })}</div>`;
    }
    if (el.hitListDetails) {
      el.hitListDetails.classList.add("hidden");
      el.hitListDetails.disabled = true;
    }
    renderCandidateCharts();
  }
}

function base64ToBlob(base64Text, contentType = "application/octet-stream") {
  const binary = atob(String(base64Text || ""));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: contentType });
}

async function exportRunPackage() {
  if (!state.currentRunId) {
    if (el.reportStatus) el.reportStatus.textContent = t("export.selectRun");
    return;
  }
  if (el.reportStatus) el.reportStatus.textContent = t("export.exporting");
  try {
    const packageInfo = await apiCall("pipeline.export_results_package", {
      run_id: state.currentRunId,
      include_top_n: 10,
      weights: state.hitListWeights,
    });
    const packagePath = String(packageInfo?.path || "").trim();
    if (!packagePath) throw new Error("package path missing");
    const read = await apiCall("pipeline.read_artifact", {
      run_id: state.currentRunId,
      path: packagePath,
      max_bytes: Math.max(2_000_000, Number(packageInfo?.size_bytes || 0) + 1024),
      base64: true,
    });
    const blob = base64ToBlob(read?.base64 || "", "application/zip");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = packagePath.split("/").pop() || `${state.currentRunId}_results.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    if (el.reportStatus) {
      el.reportStatus.textContent = `Exported ${link.download} (${Number(packageInfo?.size_bytes || 0)} bytes)`;
    }
    await refreshArtifacts();
  } catch (err) {
    if (el.reportStatus) {
      el.reportStatus.textContent = t("export.failed", { error: err.message });
    }
  }
}

const REPORT_HITLIST_START = "<!-- KBF_HITLIST_START -->";
const REPORT_HITLIST_END = "<!-- KBF_HITLIST_END -->";
const REPORT_CHARTS_START = "<!-- KBF_CHARTS_START -->";
const REPORT_CHARTS_END = "<!-- KBF_CHARTS_END -->";
const REPORT_COMPARE_START = "<!-- KBF_COMPARE_START -->";
const REPORT_COMPARE_END = "<!-- KBF_COMPARE_END -->";

function stripReportHitListSection(text) {
  const raw = String(text || "");
  const start = raw.indexOf(REPORT_HITLIST_START);
  if (start < 0) return raw;
  const end = raw.indexOf(REPORT_HITLIST_END, start);
  if (end < 0) return raw.slice(0, start).trimEnd();
  return `${raw.slice(0, start)}${raw.slice(end + REPORT_HITLIST_END.length)}`.trimEnd();
}

function stripReportChartSection(text) {
  const raw = String(text || "");
  const start = raw.indexOf(REPORT_CHARTS_START);
  if (start < 0) return raw;
  const end = raw.indexOf(REPORT_CHARTS_END, start);
  if (end < 0) return raw.slice(0, start).trimEnd();
  return `${raw.slice(0, start)}${raw.slice(end + REPORT_CHARTS_END.length)}`.trimEnd();
}

function stripReportCompareSection(text) {
  const raw = String(text || "");
  const start = raw.indexOf(REPORT_COMPARE_START);
  if (start < 0) return raw;
  const end = raw.indexOf(REPORT_COMPARE_END, start);
  if (end < 0) return raw.slice(0, start).trimEnd();
  return `${raw.slice(0, start)}${raw.slice(end + REPORT_COMPARE_END.length)}`.trimEnd();
}

function normalizeSvgAttachmentText(svgText) {
  const raw = String(svgText || "").trim();
  if (!raw || !/^<svg\b/i.test(raw)) return "";
  let normalized = raw;
  if (!/\bxmlns=/.test(normalized)) {
    normalized = normalized.replace(/^<svg\b/i, '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  return `${normalized}\n`;
}

function buildReportChartSection() {
  const rows = filteredHitListRows({ applyLimit: false });
  const lines = [];
  const attachments = [];
  lines.push(`## ${t("report.chart.sectionTitle")}`);
  lines.push("");
  if (!rows.length) {
    lines.push(`- ${t("report.chart.sectionEmpty")}`);
    lines.push("");
    return { markdown: lines.join("\n"), attachments };
  }

  const chartDefs = [
    {
      id: "plddt_rmsd",
      title: t("analyze.chart.option.plddtRmsd"),
      build: buildPlddtRmsdScatter,
    },
    {
      id: "score_hist",
      title: t("analyze.chart.option.scoreHist"),
      build: buildScoreHistogram,
    },
    {
      id: "tier_pass",
      title: t("analyze.chart.option.tierPass"),
      build: buildTierPassRateChart,
    },
  ];

  chartDefs.forEach((chart) => {
    const payload = chart.build(rows);
    if (!payload || !String(payload.svg || "").trim()) return;
    const path = `report_assets/${chart.id}.svg`;
    const svgText = normalizeSvgAttachmentText(payload.svg);
    if (!svgText) return;
    attachments.push({
      path,
      text: svgText,
      content_type: "image/svg+xml",
    });
    lines.push(`### ${chart.title}`);
    lines.push(`![${chart.title}](${path})`);
    if (payload.caption) {
      lines.push(`- ${payload.caption}`);
    }
    lines.push("");
  });

  if (!attachments.length) {
    lines.push(`- ${t("report.chart.sectionEmpty")}`);
    lines.push("");
  }
  return { markdown: lines.join("\n"), attachments };
}

function selectReportComparePaths() {
  const structureItems = collectCompareStructureItems(state.artifacts);
  if (!structureItems.length) return { leftPath: "", rightPath: "" };
  chooseDefaultComparePaths(structureItems);
  const refs = resolveCompareReferenceItems(structureItems);
  let leftPath = String(state.artifactCompareLeftPath || "").trim();
  let rightPath = String(state.artifactCompareRightPath || "").trim();
  if (!rightPath) {
    const hitRows = filteredHitListRows({ applyLimit: false });
    const fromHit = hitRows.find((row) => String(row?.af2_ranked_pdb_path || "").trim());
    if (fromHit) rightPath = String(fromHit.af2_ranked_pdb_path || "").trim();
  }
  if (!leftPath || leftPath === rightPath) {
    leftPath = String(refs.input?.path || refs.wt?.path || refs.working?.path || structureItems[0]?.path || "");
  }
  if (leftPath === rightPath) {
    const alt = structureItems.find((item) => String(item?.path || "") !== leftPath);
    rightPath = String(alt?.path || "");
  }
  return { leftPath, rightPath };
}

function buildStructureDiffSvg(structureDiff, leftPath, rightPath) {
  if (!structureDiff || !structureDiff.ok) return "";
  const metrics = Array.isArray(structureDiff.residueMetrics) ? structureDiff.residueMetrics.slice(0, 28) : [];
  if (!metrics.length) return "";
  const width = 780;
  const left = 178;
  const right = 24;
  const top = 72;
  const rowH = 18;
  const plotW = width - left - right;
  const height = top + metrics.length * rowH + 34;
  const maxDist = Math.max(
    0.1,
    ...metrics.map((item) => {
      const raw = Number(item?.distance);
      return Number.isFinite(raw) ? raw : 0;
    })
  );
  const bars = metrics
    .map((item, idx) => {
      const chain = String(item?.chain || "_");
      const resi = Number(item?.resi);
      const label = `${chain}:${Number.isFinite(resi) ? resi : "-"}`;
      const dist = Number(item?.distance);
      const safeDist = Number.isFinite(dist) ? dist : 0;
      const ratio = Math.max(0, Math.min(1, safeDist / maxDist));
      const y = top + idx * rowH;
      const barW = ratio * plotW;
      const color = safeDist > 3 ? "#d62728" : safeDist > 1.5 ? "#e6a700" : "#2f7f84";
      return [
        `<text x="${left - 8}" y="${(y + 12).toFixed(1)}" text-anchor="end" fill="#38575b" font-size="11">${svgSafe(label)}</text>`,
        `<rect x="${left}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="12" fill="${color}" fill-opacity="0.86"><title>${svgSafe(
          `${label} d=${safeDist.toFixed(2)}A`
        )}</title></rect>`,
        `<text x="${(left + barW + 6).toFixed(1)}" y="${(y + 11.5).toFixed(1)}" fill="#38575b" font-size="10">${svgSafe(
          safeDist.toFixed(2)
        )}</text>`,
      ].join("");
    })
    .join("");
  const summary = `RMSD=${chartTickText(structureDiff.rmsd, 2)}A, P90=${chartTickText(
    structureDiff.p90Distance,
    2
  )}A, n=${Number(structureDiff.commonCount || 0)}`;
  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${svgSafe(
    "Structure difference"
  )}">
    <rect x="0" y="0" width="${width}" height="${height}" fill="rgba(255,255,255,0.98)" />
    <text x="18" y="24" fill="#16393d" font-size="14" font-weight="600">${svgSafe("Structure Difference (CA)")}</text>
    <text x="18" y="42" fill="#3d5a5f" font-size="11">${svgSafe(`Reference: ${leftPath}`)}</text>
    <text x="18" y="56" fill="#3d5a5f" font-size="11">${svgSafe(`Candidate: ${rightPath}`)}</text>
    <text x="${left}" y="24" fill="#16393d" font-size="11">${svgSafe(summary)}</text>
    <line x1="${left}" y1="${top - 8}" x2="${(left + plotW).toFixed(1)}" y2="${top - 8}" stroke="rgba(22,57,61,0.25)" />
    <text x="${left}" y="${top - 12}" fill="#3d5a5f" font-size="10">0</text>
    <text x="${(left + plotW).toFixed(1)}" y="${top - 12}" text-anchor="end" fill="#3d5a5f" font-size="10">${svgSafe(
      maxDist.toFixed(2)
    )}</text>
    ${bars}
  </svg>`;
}

function buildSequenceDiffSvg(seqDiff, leftPath, rightPath) {
  if (!seqDiff) return "";
  const leftResidues = seqDiff.leftResidues && typeof seqDiff.leftResidues === "object" ? seqDiff.leftResidues : {};
  const rightResidues = seqDiff.rightResidues && typeof seqDiff.rightResidues === "object" ? seqDiff.rightResidues : {};
  const chains = Array.from(new Set([...Object.keys(leftResidues), ...Object.keys(rightResidues)])).sort();
  const width = 720;
  const height = Math.max(180, 120 + chains.length * 24);
  const left = 132;
  const right = 24;
  const top = 72;
  const plotW = width - left - right;
  const countFor = (bucket, chain) => (Array.isArray(bucket?.[chain]) ? bucket[chain].length : 0);
  const maxCount = Math.max(1, ...chains.map((chain) => Math.max(countFor(leftResidues, chain), countFor(rightResidues, chain))));
  const rows = chains
    .map((chain, idx) => {
      const leftCount = countFor(leftResidues, chain);
      const rightCount = countFor(rightResidues, chain);
      const y = top + idx * 24;
      const leftW = (leftCount / maxCount) * (plotW / 2 - 12);
      const rightW = (rightCount / maxCount) * (plotW / 2 - 12);
      const mid = left + plotW / 2;
      return [
        `<text x="${left - 10}" y="${(y + 12).toFixed(1)}" text-anchor="end" fill="#38575b" font-size="11">${svgSafe(
          chain || "_"
        )}</text>`,
        `<rect x="${(mid - leftW).toFixed(1)}" y="${y.toFixed(1)}" width="${leftW.toFixed(1)}" height="10" fill="#1f77b4" fill-opacity="0.86"></rect>`,
        `<rect x="${mid.toFixed(1)}" y="${y.toFixed(1)}" width="${rightW.toFixed(1)}" height="10" fill="#ff7f0e" fill-opacity="0.86"></rect>`,
        `<text x="${(mid - leftW - 4).toFixed(1)}" y="${(y + 9.8).toFixed(1)}" text-anchor="end" fill="#38575b" font-size="10">${leftCount}</text>`,
        `<text x="${(mid + rightW + 4).toFixed(1)}" y="${(y + 9.8).toFixed(1)}" fill="#38575b" font-size="10">${rightCount}</text>`,
      ].join("");
    })
    .join("");
  const total = Number(seqDiff.totalCount || 0);
  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${svgSafe(
    "Sequence difference"
  )}">
    <rect x="0" y="0" width="${width}" height="${height}" fill="rgba(255,255,255,0.98)" />
    <text x="18" y="24" fill="#16393d" font-size="14" font-weight="600">${svgSafe("Sequence Difference (by chain)")}</text>
    <text x="18" y="42" fill="#3d5a5f" font-size="11">${svgSafe(`Reference: ${leftPath}`)}</text>
    <text x="18" y="56" fill="#3d5a5f" font-size="11">${svgSafe(`Candidate: ${rightPath}`)}</text>
    <text x="${left}" y="24" fill="#16393d" font-size="11">${svgSafe(`Differing residues: ${total}`)}</text>
    <line x1="${(left + plotW / 2).toFixed(1)}" y1="${(top - 12).toFixed(1)}" x2="${(left + plotW / 2).toFixed(
      1
    )}" y2="${(height - 24).toFixed(1)}" stroke="rgba(22,57,61,0.2)" />
    <text x="${(left + plotW / 2 - 8).toFixed(1)}" y="${top - 18}" text-anchor="end" fill="#1f77b4" font-size="10">${svgSafe(
      "Reference"
    )}</text>
    <text x="${(left + plotW / 2 + 8).toFixed(1)}" y="${top - 18}" fill="#ff7f0e" font-size="10">${svgSafe("Candidate")}</text>
    ${rows}
  </svg>`;
}

function buildReportCompareSection() {
  const lines = [];
  const { leftPath, rightPath } = selectReportComparePaths();
  lines.push(`## ${t("report.compare.sectionTitle")}`);
  lines.push("");
  if (!leftPath || !rightPath) {
    lines.push(`- ${t("report.compare.sectionEmpty")}`);
    lines.push("");
    return { markdown: lines.join("\n"), leftPath: "", rightPath: "" };
  }
  lines.push(`- ${t("report.compare.left")}: \`${leftPath}\``);
  lines.push(`- ${t("report.compare.right")}: \`${rightPath}\``);
  lines.push("");
  lines.push("### Structure Difference (CA)");
  lines.push("![Structure Difference](report_assets/structure_diff.svg)");
  lines.push("");
  lines.push("### Sequence Difference");
  lines.push("![Sequence Difference](report_assets/sequence_diff.svg)");
  lines.push("");
  return { markdown: lines.join("\n"), leftPath, rightPath };
}

async function buildReportCompareAttachments(compareSection) {
  const runId = String(state.currentRunId || "").trim();
  const leftPath = String(compareSection?.leftPath || "").trim();
  const rightPath = String(compareSection?.rightPath || "").trim();
  if (!runId || !leftPath || !rightPath) return [];
  if (!/\.pdb$/i.test(leftPath) || !/\.pdb$/i.test(rightPath)) return [];
  try {
    const [leftResult, rightResult] = await Promise.all([
      apiCall("pipeline.read_artifact", { run_id: runId, path: leftPath, max_bytes: 800000 }),
      apiCall("pipeline.read_artifact", { run_id: runId, path: rightPath, max_bytes: 800000 }),
    ]);
    const [leftText, rightText] = await Promise.all([
      normalizeComparePdbTextForArtifact(runId, leftPath, String(leftResult?.text || "")),
      normalizeComparePdbTextForArtifact(runId, rightPath, String(rightResult?.text || "")),
    ]);
    if (!leftText.trim() || !rightText.trim()) return [];
    const attachments = [];
    const structureSvg = normalizeSvgAttachmentText(buildStructureDiffSvg(computePdbStructuralDiff(leftText, rightText), leftPath, rightPath));
    if (structureSvg) {
      attachments.push({
        path: "report_assets/structure_diff.svg",
        text: structureSvg,
        content_type: "image/svg+xml",
      });
    }
    const sequenceSvg = normalizeSvgAttachmentText(buildSequenceDiffSvg(computePdbSequenceDiff(leftText, rightText), leftPath, rightPath));
    if (sequenceSvg) {
      attachments.push({
        path: "report_assets/sequence_diff.svg",
        text: sequenceSvg,
        content_type: "image/svg+xml",
      });
    }
    return attachments;
  } catch (_err) {
    return [];
  }
}

function buildReportHitListSection() {
  const rows = filteredHitListRows({ applyLimit: false });
  const cutoff = Math.max(0, Math.min(100, Number(state.hitListCutoff || 0)));
  const maxRows = Math.min(rows.length, Math.max(20, Math.min(200, Number(state.hitListLimit || 120))));
  const lines = [];
  lines.push(`## ${t("report.hitList.title")}`);
  lines.push("");
  if (!rows.length) {
    lines.push(`- ${t("report.hitList.empty")}`);
    lines.push("");
    return lines.join("\n");
  }
  lines.push(
    `- ${t("report.hitList.summary", {
      shown: maxRows,
      total: rows.length,
      cutoff: cutoff.toFixed(0),
    })}`
  );
  lines.push("");
  lines.push(
    `| Rank | seq_id | Source | Tier | Score | SoluProt | pLDDT | RMSD | ${af2ProviderSelectedLabel(currentRunAf2Provider())} |`
  );
  lines.push("|---:|---|---|---:|---:|---:|---:|---:|---|");
  rows.slice(0, maxRows).forEach((row) => {
    lines.push(
      `| ${row.rank || "-"} | ${row.seq_id || "-"} | ${row.source || "-"} | ${formatMetricValue(row.tier, 2)} | ${formatMetricValue(row.score, 1)} | ${formatMetricValue(row.soluprot, 3)} | ${formatMetricValue(row.plddt, 1)} | ${formatMetricValue(row.rmsd, 2)} | ${row.af2_selected ? "yes" : "no"} |`
    );
  });
  lines.push("");
  return lines.join("\n");
}

function mergeReportWithGeneratedSections(text) {
  const withoutHit = stripReportHitListSection(text);
  const withoutChart = stripReportChartSection(withoutHit);
  const base = stripReportCompareSection(withoutChart);
  const hitListSection = buildReportHitListSection();
  const chartSection = buildReportChartSection();
  const compareSection = buildReportCompareSection();

  const sections = [];
  if (String(chartSection.markdown || "").trim()) {
    sections.push(`${REPORT_CHARTS_START}\n${chartSection.markdown}\n${REPORT_CHARTS_END}`);
  }
  if (String(compareSection.markdown || "").trim()) {
    sections.push(`${REPORT_COMPARE_START}\n${compareSection.markdown}\n${REPORT_COMPARE_END}`);
  }
  if (String(hitListSection || "").trim()) {
    sections.push(`${REPORT_HITLIST_START}\n${hitListSection}\n${REPORT_HITLIST_END}`);
  }

  const trimmed = String(base || "").trimEnd();
  const suffix = sections.join("\n\n");
  const content = suffix ? `${trimmed}${trimmed ? "\n\n" : ""}${suffix}\n` : `${trimmed}\n`;
  return {
    content,
    attachments: Array.isArray(chartSection.attachments) ? chartSection.attachments : [],
    compare: compareSection,
  };
}

function selectReportBody(payload) {
  const preferred = resolveReportLang();
  const primary = preferred === "ko" ? payload?.report_ko : payload?.report;
  const fallback = preferred === "ko" ? payload?.report : payload?.report_ko;
  const body = String(primary || fallback || "");
  return mergeReportWithGeneratedSections(body).content;
}

async function loadReport() {
  if (!state.currentRunId || !el.reportContent) return;
  try {
    if (!Array.isArray(state.hitListRows) || state.hitListRows.length === 0) {
      await refreshHitList();
    }
    const result = await apiCall("pipeline.get_report", { run_id: state.currentRunId });
    el.reportContent.value = selectReportBody(result);
    updateReportScore(result);
    updateReportArtifactLinks(el.reportContent.value);
    void refreshArtifactComparisonSummary();
    if (el.reportStatus) el.reportStatus.textContent = t("report.loaded");
  } catch (err) {
    const msg = String(err.message || "");
    if (msg.includes("run_id not found")) {
      if (el.reportStatus) el.reportStatus.textContent = t("report.notAvailable");
      if (el.reportContent) el.reportContent.value = "";
      updateReportScore({});
      updateReportArtifactLinks("");
    } else if (el.reportStatus) {
      el.reportStatus.textContent = t("report.loadFailed", { error: err.message });
    }
  }
}

async function generateReport() {
  if (!state.currentRunId || !el.reportContent) return;
  try {
    if (!Array.isArray(state.hitListRows) || state.hitListRows.length === 0) {
      await refreshHitList();
    }
    const result = await apiCall("pipeline.generate_report", { run_id: state.currentRunId });
    el.reportContent.value = selectReportBody(result);
    updateReportScore(result);
    updateReportArtifactLinks(el.reportContent.value);
    await refreshArtifacts();
    void refreshArtifactComparisonSummary();
    if (el.reportStatus) el.reportStatus.textContent = t("report.generated");
  } catch (err) {
    if (el.reportStatus) {
      el.reportStatus.textContent = t("report.generateFailed", { error: err.message });
    }
  }
}

async function openRenderedReport() {
  if (!state.currentRunId || !el.reportContent) return;
  let text = String(el.reportContent.value || "").trim();
  if (!text) {
    await loadReport();
    text = String(el.reportContent.value || "").trim();
  }
  if (!text) {
    if (el.reportStatus) el.reportStatus.textContent = t("report.notAvailable");
    return;
  }
  const isKo = resolveReportLang() === "ko";
  openReportModal(t("report.title"), text, isKo ? "report_ko.md" : "report.md");
}

async function saveReport() {
  if (!state.currentRunId || !el.reportContent) return;
  if (!Array.isArray(state.artifacts) || state.artifacts.length === 0) {
    await refreshArtifacts();
  }
  const merged = mergeReportWithGeneratedSections(el.reportContent.value || "");
  const content = String(merged.content || "").trim();
  if (!content) {
    if (el.reportStatus) el.reportStatus.textContent = t("report.empty");
    return;
  }
  try {
    const compareAttachments = await buildReportCompareAttachments(merged.compare);
    const attachments = [
      ...(Array.isArray(merged.attachments) ? merged.attachments : []),
      ...(Array.isArray(compareAttachments) ? compareAttachments : []),
    ];
    await apiCall("pipeline.save_report", {
      run_id: state.currentRunId,
      content,
      attachments,
    });
    el.reportContent.value = String(merged.content || content);
    await refreshArtifacts();
    if (el.reportStatus) el.reportStatus.textContent = t("report.saved");
    updateReportArtifactLinks(content);
  } catch (err) {
    if (el.reportStatus) {
      el.reportStatus.textContent = t("report.saveFailed", { error: err.message });
    }
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
    state.runs = runs;
    renderRuns(runs);
    populateRunCompareBaselineOptions();
  } catch (err) {
    // ignore errors here
  }
}

function syncRunSelector(runs = []) {
  const current = String(state.currentRunId || "").trim();
  const ordered = [];
  if (current) ordered.push(current);
  (runs || []).forEach((item) => {
    const runId = String(item || "").trim();
    if (!runId || ordered.includes(runId)) return;
    ordered.push(runId);
  });
  [el.runSelector, el.setupRunSelector, el.analyzeRunSelector].forEach((selectorEl) => {
    if (!selectorEl) return;
    selectorEl.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = t("monitor.selectRun");
    selectorEl.appendChild(placeholder);
    ordered.forEach((runId) => {
      const opt = document.createElement("option");
      opt.value = runId;
      opt.textContent = runId;
      selectorEl.appendChild(opt);
    });
    selectorEl.value = current && ordered.includes(current) ? current : "";
  });
}

function renderRuns(runs) {
  syncRunSelector(runs);
  el.runList.innerHTML = "";
  if (!runs.length) {
    el.runList.innerHTML = `<div class="placeholder">${t("runs.none")}</div>`;
    return;
  }
  runs.forEach((runId) => {
    const div = document.createElement("div");
    div.className = "run-item";
    if (runId === state.currentRunId) {
      div.classList.add("active");
    }
    const label = document.createElement("span");
    label.textContent = runId;
    const actions = document.createElement("div");
    actions.className = "run-item-actions";
    const loadTag = document.createElement("span");
    loadTag.className = "stage-tag";
    loadTag.textContent = t("runs.load");
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "run-delete";
    deleteBtn.textContent = t("runs.delete");
    deleteBtn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const ok = window.confirm(t("runs.deleteConfirm", { id: runId }));
      if (!ok) return;
      try {
        await apiCall("pipeline.delete_run", { run_id: runId });
        delete state.runModeById[runId];
        delete state.af2ProviderByRunId[runId];
        delete state.progressByRunId[runId];
        delete state.progressContextByRunId[runId];
        if (state.workflowPlansByRunId && state.workflowPlansByRunId[runId]) {
          delete state.workflowPlansByRunId[runId];
          persistWorkflowPlans();
        }
        if (state.currentRunId === runId) {
          setCurrentRunId("");
          state.artifacts = [];
          renderAllArtifactViews([]);
          setFilePreviewPlaceholder("monitor");
          setFilePreviewPlaceholder("analyze", "analyze.files.placeholder");
          setComparePreviewPlaceholder("artifacts.preview.placeholder");
        }
        setMessage(t("runs.deleteSuccess", { id: runId }), "ai");
        await refreshRuns();
      } catch (err) {
        setMessage(t("runs.deleteFailed", { error: err.message }), "ai");
      }
    });
    actions.appendChild(loadTag);
    actions.appendChild(deleteBtn);
    div.appendChild(label);
    div.appendChild(actions);
    div.addEventListener("click", async () => {
      setCurrentRunId(runId);
      await pollStatus(runId);
      await refreshArtifacts();
      await refreshRunCompare();
      await refreshHitList();
      ensureAutoPoll();
    });
    el.runList.appendChild(div);
  });
}

async function healthCheck() {
  el.healthStatus.textContent = t("health.checking");
  try {
    const res = await fetch(`${state.apiBase}/healthz`);
    if (res.ok) {
      el.healthStatus.textContent = t("health.ok");
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
    el.adminStatus.textContent = t("auth.required");
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
      throw new Error(payload.error || t("auth.createFailed"));
    }
    el.adminStatus.textContent = t("auth.created", { username: payload.user.username });
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

if (el.checkBtn) {
  el.checkBtn.addEventListener("click", () => {
    runPreflight({ announce: true });
  });
}

el.clearBtn.addEventListener("click", () => {
  el.promptInput.value = "";
});

if (el.clearMonitorMessages) {
  el.clearMonitorMessages.addEventListener("click", () => {
    clearMessagePanels();
  });
}

if (el.clearMonitorMessagesMonitor) {
  el.clearMonitorMessagesMonitor.addEventListener("click", () => {
    clearMessagePanels();
  });
}

el.runBtn.addEventListener("click", runPipeline);

if (el.setupStepPrev) {
  el.setupStepPrev.addEventListener("click", () => {
    state.setupStepIndex = Math.max(0, Number(state.setupStepIndex || 0) - 1);
    renderQuestions(state.plan?.questions || []);
  });
}

if (el.setupStepNext) {
  el.setupStepNext.addEventListener("click", () => {
    const maxStep = SETUP_WIZARD_STEPS.length - 1;
    state.setupStepIndex = Math.min(maxStep, Number(state.setupStepIndex || 0) + 1);
    renderQuestions(state.plan?.questions || []);
  });
}

if (el.viewRunReport) {
  el.viewRunReport.addEventListener("click", loadRunReportModal);
}

if (el.viewAgentReport) {
  el.viewAgentReport.addEventListener("click", loadAgentReportModal);
}

el.pollBtn.addEventListener("click", () => {
  if (state.currentRunId) {
    void pollCurrentRun({ includeArtifacts: true });
  }
});

if (el.setupPollBtn) {
  el.setupPollBtn.addEventListener("click", () => {
    if (state.currentRunId) {
      void pollCurrentRun({ includeArtifacts: true });
    }
  });
}

if (el.setupMonitorTabBtn) {
  el.setupMonitorTabBtn.addEventListener("click", () => {
    setActiveTab("monitor");
  });
}

if (el.cancelRunBtn) {
  el.cancelRunBtn.addEventListener("click", () => {
    cancelCurrentRun();
  });
}

if (el.resumeRunBtn) {
  el.resumeRunBtn.addEventListener("click", () => {
    resumeCurrentRun();
  });
}

if (el.refreshRunsBtn) {
  el.refreshRunsBtn.addEventListener("click", () => {
    refreshRuns();
  });
}

async function handleRunSelectorChange(nextRunId) {
  const runId = String(nextRunId || "").trim();
  if (!runId || runId === state.currentRunId) return;
  setCurrentRunId(runId);
  renderQuestions(state.plan?.questions || []);
  await pollStatus(runId);
  await refreshArtifacts();
  await refreshAgentPanel();
  await refreshRunCompare();
  await refreshHitList();
  ensureAutoPoll();
}

if (el.runSelector) {
  el.runSelector.addEventListener("change", async () => {
    await handleRunSelectorChange(el.runSelector.value);
  });
}

if (el.setupRunSelector) {
  el.setupRunSelector.addEventListener("change", async () => {
    await handleRunSelectorChange(el.setupRunSelector.value);
  });
}

if (el.analyzeRunSelector) {
  el.analyzeRunSelector.addEventListener("change", async () => {
    await handleRunSelectorChange(el.analyzeRunSelector.value);
  });
}

if (el.runCompareBaseline) {
  el.runCompareBaseline.addEventListener("change", () => {
    state.runCompareBaselineId = String(el.runCompareBaseline.value || "").trim();
  });
}

if (el.runCompareRefresh) {
  el.runCompareRefresh.addEventListener("click", () => {
    refreshRunCompare();
  });
}

if (el.runCompareDetails) {
  el.runCompareDetails.addEventListener("click", () => {
    if (!state.runCompareResult) return;
    const markdown = buildRunCompareDetailsMarkdown(state.runCompareResult);
    const runId = state.runCompareResult.run_id || state.currentRunId || "run";
    openReportModal(t("analyze.runCompare.detailsTitle"), markdown, `run_compare_${runId}.md`);
  });
}

if (el.refreshAgentPanel) {
  el.refreshAgentPanel.addEventListener("click", () => {
    refreshAgentPanel();
  });
}

el.autoPoll.addEventListener("change", () => {
  ensureAutoPoll();
});

if (el.refreshArtifacts) {
  el.refreshArtifacts.addEventListener("click", refreshArtifacts);
}
if (el.analyzeRefreshArtifacts) {
  el.analyzeRefreshArtifacts.addEventListener("click", refreshArtifacts);
}
bindArtifactFilterControls("monitor");
bindArtifactFilterControls("analyze");

if (el.artifactCompareLeft) {
  el.artifactCompareLeft.addEventListener("change", () => {
    state.artifactCompareLeftPath = String(el.artifactCompareLeft.value || "");
    renderArtifactCompareSelects();
    renderCopilotContext();
    if (state.artifactCompareLeftPath && state.artifactCompareRightPath) {
      void compareSelected3dArtifacts();
    }
  });
}

if (el.artifactCompareMode) {
  el.artifactCompareMode.addEventListener("change", () => {
    const mode = String(el.artifactCompareMode.value || "structure").trim().toLowerCase();
    state.artifactCompareMode = mode === "sequence" ? "sequence" : "structure";
    renderCopilotContext();
    if (state.artifactCompareLeftPath && state.artifactCompareRightPath) {
      void compareSelected3dArtifacts();
    }
  });
}

if (el.artifactCompareRight) {
  el.artifactCompareRight.addEventListener("change", () => {
    state.artifactCompareRightPath = String(el.artifactCompareRight.value || "");
    renderArtifactCompareSelects();
    renderCopilotContext();
    if (state.artifactCompareLeftPath && state.artifactCompareRightPath) {
      void compareSelected3dArtifacts();
    }
  });
}

if (el.artifactCompareSwap) {
  el.artifactCompareSwap.addEventListener("click", () => {
    const leftPath = String(state.artifactCompareLeftPath || "");
    const rightPath = String(state.artifactCompareRightPath || "");
    state.artifactCompareLeftPath = rightPath;
    state.artifactCompareRightPath = leftPath;
    renderArtifactCompareSelects();
    renderCopilotContext();
    if (state.artifactCompareLeftPath && state.artifactCompareRightPath) {
      void compareSelected3dArtifacts();
    }
  });
}

if (el.artifactCompareRun) {
  el.artifactCompareRun.addEventListener("click", () => {
    compareSelected3dArtifacts();
  });
}

if (el.artifactCompareClear) {
  el.artifactCompareClear.addEventListener("click", () => {
    state.artifactCompareLeftPath = "";
    state.artifactCompareRightPath = "";
    renderArtifactCompareSelects();
    setComparePreviewPlaceholder("artifacts.preview.placeholder");
    renderCopilotContext();
  });
}

if (el.artifactGenerateReport) {
  el.artifactGenerateReport.addEventListener("click", async () => {
    if (!state.currentRunId) return;
    await generateReport();
  });
}

if (el.artifactComparisonDetails) {
  el.artifactComparisonDetails.addEventListener("click", () => {
    openComparisonDetailModal();
  });
}

if (el.settingsBtn && el.settingsPanel) {
  el.settingsBtn.addEventListener("click", () => {
    el.settingsPanel.classList.remove("hidden");
    if (el.apiBaseValue) {
      el.apiBaseValue.textContent = state.apiBase;
    }
    updateReportLangSelect();
  });
}

if (el.settingsClose && el.settingsPanel) {
  el.settingsClose.addEventListener("click", () => {
    el.settingsPanel.classList.add("hidden");
  });
}

if (el.reportLangSelect) {
  el.reportLangSelect.addEventListener("change", () => {
    setReportLang(el.reportLangSelect.value);
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

if (el.helpBtn && el.helpPanel) {
  el.helpBtn.addEventListener("click", () => {
    el.helpPanel.classList.remove("hidden");
  });
}

if (el.helpClose && el.helpPanel) {
  el.helpClose.addEventListener("click", () => {
    el.helpPanel.classList.add("hidden");
  });
}

if (el.helpPanel) {
  el.helpPanel.addEventListener("click", (event) => {
    if (event.target === el.helpPanel) {
      el.helpPanel.classList.add("hidden");
    }
  });
}

if (el.reportModalClose) {
  el.reportModalClose.addEventListener("click", closeReportModal);
}

if (el.reportModal) {
  el.reportModal.addEventListener("click", (event) => {
    if (event.target === el.reportModal) {
      closeReportModal();
    }
  });
}

if (el.reportModalToggle) {
  el.reportModalToggle.addEventListener("click", toggleReportModalMode);
}

if (el.reportModalDownload) {
  el.reportModalDownload.addEventListener("click", downloadReportModal);
}

if (el.adminBtn && el.adminPanel) {
  el.adminBtn.addEventListener("click", () => {
    el.adminPanel.classList.remove("hidden");
  });
}

if (el.adminClose && el.adminPanel) {
  el.adminClose.addEventListener("click", () => {
    el.adminPanel.classList.add("hidden");
  });
}

if (el.adminPanel) {
  el.adminPanel.addEventListener("click", (event) => {
    if (event.target === el.adminPanel) {
      el.adminPanel.classList.add("hidden");
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

if (el.submitReportReview) {
  el.submitReportReview.addEventListener("click", submitReportReview);
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

if (el.viewReportRendered) {
  el.viewReportRendered.addEventListener("click", openRenderedReport);
}

if (el.saveReport) {
  el.saveReport.addEventListener("click", saveReport);
}

if (el.exportRunPackage) {
  el.exportRunPackage.addEventListener("click", exportRunPackage);
}

if (el.hitListCutoff) {
  el.hitListCutoff.addEventListener("input", () => {
    state.hitListCutoff = Math.max(0, Math.min(100, Number(el.hitListCutoff.value || 0)));
    updateHitCutoffLabel();
    renderHitList();
  });
}

if (el.hitListLimit) {
  el.hitListLimit.addEventListener("change", () => {
    const value = Number(el.hitListLimit.value || state.hitListLimit || 120);
    state.hitListLimit = Math.max(10, Math.min(500, Number.isFinite(value) ? value : 120));
    el.hitListLimit.value = String(state.hitListLimit);
    renderHitList();
  });
}

[
  el.hitWeightSoluprot,
  el.hitWeightPlddt,
  el.hitWeightRmsd,
  el.hitWeightNovelty,
].forEach((inputEl) => {
  if (!inputEl) return;
  inputEl.addEventListener("change", () => {
    state.hitListWeights = readHitWeightsFromInputs();
    setHitWeightInputValues();
  });
});

if (el.hitListRefresh) {
  el.hitListRefresh.addEventListener("click", () => {
    refreshHitList();
  });
}

if (el.hitListDetails) {
  el.hitListDetails.addEventListener("click", () => {
    const markdown = buildHitListDetailsMarkdown();
    openReportModal(t("analyze.hitList.detailsTitle"), markdown, `hit_list_${state.currentRunId || "run"}.md`);
  });
}

if (el.analyzeChartType) {
  el.analyzeChartType.addEventListener("change", () => {
    setChartView(el.analyzeChartType.value);
  });
}

if (el.reportChartType) {
  el.reportChartType.addEventListener("change", () => {
    setChartView(el.reportChartType.value);
  });
}

if (el.reportContent) {
  el.reportContent.addEventListener("input", () => {
    updateReportArtifactLinks(el.reportContent.value);
  });
}

initLanguage();
initCopilot();

if (state.user && state.token) {
  loadSession();
} else {
  showLogin();
}

initFeedbackUI();
if (el.hitListCutoff) {
  state.hitListCutoff = Math.max(0, Math.min(100, Number(el.hitListCutoff.value || 0)));
}
if (el.hitListLimit) {
  const limit = Number(el.hitListLimit.value || state.hitListLimit || 120);
  state.hitListLimit = Math.max(10, Math.min(500, Number.isFinite(limit) ? limit : 120));
  el.hitListLimit.value = String(state.hitListLimit);
}
setHitWeightInputValues();
updateHitCutoffLabel();
populateRunCompareBaselineOptions();
syncChartSelectors();
renderRunCompareSummary(null);
renderHitList();
renderMonitorCompleteness(null, null);
updateAnalyzeSummary();
renderAllArtifactViews(state.artifacts);
setFilePreviewPlaceholder("monitor");
setFilePreviewPlaceholder("analyze", "analyze.files.placeholder");
setComparePreviewPlaceholder("artifacts.preview.placeholder");
updateMonitorActionButtons();
renderCopilotContext();
ensureAutoPoll();
