# protein_pipeline

MCP-enabled protein design pipeline with optional RFD3 (RFDiffusion3), BioEmu, and DiffDock stages.

## What it does
- Optional backbone generation with RFD3 and/or BioEmu
- MSA + conservation
- Optional DiffDock for ligand placement (mask only)
- ProteinMPNN design (tiers)
- Optional SoluProt / AlphaFold2 / novelty search

## RunPod endpoint env vars
- Required: `RUNPOD_API_KEY`, `MMSEQS_ENDPOINT_ID`, `PROTEINMPNN_ENDPOINT_ID`
- Optional: `RFD3_ENDPOINT_ID`, `BIOEMU_ENDPOINT_ID`, `DIFFDOCK_ENDPOINT_ID`, `ALPHAFOLD2_ENDPOINT_ID`

## MCP tools
- `pipeline.plan_from_prompt`: Parse a natural-language prompt and return missing inputs/questions (no execution)
- `pipeline.run_from_prompt`: Parse a prompt and run immediately (requires target_pdb/target_fasta)
- `pipeline.run`: Run with explicit parameters
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

## Docs
- Usage guide + screenshots: `docs/USAGE.md`
- MCP skill: `skills/protein-pipeline-stepper/SKILL.md`

## Repo structure
- `pipeline-mcp/`: MCP server implementation
- `docs/`: usage and screenshots
- `skills/`: Codex skill files for guided execution
