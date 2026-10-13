import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");

test("the assistant drawer always tells users their messages leave KRIBB", () => {
  const drawer = html.slice(html.indexOf('id="copilotDrawer"'), html.indexOf('id="copilotFabBtn"'));
  assert.match(drawer, /id="copilotExternalAiNotice"[^>]*data-i18n="externalAi\.copilotNotice"/);
});

test("both languages define the external-AI warnings", () => {
  for (const key of ["externalAi.copilotNotice", "externalAi.paperConfirm"]) {
    const count = app.split(`"${key}":`).length - 1;
    assert.equal(count, 2, `${key} should be defined once in English and once in Korean`);
  }
});

test("a paper PDF is not sent to Gemini until the user confirms", () => {
  const start = app.indexOf("function handlePaperMaskUpload(");
  const body = app.slice(start, app.indexOf("apiCall(\"pipeline.analyze_paper_for_masking\"", start));
  assert.match(body, /window\.confirm\(t\("externalAi\.paperConfirm"\)\)/);
  assert.ok(body.indexOf("window.confirm") < body.indexOf("new FileReader"), "confirm must come before the file is read");
});
