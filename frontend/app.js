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

const LANG_KEY = "kbf.lang";
const LANG_OPTIONS = ["en", "ko"];

function loadLang() {
  const saved = localStorage.getItem(LANG_KEY);
  if (LANG_OPTIONS.includes(saved)) return saved;
  const browser = String(navigator.language || "").toLowerCase();
  if (browser.startsWith("ko")) return "ko";
  return "en";
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

const state = {
  apiBase: resolveApiBase(),
  user: loadUser(),
  token: localStorage.getItem("kbf.token") || "",
  lang: loadLang(),
  plan: null,
  runMode: "pipeline",
  feedbackRating: "good",
  feedbackReasons: [],
  reportReviewRating: "good",
  reportReviewReasons: [],
  answers: {},
  currentRunId: null,
  pollTimer: null,
  lastStatusKey: "",
  answerMeta: {},
  chainRanges: null,
  artifacts: [],
  runs: [],
  lastScore: null,
  reportModalText: "",
  reportModalMode: "rendered",
  reportModalFilename: "report.md",
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
  promptInput: document.getElementById("promptInput"),
  checkBtn: document.getElementById("checkBtn"),
  planBtn: document.getElementById("planBtn"),
  clearBtn: document.getElementById("clearBtn"),
  questionStack: document.getElementById("questionStack"),
  runBtn: document.getElementById("runBtn"),
  runHint: document.getElementById("runHint"),
  runInlineStatus: document.getElementById("runInlineStatus"),
  runIdValue: document.getElementById("runIdValue"),
  runStageValue: document.getElementById("runStageValue"),
  runStateValue: document.getElementById("runStateValue"),
  runUpdatedValue: document.getElementById("runUpdatedValue"),
  runScoreValue: document.getElementById("runScoreValue"),
  runEvidenceValue: document.getElementById("runEvidenceValue"),
  runRecommendationValue: document.getElementById("runRecommendationValue"),
  pollBtn: document.getElementById("pollBtn"),
  autoPoll: document.getElementById("autoPoll"),
  refreshRunsBtn: document.getElementById("refreshRunsBtn"),
  artifactList: document.getElementById("artifactList"),
  artifactFilter: document.getElementById("artifactFilter"),
  refreshArtifacts: document.getElementById("refreshArtifacts"),
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
  viewRunReportKo: document.getElementById("viewRunReportKo"),
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
  settingsBtn: document.getElementById("settingsBtn"),
  settingsPanel: document.getElementById("settingsPanel"),
  settingsClose: document.getElementById("settingsClose"),
  apiBaseValue: document.getElementById("apiBaseValue"),
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
    "login.title": "Enter the Lab",
    "login.desc": "Identify yourself to separate runs and keep artifacts organized.",
    "login.username": "Username",
    "login.username.placeholder": "e.g. hana.kim",
    "login.password": "Password",
    "login.password.placeholder": "••••••••",
    "login.submit": "Access Console",
    "setup.title": "Run Setup",
    "setup.desc": "Choose a workflow, attach inputs, and launch the job.",
    "setup.prompt.placeholder": "Optional notes or questions for this run.",
    "setup.check": "Check Setup",
    "setup.reset": "Reset Inputs",
    "setup.clear": "Clear Log",
    "setup.hint": "Complete required inputs to enable execution.",
    "setup.runStatus.empty": "Run status: -",
    "setup.runStatus.line": "Run status: {id} · {stage} / {state} · {updated}",
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
    "monitor.stage": "Stage",
    "monitor.state": "State",
    "monitor.updated": "Updated",
    "monitor.scoring": "Scoring",
    "monitor.poll": "Poll Now",
    "monitor.autoPoll": "Auto Poll",
    "monitor.recentRuns": "Recent Runs",
    "monitor.refreshRuns": "Refresh",
    "monitor.showAll": "Show all runs (admin)",
    "agent.title": "Agent Panel",
    "agent.desc": "Stage-by-stage expert consensus and recovery notes.",
    "agent.refresh": "Refresh",
    "agent.viewReport": "View Report",
    "agent.viewReportKo": "View Report (KO)",
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
    "artifacts.preview.title": "Artifact Preview",
    "artifacts.preview.desc": "3D structures, images, or text extracts.",
    "artifacts.preview.placeholder": "Select an artifact to preview it here.",
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
    "question.stopAfter.help": "Where to stop? (msa/design/soluprot/af2/novelty)",
    "question.designChains.label": "Design Chains",
    "question.designChains.help": "Which chains to design? (default: all)",
    "question.wtCompare.label": "WT Compare",
    "question.wtCompare.help": "Compute WT baseline (SoluProt/AF2) and compare in report.",
    "question.maskConsensusApply.label": "Apply Mask Consensus",
    "question.maskConsensusApply.help": "Apply expert mask consensus to ProteinMPNN (optional).",
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
    "hint.none": "No missing inputs. You can run now.",
    "hint.ready": "All required inputs captured.",
    "hint.missing": "Missing required inputs.",
    "run.reset": "Inputs reset. Reconfirm selections and attachments.",
    "runmode.pipeline": "Full Pipeline",
    "runmode.rfd3": "RFD3 (Backbone)",
    "runmode.msa": "MSA (MMseqs2)",
    "runmode.design": "ProteinMPNN",
    "runmode.soluprot": "SoluProt",
    "runmode.af2": "AlphaFold2",
    "runmode.diffdock": "DiffDock",
    "stop.full": "Full (Novelty)",
    "stage.msa": "MSA",
    "stage.design": "Design",
    "stage.soluprot": "SoluProt",
    "stage.af2": "AlphaFold2",
    "run.label.pipeline": "Run Pipeline",
    "run.label.rfd3": "Run RFD3",
    "run.label.msa": "Run MSA",
    "run.label.design": "Run ProteinMPNN",
    "run.label.soluprot": "Run SoluProt",
    "run.label.af2": "Run AlphaFold2",
    "run.label.diffdock": "Run DiffDock",
    "mode.pipeline": "pipeline",
    "mode.rfd3": "RFD3",
    "mode.msa": "MSA",
    "mode.design": "ProteinMPNN",
    "mode.soluprot": "SoluProt",
    "mode.af2": "AlphaFold2",
    "mode.diffdock": "DiffDock",
    "run.launching": "Launching {mode} run {id}...",
    "run.started": "Run started: {id}",
    "run.failed": "Run failed: {error}",
    "status.line": "Status: {stage} / {state}",
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
    "login.title": "랩 입장",
    "login.desc": "실행을 구분하고 아티팩트를 정리하기 위해 계정을 확인합니다.",
    "login.username": "사용자명",
    "login.username.placeholder": "예: hana.kim",
    "login.password": "비밀번호",
    "login.password.placeholder": "••••••••",
    "login.submit": "콘솔 접속",
    "setup.title": "실행 설정",
    "setup.desc": "워크플로를 선택하고 입력을 첨부해 실행하세요.",
    "setup.prompt.placeholder": "선택: 실행 메모/질문을 남기세요.",
    "setup.check": "설정 점검",
    "setup.reset": "입력 초기화",
    "setup.clear": "로그 지우기",
    "setup.hint": "필수 입력을 완료하면 실행할 수 있습니다.",
    "setup.runStatus.empty": "실행 상태: -",
    "setup.runStatus.line": "실행 상태: {id} · {stage} / {state} · {updated}",
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
    "monitor.stage": "단계",
    "monitor.state": "상태",
    "monitor.updated": "업데이트",
    "monitor.scoring": "점수",
    "monitor.poll": "지금 조회",
    "monitor.autoPoll": "자동 조회",
    "monitor.recentRuns": "최근 실행",
    "monitor.refreshRuns": "새로고침",
    "monitor.showAll": "모든 실행 보기 (관리자)",
    "agent.title": "에이전트 패널",
    "agent.desc": "단계별 전문가 합의와 복구 기록을 확인합니다.",
    "agent.refresh": "새로고침",
    "agent.viewReport": "리포트 보기",
    "agent.viewAgentReport": "에이전트 리포트",
    "agent.report.loading": "리포트를 불러오는 중...",
    "agent.report.missing": "아직 리포트가 없습니다.",
    "agent.report.failed": "리포트 로드 실패: {error}",
    "agent.viewReportKo": "리포트 보기 (KO)",
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
    "artifacts.preview.title": "아티팩트 미리보기",
    "artifacts.preview.desc": "3D 구조, 이미지, 텍스트 미리보기.",
    "artifacts.preview.placeholder": "아티팩트를 선택하면 여기서 미리보기를 볼 수 있습니다.",
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
    "question.stopAfter.help": "어디까지 실행할까요? (msa/design/soluprot/af2/novelty)",
    "question.designChains.label": "디자인 체인",
    "question.designChains.help": "디자인할 체인을 선택하세요. (기본: 전체)",
    "question.wtCompare.label": "WT 비교",
    "question.wtCompare.help": "WT 기준(SoluProt/AF2)을 계산해 리포트에 비교합니다.",
    "question.maskConsensusApply.label": "합의 마스킹 적용",
    "question.maskConsensusApply.help": "전문가 합의 마스킹을 ProteinMPNN에 적용합니다.",
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
    "hint.none": "누락된 입력이 없습니다. 지금 실행할 수 있습니다.",
    "hint.ready": "필수 입력이 모두 완료되었습니다.",
    "hint.missing": "필수 입력이 누락되었습니다.",
    "run.reset": "입력을 초기화했습니다. 선택과 첨부를 다시 확인하세요.",
    "runmode.pipeline": "전체 파이프라인",
    "runmode.rfd3": "RFD3 (Backbone)",
    "runmode.msa": "MSA (MMseqs2)",
    "runmode.design": "ProteinMPNN",
    "runmode.soluprot": "SoluProt",
    "runmode.af2": "AlphaFold2",
    "runmode.diffdock": "DiffDock",
    "stop.full": "전체 (Novelty)",
    "stage.msa": "MSA",
    "stage.design": "디자인",
    "stage.soluprot": "SoluProt",
    "stage.af2": "AlphaFold2",
    "run.label.pipeline": "파이프라인 실행",
    "run.label.rfd3": "RFD3 실행",
    "run.label.msa": "MSA 실행",
    "run.label.design": "ProteinMPNN 실행",
    "run.label.soluprot": "SoluProt 실행",
    "run.label.af2": "AlphaFold2 실행",
    "run.label.diffdock": "DiffDock 실행",
    "mode.pipeline": "파이프라인",
    "mode.rfd3": "RFD3",
    "mode.msa": "MSA",
    "mode.design": "ProteinMPNN",
    "mode.soluprot": "SoluProt",
    "mode.af2": "AlphaFold2",
    "mode.diffdock": "DiffDock",
    "run.launching": "{mode} 실행 {id} 시작...",
    "run.started": "실행 시작: {id}",
    "run.failed": "실행 실패: {error}",
    "status.line": "상태: {stage} / {state}",
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
  { labelKey: "runmode.msa", value: "msa" },
  { labelKey: "runmode.design", value: "design" },
  { labelKey: "runmode.soluprot", value: "soluprot" },
  { labelKey: "runmode.af2", value: "af2" },
  { labelKey: "runmode.diffdock", value: "diffdock" },
];

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
  renderArtifacts(state.artifacts);
  if (state.runs) renderRuns(state.runs);
  updateReportArtifactLinks(el.reportContent ? el.reportContent.value : "");
  updateReportScore(state.lastScore || {});
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
        default: false,
      },
      {
        id: "mask_consensus_apply",
        labelKey: "question.maskConsensusApply.label",
        questionKey: "question.maskConsensusApply.help",
        required: false,
        default: false,
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
        id: "pdb_strip_nonpositive_resseq",
        labelKey: "question.stripNonpositive.label",
        questionKey: "question.stripNonpositive.help",
        required: false,
        default: true,
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

function updateRunInfo(status) {
  if (!status) return;
  el.runStageValue.textContent = status.stage || "-";
  el.runStateValue.textContent = status.state || "-";
  el.runUpdatedValue.textContent = status.updated_at || "-";
  updateInlineStatus(status);
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
  state.lastStatusKey = "";
  el.runIdValue.textContent = runId || "-";
  updateInlineStatus(null, runId);
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
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const payload = await res.json();
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

function parsePdbChainRanges(pdbText) {
  const proteinResnames = new Set([
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
  const ranges = {};
  const lines = String(pdbText || "").split(/\r?\n/);
  for (const line of lines) {
    if (line.startsWith("ATOM")) {
      // ok
    } else if (line.startsWith("HETATM")) {
      const resname = line.slice(17, 20).trim().toUpperCase();
      if (!proteinResnames.has(resname)) continue;
    } else {
      continue;
    }
    const chainId = (line[21] || "").trim() || "_";
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

function updateChainRangesFromText(text) {
  const ranges = parsePdbChainRanges(text);
  state.chainRanges = ranges;
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
  el.questionStack.innerHTML = "";
  if (!questions.length) {
    el.runBtn.disabled = false;
    el.runHint.textContent = t("hint.none");
    return;
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
    "stop_after",
    "design_chains",
    "rfd3_contig",
    "pdb_strip_nonpositive_resseq",
    "wt_compare",
    "mask_consensus_apply",
  ]);

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
          { labelKey: "stage.msa", value: "msa" },
          { labelKey: "stage.design", value: "design" },
          { labelKey: "stage.soluprot", value: "soluprot" },
          { labelKey: "stage.af2", value: "af2" },
          { labelKey: "stop.full", value: "novelty" },
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
      allBtn.textContent = t("choice.allChains");
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
        current = q.default !== undefined ? Boolean(q.default) : true;
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
          updateRunEligibility(questions);
        }
      );
    }

    if (q.id === "wt_compare") {
      let current = state.answers.wt_compare;
      if (typeof current !== "boolean") {
        current = q.default !== undefined ? Boolean(q.default) : false;
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
          updateRunEligibility(questions);
        }
      );
    }

    if (q.id === "mask_consensus_apply") {
      let current = state.answers.mask_consensus_apply;
      if (typeof current !== "boolean") {
        current = q.default !== undefined ? Boolean(q.default) : false;
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
          updateRunEligibility(questions);
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
          updateRunEligibility(questions);
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

    el.questionStack.appendChild(card);
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
      clearBtn.textContent = t("attachment.clear");

      fileInput.addEventListener("change", async (event) => {
        const file = event.target.files?.[0];
        if (!file) {
          state.answers[q.id] = "";
          state.answerMeta[q.id] = {};
          fileName.textContent = t("attachment.none");
          meta.textContent = t("attachment.none");
          updateRunEligibility(questions);
          return;
        }
        try {
          const text = await file.text();
          state.answers[q.id] = text;
          state.answerMeta[q.id] = { fileName: file.name };
          const kb = Math.max(1, Math.round(file.size / 1024));
          fileName.textContent = file.name;
          meta.textContent = t("attachment.attached", { name: file.name, kb });
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
          fileName.textContent = t("attachment.none");
          meta.textContent = t("attachment.failed", { error: err.message });
        }
        updateRunEligibility(questions);
      });

      clearBtn.addEventListener("click", () => {
        fileInput.value = "";
        state.answers[q.id] = "";
        state.answerMeta[q.id] = {};
        fileName.textContent = t("attachment.none");
        meta.textContent = t("attachment.none");
        if (q.id === "target_input" || q.id === "rfd3_input_pdb") {
          state.chainRanges = null;
        }
        if (q.id === "rfd3_input_pdb" && state.runMode === "pipeline") {
          state.answers.rfd3_contig = "";
        }
        updateRunEligibility(questions);
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
    el.runHint.textContent = t("hint.ready");
  } else {
    el.runBtn.disabled = true;
    el.runHint.textContent = t("hint.missing");
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
      "diffdock_ligand_smiles",
      "diffdock_ligand_sdf",
      "design_chains",
      "pdb_strip_nonpositive_resseq",
      "wt_compare",
      "mask_consensus_apply",
      "stop_after",
    ],
    rfd3: ["rfd3_input_pdb", "rfd3_contig", "pdb_strip_nonpositive_resseq"],
    msa: ["target_fasta", "target_pdb", "pdb_strip_nonpositive_resseq"],
    design: ["target_fasta", "target_pdb", "design_chains", "pdb_strip_nonpositive_resseq"],
    soluprot: ["target_fasta", "target_pdb", "design_chains", "pdb_strip_nonpositive_resseq"],
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
  if (mode === "msa") return { stop_after: "msa" };
  if (mode === "design") return { stop_after: "design" };
  if (mode === "soluprot") return { stop_after: "soluprot" };
  if (mode === "af2") return { stop_after: "af2" };
  return state.plan?.routed_request || {};
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

async function runPreflight({ announce = true } = {}) {
  const prompt = el.promptInput.value.trim();
  const mode = state.runMode || "pipeline";
  const preflightModes = new Set(["pipeline", "rfd3", "msa", "design", "soluprot"]);
  if (!preflightModes.has(mode)) {
    if (announce) {
      setMessage(t("preflight.unavailable", { mode: t(`mode.${mode}`) || mode }), "ai");
    }
    return { ok: false, preflight: null, plan: null };
  }
  const rawAnswers = buildAnswerPayload(mode);
  const answers = filterAnswersForMode(mode, rawAnswers);
  const routed = buildRoutedForMode(mode);
  const args = buildRunArguments({
    prompt,
    routed,
    answers,
    runId: "",
  });
  delete args.run_id;

  if (announce && prompt) {
    setMessage(prompt, "user");
  }

  let preflight = null;
  let plan = null;
  try {
    preflight = await apiCall("pipeline.preflight", args);
  } catch (err) {
    if (announce) {
      setMessage(t("preflight.failed", { error: err.message }), "ai");
    }
    return { ok: false, preflight: null, plan: null };
  }

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
    const warnBlock = _formatList(t("preflight.warnings"), preflight.warnings || []);
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
  if (!state.plan) return;
  const prompt = el.promptInput.value.trim();
  const prefix = state.user?.run_prefix || buildUserPrefix({ name: state.user?.username || "user" });
  const runId = createRunId(prefix);
  const mode = state.runMode || "pipeline";
  const rawAnswers = buildAnswerPayload(mode);
  const answers = filterAnswersForMode(mode, rawAnswers);
  let args = {};
  let toolName = "pipeline.run";

  if (["pipeline", "rfd3", "msa", "design", "soluprot"].includes(mode)) {
    const pre = await runPreflight({ announce: true });
    if (!pre.ok) {
      return;
    }
  }

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

  const modeLabel = t(`mode.${mode}`) || mode;
  setMessage(t("run.launching", { mode: modeLabel, id: runId }), "ai");
  setCurrentRunId(runId);

  try {
    const result = await apiCall(toolName, args);
    setMessage(t("run.started", { id: result.run_id }), "ai");
    setCurrentRunId(result.run_id);
    await refreshRuns();
    ensureAutoPoll();
    await pollStatus(result.run_id);
  } catch (err) {
    setMessage(t("run.failed", { error: err.message }), "ai");
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
      setMessage(t("status.line", { stage, state: stateText }), "ai");
    }
  } catch (err) {
    setMessage(t("status.error", { error: err.message }), "ai");
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
    el.artifactList.innerHTML = `<div class="placeholder">${t("artifact.none")}</div>`;
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
    renderArtifacts(state.artifacts);
    refreshArtifactSelects();
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
  const title = lang === "ko" ? t("agent.viewReportKo") : t("agent.viewReport");
  const filename = lang === "ko" ? "report_ko.md" : "report.md";
  openReportModal(title, t("agent.report.loading"));
  try {
    let text = "";
    if (lang === "ko") {
      const result = await apiCall("pipeline.read_artifact", {
        run_id: state.currentRunId,
        path: "report_ko.md",
        max_bytes: 2_000_000,
      });
      text = result?.text || "";
    } else {
      const result = await apiCall("pipeline.get_report", { run_id: state.currentRunId });
      text = result?.report || "";
    }
    if (!text.trim()) {
      openReportModal(title, t("agent.report.missing"));
      return;
    }
    openReportModal(title, text, filename);
  } catch (err) {
    openReportModal(title, t("agent.report.failed", { error: err.message }));
  }
}

async function loadAgentReportModal() {
  if (!state.currentRunId) {
    setMessage(t("agent.report.missing"), "ai");
    return;
  }
  openReportModal(t("agent.viewAgentReport"), t("agent.report.loading"));
  try {
    const result = await apiCall("pipeline.read_artifact", {
      run_id: state.currentRunId,
      path: "agent_panel_report.md",
      max_bytes: 2_000_000,
    });
    const text = result?.text || "";
    if (!text.trim()) {
      openReportModal(t("agent.viewAgentReport"), t("agent.report.missing"));
      return;
    }
    openReportModal(t("agent.viewAgentReport"), text, "agent_panel_report.md");
  } catch (err) {
    openReportModal(t("agent.viewAgentReport"), t("agent.report.failed", { error: err.message }));
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
      limit: 5,
    });
    const items = result.items || [];
    if (!items.length) {
      el.feedbackList.innerHTML = `<div class="placeholder">${t("feedback.none")}</div>`;
      return;
    }
    el.feedbackList.innerHTML = "";
    items.forEach((item) => {
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
      limit: 5,
    });
    const items = result.items || [];
    if (!items.length) {
      el.experimentList.innerHTML = `<div class="placeholder">${t("experiment.none")}</div>`;
      return;
    }
    el.experimentList.innerHTML = "";
    items.forEach((item) => {
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

function updateReportScore(result) {
  if (!el.reportScoreValue || !el.reportEvidenceValue || !el.reportRecommendationValue) return;
  const { score, evidence, recommendation } = formatScoreValues(result);
  state.lastScore = { score, evidence, recommendation };
  el.reportScoreValue.textContent = `${t("common.score")}: ${score}`;
  el.reportEvidenceValue.textContent = `${t("common.evidence")}: ${evidence}`;
  el.reportRecommendationValue.textContent = `${t("common.recommendation")}: ${recommendation}`;
  updateRunScore(result);
}

async function loadReport() {
  if (!state.currentRunId || !el.reportContent) return;
  try {
    const result = await apiCall("pipeline.get_report", { run_id: state.currentRunId });
    el.reportContent.value = result.report || "";
    updateReportScore(result);
    updateReportArtifactLinks(result.report || "");
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

function renderRuns(runs) {
  el.runList.innerHTML = "";
  if (!runs.length) {
    el.runList.innerHTML = `<div class="placeholder">${t("runs.none")}</div>`;
    return;
  }
  runs.forEach((runId) => {
    const div = document.createElement("div");
    div.className = "run-item";
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
  el.messages.innerHTML = "";
  resetPlan();
});

el.runBtn.addEventListener("click", runPipeline);

if (el.viewRunReport) {
  el.viewRunReport.addEventListener("click", loadRunReportModal);
}

if (el.viewRunReportKo) {
  el.viewRunReportKo.addEventListener("click", () => loadRunReportModal({ lang: "ko" }));
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

if (el.refreshRunsBtn) {
  el.refreshRunsBtn.addEventListener("click", () => {
    refreshRuns();
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

if (el.settingsBtn && el.settingsPanel) {
  el.settingsBtn.addEventListener("click", () => {
    el.settingsPanel.classList.remove("hidden");
    if (el.apiBaseValue) {
      el.apiBaseValue.textContent = state.apiBase;
    }
  });
}

if (el.settingsClose && el.settingsPanel) {
  el.settingsClose.addEventListener("click", () => {
    el.settingsPanel.classList.add("hidden");
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
ensureAutoPoll();
