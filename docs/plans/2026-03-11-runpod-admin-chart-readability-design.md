# RunPod Admin Chart Readability Refresh

**Date:** 2026-03-11

**Goal:** Make RunPod monitoring charts readable at a glance by adding numeric scale cues, sparse time labels, and period-aligned chart rollups that avoid repeated same-day axis text.

## Context

The current dashboard charts show trend lines, but operators still have to infer too much:

- charts do not expose visible numeric scale values on the graph itself
- x-axis labels render one label per sample, which creates noisy repeats such as `Mar 11` dozens of times
- selecting a single endpoint can introduce raw snapshot history that is denser than the current calendar window implies

The result is visually active but operationally weak. The chart tells you a shape, but not enough numbers.

## Approved Direction

The user approved the monitoring-oriented chart treatment:

1. add numeric values so charts are readable without guessing
2. stop flooding the x-axis with repeated date labels
3. keep period semantics aligned with the chosen preset
4. show compact numeric summaries under each chart

## Root Cause

Two separate issues are combining into the bad experience:

1. **Presentation problem**
   - SVG lines have no visible y-axis numbers
   - x-axis is rendered from every sample

2. **Data-shaping problem**
   - selected endpoint detail can merge raw usage snapshots into frontend history
   - month/week views then display many samples that collapse to the same visible day label

## Design

### 1. Period-Aligned Chart Samples

Before rendering, frontend chart series will be rolled up to the active monitoring preset:

- `week` and `month` usage charts render one bucket per day
- `months_6` usage charts render one bucket per month
- billing charts follow the same visible calendar grain

Usage buckets use max-per-bucket semantics so the chart preserves operational peaks for workers, queued, and running. Billing buckets sum cost and record counts.

### 2. Sparse Time Axis

Charts will no longer print one label for every point.

- use at most 5-7 labels depending on the chart width/preset
- always include first and last visible labels
- use evenly sampled intermediate labels
- keep the existing month names for 6-month views

This removes `Mar 11` repetition and turns the axis back into orientation rather than noise.

### 3. Numeric Scale on the Chart

Each chart gets a left-side y-axis with simple numeric scale labels:

- top value
- midpoint
- zero

Counts stay integer-friendly. Spend can keep currency formatting.

### 4. Numeric Summary Row

Each chart gets a compact summary row below the plot:

- usage series: `latest`, `avg`, `peak`
- spend series: `latest`, `total`, `peak`

This replaces guesswork with immediately scannable numbers while keeping the line chart for trend context.

### 5. Detail History Safety

Selected endpoint detail should not degrade the current period chart view.

- detail fetches may still return endpoint history for other uses
- chart rendering will use period-aligned rolled samples
- the frontend should avoid overwriting current rolled monitoring history with raw endpoint-detail snapshots

## Non-Goals

- adding hover tooltips
- changing backend history storage
- redesigning comparison cards
- changing CSV export formats

## Testing Strategy

- add frontend helper tests for:
  - usage rollup collapsing multiple same-day samples into one daily point
  - sparse tick generation limiting label count
  - chart scale label generation
- add static CSS tests for chart axis and stats-row classes
- keep existing frontend period-window tests green
- keep backend regression tests unchanged
