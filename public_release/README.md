# RAPID Public Release

RAPID is a reproducible AI pipeline for integrated protein redesign. It records
each run through a stable artifact contract so users can rerun failed stages,
replace model backends, audit benchmark results, and connect computational
candidate generation to later experimental feedback.

This folder is the public-release package for RAPID. It contains the portable
backend, browser UI, benchmark scripts, compact benchmark data, manuscript
figures/tables, and setup documentation needed to run RAPID on a local machine,
lab server, or GPU-backed remote server.

It does not include private `.env` files, API keys, runtime logs, temporary test
output, `node_modules`, Python virtual environments, full output archives, or
private hosted-service configuration.

## Contents

- `pipeline-mcp/` - HTTP/MCP backend used by the pipeline UI and MCP clients.
- `frontend/` - Vite/Tailwind browser UI for the local/server
  solubility-aware workflow. Build it before serving from a reverse proxy.
- `scripts/benchmark/` - scripts used to prepare the CATH benchmark, train/test
  surrogate models, and regenerate paper tables/figures.
- `data/benchmark/` - processed benchmark dataset, ESM embeddings, and benchmark
  result tables used for the manuscript.
- `data/case_studies/` - compact 3RGK and 1LVM direct/evolution run summaries
  plus best-design PDBs for the representative multi-round traces.
- `data/benchmark/results/rapid_target_manifest.csv` - corrected-chain CATH
  refresh manifest with 40 re-screening targets and 8 structural-context
  ablation targets.
- `data/cath_curated/` - QC-filtered pre-refresh CATH benchmark table and
  inclusion/exclusion reports retained for component-level analysis.
- `data/cath_73/` - raw lightweight summary tables for the expanded 73-run CATH
  execution corpus before paper-level QC.
- `figures/benchmark/` - manuscript figures and LaTeX tables.
- `manuscript/` - markdown and Word versions of the current manuscript draft.
- `docs/` - setup, reproduction, data, and release notes.

## Public Package vs Hosted Service

This package is intended for self-hosted use. External users should clone the
repository, copy `pipeline-mcp/.env.example` to `.env`, provide their own
RunPod/S3/auth settings, and run RAPID on their own local or server
environment.

Development and staging URLs are not part of the public interface. If you run
hosted environments, use the following boundary:

- `dev`: private maintainer environment only; protect with VPN, IP allowlist,
  or reverse-proxy authentication.
- `staging`: private reviewer/tester environment only; do not publish it in a
  manuscript, README, or release notes.
- `production`: public only after authentication, job quotas, RunPod cost
  controls, and abuse monitoring are configured.

See `docs/deployment_security.md` for the recommended access-control checklist.

## Quick Start

Start the backend:

```bash
cd pipeline-mcp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill RUNPOD_API_KEY, ProteinMPNN, MMseqs2,
# and at least one AF2/ColabFold backend.
PYTHONPATH=src python -m pipeline_mcp.http_server --host 127.0.0.1 --port 18080
```

Start the frontend in another shell:

```bash
cd frontend
npm ci
npm run dev
```

Then open `http://127.0.0.1:5173`. By default, the frontend points to
`http://127.0.0.1:18080` when served from localhost.

For a shared server, build the frontend and serve `frontend/dist` through Caddy
or another HTTPS reverse proxy. Keep the backend bound to `127.0.0.1` and expose
only the reverse-proxy route:

```bash
cd frontend
npm ci
npm run build
```

## Authentication

The public package is configured for local username/password authentication by
default. Copy `pipeline-mcp/.env.example` to `pipeline-mcp/.env`, set a strong
`PIPELINE_ADMIN_PASSWORD`, and restart the backend.

OIDC/SSO is optional. To use it, set `PIPELINE_OIDC_ISSUER`,
`PIPELINE_OIDC_CLIENT_ID`, and related OIDC fields in `.env`. If those values
are empty, the backend uses local auth only.

## RunPod / Remote Server Use

Run the backend on the GPU/server side, keep RunPod credentials in
`pipeline-mcp/.env`, build the frontend, and either:

- use SSH port forwarding from your local browser:

```bash
ssh -L 18080:127.0.0.1:18080 user@your-server
```

