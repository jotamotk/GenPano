"""J5 fixture — enforce the round-9 admin-write invariant on `users`.

Round 9 (decision #30.H Path B Variant 2) lock-in: the only column on
`users` that an admin endpoint is permitted to write is
`deletion_requested_at`. Every other state change (freeze, force
password reset, soft-delete audit trail) must land in
`user_moderation_actions` instead.

This module exposes:

- `ALLOWED_USER_WRITE_COLUMNS` — the whitelist (frozenset).
- `assert_user_write_columns(columns)` — raise NotImplementedError if
  any name in `columns` is outside the whitelist.
- `install_j5_guard(session)` — register a `before_flush` listener on
  an AsyncSession's sync session that inspects every dirty User
  instance and raises NotImplementedError if any non-whitelisted
  attribute was modified within the unit-of-work. Tests opt in by
  calling this helper inside their setup; the guard is **not**
  installed globally so production endpoints retain free access to all
  columns of the model layer (the contract is admin-API-shape, not
  ORM-level).

Decision references:
- CLAUDE.md #30.H (Path B Variant 2 — Y3 freeze writes moderation, Y5
  soft-delete is the only `users` column write).
- ADMIN_PRD §4.1 Module A endpoint surface.
- DATA_MODEL §1.1 canonical schema.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from app.models.user import User

ALLOWED_USER_WRITE_COLUMNS: frozenset[str] = frozenset({"deletion_requested_at"})


class J5InvariantViolation(NotImplementedError):
    """Raised when an admin code path tries to write a `users` column
    other than `deletion_requested_at`."""


def assert_user_write_columns(columns: Iterable[str]) -> None:
    """Raise J5InvariantViolation if any column is outside the J5 whitelist.

    Used at boundary tests (DTO → ORM bridge) to prove that the admin
    endpoint shape never even *attempts* to mutate non-whitelisted
    columns. The check is set-difference based, so duplicates and order
    are irrelevant.
    """

    offenders = sorted(set(columns) - ALLOWED_USER_WRITE_COLUMNS)
    if offenders:
        raise J5InvariantViolation(
            "J5 invariant violation: admin code attempted to write "
            f"users column(s) {offenders!r}; "
            f"only {sorted(ALLOWED_USER_WRITE_COLUMNS)!r} is permitted."
        )


def install_j5_guard(session: AsyncSession) -> None:
    """Register a `before_flush` listener on the session's sync proxy.

    The listener walks every dirty User instance, computes the set of
    actually-modified attribute keys (via `inspect(obj).attrs[k].history.has_changes()`),
    and raises J5InvariantViolation if any is outside the whitelist.

    Calling this twice on the same session is a no-op (the listener is
    idempotent on identity).
    """

    sync_session = session.sync_session

    if getattr(sync_session, "_j5_guard_installed", False):
        return

    @event.listens_for(sync_session, "before_flush")
    def _enforce_user_write_whitelist(
        sess: SyncSession,
        _flush_context: Any,
        _instances: Any,
    ) -> None:
        for obj in sess.dirty:
            if not isinstance(obj, User):
                continue
            state = inspect(obj)
            modified = {attr.key for attr in state.attrs if attr.history.has_changes()}
            offenders = sorted(modified - ALLOWED_USER_WRITE_COLUMNS)
            if offenders:
                raise J5InvariantViolation(
                    "J5 invariant violation in flush: User row "
                    f"{getattr(obj, 'id', '?')!r} had column(s) {offenders!r} "
                    f"modified; only {sorted(ALLOWED_USER_WRITE_COLUMNS)!r} "
                    "is permitted from admin code paths."
                )

    sync_session._j5_guard_installed = True  # type: ignore[attr-defined]


__all__ = [
    "ALLOWED_USER_WRITE_COLUMNS",
    "J5InvariantViolation",
    "assert_user_write_columns",
    "install_j5_guard",
]
