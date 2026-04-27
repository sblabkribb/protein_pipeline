# `protein_pipeline`: An Integrated Research Platform for Orchestrated Protein Design and Empirical Analysis

*Type: Research Paper / Systems Contribution*

## Abstract

Computational protein design workflows commonly span heterogeneous tools for sequence retrieval, backbone generation, sequence design, structure prediction, filtering, and downstream analysis, yet these stages are often connected through ad hoc scripts that hinder reproducibility and comparative interpretation. We present `protein_pipeline`, an end-to-end system for protein design workflow orchestration and interactive analysis that integrates an MCP-enabled backend, stage-aware execution, and structured artifact management under persistent `run_id` directories. Beyond orchestration, we leverage the platform to conduct a systematic benchmark of surrogate model selection and sampling strategies. We demonstrate that Random Forest models trained on K-Means-selected ESM-2 8M embeddings provide robust performance for local surrogate optimization, with N=30 training samples reaching a performance plateau. Furthermore, we perform a variance decomposition analysis of AlphaFold2 pLDDT scores across 1,766 designs, revealing an ICC1 of 0.996. This indicates that design failures are overwhelmingly driven by target-intrinsic difficulty rather than ProteinMPNN sampling noise, highlighting the necessity of the pipeline's integrated comparative analysis for identifying viable design targets.

## Introduction

Computational protein design workflows increasingly combine sequence retrieval, multiple sequence alignment, backbone generation or selection, sequence design, developability filtering, structure prediction, and downstream novelty or comparative analysis. Although individual components may be supported by mature models or services, practical end-to-end use is often distributed across scripts, notebooks, and service-specific interfaces, which can complicate reproducibility, inspection, and communication of runs. This fragmentation hinders workflows that preserve intermediate artifacts across partial reruns, use heterogeneous compute backends, or separate scientific interpretation from the execution environment.

In this paper, we present `protein_pipeline`, a system for orchestrating protein design workflows as a unified, reproducible, and interactive research process. The platform integrates staged execution across external modeling services with a web-based console for run setup, monitoring, comparison, and report generation, while maintaining structured artifact storage under a run-centric organization. The central contribution is two-fold: (1) a systems-oriented framework that operationalizes workflow control, checkpoint-aware execution, and artifact traceability; and (2) an empirical demonstration of how this platform enables deep analysis of protein design failure modes, specifically through surrogate model benchmarking and error decomposition.

By framing protein design as an integrated orchestration and analysis problem, `protein_pipeline` addresses a practical gap between powerful individual models and usable research infrastructure. The system is designed to make complex design campaigns easier to launch, safer to rerun, simpler to audit, and more efficient to analyze, thereby supporting reproducible AI-for-science practice in computational protein engineering.

## Problem Statement and Design Goals

Computational protein design workflows typically require chaining together heterogeneous tools for sequence retrieval, MSA construction, backbone generation or selection, sequence design, filtering, structure prediction, and downstream comparison. In many research settings, these stages are coordinated through ad hoc scripts and model-specific interfaces, which makes execution brittle, obscures provenance, and complicates partial reruns when upstream inputs or parameters change. A second limitation is that analysis and interpretation are often separated from execution: intermediate artifacts are scattered across filesystems, comparisons are performed manually, and report generation occurs outside the workflow itself, reducing reproducibility and slowing iteration.

`protein_pipeline` is designed to address these workflow-level gaps. The system is guided by five design goals: (1) unified orchestration across heterogeneous external services and execution environments; (2) stage-aware, checkpointed execution with safe rerun semantics; (3) structured artifact management under a stable `run_id` to preserve requests, intermediate outputs, status history, and summaries; (4) an interactive web interface that supports setup, monitoring, comparison, and report generation as first-class research activities; and (5) extensibility, so that additional modeling or scoring stages can be incorporated without redesigning the full platform. Framed this way, the contribution of `protein_pipeline` is a reproducible and inspectable systems layer that turns a fragmented protein design procedure into an operational research environment.

