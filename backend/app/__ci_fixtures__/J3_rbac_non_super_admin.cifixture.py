"""Sentinel: this file deliberately violates J3 by design.

J3 — `require_role(...)` must always be called with the single literal
string `'super_admin'` (decision #24.C2 single-role MVP scope). This
fixture calls it with a non-canonical role.

Used by scripts/ci_harness_selftest.py to verify the rule registry can
detect violations. Do NOT remove or "fix" this file; remove the
corresponding rule first (or accept the harness silently passing on
regressions).
"""

from __future__ import annotations


def require_role(*_args: object) -> object:
    return None


_dependency = require_role("ops_admin")
