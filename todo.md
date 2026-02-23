# UI + Frontend Plan (K-Biofoundry)

## Goals
- Add a standalone `frontend/` UI that drives the existing MCP HTTP tools.
- Keep the interactive flow: AI asks → human answers → pipeline runs.
- Provide basic user separation via login + per-user run_id prefix.
- Expose intermediate results (status + artifacts) in a clear, logical layout.
- Deliver a K-Biofoundry-appropriate visual system.

## Implementation Tasks
1. Create `frontend/` folder with a static, zero-build UI (HTML/CSS/JS).
2. Implement login gate (localStorage) and per-user run_id creation.
3. Implement conversation flow:
   - Prompt submission → `pipeline.plan_from_prompt`.
   - Render returned questions and capture answers (text + file uploads).
   - Build explicit `pipeline.run` arguments and execute.
4. Implement run monitoring:
   - `pipeline.status` polling with auto-poll toggle.
   - `pipeline.list_runs` filtered by user prefix.
5. Implement artifact browser:
   - `pipeline.list_artifacts` + stage inference tags.
   - `pipeline.read_artifact` preview (text + images).
6. Add a simple settings panel for API base URL + health check.
7. Add frontend unit tests for pure logic (run_id, argument building, stage inference).

## Tests
- `node --test` in `frontend/` (pure JS unit tests).

## Notes / Assumptions
- Login is client-side only (localStorage). For real multi-tenant auth, add server-side auth later.
- API base defaults to `http://127.0.0.1:18080` but is user-configurable.
