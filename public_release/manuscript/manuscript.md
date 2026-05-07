# `protein_pipeline`: A Reproducible Solubility-Aware Multiple-Mutant Redesign Pipeline with Active-Learning-Based AF2 Budget Reduction

*Type: Software Paper / Empirical Benchmark Contribution*

## Abstract

Solubility-oriented multiple-mutant redesign increasingly depends on multi-stage workflows that combine homology search, MSA-derived residue constraints, structure-based sequence generation, soluble-expression filtering, structure prediction, and novelty analysis. In practice, these stages are often connected by ad hoc scripts, making runs difficult to reproduce, partially rerun, or update when upstream models change. We present `protein_pipeline`, a stage-aware and artifact-preserving orchestration framework for reproducible solubility-aware protein library design. The system exposes each modelling stage through typed inputs and run-scoped artifacts, enabling safe partial reruns and model replacement without changing downstream analysis.

We use this framework to address the dominant compute bottleneck after SoluProt filtering in ProteinMPNN-driven redesign: repeated AlphaFold2 (AF2) evaluation of candidate sequences. A local active-learning module embeds SoluProt-passing candidates with ESM-2, selects a small diverse AF2-labelled training set using K-means, fits a surrogate model, and sends only the top-ranked candidates to AF2. The statistical benchmark uses a QC-filtered CATH set of 23 targets comprising 2,737 paired SoluProt and AF2/pLDDT records. K-means selection improves cold-start Random Forest BO uplift by 38% over random sampling at N = 5 and converges near random sampling by N = 30. At the N = 30 operating point, Random Forest gives the strongest pLDDT BO uplift, while Ridge is strongest for SoluProt-related ranking metrics.

Beyond surrogate selection, a variance decomposition shows that target identity explains 98.8% of pLDDT variance and 96.8% of SoluProt variance in the benchmark. This shifts the main compute-allocation decision from deeper sequence sampling within a fixed backbone toward early target or backbone triage. A three-target paired backbone-context pilot further shows that RFD3 and RFD3-ensemble inputs produce target-dependent tradeoffs rather than a uniform quality gain. Under a four-round orchestration-level budget model, reuse of the active-learning loop reduces projected AF2 calls from 360 to 110 per target, an approximately 3.3x reduction in AF2 GPU time. Two representative completed runs further verified the multi-round path at production scale, evaluating 94 and 49 AF2 records from 8,000 SoluProt-gated candidates for 3RGK and 1LVM, respectively. Together, these results show that a reproducible, model-replaceable pipeline can serve not only as execution infrastructure for soluble protein-library design but also as an empirical platform for deciding where expensive structure-prediction compute should be spent.

## 1. Introduction

Computational protein design has moved fast in the past three years. ProteinMPNN [1], AlphaFold2 [2], and RFdiffusion established a baseline modular stack, and a next generation of components - LigandMPNN, AlphaFold3, and conformational ensemble models such as BioEmu - is arriving on roughly annual cadence. However, many practical biofoundry campaigns are not unconstrained de novo design problems. They are soluble protein-library redesign problems: starting from a target sequence or scaffold, the operator wants a tractable library of multiple-mutant variants that preserves protected residues, respects sequence/structure constraints, improves soluble-expression likelihood, and remains structurally plausible. Earlier structure- and sequence-based redesign systems such as PROSS targeted bacterial expression and stability [9], and solubility-aware AfDesign showed that solubility can be made an explicit design objective rather than a post hoc concern [10]. `protein_pipeline` is positioned in this redesign setting, not as a universal substitute for specialised binder, enzyme, or fold-generation systems.

Two consequences follow for groups running solubility-aware redesign campaigns at scale. First, analysis code hard-coded to a particular model version goes stale within a year, because each new release ships its own input format, output schema, and evaluation conventions. Second, AF2 or ColabFold structure evaluation [2, 3] is now the dominant GPU cost after inexpensive sequence and solubility filters: a single target can yield thousands of ProteinMPNN variants, and folding every one is rarely justified. The operational question is therefore not only how to generate soluble candidate sequences, but how to decide which candidates deserve expensive structure prediction without collapsing the search around one structural context.

The full redesign stack combines mature but heterogeneous components: sequence search, MSA construction, optional backbone or ensemble generation, inverse folding, soluble-expression filtering, structure prediction, and novelty analysis [1-8]. General workflow systems such as RosettaScripts demonstrated the value of composable modelling protocols for non-expert use and reproducible protocol exchange [11]. In current deep-learning-driven design practice, however, many campaigns still remain organised as scripts, notebooks, and service-specific interfaces. This creates three recurring problems. First, provenance becomes fragile: intermediate artifacts, parameter choices, and filtering decisions are difficult to trace after a run finishes. Second, partial reruns are unsafe: changing a downstream solubility threshold may accidentally trigger upstream recomputation, while changing an upstream input may leave stale downstream artifacts in place. Third, model replacement is costly: a new structure predictor, inverse-folding model, or solubility predictor can require substantial changes to the analysis code, even when the scientific question is unchanged.

These failure modes compound across multi-ablation studies. The value of an orchestration layer is therefore not simply that heterogeneous tools can be launched from one interface, but that otherwise fragmented model outputs are converted into a reusable experimental substrate. In this study, that substrate allowed the selection-method, surrogate-family, rank-mean ensemble, training-set-size, acquisition-bias, and variance analyses to be computed from the same 2,737 stored AF2/SoluProt records without per-ablation re-folding. It also made the AF2 budget explicit enough to compare a 360-call four-round baseline with a 110-call active-learning schedule and to attach representative multi-round executions to the same artifact logic. Thus, the pipeline is evaluated as infrastructure that changes what can be measured, reused, and optimized in solubility-aware redesign campaigns.

Active learning is one practical strategy for reducing the AF2 cost after the fast solubility filter has already narrowed the pool. A cheap surrogate can be trained on a small AF2-labelled subset, rank the remaining SoluProt-passing candidates, and reserve AF2 for the surrogate's top selections. Similar principles underlie recent language-model-guided directed evolution work [12], but several design choices remain unsettled for a modular solubility-oriented redesign pipeline: which surrogate should be used, how the initial labelled set should be selected, how large that labelled set should be, and whether additional sequence sampling within the same target is the best use of compute.

This paper presents `protein_pipeline`, a reproducible orchestration framework for solubility-aware multiple-mutant protein redesign, and uses it to study these compute-allocation questions. The contribution is two-fold. First, we describe a stage-aware pipeline architecture that preserves artifacts under a run identifier, supports controlled partial reruns, exposes a local/static web interface, and keeps model interfaces replaceable across backbone generation, inverse folding, solubility filtering, and structure prediction. Second, we use the pipeline's artifacts to benchmark a local active-learning module and to quantify whether design-quality variance is dominated by target or backbone context rather than by deeper ProteinMPNN sampling within one context. The paper is organised in the conventional order of Methods, Results, Discussion, Limitations, and Conclusion.

