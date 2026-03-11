# Workflow Studio Tier Lanes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add tier-aware execution lanes to Workflow Studio while keeping the existing pipeline behavior unchanged for normal runs.

**Architecture:** The backend gains an optional `selected_tiers` subset that scopes only tiered execution loops. The frontend keeps base stages for general pipeline flows and introduces lane ids only inside Workflow Studio, mapping them back to `{ stop_after, selected_tiers }` at launch time.

**Tech Stack:** Vanilla JS frontend, Python MCP backend, Node test runner, pytest

---

### Task 1: Add backend request parsing for optional tier subsets

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Test: `pipeline-mcp/tests/test_tools.py`

**Step 1: Write the failing test**

Add a test that calls `pipeline_request_from_args()` with `conservation_tiers=[0.3,0.5,0.7]` and `selected_tiers=[0.5]`, then asserts `req.selected_tiers == [0.5]`.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=pipeline-mcp/src python3 -m pytest pipeline-mcp/tests/test_tools.py -k selected_tiers -v`
Expected: FAIL because `PipelineRequest` has no `selected_tiers` field yet.

**Step 3: Write minimal implementation**

Add `selected_tiers` to `PipelineRequest`, parse it in `pipeline_request_from_args()`, and expose it in the tool schema.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=pipeline-mcp/src python3 -m pytest pipeline-mcp/tests/test_tools.py -k selected_tiers -v`
Expected: PASS

### Task 2: Scope tier execution and cleanup by `selected_tiers`

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Test: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Write the failing tests**

Add dry-run coverage for:
- `selected_tiers=[0.5]` only writing `tiers/50/*` after design/soluprot/af2.
- partial rerun safety not rejecting when only `selected_tiers` differs.

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=pipeline-mcp/src python3 -m pytest pipeline-mcp/tests/test_pipeline_dry_run.py -k "selected_tiers or partial_rerun" -v`
Expected: FAIL because tier loops still process every configured tier.

**Step 3: Write minimal implementation**

Compute normalized `active_tiers`, use them in tier loops, ignore `selected_tiers` in rerun comparisons, and allow cleanup helpers to clear only the requested subset.

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=pipeline-mcp/src python3 -m pytest pipeline-mcp/tests/test_pipeline_dry_run.py -k "selected_tiers or partial_rerun" -v`
Expected: PASS

### Task 3: Add lane-aware Workflow Studio helpers

**Files:**
- Modify: `frontend/lib/pipeline.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing tests**

Add tests for:
- parsing `proteinmpnn_30` into base stage `design` and `selected_tiers=[0.3]`
- `workflowStudioStageFields("soluprot_50")` returning `soluprot` fields
- `nextWorkflowStudioStage()` respecting tier lane order

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: FAIL because Workflow Studio helpers only know base stages.

**Step 3: Write minimal implementation**

Add lane parsing helpers, lane-aware node ordering, field mapping, dependency checks, and request argument mapping for Workflow Studio.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: PASS

### Task 4: Wire lane ids into Workflow Studio session execution

**Files:**
- Modify: `frontend/app.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing tests**

Add tests that simulate a Workflow Studio lane launch and assert the generated run args include:
- `stop_after` set to the base stage
- `selected_tiers` set to the chosen tier
- unchanged behavior for non-lane workflow nodes

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: FAIL because Studio currently sends only base `stop_after`.

**Step 3: Write minimal implementation**

Update Studio node normalization, stage state tracking, preview/run argument building, and recovery logic so lane ids are preserved in the session but mapped correctly for backend calls.

**Step 4: Run tests to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: PASS

### Task 5: Verify the integrated behavior

**Files:**
- Modify: none
- Test: `frontend/tests/pipeline.test.js`
- Test: `pipeline-mcp/tests/test_tools.py`
- Test: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Run focused verification**

Run: `node --check frontend/app.js`
Expected: PASS

Run: `node --test frontend/tests/pipeline.test.js`
Expected: PASS

Run: `PYTHONPATH=pipeline-mcp/src python3 -m pytest pipeline-mcp/tests/test_tools.py -k "selected_tiers or workflow_session" -v`
Expected: PASS

Run: `PYTHONPATH=pipeline-mcp/src python3 -m pytest pipeline-mcp/tests/test_pipeline_dry_run.py -k "selected_tiers or novelty_stage" -v`
Expected: PASS

**Step 2: Commit**

```bash
git add docs/plans/2026-03-11-workflow-studio-tier-lanes-design.md docs/plans/2026-03-11-workflow-studio-tier-lanes-implementation.md frontend/lib/pipeline.js frontend/app.js frontend/tests/pipeline.test.js pipeline-mcp/src/pipeline_mcp/models.py pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/src/pipeline_mcp/pipeline.py pipeline-mcp/tests/test_tools.py pipeline-mcp/tests/test_pipeline_dry_run.py
git commit -m "feat: add tier-aware workflow studio lanes"
```
