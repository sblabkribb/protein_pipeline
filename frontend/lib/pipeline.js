const STAGE_ORDER = ["msa", "rfd3", "bioemu", "design", "soluprot", "af2", "novelty"];

function normalizeStage(value) {
  let raw = String(value || "")
    .trim()
    .toLowerCase();
  raw = raw.replace(/[\s-]+/g, "_");
  if (raw === "wt_diff" || raw === "wtdiff") raw = "novelty";
  if (!raw) return "";
  return STAGE_ORDER.includes(raw) ? raw : "";
}

function hasMeaningfulValue(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "boolean") return value === true;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return false;
}

export function sanitizeName(input) {
  return String(input || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "_")
    .replace(/^[_\-.]+|[_\-.]+$/g, "")
    .slice(0, 32);
}

export function buildUserPrefix(profile) {
  const base = sanitizeName(profile?.name || "user");
  const org = sanitizeName(profile?.org || "");
  const token = org ? `${org}_${base}` : base;
  return token || "user";
}

export function createRunId(prefix, now = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  const ts = `${now.getUTCFullYear()}${pad(now.getUTCMonth() + 1)}${pad(
    now.getUTCDate()
  )}_${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}${pad(now.getUTCSeconds())}`;
  const rand = Math.random().toString(16).slice(2, 10);
  const safePrefix = sanitizeName(prefix || "pipeline") || "pipeline";
  return `${safePrefix}_${ts}_${rand}`;
}

function normalizeArtifactPath(path) {
  return String(path || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/+/g, "/")
    .toLowerCase();
}

function matchPath(path, pattern) {
  return pattern.test(path);
}

function isLegacyRfd3Id(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase();
  const cleaned = raw.replace(/\.[a-z0-9.]+$/i, "");
  return (
    /^inputs[_-]/.test(cleaned) &&
    (/^inputs[_-]spec(?:[_-]|$)/.test(cleaned) || /(?:^|[_-])model[_-]\d+(?::\d+)?$/.test(cleaned))
  );
}

export function displayRfd3Id(value) {
  const raw = String(value || "");
  if (!raw || !isLegacyRfd3Id(raw)) return raw;
  const trimmed = raw.replace(/^inputs[_-]*/i, "").replace(/^[_-]+/, "");
  return trimmed ? `rfd3_${trimmed}` : "rfd3";
}

export function displayArtifactPath(path) {
  return String(path || "")
    .split(/([/\\])/)
    .map((part) => (part === "/" || part === "\\" ? part : displayRfd3Id(part)))
    .join("");
}

function backboneSourceFromId(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase();
  if (!raw) return "";
  if (/bioemu/.test(raw)) return "bioemu";
  if (isLegacyRfd3Id(raw) || /(?:^|[_-])rfd3(?:[_-]|$)/.test(raw)) return "rfd3";
  return "";
}

function backboneIdFromPath(normalizedPath) {
  const normalized = String(normalizedPath || "");
  const backboneMatch = normalized.match(/(?:^|\/)backbones\/([^/]+)/);
  if (backboneMatch) return backboneMatch[1];

  const stageDesignMatch = normalized.match(/(?:^|\/)(?:rfd3|bioemu)\/designs\/([^/]+)\.pdb$/);
  if (stageDesignMatch) return stageDesignMatch[1];

  const af2RankedMatch = normalized.match(/(?:^|\/)tiers\/[^/]+\/af2\/([^/]+)\/ranked_\d+\.pdb$/);
  if (af2RankedMatch) {
    return af2RankedMatch[1].replace(/_\d+$/, "");
  }
  return "";
}

