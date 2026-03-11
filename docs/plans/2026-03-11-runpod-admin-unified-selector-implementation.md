# RunPod Admin Unified Selector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify the RunPod admin dashboard so `All` shows a compact endpoint fleet list, selecting one endpoint shows one full detail sheet, and setup controls move into collapsed settings.

**Architecture:** Keep the existing API calls, monitoring windows, charts, downloads, and endpoint detail renderer. Replace the split watchboard/detail layout with a selector-driven unified endpoint area, introduce explicit `all` scope state in the frontend, and compress the header so operational monitoring sits above configuration.

**Tech Stack:** Vanilla JS, static HTML/CSS, Node `node:test`, Python `unittest`.

---

### Task 1: Add failing tests for the unified selector layout

**Files:**
- Modify: `frontend/tests/runpod-admin.test.js`
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/styles.css`

**Step 1: Write the failing test**

- Add tests asserting:
  - the header contains a compact one-line title and no `RunPod Operations Deck`
  - a collapsed settings container includes `Pipeline API Base`
  - endpoint selector markup includes an `All` control
  - `Serverless watchboard` no longer appears
  - a unified endpoint area container exists

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because the current markup still exposes the old hero/watchboard structure.

**Step 3: Write minimal implementation**

- Update static HTML/CSS so the new structure exists.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/runpod-admin.test.js frontend/runpod-admin/index.html frontend/runpod-admin/styles.css
git commit -m "test: cover runpod admin unified selector layout"
```

### Task 2: Implement selector-driven endpoint scope

**Files:**
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/styles.css`
- Test: `frontend/tests/runpod-admin.test.js`

**Step 1: Write the failing test**

- Add or extend tests for any extracted helper if needed.
- Otherwise rely on Task 1 markup tests and runtime rendering behavior covered by the existing file-level assertions.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL until the old split layout is removed.

**Step 3: Write minimal implementation**

- introduce frontend scope state for `all` vs endpoint id
- render selector chips with `All` first
- in `All`, render a compact endpoint fleet list only
- in single-endpoint mode, render only the chosen endpoint detail sheet
- keep fleet downloads in overview and endpoint downloads only in single-endpoint mode
- move settings actions into collapsed settings

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/runpod-admin/app.js frontend/runpod-admin/index.html frontend/runpod-admin/styles.css frontend/tests/runpod-admin.test.js
git commit -m "feat: unify runpod admin endpoint selection flow"
```

### Task 3: Verify the redesigned dashboard and regressions

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
