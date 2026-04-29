"""Drift guard between CLAUDE.md body decisions and docs/DECISION_LOG.md index.

Plan J D4 (decision #25 Rule 6 / 2026-04-26): a CLAUDE.md decision body
without a matching DECISION_LOG.md index row (or vice versa) is the
canonical source of stale references. This guard enforces:

  1. The set of decision numbers in CLAUDE.md `^N\\. \\*\\*` body anchors
     equals the set of decision numbers in DECISION_LOG.md `^| N |`
     table rows.
  2. Numbers are monotonic with no gaps in `[1..max]` on either side.

Direct port of `scripts/decision-log-sync-check.mjs` (TS era, deleted in
Session A1' Step 8 .mjs sweep — decision #30.D / CLAUDE.md #29.B).
Behaviour and exit codes are preserved one-to-one.

Exit codes:
  0 — in sync
  1 — drift detected (PR block)
  2 — file missing or unreadable
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
DECISION_LOG = REPO_ROOT / "docs" / "DECISION_LOG.md"

_CLAUDE_RE = re.compile(r"^(\d+)\. \*\*", re.MULTILINE)
_LOG_RE = re.compile(r"^\|\s*(\d+)\s*\|", re.MULTILINE)


def _fail(msg: str, code: int = 1) -> int:
    print(f"[decision-log-sync-check] FAIL: {msg}", file=sys.stderr)
    return code


def _ok(msg: str) -> int:
    print(f"[decision-log-sync-check] OK: {msg}")
    return 0


def main() -> int:
    if not CLAUDE_MD.is_file():
        return _fail(f"CLAUDE.md not found at {CLAUDE_MD}", 2)
    if not DECISION_LOG.is_file():
        return _fail(f"DECISION_LOG.md not found at {DECISION_LOG}", 2)

    claude_text = CLAUDE_MD.read_text(encoding="utf-8")
    log_text = DECISION_LOG.read_text(encoding="utf-8")

    claude_numbers = {int(m.group(1)) for m in _CLAUDE_RE.finditer(claude_text)}
    if not claude_numbers:
        return _fail("No decision anchors `^N\\. \\*\\*` found in CLAUDE.md — wrong file?")

    log_numbers = {int(m.group(1)) for m in _LOG_RE.finditer(log_text)}
    if not log_numbers:
        return _fail("No table rows `| N |` found in DECISION_LOG.md — wrong file?")

    max_claude = max(claude_numbers)
    max_log = max(log_numbers)

    if max_claude != max_log:
        return _fail(
            f"max decision number drift: CLAUDE.md = {max_claude}, "
            f"DECISION_LOG.md = {max_log}. Either a decision body was added "
            "without an index row, or vice versa. Editing rule #1: same PR."
        )

    missing_from_claude = [n for n in range(1, max_claude + 1) if n not in claude_numbers]
    missing_from_log = [n for n in range(1, max_claude + 1) if n not in log_numbers]

    if missing_from_claude or missing_from_log:
        parts: list[str] = []
        if missing_from_claude:
            parts.append(f"missing from CLAUDE.md body: {missing_from_claude}")
        if missing_from_log:
            parts.append(f"missing from DECISION_LOG.md index: {missing_from_log}")
        return _fail(
            f"gap detected — {' / '.join(parts)}. Editing rule #3: numbers are "
            "monotonic, never renumber."
        )

    return _ok(
        f"{max_claude} decisions, fully in sync between CLAUDE.md body "
        "and DECISION_LOG.md index."
    )


if __name__ == "__main__":
    sys.exit(main())
