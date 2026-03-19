# Home, Rounds, and Product Shell Design

## Summary

This redesign replaces the current top-tab-first console with an action-oriented product shell.
The default landing page becomes `Home`, not `Setup`.
`Home` acts as a launcher with light context, while deeper operational views move into dedicated areas such as `Rounds`, `Monitor`, and `Analyze`.

The product should feel closer to a polished scientific platform than a developer console:

- clean, editorial layout
- stronger typography hierarchy
- restrained motion and depth
- obvious entry points for novice and expert users

## Goals

- Make first entry understandable without exposing the full setup form immediately.
- Split primary creation flows into three clear modes: `Fast`, `Advanced`, `Studio`.
- Introduce a `Project > Round > Run` mental model that supports repeated experimental cycles.
- Prepare the UI and data model for future round-level ML guidance without shipping unfinished model UX now.
- Replace the current top tab bar with a cleaner sidebar-driven application shell.

## Non-goals

- Do not implement ML candidate suggestion UX now.
- Do not redesign the scientific logic of the pipeline itself as part of this work.
- Do not attempt a full backend multi-tenant project system beyond what is needed for round metadata.

## Product Information Architecture

### Primary Navigation

The application shell should use a left sidebar with the following sections:

- `Home`
- `Fast`
- `Advanced`
- `Studio`
- `Rounds`
- `Monitor`
- `Analyze`
- `MCP`

`Home` becomes the default route after login.

### Home

`Home` is not a metrics-heavy dashboard.
It is a launcher with minimal context.

Recommended layout:

1. top context strip
   - active project selector
   - active round selector
2. primary action cards
   - `Fast`
   - `Advanced`
   - `Studio`
3. light context rail
   - active round status
   - runs in progress
   - recent report/result
4. quick actions
   - continue active round
   - open monitor
   - open analyze

This keeps the first screen clean while still grounding users in current work.

### Fast

`Fast` is the low-friction launch surface.
It should accept a minimal set of inputs and auto-configure the rest.

Core expectations:

- user provides PDB or FASTA
- system chooses the standard pipeline defaults
- RFD3 remains off by default
- BioEmu is the default exploratory backbone source
- if ligand context is absent, ligand-only steps are skipped automatically
- user gets a concise review card before launch, not a full expert form

### Advanced

`Advanced` is the explicit configuration surface.
It replaces the current `Setup` role.

Core expectations:

- expose full request controls
- preserve current preflight and validation workflow
- group controls by intent rather than raw backend order when possible
- keep expert-only fields visible here, not on `Home`

### Studio

`Studio` remains the workflow-authoring surface.
It should stay stage-aware and execution-aware, but live inside the new shell.

It remains the place for:

- composing workflow paths
- stage-by-stage reruns
- artifact-aware iteration

### Rounds

`Rounds` becomes the operational dashboard for iterative work.
`Home` launches work; `Rounds` manages cycles.

Recommended layout:

- left list: rounds for current project
- main detail panel: selected round

Round detail should include:

- objective / hypothesis
- linked runs
- selected candidates
- experiment notes and outcomes
- report summary
- next-round notes
- future placeholder for model suggestions

### Monitor and Analyze

These remain specialized workspaces, but they should become round-aware where possible.

- `Monitor`: execution state, resume, retry, per-run status
- `Analyze`: compare, hit list, experiment logging, reports

## Domain Model

### Hierarchy

The application should adopt:

- `Project`
- `Round`
- `Run`

Definitions:

- `Project`: a target or campaign
- `Round`: one design-test-learn cycle inside a project
- `Run`: one concrete pipeline execution attached to a round

### Why This Hierarchy

This hierarchy matches the way users actually operate:

- many runs belong to one round
- multiple rounds belong to one target campaign
- future ML recommendations belong at the round level, not the raw run level

## Persistence Strategy

Rounds should not be browser-only objects.
They need backend persistence.

Recommended persisted entities:

- `project.json`
- `round.json`
- round-linked run references

Suggested minimum fields:

### Project

- `project_id`
- `name`
- `description`
- `target_summary`
- `created_by`
- `created_at`
- `updated_at`

### Round

- `round_id`
- `project_id`
- `parent_round_id`
- `title`
- `goal`
- `hypothesis`
- `notes`
- `status`
- `linked_run_ids`
- `selected_candidates`
- `experiment_summary`
- `created_by`
- `created_at`
- `updated_at`

### Run Linkage

Each pipeline request should optionally include:

- `project_id`
- `round_id`

Legacy runs can remain unattached until imported or assigned.

## Visual Direction

The visual system should follow an `Editorial Lab Modern` direction.

### Style Principles

- generous whitespace
- stronger display typography
- subdued scientific color palette
- soft depth instead of glossy effects
- motion limited to transitions, reveals, and hover lift

### Typography

Recommended pairing:

- display/headings: `Space Grotesk`
- UI/body: `Instrument Sans`
- numeric/technical: `IBM Plex Mono`

### Color

- warm off-white base background
- dark ink body text
- restrained teal accent
- state colors used sparingly and primarily in monitoring contexts

### Motion and Depth

- subtle fade/slide transitions
- card hover lift with soft shadow
- no heavy floating glass or exaggerated 3D treatment

## Migration Strategy

This should be delivered incrementally.

### Phase 1

- new shell
- sidebar
- `Home`
- `Fast` and `Advanced` split
- Studio moved into new shell

### Phase 2

- backend round metadata
- `Rounds` UI
- run-to-round linkage

### Phase 3

- round-aware monitor/analyze
- improved summaries and entry actions
- placeholder future hooks for ML suggestions

## Future ML Integration

Do not ship model-driven recommendations now.
Instead, leave the data model and round detail surface ready for future use.

When the model is ready, it should appear inside `Round` detail as:

- candidate suggestions
- next round proposal
- learning from assay outcomes

This is intentionally deferred so unfinished model behavior does not leak into the primary UX.

## Success Criteria

- first-time users can start a run without seeing the full expert form
- experienced users still have a complete expert path
- iterative work has an explicit home in `Rounds`
- the product looks like a scientific platform, not an internal tool panel
- future ML guidance can attach to `Round` detail without another top-level IA rewrite
