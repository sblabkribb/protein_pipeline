# RFD3 Target RMSD Gating Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reject off-target RFD3 backbones before design, resample until the accepted set reaches the requested count, and fail loudly if that cannot be achieved within the retry budget.

**Architecture:** Keep the existing exact-CA duplicate collapse, then add a second RFD3-stage gate that compares each unique backbone against the processed target reference on the design chain(s). Only accepted backbones propagate into `backbones/` and downstream design; rejected backbones remain in raw RFD3 artifacts and are counted in debug metadata. Retries request only the remaining deficit, up to a fixed retry budget, and raise a contract error if the accepted set is still short.

**Tech Stack:** Python dataclasses, pipeline orchestration in `pipeline.py`, unit tests in `test_pipeline_dry_run.py`.

---

### Task 1: Add failing tests for target-RMSD gated RFD3 refill

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`

**Steps:**
1. Add a non-dry-run RFD3 stub test where the first batch returns only off-target unique backbones and the retry batch returns target-like unique backbones.
2. Assert that the run stops at `rfd3`, emits exactly the requested accepted backbone count, rewrites `selected.pdb` to an accepted backbone, and records off-target rejects in `debug_summary.json`.
3. Run the new test and confirm it fails before implementation.

### Task 2: Add failing test for retry exhaustion

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`

**Steps:**
1. Add a non-dry-run RFD3 stub test where every sampled backbone stays off-target.
2. Assert that the run raises a loud RFD3 contract error instead of silently falling back or continuing with fewer backbones.
3. Run the new test and confirm it fails before implementation.

### Task 3: Implement RFD3 target-RMSD gate and refill logic

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/pipeline.py`

**Steps:**
1. Add request defaults for the RFD3 target-RMSD gate and retry budget.
2. Add helpers to resolve a processed target reference and design chain selection for the RFD3 gate before downstream chain strategy runs.
3. Extend RFD3 refresh/finalization to:
   - deduplicate exact duplicates,
   - reject unique backbones above the target-RMSD cutoff,
   - keep rejection metadata,
   - retry by requesting the remaining deficit,
   - promote the first accepted backbone to the selected RFD3 backbone,
   - fail with `BackboneContractError` when the accepted set stays short.
4. Persist accepted designs to `rfd3/designs`, keep all raw designs in `rfd3/raw_designs`, and enrich `debug_summary.json`.

### Task 4: Verify end-to-end test coverage

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`

**Steps:**
1. Run the new targeted tests until both are green.
2. Run the broader pipeline regression suite covering the touched behavior.
3. Check that the output artifacts and debug metadata match the intended accepted/rejected counts.
