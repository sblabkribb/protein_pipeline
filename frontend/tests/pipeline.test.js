import test from "node:test";
import assert from "node:assert/strict";
import {
  buildRunArguments,
  buildUserPrefix,
  createRunId,
  detectTargetKey,
  filterRunsByPrefix,
  sanitizeName,
  stageFromPath,
} from "../lib/pipeline.js";

test("sanitizeName normalizes", () => {
  assert.equal(sanitizeName(" Hana Kim "), "hana_kim");
  assert.equal(sanitizeName("K-Biofoundry!!"), "k-biofoundry");
  assert.equal(sanitizeName("..."), "");
});

test("buildUserPrefix builds org_name", () => {
  const prefix = buildUserPrefix({ name: "Hana", org: "KBF" });
  assert.equal(prefix, "kbf_hana");
});

test("createRunId uses prefix and utc timestamp", () => {
  const runId = createRunId("kbf_hana", new Date(Date.UTC(2024, 0, 2, 3, 4, 5)));
  assert.match(runId, /^kbf_hana_20240102_030405_[0-9a-f]{8}$/);
});

test("stageFromPath inference", () => {
  assert.equal(stageFromPath("msa/a3m.gz"), "msa");
  assert.equal(stageFromPath("designs/seqs.fasta"), "design");
  assert.equal(stageFromPath("af2/ranking_debug.json"), "af2");
});

test("buildRunArguments merges routed and answers", () => {
  const args = buildRunArguments({
    prompt: "design",
    routed: { stop_after: "design" },
    answers: { target_pdb: "PDB" },
    runId: "run1",
  });
  assert.equal(args.prompt, "design");
  assert.equal(args.stop_after, "design");
  assert.equal(args.target_pdb, "PDB");
  assert.equal(args.run_id, "run1");
});

test("filterRunsByPrefix", () => {
  const runs = ["kbf_user_1", "other_2", "kbf_user_3"];
  assert.deepEqual(filterRunsByPrefix(runs, "kbf_user"), ["kbf_user_1", "kbf_user_3"]);
});

test("detectTargetKey", () => {
  assert.equal(detectTargetKey(">seq\nAAAA"), "target_fasta");
  assert.equal(detectTargetKey("ATOM      1  N"), "target_pdb");
  assert.equal(detectTargetKey("ACDEFGHIK"), "target_fasta");
});
