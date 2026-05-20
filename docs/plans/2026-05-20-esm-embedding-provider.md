# ESM Embedding Provider Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move ESM-2 embedding for surrogate triage/evolution to a configurable GPU worker while keeping AF2/ColabFold acquisition capped.

**Architecture:** Add an `esm_embedding` model provider to RAPID. The provider can be RunPod Serverless or HTTP API backed. RAPID sends SoluProt-passing sequence pools to the provider, receives a float32 embedding matrix, then keeps K-means, AF2 labelling, surrogate fitting, and Top-K acquisition in the existing pipeline code.

**Tech Stack:** Python, RunPod Serverless, FastAPI optional HTTP mode, PyTorch, transformers, numpy, pytest, vanilla JS frontend.

---

### Task 1: GPU Worker Package

**Files:**
- Create: `workers/esm_embedding/Dockerfile`
- Create: `workers/esm_embedding/requirements.txt`
- Create: `workers/esm_embedding/embedder.py`
- Create: `workers/esm_embedding/handler.py`
- Create: `workers/esm_embedding/http_server.py`
- Create: `workers/esm_embedding/test_payload.json`
- Create: `workers/esm_embedding/README.md`

**Steps:**
1. Implement shared ESM-2 embedding code returning `npz_b64`.
2. Wrap it in a RunPod handler.
3. Add optional FastAPI server for persistent GPU HTTP deployments.
4. Document build, push, endpoint setup, validation payload, and expected output.

### Task 2: RAPID Provider Integration

**Files:**
- Create: `pipeline-mcp/src/pipeline_mcp/clients/esm_embedding.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/model_providers.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/app.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/evolution.py`
- Test: `pipeline-mcp/tests/test_model_provider_runner.py`
- Test: `pipeline-mcp/tests/test_surrogate_triage.py`

**Steps:**
1. Add `esm_embedding` to the model registry.
2. Add RunPod and HTTP clients that decode `npz_b64`.
3. Attach `esm_embedding` to `PipelineRunner`.
4. Use the provider before local ESM fallback in surrogate triage and evolution.
5. Add tests for provider selection and embedding path use.

### Task 3: UI And Manuscript

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/tests/app-syntax.test.js`
- Modify: `docs/manuscript.md`
- Modify: `public_release/manuscript/supplementary.md`

**Steps:**
1. Update surrogate UI copy to mention GPU ESM embedding and a 10,000-candidate operating pool.
2. Ensure model provider UI naturally lists `ESM Embedding`.
3. Update manuscript/supplementary language to describe GPU-backed ESM embedding worker and fallback behavior.

### Task 4: Verification And Deployment Order

**Steps:**
1. Run backend and frontend focused tests.
2. Build frontend.
3. Sync `public_release`.
4. Apply changes to `/opt/protein_pipeline-dev` first.
5. Validate dev health.
6. Apply the same changes to `/opt/protein_pipeline-staging`.
7. Validate staging health and note any dirty worktree state.
