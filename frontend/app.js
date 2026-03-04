import {
  artifactMetaFromPath,
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

const LANG_KEY = "kbf.lang";
const LANG_OPTIONS = ["en", "ko"];
const REPORT_LANG_KEY = "kbf.reportLang";
const REPORT_LANG_OPTIONS = ["auto", "en", "ko"];

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
  lastStatusKey: "",
  answerMeta: {},
  chainRanges: null,
  artifacts: [],
  artifactMetaByPath: {},
  artifactFilters: {
    stage: "all",
    tier: "all",
    type: "all",
  },
  artifactComparison: null,
  artifactComparisonRunId: "",
  monitorNeedsReport: false,
  artifactCompareLeftPath: "",
  artifactCompareRightPath: "",
  runs: [],
  runModeById: {},
  progressByRunId: {},
  timingByRunId: {},
  feedbackCount: 0,
  experimentCount: 0,
  lastScore: null,
  lastRunStatus: null,
  reportModalText: "",
  reportModalMode: "rendered",
  reportModalFilename: "report.md",
  showBioemuCountOptions: false,
  showRfd3CountOptions: false,
  setupResiduePicker: createSetupResiduePickerState(),
};

if (state.apiBase && state.apiBase !== normalizeApiBase(savedApiBase)) {
  localStorage.setItem("kbf.apiBase", state.apiBase);
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
  pollBtn: document.getElementById("pollBtn"),
  cancelRunBtn: document.getElementById("cancelRunBtn"),
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
  artifactComparisonSummary: document.getElementById("artifactComparisonSummary"),
  artifactCompareLeft: document.getElementById("artifactCompareLeft"),
  artifactCompareRight: document.getElementById("artifactCompareRight"),
  artifactCompareRun: document.getElementById("artifactCompareRun"),
  artifactCompareClear: document.getElementById("artifactCompareClear"),
  artifactGenerateReport: document.getElementById("artifactGenerateReport"),
  artifactPreview: document.getElementById("artifactPreview"),
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
      "Select residues from a structure and append them to fixed_positions_extra. If target_pdb is missing, run once to create target.pdb (AF2 target), then load it from the selected run.",
    "setup.residuePicker.source": "Structure source: {source}",
    "setup.residuePicker.source.none": "none",
    "setup.residuePicker.loadTargetInput": "Load target_input PDB",
    "setup.residuePicker.loadRfd3Input": "Load rfd3_input_pdb",
    "setup.residuePicker.loadRunTarget": "Load selected run target.pdb",
    "setup.residuePicker.runAf2": "Run AF2 from FASTA",
    "setup.residuePicker.runAf2Running": "Running AF2 to generate a target structure...",
    "setup.residuePicker.runAf2NeedsFasta": "Attach a FASTA/sequence in target_input first.",
    "setup.residuePicker.runAf2NoResult": "AF2 completed but ranked_0.pdb was not found.",
    "setup.residuePicker.runAf2Loaded": "AF2 structure loaded from {run}:{path}",
    "setup.residuePicker.runAf2Failed": "AF2 run failed: {error}",
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
    "monitor.poll": "Poll Now",
    "monitor.stop": "Stop Run",
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
    "artifacts.desc": "Filter outputs and open previews.",
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
    "artifacts.compare.generateReport": "Generate Report",
    "artifacts.compare.wt": "WT vs Design",
    "artifacts.compare.source": "RFD3 vs BioEmu",
    "artifacts.compare.metric": "Metric",
    "artifacts.compare.wtValue": "WT",
    "artifacts.compare.designMedian": "Design median",
    "artifacts.compare.delta": "Delta",
    "artifacts.compare.wtEnabled": "WT compare enabled: {enabled}",
    "artifacts.compare.sourceName": "Source",
    "artifacts.compare.backbones": "Backbones",
    "artifacts.compare.passRate": "SoluProt pass",
    "artifacts.compare.af2Selected": "AF2 selected",
    "artifacts.compare.plddtMedian": "Median pLDDT",
    "artifacts.compare.rmsdMedian": "Median RMSD",
    "artifacts.preview.title": "Artifact Preview",
    "artifacts.preview.desc": "3D structures, images, or text extracts.",
    "artifacts.preview.placeholder": "Select an artifact to preview it here.",
    "artifacts.preview.compare.left": "WT/Reference 3D",
    "artifacts.preview.compare.right": "Design 3D",
    "artifacts.preview.compare.run": "Compare 3D",
    "artifacts.preview.compare.clear": "Clear",
    "artifacts.preview.compare.missing": "Select both left and right 3D artifacts first.",
    "artifacts.preview.compare.failed": "3D comparison failed: {error}",
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
    "report.save": "Save",
    "report.links": "Artifact Links",
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
    "help.analyze.step1": "Feedback captures subjective evaluation.",
    "help.analyze.step2": "Experiments log wet-lab outcomes.",
    "help.analyze.step3": "Reports consolidate results and link artifacts.",
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
    "question.targetInput.label": "Target Input",
    "question.targetInput.help": "Provide target_pdb or target_fasta (raw text).",
    "question.stopAfter.label": "Stop After",
    "question.stopAfter.help": "Where to stop? (msa/rfd3/bioemu/design/soluprot/af2/novelty)",
    "question.designChains.label": "Design Chains",
    "question.designChains.help": "Which chains to design? (default: all)",
    "question.wtCompare.label": "WT Compare",
    "question.wtCompare.help": "Compute WT baseline (SoluProt/AF2) and compare in report.",
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
    "question.af2MaxCandidatesPerTier.label": "AF2 per Tier (Top N)",
    "question.af2MaxCandidatesPerTier.help":
      "Run AF2 only for top N SoluProt-passed designs per tier (ranked by SoluProt score, 0 = all).",
    "question.af2PlddtCutoff.label": "AF2 pLDDT Cutoff",
    "question.af2PlddtCutoff.help": "Minimum pLDDT threshold for AF2 pass filtering (default: 85).",
    "question.af2RmsdCutoff.label": "AF2 RMSD Cutoff",
    "question.af2RmsdCutoff.help": "Maximum RMSD threshold (angstrom) for AF2 pass filtering (default: 2.0).",
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
    "question.targetFasta.help": "Provide target FASTA or sequence for AlphaFold2.",
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
    "hint.none": "No missing inputs. You can run now.",
    "hint.ready": "All required inputs captured.",
    "hint.missing": "Missing required inputs.",
    "hint.running": "A run is already in progress.",
    "run.reset": "Inputs reset. Reconfirm selections and attachments.",
    "runmode.pipeline": "Full Pipeline",
    "runmode.rfd3": "RFD3 (Backbone)",
    "runmode.bioemu": "BioEmu (Backbone)",
    "runmode.msa": "MSA (MMseqs2)",
    "runmode.design": "ProteinMPNN",
    "runmode.soluprot": "SoluProt",
    "runmode.af2": "AlphaFold2",
    "runmode.diffdock": "DiffDock",
    "stop.full": "Full (Novelty)",
    "stage.msa": "MSA",
    "stage.rfd3": "RFD3",
    "stage.bioemu": "BioEmu",
    "stage.design": "Design",
    "stage.soluprot": "SoluProt",
    "stage.af2": "AlphaFold2",
    "run.label.pipeline": "Run Pipeline",
    "run.label.rfd3": "Run RFD3",
    "run.label.bioemu": "Run BioEmu",
    "run.label.msa": "Run MSA",
    "run.label.design": "Run ProteinMPNN",
    "run.label.soluprot": "Run SoluProt",
    "run.label.af2": "Run AlphaFold2",
    "run.label.diffdock": "Run DiffDock",
    "mode.pipeline": "pipeline",
    "mode.rfd3": "RFD3",
    "mode.bioemu": "BioEmu",
    "mode.msa": "MSA",
    "mode.design": "ProteinMPNN",
    "mode.soluprot": "SoluProt",
    "mode.af2": "AlphaFold2",
    "mode.diffdock": "DiffDock",
    "run.launching": "Launching {mode} run {id}...",
    "run.started": "Run started: {id}",
    "run.failed": "Run failed: {error}",
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
    "feedback.reason.low_novelty": "Low Novelty",
    "feedback.reason.high_novelty": "High Novelty",
    "feedback.reason.unstable": "Unstable",
    "feedback.reason.stable": "Stable",
    "feedback.reason.other": "Other",
    "feedback.stage.auto": "Auto",
    "feedback.stage.msa": "MSA",
    "feedback.stage.design": "Design",
    "feedback.stage.soluprot": "SoluProt",
    "feedback.stage.af2": "AlphaFold2",
    "feedback.stage.novelty": "Novelty",
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
      "구조에서 잔기를 선택해 fixed_positions_extra에 추가합니다. target_pdb가 없으면 먼저 1회 실행해 target.pdb(AF2 target)를 만든 뒤, 선택한 run에서 불러오세요.",
    "setup.residuePicker.source": "구조 소스: {source}",
    "setup.residuePicker.source.none": "없음",
    "setup.residuePicker.loadTargetInput": "target_input PDB 불러오기",
    "setup.residuePicker.loadRfd3Input": "rfd3_input_pdb 불러오기",
    "setup.residuePicker.loadRunTarget": "선택 run의 target.pdb 불러오기",
    "setup.residuePicker.runAf2": "FASTA로 AF2 실행",
    "setup.residuePicker.runAf2Running": "target 구조 생성을 위해 AF2를 실행 중입니다...",
    "setup.residuePicker.runAf2NeedsFasta": "먼저 target_input에 FASTA/서열을 첨부하세요.",
    "setup.residuePicker.runAf2NoResult": "AF2는 완료됐지만 ranked_0.pdb를 찾지 못했습니다.",
    "setup.residuePicker.runAf2Loaded": "{run}:{path} 에서 AF2 구조를 불러왔습니다.",
    "setup.residuePicker.runAf2Failed": "AF2 실행 실패: {error}",
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
    "monitor.poll": "지금 조회",
    "monitor.stop": "정지",
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
    "artifacts.desc": "출력을 필터하고 미리보기를 열 수 있습니다.",
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
    "artifacts.compare.generateReport": "리포트 생성",
    "artifacts.compare.wt": "WT 대비 Design",
    "artifacts.compare.source": "RFD3 대비 BioEmu",
    "artifacts.compare.metric": "지표",
    "artifacts.compare.wtValue": "WT",
    "artifacts.compare.designMedian": "Design 중앙값",
    "artifacts.compare.delta": "차이",
    "artifacts.compare.wtEnabled": "WT 비교 사용: {enabled}",
    "artifacts.compare.sourceName": "소스",
    "artifacts.compare.backbones": "백본 수",
    "artifacts.compare.passRate": "SoluProt 통과",
    "artifacts.compare.af2Selected": "AF2 선발",
    "artifacts.compare.plddtMedian": "pLDDT 중앙값",
    "artifacts.compare.rmsdMedian": "RMSD 중앙값",
    "artifacts.preview.title": "아티팩트 미리보기",
    "artifacts.preview.desc": "3D 구조, 이미지, 텍스트 미리보기.",
    "artifacts.preview.placeholder": "아티팩트를 선택하면 여기서 미리보기를 볼 수 있습니다.",
    "artifacts.preview.compare.left": "WT/기준 3D",
    "artifacts.preview.compare.right": "Design 3D",
    "artifacts.preview.compare.run": "3D 비교",
    "artifacts.preview.compare.clear": "초기화",
    "artifacts.preview.compare.missing": "좌/우 3D 아티팩트를 모두 선택하세요.",
    "artifacts.preview.compare.failed": "3D 비교 실패: {error}",
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
    "report.save": "저장",
    "report.links": "아티팩트 링크",
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
    "help.analyze.step1": "Feedback은 주관적 평가를 기록합니다.",
    "help.analyze.step2": "Experiments에 습식 결과를 기록합니다.",
    "help.analyze.step3": "Reports는 결과를 정리하고 아티팩트를 연결합니다.",
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
    "question.targetInput.label": "타깃 입력",
    "question.targetInput.help": "target_pdb 또는 target_fasta 원문을 입력하세요.",
    "question.stopAfter.label": "중단 단계",
    "question.stopAfter.help": "어디까지 실행할까요? (msa/rfd3/bioemu/design/soluprot/af2/novelty)",
    "question.designChains.label": "디자인 체인",
    "question.designChains.help": "디자인할 체인을 선택하세요. (기본: 전체)",
    "question.wtCompare.label": "WT 비교",
    "question.wtCompare.help": "WT 기준(SoluProt/AF2)을 계산해 리포트에 비교합니다.",
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
    "question.af2MaxCandidatesPerTier.label": "AF2 티어당 실행 개수 (상위 N개)",
    "question.af2MaxCandidatesPerTier.help":
      "티어별 SoluProt 통과 서열 중 상위 N개(점수 순)만 AF2를 실행합니다. 0이면 전체 실행.",
    "question.af2PlddtCutoff.label": "AF2 pLDDT 컷오프",
    "question.af2PlddtCutoff.help": "AF2 통과 필터링에 사용할 최소 pLDDT 임계값입니다. (기본값: 85)",
    "question.af2RmsdCutoff.label": "AF2 RMSD 컷오프",
    "question.af2RmsdCutoff.help": "AF2 통과 필터링에 사용할 최대 RMSD 임계값(Å)입니다. (기본값: 2.0)",
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
    "question.targetFasta.help": "AlphaFold2용 FASTA 또는 서열을 입력하세요.",
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
    "hint.none": "누락된 입력이 없습니다. 지금 실행할 수 있습니다.",
    "hint.ready": "필수 입력이 모두 완료되었습니다.",
    "hint.missing": "필수 입력이 누락되었습니다.",
    "hint.running": "이미 실행 중인 작업이 있습니다.",
    "run.reset": "입력을 초기화했습니다. 선택과 첨부를 다시 확인하세요.",
    "runmode.pipeline": "전체 파이프라인",
    "runmode.rfd3": "RFD3 (Backbone)",
    "runmode.bioemu": "BioEmu (Backbone)",
    "runmode.msa": "MSA (MMseqs2)",
    "runmode.design": "ProteinMPNN",
    "runmode.soluprot": "SoluProt",
    "runmode.af2": "AlphaFold2",
    "runmode.diffdock": "DiffDock",
    "stop.full": "전체 (Novelty)",
    "stage.msa": "MSA",
    "stage.rfd3": "RFD3",
    "stage.bioemu": "BioEmu",
    "stage.design": "디자인",
    "stage.soluprot": "SoluProt",
    "stage.af2": "AlphaFold2",
    "run.label.pipeline": "파이프라인 실행",
    "run.label.rfd3": "RFD3 실행",
    "run.label.bioemu": "BioEmu 실행",
    "run.label.msa": "MSA 실행",
    "run.label.design": "ProteinMPNN 실행",
    "run.label.soluprot": "SoluProt 실행",
    "run.label.af2": "AlphaFold2 실행",
    "run.label.diffdock": "DiffDock 실행",
    "mode.pipeline": "파이프라인",
    "mode.rfd3": "RFD3",
    "mode.bioemu": "BioEmu",
    "mode.msa": "MSA",
    "mode.design": "ProteinMPNN",
    "mode.soluprot": "SoluProt",
    "mode.af2": "AlphaFold2",
    "mode.diffdock": "DiffDock",
    "run.launching": "{mode} 실행 {id} 시작...",
    "run.started": "실행 시작: {id}",
    "run.failed": "실행 실패: {error}",
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
    "feedback.reason.low_novelty": "신규성 낮음",
    "feedback.reason.high_novelty": "신규성 높음",
    "feedback.reason.unstable": "불안정",
    "feedback.reason.stable": "안정적",
    "feedback.reason.other": "기타",
    "feedback.stage.auto": "자동",
    "feedback.stage.msa": "MSA",
    "feedback.stage.design": "Design",
    "feedback.stage.soluprot": "SoluProt",
    "feedback.stage.af2": "AlphaFold2",
    "feedback.stage.novelty": "Novelty",
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

function t(key, params = {}) {
  const table = I18N[state.lang] || I18N.en;
  const fallback = I18N.en[key] || key;
  const template = table[key] || fallback;
  return String(template).replace(/\{(\w+)\}/g, (_, k) => {
    if (params[k] === undefined || params[k] === null) return "";
    return String(params[k]);
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

const RUN_MODE_OPTIONS = [
  { labelKey: "runmode.pipeline", value: "pipeline" },
  { labelKey: "runmode.rfd3", value: "rfd3" },
  { labelKey: "runmode.bioemu", value: "bioemu" },
  { labelKey: "runmode.msa", value: "msa" },
  { labelKey: "runmode.design", value: "design" },
  { labelKey: "runmode.soluprot", value: "soluprot" },
  { labelKey: "runmode.af2", value: "af2" },
  { labelKey: "runmode.diffdock", value: "diffdock" },
];

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
  stop_after: {
    labelKey: "question.stopAfter.label",
    questionKey: "question.stopAfter.help",
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
  af2_target: { en: "AF2 Target", ko: "AF2 타깃" },
  pdb_preprocess: { en: "PDB Preprocess", ko: "PDB 전처리" },
  query_pdb_check: { en: "Query/PDB Check", ko: "Query/PDB 검증" },
  diffdock: { en: "DiffDock", ko: "DiffDock" },
  ligand_mask: { en: "Ligand Mask", ko: "리간드 마스킹" },
  surface_mask: { en: "Surface Mask", ko: "표면 마스킹" },
  mask_consensus: { en: "Mask Consensus", ko: "마스킹 합의" },
  design: { en: "ProteinMPNN", ko: "ProteinMPNN" },
  soluprot: { en: "SoluProt", ko: "SoluProt" },
  af2: { en: "AlphaFold2", ko: "AlphaFold2" },
  novelty: { en: "Novelty", ko: "Novelty" },
  wt: { en: "WT Compare", ko: "WT 비교" },
  wt_baseline: { en: "WT Baseline", ko: "WT 기준선" },
  wt_soluprot: { en: "WT SoluProt", ko: "WT SoluProt" },
  wt_af2: { en: "WT AF2", ko: "WT AF2" },
  agent: { en: "Agent Panel", ko: "에이전트 패널" },
  misc: { en: "Misc", ko: "기타" },
};

const PROGRESS_PLANS = {
  pipeline: ["msa", "conservation", "backbone", "wt", "masking", "design", "soluprot", "af2", "novelty", "done"],
  design: ["msa", "conservation", "backbone", "masking", "design", "done"],
  soluprot: ["msa", "conservation", "backbone", "masking", "design", "soluprot", "done"],
  rfd3: ["msa", "conservation", "rfd3", "done"],
  bioemu: ["msa", "conservation", "bioemu", "done"],
  msa: ["msa", "done"],
  af2: ["af2", "done"],
  diffdock: ["diffdock", "done"],
};

const TERMINAL_RUN_STATES = new Set(["completed", "failed", "cancelled"]);

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

function openReportModal(title, content, filename) {
  if (!el.reportModal) return;
  state.reportModalText = String(content || "");
  state.reportModalMode = "rendered";
  state.reportModalFilename = filename || "report.md";
  if (el.reportModalTitle) el.reportModalTitle.textContent = title || "Report";
  if (el.reportModalToggle) el.reportModalToggle.textContent = t("report.modal.toggleRendered");
  if (el.reportModalContent) {
    el.reportModalContent.innerHTML = renderMarkdown(state.reportModalText);
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
    el.reportModalContent.innerHTML = renderMarkdown(state.reportModalText || "");
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
  updateMonitorReportActions();
  renderArtifactFilters(state.artifacts);
  renderArtifacts(state.artifacts);
  if (state.runs) renderRuns(state.runs);
  updateReportArtifactLinks(el.reportContent ? el.reportContent.value : "");
  updateReportScore(state.lastScore || {});
  updateAnalyzeSummary();
  updateReportLangSelect();
  if (state.lastRunStatus) {
    updateRunInfo(state.lastRunStatus);
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
        id: "stop_after",
        labelKey: "question.stopAfter.label",
        questionKey: "question.stopAfter.help",
        required: false,
        default: "novelty",
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
    questions.push({
      id: "target_input",
      labelKey: "question.targetFasta.label",
      questionKey: "question.targetFasta.help",
      required: true,
    });
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
  state.showBioemuCountOptions = false;
  state.showRfd3CountOptions = false;
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
    ...state.artifacts.map((item) => ({ label: item.path, value: item.path })),
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
  if (!payload || typeof payload !== "object") return "";

  const stopAfter = String(payload.stop_after || "")
    .trim()
    .toLowerCase();
  if (stopAfter === "msa") return "msa";
  if (stopAfter === "rfd3") return "rfd3";
  if (stopAfter === "bioemu") return "bioemu";
  if (stopAfter === "design") return "design";
  if (stopAfter === "soluprot") return "soluprot";
  if (stopAfter === "af2") return "af2";
  if (stopAfter === "novelty") return "pipeline";

  const isDiffdockRequest =
    "protein_pdb" in payload ||
    "diffdock_ligand_smiles" in payload ||
    "diffdock_ligand_sdf" in payload;
  if (isDiffdockRequest) return "diffdock";

  const isPipelineRequest =
    "num_seq_per_tier" in payload ||
    "mmseqs_target_db" in payload ||
    "novelty_target_db" in payload ||
    "rfd3_max_return_designs" in payload;
  if (isPipelineRequest) return "pipeline";

  const isAf2Request = "af2_model_preset" in payload && "af2_db_preset" in payload;
  if (isAf2Request) return "af2";

  return "";
}

async function ensureRunModeForRunId(runId, status) {
  if (!runId) return "pipeline";
  const mapped = state.runModeById[runId];
  if (mapped && PROGRESS_PLANS[mapped]) return mapped;

  try {
    const req = await apiCall("pipeline.read_artifact", {
      run_id: runId,
      path: "request.json",
      max_bytes: 512000,
    });
    const text = typeof req?.text === "string" ? req.text : "";
    if (text.trim()) {
      const payload = JSON.parse(text);
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

function progressStepLabel(step) {
  if (step === "backbone") return t("monitor.progress.backbone");
  if (step === "wt") return t("monitor.progress.wt");
  if (step === "masking") return t("monitor.progress.masking");
  if (step === "done") return t("monitor.progress.done");
  return formatStageLabel(step);
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
  const steps = PROGRESS_PLANS[mode] || PROGRESS_PLANS.pipeline;
  const runState = String(status?.state || "").trim().toLowerCase();
  const currentStep = mapStageToProgressStep(status?.stage, mode);

  const runId = state.currentRunId || "";
  const cached = runId ? state.progressByRunId[runId] : null;
  let stepIndex = currentStep ? steps.indexOf(currentStep) : -1;
  if (stepIndex < 0 && cached && cached.mode === mode && Number.isFinite(cached.index)) {
    stepIndex = cached.index;
  }
  if (stepIndex < 0) stepIndex = 0;

  let percent = 0;
  if (currentStep === "done") {
    percent = 100;
    stepIndex = steps.length - 1;
  } else {
    const base = Math.max(0, stepIndex);
    const offset =
      runState === "running" ? 0.45 : runState === "completed" ? 1.0 : runState === "failed" ? 0.2 : 0.1;
    percent = ((base + offset) / Math.max(1, steps.length)) * 100;
    if (TERMINAL_RUN_STATES.has(runState) && runState !== "completed") {
      percent = Math.max(percent, ((base + 0.75) / Math.max(1, steps.length)) * 100);
    }
    percent = Math.max(1, Math.min(99, percent));
  }

  const rounded = Math.max(0, Math.min(100, Math.round(percent)));
  el.runProgressFill.style.width = `${rounded}%`;
  el.runProgressPercent.textContent = `${rounded}%`;
  el.runProgressLabel.textContent = progressStepLabel(steps[Math.min(stepIndex, steps.length - 1)]);

  el.runProgressStages.innerHTML = steps
    .map((step, index) => {
      let cls = "";
      if (index < stepIndex) cls = "done";
      else if (index === stepIndex) cls = runState === "failed" || runState === "error" ? "failed" : "current";
      return `<span class="progress-stage ${cls}">${escapeHtml(progressStepLabel(step))}</span>`;
    })
    .join("");

  if (runId) {
    state.progressByRunId[runId] = { mode, index: stepIndex, percent: rounded };
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
  el.runStageValue.textContent = status.stage || "-";
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

  if (el.setupContextStageValue) el.setupContextStageValue.textContent = status.stage || "-";
  if (el.setupContextStateValue) {
    el.setupContextStateValue.textContent = status.state || "-";
    setStateBadge(el.setupContextStateValue, runState);
  }
  if (el.analyzeContextStageValue) el.analyzeContextStageValue.textContent = status.stage || "-";
  if (el.analyzeContextStateValue) {
    el.analyzeContextStateValue.textContent = status.state || "-";
    setStateBadge(el.analyzeContextStateValue, runState);
  }

  if (el.setupRunIdValue) el.setupRunIdValue.textContent = state.currentRunId || "-";
  if (el.setupRunStageValue) el.setupRunStageValue.textContent = status.stage || "-";
  if (el.setupRunStateValue) {
    el.setupRunStateValue.textContent = status.state || "-";
    setStateBadge(el.setupRunStateValue, runState);
  }
  if (el.setupRunUpdatedValue) el.setupRunUpdatedValue.textContent = status.updated_at || "-";
  if (el.setupRunEtaValue) el.setupRunEtaValue.textContent = etaText;

  updateMonitorErrorCards(status);
  state.currentRunState = String(status.state || "").toLowerCase();
  updateInlineStatus(status);
  updateRunEligibility(state.plan?.questions || []);
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
  state.artifactCompareLeftPath = "";
  state.artifactCompareRightPath = "";
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
  updateMonitorErrorCards(null);
  updateAnalyzeSummary();
  resetRunProgress();
  updateInlineStatus(null, runId);
  updateRunEligibility(state.plan?.questions || []);
  renderArtifactFilters(state.artifacts);
  renderArtifacts(state.artifacts);
  refreshArtifactSelects();
  renderArtifactComparisonSummary(null);
  updateMonitorReportActions();
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
    if (state.currentRunId) {
      pollStatus(state.currentRunId);
      refreshAgentPanel();
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
    btn.textContent = labelFor(opt);
    btn.addEventListener("click", () => {
      onSelect(opt.value);
      renderQuestions(state.plan?.questions || []);
    });
    group.appendChild(btn);
  });
  container.appendChild(group);
}

function renderQuestions(questions) {
  const inputStack = el.questionInputStack || el.questionStack;
  const configStack = el.questionConfigStack || el.questionStack;
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
    el.runBtn.disabled = false;
    el.runHint.textContent = t("hint.none");
    return;
  }

  const normalizedQuestions = (questions || [])
    .map((q) => normalizeQuestion(q))
    .filter(Boolean);

  const fileQuestionIds = new Set([
    "target_input",
    "target_pdb",
    "target_fasta",
    "rfd3_input_pdb",
    "diffdock_ligand",
  ]);

  const choiceQuestionIds = new Set([
    "run_mode",
    "stop_after",
    "design_chains",
    "rfd3_contig",
    "pdb_strip_nonpositive_resseq",
    "wt_compare",
    "mask_consensus_apply",
    "ligand_mask_use_original_target",
    "bioemu_use",
    "confirm_run",
  ]);

  const isFileQuestion = (q) => q && fileQuestionIds.has(q.id);
  const isChoiceQuestion = (q) => q && choiceQuestionIds.has(q.id);
  const fileQuestions = [];
  const choiceQuestions = [];
  const textQuestions = [];

  normalizedQuestions.forEach((q) => {
    if (isFileQuestion(q)) {
      fileQuestions.push(q);
    } else if (isChoiceQuestion(q)) {
      choiceQuestions.push(q);
    } else {
      textQuestions.push(q);
    }
  });

  choiceQuestions.forEach((q) => {
    const card = document.createElement("div");
    card.className = "question-card" + (q.required ? " required" : "");

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
    }

    if (q.id === "stop_after") {
      const routedDefault = state.plan?.routed_request?.stop_after;
      const current = state.answers.stop_after || routedDefault || q.default || "design";
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
          state.answers.stop_after = value;
          if (value === "bioemu") {
            state.answers.bioemu_use = true;
          }
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
          current = q.default !== undefined ? Boolean(q.default) : false;
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
          current = q.default !== undefined ? Boolean(q.default) : false;
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

  const bioemuCountQuestionIds = new Set(["bioemu_num_samples", "bioemu_max_return_structures"]);
  const rfd3CountQuestionIds = new Set(["rfd3_max_return_designs"]);
  const bioemuCountRelevant =
    state.runMode === "bioemu" || state.answers.bioemu_use === true || state.answers.stop_after === "bioemu";
  const rfd3CountRelevant =
    state.runMode === "rfd3" || state.answers.stop_after === "rfd3" || !isAnswerMissing(state.answers.rfd3_input_pdb);
  if (!bioemuCountRelevant) state.showBioemuCountOptions = false;
  if (!rfd3CountRelevant) state.showRfd3CountOptions = false;

  const appendCountToggleCard = ({
    titleKey,
    helpKey,
    showKey,
    hideKey,
    enabled,
    onToggle,
    summaryText = "",
  }) => {
    const card = document.createElement("div");
    card.className = "question-card";

    const title = document.createElement("div");
    title.className = "question-title";
    title.textContent = t(titleKey);

    const help = document.createElement("div");
    help.className = "question-help";
    help.textContent = t(helpKey);

    const summary = document.createElement("div");
    summary.className = "question-summary";
    summary.textContent = summaryText;

    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "ghost";
    toggleBtn.textContent = enabled ? t(hideKey) : t(showKey);
    toggleBtn.addEventListener("click", () => {
      onToggle(!enabled);
      renderQuestions(state.plan?.questions || []);
    });

    card.appendChild(title);
    card.appendChild(help);
    card.appendChild(summary);
    card.appendChild(toggleBtn);
    appendConfigCard(card);
  };

  const hasBioemuCountQuestions =
    bioemuCountRelevant && textQuestions.some((q) => bioemuCountQuestionIds.has(q.id));
  if (hasBioemuCountQuestions) {
    appendCountToggleCard({
      titleKey: "advanced.bioemuCounts.title",
      helpKey: "advanced.bioemuCounts.help",
      showKey: "advanced.bioemuCounts.show",
      hideKey: "advanced.bioemuCounts.hide",
      enabled: state.showBioemuCountOptions,
      summaryText: `samples=${state.answers.bioemu_num_samples ?? 10}, keep=${state.answers.bioemu_max_return_structures ?? 10}`,
      onToggle: (next) => {
        state.showBioemuCountOptions = Boolean(next);
      },
    });
    if (state.showBioemuCountOptions) {
      textQuestions
        .filter((q) => bioemuCountQuestionIds.has(q.id))
        .forEach((q) => appendTextQuestionCard(q));
    }
  }

  const hasRfd3CountQuestions =
    rfd3CountRelevant && textQuestions.some((q) => rfd3CountQuestionIds.has(q.id));
  if (hasRfd3CountQuestions) {
    appendCountToggleCard({
      titleKey: "advanced.rfd3Counts.title",
      helpKey: "advanced.rfd3Counts.help",
      showKey: "advanced.rfd3Counts.show",
      hideKey: "advanced.rfd3Counts.hide",
      enabled: state.showRfd3CountOptions,
      summaryText: `keep=${state.answers.rfd3_max_return_designs ?? 10}`,
      onToggle: (next) => {
        state.showRfd3CountOptions = Boolean(next);
      },
    });
    if (state.showRfd3CountOptions) {
      textQuestions
        .filter((q) => rfd3CountQuestionIds.has(q.id))
        .forEach((q) => appendTextQuestionCard(q));
    }
  }

  function appendTextQuestionCard(q) {
    const card = document.createElement("div");
    card.className = "question-card" + (q.required ? " required" : "");

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

  const hiddenCountQuestionIds = new Set([...bioemuCountQuestionIds, ...rfd3CountQuestionIds]);
  textQuestions.forEach((q) => {
    if (hiddenCountQuestionIds.has(q.id)) return;
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
            if (state.runMode === "pipeline") {
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
            if (state.runMode === "pipeline") {
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
        if (q.id === "rfd3_input_pdb" && state.runMode === "pipeline") {
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
    state.runMode === "pipeline" && normalizedQuestions.some((q) => q.id === "fixed_positions_extra");
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

  const missing = Array.from(requiredIds).filter((id) => {
    if (id === "confirm_run") return state.answers.confirm_run !== true;
    if (id === "bioemu_use") return state.answers.bioemu_use !== true;
    return isAnswerMissing(state.answers[id]);
  });
  const runBusy = state.runSubmitting || String(state.currentRunState || "").toLowerCase() === "running";
  if (missing.length === 0 && !runBusy) {
    el.runBtn.disabled = false;
    el.runHint.textContent = t("hint.ready");
  } else {
    el.runBtn.disabled = true;
    el.runHint.textContent = runBusy ? t("hint.running") : t("hint.missing");
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
  if (mode === "pipeline" && isAnswerMissing(answers.rfd3_input_pdb)) {
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
      "num_seq_per_tier",
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

function buildRoutedForMode(mode) {
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
  const preflightModes = new Set(["pipeline", "rfd3", "bioemu", "msa", "design", "soluprot"]);
  if (!preflightModes.has(mode)) {
    if (announce) {
      setMessage(t("preflight.unavailable", { mode: t(`mode.${mode}`) || mode }), "ai");
    }
    return { ok: false, preflight: null, plan: null };
  }
  const rawAnswers = buildAnswerPayload(mode);
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

  const routed = mergeRoutedWithMode(mode, plan?.routed_request || {});
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
  const prefix = state.user?.run_prefix || buildUserPrefix({ name: state.user?.username || "user" });
  const runId = createRunId(prefix);
  const mode = state.runMode || "pipeline";
  state.runModeById[runId] = mode;
  const rawAnswers = buildAnswerPayload(mode);
  const answers = state.plan?.allow_unfiltered_answers ? rawAnswers : filterAnswersForMode(mode, rawAnswers);
  let args = {};
  let toolName = "pipeline.run";

  if (["pipeline", "rfd3", "bioemu", "msa", "design", "soluprot"].includes(mode)) {
    const pre = await runPreflight({ announce: true });
    if (!pre.ok) {
      return;
    }
  }

  if (state.plan?.source === "prompt" && state.answers.confirm_run !== true) {
    setMessage(t("run.confirmRequired"), "ai");
    return;
  }

  if (["pipeline", "rfd3", "bioemu", "msa", "design", "soluprot"].includes(mode)) {
    args = buildRunArguments({
      prompt,
      routed: mergeRoutedWithMode(mode, state.plan?.routed_request || {}),
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

  const modeLabel = t(`mode.${mode}`) || mode;
  setMessage(t("run.launching", { mode: modeLabel, id: runId }), "ai");
  setCurrentRunId(runId);
  state.currentRunState = "running";
  state.runSubmitting = true;
  updateRunEligibility(state.plan?.questions || []);

  try {
    const result = await apiCall(toolName, args);
    state.runModeById[result.run_id] = mode;
    setMessage(t("run.started", { id: result.run_id }), "ai");
    setCurrentRunId(result.run_id);
    await refreshRuns();
    ensureAutoPoll();
    await pollStatus(result.run_id);
  } catch (err) {
    state.currentRunState = "failed";
    setMessage(t("run.failed", { error: err.message }), "ai");
  } finally {
    state.runSubmitting = false;
    updateRunEligibility(state.plan?.questions || []);
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
        const stage = fallbackStatus.stage || "-";
        const stateText = fallbackStatus.state || "-";
        const key = `${stage}|${stateText}`;
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
    const stage = result.status?.stage || "-";
    const stateText = result.status?.state || "-";
    const key = `${stage}|${stateText}`;
    if (key !== state.lastStatusKey) {
      state.lastStatusKey = key;
      setMessage(t("status.line", { stage, state: stateText }), "ai");
    }
  } catch (err) {
    state.currentRunState = "";
    updateRunEligibility(state.plan?.questions || []);
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

function renderArtifacts(list) {
  const filter = el.artifactFilter.value.trim().toLowerCase();
  el.artifactList.innerHTML = "";
  const stageFilter = state.artifactFilters.stage || "all";
  const tierFilter = state.artifactFilters.tier || "all";
  const typeFilter = state.artifactFilters.type || "all";
  const filtered = list.filter((item) => {
    const path = String(item.path || "");
    if (filter && !path.toLowerCase().includes(filter)) return false;
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
    el.artifactList.innerHTML = `<div class="placeholder">${t("artifact.none")}</div>`;
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
    const listEl = document.createElement("div");
    listEl.className = "artifact-group-list";
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
      div.innerHTML = `
        <span>${item.path}</span>
        <span class="artifact-meta">${tags.join("")}</span>
      `;
      div.addEventListener("click", () => previewArtifact(item));
      listEl.appendChild(div);
    });
    group.appendChild(header);
    group.appendChild(listEl);
    el.artifactList.appendChild(group);
  });
}

async function previewArtifact(item) {
  if (!state.currentRunId) return;
  if (item.type !== "file") return;
  const path = item.path;

  if (isStructurePath(path)) {
    try {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: state.currentRunId,
        path,
        max_bytes: 500000,
      });
      const format = /\.sdf$/i.test(path) ? "sdf" : "pdb";
      render3dModel(result.text || "", format);
      if (!state.artifactCompareLeftPath) {
        state.artifactCompareLeftPath = path;
      } else if (!state.artifactCompareRightPath && state.artifactCompareLeftPath !== path) {
        state.artifactCompareRightPath = path;
      }
      renderArtifactCompareSelects();
    } catch (err) {
      el.artifactPreview.innerHTML = `<div class="placeholder">${t("artifact.preview.failed", {
        error: err.message,
      })}</div>`;
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
      el.artifactPreview.innerHTML = `<div class="placeholder">${t("artifact.preview.failed", {
        error: err.message,
      })}</div>`;
    }
    return;
  }

  if (isBinaryPath(path)) {
    el.artifactPreview.innerHTML = `<div class="placeholder">${t("artifact.preview.binary", {
      path,
    })}</div>`;
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
    el.artifactPreview.innerHTML = `<div class="placeholder">${t("artifact.preview.failed", {
      error: err.message,
    })}</div>`;
  }
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
    link.innerHTML = `<span>${item.path}</span><span class=\"stage-tag\">${escapeHtml(
      formatStageLabel(stage)
    )}</span>`;
    link.addEventListener("click", () => previewArtifact(item));
    el.reportArtifactLinks.appendChild(link);
  });
}

function render3dModel(text, format) {
  if (!window.$3Dmol) {
    el.artifactPreview.innerHTML = `<div class="placeholder">${t(
      "artifact.preview.unavailable"
    )}</div>`;
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

function formatMetricValue(value, digits = 2, signed = false) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  const text = value.toFixed(digits);
  if (signed && value > 0) return `+${text}`;
  return text;
}

function localizedYesNo(value) {
  const isKo = (state.lang || "en") === "ko";
  return value ? (isKo ? "예" : "yes") : isKo ? "아니오" : "no";
}

function sourceLabel(source) {
  if (source === "rfd3") return "RFD3";
  if (source === "bioemu") return "BioEmu";
  return (state.lang || "en") === "ko" ? "기타" : "Other";
}

function formatPassRate(sourceBucket) {
  const total = Number(sourceBucket?.soluprot_total || 0);
  const passed = Number(sourceBucket?.soluprot_passed || 0);
  if (total <= 0) return "-";
  const rate = (passed / total) * 100.0;
  return `${passed}/${total} (${rate.toFixed(1)}%)`;
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
    /WT AF2:\s*pLDDT=([+-]?\d+(?:\.\d+)?|-)\s+RMSD=([+-]?\d+(?:\.\d+)?|-)/i
  );
  if (wtAf2Match) {
    summary.wt_vs_design.plddt.wt = parseNumberOrNull(wtAf2Match[1]);
    summary.wt_vs_design.rmsd.wt = parseNumberOrNull(wtAf2Match[2]);
    hasAny = true;
  }

  const designPlddtMatch = text.match(/Designs AF2 pLDDT:\s*median=([+-]?\d+(?:\.\d+)?).*?\(n=(\d+)\)/i);
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
    const selectedN = text.match(/Designs AF2 pLDDT:.*?\(n=(\d+)\)/i);
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

  const rowRegex =
    /^\|\s*(RFD3|BioEmu|Other|기타)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|/gim;
  let rowMatch = null;
  while ((rowMatch = rowRegex.exec(text))) {
    const sourceLabelRaw = String(rowMatch[1] || "").trim().toLowerCase();
    const key = sourceLabelRaw === "rfd3" ? "rfd3" : sourceLabelRaw === "bioemu" ? "bioemu" : "other";
    const backboneCount = Number(parseNumberOrNull(rowMatch[2]) || 0);
    const pass = parsePassStat(rowMatch[3]);
    const af2Count = Number(parseNumberOrNull(rowMatch[5]) || 0);
    summary.source_compare[key] = {
      backbone_count: backboneCount,
      soluprot_total: pass.total,
      soluprot_passed: pass.passed,
      soluprot_pass_rate: pass.passRate,
      af2_selected_total: af2Count,
      plddt_median: parseNumberOrNull(rowMatch[6]),
      rmsd_median: parseNumberOrNull(rowMatch[7]),
    };
    hasAny = true;
  }

  return hasAny ? summary : null;
}

function renderArtifactComparisonSummary(summary) {
  if (!el.artifactComparisonSummary) return;
  if (!summary || typeof summary !== "object") {
    el.artifactComparisonSummary.innerHTML = `<div class="placeholder">${t(
      "artifacts.compare.placeholder"
    )}</div>`;
    return;
  }

  const wt = summary?.wt_vs_design && typeof summary.wt_vs_design === "object" ? summary.wt_vs_design : {};
  const source =
    summary?.source_compare && typeof summary.source_compare === "object" ? summary.source_compare : {};
  const wtEnabled = Boolean(summary?.wt_compare_enabled);

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

  if (!wtHasData && sourceRows.length === 0) {
    el.artifactComparisonSummary.innerHTML = `<div class="placeholder">${t(
      "artifacts.compare.noData"
    )}</div>`;
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

  const sourceTableRows = sourceRows
    .map((key) => {
      const bucket = source[key] && typeof source[key] === "object" ? source[key] : {};
      const backbone = String(Number(bucket.backbone_count || 0));
      const passText = formatPassRate(bucket);
      const af2 = String(Number(bucket.af2_selected_total || 0));
      const plddt = formatMetricValue(bucket.plddt_median, 1, false);
      const rmsd = formatMetricValue(bucket.rmsd_median, 2, false);
      return `
        <tr>
          <th>${escapeHtml(sourceLabel(key))}</th>
          <td>${escapeHtml(backbone)}</td>
          <td>${escapeHtml(passText)}</td>
          <td>${escapeHtml(af2)}</td>
          <td>${escapeHtml(plddt)}</td>
          <td>${escapeHtml(rmsd)}</td>
        </tr>
      `;
    })
    .join("");

  const wtNote = t("artifacts.compare.wtEnabled", { enabled: localizedYesNo(wtEnabled) });
  el.artifactComparisonSummary.innerHTML = `
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
            <th>${escapeHtml(t("artifacts.compare.af2Selected"))}</th>
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
}

function updateMonitorReportActions() {
  if (!el.artifactGenerateReport) return;
  const hasRun = Boolean(String(state.currentRunId || "").trim());
  const shouldShow = hasRun && Boolean(state.monitorNeedsReport);
  el.artifactGenerateReport.classList.toggle("hidden", !shouldShow);
  el.artifactGenerateReport.disabled = !hasRun;
}

async function refreshArtifactComparisonSummary() {
  if (!el.artifactComparisonSummary) return;
  const runId = String(state.currentRunId || "").trim();
  if (!runId) {
    state.artifactComparison = null;
    state.artifactComparisonRunId = "";
    state.monitorNeedsReport = false;
    renderArtifactComparisonSummary(null);
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
    state.artifactComparison = parsed && typeof parsed === "object" ? parsed : null;
    state.artifactComparisonRunId = runId;
    state.monitorNeedsReport = false;
    renderArtifactComparisonSummary(state.artifactComparison);
    updateMonitorReportActions();
  } catch (_err) {
    if (String(state.currentRunId || "").trim() !== runId) return;
    try {
      const reportPayload = await apiCall("pipeline.get_report", { run_id: runId });
      if (String(state.currentRunId || "").trim() !== runId) return;
      const summaryFromApi =
        reportPayload?.comparison_summary && typeof reportPayload.comparison_summary === "object"
          ? reportPayload.comparison_summary
          : null;
      const summaryFromText = parseComparisonSummaryFromReportText(
        reportPayload?.report || reportPayload?.report_ko || ""
      );
      const resolved = summaryFromApi || summaryFromText;
      if (resolved) {
        state.artifactComparison = resolved;
        state.artifactComparisonRunId = runId;
        state.monitorNeedsReport = false;
        renderArtifactComparisonSummary(resolved);
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
        } else {
          renderArtifactComparisonSummary(null);
        }
      }
      updateMonitorReportActions();
    } catch (_reportErr) {
      if (String(state.currentRunId || "").trim() !== runId) return;
      state.artifactComparison = null;
      state.artifactComparisonRunId = runId;
      state.monitorNeedsReport = true;
      renderArtifactComparisonSummary(null);
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

function render3dComparison(left, right) {
  if (!window.$3Dmol) {
    el.artifactPreview.innerHTML = `<div class="placeholder">${t(
      "artifact.preview.unavailable"
    )}</div>`;
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "viewer3d-compare";
  el.artifactPreview.innerHTML = "";
  el.artifactPreview.appendChild(wrap);
  const buildPane = (path, text, format) => {
    const pane = document.createElement("div");
    pane.className = "viewer3d-pane";
    const header = document.createElement("div");
    header.className = "viewer3d-pane-header";
    header.textContent = path;
    const body = document.createElement("div");
    body.className = "viewer3d-pane-body";
    pane.appendChild(header);
    pane.appendChild(body);
    wrap.appendChild(pane);
    const viewer = window.$3Dmol.createViewer(body, { backgroundColor: "white" });
    viewer.addModel(text, format);
    apply3dStyle(viewer, format);
    viewer.zoomTo();
    viewer.render();
    if (typeof viewer.resize === "function") {
      viewer.resize();
    }
  };
  buildPane(left.path, left.text, left.format);
  buildPane(right.path, right.text, right.format);
}

function chooseDefaultComparePaths(structureItems) {
  const paths = new Set(structureItems.map((item) => String(item?.path || "")));
  if (!paths.has(state.artifactCompareLeftPath)) state.artifactCompareLeftPath = "";
  if (!paths.has(state.artifactCompareRightPath)) state.artifactCompareRightPath = "";

  if (!state.artifactCompareLeftPath) {
    const wtItem = structureItems.find((item) => artifactMetaForPath(item.path).stage === "wt");
    const targetItem = structureItems.find((item) => artifactMetaForPath(item.path).stage === "af2_target");
    state.artifactCompareLeftPath = String(wtItem?.path || targetItem?.path || structureItems[0]?.path || "");
  }

  if (!state.artifactCompareRightPath) {
    const designItem = structureItems.find((item) => {
      const path = String(item?.path || "");
      if (!path || path === state.artifactCompareLeftPath) return false;
      const meta = artifactMetaForPath(path);
      if (meta.tier) return true;
      if (meta.stage === "af2" && !/(?:^|\/)wt(?:\/|$)/i.test(path)) return true;
      return false;
    });
    if (designItem) {
      state.artifactCompareRightPath = String(designItem.path || "");
    }
  }

  if (state.artifactCompareRightPath === state.artifactCompareLeftPath) {
    const fallback = structureItems.find((item) => String(item?.path || "") !== state.artifactCompareLeftPath);
    state.artifactCompareRightPath = String(fallback?.path || "");
  }
}

function renderArtifactCompareSelects() {
  if (!el.artifactCompareLeft || !el.artifactCompareRight) return;
  const structureItems = (state.artifacts || [])
    .filter((item) => isStructureArtifactItem(item))
    .sort((a, b) => String(a.path || "").localeCompare(String(b.path || "")));

  chooseDefaultComparePaths(structureItems);
  const fill = (selectEl, placeholderKey) => {
    selectEl.innerHTML = "";
    const first = document.createElement("option");
    first.value = "";
    first.textContent = t(placeholderKey);
    selectEl.appendChild(first);
    structureItems.forEach((item) => {
      const path = String(item.path || "");
      const meta = artifactMetaForPath(path);
      const opt = document.createElement("option");
      opt.value = path;
      opt.textContent = `${formatStageLabel(meta.stage)} · ${path}`;
      selectEl.appendChild(opt);
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
    el.artifactPreview.innerHTML = `<div class="placeholder">${t(
      "artifacts.preview.compare.missing"
    )}</div>`;
    return;
  }
  try {
    const [leftResult, rightResult] = await Promise.all([
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
    ]);
    render3dComparison(
      {
        path: leftPath,
        text: String(leftResult?.text || ""),
        format: /\.sdf$/i.test(leftPath) ? "sdf" : "pdb",
      },
      {
        path: rightPath,
        text: String(rightResult?.text || ""),
        format: /\.sdf$/i.test(rightPath) ? "sdf" : "pdb",
      }
    );
  } catch (err) {
    el.artifactPreview.innerHTML = `<div class="placeholder">${t("artifacts.preview.compare.failed", {
      error: err.message,
    })}</div>`;
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
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

    const formatInline = (line) => {
      let out = escapeHtml(line);
      out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
      out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
      return out;
    };

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        closeLists();
        closePara();
        return;
      }

      const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
      if (heading) {
        closeLists();
        closePara();
        const level = heading[1].length;
        html.push(`<h${level}>${formatInline(heading[2])}</h${level}>`);
        return;
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
        return;
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
        return;
      }

      closeLists();
      if (!inPara) {
        html.push("<p>");
        inPara = true;
        html.push(formatInline(trimmed));
      } else {
        html.push("<br />" + formatInline(trimmed));
      }
    });

    closeLists();
    closePara();
  });

  return html.join("\n");
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
    rebuildArtifactMetaIndex(state.artifacts);
    renderArtifactFilters(state.artifacts);
    renderArtifacts(state.artifacts);
    refreshArtifactSelects();
    void refreshArtifactComparisonSummary();
    updateReportArtifactLinks(el.reportContent ? el.reportContent.value : "");
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

function renderArtifactFilters(items) {
  if (!el.artifactStageFilter || !el.artifactTierFilter || !el.artifactTypeFilter) return;
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

  state.artifactFilters.stage = setStageOptions(
    el.artifactStageFilter,
    stageOptions,
    t("artifacts.filter.allStages"),
    state.artifactFilters.stage
  );
  state.artifactFilters.tier = setOptions(
    el.artifactTierFilter,
    tiers,
    t("artifacts.filter.allTiers"),
    state.artifactFilters.tier
  );
  state.artifactFilters.type = setOptions(
    el.artifactTypeFilter,
    types,
    t("artifacts.filter.allTypes"),
    state.artifactFilters.type
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

async function loadReport() {
  if (!state.currentRunId || !el.reportContent) return;
  try {
    const result = await apiCall("pipeline.get_report", { run_id: state.currentRunId });
    el.reportContent.value = result.report || "";
    updateReportScore(result);
    updateReportArtifactLinks(result.report || "");
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
    const result = await apiCall("pipeline.generate_report", { run_id: state.currentRunId });
    el.reportContent.value = result.report || "";
    updateReportScore(result);
    updateReportArtifactLinks(result.report || "");
    await refreshArtifacts();
    void refreshArtifactComparisonSummary();
    if (el.reportStatus) el.reportStatus.textContent = t("report.generated");
  } catch (err) {
    if (el.reportStatus) {
      el.reportStatus.textContent = t("report.generateFailed", { error: err.message });
    }
  }
}

async function saveReport() {
  if (!state.currentRunId || !el.reportContent) return;
  const content = el.reportContent.value.trim();
  if (!content) {
    if (el.reportStatus) el.reportStatus.textContent = t("report.empty");
    return;
  }
  try {
    await apiCall("pipeline.save_report", { run_id: state.currentRunId, content });
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
        delete state.progressByRunId[runId];
        if (state.currentRunId === runId) {
          setCurrentRunId("");
          state.artifacts = [];
          renderArtifacts([]);
          if (el.artifactPreview) {
            el.artifactPreview.innerHTML = `<div class="placeholder">${t(
              "artifacts.preview.placeholder"
            )}</div>`;
          }
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

if (el.viewRunReport) {
  el.viewRunReport.addEventListener("click", loadRunReportModal);
}

if (el.viewAgentReport) {
  el.viewAgentReport.addEventListener("click", loadAgentReportModal);
}

el.pollBtn.addEventListener("click", () => {
  if (state.currentRunId) {
    pollStatus(state.currentRunId);
    refreshAgentPanel();
  }
});

if (el.setupPollBtn) {
  el.setupPollBtn.addEventListener("click", () => {
    if (state.currentRunId) {
      pollStatus(state.currentRunId);
      refreshAgentPanel();
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

if (el.refreshAgentPanel) {
  el.refreshAgentPanel.addEventListener("click", () => {
    refreshAgentPanel();
  });
}

el.autoPoll.addEventListener("change", () => {
  ensureAutoPoll();
});

el.refreshArtifacts.addEventListener("click", refreshArtifacts);

el.artifactFilter.addEventListener("input", () => {
  renderArtifacts(state.artifacts);
});

if (el.artifactStageFilter) {
  el.artifactStageFilter.addEventListener("change", () => {
    state.artifactFilters.stage = el.artifactStageFilter.value || "all";
    renderArtifacts(state.artifacts);
  });
}

if (el.artifactTierFilter) {
  el.artifactTierFilter.addEventListener("change", () => {
    state.artifactFilters.tier = el.artifactTierFilter.value || "all";
    renderArtifacts(state.artifacts);
  });
}

if (el.artifactTypeFilter) {
  el.artifactTypeFilter.addEventListener("change", () => {
    state.artifactFilters.type = el.artifactTypeFilter.value || "all";
    renderArtifacts(state.artifacts);
  });
}

if (el.artifactCompareLeft) {
  el.artifactCompareLeft.addEventListener("change", () => {
    state.artifactCompareLeftPath = String(el.artifactCompareLeft.value || "");
  });
}

if (el.artifactCompareRight) {
  el.artifactCompareRight.addEventListener("change", () => {
    state.artifactCompareRightPath = String(el.artifactCompareRight.value || "");
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
    el.artifactPreview.innerHTML = `<div class="placeholder">${t("artifacts.preview.placeholder")}</div>`;
  });
}

if (el.artifactGenerateReport) {
  el.artifactGenerateReport.addEventListener("click", async () => {
    if (!state.currentRunId) return;
    await generateReport();
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

if (el.saveReport) {
  el.saveReport.addEventListener("click", saveReport);
}

if (el.reportContent) {
  el.reportContent.addEventListener("input", () => {
    updateReportArtifactLinks(el.reportContent.value);
  });
}

initLanguage();

if (state.user && state.token) {
  loadSession();
} else {
  showLogin();
}

initFeedbackUI();
updateAnalyzeSummary();
ensureAutoPoll();
