# RAPID: A Reproducible Artifact Pipeline for Solubility-Aware Protein Redesign with Budget-Aware Surrogate Triage

*Type: Software Paper / Empirical Benchmark Contribution*

## Abstract

Solubility-aware protein redesign increasingly combines sequence search, conservation analysis, structural-context sampling, inverse folding, soluble-expression filtering, structure prediction, and novelty assessment. These models are powerful individually, but ad hoc chaining makes provenance, partial reruns, backend replacement, and experimental feedback difficult to audit. We present RAPID, a run-scoped artifact pipeline for solubility-aware multiple-mutant redesign. RAPID stores typed requests, stage outputs, status and trace records, quality-control summaries, experiment records, and final summaries under stable run identifiers, allowing analyses to be regenerated from artifacts rather than repeated model calls. We evaluate three bounded claims. First, the artifact contract makes model replacement and retrospective analysis operational. Second, a structure-prediction-budgeted surrogate triage mode uses SoluProt gating, ESM-2 embeddings, K-means bootstrap selection, internal cross-validation of local surrogate policies, and Top-K acquisition to reduce AF2/ColabFold evaluations; in a five-target strict run, 49,946 candidates entering triage were reduced to 250 AF2/ColabFold records (99.5% reduction), assuming those candidates would otherwise be folded. Third, target-level variation dominates observed proxy scores, motivating explicit compute-allocation tests across single, BioEmu, RFD3, and RFD3+BioEmu structural contexts. RAPID also provides an experimental-feedback evolution interface for assay-labelled next-candidate recommendation. The present evidence is computational and proxy-based: pLDDT, SoluProt, and relax scores do not establish wet-lab soluble expression, thermodynamic stability, or activity.

## 1. Introduction

Computational protein redesign has become a multi-model workflow. A practical solubility-oriented campaign may begin with MMseqs2-based sequence search, derive residue constraints from an MSA, optionally diversify structural context with RFdiffusion or BioEmu, generate multiple-mutant sequences with ProteinMPNN, filter them with a soluble-expression predictor, evaluate selected candidates with AF2 or ColabFold, and finally compare novelty or downstream developability signals [1-8]. The scientific question is often not unconstrained protein generation. It is constrained redesign: starting from an existing target or scaffold, the operator wants a tractable library of multiple-mutant variants that preserves important positions, improves computational soluble-expression likelihood, and remains structurally plausible. This framing is consistent with earlier work showing that protein expression, stability, and solubility can be improved by structure- and sequence-aware computational design, while still requiring experimental validation for final biological claims [9,10].

This setting creates an infrastructure problem. Individual models are updated rapidly and often expose different input formats, output schemas, runtime assumptions, and failure modes. When campaigns are organised as scripts and notebooks, intermediate artifacts become difficult to audit, partial reruns become unsafe, and later model replacement can force a rewrite of the analysis code. These problems are especially costly in biofoundry-scale workflows. A workflow at this scale does not usually evaluate one target and one model setting in isolation; it generates batches of candidate sequences across targets, masking policies, backbone contexts, and scoring thresholds, then has to connect those computational candidates to experimental rounds, assay measurements, and follow-up design decisions. The resulting bottleneck is therefore both computational and interpretive: large candidate sets must be generated cheaply enough to be useful, but their provenance and outcome labels must also remain organised enough to support the next design-test-learn cycle.

The dominant downstream cost in such workflows is structure prediction. ProteinMPNN can generate hundreds or thousands of variants per target, and SoluProt can score them cheaply, but folding every SoluProt-passing sequence is rarely justified. The practical question is therefore not only how to generate candidates, but how to decide where expensive AF2/ColabFold evaluations should be spent and how those decisions should be interpreted after experimental feedback arrives. A useful platform should make this decision auditable: it should preserve the full path from input to candidate, allow the same stored results to support multiple analyses, record assay-derived objective values in a form that can be reused by later rounds, and expose enough model-replacement structure that new backends can be tested without changing the scientific question.

We present RAPID, a reproducible artifact pipeline for integrated design. RAPID is not introduced as a new predictive model or as a universal protein-design engine. It is a model-orchestration and artifact layer specialised here for solubility-aware, structural-confidence-guided multiple-mutant redesign. The paper is organised around three claims. First, RAPID converts fragmented model outputs into a reusable, model-replaceable artifact substrate. Second, RAPID implements and benchmarks structure-prediction-budgeted surrogate triage for post-SoluProt candidate selection. Third, RAPID makes structural-context allocation testable by comparing single-backbone, BioEmu, RFD3, and combined RFD3+BioEmu contexts under explicit design and AF2 budgets. Separately, RAPID records wet-lab outcomes and supports experimental-feedback evolution, but experimental activity or expression improvement is not claimed without prospective validation.

