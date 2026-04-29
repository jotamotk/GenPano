"""Sentinel: this file deliberately violates J5 by design.

J5 (round 9) — admin code may only write `users.deletion_requested_at`
on the App `User` row. Every other column (email / password_hash /
name_zh / name_en / locale / preferences / email_verified_at /
force_password_change_at) is forbidden; admin moderation lands in
`user_moderation_actions` instead (decision #30.H Path B Variant 2).
This fixture mutates `user.password_hash`, which J5 must surface.

Used by scripts/ci_harness_selftest.py to verify the rule registry can
detect violations. Do NOT remove or "fix" this file; remove the
corresponding rule first (or accept the harness silently passing on
regressions).
"""

from __future__ import annotations


class _User:
    password_hash: str = ""
    email: str = ""


def force_rewrite_password(user: _User) -> None:
    user.password_hash = "$2a$12$evil"
