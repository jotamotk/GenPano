"""DB operations for ``llm_accounts`` (Phase 7 slice 7b — HIGHEST sensitivity).

``llm_accounts`` is NOT in backend's ORM (production-only table per
ADR-002). All queries use raw ``text()`` SQL with defensive
``information_schema`` probes so sqlite tests degrade to "no data"
rather than blowing up.

Operator credentials (the cookies_json blob) are read by these
helpers but NEVER returned in audit-friendly diffs — the route
handler audits only counts + platform / label.

Public:
- ``fetch_accounts(session)`` — list (no cookies blob in the wire row).
- ``upsert_account_from_cookies(session, *, platform, label,
  cookies_json_str, daily_limit)`` — INSERT/UPDATE keyed on
  (llm_name, phone_number).
- ``update_account_status(session, *, account_id, status)``.
- ``reset_account_fails(session, *, account_id)``.
- ``delete_account(session, *, account_id)``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Columns ``app.admin.accounts`` reads or writes. Kept in sync with the
# Alembic repair migration ``20260507_llm_accounts_schema_repair`` so a
# legacy DB that hasn't been migrated yet gets a clean 503 rather than a
# raw psycopg ``UndefinedColumn`` 500. Same defensive pattern PR #367
# introduced for query_pool.
_REQUIRED_LLM_ACCOUNT_COLUMNS: frozenset[str] = frozenset(
    {
        "id",
        "llm_name",
        "phone_number",
        "email",
        "password_encrypted",
        "cookies_json",
        "cookies_updated_at",
        "status",
        "consecutive_fails",
        "query_count_today",
        "daily_limit",
        "cooldown_until",
        "created_at",
    }
)


async def _table_exists(session: AsyncSession, name: str) -> bool:
    try:
        row = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :n LIMIT 1"
                ),
                {"n": name},
            )
        ).first()
    except Exception:
        return False
    return row is not None


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
    """Column set for ``public.<name>``. Empty on sqlite / probe failure."""
    try:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :n"
            ),
            {"n": name},
        )
    except Exception:
        return set()
    return {row[0] for row in result.all()}


async def assert_llm_accounts_schema(session: AsyncSession) -> None:
    """Raise ``RuntimeError`` with a stable code when the production
    ``llm_accounts`` schema is missing columns slice 7b depends on.

    Defense-in-depth against the schema-drift bug class PR #367 fixed for
    Query Pool: if an operator DB predates the repair migrations, the
    SPA gets a clean 503 ``llm_accounts_schema_outdated`` with the
    missing column list, instead of a raw psycopg crash buried in
    ``cookies_json::text`` evaluation.

    Skipped on sqlite (``_table_columns`` returns ``set()``); skipped
    when the table doesn't exist (caller already handles that path).
    """
    if not await _table_exists(session, "llm_accounts"):
        return
    cols = await _table_columns(session, "llm_accounts")
    if not cols:
        # information_schema probe failed (sqlite or permissions issue);
        # don't block the request — the table_exists check passed so we
        # at least know the table is reachable.
        return
    missing = _REQUIRED_LLM_ACCOUNT_COLUMNS - cols
    if missing:
        # Sorted for deterministic error output (tests + log aggregation).
        missing_csv = ",".join(sorted(missing))
        raise RuntimeError(f"llm_accounts_schema_outdated:{missing_csv}")


async def _isoformat_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


async def fetch_accounts(session: AsyncSession) -> list[dict[str, Any]]:
    """List llm_accounts (without exposing the cookies_json blob).

    Mirrors admin_console wire shape: id, llm_name, phone_number, status,
    daily_used (from query_count_today), daily_limit, consecutive_fails,
    cookie_count (computed from cookies_json), cookies_updated_at,
    updated_at (from created_at — admin_console quirk).

    Returns ``[]`` when the table doesn't exist (sqlite tests).
    """
    if not await _table_exists(session, "llm_accounts"):
        return []
    await assert_llm_accounts_schema(session)
    sql = text(
        """
        SELECT id,
               llm_name,
               phone_number,
               status,
               query_count_today AS daily_used,
               daily_limit,
               consecutive_fails,
               CASE
                 WHEN cookies_json IS NOT NULL AND cookies_json::text <> ''
                 THEN CASE
                   WHEN cookies_json::text LIKE '[%'
                     THEN json_array_length(cookies_json::json)
                   WHEN cookies_json::text LIKE '{%'
                     THEN json_array_length((cookies_json::json->'cookies'))
                   ELSE 0
                 END
                 ELSE 0
               END AS cookie_count,
               cookies_updated_at,
               created_at AS updated_at
        FROM llm_accounts
        ORDER BY llm_name, id
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["updated_at"] = await _isoformat_or_none(item.get("updated_at"))
        item["cookies_updated_at"] = await _isoformat_or_none(item.get("cookies_updated_at"))
        out.append(item)
    return out