## 2. Methods

### 2.1 RAPID Scope and Architecture

RAPID represents each redesign campaign as a stage-aware orchestration run designed for biofoundry-scale throughput rather than as a collection of disconnected jobs. The canonical stage order is `msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty`. This order is dependency-driven. MSA construction provides conservation-derived residue constraints; optional RFD3 and BioEmu stages provide alternative backbone or conformational contexts; ProteinMPNN generates multiple-mutant sequence libraries under the active fixed-position constraints; SoluProt scores soluble-expression likelihood; AF2 or ColabFold supplies structural-confidence labels; novelty analysis compares surviving designs against sequence databases. Rosetta Relax is available as an optional post-AF2 refinement and scoring step, but it is disabled by default in the benchmark path because full relax coverage was not available for all artifact sets [11,14]. The backend is distributed as a pipeline-MCP service, using a tool-oriented service boundary rather than binding the workflow to one browser session or notebook [13].

The implementation separates the workflow into a control layer and a model-execution layer. The control layer validates requests, resolves stage order, records status transitions, and enforces safe rerun semantics. The model-execution layer dispatches stages to local, HTTP, or RunPod-backed providers as long as each provider writes the expected artifact fields. Optional diagnostic summaries can be generated from stored artifacts for audit and failure review, but they do not alter mutation masks or replace the deterministic execution graph in the analyses reported here.

### 2.2 Solubility-Aware Multiple-Mutant Redesign

RAPID is evaluated here as a solubility-aware redesign workflow. Conservation tiers at 30%, 50%, and 70% determine progressively constrained fixed-position sets from the MSA. These tiers do not define a single-mutation trajectory. Instead, ProteinMPNN redesigns the remaining positions jointly, producing multiple-mutant libraries under each conservation constraint. Manual residue selections from the interface enter through `fixed_positions_extra` and are unioned into the fixed-position set. Programmatic mask consensus can aggregate MSA conservation, ligand proximity, MSA quality, and query-PDB identity into advisory or applied fixed positions, depending on whether consensus application is enabled.

The default scoring path treats SoluProt as a cheap soluble-expression gate before AF2/ColabFold. pLDDT is used as a structural-confidence proxy for short-listing, not as evidence of experimental stability. When relax is enabled, its energy scores can be included as a penalty term in the composite ranking, but the manuscript does not claim thermodynamic stability improvement without wet-lab measurement.

![RAPID artifact orchestration](figures/benchmark/fig1_pipeline_overview.png)

*Figure 1. RAPID provenance-centered redesign substrate. The linear stage order is one operational view. The central contribution is the run_id-centered artifact contract, which preserves requests, stage outputs, status and trace records, quality-control records, metrics, experiment records, and final summaries. This substrate supports safe partial reruns, retrospective benchmark reconstruction, downstream experimental-feedback cycles, and backend replacement without treating RAPID as a simple linear wrapper over model calls.*

### 2.3 Artifact Contract, Interface, and Model Replacement

Each RAPID run writes a typed request, stage outputs, status records, orchestration trace events, diagnostic records, experiment records, and final summaries under a stable run identifier. The run identifier is the unit of provenance. This structure supports controlled partial reruns: downstream thresholds or ranking steps can be repeated from stored artifacts, while upstream input changes invalidate unsafe reuse. The same contract is used by benchmark scripts, so model-comparison and surrogate-triage analyses can be regenerated from stored outputs without refolding the candidate set for every ablation.

The artifact contract is defined around shared downstream fields rather than around a single model implementation (Table 1). This is the basis of the model-replacement claim: replacement is not asserted because every possible backend has already been benchmarked, but because the downstream analysis code consumes stable artifacts rather than model-specific folders.

| Replaceable module | Tested or implemented options | Shared artifact fields | Downstream reuse |
|---|---|---|---|
| Structural context | Single target, BioEmu, RFD3, RFD3+BioEmu | `backbone_id`, source, PDB path, sequence map | ProteinMPNN, SoluProt, AF2 |
| Structure scorer | ColabFold/AF2 | pLDDT, ranking confidence, output PDB | Surrogate benchmark, composite score |
| Solubility scorer | SoluProt | Solubility score, pass/fail records | Gate, composite score |
| Surrogate | RF, Ridge, XGBoost, LightGBM, rank-mean | Predicted pLDDT or rank | Top-K acquisition |
| Relax | Optional Rosetta Relax | Relax score, penalty flag | Composite score |

