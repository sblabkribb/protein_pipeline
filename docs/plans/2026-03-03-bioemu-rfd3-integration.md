# BioEmu Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add BioEmu RunPod integration so pipeline can feed combined RFD3 and BioEmu backbone sets into ProteinMPNN.

**Architecture:** Extend the pipeline contract with BioEmu request parameters, add a dedicated RunPod client, and insert a BioEmu backbone stage before the ProteinMPNN backbone loop. Backbones are normalized into one list with explicit `source` metadata (`rfd3` or `bioemu`) so downstream design/filter stages remain unchanged. Update bioemu-runpod handler to optionally return per-sample PDB structures from trajectory frames.

**Tech Stack:** Python 3, dataclasses, RunPod HTTP API, unittest/pytest dry-run tests.

---

### Task 1: Add failing tests for BioEmu pipeline behavior

**Files:**
- Modify: `pipeline-mcp/tests/test_pipeline_dry_run.py`
- Modify: `pipeline-mcp/tests/test_tools.py`

1. Add a test that runs dry-run with `rfd3_use_ensemble + bioemu_use` and verifies `backbones.json` includes both `rfd3` and `bioemu` sources.
2. Add a test that verifies `pipeline_request_from_args` parses BioEmu options.
3. Run targeted tests to confirm failure before implementation.

### Task 2: Implement BioEmu client/config wiring in pipeline-mcp

**Files:**
- Create: `pipeline-mcp/src/pipeline_mcp/clients/bioemu_runpod.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/clients/__init__.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/config.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/app.py`

1. Add `BioEmuRunPodClient` with payload/response validation.
2. Add optional `BIOEMU_ENDPOINT_ID` config.
3. Instantiate client in `build_runner` and inject into `PipelineRunner`.

### Task 3: Implement pipeline request + execution path for BioEmu

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/models.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`
- Modify: `pipeline-mcp/src/pipeline_mcp/pipeline.py`

1. Extend `PipelineRequest` and tool schema/arg parsing with BioEmu fields.
2. Add BioEmu stage in `PipelineRunner.run` (dry-run + real mode).
3. Merge backbones as `rfd3 + bioemu` and propagate `source` metadata through backbone artifacts.
4. Support `stop_after='bioemu'`.

### Task 4: Extend bioemu-runpod output for sample PDB export

**Files:**
- Modify: `bioemu-runpod/handler.py`
- Modify: `bioemu-runpod/README.md`

1. Add optional response field `sample_pdbs` generated from topology+trajectory frames.
2. Add input knobs `return_sample_pdbs`, `max_return_sample_pdbs`.
3. Update README input/output contract.

### Task 5: Verify and update user docs

**Files:**
- Modify: `README.md`
- Modify: `docs/USAGE.md`

1. Document BioEmu endpoint env var and pipeline args.
2. Add example for RFD3 50 + BioEmu 50 to ProteinMPNN.
3. Run focused test suite and report exact command outputs.
