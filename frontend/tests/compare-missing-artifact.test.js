import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isArtifactNotFoundError } from "../lib/compare.js";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

test("a missing artifact is recognised as no-data, not a transport fault", () => {
  assert.equal(isArtifactNotFoundError(new Error("artifact not found")), true);
  assert.equal(isArtifactNotFoundError({ message: "Artifact Not Found" }), true);
  assert.equal(isArtifactNotFoundError("artifact not found"), true);

  assert.equal(isArtifactNotFoundError(new Error("unauthorized")), false);
  assert.equal(isArtifactNotFoundError(new Error("network timeout")), false);
  assert.equal(isArtifactNotFoundError(null), false);
  assert.equal(isArtifactNotFoundError(undefined), false);
});

test("the compare studio shows no-data instead of the raw error", () => {
  assert.match(
    source,
    /if \(isArtifactNotFoundError\(err\)\) \{\s*setComparePreviewPlaceholder\("artifacts\.preview\.compare\.noData"\);/,
    "a missing artifact should route to the no-data placeholder"
  );
});

test("switching runs clears the previous run's compare selection", () => {
  // Resetting only the select element would leave the stale path live in state,
  // and the next comparison would request an artifact this run does not have.
  assert.match(
    source,
    /if \(!leftPaths\.has\(state\.artifactCompareLeftPath\)\) \{\s*state\.artifactCompareLeftPath = "";/,
    "left compare path should be cleared when absent from the current run"
  );
  assert.match(
    source,
    /if \(!rightPaths\.has\(state\.artifactCompareRightPath\)\) \{\s*state\.artifactCompareRightPath = "";/,
    "right compare path should be cleared when absent from the current run"
  );
  assert.match(
    source,
    /el\.artifactCompareLeft\.value = state\.artifactCompareLeftPath;/,
    "the select should follow state rather than diverge from it"
  );
});

test("the no-data message exists in both locales", () => {
  const keys = source.match(/"artifacts\.preview\.compare\.noData":/g) || [];
  assert.equal(keys.length, 2, "expected an English and a Korean entry");
  assert.match(source, /"artifacts\.preview\.compare\.noData": "No data\./);
  assert.match(source, /"artifacts\.preview\.compare\.noData": "데이터 없음\./);
});