export function artifactMetaFromPath(path) {
  const normalized = normalizeArtifactPath(path);
  const tierMatch = normalized.match(/(?:^|\/)tiers\/([^/]+)/);
  const tier = tierMatch ? tierMatch[1] : null;
  const backboneId = backboneIdFromPath(normalized);
  const isBioemuBackbone = backboneId ? /bioemu/.test(backboneId) : false;
  const isRfd3Backbone = backboneId ? /(?:^|[_-])inputs?_spec(?:[_-]|$)|(?:^|[_-])rfd3(?:[_-]|$)/.test(backboneId) : false;
  const backboneSource = backboneSourceFromId(backboneId);
  const isRootInputReference = normalized === "target.original.pdb";
  const isRootWorkingBackbone = normalized === "target.pdb";
  const isWtColabfold = normalized === "wt/af2/ranked_0.pdb";
  const isBackboneSnapshot = /(?:^|\/)backbones\/[^/]+\/target\.pdb$/i.test(normalized);
  const isBackboneInputSnapshot = /(?:^|\/)backbones\/[^/]+\/target\.original\.pdb$/i.test(normalized);
  const isAf2Candidate = /(?:^|\/)tiers\/[^/]+\/af2\/[^/]+\/ranked_\d+\.pdb$/i.test(normalized);
  const isSourceOutput = /(?:^|\/)(?:rfd3|bioemu)\/designs\/[^/]+\.pdb$/i.test(normalized);

  let stage = "misc";
  if (isRootInputReference) {
    stage = "input_reference";
  } else if (isRootWorkingBackbone) {
    stage = "working_backbone";
  } else if (isWtColabfold) {
    stage = "wt_af2";
  } else if (
    matchPath(normalized, /(?:^|\/)mask_consensus(?:\/|$)/) ||
    normalized.includes("mask_consensus")
  ) {
    stage = "mask_consensus";
  } else if (
    matchPath(normalized, /(?:^|\/)surface_mask(?:\/|$)/) ||
    normalized.includes("surface_mask")
  ) {
    stage = "surface_mask";
  } else if (
    matchPath(normalized, /(?:^|\/)ligand_mask(?:\/|$)/) ||
    normalized.includes("ligand_mask")
  ) {
    stage = "ligand_mask";
  } else if (
    matchPath(normalized, /(?:^|\/)conservation(?:\/|$)/) ||
    normalized.includes("conservation")
  ) {
    stage = "conservation";
  } else if (
    matchPath(normalized, /(?:^|\/)pdb_preprocess(?:\/|$)/) ||
    normalized.includes("pdb_preprocess")
  ) {
    stage = "pdb_preprocess";
  } else if (
    matchPath(normalized, /(?:^|\/)query_pdb(?:_check)?(?:\/|$)/) ||
    normalized.includes("query_pdb")
  ) {
    stage = "query_pdb_check";
  } else if (matchPath(normalized, /(?:^|\/)agent_panel(?:\/|$)/)) {
    stage = "agent";
  } else if (matchPath(normalized, /(?:^|\/)wt(?:\/|$)/)) {
    stage = "wt";
  } else if (isRfd3Backbone || matchPath(normalized, /(?:^|\/)(?:rfd3|rfdiffusion)(?:\/|$)/)) {
    stage = "rfd3";
  } else if (isBioemuBackbone || matchPath(normalized, /(?:^|\/)bioemu(?:\/|$)/)) {
    stage = "bioemu";
  } else if (
    matchPath(normalized, /(?:^|\/)af2_target(?:\/|$)/) ||
    normalized.endsWith("/target.pdb") ||
    normalized === "target.pdb"
  ) {
    stage = "af2_target";
  } else if (matchPath(normalized, /(?:^|\/)diffdock(?:\/|$)/)) {
    stage = "diffdock";
  } else if (matchPath(normalized, /(?:^|\/)(?:af2|alphafold2?|alphafold|colabfold)(?:\/|$)/)) {
    stage = "af2";
  } else if (matchPath(normalized, /(?:^|\/)soluprot(?:\/|$)/) || normalized.includes("soluprot")) {
    stage = "soluprot";
  } else if (
    matchPath(normalized, /(?:^|\/)(?:designs?|proteinmpnn|mpnn)(?:\/|$)/) ||
    normalized.includes("proteinmpnn")
  ) {
    stage = "design";
  } else if (
    matchPath(normalized, /(?:^|\/)(?:msa|mmseqs|a3m)(?:\/|$)/) ||
    normalized.includes("mmseq")
  ) {
    stage = "msa";
  } else if (
    matchPath(normalized, /(?:^|\/)(?:novelty|novel)(?:\/|$)/) ||
    normalized.includes("novelty")
  ) {
    stage = "novelty";
  }

  let source = "other";
  if (stage === "wt") source = "wt";
  else if (stage === "rfd3") source = "rfd3";
  else if (stage === "bioemu") source = "bioemu";
  else if (tier) source = "tier";

  let compareRole = "structure_artifact";
  let compareGroup = "other";
  if (isRootInputReference) {
    compareRole = "input_reference";
    compareGroup = "references";
  } else if (isRootWorkingBackbone) {
    compareRole = "working_backbone";
    compareGroup = "references";
  } else if (isWtColabfold) {
    compareRole = "wt_colabfold";
    compareGroup = "references";
  } else if (isBackboneSnapshot) {
    compareRole = "backbone_snapshot";
    compareGroup = "backbones";
  } else if (isAf2Candidate) {
    compareRole = "af2_candidate";
    compareGroup = "af2_candidates";
  } else if (isSourceOutput) {
    compareRole = "source_output";
    compareGroup = "source_outputs";
  } else if (isBackboneInputSnapshot) {
    compareRole = "backbone_input_snapshot";
    compareGroup = "internal";
  }

  return {
    path: String(path || ""),
    normalizedPath: normalized,
    tier,
    stage,
    source,
    backboneId,
    backboneSource,
    compareRole,
    compareGroup,
  };
}

