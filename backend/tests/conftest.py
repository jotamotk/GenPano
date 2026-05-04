"""Top-level pytest fixtures shared by Phase 0+ tests.

Single combined fixture provides both `client` (httpx.AsyncClient) and
`db_session` (AsyncSession) so commits in `db_session` are visible to HTTP
requests through `client`.

Implementation note: SQLite in-memory DB is per-connection; we use a temp
file so multiple async connections (test setup + override session) see the
same DB.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from genpano_models import Base
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import _upstream_stubs  # noqa: F401  — registers upstream Tables


@dataclass
class TestEnv:
    """Combined fixture handle: HTTP client + DB session in same DB."""

    client: AsyncClient
    sessionmaker: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[TestEnv, None]:
    """Per-test combined HTTP + DB fixture."""
    monkeypatch.setenv("USER_JWT_SECRET", "u" * 64)

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        db_path = Path(tmp.name)

    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from app.db.session import get_db
    from app.main import app

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield TestEnv(client=c, sessionmaker=sessionmaker)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        db_path.unlink(missing_ok=True)  # noqa: ASYNC240 — sync os call OK in cleanup


@pytest_asyncio.fixture
async def client(env: TestEnv) -> AsyncClient:
    return env.client


@pytest_asyncio.fixture
async def db_session(env: TestEnv) -> AsyncGenerator[AsyncSession, None]:
    """Direct DB session for fixture setup. Same DB as `client`."""
    async with env.sessionmaker() as session:
        yield session
