import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  buildCompareMetaTooltip,
  buildCompareScopeDescription,
  buildStructureDiffLegend,
  coerceFiniteMetricValue,
  extractDesignChainsFromPayload,
  filterPdbTextByChains,
  selectResidueStripMetrics,
} from "../lib/compare.js";
import {
  buildCopilotReply,
  copilotIntentFromPrompt,
} from "../lib/copilot.js";
import {
  DEFAULT_ARTIFACT_COMPARE_MODE,
  DEFAULT_ARTIFACT_LIST_LIMIT,
  artifactMetaFromPath,
  artifactMetaFromPathForManifest,
  artifactDownloadFilename,
  buildArtifactDownloadRequest,
  backboneSourceIndexFromManifest,
  buildWorkflowStudioFreshSessionSeed,
  buildWorkflowStudioNodesFromRequest,
  buildWorkflowStudioEffectiveAnswers,
  buildSetupDraftFromRequest,
  buildRunArguments,
  buildUserPrefix,
  createWorkflowSessionId,
  createRunId,
  detectTargetKey,
  displayArtifactPath,
  displayRfd3Id,
  effectiveRfd3InputPdb,
  expandWorkflowStudioNodes,
  filterRunsByPrefix,
  formatBackboneUsageSummary,
  inferRequestRunMode,
  latestWorkflowStudioCompletedNodesFromEvents,
  latestMeaningfulStatusFromEvents,
  mergeFixedPositionsExtraDraft,
  normalizeSetupDraftForFreshRun,
  normalizeFixedPositionsExtraDraft,
  formatWtIdentitySummary,
  mergeWorkflowStudioAnswers,
  minimumWorkflowStudioStartStage,
  normalizeWorkflowStudioPayloadForComparison,
  nextWorkflowStudioStage,
  parseWorkflowStudioNode,
  resolveWorkflowStudioStageForSession,
  runUsesRfd3Stage,
  sanitizeName,
  shouldReuseSelectedRun,
  shouldShowRfd3InputPdbField,
  shouldPollRunForTabChange,
  stageFromPath,
  splitWorkflowStudioAnswers,
  workflowStudioRetainedArtifactPath,
  workflowStudioActionRunIdForSession,
  workflowStudioExecutionTarget,
  workflowStudioOwnerFromUser,
  workflowStudioSessionBelongsToUser,
  workflowStudioStorageKeysForUser,
  buildWorkflowProgressContext,
  progressStepsForRequest,
  progressUnitsForRequest,
  residuePickerControlState,
  filterWorkflowStudioSessionsForUser,
  workflowStudioChangedFields,
  workflowStudioDependencyStatus,
  workflowStudioSessionIdForRun,
  workflowStudioStageFields,
  upsertWorkflowStudioStageStatus,
  withFixedPositionsExtra,
  workflowStudioSessionRunKey,
} from "../lib/pipeline.js";
import {
  aminoAcidPropertyInfo,
  availableConservedTierPresetKeys,
  buildSequenceSelectionTracks,
  buildDetachedResiduePickerStoragePayload,
  buildDetachedResiduePickerResultStoragePayload,
  classifyResidueExposure,
  clearResiduePickerSelectionState,
  conservedTierPresetState,
  DEFAULT_SURFACE_AREA_CUTOFF,
  deriveResidueSpatialPresets,
  mergeResidueSelectionMaps,
  queryPositionsToResidueSelectionMap,
  resolveResiduePickerSelectionState,
  resolveResidueSelectionMaps,
  selectionMapContains,
  toggleResidueSelectionMaps,
} from "../lib/residue-picker.js";
import { buildPopupWindowFeatures, openPopupWindow } from "../lib/windowing.js";
import {
  buildCompareViewerLegendLines,
  buildResiduePickerHoverText,
  buildResiduePickerViewerLegendLines,
} from "../lib/viewer-annotations.js";

test("sanitizeName normalizes", () => {
  assert.equal(sanitizeName(" Hana Kim "), "hana_kim");
  assert.equal(sanitizeName("K-Biofoundry!!"), "k-biofoundry");
  assert.equal(sanitizeName("..."), "");
});

test("buildUserPrefix builds org_name", () => {
  const prefix = buildUserPrefix({ name: "Hana", org: "KBF" });
  assert.equal(prefix, "kbf_hana");
});

test("createRunId uses prefix and utc timestamp", () => {
  const runId = createRunId("kbf_hana", new Date(Date.UTC(2024, 0, 2, 3, 4, 5)));
  assert.match(runId, /^kbf_hana_20240102_030405_[0-9a-f]{8}$/);
});

test("createWorkflowSessionId uses studio suffix and utc timestamp", () => {
  const sessionId = createWorkflowSessionId("kbf_hana", new Date(Date.UTC(2024, 0, 2, 3, 4, 5)));
  assert.match(sessionId, /^kbf_hana_studio_20240102_030405_[0-9a-f]{8}$/);
});

test("workflowStudioStorageKeysForUser scopes browser storage by run prefix", () => {
  const keys = workflowStudioStorageKeysForUser({
    username: "hana.kim",
    role: "user",
    run_prefix: "hana_kim",
  });
  assert.deepEqual(keys, {
    scope: "hana_kim",
    sessionsKey: "kbf.workflowStudioSessions.hana_kim",
    currentKey: "kbf.workflowStudioCurrent.hana_kim",
  });
});

test("workflowStudioSessionBelongsToUser prefers owner metadata and legacy prefix fallback", () => {
  const hana = { username: "hana", role: "user", run_prefix: "hana" };
  const minsu = { username: "minsu", role: "user", run_prefix: "minsu" };
  const owned = {
    session_id: "hana_studio_20260317_010101_deadbeef",
    owner_username: "hana",
    owner_run_prefix: "hana",
    head_run_id: "hana_20260317_010101_deadbeef",
  };
  const legacyOwned = {
    session_id: "hana_studio_20260317_010101_deadbeef",
    head_run_id: "hana_20260317_010101_deadbeef",
    source_run_id: "hana_20260317_010101_deadbeef",
    stage_run_ids: { msa: "hana_20260317_010101_deadbeef" },
  };
  const foreign = {
    session_id: "minsu_studio_20260317_010101_deadbeef",
    owner_username: "minsu",
    owner_run_prefix: "minsu",
    head_run_id: "minsu_20260317_010101_deadbeef",
  };

  assert.equal(workflowStudioSessionBelongsToUser(owned, hana), true);
  assert.equal(workflowStudioSessionBelongsToUser(owned, minsu), false);
  assert.equal(workflowStudioSessionBelongsToUser(legacyOwned, hana), true);
  assert.equal(workflowStudioSessionBelongsToUser(legacyOwned, minsu), false);
  assert.equal(workflowStudioSessionBelongsToUser(foreign, hana), false);
});

test("filterWorkflowStudioSessionsForUser keeps only the active user's sessions", () => {
  const hana = { username: "hana", role: "user", run_prefix: "hana" };
  const sessions = {
    hana_owned: {
      session_id: "hana_studio_20260317_010101_deadbeef",
      owner_username: "hana",
      owner_run_prefix: "hana",
    },
    hana_legacy: {
      session_id: "hana_studio_20260317_010102_deadbeef",
      head_run_id: "hana_20260317_010102_deadbeef",
    },
    foreign: {
      session_id: "minsu_studio_20260317_010103_deadbeef",
      owner_username: "minsu",
      owner_run_prefix: "minsu",
    },
  };

  assert.deepEqual(Object.keys(filterWorkflowStudioSessionsForUser(sessions, hana)).sort(), [
    "hana_legacy",
    "hana_owned",
  ]);
  assert.deepEqual(workflowStudioOwnerFromUser(hana), {
    owner_username: "hana",
    owner_run_prefix: "hana",
    owner_role: "user",
  });
});