export function stageFromPath(path) {
  return artifactMetaFromPath(path).stage;
}

export function isBinaryPath(path) {
  return /\.(gz|zip|npy|npz|pt|bin)$/i.test(
    String(path || "")
  );
}

export function isImagePath(path) {
  return /\.(png|jpg|jpeg|gif|svg)$/i.test(String(path || ""));
}

export function mergeRunInputs(answers) {
  const payload = {};
  for (const [key, value] of Object.entries(answers || {})) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string" && value.trim() === "") continue;
    payload[key] = value;
  }
  return payload;
}

export function buildRunArguments({ prompt, routed, answers, runId }) {
  const args = {
    prompt,
    run_id: runId,
    ...routed,
    ...mergeRunInputs(answers),
  };
  const startFrom = normalizeStage(args.start_from);
  const stopAfter = normalizeStage(args.stop_after);
  if (startFrom && startFrom !== "msa") args.start_from = startFrom;
  else delete args.start_from;
  if (stopAfter) args.stop_after = stopAfter;
  else delete args.stop_after;

  if (startFrom && stopAfter) {
    if (STAGE_ORDER.indexOf(startFrom) > STAGE_ORDER.indexOf(stopAfter)) {
      args.stop_after = startFrom;
    }
  }

  const normalizedStopAfter = normalizeStage(args.stop_after);
  if (normalizedStopAfter === "novelty") {
    args.novelty_enabled = true;
  } else if (args.novelty_enabled === true && !normalizedStopAfter) {
    args.stop_after = "novelty";
  }
  delete args.questions;
  delete args.missing;
  return args;
}

const WORKFLOW_STUDIO_STAGE_FIELDS = Object.freeze({
  msa: Object.freeze(["target_input", "pdb_strip_nonpositive_resseq"]),
  rfd3: Object.freeze(["rfd3_input_pdb", "rfd3_contig", "rfd3_max_return_designs"]),
  bioemu: Object.freeze(["bioemu_use", "bioemu_num_samples", "bioemu_max_return_structures"]),
  design: Object.freeze([
    "design_chains",
    "fixed_positions_extra",
    "num_seq_per_tier",
    "mask_consensus_apply",
    "ligand_mask_use_original_target",
  ]),
  soluprot: Object.freeze(["soluprot_cutoff"]),
  af2: Object.freeze(["af2_provider", "af2_max_candidates_per_tier", "af2_plddt_cutoff", "af2_rmsd_cutoff"]),
  novelty: Object.freeze(["novelty_enabled", "wt_compare"]),
});

