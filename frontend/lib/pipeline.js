const STAGE_ORDER = ["msa", "rfd3", "bioemu", "design", "soluprot", "af2", "novelty"];
const WORKFLOW_TIER_STAGE_ORDER = ["proteinmpnn", "soluprot", "af2", "novelty"];
const WORKFLOW_TIER_STAGE_TO_BASE = Object.freeze({
  proteinmpnn: "design",
  soluprot: "soluprot",
  af2: "af2",
  novelty: "novelty",
});
const DEFAULT_WORKFLOW_TIER_KEYS = Object.freeze(["30", "50", "70"]);
const DEFAULT_SELECTED_TIERS = Object.freeze([0.3, 0.5, 0.7]);
const TERMINAL_STATUS_STAGES = new Set(["done"]);
const PIPELINE_PROGRESS_STEPS = Object.freeze([
  "msa",
  "conservation",
  "backbone",
  "wt",
  "masking",
  "design",
  "soluprot",
  "af2",
  "novelty",
]);
const RUN_PROGRESS_PLANS = Object.freeze({
  pipeline: [...PIPELINE_PROGRESS_STEPS, "done"],
  workflow: [...PIPELINE_PROGRESS_STEPS, "done"],
  design: ["msa", "conservation", "backbone", "masking", "design", "done"],
  soluprot: ["msa", "conservation", "backbone", "masking", "design", "soluprot", "done"],
  rfd3: ["msa", "conservation", "rfd3", "done"],
  bioemu: ["msa", "conservation", "bioemu", "done"],
  msa: ["msa", "done"],
  af2: ["af2", "done"],
  diffdock: ["diffdock", "done"],
});

export const DEFAULT_ARTIFACT_COMPARE_MODE = "sequence";
export const DEFAULT_ARTIFACT_LIST_LIMIT = 1000;

function isKoreanLang(lang = "en") {
  return String(lang || "").trim().toLowerCase().startsWith("ko");
}

function formatPercentLike(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "";
  const rounded = Math.round(num * 100) / 100;
  const text = Number.isInteger(rounded) ? String(Math.trunc(rounded)) : String(rounded);
  return text;
}

export function normalizeConservationTier(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const num = Number(text);
  if (!Number.isFinite(num) || num <= 0) return null;
  return num > 1 ? num / 100 : num;
}

function normalizeSelectedTiers(values, fallback = DEFAULT_SELECTED_TIERS) {
  const source = Array.isArray(values) ? values : values === undefined || values === null ? [] : [values];
  const normalized = Array.from(
    new Set(source.map((value) => normalizeConservationTier(value)).filter((value) => value !== null))
  ).sort((left, right) => left - right);
  return normalized.length ? normalized : Array.isArray(fallback) ? [...fallback] : [];
}

export function formatConservationTierValue(value) {
  const normalized = normalizeConservationTier(value);
  if (normalized === null) return "-";
  const percentText = formatPercentLike(normalized * 100);
  return percentText ? `${percentText}%` : "-";
}

export function formatConservationTierLabel(value, lang = "en") {
  const tierValue = formatConservationTierValue(value);
  if (tierValue === "-") return "-";
  return isKoreanLang(lang) ? `서열 보존율 ${tierValue}` : `Sequence conservation ${tierValue}`;
}

function wtIdentityPercent(row) {
  const directPct = Number(row?.wt_identity_pct);
  if (Number.isFinite(directPct)) return directPct;
  const rawIdentity = Number(row?.wt_identity);
  if (!Number.isFinite(rawIdentity)) return null;
  return rawIdentity <= 1 ? rawIdentity * 100 : rawIdentity;
}

export function formatWtIdentitySummary(row, lang = "en") {
  const diffCount = Number(row?.wt_diff_count);
  const compareLen = Number(row?.wt_compare_len);
  const identityPct = wtIdentityPercent(row);
  const label = isKoreanLang(lang) ? "상동성" : "identity";
  const countText =
    Number.isFinite(diffCount) && Number.isFinite(compareLen) && compareLen > 0
      ? `${Math.max(0, Math.round(diffCount))}/${Math.round(compareLen)}`
      : "";
  const identityText = Number.isFinite(identityPct) ? `${label} ${Number(identityPct).toFixed(1)}%` : "";
  if (countText && identityText) return `${countText} · ${identityText}`;
  return countText || identityText || "-";
}

function normalizeStage(value) {
  let raw = String(value || "")
    .trim()
    .toLowerCase();
  raw = raw.replace(/[\s-]+/g, "_");
  if (raw === "wt_diff" || raw === "wtdiff") raw = "novelty";
  if (!raw) return "";
  return STAGE_ORDER.includes(raw) ? raw : "";
}

export function normalizeRfd3Mode(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (!raw) return "";
  const aliases = {
    legacy: "legacy_contig",
    contig: "legacy_contig",
    simple: "legacy_contig",
    legacy_contig: "legacy_contig",
    binder: "binder",
    binder_mode: "binder",
    enzyme: "enzyme",
    enzyme_mode: "enzyme",
    local_diversify: "local_diversify",
    local_diversify_mode: "local_diversify",
    diversify: "local_diversify",
    advanced: "advanced",
    advanced_inputs: "advanced",
  };
  return aliases[raw] || raw;
}

export function effectiveRfd3Mode(payload = {}) {
  const explicit = normalizeRfd3Mode(payload?.rfd3_mode);
  if (explicit) return explicit;
  if (hasMeaningfulValue(payload?.rfd3_inputs_text) || hasMeaningfulValue(payload?.rfd3_inputs)) {
    return "advanced";
  }
  if (
    hasMeaningfulValue(payload?.rfd3_unindex) ||
    hasMeaningfulValue(payload?.rfd3_length) ||
    hasMeaningfulValue(payload?.rfd3_select_fixed_atoms)
  ) {
    return "enzyme";
  }
  if (
    hasMeaningfulValue(payload?.rfd3_hotspots) ||
    hasMeaningfulValue(payload?.rfd3_infer_ori_strategy) ||
    typeof payload?.rfd3_is_non_loopy === "boolean"
  ) {
    return "binder";
  }
  if (hasMeaningfulValue(payload?.rfd3_contig)) {
    return "legacy_contig";
  }
  if (hasMeaningfulValue(payload?.rfd3_input_pdb)) {
    return "local_diversify";
  }
  const targetInput = String(payload?.target_input || "").trim();
  if (targetInput && detectTargetKey(targetInput) === "target_pdb") {
    return "local_diversify";
  }
  if (hasMeaningfulValue(payload?.target_pdb)) {
    return "local_diversify";
  }
  return "";
}

function hasLegacyRfd3Config(payload = {}) {
  return Boolean(
    hasMeaningfulValue(payload?.rfd3_inputs_text) ||
      hasMeaningfulValue(payload?.rfd3_inputs) ||
      hasMeaningfulValue(payload?.rfd3_input_files) ||
      hasMeaningfulValue(payload?.rfd3_input_pdb) ||
      hasMeaningfulValue(payload?.rfd3_mode) ||
      hasMeaningfulValue(payload?.rfd3_contig) ||
      hasMeaningfulValue(payload?.rfd3_hotspots) ||
      hasMeaningfulValue(payload?.rfd3_infer_ori_strategy) ||
      typeof payload?.rfd3_is_non_loopy === "boolean" ||
      hasMeaningfulValue(payload?.rfd3_unindex) ||
      hasMeaningfulValue(payload?.rfd3_length) ||
      hasMeaningfulValue(payload?.rfd3_select_fixed_atoms) ||
      hasMeaningfulValue(payload?.rfd3_ligand) ||
      hasMeaningfulValue(payload?.rfd3_select_unfixed_sequence) ||
      hasMeaningfulValue(payload?.rfd3_cli_args) ||
      hasMeaningfulValue(payload?.rfd3_env) ||
      hasMeaningfulValue(payload?.rfd3_partial_t) ||
      hasMeaningfulValue(payload?.rfd3_sampling_strategy) ||
      payload?.rfd3_fail_on_duplicate_backbones === true ||
      payload?.rfd3_use_ensemble === true
  );
}

