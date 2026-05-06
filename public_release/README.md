# Protein Pipeline Public Release

This folder is a compact public-release package for a solubility-aware protein
redesign pipeline, active-learning evolution workflow, benchmark scripts,
benchmark data, figures, and manuscript draft artifacts.

The package is organized to be runnable from a local machine, a lab server, or a
GPU server such as RunPod. It does not include private `.env` files, API keys,
runtime logs, temporary test output, `node_modules`, or Python virtual
environments.

## Contents

- `pipeline-mcp/` - HTTP/MCP backend used by the pipeline UI and MCP clients.
- `frontend/` - static browser UI for the local/server solubility-aware workflow.
  It can be served by any static file server.
- `scripts/benchmark/` - scripts used to prepare the CATH benchmark, train/test
  surrogate models, and regenerate paper tables/figures.
- `data/benchmark/` - processed benchmark dataset, ESM embeddings, and benchmark
  result tables used for the manuscript.
- `data/case_studies/` - compact 3RGK and 1LVM direct/evolution run summaries
  plus best-design PDBs for the representative multi-round traces.
- `data/cath_curated/` - QC-filtered CATH expansion table and inclusion/exclusion
  reports for the publication-grade subset.
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
PYTHONPATH=src python -m pipeline_mcp.http_server --host 0.0.0.0 --port 18080
```

Start the frontend in another shell:

```bash
cd frontend
python3 -m http.server 5173 --bind 127.0.0.1
```

Then open `http://127.0.0.1:5173`. By default, the frontend points to
`http://127.0.0.1:18080` when served from localhost.

## Authentication

The public package is configured for local username/password authentication by
default. Copy `pipeline-mcp/.env.example` to `pipeline-mcp/.env`, set a strong
`PIPELINE_ADMIN_PASSWORD`, and restart the backend.

OIDC/SSO is optional. To use it, set `PIPELINE_OIDC_ISSUER`,
`PIPELINE_OIDC_CLIENT_ID`, and related OIDC fields in `.env`. If those values
are empty, the backend uses local auth only.

## RunPod / Remote Server Use

Run the backend on the GPU/server side, keep RunPod credentials in
`pipeline-mcp/.env`, and either:

- use SSH port forwarding from your local browser:

```bash
ssh -L 18080:127.0.0.1:18080 user@your-server
```

- or expose the backend through your own HTTPS reverse proxy and set
  `PIPELINE_CORS_ORIGINS` to the frontend origin.

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

The optional backbone/ensemble ablation is run through the live pipeline, not
from cached model tables. `scripts/benchmark/13_run_backbone_ensemble_ablation.py`
defines the matched single-backbone, RFD3-single, and RFD3-ensemble arms;
`scripts/benchmark/launch_backbone_ensemble_ablation.py` starts the pilot as a
managed background job on a configured server.

Representative multi-round execution summaries used by the manuscript are under
`data/case_studies/`. These are compact exports from completed production runs,
not full `outputs/` directories.

The expanded CATH archive contains 73 completed run directories, but not all are
valid design outputs for manuscript analysis. QC excludes fallback or
input-incompatible runs and retains 23 publication-grade targets with 2,737
valid paired SoluProt/pLDDT records. The curated summaries are included under
`data/cath_curated/`; raw 73-run summaries are under `data/cath_73/`. The full
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
