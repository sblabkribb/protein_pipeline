# Literature-Driven Masking Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a feature that extracts structural constraints (masks) from an uploaded research paper (PDF/text) using Gemini 3.1 Pro Preview and allows users to review and apply them in the UI.

**Architecture:** A new MCP backend tool `pipeline.analyze_paper_for_masking` parses the PDF and prompts Gemini to extract JSON-formatted constraints. The frontend `app.js` calls this tool via a new upload button, renders the suggestions in a review panel, and merges selected constraints into `state.answers.fixed_positions_extra`.

**Tech Stack:** Python 3.12 (Backend MCP), `pypdf`, `google-generativeai`, Vanilla JS/HTML/CSS (Frontend).

---

### Task 1: Backend PDF Parsing & Agent Tool

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/tools.py`

- [ ] **Step 1: Implement PDF parsing helper**

Add a helper function to extract text from a base64-encoded PDF.

```python
def _extract_text_from_base64_pdf(b64_data: str) -> str:
    import base64
    import io
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is required to process PDFs")
    
    try:
        pdf_bytes = base64.b64decode(b64_data)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")
```

- [ ] **Step 2: Implement `pipeline.analyze_paper_for_masking` tool**

```python
def _analyze_paper_for_masking(runner: PipelineRunner, arguments: dict[str, Any]) -> dict[str, Any]:
    file_b64 = arguments.get("file_b64")
    file_text = arguments.get("file_text")
    target_sequence = str(arguments.get("target_sequence") or "").strip()
    
    if not file_b64 and not file_text:
        raise ValueError("Either file_b64 or file_text must be provided")
    
    paper_content = ""
    if file_b64:
        paper_content = _extract_text_from_base64_pdf(str(file_b64))
    else:
        paper_content = str(file_text).strip()
        
    if not paper_content:
        raise ValueError("Could not extract any text from the provided document")

    if not runner.gemini or not runner.gemini.is_available():
        raise RuntimeError("Gemini reasoning agent is not configured or unavailable")

    system_instruction = (
        "You are an expert structural biologist. Your task is to read a research paper and extract structural constraints for protein design. "
        "Identify critical residues that MUST NOT be mutated (e.g., catalytic triads, binding interfaces, conserved motifs). "
        "Return the result ONLY as a valid JSON object matching this schema:\n"
        "{\n"
        "  \"suggested_masks\": [\n"
        "    {\n"
        "      \"chain\": \"A\",\n"
        "      \"residue_index\": 64,\n"
        "      \"residue_name\": \"HIS\",\n"
        "      \"label\": \"Short descriptive label (e.g., Catalytic Site)\",\n"
        "      \"evidence\": \"Exact quote from the paper justifying this selection\",\n"
        "      \"confidence\": \"high\" or \"low_sequence_mismatch\" (use low if numbering seems to mismatch the provided sequence)\n"
        "    }\n"
        "  ]\n"
        "}"
    )
    
    prompt = f"Reference Paper Content:\n{paper_content[:150000]}\n\n" # Limit to avoid massive context
    if target_sequence:
        prompt += f"Target Protein Sequence (for numbering alignment check):\n{target_sequence}\n\n"
    prompt += "Extract the structural constraints as requested."

    try:
        import json
        response_text = runner.gemini.chat(system_instruction, prompt)
        
        # Clean up markdown code blocks if present
        clean_json = response_text
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()
        
        parsed = json.loads(clean_json)
        if "suggested_masks" not in parsed:
             parsed = {"suggested_masks": []}
        return {"success": True, "result": parsed}
    except Exception as e:
        raise RuntimeError(f"Agent failed to process the document: {str(e)}")
```

- [ ] **Step 3: Register the tool in `tool_definitions`**

```python
        {
            "name": "pipeline.analyze_paper_for_masking",
            "description": "Analyze a research paper (PDF base64 or text) to extract residues that should be masked.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_b64": {"type": "string"},
                    "file_text": {"type": "string"},
                    "target_sequence": {"type": "string"}
                }
            }
        },
```

- [ ] **Step 4: Route the tool in `ToolDispatcher.call_tool`**

```python
        if name == "pipeline.analyze_paper_for_masking":
            return _analyze_paper_for_masking(self.runner, arguments)
