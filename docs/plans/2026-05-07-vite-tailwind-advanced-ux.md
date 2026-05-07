# Vite Tailwind Advanced UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Vite/Tailwind build infrastructure and make the Advanced run setup easier to use through staged controls and cleaner visual hierarchy.

**Architecture:** Keep the current static frontend entrypoints operational while adding Vite as the build and dev layer. Add Tailwind v4 through the Vite plugin, but keep existing CSS as the compatibility layer for the current Caddy root. Implement Advanced UX changes in the existing `frontend/app.js`, `frontend/index.html`, and `frontend/styles.css` surface, with source-based tests for build wiring and staged setup behavior.

**Tech Stack:** Vanilla JavaScript modules, Vite, Tailwind CSS v4, Node test runner, static Caddy frontend deployment, GitHub Actions, Bash deployment script.

---

### Task 1: Add Vite And Tailwind Build Wiring

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vite.config.mjs`
- Create: `frontend/tailwind-entry.css`
- Modify: `frontend/tests/app-syntax.test.js`
- Modify: `.gitignore`

**Step 1: Write source checks**

Add tests in `frontend/tests/app-syntax.test.js` that assert:

```js
const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
assert.equal(packageJson.scripts.build, "vite build");
assert.equal(packageJson.scripts.dev, "vite --host 127.0.0.1");
assert.ok(packageJson.devDependencies.vite);
assert.ok(packageJson.devDependencies.tailwindcss);
assert.ok(packageJson.devDependencies["@tailwindcss/vite"]);

const viteConfig = readFileSync(new URL("../vite.config.mjs", import.meta.url), "utf8");
assert.match(viteConfig, /@tailwindcss\/vite/);
assert.match(viteConfig, /tailwindcss\(\)/);

const tailwindEntry = readFileSync(new URL("../tailwind-entry.css", import.meta.url), "utf8");
assert.match(tailwindEntry, /@import "tailwindcss"/);
```

**Step 2: Run test to verify it fails**

Run: `cd /opt/protein_pipeline-work && node --test frontend/tests/app-syntax.test.js`
Expected: FAIL because Vite/Tailwind files and scripts do not exist yet.

**Step 3: Add minimal Vite/Tailwind implementation**

Update `frontend/package.json` scripts and dev dependencies. Add `frontend/vite.config.mjs`:

```js
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
  },
});
```

Add `frontend/tailwind-entry.css`:

```css
@import "tailwindcss";

@theme {
  --font-sans: "Instrument Sans", "Space Grotesk", system-ui, sans-serif;
  --color-kbf-teal: #0f7a77;
  --color-kbf-ink: #182129;
  --color-kbf-paper: #fffdf8;
}
```

Add generated dependency lockfile with `npm --prefix frontend install`.

**Step 4: Run tests and build**

Run:

```bash
cd /opt/protein_pipeline-work
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: PASS.

**Step 5: Commit**

```bash
git add .gitignore frontend/package.json frontend/package-lock.json frontend/vite.config.mjs frontend/tailwind-entry.css frontend/tests/app-syntax.test.js
git commit -m "build: add vite tailwind frontend build"
```

### Task 2: Add Frontend Build To CI And Deployment

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Modify: `scripts/deploy/deploy_from_github.sh`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write source checks**

Add tests that assert:

```js
const workflow = readFileSync(new URL("../../.github/workflows/deploy.yml", import.meta.url), "utf8");
assert.match(workflow, /npm --prefix frontend ci/);
assert.match(workflow, /npm --prefix frontend run build/);

const deployScript = readFileSync(new URL("../../scripts/deploy/deploy_from_github.sh", import.meta.url), "utf8");
assert.match(deployScript, /npm --prefix frontend ci/);
assert.match(deployScript, /npm --prefix frontend run build/);
```

**Step 2: Run test to verify it fails**

Run: `cd /opt/protein_pipeline-work && node --test frontend/tests/app-syntax.test.js`
Expected: FAIL because CI and deploy scripts do not yet build the frontend.

**Step 3: Update workflow and deploy script**

In `.github/workflows/deploy.yml`, add after frontend node tests:

```yaml
          npm --prefix frontend ci
          npm --prefix frontend run build
```

In `scripts/deploy/deploy_from_github.sh`, add after Python dependency install:

```bash
if [[ -f frontend/package-lock.json ]]; then
  npm --prefix frontend ci
  npm --prefix frontend run build
fi
```

**Step 4: Verify**

Run:

```bash
cd /opt/protein_pipeline-work
node --test frontend/tests/app-syntax.test.js
npm --prefix frontend run build
```

Expected: PASS.

**Step 5: Commit**