test("app scopes Workflow Studio storage and reloads it per active user", () => {
  const source = readFileSync(resolve(process.cwd(), "frontend/app.js"), "utf-8");

  assert.match(source, /function reloadWorkflowStudioSessionsForUser\(/);
  assert.match(source, /workflowStudioStorageKeysForUser\(/);
  assert.match(source, /workflowStudioOwnerFromUser\(/);
  assert.match(source, /filterWorkflowStudioSessionsForUser\(/);
  assert.doesNotMatch(source, /workflowStudioSessionsById:\s*loadWorkflowStudioSessionsById\(\)/);
  assert.doesNotMatch(source, /currentWorkflowStudioSessionId:\s*loadCurrentWorkflowStudioSessionId\(\)/);
});

test("buildWorkflowStudioFreshSessionSeed creates a blank session while preserving workflow nodes", () => {
  const seed = buildWorkflowStudioFreshSessionSeed({
    session: {
      prompt: "optimize scaffold",
      nodes: ["msa", "proteinmpnn_30", "af2_30"],
      head_run_id: "run-123",
      head_request: {
        target_pdb: "HEADER\n",
        wt_compare: true,
      },
      base_answers: {
        target_pdb: "HEADER\n",
      },
      stage_drafts: {
        design: {
          fixed_positions_extra: { A: [5, 9] },
        },
        af2: {
          af2_provider: "af2",
        },
      },
    },
  });

  assert.equal(seed.prompt, "");
  assert.deepEqual(seed.nodes, ["msa", "proteinmpnn_30", "af2_30"]);
  assert.equal(seed.sourceRunId, "");
  assert.deepEqual(seed.answers, {});
});

test("buildWorkflowStudioFreshSessionSeed stays blank when no studio session exists", () => {
  const seed = buildWorkflowStudioFreshSessionSeed({
    prompt: "fresh start",
    answers: {
      target_pdb: "HEADER\n",
      fixed_positions_extra: { A: [2] },
    },
    nodes: ["af2_70", "msa", "proteinmpnn_70"],
  });

  assert.equal(seed.prompt, "");
  assert.deepEqual(seed.nodes, ["msa", "proteinmpnn_70", "af2_70"]);
  assert.equal(seed.sourceRunId, "");
  assert.deepEqual(seed.answers, {});
});

test("buildWorkflowStudioNodesFromRequest reconstructs studio lanes for direct pipeline runs", () => {
  const nodes = buildWorkflowStudioNodesFromRequest({
    target_pdb: "HEADER\n",
    bioemu_use: true,
    conservation_tiers: [0.3, 0.5, 0.7],
    stop_after: "af2",
    wt_compare: true,
  });

  assert.deepEqual(nodes, [
    "msa",
    "rfd3",
    "bioemu",
    "proteinmpnn_30",
    "soluprot_30",
    "af2_30",
    "proteinmpnn_50",
    "soluprot_50",
    "af2_50",
    "proteinmpnn_70",
    "soluprot_70",
    "af2_70",
  ]);
});

test("workflowStudioActionRunIdForSession does not borrow current run for a fresh session", () => {
  assert.equal(
    workflowStudioActionRunIdForSession(
      {
        session_id: "admin_studio_20260313_063140_82003e07",
        head_run_id: "",
        source_run_id: "",
        pending: null,
        history: [],
        stage_run_ids: {},
      },
      "admin_20260310_065409_2f2c2372"
    ),
    ""
  );
  assert.equal(workflowStudioActionRunIdForSession(null, "admin_20260310_065409_2f2c2372"), "admin_20260310_065409_2f2c2372");
});

test("stageFromPath inference", () => {
  assert.equal(stageFromPath("msa/a3m.gz"), "msa");
  assert.equal(stageFromPath("designs/seqs.fasta"), "design");
  assert.equal(stageFromPath("af2/ranking_debug.json"), "af2");
  assert.equal(stageFromPath("bioemu/sample_pdbs.json"), "bioemu");
  assert.equal(stageFromPath("backbones/bioemu_topology/target.pdb"), "bioemu");
  assert.equal(stageFromPath("backbones/inputs_spec-1_0_model_0/target.pdb"), "rfd3");
  assert.equal(stageFromPath("backbones/rfd3_spec-1_0_model_0/target.pdb"), "rfd3");
});

test("artifactMetaFromPath infers backbone ids and sources", () => {
  const rfd3Ranked = artifactMetaFromPath("tiers/30/af2/inputs_spec-1_0_model_0_2/ranked_0.pdb");
  assert.equal(rfd3Ranked.tier, "30");
  assert.equal(rfd3Ranked.backboneId, "inputs_spec-1_0_model_0");
  assert.equal(rfd3Ranked.backboneSource, "rfd3");

  const bioemuRanked = artifactMetaFromPath("tiers/50/af2/bioemu_topology_1/ranked_0.pdb");
  assert.equal(bioemuRanked.tier, "50");
  assert.equal(bioemuRanked.backboneId, "bioemu_topology");
  assert.equal(bioemuRanked.backboneSource, "bioemu");

  const stageDesign = artifactMetaFromPath("rfd3/designs/inputs_spec-1_0_model_0.pdb");
  assert.equal(stageDesign.backboneId, "inputs_spec-1_0_model_0");
  assert.equal(stageDesign.backboneSource, "rfd3");
});

test("artifactMetaFromPath classifies compare references and source outputs", () => {
  const inputRef = artifactMetaFromPath("target.original.pdb");
  assert.equal(inputRef.stage, "input_reference");
  assert.equal(inputRef.compareRole, "input_reference");
  assert.equal(inputRef.compareGroup, "references");

  const working = artifactMetaFromPath("target.pdb");
  assert.equal(working.stage, "working_backbone");
  assert.equal(working.compareRole, "working_backbone");
  assert.equal(working.compareGroup, "references");

  const wt = artifactMetaFromPath("wt/af2/ranked_0.pdb");
  assert.equal(wt.stage, "wt_af2");
  assert.equal(wt.compareRole, "wt_colabfold");
  assert.equal(wt.compareGroup, "references");

  const bioemuBackbone = artifactMetaFromPath("backbones/bioemu_topology/target.pdb");
  assert.equal(bioemuBackbone.compareRole, "backbone_snapshot");
  assert.equal(bioemuBackbone.compareGroup, "backbones");

  const sourceOutput = artifactMetaFromPath("bioemu/designs/bioemu_topology.pdb");
  assert.equal(sourceOutput.compareRole, "source_output");
  assert.equal(sourceOutput.compareGroup, "source_outputs");
});

test("artifactMetaFromPathForManifest reclassifies backbone descendants by source manifest", () => {
  const manifest = {
    backbones: [
      { id: "rfd3_spec-1_0_model_0", source: "rfd3" },
      { id: "sample_0000", source: "bioemu" },
    ],
  };
  const sourceIndex = backboneSourceIndexFromManifest(manifest);

  const rfd3Tier = artifactMetaFromPathForManifest(
    "backbones/rfd3_spec-1_0_model_0/tiers/30/proteinmpnn.json",
    sourceIndex
  );
  assert.equal(rfd3Tier.stage, "rfd3");
  assert.equal(rfd3Tier.source, "rfd3");

  const bioemuTier = artifactMetaFromPathForManifest("backbones/sample_0000/tiers/30/proteinmpnn.json", sourceIndex);
  assert.equal(bioemuTier.stage, "bioemu");
  assert.equal(bioemuTier.source, "bioemu");
  assert.equal(bioemuTier.backboneSource, "bioemu");

  const bioemuAf2 = artifactMetaFromPathForManifest("tiers/30/af2/sample_0000_1/ranked_0.pdb", sourceIndex);
  assert.equal(bioemuAf2.backboneId, "sample_0000");
  assert.equal(bioemuAf2.stage, "bioemu");
  assert.equal(bioemuAf2.source, "bioemu");

  const unrelated = artifactMetaFromPathForManifest("tiers/30/soluprot.json", sourceIndex);
  assert.equal(unrelated.stage, "soluprot");
});

test("DEFAULT_ARTIFACT_LIST_LIMIT leaves room for WT compare references in larger runs", () => {
  assert.equal(DEFAULT_ARTIFACT_LIST_LIMIT, 1000);
  assert.ok(DEFAULT_ARTIFACT_LIST_LIMIT > 300);
});

test("extractDesignChainsFromPayload prefers resolved design chains", () => {
  const chains = extractDesignChainsFromPayload({
    requested_design_chains: ["A", "B"],
    design_chains_used: ["B"],
  });
  assert.deepEqual(chains, ["B"]);
});

test("filterPdbTextByChains removes non-design chains", () => {
  const pdb = [
    "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C",
    "ATOM      2  CA  GLY B   1       1.000   0.000   0.000  1.00 20.00           C",
    "HETATM    3  C1  LIG B   2       2.000   0.000   0.000  1.00 20.00           C",
    "END",
    "",
  ].join("\n");
  const filtered = filterPdbTextByChains(pdb, ["A"]);
  assert.match(filtered, /ALA A/);
  assert.doesNotMatch(filtered, /GLY B/);
  assert.doesNotMatch(filtered, /LIG B/);
});

test("selectResidueStripMetrics keeps meaningful residues in numeric order", () => {
  const selected = selectResidueStripMetrics([
    { key: "A:100", chain: "A", resi: 100, distance: 4.1 },
    { key: "A:98", chain: "A", resi: 98, distance: 7.0 },
    { key: "A:102", chain: "A", resi: 102, distance: 0.8 },
    { key: "A:101", chain: "A", resi: 101, distance: 2.5 },
  ]);
  assert.deepEqual(
    selected.map((item) => item.resi),
    [98, 100, 101]
  );
});

test("selectResidueStripMetrics falls back to top metrics when all diffs are low", () => {
  const selected = selectResidueStripMetrics(
    [
      { key: "A:10", chain: "A", resi: 10, distance: 0.9 },
      { key: "A:2", chain: "A", resi: 2, distance: 0.8 },
    ],
    { fallbackCount: 2 }
  );
  assert.deepEqual(
    selected.map((item) => item.resi),
    [2, 10]
  );
});

test("coerceFiniteMetricValue parses residue distances from dataset strings", () => {
  assert.equal(coerceFiniteMetricValue("7.44"), 7.44);
  assert.equal(coerceFiniteMetricValue(3.4), 3.4);
  assert.equal(coerceFiniteMetricValue(""), null);
  assert.equal(coerceFiniteMetricValue("-"), null);
});

test("displayArtifactPath aliases legacy rfd3 ids", () => {
  assert.equal(
    displayArtifactPath("backbones/inputs_spec-1_0_model_0/target.pdb"),
    "backbones/rfd3_spec-1_0_model_0/target.pdb"
  );
  assert.equal(displayRfd3Id("inputs_spec-1_0_model_0:1"), "rfd3_spec-1_0_model_0:1");
  assert.equal(displayArtifactPath("rfd3/inputs.json"), "rfd3/inputs.json");
});

test("formatBackboneUsageSummary includes representative backbone id in Korean summaries", () => {
  const text = formatBackboneUsageSummary(
    "rfd3",
    {
      requested_count: 10,
      observed_count: 10,
      materialized_count: 1,
      propagated_count: 1,
      propagation_mode: "selected_only",
      selected_backbone_id: "rfd3_spec-1_0_model_0",
    },
    {
      lang: "ko",
      includeSourceLabel: true,
      includeSelected: true,
    }
  );
  assert.equal(
    text,
    "RFD3 · 요청 10 · 관측 10 · 저장 1 · 사용 1 · 대표 1개만 사용 · 대표 rfd3_spec-1_0_model_0"
  );
});

test("buildArtifactDownloadRequest requests base64 bytes with size slack", () => {
  assert.deepEqual(
    buildArtifactDownloadRequest({
      type: "file",
      path: "tiers/30/af2/ranked_0.pdb",
      size: 4096,
    }),
    {
      path: "tiers/30/af2/ranked_0.pdb",
      max_bytes: 5120,
      base64: true,
    }
  );
});

test("artifactDownloadFilename falls back to basename", () => {
  assert.equal(
    artifactDownloadFilename("backbones/rfd3_spec-1_0_model_0/target.pdb"),
    "target.pdb"
  );
  assert.equal(artifactDownloadFilename("report.md"), "report.md");
});

test("renderMcpGuideMarkup provides Korean token instructions for VS Code MCP", async () => {
  const mcpGuide = await import("../lib/mcp-guide.js").catch(() => null);
  assert.ok(mcpGuide && typeof mcpGuide.renderMcpGuideMarkup === "function");

  const html = mcpGuide.renderMcpGuideMarkup({ lang: "ko" });
  assert.match(html, /MCP 가이드/);
  assert.match(html, /KBF_SSO_ACCESS_TOKEN/);
  assert.match(html, /auth-storage/);
  assert.match(html, /access_token/);
  assert.match(html, /로컬 스토리지|Local Storage/);
  assert.match(html, /Codex/);
  assert.match(html, /원격 MCP 엔드포인트/);
});

test("renderMcpGuideMarkup keeps English MCP setup and token copy steps", async () => {
  const mcpGuide = await import("../lib/mcp-guide.js").catch(() => null);
  assert.ok(mcpGuide && typeof mcpGuide.renderMcpGuideMarkup === "function");

  const html = mcpGuide.renderMcpGuideMarkup({ lang: "en" });
  assert.match(html, /VS Code mcp\.json/);
  assert.match(html, /Authorization/);
  assert.match(html, /Bearer/);
  assert.match(html, /KBF_SSO_ACCESS_TOKEN/);
  assert.match(html, /notebook service MCP page/i);
  assert.match(html, /Codex/);
});

test("buildRunArguments merges routed and answers", () => {
  const args = buildRunArguments({
    prompt: "design",
    routed: { stop_after: "design" },
    answers: { target_pdb: "PDB" },
    runId: "run1",
  });
  assert.equal(args.prompt, "design");
  assert.equal(args.stop_after, "design");
  assert.equal(args.target_pdb, "PDB");
  assert.equal(args.run_id, "run1");
});

test("buildRunArguments normalizes start/stop stage range", () => {
  const args = buildRunArguments({
    prompt: "",
    routed: { stop_after: "msa" },
    answers: { start_from: "AF2" },
    runId: "run2",
  });
  assert.equal(args.start_from, "af2");
  assert.equal(args.stop_after, "af2");
});

test("buildRunArguments keeps false/zero values from answers", () => {
  const args = buildRunArguments({
    prompt: "",
    routed: {},
    answers: {
      bioemu_use: false,
      af2_max_candidates_per_tier: 0,
      af2_provider: "af2",
    },
    runId: "run3",
  });
  assert.equal(args.bioemu_use, false);
  assert.equal(args.af2_max_candidates_per_tier, 0);
  assert.equal(args.af2_provider, "af2");
});

test("buildRunArguments maps novelty_enabled to stop_after novelty", () => {
  const args = buildRunArguments({
    prompt: "",
    routed: {},
    answers: { novelty_enabled: true },
    runId: "run4",
  });
  assert.equal(args.novelty_enabled, true);
  assert.equal(args.stop_after, "novelty");
});

test("buildRunArguments normalizes wt_diff alias to novelty", () => {
  const args = buildRunArguments({
    prompt: "",
    routed: { stop_after: "wt_diff" },
    answers: {},
    runId: "run4b",
  });
  assert.equal(args.stop_after, "novelty");
});

test("workflowStudioChangedFields ignores absent optional values", () => {
  const previous = {
    target_pdb: "PDB",
    target_fasta: "",
    design_chains: null,
    fixed_positions_extra: null,
    novelty_enabled: false,
    af2_provider: "colabfold",
  };
  const next = {
    target_pdb: "PDB",
    novelty_enabled: false,
    af2_provider: "colabfold",
  };
  assert.deepEqual(workflowStudioChangedFields(previous, next), []);
  assert.equal(
    minimumWorkflowStudioStartStage({
      previousPayload: previous,
      nextPayload: next,
      targetStage: "novelty",
    }),
    "novelty"
  );
});

test("buildRunArguments omits start_from when it is msa", () => {
  const args = buildRunArguments({
    prompt: "",
    routed: { stop_after: "af2" },
    answers: { start_from: "msa" },
    runId: "run5",
  });
  assert.equal(args.stop_after, "af2");
  assert.equal(args.start_from, undefined);
});

test("normalizeFixedPositionsExtraDraft keeps only positive unique positions by chain", () => {
  assert.deepEqual(
    normalizeFixedPositionsExtraDraft({
      A: [9, "4", 9, -1, 0],
      b: [3, 3, 7],
      C: [],
    }),
    {
      A: [4, 9],
      b: [3, 7],
    }
  );
});

test("mergeFixedPositionsExtraDraft appends new query positions without duplicates", () => {
  assert.deepEqual(
    mergeFixedPositionsExtraDraft(
      { A: [2, 5] },
      { A: [5, 8], B: [3] }
    ),
    {
      A: [2, 5, 8],
      B: [3],
    }
  );
});

test("withFixedPositionsExtra clears fixed_positions_extra when selection is empty", () => {
  assert.deepEqual(
    withFixedPositionsExtra(
      {
        target_pdb: "ATOM",
        fixed_positions_extra: { A: [4, 9] },
      },
      {}
    ),
    {
      target_pdb: "ATOM",
    }
  );
});

test("workflowStudioStageFields exposes key fields per stage", () => {
  assert.deepEqual(workflowStudioStageFields("design"), [
    "design_chains",
    "fixed_positions_extra",
    "num_seq_per_tier",
    "mask_consensus_apply",
    "ligand_mask_use_original_target",
  ]);
  assert.deepEqual(workflowStudioStageFields("soluprot"), ["soluprot_cutoff"]);
  assert.deepEqual(workflowStudioStageFields("soluprot_50"), ["soluprot_cutoff"]);
  assert.deepEqual(workflowStudioStageFields("unknown"), []);
});

test("parseWorkflowStudioNode parses tier lanes into base execution stages", () => {
  assert.deepEqual(parseWorkflowStudioNode("proteinmpnn_30"), {
    nodeId: "proteinmpnn_30",
    baseStage: "design",
    executionStage: "design",
    isTier: true,
    tierKey: "30",
    tier: 0.3,
    tierStage: "proteinmpnn",
    selectedTiers: [0.3],
  });
  assert.equal(parseWorkflowStudioNode("af2").baseStage, "af2");
});

test("expandWorkflowStudioNodes expands downstream workflow stages per tier", () => {
  assert.deepEqual(expandWorkflowStudioNodes(["msa", "design", "soluprot", "af2"], [0.3, 0.5]), [
    "msa",
    "proteinmpnn_30",
    "soluprot_30",
    "af2_30",
    "proteinmpnn_50",
    "soluprot_50",
    "af2_50",
  ]);
});

test("splitWorkflowStudioAnswers isolates stage-owned drafts", () => {
  const split = splitWorkflowStudioAnswers({
    target_input: ">q1\nACDE",
    design_chains: ["A"],
    af2_provider: "af2",
    conservation_tiers: [0.3, 0.5],
    stop_after: "af2",
  });
  assert.deepEqual(split.baseAnswers, { conservation_tiers: [0.3, 0.5] });
  assert.deepEqual(split.stageDrafts.msa, { target_input: ">q1\nACDE" });
  assert.deepEqual(split.stageDrafts.design, { design_chains: ["A"] });
  assert.deepEqual(split.stageDrafts.af2, { af2_provider: "af2" });
});

test("mergeWorkflowStudioAnswers applies drafts in pipeline stage order", () => {
  const merged = mergeWorkflowStudioAnswers({
    baseAnswers: { conservation_tiers: [0.3] },
    stageDrafts: {
      msa: { target_input: ">q1\nACDE" },
      design: { design_chains: ["A"] },
      af2: { af2_provider: "af2" },
    },
    nodes: ["msa", "design", "af2"],
  });
  assert.deepEqual(merged, {
    conservation_tiers: [0.3],
    target_input: ">q1\nACDE",
    design_chains: ["A"],
    af2_provider: "af2",
  });
});

test("buildWorkflowStudioEffectiveAnswers inherits prior run values for untouched fields", () => {
  const merged = buildWorkflowStudioEffectiveAnswers({
    headRequest: {
      target_pdb: "ATOM",
      rfd3_input_pdb: "ATOM",
      rfd3_contig: "A1-10",
      bioemu_use: true,
      bioemu_num_samples: 10,
      bioemu_max_return_structures: 10,
      stop_after: "rfd3",
    },
    baseAnswers: {},
    stageDrafts: {
      msa: { target_input: "ATOM" },
      rfd3: { rfd3_input_pdb: "ATOM" },
      bioemu: { bioemu_use: true, bioemu_num_samples: 10, bioemu_max_return_structures: 10 },
    },
    nodes: ["msa", "rfd3", "bioemu"],
  });
  assert.equal(merged.rfd3_contig, "A1-10");
  assert.equal(merged.bioemu_use, true);
});

test("buildWorkflowStudioEffectiveAnswers applies workflow defaults for untouched design and af2 counts", () => {
  const merged = buildWorkflowStudioEffectiveAnswers({
    headRequest: {
      target_pdb: "ATOM",
      stop_after: "af2",
    },
    baseAnswers: {},
    stageDrafts: {
      msa: { target_input: "ATOM" },
    },
    nodes: ["msa", "design", "af2"],
  });
  assert.equal(merged.num_seq_per_tier, 2);
  assert.equal(merged.af2_max_candidates_per_tier, 0);
});

test("buildWorkflowStudioEffectiveAnswers applies workflow defaults for untouched rfd3 and bioemu counts", () => {
  const merged = buildWorkflowStudioEffectiveAnswers({
    headRequest: {
      target_pdb: "ATOM",
      stop_after: "af2",
      bioemu_use: true,
    },
    baseAnswers: {},
    stageDrafts: {
      msa: { target_input: "ATOM" },
      bioemu: { bioemu_use: true },
    },
    nodes: ["msa", "rfd3", "bioemu", "design", "af2"],
  });
  assert.equal(merged.rfd3_max_return_designs, 10);
  assert.equal(merged.bioemu_num_samples, 20);
  assert.equal(merged.bioemu_max_return_structures, 10);
  assert.equal(merged.bioemu_filter_samples, true);
  assert.equal(merged.num_seq_per_tier, 2);
  assert.equal(merged.af2_max_candidates_per_tier, 0);
});

test("workflow studio question metadata keeps default return counts for rfd3 and bioemu", () => {
  const source = readFileSync(resolve(process.cwd(), "frontend/app.js"), "utf-8");
  assert.match(
    source,
    /bioemu_num_samples:\s*\{[\s\S]*?labelKey:\s*"question\.bioemuNumSamples\.label",[\s\S]*?default:\s*20,/m
  );
  assert.match(
    source,
    /bioemu_max_return_structures:\s*\{[\s\S]*?labelKey:\s*"question\.bioemuMaxReturn\.label",[\s\S]*?default:\s*10,/m
  );
  assert.match(
    source,
    /rfd3_max_return_designs:\s*\{[\s\S]*?labelKey:\s*"question\.rfd3MaxReturn\.label",[\s\S]*?default:\s*10,/m
  );
  assert.match(source, /rfd3_partial_t:\s*\{[\s\S]*?default:\s*10(?:\.0)?,/m);
});

test("RFD3 mode question metadata and localized guidance copy are present", () => {
  const source = readFileSync(resolve(process.cwd(), "frontend/app.js"), "utf-8");
  assert.match(
    source,
    /rfd3_mode:\s*\{[\s\S]*?labelKey:\s*"question\.rfd3Mode\.label",[\s\S]*?questionKey:\s*"question\.rfd3Mode\.help",[\s\S]*?default:\s*"local_diversify",/m
  );
  assert.match(
    source,
    /if \(q\.id === "rfd3_mode"\) \{[\s\S]*?mode-guide-desc[\s\S]*?rfd3ModeDescriptionKey\(/m
  );
  ["localDiversify", "legacyContig", "binder", "enzyme", "advanced"].forEach((suffix) => {
    assert.equal(source.split(`"choice.rfd3Mode.${suffix}":`).length - 1, 2);
    assert.equal(source.split(`"question.rfd3Mode.mode.${suffix}":`).length - 1, 2);
  });
});

test("Setup and Studio source reflect RFD3 detail localization and no Studio new workflow action", () => {
  const source = readFileSync(resolve(process.cwd(), "frontend/app.js"), "utf-8");
  const html = readFileSync(resolve(process.cwd(), "frontend/index.html"), "utf-8");

  assert.doesNotMatch(source, /data-studio-action="new"/);
  assert.doesNotMatch(source, /studioNewSessionBtn/);
  assert.doesNotMatch(source, /studio\.action\.new/);
  assert.doesNotMatch(source, /createFreshWorkflowStudioSession\(/);
  assert.doesNotMatch(html, /studioNewSessionBtn/);

  [
    "question.rfd3Hotspots.label",
    "question.rfd3Hotspots.help",
    "question.rfd3Orientation.label",
    "question.rfd3Orientation.help",
    "question.rfd3NonLoopy.label",
    "question.rfd3NonLoopy.help",
    "question.rfd3Unindex.label",
    "question.rfd3Unindex.help",
    "question.rfd3Length.label",
    "question.rfd3Length.help",
    "question.rfd3FixedAtoms.label",
    "question.rfd3FixedAtoms.help",
    "question.rfd3AdvancedInputs.label",
    "question.rfd3AdvancedInputs.help",
    "question.rfd3PartialT.label",
    "question.rfd3PartialT.help",
    "question.bioemuFilterSamples.label",
    "question.bioemuFilterSamples.help",
    "question.bioemuSteeringConfig.label",
    "question.bioemuSteeringConfig.help",
  ].forEach((key) => {
    assert.ok(source.split(`"${key}"`).length - 1 >= 2, `missing localized key ${key}`);
  });

  [
    "choice.rfd3Mode.localDiversify",
    "choice.rfd3Mode.legacyContig",
    "choice.rfd3Mode.binder",
    "choice.rfd3Mode.enzyme",
    "choice.rfd3Mode.advanced",
  ].forEach((key) => {
    assert.equal(source.split(`"${key}":`).length - 1, 2, `missing mode choice key ${key}`);
  });
  assert.equal(source.split(`"choice.rfd3Mode.localDiversify": "Local Diversify"`).length - 1, 2);
  assert.equal(source.split(`"choice.rfd3Mode.legacyContig": "Legacy Contig"`).length - 1, 2);
  assert.equal(source.split(`"choice.rfd3Mode.binder": "Binder"`).length - 1, 2);
  assert.equal(source.split(`"choice.rfd3Mode.enzyme": "Enzyme"`).length - 1, 2);
  assert.equal(source.split(`"choice.rfd3Mode.advanced": "Advanced"`).length - 1, 2);

  const rfd3DetailIdsBlock = source.match(/const SETUP_RFD3_MODE_DETAIL_IDS = new Set\(\[([\s\S]*?)\]\);/);
  assert.ok(rfd3DetailIdsBlock);
  assert.match(rfd3DetailIdsBlock[1], /"rfd3_partial_t"/);
  assert.match(source, /function renderSetupRfd3ModeDetailsCard\(/);
  assert.match(source, /renderSetupRfd3ModeDetailsCard\(card, normalizedQuestions\)/);
  const compactChoiceBlock = source.match(/const compactChoiceQuestionIds = new Set\(\[([\s\S]*?)\]\);/);
  assert.ok(compactChoiceBlock);
  assert.doesNotMatch(compactChoiceBlock[1], /ligand_mask_use_original_target/);
  const compactParameterBlock = source.match(/const compactParameterQuestionIds = new Set\(\[([\s\S]*?)\]\);/);
  assert.ok(compactParameterBlock);
  assert.doesNotMatch(compactParameterBlock[1], /rfd3_partial_t/);
});

test("normalizeWorkflowStudioPayloadForComparison ignores implicit studio defaults", () => {
  const normalized = normalizeWorkflowStudioPayloadForComparison(
    {
      target_input: "ATOM",
      num_seq_per_tier: 2,
      af2_max_candidates_per_tier: 0,
    },
    { nodes: ["msa", "design", "af2"] }
  );
  assert.equal(normalized.num_seq_per_tier, undefined);
  assert.equal(normalized.af2_max_candidates_per_tier, undefined);
});

test("buildRunArguments preserves distinct BioEmu generated and return counts", () => {
  const args = buildRunArguments({
    prompt: "sample backbones",
    routed: { stop_after: "bioemu", bioemu_use: true },
    answers: { bioemu_num_samples: 20, bioemu_max_return_structures: 10 },
    runId: "bioemu_count_sync",
  });
  assert.equal(args.bioemu_num_samples, 20);
  assert.equal(args.bioemu_max_return_structures, 10);
});

test("runUsesRfd3Stage tracks whether current execution path includes rfd3", () => {
  assert.equal(
    runUsesRfd3Stage({
      mode: "pipeline",
      answers: {
        target_input: "ATOM      1  N",
        start_from: "msa",
        stop_after: "novelty",
      },
    }),
    true
  );
  assert.equal(
    runUsesRfd3Stage({
      mode: "pipeline",
      answers: {
        target_input: "ATOM      1  N",
        start_from: "design",
        stop_after: "novelty",
      },
    }),
    false
  );
  assert.equal(
    runUsesRfd3Stage({
      mode: "workflow",
      answers: {
        target_input: "ATOM      1  N",
      },
      nodes: ["msa", "design", "af2"],
    }),
    false
  );
  assert.equal(
    runUsesRfd3Stage({
      mode: "workflow",
      answers: {
        target_input: "ATOM      1  N",
      },
      nodes: ["msa", "rfd3", "design"],
    }),
    true
  );
});

test("effectiveRfd3InputPdb defaults to target_input pdb only when rfd3 is in scope", () => {
  assert.equal(
    effectiveRfd3InputPdb({
      mode: "pipeline",
      answers: {
        target_input: "ATOM      1  N",
        start_from: "msa",
        stop_after: "novelty",
      },
    }),
    "ATOM      1  N"
  );
  assert.equal(
    effectiveRfd3InputPdb({
      mode: "pipeline",
      answers: {
        target_input: "ATOM      1  N",
        start_from: "design",
        stop_after: "novelty",
      },
    }),
    ""
  );
  assert.equal(
    effectiveRfd3InputPdb({
      mode: "workflow",
      answers: {
        target_input: "ATOM      1  N",
        rfd3_input_pdb: "ATOM      1  CA",
      },
      nodes: ["msa", "rfd3", "design"],
    }),
    "ATOM      1  CA"
  );
});

test("shouldShowRfd3InputPdbField only exposes separate override when needed", () => {
  assert.equal(
    shouldShowRfd3InputPdbField({
      mode: "pipeline",
      answers: {
        target_input: "ATOM      1  N",
        start_from: "msa",
        stop_after: "novelty",
      },
    }),
    false
  );
  assert.equal(
    shouldShowRfd3InputPdbField({
      mode: "pipeline",
      answers: {
        target_input: ">q1\nACDE",
        start_from: "msa",
        stop_after: "novelty",
      },
    }),
    true
  );
  assert.equal(
    shouldShowRfd3InputPdbField({
      mode: "pipeline",
      answers: {
        target_input: "ATOM      1  N",
        start_from: "msa",
        stop_after: "novelty",
      },
      overrideVisible: true,
    }),
    true
  );
});

test("workflowStudioChangedFields compares nested values", () => {
  const changed = workflowStudioChangedFields(
    {
      target_pdb: "ATOM",
      design_chains: ["A"],
      fixed_positions_extra: { A: [6, 10] },
    },
    {
      target_pdb: "ATOM",
      design_chains: ["A", "B"],
      fixed_positions_extra: { A: [6, 10] },
    }
  );
  assert.deepEqual(changed, ["design_chains"]);
});

test("minimumWorkflowStudioStartStage returns earliest affected stage", () => {
  assert.equal(
    minimumWorkflowStudioStartStage({
      previousPayload: { target_pdb: "ATOM", af2_provider: "colabfold" },
      nextPayload: { target_pdb: "ATOM", af2_provider: "af2" },
      targetStage: "af2",
    }),
    "af2"
  );
  assert.equal(
    minimumWorkflowStudioStartStage({
      previousPayload: { target_pdb: "ATOM", design_chains: ["A"] },
      nextPayload: { target_pdb: "MODEL", design_chains: ["A", "B"] },
      targetStage: "design",
    }),
    "msa"
  );
});

test("workflowStudioDependencyStatus blocks downstream stages without current-run upstream outputs", () => {
  const soluprot = workflowStudioDependencyStatus({
    targetStage: "soluprot",
    requiredStart: "soluprot",
    artifacts: [],
  });
  assert.equal(soluprot.required, true);
  assert.equal(soluprot.blocked, true);
  assert.equal(soluprot.code, "design_outputs_missing");

  const af2 = workflowStudioDependencyStatus({
    targetStage: "af2",
    requiredStart: "af2",
    artifacts: [{ type: "file", path: "tiers/30/soluprot.json", size: 128 }],
  });
  assert.equal(af2.required, true);
  assert.equal(af2.blocked, true);
  assert.equal(af2.code, "soluprot_passed_missing");

  const novelty = workflowStudioDependencyStatus({
    targetStage: "novelty",
    requiredStart: "novelty",
    artifacts: [{ type: "file", path: "tiers/30/af2_selected.fasta", size: 0 }],
  });
  assert.equal(novelty.required, true);
  assert.equal(novelty.blocked, true);
  assert.equal(novelty.code, "af2_selected_missing");
});

test("workflowStudioDependencyStatus accepts matching upstream outputs", () => {
  const soluprot = workflowStudioDependencyStatus({
    targetStage: "soluprot",
    requiredStart: "soluprot",
    artifacts: [{ type: "file", path: "tiers/30/proteinmpnn.json", size: 256 }],
  });
  assert.equal(soluprot.blocked, false);
  assert.deepEqual(soluprot.matchedPaths, ["tiers/30/proteinmpnn.json"]);

  const af2 = workflowStudioDependencyStatus({
    targetStage: "af2",
    requiredStart: "af2",
    artifacts: [{ type: "file", path: "tiers/30/designs_filtered.fasta", size: 64 }],
  });
  assert.equal(af2.blocked, false);

  const novelty = workflowStudioDependencyStatus({
    targetStage: "novelty",
    requiredStart: "novelty",
    artifacts: [{ type: "file", path: "tiers/30/af2_selected.fasta", size: 64 }],
  });
  assert.equal(novelty.blocked, false);
});

test("workflowStudioDependencyStatus scopes tier lanes to matching tier outputs", () => {
  const dependency = workflowStudioDependencyStatus({
    targetStage: "af2_50",
    requiredStart: "af2",
    artifacts: [
      { type: "file", path: "tiers/30/designs_filtered.fasta", size: 64 },
      { type: "file", path: "tiers/50/designs_filtered.fasta", size: 64 },
    ],
  });
  assert.equal(dependency.blocked, false);
  assert.deepEqual(dependency.matchedPaths, ["tiers/50/designs_filtered.fasta"]);
});

test("workflowStudioDependencyStatus is skipped when rerun regenerates upstream outputs", () => {
  const dependency = workflowStudioDependencyStatus({
    targetStage: "novelty",
    requiredStart: "af2",
    artifacts: [],
  });
  assert.equal(dependency.required, false);
  assert.equal(dependency.blocked, false);
});

test("nextWorkflowStudioStage follows configured workflow nodes", () => {
  assert.equal(nextWorkflowStudioStage(["msa", "design", "af2"], "msa"), "design");
  assert.equal(nextWorkflowStudioStage(["msa", "design", "af2"], "af2"), "");
  assert.equal(
    nextWorkflowStudioStage(
      ["msa", "proteinmpnn_30", "soluprot_30", "af2_30", "proteinmpnn_50"],
      "af2_30"
    ),
    "proteinmpnn_50"
  );
});

test("workflowStudioExecutionTarget maps tier nodes to base stop_after and selected_tiers", () => {
  assert.deepEqual(workflowStudioExecutionTarget("novelty_70"), {
    nodeId: "novelty_70",
    baseStage: "novelty",
    stopAfter: "novelty",
    selectedTiers: [0.7],
    tierKey: "70",
    isTier: true,
  });
  assert.deepEqual(workflowStudioExecutionTarget("bioemu"), {
    nodeId: "bioemu",
    baseStage: "bioemu",
    stopAfter: "bioemu",
    selectedTiers: undefined,
    tierKey: "",
    isTier: false,
  });
});

test("resolveWorkflowStudioStageForSession keeps legacy base sessions aligned with live tier stages", () => {
  assert.equal(
    resolveWorkflowStudioStageForSession(["msa", "rfd3", "bioemu", "design", "soluprot", "af2"], "af2_30"),
    "af2"
  );
  assert.equal(
    resolveWorkflowStudioStageForSession(["msa", "proteinmpnn_30", "soluprot_30", "af2_30"], "af2"),
    "af2_30"
  );
  assert.equal(
    resolveWorkflowStudioStageForSession(["msa", "proteinmpnn_30", "soluprot_30", "af2_30"], "af2_30"),
    "af2_30"
  );
});

test("workflowStudioRetainedArtifactPath only preserves explicit artifact selections", () => {
  const artifacts = [
    { type: "file", path: "tiers/30/af2_scores.json" },
    { type: "file", path: "tiers/30/af2/ranked_0.pdb" },
  ];
  assert.equal(workflowStudioRetainedArtifactPath(artifacts, ""), "");
  assert.equal(
    workflowStudioRetainedArtifactPath(artifacts, "tiers/30/af2/ranked_0.pdb"),
    "tiers/30/af2/ranked_0.pdb"
  );
  assert.equal(workflowStudioRetainedArtifactPath(artifacts, "tiers/70/af2/ranked_0.pdb"), "");
});

test("residuePickerControlState enables FASTA-based AF2 runs when sequence input is present", () => {
  assert.deepEqual(
    residuePickerControlState({
      targetPdbText: "",
      targetFastaText: ">target\nACDEFG",
      rfd3PdbText: "",
      selectedRunId: "run-1",
      busy: false,
    }),
    {
      canLoadTarget: false,
      canLoadRfd3: false,
      canLoadRun: true,
      canRunAf2: true,
    }
  );
  assert.deepEqual(
    residuePickerControlState({
      targetPdbText: "ATOM",
      targetFastaText: ">target\nACDEFG",
      rfd3PdbText: "ATOM",
      selectedRunId: "run-1",
      busy: true,
    }),
    {
      canLoadTarget: false,
      canLoadRfd3: false,
      canLoadRun: false,
      canRunAf2: false,
    }
  );
});

test("upsertWorkflowStudioStageStatus only reports changes when state or run id actually changed", () => {
  const stageStates = {};
  const stageRunIds = {};
  assert.equal(upsertWorkflowStudioStageStatus(stageStates, stageRunIds, "af2", "running", "run-1"), true);
  assert.deepEqual(stageStates, { af2: "running" });
  assert.deepEqual(stageRunIds, { af2: "run-1" });
  assert.equal(upsertWorkflowStudioStageStatus(stageStates, stageRunIds, "af2", "running", "run-1"), false);
  assert.equal(upsertWorkflowStudioStageStatus(stageStates, stageRunIds, "af2", "completed", "run-1"), true);
  assert.deepEqual(stageStates, { af2: "completed" });
  assert.deepEqual(stageRunIds, { af2: "run-1" });
  assert.equal(upsertWorkflowStudioStageStatus(stageStates, stageRunIds, "af2", "completed", "run-2"), true);
  assert.deepEqual(stageRunIds, { af2: "run-2" });
});

test("latestMeaningfulStatusFromEvents skips terminal done stages when recovering Studio state", () => {
  const status = latestMeaningfulStatusFromEvents(
    [
      JSON.stringify({
        kind: "status",
        run_id: "admin_20260310_065409_2f2c2372",
        stage: "af2_70",
        state: "completed",
        updated_at: "2026-03-12 01:09:20",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "admin_20260310_065409_2f2c2372",
        stage: "done",
        state: "completed",
        updated_at: "2026-03-12 01:09:20",
      }),
    ].join("\n"),
    "admin_20260310_065409_2f2c2372"
  );
  assert.equal(status?.stage, "af2_70");
  assert.equal(status?.state, "completed");
});

test("latestMeaningfulStatusFromEvents falls back to the latest status when only terminal events exist", () => {
  const status = latestMeaningfulStatusFromEvents(
    JSON.stringify({
      kind: "status",
      run_id: "run-1",
      stage: "done",
      state: "completed",
      updated_at: "2026-03-12 01:09:20",
    }),
    "run-1"
  );
  assert.equal(status?.stage, "done");
  assert.equal(status?.state, "completed");
});

test("latestWorkflowStudioCompletedNodesFromEvents only keeps the latest reused run segment", () => {
  const nodes = latestWorkflowStudioCompletedNodesFromEvents(
    [
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "af2_70",
        state: "completed",
        updated_at: "2026-03-12 01:09:20",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "done",
        state: "completed",
        updated_at: "2026-03-12 01:09:20",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "init",
        state: "running",
        updated_at: "2026-03-12 01:42:15",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "rfd3",
        state: "completed",
        updated_at: "2026-03-12 01:42:15",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "proteinmpnn_50",
        state: "completed",
        updated_at: "2026-03-12 01:45:48",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "soluprot_50",
        state: "completed",
        updated_at: "2026-03-12 01:45:48",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "af2_50",
        state: "completed",
        updated_at: "2026-03-12 01:45:48",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "novelty_50",
        state: "completed",
        updated_at: "2026-03-12 01:45:48",
      }),
      JSON.stringify({
        kind: "status",
        run_id: "run-1",
        stage: "done",
        state: "completed",
        updated_at: "2026-03-12 01:45:48",
      }),
    ].join("\n"),
    "run-1"
  );
  assert.deepEqual(nodes, ["rfd3", "proteinmpnn_50", "soluprot_50", "af2_50", "novelty_50"]);
});

test("latestWorkflowStudioCompletedNodesFromEvents can recover AF2 for base-node Studio sessions", () => {
  const resolved = Array.from(
    new Set(
      latestWorkflowStudioCompletedNodesFromEvents(
        [
          JSON.stringify({
            kind: "status",
            run_id: "admin_20260310_065409_2f2c2372",
            stage: "init",
            state: "running",
            updated_at: "2026-03-12 01:42:15",
          }),
          JSON.stringify({
            kind: "status",
            run_id: "admin_20260310_065409_2f2c2372",
            stage: "proteinmpnn_30",
            state: "completed",
            updated_at: "2026-03-12 01:45:48",
          }),
          JSON.stringify({
            kind: "status",
            run_id: "admin_20260310_065409_2f2c2372",
            stage: "soluprot_30",
            state: "completed",
            updated_at: "2026-03-12 01:45:48",
          }),
          JSON.stringify({
            kind: "status",
            run_id: "admin_20260310_065409_2f2c2372",
            stage: "af2_30",
            state: "completed",
            updated_at: "2026-03-12 01:45:48",
          }),
          JSON.stringify({
            kind: "status",
            run_id: "admin_20260310_065409_2f2c2372",
            stage: "novelty_30",
            state: "completed",
            updated_at: "2026-03-12 01:45:48",
          }),
          JSON.stringify({
            kind: "status",
            run_id: "admin_20260310_065409_2f2c2372",
            stage: "done",
            state: "completed",
            updated_at: "2026-03-12 01:45:48",
          }),
        ].join("\n"),
        "admin_20260310_065409_2f2c2372"
      )
        .map((stage) =>
          resolveWorkflowStudioStageForSession(["msa", "rfd3", "bioemu", "design", "soluprot", "af2", "novelty"], stage, "")
        )
        .filter(Boolean)
    )
  );
  assert.deepEqual(resolved, ["design", "soluprot", "af2", "novelty"]);
});

test("shouldPollRunForTabChange polls immediately when entering Studio with a session run", () => {
  assert.equal(
    shouldPollRunForTabChange({
      nextTab: "studio",
      studioRunId: "admin_20260310_065409_2f2c2372",
      currentRunId: "",
      autoPollEnabled: false,
    }),
    true
  );
  assert.equal(
    shouldPollRunForTabChange({
      nextTab: "monitor",
      studioRunId: "",
      currentRunId: "admin_20260310_065409_2f2c2372",
      autoPollEnabled: false,
    }),
    false
  );
  assert.equal(
    shouldPollRunForTabChange({
      nextTab: "monitor",
      studioRunId: "",
      currentRunId: "admin_20260310_065409_2f2c2372",
      autoPollEnabled: true,
    }),
    true
  );
});

test("workflowStudioSessionRunKey groups duplicate sessions by linked run id", () => {
  assert.equal(workflowStudioSessionRunKey({ head_run_id: "run-head" }), "run-head");
  assert.equal(workflowStudioSessionRunKey({ pending: { run_id: "run-pending" } }), "run-pending");
  assert.equal(workflowStudioSessionRunKey({ source_run_id: "run-source" }), "run-source");
  assert.equal(
    workflowStudioSessionRunKey({
      history: [{ run_id: "run-history" }, { run_id: "run-older" }],
    }),
    "run-history"
  );
  assert.equal(
    workflowStudioSessionRunKey({
      stage_run_ids: { msa: "run-stage", af2: "run-stage" },
    }),
    "run-stage"
  );
  assert.equal(
    workflowStudioSessionRunKey({
      stage_run_ids: { msa: "run-a", af2: "run-b" },
    }),
    ""
  );
});

test("workflowStudioSessionIdForRun finds a linked studio session for a run", () => {
  const sessions = [
    { session_id: "studio-head", head_run_id: "run-head" },
    { session_id: "studio-source", source_run_id: "run-source" },
    { session_id: "studio-history", history: [{ run_id: "run-history" }] },
    { session_id: "studio-stage", stage_run_ids: { af2: "run-stage" } },
  ];

  assert.equal(workflowStudioSessionIdForRun(sessions, "run-head"), "studio-head");
  assert.equal(workflowStudioSessionIdForRun(sessions, "run-source"), "studio-source");
  assert.equal(workflowStudioSessionIdForRun(sessions, "run-history"), "studio-history");
  assert.equal(workflowStudioSessionIdForRun(sessions, "run-stage"), "studio-stage");
  assert.equal(workflowStudioSessionIdForRun(sessions, "run-missing"), "");
});

test("buildWorkflowProgressContext prefers workflow nodes over partial rerun bounds", () => {
  assert.deepEqual(
    buildWorkflowProgressContext({
      nodes: ["msa", "rfd3", "bioemu", "design", "soluprot", "af2", "novelty"],
      tierKeys: [0.3, 0.5, 0.7],
      wtCompare: true,
    }),
    {
      tierKeys: ["30", "50", "70"],
      noveltyEnabled: true,
      stopAfter: "novelty",
      startFrom: "msa",
      wtCompare: true,
    }
  );
});

test("normalizeWorkflowStudioPayloadForComparison ignores equivalent RFD3 seed PDB text", () => {
  const pdbText = [
    "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C",
    "END",
  ].join("\n");
  const previousPayload = normalizeWorkflowStudioPayloadForComparison(
    {
      target_pdb: pdbText,
      rfd3_input_pdb: `${pdbText}   \n`,
      rfd3_contig: "A1-3",
    },
    { nodes: ["msa", "rfd3", "novelty"] }
  );
  const nextPayload = normalizeWorkflowStudioPayloadForComparison(
    {
      target_input: pdbText,
      rfd3_contig: "A1-3",
    },
    { nodes: ["msa", "rfd3", "novelty"] }
  );

  assert.deepEqual(workflowStudioChangedFields(previousPayload, nextPayload), []);
  assert.equal(
    minimumWorkflowStudioStartStage({
      previousPayload,
      nextPayload,
      targetStage: "novelty",
    }),
    "novelty"
  );
});

test("normalizeWorkflowStudioPayloadForComparison preserves visible binder partial_t fields", () => {
  const normalized = normalizeWorkflowStudioPayloadForComparison(
    {
      target_input: "ATOM      1  CA  ALA A   1       0.0   0.0   0.0  1.00 20.00           C\nEND\n",
      rfd3_mode: "binder",
      rfd3_contig: "A1-3",
      rfd3_partial_t: 8,
      rfd3_hotspots: "A10",
    },
    { nodes: ["msa", "rfd3", "novelty"] }
  );
  assert.equal(normalized.rfd3_mode, "binder");
  assert.equal(normalized.rfd3_partial_t, 8);
  assert.equal(normalized.rfd3_contig, "A1-3");
  assert.equal(normalized.rfd3_hotspots, "A10");
});

test("normalizeWorkflowStudioPayloadForComparison drops advanced-only-hidden partial_t", () => {
  const normalized = normalizeWorkflowStudioPayloadForComparison(
    {
      target_input: "ATOM      1  CA  ALA A   1       0.0   0.0   0.0  1.00 20.00           C\nEND\n",
      rfd3_mode: "advanced",
      rfd3_partial_t: 8,
      rfd3_inputs_text: "{\"spec-1\":{\"input\":\"input.pdb\"}}",
    },
    { nodes: ["msa", "rfd3", "novelty"] }
  );
  assert.equal(normalized.rfd3_mode, "advanced");
  assert.equal(normalized.rfd3_partial_t, undefined);
  assert.equal(normalized.rfd3_inputs_text, "{\"spec-1\":{\"input\":\"input.pdb\"}}");
});

test("progressStepsForRequest narrows novelty reruns to WT baseline and novelty", () => {
  assert.deepEqual(
    progressStepsForRequest({
      mode: "pipeline",
      startFrom: "novelty",
      stopAfter: "novelty",
      noveltyEnabled: true,
      wtCompare: true,
    }),
    ["wt", "novelty", "done"]
  );
});

test("progressUnitsForRequest expands partial reruns across tiers without replaying skipped stages", () => {
  assert.deepEqual(
    progressUnitsForRequest({
      mode: "pipeline",
      startFrom: "novelty",
      stopAfter: "novelty",
      noveltyEnabled: true,
      wtCompare: true,
      tierKeys: ["30", "50", "70"],
    }),
    [
      { step: "wt" },
      { step: "novelty", tierKey: "30" },
      { step: "novelty", tierKey: "50" },
      { step: "novelty", tierKey: "70" },
      { step: "done" },
    ]
  );
  assert.deepEqual(
    progressUnitsForRequest({
      mode: "pipeline",
      startFrom: "design",
      stopAfter: "design",
      noveltyEnabled: true,
      tierKeys: ["30", "50"],
    }),
    [
      { step: "design", tierKey: "30" },
      { step: "design", tierKey: "50" },
      { step: "done" },
    ]
  );
});

test("shouldReuseSelectedRun requires explicit continue toggle and partial stage", () => {
  assert.equal(
    shouldReuseSelectedRun({
      mode: "pipeline",
      startFrom: "af2",
      continueInSelectedRun: true,
      selectedRunId: "run-1",
    }),
    true
  );
  assert.equal(
    shouldReuseSelectedRun({
      mode: "pipeline",
      startFrom: "msa",
      continueInSelectedRun: true,
      selectedRunId: "run-1",
    }),
    false
  );
  assert.equal(
    shouldReuseSelectedRun({
      mode: "pipeline",
      startFrom: "af2",
      continueInSelectedRun: false,
      selectedRunId: "run-1",
    }),
    false
  );
});

test("buildSetupDraftFromRequest prepares file answers and metadata", () => {
  const draft = buildSetupDraftFromRequest({
    target_pdb: "ATOM      1  N",
    target_fasta: ">q1\nACDE",
    rfd3_input_pdb: "ATOM      1  CA",
    start_from: "AF2",
    stop_after: "novelty",
    design_chains: ["A"],
  });
  assert.equal(draft.mode, "pipeline");
  assert.equal(draft.answers.target_input, "ATOM      1  N");
  assert.equal(draft.answers.target_pdb, "ATOM      1  N");
  assert.equal(draft.answers.target_fasta, ">q1\nACDE");
  assert.equal(draft.answers.rfd3_input_pdb, "ATOM      1  CA");
  assert.equal(draft.answers.start_from, "af2");
  assert.equal(draft.answers.stop_after, "novelty");
  assert.deepEqual(draft.answers.design_chains, ["A"]);
  assert.equal(draft.answerMeta.target_input.fileName, "request.json:target_pdb");
  assert.equal(draft.answerMeta.rfd3_input_pdb.fileName, "request.json:rfd3_input_pdb");
});

test("buildSetupDraftFromRequest drops redundant rfd3_input_pdb when it matches target_pdb", () => {
  const draft = buildSetupDraftFromRequest({
    target_pdb: "ATOM      1  N",
    rfd3_input_pdb: "ATOM      1  N",
    rfd3_contig: "A1-20",
  });
  assert.equal(draft.answers.target_input, "ATOM      1  N");
  assert.equal(draft.answers.rfd3_input_pdb, undefined);
  assert.equal(draft.answerMeta.rfd3_input_pdb, undefined);
  assert.equal(draft.answers.rfd3_contig, "A1-20");
});

test("normalizeSetupDraftForFreshRun resets pipeline start_from to msa", () => {
  const draft = {
    mode: "pipeline",
    answers: {
      start_from: "af2",
      stop_after: "novelty",
      design_chains: ["A"],
    },
    answerMeta: {
      target_input: { fileName: "request.json:target_pdb" },
    },
  };
  const normalized = normalizeSetupDraftForFreshRun(draft);
  assert.equal(normalized.mode, "pipeline");
  assert.equal(normalized.answers.start_from, "msa");
  assert.equal(normalized.answers.stop_after, "novelty");
  assert.deepEqual(normalized.answers.design_chains, ["A"]);
  assert.equal(normalized.answerMeta.target_input.fileName, "request.json:target_pdb");
  assert.equal(draft.answers.start_from, "af2");
});

test("normalizeSetupDraftForFreshRun leaves non-pipeline modes unchanged", () => {
  const draft = {
    mode: "af2",
    answers: {
      target_fasta: ">seq\nAAAA",
      af2_provider: "colabfold",
    },
    answerMeta: {},
  };
  const normalized = normalizeSetupDraftForFreshRun(draft);
  assert.equal(normalized.mode, "af2");
  assert.equal(normalized.answers.target_fasta, ">seq\nAAAA");
  assert.equal(normalized.answers.af2_provider, "colabfold");
  assert.equal(normalized.answers.start_from, undefined);
});

test("buildSetupDraftFromRequest maps diffdock ligand metadata", () => {
  const draft = buildSetupDraftFromRequest({
    target_pdb: "ATOM      1  N",
    diffdock_ligand_smiles: "CCO",
  });
  assert.equal(draft.mode, "diffdock");
  assert.equal(draft.answers.diffdock_ligand, "CCO");
  assert.equal(draft.answers.diffdock_use, "use");
  assert.equal(draft.answerMeta.diffdock_ligand.fileName, "request.json:diffdock_ligand.smiles");
});

test("buildSetupDraftFromRequest preserves distinct BioEmu generated and return counts", () => {
  const draft = buildSetupDraftFromRequest({
    target_pdb: "ATOM      1  N",
    stop_after: "bioemu",
    bioemu_use: true,
    bioemu_num_samples: 20,
    bioemu_max_return_structures: 10,
  });
  assert.equal(draft.mode, "bioemu");
  assert.equal(draft.answers.bioemu_num_samples, 20);
  assert.equal(draft.answers.bioemu_max_return_structures, 10);
});

test("inferRequestRunMode keeps pipeline runs with stop_after af2 in pipeline mode", () => {
  const mode = inferRequestRunMode({
    stop_after: "af2",
    af2_provider: "colabfold",
    protein_pdb: null,
    num_seq_per_tier: 2,
    rfd3_max_return_designs: 10,
    mmseqs_target_db: "uniref90",
    wt_compare: true,
  });
  assert.equal(mode, "pipeline");
});

test("inferRequestRunMode ignores empty diffdock placeholders", () => {
  const mode = inferRequestRunMode({
    stop_after: "af2",
    protein_pdb: null,
    diffdock_ligand_smiles: "",
    diffdock_ligand_sdf: null,
    af2_provider: "colabfold",
    num_seq_per_tier: 2,
    rfd3_max_return_designs: 10,
  });
  assert.equal(mode, "pipeline");
});

test("inferRequestRunMode keeps af2-only requests in af2 mode", () => {
  const mode = inferRequestRunMode({
    stop_after: "af2",
    target_fasta: ">x\nAAAA",
    af2_provider: "colabfold",
    af2_model_preset: "auto",
    af2_db_preset: "full_dbs",
  });
  assert.equal(mode, "af2");
});

test("inferRequestRunMode preserves design-only mode for non-pipeline requests", () => {
  const mode = inferRequestRunMode({
    stop_after: "design",
    target_pdb: "ATOM      1  N",
    batch_size: 1,
    sampling_temp: 0.1,
  });
  assert.equal(mode, "design");
});

test("filterRunsByPrefix", () => {
  const runs = ["kbf_user_1", "other_2", "kbf_user_3"];
  assert.deepEqual(filterRunsByPrefix(runs, "kbf_user"), ["kbf_user_1", "kbf_user_3"]);
});

test("detectTargetKey", () => {
  assert.equal(detectTargetKey(">seq\nAAAA"), "target_fasta");
  assert.equal(detectTargetKey("ATOM      1  N"), "target_pdb");
  assert.equal(detectTargetKey("ACDEFGHIK"), "target_fasta");
});

test("DEFAULT_ARTIFACT_COMPARE_MODE prefers sequence diff", () => {
  assert.equal(DEFAULT_ARTIFACT_COMPARE_MODE, "sequence");
});

test("formatWtIdentitySummary shows difference count and identity percent", () => {
  assert.equal(
    formatWtIdentitySummary({
      wt_diff_count: 8,
      wt_compare_len: 10,
      wt_identity_pct: 20,
    }),
    "8/10 · identity 20.0%"
  );
});

test("buildStructureDiffLegend stays in structure language only", () => {
  const text = buildStructureDiffLegend({
    rmsd: 1.07,
    p90Distance: 1.39,
    commonCount: 221,
    lang: "en",
  });
  assert.match(text, /RMSD=1\.07A/);
  assert.match(text, /P90=1\.39A/);
  assert.doesNotMatch(text, /gap/i);
  assert.doesNotMatch(text, /WT.*Design/i);
});

test("buildCompareScopeDescription explains reference and candidate scope", () => {
  const text = buildCompareScopeDescription({
    leftMeta: { compareRole: "wt_colabfold" },
    rightMeta: { compareRole: "af2_candidate", tier: "30", backboneSource: "bioemu" },
    provider: "colabfold",
    lang: "en",
  });
  assert.match(text, /predicted wild-type reference/i);
  assert.match(text, /single candidate/i);
  assert.match(text, /Tier 0\.30/i);
});

test("buildCompareMetaTooltip explains hard-to-read compare metrics", () => {
  const wtRmsd = buildCompareMetaTooltip("wtStructRmsd", { provider: "colabfold", lang: "ko" });
  const scope = buildCompareMetaTooltip("predScope", { provider: "colabfold", lang: "en" });
  assert.match(wtRmsd, /WT/i);
  assert.match(wtRmsd, /RMSD/i);
  assert.match(wtRmsd, /야생형|기준 구조/);
  assert.match(scope, /exact file|WT reference|tier\/backbone summary/i);
});

test("copilotIntentFromPrompt detects metric term questions", () => {
  assert.equal(copilotIntentFromPrompt("WT CF RMSD 이 무슨 의미야"), "term");
});

test("buildCopilotReply defines terms before snapshot dumping", () => {
  const text = buildCopilotReply({
    prompt: "WT CF RMSD 이 무슨 의미야",
    lang: "ko",
    snapshot: {
      runId: "admin_20260310_065409_2f2c2372",
      provider: "ColabFold",
      rows: [],
      compare: { ready: false },
    },
  });
  assert.match(text, /^WT CF RMSD는/);
  assert.doesNotMatch(text, /^Run /);
});

test("buildCopilotReply recommends top 3 rows when asked", () => {
  const text = buildCopilotReply({
    prompt: "최종 3종을 추천해줘",
    lang: "ko",
    snapshot: {
      runId: "admin_20260310_065409_2f2c2372",
      provider: "ColabFold",
      rows: [
        {
          seq_id: "bioemu_topology:2",
          source: "bioemu",
          score: 76.8,
          plddt: 89.0,
          rmsd: 1.78,
          wt_diff_count: 10,
          wt_compare_len: 229,
          wt_identity_pct: 95.6,
        },
        {
          seq_id: "rfd3_spec-1_0_model_0:1",
          source: "rfd3",
          score: 74.4,
          plddt: 87.5,
          rmsd: 1.55,
          wt_diff_count: 15,
          wt_compare_len: 229,
          wt_identity_pct: 93.4,
        },
        {
          seq_id: "bioemu_topology:5",
          source: "bioemu",
          score: 72.1,
          plddt: 86.3,
          rmsd: 1.92,
          wt_diff_count: 12,
          wt_compare_len: 229,
          wt_identity_pct: 94.8,
        },
      ],
      compare: { ready: false },
    },
  });
  assert.match(text, /1\.\s+bioemu_topology:2/);
  assert.match(text, /2\.\s+rfd3_spec-1_0_model_0:1/);
  assert.match(text, /3\.\s+bioemu_topology:5/);
});

test("aminoAcidPropertyInfo groups residues by chemistry", () => {
  assert.equal(aminoAcidPropertyInfo("D").group, "negative");
  assert.equal(aminoAcidPropertyInfo("W").group, "aromatic");
  assert.equal(aminoAcidPropertyInfo("G").group, "special");
});

test("classifyResidueExposure uses exposed atom area cutoff for surface/core and keeps interface", () => {
  const result = classifyResidueExposure([
    { chain: "A", resi: 1, exposedAreaMax: 18.2, interface: false },
    { chain: "A", resi: 2, exposedAreaMax: 0.8, interface: false },
    { chain: "A", resi: 3, exposedAreaMax: 12.4, interface: true },
  ], {
    surfaceAreaCutoff: DEFAULT_SURFACE_AREA_CUTOFF,
  });
  assert.deepEqual(result.surface, { A: [1, 3] });
  assert.deepEqual(result.core, { A: [2] });
  assert.deepEqual(result.interface, { A: [3] });
});

test("deriveResidueSpatialPresets reclassifies surface/core when cutoff changes", () => {
  const pdbText = "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C";

  const defaultResult = deriveResidueSpatialPresets(pdbText, {
    surfaceAreaCutoff: DEFAULT_SURFACE_AREA_CUTOFF,
  });
  assert.deepEqual(defaultResult.surface, { A: [1] });
  assert.deepEqual(defaultResult.core, {});

  const strictResult = deriveResidueSpatialPresets(pdbText, {
    surfaceAreaCutoff: 200,
  });
  assert.deepEqual(strictResult.surface, {});
  assert.deepEqual(strictResult.core, { A: [1] });
});

test("mergeResidueSelectionMaps unions preset and manual picks", () => {
  assert.deepEqual(
    mergeResidueSelectionMaps(
      { A: [1, 3] },
      { A: [2], B: [4] }
    ),
    { A: [1, 2, 3], B: [4] }
  );
});

test("toggleResidueSelectionMaps removes preset residues on second click", () => {
  assert.equal(selectionMapContains({ A: [1, 2], B: [4] }, { A: [1], B: [4] }), true);
  assert.equal(selectionMapContains({ A: [1] }, { A: [1, 2] }), false);

  assert.deepEqual(
    toggleResidueSelectionMaps(
      { A: [1, 2, 9], B: [4] },
      { A: [1, 2], B: [4] }
    ),
    { A: [9] }
  );

  assert.deepEqual(
    toggleResidueSelectionMaps(
      { A: [1] },
      { A: [1, 2] }
    ),
    { A: [1, 2] }
  );
});

test("resolveResidueSelectionMaps keeps overlapping presets and manual exclusions separate", () => {
  assert.deepEqual(
    resolveResidueSelectionMaps({
      activePresetIds: ["core", "interface"],
      presetSelectionsById: {
        core: { A: [2, 3, 4] },
        interface: { A: [4, 5] },
      },
      manualSelection: { A: [9] },
      excludedSelection: { A: [4] },
    }),
    { A: [2, 3, 5, 9] }
  );
});

test("clearResiduePickerSelectionState clears active picks without dropping other picker state", () => {
  assert.deepEqual(
    clearResiduePickerSelectionState({
      pdbText: "ATOM ...",
      sourceKey: "target_input",
      selection: { A: [5] },
      manualSelection: { A: [5] },
      excludedSelection: { A: [6] },
      activePresetIds: ["core"],
      notice: "selected",
    }),
    {
      pdbText: "ATOM ...",
      sourceKey: "target_input",
      selection: {},
      manualSelection: {},
      excludedSelection: {},
      activePresetIds: [],
      notice: "",
    }
  );
});

test("resolveResiduePickerSelectionState does not resurrect a preset after it is toggled off", () => {
  assert.deepEqual(
    resolveResiduePickerSelectionState({
      selectionFallback: { A: [10, 11] },
      manualSelection: {},
      excludedSelection: {},
      activePresetIds: [],
      presetSelectionsById: {
        core: { A: [10, 11] },
      },
      allowFallback: false,
    }),
    {
      manualSelection: {},
      excludedSelection: {},
      activePresetIds: [],
      selection: {},
    }
  );
});

test("buildSequenceSelectionTracks chunks chains into numbered sequence rows", () => {
  const tracks = buildSequenceSelectionTracks(
    { A: "ACDEFGHIKLMN" },
    { A: [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22] },
    { lineLength: 5, labelEvery: 2 }
  );
  assert.equal(tracks.length, 1);
  assert.equal(tracks[0].rows.length, 3);
  assert.equal(tracks[0].rows[0].startResi, 11);
  assert.equal(tracks[0].rows[0].endResi, 15);
  assert.deepEqual(
    tracks[0].rows[0].cells.map((cell) => cell.resi),
    [11, 12, 13, 14, 15]
  );
  assert.deepEqual(
    tracks[0].rows[0].labels.map((label) => label.value),
    ["11", "12", "14", "15"]
  );
  assert.equal(tracks[0].rows[2].startResi, 21);
  assert.equal(tracks[0].rows[2].endResi, 22);
});

test("conservedTierPresetState disables when conservation preview is missing", () => {
  const state = conservedTierPresetState(null, 0.3, "en");
  assert.equal(state.enabled, false);
  assert.match(state.reason, /conservation/i);
});

test("availableConservedTierPresetKeys only returns tiers with preview data", () => {
  assert.deepEqual(availableConservedTierPresetKeys(null), []);
  assert.deepEqual(
    availableConservedTierPresetKeys({
      tiers: {
        30: [1, 2],
        70: [9],
      },
    }),
    ["30", "70"]
  );
});

test("buildDetachedResiduePickerStoragePayload strips bulky structure text before storage", () => {
  const payload = buildDetachedResiduePickerStoragePayload({
    token: "picker_tab_20260313_064037_03031a3f",
    context: "studio",
    sessionId: "admin_studio_20260313_063140_82003e07",
    activeStage: "design",
    targetPdbText: "ATOM      1  N   GLY A   1",
    targetFastaText: ">A\nACDEFG",
    rfd3PdbText: "ATOM      1  CA  ALA A   1",
    selectedRunId: "admin_20260310_065409_2f2c2372",
    pickerProvider: "colabfold",
    snapshot: {
      pdbText: "ATOM      1  N   GLY A   1",
      sourceLabel: "loaded target",
      sourceKey: "target_input",
      selection: { A: [5, 9] },
      manualSelection: { A: [5, 9] },
      excludedSelection: {},
      activePresetIds: ["surface"],
      structureColorMode: "chain",
      conservationPreview: { tiers: { 30: [5, 9] } },
    },
  });

  assert.equal(payload.targetPdbText, "");
  assert.equal(payload.rfd3PdbText, "");
  assert.equal(payload.targetFastaText, ">A\nACDEFG");
  assert.equal(payload.snapshot.pdbText, "");
  assert.equal(payload.snapshot.sourceLabel, "");
  assert.equal(payload.snapshot.sourceKey, "");
  assert.deepEqual(payload.snapshot.selection, { A: [5, 9] });
  assert.deepEqual(payload.snapshot.activePresetIds, ["surface"]);
});

test("buildDetachedResiduePickerResultStoragePayload strips bulky popup result fields before storage fallback", () => {
  const payload = buildDetachedResiduePickerResultStoragePayload({
    token: "picker_tab_20260313_064037_03031a3f",
    context: "studio",
    sessionId: "admin_studio_20260313_063140_82003e07",
    mappedSelection: { A: [5, 9] },
    selectedCount: 2,
    snapshot: {
      pdbText: "ATOM      1  N   GLY A   1",
      sourceLabel: "loaded target",
      sourceKey: "target_input",
      selection: { A: [58, 62] },
      manualSelection: { A: [58, 62] },
      excludedSelection: {},
      activePresetIds: ["surface"],
    },
    predictedResult: {
      outRunId: "tmp_af2_run",
      selectedPath: "af2/ranked_0.pdb",
      selectedPdb: "ATOM      1  N   GLY A   1",
      fastaText: ">A\nACDEFG",
    },
  });

  assert.equal(payload.snapshot.pdbText, "");
  assert.equal(payload.snapshot.sourceLabel, "");
  assert.equal(payload.snapshot.sourceKey, "");
  assert.deepEqual(payload.snapshot.selection, { A: [58, 62] });
  assert.equal(payload.predictedResult.selectedPdb, "");
  assert.equal(payload.predictedResult.fastaText, ">A\nACDEFG");
});

test("queryPositionsToResidueSelectionMap maps fixed_positions_extra back to residue ids", () => {
  assert.deepEqual(
    queryPositionsToResidueSelectionMap(
      { A: [1, 3], B: [2] },
      {
        A: [58, 62, 74],
        B: [101, 102, 103],
      }
    ),
    {
      A: [58, 74],
      B: [102],
    }
  );
});

test("buildPopupWindowFeatures requests a centered resizable popup window", () => {
  const features = buildPopupWindowFeatures({
    screenX: 100,
    screenY: 80,
    outerWidth: 1600,
    outerHeight: 1200,
    availWidth: 1920,
    availHeight: 1080,
  });

  assert.match(features, /popup=yes/);
  assert.match(features, /resizable=yes/);
  assert.match(features, /scrollbars=yes/);
  assert.match(features, /width=1600/);
  assert.match(features, /height=950/);
  assert.match(features, /left=100/);
  assert.match(features, /top=205/);
});

test("openPopupWindow bootstraps a blank popup before navigating to the target url", () => {
  const calls = [];
  const popup = {
    location: {
      replace(url) {
        this.url = url;
      },
    },
    focusCalled: false,
    focus() {
      this.focusCalled = true;
    },
  };
  const opened = openPopupWindow({
    open: (url, name, features) => {
      calls.push({ url, name, features });
      return popup;
    },
    url: "https://example.test/picker?token=abc",
    name: "picker_popup",
    features: "popup=yes,width=1200",
  });

  assert.equal(opened, popup);
  assert.deepEqual(calls, [{ url: "", name: "picker_popup", features: "popup=yes,width=1200" }]);
  assert.equal(popup.location.url, "https://example.test/picker?token=abc");
  assert.equal(popup.focusCalled, true);
});

test("buildResiduePickerViewerLegendLines describes color mode and selection", () => {
  assert.deepEqual(
    buildResiduePickerViewerLegendLines({ colorMode: "secondary", lang: "en" }),
    [
      "Cartoon view",
      "Base colors: secondary structure",
      "Selected residue: orange",
      "Hover a residue to inspect it",
    ]
  );
});

test("buildCompareViewerLegendLines explains structure diff colors", () => {
  assert.deepEqual(
    buildCompareViewerLegendLines({ compareMode: "structure", lang: "en" }),
    [
      "Gray: aligned backbone",
      "Amber: 1.5-3.0A shift",
      "Red: >3.0A shift",
      "Teal: selected residue",
    ]
  );
});

test("buildResiduePickerHoverText summarizes residue annotations", () => {
  const text = buildResiduePickerHoverText({
    chain: "A",
    resi: 58,
    resn: "TYR",
    selected: true,
    exposureClass: "core",
    interfaceHit: true,
    lang: "en",
  });
  assert.match(text, /A:58 TYR/);
  assert.match(text, /selected/i);
  assert.match(text, /core/i);
  assert.match(text, /interface/i);
});
