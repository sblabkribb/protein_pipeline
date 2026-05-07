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
