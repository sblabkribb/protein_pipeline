# Home, Rounds, and Product Shell Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current tab-first console with a sidebar-based shell, add a Home launcher, split Setup into Fast and Advanced flows, and introduce persisted Project/Round metadata that can organize runs without changing the underlying scientific pipeline behavior.

**Architecture:** Keep the current frontend state and pipeline request model as the execution backbone, but add a new application shell and round context layer above them. Persist project/round metadata in backend-managed JSON records and pass `project_id` / `round_id` through run requests so Monitor, Analyze, and future ML features can anchor to the same hierarchy.

**Tech Stack:** Vanilla JS frontend, static HTML/CSS shell, existing frontend state in `frontend/app.js`, helper logic in `frontend/lib/pipeline.js`, Python MCP backend in `pipeline-mcp/src/pipeline_mcp`, JSON persistence under the pipeline output root, Node test runner, Pytest.

---

### Task 1: Add shell-level navigation primitives

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add assertions that the shell includes:

- a `Home` entry
- a sidebar navigation container
- distinct `Fast` and `Advanced` navigation entries

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL because the new shell/navigation strings are missing.

**Step 3: Write minimal implementation**

- replace top-tab-only shell in `frontend/index.html` with a sidebar container
- keep existing panel ids where possible to reduce JS churn
- add a new `Home` panel and split `Setup` naming into `Fast` / `Advanced`

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS for the new shell test.

**Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css frontend/tests/pipeline.test.js
git commit -m "feat: add sidebar product shell"
```

### Task 2: Introduce Home as the default landing surface

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add tests asserting:

- `Home` is the default active panel after login
- the Home view contains `Fast`, `Advanced`, and `Studio` action cards

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL because Setup is still the default.

**Step 3: Write minimal implementation**

- switch initial active tab/panel logic to `home`
- render launcher cards
- add a light context strip for active project/round/run summary placeholders

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css frontend/tests/pipeline.test.js
git commit -m "feat: add home launcher"
```

### Task 3: Split the current Setup flow into Fast and Advanced

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/lib/pipeline.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add tests for:

- `Fast` mode building a reduced request path
- `Advanced` mode preserving full setup capabilities
- correct routing labels and mode inference

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL because the new modes do not exist yet.

**Step 3: Write minimal implementation**

- map current full Setup behavior to `Advanced`
- create a reduced `Fast` form with PDB/FASTA-first inputs
- auto-derive default execution behavior from Fast inputs
- codify Fast defaults in a shared helper instead of duplicating them in the DOM layer
- make Fast defaults explicit:
  - `RFD3 off`
  - `BioEmu on`
  - `20` generated / `10` returned
  - stop after `novelty`
- preserve the existing expert validation path in Advanced
- provide both `Run Fast` and `Review in Advanced` actions from the Fast surface

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/app.js frontend/index.html frontend/lib/pipeline.js frontend/tests/pipeline.test.js
git commit -m "feat: split fast and advanced launch modes"
```

### Task 4: Preserve Studio inside the new shell without regressions

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add assertions that:

- Studio remains reachable through the new sidebar
- current workflow-studio session behaviors are still mounted
- Home can route to Studio directly

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL if shell refactor disconnects Studio.

**Step 3: Write minimal implementation**

- keep current Studio panel ids and rendering functions
- wire the Home `Studio` card to the existing Studio surface
- ensure no duplicate navigation state is created
- ensure Studio-launched runs inherit the currently selected `project_id` / `round_id` context by default
- cover rerun/fork/continue flows so they do not silently drop round linkage

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/app.js frontend/index.html frontend/styles.css frontend/tests/pipeline.test.js
git commit -m "fix: retain workflow studio in new shell"
```

### Task 5: Add backend Project and Round metadata models

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/http_server.py`
- Test: `pipeline-mcp/tests/test_tools.py`

**Step 1: Write the failing test**

Add tests for:

- creating a project payload
- creating/updating a round payload
- listing/getting owned project and round records
- validating optional `project_id` and `round_id` on pipeline requests
- validating owner metadata and admin/non-admin access rules

**Step 2: Run test to verify it fails**

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py -q`
Expected: FAIL because the metadata tools do not exist.

**Step 3: Write minimal implementation**

- add `project_id` and `round_id` to `PipelineRequest`
- define minimal tool handlers for project/round CRUD
- define explicit list/get handlers for project/round selectors
- define owner metadata fields for project/round records
- expose `project_id` / `round_id` in MCP run schemas and inject authenticated user context on the real HTTP tool-call path so owner enforcement applies outside direct in-process calls
- keep schemas simple and JSON-file-backed

**Step 4: Run test to verify it passes**

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/models.py pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/src/pipeline_mcp/http_server.py pipeline-mcp/tests/test_tools.py
git commit -m "feat: add project and round metadata tools"
```

### Task 6: Persist Project and Round records on disk

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`
- Test: `pipeline-mcp/tests/test_tools.py`
- Test: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Write the failing test**

