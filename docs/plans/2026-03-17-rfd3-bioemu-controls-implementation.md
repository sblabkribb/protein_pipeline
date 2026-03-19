# RFD3 and BioEmu Controls Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add safer defaults and explicit control surfaces for RFD3 and BioEmu across backend and frontend.

**Architecture:** Backend request parsing and pipeline spec synthesis become mode-aware for RFD3 and steering-aware for BioEmu. Frontend Setup/Studio expose only the controls relevant to the selected mode, while preserving legacy compatibility where possible.

**Tech Stack:** Python dataclasses and pipeline orchestration, RunPod clients, vanilla JS frontend, unittest, node:test.

---

### Task 1: Extend request models and tool parsing

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/tools.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_tools.py`

**Steps**

1. Add RFD3 mode and mode-specific request fields plus BioEmu steering text.
2. Parse the new fields in `pipeline_request_from_args`.
3. Update the tool schema so new fields are accepted.
4. Add tests for BioEmu default filtering and RFD3 parsing defaults.

### Task 2: Make pipeline RFD3/BioEmu behavior mode-aware

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/clients/bioemu_runpod.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`

**Steps**

1. Add RFD3 mode helpers and canonical spec synthesis.
2. Replace unconditional `partial_t` injection with mode-aware defaults.
3. Add duplicate-backbone QA summary for RFD3 outputs.
4. Pass BioEmu steering config through the client and pipeline request.
5. Add focused dry-run tests for mode behavior and duplicate summaries.

### Task 3: Relax router/preflight assumptions

**Files:**
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/router.py`
- Modify: `/opt/protein_pipeline/pipeline-mcp/src/pipeline_mcp/preflight.py`

**Steps**

1. Stop assuming `rfd3_contig` is always required.
2. Keep `rfd3_input_pdb` prompt support, but only require mode-relevant fields.
3. Update preflight error text to refer to “RFD3 inputs” rather than `input_pdb + contig`.

### Task 4: Update Setup and Studio UI

**Files:**
- Modify: `/opt/protein_pipeline/frontend/app.js`
- Modify: `/opt/protein_pipeline/frontend/lib/pipeline.js`
- Test: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`

**Steps**

1. Add question presets and stage ownership for new RFD3/BioEmu fields.
2. Add conditional visibility and required logic by `rfd3_mode`.
3. Add BioEmu advanced controls for `filter_samples` and steering config.
4. Update payload filtering and Studio defaults.
5. Add frontend tests for new defaults and field routing.

### Task 5: Verify targeted behavior

**Files:**
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_tools.py`
- Test: `/opt/protein_pipeline/pipeline-mcp/tests/test_pipeline_dry_run.py`
- Test: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`

**Steps**

1. Run focused Python tests for request parsing and pipeline dry-run behavior.
2. Run focused frontend tests for Setup/Studio payload shaping.
3. Review failures and patch only the affected RFD3/BioEmu paths.
