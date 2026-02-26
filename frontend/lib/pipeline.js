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

export function stageFromPath(path) {
  const p = String(path || "").toLowerCase();
  if (p.includes("mask_consensus")) return "mask_consensus";
  if (p.includes("ligand_mask")) return "ligand_mask";
  if (p.includes("conservation")) return "conservation";
  if (p.includes("pdb_preprocess")) return "pdb_preprocess";
  if (p.includes("query_pdb")) return "query_pdb_check";
  if (p.includes("agent_panel")) return "agent";
  if (p.includes("/wt/") || p.startsWith("wt/") || p.includes("wt/")) return "wt";
  if (p.includes("rfd3")) return "rfd3";
  if (p.includes("diffdock") || p.includes("ligand")) return "diffdock";
  if (p.includes("af2") || p.includes("alphafold")) return "af2";
  if (p.includes("soluprot")) return "soluprot";
  if (p.includes("design") || p.includes("mpnn")) return "design";
  if (p.includes("msa") || p.includes("a3m") || p.includes("mmseq")) return "msa";
  if (p.includes("novel")) return "novelty";
  return "misc";
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
