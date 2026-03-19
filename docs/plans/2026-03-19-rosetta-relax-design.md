# Rosetta Relax Adoption and Integration Design

**Goal:** Add Rosetta FastRelax as a supplementary quality metric for designed structures, while de-risking licensing, installation, and runtime integration on the current NPC host.

**Scope**

- Decide whether Rosetta can be used in this environment from a licensing and deployment perspective.
- Choose a validation path that fits the current infrastructure.
- Define how FastRelax should be integrated into the existing pipeline as a post-AF2 analysis stage.
- Expose relax results in Analyze first, and allow cutoff control from advanced settings and Workflow Studio.
- Keep hit-list weighting out of the first iteration unless a later pass shows it is needed.

**Context**

- `pipeline-mcp` is currently a host Python service started by systemd, not a long-lived containerized backend.
- Docker is available on this host, so short-term validation can use an isolated Rosetta runtime.
- No Rosetta binaries are currently installed on the host or visible in `PATH`.
- The existing metric flow is `SoluProt -> AF2 pLDDT/RMSD -> summary/tools.py -> Analyze/Hit List/Studio`.

**Decision**

- Public Rosetta servers are useful only for manual spot checks.
  - They are not appropriate as the primary runtime for this feature because they are public shared resources and do not fit repeatable pipeline automation.
- Docker on the NPC is the best first validation path.
  - It avoids an immediate host install.
  - It can prove that FastRelax works on representative AF2 outputs before the backend is changed.
- Native host installation is the best steady-state runtime if the feature is kept.
  - `pipeline-mcp` runs on the host, so direct subprocess execution is simpler than forcing the backend to shell out to Docker forever.

**License Gate**

- The first gate is usage classification, not technical setup.
- If the intended use is academic or otherwise non-commercial research, proceed with Rosetta evaluation and installation under the non-commercial path.
- If the intended use is commercial, customer-facing, or company-internal product work that requires a paid Rosetta license, stop before installation and route through the commercial licensing path.
- The implementation should assume that the operator confirms the correct license path before enabling relax in production.

**TensorFlow / GPU**

- FastRelax does not require TensorFlow for the intended use here.
- CPU-only execution is acceptable for the first iteration.
- GPU support is not a requirement for this feature.

**Metric Choice**

- The first iteration should not use raw Rosetta `total_score` as the only UI-facing cutoff metric.
- The persisted artifact should include:
  - `total_score`
  - `score_per_residue`
  - `delta_total_score` versus the input AF2 structure score when available
- The default cutoff field should use `score_per_residue`.
  - It is length-normalized.
  - It is easier to compare across candidates and future workflows.
- Analyze can still show `total_score` and `delta_total_score` as supporting context.

**Pipeline Placement**

- Add a new `relax` stage after AF2 selection and before novelty.
- Only run relax on `af2_selected_ids`.
  - This keeps CPU cost bounded.
  - It matches the user intent that relax is a secondary judgment metric rather than a full replacement for AF2 filtering.
- Stage order becomes:
  - `msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> relax -> novelty`

**Runtime Design**

- Add a Rosetta relax client with two supported execution modes:
  - `docker` mode for initial validation and fallback operation
  - `native` mode for the expected long-term host runtime
- The client should accept an input PDB text plus lightweight runtime options and return:
  - best relaxed PDB text
  - parsed score table
  - computed metrics
  - runtime metadata such as mode, image/binary, and command summary

**Artifact Layout**

- For each selected candidate:
  - `tiers/<tier>/relax/<seq_id>/input.pdb`
  - `tiers/<tier>/relax/<seq_id>/relaxed_0001.pdb`
  - `tiers/<tier>/relax/<seq_id>/score.sc`
  - `tiers/<tier>/relax/<seq_id>/metrics.json`
- Tier summary:
  - `tiers/<tier>/relax_scores.json`
- Suggested tier summary schema:
  - `score_per_residue`
  - `total_score`
  - `delta_total_score`
  - `candidate_ids`
  - `passed_ids`
  - `selected_ids`
  - `cutoff`
  - `nstruct`
  - `runtime_mode`
  - `runtime_label`
  - `failed_ids`
  - `errors`
  - `cached`

**Backend Request Model**

- Add request fields:
  - `relax_enabled: bool`
  - `relax_cutoff: float | None`
  - `relax_nstruct: int`
  - `relax_extra_flags: str | None`
- `relax_cutoff` applies to `score_per_residue`, where lower is better.
- Keep the default conservative:
  - If Rosetta is not configured, `relax_enabled=false` by default.

**Failure Handling**

- If `relax_enabled=false`, skip the stage cleanly.
- If `relax_enabled=true` but the runtime is unavailable:
  - Record a stage error.
  - Persist an empty `relax_scores.json` with an explicit runtime/config reason.
  - Do not destroy AF2 outputs.
- If one candidate fails and others succeed:
  - Keep per-candidate errors in `relax_scores.json`.
  - Continue to aggregate available metrics.

**UI Design**

- Analyze:
  - Show relax medians and pass counts in run summary tables.
  - Add a relax column to candidate tables and detail markdown export.
  - Include relax deltas in run-to-run compare once backend summaries expose them.
- Advanced settings / Setup:
  - Expose `relax_enabled`, `relax_cutoff`, and `relax_nstruct`.
- Workflow Studio:
  - Add a dedicated `relax` stage after `af2`.
  - Allow reruns from `relax` forward.
  - Require AF2 outputs when starting from `relax`.
- Hit List:
  - Show relax as a passive column if desired in the first pass.
  - Do not add relax weight to the composite score yet.

**Why Not Weight It Immediately**

- The user asked for a supporting judgment metric and cutoff control.
- Adding it to ranking at the same time would introduce a second design choice:
  - how to normalize it
  - how to trade it off against pLDDT/RMSD/SoluProt
- The first iteration should stop at:
  - run relax
  - persist metrics
  - show in Analyze
  - allow cutoff in Setup and Studio

**Testing**

- Validation before code integration:
  - Confirm the host can pull and run the official Rosetta Docker image.
  - Confirm FastRelax runs on one representative PDB and produces `score.sc`.
- Backend tests:
  - request parsing and schema
  - stage ordering / partial rerun support
  - relax artifact generation with a fake client
  - aggregation into compare/hit-list payloads
- Frontend tests:
  - Setup/Studio field ownership and defaults
  - dependency checks for the new `relax` stage
  - Analyze rendering for relax metrics

**Recommendation**

- Use a two-phase rollout:
  - Phase 1: confirm the license path and run a Docker-based FastRelax smoke test on the NPC.
  - Phase 2: integrate a host-oriented Rosetta client into `pipeline-mcp`, using Analyze display and stage cutoffs but no hit-list weighting.
