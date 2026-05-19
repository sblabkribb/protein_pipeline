# RAPID: A Reproducible Artifact Pipeline for Solubility-Aware Protein Redesign with AF2-Budgeted Surrogate Triage

*Type: Software Paper / Empirical Benchmark Contribution*

## Abstract

Solubility-aware protein redesign increasingly depends on heterogeneous AI models for sequence search, conservation analysis, backbone or conformational sampling, inverse folding, soluble-expression filtering, structure prediction, and novelty assessment. These components are powerful individually, but practical campaigns often connect them with ad hoc scripts, making runs difficult to reproduce, rerun, compare, or update when a model backend changes. We present RAPID, a reproducible artifact pipeline for integrated design that turns fragmented model outputs into a stage-aware, run-scoped experimental substrate for solubility-aware multiple-mutant redesign. RAPID preserves typed requests, intermediate artifacts, status histories, orchestration traces, evidence-agent verdicts, experiment records, and final summaries under stable run identifiers, allowing downstream analyses to be regenerated from stored artifacts rather than from repeated live model calls. We use RAPID to support three claims. First, an artifact contract and local/static interface make model replacement and retrospective analysis operational rather than manual. Second, an AF2-budgeted surrogate triage mode reduces structure-prediction use after SoluProt gating by using ESM-2 embeddings, K-means bootstrap selection, local surrogate ranking, and Top-K acquisition; in the current artifact benchmark, K-means gives its largest advantage in the small-label regime, Random Forest is the conservative default for pLDDT-oriented triage, and a four-round budget model reduces AF2 calls from 360 to 110 per target. Third, target-level variation dominates observed design-quality variation, motivating explicit tests of compute allocation across single-target, BioEmu, RFD3, and RFD3+BioEmu structural contexts rather than simply increasing sequence sampling around one backbone. RAPID also exposes an experimental-feedback evolution mode that writes candidate sets for wet-lab testing and can train the next surrogate from user-supplied objective values. The present evidence is computational and proxy-based: pLDDT, SoluProt, and relax scores do not establish wet-lab soluble expression, thermodynamic stability, or activity. RAPID is therefore positioned as reproducible infrastructure for solubility-aware redesign and compute allocation, with final biological validation left to experimental follow-up.

## 1. Introduction

Computational protein redesign has become a multi-model workflow. A practical solubility-oriented campaign may begin with MMseqs2-based sequence search, derive residue constraints from an MSA, optionally diversify structural context with RFdiffusion or BioEmu, generate multiple-mutant sequences with ProteinMPNN, filter them with a soluble-expression predictor, evaluate selected candidates with AF2 or ColabFold, and finally compare novelty or downstream developability signals [1-8]. The scientific question is often not unconstrained protein generation. It is constrained redesign: starting from an existing target or scaffold, the operator wants a tractable library of multiple-mutant variants that preserves important positions, improves computational soluble-expression likelihood, and remains structurally plausible.

This setting creates an infrastructure problem. Individual models are updated rapidly and often expose different input formats, output schemas, runtime assumptions, and failure modes. When campaigns are organised as scripts and notebooks, intermediate artifacts become difficult to audit, partial reruns become unsafe, and later model replacement can force a rewrite of the analysis code. These problems are especially costly in biofoundry-style workflows, where many targets, masking policies, backbone contexts, and scoring thresholds must be compared under finite GPU budgets.

The dominant downstream cost in such workflows is structure prediction. ProteinMPNN can generate hundreds or thousands of variants per target, and SoluProt can score them cheaply, but folding every SoluProt-passing sequence is rarely justified. The practical question is therefore not only how to generate candidates, but how to decide where expensive AF2/ColabFold evaluations should be spent. A useful platform should make this decision auditable: it should preserve the full path from input to candidate, allow the same stored results to support multiple analyses, and expose enough model-replacement structure that new backends can be tested without changing the scientific question.

