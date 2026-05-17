"""Raw-SQL helpers for vm_session-flavoured ``llm_accounts`` rows.

``llm_accounts`` is production-only (NOT in backend's ORM, per ADR-002).
Every helper here uses ``text()`` SQL with defensive ``information_schema``
probes so sqlite test fixtures degrade to "no data" / 503 rather than
blowing up. Mirrors the pattern in ``app/admin/accounts/db.py`` (Phase 7
slice 7b) and ``20260507_llm_accounts_schema_repair``.

Phase 1 (#1114) migration ``20260517_exec_mode`` added two columns the
helpers below depend on:

- ``execution_mode TEXT NOT NULL DEFAULT 'local_cookie'``
- ``vm_id TEXT NULL``

And a CHECK ``chk_exec_mode_cookies`` enforcing the R2.5 invariant
(vm_session rows MUST NOT carry cookies_json). This module assumes the
migration has run; if not, the schema-drift guard surfaces a 503 with
``llm_accounts_schema_outdated:execution_mode,vm_id`` so the SPA shows
a clean banner rather than a raw psycopg crash.

Public surface:

- ``fetch_vm_accounts(session)`` — list rows where
  ``execution_mode = 'vm_session'`` plus a 7-day success_count counter
  derived from ``query_attempts`` when available (empty on sqlite).
- ``create_vm_account(session, engine_id, vm_id, segment_group, ...)``
  — INSERT row with execution_mode='vm_session'. Reject if cookies_json
  supplied (defense-in-depth above the DB CHECK).
- ``toggle_execution_mode(session, account_id, new_mode, cookies_json,
  vm_id)`` — flip between modes with the contract:
    * local_cookie → vm_session: cookies_json MUST be NULL and vm_id required.
    * vm_session → local_cookie: vm_id cleared and cookies_json required.
- ``mark_needs_relogin(session, vm_id, engine)`` — flip status to a
  reserved sentinel (``needs_relogin``) so the admin pool surfaces it.
- ``clear_needs_relogin(session, vm_id, engine)`` — clear sentinel +
  stamp ``last_relogin_at`` (used by operator confirmation route).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# MVP engine universe — see ``docs/ADAPTER_CONTRACT.md`` §1.1.
MVP_ENGINES: frozenset[str] = frozenset({"chatgpt", "doubao", "deepseek-CN"})

# Sentinel status value used to flag vm_session accounts the watchdog
# detected as needing CAPTCHA / re-login. Kept distinct from the
# existing ``ACCOUNT_STATUSES`` so the SPA can render a dedicated
# highlighted badge without inheriting unrelated 'expired' semantics.
NEEDS_RELOGIN_STATUS = "needs_relogin"

# Required columns the vm_session router reads/writes. Mirrors
# ``_REQUIRED_LLM_ACCOUNT_COLUMNS`` in ``app/admin/accounts/db.py`` but
# adds the two Phase 1 (#1114) additions so a partially-migrated DB
# surfaces a 503 instead of a raw psycopg error.
_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "id",
        "llm_name",
        "phone_number",
        "execution_mode",
        "vm_id",
        "status",
        "cookies_json",
        "consecutive_fails",
        "query_count_today",
        "daily_limit",
        "created_at",
        "cookies_updated_at",
    }
)

# Columns that may not exist on every legacy operator DB. Best-effort
# read; SQL falls back to ``NULL`` when missing.
_OPTIONAL_COLUMNS: frozenset[str] = frozenset(
    {
        "segment_group",
        "last_used_at",
        "last_relogin_at",
    }
)


class VmAccountValidationError(RuntimeError):
    """Raised when an input violates the R2.5 contract or MVP-engine rule.

    Carries a stable ``code`` the router maps to a 400 JSON response so
    the SPA can render a localized message without parsing prose.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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


async def assert_schema(session: AsyncSession) -> None:
    """Raise ``RuntimeError("llm_accounts_schema_outdated:<csv>")`` when
    the running DB is missing columns the vm_session router needs.

    Skipped on sqlite (``_table_columns`` returns empty set); skipped
    when the table doesn't exist (caller already handles that path).
    Defense-in-depth against the schema-drift bug class PR #367 hit on
    Query Pool.
    """
    if not await _table_exists(session, "llm_accounts"):
        return
    cols = await _table_columns(session, "llm_accounts")
    if not cols:
        return  # sqlite / no permission to probe info schema
    missing = _REQUIRED_COLUMNS - cols
    if missing:
        raise RuntimeError(f"llm_accounts_schema_outdated:{','.join(sorted(missing))}")


