# Workflow Studio Session Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent non-admin users from seeing Workflow Studio sessions created by other users on the same browser.

**Architecture:** Move Workflow Studio browser storage from shared global keys to user-scoped keys keyed by `run_prefix`, and stamp each session with owner metadata so legacy/global sessions can be filtered safely during migration. Keep run-level Studio adoption behavior intact, but only persist sessions into the current user's scoped store.

**Tech Stack:** Frontend JavaScript, browser `localStorage`, node test runner

---

### Task 1: Add failing ownership and storage-scope tests

**Files:**
- Modify: `frontend/tests/pipeline.test.js`
- Modify: `frontend/lib/pipeline.js`

**Step 1: Write the failing test**

Add tests for:
- `workflowStudioStorageKeysForUser()` returning scoped keys per user
- `workflowStudioSessionBelongsToUser()` matching owner metadata
- legacy prefix fallback matching only the current user's sessions

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: FAIL because the new helpers do not exist yet.

**Step 3: Write minimal implementation**

Add pure helpers to `frontend/lib/pipeline.js` for:
- user-scoped Studio storage keys
- owner metadata extraction
- user/session ownership checks
- filtering a session map by user

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: PASS for the new helper tests.

### Task 2: Scope Workflow Studio browser persistence by user

**Files:**
- Modify: `frontend/app.js`
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add source/behavior assertions covering:
- app boot loading Studio sessions with a user-aware loader
- persistence writing to scoped keys, not just the shared global key
- sessions stamped with owner metadata

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: FAIL because app code still uses shared Studio keys.

**Step 3: Write minimal implementation**

Update `frontend/app.js` to:
- derive scoped Studio storage keys from `state.user`
- load only sessions owned by the active user
- reload Studio sessions on login/session restore
- clear in-memory Studio state on logout
- stamp/normalize owner metadata on session create/upsert
- optionally migrate matching legacy sessions from the old global key into the scoped store

**Step 4: Run test to verify it passes**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: PASS.

### Task 3: Verify no regression in the frontend bundle logic

**Files:**
- Modify: none unless needed
- Test: `frontend/tests/pipeline.test.js`

**Step 1: Run syntax and targeted tests**

Run:
- `node --check frontend/app.js`
- `node --test frontend/tests/pipeline.test.js`

Expected:
- syntax check passes
- targeted test suite passes

**Step 2: Commit**

```bash
git add docs/plans/2026-03-17-workflow-studio-session-isolation.md frontend/lib/pipeline.js frontend/app.js frontend/tests/pipeline.test.js
git commit -m "fix: isolate workflow studio sessions by user"
```
