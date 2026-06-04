# MCP One-Click Token + Integrated Skill Download — Design

Date: 2026-06-04
Status: Approved (brainstorming) — ready for implementation plan
Scope: `protein_pipeline-work` → dev → staging → prod

## Problem

Connecting the shared protein-pipeline MCP endpoint from VS Code / Codex / Claude
currently requires the user to **manually dig a bearer token out of browser
devtools** (`Local Storage` > `auth-storage` > `access_token`) and paste it into
`mcp.json`. The MCP tab guide (`frontend/lib/mcp-guide.js`) documents this manual
flow.

Two gaps:

1. **No automatic token retrieval.** A Claude/VS Code *skill* is just markdown
   instructions; it cannot itself perform SSO/OAuth login and fetch a token. The
   MCP server (`/mcp`) only validates an `Authorization: Bearer <token>` header and
   exposes **no** OAuth authorization-server metadata
   (`.well-known/oauth-protected-resource`, `/authorize`, `/token`, dynamic client
   registration). So clients cannot do an automatic login dance today.
2. **The existing skill does not cover connection.** `protein-pipeline-stepper`
   only documents *how to run the pipeline once connected* — nothing about auth or
   getting a token.

## Decisions (from brainstorming)

- **Phased approach — ship one-click token first.** Real MCP OAuth (automatic
  browser login + token refresh handled by the client) is the eventual "fully
  automatic" answer but is larger/riskier and has weaker client support (Codex).
  It is **out of scope** for this round.
- **One integrated skill** (connection + execution in a single
  `protein-pipeline-stepper` skill), downloadable from the MCP tab.
- **Hand out the SSO token as-is + show expiry.** The server returns the session's
  (refreshed) `access_token`; the UI tells the user when it expires and to click
  again to refresh. No new long-lived credential store is introduced.

## Feasibility (verified in code)

- `SessionManager` already stores OIDC `access_token` / `refresh_token` /
  `access_expires_at` and has refresh logic (`refresh_oidc_tokens`,
  `get_oidc_id_token`). A server-side endpoint can return a freshly-refreshed
  access token.
- `_send_model_registration_skill_archive()` + `GET /model_provider_skill.zip` +
  frontend `downloadModelRegistrationSkill()` are an existing, working pattern for
  "download a skill zip from a tab" — we mirror it.
- Route handling in `http_server.py` is path-based (`route_path == "/auth/me"`,
  etc.) with prefix normalization, and `_require_auth()` gates authenticated GETs.

## Components

### 1. Backend — token endpoint (`pipeline-mcp/src/pipeline_mcp/http_server.py`)

- `GET /auth/mcp_token`, gated by `_require_auth()` (mirror `/auth/me`).
  - **OIDC session:** refresh if near expiry (reuse existing refresh path), then
    return the current `access_token`. Add `SessionManager.get_oidc_access_token()`
    in `session_auth.py`, symmetric to the existing `get_oidc_id_token()`, returning
    `(token, access_expires_at)`.
  - **Local session:** return the local bearer token.
  - Response JSON: `{ "ok": true, "token": "<bearer>", "auth_type": "oidc"|"local",
    "expires_at": <epoch seconds or 0> }`.
  - Token is in the body only; respond with `Cache-Control: no-store`.
  - Unauthenticated → existing 401 path (`_require_auth` already emits it).

### 2. Backend — skill zip endpoint

- `GET /pipeline_skill.zip` → new `_send_pipeline_skill_archive()`, mirroring
  `_send_model_registration_skill_archive()`.
  - Source dir: the repo's `skills/protein-pipeline-stepper/`, overridable via env
    `PIPELINE_STEPPER_SKILL_DIR` (default resolves to the in-repo path).
  - Archive root folder `protein-pipeline-stepper/`, download filename
    `protein-pipeline-stepper.zip`, `Cache-Control: no-store`.
  - Auth-gated consistently with the model-registration archive.

### 3. Skill update (`skills/protein-pipeline-stepper/SKILL.md`)

- Prepend a **"Connecting (MCP auth)"** section:
  - Get a token with one click from the pipeline app's MCP tab and paste the
    generated `mcp.json` into the client (VS Code: *MCP: Open User Configuration*;
    Codex: add server with the same URL + `Authorization` header).
  - Note that SSO tokens are short-lived; when calls start returning 401, click the
    button again to refresh the token in `mcp.json`.
  - Keep the existing execution sections (Stage Runner, stage templates) unchanged.
- Update the front-matter `description` to cover **connection + execution**.

### 4. Frontend — MCP tab (`frontend/lib/mcp-guide.js`, `frontend/app.js`, `index.html`)

- Replace the "3) How to get the token" manual-devtools copy with a **one-click**
  control:
  - Button `Copy mcp.json with my token` → `fetch(${apiBase}/auth/mcp_token)` with
    credentials → inject the returned token into the `mcp.json` snippet (replacing
    `<KBF_SSO_ACCESS_TOKEN>`) → copy to clipboard.
  - Show "expires in ≈N min — click again when it stops working" using `expires_at`.
  - On 401 / no session: show a "sign in first" hint instead of a token.
- Add a **skill download** card/button → `downloadPipelineSkill()` →
  `${apiBase}/pipeline_skill.zip` (mirror `downloadModelRegistrationSkill()`,
  including the element wiring near `modelProviderSkillDownload`).
- Update **both** `ko` and `en` copy in `GUIDE_COPY`. Keep the existing bilingual
  structure.

### 5. Tests

- `frontend/tests/mcp-tab.test.js`: assert the rendered markup includes the skill
  download control and the one-click token control (and no longer instructs raw
  devtools copying as the only path).
- Backend tests (alongside existing `pipeline-mcp/tests/`):
  - `/auth/mcp_token` requires auth; returns token + `expires_at` for OIDC and for
    local sessions.
  - `/pipeline_skill.zip` returns a zip containing `protein-pipeline-stepper/SKILL.md`.

### 6. Deployment

- Use the existing pipeline (`scripts/deploy/deploy_from_github.sh` +
  `protein_pipeline-actions-runner`). Promote **work → dev → staging → prod**,
  verifying the MCP tab (token copy + skill download) at each stage before
  promoting. Ensure `PIPELINE_STEPPER_SKILL_DIR` resolves correctly in each
  deployed environment (or rely on the in-repo default).

## Data flow (one-click token)

```
Browser (session cookie)
  → GET /auth/mcp_token  (credentials: include)
  → server reads session; OIDC: refresh if near expiry → access_token
  → JSON { token, auth_type, expires_at }
  → JS injects token into mcp.json snippet
  → clipboard copy + expiry hint shown
```

## Out of scope (next round)

- Real MCP OAuth: `.well-known/oauth-protected-resource` +
  `.well-known/oauth-authorization-server` (or thin proxy to the existing OIDC/SSO
  provider), `/authorize`, `/token`, PKCE, dynamic client registration — enabling
  VS Code/Claude to log in automatically and auto-refresh with no copying.
- A dedicated, long-lived, revocable per-user MCP token.

## Risks / notes

- Short-lived access tokens mean periodic re-copy; this is accepted for the phased
  approach and called out in both the UI and the skill.
- The token endpoint must never log or cache the token (`no-store`, body-only).
- Codex's weaker OAuth support is a key reason the bearer-token path is retained as
  the primary, client-agnostic mechanism.
