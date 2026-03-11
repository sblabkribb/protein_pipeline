# RunPod Admin UI Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove duplicated selected-endpoint summary UI, simplify overview metrics, and make the endpoint detail panel easier to read.

**Architecture:** Keep the existing data flow, period navigation, and comparison helpers, but simplify the rendered layout. Remove the overview-level selected-endpoint summary, reduce the number of top-level summary surfaces, and let the detail panel participate in normal page scrolling instead of using an inner scroll container.

**Tech Stack:** Vanilla JS, static HTML/CSS, Node `node:test`, Python `unittest`.

---

### Task 1: Add failing tests for simplified markup

**Files:**
- Modify: `frontend/tests/runpod-admin.test.js`
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/styles.css`

**Step 1: Write the failing test**

- Add tests asserting:
  - `Managed endpoint snapshot` no longer appears
  - navigation controls still appear
  - `.detail-panel` no longer uses `overflow: auto`

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because the old overview snapshot and detail scroll style still exist.

**Step 3: Write minimal implementation**

- Remove or rename the redundant overview snapshot markup path.
- Adjust styles so the detail panel no longer traps scrolling.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/runpod-admin.test.js frontend/runpod-admin/index.html frontend/runpod-admin/styles.css
git commit -m "test: simplify runpod admin markup"
```

### Task 2: Simplify overview rendering

**Files:**
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/styles.css`

**Step 1: Write the failing test**

- Add or update tests only if a helper is needed; otherwise rely on the markup failure from Task 1.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL or remain red from Task 1 until implementation lands.

**Step 3: Write minimal implementation**

- remove `renderSelectionOverview()` from overview
- simplify the selector section label/copy
- reduce top summary cards to a smaller operational set
- compress comparison output into a lighter presentation

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/runpod-admin/app.js frontend/runpod-admin/index.html frontend/runpod-admin/styles.css frontend/tests/runpod-admin.test.js
git commit -m "feat: simplify runpod admin overview"
```

### Task 3: Verify end-to-end

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
