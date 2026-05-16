#!/usr/bin/env python3
"""Lint a Pull Request body against the contract in AGENTS.md.

The PR body MUST contain three sections:
  - ## Linked Work        (with Business Goal: and Final Success Evidence:)
  - ## Root Cause Gate    (with Direct trigger, Underlying ... root cause, Evidence proving it)
  - ## Verification Evidence Ledger (with at least one - [x] and one https:// URL)

Escape hatches:
  - "Classification: not an incident" under Root Cause Gate makes its rest optional.
  - "<section> N/A: <reason>" with reason > 10 chars accepts any section.

Placeholder text (TODO/TBD/PLACEHOLDER/xxx/...) is rejected as if the field were empty.

Usage:
  python3 lint_pr_body.py              # read PR body on stdin
  python3 lint_pr_body.py --body-file path/to/body.md
  python3 lint_pr_body.py --help

Exit codes:
  0 - lint passed
  1 - lint failed (problems printed to stdout, one per line, last line is "FAIL")
  2 - input/argument error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

# Section headers we require, in order. Match exactly the `## ` form.
SECTION_LINKED_WORK = "Linked Work"
SECTION_ROOT_CAUSE = "Root Cause Gate"
SECTION_LEDGER = "Verification Evidence Ledger"

REQUIRED_SECTIONS = (SECTION_LINKED_WORK, SECTION_ROOT_CAUSE, SECTION_LEDGER)

# Field name -> section it must live under. Case-sensitive on the field name to
# match the template; the value must be non-empty and not a placeholder.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    SECTION_LINKED_WORK: ("Business Goal", "Final Success Evidence"),
    SECTION_ROOT_CAUSE: (
        "Direct trigger",
        "Underlying product/system root cause",
        "Evidence proving it",
    ),
}

# Strings that count as "the agent left the placeholder in" — case-insensitive.
PLACEHOLDER_TOKENS = (
    "todo",
    "tbd",
    "placeholder",
    "xxx",
    "...",
    "<reason>",
    "<url/route>",
    "<route>",
    "<action>",
    "<visible result>",
    "<某个动作>",
    "<肉眼可见的结果>",
    "fill in",
    "to be filled",
    "n/a",  # bare "N/A" without reason is not a real escape hatch
)

# Specific Chinese template stub from the issue template's Business Goal example.
# If the agent copy-pasted it verbatim without changing the angle-bracket bits,
# it's a placeholder.
TEMPLATE_STUB_PATTERNS = (
    re.compile(r"用户在\s*`?http://116\.62\.36\.173/<route>`?", re.UNICODE),
    re.compile(r"<某个动作>后[，,]\s*<肉眼可见的结果>", re.UNICODE),
)


@dataclass
class LintResult:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def add(self, msg: str) -> None:
        self.problems.append(msg)


def _strip_html_comments(text: str) -> str:
    """Remove HTML comments so commented-out template hints don't trip placeholder
    detection."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _normalize(text: str) -> str:
    # Normalize CRLF and strip BOM.
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")


def _split_sections(body: str) -> dict[str, str]:
    """Split a markdown body on `## ` headers. Returns {section_name: body_text}.

    section_name is the exact heading text (without the `## ` prefix and trimmed).
    Body text excludes the heading line itself.
    """
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_buf: list[str] = []
    for line in body.split("\n"):
        # Accept "## Foo" but not "### Foo" (we only care about top-level PR sections).
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            if current_name is not None:
                sections[current_name] = "\n".join(current_buf).strip("\n")
            current_name = m.group(1).strip()
            current_buf = []
        else:
            if current_name is not None:
                current_buf.append(line)
    if current_name is not None:
        sections[current_name] = "\n".join(current_buf).strip("\n")
    return sections


def _is_placeholder(value: str) -> bool:
    """Return True if the value is empty or matches a placeholder pattern."""
    stripped = value.strip()
    if not stripped:
        return True
    # Strip surrounding markdown emphasis/quotes/backticks for the token check.
    bare = stripped.strip("`*_>\"' ").lower()
    if not bare:
        return True
    if bare in PLACEHOLDER_TOKENS:
        return True
    # Also reject things that are *only* a placeholder token + punctuation.
    if re.fullmatch(r"[\s.,;:\-_*`>'\"]*", bare):
        return True
    for pattern in TEMPLATE_STUB_PATTERNS:
        if pattern.search(stripped):
            return True
    return False


def _extract_field(section_body: str, field_name: str) -> str | None:
    """Find a line of the form `Field Name: value` (optionally bullet/checkbox-led).

    Multi-line values are supported — we capture from the colon until the next
    line that looks like another field or a blank line followed by a non-indented
    line. For our simple needs, we just take the rest of the same line plus
    immediately-following indented continuation lines.

    Returns the value string, or None if the field is not present at all.
    """
    # Allow optional leading "- ", "* ", "- [ ]", "- [x]" markdown bullets/checkboxes.
    # Field name is matched case-insensitively to be lenient on agent style.
    field_re = re.compile(
        r"^[\-*]?\s*(?:\[[x ]\]\s*)?"  # bullet / checkbox lead
        + re.escape(field_name)
        + r"\s*:\s*(.*)$",
        re.IGNORECASE,
    )
    lines = section_body.split("\n")
    for i, line in enumerate(lines):
        m = field_re.match(line)
        if not m:
            continue
        value = m.group(1).rstrip()
        # Collect indented continuation lines.
        j = i + 1
        continuation: list[str] = []
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                break
            if re.match(r"^\s{2,}", nxt):  # indented continuation
                continuation.append(nxt.strip())
                j += 1
                continue
            break
        if continuation:
            value = (value + " " + " ".join(continuation)).strip()
        return value
    return None


