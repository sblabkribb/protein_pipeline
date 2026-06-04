# MCP One-Click Token + Integrated Skill Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual devtools token copying with a one-click `/auth/mcp_token` endpoint, add a downloadable integrated `protein-pipeline-stepper` skill from the MCP tab, refresh the MCP tab UI guidance, and promote the change work → dev → staging → prod.

**Architecture:** Two new auth-gated GET endpoints in the pipeline-mcp HTTP server (`/auth/mcp_token` returns the session's refreshed bearer token + expiry; `/pipeline_skill.zip` streams the skill folder as a zip, mirroring the existing model-registration archive). The MCP tab front-end gains a "copy mcp.json with my token" button and a "download skill" button. The skill markdown gains a connection/auth section. No new credential store — OIDC access tokens are handed out as-is with an expiry hint.

**Tech Stack:** Python stdlib `http.server` handler (`pipeline-mcp/src/pipeline_mcp/http_server.py`), `SessionManager`/`AuthManager`, pytest; vanilla ES-module front-end (`frontend/lib/mcp-guide.js`, `frontend/app.js`), `node:test`.

---

## File Structure

- `pipeline-mcp/src/pipeline_mcp/session_auth.py` — add `SessionManager.get_oidc_access_token()` (mirror `get_oidc_id_token`).
- `pipeline-mcp/src/pipeline_mcp/auth.py` — add `AuthManager.issue_token()` public mint method.
- `pipeline-mcp/src/pipeline_mcp/http_server.py` — add `_send_mcp_token()` + `_send_pipeline_skill_archive()` and wire both into `do_GET`.
- `pipeline-mcp/tests/test_session_auth.py` — test `get_oidc_access_token`.
- `pipeline-mcp/tests/test_auth_manager.py` — test `issue_token`.
- `pipeline-mcp/tests/test_http_server_auth.py` — test both endpoints.
- `skills/protein-pipeline-stepper/SKILL.md` — add "Connecting (MCP auth)" section, update `description`.
- `frontend/lib/mcp-guide.js` — token-copy + skill-download markup, `buildMcpJsonSnippetWithToken()` export, ko/en copy.
- `frontend/app.js` — element refs, `copyMcpJsonWithToken()`, `downloadPipelineSkill()`, wire-up in `renderMcpGuide()`, i18n strings.
- `frontend/tests/mcp-tab.test.js` — assert new controls + snippet helper.

Conventions to follow (verified in code):
- Endpoints are dispatched by `route_path == "..."` inside `do_GET`; auth GETs use the `if self._auth_enabled(): user = self._require_auth(); if user is None: return` pattern (see `_send_model_registration_skill_archive`).
- `self._json(status, payload, extra_headers=...)` and `self._binary(status, bytes, content_type, extra_headers=...)` are the response helpers.
- Backend unit tests build a handler with `Handler.__new__(Handler)`, monkeypatch module globals `http_server._AUTH/_OIDC/_SESSIONS`, set `handler.headers`, and stub `handler._json` to capture output.
- Front-end MCP panel is rendered via `el.mcpGuidePanel.innerHTML = renderMcpGuideMarkup(...)` in `renderMcpGuide()`; button listeners are attached after that assignment by querying inside the panel.

---

## Task 1: `SessionManager.get_oidc_access_token()`

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/session_auth.py` (add method near `get_oidc_id_token`, ~line 139)
- Test: `pipeline-mcp/tests/test_session_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `pipeline-mcp/tests/test_session_auth.py`:

```python
def test_get_oidc_access_token_returns_token_and_expiry(tmp_path):
    from pipeline_mcp.session_auth import SessionConfig, SessionManager

    manager = SessionManager(
        SessionConfig(
            store_path=tmp_path / "sessions.json",
            cookie_name="kbf_session",
            local_ttl_s=3600,
            oidc_refresh_leeway_s=60,
            oidc_fallback_ttl_s=300,
        )
    )
    # Inject an OIDC session directly (no refresh needed: access token still valid).
    import time
    sid = "sess-oidc"
    exp = int(time.time()) + 1800
    manager._sessions[sid] = {
        "auth_type": "oidc",
        "user": {"username": "alice", "role": "user"},
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "expires_at": exp,
        "oidc": {"access_token": "AT-123", "access_expires_at": exp},
    }

    token, expires_at = manager.get_oidc_access_token(sid)
    assert token == "AT-123"
    assert expires_at == exp


def test_get_oidc_access_token_empty_for_local_session(tmp_path):
    from pipeline_mcp.session_auth import SessionConfig, SessionManager

    manager = SessionManager(
        SessionConfig(
            store_path=tmp_path / "sessions.json",
            cookie_name="kbf_session",
            local_ttl_s=3600,
            oidc_refresh_leeway_s=60,
            oidc_fallback_ttl_s=300,
        )
    )
    sid = manager.create_local_session({"username": "bob", "role": "user"})
    token, expires_at = manager.get_oidc_access_token(sid)
    assert token == ""
    assert expires_at == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline-mcp && python -m pytest tests/test_session_auth.py -k get_oidc_access_token -v`
Expected: FAIL with `AttributeError: 'SessionManager' object has no attribute 'get_oidc_access_token'`

- [ ] **Step 3: Write minimal implementation**

In `session_auth.py`, immediately after the `get_oidc_id_token` method, add:

```python
    def get_oidc_access_token(
        self, session_id: str, *, oidc_settings: "OIDCSettings | None" = None
    ) -> tuple[str, int]:
        """Return (access_token, access_expires_at_epoch) for an OIDC session.

        Refreshes the session first when oidc_settings is provided so the
        returned access token is as fresh as the stored refresh token allows.
        Returns ("", 0) for non-OIDC sessions or when no access token exists.
        """
        session = self.get_session(session_id, oidc_settings=oidc_settings)
        if not isinstance(session, dict):
            return "", 0
        if str(session.get("auth_type") or "") != "oidc":
            return "", 0
        oidc = session.get("oidc")
        if not isinstance(oidc, dict):
            return "", 0
        token = str(oidc.get("access_token") or "").strip()
        expires_at = _coerce_int(oidc.get("access_expires_at"))
        return token, expires_at
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline-mcp && python -m pytest tests/test_session_auth.py -k get_oidc_access_token -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/session_auth.py pipeline-mcp/tests/test_session_auth.py
git commit -m "Add SessionManager.get_oidc_access_token for one-click MCP token"
```

---

## Task 2: `AuthManager.issue_token()`

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/auth.py` (add method after `authenticate`, ~line 68)
- Test: `pipeline-mcp/tests/test_auth_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `pipeline-mcp/tests/test_auth_manager.py` (follow the file's existing fixture style for building an `AuthManager`; if the file constructs one via a helper, reuse it — otherwise use `bootstrap_auth_manager` from `pipeline_mcp.auth` if present, or create a user with `create_user`):

```python
def test_issue_token_round_trips_through_verify(tmp_path):
    from pipeline_mcp.auth import AuthManager, AuthConfig

    manager = AuthManager(
        config=AuthConfig(
            enabled=True,
            store_path=tmp_path / "users.json",
            secret_path=tmp_path / "secret.bin",
            token_ttl_s=3600,
        )
    )
    created = manager.create_user(username="carol", password="pw123456", role="user")

    issued = manager.issue_token(created)
    assert issued["token"]
    assert issued["expires_at"] > 0

    verified = manager.verify_token(issued["token"])
    assert verified is not None
    assert verified["username"] == "carol"
```

> Note: confirm the `AuthConfig` field names against the top of `auth.py` (`enabled`, `store_path`, `secret_path`, `token_ttl_s`). Adjust the constructor call to match the real signature if it differs.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline-mcp && python -m pytest tests/test_auth_manager.py -k issue_token -v`
Expected: FAIL with `AttributeError: 'AuthManager' object has no attribute 'issue_token'`

- [ ] **Step 3: Write minimal implementation**

In `auth.py`, add a method right after `authenticate`:

```python
    def issue_token(self, user: dict[str, Any]) -> dict[str, Any]:
        """Mint a fresh bearer token for an already-authenticated user.

        Used by the one-click MCP token endpoint for local-auth sessions,
        where the original login token is not stored server-side.
        """
        username = str(user.get("username") or "")
        role = str(user.get("role") or "user")
        ttl_s = int(self.config.token_ttl_s)
        token = _issue_token(self.secret, username=username, role=role, ttl_s=ttl_s)
        return {"token": token, "expires_at": int(time.time()) + max(0, ttl_s)}
```

Ensure `import time` exists at the top of `auth.py` (add it if missing — check the existing imports first).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline-mcp && python -m pytest tests/test_auth_manager.py -k issue_token -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/auth.py pipeline-mcp/tests/test_auth_manager.py
git commit -m "Add AuthManager.issue_token to mint MCP bearer token for local sessions"
```

---

## Task 3: `/auth/mcp_token` endpoint

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/http_server.py` (add `_send_mcp_token`; wire into `do_GET` near the `/auth/me` branch ~line 745)
- Test: `pipeline-mcp/tests/test_http_server_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `pipeline-mcp/tests/test_http_server_auth.py`:

```python
def test_mcp_token_returns_oidc_access_token(tmp_path, monkeypatch):
    import time
    from pipeline_mcp import http_server
    from pipeline_mcp.http_server import Handler
    from pipeline_mcp.session_auth import SessionConfig, SessionManager

    manager = SessionManager(
        SessionConfig(
            store_path=tmp_path / "sessions.json",
            cookie_name="kbf_session",
            local_ttl_s=3600,
            oidc_refresh_leeway_s=60,
            oidc_fallback_ttl_s=300,
        )
    )
    exp = int(time.time()) + 1800
    sid = "sess-oidc"
    manager._sessions[sid] = {
        "auth_type": "oidc",
        "user": {"username": "alice", "role": "user"},
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "expires_at": exp,
        "oidc": {"access_token": "AT-XYZ", "access_expires_at": exp},
    }

    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", manager, raising=False)

    captured = {}
    handler = Handler.__new__(Handler)
    handler.headers = {"Cookie": f"kbf_session={sid}"}
    handler._json = lambda status, payload, extra_headers=None: captured.update(
        status=status, payload=payload, extra_headers=extra_headers
    )

    handler._send_mcp_token()

    assert captured["status"] == 200
    assert captured["payload"]["ok"] is True
    assert captured["payload"]["token"] == "AT-XYZ"
    assert captured["payload"]["auth_type"] == "oidc"
    assert captured["payload"]["expires_at"] == exp
    assert ("Cache-Control", "no-store") in (captured["extra_headers"] or [])


def test_mcp_token_requires_auth_when_enabled(monkeypatch):
    from pipeline_mcp.http_server import Handler

    captured = {}
    handler = Handler.__new__(Handler)
    handler._auth_enabled = lambda: True
    handler._require_auth = lambda: None  # simulates unauthorized (401 already emitted)
    handler._json = lambda status, payload, extra_headers=None: captured.update(
        status=status, payload=payload
    )

    handler._send_mcp_token()
    # When _require_auth returns None, the handler must stop without emitting a 200.
    assert captured.get("status") != 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline-mcp && python -m pytest tests/test_http_server_auth.py -k mcp_token -v`
Expected: FAIL with `AttributeError: ... has no attribute '_send_mcp_token'`

- [ ] **Step 3: Write minimal implementation**

In `http_server.py`, add the method (place it just before `_send_model_registration_skill_archive`):

```python
    def _send_mcp_token(self) -> None:
        user = None
        if self._auth_enabled():
            user = self._require_auth()
            if user is None:
                return  # 401/403 already emitted by _require_auth

        token = ""
        auth_type = ""
        expires_at = 0

        manager = self.sessions
        session_id = self._session_id_from_cookie()
        if manager is not None and session_id:
            session = manager.get_session(session_id, oidc_settings=self.oidc)
            if isinstance(session, dict):
                auth_type = str(session.get("auth_type") or "")
                if auth_type == "oidc":
                    token, expires_at = manager.get_oidc_access_token(
                        session_id, oidc_settings=self.oidc
                    )

        if not token:
            auth = self.auth
            if (
                auth is not None
                and getattr(auth, "enabled", False)
                and isinstance(user, dict)
            ):
                issued = auth.issue_token(user)
                token = str(issued.get("token") or "")
                expires_at = int(issued.get("expires_at") or 0)
                auth_type = auth_type or "local"

        if not token:
            self._json(
                409,
                {"ok": False, "error": "no MCP token available for this session"},
            )
            return

        self._json(
            200,
            {
                "ok": True,
                "token": token,
                "auth_type": auth_type or "local",
                "expires_at": int(expires_at or 0),
            },
            extra_headers=[("Cache-Control", "no-store")],
        )
```

Then wire it into `do_GET`, immediately after the `/auth/me` branch:

```python
        if route_path == "/auth/mcp_token":
            self._send_mcp_token()
            return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline-mcp && python -m pytest tests/test_http_server_auth.py -k mcp_token -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/http_server.py pipeline-mcp/tests/test_http_server_auth.py
git commit -m "Add GET /auth/mcp_token one-click bearer token endpoint"
```

---

## Task 4: `/pipeline_skill.zip` endpoint

**Files:**
- Modify: `pipeline-mcp/src/pipeline_mcp/http_server.py` (add `_send_pipeline_skill_archive`; wire into `do_GET` near `/model_provider_skill.zip` ~line 751)
- Test: `pipeline-mcp/tests/test_http_server_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `pipeline-mcp/tests/test_http_server_auth.py`:

```python
def test_pipeline_skill_archive_contains_skill_md(tmp_path, monkeypatch):
    from pipeline_mcp import http_server
    from pipeline_mcp.http_server import Handler

    skill_dir = tmp_path / "protein-pipeline-stepper"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Protein Pipeline Stepper\n", encoding="utf-8")
    monkeypatch.setenv("PIPELINE_STEPPER_SKILL_DIR", str(skill_dir))

    monkeypatch.setattr(http_server, "_AUTH", None, raising=False)
    monkeypatch.setattr(http_server, "_OIDC", None, raising=False)
    monkeypatch.setattr(http_server, "_SESSIONS", None, raising=False)

    captured = {}
    handler = Handler.__new__(Handler)
    handler.headers = {}
    handler._binary = lambda status, body, content_type, extra_headers=None: captured.update(
        status=status, body=body, content_type=content_type, extra_headers=extra_headers
    )

    handler._send_pipeline_skill_archive()

    assert captured["status"] == 200
    assert captured["content_type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(captured["body"])).namelist()
    assert "protein-pipeline-stepper/SKILL.md" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline-mcp && python -m pytest tests/test_http_server_auth.py -k pipeline_skill -v`
Expected: FAIL with `AttributeError: ... has no attribute '_send_pipeline_skill_archive'`

- [ ] **Step 3: Write minimal implementation**

In `http_server.py`, add (place right after `_send_model_registration_skill_archive`):

```python
    def _send_pipeline_skill_archive(self) -> None:
        if self._auth_enabled():
            user = self._require_auth()
            if user is None:
                return

        default_dir = str(
            (Path(__file__).resolve().parents[3] / "skills" / "protein-pipeline-stepper")
        )
        raw_root = os.environ.get("PIPELINE_STEPPER_SKILL_DIR", default_dir)
        root = Path(raw_root).expanduser().resolve()
        if not root.is_dir():
            self._json(
                404,
                {
                    "ok": False,
                    "error": "pipeline skill directory not found",
                    "path": str(root),
                },
            )
            return

        buffer = io.BytesIO()
        archive_root = Path("protein-pipeline-stepper")
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(root.rglob("*")):
                if not file_path.is_file():
                    continue
                archive.write(file_path, str(archive_root / file_path.relative_to(root)))

        self._binary(
            200,
            buffer.getvalue(),
            "application/zip",
            extra_headers=[
                ("Content-Disposition", 'attachment; filename="protein-pipeline-stepper.zip"'),
                ("Cache-Control", "no-store"),
            ],
        )
```

> Verify `Path(__file__).resolve().parents[3]` points at the repo root in the deployed layout (`pipeline-mcp/src/pipeline_mcp/http_server.py` → parents[3] = repo root). If the deployment installs the package elsewhere, rely on `PIPELINE_STEPPER_SKILL_DIR` being set in the environment (documented in Task 9 deploy notes).

Then wire it into `do_GET` after the `/model_provider_skill.zip` branch:

```python
        if route_path == "/pipeline_skill.zip":
            self._send_pipeline_skill_archive()
            return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline-mcp && python -m pytest tests/test_http_server_auth.py -k pipeline_skill -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline-mcp/src/pipeline_mcp/http_server.py pipeline-mcp/tests/test_http_server_auth.py
git commit -m "Add GET /pipeline_skill.zip to download the integrated pipeline skill"
```

---

## Task 5: Update the skill (connection + execution)

**Files:**
- Modify: `skills/protein-pipeline-stepper/SKILL.md`

- [ ] **Step 1: Update the front-matter description**

Replace the `description:` line so it covers connection + execution. New value:

```
description: Connect to and run the protein-pipeline via MCP. Covers one-click token setup (mcp.json) for VS Code/Codex, plus stepwise pipeline.run/pipeline.status execution with safe polling, run_id reuse, stop_after staging, and duplicate-job avoidance. Use when connecting the protein-pipeline MCP server or running staged RFD3/MMseqs2/ProteinMPNN/SoluProt/AF2 jobs and you want output paths (not narrative summaries).
```

- [ ] **Step 2: Insert a "Connecting (MCP auth)" section**

Insert this section immediately after the `# Protein Pipeline Stepper` / `## Overview` block and **before** `## Prerequisites`:

```markdown
## Connecting (MCP auth)

Before running anything, the MCP server `protein-pipeline` must be reachable and authenticated.

1. Open the protein-pipeline web app and sign in (local login or KBF SSO).
2. Go to the **MCP** tab and click **Copy mcp.json with my token**. This copies a
   ready-to-paste `mcp.json` with your bearer token already filled in — you do not
   need to open browser devtools.
3. Add it to your client:
   - **VS Code:** run **MCP: Open User Configuration** and paste into `mcp.json`.
   - **Codex:** add an MCP server named `protein-pipeline` with the same URL and the
     `Authorization: Bearer <token>` header.
4. The token is a short-lived SSO/login token. When MCP calls start failing with an
   auth error (401), return to the MCP tab and click the button again to refresh the
   token in your `mcp.json`.

You can also download this skill from the MCP tab (**Download skill**) so your client
has the connection + execution instructions locally.
```

- [ ] **Step 3: Verify the file is coherent**

Run: `sed -n '1,40p' skills/protein-pipeline-stepper/SKILL.md`
Expected: front-matter `description` updated; "Connecting (MCP auth)" section present before "Prerequisites"; existing execution sections unchanged below.

- [ ] **Step 4: Commit**

```bash
git add skills/protein-pipeline-stepper/SKILL.md
git commit -m "Add MCP connection/auth section to protein-pipeline-stepper skill"
```

---

## Task 6: MCP guide markup — token copy + skill download (`mcp-guide.js`)

**Files:**
- Modify: `frontend/lib/mcp-guide.js`
- Test: `frontend/tests/mcp-tab.test.js`

- [ ] **Step 1: Write the failing test**

Replace the body of `frontend/tests/mcp-tab.test.js` test with assertions for the new controls, and add a snippet-helper test:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

test("pipeline MCP tab is Korean-first and includes VS Code plus Codex guidance", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    const html = mcpGuide.renderMcpGuideMarkup({ lang: "ko" });
    assert.equal(html.includes("https://pipeline.k-biofoundrycopilot.duckdns.org/mcp"), true);
    assert.equal(html.includes("MCP: Open User Configuration"), true);
    assert.equal(html.includes("Codex"), true);
    assert.equal(html.includes("질문 예시"), true);
    // New one-click controls (stable IDs used by app.js):
    assert.equal(html.includes('id="mcpTokenCopyBtn"'), true);
    assert.equal(html.includes('id="mcpSkillDownloadBtn"'), true);
  });
});

