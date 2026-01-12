---
name: protein-pipeline-stepper
description: Stepwise execution of the protein-pipeline via MCP (pipeline.run/pipeline.status) with safe polling, run_id reuse, stop_after staging, and duplicate-job avoidance. Use when you need staged MMseqs2/ProteinMPNN/SoluProt/AF2 runs and want output paths (not narrative summaries).
---

# Protein Pipeline Stepper

## Overview

Run the protein pipeline in deterministic stages via MCP tools and return the output paths required for the next step.

## Prerequisites

- Use the MCP server named `protein-pipeline` (it must expose `pipeline.run`, `pipeline.status`, `pipeline.list_runs`).
- Treat `pipeline.run` as potentially long-running; prefer staged execution with `stop_after`.

## Non-Negotiable Rules

- Always reuse a stable `run_id` across stages. If the user does not supply one, create one with only `[a-zA-Z0-9_.-]` and no spaces.
- Never pass file paths as `target_fasta` / `target_pdb`. Read the file contents and pass the raw text.
- Before calling `pipeline.run` for a `run_id`, call `pipeline.status(run_id)`:
  - If `state=running`, do not call `pipeline.run` again. Poll `pipeline.status` until completion/failure.
  - If `state=failed` (or similar), stop and report the error details.
- If a `pipeline.run` call times out in the client, assume the remote job may still be running; switch to polling with `pipeline.status`.

## Workflow (Stage Runner)

1) Collect inputs
- Require: one of `target_fasta` or `target_pdb` (raw text, not a file path).
  - If only `target_pdb` is provided, the pipeline extracts the sequence from `ATOM` records for `MMseqs2`/conservation.
  - If `target_pdb` is missing and `stop_after!="msa"`, the pipeline will first run AlphaFold2 to generate a target structure (`target.pdb`) (requires `ALPHAFOLD2_ENDPOINT_ID` or `AF2_URL` configured).
- Choose: `run_id` (reuse across steps).
- Choose: next stage via `stop_after` (`msa` -> `design` -> `soluprot` -> `af2` -> `novelty`).

2) Gate on current status
- Call `pipeline.status` for the `run_id`.
- If `found=false`: start the requested stage with `pipeline.run`.
- If `found=true` and `state=running`: poll with `pipeline.status` (e.g., every 30-60s).
- If `found=true` and not running: proceed to the requested stage with `pipeline.run` (it will reuse cached artifacts unless `force=true`).
- If `state=running` looks stale (e.g., long time since `updated_at` and you know nothing is running), you may proceed with `pipeline.run` to resume, or use a new `run_id`.

3) Execute one stage at a time
- Call `pipeline.run` with `stop_after` set to the stage you want to complete.
- After completion, return:
  - `output_dir`
  - stage-specific file paths from the result (e.g., `msa_a3m_path`, `msa_tsv_path`)
  - the next recommended stage (if the user asked to continue)

## Stage Templates (Arguments)

Use these argument shapes when calling `pipeline.run`:

### MSA (`stop_after="msa"`)
- Required: `run_id` and one of `target_fasta` / `target_pdb`
- Recommended:
  - `mmseqs_target_db="uniref90"`
  - `mmseqs_max_seqs=3000`

### Design (`stop_after="design"`)
- Required: `run_id` and either:
  - `target_pdb` (recommended), or
  - `target_fasta` (pipeline will generate `target.pdb` via AF2 first; AF2 must be configured)
- Recommended:
  - `conservation_tiers=[0.3, 0.5, 0.7]`
  - `num_seq_per_tier=16`
  - Optionally: `design_chains`, `seed`, `sampling_temp`, `batch_size`

### SoluProt (`stop_after="soluprot"`)
- Required: `run_id` and either `target_pdb` or (`target_fasta` + AF2 configured)
- Recommended: `soluprot_cutoff=0.5`

### AlphaFold2 (`stop_after="af2"`)
- Required: `run_id` and either `target_pdb` or (`target_fasta` + AF2 configured)
- Recommended:
  - `af2_plddt_cutoff=85`
  - `af2_top_k=20`
  - `af2_sequence_ids=["1"]` (run AF2 only for selected design ids to save time)

## Output Expectations

- Always return `output_dir` and any stage-specific paths from the tool result.
- Point users to `PIPELINE_OUTPUT_ROOT/<run_id>/` on the execution host for artifacts (`msa/`, `tiers/`, `status.json`, `summary.json`).

## Example (Minimal)

Run MSA only:
- Call `pipeline.run` with `run_id`, `stop_after="msa"`, `mmseqs_target_db`, `mmseqs_max_seqs`, and FASTA text.
- If the call is slow, poll with `pipeline.status(run_id)` until it completes.

## Quick Start Prompts (Copy/Paste)

These are example user prompts that should trigger this skill and result in MCP tool calls.

### Full pipeline (requires target_pdb)

Request:
- "Use protein-pipeline-stepper. Run msa -> design -> soluprot -> af2 sequentially for run_id=intein_full_001. Read target_fasta from the pasted FASTA text. Read target_pdb from ./target.pdb file contents. Use defaults for all other params. If any stage is running, poll pipeline.status every 60s and do not re-run pipeline.run. After each stage, return output_dir and the paths needed for the next stage."

### MSA only (no PDB required)

Request:
- "Use protein-pipeline-stepper. Run MSA only (stop_after=msa) for run_id=intein_msa_001 using the pasted FASTA text. Use defaults. Poll status if needed. Return output_dir, msa_a3m_path, msa_tsv_path."
