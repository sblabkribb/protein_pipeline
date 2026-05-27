# Supplementary Material for RAPID

## Supplementary Note 1. Status of the CATH Benchmark Refresh

The main manuscript uses the current 23-target CATH artifact benchmark as component-level evidence for structure-prediction-budgeted surrogate-triage design choices rather than as the final corrected-chain benchmark. That benchmark was generated before the final chain-selection fixes and is retained because it provides paired SoluProt and pLDDT records for surrogate and acquisition analyses. A corrected-chain refresh manifest has been generated at `public_release/data/benchmark/results/rapid_target_manifest.csv`. The manifest selects 40 CATH targets for re-screening and 8 targets for the four-arm structural-context ablation. The selected structural-context arms are the original target backbone, target plus BioEmu ensemble, selected RFD3 backbone, and RFD3 plus BioEmu ensemble.

## Supplementary Note 2. Current CATH Artifact Corpus

The pre-refresh CATH archive contains 73 completed CATH run directories. Twenty-three runs passed the QC rule requiring all three conservation tiers, at least 100 valid non-fallback amino-acid design sequences, and at least 100 positive pLDDT records. The included subset contains 2,737 paired SoluProt/pLDDT design rows. Excluded records are treated as input-compatibility or fallback-design artifacts under the previous pipeline contract, not as valid low-quality biological designs.

![QC-filtered CATH artifact corpus](figures/benchmark/fig11_cath_curated_expansion.png)

*Supplementary Figure S1. Target-level summary of the pre-refresh CATH artifact corpus. The figure shows target-level pLDDT and SoluProt heterogeneity after excluding fallback or input-incompatible outputs.*

| Metric | Value |
|---|---:|
| Completed CATH runs parsed | 73 |
| QC-included targets | 23 |
| QC-excluded runs | 50 |
| Valid paired design rows | 2,737 |
| Positive pLDDT records | 2,737 |
| SoluProt records | 2,737 |
| Mean pLDDT | 91.91 |
| Maximum pLDDT | 97.89 |
| Mean SoluProt | 0.615 |
| Maximum SoluProt | 0.971 |

## Supplementary Note 3. Training-Set Selection

The Random Forest selection-size ablation shows that K-means is most useful when AF2 labels are scarce. The K-means advantage is largest at N = 5 and N = 10 and becomes small near the production default N = 30. This supports using K-means as a cold-start safeguard rather than as a claim that K-means always dominates random selection at larger training budgets.

![Selection-size ablation](figures/benchmark/fig3_selection_n_curves.png)

*Supplementary Figure S2. Random Forest BO uplift Top-5 as a function of the number of AF2-labelled training examples. K-means selection provides its largest benefit in the low-label regime and converges with random selection near N = 30.*

![Selection by surrogate family](figures/benchmark/fig4_selection_comparison.png)

*Supplementary Figure S3. Effect of K-means versus random training-set selection at fixed N = 30 across surrogate families. The smaller differences at N = 30 support using K-means primarily as a bootstrap safeguard rather than as a universal advantage at all training sizes.*

| N | Random RF pLDDT BO uplift Top-5 | K-means RF pLDDT BO uplift Top-5 | Delta |
|---:|---:|---:|---:|
| 5 | 0.254 | 0.350 | +0.097 (+38%) |
| 10 | 0.327 | 0.390 | +0.063 (+19%) |
| 20 | 0.418 | 0.468 | +0.050 (+12%) |
| 30 | 0.459 | 0.456 | -0.003 (-1%) |
| 50 | 0.459 | 0.484 | +0.025 (+5%) |
| 80 | 0.454 | 0.490 | +0.036 (+8%) |

## Supplementary Note 4. Surrogate Model Comparison

The surrogate-family benchmark was run on the fully labelled artifact pool used to choose the production operating point, rather than on the later strict 9,999-candidate triage runs. In this retrospective benchmark, each target-tier unit contained approximately 120 ProteinMPNN designs with SoluProt scores and AF2/ColabFold pLDDT records where available. Thirty candidates were selected by K-means as the bootstrap-labelled set, and the remaining labelled candidates were held out to evaluate whether each model could recover high-scoring designs from the same local candidate pool. This analysis is therefore a model-family benchmark for acquisition behaviour; it is separate from the main-text surrogate-triage budget result, where only 30 bootstrap candidates and 20 acquired candidates are folded for each target.

