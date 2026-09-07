import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mapStatusStageToStep, stageProgressPercent, nextPollDelayMs } from "../guided/monitor.js";

test("backend status stages map to the progress plan's steps", () => {
  assert.equal(mapStatusStageToStep("af2_50"), "af2");
  assert.equal(mapStatusStageToStep("relax_30"), "relax");
  assert.equal(mapStatusStageToStep("wt_diff"), "wt");
  assert.equal(mapStatusStageToStep("init"), "msa");
  assert.equal(mapStatusStageToStep("mmseqs_msa"), "msa");
  assert.equal(mapStatusStageToStep("rfd3"), "backbone");
  assert.equal(mapStatusStageToStep("bioemu"), "backbone");
  assert.equal(mapStatusStageToStep("proteinmpnn_50"), "design");
  assert.equal(mapStatusStageToStep("af2_target"), "af2");
  assert.equal(mapStatusStageToStep("wt_relax"), "wt");
  assert.equal(mapStatusStageToStep("ligand_mask"), "masking");
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

test("the poll loop invalidates stale ticks and stops on terminal states", () => {
  const src = readFileSync(new URL("../guided/monitor.js", import.meta.url), "utf8");
  assert.ok(src.includes("poll.gen += 1"), "stopPolling must invalidate in-flight ticks");
  assert.ok(src.includes("gen !== poll.gen"), "tick must bail when superseded");
  assert.ok(src.includes('"done", "failed", "cancelled"'), "terminal states must stop polling");
});

test("loadRunStatus is staleness-aware so a slow older response cannot repaint", () => {
  const src = readFileSync(new URL("../guided/monitor.js", import.meta.url), "utf8");
  assert.ok(src.includes("isStale"), "loadRunStatus must accept a staleness predicate");
  assert.ok(/isStale\(\)\s*(return|;)/.test(src) || src.includes("if (isStale()) return;"),
            "must bail before painting when stale");
});

test("the artifact preview bails on stale reads instead of painting", () => {
  const src = readFileSync(new URL("../guided/monitor.js", import.meta.url), "utf8");
  assert.ok(/openArtifact\(runId, path, format, maxBytes, \{ isStale/.test(src),
            "openArtifact must take the staleness predicate");
  assert.ok(/openArtifact\(runId, path, format, null, \{ isStale \}\)/.test(src),
            "artifact rows must thread the staleness predicate through");
});
