# RunPod Admin Monitoring Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix incorrect RunPod running-state reporting and rebuild the RunPod admin UI into a monitoring-first dashboard with fleet-wide/per-endpoint 7-day charts and downloads.

**Architecture:** Keep the existing `pipeline.runpod_*` API surface, correct the backend usage normalization that feeds `metrics.sqlite`, and move most new aggregation/export behavior into frontend helpers so the dashboard can derive fleet-wide charts from already-available endpoint history. Restructure the static UI into `overview -> endpoint monitoring -> endpoint detail`, with patch controls collapsed below the monitoring content.

**Tech Stack:** Python 3, sqlite-backed usage collector, vanilla JS, static HTML/CSS, Node `node:test`, Python `unittest`.

---

### Task 1: Lock the running-state bug with failing backend tests

**Files:**
- Modify: `pipeline-mcp/tests/test_runpod_metrics.py`
- Modify: `pipeline-mcp/tests/test_runpod_admin.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/runpod_metrics.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/runpod_admin.py`

1. Add a test for collector health normalization where `jobs.inProgress` is missing or zero but worker buckets contain warm/ready counts; assert `running == 0`.
2. Add a test for endpoint history sampling that uses `worker_summary.states` with warm/ready counts; assert the sampled `running` metric still stays `0`.
3. Run:
   ```bash
   python3 -m unittest pipeline-mcp.tests.test_runpod_metrics pipeline-mcp.tests.test_runpod_admin
   ```
   Expected before implementation: failure showing warm/ready states are still treated as running.
4. Implement the minimal backend fix so only real in-progress job counters populate `running`.
5. Re-run the same unittest command and confirm green.

### Task 2: Add failing frontend tests for monitoring summaries and downloads

**Files:**
- Modify: `frontend/tests/runpod-admin.test.js`
- Modify: `frontend/runpod-admin/lib.js`

1. Add tests for endpoint status derivation:
   - queued jobs => `Queued`
   - running jobs => `Running`
   - live workers without running jobs => `Warm` or `Idle`
   - zero workers + zero max => `Paused`
2. Add tests for fleet aggregation helpers:
   - aggregate billing series across endpoints into one 7-day fleet series
   - aggregate usage series across endpoints by timestamp
3. Add tests for CSV serialization helpers that emit:
   - fleet billing CSV
   - fleet usage CSV
   - endpoint billing CSV
   - endpoint usage CSV
4. Run:
   ```bash
   node --test frontend/tests/runpod-admin.test.js
   ```
   Expected before implementation: failures for missing helpers / changed semantics.
5. Implement only the helper layer required to satisfy the tests.

### Task 3: Rebuild the RunPod admin information architecture

**Files:**
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/styles.css`
- Modify: `frontend/runpod-admin/lib.js`

1. Replace the current multi-panel clutter with three sections:
   - fleet overview
   - endpoint monitoring board
   - endpoint detail
2. Keep the API/auth controls but visually compress the hero.
3. Add two fleet-wide charts:
   - spend over the selected window
   - usage over the selected window
4. Add endpoint monitoring rows/cards with:
   - status badge
   - workers / queued / running
   - 7-day spend
   - usage sparkline
   - spend sparkline
   - export buttons
5. Move the configuration patch form into a collapsed section below the detail charts.
6. Ensure the selected endpoint detail still shows worker table, larger charts, and patch/reset actions.

### Task 4: Wire chart and CSV downloads into the new dashboard

**Files:**
- Modify: `frontend/runpod-admin/index.html`
- Modify: `frontend/runpod-admin/app.js`
- Modify: `frontend/runpod-admin/lib.js`

1. Add fleet-level download actions for:
   - billing CSV
   - usage CSV
   - spend chart SVG
   - usage chart SVG
2. Add selected-endpoint download actions for:
   - billing CSV
   - usage CSV
   - spend chart SVG
   - usage chart SVG
3. Keep file names deterministic and window-scoped, for example:
   - `runpod-fleet-billing-7d.csv`
   - `runpod-endpoint-<id>-usage-7d.csv`
4. Make downloads client-side without adding new backend endpoints.

### Task 5: Verify behavior end-to-end

**Files:**
- Verify only

1. Run backend tests:
   ```bash
   python3 -m unittest pipeline-mcp.tests.test_runpod_metrics pipeline-mcp.tests.test_runpod_admin
   ```
2. Run frontend tests:
   ```bash
   node --test frontend/tests/runpod-admin.test.js
   ```
3. Restart the service:
   ```bash
   systemctl restart pipeline-mcp.service
   ```
4. Verify live endpoints/billing through local API calls and confirm the dashboard is no longer read-only.
5. Open the dashboard manually and verify:
   - endpoints with warm workers but no jobs are not labeled running
   - fleet-wide 7-day spend and usage charts render
   - endpoint-specific charts render
   - CSV/SVG downloads work
   - patch controls start collapsed and remain accessible
