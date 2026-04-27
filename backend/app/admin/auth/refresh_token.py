"""Opaque refresh token primitives (NOT JWT — server-side rotation only).

Refresh tokens are 32-byte url-safe randoms; only the SHA-256 hex of the
token ever lands in `admin_sessions.refresh_token_hash`. The plaintext
travels exactly twice: once back to the browser inside the HttpOnly cookie
on /refresh, once forward as the cookie on the next /refresh attempt.

`constant_time_equal_hex` is the only safe way to compare two refresh-token
hashes — short-circuits length mismatch before the timing-safe compare so
length doesn't leak. Malformed hex (odd length, non-hex chars) returns False
without raising.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from hashlib import sha256

_TOKEN_BYTES = 32  # 32 random bytes → 43-char base64url string


@dataclass(frozen=True)
class GeneratedRefreshToken:
    token: str  # url-safe base64; sent to browser, NEVER stored
    hash_hex: str  # sha256 hex; stored in admin_sessions.refresh_token_hash


def generate_refresh_token() -> GeneratedRefreshToken:
    """Mint a fresh refresh token + its sha256 hex digest."""

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    digest = sha256(token.encode("utf-8")).hexdigest()
    return GeneratedRefreshToken(token=token, hash_hex=digest)


def hash_refresh_token(token: str) -> str:
    """Compute the canonical sha256 hex digest used for DB lookup."""

    return sha256(token.encode("utf-8")).hexdigest()


def constant_time_equal_hex(a: str, b: str) -> bool:
    """Constant-time hex compare with safe short-circuits.

    - Length-mismatch returns False before the compare (length itself never
      reached `hmac.compare_digest`).
    - Non-hex / odd-length inputs return False (caught via `bytes.fromhex`).
    - Equal-length valid hex routes to `hmac.compare_digest` for the actual
      timing-safe comparison on the decoded bytes.
    """

    if len(a) != len(b):
        return False
    try:
        a_bytes = bytes.fromhex(a)
        b_bytes = bytes.fromhex(b)
    except ValueError:
        return False
    return hmac.compare_digest(a_bytes, b_bytes)