![Surrogate model comparison](figures/benchmark/fig5_model_comparison.png)

*Supplementary Figure S4. Retrospective surrogate-family comparison at K-means N = 30. The benchmark uses fully labelled target-tier candidate pools to compare model ranking and acquisition behaviour for pLDDT and SoluProt objectives. It supports a configurable acquisition layer rather than a universal single-model rule.*

At K-means N = 30, Random Forest gives the highest mean pLDDT BO uplift Top-5 among the individual models shown here, whereas Ridge is strongest for SoluProt ranking and recall-oriented metrics. The production recommendation is therefore score-specific: Random Forest is a conservative pLDDT acquisition reference, and Ridge is retained when the operator prioritises SoluProt-related ranking or recall. The implemented RAPID default treats these models as comparator policies: they are evaluated on the initial AF2-labelled bootstrap set, the selected acquisition policy is refit on all bootstrap labels, and only that policy's Top-K is sent to AF2. The main text summarizes the run-level budget and selected-candidate outcomes in Figure 2; the table below reports the numerical model-level comparison.

| Model | pLDDT Spearman rho | pLDDT Top-5 recall | pLDDT BO uplift Top-5 | SoluProt Spearman rho | SoluProt Top-5 recall | SoluProt BO uplift Top-5 |
|---|---:|---:|---:|---:|---:|---:|
| RF | 0.409 | 0.150 | 0.602 | 0.718 | 0.400 | 0.034 |
| Ridge | 0.371 | 0.155 | 0.583 | 0.904 | 0.656 | 0.042 |
| GP-RBF | 0.438 | 0.092 | 0.326 | 0.781 | 0.278 | 0.020 |
| XGBoost | 0.353 | 0.141 | 0.558 | 0.624 | 0.339 | 0.031 |
| LightGBM | 0.358 | 0.137 | 0.549 | 0.648 | 0.323 | 0.030 |
| KNN | 0.383 | 0.132 | 0.572 | 0.597 | 0.311 | 0.029 |
| MLP | 0.089 | 0.057 | 0.185 | 0.127 | 0.101 | 0.008 |
| Random | -0.005 | 0.052 | 0.016 | -0.005 | 0.061 | 0.000 |

## Supplementary Note 5. Sample-Size Operating Point

The N-ablation places N = 30 on a cost-efficient plateau. Increasing RF training labels from 30 to 80 requires approximately 2.7 times more AF2-labelled training examples but gives a modest additional pLDDT BO-uplift gain. The N = 30 default is therefore a conservative operating point for the bootstrap round.

![Sample-size ablation](figures/benchmark/fig8_sample_size.png)

*Supplementary Figure S5. Sample-size ablation for production-supported surrogate families. The vertical reference at N = 30 marks the operating point used in RAPID. The curves show diminishing returns beyond roughly 20-30 AF2-labelled examples, supporting N = 30 as a conservative default rather than an arbitrary setting.*

| N_train | RF pLDDT BO uplift Top-5 | Percent of N = 80 | RF SoluProt BO uplift Top-5 | Percent of N = 80 |
|---:|---:|---:|---:|---:|
| 5 | 0.350 | 71.4% | 0.0140 | 62.1% |
| 10 | 0.390 | 79.7% | 0.0155 | 69.1% |
| 20 | 0.468 | 95.6% | 0.0199 | 88.5% |
| 30 | 0.456 | 93.1% | 0.0202 | 89.8% |
| 50 | 0.484 | 98.9% | 0.0213 | 94.5% |
| 80 | 0.490 | 100.0% | 0.0225 | 100.0% |

## Supplementary Note 6. Acquisition Bias and Diversity

K-means training selection does not by itself remove acquisition bias. In the current artifact benchmark, RF-selected Top-K sets are more internally similar than the true Top-K sets, even when the bootstrap training set is selected by K-means. At N = 30, the K-means-trained RF Top-5 set had an internal identity of 0.891, compared with 0.866 for the true Top-5 set, and the corresponding Top-10 values were 0.887 and 0.864. This means diversity control belongs at acquisition time if sequence diversity is an explicit design objective.