*Table 1. Replaceable modules and shared artifact fields in RAPID. The table separates the implemented artifact contract from any claim that all possible replacement models have already been validated.*

The local browser interface is treated as a reproducibility surface rather than as a separate scientific claim. It exposes the same run identifiers, request fields, status records, and exportable artifacts used by the benchmark scripts, and it is distributed as static assets over the backend API so that RAPID can be run locally or on a GPU server without relying on a hosted service. Interface-level controls and deployment details are reported in Supplementary Note 14.

### 2.4 Structure-Prediction-Budgeted Surrogate Triage and Experimental Evolution

RAPID separates two related uses of surrogates. The first is a computational structure-prediction-budgeted triage mode used in the benchmark (Figure 2). ProteinMPNN first generates a candidate pool across conservation tiers, and SoluProt scores every candidate. SoluProt-passing candidates are embedded with mean-pooled ESM-2 8M embeddings [4]. In deployment, this embedding stage can be backed by a GPU ESM worker, allowing large ProteinMPNN pools to be featurized without expanding the AF2/ColabFold acquisition budget. K-means selects a diverse bootstrap training set, AF2 labels those candidates, and local surrogate policies are compared by internal cross-validation on the labelled set. The selected acquisition policy is then refit on all bootstrap labels and used to rank the remaining SoluProt-passing pool. AF2 evaluates only the selected policy's Top-K candidates. The supported policy set uses standard Random Forest, Ridge, XGBoost, LightGBM, scikit-learn, k-means, and Bayesian-optimization-inspired acquisition concepts [16-21]. This mode is a compute-allocation policy for structure prediction, not evidence of experimental activity or expression.

The production triage default uses one shared budget across the selected 30%, 50%, and 70% conservation tiers. By default, ProteinMPNN generates 3,333 candidates per tier, giving approximately 9,999 designs before SoluProt filtering. RAPID then labels 30 K-means-selected bootstrap candidates from the pooled SoluProt-passing set and evaluates 20 Top-K AF2 acquisitions from the same pooled set. The N = 30 bootstrap was chosen because the sample-size ablation reaches most of the observed Random Forest pLDDT uplift by that point, while Top-K = 20 fixes a target-level validation budget that is large enough for manual review but small enough to keep the AF2 cost explicit. RAPID trains comparator policies on the same labelled bootstrap set, writes cross-validation metrics, a model-comparison SVG, candidate-level predictions, feature-importance or coefficient tables, and fitted model files, and then uses only one selected acquisition policy for the final Top-K. Thus model comparison is recorded without multiplying AF2 calls. Manual override remains available for controlled runs using Random Forest, Ridge, XGBoost, LightGBM, or rank-mean ensemble.

The second use is an experimental-feedback evolution mode. In this mode, RAPID generates a SoluProt-gated candidate pool and writes `experiment_request.csv` when no wet-lab labels are available. Users can then record assay outcomes through the experiment interface using candidate or sequence identifiers, metric names, metric values, units, directions, and replicate identifiers. When labels for a specified objective metric are present in `experiments.jsonl`, RAPID trains a local surrogate on the labelled sequences and writes `next_candidates.csv` for the next design-test-learn cycle. This interface is related to active-learning directed-evolution frameworks such as EVOLVEpro, but the present manuscript treats it as an assay-feedback handoff rather than as a prospective wet-lab validation result [12]. A legacy `in_silico_af2` label source preserves the earlier AF2-oracle behaviour for computational comparisons, but the default evolution label source is experimental feedback.

This separation is important for biofoundry-scale workflows. The surrogate-triage mode reduces how many candidates require expensive structure prediction before a shortlist is made, whereas experimental-feedback evolution defines how the shortlist can re-enter the system after expression, solubility, activity, or stability assays. Operationally, RAPID provides computational infrastructure upstream of an assay queue: the platform produces traceable shortlists and experiment-request files, while physical measurements are performed outside the software and re-enter RAPID only as labelled outcomes (see Supplementary Note 10 for an illustrative data-trace schema). This is an intended deployment and data pathway, not evidence that the present computational benchmark has already achieved wet-lab enrichment. In other words, RAPID treats computational predictions and experimental measurements as different label sources under the same run-scoped artifact contract. This makes high-throughput candidate generation interpretable across rounds: a later campaign can ask whether a model, masking rule, or backbone context changed the distribution of candidates without manually reconstructing which files, scores, and assay records belonged to each decision.

