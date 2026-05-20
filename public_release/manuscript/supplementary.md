# Supplementary Material for RAPID

## Supplementary Note 1. Status of the CATH Benchmark Refresh

The main manuscript uses the current 23-target CATH artifact benchmark as component-level evidence for AF2-budgeted surrogate-triage design choices rather than as the final corrected-chain benchmark. That benchmark was generated before the final chain-selection fixes and is retained because it provides paired SoluProt and pLDDT records for surrogate and acquisition analyses. A corrected-chain refresh manifest has been generated at `public_release/data/benchmark/results/rapid_target_manifest.csv`. The manifest selects 40 CATH targets for re-screening and 8 targets for the four-arm structural-context ablation. The selected structural-context arms are the original target backbone, target plus BioEmu ensemble, selected RFD3 backbone, and RFD3 plus BioEmu ensemble.

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

At K-means N = 30, Random Forest gives the highest mean pLDDT BO uplift Top-5, while Ridge remains strongest for SoluProt ranking and recall-oriented metrics. The production recommendation is therefore score-specific: Random Forest is the conservative pLDDT acquisition reference, and Ridge is retained when the operator prioritises SoluProt-related ranking or recall. The implemented RAPID default now treats these models as comparator policies: they are evaluated on the initial AF2-labelled bootstrap set, the selected acquisition policy is refit on all bootstrap labels, and only that policy's Top-K is sent to AF2. The aggregate visualization is shown once in the main manuscript as Figure 3; the supplementary material reports the numerical model-level comparison to avoid duplicating the same figure.

| Model | pLDDT BO uplift Top-5 | Delta vs RF | Holm-adjusted p vs RF | Cliff's delta |
|---|---:|---:|---:|---:|
| RF | 0.602 | - | - | - |
| Ridge | 0.583 | -0.019 | 0.71 | +0.04 |
| KNN | 0.572 | -0.030 | 0.51 | +0.05 |
| XGBoost | 0.558 | -0.044 | 0.51 | +0.07 |
| LightGBM | 0.549 | -0.053 | 0.046 | +0.05 |
| GP-RBF | 0.326 | -0.276 | 0.00022 | +0.20 |
| MLP | 0.185 | -0.417 | 1.6e-13 | +0.49 |
| Random | 0.016 | -0.586 | 1.1e-11 | +0.47 |

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

K-means training selection does not by itself remove acquisition bias. In the current artifact benchmark, RF-selected Top-K sets are more internally similar than the true Top-K sets, even when the bootstrap training set is selected by K-means. This means diversity control belongs at acquisition time if sequence diversity is an explicit design objective.

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

Two representative historical in-silico runs verify the implemented computational surrogate path but are not treated as a paired biological benchmark. They used AF2/pLDDT as a computational label source and therefore support the software and budget path, not experimental enrichment. The current paper-run script for claim 2 is `scripts/paper_runs/03_launch_surrogate_triage_budget.py`, which runs the standard pipeline with `evolution_mode=False`, `surrogate_triage_enabled=True`, `surrogate_triage_scope="pooled_tiers"`, RFD3/BioEmu/Relax disabled, and the manuscript operating point of 3,333 generated candidates per 30/50/70% conservation tier, `N_train = 30`, and `Top-K = 20`. In the current implementation, `surrogate_triage_model="auto"` compares configured policies by internal CV on the bootstrap labels and records the selected policy under `surrogate_triage/model_selection.json`; per-tier AF2 score files point back to the same pooled selection artifact. The ESM-2 embedding stage can be delegated to a configured GPU worker through the `esm_embedding` model provider; if no provider is configured, RAPID falls back to the local ESM path and then to deterministic sequence-composition features unless strict ESM mode is requested. The live paper run uses the RunPod ColabFold backend by default so that job identifiers are recorded during AF2 evaluation.

| Target | Run ID | SoluProt-gated candidates | AF2 records | AF2 reduction vs folding all gated candidates | Top-K setting | Best phase | Best SoluProt | Best pLDDT | Best relax score |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| 3RGK | `pys74631_kribb.re.kr_ev_3rgk` | 8,000 | 94 | 98.8% | 20 | R1 train | 0.794 | 97.05 | -3.13 |
| 1LVM | `admin_20260430_064926_afb67369` | 8,000 | 49 | 99.4% | 5 | R3 top-k | 0.734 | 89.52 | -3.15 |

The Top-K default of 20 is an operating budget rather than a fitted hyperparameter. It pairs with the N = 30 bootstrap setting to give 50 AF2 calls per pooled target decision point when the SoluProt-passing pool exceeds the budget. N = 30 is supported by the sample-size ablation, where additional labels beyond 30 provide diminishing returns in the current artifact benchmark; Top-K = 20 keeps enough candidates for manual review while making the AF2/ColabFold cost visible before a run is launched. Model-comparison artifacts are written to `surrogate_triage/cv_metrics.csv`, `model_comparison.svg`, `model_predictions.csv`, `feature_importance.csv`, `acquired_topk.csv`, and `models/*.pkl`, allowing the analysis tab or exported run package to audit why a policy was selected without repeating AF2 calls.

