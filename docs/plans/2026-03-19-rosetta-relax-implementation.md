# Rosetta Relax Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Rosetta FastRelax as a post-AF2 supplementary metric, show it in Analyze, and support relax-based cutoffs in advanced settings and Workflow Studio.

**Architecture:** Validate Rosetta runtime on the NPC first, then add a new backend `relax` stage that runs only on AF2-selected structures. Persist per-candidate relax artifacts and aggregate them through the existing `tools.py -> frontend` reporting path, while keeping relax out of hit-list weighting in the first iteration.

**Tech Stack:** Rosetta FastRelax, Docker and/or native Linux binaries, Python subprocess orchestration, pipeline dataclasses, vanilla JS frontend, unittest, node:test.

---

### Task 1: Record the operational decision and validate runtime prerequisites

**Files:**
- Modify: `/opt/protein_pipeline/docs/plans/2026-03-19-rosetta-relax-design.md`
- Create: `/opt/protein_pipeline/docs/plans/2026-03-19-rosetta-relax-validation.md`

**Steps**

1. Record the final license gate decision criteria in the design doc.
2. Add a short validation checklist doc for:
   - usage classification
   - Docker image pull
   - one-PDB FastRelax smoke test
3. Write exact operator commands for the first smoke test.
4. Do not install Rosetta permanently until the license path is confirmed.

### Task 2: Add Rosetta runtime configuration and client wrapper

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/config.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/app.py`
- Create: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/clients/rosetta_relax.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_rosetta_relax_client.py`

**Steps**

1. Add environment-backed Rosetta runtime config:
   - `ROSETTA_MODE`
   - `ROSETTA_BIN`
   - `ROSETTA_DATABASE`
   - `ROSETTA_DOCKER_IMAGE`
2. Implement a client that can run FastRelax in:
   - native mode
   - docker mode
3. Make the client write workdir-local inputs and parse `score.sc`.
4. Return normalized metrics:
   - `total_score`
   - `score_per_residue`
   - `delta_total_score`
5. Add unit tests for command construction and score parsing.

### Task 3: Extend request models, tool parsing, and stage ordering

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/router.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/tools.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_tools.py`

**Steps**

1. Add request fields:
   - `relax_enabled`
   - `relax_cutoff`
   - `relax_nstruct`
   - `relax_extra_flags`
2. Add prompt parsing and schema support for the new fields.
3. Insert `relax` into stage normalization and partial rerun field ownership.
4. Add parsing tests and schema tests for the new fields.

### Task 4: Implement the backend relax stage and artifacts

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/models.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`

**Steps**

1. Insert a new `relax` stage after AF2 and before novelty.
2. Run relax only for `af2_selected_ids`.
3. Use AF2 `ranked_0.pdb` as the relax input structure.
4. Persist candidate artifacts under `tiers/<tier>/relax/<seq_id>/`.
5. Write `tiers/<tier>/relax_scores.json`.
6. Add `TierResult` fields for relax summary and passed IDs.
7. Respect `relax_cutoff` against `score_per_residue`.
8. Add dry-run tests with a fake relax client and cached artifact behavior.

### Task 5: Aggregate relax metrics into analysis payloads

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/tools.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_tools.py`

**Steps**

1. Extend design summary aggregation to collect:
   - candidate relax scores
   - selected relax scores
   - relax pass counts
2. Extend per-tier compare rows with relax medians and pass rates.
3. Extend hit-list rows with passive relax fields.
4. Keep relax out of weighted score calculation in this pass.
5. Add tests for rows and summary payloads containing relax values.

### Task 6: Add Workflow Studio and Setup support for relax cutoffs

**Files:**
- Modify: `/opt/protein_pipeline/frontend/lib/pipeline.js`
- Modify: `/opt/protein_pipeline/frontend/app.js`
- Test: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`

**Steps**

1. Add a `relax` stage between `af2` and `novelty`.
2. Assign stage-owned fields:
   - `relax_enabled`
   - `relax_cutoff`
   - `relax_nstruct`
3. Add dependency checks so `relax` requires AF2 outputs.
4. Add question metadata, defaults, and validation for relax inputs.
5. Add frontend tests for stage ordering, defaults, and dependency resolution.

### Task 7: Show relax metrics in Analyze and exported details

**Files:**
- Modify: `/opt/protein_pipeline/frontend/index.html`
- Modify: `/opt/protein_pipeline/frontend/app.js`
- Test: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`

**Steps**

1. Add relax summary fields to Analyze tables and run-to-run compare.
2. Add a relax column to candidate tables and markdown details export.
3. Preserve current chart behavior; do not add a relax chart until the data shape settles.
4. Add frontend tests for Analyze rendering and details export.

### Task 8: Verify end-to-end behavior

**Files:**
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_rosetta_relax_client.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_tools.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`
- Test: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`

**Steps**

1. Run focused backend tests for Rosetta config, artifact generation, and aggregation.
2. Run focused frontend tests for Setup/Studio/Analyze changes.
3. If the license path is confirmed, run one manual Docker FastRelax smoke test on the NPC.
4. Restart `pipeline-mcp` only after tests pass and runtime config is present.