export function rfd3UseValue(payload = {}) {
  if (typeof payload?.rfd3_use === "boolean") return payload.rfd3_use;
  return hasLegacyRfd3Config(payload);
}

function stageRangeIncludes(start, stop, targetStage) {
  const normalizedStart = normalizeStage(start) || "msa";
  const normalizedStop = normalizeStage(stop) || normalizedStart;
  const normalizedTarget = normalizeStage(targetStage);
  const startIdx = STAGE_ORDER.indexOf(normalizedStart);
  const stopIdx = STAGE_ORDER.indexOf(normalizedStop);
  const targetIdx = STAGE_ORDER.indexOf(normalizedTarget);
  if (startIdx < 0 || stopIdx < 0 || targetIdx < 0) return false;
  const from = Math.min(startIdx, stopIdx);
  const to = Math.max(startIdx, stopIdx);
  return targetIdx >= from && targetIdx <= to;
}

function normalizeWorkflowTierKey(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  if (Math.abs(parsed) <= 1.0) {
    return String(Math.round(parsed * 100));
  }
  return String(Math.round(parsed));
}

export function normalizeWorkflowStudioNode(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  const base = normalizeStage(raw);
  if (base) return base;
  const match = raw.match(/^(proteinmpnn|soluprot|af2|novelty)_([0-9]+(?:\.[0-9]+)?)$/);
  if (!match) return "";
  const tierKey = normalizeWorkflowTierKey(match[2]);
  if (!tierKey) return "";
  return `${match[1]}_${tierKey}`;
}

export function parseWorkflowStudioNode(value) {
  const nodeId = normalizeWorkflowStudioNode(value);
  if (!nodeId) return null;
  const baseStage = normalizeStage(nodeId);
  if (baseStage) {
    return {
      nodeId,
      baseStage,
      executionStage: baseStage,
      isTier: false,
      tierKey: "",
      tier: null,
      tierStage: "",
      selectedTiers: null,
    };
  }
  const match = nodeId.match(/^(proteinmpnn|soluprot|af2|novelty)_([0-9]+)$/);
  if (!match) return null;
  const tierStage = match[1];
  const tierKey = match[2];
  const base = WORKFLOW_TIER_STAGE_TO_BASE[tierStage] || "";
  if (!base) return null;
  return {
    nodeId,
    baseStage: base,
    executionStage: base,
    isTier: true,
    tierKey,
    tier: Number(tierKey) / 100,
    tierStage,
    selectedTiers: [Number(tierKey) / 100],
  };
}

export function resolveWorkflowStudioStageForSession(nodes, stage, fallback = "") {
  const sessionNodes = Array.from(
    new Set(
      (Array.isArray(nodes) ? nodes : [])
        .map((item) => normalizeWorkflowStudioNode(item))
        .filter(Boolean)
    )
  );
  const normalizedStage = normalizeWorkflowStudioNode(stage);
  if (!normalizedStage) return fallback;
  if (sessionNodes.includes(normalizedStage)) return normalizedStage;
  const stageMeta = parseWorkflowStudioNode(normalizedStage);
  if (!stageMeta) return fallback;
  if (stageMeta.isTier && sessionNodes.includes(stageMeta.baseStage)) {
    return stageMeta.baseStage;
  }
  const sameBaseNode = sessionNodes.find((item) => parseWorkflowStudioNode(item)?.baseStage === stageMeta.baseStage);
  return sameBaseNode || fallback;
}

export function workflowStudioRetainedArtifactPath(items, currentPath = "") {
  const selected = String(currentPath || "").trim();
  if (!selected) return "";
  const files = Array.isArray(items) ? items : [];
  return files.some((item) => item && item.type === "file" && String(item.path || "").trim() === selected) ? selected : "";
}

export function residuePickerControlState({
  targetPdbText = "",
  targetFastaText = "",
  rfd3PdbText = "",
  selectedRunId = "",
  busy = false,
} = {}) {
  const isBusy = Boolean(busy);
  return {
    canLoadTarget: !isBusy && Boolean(String(targetPdbText || "").trim()),
    canLoadRfd3: !isBusy && Boolean(String(rfd3PdbText || "").trim()),
    canLoadRun: !isBusy && Boolean(String(selectedRunId || "").trim()),
    canRunAf2: !isBusy && Boolean(String(targetFastaText || "").trim()),
  };
}

export function upsertWorkflowStudioStageStatus(stageStates = {}, stageRunIds = {}, stage = "", nextState = "", runId = "") {
  const normalizedStage = normalizeWorkflowStudioNode(stage);
  const normalizedState = String(nextState || "").trim().toLowerCase();
  const normalizedRunId = String(runId || "").trim();
  if (!normalizedStage || !normalizedState) return false;
  const previousState = String(stageStates?.[normalizedStage] || "").trim().toLowerCase();
  const previousRunId = String(stageRunIds?.[normalizedStage] || "").trim();
  if (previousState === normalizedState && previousRunId === normalizedRunId) {
    return false;
  }
  stageStates[normalizedStage] = normalizedState;
  if (normalizedRunId) {
    stageRunIds[normalizedStage] = normalizedRunId;
  } else {
    delete stageRunIds[normalizedStage];
  }
  return true;
}

function statusFromEventItem(item, runId = "") {
  if (!item || typeof item !== "object") return null;
  if (String(item.kind || "").trim().toLowerCase() !== "status") return null;
  const itemRunId = String(item.run_id || runId || "").trim();
  const expectedRunId = String(runId || "").trim();
  if (expectedRunId && itemRunId && itemRunId !== expectedRunId) return null;
  const stage = String(item.stage || "").trim() || "init";
  const stateText = String(item.state || "").trim() || "running";
  const updatedAt = String(item.updated_at || "").trim() || "-";
  const detailText =
    item.detail !== undefined && item.detail !== null ? String(item.detail).trim() : "events fallback";
  return {
    run_id: itemRunId || expectedRunId,
    stage,
    state: stateText,
    updated_at: updatedAt,
    detail: detailText || "events fallback",
  };
}

function statusRecordsFromEvents(eventsText, runId = "") {
  const raw = String(eventsText || "");
  if (!raw.trim()) return [];
  return raw
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch (err) {
        return null;
      }
    })
    .map((item) => statusFromEventItem(item, runId))
    .filter(Boolean);
}

export function latestMeaningfulStatusFromEvents(eventsText, runId = "") {
  const records = statusRecordsFromEvents(eventsText, runId);
  if (!records.length) return null;
  let fallback = null;
  for (let i = records.length - 1; i >= 0; i -= 1) {
    const record = records[i];
    if (!record) continue;
    if (!fallback) fallback = record;
    const stage = String(record.stage || "").trim().toLowerCase();
    if (!TERMINAL_STATUS_STAGES.has(stage)) {
      return record;
    }
  }
  return fallback;
}

