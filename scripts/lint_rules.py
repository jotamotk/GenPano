#!/usr/bin/env python3
"""Meta-lint for the rules/ directory.

Enforces structural constraints on rules/*.md so the modular ruleset stays
maintainable and doesn't drift back into the same antipatterns we just refactored
out:

  1. Every rule file (not README, not INCIDENTS, not MAINTENANCE) must carry a
     YAML frontmatter block with the required keys.
  2. No file under rules/ may exceed 200 lines (single-rule-per-file principle).
  3. No rule body may contain a `#<digit-digit-digit-or-four-digit>` PR-number
     reference — those belong in rules/INCIDENTS.md, not rule prose. (See
     rules/MAINTENANCE.md `4.2 War story 隔离`.)

Usage:
  python3 scripts/lint_rules.py rules/
  python3 scripts/lint_rules.py rules/ --quiet

Exit codes:
  0 = clean
  1 = at least one violation
  2 = bad invocation
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_FRONTMATTER_KEYS = (
    "last-reviewed",
    "owner-hat",
    "next-review-by",
    "status",
    "applies-to",
    "hardness",
)

# Files exempt from rule-file constraints (they are indexes / archives / meta).
EXEMPT_FILENAMES = {"README.md", "INCIDENTS.md", "MAINTENANCE.md"}

# PR-number pattern: # followed by 3-4 digits. Matches #905, #1283.
PR_NUMBER_RE = re.compile(r"#\d{3,4}\b")

MAX_LINES = 200


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return frontmatter as {key: raw_value} dict, or None if missing/malformed.

    Frontmatter format:
        ---
        key: value
        key2: value2
        ---
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    block = text[4:end]
    fm: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm


def lint_file(path: Path, display_root: Path) -> list[str]:
    """Return a list of violation strings for this file (empty = pass).

    `display_root` is the directory used to render relative paths in error
    messages. Typically it is the parent of the `root` passed to `lint_tree`,
    so error lines look like `rules/testing/foo.md` rather than absolute paths.
    """
    try:
        rel = path.relative_to(display_root)
    except ValueError:
        rel = path
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    line_count = text.count("\n") + (0 if text.endswith("\n") else 1)

    # Rule 2: line count cap (applies to every file under rules/).
    if line_count > MAX_LINES:
        problems.append(
            f"{rel}: {line_count} lines > {MAX_LINES} (split into subfolder; see MAINTENANCE.md §4.5)"
        )

    is_exempt = path.name in EXEMPT_FILENAMES
    if is_exempt:
        return problems

    # Rule 1: frontmatter required keys.
    fm = parse_frontmatter(text)
    if fm is None:
        problems.append(f"{rel}: missing or malformed YAML frontmatter (need keys: {', '.join(REQUIRED_FRONTMATTER_KEYS)})")
    else:
        missing = [k for k in REQUIRED_FRONTMATTER_KEYS if k not in fm]
        if missing:
            problems.append(f"{rel}: frontmatter missing keys: {', '.join(missing)}")

    # Rule 3: no PR-number references in rule body (war story isolation).
    # Strip frontmatter before scanning.
    if fm is not None:
        end = text.find("\n---\n", 4)
        body = text[end + 5 :] if end != -1 else text
    else:
        body = text
    # Strip markdown links `[text](url)` — the URL portion legitimately contains
    # `INCIDENTS.md#NNN` anchors, and the link-text typically mirrors them.
    # Also strip inline code blocks and fenced code, which may contain template
    # placeholders like `#NNN`.
    body_clean = re.sub(r"\[[^\]\n]*\]\([^)\n]*\)", "", body)
    body_clean = re.sub(r"`[^`\n]*`", "", body_clean)
    body_clean = re.sub(r"```[\s\S]*?```", "", body_clean)
    for match in PR_NUMBER_RE.finditer(body_clean):
        snippet = body_clean[max(0, match.start() - 20) : match.end() + 20].replace("\n", " ")
        problems.append(
            f"{rel}: PR-number reference {match.group(0)!r} in rule body — move to rules/INCIDENTS.md (context: …{snippet}…)"
        )
        # Continue scanning — report every offending reference in one pass so
        # contributors don't fix one and re-trigger CI to discover the next.

    return problems


def lint_tree(root: Path) -> list[str]:
    """Lint every .md file under root recursively, plus the cross-source
    consistency check between rules/security/enforcement.md and the actual
    CI lint script `.github/scripts/lint_pr_body.py`."""
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        sys.exit(2)
    # Display paths relative to root's parent: `rules/testing/foo.md` rather
    # than an absolute or filesystem-root-anchored path.
    display_root = root.parent if root.is_absolute() else Path.cwd()
    all_problems: list[str] = []
    for path in sorted(root.rglob("*.md")):
        all_problems.extend(lint_file(path, display_root))
    all_problems.extend(_check_enforcement_doc_in_sync(root, display_root))
    return all_problems


# Drift-detection between the rule prose and the CI lint constants.
# Without this, lint_pr_body.py can rename REQUIRED_SECTIONS and
# rules/security/enforcement.md silently goes stale — exactly the failure
# mode the modular refactor is meant to prevent. Peer review flagged this
# as the highest-risk regression vector (see PR #1288 review).
LINT_PR_BODY_REL = Path(".github/scripts/lint_pr_body.py")
ENFORCEMENT_REL = Path("rules/security/enforcement.md")


def _check_enforcement_doc_in_sync(rules_root: Path, display_root: Path) -> list[str]:
    """Verify rules/security/enforcement.md mentions every required section
    name that .github/scripts/lint_pr_body.py declares in `REQUIRED_SECTIONS`.
    """
    repo_root = rules_root.parent if rules_root.is_absolute() else (Path.cwd() / rules_root).resolve().parent
    pr_body_lint = repo_root / LINT_PR_BODY_REL
    enforcement_md = repo_root / ENFORCEMENT_REL
    if not pr_body_lint.exists() or not enforcement_md.exists():
        return []  # Tolerate missing files; this check is additive.
    src = pr_body_lint.read_text(encoding="utf-8")
    # Extract every quoted literal assigned to SECTION_* constants.
    section_constants = re.findall(
        r'^SECTION_[A-Z_]+\s*=\s*["\']([^"\']+)["\']', src, re.MULTILINE
    )
    if not section_constants:
        return []  # Constants moved or renamed; can't check.
    doc = enforcement_md.read_text(encoding="utf-8")
    missing = [name for name in section_constants if name not in doc]
    if not missing:
        return []
    try:
        enf_rel = enforcement_md.relative_to(display_root)
    except ValueError:
        enf_rel = enforcement_md
    return [
        f"{enf_rel}: drift vs `.github/scripts/lint_pr_body.py` — required "
        f"section name(s) {missing!r} declared in lint script but not mentioned in enforcement doc"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Path to rules/ directory")
    parser.add_argument("--quiet", action="store_true", help="Print only PASS/FAIL")
    args = parser.parse_args(argv)

    problems = lint_tree(args.root)
    if not problems:
        print("PASS")
        return 0

    if not args.quiet:
        print(f"rules/ lint FAILED. {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        print("")
        print("Fix: see rules/MAINTENANCE.md §4 (反 Context 中毒规则) for the rationale.")
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