```bash
git add .github/workflows/deploy.yml scripts/deploy/deploy_from_github.sh frontend/tests/app-syntax.test.js
git commit -m "ci: verify frontend vite build"
```

### Task 3: Enable Staged Advanced Setup

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write source checks**

Add tests that assert:

```js
assert.match(source, /const ENABLE_SETUP_WIZARD = true/);
assert.match(source, /setup\.wizard\.expert/);
assert.match(source, /setup\.wizard\.review/);
assert.match(source, /function renderSetupReviewCard/);
```

**Step 2: Run test to verify it fails**

Run: `cd /opt/protein_pipeline-work && node --test frontend/tests/app-syntax.test.js`
Expected: FAIL because wizard is disabled and review card does not exist yet.

**Step 3: Implement the staged setup**

- Change `ENABLE_SETUP_WIZARD` to `true`.
- Extend `SETUP_WIZARD_STEPS` to `scope`, `input`, `options`, `expert`, `review`.
- Update `questionSetupStepId()` to route:
  - `run_mode`, `start_from`, `stop_after` -> `scope`
  - target and file inputs -> `input`
  - common toggles and counts -> `options`
  - cutoffs, fixed positions, RFD3 internals, steering text -> `expert`
- Add `renderSetupReviewCard()` to summarize run mode, stages, target input presence, RFD3/BioEmu/AF2 settings, and selected conservation tiers.
- In `renderQuestions()`, append the review card when the active wizard step is `review`.

**Step 4: Verify**

Run:

```bash
cd /opt/protein_pipeline-work
node --test frontend/tests/app-syntax.test.js
node --check frontend/app.js
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/app.js frontend/tests/app-syntax.test.js
git commit -m "feat: stage advanced setup flow"
```

### Task 4: Refine Advanced Visual Hierarchy

**Files:**
- Modify: `frontend/styles.css`
- Modify: `frontend/index.html`
- Modify: `frontend/tests/app-syntax.test.js`

**Step 1: Write source checks**

Add tests that assert:

```js
assert.doesNotMatch(styles, /\.bg-orb/);
assert.match(styles, /--radius-sm:\s*8px/);
assert.match(styles, /\.setup-review-card/);
assert.match(styles, /\.expert-option/);
assert.match(html, /class="setup-primary-layout"/);
```

**Step 2: Run test to verify it fails**

Run: `cd /opt/protein_pipeline-work && node --test frontend/tests/app-syntax.test.js`
Expected: FAIL because current UI still uses orb background and lacks review/expert styling.

**Step 3: Implement visual changes**

- Remove decorative `bg-orb` markup from `frontend/index.html`.
- Add a `setup-primary-layout` class to the Advanced grid wrapper.
- Introduce compact tokens in `frontend/styles.css`: `--radius-sm`, `--radius-md`, `--surface-muted`.
- Make setup cards tighter, with clearer headings and lower radius.
- Add `.setup-review-card`, `.setup-review-grid`, `.expert-option`, and stronger focus-visible styles.
- Keep mobile layout single-column and prevent button text overflow.

**Step 4: Verify**

Run:

```bash
cd /opt/protein_pipeline-work
node --test frontend/tests/app-syntax.test.js
npm --prefix frontend run build
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/index.html frontend/styles.css frontend/tests/app-syntax.test.js
git commit -m "style: refine advanced setup console"
```

### Task 5: Deploy To Development And Inspect

**Files:**
- No source changes expected unless verification finds a bug.

**Step 1: Run full local verification**

Run:

```bash
cd /opt/protein_pipeline-work
node --test frontend/tests/app-syntax.test.js frontend/tests/auth-session.test.js frontend/tests/auth.test.js frontend/tests/login-bootstrap.test.js frontend/tests/mcp-tab.test.js frontend/tests/runpod-admin.test.js
(cd frontend && node --test tests/logout-bridge.test.js)
npm --prefix frontend run build
```

Expected: PASS.

**Step 2: Push develop**

Run:

```bash
git push origin develop
```

Expected: GitHub Actions starts for `develop`.

**Step 3: Watch GitHub Actions**

Run:

```bash
gh run list --repo sblabkribb/protein_pipeline --workflow deploy.yml --limit 3
gh run watch <develop-run-id> --repo sblabkribb/protein_pipeline
```

Expected: PASS.

**Step 4: Verify dev health and UI**

Run:

```bash
curl -ksS https://dev-pipeline.k-biofoundrycopilot.duckdns.org/api/healthz
```

Expected: `{"ok": true}`.

Use browser/devtools screenshot checks to confirm the Advanced tab shows staged setup, compact cards, and no layout overlap on desktop and mobile widths.