export function latestWorkflowStudioCompletedNodesFromEvents(eventsText, runId = "") {
  const records = statusRecordsFromEvents(eventsText, runId);
  if (!records.length) return [];
  let startIndex = 0;
  for (let i = records.length - 1; i >= 0; i -= 1) {
    const stage = String(records[i]?.stage || "").trim().toLowerCase();
    const stateText = String(records[i]?.state || "").trim().toLowerCase();
    if (stage === "init" && stateText === "running") {
      startIndex = i;
      break;
    }
  }
  const recovered = [];
  for (let i = startIndex; i < records.length; i += 1) {
    const record = records[i];
    const stage = String(record?.stage || "").trim().toLowerCase();
    const stateText = String(record?.state || "").trim().toLowerCase();
    if (!["completed", "done"].includes(stateText)) continue;
    if (TERMINAL_STATUS_STAGES.has(stage)) continue;
    const nodeId = normalizeWorkflowStudioNode(stage);
    if (!nodeId) continue;
    recovered.push(nodeId);
  }
  return orderedWorkflowStudioNodes(recovered);
}

export function shouldPollRunForTabChange({
  nextTab = "",
  studioRunId = "",
  currentRunId = "",
  autoPollEnabled = false,
} = {}) {
  const tab = String(nextTab || "").trim().toLowerCase();
  const studioRun = String(studioRunId || "").trim();
  const currentRun = String(currentRunId || "").trim();
  if (tab === "studio") {
    return Boolean(studioRun || currentRun);
  }
  if (tab === "monitor") {
    return Boolean(autoPollEnabled) && Boolean(currentRun);
  }
  return false;
}

function workflowStudioNodeSortKey(value) {
  const meta = parseWorkflowStudioNode(value);
  if (!meta) return Number.MAX_SAFE_INTEGER;
  if (!meta.isTier) {
    const baseIdx = STAGE_ORDER.indexOf(meta.baseStage);
    if (meta.baseStage === "msa") return 0;
    if (meta.baseStage === "rfd3") return 100;
    if (meta.baseStage === "bioemu") return 200;
    return 900 + Math.max(0, baseIdx);
  }
  const tierNum = Number(meta.tierKey || 0);
  const stageIdx = Math.max(0, WORKFLOW_TIER_STAGE_ORDER.indexOf(meta.tierStage));
  return 300 + tierNum * 10 + stageIdx;
}

function orderedWorkflowStudioNodes(nodes) {
  const normalized = Array.from(
    new Set(
      (Array.isArray(nodes) ? nodes : [])
        .map((stage) => normalizeWorkflowStudioNode(stage))
        .filter(Boolean)
    )
  );
  return normalized.sort((a, b) => {
    const diff = workflowStudioNodeSortKey(a) - workflowStudioNodeSortKey(b);
    if (diff !== 0) return diff;
    return String(a).localeCompare(String(b));
  });
}

function normalizedWorkflowTierKeys(tiers) {
  const keys = Array.from(
    new Set(
      (Array.isArray(tiers) ? tiers : [])
        .map((item) => normalizeWorkflowTierKey(item))
        .filter(Boolean)
    )
  );
  return keys.length ? keys.sort((a, b) => Number(a) - Number(b)) : [...DEFAULT_WORKFLOW_TIER_KEYS];
}

export function expandWorkflowStudioNodes(nodes, conservationTiers = [0.3, 0.5, 0.7]) {
  const source = Array.isArray(nodes) ? nodes : [];
  const normalized = source.map((stage) => normalizeWorkflowStudioNode(stage)).filter(Boolean);
  if (!normalized.length) {
    return ["msa", "proteinmpnn_30", "soluprot_30", "af2_30"];
  }
  if (normalized.some((stage) => parseWorkflowStudioNode(stage)?.isTier)) {
    return orderedWorkflowStudioNodes(normalized);
  }

  const selectedBaseStages = new Set(
    normalized
      .map((stage) => parseWorkflowStudioNode(stage)?.baseStage || normalizeStage(stage))
      .filter(Boolean)
  );
  const output = [];
  ["msa", "rfd3", "bioemu"].forEach((stage) => {
    if (selectedBaseStages.has(stage)) output.push(stage);
  });
  const tierKeys = normalizedWorkflowTierKeys(conservationTiers);
  tierKeys.forEach((tierKey) => {
    if (selectedBaseStages.has("design")) output.push(`proteinmpnn_${tierKey}`);
    if (selectedBaseStages.has("soluprot")) output.push(`soluprot_${tierKey}`);
    if (selectedBaseStages.has("af2")) output.push(`af2_${tierKey}`);
    if (selectedBaseStages.has("novelty")) output.push(`novelty_${tierKey}`);
  });
  return output.length ? output : ["msa", "proteinmpnn_30", "soluprot_30", "af2_30"];
}

export function workflowStudioSessionRunKey(session) {
  if (!session || typeof session !== "object") return "";
  const direct = [
    session.head_run_id,
    session.pending?.run_id,
    session.source_run_id,
  ]
    .map((item) => String(item || "").trim())
    .find(Boolean);
  if (direct) return direct;
  if (Array.isArray(session.history)) {
    const historyRunId = session.history.map((item) => String(item?.run_id || "").trim()).find(Boolean);
    if (historyRunId) return historyRunId;
  }
  const stageRunIds = Object.values(session.stage_run_ids || {})
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const uniqueRunIds = Array.from(new Set(stageRunIds));
  return uniqueRunIds.length === 1 ? uniqueRunIds[0] : "";
}

export function workflowStudioActionRunIdForSession(session, currentRunId = "") {
  if (!session || typeof session !== "object") {
    return String(currentRunId || "").trim();
  }
  const pendingRunId = String(session?.pending?.run_id || "").trim();
  if (pendingRunId) return pendingRunId;
  return workflowStudioSessionRunKey(session);
}

export function workflowStudioSessionIdForRun(sessions, runId = "") {
  const key = String(runId || "").trim();
  if (!key) return "";
  const matched = (Array.isArray(sessions) ? sessions : []).find(
    (session) => workflowStudioSessionRunKey(session) === key
  );
  return String(matched?.session_id || "").trim();
}

export function buildWorkflowProgressContext({
  nodes = [],
  tierKeys = DEFAULT_WORKFLOW_TIER_KEYS,
  wtCompare = false,
} = {}) {
  const baseNodes = Array.from(
    new Set(
      (Array.isArray(nodes) ? nodes : [])
        .map((item) => parseWorkflowStudioNode(item)?.baseStage || normalizeStage(item))
        .filter(Boolean)
    )
  );
  if (!baseNodes.length) return null;
  const startFrom = baseNodes[0] || "msa";
  const stopAfter = baseNodes[baseNodes.length - 1] || "af2";
  return {
    tierKeys: normalizedWorkflowTierKeys(tierKeys),
    noveltyEnabled: stopAfter === "novelty",
    stopAfter,
    startFrom,
    wtCompare: Boolean(wtCompare),
  };
}

function progressStepForRequestedStage(stage, { wtCompare = false, start = false } = {}) {
  const normalized = normalizeStage(stage);
  if (normalized === "msa") return "msa";
  if (normalized === "rfd3" || normalized === "bioemu") return "backbone";
  if (normalized === "design") return "design";
  if (normalized === "soluprot") return "soluprot";
  if (normalized === "af2") return "af2";
  if (normalized === "novelty") return start && wtCompare ? "wt" : "novelty";
  return "";
}