## 2. Methods

### 2.1 Pipeline Scope and Evaluation Questions

The method was designed around six requirements that are directly tied to solubility-aware redesign rather than general-purpose protein generation.

1. **Reproducible execution.** Each run should preserve the original request, stage outputs, status history, and summary artifacts under a stable run identifier.
2. **Safe partial reruns.** Users should be able to rerun downstream stages after threshold or selection changes without recomputing upstream artifacts, while upstream changes should invalidate unsafe reuse.
3. **Constrained multiple-mutant library design.** The default workflow should redesign non-protected positions jointly rather than as a single-mutation walk, producing sequence libraries that preserve protected residues, pass an explicit soluble-expression filter, and remain structurally plausible.
4. **Structure-context diversification.** Optional backbone and conformational-ensemble stages should allow the same redesign protocol to be applied across more than one structural context when a campaign requires broader landscape exploration.
5. **Model replacement.** External models should be accessed through typed inputs and run-scoped artifact contracts so that a structure predictor, inverse-folding model, or filtering model can be replaced without rewriting the benchmark code.
6. **Compute-aware evaluation.** Expensive stages, especially AF2, should be invoked only after cheaper signals have filtered or ranked candidates.

The empirical part of the paper asks four questions about the compute-allocation layer.

- **Q1 - Surrogate choice after solubility filtering.** Among common regression and ranking models trained on ESM-2 embeddings, which surrogate best prioritises SoluProt-passing candidates for AF2 evaluation?
- **Q2 - Training-set selection.** Given a fixed AF2 budget for initial labelling, does K-means diversity sampling improve surrogate quality over random sampling, especially at small N?
- **Q3 - Variance source.** Across CATH test topologies, how much of the observed pLDDT and SoluProt variance is attributable to target identity rather than ProteinMPNN sampling noise?
- **Q4 - Model replacement.** Can the same benchmark protocol be rerun when the structure predictor or inverse-folding model changes?

### 2.2 Solubility-Aware Stage Architecture

`protein_pipeline` organises a solubility-aware redesign campaign as a stage-aware run rather than as a collection of disconnected jobs. The canonical stage order is:

`msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty`

This core ordering is dependency-driven rather than cost-driven. MSA construction must run first because per-position conservation, and the 30%/50%/70% identity tiers used to bound how much sequence latitude each ProteinMPNN run is given, are computed from the alignment. These tiers do not define a single-substitution trajectory. They define progressively constrained fixed-position sets; ProteinMPNN then redesigns the remaining positions jointly, so each pass produces a multiple-mutant library under the selected conservation constraint. Before design, an internal mask-consensus routine can aggregate programmatic signals - MSA conservation, ligand proximity, MSA quality, and query-PDB identity - into per-tier consensus positions. By default this output is written as an advisory artifact; when `mask_consensus_apply=true`, the consensus positions are used by the design stage. Manual residue selections from the user interface enter through a separate `fixed_positions_extra` channel and are unioned into the final fixed-position set used for ProteinMPNN (Section 2.3).

The implementation follows a Model Context Protocol-style separation between tool interface and model backend [13], so individual stages - the masking source, the inverse-folding model, the soluble-expression filter, the structure predictor, the relax backend - can be enabled, disabled, or replaced from the request without rewriting the analysis code. RFdiffusion and BioEmu occupy optional hooks after MSA and provide backbone-topology and conformational diversification [5, 6]; they generate the structures on which ProteinMPNN operates and can be enabled or disabled independently of the masking flow. ProteinMPNN then generates candidate sequences once per conservation tier under the active `fixed_positions` constraint [1]. SoluProt is the default fast soluble-expression gate before AF2 [7]; AF2 or ColabFold supplies pLDDT-based structural confidence on the surviving sequences [2, 3]. Novelty analysis then compares the surviving designs against a reference database with MMseqs2 [8]. An optional Rosetta Relax post-processing step (off by default, controlled by `relax_enabled`) refines AF2 outputs and returns per-residue energy scores that contribute a relax-penalty term to the composite design score [14]. The cost-aware property of this order - cheap soluble-expression and sequence-level signals before expensive structure prediction - follows from these dependencies rather than driving them.

Each run writes request metadata, intermediate outputs, status records, and final summaries under a run-scoped artifact directory. The run identifier is the unit of provenance. This structure supports controlled partial reruns: downstream filtering or evaluation can be repeated when only downstream parameters change, while unsafe reuse is blocked when upstream inputs differ. The same artifact contract is used by the benchmark scripts, so the empirical analyses can be rerun from stored outputs rather than from live model calls.

### 2.3 Diversification and Constraint Handling

The pipeline exposes three sources of candidate diversity before AF2 is invoked (Figure 1). RFdiffusion provides topology-level backbone diversification. BioEmu samples conformational frames around a backbone. MSA-derived conservation tiers fix progressively larger sets of conserved positions during ProteinMPNN design, producing sequence pools with different redesign latitude. In this architecture, ensemble or alternative structural inputs are treated as controlled sources of landscape expansion, not as evidence by themselves that design quality improves. This separation between across-backbone exploration and within-backbone sequence sampling becomes important for interpreting the variance decomposition and backbone-context ablation in Sections 3.7 and 3.9.

Residue protection has two paths into the design stage. (i) Mask consensus aggregates programmatic signals - MSA conservation, ligand proximity to non-water hetero atoms, MSA quality, and query-PDB identity - into per-tier consensus positions and writes them to `mask_consensus.json`. Unless `mask_consensus_apply=true`, these positions remain advisory and the design stage continues from the MSA-derived conservation tiers. When consensus application is enabled, the consensus positions become the tier-specific fixed positions passed into ProteinMPNN. (ii) Manual residue selections from the user interface enter through a separate `fixed_positions_extra` channel and are unioned into the final per-chain fixed-position set. A Gemini-based agent panel reads the same artifacts and supplies literature-grounded commentary for the operator alongside the run, but does not feed the consensus computation or update the mutation mask in the analyses reported here. The design stage therefore sees a single fixed-position structure after the enabled programmatic and manual constraints are merged, while the agent layer functions as an expert-review aid rather than as a mutation-policy model.

The packaged web interface mirrors this distinction. A basic mode exposes the end-to-end solubility-aware library workflow with a small number of output-size and threshold controls. Advanced mode exposes start and stop points, optional backbone/ensemble stages, masking controls, and AF2 budget parameters. The interface is distributed as static assets over the same backend API, so users can run the backend locally or on a GPU server without relying on a hosted service.

![Pipeline overview](figures/benchmark/fig1_pipeline_overview.png)

*Figure 1. Stage order and diversification levers in `protein_pipeline`. The default path is a solubility-aware redesign workflow: MSA-derived constraints guide ProteinMPNN sequence generation, SoluProt filters candidate soluble-expression likelihood, and AF2/ColabFold is reserved for structurally plausible short lists. RFdiffusion and BioEmu diversify backbone topology and conformation, conservation tiers diversify sequences within a backbone, and ligand-aware masking can protect residues that should not be redesigned.*

