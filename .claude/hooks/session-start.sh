#!/bin/bash
# SessionStart hook for Claude Code sessions in this repository.
#
# Mechanism: Claude Code runs this script at session start (sources:
# startup | resume | clear | compact). Whatever this script prints to stdout
# is wrapped as a `system-reminder` and injected into Claude's first model
# request, ensuring the AGENTS.md hard rules are in context for every
# session even after resume/clear/compact.
#
# Anti-context-poisoning design:
#   * The "Hard rules" block is NOT hand-written here. It is extracted at
#     runtime from AGENTS.md's `<!-- DIGEST-BEGIN -->...<!-- DIGEST-END -->`
#     section via awk. Editing the digest in this script is forbidden — see
#     rules/MAINTENANCE.md §4.1. The single source of truth is AGENTS.md.
#   * If extraction fails (block missing / malformed), we fail loudly with a
#     visible marker so the gap is obvious instead of silently injecting
#     stale text from a previous version.
#
# This is Layer 3 of the enforcement model documented in
# rules/security/enforcement.md and rules/MAINTENANCE.md §5
# (Cross-agent Consistency Contract) — best-effort, agent-specific. If this
# layer fails, Layer 1 (`.github/workflows/pr-body-lint.yml`) still blocks
# non-conforming PRs at merge time.
#
# Design constraints:
# - Synchronous (no `{"async": true}` wrapper). Output is plain stdout, not JSON.
# - Must not fail session start if any inner command fails. Tolerate errors
#   with `|| echo unknown` / `|| true` patterns; intentionally omit `set -e`.
# - Must work both inside the repo and from a clean clone where `.git` may
#   be absent or the working directory may differ.
# - Output is intentionally narrow (~40-60 lines) — the goal is high-signal
#   rule reminders, not re-pasting all of rules/.

set -uo pipefail  # NB: no -e; we tolerate inner command failures

PROJECT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo /home/user/trash_test)}"

# Gather session-specific git context defensively. Any failure -> "unknown".
BRANCH="$(cd "$PROJECT" 2>/dev/null && git branch --show-current 2>/dev/null || echo unknown)"
CHANGED_COUNT="$(cd "$PROJECT" 2>/dev/null && git status --short 2>/dev/null | wc -l | tr -d ' ' || echo 0)"
RECENT_COMMIT="$(cd "$PROJECT" 2>/dev/null && git log -1 --oneline 2>/dev/null || echo none)"

# Machine-extract the Hard Rule Digest block from AGENTS.md.
# The block is delimited by `<!-- DIGEST-BEGIN -->` and `<!-- DIGEST-END -->`.
# awk prints inclusive of the markers; `sed '1d;$d'` strips the marker lines.
DIGEST_BLOCK=""
if [ -f "$PROJECT/AGENTS.md" ]; then
  DIGEST_BLOCK="$(awk '/<!-- DIGEST-BEGIN -->/,/<!-- DIGEST-END -->/' "$PROJECT/AGENTS.md" 2>/dev/null \
    | sed '1d;$d' 2>/dev/null || echo '')"
fi

if [ -z "$DIGEST_BLOCK" ]; then
  DIGEST_BLOCK="!! DIGEST MISSING from AGENTS.md — agents should open a rules-change issue immediately. See rules/MAINTENANCE.md §4.1."
fi

cat <<EOF
=== Repository agent rules (auto-extracted from AGENTS.md DIGEST block) ===

This repo has hard rules that have been violated in the past. ALL agents
(Claude main session, subagents dispatched via the Agent tool, Codex,
Cursor, Aider, Devin, human contributors) MUST follow these.

Index:        ${PROJECT}/AGENTS.md
Detail rules: ${PROJECT}/rules/ — load on demand by concern:
  - rules/global/        (orchestrator / fast-full path / topology / peer review)
  - rules/testing/       (evidence-first / acceptance / tiered E2E)
  - rules/security/      (enforcement / CI gates)
  - rules/frontend/      (admin surface / workflow / terms)
  - rules/backend/       (admin boundary)
  - rules/documentation/ (issue / PR / PRD)

== Hard rules ==
${DIGEST_BLOCK}

== CI enforcement ==

GitHub CI rejects any PR whose body omits Root Cause Gate / Business Goal /
Verification Evidence Ledger. \`.github/workflows/pr-body-lint.yml\` is the
gate. No agent (including this one) can bypass at merge time. See
rules/security/enforcement.md and rules/MAINTENANCE.md §5 (Cross-agent
Consistency Contract).

== Session-specific context ==

Current branch:      ${BRANCH}
Uncommitted files:   ${CHANGED_COUNT}
Most-recent commit:  ${RECENT_COMMIT}

EOF
