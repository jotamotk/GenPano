#!/bin/bash
# SessionStart hook for Claude Code sessions in this repository.
#
# Mechanism: Claude Code runs this script at session start (sources:
# startup | resume | clear | compact). Whatever this script prints to stdout
# is wrapped as a `system-reminder` and injected into Claude's first model
# request, ensuring the AGENTS.md hard rules are in context for every
# session even after resume/clear/compact.
#
# This is Layer 3 of the enforcement model documented in
# AGENTS.md `## Enforcement` — best-effort, agent-specific. If this layer
# fails for any reason, Layer 1 (`.github/workflows/pr-body-lint.yml`) still
# blocks non-conforming PRs at merge time.
#
# Design constraints:
# - Synchronous (no `{"async": true}` wrapper). Output is plain stdout, not
#   JSON.
# - Must not fail session start if any inner command fails. We tolerate
#   errors with `|| echo unknown` / `|| true` patterns and intentionally
#   omit `set -e`.
# - Must work both inside the repo and from a clean clone where `.git` may
#   be absent or the working directory may differ.
# - Output is intentionally narrow (~40-50 lines) — the goal is high-signal
#   rule reminders, not re-pasting all ~400 lines of AGENTS.md.

set -uo pipefail  # NB: no -e; we tolerate inner command failures

PROJECT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo /home/user/trash_test)}"

# Gather session-specific git context defensively. Any failure -> "unknown".
BRANCH="$(cd "$PROJECT" 2>/dev/null && git branch --show-current 2>/dev/null || echo unknown)"
CHANGED_COUNT="$(cd "$PROJECT" 2>/dev/null && git status --short 2>/dev/null | wc -l | tr -d ' ' || echo 0)"
RECENT_COMMIT="$(cd "$PROJECT" 2>/dev/null && git log -1 --oneline 2>/dev/null || echo none)"

cat <<EOF
=== Repository agent rules (digest from AGENTS.md) ===

This repo has hard rules that have been violated in the past. ALL agents
(Claude main session, subagents dispatched via the Agent tool, Codex,
Cursor, Aider, Devin, human contributors) MUST follow these.

Full ruleset: ${PROJECT}/AGENTS.md
Key sections: "Evidence-First Debugging", "Business Goal And Root Cause
Gates", "Evidence-First Shipping", "## Enforcement"

== Hard rules ==

1. EVIDENCE BEFORE CODE. For any bug-fix task: capture the broken surface's
   actual output (API JSON, DB row, log line, screenshot) FIRST. \`file:line\`
   references describe what code *might* do, not what *happened*. They are
   NOT evidence.

2. DB ACCESS IS AVAILABLE VIA CI/CD. Existing workflows (e.g.,
   \`app-analytics-readonly-evidence.yml\`) can run one-off SQL against
   production. Do not say "I cannot access the DB" — set up a
   workflow_dispatch or use an existing readonly workflow. There is no
   infrastructure excuse for inferring DB state from code.

3. DO NOT SHIP ON HYPOTHESIS. If the 4-step Evidence-First checklist
   (AGENTS.md "Evidence-First Debugging") cannot be completed, STOP and
   report \`BLOCKED: need <X>\`. Never close an issue on a hypothesis.

4. TEST PASSING != BUG FIXED. A test that seeds its own sample matching the
   fix's hypothesis only proves the fix handles its own assumption — not
   that the assumption matches production. Tie at least one test fixture to
   a real captured value.

5. SECOND FAILED ITERATION -> FULL REVERT + RESTART. If the same issue has
   been "fixed" twice and the user still reports the symptom, REVERT all
   prior fixes before attempting a third attempt. Do not patch forward.

6. ORCHESTRATOR DISCIPLINE. When dispatching a subagent via the Agent tool:
   - First dispatch for a bug-fix task is INVESTIGATE ONLY (no code).
   - Subagent prompts MUST include "Read AGENTS.md Evidence-First Debugging
     section before proceeding" or equivalent rule reference.
   - Do NOT pre-bake hypotheses into the prompt ("Hypothesis X is correct,
     fix at file:Y" is an anti-pattern).

== CI enforcement (merged as #1067) ==

GitHub CI rejects any PR whose body omits Root Cause Gate / Business Goal /
Verification Evidence Ledger. \`.github/workflows/pr-body-lint.yml\` is the
gate. No agent (including this one) can bypass at merge time. See
AGENTS.md \`## Enforcement\` for the three-layer model.

== Session-specific context ==

Current branch:      ${BRANCH}
Uncommitted files:   ${CHANGED_COUNT}
Most-recent commit:  ${RECENT_COMMIT}

EOF