### 2.4 Active-Learning Module for AF2 Reduction

The active-learning module supports a multi-round orchestration mode within one pipeline invocation (Figure 2). Round 1 bootstraps a local surrogate from a K-means-selected AF2-labelled training set; subsequent rounds generate new candidate pools, reuse the archived surrogate, and send only the surrogate-ranked Top-K candidates to AF2. Closed-loop learning in this study is therefore implemented by the surrogate-selection step, which uses AF2/ColabFold-derived structural-confidence labels and directly observed SoluProt scores; the agent panel described above remains advisory. The benchmark below validates the component choices from stored candidate pools; Section 3.8 reports two completed representative multi-round runs to verify the implemented orchestration path, while leaving broad campaign-level hit-rate estimation to future work.

The loop has six steps. First, ProteinMPNN generates a multiple-mutant candidate pool across conservation tiers, and SoluProt scores every candidate. Second, candidates passing the SoluProt gate are embedded with mean-pooled ESM-2 8M embeddings [4], and K-means selects a diverse initial training set. Third, AF2 evaluates the selected training candidates. Fourth, a local surrogate is trained on the AF2-labelled examples and ranks the unlabelled SoluProt-passing pool by predicted pLDDT. Fifth, AF2 evaluates the surrogate's top-ranked candidates. Sixth, the evaluated set is ranked by a composite score combining observed pLDDT, directly observed SoluProt, and an optional relax penalty [14].

At the production defaults, the first round evaluates 30 K-means-selected training candidates and 20 surrogate-selected candidates, for approximately 50 AF2 calls. Later rounds reuse the archived surrogate and evaluate only 20 surrogate-selected candidates per round. Evaluating every candidate in a 90-candidate SoluProt-gated pool would require approximately 90 AF2 calls per round.

![Active-learning loop](figures/benchmark/fig2_active_learning_loop.png)

*Figure 2. Active-learning loop used to reduce AF2 calls. A small K-means-selected training set is labelled by AF2, a local surrogate ranks the remaining pool, and AF2 is reserved for the surrogate's top-ranked candidates. In multi-round mode, the archived surrogate is reused on later candidate pools so that only Top-K candidates are folded after the bootstrap round.*

### 2.5 Benchmark Dataset, Surrogates, and QC Filtering

The statistical benchmark uses a QC-filtered CATH [15] set assembled from completed pipeline executions. Runs whose `designs.fasta` or `designs_filtered.fasta` artifacts consisted of fallback identifiers, invalid amino-acid sequences, missing conservation tiers, or too few positive AF2 confidence records were excluded from the analysis set. The retained benchmark contains 23 CATH targets and 2,737 valid designs with paired SoluProt and positive pLDDT records. This set partially overlaps the earlier 15-target pilot but replaces it as the analysis set used for the surrogate, bias, sample-size, rank-mean ensemble, and variance results reported below. All surrogates consume mean-pooled ESM-2 8M embeddings (320 dimensions) [4].

The 23-target benchmark was built by applying the same artifact parser and QC rules to 73 completed CATH run directories. Twenty-three runs passed the publication QC rule requiring all three conservation tiers, at least 100 valid non-fallback amino-acid design sequences, and at least 100 positive pLDDT records. The included subset contains 2,737 paired SoluProt/pLDDT design rows (Table 1). Target-level summaries show that the curated corpus spans both high-confidence redesign cases and lower-confidence or low-solubility targets, rather than only near-perfect examples (Figure 3).

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

*Table 1. QC-filtered CATH benchmark corpus used for the surrogate, sample-size, bias, ensemble, and variance analyses. Excluded records are fallback or input-incompatible runs under the current pipeline contract, not valid low-quality designs.*

![QC-filtered CATH benchmark corpus](figures/benchmark/fig11_cath_curated_expansion.png)

*Figure 3. Target-level summary of the 23-target QC-filtered CATH benchmark corpus. Targets are sorted by mean pLDDT; dashed guides mark pLDDT = 85 and SoluProt = 0.5. The corpus preserves target-level heterogeneity while excluding fallback or invalid-sequence records.*

Seven regression surrogates are evaluated against a random baseline: Random Forest [16], Ridge regression, Gaussian Process with RBF kernel, XGBoost [17], LightGBM [18], K-Nearest Neighbours, and a small multilayer perceptron. Implementations come from standard machine-learning libraries [19]. K-means uses k-means++ initialisation [20]. The production evolution loop exposes the benchmark-supported RF, Ridge, LightGBM, XGBoost, and rank-mean ensemble options; GP-RBF, KNN, MLP, and random selection are retained as empirical comparators rather than production defaults.

For each target and seed, a training pool of N candidates is selected either uniformly at random or by K-means cluster centres. The surrogate is trained on that pool and ranks a held-out candidate set. The main model comparison uses N = 30, and the sample-size ablation evaluates N in {5, 10, 20, 30, 50, 80}. The production loop uses N = 30 to match the benchmark default: the N-ablation in Section 3.5 places 20-30 examples on the cost-efficient plateau, so 30 is the largest near-plateau value validated by the main model comparison.

### 2.6 Metrics and Statistical Analysis

The benchmark reports three metric families. **Spearman rho** measures rank correlation between predicted and observed scores. **Top-K recall** measures how many true Top-K candidates are recovered by the surrogate's predicted Top-K. **BO uplift Top-K**, following the selection-focused evaluation common in Bayesian optimization [21], measures the difference between the mean observed score of the surrogate-selected Top-K and the mean score of K random draws from the same held-out pool. We use Top-5 as the primary setting because it is the most discriminating short-list regime in a 90-candidate pool.

Paired comparisons use the Wilcoxon signed-rank test [22] with Holm-Bonferroni correction [23]. Effect sizes are reported as Cliff's delta [24]. Confidence intervals are 95% cluster bootstrap intervals with target as the cluster. Variance decomposition uses the one-way ANOVA-based intraclass correlation coefficient ICC1 [25].

## 3. Results

### 3.1 Pipeline Execution and Artifact Reuse

The first measured effect of orchestration is that execution artifacts become reusable evidence rather than run-specific by-products. A run contains the request, stage outputs, status logs, SoluProt scores, AF2 outputs, and final summaries needed to reconstruct the path from input target to selected soluble-design candidate. This matters concretely: every result in Sections 3.2-3.7 below - the K-means versus random ablation, the eight-surrogate comparison, the rank-mean ensemble study, the N-ablation, the bias and diversity analysis, and the variance decomposition - was computed from the same 2,737 stored AF2 outputs using the same parsing code. No per-ablation re-folding was performed; ESM-2 8M embeddings were computed once and reused across downstream surrogate analyses. No ablation required modifying the artifact schema. It also matters for model replacement: if a new structure predictor, inverse-folding backend, or solubility model writes the same artifact fields, the benchmark can be rerun with the same analysis protocol.

