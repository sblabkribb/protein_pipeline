# KBF Protein Solubility and Stability Platform Redesign Design

## Decision

The deployed product name will be **KBF Protein Solubility & Stability Platform** in the UI and **KBF Protein Solubility and Stability Platform** in formal copy and documentation. The existing KBF identity stays, but the product framing moves away from a generic "Protein Pipeline Console" toward a focused solubility/stability research platform.

## Goal

Redesign the frontend around experiment launch and evaluation without adding new scientific capabilities or changing backend APIs. The first screen should help users start a new solubility/stability experiment, load an existing run, or inspect results with minimal ambiguity.

## Non-Goals

- No backend API changes.
- No new pipeline stages or scientific features.
- No production-only deployment change in this pass.
- No React/Vue rewrite in the first implementation pass.
- No marketing landing page.

## Product Shape

The first viewport becomes an execution surface, not a dashboard or hero page. Users should immediately see:

- a primary path to create a new solubility/stability experiment,
- a secondary path to load an existing run,
- a direct path to analyze completed results,
- a visible environment badge for development and staging.

The UI should feel like an institutional research platform: dense, calm, precise, and repeatable. It should not feel like a broad SaaS landing page or a decorative product brochure.

## Information Architecture

The main navigation remains recognizable but is renamed and reordered around real workflows:

- **Experiment**: new first screen for run creation and common actions.
- **Fast Setup**: guided quick path for common solubility/stability runs.
- **Advanced Setup**: detailed configuration path.
- **Workflow Studio**: stage-by-stage execution workspace.
- **Monitor**: run status and restart/resume operations.
- **Analyze**: artifacts, hit lists, charts, and reports.
- **Operations**: CATH, RunPod/admin, MCP/help surfaces grouped where possible.

Advanced Setup should no longer read as a long set of unrelated controls. It becomes a staged run builder:

1. **Input**: target PDB/FASTA, optional ligand/paper-derived constraints, selected run import.
2. **Workflow**: run mode, start/stop stages, RFD3/BioEmu/AF2 inclusion.
3. **Criteria**: solubility/stability thresholds, candidate counts, conservation tiers, AF2/Relax gates.
4. **Expert**: RFD3 internals, steering text, fixed positions, raw advanced inputs.
5. **Review**: compact run summary and launch state.

## Visual System

Use Tailwind's palette as a reference rather than importing a one-note Tailwind look. The target palette:

- **Neutral base**: Tailwind slate-inspired surfaces for text, borders, panels, and page chrome.
- **Primary action**: Tailwind teal-inspired action color for run creation, active nav, and focused controls.
- **Positive/scientific success**: Tailwind emerald-inspired success/state color for completed runs and stability-positive outcomes.
- **Caution**: Tailwind amber-inspired warning color for partial inputs, long-running jobs, and review warnings.
- **Error**: Tailwind red/rose-inspired error color for failed runs and validation errors.

The CSS should expose semantic tokens rather than using raw colors everywhere:

```css
:root {
  --surface-canvas: oklch(98.4% 0.003 247.858);
  --surface-panel: #ffffff;
  --surface-muted: oklch(96.8% 0.007 247.896);
  --text-strong: oklch(12.9% 0.042 264.695);
  --text-body: oklch(27.9% 0.041 260.031);
  --text-muted: oklch(55.4% 0.046 257.417);
  --action-primary: oklch(51.1% 0.096 186.391);
  --action-primary-hover: oklch(43.7% 0.078 188.216);
  --state-success: oklch(50.8% 0.118 165.612);
  --state-warning: oklch(66.6% 0.179 58.318);
  --radius-sm: 8px;
  --radius-md: 12px;
}
```

The visual design should use compact panels, 8px card radii where practical, stable grid dimensions, and limited shadows. Avoid decorative orbs, bokeh, oversized hero blocks, and nested cards.

## Component Direction

The first implementation can keep the current static frontend while preparing for better modularization:

- keep `frontend/index.html` as the served entry,
- keep `frontend/app.js` behavior intact,
- use `frontend/styles.css` and `frontend/tailwind-entry.css` for tokens and layout,
- add source tests that guard naming, IA, token usage, and Advanced step behavior.

Expected component patterns:

- **Experiment Launchpad**: compact action panel with three primary lanes: New Experiment, Load Run, Analyze.
- **Run Context Strip**: selected run, environment, run state, and quick actions.
- **Advanced Stepper**: Input, Workflow, Criteria, Expert, Review.
- **Criteria Board**: solubility/stability thresholds and quality gates in one scannable board.
- **Review Card**: final values grouped by input, workflow, criteria, expert overrides.

## Data Flow

No data contract changes are required. Existing `state.answers`, `state.plan`, `buildAnswerPayload()`, `runPreflight()`, and `runPipeline()` remain the source of truth. The redesign should reorganize controls and copy without changing the payload shape sent to the backend.

## Error Handling

Existing validation remains active. The redesigned UI should make failures easier to see:

- missing required input stays attached to the relevant step,
- run submission remains disabled until Review is reached and required inputs pass,
- partial rerun warnings stay explicit,
- deployment environment remains visible on non-production hosts.

## Testing

Use source-based tests first because the current frontend is static and large:

- brand naming tests,
- Tailwind-inspired token tests,
- first-screen action tests,
- Advanced stepper IA tests,
- review card and expert option tests,
- existing deployment test suite.

Browser screenshot verification should be done after deployment to development when Chrome tooling is available. If browser tooling is unavailable, verify deployed HTML/CSS markers and API health over HTTPS.

## Rollout

1. Implement and push to `develop`.
2. Verify GitHub Actions and development deployment.
3. Manually review `https://dev-pipeline.k-biofoundrycopilot.duckdns.org`.
4. Merge `develop` to `staging` only after the new first screen and Advanced flow are usable.
5. Tag production only after staging validation.
