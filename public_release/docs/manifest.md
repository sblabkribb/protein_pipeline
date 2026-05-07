# Release Manifest

## Included

- Backend/MCP service: `pipeline-mcp/src/pipeline_mcp/`
- Backend tests: `pipeline-mcp/tests/`
- Backend model artifacts: `pipeline-mcp/models/global_plddt_v1.pkl`,
  `pipeline-mcp/models/global_soluprot_v1.pkl`
- Static frontend: `frontend/`
- Benchmark scripts: `scripts/benchmark/`
- Benchmark data and cached results: `data/benchmark/`
- Representative direct/evolution case-study summaries: `data/case_studies/`
- QC-filtered CATH benchmark summaries: `data/cath_curated/`
- Raw expanded 73-run CATH archive summaries: `data/cath_73/`
- Figures and tables: `figures/benchmark/`
- Manuscript draft: `manuscript/`
- Public setup/reproduction docs: `docs/`

## Excluded

- private `.env` files
- Python virtual environments
- frontend `node_modules`
- runtime `outputs/` and `logs/`
- full CATH run-output archive (`cath_outputs/`)
- `pipeline-mcp/tests/_tmp/`
- Python bytecode and pytest cache directories
- local expert-memory models generated during future evolution runs

## Notes

Local expert-memory models are generated under `pipeline-mcp/models/experts/`
when memory-bank evolution is used. The directory is ignored because it is a
runtime artifact, not a required release input.
