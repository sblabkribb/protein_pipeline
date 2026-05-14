# Model Provider Registry and Auth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the RFP-aligned model provider registry, model-management roles, user approval gate, and Google OAuth2/OIDC-ready login flow.

**Architecture:** Keep `pipeline-mcp` as the orchestrator. Add a file-backed provider registry under `PIPELINE_OUTPUT_ROOT` that can resolve each model to RunPod, HTTP API, or disabled mode while preserving existing `.env` fallbacks. Extend auth/OIDC public user payloads with `status` and `model_manager` role handling so admins and approved model managers can manage model endpoints.

**Tech Stack:** Python stdlib JSON storage, existing `ToolDispatcher` MCP tools, existing cookie/OIDC session auth, frontend static HTML/JS, Node tests, pytest.

---

### Task 1: Provider Registry Backend

**Files:**
- Create: `pipeline-mcp/src/pipeline_mcp/model_providers.py`
- Test: `pipeline-mcp/tests/test_model_providers.py`

**Steps:**
1. Write tests for default `.env` fallback provider listing, HTTP provider upsert, token masking, and health check payload.
2. Run the new tests and verify they fail because the module does not exist.
3. Implement `ModelProviderStore` with model specs for `mmseqs`, `proteinmpnn`, `colabfold`, `alphafold2`, `esmfold`, `rfd3`, `bioemu`, `diffdock`, and `rosetta_relax`.
4. Run tests and verify they pass.

### Task 2: Provider Tools and Permissions

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/http_server.py`
- Test: `pipeline-mcp/tests/test_model_providers.py`
- Test: `pipeline-mcp/tests/test_http_server_auth.py`

**Steps:**
1. Write tests proving `pipeline.model_provider_list`, `pipeline.model_provider_update`, and `pipeline.model_provider_health` exist.
2. Write permission tests proving `model_manager` can call provider tools and normal `user` cannot.
3. Implement tools and `_is_model_manager`.
4. Run focused tests.

### Task 3: Registry-Based Runner Resolution

**Files:**
- Create: `pipeline-mcp/src/pipeline_mcp/clients/local_http.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/app.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/config.py`
- Test: `pipeline-mcp/tests/test_model_provider_runner.py`

**Steps:**
1. Write tests proving HTTP provider entries create local HTTP-backed clients for existing model keys.
2. Implement minimal HTTP adapter classes that preserve current client method interfaces by posting `{"input": payload}` to `/run`.
3. Make `build_runner()` consult provider registry first and `.env` fallbacks second.
4. Run focused tests.

### Task 4: Approval and Google OIDC

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/auth.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/oidc.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/http_server.py`
- Test: `pipeline-mcp/tests/test_oidc_auth.py`
- Test: `pipeline-mcp/tests/test_http_server_auth.py`

**Steps:**
1. Write tests for pending OIDC user rejection, approved user acceptance, and `pipeline-model-manager` role mapping.
2. Add Google issuer shorthand/default support without hard-coding a client id.
3. Add approval store backed by the existing auth user store.
4. Run focused tests.

### Task 5: Frontend Model Providers UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Test: `frontend/tests/runpod-admin.test.js` or a new `frontend/tests/model-providers.test.js`

**Steps:**
1. Add tests for provider option normalization and masked token rendering.
2. Rename the topbar action from RunPod Admin to Model Providers.
3. Add a compact provider modal that lists models, provider type, endpoint/url, ready state, and health check/update actions.
4. Run Node frontend tests and `npm run build`.

### Task 6: Dev Rollout

**Files:**
- Commit all changed files.

**Steps:**
1. Run focused backend and frontend tests.
2. Commit and push `develop`.
3. Confirm GitHub Actions dev deploy succeeds.
4. Verify dev `/api/healthz`.
