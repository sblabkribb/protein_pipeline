# Compare Metadata Scope Selector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an Advanced-tab compact-parameter selector that controls whether Compare metadata shows input-structure RMSD, working-backbone RMSD, both, or neither, while keeping the selector out of backend run payloads.

**Architecture:** The selector is implemented as a frontend-only setup answer field in `frontend/app.js` and `frontend/lib/pipeline.js`. Compare preview metadata computes optional RMSD rows from already available input/working reference PDB text and renders them only when the selected scope requires them.

**Tech Stack:** Static browser JavaScript modules, Node test runner, existing setup/compare helpers in `frontend/app.js` and `frontend/lib/pipeline.js`.

---

### Task 1: Add failing tests for the new selector contract

**Files:**
- Modify: `frontend/tests/pipeline.test.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing tests**

Add tests that assert:

- `frontend/app.js` contains a `compare_rmsd_scope` question preset with default `off`
- the compact parameter board includes `compare_rmsd_scope`
- `buildRunArguments()` strips `compare_rmsd_scope`
- `buildSetupDraftFromRequest()` falls back to `off` when the field is absent
- compare tooltip/localization keys exist for input/backbone RMSD rows

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js --test-name-pattern 'compare metadata scope|compare_rmsd_scope'`

Expected: FAIL because the selector and related strings do not exist yet.

### Task 2: Implement the frontend-only setup field

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/lib/pipeline.js`

**Step 1: Write minimal implementation**

- Add question preset and localized labels/help/options for `compare_rmsd_scope`
- Add it to the compact parameter board ordering
- Render it as a select field with four choices
- Default missing values to `off`
- Strip `compare_rmsd_scope` in `buildRunArguments()`

**Step 2: Run focused tests**

Run: `node --test frontend/tests/pipeline.test.js --test-name-pattern 'compare metadata scope|compare_rmsd_scope'`

Expected: selector-related tests pass, while metadata rendering tests may still fail.

### Task 3: Render optional compare metadata rows

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/lib/compare.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Extend tests to assert that localization and tooltip definitions cover input/backbone RMSD keys and that runtime source contains the conditional row handling.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js --test-name-pattern 'compare metadata scope|compare_rmsd_scope'`

Expected: FAIL until metadata row handling is implemented.

**Step 3: Write minimal implementation**

- Compute input/backbone structural diffs in `buildComparePreviewCardData()`
- Add metadata fields for their RMSD and shared aligned CA count
- Conditionally append the new rows in `renderCompareMetadataPanel()` based on the selected selector mode
- Add tooltip copy for the new metadata rows

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js --test-name-pattern 'compare metadata scope|compare_rmsd_scope'`

Expected: PASS.

### Task 4: Run broader regression checks

**Files:**
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Run broader targeted frontend tests**

Run: `node --test frontend/tests/pipeline.test.js --test-name-pattern 'RFD3|hidden target RMSD gate|compare metadata scope|compare_rmsd_scope'`

Expected: PASS for the touched frontend behavior.

**Step 2: Review diffs**

Run: `git diff -- frontend/app.js frontend/lib/pipeline.js frontend/lib/compare.js frontend/tests/pipeline.test.js docs/plans/2026-03-30-compare-metadata-scope-design.md docs/plans/2026-03-30-compare-metadata-scope-implementation.md`

Expected: only the intended selector, metadata, test, and doc changes appear.
