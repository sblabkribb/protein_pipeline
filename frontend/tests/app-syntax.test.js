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