def _isoformat_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def validate_create_payload(
    *,
    engine_id: Any,
    vm_id: Any,
    segment_group: Any,
    cookies_json: Any,
) -> tuple[str, str, str | None]:
    """Validate POST /vm/accounts body. Raise ``VmAccountValidationError``
    on the first failure so the router can return a 400 with a stable
    error code.

    Returns ``(engine_id, vm_id, segment_group)`` normalized.

    Defense-in-depth above the DB CHECK ``chk_exec_mode_cookies``:
    vm_session rows must never carry ``cookies_json``. If we relied on
    the CHECK alone, the failure surfaces as a generic IntegrityError
    in the operator console with no actionable code; here we reject
    upfront with ``vm_session_cookies_forbidden``.
    """
    if not engine_id:
        raise VmAccountValidationError("engine_id_required", "engine_id is required")
    engine_id_norm = str(engine_id).strip()
    if engine_id_norm not in MVP_ENGINES:
        raise VmAccountValidationError(
            "engine_id_invalid",
            f"engine_id must be one of {sorted(MVP_ENGINES)}",
        )
    if not vm_id:
        raise VmAccountValidationError("vm_id_required", "vm_id is required")
    vm_id_norm = str(vm_id).strip()
    if not vm_id_norm:
        raise VmAccountValidationError("vm_id_required", "vm_id must be non-empty")
    segment_norm: str | None = None
    if segment_group is not None and str(segment_group).strip():
        segment_norm = str(segment_group).strip()
    # R2.5: reject any cookies payload on create for vm_session
    if cookies_json not in (None, "", "null"):
        raise VmAccountValidationError(
            "vm_session_cookies_forbidden",
            "vm_session accounts must not carry cookies_json (R2.5).",
        )
    return engine_id_norm, vm_id_norm, segment_norm


def validate_toggle_payload(
    *,
    new_mode: Any,
    vm_id: Any,
    cookies_json: Any,
) -> tuple[str, str | None, str | None]:
    """Validate PATCH /vm/accounts/{id} body for an execution_mode flip.

    Contract:
    - new_mode='local_cookie' requires cookies_json (non-empty) AND vm_id
      to be explicitly null/empty (the local connector owns its cookies;
      vm_id has no meaning for it).
    - new_mode='vm_session' requires vm_id (non-empty) AND cookies_json
      to be null/empty (R2.5 self-cloning prevention).

    Returns ``(new_mode, vm_id_or_None, cookies_json_or_None)``.
    """
    mode = str(new_mode or "").strip()
    if mode not in {"local_cookie", "vm_session"}:
        raise VmAccountValidationError(
            "execution_mode_invalid",
            "execution_mode must be 'local_cookie' or 'vm_session'.",
        )

    vm_id_norm: str | None = None
    if vm_id is not None and str(vm_id).strip():
        vm_id_norm = str(vm_id).strip()

    cookies_norm: str | None = None
    if cookies_json not in (None, "", "null"):
        if isinstance(cookies_json, (dict, list)):
            cookies_norm = json.dumps(cookies_json)
        else:
            cookies_norm = str(cookies_json)

    if mode == "vm_session":
        if not vm_id_norm:
            raise VmAccountValidationError(
                "vm_id_required",
                "Toggling to vm_session requires vm_id.",
            )
        if cookies_norm:
            raise VmAccountValidationError(
                "vm_session_cookies_forbidden",
                "Toggling to vm_session requires cookies_json to be null (R2.5).",
            )
    else:  # local_cookie
        if not cookies_norm:
            raise VmAccountValidationError(
                "cookies_json_required",
                "Toggling to local_cookie requires cookies_json.",
            )
        if vm_id_norm:
            raise VmAccountValidationError(
                "vm_id_must_be_null",
                "Toggling to local_cookie requires vm_id to be cleared.",
            )

    return mode, vm_id_norm, cookies_norm


