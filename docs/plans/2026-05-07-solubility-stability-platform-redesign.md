# KBF Protein Solubility and Stability Platform Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebrand the frontend as KBF Protein Solubility & Stability Platform and reshape the UI around experiment-first setup with a redesigned Advanced flow.

**Architecture:** Keep the existing static frontend entrypoints and backend contracts intact while redesigning the shell, first screen, design tokens, and Advanced setup IA. Use source-based tests to guard the new naming, Tailwind-inspired palette tokens, first-screen action structure, and Advanced step mapping before editing implementation files.

**Tech Stack:** Vanilla JavaScript modules, Vite, Tailwind CSS v4 reference palette, CSS custom properties, Node test runner, GitHub Actions deploy workflow.

---

### Task 1: Rebrand Product Naming

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write the failing test**

Add a test to `frontend/tests/app-syntax.test.js`:

```js
test("frontend uses solubility and stability platform branding", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(html, /KBF Protein Solubility &amp; Stability Platform/);
  assert.match(source, /KBF Protein Solubility & Stability Platform/);
  assert.doesNotMatch(html, /Protein Pipeline Console/);
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
node frontend/tests/app-syntax.test.js
```

Expected: FAIL because the current UI still uses Protein Pipeline Console branding.

**Step 3: Implement the minimal branding change**

Update `frontend/index.html`:

- `<title>` to `KBF | Protein Solubility & Stability Platform`
- `.brand-title` visible text to `KBF`
- `.brand-subtitle` visible text to `Protein Solubility & Stability Platform`

Update `frontend/app.js` i18n:

- `brand.subtitle` English to `Protein Solubility & Stability Platform`
- `brand.subtitle` Korean to `Protein Solubility & Stability Platform`
- help/home copy that says "Protein Pipeline Console" to the new platform name.

**Step 4: Verify**

Run:

```bash
node frontend/tests/app-syntax.test.js
node --check frontend/app.js
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/tests/app-syntax.test.js
git commit -m "brand: rename solubility stability platform"
```

### Task 2: Add Tailwind-Inspired Design Tokens

**Files:**
- Modify: `frontend/tailwind-entry.css`
- Modify: `frontend/styles.css`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write the failing test**

Add a test:

```js
test("frontend exposes Tailwind-inspired platform color tokens", () => {
  const tailwindEntry = readFileSync(new URL("../tailwind-entry.css", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(tailwindEntry, /--color-platform-teal/);
  assert.match(tailwindEntry, /--color-platform-emerald/);
  assert.match(tailwindEntry, /--color-platform-slate/);
  assert.match(styles, /--surface-canvas/);
  assert.match(styles, /--action-primary/);
  assert.match(styles, /--state-success/);
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
node frontend/tests/app-syntax.test.js
```

Expected: FAIL because semantic platform tokens do not exist yet.

**Step 3: Implement design tokens**

Update `frontend/tailwind-entry.css` `@theme` with platform aliases:

```css
@theme {
  --font-sans: "Instrument Sans", "Space Grotesk", system-ui, sans-serif;
  --color-platform-slate: oklch(27.9% 0.041 260.031);
  --color-platform-teal: oklch(51.1% 0.096 186.391);
  --color-platform-emerald: oklch(50.8% 0.118 165.612);
  --color-platform-amber: oklch(66.6% 0.179 58.318);
}
```

Update `frontend/styles.css` `:root` with semantic tokens:

```css
--surface-canvas: oklch(98.4% 0.003 247.858);
--surface-panel: #ffffff;
--surface-muted: oklch(96.8% 0.007 247.896);
--text-strong: oklch(12.9% 0.042 264.695);
--text-body: oklch(27.9% 0.041 260.031);
--text-muted: oklch(55.4% 0.046 257.417);
--action-primary: oklch(51.1% 0.096 186.391);
--action-primary-hover: oklch(43.7% 0.078 188.216);
--state-success: oklch(50.8% 0.118 165.612);
--state-warning: oklch(66.6% 0.179 58.318);
```

