# RFD3 Auto Local Diversify Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make auto RFD3 mode treat PDB-input contig runs as local_diversify semantics so the first contig residue is sent as `unindex` and `select_fixed_atoms`, while the transmitted contig starts at the next residue.

**Architecture:** Keep explicit RFD3 modes unchanged and only alter auto-mode inference. Update both backend and frontend auto-mode resolution so they agree on mode selection and on deriving shifted contig defaults from either the user-provided contig or the inferred chain range.

**Tech Stack:** Python pipeline runner, frontend JavaScript helpers, unittest, node:test.

---

### Task 1: Document the desired auto-mode behavior in tests

**Files:**
- Modify: `pipeline-mcp/tests/test_pipeline_dry_run.py`
- Modify: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing backend tests**

Add tests that show:
- auto mode with direct PDB input plus `rfd3_contig="A1-3"` resolves to `local_diversify`
- the generated RFD3 spec sends `contig="A2-3"`, `unindex="A1"`, and `select_fixed_atoms={"A1":"ALL"}`

**Step 2: Run the backend tests to verify they fail**

Run: `cd /opt/protein_pipeline/pipeline-mcp && PYTHONPATH=src python3 -m unittest tests.test_pipeline_dry_run -k rfd3`

Expected: failure in the new auto-mode assertions.

**Step 3: Write the failing frontend tests**

Add tests that show:
- `effectiveRfd3Mode()` returns `local_diversify` for PDB input even when auto mode has a contig value
- `resolveRfd3Defaults()` shifts `A1-3` to `A2-3` and infers `A1` as `unindex` and fixed atom

**Step 4: Run the frontend tests to verify they fail**

Run: `cd /opt/protein_pipeline && node --test frontend/tests/pipeline.test.js --test-name-pattern 'RFD3'`

Expected: failure in the new auto-mode assertions.

### Task 2: Implement backend auto-mode local_diversify behavior

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Test: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Update auto mode inference**

When `rfd3_mode` is auto/empty and a PDB input exists:
- keep `binder` and `advanced` detection unchanged
- keep `enzyme` detection for explicit `rfd3_length`
- stop treating a present contig as `legacy_contig`
- resolve to `local_diversify`

**Step 2: Add a helper for shifted contig defaults**

Implement a helper that, for a single contig string like `A1-221`, returns:
- shifted contig `A2-221`
- unindex `A1`
- fixed atoms `{"A1":"ALL"}`

Use this helper only for auto/local_diversify inference when `unindex` is not explicitly set.

**Step 3: Apply the helper in `_rfd3_simple_inputs()`**

For `local_diversify` auto behavior:
- if user supplied a contig, derive the shift from that contig
- otherwise fall back to the existing first-residue-from-PDB inference

**Step 4: Run the backend tests**

Run: `cd /opt/protein_pipeline/pipeline-mcp && PYTHONPATH=src python3 -m unittest tests.test_pipeline_dry_run -k rfd3`

Expected: PASS.

### Task 3: Implement frontend auto-mode alignment

**Files:**
- Modify: `frontend/lib/pipeline.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Update `effectiveRfd3Mode()`**

Make auto mode with direct PDB input resolve to `local_diversify` even when `rfd3_contig` is present.

**Step 2: Add shifted contig inference**

Add a frontend helper that mirrors the backend behavior for a simple contig string, producing:
- shifted contig
- unindex
- `select_fixed_atoms`

Use it inside `resolveRfd3Defaults()` before falling back to PDB-range inference.

**Step 3: Run the frontend tests**

Run: `cd /opt/protein_pipeline && node --test frontend/tests/pipeline.test.js --test-name-pattern 'RFD3'`

Expected: PASS.

### Task 4: Final verification

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Modify: `frontend/lib/pipeline.js`
- Test: `pipeline-mcp/tests/test_pipeline_dry_run.py`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Run the targeted backend suite**

Run: `cd /opt/protein_pipeline/pipeline-mcp && PYTHONPATH=src python3 -m unittest tests.test_pipeline_dry_run -k rfd3`

Expected: PASS.

**Step 2: Run the targeted frontend suite**

Run: `cd /opt/protein_pipeline && node --test frontend/tests/pipeline.test.js --test-name-pattern 'RFD3'`

Expected: PASS.
