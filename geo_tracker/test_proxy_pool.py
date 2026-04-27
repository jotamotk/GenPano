"""测试代理池功能"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine,from sqlalchemy.ext.asyncio import async_sessionmaker
from geo_tracker.db.models import Base,from geo_tracker.pool.proxy_pool import ProxyPool

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///geo_tracker/test_proxy.db')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SM = async_sessionmaker(engine, expire_on_commit=False)
    async with SM() as db:
        pool = ProxyPool(db)

        # 测试国内 LLM
        proxy = await pool.acquire("kimi")
        assert proxy is None, " print("✓ 国内 LLM kimi: 直连模式")

        # 测试国际 LLM
        proxy = await pool.acquire("chatgpt")
        print(f"国际 LLM chatgpt: 代理状态: {proxy.proxy_url if proxy else 'None'}")

        # 壥康检查
        health = await pool.health_check()
        print(f"代理池状态: {health}")

if __name__ == "__main__":
    asyncio.run(test())