![structure-prediction-budgeted surrogate triage](figures/benchmark/fig2_active_learning_loop.png)

*Figure 2. Structure-prediction-budgeted surrogate triage. ProteinMPNN candidates from the selected conservation tiers are pooled after SoluProt filtering. K-means selects a diverse AF2-labelled bootstrap set from this pooled candidate set. RAPID compares configured local surrogate policies by internal cross-validation, refits the selected policy on all bootstrap labels, and reserves AF2/ColabFold for one pooled Top-K acquisition set. Comparator-model metrics, optional rank-mean ensemble results, feature summaries, fitted model files, and prediction tables are exported as artifacts without expanding the AF2 budget. Experimental-feedback evolution uses the same candidate and embedding contract but learns from user-recorded wet-lab objective values rather than treating AF2 as a biological oracle.*

### 2.5 Current Artifact Benchmark and Statistical Analysis

The current stored artifact benchmark contains 2,737 paired SoluProt and pLDDT records from 23 QC-passing CATH runs [15]. These data were generated before the final corrected-chain CATH refresh and are therefore used in the main text as component-level evidence for structure-prediction-budgeted surrogate triage rather than as the final population estimate for RAPID. Runs with fallback sequences, invalid amino-acid records, missing conservation tiers, or insufficient positive pLDDT records were excluded from that artifact benchmark. The full pre-fix 73-run archive and QC details are reported in Supplementary Notes 1 and 2.

The primary surrogate-triage metrics are Spearman rank correlation, Top-K recall, and BO uplift Top-K. BO uplift measures the difference between the mean observed score of the surrogate-selected Top-K and the mean score of K random draws from the same held-out pool. Paired comparisons use Wilcoxon signed-rank tests with Holm correction, effect-size interpretation uses Cliff's dominance statistic, and uncertainty is estimated by cluster bootstrap with target as the cluster [22-24]. Variance decomposition uses a one-way ANOVA intraclass correlation coefficient to estimate how much score variation is attributable to target identity [25].

### 2.6 Structural-Context Ablation Protocol

The structural-context claim is tested by running matched design and AF2 budgets across four arms: the original target backbone, target plus BioEmu conformational samples, a selected RFD3 backbone, and a combined RFD3+BioEmu ensemble. Because ProteinMPNN conditions sequence generation on the supplied backbone, changing the backbone or conformational context changes the accessible sequence neighbourhood even when the masking rule and sampling budget are held fixed. The updated RAPID ablation script records the planned backbone count, planned design count, RFD3 settings, BioEmu settings, and AF2 budget for every target-arm pair. Each target-arm run caps AF2 at 30 candidates, so differences are interpreted as structural-context allocation effects rather than as unrestricted additional folding. BioEmu-containing arms are evaluated only when the requested near-target conformers pass the pre-specified target-RMSD gate. Arms that fail this gate are reported as not evaluable for that comparison, rather than being assigned zero-valued design scores, because the failure indicates that the conformational-sampling contract was not satisfied.

| Arm | Structural context tested | Interpretation |
|---|---|---|
| Single | Original target backbone | Baseline redesign around one input structure |
| BioEmu | Conformational ensemble around the target backbone | Same topology with conformational variation |
| RFD3 | Selected/generated RFD3 backbone | Altered backbone geometry or topology context |
| RFD3 + BioEmu | BioEmu ensemble seeded from an RFD3 backbone | Combined backbone diversification and conformational sampling |

*Table 2. Structural-context arms used for RAPID compute-allocation analysis. The arms are designed as controlled exploration modes under matched AF2 caps, not as a priori quality-ranking assumptions.*

The present structural-context analysis uses a corrected-chain eight-target RAPID ablation. The single-backbone and RFD3 arms are evaluable for all eight targets, whereas BioEmu-containing arms are evaluable for four targets under the 2.0 Å target-RMSD gate. This partial evaluability is treated as a workflow QC outcome rather than as a failed design score. For BioEmu sensitivity analyses, sampling budgets may be increased, but the acceptance cutoff is kept fixed to avoid post-hoc relaxation of the structural-quality criterion.

## 3. Results

### 3.1 Claim 1: RAPID Converts Fragmented Model Outputs into Reusable Experimental Artifacts

