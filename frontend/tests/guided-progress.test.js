import test from "node:test";
import assert from "node:assert/strict";
import { mapStatusStageToStep, stageProgressPercent, nextPollDelayMs } from "../guided/monitor.js";

test("tier-suffixed status stages map to their base step", () => {
  assert.equal(mapStatusStageToStep("af2_50"), "af2");
  assert.equal(mapStatusStageToStep("relax_30"), "relax");
  assert.equal(mapStatusStageToStep("wt_diff"), "wt");
  assert.equal(mapStatusStageToStep("init"), "msa");
});

test("progress percent walks the request's step plan", () => {
  const steps = ["msa", "design", "soluprot", "af2", "done"];
  assert.equal(stageProgressPercent("msa", "running", steps), 20);
  assert.equal(stageProgressPercent("af2", "running", steps), 80);
  assert.equal(stageProgressPercent("done", "done", steps), 100);
  assert.equal(stageProgressPercent("unknown", "running", steps), 0);
});

test("polling backs off by activity and stops after repeated failures", () => {
  assert.equal(nextPollDelayMs(0, true), 5000);
  assert.equal(nextPollDelayMs(0, false), 30000);
  assert.equal(nextPollDelayMs(2, true), 5000);
  assert.equal(nextPollDelayMs(3, true), 0);
});
