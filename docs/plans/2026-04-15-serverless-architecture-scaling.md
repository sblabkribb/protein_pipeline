# Architecture: RunPod Serverless & Distributed Data Flywheel

## 1. Overview
As the `protein_pipeline` scales, the computational demands of the Deep Meta-Surrogate model (particularly AlphaFold2 validation and periodic MLP fine-tuning) exceed the capacity of a monolithic local server. 

To ensure limitless scalability and cost-efficiency, we designed a **Fully Cloud-Native Serverless Architecture** leveraging **RunPod Serverless** for computation and **NCP S3 Object Storage** for data management.

## 2. Distributed Architecture Design

The system separates *Orchestration*, *Storage*, and *Compute* into independent, scalable layers:

### 2.1. Orchestration Layer (Main Server)
*   The current `pipeline-mcp` server acts purely as a lightweight orchestrator.
*   It receives user requests, handles UI interactions, and delegates heavy computing tasks to remote serverless workers via API calls.
*   It maintains zero local state; all knowledge is fetched from S3.

### 2.2. Data Lake Layer (NCP S3)
*   **Artifact Bucket:** Stores every generated PDB, A3M, and JSON file.
*   **Knowledge Ledger:** A continuous stream of `[ESM-Embedding, pLDDT, SoluProt, Relax]` tuples. As users run the pipeline, the Oracle results automatically append to this ledger.
*   **Model Registry:** Stores versioned weights of the Deep Meta-Surrogate model (e.g., `meta_surrogate_v2.pt`).

### 2.3. Serverless Compute Layer (RunPod)
Instead of running heavy models locally, the orchestrator triggers independent RunPod endpoints:
1.  **Generator Worker (ProteinMPNN / RFD3):** Extremely fast. Can generate 1,000+ sequences in seconds.
2.  **Surrogate Inference Worker (ESM-3 + MLP):** Loads the latest model from S3. Takes the 1,000 sequences, generates ESM-3 embeddings, and returns the top 20 ranked IDs within milliseconds.
3.  **Oracle Worker (AlphaFold2 / Rosetta):** The most computationally expensive worker. Scales up (e.g., 20 concurrent GPU pods) to evaluate the top 20 candidates in parallel, reducing validation time from hours to minutes.
4.  **Trainer Worker (Periodic Cron Job):** Wakes up weekly, pulls the massive Knowledge Ledger from S3, fine-tunes the Meta-Surrogate MLP weights, pushes the new weights back to the S3 Registry, and immediately spins down to save costs.

## 3. Data Generation Strategy (Bootstrap Phase)
To build the foundational "Global Prior" without requiring users to wait, we utilize the Serverless architecture for a massive parallel bootstrap:
*   **Target:** 1,000 diverse protein families.
*   **Generation:** ProteinMPNN generates 120 sequences per family = 120,000 total sequences. (Compute time: ~2-4 hours).
*   **Evaluation Bottleneck:** AF2 evaluation of 120,000 sequences takes ~83 days on a single GPU.
*   **Serverless Solution:** By spinning up 100 concurrent RunPod Oracle Workers, the entire 120,000-sequence Ground Truth dataset is generated in **under 24 hours**.

## 4. Conclusion for Paper Defense
By moving to a Serverless model, the `protein_pipeline` transcends the limitations of local hardware. It becomes a **"Compute-as-a-Service"** platform where the AI Meta-Surrogate becomes exponentially smarter with every run, and the infrastructure automatically scales horizontally to absorb any level of user demand without accumulating idle server costs.