# RAPID Public Release

This folder is a compact public-release package for RAPID, a reproducible
artifact pipeline for solubility-aware protein redesign, active-learning
evolution, benchmark scripts, benchmark data, figures, and manuscript draft
artifacts.

The package is organized to be runnable from a local machine, a lab server, or a
GPU server such as RunPod. It does not include private `.env` files, API keys,
runtime logs, temporary test output, `node_modules`, or Python virtual
environments.

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

## Quick Start

Start the backend:

```bash
cd pipeline-mcp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill RUNPOD_API_KEY, MMSEQS_ENDPOINT_ID, PROTEINMPNN_ENDPOINT_ID,
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
or another HTTPS reverse proxy:

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
ColabFold/AF2, RFD3, BioEmu, and Rosetta Relax.

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
recomputed.

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

## Data Policy

The included benchmark data and summary tables are small enough for normal
GitHub hosting. The full 73-run CATH output archive is not. For a journal
submission, also create an immutable release archive or Zenodo/OSF deposit and
cite its DOI in the manuscript. Keep large runtime outputs, model caches, and
private `.env` files outside Git.

## Before Making the Repository Public

See `docs/release_checklist.md`. At minimum, choose a license, fill the
`CITATION.cff` author fields, verify the `.env` scan, and tag a release.
