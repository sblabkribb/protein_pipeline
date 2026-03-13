# Pipeline/Studio Consistency Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the pipeline, Setup/Workflow Studio, Analyze, Hit List, and Copilot describe backbone generation and WT-difference semantics consistently while expanding residue selection UX.

**Architecture:** Extend the existing backbone manifests instead of replacing them, preserve selected-only propagation as an explicit mode, and update frontend rendering to read the manifest first. Implement the UX changes in testable helper functions before wiring them into the main static app.

**Tech Stack:** Python pipeline backend, Node test runner, static frontend JavaScript, CSS, JSON manifest artifacts

---

### Task 1: Backend Manifest Truthfulness

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Test: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Write the failing test**

Add Python tests that assert:

- `backbones.json` includes source-level summary fields for requested/observed/materialized/propagated counts
- selected-only propagation is explicit in `propagation_mode`
- `proteinmpnn_backbones.json` preserves backbone source ids when multiple backbones are present

**Step 2: Run test to verify it fails**

Run: `pytest pipeline-mcp/tests/test_pipeline_dry_run.py -k backbones -v`
Expected: FAIL because the new manifest fields are missing

**Step 3: Write minimal implementation**

Update the pipeline so `backbones.json` and tier manifests record:

- requested counts from request parameters
- observed counts from source metadata payloads
- materialized counts from backbone PDB availability
- propagated counts from actual backbone contexts used downstream
- selected/propagated flags per backbone

**Step 4: Run test to verify it passes**

Run: `pytest pipeline-mcp/tests/test_pipeline_dry_run.py -k backbones -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/pipeline.py pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/tests/test_pipeline_dry_run.py
git commit -m "feat: add backbone propagation manifest metadata"
```

### Task 2: Hit List WT Identity Semantics

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Test: `pipeline-mcp/tests/test_tools_hit_list.py`

**Step 1: Write the failing test**

Create a backend hit-list test that asserts each row preserves:

- `wt_diff_count`
- `wt_compare_len`
- `wt_identity`
- `wt_identity_pct`

and that exported row formatting inputs do not require inversion to derive homology.

**Step 2: Run test to verify it fails**

Run: `pytest pipeline-mcp/tests/test_tools_hit_list.py -v`
Expected: FAIL because the helper coverage is missing or current semantics are not pinned

**Step 3: Write minimal implementation**

Add or update the backend test scaffolding and keep hit-list row payloads explicit and stable for frontend rendering.

**Step 4: Run test to verify it passes**

Run: `pytest pipeline-mcp/tests/test_tools_hit_list.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/tests/test_tools_hit_list.py
git commit -m "test: pin hit list wt identity payloads"
```

### Task 3: Compare/Analyze Helper Behavior

**Files:**
- Modify: `frontend/lib/compare.js`
- Modify: `frontend/lib/pipeline.js`
- Modify: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add frontend tests for pure helpers that assert:

- Compare Studio default mode is sequence
- structure legend text excludes sequence-only language
- WT display formatting shows `diff_count/len · identity%`
- compare scope labels can explain exact candidate vs aggregate

**Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/pipeline.test.js`
Expected: FAIL because the helper behavior is not implemented yet

**Step 3: Write minimal implementation**

Add or extend helper functions in `frontend/lib/compare.js` and `frontend/lib/pipeline.js` so `frontend/app.js` can consume tested behavior instead of duplicating string logic inline.

**Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/pipeline.test.js`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/lib/compare.js frontend/lib/pipeline.js frontend/tests/pipeline.test.js
git commit -m "feat: add tested compare and wt identity helpers"
```

### Task 4: Shared Residue Selection Workspace

**Files:**
- Create: `frontend/lib/residue-picker.js`
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add frontend tests for pure residue-selection helpers that cover:

- amino-acid property color mapping
- surface/core partition helpers
- preset selection merge behavior
- conserved-tier enable/disable logic

**Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/pipeline.test.js`
Expected: FAIL because the helper module does not exist yet

**Step 3: Write minimal implementation**

Create `frontend/lib/residue-picker.js` with pure helpers, then wire `frontend/app.js` to render:

- sequence pane
- structure color-mode toggles
- preset chips
- shared apply flow for Setup and Workflow Studio

**Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/pipeline.test.js`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/lib/residue-picker.js frontend/app.js frontend/index.html frontend/styles.css frontend/tests/pipeline.test.js
git commit -m "feat: expand shared residue selection workspace"
```

### Task 5: Analyze, Compare Studio, and Copilot Wiring

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add frontend tests that assert:

- compare mode initializes to sequence
- residue-linked legend copy is present
- Copilot intent replies define terms before dumping run snapshots
- recommendation replies use actual hit-list rows when available

**Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/pipeline.test.js`
Expected: FAIL because the UI/copy logic still uses the old behavior

**Step 3: Write minimal implementation**

Update `frontend/app.js`, `frontend/index.html`, and `frontend/styles.css` to:

- show manifest-backed source summaries
- add tooltips/help affordances
- clean compare legends
- update Hit List WT text
- improve Copilot response construction

**Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/pipeline.test.js`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app.js frontend/index.html frontend/styles.css frontend/tests/pipeline.test.js
git commit -m "feat: align analyze and copilot with manifest semantics"
```

### Task 6: Full Regression Verification

**Files:**
- Modify: `docs/plans/2026-03-13-pipeline-studio-consistency-design.md`
- Modify: `docs/plans/2026-03-13-pipeline-studio-consistency-implementation.md`

**Step 1: Run targeted backend tests**

Run: `pytest pipeline-mcp/tests/test_pipeline_dry_run.py -k backbones -v`
Expected: PASS

**Step 2: Run full relevant backend tests**

Run: `pytest pipeline-mcp/tests -q`
Expected: PASS

**Step 3: Run frontend tests**

Run: `cd frontend && node --test tests/pipeline.test.js tests/runpod-admin.test.js`
Expected: PASS

**Step 4: Run sample artifact sanity checks**

Run: `python3 - <<'PY'\nimport json\nfrom pathlib import Path\nroot=Path('outputs/admin_20260310_065409_2f2c2372')\nprint((root/'backbones.json').exists())\nPY`
Expected: existing sample output still readable and no helper code assumes the new fields are mandatory

**Step 5: Commit**

```bash
git add docs/plans/2026-03-13-pipeline-studio-consistency-design.md docs/plans/2026-03-13-pipeline-studio-consistency-implementation.md
git commit -m "docs: add pipeline studio consistency design and plan"
```