- or expose the frontend and backend through your own HTTPS reverse proxy.
  Serve `frontend/dist` as static files and reverse proxy `/api/*` to the
  backend on `127.0.0.1:18080`.

Do not commit a filled `.env` file.

The RunPod endpoint images used by the packaged workflow are listed in
`docs/runpod_images.md`. They include pinned images for MMseqs2, ProteinMPNN,
ColabFold/AF2, RFD3, BioEmu, and Rosetta Relax. The optional GPU ESM embedding
worker used by surrogate triage is provided under `workers/esm_embedding/`; build
and push that image for your own RunPod endpoint, then set
`ESM_EMBEDDING_ENDPOINT_ID` in `pipeline-mcp/.env`. A self-hosted HTTP embedding
service can be used instead by setting `ESM_EMBEDDING_URL`.

## Reproducing Paper Tables and Figures

Install benchmark dependencies:

```bash
python -m pip install -r requirements-benchmark.txt
```

Regenerate the paper tables/figures from the included cached benchmark outputs:

```bash
bash scripts/reproduce_paper_tables_figures.sh
```

Full benchmark reruns are documented in `docs/reproduce_paper.md`. They can take
substantially longer because ESM embedding generation and model comparisons are
recomputed. For large surrogate-triage pools, configure the ESM embedding worker
before rerunning the live scripts; otherwise RAPID falls back to local ESM
embedding, which is slower and depends on the backend machine.
The manuscript surrogate-triage launcher defaults to pooled conservation-tier
triage: 3,333 ProteinMPNN candidates per 30%, 50%, and 70% tier, followed by one
shared 30-label bootstrap and 20-candidate Top-K AF2 budget.

The optional structural-context ablation is run through the live pipeline, not
from cached model tables. `scripts/benchmark/13_run_backbone_ensemble_ablation.py`
now defines matched single-backbone, BioEmu, RFD3-single, and RFD3+BioEmu arms;
`rfd3_ensemble3` remains available as a supplementary arm. Use
`scripts/benchmark/15_select_rapid_targets.py` to regenerate the corrected-chain
target manifest, and `scripts/benchmark/launch_backbone_ensemble_ablation.py`
to start the ablation as a managed background job on a configured server.

Representative multi-round execution summaries used by the manuscript are under
`data/case_studies/`. These are compact exports from completed production runs,
not full `outputs/` directories.

The expanded CATH archive contains 73 completed pre-refresh run directories, but
not all are valid design outputs for manuscript analysis. QC excludes fallback
or input-incompatible runs and retains 23 targets with 2,737 valid paired
SoluProt/pLDDT records for component-level active-learning analysis. The final
RAPID submission should replace population-level CATH statements with the
corrected-chain refresh generated from `rapid_target_manifest.csv`. The full
run-output archive is several gigabytes and should be deposited as a large
release artifact or S3-backed dataset rather than committed to this source
package.

The completed CATH artifacts can also be reused for pooled surrogate-scaling
checks with `scripts/benchmark/17_run_pooled_surrogate_scaling.py`. The cached
ESM-plus-composition result included here is intentionally conservative: it did
not show a stable pooled-model improvement over target-specific calibration, so
pooled surrogate accumulation is documented as future modelling infrastructure
rather than as a main performance claim.

## CI/CD Boundary

The public package is source-controlled with the main RAPID repository. The
deployment workflow promotes exact Git SHAs by environment: `dev`/`develop`
branches deploy to development, `staging` deploys to staging, and `v*` tags
deploy to production. This package should therefore be committed with the same
SHA as the backend/frontend code it documents.

Do not commit environment-specific `.env` files. CI/CD should inject secrets
from GitHub Environments or server-local files, not from `public_release/`.

## Data Policy

The included benchmark data and summary tables are small enough for normal
GitHub hosting. The full 73-run CATH output archive is not. For a journal
submission, also create an immutable release archive or Zenodo/OSF deposit and
cite its DOI in the manuscript. Keep large runtime outputs, model caches, and
private `.env` files outside Git.

## Before Making the Repository Public

See `docs/release_checklist.md`. At minimum, choose a license, fill the
`CITATION.cff` author fields, protect non-production hosted URLs, verify the
secret scan, and tag a release.
