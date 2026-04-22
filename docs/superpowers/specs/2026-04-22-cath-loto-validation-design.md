# CATH LOTO Validation Strategy

## 1. Goal
Validate the generalization capability of the Deep Meta-Surrogate model (ESM-2 + MLP) across completely novel protein backbones. By utilizing a **Leave-One-Target-Out (LOTO)** cross-validation strategy on the recent 9-target CATH batch (approx. 1,080 sequences), we will prove that historical pipeline data can effectively predict performance metrics (SoluProt, pLDDT) for unseen protein families without requiring initial AlphaFold2 calls (Zero-Shot).

## 2. Architecture & Data Flow

### 2.1. Data Aggregation & Embedding
1.  **Source:** Parse the output data for the 9 completed CATH targets (from S3/local sync).
2.  **Feature Extraction:** Extract `target_id`, `sequence`, `soluprot_score`, and `plddt_score`.
3.  **Embedding Generation:** Pass all unique sequences through the frozen `ESM-2 (8M)` model to extract mean sequence representations (320-dimensional).
4.  **Caching:** Save the extracted data and embeddings locally (`cath_extracted_data.csv`, `cath_embeddings.npy`) to accelerate the training loop.

### 2.2. LOTO Validation Loop
For each of the 9 targets (`T`):
1.  **Split:** 
    *   Test Set = All sequences belonging to Target `T`.
    *   Train Set = All sequences belonging to the remaining 8 targets.
2.  **Train:** Initialize a fresh MLPRegressor (e.g., hidden layers 256, 128) and train it on the Train Set. Separate models will be trained for SoluProt and pLDDT.
3.  **Evaluate:** Predict scores for the Test Set and calculate the Mean Squared Error (MSE).

## 3. MLflow Integration
The entire process will be logged to the internal MLflow server (`http://127.0.0.1:18050`).
*   **Experiment Name:** `CATH_LOTO_Validation`
*   **Hierarchy:**
    *   **Parent Run:** `LOTO_Summary_<timestamp>` (Logs the average MSE across all 9 folds and final hyperparameters).
    *   **Nested Runs:** `Fold_<Target_ID>` (Logs the train size, test size, and individual MSE for that specific target).

## 4. Success Criteria
*   **Backbone Generalization:** The primary metric is the average LOTO pLDDT MSE. If the average error remains comparable to the random-split baseline (e.g., MSE < 2.5), it empirically proves that the ESM embeddings provide sufficient structural context to generalize across different CATH topologies without target-specific fine-tuning.
