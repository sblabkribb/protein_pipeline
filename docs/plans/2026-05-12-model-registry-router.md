# Model Registry and Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a configurable model registry so admins and approved users can switch pipeline models between RunPod endpoints and self-hosted GPU HTTP APIs without code changes.

**Architecture:** Keep `pipeline-mcp` as the workflow orchestrator and keep GPU servers as model-serving workers only. Add a backend `ModelRegistry` for registered providers, a `ModelRouter` that selects the effective provider for each model, and admin UI for registration, health checks, and default selection. Start with ProteinMPNN because the GPU HTTP worker is already validated, then extend the same contract to RFD3, BioEmu, Relax, and later AF2/MMseqs.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, `requests`, explicit `cryptography` for encrypted provider secrets, existing `pipeline-mcp` HTTP tool server, existing static frontend.

---

## Scope Decision

Implement this plan after GPU-side workers are validated. Do not block GPU worker rollout on this site work.

### Phase 0: GPU Worker Rollout First

Recommended GPU rollout order:

1. **ProteinMPNN**: already validated through `POST http://211.188.35.221:18101/run`.
2. **Rosetta Relax**: likely the next best candidate because it is a self-contained compute stage and can use a similar `/run` wrapper.
3. **BioEmu**: move after Relax; validate image weights/cache behavior before wiring to production.
4. **RFD3**: move after BioEmu; heavier model behavior and output contract require more validation.
5. **DiffDock**: only if ligand workflows become active.
6. **MMseqs2 / ColabFold / AF2**: last, because database/storage/cache strategy is materially different.

Suggested worker ports:

```text
18101 ProteinMPNN
18102 Rosetta Relax
18103 BioEmu
18104 RFD3
18105 DiffDock
```

Only open each port in ACG after that worker is running and only from the pipeline server IP.

---

## Data Model

### Model Profile

Each registered model profile should have:

```json
{
  "id": "uuid",
  "model_key": "proteinmpnn",
  "display_name": "NCP GPU ProteinMPNN",
  "provider": "http_api",
  "scope": "global",
  "owner_username": null,
  "project_id": null,
  "is_default": true,
  "enabled": true,
  "endpoint": {
    "url": "http://211.188.35.221:18101",
    "runpod_endpoint_id": null
  },
  "secret_ref": "encrypted bearer token or runpod api key",
  "timeout_s": 21600,
  "created_at": "2026-05-12T00:00:00Z",
  "updated_at": "2026-05-12T00:00:00Z",
  "last_health": {
    "ok": true,
    "checked_at": "2026-05-12T00:00:00Z",
    "message": "ok"
  }
}
```

Supported `model_key` values for the first implementation:

```text
proteinmpnn
```

Future values:

```text
rfd3
bioemu
rosetta_relax
colabfold
alphafold2
mmseqs
diffdock
```

Supported `provider` values:

```text
runpod
http_api
```

Supported `scope` values for phase 1:

```text
global
```

Keep `user` and `project` scope fields in the schema, but do not expose them in the first UI. This avoids a migration later while keeping the first implementation small.

---

### Storage

Use SQLite under:

```text
{PIPELINE_OUTPUT_ROOT}/_workspace/model_registry.sqlite
```

Use an encryption key under:

```text
{PIPELINE_OUTPUT_ROOT}/.auth/model_registry.key
```

File permissions:

```text
model_registry.sqlite: 600 or inherited service-user private directory
model_registry.key: 600
```

Secrets must never be returned to the frontend after creation/update. Return only:

```json
{
  "has_secret": true,
  "secret_preview": "********"
}
```

---

## Task 1: Add Explicit Crypto Dependency

**Files:**
- Modify: `pipeline-mcp/requirements.txt`
- Modify: `public_release/pipeline-mcp/requirements.txt`

**Step 1: Update dependency file**

Add:

```text
cryptography>=42.0.0
```

**Step 2: Verify install still works**

Run:

```bash
cd /opt/protein_pipeline-work/pipeline-mcp
uv run pytest tests/test_proteinmpnn_gpu_http.py
```

Expected: pass.

**Step 3: Commit**

```bash
git add pipeline-mcp/requirements.txt public_release/pipeline-mcp/requirements.txt
git commit -m "Add explicit cryptography dependency"
```

---

## Task 2: Implement Model Registry Store

