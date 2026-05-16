#!/usr/bin/env python3
"""Self-tests for ``check_agent_prompt.py``.

Run with: ``python3 test_check_agent_prompt.py``

The tests build PreToolUse envelopes that mirror what Claude Code passes on
stdin (per https://code.claude.com/docs/en/hooks) and assert the validator's
allow/deny decision plus reason fragments. Five fixtures cover the test
matrix specified in the PR brief.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "check_agent_prompt.py"


def run_validator(envelope: dict) -> tuple[int, str]:
    """Invoke the validator as a subprocess, returning (exit_code, stdout)."""
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"validator exited {proc.returncode}, stderr=\n{proc.stderr}"
        )
    return proc.returncode, proc.stdout


def agent_envelope(prompt: str) -> dict:
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/test-transcript.jsonl",
        "cwd": str(HERE),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {
            "description": "test dispatch",
            "prompt": prompt,
            "subagent_type": "general-purpose",
        },
        "tool_use_id": "tool_test",
    }


def parse_decision(stdout: str) -> dict | None:
    stdout = stdout.strip()
    if not stdout:
        return None
    return json.loads(stdout)


class ValidatorTests(unittest.TestCase):
    # ---- Fixture 1: rule-marker present -> allow ------------------------

    def test_1_rule_marker_allows(self):
        envelope = agent_envelope(
            "Investigate the bug per AGENTS.md Evidence-First section. "
            "Capture the live response from the broken surface before "
            "proposing a fix."
        )
        _, out = run_validator(envelope)
        self.assertIsNone(
            parse_decision(out),
            f"Expected implicit allow (empty stdout), got: {out!r}",
        )

    # ---- Fixture 2: no markers, no anti-pattern -> deny -----------------

    def test_2_missing_markers_denies(self):
        envelope = agent_envelope("Just fix the function in main.py")
        _, out = run_validator(envelope)
        decision = parse_decision(out)
        self.assertIsNotNone(decision)
        hsout = decision["hookSpecificOutput"]
        self.assertEqual(hsout["hookEventName"], "PreToolUse")
        self.assertEqual(hsout["permissionDecision"], "deny")
        self.assertIn("rule-reference marker", hsout["permissionDecisionReason"])
        self.assertIn("AGENTS.md", hsout["permissionDecisionReason"])

    # ---- Fixture 3: anti-pattern + missing markers -> deny --------------

    def test_3_antipattern_denies(self):
        envelope = agent_envelope(
            "Hypothesis B is correct, fix at _topic_service.py:572"
        )
        _, out = run_validator(envelope)
        decision = parse_decision(out)
        self.assertIsNotNone(decision)
        hsout = decision["hookSpecificOutput"]
        self.assertEqual(hsout["permissionDecision"], "deny")
        reason = hsout["permissionDecisionReason"]
        # The anti-pattern reason should win, listing both hits.
        self.assertIn("anti-pattern detected", reason)
        self.assertIn("Pre-baked hypothesis", reason)
        self.assertIn("Pre-baked fix location", reason)
        self.assertIn("Allow pre-baked hypothesis", reason)

    # ---- Fixture 4: anti-pattern + escape hatch -> allow ----------------

    def test_4_escape_hatch_allows(self):
        # Matches the PR brief's exact fixture: anti-pattern present, no
        # rule markers, but the explicit escape hatch token + >=20-char
        # justification bypasses both checks.
        envelope = agent_envelope(
            "Hypothesis B is correct... Allow pre-baked hypothesis: "
            "orchestrator confirmed via independent DB readback already"
        )
        _, out = run_validator(envelope)
        self.assertIsNone(
            parse_decision(out),
            f"Expected implicit allow via escape hatch, got: {out!r}",
        )

    # ---- Fixture 5: non-Agent tool -> allow (hook ignores) --------------

    def test_5_non_agent_tool_ignored(self):
        envelope = {
            "session_id": "test-session",
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/etc/hosts"},
            "tool_use_id": "tool_test",
        }
        _, out = run_validator(envelope)
        self.assertIsNone(
            parse_decision(out),
            f"Expected implicit allow (non-Agent tool), got: {out!r}",
        )

    # ---- Extra safety net: escape hatch reason must be >= 20 chars ------

    def test_6_short_escape_reason_still_denies(self):
        envelope = agent_envelope(
            "Hypothesis A is correct. Allow pre-baked hypothesis: short"
        )
        _, out = run_validator(envelope)
        decision = parse_decision(out)
        self.assertIsNotNone(
            decision,
            "Escape hatch must require >= 20 chars of justification.",
        )

    # ---- Extra safety net: marker without anti-pattern still allows -----

    def test_7_chinese_marker_allows(self):
        envelope = agent_envelope(
            "根据证据优先原则调查 /products 接口的真实响应，先抓 live response。"
        )
        _, out = run_validator(envelope)
        self.assertIsNone(
            parse_decision(out),
            f"Expected allow with Chinese rule marker, got: {out!r}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
