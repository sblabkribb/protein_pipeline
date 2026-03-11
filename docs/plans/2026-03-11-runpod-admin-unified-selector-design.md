# RunPod Admin Unified Selector Redesign

**Date:** 2026-03-11

**Goal:** Rebuild the RunPod admin dashboard around a single endpoint selector so monitoring stays readable, `All` mode is the default, and settings/patch controls stay available without dominating the page.

## Context

The current dashboard still asks the operator to parse multiple endpoint surfaces at once:

- `Fleet Overview` contains fleet charts plus managed endpoint chips
- `Serverless watchboard` lists all endpoints again
- the right detail panel shows a third endpoint-focused surface
- header actions expose `Pipeline API Base` and auth actions even though they are setup tasks, not monitoring tasks

The result is functional but noisy. Clicking a managed endpoint chip also forces the operator to keep jumping between top and bottom regions.

## Approved Direction

The user approved a single monitoring flow:

1. keep `Fleet Overview` first
2. move the endpoint selector directly under overview content
3. add an explicit `All` button as the default scope
4. replace the separate watchboard/detail split with one unified endpoint area
5. in `All`, show compact endpoint cards only
6. in single-endpoint mode, show only that endpoint's full detail sheet
7. hide `Pipeline API Base` and related controls in collapsed settings
8. reduce the header to a compact one-line title

## Information Architecture

### Header

- one-line title only
- refresh remains directly visible
- setup/auth controls move into a collapsed `Settings` panel

### Fleet Overview

- summary cards
- period preset + previous/next navigation
- fleet usage/spend charts
- comparison strip
- endpoint selector row:
  - `All`
  - managed endpoint chips

### Unified Endpoint Area

- one section only
- `All` mode:
  - compact endpoint list
  - each card shows status, load, spend, and one concise action
- single-endpoint mode:
  - one authoritative detail sheet
  - charts, worker table, downloads, quick actions, and patch controls

## Interaction Model

### Selector state

- default state is `All`
- clicking a selector chip switches scope without creating a second summary surface
- clicking a compact endpoint card also switches to that endpoint's single-detail mode
- the `All` button returns to the fleet card list

### Downloads

- fleet downloads remain visible in overview
- endpoint downloads appear only in single-endpoint mode

### Settings

- collapsed by default
- contains:
  - `Pipeline API Base`
  - `Save API`
  - `Health`
  - `Main Console`
  - `Logout`

## Simplification Rules

- one endpoint surface at a time
- overview is fleet-only
- setup controls are hidden until needed
- titles should not wrap into a large hero block
- prefer short labels and obvious actions over duplicated explanations

## Non-Goals

- changing backend APIs
- changing chart math or calendar-window logic
- removing patch/edit capability
- removing comparison or export support

## Risks

- hiding setup controls too aggressively could make them feel lost
- `All` mode could still feel dense if endpoint cards stay too detailed

## Mitigations

- keep a clearly labeled `Settings` disclosure near the top
- keep compact endpoint cards limited to core operational metrics
- use `All` as an obvious reset state in the selector row

## Testing Strategy

- frontend tests should verify:
  - compact header/title presence
  - `Settings` disclosure contains `Pipeline API Base`
  - selector row includes `All`
  - old `Serverless watchboard` heading is removed
  - unified endpoint area container exists
- existing period navigation and comparison helper tests must continue to pass
- backend regression tests remain unchanged
