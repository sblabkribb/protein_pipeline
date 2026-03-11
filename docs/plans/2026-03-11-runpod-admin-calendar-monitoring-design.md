# RunPod Admin Calendar-Aligned Monitoring Redesign

**Date:** 2026-03-11

**Goal:** Reposition the RunPod admin console around fleet monitoring, move endpoint focus controls below the fleet overview, and align UI, CSV exports, and backend aggregation to calendar-based week and month windows.

## Context

The monitoring-first redesign improved the dashboard structure, but two usability gaps remain:

- the top "selected model" focus block competes with `Fleet Overview` instead of supporting it
- fleet-wide usage exists in code, but the UI still feels centered on endpoint-local history
- time windows still mean trailing days from "now", which makes weekly and monthly review harder

The operator wants the dashboard to read like an operations deck:

- fleet view first
- endpoint comparison second
- settings last
- time windows aligned to business review periods

## Approved Direction

The console will keep the existing three-layer structure, but the emphasis changes:

1. **Fleet Overview**
   - Remains the first major section.
   - Gains explicit fleet-wide usage summaries and clearer period labeling.
   - Becomes the place where model chips live, directly under the main charts, instead of the separate top-right focus panel.

2. **Endpoint Monitoring**
   - Stays below `Fleet Overview`.
   - Uses the fleet-selected model chips as filters/focus controls rather than as a separate hero panel.
   - Continues to show per-endpoint usage/spend sparklines and live status.

3. **Endpoint Detail / Patch**
   - Still appears below the monitoring board.
   - Patch/settings editing stays collapsed and visually secondary.

## Time Window Semantics

### Weekly

- `Week` means the current calendar week from Monday 00:00:00 through Sunday 23:59:59 in the UI timezone.
- Chart buckets for weekly mode should be day buckets labeled by weekday/date.
- CSV exports for weekly mode must use the same start/end window and bucket boundaries.

### Monthly

- `Month` means calendar months, not trailing 30 days.
- The default multi-month view will aggregate by month and label buckets with month names such as `Jan`, `Feb`, `Mar`.
- CSV exports for monthly mode must use the same month boundaries.

### Backend/API

- Frontend controls must stop relying on `days=N` for these presets.
- Requests should send explicit `start_time` and `end_time`, plus a matching resolution/bucket size, so frontend rendering and backend data use the same calendar definition.

## Information Architecture

### Fleet Overview

- KPI strip remains at the top.
- Fleet charts become the primary visual anchors:
  - fleet usage
  - fleet spend
- Directly below the charts, a compact "fleet model focus" row shows the managed endpoints/models currently in scope.
- Clicking a model chip updates the selected endpoint/filter state inside the page instead of feeling like navigation to a separate focus panel.

### Endpoint Monitoring

- This section becomes the first place where per-endpoint differences are compared in detail.
- Endpoint rows inherit the selected calendar window from `Fleet Overview`.
- Each row continues to expose:
  - current state
  - current workers / queued / running
  - period spend
  - usage sparkline
  - spend sparkline
  - export actions

### Endpoint Detail

- Selecting an endpoint still opens the detailed worker and chart view.
- The detail charts use the same calendar-aligned period as the fleet charts.
- Patch configuration remains collapsed by default at the bottom.

## Data Model Adjustments

### Frontend

- Replace the `billingDays` concept with a preset-based period model such as:
  - `week`
  - `month`
  - `months_6`
- Add helpers that compute:
  - period `start_time`
  - period `end_time`
  - display labels
  - download filename suffixes
- Add rebucketing/label helpers where existing stored timestamps need to be displayed as weekday or month labels.

### Backend

- Keep the existing API surface, but ensure `get_history` and `list_billing` can be driven entirely by explicit `start_time/end_time`.
- Preserve current fallback behavior for callers that still send `days`, but the dashboard should switch to explicit calendar windows.

## Testing Strategy

- frontend tests for:
  - calendar window calculation
  - fleet usage visibility/placement signals in rendered output
  - download filenames and CSV timestamps for week/month presets
  - fleet aggregation labels for weekday/month buckets
- backend tests for:
  - explicit `start_time/end_time` propagation through history and billing tools
  - calendar-window metadata in tool responses
- end-to-end verification:
  - switch between week and month in the dashboard
  - confirm overview charts, endpoint charts, and downloads all use the same period

## Non-Goals

- custom arbitrary date range pickers
- server-side timezone preference storage
- changes to endpoint patch semantics
- introducing a new charting library

## Risks

- calendar boundaries can be confusing if the browser timezone and backend UTC storage are mixed carelessly
- rebucketing month labels in the frontend can drift from backend data if the requested resolution is inconsistent
- hiding the separate focus panel must not remove useful endpoint selection affordances

## Mitigations

- compute and send explicit ISO `start_time/end_time` from the frontend
- keep bucket sizes explicit per preset (`day` for week, `month` for multi-month views)
- reuse the endpoint selection state, but relocate its visible controls under `Fleet Overview`