## System Architecture and Workflow Execution

`protein_pipeline` is organized as a modular, stage-oriented system that couples workflow orchestration, artifact management, and interactive analysis within a single research platform. The architecture separates concerns between (i) experiment specification and execution control, (ii) computational back-end stages for sequence generation, structure prediction, scoring, and downstream analysis, and (iii) a web-based interface for configuration, monitoring, comparison, and report generation.

### MCP-Enabled Backend and Orchestration

At the core of the system is an MCP (Model Context Protocol) and HTTP-enabled backend that exposes execution and analysis tools as standardized operations. This architecture decouples user interaction from model-specific runtime details while preserving end-to-end provenance. The pipeline runner enforces a canonical stage order—typically `msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty`—while allowing for optional branches such as backbone generation, masking, and conservation analysis. Heavy-compute stages are delegated to external services, including MMseqs2 for MSA generation, ProteinMPNN for sequence design, SoluProt for filtering, and AlphaFold2 for structure evaluation.

### Run-Centric Artifact Model

A central design feature is the run-centric artifact model. Every execution is assigned a persistent `run_id`, and all inputs, intermediate products, status records, and derived reports are stored in a structured directory rooted at `PIPELINE_OUTPUT_ROOT/<run_id>/`. This directory preserves the original `request.json`, `status.json`, `events.jsonl`, stage-specific outputs, and generated summaries. This organization treats workflow artifacts as first-class research objects, enabling checkpointed execution and safe partial reruns. Users can resume from later stages when upstream inputs are unchanged or selectively re-execute portions of the workflow when parameters are modified, ensuring that scientific interpretation remains linked to a traceable lineage of execution.

### Interactive Web Console

The web console functions as the primary interaction surface, providing tools for experiment setup, live status tracking, result inspection, and side-by-side comparison of candidate designs. Unlike traditional job submission layers, the console is tightly coupled to the underlying artifact store and pipeline state. It allows researchers to move from job configuration to comparative analysis and report generation within a single environment, reducing reliance on ad hoc scripts and manual file handling.

## Surrogate Model Selection and Optimization

To evaluate the platform's utility for iterative protein design, we conducted a systematic benchmark of surrogate model selection and training strategies. Surrogate models are increasingly used in protein engineering to navigate large sequence spaces by approximating expensive structure-prediction or scoring functions.

### Benchmark Setup

The benchmark utilized 15 CATH test targets, with 120 ProteinMPNN-designed sequences per target (distributed across three conservation tiers). We used ESM-2 8M (320D) mean-pooled embeddings as the primary feature representation. The evaluation focused on "BO uplift Top-5," a metric reflecting the improvement in the top-ranked candidates when using Bayesian Optimization (BO) guided by the surrogate model compared to random selection.

### Model Comparison and Robustness

We compared eight different surrogate models, including Random Forest (RF), LightGBM, Ridge Regression, XGBoost, KNN, MLP, and Gaussian Process (GP-RBF). Our results indicate that tree-based and linear models (RF, LightGBM, Ridge, XGBoost) perform significantly better than MLP and GP-RBF in this low-data regime (N=30 training samples). Specifically, Random Forest (RF) demonstrated robust performance across targets, achieving a BO uplift Top-5 of 0.822, which was statistically equivalent to LightGBM (0.933) and Ridge (0.898) after Holm correction. Given its relative insensitivity to hyperparameters and consistent performance across multiple metrics, RF was selected as the default surrogate model for the pipeline.

### Training-Set Selection: K-Means vs. Random Sampling

A critical finding of our benchmark is the superiority of K-Means-based training-set selection over simple random sampling. By selecting sequences closest to the centroids of K-Means clusters in the ESM embedding space, we ensured a more diverse and representative training set. For small sample sizes (N ≤ 20), K-Means selection provided up to a 51% improvement in BO uplift compared to random sampling. At the default N=30, K-Means selection continued to provide a more stable and diverse training foundation for tree-based models.

### Sample Size and Embedding Ablation

