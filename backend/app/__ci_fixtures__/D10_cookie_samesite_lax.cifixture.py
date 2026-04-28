"""Sentinel: this file deliberately violates a rule by design.

Used by scripts/ci_harness_selftest.py to verify the rule registry can detect
violations. Do NOT remove or "fix" this file; remove the corresponding rule
first (or accept that the harness will start silently passing on regressions).
"""


def emit(response: object) -> None:
    response.set_cookie(  # type: ignore[attr-defined]
        key="admin_access_token",
        value="x",
        httponly=True,
        samesite="lax",
        path="/admin",
    )
