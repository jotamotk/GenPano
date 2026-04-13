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

# ─── 火山引擎 API 配置（Analyzer 使用）──────────────────────────────────────
ARK_API_KEY = os.getenv("ARK_API_KEY", "")              # 豆包大模型 API Key
ARK_BASE_URL = os.getenv(                                # Ark API 兼容 OpenAI 协议
    "ARK_BASE_URL",
    "https://ark.cn-beijing.volces.com/api/v3",
)
ARK_MODEL = os.getenv("ARK_MODEL", "doubao-pro-32k")    # 豆包模型 ID
VOLC_NLP_API_KEY = os.getenv("VOLC_NLP_API_KEY", "")    # 火山 NLP 情感分析 API Key
VOLC_NLP_API_URL = os.getenv(                            # 火山 NLP API URL
    "VOLC_NLP_API_URL",
    "https://open.volcengineapi.com/api/v1/nlp/sentiment",
)

# 全局 engine（用于 FastAPI 等常驻服务）
engine = create_async_engine(DATABASE_URL, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_async_session():
    """全局会话（用于 FastAPI）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def create_task_engine():
    """为 Celery 任务创建独立的 engine（避免连接冲突）"""
    return create_async_engine(DATABASE_URL, pool_size=1, max_overflow=0)


@asynccontextmanager
async def get_task_async_session(task_engine):
    """Celery 任务用的会话（配合独立 engine 使用）"""
    TaskAsyncSessionLocal = async_sessionmaker(task_engine, expire_on_commit=False)
    async with TaskAsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
