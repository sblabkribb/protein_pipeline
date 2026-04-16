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

### 4.1. Data Management: NCP S3 Object Storage
The system utilizes **NCP (Naver Cloud Platform) Object Storage** as the central repository for all design artifacts and the cumulative knowledge base. This enables a true **Distributed Data Flywheel**.
*   **Artifact Sync:** Upon completion of any run, the entire `outputs/{run_id}` directory is synchronized to the `protein-pipeline-outputs` bucket.
*   **Knowledge Ledger:** A structured file (e.g., `knowledge_base/training_ledger.parquet`) is maintained in S3. It stores sanitized `[Sequence, Mean_Embedding, Global_pLDDT, SoluProt, Relax]` tuples from every validated design.
*   **Scalability:** Storing data in S3 allows multiple pipeline instances (nodes) to share the same intelligence and enables large-scale offline training without local disk constraints.

### 4.2. pLDDT Handling & Training Granularity
While AlphaFold2 provides per-residue confidence scores, our Meta-Surrogate is optimized for **Global Design Selection**.
*   **Input Representation:** Residue-level ESM-3 embeddings are combined via **Mean Pooling** to represent the sequence's overall structural potential.
*   **Target Metric:** The model is trained to predict the **Global Average pLDDT** of the structure. This provides a single, high-signal optimization target for the Bayesian Acquisition function.
*   **Logic:** By mapping the entire semantic space of the PLM to the global confidence score, the surrogate learns to identify sequences that achieve high structural integrity across the entire 3D fold.

### 4.3. Model Management & Training Lifecycle
1.  **V1 (Offline Pre-training):** Initial models are trained on historical data accumulated from previous SOTA runs.
2.  **V2+ (Continual Learning):** A periodic re-training job pulls the latest `training_ledger.parquet` from NCP S3, performs incremental fine-tuning (Transfer Learning), and pushes the updated weights back to the **S3 Model Registry**.
3.  **Deployment:** The `evolution.py` engine always fetches the `latest` model weights from S3 at runtime to ensure maximum predictive accuracy.

## 5. Implementation Plan (Prototyping Phase)

Before full integration, we will build and validate a prototype:
1.  **Data Extraction:** Write a script to scrape existing `outputs/` directories for `[Sequence, pLDDT, SoluProt]` pairs.
2.  **Embedding & Training:** Use an accessible ESM model to generate embeddings and train a simple Multi-Layer Perceptron (MLP).
3.  **Validation:** Run ProteinMPNN to generate 100 novel sequences for a test target. Use the MLP to rank them. Select the top 10% and bottom 10%, run them through actual AF2, and verify that the top 10% has a statistically significant higher average pLDDT.

## 6. Success Metrics (For Paper Benchmarking)
*   **Sample Efficiency:** The new system should reach >85 pLDDT in <5 AF2 calls, whereas standard BO might take 20+.
*   **Multi-Objective Success:** Demonstrate the ability to find sequences that are both structurally sound (high pLDDT) and thermodynamically stable (good Relax score) faster than serial filtering.
*   **System Learning Curve:** Show a graph where the surrogate model's Mean Squared Error (MSE) against Oracle predictions decreases over time as more user runs are completed.