```

- [ ] **Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/tools.py
git commit -m "feat(backend): add pipeline.analyze_paper_for_masking tool using Gemini"
```

### Task 2: Frontend HTML Elements

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add upload button and review panel**

Find a suitable place in the Advanced Settings / Constraints section (or create a new shared component area) to add the UI. Assuming we place it near the `fixed_positions_extra` input in Advanced tab:

```html
            <!-- Literature-Driven Masking UI -->
            <div class="field-group">
              <label>Extract Constraints from Paper (PDF)</label>
              <div style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem;">
                <input type="file" id="paperMaskInput" accept="application/pdf" style="display: none;" />
                <button type="button" class="btn" id="paperMaskUploadBtn">Upload & Analyze Paper</button>
                <span id="paperMaskStatus" class="status-subtitle" style="margin: 0;"></span>
              </div>
              <div id="paperMaskReviewPanel" class="hidden" style="border: 1px solid var(--border-color); padding: 1rem; border-radius: 4px; background: var(--bg-color-alt);">
                <div class="status-subtitle">AI Suggested Masks</div>
                <div id="paperMaskList" style="display: flex; flex-direction: column; gap: 0.5rem; max-height: 300px; overflow-y: auto; margin-bottom: 1rem;">
                  <!-- Items injected here -->
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
                  <button type="button" class="btn" id="paperMaskCancelBtn">Cancel</button>
                  <button type="button" class="btn primary" id="paperMaskApplyBtn">Apply Selected to Constraints</button>
                </div>
              </div>
            </div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/index.html
git commit -m "feat(ui): add paper upload and review panel for mask extraction"
```

### Task 3: Frontend Logic Integration

**Files:**
- Modify: `frontend/app.js`

- [ ] **Step 1: Add element references to `el` object**

```javascript
  paperMaskInput: document.getElementById("paperMaskInput"),
  paperMaskUploadBtn: document.getElementById("paperMaskUploadBtn"),
  paperMaskStatus: document.getElementById("paperMaskStatus"),
  paperMaskReviewPanel: document.getElementById("paperMaskReviewPanel"),
  paperMaskList: document.getElementById("paperMaskList"),
  paperMaskApplyBtn: document.getElementById("paperMaskApplyBtn"),
  paperMaskCancelBtn: document.getElementById("paperMaskCancelBtn"),
```

- [ ] **Step 2: Implement upload and analyze logic**

Add state for suggested masks: `state.suggestedMasks = [];`

```javascript
function handlePaperMaskUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = async (e) => {
    const base64Data = e.target.result.split(',')[1];
    
    if (el.paperMaskStatus) el.paperMaskStatus.textContent = "Analyzing document with AI...";
    if (el.paperMaskUploadBtn) el.paperMaskUploadBtn.disabled = true;
    if (el.paperMaskReviewPanel) el.paperMaskReviewPanel.classList.add("hidden");

    // Try to get sequence from input
    let targetSeq = "";
    const fastaText = String(el.fastTargetInput?.value || "").trim();
    if (fastaText && !fastaText.startsWith("HEADER")) {
       targetSeq = fastaText.replace(/^>.*$/gm, '').replace(/\s+/g, '');
    }

    try {
      const response = await apiCall("pipeline.analyze_paper_for_masking", {
        file_b64: base64Data,
        target_sequence: targetSeq
      });
      
      if (response && response.success && response.result) {
        state.suggestedMasks = response.result.suggested_masks || [];
        renderPaperMaskReviewPanel();
      }
    } catch (err) {
      if (el.paperMaskStatus) el.paperMaskStatus.textContent = `Error: ${err.message}`;
    } finally {
      if (el.paperMaskUploadBtn) el.paperMaskUploadBtn.disabled = false;
      event.target.value = ""; // Reset input
    }
  };
  reader.readAsDataURL(file);
}

if (el.paperMaskUploadBtn && el.paperMaskInput) {
  el.paperMaskUploadBtn.addEventListener("click", () => el.paperMaskInput.click());
  el.paperMaskInput.addEventListener("change", handlePaperMaskUpload);
}
```

- [ ] **Step 3: Implement rendering logic for the review panel**

