# Artifact Download And Source Summary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-artifact download buttons in Monitor/Analyze and show representative backbone IDs directly in the compare manifest source summaries.

**Architecture:** Reuse the existing frontend artifact rendering path and the existing `pipeline.read_artifact` tool call. Keep backend aggregation unchanged and only adjust frontend display so summary chips expose `selected_backbone_id` consistently.

**Tech Stack:** Vanilla frontend JavaScript, existing MCP tool calls, Node test runner, existing frontend CSS.

---

### Task 1: Lock Down Compare Manifest Summary Rendering

**Files:**
- Modify: `frontend/tests/pipeline.test.js`
- Modify: `frontend/app.js`

**Step 1: Write the failing test**

Add a test for `formatBackboneUsageSummary()` or `compareManifestSummaryText()` proving the rendered text includes the representative backbone id for RFD3/BioEmu summaries.

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: failure showing the current compare manifest summary omits the representative id.

**Step 3: Write minimal implementation**

Update the compare manifest strip rendering path to include `selected_backbone_id` in the visible summary text while preserving the existing tooltip.

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS for the new summary assertion.

### Task 2: Lock Down Per-Artifact Download UI

**Files:**
- Modify: `frontend/tests/pipeline.test.js`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

**Step 1: Write the failing test**

Add tests that:
- artifact rows render a download button in both monitor/analyze artifact lists
- clicking the button triggers a `pipeline.read_artifact` request with `base64=true`
- clicking the button does not invoke preview selection

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: failure because no download button/action exists yet.

**Step 3: Write minimal implementation**

Implement:
- a shared `downloadArtifact()` helper
- row-level download button rendering in `renderArtifacts()`
- CSS for the row action area and button
- localized button/status strings if needed

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS for new download interaction tests.

### Task 3: Verify Integrated Frontend Behavior

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

**Step 1: Minimal polish**

Ensure:
- button layout works in both Monitor and Analyze lists
- download failures surface through existing message/status UI
- compare manifest text remains readable with long ids

**Step 2: Run focused verification**

Run: `node frontend/tests/pipeline.test.js`
Expected: full frontend test suite passes.

**Step 3: Manual smoke checks**

Use the app to verify:
- Monitor artifact row download
- Analyze artifact row download
- Compare manifest strip displays `대표 ...`

### Task 4: Restart Only If Needed

**Files:**
- No code changes unless deployment wiring needs it

**Step 1: Check whether frontend is served as static files without build step**

If the running service serves files directly from `frontend/`, only refresh the page. If the service caches/bundles assets, restart the relevant service after code verification.

**Step 2: Verify post-restart behavior**

Re-open the UI and confirm the new buttons and summary text are visible.
