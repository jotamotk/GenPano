#!/usr/bin/env bash
# GENPANO Session A1' Phase Gate Layer 2 wrapper.
# Boots scripts/smoke_admin_a1.py from the backend uv environment.
# Usage: bash scripts/smoke_admin_a1.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/backend"

if ! command -v uv > /dev/null 2>&1; then
  echo "[smoke_admin_a1] uv not on PATH. install with: pip install uv==0.11.4"
  exit 2
fi

exec uv run python "$REPO_ROOT/scripts/smoke_admin_a1.py" "$@"
