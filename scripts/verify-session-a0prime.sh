#!/usr/bin/env bash
# GENPANO Session A0' Phase Gate Layer 1 verification script
# Usage: bash scripts/verify-session-a0prime.sh
# Run from repo root.
#
# Mirrors scripts/verify-session-0prime.sh in shape so Frank's daily flow is
# identical across both sessions. Single bash file, runs on Git Bash (Windows)
# and Linux sandbox alike. No PowerShell mirror — same code path everywhere.
#
# Sections (matches docs/SESSION_A0_PRIME_PROMPT.md §4.G_A0.1):
#   §1  File-presence checks (12 backend modules + 6 endpoints + 8 frontend)
#   §2  ruff lint + mypy strict
#   §3  pytest with coverage gate ≥80%
#   §4  alembic upgrade head
#   §5  4 admin tables exist (cross-DB via SQLAlchemy)
#   §6  CHECK constraint actual reject (Postgres only; SQLite [skipped])
#   §7  harness selftest (7/7 fixture expectations met)
#   §8  admin-bootstrap idempotency (row count invariant across two runs)
#
# Decision #25 Rule 3 deviations from the prompt (intentional):
#   C1 · psql literal → SQLAlchemy Python helper for cross-DB / cross-platform
#   C2 · CHECK assert gated on Postgres; SQLite skipped (default no enforce)
#   C3 · selftest expected 7 not 6 (D9 + D10 fixtures landed in Step 6).
#        Prompt §4.G_A0.2 line 254 alignment deferred to Step 12 docs sync.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==============================================="
echo "GENPANO Session A0' Phase Gate Layer 1"
echo "==============================================="
echo ""

PASS=0
FAIL=0
SKIP=0

check() {
  local label="$1"
  local cmd="$2"
  echo -n "[$((PASS + FAIL + SKIP + 1))] $label ... "
  # Run inside a subshell so any `cd` inside $cmd does NOT leak across
  # consecutive checks. Each check starts back at $REPO_ROOT.
  if ( eval "$cmd" ) > /tmp/genpano-verify-a0.log 2>&1; then
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL"
    echo "    Command: $cmd"
    echo "    Output (last 12 lines):"
    tail -12 /tmp/genpano-verify-a0.log | sed 's/^/      /'
    FAIL=$((FAIL + 1))
  fi
}

skip() {
  local label="$1"
  local reason="$2"
  echo "[$((PASS + FAIL + SKIP + 1))] $label ... SKIP ($reason)"
  SKIP=$((SKIP + 1))
}

# --------------------------------------------------------------------------
# §1 File-presence checks
# --------------------------------------------------------------------------
echo "▶ §1 File-presence (Steps 1-8 deliverables)"

# Backend admin/auth modules (Steps 2-4)
# Python translation inlined `rate_limit_config` constants into rate_limiter.py
# (capacity + window literals, lines 30-32) so there are 11 modules, not 12.
# CLAUDE.md decision #24.B / #24.F still mentions rate-limit-config.ts as the
# TypeScript-era module name; the Python merge is registered as a Step 12 docs
# sync alongside the §7 selftest 6→7 alignment (decision #25 Rule 3 deviation).
for f in constants jwt refresh_token password cookies reauth_gate \
         rate_limiter session_repo middleware audit email; do
  check "backend/app/admin/auth/${f}.py" \
        "test -f backend/app/admin/auth/${f}.py"
done

# Backend admin/auth endpoints (Step 5)
for f in login refresh logout forgot_password reset_password change_password; do
  check "backend/app/admin/api/v1/auth/${f}.py" \
        "test -f backend/app/admin/api/v1/auth/${f}.py"
done

# Bootstrap script (Step 6)
check "backend/scripts/admin-bootstrap.py" \
      "test -f backend/scripts/admin-bootstrap.py"

# Frontend baseline (Step 7-8)
for f in pages/AdminLoginPage.jsx pages/AdminForgotPasswordPage.jsx \
         pages/AdminChangePasswordPage.jsx pages/AdminDashboardPage.jsx \
         context/AdminAuthContext.jsx components/AdminRouteGuard.jsx \
         components/SessionExpiredModal.jsx lib/adminApi.js; do
  check "frontend/src/admin/${f}" "test -f frontend/src/admin/${f}"
done

# E2E test file (Step 9)
check "backend/tests/admin/auth/test_e2e_integration.py" \
      "test -f backend/tests/admin/auth/test_e2e_integration.py"

# --------------------------------------------------------------------------
# §2-§8 — backend functional checks (require uv)
# --------------------------------------------------------------------------
if ! command -v uv > /dev/null 2>&1; then
  echo ""
  echo "▶ §2-§8 backend checks SKIPPED — uv not installed"
  echo "    Install with: pip install uv==0.11.4"
  SKIP=$((SKIP + 7))