const WORKFLOW_STUDIO_IGNORED_FIELDS = new Set([
  "run_mode",
  "start_from",
  "stop_after",
  "confirm_run",
  "questions",
  "missing",
]);

const WORKFLOW_STUDIO_FIELD_STAGE = Object.freeze(
  Object.fromEntries(
    Object.entries(WORKFLOW_STUDIO_STAGE_FIELDS).flatMap(([stage, fields]) =>
      fields.map((fieldId) => [fieldId, stage])
    )
  )
);

const WORKFLOW_STUDIO_EXISTING_OUTPUT_REQUIREMENTS = Object.freeze({
  soluprot: Object.freeze({
    satisfiedByStartFrom: "design",
    upstreamStage: "design",
    code: "design_outputs_missing",
    minSize: 1,
    pathPatterns: Object.freeze([
      /(?:^|\/)tiers\/[^/]+\/proteinmpnn\.json$/i,
      /(?:^|\/)tiers\/[^/]+\/designs(?:_pi_filtered)?\.fasta$/i,
    ]),
  }),
  af2: Object.freeze({
    satisfiedByStartFrom: "soluprot",
    upstreamStage: "soluprot",
    code: "soluprot_passed_missing",
    minSize: 1,
    pathPatterns: Object.freeze([/(?:^|\/)tiers\/[^/]+\/designs_filtered\.fasta$/i]),
  }),
  novelty: Object.freeze({
    satisfiedByStartFrom: "af2",
    upstreamStage: "af2",
    code: "af2_selected_missing",
    minSize: 1,
    pathPatterns: Object.freeze([/(?:^|\/)tiers\/[^/]+\/af2_selected\.fasta$/i]),
  }),
});

function stageIndex(stage) {
  const normalized = normalizeStage(stage);
  return normalized ? STAGE_ORDER.indexOf(normalized) : -1;
}

function cloneWorkflowValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => cloneWorkflowValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, cloneWorkflowValue(item)])
    );
  }
  return value;
}

function workflowValuesEqual(a, b) {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((item, idx) => workflowValuesEqual(item, b[idx]));
  }
  if (a && typeof a === "object") {
    if (!b || typeof b !== "object" || Array.isArray(b)) return false;
    const aKeys = Object.keys(a).sort();
    const bKeys = Object.keys(b).sort();
    if (!workflowValuesEqual(aKeys, bKeys)) return false;
    return aKeys.every((key) => workflowValuesEqual(a[key], b[key]));
  }
  if (b && typeof b === "object") return false;
  return false;
}