The retained CATH benchmark has mean pLDDT 91.91, maximum pLDDT 97.89, mean SoluProt 0.615, and maximum SoluProt 0.971. These values are derived from the stored run artifacts and summarised in `cath_outputs/paper_curated/curated_summary.json`. Records excluded by QC are not treated as failed designs; they are treated as input-compatibility or design-generation failures under the current pipeline contract.

The stage order also makes the compute policy explicit. Backbone diversification and joint multiple-position sequence generation occur before AF2, while SoluProt acts as a cheap soluble-expression gate. The active-learning module then reduces the number of SoluProt-passing candidates sent to AF2. The remaining results quantify the operating point of this policy.

### 3.2 Training-Set Selection Improves Small-N Efficiency (Q2)

K-means training-set selection improves Random Forest BO uplift in the small-N regime (Figure 4, Table 2). At N = 5, K-means improves pLDDT BO uplift by 38% over random sampling; at N = 10, by 19%; and at N = 20, by 12%. The gap closes near N = 30, where random sampling becomes diverse enough by chance, and reopens only modestly at larger N.

![Selection x N](figures/benchmark/fig3_selection_n_curves.png)

*Figure 4. Random Forest BO uplift Top-5 as a function of training-set size N under random and K-means training-set selection. K-means gives its largest advantage in the low-label regime and converges with random sampling near the production default of N = 30.*

| N | Random | K-means | Delta (K-means - random) |
|---:|---:|---:|---:|
| 5 | 0.254 | **0.350** | +0.097 (+38%) |
| 10 | 0.327 | **0.390** | +0.063 (+19%) |
| 20 | 0.418 | **0.468** | +0.050 (+12%) |
| 30 (production and benchmark default) | 0.459 | 0.456 | -0.003 (-1%) |
| 50 | 0.459 | **0.484** | +0.025 (+5%) |
| 80 | 0.454 | **0.490** | +0.036 (+8%) |

*Table 2. Random versus K-means training-set selection for the production Random Forest surrogate. The K-means advantage is largest precisely in the small-N cold-start regime targeted by the multi-round budget model.*

The selection strategy interacts with surrogate family (Figure 5). At N = 30, the average difference between K-means and random selection is small, but the small-N ablation shows why the production loop uses K-means for the bootstrap round: it protects the cold start from redundant local sampling before any AF2 labels are available.

![Selection x model](figures/benchmark/fig4_selection_comparison.png)

*Figure 5. Per-model effect of training-set selection on BO uplift Top-5 at fixed N = 30. Differences are smaller than in the low-N regime, indicating that K-means is most valuable as a cold-start safeguard rather than as a universal advantage at all label budgets.*

### 3.3 RF Is the Conservative pLDDT Triage Default (Q1)

Under K-means selection at N = 30, RF gives the highest mean pLDDT BO uplift in the 23-target benchmark (Figure 6, Table 3). Ridge, KNN, and XGBoost remain statistically indistinguishable from RF after Holm correction, whereas LightGBM is slightly but significantly lower on this primary pLDDT metric. GP-RBF, MLP, and the random baseline are substantially worse. The mean ordering therefore supports RF as the conservative default for the AF2-derived pLDDT bottleneck, with Ridge retained when SoluProt ranking or recall-oriented metrics are prioritised.

![Model comparison](figures/benchmark/fig5_model_comparison.png)

*Figure 6. Eight surrogate models (RF, Ridge, GP-RBF, XGBoost, LightGBM, KNN, MLP, Random) compared on Spearman rho and BO uplift Top-5 for both pLDDT and SoluProt prediction. K-means training-set selection, N = 30, held-out candidate pool, 5 seeds x 23 targets = 115 paired observations. Error bars are 95% cluster bootstrap CIs.*

| Model | BO uplift Top-5 | Delta vs RF | p_holm vs RF | Cliff's delta |
|---|---:|---:|---:|---:|
| **RF** | **0.602** | - | - | - |
| Ridge | 0.583 | -0.019 | 0.71 (n.s.) | +0.04 |
| KNN | 0.572 | -0.030 | 0.51 (n.s.) | +0.05 |
| XGBoost | 0.558 | -0.044 | 0.51 (n.s.) | +0.07 |
| LightGBM | 0.549 | -0.053 | 0.046* | +0.05 |
| GP-RBF | 0.326 | -0.276 | 0.00022*** | +0.20 |
| MLP | 0.185 | -0.417 | 1.6e-13*** | +0.49 |
| Random | 0.016 | -0.586 | 1.1e-11*** | +0.47 |

*Table 3. pLDDT BO uplift Top-5 under K-means selection at N = 30. Holm-corrected paired Wilcoxon places Ridge, KNN, and XGBoost in a statistical tie with RF; LightGBM is slightly lower after correction, and GP-RBF, MLP, and the random baseline are clearly worse.*

Ridge is the strongest model for SoluProt-related metrics and for pLDDT Top-K recall (Table 4). This supports score-specific defaults rather than a single universally best surrogate. In the implemented evolution loop, however, SoluProt is directly scored for all candidates; the local surrogate is used primarily for the AF2-derived pLDDT bottleneck.

| Metric (K-means, N = 30) | 1st | 2nd | RF rank |
|---|---|---|:-:|
| pLDDT - BO uplift Top-5 | **RF 0.602** | Ridge 0.583 | 1st |
| pLDDT - Top-5 recall | **Ridge 0.155** | RF 0.150 | 2nd |
| pLDDT - Top-20 recall | **Ridge 0.404** | RF 0.396 | 2nd |
| pLDDT - Spearman rho | GP-RBF 0.438 | RF 0.409 | 2nd |
| SoluProt - Spearman rho | **Ridge 0.904** | GP-RBF 0.781 | 3rd (0.718) |
| SoluProt - Top-5 recall | **Ridge 0.656** | RF 0.400 | 2nd |
| SoluProt - Top-20 recall | **Ridge 0.797** | RF 0.613 | 2nd |
| SoluProt - BO uplift Top-5 | **Ridge 0.042** | RF 0.034 | 2nd |

*Table 4. Best models across pLDDT and SoluProt production-quality metrics. RF is strongest for the primary pLDDT BO uplift objective, whereas Ridge dominates SoluProt ranking and recall-oriented metrics. GP-RBF has the highest pLDDT Spearman rho but weaker selection metrics, so it is retained as an empirical comparator rather than as a production default.*

This produces a deliberate score-specific recommendation rather than a single universal winner. RF is retained as the conservative default for pLDDT-driven AF2 triage. Ridge is retained as a production option when the operator wants stronger SoluProt ranking or Top-K recall. XGBoost and LightGBM remain useful alternatives for model-replacement experiments, but the 23-target benchmark no longer supports making LightGBM the default pLDDT surrogate.

### 3.4 Rank-Mean Ensembles Are an Optional Robustness Layer

