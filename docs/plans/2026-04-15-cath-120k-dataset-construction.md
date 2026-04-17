# Project: CATH-based 120K Protein Backbone Dataset Construction

## 1. Overview
This project aims to construct a high-fidelity, large-scale protein design dataset of **120,000 sequences** with corresponding structural confidence (pLDDT), physicochemical solubility (SoluProt), and thermodynamic stability (Rosetta Relax) metrics. By leveraging the **CATH database** for target selection, the dataset will provide unprecedented coverage of the protein structural universe, serving as the ultimate foundation for training advanced generative models such as GFlowNets and Reinforcement Learning (RL) agents.

## 2. Target Selection Strategy: CATH Sunburst Sampling
To ensure maximum diversity and eliminate family bias, targets are sampled based on the CATH hierarchical classification (Class, Architecture, Topology, Homologous superfamily).

*   **Goal:** 1,000 representative protein targets.
*   **Methodology:** 
    *   Systematic traversal of the **CATH Sunburst** levels.
    *   Select 1,000 distinct topologies (T-level) or architectures (A-level) to span the entire known protein fold space.
    *   Prioritize PDB entries with high-resolution experimental data for baseline accuracy.

## 3. Data Generation Pipeline (120K Scale)

The generation process follows a massive parallel execution model:
1.  **Mass Sampling (ProteinMPNN):** For each of the 1,000 CATH targets, generate **120 novel sequences** using ProteinMPNN with varying sampling temperatures (0.1 to 0.3) to capture a range of sequence-space near the target fold.
    *   *Total Yield:* 1,000 targets × 120 sequences/target = 120,000 unique protein sequences.
2.  **Multifaceted Evaluation (The Oracle):**
    *   **pLDDT (Structural Confidence):** Execute AlphaFold2 on all 120,000 sequences.
    *   **SoluProt (Solubility):** Rapid CPU-based solubility prediction for all sequences.
    *   **Relax/res (Stability):** Perform Rosetta FastRelax on AF2-predicted structures to obtain per-residue energy scores.

## 4. Scalable Compute Architecture (RunPod Serverless)

To overcome the 83-day single-GPU bottleneck, the project utilizes **RunPod Serverless Scale-out**:
*   **Parallel Workers:** Deploy 10 to 20 concurrent RunPod GPU instances (L4 or RTX A4000).
*   **Estimated Timeline:**
    *   With 10 parallel workers: ~8.3 days.
    *   With 20 parallel workers: ~4.1 days.
*   **Data Sink:** All results are streamed directly to **NCP S3 Object Storage** in real-time to ensure zero data loss and enable concurrent monitoring.

## 5. Downstream Modeling Applications
The 120K dataset will be formatted for immediate use in training:
*   **Deep Meta-Surrogates:** Multi-task MLP/CNNs for zero-shot screening.
*   **GFlowNets:** Learning reward-proportional probability distributions for diverse sequence generation.
*   **Offline RL:** Policy optimization for sequence design based on the 120K "experience" tuples.
*   **Foundation Model Fine-tuning:** Instruction-tuning ESM-3 or Evo2 on specific structural stability tasks.

## 6. Success Metrics & Quality Control
*   **Fold Coverage:** % of CATH architectures represented in the final dataset.
*   **Data Balance:** Ensure a healthy distribution of both "successes" (high pLDDT/low energy) and "failures" (low pLDDT/high energy) to provide strong discriminative signals for models.
*   **S3 Integrity:** Automated validation of PDB and JSON file integrity for all 120,000 entries.
