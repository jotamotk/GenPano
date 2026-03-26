"""
Celery 任务定义
- execute_query: 单条 Query 执行
- dispatch_batch: 批量分发 pending queries
- reset_daily_counts: 每日重置账号计数（Beat调度）
"""
from __future__ import annotations

import asyncio
import logging

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from geo_tracker.agent.captcha import CaptchaSolver
from geo_tracker.agent.executor import QueryExecutor
from geo_tracker.db.models import Query, QueryStatus, LLMResponse
from geo_tracker.pool.account_pool import AccountPool
from geo_tracker.pool.proxy_pool import ProxyPool

# 数据库 & Redis 连接（实际项目从 config 读取）
from geo_tracker.config import create_task_engine, get_task_async_session, REDIS_URL

logger = logging.getLogger(__name__)

app = Celery("geo_tracker", broker=REDIS_URL, backend=REDIS_URL)

app.conf.update(
    task_serializer   = "json",
    result_serializer = "json",
    timezone          = "UTC",
    # 失败重试：最多3次，指数退避
    task_max_retries  = 3,
    task_default_retry_delay = 60,
    # 并发数：根据账号池大小调整
    worker_concurrency = 10,
    # Beat 定时任务
    beat_schedule = {
        "reset-daily-counts": {
            "task":     "geo_tracker.tasks.celery_tasks.reset_daily_counts",
            "schedule": crontab(hour=0, minute=0),   # UTC 00:00
        },
        "dispatch-pending-queries": {
            "task":     "geo_tracker.tasks.celery_tasks.dispatch_batch",
            "schedule": crontab(minute="*/5"),        # 每5分钟扫描 pending
        },
    },
)


# ─── 单条 Query 执行任务 ──────────────────────────────────────────────────────

@app.task(bind=True, max_retries=3)
def execute_query(self, query_id: int) -> dict:
    """
    执行单条查询
    bind=True 支持 self.retry()
    """
    task_engine = create_task_engine()

    async def _run():
        async with get_task_async_session(task_engine) as db:
            query = await db.get(Query, query_id)
            if not query or query.status == QueryStatus.DONE.value:
                return {"skipped": True}

            query.status = QueryStatus.RUNNING.value
            await db.commit()

            account_pool  = AccountPool(db)
            proxy_pool    = ProxyPool(db)
            captcha_solver = CaptchaSolver()

            executor = QueryExecutor(account_pool, proxy_pool, captcha_solver)

            try:
                response: LLMResponse | None = await executor.execute(query)

                if response:
                    db.add(response)
                    query.status = QueryStatus.DONE.value
                    await db.commit()
                    logger.info(f"Query {query_id} DONE, response len={len(response.raw_text)}")
                    return {"query_id": query_id, "status": "done"}
                else:
                    query.status = QueryStatus.FAILED.value
                    query.retry_count += 1
                    await db.commit()
                    return {"query_id": query_id, "status": "failed"}

            finally:
                await captcha_solver.close()

    try:
        # Clean up any existing event loop
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.close()
        except RuntimeError:
            pass
        # Create new loop and run
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.close()
        except RuntimeError:
            pass
        # Create new loop and run
        result = asyncio.run(_run())
        return result
    except Exception as exc:
        logger.exception(f"execute_query {query_id} raised: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        asyncio.run(task_engine.dispose())


# ─── 批量分发 Pending Queries ─────────────────────────────────────────────────

@app.task(queue="celery")
def dispatch_batch(limit: int = 50) -> dict:
    """
    扫描 pending queries，分发到 execute_query
    limit: 每次最多分发条数，避免瞬间压满队列
    """
    task_engine = create_task_engine()

    async def _run():
        async with get_task_async_session(task_engine) as db:
            result = await db.execute(
                select(Query)
                .where(Query.status == QueryStatus.PENDING.value)
                .limit(limit)
            )
            queries = result.scalars().all()

            dispatched = 0
            for q in queries:
                execute_query.apply_async(
                    args=[q.id],
                    # 按 LLM 分组到不同队列，避免某家LLM阻塞其他
                    queue=f"llm_{q.target_llm}",
                )
                dispatched += 1

            logger.info(f"Dispatched {dispatched} queries")
            return {"dispatched": dispatched}

    # Clean up any existing event loop
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.close()
    except RuntimeError:
        pass
    # Create new loop and run
    try:
        return asyncio.run(_run())
    finally:
        asyncio.run(task_engine.dispose())


# ─── 每日重置账号计数 ─────────────────────────────────────────────────────────

@app.task(queue="celery")
def reset_daily_counts() -> dict:
    task_engine = create_task_engine()

    async def _run():
        async with get_task_async_session(task_engine) as db:
            pool = AccountPool(db)
            await pool.reset_daily_counts()
            return {"status": "ok"}

    # Clean up any existing event loop
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.close()
    except RuntimeError:
        pass
    # Create new loop and run
    try:
        return asyncio.run(_run())
    finally:
        asyncio.run(task_engine.dispose())
