"""GENPANO L1 Harness selftest: every rule must catch its own fixture.

Per CLAUDE.md #21.C (TS era, inherited): a rule registry without self-seeded
fixtures rots silently — the day you accidentally weaken a regex or AST
matcher, no test fails because the only thing watching the rule is whatever
real-world violation might appear in CI logs months later. Fixture-driven
selftest is the protection.

EXPECTED_POSITIVES is the contract: each rule_id maps to the minimum number
of violations it must surface against backend/app/__ci_fixtures__/. Falling
below the count = rule is broken (or fixture deleted) = exit non-zero.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from ci_check import ALL_RULES, iter_python_files  # noqa: E402

EXPECTED_POSITIVES: dict[str, int] = {
    "F1": 1,
    "F4-1": 1,
    "F4-2": 1,
    "F4-3": 1,
    "D8": 1,
    "D9": 1,
    "D10": 1,
}


def main() -> int:
    backend_root = _HERE.parent
    files = [
        p
        for p in iter_python_files(backend_root, ["app"], include_fixtures=True)
        if "__ci_fixtures__" in p.parts
    ]

    if not files:
        print("● selftest: FAIL — no fixture files found under app/__ci_fixtures__/")
        return 1

    counts: Counter[str] = Counter()
    for rule in ALL_RULES:
        for v in rule.scan(files):  # type: ignore[attr-defined]
            counts[v.rule_id] += 1

    expected_total = sum(EXPECTED_POSITIVES.values())
    met = 0
    failures: list[str] = []
    for rule_id, expected in EXPECTED_POSITIVES.items():
        got = counts.get(rule_id, 0)
        if got >= expected:
            met += expected
        else:
            failures.append(f"  - {rule_id}: expected ≥ {expected} fixture violation(s), got {got}")

    if failures:
        print("● selftest: FAIL")
        for line in failures:
            print(line)
        print(f"  ({met} / {expected_total} fixture expectations met)")
        return 1

    print(
        f"● selftest: PASS ({met} / {expected_total} fixture expectations met "
        f"across {len(files)} fixture file(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
