# Manuscript Agentic Enhancement Spec

## Goal
Elevate the narrative of `protein_pipeline` in the manuscript from a simple "workflow orchestrator" to an "autonomous quality control system governed by scientific guardrails." The agent panel and its underlying logic (MSA depth gating, SoluProt filtering, AF2 pLDDT checks) should be presented as the primary systems contribution that ensures reproducibility and scientific validity.

## Context
The current manuscript `docs/manuscript.md` has been partially updated but suffered structural corruption (e.g., duplicated sections, "References" appearing before the end of the file). The citations have been verified as real 2025/2026 papers.

## Structural Fixes Required
1. Move the `References` section to the very end of the file.
2. Remove the duplicated/misplaced sections (`Pipeline Workflow and Stage Design`, `Web Interface and User Workflow`, `Reproducibility, Artifact Management, and Rerun Semantics`, `Limitations and Future Work`) that currently appear *after* the Conclusion/References. Ensure their content is properly integrated into the main body sections of the same names.

## Content Enhancements Required
### 1. Abstract & Introduction
*   **Shift Focus**: Change the primary value proposition from "orchestration" to "autonomous quality control via scientific guardrails."
*   **Add Detail**: Mention the multi-agent consensus panel actively making "proceed", "monitor", or "recover" decisions based on real-time metrics (pLDDT, MSA depth, etc.).

### 2. Architecture & Implementation
*   **Tool Dispatcher**: Describe the `ToolDispatcher` as the MCP-enabled execution layer.
*   **Feedback Loop**: Detail how the Agent Panel evaluates `events.jsonl` and stage artifacts to provide feedback to the Tool Dispatcher.

### 3. Workflow Execution Model
*   **Concrete Thresholds**: Explicitly state the guardrails used:
    *   MSA Depth < 50: Recover (suggest increasing `mmseqs_max_seqs`).
    *   SoluProt Pass Rate < 20%: Monitor/Recover (suggest relaxing constraints).
    *   AlphaFold2 pLDDT < 75: Monitor (suggest adjusting cutoffs).

## Trade-offs Considered
*   **Approach A: Self-Correction Focus (Selected)**. Focuses on the *rules* the agents follow (the thresholds) and how they correct the workflow. This grounds the paper in practical scientific utility.
*   **Approach B: Tool Integration Focus**. Focuses heavily on the MCP protocol specifics. *Trade-off*: Too technical for a general bioinformatics audience.

## Artifacts
The final product will be a cleaned, structurally sound `docs/manuscript.md` that heavily emphasizes the multi-agent consensus capabilities of `protein_pipeline`.