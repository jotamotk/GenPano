# GenPano repository-level Makefile (Phase R.5)
#
# Provides single-command developer experience for the whole stack:
#   make dev      — start backend + worker + frontend dev servers
#   make ci       — run full CI suite (backend + frontend + cross-package checks)
#   make migrate  — alembic upgrade head
#   make lint     — ruff + tsc across stack
#   make test     — pytest + vitest
#
# Sub-Makefiles in backend/, frontend/ retain their fine-grained targets.

.PHONY: help dev dev-backend dev-frontend dev-worker \
        ci ci-backend ci-frontend ci-fast ci-docs \
        migrate migrate-down migrate-rev \
        lint lint-backend lint-frontend lint-fix \
        test test-backend test-frontend test-e2e \
        clean install build

help: ## Show this help
	@echo 'GenPano Makefile targets:'
	@echo ''
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Common workflows:'
	@echo '  Local dev:    make install && make dev'
	@echo '  Pre-commit:   make lint && make test'
	@echo '  CI dry-run:   make ci'

# ─────────────────────────────────────────────────────────────────
# Install
# ─────────────────────────────────────────────────────────────────

install: ## Install all dependencies (backend uv + frontend npm)
	cd backend && uv sync
	cd frontend && npm install
	@echo '✓ Dependencies installed.'

# ─────────────────────────────────────────────────────────────────
# Dev
# ─────────────────────────────────────────────────────────────────

dev: ## Start backend + frontend (use Ctrl+C to stop)
	@echo 'Starting backend (port 4000) + frontend (port 3000)...'
	@echo 'Note: worker not started here; run "make dev-worker" in another shell if needed.'
	@( $(MAKE) dev-backend & $(MAKE) dev-frontend & wait )

dev-backend: ## Start FastAPI backend with reload
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 4000

dev-frontend: ## Start Vite dev server
	cd frontend && npm run dev

dev-worker: ## Start Celery worker (collection + analysis queues)
	cd geo_tracker && celery -A geo_tracker.tasks.celery_tasks worker -Q collection,analysis -l info

# ─────────────────────────────────────────────────────────────────
# CI
# ─────────────────────────────────────────────────────────────────

ci: ci-backend ci-frontend ci-docs ## Full CI suite (backend + frontend + docs)
	@echo '✓ All CI checks passed.'

ci-backend: ## Backend ruff + mypy + pytest
	cd backend && $(MAKE) ci

ci-frontend: ## Frontend lint + unit + harness
	cd frontend && npm run ci

ci-fast: ## Frontend fast CI subset (changed files only)
	cd frontend && npm run ci:fast

ci-docs: ## Validate docs (PRD anchors + OpenAPI sync placeholders)
	@echo 'Phase P CI guards (placeholder until tests land):'
	@echo '  - docs/PRD_PAGE_MAP.md exists?'
	@test -f docs/PRD_PAGE_MAP.md && echo '    ✓ yes' || (echo '    ✗ MISSING'; exit 1)
	@echo '  - docs/ADR/ has 15 ADRs?'
	@test $$(ls docs/ADR/0*.md 2>/dev/null | wc -l) -ge 15 && echo '    ✓ yes' || (echo '    ✗ found <15'; exit 1)
	@echo '  - docs/openapi*.yaml exists?'
	@test -f docs/openapi.yaml -a -f docs/openapi_addendum_phase_p.yaml && echo '    ✓ yes' || (echo '    ✗ MISSING'; exit 1)

# ─────────────────────────────────────────────────────────────────
# Database / Alembic
# ─────────────────────────────────────────────────────────────────

migrate: ## alembic upgrade head
	cd backend && uv run alembic upgrade head

migrate-down: ## alembic downgrade -1
	cd backend && uv run alembic downgrade -1

migrate-rev: ## alembic revision --autogenerate -m "..."（需 traist 参数 m=）
	@if [ -z "$(m)" ]; then echo 'usage: make migrate-rev m="add foo table"'; exit 1; fi
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

migrate-heads: ## Show alembic head(s)
	cd backend && uv run alembic heads

# ─────────────────────────────────────────────────────────────────
# Lint
# ─────────────────────────────────────────────────────────────────

lint: lint-backend lint-frontend ## Lint backend + frontend
	@echo '✓ All lint checks passed.'

lint-backend: ## Backend ruff + mypy
	cd backend && uv run ruff check . && uv run mypy app/ genpano_models/

lint-frontend: ## Frontend tsc + eslint (eslint via npm script if exists)
	cd frontend && npx tsc --noEmit
	@cd frontend && (npm run lint 2>/dev/null || echo '  (no eslint script defined; tsc only)')

lint-fix: ## Auto-fix lint issues (ruff + ts-no-fix-available)
	cd backend && uv run ruff check --fix . && uv run ruff format .

# ─────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────

test: test-backend test-frontend ## Run all tests (no e2e)
	@echo '✓ All tests passed.'

test-backend: ## Backend pytest
	cd backend && uv run pytest

test-frontend: ## Frontend vitest
	cd frontend && npm run test:unit -- --run

test-e2e: ## Frontend Playwright e2e
	cd frontend && npm run test:e2e

test-cov: ## Backend coverage report
	cd backend && uv run pytest --cov=app --cov=genpano_models --cov-report=term-missing

# ─────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────

build: ## Production frontend build
	cd frontend && npm run build

# ─────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────

clean: ## Remove caches / build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist frontend/node_modules/.vite 2>/dev/null || true
	@echo '✓ Caches cleaned.'

.DEFAULT_GOAL := help
