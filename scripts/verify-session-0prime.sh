#!/usr/bin/env bash
# GENPANO Session 0' Phase Gate 1 verification script
# Usage: bash scripts/verify-session-0prime.sh
# Run from repo root.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==============================================="
echo "GENPANO Session 0' Phase Gate 1 verification"
echo "==============================================="
echo ""

PASS=0
FAIL=0

check() {
  local label="$1"
  local cmd="$2"
  echo -n "[$((PASS + FAIL + 1))] $label ... "
  if eval "$cmd" > /tmp/genpano-verify.log 2>&1; then
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL"
    echo "    Command: $cmd"
    echo "    Output (last 10 lines):"
    tail -10 /tmp/genpano-verify.log | sed 's/^/      /'
    FAIL=$((FAIL + 1))
  fi
}

# 1. Repo structure
check "backend/pyproject.toml exists" "test -f backend/pyproject.toml"
check "backend/uv.lock exists" "test -f backend/uv.lock"
check "backend/alembic/env.py exists" "test -f backend/alembic/env.py"
check "backend/app/celery_app.py exists" "test -f backend/app/celery_app.py"
check "backend/app/core/config.py exists" "test -f backend/app/core/config.py"
check "backend/scripts/ci_check.py exists" "test -f backend/scripts/ci_check.py"
check "backend/scripts/ci_harness_selftest.py exists" "test -f backend/scripts/ci_harness_selftest.py"
check "backend/Makefile exists" "test -f backend/Makefile"
check ".pre-commit-config.yaml exists" "test -f .pre-commit-config.yaml"

# 2. Workflows
check ".github/workflows/ci.yml exists" "test -f .github/workflows/ci.yml"
check ".github/workflows/deploy-preview.yml exists" "test -f .github/workflows/deploy-preview.yml"
check "ci.yml has backend-lint-test job" "grep -q 'backend-lint-test:' .github/workflows/ci.yml"
check "deploy-preview.yml has backend-preview job" "grep -q 'backend-preview:' .github/workflows/deploy-preview.yml"

# 3. Fixtures (5 self-seeded)
for fix in F1_playwright_bare_import F4_1_no_response_source_stamp F4_2_api_fallback_no_label F4_3_orm_insert_no_response_source D8_hardcoded_jwt_secret; do
  check "fixture $fix exists" "test -f backend/app/__ci_fixtures__/${fix}.cifixture.py"
done

# 4. Backend functional checks (require uv installed)
if command -v uv > /dev/null 2>&1; then
  check "uv sync --frozen" "cd backend && uv sync --frozen"
  check "ruff check passes" "cd backend && uv run ruff check ."
  check "mypy app passes" "cd backend && uv run mypy app"
  check "ci_check.py main lanes clean" "cd backend && uv run python scripts/ci_check.py"
  check "ci_harness_selftest.py 5/5" "cd backend && uv run python scripts/ci_harness_selftest.py"
  check "alembic upgrade head" "cd backend && uv run alembic upgrade head"
else
  echo "    [skipped] uv not installed -- install with 'pip install uv==0.11.4'"
fi

# 5. Summary
echo ""
echo "==============================================="
echo "Result: $PASS PASS / $FAIL FAIL"
echo "==============================================="

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo "Session 0' Phase Gate 1 verification: GREEN"
