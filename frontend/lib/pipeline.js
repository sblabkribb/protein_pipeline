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