## Supplementary Note 9. Pooled Surrogate Scaling as a Guardrail Analysis

The completed CATH archive was also used to test whether accumulated surrogate labels already justify replacing RAPID's per-target surrogate with a pooled model. This analysis is framed as a guardrail for the production default, not as evidence that label accumulation is uninformative. RAPID currently uses lightweight per-run calibration because each target, backbone context, and conservation tier can change the sequence-quality relationship seen by the surrogate. If a pooled model were already stable under these conditions, it would support replacing per-run Auto-CV with a transferable surrogate. If not, the result supports the current decision to keep the production path adaptive and run-specific while continuing to store labels for future modelling.

This retrospective analysis parsed 4,392 AF2-labelled designs from the completed CATH outputs. After excluding target-tier units with fewer than 35 positive pLDDT labels, 107 target-tier units from 38 targets remained evaluable. For each target-tier unit, 30 designs were used as the target calibration set and the remaining designs were held out. Candidate features used the same ESM-2 8M mean embedding family used by RAPID surrogate triage, concatenated with sequence-composition and ProteinMPNN metadata features. Labels were centered within each target-tier training set before fitting a ridge residual surrogate, so pooled data had to improve within-target ranking rather than merely learn target-level pLDDT offsets.

The result did not support a monotonic pooled-model improvement. Target-only calibration gave a mean held-out top-3 regret of 0.351 pLDDT. Adding labels from 10 external pooled targets reduced the mean regret to 0.320 pLDDT, but this improvement was not stable as the pool increased: the mean regret was 0.347 with 20 pooled targets and 0.357 with 30 pooled targets. Mean MAE also did not improve over the target-only baseline. The paired win rate for pooled-plus-target calibration was approximately 35% across pool sizes. RAPID therefore stores pooled surrogate labels and fitted-model artifacts for future cross-target modelling, but the present manuscript keeps the production default as target-specific calibration with per-run Auto-CV rather than claiming that a pooled surrogate has already improved generalization. In practical terms, the analysis supports a staged learning strategy: current RAPID runs perform local surrogate orchestration; subsequent campaigns should accumulate AF2 labels, assay labels, paired rankings, target metadata, and structural-context annotations as a preference dataset; only after sufficient labelled coverage should a target-conditioned preference model be evaluated as a transferable predictor.

![Pooled surrogate scaling](figures/benchmark/fig9_pooled_surrogate_scaling_esm.png)

*Supplementary Figure S8. Retrospective pooled-surrogate scaling from completed CATH artifacts. Lower values are better for both held-out MAE and top-3 regret. The ESM-plus-composition ridge residual model did not show a monotonic benefit from adding more pooled targets, supporting the decision to keep per-run adaptive calibration as the production default while treating accumulated labels as a future preference-modelling substrate.*

| Training source | Pooled targets | Evaluable units | Mean MAE | Mean Top-3 regret | Median Spearman |
|---|---:|---:|---:|---:|---:|
| Target calibration only | 0 | 107 | 0.397 | 0.351 | 0.164 |
| Pooled prior + target calibration | 10 | 107 | 0.407 | 0.320 | 0.139 |
| Pooled prior + target calibration | 20 | 107 | 0.412 | 0.347 | 0.067 |
| Pooled prior + target calibration | 30 | 107 | 0.408 | 0.357 | 0.139 |

*Supplementary Table S8. Pooled surrogate scaling summary. The non-monotonic regret and unchanged or worse MAE indicate that the current completed CATH artifact set is useful for testing pooled-model infrastructure and label accumulation, but not yet sufficient to support a pooled-surrogate performance claim.*

## Supplementary Note 10. Structural-Context Ablation

The corrected-chain structural-context ablation compares the original target backbone, BioEmu conformational sampling, one selected RFD3 backbone, and RFD3+BioEmu across eight selected CATH targets. Because ProteinMPNN is conditioned on the supplied backbone, these arms test whether changing structural context perturbs the accessible sequence neighbourhood under matched masking and AF2 budgets. The single-backbone and RFD3 arms are evaluable for all eight targets. BioEmu-containing arms are evaluable for the four targets that passed the fixed 2.0 Å target-RMSD gate. The figure is shown once in the main manuscript as Figure 5; the supplementary material retains the numerical summary and BioEmu QC context rather than repeating the same image.

