# MCP Guide Localization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Localize the MCP tab guide for Korean users and add explicit `KBF_SSO_ACCESS_TOKEN` retrieval instructions for both local-auth and KBF SSO modes.

**Architecture:** Replace the MCP tab's hard-coded HTML body with a small `frontend/lib/mcp-guide.js` renderer that returns localized markup. Wire that renderer into `frontend/app.js` so the guide re-renders whenever the UI language changes, while keeping the existing styles and tab layout intact.

**Tech Stack:** Vanilla frontend JavaScript modules, static HTML shell, existing Node test runner.

---

### Task 1: Lock the desired MCP copy in tests

**Files:**
- Modify: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

```js
test("renderMcpGuideMarkup provides Korean token instructions for VS Code MCP", async () => {
  const mcpGuide = await import("../lib/mcp-guide.js").catch(() => null);
  assert.ok(mcpGuide && typeof mcpGuide.renderMcpGuideMarkup === "function");
});
```

**Step 2: Run test to verify it fails**

Run: `node frontend/tests/pipeline.test.js`
Expected: FAIL because `frontend/lib/mcp-guide.js` does not exist yet.

**Step 3: Write minimal implementation**

```js
export function renderMcpGuideMarkup() {
  return "";
}
```

**Step 4: Run test to verify it passes**

Run: `node frontend/tests/pipeline.test.js`
Expected: the missing-module failure is gone, then tighten the assertions for Korean and English copy.

### Task 2: Render localized MCP guide markup

**Files:**
- Create: `frontend/lib/mcp-guide.js`
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`

**Step 1: Build the localized helper**

```js
export function renderMcpGuideMarkup({ lang = "en" } = {}) {
  const copy = GUIDE_COPY[lang] || GUIDE_COPY.en;
  return `...`;
}
```

**Step 2: Replace the static MCP body with a render target**

```html
<div class="panel panel-block">
  <div id="mcpGuidePanel"></div>
</div>
```

**Step 3: Wire the renderer into the language refresh path**

```js
function renderMcpGuide() {
  if (!el.mcpGuidePanel) return;
  el.mcpGuidePanel.innerHTML = renderMcpGuideMarkup({ lang: state.lang });
}
```

**Step 4: Run tests to verify the guide content**

Run: `node frontend/tests/pipeline.test.js`
Expected: PASS with the Korean and English MCP guide tests green.

### Task 3: Validate syntax and browser pickup behavior

**Files:**
- Modify: `frontend/index.html`

**Step 1: Bump the module asset version**

```html
<script type="module" src="./app.js?v=20260316_mcp1"></script>
```

**Step 2: Run syntax checks**

Run: `node --check frontend/app.js`
Expected: PASS

Run: `node --check frontend/lib/mcp-guide.js`
Expected: PASS

**Step 3: Confirm deployment note**

No server restart should be needed for the static frontend; a browser refresh should load the new asset URL.