We present RAPID, a reproducible artifact pipeline for integrated design. RAPID is not introduced as a new predictive model or as a universal protein-design engine. It is a model-orchestration and artifact layer specialised here for solubility-aware, structural-confidence-guided multiple-mutant redesign. The paper is organised around three claims. First, RAPID converts fragmented model outputs into a reusable, model-replaceable artifact substrate. Second, RAPID implements and benchmarks AF2-budgeted surrogate triage for post-SoluProt candidate selection. Third, RAPID makes structural-context allocation testable by comparing single-backbone, BioEmu, RFD3, and combined RFD3+BioEmu contexts under explicit design and AF2 budgets. Separately, RAPID records wet-lab outcomes and supports experimental-feedback evolution, but experimental activity or expression improvement is not claimed without prospective validation.

## 2. Methods

### 2.1 RAPID Scope and Architecture

RAPID represents each redesign campaign as a stage-aware, biofoundry-oriented orchestration run rather than as a collection of disconnected jobs. The canonical stage order is `msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty`. This order is dependency-driven. MSA construction provides conservation-derived residue constraints; optional RFD3 and BioEmu stages provide alternative backbone or conformational contexts; ProteinMPNN generates multiple-mutant sequence libraries under the active fixed-position constraints; SoluProt scores soluble-expression likelihood; AF2 or ColabFold supplies structural-confidence labels; novelty analysis compares surviving designs against sequence databases. Rosetta Relax is available as an optional post-AF2 refinement and scoring step, but it is disabled by default in the benchmark path because full relax coverage was not available for all artifact sets.

The implementation separates three planes. The control plane validates requests, resolves stage order, records status transitions, and enforces safe rerun semantics. The model-execution plane dispatches stages to local, HTTP, or RunPod-backed providers as long as each provider writes the expected artifact fields. The evidence plane contains advisory agents that read stored artifacts and emit structured verdicts, confidence values, rationales, and recovery suggestions. These agents do not silently alter mutation masks or replace the deterministic execution graph in the analyses reported here; they function as evidence-review and failure-diagnosis support.

### 2.2 Solubility-Aware Multiple-Mutant Redesign

RAPID is evaluated here as a solubility-aware redesign workflow. Conservation tiers at 30%, 50%, and 70% determine progressively constrained fixed-position sets from the MSA. These tiers do not define a single-mutation trajectory. Instead, ProteinMPNN redesigns the remaining positions jointly, producing multiple-mutant libraries under each conservation constraint. Manual residue selections from the interface enter through `fixed_positions_extra` and are unioned into the fixed-position set. Programmatic mask consensus can aggregate MSA conservation, ligand proximity, MSA quality, and query-PDB identity into advisory or applied fixed positions, depending on whether consensus application is enabled.

The default scoring path treats SoluProt as a cheap soluble-expression gate before AF2/ColabFold. pLDDT is used as a structural-confidence proxy for short-listing, not as evidence of experimental stability. When relax is enabled, its energy scores can be included as a penalty term in the composite ranking, but the manuscript does not claim thermodynamic stability improvement without wet-lab measurement.

![RAPID workflow](figures/benchmark/fig1_pipeline_overview.png)

*Figure 1. RAPID stage order and diversification levers. The default workflow is solubility-aware multiple-mutant redesign: MSA-derived constraints guide ProteinMPNN sequence generation, SoluProt filters soluble-expression likelihood, and AF2/ColabFold is reserved for structurally plausible short lists. RFD3 and BioEmu provide structural-context diversification, while conservation tiers vary the number and placement of jointly redesigned positions.*

### 2.3 Artifact Contract, Interface, and Model Replacement

Each RAPID run writes a typed request, stage outputs, status records, orchestration trace events, evidence-agent records, experiment records, and final summaries under a stable run identifier. The run identifier is the unit of provenance. This structure supports controlled partial reruns: downstream thresholds or ranking steps can be repeated from stored artifacts, while upstream input changes invalidate unsafe reuse. The same contract is used by benchmark scripts, so model-comparison and surrogate-triage analyses can be regenerated from stored outputs without refolding the candidate set for every ablation.

The artifact contract is defined around shared downstream fields rather than around a single model implementation (Table 1). This is the basis of the model-replacement claim: replacement is not asserted because every possible backend has already been benchmarked, but because the downstream analysis code consumes stable artifacts rather than model-specific folders.

