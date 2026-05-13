import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  buildProviderUpdatePayload,
  normalizeProviderType,
  providerConnectionSummary,
  visibleTokenLabel,
} from "../lib/model-providers.js";

test("provider type aliases normalize to the registry contract", () => {
  assert.equal(normalizeProviderType("http"), "http_api");
  assert.equal(normalizeProviderType("local_http"), "http_api");
  assert.equal(normalizeProviderType("runpod"), "runpod");
  assert.equal(normalizeProviderType("off"), "disabled");
  assert.equal(normalizeProviderType(""), "disabled");
});

test("provider update payload trims fields and never sends a blank token", () => {
  const payload = buildProviderUpdatePayload({
    modelKey: "proteinmpnn",
    providerType: " http ",
    endpointId: " ep-123 ",
    baseUrl: " http://127.0.0.1:18101/ ",
    token: "   ",
    timeoutS: "45",
    enabled: true,
  });

  assert.deepEqual(payload, {
    model_key: "proteinmpnn",
    provider: {
      provider_type: "http_api",
      endpoint_id: "ep-123",
      base_url: "http://127.0.0.1:18101",
      enabled: true,
      timeout_s: 45,
    },
  });
});

test("provider token display prefers masked values and never exposes raw token text", () => {
  const provider = {
    token: "raw-secret-token",
    token_masked: "********oken",
  };

  assert.equal(visibleTokenLabel(provider), "********oken");
  assert.doesNotMatch(visibleTokenLabel(provider), /raw-secret-token/);
});

test("provider summary explains the active connection target", () => {
  assert.equal(
    providerConnectionSummary({ provider_type: "http_api", base_url: "http://gpu:18101" }),
    "HTTP API: http://gpu:18101"
  );
  assert.equal(
    providerConnectionSummary({ provider_type: "runpod", endpoint_id: "abc123" }),
    "RunPod: abc123"
  );
  assert.equal(providerConnectionSummary({ provider_type: "disabled" }), "Disabled");
});

test("frontend exposes an in-app model provider manager instead of the legacy RunPod admin link", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(html, /id="runpodAdminBtn"[\s\S]*data-i18n="modelProviders\.open"/);
  assert.doesNotMatch(html, /runpod-admin/);
  assert.match(html, /id="modelProvidersPanel"/);
  assert.match(source, /pipeline\.model_provider_list/);
  assert.match(source, /pipeline\.model_provider_update/);
  assert.match(source, /pipeline\.model_provider_health/);
});

test("frontend admin panel exposes OIDC user approval controls", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(html, /id="adminUserList"/);
  assert.match(html, /id="adminRefreshUsers"/);
  assert.match(source, /\/auth\/list_users/);
  assert.match(source, /\/auth\/update_user/);
  assert.match(source, /data-admin-user-status/);
  assert.match(source, /data-admin-user-role/);
});
