# Spec: Multi-Objective Meta-Surrogate BO with Continual Learning

## 1. Overview
This document outlines the architectural design for a next-generation `evolution` mode in the `protein_pipeline` system. The goal is to replace the naive, zero-knowledge RandomForest Bayesian Optimization (BO) loop with a **Multi-Objective Meta-Surrogate BO** approach. 

Crucially, this architecture features a **Human-in-the-loop Continual Learning** mechanism. It leverages a pre-trained ESM-3 Deep Neural Network (DNN) backbone to drastically reduce expensive AlphaFold2 (Oracle) evaluations, while continuously learning from user-generated pipeline data to become more accurate over time.

## 2. Motivation (Paper Defense Strategy)
Traditional BO in sequence design starts with zero biological context, requiring many expensive oracle calls (AF2, Rosetta) to find optimal sequences. While large Protein Language Models (PLMs) like ESM-3 can predict structures, they are static and lack real-time tuning for custom target optimization. 

Our approach introduces a **Self-Improving Cascaded System**:
1. **Multi-Objective Surrogate:** Utilize a pre-trained surrogate model (using ESM-3 embeddings) to predict not just pLDDT, but also Relax Scores (thermodynamic stability) and SoluProt (solubility) simultaneously.
2. **Computational Economy:** Filter the candidate pool intelligently. Only the sequences with the best multi-objective Pareto balance are sent to the expensive Oracles (AF2/Rosetta).
3. **Data Flywheel (Continual Learning):** The exact Oracle results are not thrown away. They are stored and used to dynamically fine-tune the surrogate model, ensuring the system grows smarter with every user run.

This proves that our system is not just a static pipeline, but a dynamic, self-optimizing platform that orchestrates state-of-the-art models intelligently, achieving Ground Truth accuracy with a fraction of the computational cost.

## 3. Architecture Design: The 3-Stage Pipeline

When a user initiates `evolution_mode`, sequence generation creates an initial pool of candidate sequences. These pass through three gating stages:

### Stage 1: Physicochemical & Solubility Gating (Ultra-Fast)
*   **Input:** Raw amino acid sequences.
*   **Mechanism:** Heuristic checks and fast CPU-based ML predictions (e.g., SoluProt score).
*   **Action:** Sequences failing predefined basic thresholds are instantly discarded.
*   **Compute Cost:** CPU-only, milliseconds per sequence.

### Stage 2: ESM-3 Meta-Surrogate Pre-Screening (Fast)
*   **Input:** Sequences that passed Stage 1.
*   **Mechanism:** 
    *   Convert sequences into semantic embeddings using a lightweight PLM (ESM-3).
    *   Pass embeddings through a Multi-Task Deep Surrogate Model pre-trained on ~1,000 diverse protein families.
    *   The model outputs three predictions simultaneously: `Pred_pLDDT`, `Pred_RelaxScore`, `Pred_SoluProt`.
*   **Action:** Calculate a composite Acquisition Score based on user-defined weights for each objective. Rank sequences and allow only the top $N$ to proceed.
*   **Compute Cost:** Light GPU inference, <1 second per sequence.

### Stage 3: The Oracle & Continual Feedback Loop (Slow, High-Fidelity)
*   **Input:** Top $N$ sequences from Stage 2.
*   **Mechanism:** Execute standard AlphaFold2 and Rosetta Relax to obtain Ground Truth structure, actual pLDDT, and actual Relax Score.
*   **Action (Feedback):** 
    *   **Local Tuning:** The actual scores are fed back into the current BO loop to refine the search space for the immediate target.
    *   **Global Flywheel:** The `[Sequence, Actual_pLDDT, Actual_Relax, Actual_SoluProt]` tuple is committed to a central Database (`knowledge_base/`).

## 4. Model and Data Management Strategy

### 4.1. Data Management (`knowledge_base/`)
*   All pipeline outputs (`summary.json`) that contain ground truth AF2/Relax metrics are automatically parsed and appended to a centralized training ledger (e.g., SQLite or structured Parquet files).
*   Data is periodically cleaned to remove redundant sequences or failed Oracle runs.

### 4.2. Model Management & Training Lifecycle
1.  **V1 (Offline Pre-training):** Train an initial `meta_surrogate_v1.pt` on ~1,000 diverse protein families. This solves the cold-start problem.
2.  **V2+ (Continual Learning):** A background cron job or admin-triggered script reads the newly accumulated user data from the `knowledge_base/`.
3.  It performs Transfer Learning on the current model weights using the new, highly targeted data.
4.  The new weights (`meta_surrogate_v2.pt`) are deployed, making Stage 2 predictions slightly more accurate for the entire user base.

## 5. Implementation Plan (Prototyping Phase)

Before full integration, we will build and validate a prototype:
1.  **Data Extraction:** Write a script to scrape existing `outputs/` directories for `[Sequence, pLDDT, SoluProt]` pairs.
2.  **Embedding & Training:** Use an accessible ESM model to generate embeddings and train a simple Multi-Layer Perceptron (MLP).
3.  **Validation:** Run ProteinMPNN to generate 100 novel sequences for a test target. Use the MLP to rank them. Select the top 10% and bottom 10%, run them through actual AF2, and verify that the top 10% has a statistically significant higher average pLDDT.

## 6. Success Metrics (For Paper Benchmarking)
*   **Sample Efficiency:** The new system should reach >85 pLDDT in <5 AF2 calls, whereas standard BO might take 20+.
*   **Multi-Objective Success:** Demonstrate the ability to find sequences that are both structurally sound (high pLDDT) and thermodynamically stable (good Relax score) faster than serial filtering.
*   **System Learning Curve:** Show a graph where the surrogate model's Mean Squared Error (MSE) against Oracle predictions decreases over time as more user runs are completed.