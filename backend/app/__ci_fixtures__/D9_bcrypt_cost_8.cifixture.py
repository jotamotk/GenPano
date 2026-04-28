"""Sentinel: this file deliberately violates a rule by design.

Used by scripts/ci_harness_selftest.py to verify the rule registry can detect
violations. Do NOT remove or "fix" this file; remove the corresponding rule
first (or accept that the harness will start silently passing on regressions).
"""

import bcrypt

_salt = bcrypt.gensalt(rounds=8)
_hash = bcrypt.hashpw(b"never-use-this", _salt)
