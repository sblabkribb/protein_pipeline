# Pipeline/Studio Consistency Redesign

**Date:** 2026-03-13

**Goal:** Align the pipeline, Setup/Workflow Studio, Analyze, and Copilot around a single truthful contract for backbone generation, propagation, comparison, and WT-difference interpretation.

## Context

The current UI and pipeline expose several mismatches:

- the user can request multiple RFD3/BioEmu structures, but downstream usage is not explained clearly
- Analyze and Compare Studio infer meaning from paths and ad-hoc heuristics instead of a canonical manifest
- Setup residue selection is limited to ad-hoc manual picks and does not support the masking workflows users need
- Compare Studio and Copilot over-compress state into terse summaries that are hard to interpret
- Hit List displays WT difference percentage as a difference rate instead of sequence homology

The 2026-03-10 run `admin_20260310_065409_2f2c2372` showed that this is not just a frontend labeling problem:

- `request.json` requested `rfd3_max_return_designs=10`, `bioemu_num_samples=10`, and `bioemu_max_return_structures=10`
- `rfd3/designs.json` contains ten design records, but only the selected design is materialized for downstream propagation
- `bioemu/sample_pdbs.json` contains only a single `bioemu_topology` sample, so downstream propagation only sees one BioEmu backbone

## Approved Direction

Use a staged contract-first redesign:

1. keep current selected-only downstream behavior as the default when only a representative backbone is materialized
2. make that behavior explicit in pipeline manifests and UI copy instead of hiding it
3. extend Setup and Workflow Studio with a shared residue-selection workspace
4. clean up Analyze, Compare Studio, Hit List, and Copilot so they explain the current run faithfully
5. preserve a clean upgrade path to true multi-backbone propagation when endpoint payloads contain all backbone PDBs

## Architecture

### 1. Backbone Manifest Contract

`backbones.json` becomes the canonical backbone manifest for a run.

Existing `backbones[]` entries remain, but each entry is extended with propagation metadata:

- `selected`
- `propagated`
- `rank`
- `frame_index`
- `origin_stage`
- `origin_artifact`
- `materialized`

The same file gains source-level summaries under `sources`, for example:

- `requested_count`
- `observed_count`
- `materialized_count`
- `propagated_count`
- `selected_backbone_id`
- `propagation_mode`
- `note`

`propagation_mode` is `selected_only` in this redesign unless a source actually materializes multiple backbone PDBs for downstream use.

This makes the current behavior explicit:

- the run may request 10 structures
- the source may observe 10 metadata records
- the pipeline may only materialize or propagate 1 backbone

### 2. Tier-Level Propagation Contract

`tiers/<tier>/proteinmpnn_backbones.json` becomes the canonical per-tier propagation manifest.

Each record describes:

- backbone id and source
- tier-local output directory
- ProteinMPNN output paths
- per-backbone sequence counts
- SoluProt passed count
- AF2 candidate count
- AF2 selected count

Analyze, Hit List, and Copilot read this manifest before inferring structure provenance from file paths.

### 3. Shared Residue Selection Workspace

The existing residue picker is generalized into a shared workspace used by:

- Pipeline Setup
- Workflow Studio design-stage draft editor

The workspace contains:

- structure source switcher
- sequence pane
- structure pane
- selection preset controls
- selection summary and apply action

Selections still write into `fixed_positions_extra` as query positions, so backend request compatibility is preserved.

### 4. Analyze/Copilot Truthfulness Layer

Analyze and Copilot should explain the current run without implying nonexistent breadth.

The UI surfaces:

- how many backbones were requested
- how many were observed
- how many were materialized
- how many were propagated
- which representative backbone is currently selected

Copilot answers must be intent-aware and narrative, not snapshot dumps.

## Setup / Workflow Studio UX

### Residue Selection Workspace

The new workspace keeps a two-pane layout:

- left: chain-aware sequence view
- right: 3D structure view

#### Sequence pane

