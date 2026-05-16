#!/usr/bin/env bash
# PreToolUse hook: enforce subagent-prompt discipline on the Agent tool.
#
# Wiring choice:
#   This is a thin bash wrapper that reads the PreToolUse JSON envelope from
#   stdin and pipes it to the Python validator in ./lib/check_agent_prompt.py.
#   We chose bash-wrapper + Python lib (over a single python3 invocation in
#   settings.json) for two reasons:
#     1. The shebang + executable bit gives us a single stable command path
#        regardless of which python3 is in $PATH at session start.
#     2. The wrapper guards against missing python3 with a graceful fall-back
#        to "allow" — never want this hook to block the Agent tool because
#        the user's machine lacks an interpreter.
#
# Contract: see AGENTS.md section "Enforcement", Layer 3 (agent-specific
# automation). Closes the leader -> subagent inheritance gap noted in the
# #1029 retrospective.

set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$HOOK_DIR/lib/check_agent_prompt.py"

if ! command -v python3 >/dev/null 2>&1; then
  # Graceful degrade: allow the call. CI's pr-body-lint still gates merges.
  exit 0
fi

if [ ! -f "$VALIDATOR" ]; then
  # Validator missing — fail open. The hook should never be the only thing
  # standing between a developer and progress; CI lints catch the actual PR.
  exit 0
fi

# Pipe the PreToolUse JSON envelope straight through to the validator.
# The validator writes its hook-response JSON (or nothing, for non-Agent tools)
# to stdout and exits 0 in both allow and deny paths — exit code is reserved
# for hook-runtime errors only.
exec python3 "$VALIDATOR"
