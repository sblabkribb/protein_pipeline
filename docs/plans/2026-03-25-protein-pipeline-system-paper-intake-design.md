# Protein Pipeline System Paper Intake Design

## Goal

Create an upload-ready project intake document that frames `protein_pipeline` and its website as a single research system. The document should be detailed enough to seed paper drafting, but grounded in the features that are already implemented in this repository.

## Problems

- Current repository documentation is split across README, operator runbooks, orchestration notes, and UI slides.
- Those documents explain usage and operations, not the paper narrative needed for project intake.
- The project includes both a protein design pipeline and a website, but the relationship between them needs to be presented as one coherent system.
- The intake document must distinguish implemented capabilities from planned evaluation so it does not overclaim.

## Approved Direction

1. Position the paper as a system paper, not a new model paper.
2. Present the pipeline and the web console as a unified end-to-end platform for protein design workflow execution, monitoring, analysis, and reporting.
3. Emphasize technical contributions that are actually visible in the repo:
   - staged orchestration across multiple external services
   - a user-facing web interface for setup, monitoring, and analysis
   - reproducible artifact storage organized by `run_id`
   - safe partial reruns with request-diff guards
   - integrated reporting and comparison flows
4. Keep the intake document in English so it can be uploaded directly to external tooling and reused for paper drafting.
5. Make the document self-contained instead of assuming the reader has repo context.

## Audience

- Project intake systems that ingest a long-form project description
- Internal collaborators preparing the paper outline and abstract
- Future readers who need a concise explanation of the system before reading code

## Document Structure

- Quick intake fields for title, paper type, objective, audience, and central artifact
- Recommended title options
- Objective
- Project summary
- Problem statement and motivation
- System overview and architecture
- Pipeline execution workflow
- Website and user workflow
- Core technical contributions
- Research questions and evaluation plan
- Deliverables, scope boundaries, and non-goals
- Draft abstract
- Keywords and suggested figures
- Repository source basis

## Tone And Claim Boundaries

- Use system-centric language rather than biological performance claims.
- Describe the pipeline as an orchestration and analysis platform that integrates existing tools and models.
- Use phrases such as "designed to", "supports", and "the paper will evaluate" where quantitative evidence is not yet documented in the repo.
- Keep the paper contribution centered on workflow integration, interactivity, reproducibility, and operator usability.

## Validation

- Cross-check stage names against the repository README and orchestration docs.
- Cross-check UI surfaces against the UI slide notes and usage guide.
- Ensure the final intake document explicitly covers both the pipeline and the website.
- Keep the document under `docs/` so it is easy to discover and upload.