```javascript
function renderPaperMaskReviewPanel() {
  if (!el.paperMaskReviewPanel || !el.paperMaskList) return;
  
  if (!state.suggestedMasks || state.suggestedMasks.length === 0) {
    if (el.paperMaskStatus) el.paperMaskStatus.textContent = "No constraints found in the document.";
    return;
  }

  if (el.paperMaskStatus) el.paperMaskStatus.textContent = `Found ${state.suggestedMasks.length} constraint(s).`;
  el.paperMaskReviewPanel.classList.remove("hidden");
  el.paperMaskList.innerHTML = "";

  state.suggestedMasks.forEach((mask, index) => {
    const chain = String(mask.chain || "A");
    const resi = Number(mask.residue_index);
    const resn = String(mask.residue_name || "");
    const label = String(mask.label || "Constraint");
    const evidence = String(mask.evidence || "No evidence provided.");
    const confidence = String(mask.confidence || "high");
    
    const warningMarkup = confidence !== "high" ? `<span title="Sequence mismatch suspected" style="cursor:help;">⚠️</span>` : "";

    const item = document.createElement("div");
    item.style.cssText = "display: flex; flex-direction: column; padding: 0.5rem; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-color);";
    
    item.innerHTML = `
      <label style="display: flex; align-items: center; gap: 0.5rem; font-weight: 500;">
        <input type="checkbox" checked data-mask-index="${index}" class="paper-mask-checkbox" />
        Chain ${escapeHtml(chain)}: ${resi} ${escapeHtml(resn)} - ${escapeHtml(label)} ${warningMarkup}
      </label>
      <div style="margin-top: 0.25rem; font-size: 0.85em; color: var(--text-color-muted); padding-left: 1.5rem;">
        <em>"${escapeHtml(evidence)}"</em>
      </div>
    `;
    el.paperMaskList.appendChild(item);
  });
}
```

- [ ] **Step 4: Implement apply and cancel logic**

```javascript
if (el.paperMaskCancelBtn) {
  el.paperMaskCancelBtn.addEventListener("click", () => {
    if (el.paperMaskReviewPanel) el.paperMaskReviewPanel.classList.add("hidden");
    if (el.paperMaskStatus) el.paperMaskStatus.textContent = "";
    state.suggestedMasks = [];
  });
}

if (el.paperMaskApplyBtn) {
  el.paperMaskApplyBtn.addEventListener("click", () => {
    const checkboxes = Array.from(document.querySelectorAll(".paper-mask-checkbox"));
    const selectedIndexes = checkboxes.filter(cb => cb.checked).map(cb => Number(cb.getAttribute("data-mask-index")));
    
    const currentConstraintsRaw = String(el.evolutionFixedPositionsExtraInput?.value || "").trim();
    let currentConstraints = {};
    if (currentConstraintsRaw) {
      try {
        currentConstraints = JSON.parse(currentConstraintsRaw);
      } catch(e) {
        console.warn("Failed to parse existing fixed_positions_extra");
      }
    }

    let appliedCount = 0;
    selectedIndexes.forEach(index => {
      const mask = state.suggestedMasks[index];
      if (!mask) return;
      const chain = mask.chain || "A";
      const resi = Number(mask.residue_index);
      if (!Number.isFinite(resi)) return;
      
      if (!currentConstraints[chain]) currentConstraints[chain] = [];
      if (!currentConstraints[chain].includes(resi)) {
        currentConstraints[chain].push(resi);
        currentConstraints[chain].sort((a,b) => a - b);
        appliedCount++;
      }
    });

    if (appliedCount > 0) {
       const newJson = JSON.stringify(currentConstraints);
       if (el.evolutionFixedPositionsExtraInput) el.evolutionFixedPositionsExtraInput.value = newJson;
       
       // Update state.answers so it propagates
       state.answers.fixed_positions_extra = currentConstraints;
       
       setMessage(`Successfully applied ${appliedCount} residues to fixed_positions_extra.`, "ai");
    }

    if (el.paperMaskReviewPanel) el.paperMaskReviewPanel.classList.add("hidden");
    if (el.paperMaskStatus) el.paperMaskStatus.textContent = "";
  });
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/app.js
git commit -m "feat(ui): integrate paper masking agent logic"
```

---
