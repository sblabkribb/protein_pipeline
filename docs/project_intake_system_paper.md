# Project Intake: protein_pipeline System Paper

## Quick Intake Fields

- **Primary working title:** `protein_pipeline: An End-to-End System for Protein Design Workflow Orchestration and Interactive Analysis`
- **Paper type:** System paper / platform paper
- **Primary objective:** Present `protein_pipeline` as a unified research system that combines staged protein design execution, a web-based user interface, reproducible artifact management, and integrated analysis/report generation.
- **Central artifact:** An MCP-enabled protein design pipeline with a web console for setup, monitoring, comparison, and reporting.
- **Main audience:** Researchers and engineers working in computational protein design, AI for science, scientific workflow systems, and interactive research software.
- **Current framing:** The paper is about building and operationalizing the workflow system, not about introducing a new single-model architecture.

## Recommended Title Options

1. `protein_pipeline: An End-to-End System for Protein Design Workflow Orchestration and Interactive Analysis`
2. `protein_pipeline: A Web-Integrated Platform for Reproducible Protein Design and Evaluation`
3. `protein_pipeline: Orchestrating Protein Design, Structure Evaluation, and Comparative Reporting in a Unified Research System`

## Objective

This project aims to document and publish `protein_pipeline` as a unified system for computational protein design workflows. The paper will explain how the platform combines staged orchestration across external protein modeling services with a web-based console for run setup, monitoring, comparison, and report generation. The goal is to show that the contribution of the project is not a new standalone prediction model, but a reproducible and interactive workflow system that makes complex protein design pipelines easier to execute, inspect, and extend.

## One-Paragraph Project Summary

`protein_pipeline` is an end-to-end platform for running and managing protein design workflows that span multiple execution stages and external tools. The system includes an MCP-enabled backend orchestration layer, RunPod-backed model execution, a structured artifact store organized by `run_id`, and a static web console that supports setup, workflow control, monitoring, comparative analysis, and report generation. The paper should position this project as a systems contribution for AI-assisted protein engineering: a practical framework that turns a fragmented collection of design, scoring, and structure-prediction steps into a traceable, interactive, and reusable research workflow.

## Problem Statement And Motivation

Modern protein design workflows are typically assembled from many heterogeneous components: sequence retrieval and MSA generation, backbone generation or selection, sequence design, solubility filtering, structure prediction, novelty search, and downstream comparison. In practice, these steps are often glued together with ad hoc scripts, model-specific interfaces, and manual result inspection. This creates several recurring problems.

- Execution is fragmented across tools with different interfaces and infrastructure assumptions.
- Intermediate outputs are easy to lose, overwrite, or misinterpret.
- Partial reruns are operationally risky because upstream inputs may change while downstream outputs are reused.
- Comparative analysis is usually performed outside the main workflow, which weakens reproducibility and makes result interpretation slower.
- Web interfaces for these pipelines are often thin wrappers around job submission rather than integrated research environments.

The motivation for this paper is to present a system that addresses these workflow-level problems. `protein_pipeline` is designed to connect execution, inspection, comparison, and reporting in one platform so that computational protein design runs become easier to reproduce, review, and communicate.

## Why This Project Is Paper-Worthy

The publishable contribution is the system integration itself. The project brings together a protein design pipeline and a user-facing website in a way that creates a coherent research platform rather than a collection of scripts. The paper can argue that the technical novelty lies in how the system operationalizes multi-stage protein design work:

- a unified orchestration layer for heterogeneous services
- stage-aware execution and checkpointed workflow control
- a web interface that exposes both execution and scientific interpretation
- reproducible artifact storage and safe rerun semantics
- integrated comparison, hit-list generation, and report authoring

This makes the work suitable for a system paper, platform paper, demo paper, or applied AI-for-science tooling paper.

## System Overview

At a high level, `protein_pipeline` connects five layers into one system:

1. **User-facing website:** a static web console where users configure inputs, launch runs, review checkpoints, inspect outputs, and compare results.
2. **MCP and HTTP tool server:** the backend surface that exposes pipeline and analysis tools such as `pipeline.run`, `pipeline.preflight`, `pipeline.status`, `pipeline.compare_runs`, and report/export operations.
3. **Pipeline runner:** the orchestration layer that manages stage order, artifacts, run state, and safe rerun behavior.
4. **External modeling and scoring services:** RunPod-backed endpoints and HTTP services for MMseqs2, ProteinMPNN, optional RFD3/BioEmu, SoluProt, AF2, and related tasks.
5. **Artifact and report store:** structured outputs written under `PIPELINE_OUTPUT_ROOT/<run_id>/`, including the original request, status timeline, stage outputs, summaries, and reports.

The central design idea is that the workflow is not just a backend pipeline. It is a full research environment in which execution state, intermediate artifacts, comparative views, and reporting outputs are all first-class system objects.

## Architecture

The system architecture can be described as the following flow:

1. A user starts from the website and uploads a FASTA, PDB, ligand input, or other stage-specific configuration.
2. The UI sends a structured request to the MCP/HTTP backend, optionally using planning and preflight tools before execution.
3. The pipeline runner validates the request, assigns or reuses a `run_id`, and executes the relevant stages in order.
4. Individual heavy-compute stages are delegated to external endpoints such as MMseqs2, ProteinMPNN, RFD3, BioEmu, AF2, or SoluProt.
5. Outputs from every stage are persisted to the run directory, along with `request.json`, `status.json`, `events.jsonl`, summaries, and generated reports.
6. The website reads those outputs back through list/read/compare/report APIs to support monitoring, artifact preview, comparative analysis, and export packaging.

This architecture matters because it decouples the user experience from individual model runtimes while still preserving full run traceability.

## Pipeline Execution Workflow

The core stage order documented in the repository is:

`msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty`

Around that core path, the pipeline also records conservation, masking, WT comparison, reporting, and agent-panel artifacts. The practical workflow is:

1. **Ingest and preflight**
   - The system accepts target FASTA/PDB and optional backbone, ligand, or stage-specific controls.
   - `pipeline.preflight` can check service availability and request validity before execution.

2. **MSA and conservation analysis**
   - MMseqs2 generates MSA outputs and related quality metadata.
   - Conservation information is computed and later used for fixed-position strategy.

3. **Optional backbone generation or selection**
   - RFD3 and/or BioEmu can be used when the workflow requires backbone generation rather than directly using the input structure.

4. **Masking and design preparation**
   - Ligand-aware masking, consensus fixed positions, chain strategy, and query/PDB alignment checks prepare the design space.

5. **ProteinMPNN design**
   - Sequence candidates are generated, typically in tiers defined by conservation or related controls.

6. **SoluProt filtering**
   - Candidate sequences are filtered using solubility scores before expensive structure evaluation.

7. **AlphaFold2 evaluation**
   - AF2 or ColabFold-style evaluation is used to predict candidate structures and compute ranking signals such as pLDDT and RMSD-based selection criteria.

8. **Novelty search and summary generation**
   - Surviving candidates are checked for novelty, then summarized into machine-readable and human-readable reports.

This staged structure gives the paper a clear methodological backbone even though the paper itself is about the system rather than a single model.

## Website And User Workflow

The website is a major part of the paper contribution because it turns the backend pipeline into an interactive research tool rather than a job launcher.

### 1. Setup

The `Setup` surface lets users choose a run mode, upload inputs, configure stage parameters, run preflight validation, and launch new runs. It also supports loading an existing `request.json` and forking or continuing a run under controlled conditions.

### 2. Workflow Studio

`Workflow Studio` exposes checkpoint-based execution. This supports staged review and makes the pipeline feel like a managed workflow system instead of a single fire-and-forget command.

### 3. Monitor

The `Monitor` surface exposes current `run_id`, stage, state, update time, artifact previews, agent-panel outputs, and report actions. This is the operational center for inspecting what happened during a run.

### 4. Analyze

The `Analyze` surface is where the system moves beyond execution into interpretation. It includes:

- Compare Studio for structure and sequence comparison
- run-to-run comparison views
- weighted hit-list generation
- candidate charts and summaries
- report generation and review
- feedback and experiment logging

This section is important to emphasize in the paper because many pipeline systems stop at result generation, while this platform also supports comparative reasoning and reporting.

### 5. RunPod Admin

The `RunPod Admin` console extends the site into an operator-facing management surface. It exposes endpoint status, billing-oriented views, worker information, and safe scaling patches for the managed compute endpoints. This is not the main scientific contribution, but it strengthens the paper's systems story by showing that the platform includes infrastructure operations rather than only scientific UI panels.

## Reproducibility And Safe Rerun Model

One of the strongest system contributions in this repository is the explicit rerun model.

- The default behavior is to create a new `run_id`.
- Reusing the same `run_id` is intended only for controlled partial reruns in `pipeline` or `workflow` mode.
- The UI requires the user to load an existing request and explicitly enable continuation.
- The backend uses request-diff guards and stage-specific request hashes to reject unsafe late-stage reruns when upstream inputs changed.
- Outputs are stored under a stable run directory with trace files such as `request.json`, `status.json`, `events.jsonl`, `summary.json`, `comparisons.json`, and markdown reports.

This is worth emphasizing in the paper because reproducibility in scientific workflows is often weakened by informal rerun practices. Here, rerun safety is built into both the interface and the backend contract.

## Core Technical Contributions

The paper can claim the following technical contributions, provided the wording stays system-focused:

1. **An end-to-end orchestration framework for protein design workflows**
   - The system integrates MSA, optional backbone generation, design, solubility filtering, structure evaluation, novelty search, and reporting through one execution interface.

2. **An MCP-enabled research software architecture**
   - The backend exposes execution, inspection, reporting, and operational tools through a tool-oriented interface that supports both interactive use and automation.

3. **A web-based interface for execution plus scientific interpretation**
   - The platform includes not only run submission, but also checkpoint review, artifact inspection, comparison workflows, hit-list ranking, and report generation.

4. **A safe partial rerun and artifact-traceability model**
   - The system treats `run_id`, request diffs, and stage outputs as first-class workflow controls, which supports reproducible reuse without silent contamination of downstream results.

