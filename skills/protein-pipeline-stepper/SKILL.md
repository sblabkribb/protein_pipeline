---
name: protein-pipeline-stepper
description: Connect to and run the protein-pipeline via MCP. Covers one-click token setup (mcp.json) for VS Code/Codex, plus stepwise pipeline.run/pipeline.status execution with safe polling, run_id reuse, stop_after staging, and duplicate-job avoidance. Use when connecting the protein-pipeline MCP server or running staged RFD3/MMseqs2/ProteinMPNN/SoluProt/AF2 jobs and you want output paths (not narrative summaries).
---

# Protein Pipeline Stepper

## Overview

Run the protein pipeline in deterministic stages via MCP tools and return the output paths required for the next step.

## Connecting (MCP auth)

Before running anything, the MCP server `protein-pipeline` must be reachable and authenticated.

1. Open the protein-pipeline web app and sign in (local login or KBF SSO).
2. Go to the **MCP** tab and click **Copy mcp.json with my token**. This copies a
   ready-to-paste `mcp.json` with your bearer token already filled in — you do not
   need to open browser devtools.
3. Add it to your client:
   - **VS Code:** run **MCP: Open User Configuration** and paste into `mcp.json`.
   - **Codex:** add an MCP server named `protein-pipeline` with the same URL and the
     `Authorization: Bearer <token>` header.
4. The token is a short-lived SSO/login token. When MCP calls start failing with an
   auth error (401), return to the MCP tab and click the button again to refresh the
   token in your `mcp.json`.

**Long-running jobs and token expiry.** The bearer token is a *snapshot* of the
SSO access token; it does not auto-refresh, and the SSO access-token lifetime is
typically only a few minutes. Long jobs (ColabFold/AF2, RFD3, DiffDock) keep
running **server-side** regardless — they are async, and the `run_id`, artifacts,
and `status.json` persist. But your **polling** calls will start returning 401 once
the token expires mid-job. When that happens: re-fetch the token (re-click **Copy
mcp.json with my token**, update your `mcp.json` / env var), then resume
`pipeline.status(run_id)` polling on the **same `run_id`** — do not start a
duplicate run. (A client with real OAuth refresh avoids this entirely; that is a
planned follow-up.)

You can also download this skill from the MCP tab (**Download skill**) so your client
has the connection + execution instructions locally.

## Prerequisites

- Use the MCP server named `protein-pipeline` (it must expose `pipeline.run`, `pipeline.status`, `pipeline.list_runs`).
  - If available, also use `pipeline.list_artifacts` and `pipeline.read_artifact` to fetch intermediate files without asking for filesystem access.
- Treat `pipeline.run` as potentially long-running; prefer staged execution with `stop_after`.

## Non-Negotiable Rules

- Always reuse a stable `run_id` across stages. If the user does not supply one, create one with only `[a-zA-Z0-9_.-]` and no spaces.
- Never pass file paths as `target_fasta` / `target_pdb` / `rfd3_input_pdb`. Read the file contents and pass the raw text.
- Before calling `pipeline.run` for a `run_id`, call `pipeline.status(run_id)`:
  - If `state=running`, do not call `pipeline.run` again. Poll `pipeline.status` until completion/failure.
  - If `state=failed` (or similar), stop and report the error details, then diagnose and propose a corrected command (see "Result validation & self-correction"). Do not re-run without user confirmation.
- If a `pipeline.run` call times out in the client, assume the remote job may still be running; switch to polling with `pipeline.status`.

## Workflow (Stage Runner)

### Interactive setup — ask before a full run

For a **full pipeline run** (not a single stage the user already fully specified), do not silently assume everything. First call `pipeline.plan_from_prompt` with the user's request to detect missing inputs/questions, then ask a short, concrete set of questions in **one** message and wait for answers before calling `pipeline.run`:

1. **Defaults or advanced?** — "Run with sensible defaults, or set advanced options?"
2. **Surrogate triage?** — "Use the surrogate model to triage candidates before AF2 (`surrogate_triage_enabled=true`)? It screens designs with a fast surrogate and runs AF2 only on the top ones — cheaper/faster, slightly less exhaustive." If yes and they want control, offer `surrogate_triage_top_k`, `surrogate_triage_initial_samples`, `surrogate_triage_model`.
3. **Missing required inputs** surfaced by `plan_from_prompt` `questions` (target sequence/PDB, RFD3 inputs, ligand, etc.).
4. If **advanced**, offer the main knobs with their defaults:
   - MSA: `mmseqs_target_db` (uniref90), `mmseqs_max_seqs` (3000)
   - Design: `conservation_tiers` ([0.3, 0.5, 0.7]), `num_seq_per_tier` (16), `sampling_temp`
   - SoluProt: `soluprot_cutoff` (0.5)
   - AF2: `af2_plddt_cutoff` (85), `af2_top_k` (20), `af2_sequence_ids`

Accept "defaults" as a valid answer to everything. After the user answers, **echo back the final settings** (including `surrogate_triage_enabled` and any advanced knobs) and then call `pipeline.run` with exactly those. Don't re-ask on later stages of the same `run_id` unless the user changes scope. For a single standalone stage the user already specified, skip the questions and run it directly.

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

