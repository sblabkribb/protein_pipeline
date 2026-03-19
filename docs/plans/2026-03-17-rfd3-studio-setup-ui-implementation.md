# RFD3 Setup/Studio UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Setup expose all RFD3 mode-specific inputs near the mode selector, localize Studio field copy, keep RFD3 mode names English in both locales, and remove misleading Studio workflow creation.

**Architecture:** Update frontend rendering so Setup has an explicit RFD3 mode details section instead of relying on generic card ordering. Replace hardcoded field copy with i18n keys, then remove Studio new-session actions from both static markup and dynamic action bars.

**Tech Stack:** Vanilla JS frontend, HTML, node:test

---

### Task 1: Add failing frontend tests

**Files:**
- Modify: `/opt/protein_pipeline/frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

- Add assertions that:
  - `frontend/app.js` no longer contains `data-studio-action="new"` and no longer binds `studioNewSessionBtn`.
  - Korean locale strings for `choice.rfd3Mode.*` remain English labels.
  - New i18n keys exist for `question.rfd3Hotspots.*`, `question.rfd3Unindex.*`, `question.rfd3AdvancedInputs.*`, and BioEmu field copy.
  - Setup renders a dedicated RFD3 mode details path instead of leaving these fields only in the generic text-question pass.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: FAIL because the source still contains Studio new-session actions and missing localization/dedicated rendering assertions.

### Task 2: Localize RFD3/BioEmu field copy

**Files:**
- Modify: `/opt/protein_pipeline/frontend/app.js`

**Step 1: Write minimal implementation**

- Add i18n keys for:
  - `question.rfd3Hotspots.*`
  - `question.rfd3Orientation.*`
  - `question.rfd3NonLoopy.*`
  - `question.rfd3Unindex.*`
  - `question.rfd3Length.*`
  - `question.rfd3FixedAtoms.*`
  - `question.rfd3AdvancedInputs.*`
  - `question.rfd3PartialT.*`
  - `question.bioemuFilterSamples.*`
  - `question.bioemuSteeringConfig.*`
- Update `QUESTION_PRESETS` to use these keys.
- Keep mode choice labels English in both `en` and `ko` dictionaries.

**Step 2: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: some assertions still fail because Setup/Studio structural changes are not done yet.

### Task 3: Add dedicated Setup RFD3 mode details rendering

**Files:**
- Modify: `/opt/protein_pipeline/frontend/app.js`

**Step 1: Write minimal implementation**

- Add a helper to identify Setup-only RFD3 mode detail question ids.
- Remove those ids from generic standalone rendering in Setup.
- Render a dedicated card immediately after the `rfd3_mode` card with currently relevant fields.
- Keep `rfd3_partial_t` in the compact parameter board.
- Move `rfd3_contig` out of the setup input-step mapping so it lives with the other mode-specific controls.
- Remove `ligand_mask_use_original_target` from the compact option board so it falls back to a normal config card.

**Step 2: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: Setup-related assertions pass; Studio new-session assertions still fail.

### Task 4: Remove Studio new-workflow creation actions

**Files:**
- Modify: `/opt/protein_pipeline/frontend/index.html`
- Modify: `/opt/protein_pipeline/frontend/app.js`

**Step 1: Write minimal implementation**

- Remove `studioNewSessionBtn` from the toolbar markup.
- Remove inline `data-studio-action="new"` button from the Studio summary actions.
- Remove the associated click binding.
- Update any empty-state/help copy that still suggests creating a new workflow in Studio.

**Step 2: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: PASS

### Task 5: Final verification

**Files:**
- Modify: none unless cleanup is needed

**Step 1: Run final tests**

Run: `node --test frontend/tests/pipeline.test.js`

Expected: PASS

**Step 2: Optional manual UI check**

Run the frontend locally if needed and verify:
- Setup `RFD3 mode` card shows mode-specific inputs directly below it.
- Studio has no `New Workflow` action.
- Korean locale shows localized help text while keeping RFD3 mode names in English.