async def upsert_account_from_cookies(
    session: AsyncSession,
    *,
    platform: str,
    label: str,
    cookies_json_str: str,
    daily_limit: int,
    email: str,
) -> tuple[int, str]:
    """INSERT/UPDATE ``llm_accounts`` row for (platform, label).

    Returns ``(account_id, outcome)`` where outcome is "added" or
    "updated". Caller emits the audit row; we don't log the cookies
    blob here.

    Raises ``RuntimeError("llm_accounts_table_missing")`` on sqlite
    test fixtures so callers can return a 503 to the SPA.
    """
    if not await _table_exists(session, "llm_accounts"):
        raise RuntimeError("llm_accounts_table_missing")
    await assert_llm_accounts_schema(session)

    existing = (
        await session.execute(
            text(
                "SELECT id FROM llm_accounts WHERE llm_name = :platform AND phone_number = :label"
            ),
            {"platform": platform, "label": label},
        )
    ).first()
    if existing:
        account_id = int(existing[0])
        await session.execute(
            text(
                """
                UPDATE llm_accounts
                SET cookies_json = :cookies_json,
                    status = 'active',
                    consecutive_fails = 0,
                    cookies_updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"cookies_json": cookies_json_str, "id": account_id},
        )
        outcome = "updated"
    else:
        result = await session.execute(
            text(
                """
                INSERT INTO llm_accounts
                    (llm_name, email, password_encrypted, phone_number,
                     cookies_json, daily_limit, status, cookies_updated_at)
                VALUES
                    (:platform, :email, '', :label, :cookies_json,
                     :daily_limit, 'active', NOW())
                RETURNING id
                """
            ),
            {
                "platform": platform,
                "email": email,
                "label": label,
                "cookies_json": cookies_json_str,
                "daily_limit": daily_limit,
            },
        )
        new_row = result.first()
        if not new_row:
            raise RuntimeError("llm_accounts_insert_failed")
        account_id = int(new_row[0])
        outcome = "added"
    await session.commit()
    return account_id, outcome


async def update_account_status(session: AsyncSession, *, account_id: int, status: str) -> bool:
    """Flip ``status``. ``active`` also clears cooldown + consecutive
    fails (matches admin_console). Returns False if account doesn't
    exist."""
    if not await _table_exists(session, "llm_accounts"):
        return False
    await assert_llm_accounts_schema(session)
    if status == "active":
        result = await session.execute(
            text(
                "UPDATE llm_accounts SET status = :status, "
                "cooldown_until = NULL, consecutive_fails = 0 WHERE id = :id"
            ),
            {"status": status, "id": account_id},
        )
    else:
        result = await session.execute(
            text("UPDATE llm_accounts SET status = :status WHERE id = :id"),
            {"status": status, "id": account_id},
        )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        return False
    await session.commit()
    return True


async def reset_account_fails(session: AsyncSession, *, account_id: int) -> bool:
    """Reset failure counters + flip back to active. Returns False if
    the account is missing."""
    if not await _table_exists(session, "llm_accounts"):
        return False
    await assert_llm_accounts_schema(session)
    result = await session.execute(
        text(
            """
            UPDATE llm_accounts
            SET consecutive_fails = 0,
                query_count_today = 0,
                status = 'active',
                cooldown_until = NULL
            WHERE id = :id
            """
        ),
        {"id": account_id},
    )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        return False
    await session.commit()
    return True


async def delete_account(session: AsyncSession, *, account_id: int) -> bool:
    """Hard-delete an llm_accounts row. The legacy admin_console
    behaviour is destructive (no soft-delete column); preserved here.
    """
    if not await _table_exists(session, "llm_accounts"):
        return False
    result = await session.execute(
        text("DELETE FROM llm_accounts WHERE id = :id"),
        {"id": account_id},
    )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        return False
    await session.commit()
    return True


async def get_account(session: AsyncSession, *, account_id: int) -> dict[str, Any] | None:
    """Detail row (without cookies_json blob) for audit before/after."""
    if not await _table_exists(session, "llm_accounts"):
        return None
    await assert_llm_accounts_schema(session)
    sql = text(
        """
        SELECT id, llm_name, phone_number, status,
               query_count_today AS daily_used, daily_limit,
               consecutive_fails, cookies_updated_at,
               created_at AS updated_at
        FROM llm_accounts
        WHERE id = :id
        """
    )
    row = (await session.execute(sql, {"id": account_id})).mappings().first()
    if not row:
        return None
    item = dict(row)
    item["updated_at"] = await _isoformat_or_none(item.get("updated_at"))
    item["cookies_updated_at"] = await _isoformat_or_none(item.get("cookies_updated_at"))
    return item
