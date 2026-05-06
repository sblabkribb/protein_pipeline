# Integrate K-Means Active Learning into Evolution Stepper

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the `run_evolution` function in `pipeline-mcp/src/pipeline_mcp/evolution.py` to use on-the-fly Local Active Learning with K-Means diversity sampling instead of relying on global pre-trained models.

**Architecture:** 
1. Generate pool using ProteinMPNN & SoluProt.
2. Extract ESM-2 embeddings for the pool.
3. Use K-Means to select an "Oracle Budget" of N diverse sequences (e.g., N=30).
4. Run AF2 (Oracle) on these N sequences to get ground-truth pLDDT.
5. Train a `RandomForestRegressor` on the N embeddings -> pLDDT.
6. Predict pLDDT for the remaining pool.
7. Select Top K (e.g., 20) sequences based on prediction and run AF2 on them.
8. Compile all AF2-evaluated sequences, optionally run Relax, and return the best.

**Tech Stack:** Python, scikit-learn (KMeans, RandomForestRegressor), MLflow.

---

### Task 1: Refactor `run_evolution`

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/evolution.py`

- [ ] **Step 1: Rewrite `run_evolution` to implement the active learning logic.**
- Incorporate `KMeans` and `RandomForestRegressor` from `sklearn`.
- Replace Stage 2 (Meta-Surrogate Ranking with pre-trained models) with the new K-Means + RandomForest active learning logic.
- We will do AF2 calls in two batches: first the K-Means selected batch, then train RF, then the predicted Top K batch.

- [ ] **Step 2: Commit changes**
```bash
git add pipeline-mcp/src/pipeline_mcp/evolution.py
git commit -m "feat: integrate K-Means Active Learning into evolution stepper"
```
