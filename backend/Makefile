# GENPANO backend - Session 0' baseline
# Run from backend/ directory: cd backend && make <target>
#
# Targets are thin wrappers around uv. Frank's daily flow is `make ci` before
# pushing; the same lane runs in .github/workflows/ci.yml.

.PHONY: help install lint format type test harness ci migrate clean

help:
	@echo "GENPANO backend - Session 0' baseline"
	@echo ""
	@echo "Targets:"
	@echo "  install   uv sync --frozen (lock-respecting deps install)"
	@echo "  lint      uv run ruff check ."
	@echo "  format    uv run ruff format ."
	@echo "  type      uv run mypy app"
	@echo "  test      uv run pytest -q (exit 5 = no tests, accepted)"
	@echo "  harness   uv run python scripts/ci_check.py + ci_harness_selftest.py"
	@echo "  ci        full local CI: lint + type + harness + migrate + test"
	@echo "  migrate   uv run alembic upgrade head"
	@echo "  clean     remove __pycache__ / .ruff_cache / .mypy_cache / .pytest_cache"

install:
	uv sync --frozen

lint:
	uv run ruff check .

format:
	uv run ruff format .

type:
	uv run mypy app

test:
	@set +e; \
	uv run pytest -q; \
	code=$$?; \
	set -e; \
	if [ "$$code" = "0" ] || [ "$$code" = "5" ]; then \
		if [ "$$code" = "5" ]; then \
			echo "No tests collected (Session 0' baseline) -- accepted."; \
		fi; \
		exit 0; \
	fi; \
	exit $$code

harness:
	uv run python scripts/ci_check.py
	uv run python scripts/ci_harness_selftest.py

migrate:
	uv run alembic upgrade head

ci: lint type harness migrate test
	@echo ""
	@echo "Local CI green. Run 'make format' if format check fails."

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .mypy_cache .pytest_cache