Then map existing broad variables (`--bg`, `--paper`, `--ink`, `--teal`) to those semantic tokens where safe.

**Step 4: Verify**

Run:

```bash
node frontend/tests/app-syntax.test.js
npm --prefix frontend run build
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/tailwind-entry.css frontend/styles.css frontend/tests/app-syntax.test.js
git commit -m "style: add platform design tokens"
```

### Task 3: Redesign Home As Experiment Launchpad

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write the failing test**

Add a test:

```js
test("home screen is an experiment launchpad", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(html, /class="experiment-launchpad"/);
  assert.match(source, /home\.launchpad\.newExperiment/);
  assert.match(source, /home\.launchpad\.loadRun/);
  assert.match(source, /home\.launchpad\.analyzeResults/);
  assert.match(styles, /\.experiment-launchpad/);
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
node frontend/tests/app-syntax.test.js
```

Expected: FAIL because the current home screen still uses the existing home card grid.

**Step 3: Implement launchpad markup**

Replace the primary home card area in `frontend/index.html` with:

- `section.experiment-launchpad`
- primary action card: New Solubility/Stability Experiment
- secondary action card: Load Existing Run
- secondary action card: Analyze Results
- compact context strip for environment and current run.

Use existing button targets where possible:

- New Experiment opens `advanced` or `fast`.
- Load Existing Run opens `monitor`.
- Analyze Results opens `analyze`.

**Step 4: Add i18n strings**

Add English/Korean keys in `frontend/app.js`:

- `home.launchpad.title`
- `home.launchpad.subtitle`
- `home.launchpad.newExperiment`
- `home.launchpad.newExperimentDesc`
- `home.launchpad.loadRun`
- `home.launchpad.loadRunDesc`
- `home.launchpad.analyzeResults`
- `home.launchpad.analyzeResultsDesc`

**Step 5: Add CSS**

Add `.experiment-launchpad`, `.experiment-action-grid`, `.experiment-action-card`, and compact responsive rules. Keep the first screen dense and avoid a marketing hero.

**Step 6: Verify**

Run:

```bash
node frontend/tests/app-syntax.test.js
node --check frontend/app.js
```

Expected: PASS.