async def fetch_vm_accounts(session: AsyncSession) -> list[dict[str, Any]]:
    """Return every ``llm_accounts`` row with
    ``execution_mode = 'vm_session'``.

    Empty list on sqlite test fixtures (``llm_accounts`` table absent).
    The `success_count_7d` field comes back as 0 when ``query_attempts``
    doesn't exist either — same defensive degradation.
    """
    if not await _table_exists(session, "llm_accounts"):
        return []
    await assert_schema(session)
    cols = await _table_columns(session, "llm_accounts")
    optional = _OPTIONAL_COLUMNS & cols
    # SQL fragments for optional columns: include them when present, NULL otherwise
    seg_expr = "segment_group" if "segment_group" in optional else "NULL AS segment_group"
    last_used_expr = "last_used_at" if "last_used_at" in optional else "NULL AS last_used_at"
    last_relogin_expr = (
        "last_relogin_at" if "last_relogin_at" in optional else "NULL AS last_relogin_at"
    )
    has_attempts = await _table_exists(session, "query_attempts")
    if has_attempts:
        success_expr = (
            "(SELECT COUNT(*) FROM query_attempts qa "
            "WHERE qa.account_id = a.id "
            "AND qa.outcome IN ('success', 'completed') "
            "AND qa.created_at >= NOW() - INTERVAL '7 days') AS success_count_7d"
        )
    else:
        success_expr = "0 AS success_count_7d"
    sql = text(
        f"""
        SELECT a.id,
               a.llm_name AS engine_id,
               a.vm_id,
               a.execution_mode,
               a.status,
               a.consecutive_fails,
               a.query_count_today AS daily_used,
               a.daily_limit,
               {seg_expr},
               {last_used_expr},
               {last_relogin_expr},
               a.cookies_updated_at,
               {success_expr}
        FROM llm_accounts a
        WHERE a.execution_mode = 'vm_session'
        ORDER BY a.llm_name, a.id
        """
    )
    rows = (await session.execute(sql)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["last_used_at"] = _isoformat_or_none(item.get("last_used_at"))
        item["last_relogin_at"] = _isoformat_or_none(item.get("last_relogin_at"))
        item["cookies_updated_at"] = _isoformat_or_none(item.get("cookies_updated_at"))
        out.append(item)
    return out


async def create_vm_account(
    session: AsyncSession,
    *,
    engine_id: str,
    vm_id: str,
    segment_group: str | None,
) -> int:
    """INSERT a vm_session row into ``llm_accounts``. Returns the new
    account_id.

    Raises ``RuntimeError("llm_accounts_table_missing")`` on sqlite so
    the router surfaces a 503. ``IntegrityError`` from the DB CHECK
    is allowed to bubble up; the router translates known constraint
    names to clean 400s.
    """
    if not await _table_exists(session, "llm_accounts"):
        raise RuntimeError("llm_accounts_table_missing")
    await assert_schema(session)
    cols = await _table_columns(session, "llm_accounts")
    has_segment = "segment_group" in cols
    if has_segment:
        sql = text(
            """
            INSERT INTO llm_accounts
                (llm_name, phone_number, password_encrypted, email,
                 execution_mode, vm_id, segment_group,
                 daily_limit, status, created_at)
            VALUES
                (:engine_id, :vm_id, '', :email,
                 'vm_session', :vm_id, :segment_group,
                 :daily_limit, 'active', NOW())
            RETURNING id
            """
        )
    else:
        sql = text(
            """
            INSERT INTO llm_accounts
                (llm_name, phone_number, password_encrypted, email,
                 execution_mode, vm_id,
                 daily_limit, status, created_at)
            VALUES
                (:engine_id, :vm_id, '', :email,
                 'vm_session', :vm_id,
                 :daily_limit, 'active', NOW())
            RETURNING id
            """
        )
    params = {
        "engine_id": engine_id,
        "vm_id": vm_id,
        "email": f"vm-{vm_id}@{engine_id}.local",
        "daily_limit": 50,
    }
    if has_segment:
        params["segment_group"] = segment_group
    result = await session.execute(sql, params)
    new_row = result.first()
    if not new_row:
        raise RuntimeError("vm_account_insert_failed")
    await session.commit()
    return int(new_row[0])


async def toggle_execution_mode(
    session: AsyncSession,
    *,
    account_id: int,
    new_mode: str,
    vm_id: str | None,
    cookies_json: str | None,
) -> bool:
    """Flip ``execution_mode`` for ``account_id``.

    Returns ``False`` when the account doesn't exist. Raises
    ``RuntimeError("llm_accounts_table_missing")`` on sqlite so the
    router surfaces a 503.

    The caller is expected to have run ``validate_toggle_payload`` so
    we never bypass R2.5 at this layer.
    """
    if not await _table_exists(session, "llm_accounts"):
        raise RuntimeError("llm_accounts_table_missing")
    await assert_schema(session)
    if new_mode == "vm_session":
        # Clearing cookies + setting vm_id together so the DB CHECK
        # ``chk_exec_mode_cookies`` sees a consistent row in one update.
        sql = text(
            """
            UPDATE llm_accounts
            SET execution_mode = 'vm_session',
                vm_id = :vm_id,
                cookies_json = NULL
            WHERE id = :id
            """
        )
        params: dict[str, Any] = {"id": account_id, "vm_id": vm_id}
    else:  # local_cookie
        sql = text(
            """
            UPDATE llm_accounts
            SET execution_mode = 'local_cookie',
                vm_id = NULL,
                cookies_json = :cookies_json,
                cookies_updated_at = NOW()
            WHERE id = :id
            """
        )
        params = {"id": account_id, "cookies_json": cookies_json}
    result = await session.execute(sql, params)
    if (getattr(result, "rowcount", 0) or 0) == 0:
        return False
    await session.commit()
    return True


async def mark_needs_relogin(session: AsyncSession, *, vm_id: str, engine: str) -> int | None:
    """Mark the matching vm_session account as ``needs_relogin``.

    Returns the account_id when a row was touched, ``None`` when no
    match (the watchdog may emit before the operator has provisioned
    the account). The router treats no-match as a soft 200 — the
    Slack ping still fires.
    """
    if not await _table_exists(session, "llm_accounts"):
        return None
    sql = text(
        """
        UPDATE llm_accounts
        SET status = :sentinel
        WHERE vm_id = :vm_id
          AND llm_name = :engine
          AND execution_mode = 'vm_session'
        RETURNING id
        """
    )
    row = (
        await session.execute(
            sql,
            {"sentinel": NEEDS_RELOGIN_STATUS, "vm_id": vm_id, "engine": engine},
        )
    ).first()
    if not row:
        return None
    await session.commit()
    return int(row[0])


async def clear_needs_relogin(session: AsyncSession, *, vm_id: str, engine: str) -> int | None:
    """Reverse of ``mark_needs_relogin``: flip status back to active
    and stamp ``last_relogin_at`` so the dashboard shows the recovery
    timestamp.

    Skips ``last_relogin_at`` write when the column is absent (legacy
    DBs not yet migrated past Phase 1).
    """
    if not await _table_exists(session, "llm_accounts"):
        return None
    cols = await _table_columns(session, "llm_accounts")
    has_last_relogin = "last_relogin_at" in cols
    if has_last_relogin:
        sql = text(
            """
            UPDATE llm_accounts
            SET status = 'active',
                last_relogin_at = NOW(),
                consecutive_fails = 0
            WHERE vm_id = :vm_id
              AND llm_name = :engine
              AND execution_mode = 'vm_session'
            RETURNING id
            """
        )
    else:
        sql = text(
            """
            UPDATE llm_accounts
            SET status = 'active',
                consecutive_fails = 0
            WHERE vm_id = :vm_id
              AND llm_name = :engine
              AND execution_mode = 'vm_session'
            RETURNING id
            """
        )
    row = (await session.execute(sql, {"vm_id": vm_id, "engine": engine})).first()
    if not row:
        return None
    await session.commit()
    return int(row[0])


async def get_vm_account(session: AsyncSession, *, account_id: int) -> dict[str, Any] | None:
    """Return the slim audit-friendly row for one account (no cookies
    blob). Returns ``None`` when the account doesn't exist.
    """
    if not await _table_exists(session, "llm_accounts"):
        return None
    await assert_schema(session)
    cols = await _table_columns(session, "llm_accounts")
    seg_expr = "segment_group" if "segment_group" in cols else "NULL AS segment_group"
    sql = text(
        f"""
        SELECT id, llm_name AS engine_id, execution_mode, vm_id,
               status, daily_limit, query_count_today AS daily_used,
               {seg_expr}
        FROM llm_accounts
        WHERE id = :id
        """
    )
    row = (await session.execute(sql, {"id": account_id})).mappings().first()
    if not row:
        return None
    return dict(row)


def utcnow_iso() -> str:
    """Helper for tests / payload stamping."""
    return datetime.now(UTC).replace(tzinfo=None).isoformat()