- residue-level selection by click
- color by amino-acid property
- synchronized highlight with the 3D view

Recommended residue classes:

- hydrophobic
- polar
- positive
- negative
- aromatic
- special

#### Structure pane

Display mode remains `cartoon`.

Color modes:

- secondary structure
- N-to-C spectrum
- by chain

#### Preset selection controls

Supported preset chips:

- `surface`
- `core`
- `interface`
- `conserved 30`
- `conserved 50`
- `conserved 70`

Behavior:

- clicking a chip adds that residue set to the current selection
- chips show count previews where possible
- unsupported chips are disabled with a clear reason

#### Data availability rules

- `surface` and `core` use structure-derived residue exposure
- `interface` uses design-chain context plus non-design-chain or ligand proximity when available
- `conserved *` requires conservation preview data
- if conservation is unavailable in initial Setup, the chips stay disabled until the user loads a run or existing conservation artifact

## Analyze / Compare Studio

### Compare defaults

- default compare mode becomes `sequence`
- left/right default paths remain auto-selected, but the compare metadata must explain whether the right side is:
  - exact candidate
  - per-backbone aggregate
  - source representative

### Explainability improvements

Add inline help affordances for hard-to-read metrics and scope labels:

- AF2/ColabFold selection scope
- exact candidate vs backbone median
- selected/candidates ranges
- residue-linked color categories

### Structure and sequence diff cleanup

- structure-mode legend shows only structure-mode semantics
- sequence-only wording is removed from structure-mode legend
- sequence-mode legend remains sequence-specific

### Residue-linked view

Add an explicit legend for:

- low difference
- medium difference
- high difference
- left-only / WT-only
- right-only / design-only

## Hit List

The WT column changes from “difference percent” to a split semantic:

- count/length remains WT difference count
- percent becomes sequence homology / identity

The display format becomes:

- `diff_count/compare_len · identity%`

This removes the current inversion where frontend logic derives `%` as `100 - identity`.

## Copilot

Copilot answers switch from state dumps to intent-specific responses.

Intent groups:

- metric definition
- metric interpretation
- page usage
- compare explanation
- next action
- resume semantics
- recommendation / top-candidate selection

Response rules:

- define the requested term first
- interpret it using current run values second
- recommend next action third only when useful

Recommendation prompts should rank actual candidates from Hit List rows, not repeat the static top snapshot.

## Error Handling

- if manifests are missing, UI falls back to current path-based heuristics
- if conservation preview is missing, conserved-tier chips stay disabled with explanation text
- if residue metrics are unavailable, Compare Studio still renders the pair and shows an empty-state explanation
- if Copilot lacks the required context, it answers with missing-context guidance instead of stale summaries

## Testing Strategy

### Backend

- Python tests for `backbones.json` source summaries and propagation metadata
- Python tests for hit-list WT homology fields
- regression tests for selected-only propagation manifests

### Frontend

- unit tests for compare defaults, legend text selection, and WT homology formatting
- unit tests for Copilot intent replies
- unit tests for residue-selection preset helpers and sequence-color helpers

### Sample-run verification

Use `admin_20260310_065409_2f2c2372` to verify:

- source counts are displayed truthfully
- selected-only propagation is explicit
- Compare Studio defaults to sequence view
- Hit List shows identity, not inverted difference
- Copilot gives explanatory replies

## Non-Goals

- immediate full rollout of all requested backbones to downstream stages when endpoint payloads do not materialize them
- redesigning the entire Analyze layout
- replacing all artifact filenames on disk in this pass

## Risks

- users may misread “observed” versus “propagated” unless labels are explicit
- adding too much metadata text can clutter Compare Studio
- residue preset logic can drift from backend assumptions if helper logic is duplicated

## Mitigations

- keep source summary wording short and consistent everywhere
- use the manifest as the single source of truth
- keep preset computation in shared helpers with tests
- preserve old path-based fallbacks until manifest-backed rendering is stable
