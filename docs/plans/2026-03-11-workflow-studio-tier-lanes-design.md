# Workflow Studio Tier Lanes Design

## Problem

Workflow Studio currently exposes a linear stage list (`msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty`), but the backend already executes `design/soluprot/af2/novelty` per conservation tier. The result is misleading: clicking `design` in Studio stops after ProteinMPNN for every tier, while users expect to control and inspect tier-specific downstream lanes.

## Goals

- Keep the existing pipeline request/response flow working exactly as it does today when Studio is not involved.
- Let Workflow Studio represent tier lanes explicitly from ProteinMPNN onward.
- Let Studio run only the selected lane (`0.30`, `0.50`, or `0.70`) without forcing the backend to process all tiers.
- Preserve current outputs and run layout when `selected_tiers` is not provided.

## Non-goals

- Replacing the existing pipeline stage model everywhere in Setup, Monitor, or Analyze.
- Changing the output directory schema for normal pipeline runs.
- Refactoring tier execution into a new backend DAG engine.

## Options Considered

### 1. UI-only tier lanes

Show `proteinmpnn_30`, `soluprot_30`, and similar nodes in the UI, but keep backend requests unchanged.

This is not sufficient. The backend would still execute every tier because the only execution controls are `start_from` and `stop_after`.

### 2. Global tier-aware stage model

Replace the base stage model everywhere with lane-aware stage ids.

This would solve the Studio issue, but it is too invasive. Setup, Monitor, partial rerun validation, and many artifact helpers currently assume the base stage list and do not need to change for this feature.

### 3. Recommended: workflow-only lane ids plus optional backend tier selection

Keep the base stage model as the system contract. Add an optional `selected_tiers` request field that only Workflow Studio uses. Let Studio expose lane ids such as `proteinmpnn_30` and map them back to base stages plus `selected_tiers=[0.3]` when launching or rerunning a step.

This keeps the backend additive, keeps existing pipeline runs unchanged, and gives Studio real tier-level control.

## Recommended Design

### Backend

- Add `selected_tiers: list[float] | None` to `PipelineRequest`.
- Parse and validate `selected_tiers` in the MCP tool layer.
- Derive `active_tiers` inside `PipelineRunner.run()`:
  - If `selected_tiers` is absent, use `conservation_tiers` unchanged.
  - If present, normalize and intersect with `conservation_tiers`.
  - Reject empty intersections.
- Use `active_tiers` instead of `request.conservation_tiers` in the tiered loops starting at mask-consensus outputs and continuing through ProteinMPNN, SoluProt, AF2, and novelty.
- Keep written `request.json` additive: `conservation_tiers` remains the configured set, `selected_tiers` records the Studio subset that was actually requested.
- Treat `selected_tiers` as rerun-scoping metadata, not as an upstream scientific input:
  - Ignore it in partial-rerun safety comparisons.
  - Allow cleanup helpers to remove only the selected tier directories from the chosen stage onward.

### Frontend

- Keep Setup and normal pipeline mode on the base stage model.
- Make Workflow Studio nodes tier-aware only from ProteinMPNN onward:
  - Shared upstream nodes: `msa`, `rfd3`, `bioemu`
  - Tier lanes: `proteinmpnn_30 -> soluprot_30 -> af2_30 -> novelty_30`, repeated for `50` and `70`
- Add helper functions in `frontend/lib/pipeline.js` to:
  - Parse lane ids into `{ baseStage, tierKey, selectedTiers }`
  - Return field ownership by base stage for lane ids
  - Compute workflow ordering and dependencies for lane ids
- Update Studio session logic in `frontend/app.js` to store lane ids directly in `nodes`, `active_stage`, `stage_states`, and `stage_run_ids`.
- When launching a tier node:
  - Send `stop_after=<base stage>`
  - Send `selected_tiers=[tier float]`
  - Keep `start_from` based on the base stage that must be recomputed
- Keep progress bars and status labels using existing backend tier stage names (`proteinmpnn_30`, `soluprot_30`, etc.).

### Testing

- Backend dry-run tests:
  - `selected_tiers=[0.5]` should only create `tiers/50/*` downstream outputs.
  - Partial rerun with a subset should not be rejected solely because `selected_tiers` changed.
- Tool parsing tests:
  - `pipeline_request_from_args()` accepts and normalizes `selected_tiers`.
- Frontend tests:
  - Workflow lane helpers parse and order `proteinmpnn_30` style ids correctly.
  - Studio run argument building maps a lane node to the right base `stop_after` and `selected_tiers`.

## Rollout Notes

- Existing saved runs and Workflow Studio sessions remain readable because base stages are still valid.
- If a saved session contains only base stages, Studio should keep handling it as before.
- New tier-lane sessions should be additive and should not change Setup, Monitor, or Analyze for non-Studio users.