**Files:**
- Create: `pipeline-mcp/src/pipeline_mcp/model_registry.py`
- Test: `pipeline-mcp/tests/test_model_registry.py`
- Mirror after pass: `public_release/pipeline-mcp/src/pipeline_mcp/model_registry.py`
- Mirror after pass: `public_release/pipeline-mcp/tests/test_model_registry.py`

**Step 1: Write failing tests**

Test cases:

```python
def test_create_and_list_global_http_profile(tmp_path):
    store = ModelRegistryStore(tmp_path / "registry.sqlite", tmp_path / "key")
    created = store.create_profile(
        model_key="proteinmpnn",
        display_name="GPU ProteinMPNN",
        provider="http_api",
        scope="global",
        endpoint_url="http://211.188.35.221:18101",
        secret="token-123",
        timeout_s=21600,
        enabled=True,
    )
    rows = store.list_profiles(model_key="proteinmpnn")
    assert rows[0]["id"] == created["id"]
    assert rows[0]["has_secret"] is True
    assert "token-123" not in str(rows[0])
```

```python
def test_set_default_keeps_only_one_default_per_model_key(tmp_path):
    store = ModelRegistryStore(tmp_path / "registry.sqlite", tmp_path / "key")
    first = store.create_profile(...)
    second = store.create_profile(...)
    store.set_default(second["id"])
    rows = store.list_profiles(model_key="proteinmpnn")
    assert [row["id"] for row in rows if row["is_default"]] == [second["id"]]
```

```python
def test_decrypt_secret_only_inside_store_api(tmp_path):
    store = ModelRegistryStore(tmp_path / "registry.sqlite", tmp_path / "key")
    profile = store.create_profile(..., secret="token-123")
    raw = sqlite3.connect(tmp_path / "registry.sqlite").execute(
        "select encrypted_secret from model_profiles where id = ?",
        (profile["id"],),
    ).fetchone()[0]
    assert "token-123" not in raw
    assert store.get_secret(profile["id"]) == "token-123"
```

**Step 2: Run tests and verify failure**

Run:

```bash
cd /opt/protein_pipeline-work/pipeline-mcp
env PYTHONPATH=src uv run pytest tests/test_model_registry.py -v
```

Expected: fail because `pipeline_mcp.model_registry` does not exist.

**Step 3: Implement store**

Implement:

```python
class ModelRegistryStore:
    def __init__(self, db_path: Path, key_path: Path): ...
    def create_profile(...): ...
    def update_profile(...): ...
    def list_profiles(...): ...
    def get_profile(profile_id: str): ...
    def get_secret(profile_id: str): ...
    def set_default(profile_id: str): ...
    def delete_profile(profile_id: str): ...
    def resolve_default(model_key: str): ...
```

Use `cryptography.fernet.Fernet` for `encrypted_secret`.

**Step 4: Run tests**

Run:

```bash
env PYTHONPATH=src uv run pytest tests/test_model_registry.py -v
```

Expected: pass.

**Step 5: Mirror to public_release**

Copy tested source and tests into:

```text
public_release/pipeline-mcp/src/pipeline_mcp/model_registry.py
public_release/pipeline-mcp/tests/test_model_registry.py
```

**Step 6: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/model_registry.py pipeline-mcp/tests/test_model_registry.py public_release/pipeline-mcp/src/pipeline_mcp/model_registry.py public_release/pipeline-mcp/tests/test_model_registry.py
git commit -m "Add model registry store"
```

---

## Task 3: Add Model Router for ProteinMPNN

**Files:**
- Create: `pipeline-mcp/src/pipeline_mcp/model_router.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/app.py`
- Test: `pipeline-mcp/tests/test_model_router.py`
- Mirror after pass: `public_release/pipeline-mcp/src/pipeline_mcp/model_router.py`
- Mirror after pass: `public_release/pipeline-mcp/src/pipeline_mcp/app.py`
- Mirror after pass: `public_release/pipeline-mcp/tests/test_model_router.py`

**Step 1: Write failing tests**

Test registry default beats `.env` fallback:

```python
def test_registry_default_builds_http_proteinmpnn_client(tmp_path):
    store = ModelRegistryStore(tmp_path / "registry.sqlite", tmp_path / "key")
    store.create_profile(
        model_key="proteinmpnn",
        display_name="GPU ProteinMPNN",
        provider="http_api",
        scope="global",
        endpoint_url="http://gpu:18101",
        secret="token",
        timeout_s=21600,
        enabled=True,
        is_default=True,
    )
    router = ModelRouter(store=store, runpod_client=fake_runpod)
    client = router.proteinmpnn_client(env_fallback=...)
    assert client.gpu_url == "http://gpu:18101"
    assert client.gpu_token == "token"
