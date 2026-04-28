"""Shared fixtures for admin/auth DB-backed unit + integration tests.

Spins up a per-test in-memory aiosqlite engine + creates only the four
admin tables (the global `Base.metadata` carries unrelated cross-domain
models with FKs to tables we don't want here). Tests that don't touch
the DB remain unaffected — only those that explicitly inject
`db_session` or `http_env` pay the setup cost.

`http_env` (Step 5) wraps the FastAPI app with an ASGI httpx client and
overrides `get_db` to point at the same in-memory engine. The fixture
also resets the rate-limiter module singletons before AND after each
test so accumulated buckets do not leak between cases.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table
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

_ADMIN_TABLES: list[Table] = [
    cast(Table, AdminUser.__table__),
    cast(Table, AdminSession.__table__),
    cast(Table, AdminPasswordReset.__table__),
    cast(Table, AdminLoginAttempt.__table__),
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


@dataclass
class HttpEnv:
    """Bundle yielded by `http_env`: the ASGI client + a sessionmaker the
    test can use to peek at DB state directly."""

    client: AsyncClient
    sessionmaker: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def http_env() -> AsyncGenerator[HttpEnv, None]:
    from app.admin.auth.rate_limiter import reset_for_tests
    from app.db.session import get_db
    from app.main import app

    reset_for_tests()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        for table in _ADMIN_TABLES:
            await conn.run_sync(table.create)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield HttpEnv(client=client, sessionmaker=sessionmaker)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        reset_for_tests()


@pytest.fixture(autouse=True)
def _admin_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some admin/auth tests exercise jwt boot-time fast-fail directly,
    but DB-backed tests benefit from a default secret to avoid each test
    setting its own."""

    monkeypatch.setenv("ADMIN_JWT_SECRET", "x" * 64)