def _section_na_escape(section_body: str, section_name: str) -> str | None:
    """If the section starts with '<section> N/A: <reason>' return the reason."""
    # Look for a line like `Linked Work N/A: ...` or `## N/A: ...`-style.
    pattern = re.compile(
        rf"^\s*(?:{re.escape(section_name)}\s+)?N/?A\s*:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    for m in pattern.finditer(section_body):
        reason = m.group(1).strip()
        if len(reason) > 10 and not _is_placeholder(reason):
            return reason
    return None


def _root_cause_not_incident(section_body: str) -> str | None:
    """Return the classification reason if Root Cause Gate is marked 'not an incident'.

    Must NOT match the bare template line that lists all three options separated by `|`:
      `Classification: incident fix | diagnostics/instrumentation only | not an incident`
    That line is the template stub, not a chosen value.
    """
    classification = _extract_field(section_body, "Classification")
    if classification is None:
        return None
    stripped = classification.strip()
    if not stripped:
        return None
    lower = stripped.lower()
    # Reject the bare template stub: it lists multiple options separated by `|`.
    if "|" in stripped:
        return None
    if "not an incident" not in lower:
        return None
    return stripped


def _validate_ledger(section_body: str, result: LintResult) -> None:
    """The Verification Evidence Ledger needs at least one - [x] and one https:// URL."""
    # Strip code-fenced backticks for the URL search so escaped URLs still count.
    has_checked = bool(re.search(r"^\s*[-*]\s*\[[xX]\]\s+\S", section_body, re.MULTILINE))
    has_url = bool(re.search(r"https?://\S+", section_body))
    if not has_checked:
        result.add(
            "## Verification Evidence Ledger has no checked items (need at least one `- [x] ...`)"
        )
    if not has_url:
        result.add(
            "## Verification Evidence Ledger has no URLs (need at least one https:// link as evidence)"
        )


def lint(body: str) -> LintResult:
    result = LintResult()
    body = _normalize(_strip_html_comments(body))
    if not body.strip():
        result.add("PR body is empty")
        return result

    sections = _split_sections(body)

    for required in REQUIRED_SECTIONS:
        if required not in sections:
            result.add(f"Missing required section: `## {required}`")

    # Linked Work fields
    if SECTION_LINKED_WORK in sections:
        section_body = sections[SECTION_LINKED_WORK]
        na_reason = _section_na_escape(section_body, SECTION_LINKED_WORK)
        if na_reason is None:
            for fname in REQUIRED_FIELDS[SECTION_LINKED_WORK]:
                value = _extract_field(section_body, fname)
                if value is None:
                    result.add(f"## {SECTION_LINKED_WORK} missing field: `{fname}:`")
                elif _is_placeholder(value):
                    result.add(
                        f"## {SECTION_LINKED_WORK} field `{fname}:` is empty or a placeholder "
                        f"(got: {value!r})"
                    )

    # Root Cause Gate fields (with not-an-incident escape hatch)
    if SECTION_ROOT_CAUSE in sections:
        section_body = sections[SECTION_ROOT_CAUSE]
        na_reason = _section_na_escape(section_body, SECTION_ROOT_CAUSE)
        not_incident = _root_cause_not_incident(section_body)
        if na_reason is None and not_incident is None:
            for fname in REQUIRED_FIELDS[SECTION_ROOT_CAUSE]:
                value = _extract_field(section_body, fname)
                if value is None:
                    result.add(f"## {SECTION_ROOT_CAUSE} missing field: `{fname}:`")
                elif _is_placeholder(value):
                    result.add(
                        f"## {SECTION_ROOT_CAUSE} field `{fname}:` is empty or a placeholder "
                        f"(got: {value!r})"
                    )

    # Verification Evidence Ledger contents
    if SECTION_LEDGER in sections:
        section_body = sections[SECTION_LEDGER]
        na_reason = _section_na_escape(section_body, SECTION_LEDGER)
        if na_reason is None:
            _validate_ledger(section_body, result)

    return result


def _read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        try:
            with open(args.body_file, encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            print(f"ERROR: cannot read --body-file: {exc}", file=sys.stderr)
            sys.exit(2)
    # stdin
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint a PR body for the AGENTS.md contract sections (Linked Work, "
        "Root Cause Gate, Verification Evidence Ledger).",
    )
    parser.add_argument(
        "--body-file",
        help="Path to a file containing the PR body. If omitted, reads stdin.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-problem lines; print only PASS or FAIL.",
    )
    args = parser.parse_args(argv)

    body = _read_body(args)
    result = lint(body)

    if result.ok:
        print("PASS")
        return 0

    if not args.quiet:
        print("PR body lint FAILED. Problems:")
        for problem in result.problems:
            print(f"  - {problem}")
        print("")
        print(
            "Fix the PR body to include the required sections and fields. See "
            "AGENTS.md and .github/PULL_REQUEST_TEMPLATE.md."
        )
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
