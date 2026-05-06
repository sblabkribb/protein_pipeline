# Tag-Based Dev/Prod Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Recreate `/opt/protein_pipeline-dev` from a clean release baseline and add GitHub Actions deployment that keeps dev and production separated.

**Architecture:** Production remains `/opt/protein_pipeline` on `127.0.0.1:18080` and deploys only from release tags or explicit production dispatch. Development runs from `/opt/protein_pipeline-dev` on `127.0.0.1:18083`, with its own env file, venv, outputs, logs, sessions, OIDC client, and visible UI badge.

**Tech Stack:** GitHub Actions, SSH, systemd, Caddy, Python venv, static frontend.

---

### Task 1: Make the UI identify development clearly

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `frontend/tests/app-syntax.test.js`

**Steps:**
1. Add a hidden environment badge to the top bar.
2. Detect `dev-pipeline.*` hostnames in `app.js`.
3. Show the badge only for the dev host and set `body[data-environment="development"]`.
4. Add a source-level frontend test for the badge and hostname detection.
5. Run `cd frontend && npm test`.

### Task 2: Add repeatable server deployment

**Files:**
- Create: `.github/workflows/deploy.yml`
- Create: `scripts/deploy/deploy_from_github.sh`

**Steps:**
1. Run tests in CI.
2. Deploy `dev`/`develop` pushes to `/opt/protein_pipeline-dev`.
3. Deploy `v*` tags or manual prod dispatch to `/opt/protein_pipeline`.
4. Refuse deployment over tracked local modifications.
5. Restart the correct systemd service and verify `/healthz`.

### Task 3: Recreate the dev runtime

**Files:**
- Modify: `/opt/kbf-infra/systemd-overrides/pipeline-mcp-dev.service`
- Create: `/etc/systemd/system/pipeline-mcp-dev.service`
- Recreate: `/opt/protein_pipeline-dev`

**Steps:**
1. Stop the dev service if present.
2. Remove `/opt/protein_pipeline-dev`.
3. Clone the repo into `/opt/protein_pipeline-dev` and check out `v0.2.5`.
4. Create dev-only runtime directories and `.env`.
5. Create a dev venv and install `pipeline-mcp/requirements.txt`.
6. Install and start `pipeline-mcp-dev.service`.
7. Verify `http://127.0.0.1:18083/healthz`.
