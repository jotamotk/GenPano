"""Re-authentication gate for sensitive ops (change-password, MFA setup).

Decision #24.B contract: a session is "fresh enough" for sensitive ops only
if the underlying password was successfully entered within
`REAUTH_WINDOW_MS` (30 min by default). The check is purely time-based; it
does not invalidate the access token.

Three outcomes:
- `allowed=True`  → caller may proceed
- `allowed=False, reason='stale'` → caller must re-prompt for password
- `allowed=False, reason='never_authenticated'` → caller is misconfigured
  (no `last_password_at` row) — defensive branch; production rows always set
  this on first login per Step 5 endpoints

Clock skew: a `last_password_at` in the future (clock jitter) is treated as
`allowed`, never as a fault, because the only meaningful failure mode here
is "stale" — refusing to grant access on a non-monotonic clock would be a
worse UX than briefly trusting a future timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.admin.auth.constants import REAUTH_WINDOW_MS

ReauthReason = Literal["stale", "never_authenticated"]


@dataclass(frozen=True)
class ReauthDecision:
    allowed: bool
    reason: ReauthReason | None = None


def evaluate_reauth(
    *,
    last_password_at: datetime | None,
    now: datetime | None = None,
    max_age_ms: int = REAUTH_WINDOW_MS,
) -> ReauthDecision:
    if last_password_at is None:
        return ReauthDecision(allowed=False, reason="never_authenticated")

    current = now if now is not None else datetime.now(UTC)

    # Normalise both timestamps to aware UTC for comparison. Naive datetimes
    # arriving from sqlite are interpreted as UTC (matches admin.py model).
    if last_password_at.tzinfo is None:
        last_password_at = last_password_at.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)

    delta_ms = (current - last_password_at).total_seconds() * 1000.0

    # Future timestamp (clock skew) → allow rather than reject.
    if delta_ms < 0:
        return ReauthDecision(allowed=True, reason=None)

    if delta_ms > max_age_ms:
        return ReauthDecision(allowed=False, reason="stale")

    return ReauthDecision(allowed=True, reason=None)


def require_recent_auth(
    *,
    last_password_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Bool alias for callers that don't need the failure reason."""

    return evaluate_reauth(last_password_at=last_password_at, now=now).allowed
