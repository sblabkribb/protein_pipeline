# BioEmu Count Split and RFD3 Mode Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Separate BioEmu generated-sample count from final return count, while finishing the remaining RFD3 mode controls in Setup and Studio.

**Architecture:** Frontend state should carry independent `bioemu_num_samples` and `bioemu_max_return_structures` values all the way to the run payload instead of collapsing them. RFD3 mode gating should expose all mode-specific fields consistently, and `partial_t` should remain defaulted only for `local_diversify` while still being available as an explicit override in the other structured modes.

**Tech Stack:** Vanilla JS frontend, shared workflow payload helpers, Python pipeline orchestration, node:test, unittest.

---

### Task 1: Lock in the new BioEmu and RFD3 behavior with failing tests

**Files:**
- Modify: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`

**Step 1: Write failing tests**

- Replace the legacy BioEmu count-collapse assertions with tests that require:
  - `bioemu_num_samples` and `bioemu_max_return_structures` to remain distinct.
  - Workflow defaults to use `bioemu_num_samples=20`, `bioemu_max_return_structures=10`, `bioemu_filter_samples=true`.
  - `buildRunArguments()` to preserve both fields.
- Add tests that require `rfd3_partial_t` to remain visible/preserved for `legacy_contig`, `binder`, and `enzyme`, while still being removed for `advanced`.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: FAIL in the legacy BioEmu count-collapse assertions and RFD3 mode visibility assertions.

### Task 2: Preserve independent BioEmu counts through Setup, Studio, and payload building

**Files:**
- Modify: `/opt/protein_pipeline/frontend/lib/pipeline.js`
- Modify: `/opt/protein_pipeline/frontend/app.js`

**Step 1: Write minimal implementation**

- Replace the current `normalizeBioEmuCountFields()` collapse behavior with independent normalization for:
  - `bioemu_num_samples`
  - `bioemu_max_return_structures`
- Add a shared helper for recommended BioEmu generated counts:
  - if `filter_samples=true`, recommended generated count = `max_return * 2`
  - if `filter_samples=false`, recommended generated count = `max_return`
- Apply those defaults in Setup/Studio question metadata and workflow stage defaults.
- Expose both fields in Setup, Studio, and the final run payload.

**Step 2: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: PASS for the updated BioEmu tests.

### Task 3: Complete RFD3 mode field coverage

**Files:**
- Modify: `/opt/protein_pipeline/frontend/app.js`
- Modify: `/opt/protein_pipeline/frontend/lib/pipeline.js`

**Step 1: Write minimal implementation**

- Broaden `rfd3ModeUsesPartialT()` so `partial_t` is available for `local_diversify`, `legacy_contig`, `binder`, and `enzyme`.
- Keep `rfd3_inputs_text` exclusive to `advanced`.
- Ensure Setup RFD3 mode detail cards and Studio stage fields use the same visibility rules.
- Ensure payload filtering only strips `rfd3_partial_t` in `advanced`.

**Step 2: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: PASS for the updated RFD3 visibility tests.

### Task 4: Align backend defaults and BioEmu request shaping

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/tests/test_tools.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Write failing tests**

- Add tests that require `pipeline_request_from_args()` to choose recommended `bioemu_num_samples` when the caller omits it but provides `bioemu_max_return_structures`.
- Add a pipeline dry-run test that expects `num_samples=20`, `max_return_sample_pdbs=10`, and `min_return_sample_pdbs=10` when filtering is enabled and the return count is 10.

**Step 2: Write minimal implementation**

- Introduce a small helper in the backend for the recommended generated BioEmu sample count.
- Keep the strict `min_return_sample_pdbs = bioemu_max_return_structures` contract, but make sure the default generated count oversamples enough to support it.

**Step 3: Run tests to verify they pass**

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py tests/test_pipeline_dry_run.py`

Expected: PASS for the updated BioEmu parser and pipeline dry-run tests.

### Task 5: Final verification

**Files:**
- Test: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_tools.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Run verification**

Run: `node --test frontend/tests/pipeline.test.js`

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py tests/test_pipeline_dry_run.py`

**Step 2: Review**

- Confirm no legacy BioEmu count-collapse path remains.
- Confirm Setup/Studio both show completed RFD3 mode controls.
- Confirm backend keeps `min_return_sample_pdbs` strict while using oversampling defaults.
