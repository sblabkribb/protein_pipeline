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

test("home new experiment opens a mode chooser instead of forcing fast launch", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(html, /data-home-target="experiment"/);
  assert.match(html, /id="experimentChoicePanel"/);
  assert.match(html, /data-experiment-target="fast"/);
  assert.match(html, /data-experiment-target="advanced"/);
  assert.match(html, /data-experiment-target="evolution"/);
  assert.match(html, /data-experiment-target="studio"/);
  assert.doesNotMatch(html, /class="home-mode-card launchpad-primary" type="button" data-home-target="fast"/);

  assert.match(source, /function openExperimentChoicePanel/);
  assert.match(source, /function handleExperimentChoice/);
  assert.match(source, /querySelectorAll\("\[data-experiment-target\]"\)/);
  assert.match(source, /"home\.experimentChoice\.advanced\.title"/);
  assert.match(source, /"home\.experimentChoice\.studio\.desc"/);
  assert.match(styles, /\.experiment-choice-grid/);
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
  assert.match(html, /id="setupPrimaryLayout"/);
  assert.match(html, /class="setup-lane setup-lane-input"/);
  assert.match(html, /id="setupStepSummary"/);
  assert.match(source, /function renderSetupStepSummary/);
  assert.match(source, /setupPrimaryLayout\.dataset\.activeStep/);
  assert.match(styles, /\.advanced-launch-frame/);
  assert.match(styles, /\.setup-step-summary/);
  assert.match(styles, /\.setup-primary-layout\[data-active-step="input"\]/);
  assert.match(styles, /\.setup-lane-execution\s*\{[\s\S]*?order:\s*-1;/m);
  assert.match(styles, /\.setup-primary-layout:not\(\[data-active-step="input"\]\)\s+\.setup-lane-input/);
  assert.match(source, /"setup\.wizard\.stepMeta": "Current step: \{label\}"/);
  assert.match(source, /"setup\.wizard\.stepMeta": "현재 단계: \{label\}"/);
});

test("advanced evolution controls live in workflow setup, not the input step", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(source, /if \(setupWizardStepId === "workflow"\) \{\s*appendEvolutionBoard\(\);\s*\}/m);
  assert.match(source, /"setup\.evolution\.title": "Optional Evolution Search"/);
  assert.match(source, /"setup\.evolution\.title": "Evolution 탐색 \(선택\)"/);
  assert.match(source, /"setup\.customRunId\.label"/);
  assert.doesNotMatch(html, /Custom Run ID/);
});

test("advanced optional setup boards are collapsed by default", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

  assert.match(source, /function makeOptionalSetupDetails/);
  assert.match(source, /document\.createElement\("details"\)/);
  assert.match(source, /optional-setup-card/);
  assert.match(source, /appendConfigCard\(makeOptionalSetupDetails\(card\)\);/);
  assert.match(source, /appendConfigCard\(makeOptionalSetupDetails\(card,\s*\{ defaultOpen: false \}\)\);/m);
  assert.match(styles, /\.optional-setup-card/);
  assert.match(styles, /\.optional-setup-summary/);
  assert.match(styles, /\.optional-setup-body/);
});

test("user-facing Korean tutorial copy avoids internal pipeline jargon", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(source, /"question\.runMode\.detail": "모드에 따라 필요한 입력, 실행 시간, 결과를 얼마나 자세히 만들지가 달라집니다\."/);
  assert.match(source, /"tutorial\.step\.homeRound\.body":\s*"먼저 프로젝트를 고른 뒤 이번 실험 회차를 만듭니다\. 이후 실행하는 작업은 그 프로젝트와 회차 아래에 기록됩니다\."/);
  assert.match(source, /"home\.context\.round": "현재 회차"/);
  assert.doesNotMatch(source, /출력 깊이/);
  assert.doesNotMatch(source, /활성 라운드/);
  assert.doesNotMatch(source, /project\/round 정보/);
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

  assert.match(source, /const TUTORIAL_STORAGE_KEY = "kbf\.tutorial\.completed\.v2"/);
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

test("tutorial covers expert workflow controls and downstream review tools", () => {
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(source, /id: "homeProject"/);
  assert.match(source, /id: "homeRound"/);
  assert.match(source, /id: "homeProject"[\s\S]*?target: "#homeCreateProjectBtn"[\s\S]*?id: "homeRound"[\s\S]*?target: "#homeCreateRoundBtn"/m);
  assert.match(source, /id: "advancedInput"[\s\S]*?setupStep: "input"/m);
  assert.match(source, /id: "advancedWorkflow"[\s\S]*?setupStep: "workflow"/m);
  assert.match(source, /id: "advancedCriteria"[\s\S]*?setupStep: "criteria"/m);
  assert.match(source, /id: "advancedExpert"[\s\S]*?setupStep: "expert"/m);
  assert.match(source, /id: "advancedReview"[\s\S]*?setupStep: "review"/m);
  assert.match(source, /id: "pdfAgent"/);
  assert.match(source, /id: "evolutionSettings"/);
  assert.match(source, /id: "studioCheckpoint"/);
  assert.match(source, /id: "monitorAgent"/);
  assert.match(source, /id: "analyzeHitList"/);
  assert.match(source, /id: "report"/);
  assert.match(source, /id: "copilot"/);

  assert.match(source, /function applyTutorialStepContext/);
  assert.match(source, /state\.setupStepIndex = stepIndex;/);
  assert.match(source, /"tutorial\.step\.homeProject\.title"/);
  assert.match(source, /"tutorial\.step\.homeRound\.title"/);
  assert.match(source, /"tutorial\.step\.advancedInput\.title"/);
  assert.match(source, /"tutorial\.step\.advancedWorkflow\.title"/);
  assert.match(source, /"tutorial\.step\.advancedCriteria\.title"/);
  assert.match(source, /"tutorial\.step\.advancedExpert\.title"/);
  assert.match(source, /"tutorial\.step\.advancedReview\.title"/);
  assert.match(source, /"tutorial\.step\.pdfAgent\.title"/);
  assert.match(source, /"tutorial\.step\.evolutionSettings\.title"/);
  assert.match(source, /"tutorial\.step\.studioCheckpoint\.title"/);
  assert.match(source, /"tutorial\.step\.monitorAgent\.title"/);
  assert.match(source, /"tutorial\.step\.analyzeHitList\.title"/);
  assert.match(source, /"tutorial\.step\.report\.title"/);
  assert.match(source, /"tutorial\.step\.copilot\.title"/);
});
