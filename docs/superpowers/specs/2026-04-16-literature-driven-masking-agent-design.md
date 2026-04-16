# Literature-Driven Design Constraint Agent (Paper to Mask)

## Overview
This design document outlines the integration of an AI-driven agent into the Protein Pipeline console. The agent enables users to upload a reference research paper (PDF or text) and automatically extracts key structural residues (e.g., catalytic triads, binding interfaces, conserved motifs) that should remain unchanged (masked/fixed) during the protein design process.

The system emphasizes a "Human-in-the-Loop" verification step. It does not blindly apply mutations; instead, it presents the AI's suggestions alongside the exact textual evidence extracted from the paper, allowing the user to review, modify, and visually inspect the constraints before applying them to the pipeline.

## Goals
- **Automate Constraint Discovery:** Reduce the manual effort required to read papers and manually select hundreds of critical residues in the 3D viewer.
- **Traceability:** Provide clear, cited evidence (snippets from the paper) for every suggested constraint.
- **Accuracy & Safety:** Automatically verify if the residue numbering in the paper matches the provided input PDB/FASTA, flagging potential mismatches for user review.
- **Ubiquitous Access:** Make this feature available across all primary run modes (Fast, Advanced, Evolution, and Workflow Studio).

## Architecture

### 1. Frontend Integration (UI/UX)
- **Upload & Analysis Triggers:**
  - A new "📄 Find Masks from Paper (PDF)" button and file upload input will be added near the `fixed_positions_extra` or Target PDB inputs across the `Fast`, `Advanced`, `Evolution`, and `Studio` tabs.
- **Review Panel:**
  - Upon successful analysis, a dedicated review panel appears below the upload button.
  - The panel displays a list of suggested residues with checkboxes (e.g., `[x] Chain A: 64 (His) - "Catalytic Triad"`).
  - A tooltip or expandable section `[ⓘ View Evidence]` reveals the exact sentence extracted from the paper justifying the selection.
- **Mismatch Warning:**
  - If the AI detects a sequence or numbering mismatch between the paper's context and the user's PDB, a prominent warning badge (`⚠️ Sequence mismatch suspected`) is displayed next to the affected residue.
- **Application & Visualization:**
  - A "Confirm & Apply to fixed_positions_extra" button merges the selected checkboxes into the pipeline's configuration state (`state.answers.fixed_positions_extra`).
  - Users can then open the existing Residue Picker (3D Viewer) to visually confirm the applied constraints.

### 2. Backend Integration (MCP Tool)
- **New Tool (`pipeline.analyze_paper_for_masking`):**
  - Added to `pipeline-mcp/src/pipeline_mcp/tools.py`.
  - **Inputs:** Base64 encoded PDF file (or raw text) and the Target PDB/FASTA content.
  - **Process:**
    1. Extract text from the PDF using the `pypdf` library.
    2. Construct a prompt containing the target sequence and the extracted paper text.
    3. Invoke the Gemini 3.1 Pro Preview model with strict system instructions to act as a structural biology expert. The model is instructed to find constraints, cite evidence, and perform a preliminary sequence alignment check.
  - **Output Schema (JSON):**
    ```json
    {
      "suggested_masks": [
        {
          "chain": "A",
          "residue_index": 64,
          "residue_name": "HIS",
          "label": "Catalytic Site",
          "evidence": "His64 acts as a general base...",
          "confidence": "high" // or "low_sequence_mismatch"
        }
      ]
    }
    ```

### 3. Data Flow
1. User uploads a PDF via the frontend UI.
2. The frontend reads the file as Base64 and calls the `pipeline.analyze_paper_for_masking` MCP tool, passing the current Target PDB text as context.
3. The backend parses the PDF, queries Gemini, and returns the structured JSON array of suggestions.
4. The frontend renders the Review Panel.
5. The user reviews the evidence, toggles checkboxes, and clicks "Apply".
6. The frontend merges the selected items into `state.answers.fixed_positions_extra`.
7. The standard pipeline submission logic (`pipeline.run`) handles the rest without requiring core engine modifications.

## Dependencies
- Backend: `pypdf` (already added to `requirements.txt`).
- Backend: `google-generativeai` (already configured via `GeminiClient`).
- Frontend: Existing `residue-picker.js` logic for handling `fixed_positions_extra` state.

## Error Handling
- **PDF Parsing Failure:** The backend returns a clear error message if the PDF is encrypted, corrupted, or contains no extractable text.
- **Gemini Context Limit/Timeout:** The backend handles API timeouts gracefully, returning a generic error prompting the user to try a smaller excerpt or plain text.
- **No Constraints Found:** The tool returns an empty list, and the UI displays a message: "No explicit structural constraints found in the provided document."