```

Test fallback works if registry empty:

```python
def test_empty_registry_uses_env_fallback_proteinmpnn_client(tmp_path):
    store = ModelRegistryStore(tmp_path / "registry.sqlite", tmp_path / "key")
    router = ModelRouter(store=store, runpod_client=fake_runpod)
    client = router.proteinmpnn_client(env_fallback=RunPodFallback(endpoint_id="ep"))
    assert client.endpoint_id == "ep"
```

**Step 2: Run tests and verify failure**

Run:

```bash
env PYTHONPATH=src uv run pytest tests/test_model_router.py -v
```

Expected: fail because router does not exist.

**Step 3: Implement router**

Implement:

```python
class ModelRouter:
    def proteinmpnn_client(self, *, env_fallback: ProteinMPNNFallback) -> ProteinMPNNClient:
        profile = self.store.resolve_default("proteinmpnn")
        if profile is None:
            return env_fallback.to_client()
        if profile["provider"] == "http_api":
            return ProteinMPNNClient(
                runpod=None,
                endpoint_id=None,
                gpu_url=profile["endpoint_url"],
                gpu_token=self.store.get_secret(profile["id"]),
                gpu_timeout_s=float(profile["timeout_s"] or 21600),
            )
        if profile["provider"] == "runpod":
            return ProteinMPNNClient(
                runpod=self.runpod,
                endpoint_id=profile["runpod_endpoint_id"],
            )
        raise RuntimeError(...)
```

**Step 4: Wire into `build_runner()`**

In `pipeline-mcp/src/pipeline_mcp/app.py`, replace direct ProteinMPNN construction with:

```python
registry = load_model_registry(output_root=cfg.output_root)
router = ModelRouter(store=registry, runpod_client=runpod)
proteinmpnn = router.proteinmpnn_client(env_fallback=ProteinMPNNFallback.from_config(cfg, runpod))
```

**Step 5: Run tests**

Run:

```bash
env PYTHONPATH=src uv run pytest tests/test_model_router.py tests/test_proteinmpnn_gpu_http.py -v
```

Expected: pass.

**Step 6: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/model_router.py pipeline-mcp/src/pipeline_mcp/app.py pipeline-mcp/tests/test_model_router.py public_release/pipeline-mcp/src/pipeline_mcp/model_router.py public_release/pipeline-mcp/src/pipeline_mcp/app.py public_release/pipeline-mcp/tests/test_model_router.py
git commit -m "Route ProteinMPNN through model registry"
```

---

## Task 4: Add Admin Tool APIs

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/http_server.py`
- Test: `pipeline-mcp/tests/test_model_registry_tools.py`
- Mirror after pass: same files under `public_release/pipeline-mcp/`

**Step 1: Add admin-only tool names**

In `http_server.py`, add:

```python
_ADMIN_ONLY_TOOLS = {
    ...
    "pipeline.model_registry_list",
    "pipeline.model_registry_create",
    "pipeline.model_registry_update",
    "pipeline.model_registry_delete",
    "pipeline.model_registry_set_default",
    "pipeline.model_registry_health",
}
```

**Step 2: Add tool handlers**

In `tools.py`, add handlers:

```text
pipeline.model_registry_list
pipeline.model_registry_create
pipeline.model_registry_update
pipeline.model_registry_delete
pipeline.model_registry_set_default
pipeline.model_registry_health
```

For phase 1, health behavior:

```text
http_api: GET {url}/healthz
runpod: RunPodClient.health(endpoint_id)
```

Never return decrypted secrets.

**Step 3: Write tests**

Test that:

```text
create stores profile and redacts secret
list returns profile
set_default switches default
health calls the correct provider
non-admin request is rejected by http_server admin-only list
```

**Step 4: Run tests**

Run:

```bash
env PYTHONPATH=src uv run pytest tests/test_model_registry_tools.py tests/test_oidc_auth.py -v
```

Expected: pass.

**Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/src/pipeline_mcp/http_server.py pipeline-mcp/tests/test_model_registry_tools.py public_release/pipeline-mcp/src/pipeline_mcp/tools.py public_release/pipeline-mcp/src/pipeline_mcp/http_server.py public_release/pipeline-mcp/tests/test_model_registry_tools.py
git commit -m "Add model registry admin tools"
```