The first effect of RAPID is operational: it makes heterogeneous model outputs reusable across analyses. In the current artifact benchmark, the K-means versus random selection analysis, surrogate-family comparison, sample-size ablation, rank-mean ensemble test, acquisition-bias analysis, and variance decomposition were regenerated from the same 2,737 stored AF2/SoluProt records. No separate refolding was performed for each ablation, and the benchmark scripts read the same artifact fields regardless of which downstream question was asked.

This artifact reuse is the practical contribution beyond job submission. A pipeline that only launches tools has limited scientific value if each ablation still requires manual collation or repeated folding. RAPID changes the cost structure of analysis because stored artifacts can be resampled, rescored, compared, and audited after the expensive model calls have already completed. It also changes the cost of model replacement. If AF2 is replaced by another structure predictor, ProteinMPNN by another inverse-folding model, or SoluProt by another soluble-expression filter, the surrounding analysis code can remain stable as long as the replacement backend writes the same contract fields.

| Operation | Script-based workflow | RAPID artifact contract |
|---|---|---|
| Add a new surrogate comparison | Rebuild parser and manually reload AF2 outputs | Reload stored AF2/SoluProt artifact fields |
| Compare training-set sizes | Rerun or maintain custom subsampling scripts | Subsample one stored candidate pool |
| Swap structure predictor | Rewrite scoring and downstream collation | Replace backend that writes pLDDT-like artifact fields |
| Swap solubility model | Rebuild thresholding and result collation | Replace soluble-expression artifact writer |
| Add a retrospective metric | Recompute or reparse historical folders manually | Compute from run-scoped stored artifacts |
| Reproduce an old run | Recover scripts, folders, and environment manually | Open `run_id` and inspect `request.json`, status, and artifacts |

*Table 3. Operational effect of RAPID. The contribution is not that the same tools are launched from one screen, but that model outputs are converted into a reusable artifact substrate that supports retrospective analysis, partial reruns, and backend replacement.*

### 3.2 Claim 2: Structure-Prediction-Budgeted Surrogate Triage Reduces Structure-Prediction Use After SoluProt Gating

The surrogate-triage benchmark supports a conservative structure-prediction allocation policy. K-means bootstrap selection is most useful when AF2 labels are scarce: for Random Forest pLDDT BO uplift, K-means improves over random selection by 38% at N = 5, 19% at N = 10, and 12% at N = 20. At N = 30, the difference becomes small because random sampling is already diverse enough in the current pools. This pattern supports K-means as a cold-start safeguard rather than as evidence that it should be preferred at every label budget.

At the N = 30 operating point, Random Forest gives the highest mean pLDDT BO uplift Top-5 in the current artifact benchmark, while Ridge is strongest for SoluProt ranking and recall-oriented metrics. Because the best policy can vary by target and score emphasis, RAPID's implemented default is not a hard-coded Random Forest choice. Instead, RAPID compares the configured surrogate policies on the initial AF2-labelled bootstrap set and uses the strongest internally cross-validated policy for Top-K acquisition. Random Forest remains the conservative pLDDT-oriented reference policy in the artifact benchmark, and Ridge remains available when SoluProt-oriented ranking or recall is prioritised.

![Selection and model benchmark](figures/benchmark/fig5_model_comparison.png)

*Figure 3. Current artifact-benchmark surrogate comparison at N = 30. Random Forest is the conservative pLDDT BO-uplift reference, whereas Ridge dominates SoluProt-related ranking metrics. RAPID uses these benchmark results to define comparator policies and then selects the acquisition policy within each run by internal CV. Detailed model tables and per-target heatmaps are reported in the supplement.*

| Evidence item | Current result | Manuscript interpretation |
|---|---:|---|
| K-means vs random at N = 5 | +38% RF pLDDT BO uplift | K-means protects the cold start |
| K-means vs random at N = 30 | -1% RF pLDDT BO uplift | N = 30 is already near the diversity plateau |
| Best pLDDT BO uplift at N = 30 | RF, 0.602 | RF is the conservative pLDDT-triage reference policy |
| Best SoluProt ranking metrics | Ridge | Ridge remains a score-specific production option |
| N = 30 vs N = 80 | 93.1% of RF pLDDT uplift at 37.5% of labels | N = 30 is a cost-efficient operating point |

*Table 4. Surrogate-triage evidence condensed for the main manuscript. The full surrogate, sample-size, ensemble, and acquisition-bias analyses are reported in Supplementary Notes 3-7.*