Add tests for:

- saving project metadata under a stable workspace path
- saving round metadata with linked runs
- attaching a launched run to a round
- rejecting foreign project/round access for non-admin users

**Step 2: Run test to verify it fails**

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py tests/test_pipeline_dry_run.py -q`
Expected: FAIL because records are not written yet.

**Step 3: Write minimal implementation**

- choose a stable metadata root under the pipeline output root
- write project and round JSON files
- append launched run ids to the target round when request metadata is present
- enforce owner-based filtering and access checks in backend APIs

**Step 4: Run test to verify it passes**

Run: `env PYTHONPATH=src uv run pytest tests/test_tools.py tests/test_pipeline_dry_run.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/tools.py pipeline-mcp/src/pipeline_mcp/pipeline.py pipeline-mcp/tests/test_tools.py pipeline-mcp/tests/test_pipeline_dry_run.py
git commit -m "feat: persist rounds and link runs"
```

### Task 7: Add frontend round context state and selectors

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/lib/pipeline.js`
- Modify: `frontend/index.html`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add tests asserting:

- selected project and round are stored in frontend state
- Home context strip reads from current project/round
- Home allows project creation/selection, not only round selection
- Fast and Advanced requests include round metadata when selected
- frontend only renders owned project/round records for non-admin users

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL because no round context exists.

**Step 3: Write minimal implementation**

- add project/round selectors to Home
- add a lightweight project create action on Home
- store current project/round in state
- include `project_id` and `round_id` in outgoing run payloads
- treat frontend filtering as presentation only; rely on backend-scoped results

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/app.js frontend/lib/pipeline.js frontend/index.html frontend/tests/pipeline.test.js
git commit -m "feat: add round context to launch flows"
```

### Task 8: Build the Rounds workspace UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add tests asserting that:

- a `Rounds` navigation entry exists
- the page contains round list/detail regions
- project and round actions exist for create/update/select
- admin can view all records while non-admin sees only owned records

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL because the workspace does not exist.

**Step 3: Write minimal implementation**

- build a two-column Rounds workspace
- load project/round metadata from new backend APIs
- expose a lightweight project switcher/create entry within the workspace
- show linked runs and summary notes in round detail

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css frontend/tests/pipeline.test.js
git commit -m "feat: add rounds workspace"
```

### Task 9: Make Monitor and Analyze round-aware

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/lib/pipeline.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add tests for:

- filtering displayed runs by selected round when round context is active
- quick actions from Home to Monitor/Analyze preserving round context

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL because these views are run-only today.

**Step 3: Write minimal implementation**

- scope run listings and summaries by selected round when available
- show unattached legacy runs only inside an explicit admin-visible legacy bucket
- keep normal non-admin views scoped to attached owned runs only

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/app.js frontend/lib/pipeline.js frontend/tests/pipeline.test.js
git commit -m "feat: make monitor and analyze round aware"
```

### Task 10: Apply the new visual system

**Files:**
- Modify: `frontend/styles.css`
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Test: manual browser verification

**Step 1: Write a visual checklist**

Create a checklist for:

- sidebar spacing and hierarchy
- home hero and action cards
- typography scale
- motion restraint
- responsive layout

**Step 2: Run existing static verification**

Run: `node --check frontend/app.js`
Expected: PASS before style-only work continues.

**Step 3: Write minimal implementation**

- add font loading strategy
- redefine shell spacing, card treatment, and navigation styling
- introduce subtle page transitions and hover depth
- keep Monitor/Analyze data density readable

**Step 4: Run verification**

Run: `node --check frontend/app.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/styles.css frontend/index.html frontend/app.js
git commit -m "feat: apply editorial lab visual redesign"
```

### Task 11: Final regression sweep

**Files:**
- Modify if needed after failures: `frontend/app.js`
- Modify if needed after failures: `frontend/lib/pipeline.js`
- Modify if needed after failures: `pipeline-mcp/src/pipeline_mcp/*.py`
- Test: `frontend/tests/pipeline.test.js`
- Test: `pipeline-mcp/tests/test_tools.py`
- Test: `pipeline-mcp/tests/test_pipeline_dry_run.py`

**Step 1: Run frontend verification**

Run: `node --check frontend/app.js && node frontend/tests/pipeline.test.js`
Expected: PASS.

**Step 2: Run backend verification**

Run: `cd pipeline-mcp && env PYTHONPATH=src uv run pytest tests/test_tools.py tests/test_pipeline_dry_run.py -q`
Expected: PASS.

**Step 3: Manual smoke test**

Check:

- Home loads by default
- Fast launches a run
- Advanced preserves full controls
- Studio still opens and runs stages
- Rounds can be created and linked

**Step 4: Commit final fixes**

```bash
git add frontend pipeline-mcp
git commit -m "fix: complete home rounds shell rollout"
```