| Arm | Evaluable targets | Designs per target | AF2 records per target | Top-5 pLDDT | Top-5 SoluProt | Paired Top-5 pLDDT delta vs single |
|---|---:|---:|---:|---:|---:|---:|
| Single target backbone | 8 | 120 | 30 | 92.58 | 0.718 | reference |
| Target + BioEmu ensemble | 4 | 120 | 30 | 96.28 | 0.788 | -0.14 |
| RFD3 selected backbone | 8 | 120 | 30 | 92.53 | 0.690 | -0.05 |
| RFD3 + BioEmu ensemble | 4 | 120 | 30 | 95.44 | 0.734 | -0.98 |

## Supplementary Note 11. BioEmu Target-RMSD Gate QC

BioEmu-containing structural-context arms were required to satisfy the same 2.0 Å target-RMSD gate used in the primary four-arm refresh. This gate is part of the artifact contract: a BioEmu arm is quantitatively evaluable only when the requested near-target conformers are recovered. Initial BioEmu runs for four targets did not recover three accepted conformers within the 10-attempt budget. These cases are therefore treated as not evaluable for BioEmu-based score comparison, rather than as zero-valued design outcomes. A sensitivity rerun increases the BioEmu sampling and maximum-attempt budgets to 30 while preserving the 2.0 Å acceptance gate.

| Target | BioEmu accepted/attempted | BioEmu min RMSD (Å) | RFD3+BioEmu accepted/attempted | RFD3+BioEmu min RMSD (Å) | Primary handling |
|---|---:|---:|---:|---:|---|
| 1h6wA03 | 0/10 | 22.664 | 0/10 | 22.664 | Not evaluable |
| 2auaB01 | 0/10 | 8.051 | 0/10 | 8.051 | Not evaluable |
| 3jvoG00 | 0/10 | 2.887 | 0/10 | 3.219 | Not evaluable |
| 3twkA01 | 0/10 | 4.976 | 0/10 | 4.976 | Not evaluable |

*Supplementary Table S9. BioEmu target-RMSD gate failures in the initial four-arm structural-context refresh. The table reports the initial 10-attempt BioEmu runs only. The sensitivity rerun changes the sampling budget but keeps the acceptance gate fixed, avoiding post-hoc relaxation of the structural-quality criterion.*

## Supplementary Note 12. Execution Environment and RunPod Images

The public release records Docker image tags for the RunPod-backed model stages, while endpoint IDs and API keys are excluded from the repository. Endpoint IDs are deployment-specific secrets and should be supplied through `.env` or server environment variables. For manuscript reproduction, image tags should be pinned for each benchmark run, and any image tagged as `latest` should be accompanied by a digest or release note before final archival.

| Pipeline stage | Environment variable | Docker image |
|---|---|---|
| MMseqs2 MSA/search | `MMSEQS_ENDPOINT_ID` | `mimikyou0607/mmseqs-runpod:latest` |
| ProteinMPNN sequence generation | `PROTEINMPNN_ENDPOINT_ID` | `mimikyou0607/proteinmpnn-runpod:latest` |
| ColabFold/AF2 structure prediction | `COLABFOLD_ENDPOINT_ID` or `AF2_ENDPOINT_ID` | `mimikyou0607/colabfold-runpod:20260304_4` |
| RFdiffusion3 backbone generation | `RFD3_ENDPOINT_ID` | `mimikyou0607/rfd3-runpod:260408-3` |
| BioEmu ensemble sampling | `BIOEMU_ENDPOINT_ID` | `mimikyou0607/bioemu-runpod:latest` |
| Rosetta Relax post-processing | `RUNPOD_RELAX_ENDPOINT_ID` | `mimikyou0607/relax_runpod:260428_1` |
| ESM embedding | `ESM_EMBEDDING_ENDPOINT_ID` | user-built from `workers/esm_embedding` |

## Supplementary Note 13. Software Interface and Deployment Scope

RAPID is distributed with a static browser interface served by the backend API. The interface is not treated as a separate scientific contribution in the main manuscript; its role is to make the run-scoped artifact contract accessible during local or server-based operation. Basic mode exposes the default solubility-aware multiple-mutant redesign workflow with a compact set of output-size and threshold controls. Advanced mode exposes start and stop points, optional RFD3 and BioEmu stages, masking controls, AF2/ColabFold budget parameters, provider choices, surrogate-triage mode, Auto-CV acquisition-policy selection, comparator-model settings, and experimental-feedback evolution records. These controls map to the same request fields stored in each run directory, so analyses can be reproduced from the resulting artifacts without depending on the browser state.

The intended deployment model is local or server-side execution by the user, including GPU-backed RunPod endpoints configured through environment variables. Runtime `.env` files, endpoint identifiers, API keys, and raw logs are excluded from the public release. The browser interface therefore documents and exposes the reproducibility contract, but the manuscript's empirical claims are based on stored artifacts and benchmark scripts rather than on user-interface behaviour.
