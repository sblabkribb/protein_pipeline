# Manuscript Agentic Enhancement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up the structural corruption in `docs/manuscript.md` and elevate the narrative to focus on the multi-agent consensus panel and scientific guardrails.

**Architecture:** We will first extract the core body of the manuscript up to the Conclusion. Then we will append the References section. Finally, we will run targeted `replace` commands to inject specific thresholds and agentic logic into the Abstract, Introduction, Architecture, and Workflow sections.

**Tech Stack:** Markdown text manipulation.

---

### Task 1: Structural Cleanup

**Files:**
- Modify: `/opt/protein_pipeline/docs/manuscript.md`

- [ ] **Step 1: Read the full file to memory**
Use `cat` to read the entire file so you can properly split it.

- [ ] **Step 2: Rewrite the file with correct structure**
Write the file starting from `# protein_pipeline:` down to the end of `## Conclusion`. Do NOT include the duplicated sections (`## Pipeline Workflow and Stage Design` etc.) that appear after Conclusion.
Append the `## References` section (lines 1-36) at the very end.

- [ ] **Step 3: Verify the structure**
Run `grep -n '^## ' /opt/protein_pipeline/docs/manuscript.md`. The last heading should be `## References`.

### Task 2: Narrative Enhancement (Abstract & Intro)

**Files:**
- Modify: `/opt/protein_pipeline/docs/manuscript.md`

- [ ] **Step 1: Update the Abstract**
Replace the Abstract to explicitly mention "autonomous quality control via scientific guardrails" and list the specific metrics monitored (pLDDT, MSA depth, Solubility).

- [ ] **Step 2: Update the Introduction**
Modify the Introduction to highlight that the MCP-enabled backend forms a feedback loop with the Agent Panel to automatically guide researchers away from failure modes.

### Task 3: Technical Details (Architecture & Workflow)

**Files:**
- Modify: `/opt/protein_pipeline/docs/manuscript.md`

- [ ] **Step 1: Update Architecture**
Add text describing the `ToolDispatcher` as the mechanism that exposes modeling functions via MCP, allowing the multi-agent panel to intervene.

- [ ] **Step 2: Update Workflow Execution Model**
Inject the concrete thresholds:
* MSA Depth < 50 triggers a recover recommendation (increase mmseqs_max_seqs).
* SoluProt pass rate < 20% triggers a monitor recommendation (relax sampling_temp).
* AF2 average pLDDT < 75 triggers a monitor recommendation.