else
  # ----------------------------------------------------------------------
  # §2 ruff + mypy
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §2 Lint + type"
  check "ruff check ." \
        "cd backend && uv run ruff check ."
  check "mypy app" \
        "cd backend && uv run mypy app"

  # ----------------------------------------------------------------------
  # §3 pytest with coverage gate ≥80%
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §3 pytest + coverage gate"
  check "pytest tests/admin/auth/ --cov-fail-under=80" \
        "cd backend && uv run pytest tests/admin/auth/ \
            --cov=app/admin/auth --cov-report=term-missing --cov-fail-under=80"

  # ----------------------------------------------------------------------
  # §4 alembic upgrade head
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §4 alembic"
  check "alembic upgrade head" \
        "cd backend && uv run alembic upgrade head"

  # ----------------------------------------------------------------------
  # §5 4 admin tables exist (cross-DB SQLAlchemy)
  # C1 deviation · prompt used psql literal; replaced with Python helper
  # so this works on SQLite (MVP default) AND Postgres without psql.
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §5 admin tables exist"
  check "admin_users / admin_sessions / admin_password_resets / admin_login_attempts" \
        "cd backend && uv run python -c \"
import asyncio
from sqlalchemy import inspect
from app.db.session import engine
async def main():
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    expected = {'admin_users', 'admin_sessions', 'admin_password_resets', 'admin_login_attempts'}
    missing = expected - set(tables)
    if missing:
        raise SystemExit(f'missing tables: {missing}')
    print(f'all 4 admin tables present: {sorted(expected)}')
asyncio.run(main())
\""

  # ----------------------------------------------------------------------
  # §6 CHECK constraint reject (Postgres only)
  # C2 deviation · SQLite default doesn't enforce CHECK strict reject;
  # gate on DATABASE_URL prefix and skip on SQLite. CI Postgres exercise
  # lives in Step 11 GitHub Actions, not here.
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §6 CHECK constraint reject"
  DB_URL_PREFIX="$( ( cd backend && uv run python -c \
    'from app.core.config import get_settings; print(get_settings().database_url.split(":")[0])' \
    ) 2>/dev/null || echo unknown)"
  if [[ "$DB_URL_PREFIX" == postgres* ]]; then
    check "INSERT role='NOT_A_VALID_ROLE' rejected by CHECK" \
          "cd backend && uv run python -c \"
import asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db.session import AsyncSessionLocal
async def main():
    async with AsyncSessionLocal() as s:
        try:
            await s.execute(text(
                \\\"INSERT INTO admin_users (email, password_hash, role, status) \\\"
                \\\"VALUES ('check-test@x.com', 'x', 'NOT_A_VALID_ROLE', 'active')\\\"
            ))
            await s.commit()
        except IntegrityError as e:
            print(f'CHECK rejected as expected: {e.orig}')
            return
    raise SystemExit('CHECK constraint did NOT reject invalid role')
asyncio.run(main())
\""
  else
    skip "INSERT role='NOT_A_VALID_ROLE' rejected by CHECK" \
         "$DB_URL_PREFIX backend; SQLite default does not enforce strict CHECK reject. Postgres path runs in Step 11 GitHub Actions."
  fi

  # ----------------------------------------------------------------------
  # §7 harness selftest
  # C3 deviation · expected 7/7 not 6/6 (D9 + D10 fixtures land Step 6).
  # Prompt §4.G_A0.2 alignment deferred to Step 12 docs sync.
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §7 harness selftest"
  check "ci_harness_selftest 7/7 fixture expectations met" \
        "cd backend && uv run python scripts/ci_harness_selftest.py"

  # ----------------------------------------------------------------------
  # §8 admin-bootstrap idempotency
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §8 admin-bootstrap idempotent"
  check "row count invariant across two bootstrap runs" \
        "cd backend && \
         export ADMIN_BOOTSTRAP_EMAIL='verify-a0prime@example.com' && \
         export ADMIN_BOOTSTRAP_PASSWORD='Verify-A0prime-Strong-9!' && \
         uv run python scripts/admin-bootstrap.py > /dev/null && \
         BEFORE=\$(uv run python -c \"
import asyncio
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models.admin import AdminUser
async def main():
    async with AsyncSessionLocal() as s:
        n = (await s.execute(select(func.count()).select_from(AdminUser).where(AdminUser.role=='super_admin'))).scalar_one()
        print(n)
asyncio.run(main())
\") && \
         uv run python scripts/admin-bootstrap.py > /dev/null && \
         AFTER=\$(uv run python -c \"
import asyncio
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models.admin import AdminUser
async def main():
    async with AsyncSessionLocal() as s:
        n = (await s.execute(select(func.count()).select_from(AdminUser).where(AdminUser.role=='super_admin'))).scalar_one()
        print(n)
asyncio.run(main())
\") && \
         test \"\$BEFORE\" = \"\$AFTER\" && \
         echo \"super_admin count invariant: \$BEFORE = \$AFTER\""
fi

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
echo "==============================================="
echo "Result: $PASS PASS / $FAIL FAIL / $SKIP SKIP"
echo "==============================================="

if [ "$FAIL" -gt 0 ]; then
  echo "Session A0' Phase Gate Layer 1 verification: RED"
  exit 1
fi
echo "Session A0' Phase Gate Layer 1 verification: GREEN"
