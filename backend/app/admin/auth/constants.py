"""Admin auth constants.

All TTLs, lengths, algorithms, audiences, issuers, cookie names live here.
Splitting these literals across modules makes the auth surface harder to audit.

References:
- Admin auth constants
- Admin REFRESH_TOKEN_TTL = 7d intentional vs
  user side 30d — security/UX trade-off, NOT shared singleton)
"""

from __future__ import annotations

# JWT lifetimes (seconds)
ACCESS_TOKEN_TTL_SECONDS: int = 900  # 15 min
REFRESH_TOKEN_TTL_SECONDS: int = 604800  # 7 days (Admin-only; user side = 30d)

# Re-auth gate (milliseconds, matches frontend expectation)
REAUTH_WINDOW_MS: int = 30 * 60 * 1000  # 30 min

# Password
BCRYPT_COST: int = 12  # Harness D9 will reject literals < 12 elsewhere
MIN_PASSWORD_LENGTH: int = 12
MIN_ZXCVBN_SCORE: int = 3

# JWT
JWT_ALGORITHM: str = "HS256"
JWT_ISSUER: str = "genpano-admin"
JWT_AUDIENCE_ACCESS: str = "genpano-admin-access"

# Cookies
ACCESS_TOKEN_COOKIE: str = "admin_access_token"
REFRESH_TOKEN_COOKIE: str = "admin_refresh_token"
COOKIE_PATH: str = "/admin"