**Step 7: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css frontend/tests/app-syntax.test.js
git commit -m "feat: redesign home experiment launchpad"
```

### Task 4: Rework Advanced Step IA

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write the failing test**

Add a test:

```js
test("advanced setup uses experiment builder steps", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(source, /setup\.wizard\.workflow/);
  assert.match(source, /setup\.wizard\.criteria/);
  assert.doesNotMatch(source, /setup\.wizard\.scope/);
  assert.doesNotMatch(source, /setup\.wizard\.options/);
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
node frontend/tests/app-syntax.test.js
```

Expected: FAIL because the current staged setup uses Scope and Options.

**Step 3: Update wizard steps**

Change `SETUP_WIZARD_STEPS` to:

```js
const SETUP_WIZARD_STEPS = [
  { id: "input", labelKey: "setup.wizard.input" },
  { id: "workflow", labelKey: "setup.wizard.workflow" },
  { id: "criteria", labelKey: "setup.wizard.criteria" },
  { id: "expert", labelKey: "setup.wizard.expert" },
  { id: "review", labelKey: "setup.wizard.review" },
];
```

Update `questionSetupStepId()`:

- target/file inputs -> `input`
- `run_mode`, `start_from`, `stop_after`, stage toggles -> `workflow`
- AF2/Relax/BioEmu count and threshold controls -> `criteria`
- RFD3 internals, steering text, fixed positions, compare scope -> `expert`
- `confirm_run` -> `review`

**Step 4: Update i18n**

Replace:

- `setup.wizard.scope`
- `setup.wizard.options`

With:

- `setup.wizard.workflow`
- `setup.wizard.criteria`

Use Korean labels:

- `Workflow`
- `평가 기준`

**Step 5: Verify**

Run:

```bash
node frontend/tests/app-syntax.test.js
node --check frontend/app.js
```

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/app.js frontend/tests/app-syntax.test.js
git commit -m "feat: align advanced setup with experiment workflow"
```

### Task 5: Polish Advanced Layout And Paper Mask UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write the failing test**

Add a test:

```js
test("advanced setup avoids inline styles and exposes platform panels", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.doesNotMatch(html, /style="/);
  assert.match(html, /class="paper-mask-panel"/);
  assert.match(styles, /\.paper-mask-panel/);
  assert.match(styles, /\.criteria-board/);
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
node frontend/tests/app-syntax.test.js
```

Expected: FAIL because Advanced still has inline paper mask styles and criteria styling is implicit.

**Step 3: Move inline styles to CSS**

Replace the Advanced paper mask block inline styles with classes:

- `.paper-mask-panel`
- `.paper-mask-controls`
- `.paper-mask-status`
- `.paper-mask-review`
- `.paper-mask-actions`

Keep IDs unchanged so existing JS continues to work.

**Step 4: Add criteria board class**

When rendering the compact parameter board for criteria fields, add class `criteria-board` to the card. Keep payload behavior unchanged.

**Step 5: Verify**

Run:

```bash
node frontend/tests/app-syntax.test.js
node --check frontend/app.js
npm --prefix frontend run build
```

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css frontend/tests/app-syntax.test.js
git commit -m "style: polish advanced experiment builder"
```

### Task 6: Full Verification And Development Deploy

**Files:**
- No source changes expected unless verification exposes a defect.

**Step 1: Run dependency install check**

Run:

```bash
npm --prefix frontend ci
```

Expected: PASS. If sandbox blocks esbuild execution, rerun outside sandbox with approval.

**Step 2: Run frontend deployment checks**

Run:

```bash
node --test \
  frontend/tests/app-syntax.test.js \
  frontend/tests/auth-session.test.js \
  frontend/tests/auth.test.js \
  frontend/tests/login-bootstrap.test.js \
  frontend/tests/mcp-tab.test.js \
  frontend/tests/runpod-admin.test.js
cd frontend && node --test tests/logout-bridge.test.js
```

Expected: PASS.

**Step 3: Run backend deployment checks**

Run:

```bash
PYTHONPATH=pipeline-mcp/src pytest \
  pipeline-mcp/tests/test_http_server_auth.py \
  pipeline-mcp/tests/test_mcp_http_route.py \
  pipeline-mcp/tests/test_oidc_auth.py \
  pipeline-mcp/tests/test_session_auth.py \
  pipeline-mcp/tests/test_runpod_admin.py
```

Expected: PASS.

**Step 4: Run Vite build**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS. Chunk size warning is acceptable for this static migration phase.

**Step 5: Push develop**

Run:

```bash
git push origin develop
```

Expected: push succeeds and triggers `Deploy Protein Pipeline`.

**Step 6: Watch GitHub Actions**

Run:

```bash
gh run list --repo sblabkribb/protein_pipeline --limit 5
gh run watch <run-id> --repo sblabkribb/protein_pipeline --exit-status
```

Expected: test and deploy jobs succeed.

**Step 7: Verify development deployment**

Run:

```bash
git -C /opt/protein_pipeline-dev rev-parse --short HEAD
curl -ksS https://dev-pipeline.k-biofoundrycopilot.duckdns.org/api/healthz
curl -ksS https://dev-pipeline.k-biofoundrycopilot.duckdns.org/ | rg "Protein Solubility|experiment-launchpad"
```

Expected:

- deployed HEAD matches local HEAD,
- health returns `{"ok": true}`,
- deployed HTML contains the new platform name and launchpad marker.

**Step 8: Commit any verification fix**

If verification required fixes, commit them with a focused message. Otherwise no commit is needed.