export function progressStepsForRequest({
  mode = "pipeline",
  startFrom = "msa",
  stopAfter = "",
  noveltyEnabled = false,
  wtCompare = false,
} = {}) {
  const normalizedMode = String(mode || "").trim().toLowerCase();
  if (!["pipeline", "workflow"].includes(normalizedMode)) {
    const plan = RUN_PROGRESS_PLANS[normalizedMode] || RUN_PROGRESS_PLANS.pipeline;
    return noveltyEnabled === false ? plan.filter((step) => step !== "novelty") : [...plan];
  }
  const effectiveStopAfter = normalizeStage(stopAfter) || (noveltyEnabled ? "novelty" : "af2");
  const startStep = progressStepForRequestedStage(startFrom, {
    wtCompare: Boolean(wtCompare),
    start: true,
  }) || "msa";
  const endStep = progressStepForRequestedStage(effectiveStopAfter, {
    wtCompare: Boolean(wtCompare),
    start: false,
  }) || (noveltyEnabled ? "novelty" : "af2");
  if (normalizeStage(startFrom) === "novelty") {
    const steps = [];
    if (Boolean(wtCompare)) steps.push("wt");
    steps.push(endStep);
    return [...Array.from(new Set(steps.filter(Boolean))), "done"];
  }
  const startIdx = PIPELINE_PROGRESS_STEPS.indexOf(startStep);
  const endIdx = PIPELINE_PROGRESS_STEPS.indexOf(endStep);
  if (startIdx < 0 || endIdx < 0 || startIdx > endIdx) {
    return [...RUN_PROGRESS_PLANS.pipeline];
  }
  return [...PIPELINE_PROGRESS_STEPS.slice(startIdx, endIdx + 1), "done"];
}

export function progressUnitsForRequest({
  mode = "pipeline",
  startFrom = "msa",
  stopAfter = "",
  noveltyEnabled = false,
  wtCompare = false,
  tierKeys = DEFAULT_WORKFLOW_TIER_KEYS,
} = {}) {
  const normalizedMode = String(mode || "").trim().toLowerCase();
  const steps = progressStepsForRequest({
    mode: normalizedMode,
    startFrom,
    stopAfter,
    noveltyEnabled,
    wtCompare,
  }).filter(Boolean);
  if (!steps.length) return [{ step: "done" }];
  if (!["pipeline", "workflow"].includes(normalizedMode)) {
    return steps.map((step) => ({ step }));
  }
  const tierStepSet = new Set(["design", "soluprot", "af2", "novelty"]);
  const units = [];
  const normalizedTiers = normalizedWorkflowTierKeys(tierKeys);
  steps
    .filter((step) => step !== "done" && !tierStepSet.has(step))
    .forEach((step) => {
      units.push({ step });
    });
  const tierWindow = steps.filter((step) => step !== "done" && tierStepSet.has(step));
  if (tierWindow.length) {
    normalizedTiers.forEach((tierKey) => {
      tierWindow.forEach((step) => {
        units.push({ step, tierKey });
      });
    });
  }
  units.push({ step: "done" });
  return units;
}

