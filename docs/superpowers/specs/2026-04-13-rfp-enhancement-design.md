# RFP Enhancement Design: Workflow Execution, DAG Studio, and LLM Copilot

## 1. Goal
Enhance the existing protein engineering pipeline Request for Proposal (RFP) by adding advanced functional requirements. The goal is to move from a rigid, linear pipeline to a flexible, user-driven platform powered by visual editing, centralized model management, and natural language AI control.

## 2. Key Additions to RFP

### 2.1. Model Registry (ID-based Registration)
- **Target Location:** Add to Administrative Requirements.
- **Concept:** A centralized registry within the admin console where administrators can map external (RunPod/Lambda) or internal GPU endpoints to logical IDs (e.g., `model:alphafold-v1`).
- **Features:**
  - Register endpoints, API keys, and required parameters.
  - Decouple pipeline execution from hardcoded URLs.
  - Enable seamless updates or swapping of underlying infrastructure without changing user workflows.

### 2.2. DAG-based Visual Workflow Editor (Workflow Studio Expansion)
- **Target Location:** Expand `기능 요구 사항-004` (단계별 워크플로 설계 및 재실행 관리).
- **Concept:** Upgrade the "Studio" from a linear step-by-step runner to a Directed Acyclic Graph (DAG) node editor.
- **Features:**
  - Visual canvas for drag-and-drop node placement.
  - Support for custom nodes registered via the Model Registry.
  - Capabilities for parallel execution branches and conditional logic (e.g., routing based on RMSD scores).

### 2.3. LLM-Driven Workflow Execution and Control (AI Copilot)
- **Target Location:** Expand `기능 요구 사항-006` (대화형 사용자 인터페이스).
- **Concept:** Elevate the chatbot from a QA assistant to an operational Copilot that can construct and execute pipelines.
- **Features:**
  - Natural language parsing to auto-generate DAG workflows (e.g., "Run Model A, then filter, then run Model B").
  - Conversational execution control (start, pause, inspect).
  - Intelligent parameter suggestion based on protein context.
  - Multi-turn execution where LLM interprets results and queues subsequent analysis based on user prompts.

## 3. Implementation Plan
1. Parse the existing `@protein_platform_rfp_ko.md` file.
2. Formulate new Markdown text blocks corresponding to the above three features.
3. Replace or append to the existing sections (`기능 요구사항-004`, `기능 요구사항-006`, and add a new admin/registry requirement).
4. Update the requirement summary table at the bottom of the RFP.