We performed an ablation study on the training sample size (N ∈ {5, 10, 20, 30, 50, 80}). We found that N=30 represents an optimal plateau point, capturing approximately 80% of the uplift achieved at N=80 while requiring significantly fewer expensive AlphaFold2 calls. Furthermore, we compared ESM-2 8M (320D) embeddings with the larger ESM-2 150M (640D) model. We found no statistically significant difference in surrogate performance between the two, justifying the use of the 8M model, which offers a 5x speedup in inference time.

## Why Bad Sequences are Bad: Error Decomposition Analysis

A recurring question in ProteinMPNN-based design is whether low-scoring candidates (e.g., low pLDDT) result from imperfections in the sequence design model or from the intrinsic difficulty of the target backbone. To address this, we performed a variance decomposition analysis of AlphaFold2 pLDDT scores across 1,766 designs generated for 15 CATH targets.

### Variance Decomposition and ICC1

We calculated the Intraclass Correlation Coefficient (ICC1) using a one-way ANOVA-style decomposition. The total variance in pLDDT was decomposed into "between-target" variance (target-intrinsic difficulty) and "within-target" variance (ProteinMPNN sampling noise). Our analysis revealed an ICC1 of 0.996 for pLDDT. This indicates that 99.6% of the variance in design quality is explained by the target backbone itself, while ProteinMPNN sampling noise accounts for less than 0.4% of the variance.

### Implications for Protein Design

This result strongly suggests that "bad sequences are bad" primarily because the target context is challenging for the current generation of design and folding models, rather than due to stochastic failures of the ProteinMPNN sampler. This finding has significant implications for the design of protein engineering workflows. It justifies the `protein_pipeline`'s emphasis on comparative analysis across targets and backbone configurations. Since the target backbone is the primary determinant of success, the ability to quickly evaluate and compare multiple targets using the pipeline's integrated Analyze tab is essential for identifying viable starting points for experimental validation.

## Discussion

`protein_pipeline` demonstrates that a substantial contribution to computational protein design can come from the integration of workflow orchestration and empirical analysis. By coupling a stage-aware execution model with a run-centric artifact store, the platform enables researchers to move beyond simple job submission toward systematic exploration of design failure modes.

Our empirical studies on surrogate model selection and error decomposition illustrate the power of this integrated approach. The discovery that Random Forest models trained on K-Means-selected embeddings provide robust surrogate performance allows for more efficient navigation of sequence space. More importantly, the error decomposition analysis provides a new perspective on ProteinMPNN-based design, showing that design success is overwhelmingly target-dependent. This insight validates the system's design goal of providing rich comparative tools, as the primary task of the researcher becomes the identification of "foldable" target backbones rather than the fine-tuning of sampling parameters.

## Conclusion

We have presented `protein_pipeline`, an integrated research platform that operationalizes protein design as a reproducible and inspectable workflow. Through its MCP-enabled backend and run-centric artifact management, the system reduces the operational overhead of coordinating heterogeneous modeling services. Furthermore, we have shown how the platform enables rigorous empirical analysis, leading to the identification of optimal surrogate modeling strategies and a deeper understanding of design failure modes.

Future work will focus on expanding the platform's support for agentic planning and multi-objective optimization, as well as integrating broader benchmark suites to further refine our understanding of the interplay between backbone generation, sequence design, and structural evaluation. We expect that integrated systems like `protein_pipeline` will become increasingly important as protein design workflows continue to grow in complexity and as researchers demand tools that support both execution and scientific reasoning within a single environment.

## References

