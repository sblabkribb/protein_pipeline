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

export function artifactMetaFromPath(path) {
  const normalized = normalizeArtifactPath(path);
  const tierMatch = normalized.match(/(?:^|\/)tiers\/([^/]+)/);
  const tier = tierMatch ? tierMatch[1] : null;

  let stage = "misc";
  if (
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
  } else if (
    matchPath(normalized, /(?:^|\/)af2_target(?:\/|$)/) ||
    normalized.endsWith("/target.pdb") ||
    normalized === "target.pdb"
  ) {
    stage = "af2_target";
  } else if (matchPath(normalized, /(?:^|\/)agent_panel(?:\/|$)/)) {
    stage = "agent";
  } else if (matchPath(normalized, /(?:^|\/)wt(?:\/|$)/)) {
    stage = "wt";
  } else if (matchPath(normalized, /(?:^|\/)(?:rfd3|rfdiffusion)(?:\/|$)/)) {
    stage = "rfd3";
  } else if (matchPath(normalized, /(?:^|\/)bioemu(?:\/|$)/)) {
    stage = "bioemu";
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

  return {
    path: String(path || ""),
    normalizedPath: normalized,
    tier,
    stage,
    source,
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
  delete args.questions;
  delete args.missing;
  return args;
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
