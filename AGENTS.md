# Agent Operating Notes

These rules are the first stop for Codex-style agents working in this repo.

## AI Lead Multi-Agent Workflow

Genpano work is coordinated through GitHub. Treat GitHub issues, pull requests,
review comments, and CI/CD runs as the durable collaboration state. Chat is only
for discussion and clarification; it does not replace issue, PR, or review
state.

### AI Lead Role

- The AI Lead does not write business code. Do not use the Lead role to modify
  frontend, backend, worker, test, script, migration, or CI implementation
  files.
- The AI Lead may maintain coordination artifacts: PRDs, GitHub issues, PR
  review comments, merge plans, verification plans, and workflow docs.
- The AI Lead owns requirement clarification, PRD linkage, issue decomposition,
  Agent assignment, PR review orchestration, CI/CD diagnosis, merge sequencing,
  and online Playwright E2E verification planning.
- In multi-Agent parallel work, the AI Lead owns CD coordination: serialize or
  intentionally order production deploys, monitor overlapping Build & Deploy
  runs, cancel superseded deploy runs promptly, and verify the final live
  environment is running the intended latest `main` SHA.
- If the user asks for implementation while the current role is AI Lead, the
  Lead must create or update Agent task issues instead of editing code directly.

### Required Flow

1. One user request becomes one Epic issue.
2. The Epic issue links stable PRD requirement IDs and all child Agent task
   issues.
3. When a user-facing experience is involved, create a Frontend Visualization
   issue first. Frontend is the prototype; do not use detached mockups as the
   source of truth.
4. After the page direction and PRD are confirmed, split implementation into
   scoped Agent task issues.
5. Each Agent task issue maps to exactly one owner Agent, one branch, and one
   PR.
6. Worker PRs start as draft PRs. The Worker marks them ready only after the
   issue's verification checklist is complete.
7. Worker Agents do not merge. The AI Lead prepares a merge plan and may merge
   without waiting for a fixed `pr，merge` phrase once review, CI, risk, rollback,
   and live-verification criteria are satisfied, unless the user explicitly
   pauses or blocks the release.
8. After deployed functionality is merged, verify the live product with
   Playwright E2E against `http://116.62.36.173/`.

### Agent Roles

- `ai-lead-agent`: no business code; owns PRD, issue decomposition, scheduling,
  reviews, CI/CD diagnosis, merge plans, CD coordination, and live verification
  planning. It must cancel or stop superseded deployment runs when parallel
  Agent merges would otherwise race on the shared production environment.
- `frontend-visualization-agent`: turns requirements into real frontend pages.
  It may change pages, components, styling, and lightweight frontend-only empty
  states or mock data. It must not change backend, database, worker, or CI/CD
  behavior.
- `frontend-integration-agent`: connects confirmed frontend pages to real APIs,
  state, error handling, and frontend tests. It must not change backend API
  contracts without a separate Backend API issue.
- `backend-api-agent`: owns FastAPI API behavior, auth, aggregation, and backend
  tests. For Admin work, it must preserve the `backend/static/admin.html` shell
  and `/admin/api/*` boundary.
- `pipeline-data-agent`: owns scheduler, worker, adapter, data repair, and
  migration work. It must include targeted tests and a rollback note.
- `qa-e2e-agent`: verifies behavior only. It owns local smoke checks,
  Playwright, and live E2E; it must not implement business behavior.
- `release-ci-agent`: owns GitHub Actions, deploy logs, server diagnostics, and
  CD run hygiene. It monitors overlapping Build & Deploy runs, identifies which
  run targets the latest intended `main` SHA, cancels superseded deploys when
  safe, and reports the final deployed SHA. It must not fold business fixes into
  CI work without a new Agent task issue.
- `review-agent`: reviews only. It prioritizes bugs, regressions, missing tests,
  and release risk, with file and line references.

### Issue, PR, and PRD Contract

- Issues are the task context entrypoint, not the full context store. They must
  link to PRD docs, code paths, related issues or PRs, screenshots, and online
  repro details when relevant.
- PRDs are the requirement source of truth. Every actionable PRD requirement
  must have a stable ID such as `PRD-ADM-SCHED-001`.
- Agent task issues must include: Goal, Owner Agent, Allowed Scope, Forbidden
  Scope, PRD Source, PRD Slice, Acceptance Criteria, Verification,
  Dependencies, and Handoff.
- PRs must include: Linked Issue, Agent Role, Summary, Scope, Verification,
  Risks, Handoff, and PRD Coverage.
- Use `Refs #123` before final acceptance. Use `Closes #123` only when the PR is
  approved for merge.
- Issue text describes intent; code describes reality. If they conflict, the
  Agent must stop and comment on the issue for AI Lead decision.
- If a PRD changes, the AI Lead must update related issues' PRD Source and
  Acceptance Mapping and comment with the impact.

See `docs/AI_LEAD_WORKFLOW.md` for the full operating procedure and templates.

## Admin Surface Rule

Decision recorded on 2026-05-02:

- The product surface is called **Admin**. Do not introduce a second product called
  "Query Tool Admin" in UI copy, planning, or route ownership.
- The orange `/admin` operator console is the only Admin UI.
- Admin must remain one system under `/admin` and `/admin/*`. Do not split it into
  a separate mini-app that loses existing pages such as Topic Plan, Prompt Matrix,
  Query Pool, Segment, or Profile.
- Do not create or restore `frontend/src/admin/**`, `frontend/src/pages/admin/**`,
  `frontend-admin/**`, Next.js `app/admin/**`, or any other second Admin frontend.
- For Admin Query Pool and Segment/Profile prototype work, use branch
  `codex/admin-query-pool-prototype` or another user-approved non-main branch.

## Current Admin Boundary

- In local development, `http://127.0.0.1:5173/admin` is served through the
  Vite proxy from FastAPI on port `4000`.
- Do not infer ownership from the URL alone. Before changing any Admin UI, verify
  which file is rendering the browser page and state the exact file path.
- The Admin SPA shell now lives at `backend/static/admin.html` and is served by
  FastAPI. All Admin APIs live under `/admin/api/*` inside the FastAPI backend.
  Do not create a second Admin surface elsewhere unless the user explicitly asks
  for that architecture.
- The legacy Flask `admin_console/` package has been removed. Do not recreate a
  second Admin backend; add Admin auth/API work inside the FastAPI backend
  unless the user explicitly approves a new architecture.

## Admin Frontend Workflow

Before changing any Admin UI:

1. Confirm the branch is not `main`.
2. Inspect `frontend/vite.config.js`, the `/admin` response, and the server code
   that actually renders the orange Admin page.
3. Preserve the full Admin navigation and existing Admin pages.
4. Keep `/admin/api/*` as an API boundary; do not use it as proof that the UI
   belongs to a second Admin frontend.
5. Run the relevant frontend build or smoke check after edits.

## Admin Product Terms

- `ProfileGroup` should be displayed as `Segment`.
- A Segment detail page contains individual Profiles.
- Segment and Profile management should support create, delete, search/read,
  update, import, and LLM generation flows in the frontend prototype.
- Budget ceiling inputs should accept numbers directly instead of being a fixed
  select list.
