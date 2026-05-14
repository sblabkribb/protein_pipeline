# Orchestration Agent Trace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the platform's orchestration and agent layers explicit in runtime artifacts and manuscript text.

**Architecture:** Add a run-scoped `orchestration_trace.jsonl` alongside `events.jsonl` and `agent_panel.jsonl`. Status events represent the deterministic control plane; Agent Panel consensus events represent the evidence-agent plane. Update documentation and manuscript wording so the paper distinguishes orchestration, model-provider execution, checkpoint gates, and advisory agents.

**Tech Stack:** Python backend, unittest/pytest, Markdown manuscript, existing artifact storage helpers.

---

### Task 1: Add trace tests first

**Files:**
- Create: `pipeline-mcp/tests/test_orchestration_trace.py`

**Steps:**
1. Write tests showing `set_status()` emits `orchestration_trace.jsonl`.
2. Write tests showing `emit_agent_panel_event()` appends an evidence-agent verdict to the same trace.
3. Run the new tests and verify they fail because the trace file is not emitted yet.

### Task 2: Implement minimal trace emission

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/storage.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/agent_panel.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`

**Steps:**
1. Add an `orchestration_trace_jsonl` run path.
2. Append control-plane status records from `set_status()`.
3. Append evidence-agent verdict records from `emit_agent_panel_event()`.
4. Include `orchestration_trace.jsonl` in summary artifact visibility.
5. Run targeted tests.

### Task 3: Document and update manuscript

**Files:**
- Modify: `docs/pipeline_orchestration_and_agents.md`
- Modify: `public_release/manuscript/manuscript.md`
- Regenerate if possible: `public_release/manuscript/manuscript.docx`

**Steps:**
1. Replace ambiguous autonomous-agent language with a three-layer framing.
2. Add a concise manuscript subsection describing orchestration trace and evidence-agent review.
3. Regenerate DOCX from Markdown when a local converter is available.

### Task 4: Verify

**Commands:**
- `cd /opt/protein_pipeline-work/pipeline-mcp && . .venv/bin/activate && pytest tests/test_orchestration_trace.py -q`
- `cd /opt/protein_pipeline-work/pipeline-mcp && . .venv/bin/activate && pytest tests/test_pipeline_dry_run.py::TestPipelineDryRun::test_pipeline_runs_and_writes_artifacts -q`

