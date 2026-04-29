"""Sentinel: this file deliberately violates J2 by design.

J2 — the admin layer must NOT redefine the account-pool / auto-register
/ cookie-encryption surface; those names live exclusively under
`app/accounts/` (decision #28.A Platform Layer boundary). This fixture
defines `auto_register` + `class CookieEncoder` outside that home,
which J2 must surface.

Used by scripts/ci_harness_selftest.py to verify the rule registry can
detect violations. Do NOT remove or "fix" this file; remove the
corresponding rule first (or accept the harness silently passing on
regressions).
"""

from __future__ import annotations


def auto_register(_phone_number: str) -> dict[str, str]:
    return {"status": "registered"}


class CookieEncoder:
    def encrypt(self, _value: str) -> bytes:
        return b"ciphertext"
