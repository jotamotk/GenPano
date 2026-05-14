"""Legacy-schema discovery + column-aware SQL expression helpers.

Phase 2 of splitting `_topic_analysis_service.py` (Epic #885, design #887).

The topic-analysis service supports both modern Postgres schemas and the
legacy SQLite-tested ones, where individual columns may or may not exist.
These helpers answer the questions: does this table exist? which columns
does it have? — and return safe SQL fragments that adapt to whichever
columns are present.

Public surface:
- `legacy_table_exists`, `legacy_table_columns` — runtime probes
- `_select_col` — column-conditional SELECT alias
- `_not_deleted_condition` — portable soft-delete predicate
- `_topic_name_expr` / `_prompt_text_expr` / `_prompt_scope_expr` /
  `_prompt_tags_expr` — preferred-column fallback chains
- `_safe_ident` — identifier validator (raises on injection-shaped inputs)
"""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise ValueError(f"unsafe identifier: {name}")
    return name


async def legacy_table_exists(session: AsyncSession, name: str) -> bool:
    """Portable table existence probe for Postgres and sqlite tests."""
    _safe_ident(name)
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
        if row is not None:
            return True
    except Exception:
        pass
    try:
        row = (
            await session.execute(
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :n LIMIT 1"),
                {"n": name},
            )
        ).first()
        return row is not None
    except Exception:
        return False


async def legacy_table_columns(session: AsyncSession, name: str) -> set[str]:
    """Return table columns without assuming a SQL dialect."""
    name = _safe_ident(name)
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :n"
                ),
                {"n": name},
            )
        ).all()
        cols = {str(r[0]) for r in rows}
        if cols:
            return cols
    except Exception:
        pass
    try:
        rows = (await session.execute(text(f"PRAGMA table_info({name})"))).all()
        return {str(r[1]) for r in rows}
    except Exception:
        return set()


def _select_col(
    cols: set[str],
    alias: str,
    column: str,
    out_name: str,
    default: str = "NULL",
) -> str:
    return f"{alias}.{column} AS {out_name}" if column in cols else f"{default} AS {out_name}"


def _not_deleted_condition(alias: str) -> str:
    """Portable soft-delete predicate for bool, int, and text columns."""
    return (
        f"({alias}.is_deleted IS NULL "
        f"OR LOWER(CAST({alias}.is_deleted AS TEXT)) IN ('false', '0', 'f', 'no', 'n'))"
    )


def _topic_name_expr(cols: set[str]) -> str:
    if "text" in cols:
        return "t.text"
    if "name" in cols:
        return "t.name"
    if "title" in cols:
        return "t.title"
    return "CAST(t.id AS TEXT)"


def _prompt_text_expr(cols: set[str]) -> str:
    if "text" in cols:
        return "p.text"
    if "prompt_text" in cols:
        return "p.prompt_text"
    return "NULL"


def _prompt_scope_expr(cols: set[str]) -> str:
    if "prompt_scope" in cols:
        return "p.prompt_scope"
    if "promptScope" in cols:
        return 'p."promptScope"'
    return "NULL"


def _prompt_tags_expr(cols: set[str]) -> str:
    if "tags" in cols:
        return "p.tags"
    if "metadata" in cols:
        return "p.metadata"
    return "NULL"
