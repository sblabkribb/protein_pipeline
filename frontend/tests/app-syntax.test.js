import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("frontend app source parses as an ES module", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const tempDir = mkdtempSync(join(tmpdir(), "kbf-app-check-"));
  const tempFile = join(tempDir, "app-check.mjs");
  writeFileSync(tempFile, source, "utf8");

  let output = "";
  try {
    execFileSync(process.execPath, ["--check", tempFile], {
      encoding: "utf8",
      stdio: "pipe",
    });
  } catch (error) {
    output = `${error.stdout || ""}${error.stderr || ""}`.trim();
  }

  assert.equal(output, "");
});

test("managed background jobs stay in CATH ops instead of the run monitor", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.doesNotMatch(html, /id="monitorManagedJobsSection"/);
  assert.doesNotMatch(html, /id="monitorManagedJobsList"/);
  assert.match(source, /pipeline\.cath_list_jobs/);
  assert.match(source, /data-cath-job-delete/);
  assert.match(source, /pipeline\.cath_delete_job/);
});

test("pipeline route defaults do not silently force RFD3 on", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.doesNotMatch(
    source,
    /if \(mode === "pipeline"\) return \{[^}]*rfd3_use:\s*true[^}]*\}/
  );
});

test("non-production hosts get visible environment badges", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(html, /id="environmentBadge"/);
  assert.match(source, /dev-pipeline\.k-biofoundrycopilot\.duckdns\.org/);
  assert.match(source, /staging-pipeline\.k-biofoundrycopilot\.duckdns\.org/);
  assert.match(source, /body\.dataset\.environment/);
  assert.match(styles, /body\[data-environment="development"\]/);
  assert.match(styles, /body\[data-environment="staging"\]/);
});

test("frontend has Vite and Tailwind build wiring", () => {
  const packageJson = JSON.parse(
    readFileSync(new URL("../package.json", import.meta.url), "utf8")
  );
  const viteConfig = readFileSync(
    new URL("../vite.config.mjs", import.meta.url),
    "utf8"
  );
  const tailwindEntry = readFileSync(
    new URL("../tailwind-entry.css", import.meta.url),
    "utf8"
  );

  assert.equal(packageJson.scripts.build, "vite build");
  assert.equal(packageJson.scripts.dev, "vite --host 127.0.0.1");
  assert.ok(packageJson.devDependencies.vite);
  assert.ok(packageJson.devDependencies.tailwindcss);
  assert.ok(packageJson.devDependencies["@tailwindcss/vite"]);
  assert.match(viteConfig, /@tailwindcss\/vite/);
  assert.match(viteConfig, /tailwindcss\(\)/);
  assert.match(tailwindEntry, /@import "tailwindcss"/);
});

test("frontend build runs in deployment checks and local deploy", () => {
  const workflow = readFileSync(
    new URL("../../.github/workflows/deploy.yml", import.meta.url),
    "utf8"
  );
  const deployScript = readFileSync(
    new URL("../../scripts/deploy/deploy_from_github.sh", import.meta.url),
    "utf8"
  );

  assert.match(workflow, /npm --prefix frontend ci/);
  assert.match(workflow, /npm --prefix frontend run build/);
  assert.match(deployScript, /npm --prefix frontend ci/);
  assert.match(deployScript, /npm --prefix frontend run build/);
});

test("advanced setup uses a staged wizard with a final review step", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(source, /const ENABLE_SETUP_WIZARD = true/);
  assert.match(source, /setup\.wizard\.expert/);
  assert.match(source, /setup\.wizard\.review/);
  assert.match(source, /function renderSetupReviewCard/);
});

test("advanced setup visual hierarchy uses compact review and expert styling", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.doesNotMatch(styles, /\.bg-orb/);
  assert.match(styles, /--radius-sm:\s*8px/);
  assert.match(styles, /\.setup-review-card/);
  assert.match(styles, /\.expert-option/);
  assert.match(html, /class="setup-ux-grid setup-primary-layout"/);
});

