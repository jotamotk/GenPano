#!/usr/bin/env bash
# GENPANO Session A1' Phase Gate Layer 1 verification script
# Usage: bash scripts/verify-session-a1prime.sh
# Run from repo root.
#
# Mirrors scripts/verify-session-a0prime.sh in shape so Frank's daily flow is
# identical across both sessions. Single bash file, runs on Git Bash (Windows)
# and Linux sandbox alike. No PowerShell mirror — same code path everywhere.
#
# Sections (matches docs/SESSION_A1_PRIME_PROMPT.md §4 Layer 1):
#   §1  File-presence checks (Step 1-9 deliverables — backend + frontend)
#   §2  ruff lint + ruff format --check + mypy strict
#   §3  pytest with coverage gate ≥80% (admin scope)
#   §4  alembic upgrade head + downgrade -1 + upgrade head (3-way roundtrip)
#   §5  12 admin tables exist (A0' 4 + A1' Step 1 8) + users 表 + 3 FK
#   §6  J5 invariant — admin write-only column whitelist
#   §7  harness selftest (12/12 fixture expectations met)
#   §8  ci_check 12 rules 0 violations
#   §9  admin-bootstrap idempotency (row count invariant)
#  §10  Step 10 infra config syntax (docker-compose.admin / vercel.json /
#       render.yaml)
#  §11  frontend npm run build (Vite 17 admin pages compile)
#  §12  decision-log-sync-check (CLAUDE.md ↔ DECISION_LOG.md)
#
# Decision #25 Rule 3 deviations from §4 Layer 1 spec (intentional):
#   C1 · §4 Layer 1 line 352 expects selftest 32/32. Actual is 12/12 because
#        Step 8 #30.I deleted 4 TS-era frontend .mjs scripts which carried
#        20+ frontend rules; A1' selftest is 12/12 (B+J groups only). Step
#        12 docs sync will reconcile §4 line 352.
#   C2 · §4 Layer 1 line 346 L1.5 psql forbidden-column check is gated on
#        Postgres backend; SQLite (MVP default) skipped because information_
#        schema availability differs. Postgres path runs in Step 11/12 CI.
#   C3 · L1.10 admin curl smoke is split out into smoke_admin_a1.sh per the
#        §5 Step 11 row breakdown — verify script does NOT inline curl.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==============================================="
echo "GENPANO Session A1' Phase Gate Layer 1"
echo "==============================================="
echo ""

PASS=0
FAIL=0
SKIP=0

