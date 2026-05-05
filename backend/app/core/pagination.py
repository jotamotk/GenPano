"""Cursor-based pagination helpers (PRD §6.4 default).

Usage:

    from app.core.pagination import CursorParams, paginated

    @router.get("/items")
    async def list_items(p: CursorParams = Depends()):
        rows = await query_items(...)
        return paginated(rows, page_size=p.limit, key=lambda r: r.created_at)

The cursor is opaque base64-encoded; FE just passes whatever `next_cursor` we
returned. Decoding errors → 422 validation_error.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from fastapi import Query
from pydantic import BaseModel

from app.core.errors import validation_error

T = TypeVar("T")


@dataclass
class CursorParams:
    """FastAPI dependency for cursor + limit query params."""

    cursor: str | None = None
    limit: int = 20

    def __init__(
        self,
        cursor: str | None = Query(None, description="Opaque pagination cursor"),
        limit: int = Query(20, ge=1, le=100),
    ) -> None:
        self.cursor = cursor
        self.limit = limit


def encode_cursor(value: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def decode_cursor(token: str) -> Any:
    try:
        padding = "=" * (-len(token) % 4)
        return json.loads(base64.urlsafe_b64decode(token + padding).decode())
    except Exception as exc:
        raise validation_error("cursor", f"invalid cursor: {exc}") from exc


class PaginatedResponse[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    total: int | None = None
    state: str = "ok"  # 'ok' | 'empty' | 'partial'


def paginated[T](
    rows: list[T],
    *,
    page_size: int,
    key: Callable[[T], Any] | None = None,
) -> PaginatedResponse[T]:
    """Wrap a query result into a `PaginatedResponse`.

    `rows` should be the result of a query that fetched `page_size + 1` rows
    so we can detect whether there's more.
    """
    has_more = len(rows) > page_size
    items = rows[:page_size]
    next_cursor = encode_cursor(key(items[-1])) if has_more and key and items else None
    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        state="empty" if not items else "ok",
    )
