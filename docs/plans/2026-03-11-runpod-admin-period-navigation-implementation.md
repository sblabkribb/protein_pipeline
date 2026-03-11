# RunPod Admin Period Navigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add previous/next calendar period navigation, previous-period KPI comparison, and a higher-visibility endpoint detail layout to the RunPod admin dashboard.

**Architecture:** Extend the existing calendar-window helpers so the frontend can build `week`, `month`, and `6-month` windows for both the current and immediately previous period. Use those helpers to request current/comparison history in parallel, summarize deltas client-side, and restructure the monitoring workspace into a desktop split view with sticky detail and no long selection scroll jump.

**Tech Stack:** Python 3, sqlite-backed metrics history, vanilla JS, static HTML/CSS, Node `node:test`, Python `unittest`.

---

### Task 1: Add failing tests for period navigation helpers

**Files:**
- Modify: `frontend/tests/runpod-admin.test.js`
- Modify: `frontend/runpod-admin/lib.js`

**Step 1: Write the failing test**

- Add tests for:
  - `month` window creation
  - shifting a week window backward and forward
  - deriving the previous comparison window
  - preventing future navigation past the current period

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because the navigation helpers do not exist yet.

**Step 3: Write minimal implementation**

- Add pure helpers in `frontend/runpod-admin/lib.js` for:
  - month windows
  - window shifting
  - previous-period derivation
  - current-period detection

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/runpod-admin.test.js frontend/runpod-admin/lib.js
git commit -m "test: add runpod period navigation helpers"
```

### Task 2: Add failing markup tests for navigation controls

**Files:**
- Modify: `frontend/tests/runpod-admin.test.js`
- Modify: `frontend/runpod-admin/index.html`

**Step 1: Write the failing test**

- Add a simple fixture test that reads `frontend/runpod-admin/index.html` and asserts:
  - previous button exists
  - next button exists
  - preset dropdown includes `month`

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because the markup does not contain the new controls.

**Step 3: Write minimal implementation**

- Update `index.html` with:
  - `periodNavPrevBtn`
  - `periodNavNextBtn`
  - `month` preset option

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/runpod-admin/index.html frontend/tests/runpod-admin.test.js
git commit -m "feat: add runpod period navigation controls"
```

### Task 3: Implement period navigation and previous-period comparison

**Files:**
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/lib.js`
- Modify: `frontend/runpod-admin/styles.css`

**Step 1: Write the failing test**

- Add tests for client-side comparison summarization helpers if needed.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL if the comparison summary helper is missing.

**Step 3: Write minimal implementation**

- Replace the static current-period state with navigable windows.
- Fetch current and comparison history windows.
- Compute comparison metrics:
  - spend total
  - average workers
  - average running
  - peak queued
- Render deltas in the overview cards.
- Disable `Next` on the current period.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/runpod-admin/app.js frontend/runpod-admin/lib.js frontend/runpod-admin/styles.css frontend/tests/runpod-admin.test.js
git commit -m "feat: add runpod previous period comparison"
```

### Task 4: Elevate endpoint detail into the monitoring workspace

**Files:**
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/styles.css`

**Step 1: Write the failing test**

- Add a markup assertion or helper assertion that captures the new desktop structure expectations if practical.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL if the supporting structure helper or markup is absent.

**Step 3: Write minimal implementation**

- Change the workspace layout to `watchboard + sticky detail`.
- Remove forced long scroll on desktop selection.
- Keep mobile behavior readable.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/runpod-admin/index.html frontend/runpod-admin/app.js frontend/runpod-admin/styles.css frontend/tests/runpod-admin.test.js
git commit -m "feat: elevate runpod endpoint detail layout"
```

### Task 5: Verify the redesign end-to-end

**Files:**
- Verify only

**Step 1: Run targeted frontend tests**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 2: Run targeted backend tests**

Run: `cd pipeline-mcp && PYTHONPATH=src python3 -m unittest tests.test_runpod_metrics tests.test_runpod_admin`

Expected: PASS

**Step 3: Run syntax checks**

Run: `node --check frontend/runpod-admin/app.js`

Expected: PASS

Run: `node --check frontend/runpod-admin/lib.js`

Expected: PASS

**Step 4: Restart the service**

Run: `systemctl restart pipeline-mcp.service`

Expected: service restarts cleanly

**Step 5: Verify service health**

Run: `systemctl is-active pipeline-mcp.service`

Expected: `active`

Run: `curl -sS http://127.0.0.1:18080/healthz`

Expected: JSON payload with `ok: true`