Rank-mean, score-mean, and top-5 vote ensembles were evaluated over RF, Ridge, LightGBM, and XGBoost. Rank-mean gives the highest mean pLDDT BO uplift, but the gain over RF is small (0.622 versus 0.602) and does not improve Top-10 sequence diversity (Table 5). Ridge remains the strongest SoluProt surrogate. The ensemble is therefore best interpreted as a robustness option against target-level model switching, not as a replacement for the RF default.

| Combination rule | pLDDT BO uplift Top-5 | SoluProt BO uplift Top-5 | Top-10 internal identity (pLDDT) |
|---|---:|---:|---:|
| **rank-mean ensemble** | **0.622** | 0.0370 | 0.883 |
| score-mean ensemble | 0.611 | 0.0377 | 0.881 |
| RF | 0.602 | 0.0335 | 0.887 |
| top-5 vote ensemble | 0.600 | 0.0363 | 0.880 |
| Ridge | 0.583 | **0.0418** | **0.865** |
| XGBoost | 0.558 | 0.0308 | 0.873 |
| LightGBM | 0.549 | 0.0297 | 0.877 |

*Table 5. Four-model ensembles compared with single surrogate models on the same 23-target x 5-seed protocol. Rank-mean gives the highest pLDDT BO uplift, but the margin over RF is small. Ridge remains the strongest SoluProt model and gives the lowest Top-10 internal identity among the listed options.*

The ensemble result is intentionally conservative. Rank-averaging slightly improves the mean pLDDT selection score, but it does not solve the diversity-loss pattern discussed in Section 3.6 and does not replace Ridge for SoluProt. The recommended deployment therefore stays target-aware: RF for pLDDT-driven AF2 triage, Ridge for SoluProt- or recall-heavy use cases, and the rank-mean ensemble when robustness to per-target ranking flips matters more than the simplicity of one default model.

### 3.5 Sample Size Identifies a Cost-Efficient Operating Point

The sample-size ablation places the production default N = 30 on the cost-efficient plateau (Figure 7, Table 6). Increasing N from 30 to 80 requires roughly 2.7x more AF2-labelled training examples but yields only +7% pLDDT uplift and +11% SoluProt uplift relative to the N = 30 operating point.

![Sample size](figures/benchmark/fig8_sample_size.png)

*Figure 7. N-ablation under K-means selection. Four production-supported models (RF, Ridge, XGBoost, LightGBM) are compared on Spearman rho and BO uplift Top-5 for both surrogate targets, with a vertical line at N = 30 (production default).*

| N_train | RF BO uplift Top-5 (pLDDT) | % of N = 80 | RF BO uplift Top-5 (SoluProt) | % of N = 80 |
|---:|---:|---:|---:|---:|
| 5 | 0.350 | 71.4% | 0.0140 | 62.1% |
| 10 | 0.390 | 79.7% | 0.0155 | 69.1% |
| 20 | 0.468 | 95.6% | 0.0199 | 88.5% |
| **30 (production and benchmark default)** | **0.456** | **93.1%** | **0.0202** | **89.8%** |
| 50 | 0.484 | 98.9% | 0.0213 | 94.5% |
| 80 | 0.490 | 100.0% | 0.0225 | 100.0% |

*Table 6. Sample-size ablation for the RF surrogate under K-means selection. The N-ablation captures the diminishing-returns regime above N = 20-30. The N = 30 default is therefore a deliberately conservative cost-efficient operating point, leaving a small margin above N = 20 while avoiding the additional AF2 cost of N = 50-80.*

### 3.6 Training-Set Diversity Does Not Remove Acquisition Bias

The surrogate's Top-K selections can be more self-similar than the true Top-K, even when the training set is selected by K-means. We quantify this with overfitting identity to the best training sequence and internal identity within the selected Top-K (Figure 8, Table 7). K-means slightly lowers identity to the training-set best relative to random selection, but the selected Top-K remains more internally similar than the true Top-K. Diversity control therefore belongs at acquisition time, not only at training-set construction.

![Bias analysis](figures/benchmark/fig6_bias_analysis.png)

*Figure 8. Bias and diversity analysis on the 23-target benchmark (RF, N = 30). Top row: Top-5 metrics; bottom row: Top-10 metrics. Box plots aggregate per-target means across 5 seeds; red dashed lines mark the true-optimal reference; right panels additionally show the random-baseline diversity floor.*

| Metric (23 targets x 5 seeds, RF, N = 30) | Random | K-means | True optimal | Random Top-K |
|---|---:|---:|---:|---:|
| **Top-5 - overfit identity** | 0.872 | 0.862 | 0.860 | - |
| **Top-5 - internal identity** | 0.898 | 0.891 | 0.866 | 0.828 |
| **Top-5 - mean pLDDT** | 92.51 | 92.51 | 93.09 | 91.95 |
| Top-10 - overfit identity | 0.870 | 0.859 | 0.854 | - |
| Top-10 - internal identity | 0.892 | 0.887 | 0.864 | 0.831 |
| Top-10 - mean pLDDT | 92.47 | 92.45 | 92.89 | 91.91 |

*Table 7. Bias metrics on 23 CATH targets at K in {5, 10}. K-means reduces identity to the training-set best relative to random sampling, but RF-selected Top-K sets remain more internally similar than the true-optimal Top-K sets. The acquisition step therefore still needs explicit diversity control if sequence diversity is a design objective.*

Per-target results also show winner switching across surrogate families (Figure 9). This supports retaining several surrogate options rather than hard-coding one model family for all targets.

![Per-target heatmap](figures/benchmark/fig7_per_target_heatmap.png)

*Figure 9. Per-target BO uplift Top-5 difference relative to RF, K-means selection, N = 30. Each cell shows mean(model BO uplift) - mean(RF BO uplift) for one (target, model) pair, averaged over 5 seeds. Positive values mean the model beats RF on that target; negative values mean the model loses. The heatmap exposes target-level winner switching that aggregate means hide, supporting a configurable surrogate layer rather than a hard-coded single model.*

### 3.7 Target Identity Dominates Observed Design-Quality Variance (Q3)

The final analysis asks whether low design scores mainly reflect ProteinMPNN sampling noise or the target/backbone context. A one-way ANOVA over the 2,737 AF2-evaluated designs shows that target identity explains nearly all of the observed pLDDT variance (Figure 10, Table 8). The ICC1 is 0.988 for pLDDT and 0.968 for SoluProt.

![MPNN error decomposition](figures/benchmark/fig10_mpnn_decomposition.png)

*Figure 10. Per-target pLDDT distributions across ProteinMPNN designs (top, sorted by mean), variance decomposition (bottom-left), and per-target mean-versus-std scatter (bottom-right, marker size encodes max pLDDT). Targets are tightly clustered around their own mean and stretched far apart from each other.*

| Surrogate target | Between-target variance | Within-target variance | ICC1 |
|---|---:|---:|---:|
| pLDDT | 86.81 | 1.11 | **0.988** |
| SoluProt | 0.0225 | 0.00077 | **0.968** |

