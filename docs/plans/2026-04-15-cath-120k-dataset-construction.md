# Project: CATH-based Comprehensive Protein Evolution Dataset Construction

## 1. Overview
This project constructs a massive, high-fidelity protein evolution and design dataset to train advanced generative models (like ProteinMPNN selectors, GFlowNets, and RL agents). Instead of just filtering existing sequences, the dataset records the *entire evolutionary design trajectory*—from MSA conservation, masking, and backbone generation (RFD3), to sequence design (ProteinMPNN), multifaceted evaluation (Oracle), and finally, Novelty/WT Diff.

## 2. Target Selection Strategy: Topological Diversity Sampling (Train/Val/Test Split)
To eliminate sampling bias and cover the entire known protein universe efficiently without redundancy:
1.  **Topological Extraction (1,472 Targets):** We process the latest `cath-domain-list.txt` and group domains by their **Topology (C.A.T level)**, which represents completely different, unique 3D Fold shapes. By extracting exactly one random representative domain from every existing Topology, we yield exactly **1,472 distinct structural targets** (`scripts/01_fetch_and_split_datasets.py`).
2.  **Dataset Split (80:10:10):** To rigorously evaluate downstream generative models without data leakage, these 1,472 unique topologies are pre-split into separate directories before any generation occurs:
    *   **Train Set (`cath_train/`):** 1,177 Targets (80%) - Used for training generative models (GFlowNets, Meta-Surrogates).
    *   **Validation Set (`cath_val/`):** 147 Targets (10%) - Used for hyperparameter tuning and model selection.
    *   **Test Set (`cath_test/`):** 148 Targets (10%) - Held out for final, unbiased evaluation of generated sequence quality.

## 3. The 10-Step Full Trajectory Pipeline (~176K Scale)

For every target across all splits, the pipeline executes the full sequence of tools to generate an "evolutionary" dataset. 
The generation formula strictly follows **3 * 2 * 10 * 2 = 120 Trajectories per target**:
*   **3 Conservation Tiers:** MSA constraints applied at 30%, 50%, and 70% threshold.
*   **2 Backbone Generators:** Utilizing both **BioEmu** and **RFdiffusion3 (RFD3)**.
*   **10 Backbone Samples:** Generating 10 structural variations per generator per tier.
*   **2 Sequence Designs:** Running ProteinMPNN to design 2 unique sequences per backbone.

**Pipeline Steps (`scripts/02_run_cath_batch.py`):**
1.  **MSA & Conservation:** Run MMseqs2 against UniRef90.
2.  **WT Baseline:** Calculate starting metrics.
3.  **Masking:** Fixed 6Å proximity masking around existing ligands/critical sites.
4.  **Backbone Generation:** Produce structural neighborhoods via BioEmu (10 samples) and RFD3 scaffold mode (10 samples).
5.  **Mass Sampling (ProteinMPNN):** Generate 2 sequences per backbone at temperature 0.1.
6.  **SoluProt (Solubility):** Physicochemical evaluation (all results kept).
7.  **ColabFold (pLDDT):** Structural confidence assessment.
8.  **Rosetta Relax (Stability):** Thermodynamic energy minimization.
9.  **Novelty / WT Diff:** Compare structural drift and sequence novelty against WT.
10. **S3 Sync:** Export all artifacts to NCP S3 Object Storage (`outputs/run_id/tiers/`).

*   *Total Yield:* 1,472 targets × 120 trajectories = **176,640 evolutionary data tuples.**

## 4. Execution & Scalable Compute Architecture
*   **Batch Execution:** The pipeline is executed per subset using the batch script:
    *   `python3 scripts/02_run_cath_batch.py --subset test` (Run the 148 test targets first as a pilot)
    *   `python3 scripts/02_run_cath_batch.py --subset train` (Run the massive 1,177 training targets)
*   **Parallel Workers:** Due to the massive scale (176K AF2/Relax evaluations), deploying 50 to 100 concurrent ColabFold and Relax workers on RunPod Serverless is highly recommended. Using only 5 workers will take ~12 days just for the Test set.
*   **Data Sink:** Stream artifacts directly to **NCP S3 Object Storage**.

## 5. Success Metrics & Quality Control
*   **Evolutionary Trajectory Data:** Ensure that intermediate steps (MSA weights, masks, RFD3 backbones) are preserved alongside the final sequence evaluation.
*   **Data Balance:** Retain both failed and successful designs to teach models what *not* to generate.
