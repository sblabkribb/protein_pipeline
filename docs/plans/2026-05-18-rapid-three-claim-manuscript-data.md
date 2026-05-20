# RAPID Three-Claim Manuscript/Data Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Recast the manuscript around three defensible RAPID claims and refresh the benchmark data without relying on pre-chain-fix CATH results as the primary evidence.

**Architecture:** RAPID is treated as a reproducible artifact-orchestration platform for solubility-aware, structural-confidence-guided protein redesign. The main manuscript should carry only three claims: artifact/model orchestration, AF2-budgeted active learning, and structural-context compute allocation. Detailed surrogate diagnostics, bias analyses, and extended CATH QC tables move to supplementary material.

**Tech Stack:** Python benchmark scripts, `pipeline-mcp` artifact contract, CATH PDB inputs, RunPod-backed model providers, Markdown manuscript, Pandoc/Word export.

---

### Task 1: Rename and Scope the Main Manuscript Around RAPID

**Files:**
- Modify: `public_release/manuscript/manuscript.md`
- Modify: `docs/manuscript.md`
- Create/Modify: `public_release/manuscript/supplementary.md`

**Steps:**
1. Replace `protein_pipeline` as the manuscript-facing platform name with `RAPID`.
2. Define RAPID as a platform name once, preferably as “RAPID, a reproducible artifact pipeline for integrated design,” without forcing every later mention to expand the acronym.
3. Keep the biological scope as solubility-aware and structural-confidence-guided redesign; avoid claiming measured stability or general protein-design superiority without wet-lab evidence.
4. Rebuild the Results around three claims:
   - Claim 1: RAPID turns fragmented AI model outputs into reusable artifacts and enables model replacement.
   - Claim 2: RAPID reduces AF2/ColabFold use through SoluProt gating, K-means bootstrap selection, RF/Ridge surrogate ranking, and Top-K acquisition.
   - Claim 3: RAPID exposes structural-context allocation by comparing single target, BioEmu, RFD3, and RFD3+BioEmu contexts under explicit AF2 budgets.
5. Move rank-mean ensemble, detailed surrogate-family tables, acquisition-bias heatmaps, and extended CATH QC details to supplementary material.

**Verification:**
- Run `grep -n "protein_pipeline\\|23-target\\|stability improvement" public_release/manuscript/manuscript.md`.
- Confirm no main-text claim depends on the old 23-target subset as the final post-fix benchmark.

### Task 2: Refresh Corrected-Chain CATH Benchmark Targets

**Files:**
- Create/Modify: `public_release/data/benchmark/results/rapid_target_manifest.csv`
- Create: `scripts/benchmark/15_select_rapid_targets.py`
- Create: `public_release/scripts/benchmark/15_select_rapid_targets.py`

**Steps:**
1. Scan CATH train/val/test PDBs with corrected chain parsing.
2. Exclude targets already used in the public-release 73-run and curated CATH summaries when selecting the next manuscript refresh set.
3. Select a deterministic 40-target CATH re-screening set stratified by split and length bin.
4. Select an 8-target subset for structural-context ablation.
5. Store target, split, PDB path, requested chain, selected chain, length, length bin, and selection flags in the manifest.

**Verification:**
- Run `python3 scripts/benchmark/15_select_rapid_targets.py --source-root /opt/protein_pipeline --exclude-completed --limit 40 --structural-limit 8`.
- Confirm the output reports `selected_for_cath_rescreen=40` and `selected_for_structural_context=8`.

### Task 3: Extend Structural-Context Ablation to BioEmu

**Files:**
- Modify: `scripts/benchmark/backbone_ensemble_ablation.py`
- Modify: `public_release/scripts/benchmark/backbone_ensemble_ablation.py`

**Steps:**
1. Change default arms from RFD3-only pilot arms to `single,bioemu,rfd3_single,rfd3_bioemu`.
2. Keep `rfd3_ensemble3` as an optional supplementary arm.
3. Ensure each arm uses comparable ProteinMPNN design budgets and the same AF2 cap of 30 candidates per target-arm run.
4. Record planned backbone count, planned design count, RFD3 settings, and BioEmu settings in the manifest.
5. Update summary plots/tables to work with four or more arms.

**Verification:**
- Run `python3 -m py_compile scripts/benchmark/backbone_ensemble_ablation.py`.
- Run `python3 scripts/benchmark/13_run_backbone_ensemble_ablation.py --dry-run --targets 1kvdD00 --arms single,bioemu,rfd3_single,rfd3_bioemu --replicates 1`.

### Task 4: Make CATH Batch Execution CI/CD-Path Safe

**Files:**
- Modify: `scripts/02_run_cath_batch.py`
- Modify: `public_release/scripts/02_run_cath_batch.py`

**Steps:**
1. Remove the hard-coded `/opt/protein_pipeline` root.
2. Resolve project root from `PROTEIN_PIPELINE_ROOT`, falling back to the checked-out script location.
3. Keep `.env` loading relative to the resolved project root so the same script works in work, dev, staging, and production directories.

**Verification:**
- Run `python3 -m py_compile scripts/02_run_cath_batch.py`.

### Task 5: Execute and Incorporate Final Data

**Files:**
- Modify: `public_release/manuscript/manuscript.md`
- Modify: `public_release/manuscript/supplementary.md`
- Modify: `public_release/data/benchmark/results/*.csv`
- Modify: `public_release/figures/benchmark/*.png`

**Steps:**
1. After CI/CD promotes the updated code to dev/staging/prod, run the 40-target corrected-chain CATH re-screening set.
2. Run the 8-target structural-context ablation with `single,bioemu,rfd3_single,rfd3_bioemu`.
3. Regenerate tables/figures from stored artifacts.
4. Replace legacy 23-target language in the main manuscript with corrected-chain benchmark results.
5. Keep the old 23-target analyses in the supplement as pre-fix artifact-benchmark diagnostics only if they remain useful.

**Verification:**
- Confirm all generated tables and figure captions reference the same final target counts.
- Confirm no claim of wet-lab stability, soluble expression, or activity improvement is made without experimental validation.
