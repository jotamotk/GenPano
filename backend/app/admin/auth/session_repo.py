"""SQLAlchemy async repository for `admin_sessions`.

Decision #24.B mandate: refresh-token rotation MUST mark the old session
row `revoked_at = now()` BEFORE the new row is inserted, in the same
transaction. A replayed old refresh token after rotation must therefore
return 401, not silently succeed.

Layered over `AsyncSession` rather than a free function so endpoint
handlers and the integration tests share one code path. The repository
itself stores nothing — it is a thin adapter that the endpoint layer
injects via dependency.

Coverage exclusion (decision #24.F): this module is excluded from the
unit-test coverage gate because it requires a live SQLAlchemy session.
The L3 endpoint replay tests in Step 5 cover its real behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth.constants import (
    ACCESS_TOKEN_TTL_SECONDS,
    REFRESH_TOKEN_TTL_SECONDS,
)
from app.admin.auth.refresh_token import (
    GeneratedRefreshToken,
    constant_time_equal_hex,
    generate_refresh_token,
)
from app.models.admin import AdminSession


def _naive_utc(now: datetime | None = None) -> datetime:
    """Return a naive UTC datetime — admin_sessions columns are timezone=False
    (matches AdminUser convention; see `app/models/admin.py` docstring)."""

    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is not None:
        current = current.astimezone(UTC).replace(tzinfo=None)
    return current


async def create_session(
    db: AsyncSession,
    *,
    admin_user_id: str,
    access_token_jti: str,
    ip_address: str | None,
    user_agent: str | None,
    now: datetime | None = None,
) -> tuple[AdminSession, GeneratedRefreshToken]:
    """Persist a new admin_sessions row + return the plaintext refresh token.

    Caller (login endpoint) gets back the row plus the *plaintext* refresh
    token so it can be set as a Set-Cookie. The DB only stores the sha256
    hash.
    """

    issued_at = _naive_utc(now)
    access_expires_at = issued_at + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)
    refresh_expires_at = issued_at + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)

    refresh = generate_refresh_token()

    row = AdminSession(
        admin_user_id=admin_user_id,
        access_token_jti=access_token_jti,
        refresh_token_hash=refresh.hash_hex,
        ip_address=ip_address,
        user_agent=user_agent,
        issued_at=issued_at,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )
    db.add(row)
    await db.flush()
    return row, refresh


async def find_active_by_refresh_token(
    db: AsyncSession,
    refresh_token_hash: str,
    *,
    now: datetime | None = None,
) -> AdminSession | None:
    """Look up a non-revoked session by hashed refresh token.

    Constant-time hash comparison is delegated to the row-level guard in
    `constant_time_equal_hex` — the SQL `=` is used only as an indexed
    selector. Replayed (revoked) tokens return None so the endpoint maps
    to 401 cleanly.
    """

    current = _naive_utc(now)
    stmt = select(AdminSession).where(
        AdminSession.refresh_token_hash == refresh_token_hash,
        AdminSession.revoked_at.is_(None),
        AdminSession.refresh_expires_at > current,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    # Defensive: re-check with constant-time comparison even though we
    # selected by exact match. Cheap, and protects against future code
    # paths that might pass a near-collision string.
    if not constant_time_equal_hex(row.refresh_token_hash, refresh_token_hash):
        return None
    return row


async def rotate_session(
    db: AsyncSession,
    *,
    old: AdminSession,
    new_access_token_jti: str,
    ip_address: str | None,
    user_agent: str | None,
    now: datetime | None = None,
) -> tuple[AdminSession, GeneratedRefreshToken]:
    """Atomic rotation: revoke old + create new in the same transaction.

    Returns the new row + the plaintext refresh token. The endpoint must
    `await db.commit()` after this call to make the rotation durable.
    """

    rotated_at = _naive_utc(now)
    old.revoked_at = rotated_at

    new_row, new_refresh = await create_session(
        db,
        admin_user_id=old.admin_user_id,
        access_token_jti=new_access_token_jti,
        ip_address=ip_address,
        user_agent=user_agent,
        now=rotated_at,
    )
    return new_row, new_refresh


async def revoke_session(
    db: AsyncSession,
    *,
    session_row: AdminSession,
    now: datetime | None = None,
) -> None:
    """Mark a session revoked (logout)."""

    session_row.revoked_at = _naive_utc(now)
    await db.flush()


async def revoke_all_sessions_for_user(
    db: AsyncSession,
    *,
    admin_user_id: str,
    now: datetime | None = None,
) -> int:
    """Revoke every active session for a user — used on password change.

    Returns the number of rows revoked. The bulk update is intentional:
    after a password change every old refresh token must be invalidated
    immediately, not lazily on next refresh.
    """

    revoked_at = _naive_utc(now)
    stmt = select(AdminSession).where(
        AdminSession.admin_user_id == admin_user_id,
        AdminSession.revoked_at.is_(None),
    )
    result = await db.execute(stmt)
    rows = list(result.scalars())
    for row in rows:
        row.revoked_at = revoked_at
    await db.flush()
    return len(rows)
