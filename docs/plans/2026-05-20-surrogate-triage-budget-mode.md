# Surrogate Triage Budget Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align RAPID claim 2, code, UI, and manuscript artifacts around AF2-budgeted surrogate triage rather than experimental-feedback evolution.

**Architecture:** The standard pipeline keeps `evolution_mode=False` for surrogate triage. It labels a K-means-selected bootstrap set with AF2/ColabFold, trains one or more local surrogates, rank-averages held-out predictions when multiple models are selected, and evaluates only Top-K acquisitions. Experimental-feedback evolution remains a separate assay-label mode.

**Tech Stack:** Python pipeline backend, vanilla JS frontend, pytest, node:test, matplotlib/pandas manuscript utilities, pandoc for DOCX regeneration.

---

### Task 1: Multi-Model Surrogate Triage Backend

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Test: `pipeline-mcp/tests/test_surrogate_triage.py`

**Steps:**
1. Add failing tests for list-valued `surrogate_triage_model`.
2. Parse `surrogate_triage_model` as either a string or list of model names.
3. Normalize comma/newline-separated strings, expand `ensemble`, and reject unsupported names.
4. Use single-model prediction for one model and rank-mean prediction for multiple models.
5. Write metadata fields `models`, `selection_strategy`, and `fitted_models`.

### Task 2: Frontend Multi-Selection

**Files:**
- Modify: `frontend/lib/pipeline.js`
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/pipeline.test.js`

**Steps:**
1. Add failing test for surrogate model selection normalization.
2. Replace the single surrogate selector with a multi-selector.
3. Send one model as a string and multiple models as an array.
4. Update tutorial/help text to state why defaults are 30 training and 20 Top-K.

### Task 3: Manuscript Run Scripts and Artifacts

**Files:**
- Create: `scripts/paper_runs/03_launch_surrogate_triage_budget.py`
- Create: `scripts/paper_runs/05_collect_surrogate_triage_budget.py`
- Modify: `scripts/benchmark/11_make_method_figures.py`
- Modify: `docs/manuscript.md`
- Modify: `public_release/manuscript/manuscript.md`
- Modify: `public_release/manuscript/supplementary.md`

**Steps:**
1. Add a launcher that runs standard pipeline surrogate triage with RFD3/BioEmu/Relax disabled.
2. Add a collector that summarizes AF2 call budget, reduction ratio, and selected models from run artifacts.
3. Update Figure 2 wording from active-learning loop to AF2-budgeted surrogate triage.
4. Move experimental-feedback evolution to a limited extension in the manuscript.
5. Regenerate DOCX files after Markdown edits.

### Task 4: Verification

**Commands:**
- `PYTHONPATH=pipeline-mcp/src /opt/protein_pipeline/venv/bin/python -m pytest pipeline-mcp/tests/test_surrogate_triage.py -q`
- `npm test -- --test-name-pattern='surrogate|Surrogate'`
- `python scripts/benchmark/11_make_method_figures.py`
- `python scripts/paper_runs/03_launch_surrogate_triage_budget.py --dry-run`

