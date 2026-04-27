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
