# RunPod Admin Period Navigation and Elevated Detail Redesign

**Date:** 2026-03-11

**Goal:** Bring endpoint detail back into the operator's immediate viewport, add previous/next navigation for calendar monitoring periods, and show simple previous-period comparisons for weekly and monthly monitoring.

## Context

The calendar-aligned monitoring update fixed week/month semantics, but two workflow problems remain:

- selecting a managed model or endpoint still sends attention downward because the detail panel lives too far below the monitoring controls
- the operator can only inspect the current week or current rolling multi-month window, not prior weeks or prior months

The intended workflow is operational review:

- inspect the fleet overview
- switch endpoints without long page jumps
- move backward and forward through weekly and monthly periods
- compare the current period to the immediately previous equivalent period

## Approved Direction

The dashboard keeps the same top-level sections, but the workspace below `Fleet Overview` changes:

1. **Fleet Overview**
   - Gains a period navigation rail with:
     - preset dropdown
     - previous button
     - next button
     - current period label
   - Supports:
     - `Week`
     - `Month`
     - `6 Months`

2. **Monitoring Workspace**
   - Changes to a split layout on desktop:
     - left: endpoint monitoring board
     - right: sticky endpoint detail
   - Endpoint/model selection updates the right-hand detail in place without a long scroll jump.

3. **Endpoint Detail**
   - Remains fully featured.
   - Stays in the main workspace so selection feels immediate.
   - Patch controls remain collapsed below monitoring information.

## Time Navigation Semantics

### Week

- Window covers Monday through Sunday in the UI timezone.
- `Previous` moves by one full week.
- `Next` moves by one full week.
- `Next` is disabled when the selected week is the current calendar week.
- Comparison uses the immediately previous week.

### Month

- Window covers the full selected calendar month in the UI timezone.
- `Previous` moves by one calendar month.
- `Next` moves by one calendar month.
- `Next` is disabled when the selected month is the current calendar month.
- Comparison uses the immediately previous month.

### 6 Months

- Window covers six calendar months ending with the selected anchor month.
- `Previous` moves by one month, keeping the six-month span.
- `Next` moves by one month, up to the current anchor month.
- Comparison uses the immediately preceding six-month block.

## Comparison Design

Comparison stays lightweight and numeric in this phase.

- no chart overlay lines
- no arbitrary baseline selection
- no separate compare mode

The dashboard will show compact previous-period deltas for:

- total spend
- average live workers
- average running jobs
- peak queued jobs

These deltas appear near overview KPIs and in the fleet usage/spend cards so the user can read "current vs previous" without decoding an overlaid chart.

## Information Architecture

### Fleet Overview

- controls row becomes:
  - preset dropdown
  - previous button
  - next button
  - current period label
- model chips remain under the overview charts
- overview cards gain previous-period delta notes where period-based metrics make sense

### Monitoring Workspace

- left rail remains the endpoint watchboard
- right column becomes the selected endpoint sheet
- detail stays visible while the left list scrolls
- on narrow screens the detail collapses above the list instead of staying sticky

### Selection Behavior

- clicking a model chip updates detail immediately
- clicking an endpoint card updates detail immediately
- neither action should trigger a long downward scroll on desktop
- mobile can still use a shorter scroll into the nearby detail block if needed

## Data Flow

- frontend stores:
  - selected preset
  - selected monitoring window
  - previous comparison window
- refresh flow requests:
  - current history window
  - comparison history window
  - current billing ledger window
- current and previous metrics are summarized client-side from the returned history series

## Testing Strategy

- frontend tests for:
  - `month` window creation
  - shifting windows forward/backward
  - disabling navigation into future periods
  - previous-period window derivation
  - HTML markup containing previous/next controls
- end-to-end verification:
  - switch to `Month`
  - move to previous month
  - confirm label and charts update
  - compare cards change
  - select endpoint from overview without long downward jump

## Non-Goals

- arbitrary custom date picker ranges
- overlaid compare lines on charts
- server-side compare endpoints
- saved named reports

## Risks

- sticky detail can make the desktop layout feel cramped if widths are not balanced
- previous/current comparisons can be misleading if a future period is accidentally selectable
- multi-month navigation can become confusing if labels do not clearly reflect the current anchor

## Mitigations

- keep detail width moderate and mobile-responsive
- clamp `Next` when the selected period reaches the current period
- show explicit period labels such as `March 2026` or `Oct 2025 - Mar 2026`