Future diversity-aware acquisition policies, such as max-min filtering or cluster-balanced Top-K selection over ESM-2 embeddings, should be evaluated as acquisition-stage changes rather than as current performance claims [26].

![Acquisition-bias analysis](figures/benchmark/fig6_bias_analysis.png)

*Supplementary Figure S6. Acquisition-bias analysis for RF at N = 30. K-means reduces identity to the best training sequence relative to random bootstrap selection, but surrogate-selected Top-K sets remain more internally similar than the true Top-K sets.*

![Per-target surrogate heatmap](figures/benchmark/fig7_per_target_heatmap.png)

*Supplementary Figure S7. Per-target BO uplift difference relative to Random Forest. The heatmap shows target-level winner switching that is obscured by aggregate means, supporting a configurable surrogate layer rather than a hard-coded single-model policy.*

| Metric | Random training | K-means training | True optimal | Random Top-K |
|---|---:|---:|---:|---:|
| Top-5 overfit identity | 0.872 | 0.862 | 0.860 | - |
| Top-5 internal identity | 0.898 | 0.891 | 0.866 | 0.828 |
| Top-5 mean pLDDT | 92.51 | 92.51 | 93.09 | 91.95 |
| Top-10 overfit identity | 0.870 | 0.859 | 0.854 | - |
| Top-10 internal identity | 0.892 | 0.887 | 0.864 | 0.831 |
| Top-10 mean pLDDT | 92.47 | 92.45 | 92.89 | 91.91 |

## Supplementary Note 7. Rank-Mean Ensemble

A rank-mean ensemble over RF, Ridge, LightGBM, and XGBoost gives the highest mean pLDDT BO uplift in the current artifact benchmark, but the gain over RF is small and does not remove acquisition diversity collapse. Rank-mean is therefore retained as an optional robustness layer rather than as a universal default. In RAPID, Auto-CV compares the configured individual models by default; the rank-mean ensemble is added only when the operator explicitly selects ensemble members or forces the ensemble policy. RAPID distinguishes comparator models from the acquisition policy: comparator predictions, CV metrics, model-selection summaries, feature-importance or coefficient tables, and fitted model files are exported for audit, but only one selected policy contributes the final Top-K AF2 acquisitions. The number of AF2/ColabFold calls therefore remains `N_train + Top-K` unless the operator explicitly increases the validation budget.

| Combination rule | pLDDT BO uplift Top-5 | SoluProt BO uplift Top-5 | Top-10 internal identity |
|---|---:|---:|---:|
| rank-mean ensemble | 0.622 | 0.0370 | 0.883 |
| score-mean ensemble | 0.611 | 0.0377 | 0.881 |
| RF | 0.602 | 0.0335 | 0.887 |
| top-5 vote ensemble | 0.600 | 0.0363 | 0.880 |
| Ridge | 0.583 | 0.0418 | 0.865 |
| XGBoost | 0.558 | 0.0308 | 0.873 |
| LightGBM | 0.549 | 0.0297 | 0.877 |

## Supplementary Note 8. Representative Surrogate-Budget Runs

The current strict paper run verifies the implemented surrogate-triage path under the manuscript operating point. The runner is `scripts/paper_runs/03_launch_surrogate_triage_budget.py`, which executes the standard pipeline with `evolution_mode=False`, `surrogate_triage_enabled=True`, `surrogate_triage_scope="pooled_tiers"`, RFD3/BioEmu/Relax disabled, and 3,333 generated ProteinMPNN candidates per 30/50/70% conservation tier. For each target, RAPID spends `N_train = 30` AF2/ColabFold calls on K-means bootstrap labels and `Top-K = 20` calls on surrogate-selected acquisitions. In the current implementation, `surrogate_triage_model="auto"` compares configured policies by internal CV on the bootstrap labels and records the selected policy under `surrogate_triage/model_selection.json`; per-tier AF2 score files point back to the same pooled selection artifact. The strict paper run used the GPU ESM embedding provider and disabled fallback sequence recovery, so the reported candidates were produced by ProteinMPNN rather than by deterministic recovery logic.

