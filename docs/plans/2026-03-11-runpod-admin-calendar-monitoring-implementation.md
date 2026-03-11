# RunPod Admin Calendar Monitoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align the RunPod admin dashboard to calendar-based monitoring windows, surface fleet-wide usage more clearly, and move model focus controls under `Fleet Overview` while keeping patch editing secondary.

**Architecture:** Keep the current `pipeline.runpod_*` endpoints, but drive them with explicit calendar `start_time/end_time` values instead of trailing `days` presets. Replace the dashboard's `billingDays` UI state with calendar period presets, rebuild the fleet overview so model focus controls sit under the overview charts, and update CSV/SVG export naming and metadata to reflect the chosen calendar window.

**Tech Stack:** Python 3, sqlite-backed metrics history, vanilla JS, static HTML/CSS, Node `node:test`, Python `unittest`.

---

### Task 1: Add failing frontend tests for calendar presets and labels

**Files:**
- Modify: `frontend/tests/runpod-admin.test.js`
- Modify: `frontend/runpod-admin/lib.js`

**Step 1: Write the failing test**

- Add tests for helpers that compute:
  - current week window from Monday to Sunday
  - current month window with month labels
  - six-month window with month buckets
- Add a test proving download filename suffixes use preset names instead of trailing day counts.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because the calendar helpers and filename semantics do not exist yet.

**Step 3: Write minimal implementation**

- Add pure helper functions in `frontend/runpod-admin/lib.js` for calendar preset calculation, bucket labeling, and filename suffixes.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS for the new helper tests.

**Step 5: Commit**

```bash
git add frontend/tests/runpod-admin.test.js frontend/runpod-admin/lib.js
git commit -m "test: add calendar monitoring helpers"
```

### Task 2: Add failing backend tests for explicit calendar windows

**Files:**
- Modify: `pipeline-mcp/tests/test_runpod_admin.py`
- Modify: `pipeline-mcp/tests/test_runpod_metrics.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/runpod_admin.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/runpod_metrics.py`

**Step 1: Write the failing test**

- Add a test that calls `pipeline.runpod_get_history` with explicit `start_time/end_time` and asserts the returned `window` metadata preserves them.
- Add a test that calls `pipeline.runpod_list_billing` with explicit `start_time/end_time` and asserts the same.
- Add a metrics-store test for month-resolution billing reads over explicit calendar boundaries.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests.test_runpod_metrics tests.test_runpod_admin`

Expected: FAIL if metadata, resolution, or aggregation do not match the requested calendar boundaries.

**Step 3: Write minimal implementation**

- Tighten the backend history/billing paths where needed so explicit windows are echoed and used consistently.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python3 -m unittest tests.test_runpod_metrics tests.test_runpod_admin`

Expected: PASS for the new backend coverage.

**Step 5: Commit**

```bash
git add pipeline-mcp/tests/test_runpod_metrics.py pipeline-mcp/tests/test_runpod_admin.py pipeline-mcp/src/pipeline_mcp/runpod_admin.py pipeline-mcp/src/pipeline_mcp/runpod_metrics.py
git commit -m "test: cover explicit calendar monitoring windows"
```

### Task 3: Rebuild the fleet overview layout around calendar presets

**Files:**
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/styles.css`

**Step 1: Write the failing test**

- Add a rendering test or DOM assertion showing that:
  - the overview toolbar uses calendar presets instead of `Billing window (days)`
  - the model focus list renders under `Fleet Overview`
  - the separate top-level "Current Focus" panel is removed or visually demoted

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because the current markup and rendering still use the old days-based layout.

**Step 3: Write minimal implementation**

- Replace the days selector with period presets.
- Move or absorb the selection board into the fleet overview section.
- Keep endpoint detail lower on the page, with patch controls still collapsed.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS for the layout assertions.

**Step 5: Commit**

```bash
git add frontend/runpod-admin/index.html frontend/runpod-admin/app.js frontend/runpod-admin/styles.css frontend/tests/runpod-admin.test.js
git commit -m "feat: move endpoint focus under fleet overview"
```

### Task 4: Wire dashboard refresh, charts, and downloads to calendar presets

**Files:**
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/lib.js`

**Step 1: Write the failing test**

- Add tests that assert refresh payload builders request:
  - week windows with explicit Monday/Sunday `start_time/end_time`
  - month or multi-month windows with explicit month boundaries
- Add tests for CSV export builders that preserve calendar timestamps and preset-scoped filenames.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: FAIL because refresh/download behavior still depends on `billingDays`.

**Step 3: Write minimal implementation**

- Introduce a period-state model in `app.js`.
- Use it for history, billing, chart labels, summary copy, and downloads.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/runpod-admin.test.js`

Expected: PASS for the request and export semantics.

**Step 5: Commit**

```bash
git add frontend/runpod-admin/app.js frontend/runpod-admin/lib.js frontend/tests/runpod-admin.test.js
git commit -m "feat: align runpod monitoring windows to calendar presets"
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
