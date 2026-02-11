---
name: protein-pipeline-stepper
description: Stepwise execution of the protein-pipeline via MCP (pipeline.run/pipeline.status) with safe polling, run_id reuse, stop_after staging, and duplicate-job avoidance. Use when you need staged RFD3/MMseqs2/ProteinMPNN/SoluProt/AF2 runs and want output paths (not narrative summaries).
---

# Protein Pipeline Stepper

## Overview

Run the protein pipeline in deterministic stages via MCP tools and return the output paths required for the next step.

## Prerequisites

- Use the MCP server named `protein-pipeline` (it must expose `pipeline.run`, `pipeline.status`, `pipeline.list_runs`).
  - If available, also use `pipeline.list_artifacts` and `pipeline.read_artifact` to fetch intermediate files without asking for filesystem access.
- Treat `pipeline.run` as potentially long-running; prefer staged execution with `stop_after`.

## Non-Negotiable Rules

- Always reuse a stable `run_id` across stages. If the user does not supply one, create one with only `[a-zA-Z0-9_.-]` and no spaces.
- Never pass file paths as `target_fasta` / `target_pdb` / `rfd3_input_pdb`. Read the file contents and pass the raw text.
- Before calling `pipeline.run` for a `run_id`, call `pipeline.status(run_id)`:
  - If `state=running`, do not call `pipeline.run` again. Poll `pipeline.status` until completion/failure.
  - If `state=failed` (or similar), stop and report the error details.
- If a `pipeline.run` call times out in the client, assume the remote job may still be running; switch to polling with `pipeline.status`.

## Workflow (Stage Runner)

If the user wants interactive prompting, call `pipeline.plan_from_prompt` first and use its `questions` to ask for missing inputs before calling `pipeline.run`.

1) Collect inputs
- Require: one of `target_fasta` or `target_pdb` **or** RFD3 inputs (raw text, not a file path).
  - If only `target_pdb` is provided, the pipeline extracts the sequence from `ATOM` records for `MMseqs2`/conservation.
  - If `target_pdb` is missing and `stop_after!="msa"` and no RFD3 inputs are provided, the pipeline will first run AlphaFold2 to generate a target structure (`target.pdb`) (requires `ALPHAFOLD2_ENDPOINT_ID` or `AF2_URL` configured).
- Optional: DiffDock inputs for ligand placement (used only if ligand coordinates are missing in the PDB):
  - `diffdock_ligand_smiles` **or** `diffdock_ligand_sdf` (raw text).
- Choose: `run_id` (reuse across steps).
- Choose: next stage via `stop_after` (`rfd3` -> `msa` -> `design` -> `soluprot` -> `af2` -> `novelty`).

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

### RFD3 (`stop_after="rfd3"`)
- Required: `run_id` and RFD3 inputs, using one of:
  - `rfd3_inputs_text` (JSON/YAML string), or
  - `rfd3_inputs` (dict), or
  - simple builder: `rfd3_input_pdb` + `rfd3_contig`
- Recommended:
  - `rfd3_design_index=0`
- `rfd3_contig` format: `A1-229` (no colon). `A:1-229` is normalized but avoid using it.
- `rfd3_cli_args` for `n_batches`, etc. (if not provided, `diffusion_batch_size=<rfd3_max_return_designs> n_batches=1` is auto-injected)
  - Note: `rfd3_partial_t` defaults to 20 and is injected into inputs if missing.
  - If PDB residue numbers are non-standard: set `pdb_strip_nonpositive_resseq=true` and/or `pdb_renumber_resseq_from_1=true` **after** RFD3 for downstream steps.
- After completion:
  - Read `outputs/<run_id>/rfd3/selected.pdb` and pass its **contents** as `target_pdb` for the next stage.

### MSA (`stop_after="msa"`)
- Required: `run_id` and one of `target_fasta` / `target_pdb`
- Recommended:
  - `mmseqs_target_db="uniref90"`
  - `mmseqs_max_seqs=3000`
  - `mmseqs_use_gpu=false` (recommended default; set `true` only after you’ve validated the GPU image/output mapping on your deployment)
  - Optional (paper parity, `target_pdb` only): `pdb_strip_nonpositive_resseq=true`, `pdb_renumber_resseq_from_1=true` (writes `pdb_numbering.json`)
  - Optional (weighted conservation): `conservation_weighting="mmseqs_cluster"` (requires MMseqs endpoint to support `cluster`)
  - If RunPod Serverless CPU jobs time out with large DBs, try a smaller DB (e.g. `swissprot`), reduce `mmseqs_max_seqs`, or use a dedicated pod/volume-warmed setup.

### Design (`stop_after="design"`)
- Required: `run_id` and either:
  - `target_pdb` (recommended), or
  - `target_fasta` (pipeline will generate `target.pdb` via AF2 first; AF2 must be configured)
- Recommended:
  - `conservation_tiers=[0.3, 0.5, 0.7]`
  - `num_seq_per_tier=16`
  - Optional (PyMOL-style 6Å masking): `ligand_mask_distance=6.0`; use `ligand_resnames=[...]` (HETATM) and/or `ligand_atom_chains=[...]` (ATOM substrate chains)
  - Optionally: `design_chains`, `seed`, `sampling_temp`, `batch_size`
  - If ligand coordinates are missing and you have a ligand description, set:
    - `diffdock_ligand_smiles` **or** `diffdock_ligand_sdf`
    - DiffDock will run automatically before ligand masking and uses the rank1 pose **only for ligand mask** (ProteinMPNN/AF2 inputs remain the original PDB).

### Preset: Paper-Parity Enzyme+Substrate (PDB input)
- Use when the “ligand/substrate” is modeled as a separate `ATOM` chain (common for enzyme-substrate complexes).
- Set `design_chains` to the chain(s) you mutate; set `ligand_atom_chains` to substrate chain(s).
- Recommended knobs: `pdb_strip_nonpositive_resseq=true`, `pdb_renumber_resseq_from_1=true`, `conservation_weighting="mmseqs_cluster"`, `ligand_mask_distance=6.0`

### Choosing Knobs (Quick)
- If the substrate is a separate `ATOM` chain: set `ligand_atom_chains=[...]` and keep those chains out of `design_chains`.
- If the PDB has tag-like numbering: set `pdb_strip_nonpositive_resseq=true`; use `pdb_renumber_resseq_from_1=true` only if you want a clean 1..N residue numbering (check `pdb_numbering.json`).
- If ligand masking is too broad because of many HETATM: set `ligand_resnames=[...]` to include only the ligand(s) you want to protect.
- If the MSA is large/redundant: set `conservation_weighting="mmseqs_cluster"`; if clustering is unavailable/slow, keep `conservation_weighting="none"`.

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
- If DiffDock ran, mention `outputs/<run_id>/diffdock/` (e.g., `rank1.sdf`, `ligand.pdb`, `complex.pdb`, `out_dir.zip`).

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