function workflowValueIsAbsent(value) {
  if (value === undefined || value === null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0 || value.every((item) => workflowValueIsAbsent(item));
  if (value && typeof value === "object") return Object.keys(value).length === 0;
  return false;
}

function workflowStageOrderForNodes(nodes) {
  const normalized = new Set(
    (Array.isArray(nodes) ? nodes : [])
      .map((stage) => normalizeStage(stage))
      .filter(Boolean)
  );
  return normalized.size ? STAGE_ORDER.filter((stage) => normalized.has(stage)) : [...STAGE_ORDER];
}

export function createWorkflowSessionId(prefix, now = new Date()) {
  const safePrefix = sanitizeName(prefix || "workflow") || "workflow";
  return createRunId(`${safePrefix}_studio`, now);
}

export function workflowStudioStageFields(stage) {
  const normalized = normalizeStage(stage);
  return normalized ? [...(WORKFLOW_STUDIO_STAGE_FIELDS[normalized] || [])] : [];
}

export function splitWorkflowStudioAnswers(answers) {
  const baseAnswers = {};
  const stageDrafts = Object.fromEntries(STAGE_ORDER.map((stage) => [stage, {}]));
  const skipBaseKeys = new Set(WORKFLOW_STUDIO_IGNORED_FIELDS);
  if (String(answers?.target_input || "").trim()) {
    skipBaseKeys.add("target_pdb");
    skipBaseKeys.add("target_fasta");
  }
  Object.entries(answers || {}).forEach(([key, value]) => {
    if (value === undefined) return;
    const owner = WORKFLOW_STUDIO_FIELD_STAGE[key];
    if (owner) {
      stageDrafts[owner][key] = cloneWorkflowValue(value);
      return;
    }
    if (skipBaseKeys.has(key)) return;
    baseAnswers[key] = cloneWorkflowValue(value);
  });
  return { baseAnswers, stageDrafts };
}

export function mergeWorkflowStudioAnswers({ baseAnswers, stageDrafts, nodes } = {}) {
  const merged = {};
  Object.entries(baseAnswers || {}).forEach(([key, value]) => {
    if (value === undefined) return;
    merged[key] = cloneWorkflowValue(value);
  });
  workflowStageOrderForNodes(nodes).forEach((stage) => {
    Object.entries(stageDrafts?.[stage] || {}).forEach(([key, value]) => {
      if (value === undefined) return;
      merged[key] = cloneWorkflowValue(value);
    });
  });
  return merged;
}

export function buildWorkflowStudioEffectiveAnswers({ headRequest, baseAnswers, stageDrafts, nodes } = {}) {
  const inheritedDraft = buildSetupDraftFromRequest(
    headRequest && typeof headRequest === "object" && !Array.isArray(headRequest) ? headRequest : {}
  ).answers;
  const inheritedSplit = splitWorkflowStudioAnswers(inheritedDraft);
  const mergedBaseAnswers = {
    ...(inheritedSplit.baseAnswers || {}),
  };
  Object.entries(baseAnswers || {}).forEach(([key, value]) => {
    if (value === undefined) return;
    mergedBaseAnswers[key] = cloneWorkflowValue(value);
  });
  const mergedStageDrafts = Object.fromEntries(
    STAGE_ORDER.map((stage) => [
      stage,
      {
        ...(inheritedSplit.stageDrafts?.[stage] || {}),
        ...(stageDrafts?.[stage] || {}),
      },
    ])
  );
  return mergeWorkflowStudioAnswers({
    baseAnswers: mergedBaseAnswers,
    stageDrafts: mergedStageDrafts,
    nodes,
  });
}

export function workflowStudioChangedFields(previousPayload, nextPayload) {
  const previous = previousPayload && typeof previousPayload === "object" ? previousPayload : {};
  const next = nextPayload && typeof nextPayload === "object" ? nextPayload : {};
  const keys = new Set([...Object.keys(previous), ...Object.keys(next)]);
  const changed = [];
  Array.from(keys)
    .sort()
    .forEach((key) => {
      if (WORKFLOW_STUDIO_IGNORED_FIELDS.has(key)) return;
      if (workflowValueIsAbsent(previous[key]) && workflowValueIsAbsent(next[key])) return;
      if (!workflowValuesEqual(previous[key], next[key])) {
        changed.push(key);
      }
    });
  return changed;
}

export function minimumWorkflowStudioStartStage({ previousPayload, nextPayload, targetStage } = {}) {
  const target = normalizeStage(targetStage) || "msa";
  const changed = workflowStudioChangedFields(previousPayload, nextPayload);
  if (!changed.length) return target;
  let earliestIndex = STAGE_ORDER.indexOf(target);
  changed.forEach((key) => {
    const owner = WORKFLOW_STUDIO_FIELD_STAGE[key];
    const idx = owner ? STAGE_ORDER.indexOf(owner) : 0;
    if (idx >= 0 && idx < earliestIndex) {
      earliestIndex = idx;
    }
  });
  return STAGE_ORDER[earliestIndex] || target;
}

export function workflowStudioDependencyStatus({ targetStage, requiredStart, artifacts } = {}) {
  const target = normalizeStage(targetStage);
  const start = normalizeStage(requiredStart) || target;
  const requirement = target ? WORKFLOW_STUDIO_EXISTING_OUTPUT_REQUIREMENTS[target] || null : null;
  if (!target || !requirement) {
    return {
      required: false,
      blocked: false,
      code: "",
      upstreamStage: "",
      matchedPaths: [],
    };
  }

  const startIdx = stageIndex(start);
  const satisfyIdx = stageIndex(requirement.satisfiedByStartFrom);
  if (startIdx >= 0 && satisfyIdx >= 0 && startIdx <= satisfyIdx) {
    return {
      required: false,
      blocked: false,
      code: "",
      upstreamStage: requirement.upstreamStage,
      matchedPaths: [],
    };
  }

  const files = Array.isArray(artifacts)
    ? artifacts.filter((item) => item && item.type === "file" && String(item.path || "").trim())
    : [];
  const matchedPaths = files
    .filter((item) => {
      const normalizedPath = normalizeArtifactPath(item.path);
      const size = Number(item.size || 0);
      if (!Number.isFinite(size) || size < Number(requirement.minSize || 0)) return false;
      return requirement.pathPatterns.some((pattern) => pattern.test(normalizedPath));
    })
    .map((item) => String(item.path || ""));

  return {
    required: true,
    blocked: matchedPaths.length === 0,
    code: requirement.code,
    upstreamStage: requirement.upstreamStage,
    matchedPaths,
  };
}

export function nextWorkflowStudioStage(nodes, stage) {
  const order = workflowStageOrderForNodes(nodes);
  const normalized = normalizeStage(stage);
  if (!normalized) return order[0] || "";
  const idx = order.indexOf(normalized);
  if (idx < 0 || idx + 1 >= order.length) return "";
  return order[idx + 1];
}

function cloneSetupValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => cloneSetupValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, cloneSetupValue(item)])
    );
  }
  return value;
}

