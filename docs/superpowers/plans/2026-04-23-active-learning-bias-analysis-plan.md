# Active Learning Bias Analysis Documentation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document the findings from the Active Learning simulation, specifically addressing missing metrics, sampling bias, and strategies for ensuring diverse sequence selection.

**Architecture:** Create a detailed Markdown report in the `docs/2026-04-15-meta-surrogate-prototype-results/` directory that analyzes the risks of random sampling and proposes diversity-aware sampling strategies (e.g., K-Means clustering in embedding space).

**Tech Stack:** Markdown.

---

### Task 1: Create the Bias Analysis Document

**Files:**
- Create: `docs/2026-04-15-meta-surrogate-prototype-results/active_learning_sampling_bias.md`

- [ ] **Step 1: Write the document content**

```bash
cat << 'DOC' > docs/2026-04-15-meta-surrogate-prototype-results/active_learning_sampling_bias.md
# Local Active Learning: Sampling Bias and Diversity Analysis

## 1. Metric Isolation (Where did SoluProt and Relax go?)
In the final iteration of the `05_active_learning_sim.py` script, we intentionally modified the objective function to **strictly optimize and evaluate based on raw pLDDT scores**. 
*   **Why?** pLDDT is the most reliable proxy for 3D structural viability. Normalizing and combining it with SoluProt/Relax diluted its importance, making it hard to see if the model was actually picking structurally sound proteins.
*   **Result:** The MLflow runs (e.g., `642ab075...`) only show `fold_surrogate_plddt` because we explicitly instructed the Random Forest to only train on and predict the structural metric.

## 2. The Danger of Random Sampling (Sampling Bias)
Currently, our "Oracle Budget" (the first 30 sequences sent to AF2) is selected entirely at random. This introduces significant risks:

### A. The "Lucky/Unlucky Draw" Problem
*   **Overestimation:** If the random 30 happen to include the absolute best sequence in the pool, the model learns its features but we already "spent" an Oracle call to find it. The surrogate's job becomes trivial.
*   **Underestimation (Cold Start):** If the random 30 are all low-performing "junk" sequences, the Random Forest learns what *makes a bad protein*, but has no idea what a *good protein* looks like. When evaluating the remaining 90 sequences, it extrapolates blindly, leading to poor Top-10 selections.

### B. Mode Collapse (Prediction Bias)
Random Forests cannot extrapolate beyond the range of their training data. If the highest pLDDT in the training 30 is 80, the RF will never predict a score higher than 80 for the remaining pool. It becomes biased toward the local neighborhood of the training samples.

## 3. Solution: Diversity-Aware Sampling (Exploration)
To fix this, we must replace "Random Selection" with "Diverse Selection" for the initial 30 samples. If we cover the entire sequence space, the surrogate model learns the global topology of the target.

### Proposed Strategy: K-Means Clustering on ESM Embeddings
Instead of random picking, we should:
1.  Generate 320D ESM embeddings for all 1,000 generated sequences.
2.  Run **K-Means clustering** (with K=30) on the embeddings.
3.  Select the **centroid** (or the sequence closest to the centroid) of each cluster to be sent to AF2.
4.  **Result:** The 30 Oracle calls are perfectly distributed across the sequence space, capturing every major structural variation. The Surrogate Model trained on this diverse set will be highly accurate and unbiased.

## 4. Conclusion
While the N=30 Random Sampling surrogate closed 46% of the performance gap, introducing Diversity-Aware Sampling (K-Means) for the initial budget will likely push this efficiency to 80-90%, making the 1,000-Oracle run completely obsolete.
DOC
```

- [ ] **Step 2: Verify the file exists**

Run: `cat docs/2026-04-15-meta-surrogate-prototype-results/active_learning_sampling_bias.md | head -n 5`
Expected: Shows the document header.

- [ ] **Step 3: Commit the new document**

```bash
git add docs/2026-04-15-meta-surrogate-prototype-results/active_learning_sampling_bias.md
git commit -m "docs: add analysis on active learning sampling bias and diversity"
```
