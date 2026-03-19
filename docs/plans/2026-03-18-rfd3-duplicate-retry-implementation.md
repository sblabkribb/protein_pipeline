# RFD3 Duplicate Retry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add RFD3 duplicate-backbone retry/debug behavior so the pipeline preserves raw outputs, retries with independent jobs after batch collapse, and optionally fails in strict test/debug mode.

**Architecture:** The pipeline will keep batch sampling as the first attempt, aggregate raw RFD3 candidates across batch and retry attempts, deduplicate on exact CA coordinates, and persist debug artifacts. Request parsing will expose strategy and strictness flags, while strict failure remains opt-in so production runs continue with deduplicated unique backbones.

**Tech Stack:** Python dataclasses, existing pipeline RFD3 stage logic, pytest.

---

### Task 1: Add failing tests for duplicate retry and strict failure

**Files:**
- Modify: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Write failing tests**

- Add a test where the first RFD3 batch response contains only duplicate backbones and follow-up single-job retries return unique backbones. Assert:
  - retry calls happened
  - `rfd3/raw_designs.json` exists
  - `rfd3/raw_designs/*.pdb` contains all raw attempts
  - `rfd3/designs/*.pdb` contains deduplicated unique backbones
  - `rfd3/debug_summary.json` records strategy and retries
- Add a strict-mode test where batch and retries all remain duplicates. Assert the run raises with a duplicate-backbone error.

**Step 2: Run tests to verify they fail**

Run: `env PYTHONPATH=src uv run pytest tests/test_pipeline_dry_run.py -k "duplicate_backbones"`  
Expected: FAIL because retry/debug/strict logic does not exist yet.

### Task 2: Add backend request fields and parsing

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/router.py`
- Modify: `pipeline-mcp/scripts/run_pipeline_rfd3.py`

**Step 1: Add request fields**

- `rfd3_sampling_strategy: str | None = None`
- `rfd3_fail_on_duplicate_backbones: bool = False`

**Step 2: Parse and validate**

- Accept the new fields from tool args/schema.
- Pass them through the RFD3 helper CLI script.
- Add prompt parsing support in `router.py` so debugging prompts can mention them.

**Step 3: Run targeted parser tests**

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py -k "rfd3"`  
Expected: FAIL first, then PASS after implementation.

### Task 3: Implement raw artifact persistence and retry strategy

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`

**Step 1: Add helpers**

- Normalize sampling strategy values.
- Build unique local IDs for retry attempts.
- Persist raw candidate JSON/PDB artifacts.
- Build extended debug/diversity summaries.
- Produce a duplicate-backbone error message for strict mode.

**Step 2: Implement RFD3 retry flow**

- Keep batch sampling as the first attempt for `auto`/`batch`.
- For `auto`, if batch uniqueness is below requested count, issue single-design retry jobs for the remaining target count.
- For `independent_jobs`, skip batch and run one-design jobs only.
- Aggregate all raw candidates, deduplicate once, then persist deduplicated propagated designs.

**Step 3: Enforce strict behavior**

- If `rfd3_fail_on_duplicate_backbones=true` and unique count remains below requested count after retries, raise `BackboneContractError`.
- If strict mode is off, continue with deduplicated unique backbones and record the warning/debug summary.

**Step 4: Re-run failing tests**

Run: `env PYTHONPATH=src uv run pytest tests/test_pipeline_dry_run.py -k "duplicate_backbones"`  
Expected: PASS

### Task 4: Verify broader regressions

**Files:**
- Modify if needed: `pipeline-mcp/tests/test_tools.py`
- Modify if needed: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Run targeted suite**

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py tests/test_pipeline_dry_run.py`

**Step 2: Restart backend service**

Run: `systemctl restart pipeline-mcp.service`

**Step 3: Verify service health**

Run: `systemctl is-active pipeline-mcp.service`  
Run: `curl -sS http://127.0.0.1:18080/healthz`

**Step 4: Commit**

```bash
git add docs/plans/2026-03-18-rfd3-duplicate-retry-design.md \
  docs/plans/2026-03-18-rfd3-duplicate-retry-implementation.md \
  pipeline-mcp/src/pipeline_mcp/models.py \
  pipeline-mcp/src/pipeline_mcp/tools.py \
  pipeline-mcp/src/pipeline_mcp/router.py \
  pipeline-mcp/scripts/run_pipeline_rfd3.py \
  pipeline-mcp/src/pipeline_mcp/pipeline.py \
  pipeline-mcp/tests/test_tools.py \
  pipeline-mcp/tests/test_pipeline_dry_run.py
git commit -m "feat: add RFD3 duplicate retry diagnostics"
```