The release provides several CSV views of these runs. `data/benchmark/results/surrogate_triage_budget_summary.csv` is tier-level and therefore repeats the pooled pre-triage candidate count once for each conservation-tier output. `data/benchmark/results/surrogate_triage_budget_run_summary.csv` is target-level and counts the pooled candidate set once per run; this is the direct data source for the 49,946-candidate, 250-AF2-record aggregate reported in the main text. `surrogate_triage_cv_metrics.csv` records the internal policy comparison, `surrogate_triage_acquired_topk.csv` records the selected candidates and their observed AF2/SoluProt values, and `surrogate_triage_wt_metrics.csv` records one WT reference baseline per target. WT reference calls are not included in the 250 candidate-record budget.

| Target | Run ID | Candidates entering triage | AF2 records | Reduction vs folding all candidates | Selected policy | Bootstrap labels | Top-K acquisitions |
|---|---|---:|---:|---:|---|---:|---:|
| 1a6jA00 | `paper_surrogate_pooled9999_strict_20260520_cath_train_1a6jA00` | 9,954 | 50 | 99.5% | Ridge | 30 | 20 |
| 1a8rG01 | `paper_surrogate_pooled9999_strict_20260520_cath_train_1a8rG01` | 9,999 | 50 | 99.5% | Ridge | 30 | 20 |
| 1a19A00 | `paper_surrogate_pooled9999_strict_20260520_cath_val_1a19A00` | 9,999 | 50 | 99.5% | RF | 30 | 20 |
| 1advA02 | `paper_surrogate_pooled9999_strict_20260520_cath_val_1advA02` | 9,999 | 50 | 99.5% | RF | 30 | 20 |
| 1h6wA03 | `paper_surrogate_pooled9999_strict_20260520_cath_val_1h6wA03` | 9,995 | 50 | 99.5% | Ridge | 30 | 20 |
| Aggregate | - | 49,946 | 250 | 99.5% | RF/Ridge | 150 | 100 |

The WT reference values used in Figure 2D are shown below. These baselines were added after the strict candidate-selection run as reference artifacts only. They were not used to train the surrogate, select the Top-K candidates, or calculate the candidate-evaluation reduction.

| Target | WT pLDDT | WT SoluProt | Selected Top-K contains candidate above WT on both proxies |
|---|---:|---:|---|
| 1a6jA00 | 94.46 | 0.642 | yes |
| 1a8rG01 | 96.37 | 0.640 | yes |
| 1a19A00 | 97.67 | 0.629 | yes |
| 1advA02 | 90.37 | 0.529 | yes |
| 1h6wA03 | 81.54 | 0.593 | yes |

Earlier 3RGK and 1LVM in-silico traces are historical implementation traces only; they used different candidate counts and Top-K settings and are not part of the current operating evidence. The Top-K default of 20 is an operating budget rather than a fitted hyperparameter. Together with the N = 30 bootstrap setting, it gives 50 AF2 calls per pooled target decision point when the SoluProt-passing pool exceeds the budget.

## Supplementary Note 9. Pooled Surrogate Scaling as a Guardrail Analysis

The completed CATH archive was also used to test whether accumulated surrogate labels already justify replacing RAPID's per-target surrogate with a pooled model. This analysis is framed as a guardrail for the production default, not as evidence that label accumulation is uninformative. RAPID currently uses lightweight per-run calibration because each target, backbone context, and conservation tier can change the sequence-quality relationship seen by the surrogate. If a pooled model were already stable under these conditions, it would support replacing per-run Auto-CV with a transferable surrogate. If not, the result supports the current decision to keep the production path adaptive and run-specific while continuing to store labels for future modelling.

Several factors could explain the absence of monotonic scaling, including sequence length, fold class, MSA depth, conservation pattern, and backbone context. The present analysis did not decompose these factors individually, but it shows why a future transferable model should be target-conditioned rather than simply larger.

This retrospective analysis parsed 4,392 AF2-labelled designs from the completed CATH outputs. After excluding target-tier units with fewer than 35 positive pLDDT labels, 107 target-tier units from 38 targets remained evaluable. For each target-tier unit, 30 designs were used as the target calibration set and the remaining designs were held out. Candidate features used the same ESM-2 8M mean embedding family used by RAPID surrogate triage, concatenated with sequence-composition and ProteinMPNN metadata features. Labels were centered within each target-tier training set before fitting a ridge residual surrogate, so pooled data had to improve within-target ranking rather than merely learn target-level pLDDT offsets. However, centering the labels does not remove all heterogeneity: unnormalized feature distributions across different sequence lengths and target families can still introduce embedding-space shifts, reinforcing that a future transferable model should be explicitly target-conditioned rather than simply larger.

