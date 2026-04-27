# Manuscript Rewrite Design: protein_pipeline Integrated Research Paper

## Goal
Rewrite `/opt/protein_pipeline/manuscript (5).md` to integrate existing system architecture content with new empirical benchmark results (surrogate selection) and scientific analysis (MPNN error decomposition).

## Architecture of the New Manuscript

### 1. Front Matter
- **Title**: `protein_pipeline`: An Integrated Research Platform for Orchestrated Protein Design and Empirical Analysis
- **Abstract**: Updated to include both the system contribution and the key scientific findings (RF robustness, K-Means superiority, and target-intrinsic error decomposition).

### 2. Introduction & Problem Statement
- **Narrative**: Frames the "operational gap" (orchestration) and the "interpretability gap" (understanding model failures).
- **Contribution**: Presents `protein_pipeline` as the solution that enables the subsequent empirical studies.

### 3. System Architecture (Consolidated)
- **Content**: Merges the redundant sections from the original draft.
- **Key Points**: MCP-enabled backend, run-centric artifact storage (`run_id`), stage-aware execution (`msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty`), and the Analyze tab for comparative review.

### 4. Empirical Benchmark: Surrogate Model Selection
- **Setup**: 15 CATH targets, 120 ProteinMPNN sequences/target, ESM-2 8M embeddings.
- **Findings**:
    - **Model Selection**: RF, LightGBM, and Ridge are top-tier. RF is the robust default.
    - **Sampling Strategy**: K-Means selection is significantly better than random for small N (N <= 20).
    - **Sample Size**: N=30 is the optimal plateau for BO uplift.
    - **Embedding Size**: ESM-2 8M (320D) is sufficient and 5x faster than 640D.

### 5. Scientific Analysis: MPNN Error Decomposition
- **Method**: Variance decomposition (ICC1) of pLDDT across targets and designs.
- **Findings**: ICC1 = 0.996.
- **Conclusion**: "Bad sequences are bad" because the target is hard, not because ProteinMPNN is noisy. This justifies the pipeline's focus on comparative analysis across targets.

### 6. Discussion & Conclusion
- **Synthesis**: How the system's architecture (artifact persistence, comparative tools) directly enabled these findings.
- **Future Work**: Agentic planning, broader benchmarking, and multi-objective optimization.

## Data Sources
- **System Content**: `/opt/protein_pipeline/manuscript (5).md` (lines 1-138)
- **Benchmark Results**: `docs/plans/2026-04-27-cath-rf-benchmark-results-ko.md`
- **Error Decomposition**: `data/benchmark/results/mpnn_decomposition_summary.json` and `scripts/benchmark/07_mpnn_error_decomposition.py`

## Constraints
- Maintain the "system paper" narrative for the architecture parts.
- Ensure all new results are accurately reflected from the source files.
- Remove all redundant sections at the end of the original file.
