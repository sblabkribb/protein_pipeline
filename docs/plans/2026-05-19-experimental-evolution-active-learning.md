# Experimental Evolution Active Learning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split AF2-budget surrogate triage from evolution, and make evolution default to an experimental-feedback active-learning workflow.

**Architecture:** `surrogate_triage_*` remains the standard pipeline path for reducing AF2/ColabFold calls. `evolution_mode` gains `evolution_label_source`, where `experimental` generates and ranks experiment candidates from wet-lab labels, while `in_silico_af2` preserves the previous computational-oracle behavior.

**Tech Stack:** Python pipeline MCP backend, JSONL run artifacts, frontend static UI, Markdown manuscript.

---

### Task 1: Backend Request Contract

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Test: `pipeline-mcp/tests/test_experimental_evolution.py`

**Steps:**
1. Add failing tests for parsing `evolution_label_source=experimental` and schema exposure.
2. Add `evolution_label_source: str = "experimental"` to `PipelineRequest`.
3. Parse and validate `experimental` and `in_silico_af2` in `pipeline_request_from_args`.
4. Add schema documentation.
5. Verify targeted pytest.

### Task 2: Experimental Evolution Engine

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/evolution.py`
- Test: `pipeline-mcp/tests/test_experimental_evolution.py`

**Steps:**
1. Add failing tests that experimental evolution does not call AF2 and writes `experiment_request.csv`.
2. Load experiment labels from `experiments.jsonl` using `sample_id`, `candidate_id`, or `sequence_id`.
3. If no labels exist, generate a pool and select K-means candidates for experiment.
4. If labels exist, train a surrogate on labelled sequence embeddings and recommend the next Top-K.
5. Preserve previous AF2 behavior under `evolution_label_source="in_silico_af2"`.

### Task 3: UI Controls

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/lib/pipeline.js`
- Test: `frontend/tests/app-syntax.test.js`
- Test: `frontend/tests/pipeline.test.js`

**Steps:**
1. Add failing source tests for label-source controls and experiment candidate fields.
2. Add Evolution label-source selector with `Experimental feedback` default and `In-silico AF2 legacy`.
3. Extend experiment submission fields to include candidate identifiers and metric direction.
4. Ensure request payload carries `evolution_label_source`.
5. Verify targeted frontend tests and production build.

### Task 4: Manuscript Update

**Files:**
- Modify: `docs/manuscript.md`

**Steps:**
1. Reframe Claim 2 as AF2-budget surrogate triage.
2. Reframe evolution as experimental-feedback-ready DBTL support.
3. Keep limitations explicit: no wet-lab validation is claimed in the current benchmark.
4. Verify the manuscript no longer describes current evolution as experimental validation.

### Task 5: Staging Promotion

**Files:**
- Existing GitHub Actions workflow and deploy scripts.

**Steps:**
1. Run targeted backend/frontend tests and frontend build.
2. Inspect dirty worktree and stage only relevant implementation/manuscript files.
3. Commit with a clear message.
4. Push to the deployment branch and promote to `staging` per `.github/workflows/deploy.yml`.
5. Check GitHub Actions and staging health when available.
