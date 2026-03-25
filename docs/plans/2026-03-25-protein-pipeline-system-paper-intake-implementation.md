# Protein Pipeline System Paper Intake Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an upload-ready markdown document in `docs/` that frames `protein_pipeline` and its website as a unified system paper project.

**Architecture:** Reuse existing repository docs as the factual source of truth, then synthesize them into one self-contained intake document. Keep the document system-focused, explicitly cover both backend orchestration and the web interface, and separate implemented capabilities from planned evaluation.

**Tech Stack:** Markdown, repository documentation, local verification with shell commands

---

### Task 1: Create the intake document scaffold

**Files:**
- Create: `/opt/protein_pipeline/docs/project_intake_system_paper.md`
- Reference: `/opt/protein_pipeline/docs/plans/2026-03-25-protein-pipeline-system-paper-intake-design.md`

**Step 1: Write the initial document structure**

- Add sections for quick intake fields, title options, objective, project summary, problem statement, system overview, pipeline workflow, website workflow, core contributions, evaluation plan, deliverables, non-goals, draft abstract, and keywords.

**Step 2: Verify the required headings exist**

Run: `rg -n "^## " /opt/protein_pipeline/docs/project_intake_system_paper.md`

Expected: headings for `Objective`, `Problem Statement And Motivation`, `System Overview`, `Core Technical Contributions`, `Proposed Evaluation Plan`, and `Draft Abstract`.

### Task 2: Add the pipeline and architecture narrative

**Files:**
- Modify: `/opt/protein_pipeline/docs/project_intake_system_paper.md`
- Reference: `/opt/protein_pipeline/README.md`
- Reference: `/opt/protein_pipeline/docs/runbook.md`
- Reference: `/opt/protein_pipeline/docs/runpod_model_execution.md`
- Reference: `/opt/protein_pipeline/docs/stepper_orchestration.md`

**Step 1: Describe the system architecture**

- Summarize the relationship between the website, the MCP server, the pipeline runner, external services, and the artifact store.

**Step 2: Describe the execution workflow**

- Document the staged flow from ingest and preflight through MSA, optional backbone generation, design, filtering, AF2 evaluation, novelty search, and report generation.

**Step 3: Verify implemented stage names match the repo**

Run: `rg -n "msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty|pipeline.run|pipeline.status" /opt/protein_pipeline/README.md /opt/protein_pipeline/docs/project_intake_system_paper.md`

Expected: the intake doc uses the same stage order and references the same core execution concepts as the repo docs.

### Task 3: Add the website and paper-positioning sections

**Files:**
- Modify: `/opt/protein_pipeline/docs/project_intake_system_paper.md`
- Reference: `/opt/protein_pipeline/docs/USAGE.md`
- Reference: `/opt/protein_pipeline/docs/ui_pipeline_ppt_ko.md`
- Reference: `/opt/protein_pipeline/frontend/runpod-admin/README.md`

**Step 1: Document the website workflow**

- Cover the main user surfaces: `Setup`, `Workflow Studio`, `Monitor`, `Analyze`, and `RunPod Admin`.

**Step 2: Add the system-paper framing**

- Explain why the paper is about workflow orchestration, interactivity, reproducibility, and reporting rather than proposing a new foundation model.
- Add research questions, evaluation directions, deliverables, and non-goals.

**Step 3: Verify the document covers both the pipeline and the site**

Run: `rg -n "Setup|Workflow Studio|Monitor|Analyze|RunPod Admin|safe partial rerun|report|comparison" /opt/protein_pipeline/docs/project_intake_system_paper.md`

Expected: the document explicitly names the implemented website surfaces and system behaviors that justify the paper framing.

### Task 4: Final editorial review

**Files:**
- Modify: `/opt/protein_pipeline/docs/project_intake_system_paper.md` if cleanup is needed

**Step 1: Read the document top to bottom for consistency**

Run: `sed -n '1,260p' /opt/protein_pipeline/docs/project_intake_system_paper.md`

Expected: the narrative reads as a coherent project intake document without unsupported quantitative claims.

**Step 2: Check git status**

Run: `git -C /opt/protein_pipeline status --short`

Expected: only the new intake and planning docs appear as changes for this task.

**Step 3: Commit if a repository snapshot is desired**

Run: `git -C /opt/protein_pipeline add docs/project_intake_system_paper.md docs/plans/2026-03-25-protein-pipeline-system-paper-intake-design.md docs/plans/2026-03-25-protein-pipeline-system-paper-intake-implementation.md && git -C /opt/protein_pipeline commit -m "docs: add protein_pipeline system paper intake materials"`

Expected: a clean commit containing the intake document and its planning records.
