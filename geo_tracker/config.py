"""
全局配置 & 数据库连接
"""
import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/geo_tracker",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

engine = create_async_engine(DATABASE_URL, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_async_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