test("frontend uses solubility and stability platform branding", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(html, /KBF Protein Solubility &amp; Stability Platform/);
  assert.match(source, /KBF Protein Solubility & Stability Platform/);
  assert.doesNotMatch(html, /Protein Pipeline Console/);
});

test("frontend exposes Tailwind-inspired platform color tokens", () => {
  const tailwindEntry = readFileSync(
    new URL("../tailwind-entry.css", import.meta.url),
    "utf8"
  );
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(tailwindEntry, /--color-platform-teal/);
  assert.match(tailwindEntry, /--color-platform-emerald/);
  assert.match(tailwindEntry, /--color-platform-slate/);
  assert.match(styles, /--surface-canvas/);
  assert.match(styles, /--action-primary/);
  assert.match(styles, /--state-success/);
});

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

test("advanced setup uses experiment builder steps", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(source, /setup\.wizard\.workflow/);
  assert.match(source, /setup\.wizard\.criteria/);
  assert.doesNotMatch(source, /setup\.wizard\.scope/);
  assert.doesNotMatch(source, /setup\.wizard\.options/);
});

test("advanced paper mask UI is class-driven", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(html, /class="paper-mask-panel/);
  assert.match(source, /paper-mask-suggestion/);
  assert.match(styles, /\.paper-mask-panel/);
  assert.doesNotMatch(html, /style="/);
  assert.doesNotMatch(source, /item\.style\.cssText/);
});

test("fast advanced action opens advanced without requiring target input", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(source, /function openAdvancedFromFast\(\)/);
  assert.match(
    source,
    /fastOpenAdvancedBtn\?\.[\s\S]*?addEventListener\("click", \(\) => \{\s*openAdvancedFromFast\(\);\s*\}\);/
  );
});

test("advanced launch form uses a single ordered settings surface", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(html, /class="advanced-launch-frame"/);
  assert.match(html, /id="setupStepSummary"/);
  assert.match(source, /function renderSetupStepSummary/);
  assert.match(styles, /\.advanced-launch-frame/);
  assert.match(styles, /\.setup-step-summary/);
});

test("platform palette avoids beige-dominant application backgrounds", () => {
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.doesNotMatch(styles, /#f8f4ec/);
  assert.doesNotMatch(styles, /255,\s*253,\s*248/);
  assert.doesNotMatch(styles, /255,\s*249,\s*235/);
  assert.doesNotMatch(styles, /248,\s*245,\s*239/);
  assert.match(styles, /--surface-canvas:\s*oklch\(98\.5% 0\.002 247\.839\)/);
});

test("frontend includes a localized first-run tutorial overlay", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(html, /id="tutorialBtn"/);
  assert.match(html, /id="tutorialOverlay"/);
  assert.match(html, /id="tutorialSpotlight"/);
  assert.match(html, /id="tutorialStepTitle"/);
  assert.match(html, /id="tutorialSkip"/);
  assert.match(html, /id="tutorialNext"/);

  assert.match(source, /const TUTORIAL_STORAGE_KEY = "kbf\.tutorial\.completed\.v1"/);
  assert.match(source, /const TUTORIAL_STEPS = \[/);
  assert.match(source, /function maybeShowTutorialOnFirstVisit/);
  assert.match(source, /function openTutorial/);
  assert.match(source, /"action\.tutorial"/);
  assert.match(source, /"tutorial\.step\.settings\.title"/);
  assert.match(source, /"tutorial\.step\.evolution\.title"/);
  assert.match(source, /"tutorial\.step\.studio\.title"/);
  assert.match(source, /"tutorial\.step\.rounds\.title"/);
  assert.match(source, /"tutorial\.step\.analyze\.title"/);

  assert.match(styles, /\.tutorial-overlay/);
  assert.match(styles, /\.tutorial-spotlight/);
  assert.match(styles, /\.tutorial-card/);
});