The result did not support a monotonic pooled-model improvement. Target-only calibration gave a mean held-out top-3 regret of 0.351 pLDDT. Adding labels from 10 external pooled targets reduced the mean regret to 0.320 pLDDT, but this improvement was not stable as the pool increased: the mean regret was 0.347 with 20 pooled targets and 0.357 with 30 pooled targets. Mean MAE also did not improve over the target-only baseline. The paired win rate for pooled-plus-target calibration was approximately 35% across pool sizes. RAPID therefore stores pooled surrogate labels and fitted-model artifacts for future cross-target modelling, but the present manuscript keeps the production default as target-specific calibration with per-run Auto-CV rather than claiming that a pooled surrogate has already improved generalization. In practical terms, the analysis supports a staged learning strategy: current RAPID runs perform local surrogate orchestration; subsequent campaigns should accumulate AF2 labels, assay labels, paired rankings, target metadata, and structural-context annotations as a preference dataset; only after sufficient labelled coverage should a target-conditioned preference model be evaluated as a transferable predictor.

![Pooled surrogate scaling](figures/benchmark/fig9_pooled_surrogate_scaling_esm.png)

*Supplementary Figure S8. Retrospective pooled-surrogate scaling from completed CATH artifacts. Lower values are better for both held-out MAE and top-3 regret. The ESM-plus-composition ridge residual model did not show a monotonic benefit from adding more pooled targets, supporting the decision to keep per-run adaptive calibration as the production default while treating accumulated labels as a future preference-modelling substrate.*

| Training source | Pooled targets | Evaluable units | Mean MAE | Mean Top-3 regret | Median Spearman |
|---|---:|---:|---:|---:|---:|
| Target calibration only | 0 | 107 | 0.397 | 0.351 | 0.164 |
| Pooled prior + target calibration | 10 | 107 | 0.407 | 0.320 | 0.139 |
| Pooled prior + target calibration | 20 | 107 | 0.412 | 0.347 | 0.067 |
| Pooled prior + target calibration | 30 | 107 | 0.408 | 0.357 | 0.139 |

*Pooled surrogate scaling summary. The non-monotonic regret and unchanged or worse MAE indicate that the current completed CATH artifact set is useful for testing pooled-model infrastructure and label accumulation, but not yet sufficient to support a pooled-surrogate performance claim.*

## Supplementary Note 10. Experimental-Feedback Evolution Schema

The experimental-feedback evolution mode is included to define the data boundary between computational shortlisting and future assay-guided redesign. It is not used as evidence of wet-lab enrichment in the present manuscript. RAPID writes an `experiment_request.csv` after candidate generation and triage, and assay outcomes can later be recorded with stable candidate identifiers, metric names, values, units, metric direction, replicate identifiers, assay conditions, and optional quality flags.

| Field group | Required fields | Purpose |
|---|---|---|
| Candidate identity | `candidate_id`, `sequence_id` | Links a measured result to the generated sequence and run artifact. |
| Assay metric | `metric_name`, `metric_value`, `metric_unit`, `metric_direction` | Defines the objective that the next-round surrogate should learn. |
| Measurement context | `replicate_id`, `condition`, optional `quality_flag` | Preserves replicate, condition, and failure/dropout handling for audit. |

When labels for the requested objective are present, RAPID trains a local surrogate on the labelled records and writes `next_candidates.csv` for the next design-test-learn cycle. This output is a recommendation table, not a biological validation result.

## Supplementary Note 11. Structural-Context Ablation

The corrected-chain structural-context ablation compares the original target backbone, BioEmu conformational sampling, one selected RFD3 backbone, and RFD3+BioEmu across 18 selected CATH targets. Because ProteinMPNN is conditioned on the supplied backbone, these arms test whether changing structural context perturbs the accessible sequence neighbourhood under matched masking and AF2 budgets. The single-backbone and RFD3 arms are evaluable for all 18 targets. BioEmu is evaluable for nine targets and RFD3+BioEmu for eight targets — those that passed the fixed 2.0 Å target-RMSD gate. The main text summarizes this claim in Figure 3 as a distribution-spread and diversity analysis rather than as an aggregate-mean or upper-tail model ranking.

