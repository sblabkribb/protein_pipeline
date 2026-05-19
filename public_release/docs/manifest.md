# RAPID Release Manifest

## Included

- Backend/MCP service: `pipeline-mcp/src/pipeline_mcp/`
- Backend tests: `pipeline-mcp/tests/`
- Backend model artifacts: `pipeline-mcp/models/global_plddt_v1.pkl`,
  `pipeline-mcp/models/global_soluprot_v1.pkl`
- Vite/Tailwind frontend source: `frontend/`
- Benchmark scripts and release helper scripts: `scripts/benchmark/`,
  `scripts/02_run_cath_batch.py`, `scripts/train_cath_surrogate.py`,
  `scripts/run_managed_job.py`
- Benchmark data, cached results, and RAPID refresh manifest:
  `data/benchmark/`
- Representative direct/evolution case-study summaries: `data/case_studies/`
- QC-filtered pre-refresh CATH benchmark summaries: `data/cath_curated/`
- Raw expanded 73-run CATH archive summaries: `data/cath_73/`
- Figures and tables: `figures/benchmark/`
- Manuscript draft: `manuscript/`
- Public setup/reproduction docs: `docs/`

## Excluded

- private `.env` files
- Python virtual environments
- frontend `node_modules`
- frontend test harness from the private development repo
- frontend build output (`frontend/dist/`)
- runtime `outputs/` and `logs/`
- full CATH run-output archive (`cath_outputs/`)
- `pipeline-mcp/tests/_tmp/`
- Python bytecode and pytest cache directories
- local expert-memory models generated during future evolution runs

## Notes

Local expert-memory models are generated under `pipeline-mcp/models/experts/`
when memory-bank evolution is used. The directory is ignored because it is a
runtime artifact, not a required release input.