The budget effect is explicit at the run level. The default manuscript configuration generates approximately 9,999 ProteinMPNN candidates across the three conservation tiers and applies SoluProt gating before structure-prediction triage. The budget comparison assumes that every candidate entering surrogate triage would otherwise be folded. The implemented pooled surrogate-triage schedule spends 30 calls on the K-means bootstrap set and 20 calls on surrogate-ranked Top-K candidates, for 50 AF2 calls when the pooled triage set exceeds this budget. The reduction is therefore `1 - 50/P`, where `P` is the number of candidates entering surrogate triage. Larger pools produce larger absolute savings because the triage budget remains fixed while the full-folding baseline scales with the number of candidates that pass upstream filters.

| Budget model | Without surrogate | With surrogate triage | Reduction |
|---|---:|---:|---:|
| One target run, 90 triage candidates | 90 | 50 | 44% |
| One target run, 1,000 triage candidates | 1,000 | 50 | 95% |
| One target run, 9,999 triage candidates | 9,999 | 50 | 99.5% |

*Table 5. AF2 budget model for the standard pooled surrogate-triage mode. The implemented default evaluates 30 K-means bootstrap candidates and 20 Top-K acquisitions selected by one internally cross-validated acquisition policy across the pooled conservation-tier candidate set. The "without surrogate" column assumes all candidates entering triage would otherwise be folded; it is not a claim that every generated ProteinMPNN candidate is folded. Comparator models are trained and exported for audit, but they do not add AF2 calls unless the operator explicitly changes the validation budget. This table is a budget model, not a biological enrichment result; prospective wet-lab outcomes are handled by the separate experimental-feedback evolution mode.*

The current strict paper run verifies this operating point across five CATH targets and 15 conservation-tier outputs. Across 49,946 pooled candidates entering surrogate triage, RAPID evaluated 250 AF2/ColabFold records, corresponding to a 99.5% reduction relative to folding every candidate in the triage pool. The Auto-CV selector chose Random Forest for two targets and Ridge for three targets, while the comparator predictions and fitted-model artifacts were exported for audit without increasing the AF2 budget. All five runs generated 3,333 ProteinMPNN candidates per conservation tier using chunked generation, used the GPU ESM embedding provider, and disabled fallback sequence recovery. Earlier 3RGK and 1LVM traces are retained in Supplementary Note 8 as historical implementation traces rather than as the current operating evidence. The current paper-run script for claim 2 uses the standard surrogate-triage mode rather than experimental-feedback evolution, so the computational budget claim and the wet-lab feedback interface remain separate.

### 3.3 Claim 3: Structural Context Provides a Testable Compute-Allocation Axis

The current artifact benchmark shows that target identity dominates observed design-quality variation. In the 23-target stored benchmark, target identity explains 98.8% of pLDDT variance and 96.8% of SoluProt variance. This does not prove that ProteinMPNN has no sampling headroom. It shows that, in the observed artifact set, drawing more sequences around the same target/backbone has much less variance to exploit than changing the target or structural context.

![Variance decomposition](figures/benchmark/fig10_mpnn_decomposition.png)

*Figure 4. Current artifact-benchmark variance decomposition. Per-target pLDDT distributions are tightly clustered within target and separated across targets, indicating that target or structural context is the dominant observed variance axis.*

| Surrogate target | Between-target variance | Within-target variance | ICC1 |
|---|---:|---:|---:|
| pLDDT | 86.81 | 1.11 | 0.988 |
| SoluProt | 0.0225 | 0.00077 | 0.968 |

*Table 6. Variance decomposition in the current artifact benchmark. ICC1 near 1 supports allocating some early compute to target or structural-context triage rather than only to deeper sequence sampling within one context.*

The corrected-chain structural-context ablation is consistent with this interpretation but does not support a universal generator ranking. Under matched budgets, each evaluable target-arm produced 120 ProteinMPNN designs and 30 AF2/ColabFold records. Across all eight targets, the single-backbone and selected-RFD3 arms had nearly identical mean Top-5 pLDDT values (92.58 and 92.53, respectively), with mixed target-level deltas. Among the four targets for which BioEmu-containing arms passed the RMSD gate, BioEmu increased Top-5 SoluProt modestly relative to the corresponding single-backbone runs (+0.024 on average) and reduced pairwise sequence identity (-0.105), but did not improve paired Top-5 pLDDT. These results support the claim that structural context is a measurable allocation variable, not the claim that RFD3, BioEmu, or their combination is universally superior.

![Structural-context ablation](figures/benchmark/fig12_backbone_ensemble_ablation.png)

