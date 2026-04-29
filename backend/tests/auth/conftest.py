from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.user import User, UserAuthToken

_USER_TABLES: list[Table] = [
    cast(Table, User.__table__),
    cast(Table, UserAuthToken.__table__),
]


@dataclass
class UserAuthHttpEnv:
    client: AsyncClient
    sessionmaker: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def user_auth_http_env(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[UserAuthHttpEnv, None]:
    from app.db.session import get_db
    from app.main import app
    from app.user_auth.rate_limiter import reset_for_tests

    monkeypatch.setenv("USER_JWT_SECRET", "u" * 64)
    monkeypatch.setenv("USER_BASE_URL", "http://test")
    reset_for_tests()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        for table in _USER_TABLES:
            await conn.run_sync(table.create)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield UserAuthHttpEnv(client=client, sessionmaker=sessionmaker)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        reset_for_tests()