| Replaceable module | Tested or implemented options | Shared artifact fields | Downstream reuse |
|---|---|---|---|
| Structural context | Single target, BioEmu, RFD3, RFD3+BioEmu | `backbone_id`, source, PDB path, sequence map | ProteinMPNN, SoluProt, AF2 |
| Structure scorer | ColabFold/AF2 | pLDDT, ranking confidence, output PDB | Surrogate benchmark, composite score |
| Solubility scorer | SoluProt | Solubility score, pass/fail records | Gate, composite score |
| Surrogate | RF, Ridge, XGBoost, LightGBM, rank-mean | Predicted pLDDT or rank | Top-K acquisition |
| Relax | Optional Rosetta Relax | Relax score, penalty flag | Composite score |

*Table 1. Replaceable modules and shared artifact fields in RAPID. The table separates the implemented artifact contract from any claim that all possible replacement models have already been validated.*

The browser interface is part of this reproducibility model. Basic mode exposes the end-to-end solubility-aware library workflow with a small number of output-size and threshold controls. Advanced mode exposes start and stop points, optional backbone and ensemble stages, masking controls, AF2 budget parameters, and provider choices. The interface is distributed as static assets over the backend API, allowing users to run RAPID locally or on a GPU server without relying on a hosted service. This packaging matters for publication because it makes the artifact contract inspectable by users rather than hidden behind a private deployment.

### 2.4 AF2-Budgeted Surrogate Triage and Experimental Evolution

RAPID separates two related uses of surrogates. The first is a computational AF2-budgeted triage mode used in the benchmark (Figure 2). ProteinMPNN first generates a candidate pool across conservation tiers, and SoluProt scores every candidate. SoluProt-passing candidates are embedded with mean-pooled ESM-2 8M embeddings [4]. K-means selects a diverse bootstrap training set, AF2 labels those candidates, and a local surrogate is trained to rank the remaining SoluProt-passing pool by predicted pLDDT. AF2 then evaluates only the surrogate-ranked Top-K candidates. This mode is a compute-allocation policy for structure prediction, not evidence of experimental activity or expression.

The production triage default uses 30 K-means-selected bootstrap labels and 20 Top-K AF2 acquisitions. The benchmark evaluates Random Forest, Ridge, GP-RBF, XGBoost, LightGBM, KNN, MLP, and random selection, with Random Forest and Ridge retained as the primary production options because they represent different score-specific operating points.

The second use is an experimental-feedback evolution mode. In this mode, RAPID generates a SoluProt-gated candidate pool and writes `experiment_request.csv` when no wet-lab labels are available. Users can then record assay outcomes through the experiment interface using candidate or sequence identifiers, metric names, metric values, units, directions, and replicate identifiers. When labels for a specified objective metric are present in `experiments.jsonl`, RAPID trains a local surrogate on the labelled sequences and writes `next_candidates.csv` for the next design-test-learn cycle. A legacy `in_silico_af2` label source preserves the earlier AF2-oracle behaviour for computational comparisons, but the default evolution label source is experimental feedback.

![Active-learning loop](figures/benchmark/fig2_active_learning_loop.png)

*Figure 2. AF2-budgeted surrogate triage loop. K-means selects a diverse AF2-labelled bootstrap set from SoluProt-passing candidates, a local surrogate ranks the remaining pool, and AF2/ColabFold is reserved for Top-K acquisitions. Experimental-feedback evolution uses the same candidate and embedding contract but learns from user-recorded wet-lab objective values rather than treating AF2 as a biological oracle.*

### 2.5 Current Artifact Benchmark and Statistical Analysis

The current stored artifact benchmark contains 2,737 paired SoluProt and pLDDT records from 23 QC-passing CATH runs. These data were generated before the final corrected-chain CATH refresh and are therefore used in the main text as component-level evidence for AF2-budgeted surrogate triage rather than as the final population estimate for RAPID. Runs with fallback sequences, invalid amino-acid records, missing conservation tiers, or insufficient positive pLDDT records were excluded from that artifact benchmark. The full pre-fix 73-run archive and QC details are reported in the supplement.

The primary surrogate-triage metrics are Spearman rank correlation, Top-K recall, and BO uplift Top-K. BO uplift measures the difference between the mean observed score of the surrogate-selected Top-K and the mean score of K random draws from the same held-out pool. Paired comparisons use Wilcoxon signed-rank tests with Holm correction, and uncertainty is estimated by cluster bootstrap with target as the cluster. Variance decomposition uses a one-way ANOVA intraclass correlation coefficient to estimate how much score variation is attributable to target identity.

