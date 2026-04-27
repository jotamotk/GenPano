"""Shared fixtures for admin/auth DB-backed unit tests.

Spins up a per-test in-memory aiosqlite engine + creates only the four
admin tables (the global `Base.metadata` carries unrelated cross-domain
models with FKs to tables we don't want here). Tests that don't touch
the DB remain unaffected — only those that explicitly inject
`db_session` pay the setup cost.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.admin import (
    AdminLoginAttempt,
    AdminPasswordReset,
    AdminSession,
    AdminUser,
)

_ADMIN_TABLES = [
    AdminUser.__table__,
    AdminSession.__table__,
    AdminPasswordReset.__table__,
    AdminLoginAttempt.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        for table in _ADMIN_TABLES:
            await conn.run_sync(table.create)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _admin_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some admin/auth tests exercise jwt boot-time fast-fail directly,
    but DB-backed tests benefit from a default secret to avoid each test
    setting its own."""

    monkeypatch.setenv("ADMIN_JWT_SECRET", "x" * 64)
