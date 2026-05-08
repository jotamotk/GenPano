# Agent Operating Notes

These rules are the first stop for Codex-style agents working in this repo.

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