### 2.6 Structural-Context Ablation Protocol

The structural-context claim is tested by running matched design and AF2 budgets across four arms: the original target backbone, target plus BioEmu conformational samples, a selected RFD3 backbone, and a combined RFD3+BioEmu ensemble. The updated RAPID ablation script records the planned backbone count, planned design count, RFD3 settings, BioEmu settings, and AF2 budget for every target-arm pair. Each target-arm run caps AF2 at 30 candidates, so differences are interpreted as structural-context allocation effects rather than as unrestricted additional folding.

| Arm | Structural context tested | Interpretation |
|---|---|---|
| Single | Original target backbone | Baseline redesign around one input structure |
| BioEmu | Conformational ensemble around the target backbone | Same topology with conformational variation |
| RFD3 | Selected/generated RFD3 backbone | Altered backbone geometry or topology context |
| RFD3 + BioEmu | BioEmu ensemble seeded from an RFD3 backbone | Combined backbone diversification and conformational sampling |

*Table 2. Structural-context arms used for RAPID compute-allocation analysis. The arms are designed as controlled exploration modes under matched AF2 caps, not as a priori quality-ranking assumptions.*

The present structural-context analysis includes a three-target RFD3 pilot comparing a single target backbone, one selected RFD3 backbone, and a three-backbone RFD3 ensemble. This pilot is retained as preliminary evidence that structural context changes target-dependent outcomes. A corrected-chain four-arm RAPID ablation protocol has also been implemented for the expanded data refresh, using the target manifest generated from corrected-chain CATH inputs.

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

### 3.2 Claim 2: AF2-Budgeted Surrogate Triage Reduces Structure-Prediction Use After SoluProt Gating

The surrogate-triage benchmark supports a conservative AF2 allocation policy. K-means bootstrap selection is most useful when AF2 labels are scarce: for Random Forest pLDDT BO uplift, K-means improves over random selection by 38% at N = 5, 19% at N = 10, and 12% at N = 20. At N = 30, the difference becomes small because random sampling is already diverse enough in the current pools. This pattern supports K-means as a cold-start safeguard rather than as evidence that it should be preferred at every label budget.

At the N = 30 operating point, Random Forest gives the highest mean pLDDT BO uplift Top-5 in the current artifact benchmark, while Ridge is strongest for SoluProt ranking and recall-oriented metrics. Because SoluProt is directly scored for every candidate in RAPID, the primary surrogate bottleneck is pLDDT-oriented AF2 triage. RAPID therefore uses Random Forest as the conservative default for pLDDT-driven acquisition and retains Ridge as an option when SoluProt ranking or recall is prioritised.

![Selection and model benchmark](figures/benchmark/fig5_model_comparison.png)

*Figure 3. Current artifact-benchmark surrogate comparison at N = 30. Random Forest is the conservative pLDDT BO-uplift default, whereas Ridge dominates SoluProt-related ranking metrics. Detailed model tables and per-target heatmaps are reported in the supplement.*

| Evidence item | Current result | Manuscript interpretation |
|---|---:|---|
| K-means vs random at N = 5 | +38% RF pLDDT BO uplift | K-means protects the cold start |
| K-means vs random at N = 30 | -1% RF pLDDT BO uplift | N = 30 is already near the diversity plateau |
| Best pLDDT BO uplift at N = 30 | RF, 0.602 | RF is the conservative AF2-triage default |
| Best SoluProt ranking metrics | Ridge | Ridge remains a score-specific production option |
| N = 30 vs N = 80 | 93.1% of RF pLDDT uplift at 37.5% of labels | N = 30 is a cost-efficient operating point |

*Table 4. Surrogate-triage evidence condensed for the main manuscript. The full surrogate, sample-size, and acquisition-bias analyses are moved to supplementary material.*

The budget effect is explicit. Folding every candidate in a 90-candidate SoluProt-gated pool for four repeated triage cycles would require 360 AF2 calls. The RAPID surrogate schedule spends 50 AF2 calls in the bootstrap cycle and 20 calls in each of the next three acquisition cycles, for 110 calls total. This is a 69% reduction in AF2 evaluations and approximately a 3.3-fold reduction in AF2 GPU time when per-call runtime is fixed.

