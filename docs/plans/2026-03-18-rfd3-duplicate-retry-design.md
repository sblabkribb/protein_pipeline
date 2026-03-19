# RFD3 Duplicate Retry Design

**Goal:** Preserve raw RFD3 outputs, detect duplicate backbones early, and retry with independent jobs when batch sampling collapses, while allowing strict failure in test/debug runs and non-blocking continuation in production.

**Architecture:** Keep the existing RFD3 batch request path as the first attempt, then deduplicate exact CA-coordinate duplicates before downstream propagation. When duplicates collapse the unique backbone count below the requested count, optionally retry with independent one-design jobs, aggregate all raw candidates, persist debug artifacts, and only fail when strict duplicate enforcement is enabled.

**Key Decisions**

- Treat the current issue as an upstream sampling collapse, not a handler truncation bug.
- Preserve raw `designs.json` semantics and add explicit raw artifacts for debugging:
  - `rfd3/raw_designs.json`
  - `rfd3/raw_designs/*.pdb`
  - `rfd3/debug_summary.json`
- Add backend-only request controls first:
  - `rfd3_sampling_strategy = auto | batch | independent_jobs`
  - `rfd3_fail_on_duplicate_backbones = bool`
- Default behavior:
  - `rfd3_sampling_strategy = auto`
  - `rfd3_fail_on_duplicate_backbones = false`
- `auto` behavior:
  - Run the current batch request first.
  - If unique count is below requested count, run independent single-design jobs for the remaining target count.
  - Continue with deduplicated unique backbones unless strict mode is enabled.
- Test/debug behavior:
  - When `rfd3_fail_on_duplicate_backbones = true`, raise after retries if unique backbone count is still below the requested count.

**Artifacts**

- `rfd3/designs.json`: aggregate raw candidate records used for cache/reload.
- `rfd3/raw_designs.json`: explicit debug copy of raw candidate records.
- `rfd3/raw_designs/*.pdb`: per-candidate raw PDBs before deduplication.
- `rfd3/designs/*.pdb`: deduplicated propagated PDBs only.
- `rfd3/diversity_summary.json`: dedup summary, now extended with sampling strategy and retry stats.
- `rfd3/debug_summary.json`: troubleshooting-oriented summary including raw counts, unique counts, retry attempts, and input RMSD stats.

**Scope**

- Backend pipeline and request parsing.
- Tests for duplicate retry, strict failure, and raw artifact persistence.
- Service restart after backend changes.
