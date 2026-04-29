"""Sentinel: this file deliberately violates J4 by design.

J4 — admin response models must never expose `.cookies` directly; the
cookie payload must be routed through `mask_secret(...)` before crossing
the API boundary. This fixture returns the raw attribute, which J4 must
surface.

Used by scripts/ci_harness_selftest.py to verify the rule registry can
detect violations. Do NOT remove or "fix" this file; remove the
corresponding rule first (or accept the harness silently passing on
regressions).
"""

from __future__ import annotations


class _Account:
    cookies = "raw-cookie-jar-bytes"


def get_account_cookies(account: _Account) -> dict[str, object]:
    return {"id": "acc-1", "cookies": account.cookies}
