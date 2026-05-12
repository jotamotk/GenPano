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

from app.admin.accounts.lib import redact_account_row

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


async def fetch_accounts(
    session: AsyncSession, *, status: str | None = None
) -> list[dict[str, Any]]:
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
    params: dict[str, Any] = {}
    where = ""
    if status:
        where = "WHERE status = :status"
        params["status"] = status
    sql = text(
        f"""
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
                   WHEN cookies_json::text LIKE '{{%'
                     THEN json_array_length((cookies_json::json->'cookies'))
                   ELSE 0
                 END
                 ELSE 0
               END AS cookie_count,
               cookies_updated_at,
               created_at AS updated_at
        FROM llm_accounts
        {where}
        ORDER BY llm_name, id
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["updated_at"] = await _isoformat_or_none(item.get("updated_at"))
        item["cookies_updated_at"] = await _isoformat_or_none(item.get("cookies_updated_at"))
        out.append(redact_account_row(item))
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


async def update_account_daily_limit(
    session: AsyncSession, *, account_id: int, daily_limit: int
) -> bool:
    """Update one account's daily capacity. Returns False if the
    account is missing."""
    if not await _table_exists(session, "llm_accounts"):
        return False
    await assert_llm_accounts_schema(session)
    result = await session.execute(
        text("UPDATE llm_accounts SET daily_limit = :daily_limit WHERE id = :id"),
        {"daily_limit": daily_limit, "id": account_id},
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
    return redact_account_row(item)


# ─── Profile-binding helpers (account_profile_map) ────────────────────────
#
# admin_console exposed /api/accounts/{id}/profiles{,_counts,auto_assign}
# WITHOUT auth. The FastAPI port (Phase 7b follow-up) keeps the same wire
# shape but adds Depends(current_admin) at the router layer. The
# account_profile_map table is production-only (legacy admin_console
# bootstrap), so every helper degrades gracefully when the table is
# missing — sqlite test fixtures get an empty list / empty dict instead
# of a 500.

LLM_DEFAULT_GEO: dict[str, str] = {
    "doubao": "CN",
    "deepseek": "CN",
    "chatgpt": "US",
    "gemini": "US",
}


def account_engine_geo(llm_name: Any) -> str | None:
    """Mirror of admin_console's _account_engine_geo: returns the
    expected country code for an engine, or None when unknown."""
    if not llm_name:
        return None
    return LLM_DEFAULT_GEO.get(str(llm_name).lower())


def _coerce_persona(value: Any) -> dict[str, Any]:
    """``persona_json`` is JSONB in production but may come back as a
    str/None depending on driver/sqlite fallback. Normalise to a dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            import json as _json

            parsed = _json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


async def fetch_account_basics(session: AsyncSession, *, account_id: int) -> dict[str, Any] | None:
    """Slim row used by GET /accounts/{id}/profiles. Returns None when
    the account doesn't exist."""
    if not await _table_exists(session, "llm_accounts"):
        return None
    await assert_llm_accounts_schema(session)
    sql = text(
        """
        SELECT id, llm_name, phone_number, daily_limit,
               query_count_today, status
        FROM llm_accounts
        WHERE id = :id
        """
    )
    row = (await session.execute(sql, {"id": account_id})).mappings().first()
    return redact_account_row(dict(row)) if row else None


async def fetch_account_profile_bindings(
    session: AsyncSession, *, account_id: int, q: str | None = None
) -> list[dict[str, Any]]:
    """Return raw ``account_profile_map`` rows joined to ``profiles``.
    Conflict computation happens in the router so the DB layer stays
    schema-aware but presentation-free.
    """
    if not await _table_exists(session, "account_profile_map"):
        return []
    params: dict[str, Any] = {"id": account_id}
    search_pred = ""
    if q:
        like = f"%{q}%"
        search_pred = (
            " AND (CAST(p.id AS TEXT) ILIKE :like_id "
            "OR COALESCE(p.code, '') ILIKE :like "
            "OR COALESCE(p.name, '') ILIKE :like)"
        )
        params["like"] = like
        params["like_id"] = like
    sql = text(
        f"""
        SELECT
            apm.id                        AS binding_id,
            apm.profile_id                AS profile_id,
            apm.daily_quota               AS daily_quota,
            apm.conflict_acknowledged     AS conflict_acknowledged,
            p.code                        AS profile_code,
            p.name                        AS profile_name,
            p.persona_json                AS persona_json
        FROM account_profile_map apm
        LEFT JOIN profiles p ON CAST(p.id AS TEXT) = apm.profile_id
        WHERE apm.account_id = :id
          {search_pred}
        ORDER BY p.code NULLS LAST, apm.profile_id
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


async def fetch_account_quota_total(session: AsyncSession, *, account_id: int) -> int:
    """Σ daily_quota across all bindings — used to render the drawer
    quota counter."""
    if not await _table_exists(session, "account_profile_map"):
        return 0
    row = (
        await session.execute(
            text(
                "SELECT COALESCE(SUM(daily_quota), 0) AS s "
                "FROM account_profile_map WHERE account_id = :id"
            ),
            {"id": account_id},
        )
    ).first()
    return int(row[0] or 0) if row else 0


async def upsert_account_profile_bindings(
    session: AsyncSession,
    *,
    account_id: int,
    bindings: list[dict[str, Any]],
    remove_profile_ids: list[str],
) -> tuple[int, int]:
    """Upsert provided bindings + delete the ``remove_profile_ids``.
    Returns ``(upserted_count, removed_count)``. Raises
    ``RuntimeError("account_profile_map_table_missing")`` so the router
    can return a clean 503 on sqlite test fixtures.
    """
    if not await _table_exists(session, "account_profile_map"):
        raise RuntimeError("account_profile_map_table_missing")

    upserted = 0
    for b in bindings:
        pid = str(b.get("profile_id") or "").strip()
        if not pid:
            continue
        try:
            quota = int(b.get("daily_quota") or 0)
        except (TypeError, ValueError):
            quota = 0
        ack = bool(b.get("conflict_acknowledged"))
        await session.execute(
            text(
                """
                INSERT INTO account_profile_map
                    (account_id, profile_id, daily_quota, conflict_acknowledged)
                VALUES (:account_id, :profile_id, :daily_quota, :ack)
                ON CONFLICT (account_id, profile_id) DO UPDATE
                    SET daily_quota = EXCLUDED.daily_quota,
                        conflict_acknowledged = EXCLUDED.conflict_acknowledged
                """
            ),
            {
                "account_id": account_id,
                "profile_id": pid,
                "daily_quota": quota,
                "ack": ack,
            },
        )
        upserted += 1

    removed = 0
    for pid in remove_profile_ids:
        result = await session.execute(
            text(
                "DELETE FROM account_profile_map "
                "WHERE account_id = :account_id AND profile_id = :profile_id"
            ),
            {"account_id": account_id, "profile_id": str(pid)},
        )
        removed += int(getattr(result, "rowcount", 0) or 0)

    await session.commit()
    return upserted, removed


async def fetch_profile_counts(
    session: AsyncSession,
) -> dict[int, dict[str, int]]:
    """Aggregate per-account binding counts so the account pool table
    can render the 绑定Profiles column without N+1 fetches.
    """
    if not await _table_exists(session, "account_profile_map"):
        return {}
    sql = text(
        """
        SELECT account_id,
               COUNT(*) AS bindings,
               SUM(CASE WHEN conflict_acknowledged THEN 0 ELSE 1 END)
                   AS unacknowledged
        FROM account_profile_map
        GROUP BY account_id
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    return {
        int(r["account_id"]): {
            "bindings": int(r["bindings"] or 0),
            "unacknowledged": int(r["unacknowledged"] or 0),
        }
        for r in rows
    }


async def fetch_active_accounts_with_bound_count(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """List accounts eligible for auto-assignment. Mirrors the Flask
    SELECT used in admin_console's auto_assign_profiles handler.
    """
    if not await _table_exists(session, "llm_accounts"):
        return []
    await assert_llm_accounts_schema(session)
    sql = text(
        """
        SELECT a.id, a.llm_name, a.phone_number, a.daily_limit,
               (SELECT COUNT(*) FROM account_profile_map apm
                  WHERE apm.account_id = a.id) AS bound_count
        FROM llm_accounts a
        WHERE a.status = 'active'
          AND a.cookies_json IS NOT NULL AND a.cookies_json::text <> ''
        ORDER BY a.id
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    return [dict(r) for r in rows]


async def fetch_assignable_profiles(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Return Profile rows usable for round-robin / LLM assignment.
    Probes the columns at runtime because some envs lack
    ``code``/``persona_json``/``is_deleted`` (legacy admin_console DBs).
    """
    if not await _table_exists(session, "profiles"):
        return []
    cols = await _table_columns(session, "profiles")
    select_parts = ["CAST(p.id AS TEXT) AS id"]
    select_parts.append("p.code AS code" if "code" in cols else "'' AS code")
    select_parts.append("p.name AS name" if "name" in cols else "NULL AS name")
    select_parts.append(
        "p.persona_json AS persona_json" if "persona_json" in cols else "NULL AS persona_json"
    )
    where_clause = "COALESCE(p.is_deleted, FALSE) = FALSE" if "is_deleted" in cols else "TRUE"
    sql = text(
        f"""
        SELECT {", ".join(select_parts)}
        FROM profiles p
        WHERE {where_clause}
        ORDER BY CAST(p.id AS TEXT)
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        item["persona_json"] = _coerce_persona(item.get("persona_json"))
        out.append(item)
    return out


async def insert_auto_assigned_bindings(
    session: AsyncSession,
    *,
    account_id: int,
    profile_ids: list[str],
    daily_quota: int = 1,
) -> int:
    """Bulk INSERT bindings (ON CONFLICT DO NOTHING). Returns the count
    of rows actually inserted (sum of ``rowcount``)."""
    if not await _table_exists(session, "account_profile_map"):
        raise RuntimeError("account_profile_map_table_missing")
    inserted = 0
    for pid in profile_ids:
        result = await session.execute(
            text(
                """
                INSERT INTO account_profile_map
                    (account_id, profile_id, daily_quota, conflict_acknowledged)
                VALUES (:account_id, :profile_id, :daily_quota, FALSE)
                ON CONFLICT (account_id, profile_id) DO NOTHING
                """
            ),
            {
                "account_id": account_id,
                "profile_id": str(pid),
                "daily_quota": daily_quota,
            },
        )
        inserted += int(getattr(result, "rowcount", 0) or 0)
    return inserted
