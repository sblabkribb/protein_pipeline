# MCP Guide Localization Design

**Problem:** The MCP tab content is hard-coded in English inside `frontend/index.html`, so switching the console to Korean leaves the entire VS Code MCP guide untranslated. The token instructions also mention `KBF_SSO_ACCESS_TOKEN` only indirectly, which makes the SSO path hard to follow.

**Decision:** Move the MCP guide body into a small frontend helper that renders localized markup for the current UI language. Keep the rest of the page structure unchanged and reuse the existing tab card styles.

**Why this approach:**
- The guide body contains rich markup, code blocks, and inline `<code>` labels that do not fit the existing text-only `data-i18n` flow well.
- A dedicated helper keeps the MCP documentation strings in one place and allows the Korean and English versions to stay structurally aligned.
- Rendering from JS makes language switches deterministic without duplicating two large static HTML blocks in `index.html`.

**Token guidance scope:**
- Explain the local auth path via `Local Storage > kbf.token`.
- Explain the OIDC / KBF SSO path explicitly via notebook service MCP page, `Local Storage > auth-storage`, and the `access_token` field.
- Clarify that `kbf.token` can be empty in this app under SSO because the browser session uses a server-side session cookie, while VS Code still needs a bearer token in `mcp.json`.

**Validation:**
- Add a frontend test that asserts the Korean MCP guide contains the VS Code title and explicit `auth-storage` / `access_token` token-copy steps.
- Add a frontend test that asserts the English guide still renders the MCP config and notebook token path.
- Run frontend syntax checks after wiring the helper into `app.js`.