*Figure 5. Corrected-chain structural-context ablation. Single-backbone and RFD3 arms are evaluable for eight targets, while BioEmu and RFD3+BioEmu are evaluable for the four targets that passed the pre-specified 2.0 Å target-RMSD gate. The figure is interpreted as an allocation and QC analysis, not as evidence for a universal structural-generator advantage.*

| Arm | Evaluable targets | Designs per target | AF2 records per target | Top-5 pLDDT | Top-5 SoluProt | Paired Top-5 pLDDT delta vs single |
|---|---:|---:|---:|---:|---:|---:|
| Single target backbone | 8 | 120 | 30 | 92.58 | 0.718 | reference |
| Target + BioEmu ensemble | 4 | 120 | 30 | 96.28 | 0.788 | -0.14 |
| RFD3 selected backbone | 8 | 120 | 30 | 92.53 | 0.690 | -0.05 |
| RFD3 + BioEmu ensemble | 4 | 120 | 30 | 95.44 | 0.734 | -0.98 |

*Table 7. Structural-context ablation summary. Values are target-level means over evaluable target-arm pairs and one replicate per target-arm condition. BioEmu-containing rows include four RMSD-gate-passing targets, whereas single and RFD3 rows include all eight corrected-chain targets. The final column reports paired Top-5 pLDDT contrasts within the common target subset for each arm, preventing the unpaired row means from being interpreted as a universal BioEmu or RFD3 advantage.*

## 4. Discussion

RAPID should be read as a reproducible orchestration and compute-allocation contribution. The platform’s value is not that it claims a new protein-design model, but that it makes model composition, artifact reuse, and retrospective analysis practical for solubility-aware redesign. This matters in biofoundry-scale design-test-learn settings because the number of candidate sequences, target contexts, and model versions grows faster than manual collation can support. By storing typed artifacts under stable run identifiers, RAPID turns expensive model calls into reusable data that can support new ablations without repeating the compute.

The workflow-scale implication is that RAPID changes what can be analysed after a high-throughput design campaign. In the present artifact benchmark, multiple surrogate, selection-size, diversity, and variance analyses were regenerated from the same 2,737 paired SoluProt/pLDDT records rather than from separately refolded datasets. In the representative production-scale traces, thousands of SoluProt-gated candidates were reduced to tens of AF2 evaluations while preserving the candidate identifiers needed for downstream review. These examples do not establish wet-lab performance, but they show the practical effect of the artifact contract: large computational batches become reusable experimental context rather than disposable model output folders.

The surrogate-triage result is similarly bounded. The evidence supports a structure-prediction allocation policy, not a wet-lab hit-rate claim. K-means is most useful as a cold-start diversity mechanism, Random Forest is a conservative pLDDT acquisition reference, Ridge is useful for SoluProt-oriented ranking, and N = 30 is a cost-efficient bootstrap point in the current artifact benchmark. The current implementation uses those observations to define comparator policies, then selects one acquisition policy by internal CV for each run. A retrospective guardrail analysis on accumulated CATH artifacts (Supplementary Note 9) shows that simple pooled scaling without target conditioning does not monotonically improve ranking performance, which argues against prematurely replacing per-run calibration with a global pooled model. This is a guardrail result rather than a contradiction of the platform design: under the current feature set and label volume, accumulated computational labels are useful for audit and future modelling, but they do not yet justify a transferable surrogate that supersedes target-local calibration. These findings justify RAPID's implemented default as a lightweight, run-specific orchestration policy for the expensive AF2 step after SoluProt filtering. The experimental-feedback evolution mode extends the same artifact substrate into a design-test-learn workflow by accepting objective metric values from assay records, but its biological utility must be assessed prospectively.

One plausible reason for the pooled-model guardrail is target heterogeneity. Sequence length, fold class, intrinsic disorder or low-complexity propensity, MSA depth, conservation pattern, and backbone context can all change how sequence edits map to pLDDT or soluble-expression proxies. A pooled model trained before these factors are explicitly conditioned may therefore learn target-level offsets or context-specific noise rather than a transferable acquisition rule. The same logic applies to diversity: the observed acquisition bias (Supplementary Note 6) suggests that future policies should combine predicted quality with explicit ESM-space diversity constraints, such as determinantal point processes, max-min distance filtering, or cluster-balanced Top-K selection, instead of relying on score ranking alone [26].

This framing also defines the longer-term learning path. RAPID's near-term role is local surrogate orchestration: each run creates a candidate pool, labels a small diverse subset, and fits a task-specific acquisition model. The next step is not simply to train a larger sequence generator, but to accumulate a preference dataset from redesign decisions, including AF2 labels, assay labels, paired rankings, target metadata, structural context, conservation tier, and sequence-edit histories. Only after this substrate becomes sufficiently dense should a target-conditioned preference model be treated as a performance claim. In this sense, the platform is designed for biofoundry-scale learning because it records the full redesign process, not only the final selected sequences.

