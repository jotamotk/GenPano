#!/usr/bin/env python3
"""Lint a GitHub issue body against the agent-task / epic / human templates.

Issue templates use heading-form fields (e.g. `### Business Goal`). This script
detects the type and validates that the fields the template marks
`validations.required: true` are non-empty and non-placeholder.

Issue lint is FEEDBACK ONLY — the workflow comments but does not gate.

Usage:
  python3 lint_issue_body.py --type deliverable < body.md
  python3 lint_issue_body.py --type epic --body-file body.md
  python3 lint_issue_body.py --type human --body-file body.md
  python3 lint_issue_body.py --type auto --labels type:human < body.md  # auto-detect
  python3 lint_issue_body.py --help

Exit codes:
  0 - lint passed
  1 - lint failed (problems printed)
  2 - input/argument error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

# Map issue type -> list of required field headings (as they appear in the
# rendered issue body, which uses `### <label>` from the YAML form template).
# Heading text matches the `attributes.label` from the YAML.
REQUIRED_FIELDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "deliverable": (
        "Priority",
        "Priority Rationale",
        "业务目标 / Business Goal",
        "Path",
        "Owner Hat",
        "Coordination Issue",
        "Technical Deliverable",
        "Parent Business Goal",
        "Current State",
        "Decisions",
        "Execution Contract",
        "PRD Source",
        "Acceptance Matrix",
        "Root Cause Gate",
        "Failure Chain Review",
        "Verification Evidence Ledger",
        "Test Integrity",
    ),
    "epic": (
        "Priority",
        "Priority Rationale",
        "User Need",
        "Business Goal",
        "Current State",
        "Decisions",
        "PRD Source",
        "Acceptance Translation",
        "Frontend Visualization",
        "Success Criteria",
        "Live Verification",
    ),
    "human": (
        "Problem / Goal / Bug",
        "Priority",
    ),
}

PLACEHOLDER_TOKENS = (
    "todo",
    "tbd",
    "placeholder",
    "xxx",
    "...",
    "n/a",
    "pending.",  # The Decisions field's default
)


@dataclass
class IssueLintResult:
    problems: list[str] = field(default_factory=list)
    issue_type: str = "unknown"

    @property
    def ok(self) -> bool:
        return not self.problems

    def add(self, msg: str) -> None:
        self.problems.append(msg)


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")


def _split_h3_sections(body: str) -> dict[str, str]:
    """Issue form bodies use `### <Label>` for each field."""
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_buf: list[str] = []
    for line in body.split("\n"):
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
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


def _is_placeholder_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    bare = stripped.strip("`*_>\"' ").lower()
    if not bare:
        return True
    if bare in PLACEHOLDER_TOKENS:
        return True
    # Check if the whole section is just the template's default boilerplate
    # bullets (no actual content). A line like `- Pending.` or just `- ` is empty.
    non_empty_content_lines = [
        line.strip()
        for line in stripped.split("\n")
        if line.strip() and not _is_template_boilerplate(line.strip())
    ]
    if not non_empty_content_lines:
        return True
    return False


def _is_template_boilerplate(line: str) -> bool:
    """Detect lines that are clearly the template's empty default skeleton."""
    stripped = line.strip()
    if not stripped:
        return True
    # Bare bullet markers or table separators.
    if stripped in ("-", "*", "|", "| --- | --- |"):
        return True
    if re.fullmatch(r"[\-|\s]+", stripped):
        return True
    # Bullet lines whose value is just a label with no content after the colon.
    if re.match(r"^[-*]\s+\w[\w/\s]*:\s*$", stripped):
        return True
    # Lines that are only "- Pending." or "- TODO" etc.
    bare = stripped.lstrip("-*").strip("`*_>\"' ").lower()
    if bare in PLACEHOLDER_TOKENS:
        return True
    return False


def detect_type(body: str, labels: list[str]) -> str:
    """Auto-detect issue type from labels and body markers."""
    label_set = {label.lower() for label in labels}
    if "type:epic" in label_set:
        return "epic"
    if "type:human" in label_set:
        return "human"
    if "type:task" in label_set or "status:ready" in label_set:
        return "deliverable"
    # Body-based fallback: deliverable template has "Technical Deliverable",
    # epic has "User Need", human has "Problem / Goal / Bug".
    if "### Technical Deliverable" in body or "### 业务目标 / Business Goal" in body:
        return "deliverable"
    if "### User Need" in body or "### Acceptance Translation" in body:
        return "epic"
    if "### Problem / Goal / Bug" in body:
        return "human"
    return "unknown"


def lint(body: str, issue_type: str) -> IssueLintResult:
    result = IssueLintResult(issue_type=issue_type)
    body = _normalize(body)
    if not body.strip():
        result.add("Issue body is empty")
        return result

    if issue_type not in REQUIRED_FIELDS_BY_TYPE:
        result.add(
            f"Unknown issue type '{issue_type}' — cannot lint. "
            "Expected one of: deliverable, epic, human."
        )
        return result

    sections = _split_h3_sections(body)
    required = REQUIRED_FIELDS_BY_TYPE[issue_type]

    for fname in required:
        if fname not in sections:
            result.add(f"Missing field: `### {fname}`")
            continue
        if _is_placeholder_value(sections[fname]):
            result.add(f"Field `### {fname}` is empty or placeholder-only")

    return result


def _read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        try:
            with open(args.body_file, encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            print(f"ERROR: cannot read --body-file: {exc}", file=sys.stderr)
            sys.exit(2)
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint a GitHub issue body for required fields based on its template type.",
    )
    parser.add_argument(
        "--type",
        choices=("deliverable", "epic", "human", "auto", "unknown"),
        default="auto",
        help="Issue type. 'auto' uses --labels and body markers to detect.",
    )
    parser.add_argument(
        "--labels",
        default="",
        help="Comma-separated label list for auto-detection (e.g. 'type:human,priority:p2').",
    )
    parser.add_argument(
        "--body-file",
        help="Path to a file containing the issue body. If omitted, reads stdin.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-problem lines; print only PASS or FAIL.",
    )
    args = parser.parse_args(argv)

    body = _read_body(args)
    labels = [label.strip() for label in args.labels.split(",") if label.strip()]

    issue_type = args.type
    if issue_type == "auto":
        issue_type = detect_type(body, labels)
        if issue_type == "unknown":
            print(
                "Could not detect issue type from labels/body. Skipping lint. "
                "(Pass --type explicitly to force.)"
            )
            print("PASS")
            return 0

    result = lint(body, issue_type)

    if result.ok:
        print(f"Issue type detected: {issue_type}")
        print("PASS")
        return 0

    if not args.quiet:
        print(f"Issue type detected: {issue_type}")
        print("Issue body lint FAILED. Problems:")
        for problem in result.problems:
            print(f"  - {problem}")
        print("")
        print(
            "Fill in the missing fields. This is feedback only — the issue is not "
            "blocked, but agents using it as a contract should treat empty fields as a gap."
        )
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
