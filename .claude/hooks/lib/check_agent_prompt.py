#!/usr/bin/env python3
"""PreToolUse validator for the Agent tool.

Reads a Claude Code PreToolUse JSON envelope on stdin; for ``tool_name ==
"Agent"`` validates ``tool_input.prompt`` against the subagent-prompt
discipline rules captured in AGENTS.md section "Enforcement", Layer 3, and
emits a hook-response JSON on stdout. For any other tool, prints nothing
and exits 0 (implicit allow). Invoked from ``../agent-dispatch-precheck.sh``;
pure stdlib so the hook does not depend on a venv. Closes the leader ->
subagent inheritance gap surfaced in the #1029 retrospective.

Decision protocol (https://code.claude.com/docs/en/hooks): exit is always 0;
allow = empty stdout, deny = JSON with hookSpecificOutput.permissionDecision.
"""

from __future__ import annotations

import json
import re
import sys

# Rule-reference markers (case-insensitive substring). At least one must
# appear in the prompt so the subagent receives an explicit pointer to the
# discipline rules — SessionStart injection only covers the leader.
RULE_MARKERS: tuple[str, ...] = (
    "agents.md",
    "evidence-first",
    "evidence first",
    "证据优先",
    "root cause gate",
    "根因",
    "business goal",
    "业务目标",
)

# Anti-patterns. The exact phrases that surfaced in the failed #1034 / #1041
# / #1052 dispatches called out in the #1029 retrospective. Any match (case-
# insensitive) denies the dispatch with a pointed reason.
ANTIPATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"hypothesis\s+[a-z]\s+is\s+correct",
        "Pre-baked hypothesis (\"Hypothesis X is correct\") shipped as fact. "
        "AGENTS.md Evidence-First Debugging requires the subagent to gather "
        "real response/output evidence before naming a cause. Strip the "
        "hypothesis from the prompt, or use the escape hatch (see below).",
    ),
    (
        r"root\s+cause\s+already\s+diagnosed",
        "\"Root cause already diagnosed\" presented as fact. AGENTS.md "
        "Root Cause Gate requires the subagent to verify, with evidence, "
        "that the cause-and-effect chain holds. Reframe as a question for "
        "the subagent to confirm, or use the escape hatch.",
    ),
    (
        # "Fix at file:line" — pre-baking the exact line of the fix.
        r"fix\s+at\s+[A-Za-z0-9_./\\-]+(?:\.[A-Za-z0-9]+)?:\d+",
        "Pre-baked fix location (\"Fix at file:line\"). AGENTS.md "
        "Evidence-First Debugging requires the subagent to grep callers and "
        "read the live code path before applying a fix. Ask the subagent to "
        "investigate, or use the escape hatch.",
    ),
    (
        r"verify,\s*don'?t\s+re-?diagnose",
        "\"Verify, don't re-diagnose\" instructs the subagent to skip "
        "diagnosis. Exact anti-pattern from the #1029 retrospective: the "
        "leader assumed correlation = causation and the subagent inherited "
        "the wrong frame. Either ask the subagent to re-diagnose, or use "
        "the escape hatch.",
    ),
)

# Escape hatch: literal token + >=20-char justification bypasses all checks.
# The 20-char floor forces the orchestrator to write a real reason.
ESCAPE_HATCH_RE = re.compile(
    r"allow\s+pre-?baked\s+hypothesis\s*:\s*(.{20,})",
    flags=re.IGNORECASE,
)


MISSING_MARKERS_REASON = (
    "Agent dispatch prompt is missing every required rule-reference marker. "
    "AGENTS.md section Enforcement, Layer 3, requires the orchestrator to "
    "include at least one of: AGENTS.md, Evidence-First, Root Cause Gate, "
    "Business Goal. Subagents do not auto-inherit the SessionStart system "
    "reminder; without an explicit reference the subagent will not know "
    "which contract it is operating under. Add a rule reference to the prompt."
)

ESCAPE_HATCH_HINT = (
    "\n\nEscape hatch (use deliberately): include the literal string "
    "'Allow pre-baked hypothesis: <reason longer than 20 characters>' in "
    "the prompt when independent investigation has already established the "
    "cause and the subagent is dispatched for execution only."
)


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _antipattern_reasons(prompt: str) -> list[str]:
    return [
        message
        for pattern, message in ANTIPATTERNS
        if re.search(pattern, prompt, flags=re.IGNORECASE)
    ]


def _has_rule_marker(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(marker in lowered for marker in RULE_MARKERS)


def validate(envelope: dict) -> dict | None:
    """Return a deny-response dict, or None for implicit allow."""
    if envelope.get("tool_name") != "Agent":
        # Hook is scoped via settings.json matcher; defensive allow otherwise.
        return None

    tool_input = envelope.get("tool_input") or {}
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return _deny(
            "Agent dispatch is missing tool_input.prompt. The orchestrator "
            "must always pass an explicit prompt to the subagent — see "
            "AGENTS.md section Enforcement, Layer 3."
        )

    # Escape hatch overrides all other checks. The 20-char floor forces a
    # real justification rather than a reflexive token.
    if ESCAPE_HATCH_RE.search(prompt):
        return None

    hits = _antipattern_reasons(prompt)
    if hits:
        return _deny(
            "Agent dispatch denied: orchestrator anti-pattern detected."
            + "\n  - " + "\n  - ".join(hits)
            + ESCAPE_HATCH_HINT
        )

    if not _has_rule_marker(prompt):
        return _deny(MISSING_MARKERS_REASON)

    return None


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        # Malformed envelope: fail open. The hook must never itself become
        # the bug — CI's pr-body-lint still gates merges.
        return 0

    decision = validate(envelope)
    if decision is None:
        return 0
    json.dump(decision, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