export function workflowStudioExecutionTarget(stage) {
  const meta = parseWorkflowStudioNode(stage);
  if (!meta) {
    return {
      nodeId: "",
      baseStage: "",
      stopAfter: "",
      selectedTiers: undefined,
      tierKey: "",
      isTier: false,
    };
  }
  return {
    nodeId: meta.nodeId,
    baseStage: meta.baseStage,
    stopAfter: meta.executionStage,
    selectedTiers: meta.selectedTiers ? [...meta.selectedTiers] : undefined,
    tierKey: meta.tierKey,
    isTier: meta.isTier,
  };
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

function positiveIntegerOrNull(value) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function normalizeBioEmuCountFields(payload, { includeLegacyField = true } = {}) {
  const next =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? { ...payload }
      : {};
  let numSamples = positiveIntegerOrNull(next.bioemu_num_samples);
  let maxReturn = positiveIntegerOrNull(next.bioemu_max_return_structures);
  if (numSamples === null && maxReturn !== null) {
    numSamples = maxReturn;
  }
  if (maxReturn === null && numSamples !== null) {
    maxReturn = numSamples;
  }
  if (numSamples !== null) {
    next.bioemu_num_samples = numSamples;
  } else {
    delete next.bioemu_num_samples;
  }
  if (includeLegacyField) {
    if (maxReturn !== null) {
      next.bioemu_max_return_structures = maxReturn;
    } else {
      delete next.bioemu_max_return_structures;
    }
  }
  if (!includeLegacyField) {
    delete next.bioemu_max_return_structures;
  }
  return next;
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

function workflowStudioUserScope(user = null) {
  if (!user || typeof user !== "object" || Array.isArray(user)) return "";
  const explicit = sanitizeName(String(user.run_prefix || ""));
  if (explicit) return explicit;
  return sanitizeName(String(user.username || ""));
}

export function workflowStudioStorageKeysForUser(user = null) {
  const scope = workflowStudioUserScope(user);
  return {
    scope,
    sessionsKey: scope ? `kbf.workflowStudioSessions.${scope}` : "kbf.workflowStudioSessions",
    currentKey: scope ? `kbf.workflowStudioCurrent.${scope}` : "kbf.workflowStudioCurrent",
  };
}

export function workflowStudioOwnerFromUser(user = null) {
  return {
    owner_username: String(user?.username || "").trim(),
    owner_run_prefix: workflowStudioUserScope(user),
    owner_role: String(user?.role || "user").trim().toLowerCase() || "user",
  };
}

function workflowStudioOwnershipCandidates(session = null) {
  const source = session && typeof session === "object" && !Array.isArray(session) ? session : {};
  const values = [
    source.session_id,
    source.head_run_id,
    source.source_run_id,
    source.pending?.run_id,
    ...Object.values(source.stage_run_ids || {}),
    ...(Array.isArray(source.history) ? source.history.map((item) => item?.run_id) : []),
  ];
  return values
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

export function workflowStudioSessionBelongsToUser(session = null, user = null) {
  const username = String(user?.username || "").trim();
  const runPrefix = workflowStudioUserScope(user);
  if (!username || !runPrefix) return false;
  const ownerPrefix = String(session?.owner_run_prefix || "").trim();
  if (ownerPrefix) return ownerPrefix === runPrefix;
  const ownerUsername = String(session?.owner_username || "").trim();
  if (ownerUsername) return ownerUsername === username;
  return workflowStudioOwnershipCandidates(session).some((value) => value.startsWith(`${runPrefix}_`));
}

export function filterWorkflowStudioSessionsForUser(sessionsById = {}, user = null) {
  const out = {};
  Object.entries(sessionsById && typeof sessionsById === "object" && !Array.isArray(sessionsById) ? sessionsById : {}).forEach(
    ([sessionId, session]) => {
      if (!workflowStudioSessionBelongsToUser(session, user)) return;
      out[String(sessionId || "").trim()] = session;
    }
  );
  return out;
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

export function backboneSourceIndexFromManifest(manifest) {
  const out = {};
  const backbones = Array.isArray(manifest?.backbones) ? manifest.backbones : [];
  backbones.forEach((item) => {
    const id = String(item?.id || "").trim();
    const source = String(item?.source || "")
      .trim()
      .toLowerCase();
    if (!id) return;
    if (source === "rfd3" || source === "bioemu") {
      out[id] = source;
    }
  });
  return out;
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

export function artifactMetaFromPathForManifest(path, manifestOrIndex = null) {
  const meta = artifactMetaFromPath(path);
  const index = Array.isArray(manifestOrIndex?.backbones)
    ? backboneSourceIndexFromManifest(manifestOrIndex)
    : manifestOrIndex && typeof manifestOrIndex === "object"
      ? manifestOrIndex
      : null;
  const manifestSource =
    meta.backboneId && index ? String(index[meta.backboneId] || "").trim().toLowerCase() : "";
  if (manifestSource !== "rfd3" && manifestSource !== "bioemu") {
    return meta;
  }
  if (
    meta.stage === manifestSource &&
    meta.source === manifestSource &&
    meta.backboneSource === manifestSource
  ) {
    return meta;
  }
  return {
    ...meta,
    stage: manifestSource,
    source: manifestSource,
    backboneSource: manifestSource,
  };
}

export function stageFromPath(path) {
  return artifactMetaFromPath(path).stage;
}

function backboneUsageModeLabel(mode, lang = "en") {
  const raw = String(mode || "")
    .trim()
    .toLowerCase();
  const isKo = String(lang || "")
    .trim()
    .toLowerCase()
    .startsWith("ko");
  if (raw === "selected_only") return isKo ? "대표 1개만 사용" : "selected representative only";
  if (raw === "all_observed") return isKo ? "관측 구조 전체 사용" : "all observed used";
  if (raw === "all_materialized") return isKo ? "저장 구조 전체 사용" : "all saved used";
  if (raw === "partial") return isKo ? "일부만 사용" : "partially used";
  if (raw === "none") return isKo ? "미사용" : "not used";
  if (raw === "propagated_only") return isKo ? "사용" : "used";
  return raw || "-";
}

export function formatBackboneUsageSummary(
  sourceKey,
  summary,
  { lang = "en", includeSourceLabel = true, includeSelected = false } = {}
) {
  if (!summary || typeof summary !== "object") return "";
  const isKo = String(lang || "")
    .trim()
    .toLowerCase()
    .startsWith("ko");
  const label = sourceKey === "rfd3" ? "RFD3" : sourceKey === "bioemu" ? "BioEmu" : isKo ? "기타" : "Other";
  const requested = Number(summary.requested_count || 0);
  const observed = Number(summary.observed_count || 0);
  const materialized = Number(summary.materialized_count || 0);
  const used = Number(summary.propagated_count || summary.backbone_count || 0);
  const modeText = backboneUsageModeLabel(summary.propagation_mode, lang);
  const selectedId = String(summary.selected_backbone_id || "").trim();
  const prefix = includeSourceLabel ? `${label} · ` : "";
  const parts = [
    isKo ? `요청 ${requested}` : `requested ${requested}`,
    isKo ? `관측 ${observed}` : `observed ${observed}`,
    isKo ? `저장 ${materialized}` : `saved ${materialized}`,
    isKo ? `사용 ${used}` : `used ${used}`,
  ];
  if (modeText && modeText !== "-") parts.push(modeText);
  if (includeSelected && selectedId) {
    parts.push(isKo ? `대표 ${displayArtifactPath(selectedId)}` : `selected ${displayArtifactPath(selectedId)}`);
  }
  return `${prefix}${parts.join(" · ")}`;
}

export function buildArtifactDownloadRequest(item, { minBytes = 2048, slackBytes = 1024 } = {}) {
  if (!item || String(item.type || "") !== "file") return null;
  const path = String(item.path || "").trim();
  if (!path) return null;
  const rawSize = Number(item.size ?? item.size_bytes ?? 0);
  const fileSize = Number.isFinite(rawSize) && rawSize > 0 ? rawSize : 0;
  return {
    path,
    max_bytes: Math.max(minBytes, fileSize + slackBytes),
    base64: true,
  };
}

export function artifactDownloadFilename(path, fallback = "artifact.bin") {
  const raw = String(path || "").trim();
  if (!raw) return fallback;
  const parts = raw.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || fallback;
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
  const normalizedAnswers = normalizeBioEmuCountFields(answers, { includeLegacyField: true });
  const payload = {};
  for (const [key, value] of Object.entries(normalizedAnswers)) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string" && value.trim() === "") continue;
    payload[key] = value;
  }
  return payload;
}

export function normalizeFixedPositionsExtraDraft(raw) {
  if (raw === null || raw === undefined || raw === "") return {};
  let parsed = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch (_err) {
      return {};
    }
  }
  if (Array.isArray(parsed)) {
    const nums = parsed
      .map((value) => Number.parseInt(value, 10))
      .filter((value) => Number.isFinite(value) && value > 0);
    return nums.length ? { "*": Array.from(new Set(nums)).sort((left, right) => left - right) } : {};
  }
  if (!parsed || typeof parsed !== "object") return {};
  const out = {};
  Object.entries(parsed).forEach(([chain, values]) => {
    const nums = (Array.isArray(values) ? values : [values])
      .map((value) => Number.parseInt(value, 10))
      .filter((value) => Number.isFinite(value) && value > 0);
    if (nums.length) {
      out[String(chain)] = Array.from(new Set(nums)).sort((left, right) => left - right);
    }
  });
  return out;
}

export function mergeFixedPositionsExtraDraft(baseMap, addMap) {
  const merged = normalizeFixedPositionsExtraDraft(baseMap);
  Object.entries(normalizeFixedPositionsExtraDraft(addMap)).forEach(([chain, values]) => {
    const next = new Set((merged[chain] || []).map((value) => Number.parseInt(value, 10)));
    values.forEach((value) => next.add(value));
    const sorted = Array.from(next)
      .filter((value) => Number.isFinite(value) && value > 0)
      .sort((left, right) => left - right);
    if (sorted.length) merged[chain] = sorted;
  });
  return merged;
}

export function withFixedPositionsExtra(answers = {}, fixedPositions = {}) {
  const nextAnswers =
    answers && typeof answers === "object" && !Array.isArray(answers) ? cloneWorkflowValue(answers) : {};
  const normalized = normalizeFixedPositionsExtraDraft(fixedPositions);
  if (Object.keys(normalized).length) {
    nextAnswers.fixed_positions_extra = normalized;
  } else {
    delete nextAnswers.fixed_positions_extra;
  }
  return nextAnswers;
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

function positiveIntegerOrDefault(value, fallback) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function withProjectRoundContext(args = {}, context = {}) {
  const next = args && typeof args === "object" && !Array.isArray(args) ? { ...args } : {};
  const source = context && typeof context === "object" && !Array.isArray(context) ? context : {};
  const projectId = String(source.projectId ?? source.project_id ?? next.project_id ?? "").trim();
  const roundId = String(source.roundId ?? source.round_id ?? next.round_id ?? "").trim();
  if (projectId) {
    next.project_id = projectId;
  } else {
    delete next.project_id;
  }
  if (projectId && roundId) {
    next.round_id = roundId;
  } else {
    delete next.round_id;
  }
  return next;
}

export function buildFastLaunchPreset(draft = {}) {
  const source = draft && typeof draft === "object" && !Array.isArray(draft) ? draft : {};
  const targetInput = String(
    source.target_input || source.target_pdb || source.target_fasta || ""
  ).trim();
  const prompt = String(source.prompt || source.note || "").trim();
  const stopAfter = normalizeStage(source.stop_after) || "novelty";
  const noveltyEnabled = stopAfter === "novelty";
  const selectedTiers = normalizeSelectedTiers(source.selected_tiers ?? source.conservation_tiers);
  const numSeqPerTier = positiveIntegerOrDefault(source.num_seq_per_tier, 2);
  const totalOutputSequences = positiveIntegerOrDefault(source.total_output_sequences, 120);
  const activeBackboneSources = detectTargetKey(targetInput) === "target_pdb" ? 2 : 1;
  const perSourceBackboneCount = Math.max(
    1,
    Math.ceil(totalOutputSequences / (selectedTiers.length * numSeqPerTier * activeBackboneSources))
  );
  const answers = normalizeBioEmuCountFields(
    {
      target_input: targetInput,
      start_from: "msa",
      stop_after: stopAfter,
      novelty_enabled: noveltyEnabled,
      pdb_strip_nonpositive_resseq: source.pdb_strip_nonpositive_resseq !== false,
      wt_compare: source.wt_compare !== false,
      mask_consensus_apply: source.mask_consensus_apply === true,
      bioemu_use: true,
      bioemu_filter_samples: source.bioemu_filter_samples !== false,
      bioemu_num_samples: positiveIntegerOrDefault(source.bioemu_num_samples, perSourceBackboneCount * 2),
      bioemu_max_return_structures: positiveIntegerOrDefault(
        source.bioemu_max_return_structures,
        perSourceBackboneCount
      ),
      rfd3_use: true,
      rfd3_max_return_designs: positiveIntegerOrDefault(source.rfd3_max_return_designs, perSourceBackboneCount),
      selected_tiers: selectedTiers,
      num_seq_per_tier: numSeqPerTier,
    },
    { includeLegacyField: true }
  );
  return {
    mode: "pipeline",
    prompt,
    answers,
    routed: {
      stop_after: stopAfter,
      novelty_enabled: noveltyEnabled,
      bioemu_use: true,
      rfd3_use: true,
    },
  };
}

const WORKFLOW_STUDIO_STAGE_FIELDS = Object.freeze({
  msa: Object.freeze(["target_input", "pdb_strip_nonpositive_resseq"]),
  rfd3: Object.freeze([
    "rfd3_use",
    "rfd3_input_pdb",
    "rfd3_mode",
    "rfd3_contig",
    "rfd3_hotspots",
    "rfd3_infer_ori_strategy",
    "rfd3_is_non_loopy",
    "rfd3_unindex",
    "rfd3_length",
    "rfd3_select_fixed_atoms",
    "rfd3_partial_t",
    "rfd3_max_return_designs",
    "rfd3_inputs_text",
  ]),
  bioemu: Object.freeze([
    "bioemu_use",
    "bioemu_num_samples",
    "bioemu_max_return_structures",
    "bioemu_filter_samples",
    "bioemu_steering_config_text",
  ]),
  design: Object.freeze([
    "design_chains",
    "fixed_positions_extra",
    "num_seq_per_tier",
    "mask_consensus_apply",
    "ligand_mask_use_original_target",
  ]),
  soluprot: Object.freeze(["soluprot_cutoff"]),
  af2: Object.freeze([
    "af2_provider",
    "af2_max_candidates_per_tier",
    "af2_plddt_cutoff",
    "af2_rmsd_cutoff",
    "relax_enabled",
    "relax_score_per_residue_cutoff",
  ]),
  novelty: Object.freeze(["novelty_enabled", "wt_compare"]),
});

const WORKFLOW_STUDIO_STAGE_DEFAULTS = Object.freeze({
  rfd3: Object.freeze({
    rfd3_use: true,
    rfd3_max_return_designs: 10,
    rfd3_partial_t: 5.0,
  }),
  bioemu: Object.freeze({
    bioemu_num_samples: 20,
    bioemu_max_return_structures: 10,
    bioemu_filter_samples: true,
  }),
  design: Object.freeze({
    num_seq_per_tier: 2,
  }),
  af2: Object.freeze({
    af2_max_candidates_per_tier: 0,
  }),
});

const WORKFLOW_STUDIO_IGNORED_FIELDS = new Set([
  "run_mode",
  "start_from",
  "stop_after",
  "selected_tiers",
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
      .map((stage) => parseWorkflowStudioNode(stage)?.baseStage || normalizeStage(stage))
      .filter(Boolean)
  );
  return normalized.size ? STAGE_ORDER.filter((stage) => normalized.has(stage)) : [...STAGE_ORDER];
}

function applyWorkflowStudioStageDefaults(answers = {}, nodes = []) {
  const next = cloneWorkflowValue(answers && typeof answers === "object" ? answers : {});
  workflowStageOrderForNodes(nodes).forEach((stage) => {
    Object.entries(WORKFLOW_STUDIO_STAGE_DEFAULTS[stage] || {}).forEach(([key, value]) => {
      if (workflowValueIsAbsent(next[key])) {
        next[key] = cloneWorkflowValue(value);
      }
    });
  });
  return next;
}

function stripWorkflowStudioStageDefaults(answers = {}, nodes = []) {
  const next = cloneWorkflowValue(answers && typeof answers === "object" ? answers : {});
  workflowStageOrderForNodes(nodes).forEach((stage) => {
    Object.entries(WORKFLOW_STUDIO_STAGE_DEFAULTS[stage] || {}).forEach(([key, value]) => {
      if (workflowValuesEqual(next[key], value)) {
        delete next[key];
      }
    });
  });
  return next;
}

export function createWorkflowSessionId(prefix, now = new Date()) {
  const safePrefix = sanitizeName(prefix || "workflow") || "workflow";
  return createRunId(`${safePrefix}_studio`, now);
}

export function workflowStudioStageFields(stage) {
  const normalized = parseWorkflowStudioNode(stage)?.baseStage || normalizeStage(stage);
  return normalized ? [...(WORKFLOW_STUDIO_STAGE_FIELDS[normalized] || [])] : [];
}

function workflowStudioRfd3ModeUsesContig(mode) {
  const normalized = normalizeRfd3Mode(mode);
  return normalized === "legacy_contig" || normalized === "binder";
}

function workflowStudioRfd3ModeUsesBinderFields(mode) {
  return normalizeRfd3Mode(mode) === "binder";
}

function workflowStudioRfd3ModeUsesEnzymeFields(mode) {
  return normalizeRfd3Mode(mode) === "enzyme";
}

function workflowStudioRfd3ModeUsesPartialT(mode) {
  return ["local_diversify", "legacy_contig", "binder", "enzyme"].includes(normalizeRfd3Mode(mode));
}

function workflowStudioRfd3ModeUsesAdvancedInputs(mode) {
  return normalizeRfd3Mode(mode) === "advanced";
}

export function workflowStudioVisibleStageFields(stage, { answers = {}, nodes = [], overrideVisible = false } = {}) {
  const baseStage = parseWorkflowStudioNode(stage)?.baseStage || normalizeStage(stage);
  const fields = workflowStudioStageFields(stage);
  if (!fields.length) return [];
  if (baseStage !== "rfd3") return fields;

  const rfd3Mode = effectiveRfd3Mode(answers) || "local_diversify";
  const rfd3Enabled = rfd3EnabledForContext({ mode: "workflow", answers, nodes });
  const showRfd3InputPdb = shouldShowRfd3InputPdbField({
    mode: "workflow",
    answers,
    nodes,
    overrideVisible,
  });

  return fields.filter((fieldId) => {
    if (fieldId === "rfd3_use") return true;
    if (!rfd3Enabled) return false;
    if (fieldId === "rfd3_input_pdb") return showRfd3InputPdb;
    if (fieldId === "rfd3_contig") return workflowStudioRfd3ModeUsesContig(rfd3Mode);
    if (fieldId === "rfd3_hotspots" || fieldId === "rfd3_infer_ori_strategy" || fieldId === "rfd3_is_non_loopy") {
      return workflowStudioRfd3ModeUsesBinderFields(rfd3Mode);
    }
    if (fieldId === "rfd3_unindex" || fieldId === "rfd3_length" || fieldId === "rfd3_select_fixed_atoms") {
      return workflowStudioRfd3ModeUsesEnzymeFields(rfd3Mode);
    }
    if (fieldId === "rfd3_partial_t") return workflowStudioRfd3ModeUsesPartialT(rfd3Mode);
    if (fieldId === "rfd3_inputs_text") return workflowStudioRfd3ModeUsesAdvancedInputs(rfd3Mode);
    return true;
  });
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
  const mergedAnswers = mergeWorkflowStudioAnswers({
    baseAnswers: mergedBaseAnswers,
    stageDrafts: mergedStageDrafts,
    nodes,
  });
  return normalizeBioEmuCountFields(applyWorkflowStudioStageDefaults(mergedAnswers, nodes), {
    includeLegacyField: true,
  });
}

export function buildWorkflowStudioFreshSessionSeed({ session = null, prompt = "", answers = {}, nodes = [] } = {}) {
  const sourceSession = session && typeof session === "object" && !Array.isArray(session) ? session : null;
  return {
    prompt: "",
    nodes: orderedWorkflowStudioNodes(
      sourceSession && Array.isArray(sourceSession.nodes) && sourceSession.nodes.length ? sourceSession.nodes : nodes
    ),
    answers: {},
    sourceRunId: "",
  };
}

export function buildWorkflowStudioNodesFromRequest(payload = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  const mode = inferRequestRunMode(payload) || "pipeline";
  const startFrom = normalizeStage(payload.start_from) || "msa";
  const stopAfter = normalizeStage(payload.stop_after) || (Boolean(payload.novelty_enabled) ? "novelty" : "af2");
  const conservationTiers =
    Array.isArray(payload.selected_tiers) && payload.selected_tiers.length
      ? payload.selected_tiers
      : Array.isArray(payload.conservation_tiers) && payload.conservation_tiers.length
        ? payload.conservation_tiers
        : DEFAULT_WORKFLOW_TIER_KEYS;
  const nodes = [];
  if (stageRangeIncludes(startFrom, stopAfter, "msa")) nodes.push("msa");
  if (stageRangeIncludes(startFrom, stopAfter, "rfd3") && rfd3EnabledForContext({ mode, answers: payload, nodes: [] })) {
    nodes.push("rfd3");
  }
  if (stageRangeIncludes(startFrom, stopAfter, "bioemu") && Boolean(payload.bioemu_use)) {
    nodes.push("bioemu");
  }
  if (stageRangeIncludes(startFrom, stopAfter, "design")) nodes.push("design");
  if (stageRangeIncludes(startFrom, stopAfter, "soluprot")) nodes.push("soluprot");
  if (stageRangeIncludes(startFrom, stopAfter, "af2")) nodes.push("af2");
  if (stageRangeIncludes(startFrom, stopAfter, "novelty")) nodes.push("novelty");
  return expandWorkflowStudioNodes(nodes, conservationTiers);
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
  const target = parseWorkflowStudioNode(targetStage)?.baseStage || normalizeStage(targetStage) || "msa";
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
  const targetMeta = parseWorkflowStudioNode(targetStage);
  const target = targetMeta?.baseStage || normalizeStage(targetStage);
  const targetTierKey = targetMeta?.tierKey || "";
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
      upstreamStage: targetTierKey
        ? requirement.upstreamStage === "design"
          ? `proteinmpnn_${targetTierKey}`
          : `${requirement.upstreamStage}_${targetTierKey}`
        : requirement.upstreamStage,
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
      if (targetTierKey) {
        const tierMatch = normalizedPath.match(/(?:^|\/)tiers\/([^/]+)/);
        if (!tierMatch || normalizeWorkflowTierKey(tierMatch[1]) !== targetTierKey) return false;
      }
      return requirement.pathPatterns.some((pattern) => pattern.test(normalizedPath));
    })
    .map((item) => String(item.path || ""));

  return {
    required: true,
    blocked: matchedPaths.length === 0,
    code: requirement.code,
    upstreamStage: targetTierKey
      ? requirement.upstreamStage === "design"
        ? `proteinmpnn_${targetTierKey}`
        : `${requirement.upstreamStage}_${targetTierKey}`
      : requirement.upstreamStage,
    matchedPaths,
  };
}

export function nextWorkflowStudioStage(nodes, stage) {
  const order = orderedWorkflowStudioNodes(nodes);
  const normalized = normalizeWorkflowStudioNode(stage);
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
  let answers = {};
  const answerMeta = {};
  const skipKeys = new Set([
    "target_fasta",
    "target_pdb",
    "rfd3_input_pdb",
    "diffdock_ligand_sdf",
    "diffdock_ligand_smiles",
    "selected_tiers",
    "conservation_tiers",
  ]);

  Object.entries(payload).forEach(([key, value]) => {
    if (skipKeys.has(key)) return;
    if (value === undefined || value === null) return;
    if (typeof value === "string" && value.trim() === "") return;
    answers[key] = cloneSetupValue(value);
  });
  answers = normalizeBioEmuCountFields(answers, { includeLegacyField: true });

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
  if (rfd3Input.trim() && rfd3Input.trim() !== targetPdb.trim()) {
    answers.rfd3_input_pdb = rfd3Input;
    answerMeta.rfd3_input_pdb = { fileName: "request.json:rfd3_input_pdb" };
  }
  if (typeof payload.rfd3_use === "boolean") {
    answers.rfd3_use = payload.rfd3_use;
  } else if (rfd3UseValue(payload)) {
    answers.rfd3_use = true;
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

  const selectedTiers = normalizeSelectedTiers(
    Array.isArray(payload.selected_tiers) && payload.selected_tiers.length
      ? payload.selected_tiers
      : Array.isArray(payload.conservation_tiers) && payload.conservation_tiers.length
        ? payload.conservation_tiers
        : [],
    []
  );
  if (selectedTiers.length) {
    answers.selected_tiers = selectedTiers;
  }

  return { mode, answers, answerMeta };
}

export function normalizeSetupDraftForFreshRun(draft) {
  if (!draft || typeof draft !== "object" || Array.isArray(draft)) {
    return { mode: "", answers: {}, answerMeta: {} };
  }

  const mode = String(draft.mode || "").trim().toLowerCase();
  const answers =
    draft.answers && typeof draft.answers === "object" && !Array.isArray(draft.answers)
      ? cloneSetupValue(draft.answers)
      : {};
  const answerMeta =
    draft.answerMeta && typeof draft.answerMeta === "object" && !Array.isArray(draft.answerMeta)
      ? cloneSetupValue(draft.answerMeta)
      : {};

  if (mode === "pipeline") {
    answers.start_from = "msa";
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
    hasMeaningfulValue(payload.selected_tiers) ||
    hasMeaningfulValue(payload.mmseqs_target_db) ||
    hasMeaningfulValue(payload.novelty_target_db) ||
    hasMeaningfulValue(payload.rfd3_max_return_designs) ||
    hasMeaningfulValue(payload.conservation_tiers) ||
    hasMeaningfulValue(payload.wt_compare) ||
    hasMeaningfulValue(payload.mask_consensus_apply) ||
    hasMeaningfulValue(payload.ligand_mask_use_original_target) ||
    hasMeaningfulValue(payload.af2_plddt_cutoff) ||
    hasMeaningfulValue(payload.af2_rmsd_cutoff) ||
    hasMeaningfulValue(payload.relax_enabled) ||
    hasMeaningfulValue(payload.relax_score_per_residue_cutoff) ||
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

export function targetInputPdbText(answers = {}) {
  const explicit = String(answers?.target_pdb || "").trim();
  if (explicit) return explicit;
  const text = String(answers?.target_input || "").trim();
  if (!text) return "";
  return detectTargetKey(text) === "target_pdb" ? text : "";
}

export function explicitRfd3InputPdbText(answers = {}) {
  return String(answers?.rfd3_input_pdb || "").trim();
}

export function runUsesRfd3Stage({ mode = "", answers = {}, nodes = [] } = {}) {
  const normalizedMode = String(mode || "")
    .trim()
    .toLowerCase();
  if (normalizedMode === "rfd3") return true;
  if (normalizedMode === "workflow") {
    return (Array.isArray(nodes) ? nodes : []).some((node) => {
      const parsed = parseWorkflowStudioNode(node);
      return (parsed?.baseStage || normalizeStage(node)) === "rfd3";
    });
  }
  if (normalizedMode === "pipeline") {
    return stageRangeIncludes(answers?.start_from || "msa", answers?.stop_after || "novelty", "rfd3");
  }
  return false;
}

export function rfd3EnabledForContext({ mode = "", answers = {}, nodes = [] } = {}) {
  const normalizedMode = String(mode || "")
    .trim()
    .toLowerCase();
  if (normalizedMode === "rfd3") return true;
  if (!runUsesRfd3Stage({ mode, answers, nodes })) return false;
  return rfd3UseValue(answers);
}

export function effectiveRfd3InputPdb({ mode = "", answers = {}, nodes = [] } = {}) {
  const explicit = explicitRfd3InputPdbText(answers);
  if (!rfd3EnabledForContext({ mode, answers, nodes })) return "";
  if (explicit) return explicit;
  return targetInputPdbText(answers);
}

export function normalizeWorkflowStudioPayloadForComparison(payload, { nodes = [] } = {}) {
  const answers = cloneWorkflowValue(payload && typeof payload === "object" ? payload : {});
  delete answers.selected_tiers;

  const targetInput = String(answers.target_input || answers.target_pdb || answers.target_fasta || "").trim();
  delete answers.target_pdb;
  delete answers.target_fasta;
  if (targetInput) {
    if (detectTargetKey(targetInput) === "target_fasta") {
      answers.target_fasta = targetInput;
    } else {
      answers.target_pdb = targetInput;
    }
  }
  delete answers.target_input;

  if (Array.isArray(answers.design_chains) && answers.design_chains.length === 0) {
    delete answers.design_chains;
  }
  if (typeof answers.rfd3_input_pdb === "string") {
    answers.rfd3_input_pdb = answers.rfd3_input_pdb.trim();
  }
  if (typeof answers.rfd3_mode === "string") {
    answers.rfd3_mode = normalizeRfd3Mode(answers.rfd3_mode);
  }
  if (typeof answers.rfd3_contig === "string") {
    answers.rfd3_contig = answers.rfd3_contig.trim();
  }
  if (typeof answers.rfd3_hotspots === "string") {
    answers.rfd3_hotspots = answers.rfd3_hotspots.trim();
  }
  if (typeof answers.rfd3_infer_ori_strategy === "string") {
    answers.rfd3_infer_ori_strategy = answers.rfd3_infer_ori_strategy.trim();
  }
  if (typeof answers.rfd3_unindex === "string") {
    answers.rfd3_unindex = answers.rfd3_unindex.trim();
  }
  if (typeof answers.rfd3_length === "string") {
    answers.rfd3_length = answers.rfd3_length.trim();
  }
  if (typeof answers.rfd3_select_fixed_atoms === "string") {
    answers.rfd3_select_fixed_atoms = answers.rfd3_select_fixed_atoms.trim();
  }
  if (typeof answers.rfd3_inputs_text === "string") {
    answers.rfd3_inputs_text = answers.rfd3_inputs_text.trim();
  }
  if (typeof answers.bioemu_steering_config_text === "string") {
    answers.bioemu_steering_config_text = answers.bioemu_steering_config_text.trim();
  }
  if (String(answers.rfd3_input_pdb || "").trim() === String(answers.target_pdb || "").trim()) {
    delete answers.rfd3_input_pdb;
  }
  if (typeof answers.rfd3_input_pdb === "string" && !answers.rfd3_input_pdb.trim()) {
    delete answers.rfd3_input_pdb;
  }
  if (typeof answers.rfd3_mode === "string" && !answers.rfd3_mode.trim()) {
    delete answers.rfd3_mode;
  }
  if (typeof answers.rfd3_contig === "string" && !answers.rfd3_contig.trim()) {
    delete answers.rfd3_contig;
  }
  if (typeof answers.rfd3_hotspots === "string" && !answers.rfd3_hotspots.trim()) {
    delete answers.rfd3_hotspots;
  }
  if (typeof answers.rfd3_infer_ori_strategy === "string" && !answers.rfd3_infer_ori_strategy.trim()) {
    delete answers.rfd3_infer_ori_strategy;
  }
  if (typeof answers.rfd3_unindex === "string" && !answers.rfd3_unindex.trim()) {
    delete answers.rfd3_unindex;
  }
  if (typeof answers.rfd3_length === "string" && !answers.rfd3_length.trim()) {
    delete answers.rfd3_length;
  }
  if (typeof answers.rfd3_select_fixed_atoms === "string" && !answers.rfd3_select_fixed_atoms.trim()) {
    delete answers.rfd3_select_fixed_atoms;
  }
  if (typeof answers.rfd3_inputs_text === "string" && !answers.rfd3_inputs_text.trim()) {
    delete answers.rfd3_inputs_text;
  }
  if (typeof answers.bioemu_steering_config_text === "string" && !answers.bioemu_steering_config_text.trim()) {
    delete answers.bioemu_steering_config_text;
  }
  const rfd3Enabled = rfd3EnabledForContext({
    mode: "workflow",
    answers,
    nodes,
  });
  const effectiveRfd3Input = rfd3Enabled
    ? effectiveRfd3InputPdb({
        mode: "workflow",
        answers,
        nodes,
      })
    : "";
  const rfd3Mode = rfd3Enabled
    ? normalizeRfd3Mode(answers.rfd3_mode || effectiveRfd3Mode({ ...answers, rfd3_input_pdb: effectiveRfd3Input }))
    : "";
  if (rfd3Enabled && effectiveRfd3Input) {
    answers.rfd3_input_pdb = String(effectiveRfd3Input).trim();
    answers.rfd3_use = true;
  } else {
    delete answers.rfd3_input_pdb;
    delete answers.rfd3_mode;
    delete answers.rfd3_contig;
    delete answers.rfd3_hotspots;
    delete answers.rfd3_infer_ori_strategy;
    delete answers.rfd3_is_non_loopy;
    delete answers.rfd3_unindex;
    delete answers.rfd3_length;
    delete answers.rfd3_select_fixed_atoms;
    delete answers.rfd3_partial_t;
    delete answers.rfd3_inputs_text;
    delete answers.rfd3_use;
  }
  if (rfd3Enabled && rfd3Mode) {
    answers.rfd3_mode = rfd3Mode;
  }
  if (rfd3Enabled && rfd3Mode !== "legacy_contig" && rfd3Mode !== "binder") {
    delete answers.rfd3_contig;
  }
  if (rfd3Enabled && rfd3Mode !== "binder") {
    delete answers.rfd3_hotspots;
    delete answers.rfd3_infer_ori_strategy;
    delete answers.rfd3_is_non_loopy;
  }
  if (rfd3Enabled && rfd3Mode !== "enzyme") {
    delete answers.rfd3_unindex;
    delete answers.rfd3_length;
    delete answers.rfd3_select_fixed_atoms;
  }
  if (rfd3Enabled && rfd3Mode === "advanced") {
    delete answers.rfd3_partial_t;
  }
  if (rfd3Enabled && rfd3Mode !== "advanced") {
    delete answers.rfd3_inputs_text;
  }
  return stripWorkflowStudioStageDefaults(normalizeBioEmuCountFields(answers, { includeLegacyField: true }), nodes);
}

export function shouldShowRfd3InputPdbField({ mode = "", answers = {}, nodes = [], overrideVisible = false } = {}) {
  const normalizedMode = String(mode || "")
    .trim()
    .toLowerCase();
  if (normalizedMode === "rfd3") return true;
  if (!rfd3EnabledForContext({ mode, answers, nodes })) return false;
  const targetPdb = targetInputPdbText(answers);
  const explicit = explicitRfd3InputPdbText(answers);
  const hasCustomOverride = Boolean(explicit) && explicit !== targetPdb;
  if (hasCustomOverride || overrideVisible) return true;
  return !targetPdb;
}