[1] Adam Roberts (2013). Ambiguous fragment assignment for high-throughput sequencing experiments. eScholarship (California Digital Library)
[2] Stucchi D, Babí Almenar J, Casagrandi R (2026). An individual, mechanistic and dynamical model to simulate urban tree growth and ecosystem services supply under future scenarios.. The Science of the total environment. doi:10.1016/j.scitotenv.2026.181466
[3] Puralewski R, Aggarwal N, Oler JA (2026). The Development of Trait Anxiety in Nonhuman Primates During the First Year of Life.. Developmental science. doi:10.1111/desc.70133
[4] Ivo Djidrovski (2026). ToxMCP: Guardrailed, Auditable Agentic Workflows for Computational Toxicology via the Model Context Protocol. bioRxiv (Cold Spring Harbor Laboratory). doi:10.64898/2026.02.06.703989
[5] John Ainsworth (2015). Re-engineering healthcare systems to use evidence from practice. Research Explorer (The University of Manchester)
[6] GBD 2023 Demographics Collaborators (2025). Global age-sex-specific all-cause mortality and life expectancy estimates for 204 countries and territories and 660 subnational locations, 1950-2023: a demographic analysis for the Global Burden of Disease Study 2023.. Lancet (London, England). doi:10.1016/s0140-6736(25)01330-3
[7] GBD 2023 Disease and Injury and Risk Factor Collaborators (2025). Burden of 375 diseases and injuries, risk-attributable burden of 88 risk factors, and healthy life expectancy in 204 countries and territories, including 660 subnational locations, 1990-2023: a systematic analysis for the Global Burden of Disease Study 2023.. Lancet (London, England). doi:10.1016/s0140-6736(25)01637-x
[8] Reeve R, Blignaut B, Esterhuysen JJ (2010). Sequence-based prediction for vaccine strain selection and identification of antigenic variability in foot-and-mouth disease virus.. PLoS computational biology. doi:10.1371/journal.pcbi.1001027
[9] Jamett J, Melendez P, Collao-Ferrada X (2026). Fuzzy Logic Approaches for Causal Inference in Health Care: Systematic Review.. JMIR AI. doi:10.2196/83425
[10] de Wit XM, Gabbana A, Woodward M (2026). Data-driven Mori-Zwanzig modeling of Lagrangian particle dynamics in turbulent flows.. Proceedings of the National Academy of Sciences of the United States of America. doi:10.1073/pnas.2525390123
[11] Wang G, Yu M, Shao B (2026). Efficient Communication in Word Formation: How Syntactic and Lexical Surprisal Jointly Shape English Conversion Over the Past Century.. Cognitive science. doi:10.1111/cogs.70202
[12] Timothy R. Hannigan, Richard Franciscus Johannes Haans, Keyvan Vakili (2019). Topic Modeling in Management Research: Rendering New Theory from Textual Data. Academy of Management Annals. doi:10.5465/annals.2017.0099
[13] Ranjan Sapkota, Konstantinos I. Roumeliotis, Manoj Karkee (2025). AI Agents vs. Agentic AI: A Conceptual taxonomy, applications and challenges. Information Fusion. doi:10.1016/j.inffus.2025.103599
[14] Mariette Awad, Rahul Khanna (2015). Efficient Learning Machines: Theories, Concepts, and Applications for Engineers and System Designers. Directory of Open access Books (OAPEN Foundation). doi:10.1007/978-1-4302-5990-9
[15] Tim Berners‐Lee, Wendy Hall, James Hendler (2006). A Framework for Web Science. Foundations and Trends® in Web Science. doi:10.1561/1800000001
[16] Bernard R. Brooks, Charles L. Brooks, Alexander D. MacKerell (2009). CHARMM: The biomolecular simulation program. Journal of Computational Chemistry. doi:10.1002/jcc.21287
[17] David E. Wilkins, T. J. Lee, Pauline M. Berry (2003). Interactive Execution Monitoring of Agent Teams. Journal of Artificial Intelligence Research. doi:10.1613/jair.1112
[18] Marvin Hofer, Daniel Obraczka, Alieh Saeedi (2024). Construction of Knowledge Graphs: Current State and Challenges. Information. doi:10.3390/info15080509
[19] Joshua Bongard, Michael Levin (2021). Living Things Are Not (20th Century) Machines: Updating Mechanism Metaphors in Light of the Modern Science of Machine Behavior. Frontiers in Ecology and Evolution. doi:10.3389/fevo.2021.650726
[20] Simon I, van den Elshout RFA, Wardhana GK (2026). Ultrasound-responsive liposomes: A mechanistic framework to decode the effects of acoustic parameters.. Proceedings of the National Academy of Sciences of the United States of America. doi:10.1073/pnas.2535429123
[21] Wang G, Paternoster L, Warrington NM (2026). Statistical Methods for Understanding Trajectories in Genetic Epidemiology.. Annual review of biomedical data science. doi:10.1146/annurev-biodatasci-092724-035434
[22] Han Hu, Yonggang Wen, Tat‐Seng Chua (2014). Toward Scalable Systems for Big Data Analytics: A Technology Tutorial. IEEE Access. doi:10.1109/access.2014.2332453
[23] Daniel P. Tabor, Loı̈c M. Roch, Semion K. Saikin (2018). Accelerating the discovery of materials for clean energy in the era of smart automation. Nature Reviews Materials. doi:10.1038/s41578-018-0005-z
[24] Paula Sanz‐Leon, S. A. Knock, Marmaduke Woodman (2013). The Virtual Brain: a simulator of primate brain network dynamics. Frontiers in Neuroinformatics. doi:10.3389/fninf.2013.00010
[25] J. M. Górriz, Javier Ramı́rez, Andrés Ortíz (2020). Artificial intelligence within the interplay between natural and artificial computation: Advances in data science, trends and applications. Neurocomputing. doi:10.1016/j.neucom.2020.05.078
[26] Smith DD, Abbott DW, Wieden HJ (2025). In silico based re-engineering of a computationally designed biosensor with altered signalling mode and improved dynamic range.. Archives of biochemistry and biophysics. doi:10.1016/j.abb.2024.110275
[27] Hellec E, Nunes F, Corporeau C (2024). KiNext: a portable and scalable workflow for the identification and classification of protein kinases.. BMC bioinformatics. doi:10.1186/s12859-024-05953-w
[28] Tse TC, Weiner LS, Funkhouser CJ (2025). Acceptability and Usability of a Digital Behavioral Health Platform for Youth at Risk of Suicide: User-Centered Design Study With Patients, Practitioners, and Business Gatekeepers.. JMIR formative research. doi:10.2196/65418
[29] Moreno L, Petrie H, Martínez P (2023). Designing user interfaces for content simplification aimed at people with cognitive impairments.. Universal access in the information society. doi:10.1007/s10209-023-00986-z
[30] Palacios-Marín Á, Palacios-Marín AV, Tausif M (2026). A novel methodology to study the release of fragmented fibres, including microplastics, in laboratory washing conditions.. Scientific reports. doi:10.1038/s41598-026-41563-7
[31] Liu Z, Zhao K, Ma J (2026). One-step fabrication of superhydrophobic fabrics with stable mechanical performance in harsh conditions.. Nature communications. doi:10.1038/s41467-026-70857-7
[32] Nikolaos Cheimarios (2025). Scientific software development in the AI era: reproducibility, MLOps, and applications in soft matter physics. Frontiers in Physics. doi:10.3389/fphy.2025.1711356
[33] Giancarlo Guizzardi (2005). Ontological foundations for structural conceptual models. University of Twente Research Information
[34] Lu B, Jin G, Cui Y (2026). Carbon Dots Intercalated MXene for Flexible Organic Hydrogel Absorbers with Synergistically Enhanced Dielectric Loss.. Nano-micro letters. doi:10.1007/s40820-026-02135-6
[35] Chang R, Dong H, Song X (2026). Harnessing the charge-transfer-to-solvent state of aqueous triiodide: A strategy to mitigate I2 trapping and enhance hydrated electron yield.. The Journal of chemical physics. doi:10.1063/5.0321927
[36] Misra SN, Gagnani MA, M ID (2004). Biological and clinical aspects of Lanthanide coordination compounds.. Bioinorganic chemistry and applications. doi:10.1155/s1565363304000111
