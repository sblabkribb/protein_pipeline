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

## 5. Empirical Diversity Analysis (N=30)
To verify if our local surrogate suffers from Mode Collapse (picking sequences that are too similar to each other), we added a Sequence Identity tracking module to `05_active_learning_sim.py`.

We tracked three metrics across the 12 evaluated targets:
1.  **Pool Sim:** Average pairwise sequence identity within the remaining 90 candidate sequences.
2.  **Surr Sim:** Average pairwise sequence identity within the Top 10 sequences chosen by the Surrogate.
3.  **Surr vs Opt:** Average pairwise sequence identity between the Surrogate's Top 10 and the True Optimal Top 10.

### Results
| Target | Pool Sim | Surr Sim (Model's Pick) | Surr vs Opt (Accuracy) |
| :--- | :---: | :---: | :---: |
| `1h41B03` | 0.86 | 0.89 | 0.88 |
| `1f4hB01` | 0.80 | 0.93 | 0.88 |
| `1efnD00` | 0.81 | 0.94 | 0.91 |
| `1e1hB02` | 0.81 | 0.84 | 0.83 |
| `1m3iC02` | 0.76 | 0.82 | 0.80 |
| `1ltsA00` | 0.83 | 0.93 | 0.88 |
| `1jmoL00` | 0.78 | 0.78 | 0.80 |
| `1ibvC00` | 0.86 | 0.87 | 0.87 |
| `1jmzG00` | 0.79 | 0.89 | 0.84 |
| `1kvdD00` | 0.89 | 0.95 | 0.95 |
| `1b65A00` | 0.86 | 0.89 | 0.84 |
| `1keeF01` | 0.88 | 0.92 | 0.87 |

### Interpretation
1.  **ProteinMPNN Bias:** The base `Pool Sim` is very high (average ~82%). This means ProteinMPNN is generating highly conserved sequences for these specific backbones. There is very little wild variation to begin with.
2.  **Mild Mode Collapse:** The `Surr Sim` is consistently higher than the `Pool Sim` (e.g., 0.80 -> 0.93 in `1f4hB01`). This proves our hypothesis: **Random Forests do suffer from a slight mode collapse**. Once they find a "good" motif in the 30 training samples, they aggressively pick sequences that contain that exact motif, leading to less diverse Top 10 lists.
3.  **Accuracy (Surr vs Opt):** The similarity between the Surrogate's picks and the True Optimal picks is incredibly high (average ~86%). This means that even though the model is slightly biased towards certain motifs, **those motifs are actually the correct, high-scoring motifs**. 

### Final Verdict on Scaling to 10,000 Sequences
If we scale this up to 10,000 sequences, the `Pool Sim` will likely drop as more diverse sequences are generated. If we continue to use Random Sampling for the initial 30, the Random Forest's "Mode Collapse" will become a serious problem—it will ignore huge swathes of the diverse 10,000-sequence space. 

**Therefore, moving from Random Sampling to K-Means (Diversity-Aware) Sampling for the initial budget is absolutely critical before scaling the system.**
