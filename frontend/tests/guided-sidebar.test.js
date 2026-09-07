import test from "node:test";
import assert from "node:assert/strict";
import { normalizeRuns, runItemLabel } from "../guided/sidebar.js";

test("normalizeRuns accepts string lists and object lists and dedupes", () => {
  const runs = normalizeRuns(["run_b", "run_a", "run_b", { run_id: "run_c", stage: "af2_50" }]);
  assert.deepEqual(runs.map((r) => r.run_id), ["run_b", "run_a", "run_c"]);
  assert.equal(runs[2].stage, "af2_50");
});

test("runItemLabel shows the stage chip and state", () => {
  assert.equal(runItemLabel({ run_id: "r1", stage: "af2_50", state: "running" }), "af2_50 · running");
  assert.equal(runItemLabel({ run_id: "r1" }), "idle");
});

test("normalizeRuns tolerates id-less objects, null entries and non-arrays", () => {
  assert.deepEqual(normalizeRuns([{ id: "run_x" }]).map((r) => r.run_id), ["run_x"]);
  assert.deepEqual(normalizeRuns([null]), []);
  assert.deepEqual(normalizeRuns("nope"), []);
});

test("runItemLabel falls back to state alone", () => {
  assert.equal(runItemLabel({ state: "done" }), "done");
});
