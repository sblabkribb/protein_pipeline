# RunPod Admin Chart Readability Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make RunPod monitoring charts numerically readable and remove repeated same-day axis labels in endpoint and fleet views.

**Architecture:** Add frontend chart helper functions in `lib.js` for period-aligned rollups, sparse tick selection, and scale labels. Then update `app.js` to render chart frames with y-axis numbers and compact summary stats, while avoiding raw endpoint-detail history from polluting the current monitoring chart view.

**Tech Stack:** Vanilla JS, static HTML/CSS, Node `node:test`, Python `unittest`.

---

### Task 1: Add failing tests for chart rollup and axis helpers

**Files:**
- Modify: `frontend/tests/runpod-admin.test.js`
- Modify: `frontend/runpod-admin/lib.js`
- Modify: `frontend/runpod-admin/styles.css`

**Step 1: Write the failing test**

- Add tests asserting:
  - usage samples from the same day roll up to one visible point for month/week presets
  - sparse monitoring ticks cap label count and keep endpoints
  - chart scale labels expose top/mid/zero values
  - CSS exposes chart axis and chart summary stat-row classes

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because the helper functions and styles do not exist yet.

**Step 3: Write minimal implementation**

- Add the new helpers and styles needed for the assertions.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/runpod-admin.test.js frontend/runpod-admin/lib.js frontend/runpod-admin/styles.css
git commit -m "test: cover runpod admin chart readability helpers"
```

### Task 2: Update chart rendering to use rolled samples and readable numeric framing

**Files:**
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/lib.js`
- Modify: `frontend/runpod-admin/styles.css`
- Test: `frontend/tests/runpod-admin.test.js`

**Step 1: Write the failing test**

- Reuse Task 1 failing helper tests as the red state.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL until app rendering uses the new helpers.

**Step 3: Write minimal implementation**

- roll up fleet and endpoint usage/spend samples to the current preset before rendering
- render sparse x-axis labels instead of one label per sample
- add y-axis numbers for each chart
- add compact stat rows under each chart
- stop merging raw detail usage history into the current chart state during endpoint selection

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/runpod-admin/app.js frontend/runpod-admin/lib.js frontend/runpod-admin/styles.css frontend/tests/runpod-admin.test.js
git commit -m "feat: improve runpod admin chart readability"
```

### Task 3: Verify frontend and backend regressions

**Files:**
- Verify only

**Step 1: Run frontend checks**

Run: `node --check frontend/runpod-admin/app.js`

Expected: PASS

Run: `node --check frontend/runpod-admin/lib.js`

Expected: PASS

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 2: Run backend regression tests**

Run: `cd pipeline-mcp && PYTHONPATH=src python3 -m unittest tests.test_runpod_metrics tests.test_runpod_admin`

Expected: PASS

**Step 3: Verify service health**

Run: `systemctl is-active pipeline-mcp.service`

Expected: `active`

Run: `curl -sS http://127.0.0.1:18080/healthz`

Expected: `{"ok": true}`
