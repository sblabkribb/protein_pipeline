# RunPod Admin Monitoring-First Redesign

**Date:** 2026-03-11

**Goal:** Rework the RunPod admin console into a monitoring-first operations view, fix the incorrect "running" status, and add downloadable 7-day usage/billing charts for fleet-wide and per-endpoint reporting.

## Context

The current `/runpod-admin/` console already exposes endpoint inventory, per-endpoint patch actions, usage history, and billing history. The main problems reported in production are:

- endpoints without active jobs can still appear as "running"
- 7-day fleet-wide cost and usage trends are not visible in one place
- per-endpoint cost and usage trends are present but not organized for quick operations review
- charts cannot be exported
- patch controls dominate the layout even though day-to-day use is primarily monitoring

## Root Cause

The incorrect running state is caused by the usage normalization path treating worker state buckets such as `ready`, `warm`, or other non-busy workers as `running` whenever `jobs.inProgress` is absent. That value is then persisted into `usage_snapshots` and reused by the dashboard.

This affects:

- live fleet cards that display derived usage signals
- stored usage history in `metrics.sqlite`
- any chart or summary built from the persisted `running` series

## Approved Direction

The console will be reorganized around three layers:

1. **Fleet Overview**
   - Top KPI strip for endpoint count, managed count, 7-day spend, live workers, and queued jobs.
   - Two large charts: fleet-wide 7-day spend trend and fleet-wide 7-day usage trend.
   - Primary export actions for all visible billing and usage data.

2. **Endpoint Monitoring**
   - A compact, sortable monitoring board for endpoints.
   - Clear state badges such as `Idle`, `Warm`, `Queued`, `Running`, `Paused`, or `Missing`.
   - Per-endpoint 7-day spend and usage sparklines.
   - Endpoint-level CSV/SVG export actions.

3. **Endpoint Detail**
   - A focused detail panel for the selected endpoint.
   - Larger per-endpoint spend and usage charts.
   - Worker state breakdown and current queue/running metrics.
   - Patch/config controls moved below monitoring content and collapsed by default.

## Data Semantics

### Current state

- `running jobs` must come from `health_jobs.in_progress` or `jobs.inProgress`.
- non-busy worker buckets must not be promoted into `running jobs`
- `worker_summary.total` remains the provisioned/live worker count
- worker state chips remain visible so warm/idle capacity is still observable

### Historical usage

- new usage samples will persist only actual `running jobs`
- historical usage charts remain based on `workers`, `queued`, and `running`
- the UI will emphasize `workers` and `queued` in overview charts so recently corrected `running` data does not dominate interpretation

## Information Architecture

### Fleet Overview

- small hero with API controls retained but visually de-emphasized
- KPI strip directly under the hero
- chart row with:
  - `Fleet Spend · last N days`
  - `Fleet Usage · last N days`
- export row:
  - `Download fleet billing CSV`
  - `Download fleet usage CSV`
  - `Download chart SVG`

### Endpoint Monitoring

- monitoring board replaces the current dense mix of service board + fleet cards + billing block
- one row/card per endpoint with:
  - name, endpoint ID, mapping
  - status badge
  - workers / queued / running counters
  - 7-day spend
  - spend sparkline
  - usage sparkline
  - quick actions: focus, export

### Endpoint Detail

- current endpoint hero simplified into high-signal metrics
- larger spend and usage charts remain visible
- worker table stays available
- configuration patch form moves into a collapsed accordion after monitoring sections

## Export Design

Exports are client-side and require no backend changes beyond the existing data endpoints.

### CSV

- fleet billing CSV
- fleet usage CSV
- selected endpoint billing CSV
- selected endpoint usage CSV

Each CSV includes normalized timestamps and endpoint identifiers so the files can be dropped into spreadsheets directly.

### SVG

- fleet spend chart
- fleet usage chart
- selected endpoint spend chart
- selected endpoint usage chart

The existing SVG chart renderer is reused so export can serialize the same rendered chart markup with minimal extra logic.

## Testing Strategy

- backend regression tests for usage normalization so `warm/ready` workers no longer inflate `running`
- frontend unit tests for:
  - status derivation
  - fleet aggregation series
  - CSV serialization helpers
  - chart export helpers where practical
- targeted verification by restarting `pipeline-mcp`, calling RunPod admin tools, and checking the dashboard with live data

## Non-Goals

- endpoint create/delete workflows
- GPU catalog selection UX
- audit trail or alerting
- major backend API redesign

## Risks

- previously persisted usage history still reflects old semantics until newer samples replace it in recent windows
- large DOM updates in the dashboard can make the page feel heavy if monitoring cards stay too dense
- export helpers must be careful to serialize only the active chart content the user expects

## Mitigations

- shift overview charts toward `workers` and `queued` as primary signals
- simplify card density and reduce duplicate metrics
- keep downloads scoped and clearly labeled (`fleet` vs `selected endpoint`)