| Budget model | Without surrogate | With surrogate triage | Reduction |
|---|---:|---:|---:|
| Round 1 | 90 | 50 | 44% |
| Rounds 2-4 total | 270 | 60 | 78% |
| Four-round total | 360 | 110 | 69% |

*Table 5. AF2 budget model. The first cycle evaluates 30 K-means bootstrap candidates and 20 Top-K acquisitions. Subsequent cycles reuse the archived surrogate and evaluate only 20 Top-K candidates per cycle.*

Two representative production-scale in-silico traces verify that the computational triage path is implemented end to end. The 3RGK run evaluated 94 AF2 records from 8,000 SoluProt-gated candidates, and the 1LVM run evaluated 49 AF2 records from 8,000 SoluProt-gated candidates. These traces demonstrate pool generation, SoluProt gating, ESM embedding, K-means bootstrap labelling, surrogate ranking, AF2 acquisition, and final design selection within the stored artifact model. They are not treated as paired biological validation because they cover two targets, use computational pLDDT labels, and have different Top-K settings. Experimental-feedback evolution is implemented as a separate design-test-learn interface that consumes assay values recorded after physical testing.

### 3.3 Claim 3: Structural Context Provides a Testable Compute-Allocation Axis

The current artifact benchmark shows that target identity dominates observed design-quality variation. In the 23-target stored benchmark, target identity explains 98.8% of pLDDT variance and 96.8% of SoluProt variance. This does not prove that ProteinMPNN has no sampling headroom. It shows that, in the observed artifact set, drawing more sequences around the same target/backbone has much less variance to exploit than changing the target or structural context.

![Variance decomposition](figures/benchmark/fig10_mpnn_decomposition.png)

*Figure 4. Current artifact-benchmark variance decomposition. Per-target pLDDT distributions are tightly clustered within target and separated across targets, indicating that target or structural context is the dominant observed variance axis.*

| Surrogate target | Between-target variance | Within-target variance | ICC1 |
|---|---:|---:|---:|
| pLDDT | 86.81 | 1.11 | 0.988 |
| SoluProt | 0.0225 | 0.00077 | 0.968 |

*Table 6. Variance decomposition in the current artifact benchmark. ICC1 near 1 supports allocating some early compute to target or structural-context triage rather than only to deeper sequence sampling within one context.*

The completed three-target RFD3 pilot is consistent with this interpretation but is not powered as a general performance claim. Averaged over three CATH targets, the selected-RFD3 arm had higher Top-5 pLDDT than the single-backbone arm, whereas the RFD3-ensemble arm was intermediate for pLDDT and slightly higher for Top-5 SoluProt. The target-level pattern was mixed: RFD3 helped a low-pLDDT case but did not uniformly improve already high-confidence targets. This supports the claim that structural-context exploration is measurable and target-dependent, not the claim that one structural generator is universally superior.

![Structural-context pilot](figures/benchmark/fig12_backbone_ensemble_ablation.png)

*Figure 5. Three-target structural-context pilot. The single-target, selected-RFD3, and RFD3-ensemble arms were compared under matched AF2 caps. The updated RAPID implementation extends this protocol to BioEmu and RFD3+BioEmu arms for the corrected-chain data refresh.*

| Arm | Designs per target | AF2 records per target | Top-5 pLDDT | Top-5 SoluProt |
|---|---:|---:|---:|---:|
| Single target backbone | 120 | 30 | 84.76 | 0.756 |
| RFD3 selected backbone | 120 | 30 | 87.58 | 0.725 |
| RFD3 ensemble, 3 backbones | 117 | 30 | 85.58 | 0.759 |

*Table 7. Structural-context pilot summary. Values are target-level means over three CATH targets and one replicate per target-arm condition. The pilot supports structural-context exploration as a measurable workflow variable, not a universal performance advantage for a particular generator.*

## 4. Discussion

RAPID should be read as a reproducible orchestration and compute-allocation contribution. The platform’s value is not that it claims a new protein-design model, but that it makes model composition, artifact reuse, and retrospective analysis practical for solubility-aware redesign. This matters in biofoundry settings because the number of candidate sequences, target contexts, and model versions grows faster than manual collation can support. By storing typed artifacts under stable run identifiers, RAPID turns expensive model calls into reusable data that can support new ablations without repeating the compute.