export function shouldReuseSelectedRun({ mode, startFrom, continueInSelectedRun, selectedRunId }) {
  const normalizedMode = String(mode || "").trim().toLowerCase();
  const normalizedStart = normalizeStage(startFrom);
  return Boolean(
    continueInSelectedRun &&
      String(selectedRunId || "").trim() &&
      (normalizedMode === "pipeline" || normalizedMode === "workflow") &&
      normalizedStart &&
      normalizedStart !== "msa"
  );
}

export function buildSetupDraftFromRequest(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { mode: "", answers: {}, answerMeta: {} };
  }

  const mode = inferRequestRunMode(payload) || "pipeline";
  const answers = {};
  const answerMeta = {};
  const skipKeys = new Set(["target_fasta", "target_pdb", "diffdock_ligand_sdf", "diffdock_ligand_smiles"]);

  Object.entries(payload).forEach(([key, value]) => {
    if (skipKeys.has(key)) return;
    if (value === undefined || value === null) return;
    if (typeof value === "string" && value.trim() === "") return;
    answers[key] = cloneSetupValue(value);
  });

  const targetPdb = String(payload.target_pdb || "");
  const targetFasta = String(payload.target_fasta || "");
  if (targetPdb.trim()) {
    answers.target_input = targetPdb;
    answers.target_pdb = targetPdb;
    if (targetFasta.trim()) answers.target_fasta = targetFasta;
    answerMeta.target_input = { fileName: "request.json:target_pdb" };
    answerMeta.target_pdb = { fileName: "request.json:target_pdb" };
  } else if (targetFasta.trim()) {
    answers.target_input = targetFasta;
    answers.target_fasta = targetFasta;
    answerMeta.target_input = { fileName: "request.json:target_fasta" };
  }

  const rfd3Input = String(payload.rfd3_input_pdb || "");
  if (rfd3Input.trim()) {
    answers.rfd3_input_pdb = rfd3Input;
    answerMeta.rfd3_input_pdb = { fileName: "request.json:rfd3_input_pdb" };
  }

  const ligandSdf = String(payload.diffdock_ligand_sdf || "");
  const ligandSmiles = String(payload.diffdock_ligand_smiles || "");
  if (ligandSdf.trim()) {
    answers.diffdock_ligand = ligandSdf;
    answerMeta.diffdock_ligand = { fileName: "request.json:diffdock_ligand.sdf" };
  } else if (ligandSmiles.trim()) {
    answers.diffdock_ligand = ligandSmiles;
    answerMeta.diffdock_ligand = { fileName: "request.json:diffdock_ligand.smiles" };
  }

  if (mode === "pipeline") {
    answers.diffdock_use = answers.diffdock_ligand ? "use" : "skip";
  } else if (mode === "diffdock" && answers.diffdock_ligand) {
    answers.diffdock_use = "use";
  }

  const normalizedStart = normalizeStage(answers.start_from);
  if (normalizedStart) {
    answers.start_from = normalizedStart;
  }
  const normalizedStop = normalizeStage(answers.stop_after);
  if (normalizedStop) {
    answers.stop_after = normalizedStop;
  }

  return { mode, answers, answerMeta };
}