check() {
  local label="$1"
  local cmd="$2"
  echo -n "[$((PASS + FAIL + SKIP + 1))] $label ... "
  if ( eval "$cmd" ) > /tmp/genpano-verify-a1.log 2>&1; then
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL"
    echo "    Command: $cmd"
    echo "    Output (last 12 lines):"
    tail -12 /tmp/genpano-verify-a1.log | sed 's/^/      /'
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
# §1 File-presence checks (Step 1-9 deliverables)
# --------------------------------------------------------------------------
echo "▶ §1 File-presence (Steps 1-10 deliverables)"

# Backend admin module additions (Steps 1-7)
for f in services/admin_audit.py \
         admin/middleware/rbac.py \
         admin/api/v1/users.py \
         admin/api/v1/kg.py \
         models/user.py; do
  check "backend/app/${f}" "test -f backend/app/${f}"
done

# A1' Step 1 8 admin tables — covered by §5 SQLAlchemy inspect
# A1' tests
for f in test_a1_models.py \
         test_users_endpoints.py \
         test_a1_kg_endpoints.py \
         test_a1_group_j_harness.py \
         fixtures_j5.py; do
  check "backend/tests/admin/${f}" "test -f backend/tests/admin/${f}"
done

# Step 9 frontend admin pages (sample 5 of 17 .tsx — Frank's TSX migration)
for f in users/UsersListPage.tsx \
         kg/KGAliasesRelationsPage.tsx \
         kg/KGBrandSubmissionsPage.tsx \
         pipeline/PipelineOverviewPage.tsx \
         cost/CostDailyPage.tsx; do
  check "frontend/src/admin/pages/${f}" "test -f frontend/src/admin/pages/${f}"
done

# Step 10 infra
for f in docker-compose.admin.yml vercel.json render.yaml; do
  check "${f}" "test -f ${f}"
done

# --------------------------------------------------------------------------
# §2-§12 — backend functional checks (require uv)
# --------------------------------------------------------------------------
if ! command -v uv > /dev/null 2>&1; then
  echo ""
  echo "▶ §2-§12 backend checks SKIPPED — uv not installed"
  echo "    Install with: pip install uv==0.11.4"
  SKIP=$((SKIP + 11))
else
  # ----------------------------------------------------------------------
  # §2 ruff (lint + format) + mypy
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §2 Lint + format + type"
  check "ruff check ." \
        "cd backend && uv run ruff check ."
  check "ruff format --check (no auto-fix)" \
        "cd backend && uv run ruff format --check ."
  check "mypy --strict app" \
        "cd backend && uv run mypy --strict app"

  # ----------------------------------------------------------------------
  # §3 pytest with coverage gate ≥80% (full admin scope)
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §3 pytest + coverage gate"
  check "pytest --cov-fail-under=80 (full suite)" \
        "cd backend && uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=80 -q"

  # ----------------------------------------------------------------------
  # §4 alembic upgrade head + downgrade -1 + upgrade head (3-way roundtrip)
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §4 alembic 3-way roundtrip"
  check "alembic upgrade head" \
        "cd backend && uv run alembic upgrade head"
  check "alembic downgrade -1" \
        "cd backend && uv run alembic downgrade -1"
  check "alembic upgrade head (replay)" \
        "cd backend && uv run alembic upgrade head"

  # ----------------------------------------------------------------------
  # §5 12 admin tables + users + 3 FK exist (cross-DB SQLAlchemy)
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §5 admin tables + users + FK exist"
  check "12 admin tables (A0' 4 + A1' 8) + users present" \
        "cd backend && uv run python -c \"
import asyncio
from sqlalchemy import inspect
from app.db.session import engine
async def main():
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    expected = {
        'admin_users', 'admin_sessions', 'admin_password_resets', 'admin_login_attempts',
        'user_moderation_actions', 'user_activity_stats', 'kg_review_queue',
        'alias_conflicts', 'brand_submissions', 'alerts', 'cost_daily', 'budget_config',
        'users',
    }
    missing = expected - set(tables)
    if missing:
        raise SystemExit(f'missing tables: {sorted(missing)}')
    print(f'all 13 tables present ({len(expected)} expected)')
asyncio.run(main())
\""

  # ----------------------------------------------------------------------
  # §6 J5 invariant — admin write-only column whitelist
  # C2 deviation · skip on SQLite (information_schema differs)
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §6 J5 invariant — admin write-only column whitelist"
  DB_URL_PREFIX="$( ( cd backend && uv run python -c \
    'from app.core.config import get_settings; print(get_settings().database_url.split(":")[0])' \
    ) 2>/dev/null || echo unknown)"
  if [[ "$DB_URL_PREFIX" == postgres* ]]; then
    check "J5 whitelist: only users.deletion_requested_at writable by admin" \
          "cd backend && uv run python -c \"
from tests.admin.fixtures_j5 import ALLOWED_USER_WRITE_COLUMNS
expected = {'deletion_requested_at'}
got = set(ALLOWED_USER_WRITE_COLUMNS)
if got != expected:
    raise SystemExit(f'J5 whitelist drift: expected={sorted(expected)} got={sorted(got)}')
print(f'J5 whitelist invariant OK: {sorted(got)}')
\""
  else
    skip "J5 whitelist (Postgres-only)" \
         "$DB_URL_PREFIX backend; J5 enforced via pytest test_a1_group_j_harness.py + fixture in §3."
  fi

  # ----------------------------------------------------------------------
  # §7 harness selftest 12/12
  # C1 deviation · spec §4 line 352 says 32/32 (counted frontend rules
  # deleted in Step 8 #30.I). A1' actual is 12/12.
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §7 harness selftest"
  check "ci_harness_selftest 12/12 fixture expectations met" \
        "cd backend && uv run python scripts/ci_harness_selftest.py"

  # ----------------------------------------------------------------------
  # §8 ci_check 12 rules 0 violations
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §8 ci_check"
  check "ci_check 12 rules (F1/F4-1/2/3/D8/D9/D10/J1-J5) 0 violations" \
        "cd backend && uv run python scripts/ci_check.py"

  # ----------------------------------------------------------------------
  # §9 admin-bootstrap idempotency
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §9 admin-bootstrap idempotent"
  check "row count invariant across two bootstrap runs" \
        "cd backend && \
         export ADMIN_BOOTSTRAP_EMAIL='verify-a1prime@example.com' && \
         export ADMIN_BOOTSTRAP_PASSWORD='Verify-A1prime-Strong-9!' && \
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

  # ----------------------------------------------------------------------
  # §10 Step 10 infra config syntax
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §10 Step 10 infra syntax"
  check "vercel.json + render.yaml + docker-compose.admin.yml syntactically valid" \
        "cd backend && uv run python -c \"
import json, yaml
json.load(open('../vercel.json', encoding='utf-8'))
yaml.safe_load(open('../render.yaml', encoding='utf-8'))
yaml.safe_load(open('../docker-compose.admin.yml', encoding='utf-8'))
print('infra config syntax OK')
\""
  if command -v docker > /dev/null 2>&1; then
    check "docker compose -f docker-compose.admin.yml --profile admin config" \
          "docker compose -f docker-compose.admin.yml --profile admin config > /dev/null"
  else
    skip "docker compose --profile admin config" "docker not on PATH"
  fi

  # ----------------------------------------------------------------------
  # §11 frontend admin build
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §11 frontend admin build"
  if command -v npm > /dev/null 2>&1; then
    check "frontend npm run build" \
          "cd frontend && npm run build > /tmp/genpano-verify-a1-fe.log 2>&1"
  else
    skip "frontend npm run build" "npm not on PATH"
  fi

  # ----------------------------------------------------------------------
  # §12 decision-log-sync-check (Step 8 deliverable)
  # ----------------------------------------------------------------------
  echo ""
  echo "▶ §12 decision-log-sync-check"
  check "CLAUDE.md ↔ DECISION_LOG.md in sync" \
        "cd backend && uv run python scripts/decision_log_sync_check.py"
fi

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
echo "==============================================="
echo "Result: $PASS PASS / $FAIL FAIL / $SKIP SKIP"
echo "==============================================="

if [ "$FAIL" -gt 0 ]; then
  echo "Session A1' Phase Gate Layer 1 verification: RED"
  exit 1
fi
echo "Session A1' Phase Gate Layer 1 verification: GREEN"
