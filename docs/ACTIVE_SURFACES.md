# Active Surfaces

This file records the current ownership rules for pages that are easy to
confuse during the Admin migration.

## Admin

Decision recorded on 2026-05-02:

- The operator console is called **Admin**.
- `/admin` and `/admin/*` should be treated as one Admin system.
- The orange `/admin` operator console is the only Admin UI.
- Do not create or restore `frontend/src/admin/**`, `frontend/src/pages/admin/**`,
  `frontend-admin/**`, Next.js `app/admin/**`, or any other second Admin frontend.
- Before changing Admin UI, verify which file is rendering the current browser
  page and state that file path.

## Transitional State

Local development may proxy `/admin` from Vite to the orange Admin service on
port `5000`. The proxy is the expected local path for the current Admin UI; it is
not permission to create a new React Admin under `frontend/src`.

The live orange Admin source now lives under `admin_console/`. Verify the
rendering file, state the path, then make the requested change only after the
ownership is clear.

## Route Ownership

| Surface | Owner | Notes |
| --- | --- | --- |
| `/admin` and `/admin/*` | Orange Admin service on port `5000` in local dev | Keep as one Admin system with existing pages preserved. |
| `/admin/api/*` | API boundary | Proxy to the appropriate backend service; do not confuse API code with a second UI. |
| `frontend/src/admin/**` old auth stub | Removed/deprecated | Do not restore as a separate second Admin app. |
| `frontend/src/pages/admin/**` | Forbidden | Do not create a new React Admin page tree here. |
| Legacy FastAPI Admin auth/API package | Removed/deprecated | Do not restore as a second Admin backend; keep Admin work inside the orange Admin service unless explicitly re-approved. |

## Required Checks For Admin Work

1. Confirm the current branch is not `main`.
2. Check the route owner before editing files.
3. Keep Topic Plan, Prompt Matrix, Query Pool, Segment, and Profile in the same
   Admin navigation.
4. Use `Segment` instead of `ProfileGroup` in UI text.
5. Make budget ceiling a numeric input, not a fixed select.
