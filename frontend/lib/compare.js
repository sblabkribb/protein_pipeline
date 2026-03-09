function normalizeChainId(value) {
  const text = String(value || "")
    .trim()
    .toUpperCase();
  return text || "_";
}

export function compareResidueMetricPosition(left, right) {
  const leftChain = normalizeChainId(left?.chain);
  const rightChain = normalizeChainId(right?.chain);
  if (leftChain !== rightChain) return leftChain.localeCompare(rightChain);

  const leftResi = Number(left?.resi);
  const rightResi = Number(right?.resi);
  if (Number.isFinite(leftResi) && Number.isFinite(rightResi) && leftResi !== rightResi) {
    return leftResi - rightResi;
  }
  if (Number.isFinite(leftResi) && !Number.isFinite(rightResi)) return -1;
  if (!Number.isFinite(leftResi) && Number.isFinite(rightResi)) return 1;
  return String(left?.key || "").localeCompare(String(right?.key || ""));
}

export function normalizeDesignChains(values) {
  if (!Array.isArray(values)) return [];
  const out = [];
  const seen = new Set();
  values.forEach((value) => {
    const chain = normalizeChainId(value);
    if (chain === "_" || seen.has(chain)) return;
    seen.add(chain);
    out.push(chain);
  });
  return out;
}

export function extractDesignChainsFromPayload(payload) {
  if (!payload || typeof payload !== "object") return [];
  const candidates = [
    payload.design_chains_used,
    payload.auto_selected_design_chains,
    payload.design_chains,
    payload.requested_design_chains,
  ];
  for (const candidate of candidates) {
    const chains = normalizeDesignChains(candidate);
    if (chains.length) return chains;
  }
  return [];
}

const PDB_CHAIN_RECORD_RE = /^(ATOM  |HETATM|ANISOU|TER   )/;

export function filterPdbTextByChains(pdbText, chains) {
  const allowedChains = normalizeDesignChains(chains);
  const source = String(pdbText || "");
  if (!source.trim() || !allowedChains.length) return source;
  const allowed = new Set(allowedChains.map((chain) => normalizeChainId(chain)));
  const hasTrailingNewline = /\r?\n$/.test(source);
  const filtered = source
    .split(/\r?\n/)
    .filter((line) => {
      if (!PDB_CHAIN_RECORD_RE.test(line)) return true;
      return allowed.has(normalizeChainId(line.slice(21, 22)));
    })
    .join("\n");
  return hasTrailingNewline ? `${filtered}\n` : filtered;
}

export function selectResidueStripMetrics(metrics, options = {}) {
  const items = Array.isArray(metrics)
    ? metrics.filter((item) => item && typeof item === "object")
    : [];
  if (!items.length) return [];

  const midThreshold = Number(options.midThreshold);
  const threshold = Number.isFinite(midThreshold) ? midThreshold : 1.5;
  const maxCount = Math.max(1, Number(options.maxCount) || 220);
  const fallbackCount = Math.max(1, Number(options.fallbackCount) || 60);
  const significant = items.filter((item) => Number(item.distance || 0) > threshold);
  const source = significant.length ? significant.slice(0, maxCount) : items.slice(0, fallbackCount);
  return source.slice().sort(compareResidueMetricPosition);
}