*Table 8. Variance decomposition of design quality across 23 CATH targets. ICC1 near 1 means most of the spread between high- and low-scoring designs is explained by which target is chosen, not by which sequence ProteinMPNN happens to sample for that target.*

This result does not prove that ProteinMPNN is globally optimal. A low within-target variance is also consistent with a model that makes the same systematic mistake repeatedly. The result instead identifies where additional sampling is least likely to help in this dataset: drawing more sequences from the same target has limited observed headroom compared with changing or triaging the target/backbone context.

### 3.8 Representative Multi-Round Evolution Runs

To verify that the multi-round mode executes as implemented rather than only as an offline benchmark abstraction, we ran two representative RFD3-enabled redesign targets through the production evolution path. Each run generated four round-specific candidate pools with 2,000 SoluProt-gated candidates per round. The 3RGK run used 30 K-means bootstrap AF2 labels and Top-K = 20; the 1LVM run used the same 30-label bootstrap and Top-K = 5. These runs are not treated as a new statistical benchmark because they involve two targets and different Top-K budgets. They instead provide an execution trace for the pool generation, SoluProt gating, ESM embedding, K-means bootstrap, local surrogate ranking, AF2 oracle evaluation, optional relax scoring, and final design selection path.

| Target | Run ID | SoluProt-gated candidates | AF2 records | AF2 reduction vs folding all gated candidates | Top-K setting | Best round/phase | Best SoluProt | Best pLDDT | Best relax score |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| 3RGK | `pys74631_kribb.re.kr_ev_3rgk` | 8,000 | 94 | 98.8% | 20 | R1 train | 0.794 | 97.05 | -3.13 |
| 1LVM | `admin_20260430_064926_afb67369` | 8,000 | 49 | 99.4% | 5 | R3 top-k | 0.734 | 89.52 | -3.15 |

*Table 9. Representative end-to-end multi-round evolution runs. The AF2 reduction is computed as 1 - actual AF2 records / SoluProt-gated candidates. The two runs used different Top-K budgets, so the table demonstrates implemented orchestration and artifact capture rather than a paired biological comparison.*

The companion direct pipeline runs (`pys74631_kribb.re.kr_3rgk` and `admin_1lvm`) each produced 60 SoluProt-scored candidates and 59 usable AF2 outputs after the RFD3/ProteinMPNN/SoluProt path. The 3RGK direct run reached mean pLDDT 96.33 and maximum SoluProt 0.866, whereas the 1LVM direct run reached mean pLDDT 88.85 and maximum SoluProt 0.772. These direct runs confirm that the same target-specific operating regimes appear in the standard pipeline path, but they are smaller than the multi-round evolution pools.

The two evolution traces also show why the multi-round result should be interpreted cautiously. In 3RGK, the best composite design was already present in the round-1 bootstrap training set, so later surrogate-guided rounds did not improve the selected best design even though they continued to find high-pLDDT candidates. In 1LVM, the best design was selected during the round-3 Top-K phase, demonstrating that archived surrogate reuse can identify later-round candidates. This supports the implementation claim, but a larger paired campaign is still needed to estimate hit-rate improvement.

### 3.9 Backbone-Context Ablation Shows Target-Dependent Tradeoffs

To test whether structural-context diversification should be treated as a default score-improvement step or as an exploration lever, we completed a paired three-target pilot comparing the original target backbone, one selected RFD3 backbone, and a three-backbone RFD3 ensemble under matched design and AF2 budgets (Figure 11, Table 10). Each target-arm pair produced 117-120 ProteinMPNN designs and 30 AF2-scored candidates. Averaged over the three targets, the selected RFD3-backbone arm increased Top-5 pLDDT relative to the single target backbone (87.58 versus 84.76), whereas the RFD3-ensemble arm was intermediate (85.58). The ensemble arm preserved the highest Top-5 SoluProt mean (0.759 versus 0.756 for the single-backbone arm) and lowered mean pairwise identity relative to the single-backbone arm by 0.138 on average.

The target-level pattern was mixed. RFD3 improved low-pLDDT 1kvdD00 designs but did not improve pLDDT on the already high-confidence 2wejA00 and 3bukC01 cases. With three paired targets, these effects are not statistically reliable as general performance claims. They instead support using RFD3 and ensemble inputs as controlled structural-context exploration modes.

![Backbone and ensemble ablation](figures/benchmark/fig12_backbone_ensemble_ablation.png)

*Figure 11. Paired backbone-context ablation across three CATH targets. The single-backbone, selected-RFD3-backbone, and three-backbone RFD3-ensemble arms use comparable ProteinMPNN and AF2 budgets. The pilot shows target-dependent tradeoffs rather than a uniform ordering across pLDDT, SoluProt, and sequence-diversity metrics.*

| Arm | Designs per target | AF2 records per target | Top-5 pLDDT | Top-5 SoluProt |
|---|---:|---:|---:|---:|
| Single target backbone | 120 | 30 | 84.76 | 0.756 |
| RFD3 selected backbone | 120 | 30 | 87.58 | 0.725 |
| RFD3 ensemble, 3 backbones | 117 | 30 | 85.58 | 0.759 |

*Table 10. Backbone-context ablation summary. Values are target-level means over three CATH targets and one replicate per target. The selected-RFD3 arm gives the highest mean Top-5 pLDDT, while the ensemble arm gives the highest mean Top-5 SoluProt and broader sequence diversity. Because the pilot contains three paired targets, it is used to guide interpretation and workflow defaults rather than to claim a general statistical advantage.*

## 4. Discussion

### 4.1 Solubility-Aware Pipeline as an Empirical Instrument

The pipeline preserves enough structure to make solubility-aware compute-allocation questions testable. Because every stage writes run-scoped artifacts under a typed contract, every result in Sections 3.2-3.7 was derived from the same 2,737 stored AF2 outputs and their corresponding SoluProt records using the same parsing code. A model-replacement study - for example, swapping AF2 for ESMFold or AlphaFold3, ProteinMPNN for LigandMPNN/SolubleMPNN, or SoluProt for another solubility predictor - reduces to changing the backend that writes the relevant artifact fields rather than rewriting the analysis code. Table 11 maps this directly against the operations a script-based workflow would have to repeat or rewrite per ablation.

| Operation | Script-based workflow | `protein_pipeline` |
|---|---|---|
| Add a new surrogate comparison | Re-load AF2 outputs from heterogeneous folders, write a new parser | Reload stored outputs from the typed `af2/` artifact |
| Compare N in {5, ..., 80} | Re-run pipeline per N or maintain custom subsampling scripts | Subsample the stored training pool |
| Swap AF2 -> AF3 / ESMFold | Rewrite scoring, parsing, and downstream filtering | Replace the structure-prediction backend; analysis code unchanged |
| Swap SoluProt -> another solubility model | Rebuild thresholding and result collation scripts | Replace the soluble-expression artifact writer; downstream ranking unchanged |
| Add a new metric retrospectively | Re-run scoring on each historical run | Compute on stored artifacts using the same contract |
| Reproduce a 6-month-old run | Hope the relevant folders, environment, and scripts survived | Open the run_id directory; `request.json` reconstructs the configuration |
| Cross-run comparison (23 targets x 5 seeds) | Manual collation across folders, brittle to schema drift | Same artifact schema guarantees direct comparison |