export function inferRequestRunMode(payload) {
  if (!payload || typeof payload !== "object") return "";

  const stopAfter = normalizeStage(payload.stop_after);
  const isDiffdockRequest =
    hasMeaningfulValue(payload.protein_pdb) ||
    hasMeaningfulValue(payload.diffdock_ligand_smiles) ||
    hasMeaningfulValue(payload.diffdock_ligand_sdf);
  if (isDiffdockRequest) return "diffdock";

  const isPipelineLikeRequest =
    hasMeaningfulValue(payload.num_seq_per_tier) ||
    hasMeaningfulValue(payload.mmseqs_target_db) ||
    hasMeaningfulValue(payload.novelty_target_db) ||
    hasMeaningfulValue(payload.rfd3_max_return_designs) ||
    hasMeaningfulValue(payload.conservation_tiers) ||
    hasMeaningfulValue(payload.wt_compare) ||
    hasMeaningfulValue(payload.mask_consensus_apply) ||
    hasMeaningfulValue(payload.ligand_mask_use_original_target) ||
    hasMeaningfulValue(payload.af2_plddt_cutoff) ||
    hasMeaningfulValue(payload.af2_rmsd_cutoff) ||
    hasMeaningfulValue(payload.conservation_mode) ||
    hasMeaningfulValue(payload.conservation_weighting) ||
    hasMeaningfulValue(payload.surface_only);

  if (stopAfter === "novelty") return "pipeline";
  if (stopAfter === "msa") return "msa";
  if (stopAfter === "rfd3") return "rfd3";
  if (stopAfter === "bioemu") return "bioemu";
  if (stopAfter === "design") return isPipelineLikeRequest ? "pipeline" : "design";
  if (stopAfter === "soluprot") return isPipelineLikeRequest ? "pipeline" : "soluprot";
  if (stopAfter === "af2") return isPipelineLikeRequest ? "pipeline" : "af2";
  if (isPipelineLikeRequest) return "pipeline";

  const isAf2Request =
    (hasMeaningfulValue(payload.af2_model_preset) && hasMeaningfulValue(payload.af2_db_preset)) ||
    hasMeaningfulValue(payload.af2_provider);
  if (isAf2Request) return "af2";

  return "";
}

export function filterRunsByPrefix(runs, prefix) {
  const safe = sanitizeName(prefix || "");
  if (!safe) return runs || [];
  return (runs || []).filter((run) => String(run).startsWith(`${safe}_`));
}

export function detectTargetKey(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return null;
  const firstLine = trimmed.split(/\r?\n/, 1)[0] || "";
  if (firstLine.startsWith(">")) return "target_fasta";
  if (/^(ATOM|HETATM)\b/.test(firstLine)) return "target_pdb";
  const lettersOnly = trimmed.replace(/\s+/g, "");
  if (/^[A-Za-z*.-]+$/.test(lettersOnly) && lettersOnly.length > 0) {
    return "target_fasta";
  }
  return "target_pdb";
}