## Single-model / standalone execution

Run one model on its own (no full pipeline) when you only need a single computation. **Every standalone ("Single Stage") mode in the web app maps to an MCP call** — two have dedicated tools, the rest run through `pipeline.run` with `stop_after` set to a single stage:

| Standalone model | MCP call |
| --- | --- |
| RFD3 (backbone) | `pipeline.run` with `stop_after="rfd3"`, `rfd3_use=true`, and RFD3 inputs (`rfd3_input_pdb` + `rfd3_contig`, or `rfd3_inputs`/`rfd3_inputs_text`) |
| BioEmu (backbone) | `pipeline.run` with `stop_after="bioemu"`, `bioemu_use=true`, and a `target_pdb`/`target_fasta` |
| MSA (MMseqs2) | `pipeline.run` with `stop_after="msa"` and `target_fasta` or `target_pdb` |
| ProteinMPNN | `pipeline.run` with `stop_after="design"` and `target_pdb` |
| SoluProt | `pipeline.run` with `stop_after="soluprot"` and `target_pdb` (or `target_fasta` + AF2 configured) |
| ColabFold / AlphaFold2 | `pipeline.run_af2` or `pipeline.af2_predict` (standalone), **or** `pipeline.run` with `stop_after="af2"` |
| DiffDock | `pipeline.diffdock` or `pipeline.run_diffdock` (standalone) |

### Dedicated standalone tools

There are **two AF2 tools and two DiffDock tools** with different input field names — do not mix them up. Call `tools/list` if unsure, then match the schema exactly:

- **`pipeline.run_af2`** — AF2/ColabFold from a plain sequence. Input: `fasta` **or** `sequence` (note: `fasta`, *not* `target_fasta`). Optional: `af2_provider` (`colabfold`/`af2`), `af2_chain_ids` (array), `af2_model_preset` (e.g. `multimer` for multi-chain), `sequence_id`, `run_id`, `force`, `dry_run`. Best when you already have a sequence/FASTA.
- **`pipeline.af2_predict`** — AF2/ColabFold from pipeline-style inputs. Input: `target_fasta` **or** `target_pdb`. Optional: `af2_provider`, `af2_model_preset`, `af2_db_preset`, `af2_extra_flags`, `run_id`, `dry_run`. Best when your input is a `target_pdb`/`target_fasta` you'd also feed the pipeline.
- **`pipeline.run_diffdock`** — docking, lighter args. Input: `protein_pdb` + `ligand_smiles`. Optional: `run_id`, `force`, `dry_run`.
- **`pipeline.diffdock`** — docking, pipeline-style args. Input: `protein_pdb`/`target_pdb` + `diffdock_ligand_smiles`/`diffdock_ligand_sdf` (also accepts `ligand_smiles`/`ligand_sdf`). Optional: `complex_name`, `diffdock_extra_args`, `run_id`, `dry_run`.

### Single stage via `pipeline.run` + `stop_after`
- Set `stop_after` to exactly one of `rfd3`, `bioemu`, `msa`, `design`, `soluprot`, `af2` and pass a stable `run_id`. The pipeline runs only that stage's prerequisites and stops.
- **RFD3 and BioEmu must be explicitly enabled** with `rfd3_use=true` / `bioemu_use=true`; otherwise `stop_after` for that stage is rejected.
- Cached artifacts from earlier stages are reused; pass `force=true` to recompute.

Always pass raw file **contents** (not paths) for `target_pdb`/`target_fasta`/`rfd3_input_pdb`. Gate and poll standalone runs like staged runs: call `pipeline.status(run_id)` first; if `state=running`, poll instead of calling `pipeline.run`/the standalone tool again.

## Result validation & self-correction

A command can be wrong (bad params, wrong inputs) even when it "succeeds." Validate before and after, and propose fixes — but never silently re-run expensive jobs.

**Before running:** for a non-trivial or first-time command, call `pipeline.preflight` (validates inputs/config without running) and fix anything it flags before calling `pipeline.run`.

**After running, sanity-check the result:**
- Check `pipeline.status(run_id)` state plus the run's `summary.json`/`status.json`.
- Watch for implausible or empty outputs: 0 designs, empty MSA, pLDDT/solubility far outside expected ranges, or a stage that "succeeded" with no artifacts.

**If a stage failed or a result looks wrong:**
1. Diagnose — read the error details / `status.json` / `summary.json` and identify the likely cause (wrong `stop_after`, missing input, bad `rfd3_contig`, wrong `design_chains`, a file passed as a path instead of its contents, etc.).
2. Propose a corrected command — state exactly what you would change and why.
3. **Do not re-run automatically.** Ask the user to confirm before re-running, especially for GPU stages (`rfd3`, `af2`, `design`, `diffdock`). Re-run only after confirmation, using `force=true` (to override cached artifacts) or a fresh `run_id`.

This keeps a human in the loop for cost while still letting the AI catch and explain mistakes.

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
