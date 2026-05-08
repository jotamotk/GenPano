# GENPANO

GENPANO is a GEO (Generative Engine Optimization) monitoring platform. The
active architecture is data-first: platform jobs collect and analyze AI-engine
responses once, while user projects and dashboards read filtered views of that
shared platform dataset.

## Current Architecture

```text
frontend/                 React + Vite product UI; proxies the current Admin
backend/                  FastAPI control plane for product APIs, user auth, and Admin (`/admin`)
geo_tracker/              Celery workers for engine collection and analysis
docs/                     PRD, Admin PRD, data model, adapter contract
migrations/               Legacy/raw SQL migrations for tracker/analyzer work
prototypes/node-auth-backend/
                           Archived Node/Express auth prototype
```

The production backend path is now `backend/app` and runs with FastAPI. The old
Node/Express auth prototype has been moved to `prototypes/node-auth-backend` so
it remains available for reference without being confused with the active
backend.

## Architecture Source Documents

- `docs/ACTIVE_SURFACES.md` - current route ownership and Admin surface rules
- `docs/PRD.md` - product and GEO monitoring model
- `docs/ADMIN_PRD.md` - internal Admin console requirements
- `docs/ADMIN_PRD_B_PIPELINE.md` - Planner / Tracker / Analyzer design
- `docs/ADMIN_PRD_C_KG.md` - knowledge graph governance design
- `docs/DATA_MODEL.md` - intended canonical data model
- `docs/ADAPTER_CONTRACT.md` - engine adapter behavior and error contract

## Local Development

### Backend

```bash
cd backend
uv sync --frozen
cp .env.example .env
# Edit .env for database, auth, and provider settings.
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 4000
```

Useful backend checks:

```bash
cd backend
make ci
```

Health endpoints:

- `GET /health`
- `GET /healthz`
- `GET /healthz/db`

The active Admin is served by FastAPI under `backend/`. The SPA shell lives at
`backend/static/admin.html` and is mounted at `/admin`; all admin APIs live
under `/admin/api/*`. The legacy Flask `admin_console/` package has been
removed — do not restore it as a second Admin backend.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server defaults to port `3000` and proxies `/api/*` to the FastAPI
backend on port `4000`. `/admin` and `/admin/api/*` are also served by the
FastAPI backend on `4000`. Do not create a second Admin frontend under
`frontend/src/admin`, `frontend/src/pages/admin`, `frontend-admin`, or Next.js
`app/admin`; see `docs/ACTIVE_SURFACES.md`.

### Worker Stack

The deployed worker services are built from `geo_tracker/` and run Celery
queues for collection and analysis. The app also depends on Postgres and Redis.
For a local container stack:

```bash
cp .env.example .env
# Edit .env with database, Redis, Admin, proxy, and provider secrets.
docker compose up -d
```

## Environment

Root deployment variables are documented in `.env.example`. Backend-only local
variables are documented in `backend/.env.example`.

Minimum backend runtime variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` or `GENPANO_DATABASE_URL` | SQLAlchemy async database URL |
| `REDIS_URL` or `GENPANO_REDIS_URL` | Celery broker/result backend |
| `USER_JWT_SECRET` | Product user access token signing secret |
| `GENPANO_ENVIRONMENT` | `development` or `production` |

## Deployment

`.github/workflows/deploy.yml` builds these images:

- `frontend` from `frontend/`
- `backend` from `backend/` using FastAPI
- `worker` from `geo_tracker/`

`frontend/nginx.conf` routes product `/api`, `/health`, `/admin`, and
`/admin/api` to FastAPI on port `4000`.

## Prototype Notice

`prototypes/node-auth-backend` is an archived prototype for public user
signup/login/email/OAuth flows. It uses an in-memory store and is not part of
the production backend path. Migrate any still-needed public auth behavior into
FastAPI before relying on it in production.

For Admin work, check `AGENTS.md` and `docs/ACTIVE_SURFACES.md` first. The
FastAPI-served `/admin` console (SPA shell at `backend/static/admin.html`) is
the only Admin UI; old React/Next/frontend-admin Admin surfaces must not be
restored.

## Current Implementation Boundary

The repo is mid-transition from prototype surfaces to the PRD target
architecture. Treat these as active convergence tasks:

- Make FastAPI the single backend API surface.
- Persist pipeline data through `query_executions`, `attempts`, and
  `ai_responses`.
- Ensure every adapter response stamps `response_source`.
- Keep account-unavailable cases in `PENDING`, not `FAILED`.
- Move frontend pages from runtime mock data to platform APIs page by page.