The surrogate-triage result is similarly bounded. The evidence supports an AF2-allocation policy, not a wet-lab hit-rate claim. K-means is most useful as a cold-start diversity mechanism, Random Forest is a conservative pLDDT acquisition default, Ridge is useful for SoluProt-oriented ranking, and N = 30 is a cost-efficient bootstrap point in the current artifact benchmark. These findings justify the implemented budget model because they directly address the expensive AF2 step after SoluProt filtering. The experimental-feedback evolution mode extends the same artifact substrate into a design-test-learn workflow by accepting objective metric values from assay records, but its biological utility must be assessed prospectively.

The structural-context result reframes backbone and ensemble stages as allocation levers. If observed variance were mainly within a target, deeper ProteinMPNN sampling would be the primary way to spend compute. Instead, target identity dominates the current stored benchmark, and the RFD3 pilot shows target-dependent tradeoffs. The next analysis should therefore compare single, BioEmu, RFD3, and RFD3+BioEmu contexts across a corrected-chain target set rather than treating RFD3 or BioEmu as default score-improvement modules. The updated RAPID scripts now support that four-arm comparison.

The model-replacement claim is architectural but testable. RAPID can swap a structure predictor, inverse-folding model, solubility model, or relax backend when the replacement writes the same artifact fields. The numerical operating point should be re-estimated after such a replacement, but the analysis workflow does not need to be redesigned. This is why the paper keeps model replacement as Claim 1 rather than as a separate performance claim.

## 5. Limitations

The current evidence is computational and proxy-based. pLDDT, SoluProt, and relax scores do not establish soluble expression, thermodynamic stability, or activity without wet-lab validation. The current surrogate-triage benchmark is based on a stored 23-target QC-passing artifact set generated before the final corrected-chain CATH refresh, so it should be interpreted as component-level evidence for AF2 triage rather than as the final population estimate. The experimental-feedback evolution interface can ingest assay labels and recommend the next candidate set, but no prospective wet-lab enrichment result is claimed here. The completed structural-context pilot covers three targets and does not include BioEmu arms; it is sufficient to motivate the four-arm RAPID ablation but not to claim a universal advantage for RFD3, BioEmu, or their combination. The evidence-agent layer is evaluated here as structured decision support and auditability infrastructure, not as an autonomous mutation-policy model.

## 6. Conclusion

RAPID addresses a practical gap between rapidly changing protein-design models and the reproducible infrastructure needed to use them in solubility-aware redesign campaigns. It preserves run-scoped artifacts, supports controlled partial reruns, exposes the workflow through a packageable static interface and backend API, and keeps model interfaces replaceable. On top of this infrastructure, an AF2-budgeted surrogate-triage mode uses SoluProt gating, K-means bootstrap selection, local surrogate ranking, and Top-K acquisition to reduce structure-prediction calls. A separate experimental-feedback evolution mode records assay outcomes and uses those labels to recommend the next candidate set.

The manuscript’s central claims are intentionally limited. RAPID makes fragmented model outputs reusable; it reduces AF2/ColabFold evaluations for post-SoluProt triage; and it makes structural-context allocation testable across single, BioEmu, RFD3, and combined contexts. These claims are suitable for a software and empirical benchmark paper because they are tied to stored artifacts, explicit budgets, and reproducible scripts. Experimental solubility, stability, and activity remain future validation targets rather than claims of the present work, even though the software now provides the data path needed to incorporate those measurements in subsequent rounds.

## Code, Data, and Software Availability

The public-release package includes the RAPID backend/MCP service under `pipeline-mcp/`, the static browser interface under `frontend/`, benchmark scripts under `scripts/benchmark/`, generated figures under `figures/benchmark/`, tabular results under `data/benchmark/results/`, and representative 3RGK/1LVM execution summaries under `data/case_studies/`. The corrected-chain manuscript refresh manifest is stored as `data/benchmark/results/rapid_target_manifest.csv` in the public-release package. Runtime `.env` files, endpoint IDs, API keys, and logs are excluded. Large CATH and run-output archives should be distributed as a release artifact or S3-backed dataset rather than committed directly to a lightweight GitHub source tree.

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