The paired view supports this interpretation. RFD3 increased pLDDT range relative to the single-backbone arm in 14 of 18 targets (Wilcoxon p = 0.002), increased SoluProt range in 9 of 18 targets, and increased sequence diversity in 9 of 18 targets (Wilcoxon p = 0.010). BioEmu increased pLDDT range and mean pairwise sequence diversity in all nine evaluable paired targets (Wilcoxon p = 0.004 for both) and increased SoluProt range in 8 of 9 targets (Wilcoxon p = 0.008). RFD3+BioEmu increased pLDDT range and sequence diversity in all eight evaluable paired targets (Wilcoxon p = 0.008 for both), and increased SoluProt range in 6 of 8 targets. These data support structural-context allocation as a way to alter candidate-pool spread and diversity, not as evidence that any structural-context module is universally superior.

The table below retains the numerical summary and BioEmu QC context.

| Arm | Evaluable targets | Mean pLDDT range | Mean SoluProt range | Mean pairwise diversity |
|---|---:|---:|---:|---:|
| Single target backbone | 18 | 2.99 | 0.146 | 0.147 |
| Target + BioEmu ensemble | 9 | 3.82 | 0.226 | 0.294 |
| RFD3 selected backbone | 18 | 4.66 | 0.163 | 0.167 |
| RFD3 + BioEmu ensemble | 8 | 3.80 | 0.256 | 0.310 |

## Supplementary Note 12. BioEmu Target-RMSD Gate QC

BioEmu-containing structural-context arms were required to satisfy the same 2.0 Å target-RMSD gate used in the primary four-arm refresh. This gate is part of the artifact contract: a BioEmu arm is quantitatively evaluable only when the requested near-target conformers are recovered. Across the expanded 18-target ablation, eight targets did not recover any conformer under the 2.0 Å cutoff within the 10-attempt BioEmu budget, and one additional target (1iieA00) was non-evaluable due to a separate BioEmu backend failure rather than the RMSD gate. RFD3+BioEmu was additionally non-evaluable for 1a6jA00, where the RFD3-conditioned BioEmu samples drifted further from the target backbone. These cases are therefore treated as not evaluable for BioEmu-based score comparison, rather than as zero-valued design outcomes. A sensitivity rerun increases the BioEmu sampling and maximum-attempt budgets to 30 while preserving the 2.0 Å acceptance gate.

| Target | BioEmu accepted/attempted | BioEmu min RMSD (Å) | RFD3+BioEmu accepted/attempted | RFD3+BioEmu min RMSD (Å) | Primary handling |
|---|---:|---:|---:|---:|---|
| 1a6jA00 | 3/6 | 1.615 | 0/10 | 12.241 | RFD3+BioEmu not evaluable |
| 1agrE02 | 0/10 | 4.229 | 0/10 | 4.229 | Not evaluable |
| 1b12B02 | 0/10 | 2.993 | 0/10 | 2.993 | Not evaluable |
| 1h6wA03 | 0/10 | 22.664 | 0/10 | 22.664 | Not evaluable |
| 1hufA00 | 0/10 | 3.478 | 0/10 | 3.478 | Not evaluable |
| 1iieA00 | backend failure | n/a | backend failure | n/a | Not evaluable (BioEmu endpoint error) |
| 1j5uA01 | 0/10 | 5.393 | 0/10 | 5.393 | Not evaluable |
| 2auaB01 | 0/10 | 8.051 | 0/10 | 8.051 | Not evaluable |
| 3jvoG00 | 0/10 | 2.887 | 0/10 | 3.219 | Not evaluable |
| 3twkA01 | 0/10 | 4.976 | 0/10 | 4.976 | Not evaluable |

*BioEmu target-RMSD gate outcomes for the non-evaluable arms in the expanded 18-target structural-context refresh. The 1a6jA00 row reports BioEmu alone as evaluable and only the RFD3-conditioned variant as failed; 1iieA00 was excluded from BioEmu-based scoring because of a separate RunPod backend error rather than a structural quality decision. The table reports the initial 10-attempt BioEmu runs only. The sensitivity rerun changes the sampling budget but keeps the acceptance gate fixed, avoiding post-hoc relaxation of the structural-quality criterion.*