*Table 11. Operational contrast between a script-based workflow and `protein_pipeline` on the operations performed in Results. The artifact contract is what allows the same 2,737 AF2 outputs to support multiple independent ablations without re-folding or per-experiment parser rewrites.*

### 4.2 AF2 Budget Model

The implemented active-learning loop uses approximately 50 AF2 calls in the bootstrap round rather than folding every candidate in a 90-candidate SoluProt-gated pool. For a multi-round campaign, Table 12 gives the implemented orchestration-level budget: the first round bootstraps the surrogate, and later rounds reuse the archived surrogate and evaluate only the surrogate-ranked Top-K candidates. Under this model, a four-round campaign spends 110 AF2 calls rather than 360, a 69% reduction. At an assumed 30 seconds per AF2 call on the production endpoint, this corresponds to approximately 55 minutes rather than 180 minutes of GPU time per target.

| Per-round AF2 budget model | Without surrogate | Round 1 (with surrogate) | Rounds 2-4 (label reuse / archived surrogate) |
|---|---:|---:|---:|
| AF2 evaluations | 90 | 30 + 20 = 50 | 20 |
| Reduction vs no-surrogate | - | **44%** | **78%** |

*Table 12. AF2 budget per round on a 90-candidate SoluProt-gated pool. Round 1 evaluates 30 K-means training candidates and 20 surrogate-selected candidates (50 total); rounds 2-4 reuse the trained surrogate and only evaluate the 20 top-ranked candidates each. Across a four-round campaign the total AF2 budget is 50 + 20 x 3 = 110 evaluations versus 90 x 4 = 360 without the surrogate, a 69% overall reduction.*

The representative 3RGK and 1LVM evolution runs in Section 3.8 use larger RFD3-enabled pools than the 90-candidate budget illustration, with 8,000 SoluProt-gated candidates per target. Their realized AF2 records were 94 and 49, respectively, because only the bootstrap and surrogate-selected candidates are sent to the oracle. These runs validate the implemented execution path and artifact capture; a larger paired campaign remains necessary to estimate biological hit-rate improvement from archived surrogate reuse.

### 4.3 Compute Allocation Across Backbones

The variance decomposition changes the interpretation of the active-learning loop. If most observed variance were within a target, deeper ProteinMPNN sampling or a better acquisition rule would be the main compute lever. Instead, target identity explains 98.8% of pLDDT variance in this benchmark. This suggests that early rounds should allocate some budget to target or backbone triage rather than only to more sequence variants around one backbone. RFdiffusion and BioEmu are therefore best understood in this paper as operational levers for exploring the dominant variance axis, not as independently validated sources of quality improvement.

The three-target pilot in Section 3.9 is consistent with this interpretation. RFD3 changed the structural context and sometimes improved pLDDT, but the effect depended on the target and did not establish a universal ordering among single-backbone, RFD3, and RFD3-ensemble modes. Within a chosen backbone, conservation-tier sampling remains useful because it changes the number and placement of jointly redesigned positions, but the observed within-target spread bounds its expected return. Acquisition-time diversity control is still needed because the surrogate's selected Top-K is more self-similar than the true optimum. These conclusions are complementary: backbone or target triage addresses the largest observed variance axis, while acquisition diversity prevents local surrogate selections from collapsing within a promising context.

### 4.4 Re-validation After Model Replacement

The benchmark results should be interpreted as estimates for the current solubility-aware model stack, not as invariant statements about all future structure predictors, inverse-folding models, or solubility predictors. The pipeline design makes this limitation manageable. If a replacement structure predictor such as ESMFold or AlphaFold3, a replacement inverse-folding model such as LigandMPNN or SolubleMPNN, or a replacement solubility/developability model writes the same artifact fields, the same benchmark protocol can be rerun. The numerical operating point may change, but the analysis workflow does not need to be redesigned.

## 5. Limitations

- **Benchmark scope.** The reported statistical comparisons use the QC-filtered 23-target CATH benchmark, not the full set of 73 completed CATH runs. Excluded records are input-incompatible or fallback-design runs under the current pipeline contract, so the benchmark should be interpreted as a publication-grade subset rather than as a failure-rate estimate for arbitrary CATH inputs.
- **Solubility scope.** The pipeline is designed and benchmarked as a solubility-aware redesign/library-generation workflow. Binder design, enzyme active-site redesign, and fully de novo protein generation are supported only through optional or replaceable stages and are not validated as primary claims here.
- **Component-level validation.** The active-learning benchmark evaluates surrogate selection from stored SoluProt/AF2 candidate pools, not a complete wet-lab campaign. Two representative multi-round runs validate end-to-end orchestration, but campaign-level hit-rate improvement and wet-lab outcomes from archived surrogate reuse remain to be validated.
- **Computational proxies.** pLDDT and SoluProt are computational proxies. They do not establish soluble expression, thermodynamic stability, or activity without experimental measurement.
- **Backbone and ensemble ablation.** The paired backbone-context pilot covers three CATH targets and one replicate per target-arm condition. It is sufficient to show that RFD3 and ensemble inputs create measurable, target-dependent tradeoffs, but it is not powered to claim a general improvement in experimentally measured soluble expression or stability.
- **Rosetta Relax coverage.** Relax scores are not available for the full pilot artifact set, so the structural-confidence versus energy Pareto frontier is not analysed.
- **Agent evaluation.** Literature-grounded commentary and Gemini-based reasoning are operational components of the platform, but the reported benchmark does not validate autonomous agent selection of mutation masks. The learning component evaluated here is the ESM-embedding surrogate trained on AF2/ColabFold labels.
- **Model replacement not yet demonstrated.** The architecture supports model replacement by artifact contract, but the benchmark has not yet been rerun with AlphaFold3, ESMFold, LigandMPNN, or another replacement backend.

## 6. Conclusion

`protein_pipeline` addresses a practical gap between rapidly improving protein-design models and the reproducible infrastructure needed to use them in solubility-aware multiple-mutant redesign campaigns. The pipeline preserves run-scoped artifacts, supports controlled partial reruns, exposes the workflow through a packageable static web interface and backend API, and keeps model interfaces replaceable. On top of this infrastructure, a local active-learning module reduces AF2 usage by labelling a small K-means-selected training set, fitting a surrogate, and folding only the surrogate's top-ranked SoluProt-passing candidates.