5. **An integrated operational layer for managed external services**
   - The platform includes controls and visibility for the RunPod-backed infrastructure that executes the heavy stages of the workflow.

## Research Questions And Paper Claims

The paper can be structured around a small number of system-oriented research questions:

1. Can a unified orchestration layer make multi-stage protein design workflows easier to execute and inspect than script-based composition?
2. Can a web-based interface expose enough execution state and scientific context to support interactive review rather than post hoc debugging?
3. Can explicit run management and safe rerun semantics improve reproducibility and reduce workflow errors in iterative protein design experiments?
4. Can integrated comparison and reporting make the outputs of protein design workflows easier to communicate and reuse?

The associated claims should remain modest and defensible:

- `protein_pipeline` operationalizes a complex protein design workflow as a coherent system.
- The website is a core part of the research contribution because it exposes workflow control, inspection, and comparative analysis.
- The system improves the practical manageability of multi-stage design workflows by turning artifacts and rerun semantics into explicit platform concepts.

## Proposed Evaluation Plan

The evaluation section should focus on system evidence rather than only raw model metrics.

### 1. End-to-end system demonstration

Show that the platform can execute representative workflows from ingest through reporting, including runs that use optional backbone-generation branches.

### 2. Reproducibility and traceability case study

Demonstrate how `run_id`-based storage, request tracking, and safe rerun guards preserve workflow integrity across repeated and partial runs.

### 3. Interface-centered workflow analysis

Show how the website supports concrete tasks such as:

- preparing a run from FASTA/PDB inputs
- monitoring progress and inspecting stage artifacts
- comparing candidates across tiers or across runs
- generating reports and export packages

### 4. Comparative systems discussion

Compare the platform conceptually against a script-only or notebook-only baseline in terms of workflow traceability, rerun safety, and integrated analysis support.

### 5. Optional biological case studies

If time permits, add one or more design case studies that illustrate how the system can be used in realistic protein engineering workflows. These case studies should support the systems narrative, not replace it.

## Expected Deliverables

- A system paper describing the architecture, workflow model, and interface design of `protein_pipeline`
- A set of architecture and UI figures derived from the repository implementation
- Example run case studies with artifact traces and analysis outputs
- A clear description of the run-management and safe-rerun contract
- A demonstration of report generation, comparison, and hit-list workflows

## Scope Boundaries And Non-Goals

The paper should explicitly avoid overextending its claims.

- It is **not** primarily a paper about inventing a new structure prediction or sequence design model.
- It does **not** need to claim state-of-the-art biological performance in order to be valuable as a systems contribution.
- It should avoid promising wet-lab validation unless such evidence is actually available.
- It should not present the website as a cosmetic frontend; the argument is that the site is a functional layer of the research system.

## Draft Abstract

Protein design workflows increasingly depend on multi-stage computational pipelines that combine sequence analysis, structure-conditioned design, scoring, structure prediction, and downstream result interpretation. In practice, these workflows are often assembled from heterogeneous tools and ad hoc scripts, which makes execution difficult to manage and results difficult to reproduce. We present `protein_pipeline`, an end-to-end system for orchestrating protein design workflows and interacting with their outputs through a unified web-based platform. The system combines an MCP-enabled orchestration backend, staged execution across external modeling services, structured run-level artifact management, and an interactive console for setup, monitoring, comparison, and report generation. `protein_pipeline` supports execution flows spanning MSA generation, optional backbone generation, ProteinMPNN-based sequence design, SoluProt filtering, AF2-based evaluation, novelty analysis, and integrated reporting. A central design feature of the platform is its safe partial rerun model, which treats run identity, request diffs, and stage outputs as explicit workflow controls to preserve traceability across iterative experiments. We position `protein_pipeline` as a systems contribution for AI-assisted protein engineering: a practical framework that turns fragmented protein design procedures into a reproducible, inspectable, and extensible research environment.

## Suggested Keywords

- protein design workflow
- computational protein engineering
- AI for science systems
- scientific workflow orchestration
- reproducible research software
- interactive analysis platform
- MCP-enabled tools
- web-based scientific interface

## Suggested Figures And Tables For The Paper

1. **System architecture figure**
   - Website -> MCP/backend -> pipeline runner -> external services -> artifact store

2. **Pipeline stage figure**
   - MSA -> optional RFD3/BioEmu -> design -> SoluProt -> AF2 -> novelty -> report

3. **Website workflow figure**
   - Setup, Workflow Studio, Monitor, Analyze, RunPod Admin

4. **Safe rerun diagram**
   - New run fork vs controlled continuation on the same `run_id`

5. **Artifact tree table**
   - Key files under `outputs/<run_id>/` and what each contributes to reproducibility

## Repository Source Basis

This intake document is grounded in the following repository materials:

- `README.md`
- `docs/USAGE.md`
- `docs/runbook.md`
- `docs/runpod_model_execution.md`
- `docs/stepper_orchestration.md`
- `docs/ui_pipeline_ppt_ko.md`
- `frontend/runpod-admin/README.md`

These sources collectively describe the implemented pipeline stages, the website workflow, the backend orchestration model, and the operational features that justify the system-paper framing.
