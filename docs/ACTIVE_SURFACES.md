# Active Surfaces

This file records the current ownership rules for pages that are easy to
confuse.

## Admin

Decision recorded on 2026-05-02, updated 2026-05-08 after Phase X-2 (PR #386)
deleted the Flask `admin_console/` package:

- The operator console is called **Admin**.
- `/admin` and `/admin/*` are one Admin system, served by the FastAPI backend
  on port `4000`.
- Admin SPA shell: `backend/static/admin.html`, served by FastAPI via
  `FileResponse` for `/admin`, `/admin/`, and `/admin/{path:path}`.
- Admin APIs: `/admin/api/*` proxied to FastAPI `/api/*` by nginx (see
  `frontend/nginx.conf`); the SPA fetches against `/admin/api/*` directly.
- Do not create or restore `frontend/src/admin/**`, `frontend/src/pages/admin/**`,
  `frontend-admin/**`, Next.js `app/admin/**`, or any other second Admin frontend.
- Before changing Admin UI, verify which file is rendering the current browser
  page and state that file path.

## Local Development

Local Vite dev proxies `/admin` and `/admin/api` to the FastAPI backend on
port `4000` (see `frontend/vite.config.js`). The proxy is the expected local
path for the current Admin UI; it is not permission to create a new React
Admin under `frontend/src`.

Admin source now lives in two places — the SPA shell at
`backend/static/admin.html` and the API routers under
`backend/app/api/admin/*`. Verify the rendering file, state the path, then
make the requested change only after the ownership is clear.

## Route Ownership

| Surface | Owner | Notes |
| --- | --- | --- |
| `/admin` and `/admin/*` | FastAPI backend on port `4000` (`backend/static/admin.html`) | One Admin system; preserve existing pages. |
| `/admin/api/*` | FastAPI backend on port `4000` (`backend/app/api/admin/*`) | nginx rewrites `/admin/api/` → `/api/` upstream. |
| `frontend/src/admin/**` old auth stub | Removed/deprecated | Do not restore as a separate second Admin app. |
| `frontend/src/pages/admin/**` | Forbidden | Do not create a new React Admin page tree here. |
| Legacy Flask `admin_console/` package | Deleted in PR #386 | Do not recreate; add Admin work inside the FastAPI backend. |

## Required Checks For Admin Work

1. Confirm the current branch is not `main`.
2. Check the route owner before editing files.
3. Keep Topic Plan, Prompt Matrix, Query Pool, Segment, and Profile in the same
   Admin navigation.
4. Use `Segment` instead of `ProfileGroup` in UI text.
5. Make budget ceiling a numeric input, not a fixed select.
