#!/usr/bin/env bash
# GENPANO Session A0' Pre-flight Grep
# Per docs/SESSION_A0_PRIME_PROMPT.md §0 Pre-flight Grep contract
# (decision #25 rule 2). Run from repo root.
#
# Exit 0  = all F1-F8 green, OK to start Step 1
# Exit 1  = any check failed, STOP per §3 Type B and align with Frank
#
# Re-run at Step 12 closing-loop to verify truth sources have not drifted.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0

soft_check() {
  local label="$1"
  local cmd="$2"
  if eval "$cmd" > /tmp/genpano-preflight-a0.log 2>&1 && [ -s /tmp/genpano-preflight-a0.log ]; then
    echo "  [PASS] $label"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $label"
    echo "         cmd: $cmd"
    FAIL=$((FAIL + 1))
  fi
}

file_check() {
  local label="$1"
  local path="$2"
  if [ -f "$path" ]; then
    echo "  [PASS] $label  ($path)"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $label  (missing: $path)"
    FAIL=$((FAIL + 1))
  fi
}

echo "==============================================="
echo "GENPANO Session A0' · Pre-flight Grep (F1-F8)"
echo "==============================================="

echo ""
echo "F1 · CLAUDE.md decisions #24 / #25 / #29 still anchor"
# Note: bypass `·` (UTF-8 0xC2 0xB7) -- Git Bash byte-locale grep treats `.` as
# a single byte and splits the multi-byte char. Match strings on either side.
soft_check "decision #24 (master Session A0)" "grep -n 'Admin 认证脚手架交付' CLAUDE.md"
soft_check "decision #25 (Prompt 公约)"        "grep -n 'Session Prompt 编写公约固化' CLAUDE.md"
soft_check "decision #29 (Python pivot)"       "grep -n 'Python pivot' CLAUDE.md"

echo ""
echo "F2 · ADMIN_PRD §5.6.8 truth-source marker"
soft_check "§5.6.8 anchor in ADMIN_PRD"        "grep -n '5.6.8' docs/ADMIN_PRD.md"

echo ""
echo "F3 · REPLAN_2026_04_26.md §4 Session A0' spec"
soft_check "Session A0' spec in REPLAN"        "grep -n \"Session A0'\" docs/REPLAN_2026_04_26.md"

echo ""
echo "F4 · Session 0' basic infra ready"
file_check "backend/pyproject.toml"            "backend/pyproject.toml"
file_check "backend/app/main.py"               "backend/app/main.py"
file_check "backend/alembic.ini"               "backend/alembic.ini"

echo ""
echo "F5 · decision #24.C1.2 (forcePasswordChangeAt) lock"
soft_check "forcePasswordChangeAt DateTime?"   "grep -n 'forcePasswordChangeAt DateTime?' CLAUDE.md"
soft_check "decision #24.C1.2 deviation"       "grep -n 'C1.2 (字段命名 . 类型双偏差' CLAUDE.md"

echo ""
echo "F6 · ADMIN_PRD purpose / role CHECK constraints"
soft_check "role CHECK in ADMIN_PRD"           "grep -nE 'role.+IN.+super_admin' docs/ADMIN_PRD.md"

echo ""
echo "F7 · Frontend admin baseline files (复用, not new)"
file_check "AdminLoginPage.jsx"                "frontend/src/admin/pages/AdminLoginPage.jsx"
file_check "AdminForgotPasswordPage.jsx"       "frontend/src/admin/pages/AdminForgotPasswordPage.jsx"
file_check "AdminChangePasswordPage.jsx"       "frontend/src/admin/pages/AdminChangePasswordPage.jsx"
file_check "AdminDashboardPage.jsx"            "frontend/src/admin/pages/AdminDashboardPage.jsx"
file_check "AdminAuthContext.jsx"              "frontend/src/admin/context/AdminAuthContext.jsx"
file_check "AdminRouteGuard.jsx"               "frontend/src/admin/components/AdminRouteGuard.jsx"
file_check "SessionExpiredModal.jsx"           "frontend/src/admin/components/SessionExpiredModal.jsx"
file_check "adminApi.js"                       "frontend/src/admin/lib/adminApi.js"

echo ""
echo "F8 · decision-reference format compliance scan"
soft_check "decision-N references found"       "grep -nE '决策 #[0-9]+' docs/SESSION_A0_PRIME_PROMPT.md"

echo ""
echo "==============================================="
echo "Result: $PASS PASS / $FAIL FAIL"
echo "==============================================="

if [ "$FAIL" -gt 0 ]; then
  echo "Pre-flight FAILED. STOP per §3 Type B; align with Frank before Step 1."
  exit 1
fi
echo "Pre-flight GREEN. OK to start Session A0' Step 1."