The empirical benchmark shows that K-means selection improves small-N surrogate performance, that surrogate choice is score-dependent, and that a 20-30 example training set is a cost-efficient operating point. The variance decomposition further shows that target identity, not ProteinMPNN sampling noise, dominates observed pLDDT variance in the 23-target benchmark set. These results support a compute policy in which SoluProt is used as the fast soluble-expression gate, AF2 is reserved for informative structurally plausible short lists, and early campaign budget is allocated across target or backbone contexts rather than only to deeper sequence sampling within one backbone. The pipeline's artifact contract makes these conclusions re-testable as the underlying generative, solubility-prediction, and structure-prediction models change.

## Code, Data, and Software Availability

The pipeline implementation, benchmark scripts, generated figures, result tables, representative multi-round case-study summaries, and static web interface are organised in a public-release package. The backend/MCP service is under `pipeline-mcp/`, the static browser interface is under `frontend/`, benchmark scripts are under `scripts/benchmark/`, generated figures are under `figures/benchmark/`, tabular benchmark results are under `data/benchmark/results/`, and representative 3RGK/1LVM execution summaries are under `data/case_studies/`. The CATH execution archive is staged locally under `cath_outputs/`; the publication-grade benchmark subset and QC reports are under `cath_outputs/paper_curated/`. Because the full corpus is several gigabytes, it should be archived as a large release artifact or S3-backed dataset rather than committed directly to a lightweight GitHub source tree. The release documentation also records the Docker Hub images used to instantiate the RunPod endpoints for MMseqs2, ProteinMPNN, ColabFold/AF2, RFD3, BioEmu, and Rosetta Relax. The included `.env.example` documents required RunPod endpoint variables and local/OIDC authentication settings; filled `.env` files, endpoint IDs, API keys, and runtime logs are excluded. The manuscript uses stored benchmark artifacts rather than modifying generated result values. For publication, the GitHub release should be archived with a persistent DOI, and the same archive should contain the benchmark data used to regenerate the reported tables and figures.

## References

[1] Dauparas, J., Anishchenko, I., Bennett, N., et al. (2022). Robust deep learning-based protein sequence design using ProteinMPNN. *Science*. doi:10.1126/science.add2187

[2] Jumper, J., Evans, R., Pritzel, A., et al. (2021). Highly accurate protein structure prediction with AlphaFold. *Nature*. doi:10.1038/s41586-021-03819-2

[3] Mirdita, M., Schutze, K., Moriwaki, Y., Heo, L., Ovchinnikov, S., & Steinegger, M. (2022). ColabFold: making protein folding accessible to all. *Nature Methods*. doi:10.1038/s41592-022-01488-1

[4] Lin, Z., Akin, H., Rao, R., et al. (2023). Evolutionary-scale prediction of atomic-level protein structure with a language model. *Science*. doi:10.1126/science.ade2574

[5] Watson, J. L., Juergens, D., Bennett, N. R., et al. (2023). De novo design of protein structure and function with RFdiffusion. *Nature*. doi:10.1038/s41586-023-06415-8

[6] Lewis, S., Hempel, T., Jimenez-Luna, J., et al. (2025). Scalable emulation of protein equilibrium ensembles with generative deep learning. *Science*. doi:10.1126/science.adv9817

[7] Hon, J., Marusiak, M., Martinek, T., Kunka, A., Zendulka, J., Bednar, D., & Damborsky, J. (2021). SoluProt: prediction of soluble protein expression in *Escherichia coli*. *Bioinformatics*. doi:10.1093/bioinformatics/btaa1102

[8] Steinegger, M., & Soding, J. (2017). MMseqs2 enables sensitive protein sequence searching for the analysis of massive data sets. *Nature Biotechnology*. doi:10.1038/nbt.3988

[9] Goldenzweig, A., Goldsmith, M., Hill, S. E., et al. (2016). Automated structure- and sequence-based design of proteins for high bacterial expression and stability. *Molecular Cell*. doi:10.1016/j.molcel.2016.06.012

[10] Kosugi, T., & Ohue, M. (2022). Solubility-Aware Protein Binding Peptide Design Using AlphaFold. *Biomedicines*. doi:10.3390/biomedicines10071626

[11] Fleishman, S. J., Leaver-Fay, A., Corn, J. E., et al. (2011). RosettaScripts: A scripting language interface to the Rosetta macromolecular modeling suite. *PLOS ONE*. doi:10.1371/journal.pone.0020161

[12] Jiang, K., Yan, Z., Di Bernardo, M., et al. (2025). Rapid in silico directed evolution by a protein language model with EVOLVEpro. *Science*. doi:10.1126/science.adr6006

[13] Model Context Protocol Contributors (2024). Model Context Protocol Specification. https://modelcontextprotocol.io/specification/2024-11-05/index

[14] Conway, P., Tyka, M. D., DiMaio, F., Konerding, D. E., & Baker, D. (2014). Relaxation of backbone bond geometry improves protein energy landscape modeling. *Protein Science*. doi:10.1002/pro.2389

[15] Sillitoe, I., Bordin, N., Dawson, N., et al. (2021). CATH: increased structural coverage of functional space. *Nucleic Acids Research*. doi:10.1093/nar/gkaa1079

[16] Breiman, L. (2001). Random Forests. *Machine Learning*. doi:10.1023/A:1010933404324

[17] Chen, T., & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*. doi:10.1145/2939672.2939785

[18] Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., & Liu, T.-Y. (2017). LightGBM: A Highly Efficient Gradient Boosting Decision Tree. *Advances in Neural Information Processing Systems 30*. https://papers.nips.cc/paper/6907-lightgbm-a-highly-efficient-gradient-boosting-decision-tree

[19] Pedregosa, F., Varoquaux, G., Gramfort, A., et al. (2011). Scikit-learn: Machine Learning in Python. *Journal of Machine Learning Research*. https://www.jmlr.org/papers/v12/pedregosa11a.html

[20] Arthur, D., & Vassilvitskii, S. (2007). k-means++: The Advantages of Careful Seeding. *Proceedings of the Eighteenth Annual ACM-SIAM Symposium on Discrete Algorithms*. https://dl.acm.org/doi/10.5555/1283383.1283494

[21] Shahriari, B., Swersky, K., Wang, Z., Adams, R. P., & de Freitas, N. (2016). Taking the Human Out of the Loop: A Review of Bayesian Optimization. *Proceedings of the IEEE*. doi:10.1109/JPROC.2015.2494218

[22] Wilcoxon, F. (1945). Individual Comparisons by Ranking Methods. *Biometrics Bulletin*, 1(6), 80-83. doi:10.2307/3001968

[23] Holm, S. (1979). A Simple Sequentially Rejective Multiple Test Procedure. *Scandinavian Journal of Statistics*, 6(2), 65-70. https://www.jstor.org/stable/4615733

[24] Cliff, N. (1993). Dominance statistics: Ordinal analyses to answer ordinal questions. *Psychological Bulletin*. doi:10.1037/0033-2909.114.3.494

[25] Shrout, P. E., & Fleiss, J. L. (1979). Intraclass correlations: Uses in assessing rater reliability. *Psychological Bulletin*. doi:10.1037/0033-2909.86.2.420
