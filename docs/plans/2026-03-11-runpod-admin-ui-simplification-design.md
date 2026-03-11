# RunPod Admin UI Simplification

**Date:** 2026-03-11

**Goal:** Remove duplicated endpoint summary content, make endpoint detail easier to read after selection, and reduce the amount of simultaneous visual noise in the RunPod admin dashboard.

## Context

The monitoring-first redesign and later period-navigation changes improved coverage, but the dashboard became visually crowded:

- `Managed endpoint snapshot` repeats data that already exists in the right-side endpoint detail panel
- clicking managed model chips can still feel incomplete because the user sees a small summary block in overview and a larger detail block elsewhere
- overview currently contains too many competing surfaces at once:
  - KPI strip
  - comparison cards
  - fleet charts
  - model chip focus section
  - detailed endpoint panel

The result is a dashboard that technically exposes the right data, but asks the operator to parse too many layers at once.

## Root Cause

The clutter is caused by duplicated information architecture, not missing data:

- the selected endpoint is summarized in both overview and detail
- detail uses a sticky panel with its own scroll area, which makes the selected content feel partially hidden
- too many small cards compete for attention before the user reaches the actual detail workflow

## Approved Direction

The dashboard will be simplified by subtraction:

1. remove the `Managed endpoint snapshot` block entirely
2. keep only the model chips as a compact endpoint selector under `Fleet Overview`
3. keep one authoritative endpoint detail surface in the workspace
4. reduce the top KPI strip and comparison presentation so overview stays legible
5. stop using an internal scrollable sticky detail panel

## Information Architecture

### Fleet Overview

- stays first
- keeps:
  - period controls
  - a reduced KPI strip
  - fleet usage/spend charts
  - model chip selector
- removes:
  - selected endpoint mini-summary block

### Monitoring Workspace

- left column:
  - endpoint watchboard
- right column:
  - single endpoint detail panel
- detail remains sticky on desktop if possible, but should not trap content inside an inner scroll area

### Billing Ledger

- stays collapsed at the bottom
- no additional summary duplication above it

## Simplification Rules

- one selected-endpoint summary surface only
- one period summary surface only
- keep labels short and operational
- prefer fewer cards with clearer hierarchy over many small metrics

## Specific Changes

- remove `renderSelectionOverview()` output from overview
- keep model chips but rename the section to a simpler selector label
- collapse overview metrics into a smaller set of cards:
  - endpoints
  - workers
  - running / queued
  - period spend
- compress previous-period comparison into a lighter inline row rather than a full secondary grid
- make the right detail panel scroll with the page instead of having `overflow: auto`

## Testing Strategy

- frontend tests for:
  - `Managed endpoint snapshot` text removed from markup/render path
  - navigation controls still present
  - detail panel no longer uses an internal sticky scroll container style
- existing frontend helper tests should continue to pass
- backend tests remain unchanged

## Non-Goals

- changing backend APIs
- redesigning chart rendering
- removing period navigation
- removing endpoint detail

## Risks

- reducing cards too aggressively could hide useful fleet context
- removing the overview snapshot means users rely more on the right detail panel being visible

## Mitigations

- keep model chips prominent under overview charts
- keep desktop two-column layout
- remove internal scroll from detail so the full sheet reads more naturally