The structural-context result reframes backbone and ensemble stages as allocation levers. If observed variance were mainly within a target, deeper ProteinMPNN sampling would be the primary way to spend compute. Instead, target identity dominates the stored benchmark, and the corrected-chain structural-context ablation shows target-dependent tradeoffs under matched AF2 caps. RFD3 changed outcomes for some targets but did not improve the aggregate Top-5 pLDDT relative to the single-backbone arm. BioEmu-containing arms were quantitatively evaluable only for the four targets satisfying the pre-specified RMSD gate, where they increased soluble-expression scores and sequence diversity more clearly than structural-confidence scores. This pattern argues for treating RFD3 and BioEmu as controlled exploration levers with explicit QC, rather than as default score-improvement modules.

The model-replacement claim is architectural but testable. RAPID can swap a structure predictor, inverse-folding model, solubility model, or relax backend when the replacement writes the same artifact fields. The numerical operating point should be re-estimated after such a replacement, but the analysis workflow does not need to be redesigned. This is why the paper keeps model replacement as Claim 1 rather than as a separate performance claim.

## 5. Limitations

The current evidence is computational and proxy-based. pLDDT, SoluProt, and relax scores do not establish soluble expression, thermodynamic stability, or activity without wet-lab validation. The current surrogate-triage benchmark is based on a stored 23-target QC-passing artifact set generated before the final corrected-chain CATH refresh, so it should be interpreted as component-level evidence for AF2 triage rather than as the final population estimate. The completed corrected-chain CATH archive was sufficient to test pooled surrogate accumulation, but not to show a stable pooled-model advantage over target-specific calibration; we therefore treat this result as support for the current per-run adaptive default and as motivation for future preference-dataset accumulation. The experimental-feedback evolution interface can ingest assay labels and recommend the next candidate set, but no prospective wet-lab enrichment result is claimed here. The corrected-chain structural-context ablation covers eight targets, but BioEmu-containing arms are evaluable for only four targets under the fixed RMSD gate; this is sufficient to test structural-context allocation as a workflow variable, not to claim a universal advantage for RFD3, BioEmu, or their combination. Optional diagnostic summaries are used for audit and failure review only; they are not evaluated here as autonomous mutation-policy models.

## 6. Conclusion

RAPID provides a run-scoped artifact layer for solubility-aware protein redesign. It preserves typed requests, stage outputs, status and trace records, quality-control summaries, experiment records, and final summaries so that heterogeneous model modules can be rerun, replaced, and analysed without rebuilding the workflow around each backend. On top of this infrastructure, the surrogate-triage mode reduces AF2/ColabFold evaluations for post-SoluProt candidate selection while exporting comparator-model evidence for audit.

The manuscript’s claims are intentionally limited. RAPID makes fragmented model outputs reusable, reduces structure-prediction calls under an explicit triage budget, and makes structural-context allocation testable across single, BioEmu, RFD3, and combined contexts. Experimental solubility, stability, and activity remain future validation targets. The longer-term value of RAPID is the reusable learning substrate created as computational labels, assay labels, target metadata, and structural-context decisions accumulate under the same artifact contract.

## Code, Data, and Software Availability

The public-release package includes the RAPID backend/MCP service under `pipeline-mcp/`, the static browser interface under `frontend/`, benchmark scripts under `scripts/benchmark/`, generated figures under `figures/benchmark/`, tabular results under `data/benchmark/results/`, and representative 3RGK/1LVM execution summaries under `data/case_studies/`. The corrected-chain manuscript refresh manifest is stored as `data/benchmark/results/rapid_target_manifest.csv`, and the strict five-target surrogate-triage budget summary is stored as `data/benchmark/results/surrogate_triage_budget_summary.csv` with its TeX table under `figures/benchmark/table5_surrogate_triage_budget.tex`. Runtime `.env` files, endpoint IDs, API keys, and logs are excluded. Large CATH and run-output archives should be distributed as a release artifact or S3-backed dataset rather than committed directly to a lightweight GitHub source tree.

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

[26] Kulesza, A., & Taskar, B. (2012). Determinantal Point Processes for Machine Learning. *Foundations and Trends in Machine Learning*, 5(2-3), 123-286. doi:10.1561/2200000044
