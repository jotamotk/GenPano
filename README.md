# GenPano

GenPano tracks how Large Language Models (Doubao, ChatGPT, Gemini, DeepSeek, …)
talk about brands. It scrapes LLM responses end-to-end, analyzes them for share
of voice, sentiment, citation authority, and topic coverage, and surfaces the
results through an Admin pipeline view and a customer-facing Reports dashboard.

## Repository layout

| Path | What lives there |
| --- | --- |
| [`backend/`](backend/) | FastAPI HTTP API, Celery app entrypoint, Pydantic contracts, SQLAlchemy models (`genpano_models/`), Alembic migrations |
| [`frontend/`](frontend/) | React 18 + Vite + Tailwind + TanStack Query; pages under `frontend/src/pages/`, generated OpenAPI types in `frontend/src/api/api-types.d.ts` |
| [`geo_tracker/`](geo_tracker/) | LLM scraping subsystem: Playwright browser agents, account pool, analyzer, hotspots, Celery tasks |
| [`clash/`](clash/) | Production proxy infrastructure (vninja); referenced by `docker-compose.yml` and `.github/workflows/deploy.yml` — do not remove |
| [`scripts/`](scripts/) | Operational and one-off scripts (cookie import, log sanitization, cluster registration, ad-hoc triggers) |
| [`docs/`](docs/) | Architecture, PRD, ADRs, runbooks — see [`docs/INDEX.md`](docs/INDEX.md) |
| [`migrations.legacy/`](migrations.legacy/) | Pre-Alembic SQL migrations, archived per ADR-002 |
| [`.github/`](.github/) | Issue templates (epic / agent-task / human), PR template, deploy + CI workflows |

## Quickstart

Requires Docker, Python 3.12, `uv`, and Node 20+.

```bash
# Install all dependencies (backend uv + frontend npm)
make install

# Start backend (FastAPI :4000) + frontend (Vite :5173) together
make dev

# In a separate shell, start a Celery worker
make dev-worker
```

Run the full local CI suite:

```bash
make ci          # backend (ruff + mypy + pytest) + frontend (lint + vitest) + docs guard
make test        # pytest + vitest only
make lint        # ruff + tsc only
```

Container-only path:

```bash
docker-compose up
```

## Documentation entry points

- [`docs/INDEX.md`](docs/INDEX.md) — full navigation of every doc under `docs/`
- [`PRD.md`](PRD.md) — root product requirements
- [`AGENTS.md`](AGENTS.md) — AI Lead / Codex agent collaboration rules — **read before opening a PR**
- [`DEPLOY_GUIDE.md`](DEPLOY_GUIDE.md) — deployment notes
- [`docs/PRD.md`](docs/PRD.md) — long-form product spec

## Contributing

This repository is operated through the AI Lead / Codex agent workflow defined
in [`AGENTS.md`](AGENTS.md). New work starts from an Epic issue
(`.github/ISSUE_TEMPLATE/epic.yml`) with child Agent Task issues
(`.github/ISSUE_TEMPLATE/agent-task.yml`). PRs follow
`.github/PULL_REQUEST_TEMPLATE.md`.

Production target: `http://116.62.36.173/`. Frontend changes intended for
production should include a Playwright check; see the PR template.
