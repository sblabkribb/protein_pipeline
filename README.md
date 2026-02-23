# protein_pipeline

MCP-enabled protein design pipeline with optional RFD3 (RFDiffusion3) and DiffDock stages.

## What it does
- Optional backbone generation with RFD3
- MSA + conservation
- Optional DiffDock for ligand placement (mask only)
- ProteinMPNN design (tiers)
- Optional SoluProt / AlphaFold2 / novelty search

## MCP tools
- `pipeline.plan_from_prompt`: Parse a natural-language prompt and return missing inputs/questions (no execution)
- `pipeline.run_from_prompt`: Parse a prompt and run immediately (requires target_pdb/target_fasta)
- `pipeline.run`: Run with explicit parameters
- `pipeline.af2_predict`: Run AlphaFold2 on FASTA/sequence (standalone)
- `pipeline.diffdock`: Run DiffDock on protein PDB + ligand (standalone)
- `pipeline.submit_feedback`: Store a good/bad rating with metadata
- `pipeline.list_feedback`: List feedback entries
- `pipeline.submit_experiment`: Store experimental results
- `pipeline.list_experiments`: List experimental results
- `pipeline.generate_report`: Build a markdown report from stored data
- `pipeline.save_report`: Save a report revision
- `pipeline.get_report`: Fetch latest report
- `pipeline.status`: Get run status
- `pipeline.list_artifacts`: List run artifacts
- `pipeline.read_artifact`: Read an artifact safely

## Recommended flow
1) Call `pipeline.plan_from_prompt`
2) Ask the returned questions (if any)
3) Call `pipeline.run` with the completed inputs

## Artifacts
Outputs are written under `PIPELINE_OUTPUT_ROOT/<run_id>/` on the execution host.
Use `pipeline.list_artifacts` / `pipeline.read_artifact` to fetch results remotely.

## Deploy (NCP summary)
1) Build image: `docker build -t pipeline-mcp:cpu ./pipeline-mcp`
2) Push image: `docker tag` + `docker push`
3) Restart the NCP service/container
4) Verify: `POST /tools/list` includes `pipeline.plan_from_prompt`

## UI (frontend)
- Static UI under `frontend/` (no build). Run locally:
  - `cd frontend`
  - `python3 -m http.server 5173`
  - Open `http://127.0.0.1:5173`

## Auth + CORS (optional)
- Enable auth: `PIPELINE_AUTH_ENABLED=1`
- Admin bootstrap: `PIPELINE_ADMIN_USERNAME` + `PIPELINE_ADMIN_PASSWORD`
- User store (default): `${PIPELINE_OUTPUT_ROOT}/.auth/users.json`
- Token TTL: `PIPELINE_AUTH_TOKEN_TTL_S` (default 86400s)
- CORS: `PIPELINE_CORS_ORIGINS` (comma-separated, `*` default)
- MCP proxy auth: `PIPELINE_AUTH_TOKEN` or `PIPELINE_AUTH_USERNAME` + `PIPELINE_AUTH_PASSWORD`

## Report scoring (optional)
- `PIPELINE_REPORT_BASE_SCORE` (default 50)
- `PIPELINE_REPORT_FEEDBACK_WEIGHT` (default 20)
- `PIPELINE_REPORT_EXPERIMENT_WEIGHT` (default 30)
- `PIPELINE_REPORT_MIN_SCORE` / `PIPELINE_REPORT_MAX_SCORE` (default 0 / 100)
- `PIPELINE_REPORT_EVIDENCE_MEDIUM_FEEDBACK` (default 2)
- `PIPELINE_REPORT_EVIDENCE_HIGH_FEEDBACK` (default 6)
- `PIPELINE_REPORT_EVIDENCE_MEDIUM_EXPERIMENT` (default 1)
- `PIPELINE_REPORT_EVIDENCE_HIGH_EXPERIMENT` (default 3)
- `PIPELINE_REPORT_PROMOTE_SCORE` (default 75)
- `PIPELINE_REPORT_PROMISING_SCORE` (default 60)
- `PIPELINE_REPORT_REVIEW_SCORE` (default 40)
- `PIPELINE_REPORT_PROMOTE_REQUIRE_EVIDENCE` (default true)
- Custom scorer (hot-swap):
  - `PIPELINE_REPORT_SCORER` = Python module path or `/abs/path/to/scorer.py`
  - `PIPELINE_REPORT_SCORER_FN` = function name (default `score_report`)

## Nginx (Docker) for UI
See `deploy/nginx/README.md` for running a static UI on 5173/443 with `/api` proxy.

## Docs
- Usage guide + screenshots: `docs/USAGE.md`
- MCP skill: `skills/protein-pipeline-stepper/SKILL.md`

## Repo structure
- `pipeline-mcp/`: MCP server implementation
- `docs/`: usage and screenshots
- `skills/`: Codex skill files for guided execution