test("buildMcpJsonSnippetWithToken injects the real token", () => {
  return import("../lib/mcp-guide.js").then((mcpGuide) => {
    const snippet = mcpGuide.buildMcpJsonSnippetWithToken("ABC.TOKEN.123");
    assert.equal(snippet.includes("ABC.TOKEN.123"), true);
    assert.equal(snippet.includes("<KBF_SSO_ACCESS_TOKEN>"), false);
    assert.equal(snippet.includes("protein-pipeline"), true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/mcp-tab.test.js`
Expected: FAIL (`buildMcpJsonSnippetWithToken` not exported; `mcpTokenCopyBtn` not in markup)

- [ ] **Step 3: Implement the markup + helper**

In `frontend/lib/mcp-guide.js`:

(a) Add an exported snippet helper after `buildMcpJsonSnippet`:

```javascript
export function buildMcpJsonSnippetWithToken(token) {
  const safe = String(token == null ? "" : token);
  return buildMcpJsonSnippet().replaceAll(TOKEN_PLACEHOLDER, safe);
}
```

(b) Add the two button labels + a status line to both `en` and `ko` `token` copy blocks. In `GUIDE_COPY.en.token`, add:

```javascript
      copyButton: "Copy mcp.json with my token",
      downloadButton: "Download skill",
      autoNote:
        "One click fills your bearer token into the mcp.json above and copies it. The token is a short-lived sign-in token — if MCP calls start failing, click again to refresh it.",
```

In `GUIDE_COPY.ko.token`, add:

```javascript
      copyButton: "내 토큰으로 mcp.json 복사",
      downloadButton: "skill 다운로드",
      autoNote:
        "버튼 한 번이면 위 mcp.json에 bearer 토큰을 채워 클립보드에 복사합니다. 이 토큰은 수명이 짧은 로그인 토큰이라, MCP 호출이 실패하기 시작하면 다시 눌러 갱신하세요.",
```

(c) In `renderMcpGuideMarkup`, change the token card (`span-2`) to include an actions row with the two buttons and a status span. Replace the existing token card block with:

```javascript
      <div class="status-card mcp-guide-card span-2">
        <div class="panel-header small">
          <h3>${copy.token.title}</h3>
          <p>${copy.token.description}</p>
        </div>
        <div class="mcp-guide-actions">
          <button type="button" id="mcpTokenCopyBtn" class="btn-primary">${copy.token.copyButton}</button>
          <button type="button" id="mcpSkillDownloadBtn" class="btn-secondary">${copy.token.downloadButton}</button>
          <span id="mcpGuideStatus" class="mcp-guide-status" role="status"></span>
        </div>
        <div class="mcp-guide-note">${copy.token.autoNote}</div>
        ${renderList(copy.token.items)}
        <div class="mcp-guide-note">${copy.token.note}</div>
      </div>
```

> Keep `copy.token.items`/`copy.token.note` (the manual fallback) below the buttons — they remain useful when JS/clipboard is unavailable.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test tests/mcp-tab.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/mcp-guide.js frontend/tests/mcp-tab.test.js
git commit -m "Add one-click token + skill download controls to MCP guide markup"
```

---

## Task 7: Front-end wiring (`app.js`)

**Files:**
- Modify: `frontend/app.js`

- [ ] **Step 1: Bump the mcp-guide import cache-buster and import the helper**

At `frontend/app.js:132`, update the import to also pull the new helper and bump the version query:

```javascript
import { renderMcpGuideMarkup, buildMcpJsonSnippetWithToken } from "./lib/mcp-guide.js?v=20260604_v7";
```

- [ ] **Step 2: Implement the two action functions**

Add near `downloadModelRegistrationSkill` (~line 11487):

```javascript
function setMcpGuideStatus(message) {
  const node = el.mcpGuidePanel ? el.mcpGuidePanel.querySelector("#mcpGuideStatus") : null;
  if (node) node.textContent = message || "";
}

async function copyMcpJsonWithToken() {
  setMcpGuideStatus(t("mcp.token.fetching"));
  try {
    const response = await fetch(`${state.apiBase}/auth/mcp_token`, {
      method: "GET",
      credentials: "include",
      headers: { ...authHeaders() },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      if (isApiAuthFailure(response.status, payload)) {
        handleApiAuthFailure();
        setMcpGuideStatus(t("mcp.token.signIn"));
        return;
      }
      throw new Error(payload?.error || `HTTP ${response.status}`);
    }
    const token = String(payload?.token || "");
    if (!token) throw new Error(payload?.error || "no token");
    const snippet = buildMcpJsonSnippetWithToken(token);
    await navigator.clipboard.writeText(snippet);
    const expiresAt = Number(payload?.expires_at || 0);
    if (expiresAt > 0) {
      const mins = Math.max(1, Math.round((expiresAt * 1000 - Date.now()) / 60000));
      setMcpGuideStatus(t("mcp.token.copiedExpires", { mins }));
    } else {
      setMcpGuideStatus(t("mcp.token.copied"));
    }
  } catch (err) {
    setMcpGuideStatus(t("mcp.token.failed", { error: err.message || t("error.api") }));
  }
}

async function downloadPipelineSkill() {
  setMcpGuideStatus(t("mcp.skill.downloading"));
  try {
    const response = await fetch(`${state.apiBase}/pipeline_skill.zip`, {
      method: "GET",
      credentials: "include",
      headers: { ...authHeaders() },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      if (isApiAuthFailure(response.status, payload)) {
        handleApiAuthFailure();
        setMcpGuideStatus(t("mcp.token.signIn"));
        return;
      }
      throw new Error(payload?.error || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "protein-pipeline-stepper.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMcpGuideStatus(t("mcp.skill.downloaded"));
  } catch (err) {
    setMcpGuideStatus(t("mcp.skill.failed", { error: err.message || t("error.api") }));
  }
}
```

- [ ] **Step 3: Attach listeners after rendering the panel**

Update `renderMcpGuide()` (~line 11153) to wire the buttons after the innerHTML assignment:

```javascript
function renderMcpGuide() {
  if (!el.mcpGuidePanel) return;
  el.mcpGuidePanel.innerHTML = renderMcpGuideMarkup({ lang: state.lang });
  const copyBtn = el.mcpGuidePanel.querySelector("#mcpTokenCopyBtn");
  if (copyBtn) copyBtn.addEventListener("click", () => void copyMcpJsonWithToken());
  const skillBtn = el.mcpGuidePanel.querySelector("#mcpSkillDownloadBtn");
  if (skillBtn) skillBtn.addEventListener("click", () => void downloadPipelineSkill());
}
```

- [ ] **Step 4: Add i18n strings (en + ko)**

In the English translations object (the block containing `"tabs.mcp": "MCP"` near line 2226) add:

```javascript
    "mcp.token.fetching": "Fetching your token…",
    "mcp.token.copied": "Copied mcp.json with your token to the clipboard.",
    "mcp.token.copiedExpires": "Copied mcp.json — token expires in ~{mins} min. Click again to refresh.",
    "mcp.token.signIn": "Please sign in first, then click again.",
    "mcp.token.failed": "Could not get a token: {error}",
    "mcp.skill.downloading": "Preparing skill download…",
    "mcp.skill.downloaded": "Skill download started.",
    "mcp.skill.failed": "Skill download failed: {error}",
```

In the Korean translations object (the block containing `"tabs.mcp": "MCP"` near line 3933) add:

```javascript
    "mcp.token.fetching": "토큰을 가져오는 중…",
    "mcp.token.copied": "토큰이 채워진 mcp.json을 클립보드에 복사했습니다.",
    "mcp.token.copiedExpires": "mcp.json 복사 완료 — 토큰은 약 {mins}분 뒤 만료됩니다. 만료되면 다시 누르세요.",
    "mcp.token.signIn": "먼저 로그인한 뒤 다시 눌러 주세요.",
    "mcp.token.failed": "토큰을 가져오지 못했습니다: {error}",
    "mcp.skill.downloading": "skill 다운로드를 준비 중…",
    "mcp.skill.downloaded": "skill 다운로드를 시작했습니다.",
    "mcp.skill.failed": "skill 다운로드 실패: {error}",
```

> Confirm the `t(key, vars)` helper supports `{mins}` / `{error}` interpolation (the codebase already uses `t("modelProviders.guide.gpu.downloadFailed", { error: ... })`, so it does).

- [ ] **Step 5: Syntax + targeted tests**

Run: `cd frontend && node --test tests/app-syntax.test.js tests/mcp-tab.test.js`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/app.js
git commit -m "Wire one-click MCP token copy and pipeline skill download in MCP tab"
```

---

## Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend test suite**

Run: `cd pipeline-mcp && python -m pytest tests/test_http_server_auth.py tests/test_session_auth.py tests/test_auth_manager.py -v`
Expected: PASS (all, including the 5 new tests)

- [ ] **Step 2: Front-end test suite**

Run: `cd frontend && node --test tests/`
Expected: PASS (all, including updated `mcp-tab.test.js`)

- [ ] **Step 3: Manual smoke (dev server)**

Start the app per the repo's dev instructions, open the **MCP** tab while signed in, click **Copy mcp.json with my token**, confirm the clipboard holds a `mcp.json` with a real token and the status shows an expiry, then click **Download skill** and confirm `protein-pipeline-stepper.zip` downloads and contains `SKILL.md`.

- [ ] **Step 4: Commit any fixes, then open PR / merge to work main**

```bash
git log --oneline origin/main..HEAD
```
Expected: the feature commits listed. Use `superpowers:finishing-a-development-branch` to merge `feat/mcp-oneclick-token-skill-download` into the work `main`.

---

## Task 9: Deploy work → dev → staging → prod

**Files:** none (deployment); environment config only.

- [ ] **Step 1: Confirm skill dir resolves in deployed layout**

Ensure each deployed environment can locate the skill folder. Either:
- rely on the in-repo default (`<repo>/skills/protein-pipeline-stepper`), or
- set `PIPELINE_STEPPER_SKILL_DIR` in the environment/service config (alongside the existing `PIPELINE_MODEL_REGISTRATION_SKILL_DIR`).

Check where `PIPELINE_MODEL_REGISTRATION_SKILL_DIR` is configured (systemd unit / `_ops` / deploy script env) and add `PIPELINE_STEPPER_SKILL_DIR` the same way if the default path does not resolve post-install.

- [ ] **Step 2: Promote through environments**

Follow the existing pipeline (`scripts/deploy/deploy_from_github.sh` + `protein_pipeline-actions-runner`). For each of dev → staging → prod:
1. Deploy the merged branch.
2. Open the MCP tab on that environment, run the **copy token** and **download skill** smoke checks from Task 8 Step 3.
3. Verify a real MCP client (VS Code) connects with the pasted `mcp.json` and lists `protein-pipeline`.
4. Only promote to the next environment after the smoke check passes.

- [ ] **Step 3: Post-deploy verification on prod**

Confirm `GET https://pipeline.k-biofoundrycopilot.duckdns.org/api/auth/mcp_token` returns a token for a signed-in session and `/api/pipeline_skill.zip` downloads the skill. Confirm the MCP tab no longer instructs raw devtools copying as the primary path.

---

## Self-Review

- **Spec coverage:** token endpoint (Tasks 1–3), skill zip endpoint (Task 4), integrated skill update (Task 5), MCP-tab one-click + download UI ko/en (Tasks 6–7), tests (Tasks 1–8), deploy work→dev→staging→prod (Task 9). Out-of-scope items (real OAuth, long-lived token) intentionally excluded. ✓
- **Placeholders:** none — every code step shows complete code; verification notes flag the two real-world checks (`parents[3]` path, `AuthConfig` field names) rather than leaving TODOs. ✓
- **Type consistency:** `get_oidc_access_token` returns `(token, expires_at)` and is consumed that way in `_send_mcp_token`; `issue_token` returns `{"token","expires_at"}` and is consumed that way; `buildMcpJsonSnippetWithToken(token)` defined in Task 6 and imported/used in Task 7; button IDs `mcpTokenCopyBtn`/`mcpSkillDownloadBtn`/`mcpGuideStatus` consistent across Tasks 6–7. ✓