---

## Task 5: Add Model Registry Admin UI

**Files:**
- Create: `frontend/model-registry/index.html`
- Create: `frontend/model-registry/styles.css`
- Create: `frontend/model-registry/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Mirror after pass: `public_release/frontend/...`

**Step 1: Build standalone admin page first**

Create `/model-registry/` as a standalone static page like existing `/runpod-admin/`.

The UI must support:

```text
List registered model profiles
Create model profile
Edit non-secret fields
Replace secret
Run health check
Set default
Delete disabled/unused profile
```

Do not show raw tokens after save.

**Step 2: Add admin nav link**

In `frontend/index.html`, add an admin-only button:

```html
<button id="modelRegistryBtn" class="ghost hidden" type="button">Model Registry</button>
```

In `frontend/app.js`, show it only for admin users and route to:

```javascript
window.location.href = "/model-registry/";
```

**Step 3: Frontend tests/build**

Run:

```bash
cd /opt/protein_pipeline-work/frontend
npm ci
npm run build
```

Expected: build succeeds.

**Step 4: Commit**

```bash
git add frontend/model-registry frontend/index.html frontend/app.js public_release/frontend/model-registry public_release/frontend/index.html public_release/frontend/app.js
git commit -m "Add model registry admin UI"
```

---

## Task 6: Dev Rollout

**Files:**
- Modify only environment files on server, not Git:
  - `/opt/protein_pipeline-dev/pipeline-mcp/.env`

**Step 1: Keep existing fallback**

Do not remove:

```env
PROTEINMPNN_PROVIDER=gpu_http
PROTEINMPNN_GPU_URL=http://211.188.35.221:18101
PROTEINMPNN_GPU_TIMEOUT_S=21600
```

The registry should override it only when an enabled default profile exists.

**Step 2: Deploy develop**

Run:

```bash
git push origin develop
gh run watch <run-id> --repo sblabkribb/protein_pipeline --exit-status
```

Expected: dev workflow passes.

**Step 3: Create registry default profile in dev UI**

Create:

```text
model_key: proteinmpnn
display_name: NCP GPU ProteinMPNN
provider: http_api
url: http://211.188.35.221:18101
timeout_s: 21600
default: yes
```

**Step 4: Health check**

Expected:

```json
{"ok": true}
```

**Step 5: Run a minimal dev pipeline**

Use a known small PDB and set output low:

```text
ProteinMPNN samples: 1
stop_after: design or soluprot
```

Expected:

```text
proteinmpnn_* completed
tiers/*/proteinmpnn.json exists
```

**Step 6: Commit no environment files**

Environment changes stay server-local.

---

## Task 7: Staging and Production Rollout

**Files:**
- No code changes after dev verification unless bugs are found.

**Step 1: Promote develop to staging**

Run:

```bash
cd /opt/protein_pipeline-work
git switch staging
git pull origin staging
git merge develop
git push origin staging
```

Expected: staging workflow passes.

**Step 2: Add staging registry profile**

Use the same GPU API URL only if staging is allowed to call the same worker.

**Step 3: Promote to production only after staging run succeeds**

Run:

```bash
git switch main
git pull origin main
git merge staging
git push origin main
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Expected: production deploy uses tag workflow.

---

## Task 8: Extend to Other Models

Add model keys one at a time after each GPU worker has a validated `/run` contract.

Recommended sequence:

```text
rosetta_relax
bioemu
rfd3
diffdock
mmseqs
colabfold/alphafold2
```

For each model:

1. Validate GPU worker directly with `curl`.
2. Add provider adapter tests.
3. Add router support.
4. Add registry health/sample-test support.
5. Add UI model option.
6. Run a dev pipeline that exercises only that model stage.
7. Promote through staging before production.

Do not move AF2/MMseqs until storage/cache strategy is explicitly documented.

---

## Acceptance Criteria

The implementation is complete when:

```text
Admin can register a ProteinMPNN HTTP API profile.
Admin can set that profile as default.
Secrets are encrypted at rest and never returned to frontend.
pipeline-mcp uses registry default before .env fallback.
Existing .env-only deployments still work unchanged.
Dev pipeline can run ProteinMPNN through GPU API.
Staging can repeat the same run.
Production remains unchanged until tagged release.
```

